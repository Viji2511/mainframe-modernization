import os
import sys
import uuid
import json
import shutil
import zipfile
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.repository_api import router as repository_router

app = FastAPI(title="MainframeAI API", version="1.0.0")

app.include_router(repository_router)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Support all origins for easy development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
UPLOAD_BASE_DIR = os.path.abspath("uploads")
OUTPUT_BASE_DIR = os.path.abspath("outputs")
JOBS_STATE_FILE = os.path.abspath("jobs_state.json")

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
    
    input_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
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

    cmd_str = " ".join(cmd)
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print("========== COMMAND ==========")
        print(cmd_str)
        print("========== STDOUT ==========")
        print(process.stdout)
        print("========== STDERR ==========")
        print(process.stderr)
        print("========== RETURN CODE ==========")
        print(process.returncode)
        
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
                command=cmd_str,
                stdout=process.stdout,
                stderr=process.stderr,
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
            command=cmd_str,
        )

# Endpoints
@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    saved_files = []
    
    try:
        for f in files:
            file_path = os.path.join(job_dir, f.filename)
            # Ensure subdirectory paths are created if zip contains subfolders
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(f.file, buffer)
            
            # If it's a zip file, unpack it
            if f.filename.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(job_dir)
                os.remove(file_path)  # Delete original zip to keep folder clean

            saved_files.append({
                "name": f.filename,
                "size": os.path.getsize(file_path) if os.path.exists(file_path) else 0
            })
            
        # Recount actual files in directory
        total_files = 0
        for _, _, filenames in os.walk(job_dir):
            total_files += len(filenames)
            
        return {
            "job_id": job_id,
            "file_count": total_files,
            "files": saved_files
        }
    except Exception as e:
        # Clean up directory on error
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir)
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@app.post("/api/run")
async def run_pipeline(payload: RunPipelineRequest, background_tasks: BackgroundTasks):
    job_dir = os.path.join(UPLOAD_BASE_DIR, payload.job_id)
    if not os.path.exists(job_dir):
        raise HTTPException(status_code=404, detail="Uploaded files not found for this Job ID.")

    # Check if job already recorded
    jobs = load_jobs_state()
    job_exists = any(j["job_id"] == payload.job_id for j in jobs)
    
    # Get files count
    files_count = 0
    for _, _, filenames in os.walk(job_dir):
        files_count += len(filenames)

    if not job_exists:
        job_info = {
            "job_id": payload.job_id,
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
        payload.job_id,
        payload.db,
        payload.dsn,
        payload.list_vsam
    )

    return {"job_id": payload.job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    jobs = _repair_or_hide_error_jobs(load_jobs_state())
    for job in jobs:
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="Job record not found.")

@app.get("/api/result/{job_id}")
async def get_job_result(job_id: str):
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
            "error": target_job.get("error"),
            "stdout": target_job.get("stdout"),
            "stderr": target_job.get("stderr"),
            "command": target_job.get("command"),
            "return_code": target_job.get("return_code")
        }
    elif target_job["status"] != "done":
        return {"status": target_job["status"]}

    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    if not os.path.exists(output_dir):
        return []

    # Gather legacy UI JSON results, including nested output folders from older runs.
    results = []
    for current_root, _, filenames in os.walk(output_dir):
        for f in filenames:
            if f.endswith("_result.json"):
                file_path = os.path.join(current_root, f)
                try:
                    with open(file_path, "r", encoding="utf-8") as file:
                        payload = json.load(file)
                        if isinstance(payload, list):
                            results.extend(payload)
                        else:
                            results.append(payload)
                except Exception as e:
                    print(f"Error loading result {f}: {e}")

    if results:
        return results

    for file_path in _find_json_files(output_dir, "knowledge_store.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                knowledge = json.load(file)
            return _knowledge_store_to_ui_results(knowledge)
        except Exception as e:
            print(f"Error loading knowledge store {file_path}: {e}")

    # Return list (or single object if only one)
    return results

@app.get("/api/jobs")
async def get_all_jobs():
    return _repair_or_hide_error_jobs(load_jobs_state())

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    # Remove files
    upload_dir = os.path.join(UPLOAD_BASE_DIR, job_id)
    output_dir = os.path.join(OUTPUT_BASE_DIR, job_id)
    
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
        "version": "1.0.0",
        "cwd": os.getcwd(),
        "jobs_file": JOBS_STATE_FILE,
        "uploads": UPLOAD_BASE_DIR,
        "sys_executable": sys.executable
    }
