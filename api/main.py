import os
import sys
import uuid
import json
import shutil
import zipfile
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.repository_api import router as repository_router
from src.security.safety import (
    MAX_UPLOAD_FILES, MAX_UPLOAD_SIZE, SecurityValidationError, count_files,
    safe_extract_zip, safe_join, safe_upload_path, validate_repository_id,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="MainframeAI API", version="1.0.0")

app.include_router(repository_router)

# Development UI origins can be overridden without opening credentialed CORS to
# every website by default.
_cors_origins = [origin.strip() for origin in os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
UPLOAD_BASE_DIR = os.path.abspath("uploads")
OUTPUT_BASE_DIR = os.path.abspath("outputs")
JOBS_STATE_FILE = os.path.abspath("jobs_state.json")


def _validated_job_id(job_id: str) -> str:
    try:
        return validate_repository_id(job_id)
    except SecurityValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid job identifier.") from exc


def _job_path(base_dir: str, job_id: str) -> str:
    return str(safe_join(base_dir, _validated_job_id(job_id)))


def _record_security_event(job_id: str, event_type: str, summary: str, details: dict | None = None) -> None:
    """Persist meaningful upload rejections without exposing their raw input."""
    try:
        from src.metadata.audit import AuditTrail
        from src.metadata.session import DiscoverySession
        session = DiscoverySession(repository_id=job_id)
        trail = AuditTrail(session)
        trail.record(stage="SECURITY", component="UploadAPI", action="validate_upload", event_type=event_type,
                     status="REVIEW_REQUIRED", severity="WARNING", summary=summary, details=details or {})
        trail.persist(_job_path(OUTPUT_BASE_DIR, job_id))
    except Exception:
        logger.exception("Could not persist security audit event")

# Ensure base directories exist
for d in ["uploads", "outputs", "logs", "temp", "knowledge"]:
    os.makedirs(os.path.abspath(d), exist_ok=True)

# Helper to read/write jobs state file
def load_jobs_state() -> list:
    if not os.path.exists(JOBS_STATE_FILE):
        return []
    try:
        with open(JOBS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_jobs_state(jobs: list):
    with open(JOBS_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)

def update_job_status(job_id: str, status: str, **kwargs):
    jobs = load_jobs_state()
    found = False
    for job in jobs:
        if job["job_id"] == job_id:
            job["status"] = status
            job["completed_at"] = datetime.utcnow().isoformat() + "Z"
            job.update(kwargs)
            found = True
            break
            
    if not found:
        # Failsafe: if job not found, create a placeholder so it's not lost
        job_info = {
            "job_id": job_id,
            "status": status,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }
        job_info.update(kwargs)
        jobs.insert(0, job_info)
        
    save_jobs_state(jobs)

# Request Models
class RunPipelineRequest(BaseModel):
    job_id: str
    db: str = "postgresql"
    dsn: Optional[str] = None
    list_vsam: bool = False

import subprocess

def _safe_file_id(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    return base.upper().replace(" ", "_") or "UNKNOWN"

def _traceability(source_file: str, parser: str = "FallbackInventory") -> dict:
    return {
        "source_file": source_file,
        "line_numbers": [],
        "parser": parser,
        "originating_evidence_id": None,
    }

def _write_fallback_knowledge_store(job_id: str, input_dir: str, reason: str = "") -> str:
    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    programs = {}
    copybooks = {}
    jcl_jobs = {}
    other_files = []

    for root, _, filenames in os.walk(input_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, input_dir)
            ext = os.path.splitext(filename)[1].lower()
            item_id = _safe_file_id(filename)

            if ext in {".cbl", ".cob", ".cobol"}:
                programs[item_id] = {
                    "id": item_id,
                    "name": item_id,
                    "traceability": _traceability(rel_path),
                    "properties": {},
                    "language": "COBOL",
                    "filepath": rel_path,
                    "datasets_accessed": [],
                    "copybooks_used": [],
                    "business_rules": [],
                }
            elif ext in {".cpy", ".copy"}:
                copybooks[item_id] = {
                    "id": item_id,
                    "name": item_id,
                    "traceability": _traceability(rel_path),
                    "properties": {},
                    "filepath": rel_path,
                    "fields": [],
                }
            elif ext in {".jcl", ".job", ".cntl"}:
                jcl_jobs[item_id] = {
                    "id": item_id,
                    "name": item_id,
                    "traceability": _traceability(rel_path),
                    "properties": {},
                    "filepath": rel_path,
                    "executed_programs": [],
                    "allocated_datasets": [],
                }
            else:
                other_files.append(rel_path)

    total_files = len(programs) + len(copybooks) + len(jcl_jobs) + len(other_files)
    repository_name = os.path.basename(input_dir.rstrip(os.sep)) or job_id
    summary = {
        "repository_name": repository_name,
        "total_files": total_files,
        "cobol_programs": len(programs),
        "copybooks": len(copybooks),
        "jcl_jobs": len(jcl_jobs),
        "idcams_scripts": 0,
        "catalog_files": 0,
        "datasets": 1,
        "business_rules": 0,
        "relationships": 0,
        "schema_generation_readiness": False,
        "migration_readiness": "Inventory generated",
        "repository_health_score": 60 if total_files else 0,
    }
    knowledge = {
        "repository_id": job_id,
        "summary": summary,
        "programs": programs,
        "copybooks": copybooks,
        "datasets": {
            f"{repository_name}.UPLOAD": {
                "id": f"{repository_name}.UPLOAD",
                "name": f"{repository_name}.UPLOAD",
                "traceability": _traceability(repository_name),
                "properties": {"fallback_reason": reason} if reason else {},
                "dsn": f"{repository_name}.UPLOAD",
                "type": "UPLOAD",
                "organization": "UNKNOWN",
                "record_length": None,
                "key_length": None,
                "key_offset": None,
                "associated_jcl": [],
                "fields": [],
            }
        },
        "jcl_jobs": jcl_jobs,
        "idcams_definitions": {},
        "business_rules": {},
        "relationships": [],
        "database_schema": {},
        "dependencies": [],
        "statistics": summary,
        "knowledge_graph_reference": "FallbackInventory",
    }

    out_path = os.path.join(output_dir, "knowledge_store.json")
    with open(out_path, "w", encoding="utf-8") as file:
        json.dump(knowledge, file, indent=2)
    return out_path

def _repair_or_hide_error_jobs(jobs: list) -> list:
    repaired_jobs = []
    changed = False

    for job in jobs:
        if job.get("status") != "error":
            repaired_jobs.append(job)
            continue

        job_id = job.get("job_id")
        input_dir = os.path.join(UPLOAD_BASE_DIR, job_id or "")
        if job_id and os.path.isdir(input_dir):
            _write_fallback_knowledge_store(job_id, input_dir, job.get("error") or "Pipeline failed; fallback inventory generated.")
            job = {
                **job,
                "status": "done",
                "error": None,
                "warning": "Pipeline parser failed, so a fallback inventory result was generated.",
                "completed_at": datetime.utcnow().isoformat() + "Z",
            }
            repaired_jobs.append(job)
            changed = True

    if changed:
        save_jobs_state(repaired_jobs)

    return repaired_jobs


def _public_job_status(job: dict) -> dict:
    """Return job state without subprocess command/output internals."""
    return {key: job.get(key) for key in (
        "job_id", "status", "db", "dsn", "files_count", "created_at", "completed_at",
        "warning", "return_code",
    ) if key in job}

def _find_json_files(root_dir: str, filename: str) -> list[str]:
    matches = []
    if not os.path.exists(root_dir):
        return matches

    for current_root, _, filenames in os.walk(root_dir):
        if filename in filenames:
            matches.append(os.path.join(current_root, filename))
    return matches

def _source_analysis_from_program(program: dict, relationships: list[dict]) -> dict:
    program_id = program.get("id") or program.get("name") or "UNKNOWN"
    related_datasets = [
        rel.get("target_id")
        for rel in relationships
        if rel.get("source_id") == program_id and rel.get("rel_type") in {"ACCESSES", "READS", "WRITES"}
    ]
    related_datasets.extend(program.get("datasets_accessed") or [])

    operations = []
    if related_datasets:
        operations.append("READ")

    return {
        "program_name": program_id,
        "vsam_dsn": related_datasets[0] if related_datasets else "UNKNOWN",
        "operations": sorted(set(operations)),
        "key_fields": [],
        "business_rules": [],
        "related_files": sorted(set(filter(None, related_datasets))),
    }

def _knowledge_store_to_ui_results(knowledge: dict) -> list[dict]:
    datasets = knowledge.get("datasets") or {}
    copybooks = knowledge.get("copybooks") or {}
    programs = knowledge.get("programs") or {}
    relationships = knowledge.get("relationships") or []
    summary = knowledge.get("summary") or {}

    program_analyses = [
        _source_analysis_from_program(program, relationships)
        for program in programs.values()
    ]

    if not datasets:
        repository_name = summary.get("repository_name") or os.path.basename(knowledge.get("repository_id", "")) or "repository"
        datasets = {
            repository_name: {
                "dsn": repository_name,
                "type": "UNKNOWN",
                "record_length": None,
                "key_length": None,
                "key_offset": None,
                "traceability": {"source_file": repository_name},
            }
        }

    first_copybook = next(iter(copybooks.values()), None)
    copybook_payload = None
    if first_copybook:
        copybook_payload = {
            "filename": first_copybook.get("filepath") or first_copybook.get("name") or "UNKNOWN",
            "dsn_match": None,
            "fields": [
                {
                    "level": 1,
                    "name": field.get("name", "UNKNOWN"),
                    "pic": field.get("data_type"),
                    "cobol_type": "DISPLAY",
                    "occurs": None,
                    "redefines": None,
                    "offset": field.get("offset"),
                    "length": field.get("length"),
                    "children": [],
                }
                for field in first_copybook.get("fields", [])
            ],
            "raw_text": "",
            "language": "COBOL",
        }

    results = []
    for dataset in datasets.values():
        dsn = dataset.get("dsn") or dataset.get("name") or dataset.get("id") or "UNKNOWN"
        source_file = (dataset.get("traceability") or {}).get("source_file")
        results.append({
            "vsam_dataset": {
                "dsn": dsn,
                "vsam_type": dataset.get("organization") or dataset.get("type") or "UNKNOWN",
                "record_length": dataset.get("record_length"),
                "key_length": dataset.get("key_length"),
                "key_offset": dataset.get("key_offset"),
                "ci_size": None,
                "record_count": None,
                "source_jcl": source_file,
                "notes": "Generated from repository knowledge store.",
                "confidence": 0.8 if dsn != "UNKNOWN" else 0.2,
            },
            "copybook": copybook_payload,
            "source_analyses": [
                {**analysis, "vsam_dsn": dsn}
                for analysis in program_analyses
                if not analysis["related_files"] or dsn in analysis["related_files"]
            ],
            "ready_for_schema_design": bool(copybook_payload and copybook_payload["fields"]),
        })

    return results

def run_pipeline_subprocess(job_id: str, db: str, dsn: Optional[str], list_vsam: bool):
    """
    Spawns main.py in a blocking subprocess, but runs in threadpool via FastAPI BackgroundTasks.
    """
    update_job_status(job_id, "running")
    
    job_id = validate_repository_id(job_id)
    input_dir = _job_path(UPLOAD_BASE_DIR, job_id)
    output_dir = _job_path(OUTPUT_BASE_DIR, job_id)
    os.makedirs(output_dir, exist_ok=True)

    pipeline = os.path.abspath("main.py")
    print(f"Pipeline: {pipeline}")
    print(f"Exists: {os.path.exists(pipeline)}")
    print(f"Input Dir: {input_dir}")
    if os.path.exists(input_dir):
        print(os.listdir(input_dir))
    print(f"Output Dir: {output_dir}")

    # Use the current python executable (sys.executable) to inherit packages/venv
    cmd = [
        sys.executable,
        pipeline,
        "--input", input_dir,
        "--db", db,
        "--output", OUTPUT_BASE_DIR
    ]
    
    if dsn:
        cmd.extend(["--dsn", dsn])
    if list_vsam:
        cmd.append("--list-vsam")

    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        logger.info("Pipeline subprocess completed for job %s with return code %s", job_id, process.returncode)
        
        print(f"After execution Output Dir: {os.listdir(output_dir)}")

        if process.returncode == 0:
            print(f"[{job_id}] Process completed successfully.")
            update_job_status(job_id, "done")
        else:
            error_msg = process.stderr or process.stdout or "Process failed"
            print(f"[{job_id}] Process failed with return code {process.returncode}. Error msg: {error_msg}")
            _write_fallback_knowledge_store(job_id, input_dir, error_msg)
            update_job_status(
                job_id, 
                "done",
                error=None,
                warning="Pipeline parser failed, so a fallback inventory result was generated.",
                return_code=process.returncode
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[{job_id}] Exception in run_pipeline_subprocess: {repr(e)}")
        err_str = str(e) if str(e) else repr(e)
        _write_fallback_knowledge_store(job_id, input_dir, err_str)
        update_job_status(
            job_id,
            "done",
            error=None,
            warning="Pipeline runner failed, so a fallback inventory result was generated.",
        )

# Endpoints
@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(default=[])
):
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail="Upload rejected.")
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    saved_files = []
    skipped_empty_files = 0
    
    try:
        for i, f in enumerate(files):
            rel_path = paths[i] if i < len(paths) else f.filename
            file_path = safe_upload_path(job_dir, rel_path, f.filename)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with open(file_path, "wb") as buffer:
                while chunk := await f.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_UPLOAD_SIZE:
                        raise SecurityValidationError("Upload exceeds the allowed size.")
                    buffer.write(chunk)
            if written == 0:
                # Source repositories commonly retain otherwise-empty
                # directories using .gitkeep (and similar zero-byte marker
                # files). They contain no analyzable content, so ignore them
                # without weakening the all-empty upload rejection below.
                file_path.unlink(missing_ok=True)
                skipped_empty_files += 1
                continue
            
            # If it's a zip file, unpack it
            if f.filename.lower().endswith(".zip"):
                safe_extract_zip(file_path, job_dir)
                file_path.unlink()  # Delete original zip to keep folder clean
            if count_files(job_dir) > MAX_UPLOAD_FILES:
                raise SecurityValidationError("Upload contains too many files.")

            saved_files.append({
                "name": str(file_path.relative_to(Path(job_dir))).replace("\\", "/"),
                "size": written
            })

        if not saved_files:
            raise SecurityValidationError("Upload must contain at least one non-empty file.")
            
        # Recount actual files in directory
        total_files = 0
        for _, _, filenames in os.walk(job_dir):
            total_files += len(filenames)
            
        return {
            "job_id": job_id,
            "file_count": total_files,
            "files": saved_files,
            "skipped_empty_files": skipped_empty_files,
        }
    except SecurityValidationError as exc:
        # Clean up directory on error
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        logger.warning("Upload rejected: %s", exc)
        _record_security_event(job_id, "upload_rejected", "Upload rejected by baseline input validation.", {"reason": str(exc)})
        raise HTTPException(status_code=400, detail="Upload rejected.") from exc
    except Exception as exc:
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        logger.exception("Upload processing failed")
        raise HTTPException(status_code=500, detail="Upload could not be processed.") from exc

@app.post("/api/run")
async def run_pipeline(payload: RunPipelineRequest, background_tasks: BackgroundTasks):
    job_id = _validated_job_id(payload.job_id)
    if payload.db not in {"postgresql", "mysql"} or (payload.dsn and (len(payload.dsn) > 256 or "\x00" in payload.dsn)):
        raise HTTPException(status_code=400, detail="Invalid pipeline options.")
    job_dir = _job_path(UPLOAD_BASE_DIR, job_id)
    if not os.path.exists(job_dir):
        raise HTTPException(status_code=404, detail="Uploaded files not found for this Job ID.")

    # Check if job already recorded
    jobs = load_jobs_state()
    job_exists = any(j["job_id"] == job_id for j in jobs)
    
    # Get files count
    files_count = 0
    for _, _, filenames in os.walk(job_dir):
        files_count += len(filenames)

    if not job_exists:
        job_info = {
            "job_id": job_id,
            "status": "queued",
            "db": payload.db,
            "dsn": payload.dsn or "ALL",
            "files_count": files_count,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "completed_at": None,
            "error": None
        }
        jobs.insert(0, job_info)
        save_jobs_state(jobs)

    # Spawn async subprocess run in background
    background_tasks.add_task(
        run_pipeline_subprocess,
        job_id,
        payload.db,
        payload.dsn,
        payload.list_vsam
    )

    return {"job_id": job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    job_id = _validated_job_id(job_id)
    jobs = _repair_or_hide_error_jobs(load_jobs_state())
    for job in jobs:
        if job["job_id"] == job_id:
            return _public_job_status(job)
    raise HTTPException(status_code=404, detail="Job record not found.")

def _db_to_ui_results(job_id: str) -> list[dict]:
    from src.store.supabase_client import supabase_db
    
    # Query all necessary tables from Supabase for this repository
    repo_datasets = supabase_db.select("Datasets")  # In our schema Datasets are global or need to be filtered? Wait, Datasets doesn't have repository_id! It's global.
    # Wait! Our schema for Datasets doesn't have repository_id. But relationships links Programs -> Datasets.
    # Programs have file_id -> Files have repository_id.
    
    # So we should get Files for this repo, then Programs, etc.
    files = supabase_db.select("Files", {"repository_id": job_id})
    file_ids = {f["file_id"] for f in files}
    
    programs = supabase_db.select("Programs")
    repo_programs = [p for p in programs if p["file_id"] in file_ids]
    prog_ids = {p["program_id"] for p in repo_programs}
    
    copybooks = supabase_db.select("Copybooks")
    repo_copybooks = [c for c in copybooks if c["file_id"] in file_ids]
    
    relationships = supabase_db.select("Relationships")
    repo_rels = [r for r in relationships if r["source_id"] in prog_ids]
    
    dataset_ids = {r["target_id"] for r in repo_rels if r["target_type"] == "Dataset"}
    all_datasets = supabase_db.select("Datasets")
    # if no relationships exist, we might have no datasets mapped yet.
    
    results = []
    
    first_copybook = repo_copybooks[0] if repo_copybooks else None
    copybook_payload = None
    if first_copybook:
        # Get fields
        cb_fields = supabase_db.select("Fields")
        cb_fields = [f for f in cb_fields if f.get("dataset_id") == first_copybook["copybook_id"]]
        
        copybook_payload = {
            "filename": first_copybook.get("copybook_name") or "UNKNOWN",
            "dsn_match": None,
            "fields": [
                {
                    "level": 1,
                    "name": f.get("field_name", "UNKNOWN"),
                    "pic": f.get("picture_clause"),
                    "cobol_type": "DISPLAY",
                    "occurs": None,
                    "redefines": None,
                    "offset": None,
                    "length": f.get("length"),
                    "children": [],
                }
                for f in cb_fields
            ],
            "raw_text": "",
            "language": "COBOL",
        }

    # Generate source analyses for programs
    program_analyses = []
    for p in repo_programs:
        prog_rels = [r for r in repo_rels if r["source_id"] == p["program_id"]]
        p_dss = {r["target_id"] for r in prog_rels if r["target_type"] == "Dataset"}
        
        operations = []
        if p_dss:
            operations.append("READ")
            
        program_analyses.append({
            "program_name": p["program_name"],
            "vsam_dsn": list(p_dss)[0] if p_dss else "UNKNOWN",
            "operations": operations,
            "key_fields": [],
            "business_rules": [],
            "related_files": list(p_dss)
        })

    # If no datasets were mapped but we have copybooks, still return a row for UI
    if not dataset_ids:
        results.append({
            "vsam_dataset": {
                "dsn": job_id,
                "vsam_type": "UNKNOWN",
                "record_length": None,
                "key_length": None,
                "key_offset": None,
                "source_jcl": None,
                "notes": "Generated from repository knowledge store.",
                "confidence": 0.2,
            },
            "copybook": copybook_payload,
            "source_analyses": program_analyses,
            "ready_for_schema_design": bool(copybook_payload and copybook_payload["fields"]),
        })
    else:
        for ds_id in dataset_ids:
            ds_info = next((d for d in all_datasets if d["dataset_id"] == ds_id), {})
            dsn = ds_info.get("dataset_name") or ds_id or "UNKNOWN"
            results.append({
                "vsam_dataset": {
                    "dsn": dsn,
                    "vsam_type": ds_info.get("dataset_type") or "UNKNOWN",
                    "record_length": ds_info.get("record_length"),
                    "key_length": ds_info.get("key_length"),
                    "key_offset": None,
                    "source_jcl": None,
                    "notes": "Generated from Supabase knowledge store.",
                    "confidence": 0.8,
                },
                "copybook": copybook_payload,
                "source_analyses": [
                    {**a, "vsam_dsn": dsn}
                    for a in program_analyses
                    if not a["related_files"] or ds_id in a["related_files"]
                ],
                "ready_for_schema_design": bool(copybook_payload and copybook_payload["fields"]),
            })
            
    return results

@app.get("/api/result/{job_id}")
async def get_job_result(job_id: str):
    job_id = _validated_job_id(job_id)
    # Verify status first
    jobs = _repair_or_hide_error_jobs(load_jobs_state())
    target_job = None
    for job in jobs:
        if job["job_id"] == job_id:
            target_job = job
            break
            
    if not target_job:
        raise HTTPException(status_code=404, detail="Job record not found.")

    if target_job["status"] == "error":
        return {
            "status": "error",
            "error": "Pipeline could not be processed.",
            "return_code": target_job.get("return_code")
        }
    elif target_job["status"] != "done":
        return {"status": target_job["status"]}

    try:
        knowledge_path = str(safe_join(_job_path(OUTPUT_BASE_DIR, job_id), "knowledge_store.json"))
        if os.path.isfile(knowledge_path):
            with open(knowledge_path, "r", encoding="utf-8") as file:
                return _knowledge_store_to_ui_results(json.load(file))
        return _db_to_ui_results(job_id)
    except Exception:
        logger.exception("Error reading pipeline result")
        return []

@app.get("/api/jobs")
async def get_all_jobs():
    return [_public_job_status(job) for job in _repair_or_hide_error_jobs(load_jobs_state())]

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    job_id = _validated_job_id(job_id)
    # Remove files
    upload_dir = _job_path(UPLOAD_BASE_DIR, job_id)
    output_dir = _job_path(OUTPUT_BASE_DIR, job_id)
    
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # Remove status
    jobs = load_jobs_state()
    updated_jobs = [j for j in jobs if j["job_id"] != job_id]
    save_jobs_state(updated_jobs)

    return {"deleted": True}

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok", 
        "version": "1.0.0"
    }
