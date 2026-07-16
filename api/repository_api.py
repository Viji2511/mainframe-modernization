import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.models.knowledge_store import RepositoryKnowledge
from src.agents.modernization_assistant import ModernizationAssistant

router = APIRouter(prefix="/api/repository", tags=["Repository"])

OUTPUT_BASE_DIR = os.path.abspath("outputs")
UPLOAD_BASE_DIR = os.path.abspath("uploads")

def _parse_copybook_fields(content: str) -> list[dict]:
    import re
    fields = []
    pattern = re.compile(r"^\s*(\d{2})\s+([A-Z0-9_-]+)(?:\s+PIC\s+([A-Z0-9()VXS9+\-.]+))?", re.IGNORECASE)
    for line in content.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        name = match.group(2).upper()
        pic = match.group(3)
        fields.append({
            "name": name,
            "data_type": pic.upper() if pic else "GROUP",
            "length": None,
            "offset": None,
            "decimals": None,
            "is_key": any(token in name for token in ("ID", "KEY", "NUM", "NO")),
        })
    return fields

def _augment_store_from_uploads(repo_id: str, store: dict) -> dict:
    upload_dir = os.path.join(UPLOAD_BASE_DIR, repo_id)
    copybooks = store.get("copybooks") or {}
    if not os.path.isdir(upload_dir) or not copybooks:
        return store

    for copybook in copybooks.values():
        if copybook.get("fields"):
            continue
        filepath = copybook.get("filepath") or copybook.get("traceability", {}).get("source_file")
        if not filepath:
            continue
        source_path = os.path.join(upload_dir, filepath)
        if not os.path.exists(source_path):
            matches = [
                os.path.join(root, filename)
                for root, _, filenames in os.walk(upload_dir)
                for filename in filenames
                if filename.upper() == os.path.basename(filepath).upper()
            ]
            source_path = matches[0] if matches else source_path
        if not os.path.exists(source_path):
            continue
        try:
            with open(source_path, "r", encoding="utf-8", errors="replace") as file:
                copybook["fields"] = _parse_copybook_fields(file.read())
        except Exception:
            continue

    return store

def _normalize_summary(store: dict, repo_id: str) -> dict:
    summary = store.get("summary") or {}
    programs = store.get("programs") or {}
    copybooks = store.get("copybooks") or {}
    datasets = store.get("datasets") or {}
    jcl_jobs = store.get("jcl_jobs") or {}
    relationships = store.get("relationships") or []
    business_rules = store.get("business_rules") or {}

    total_files = (
        len(programs)
        + len(copybooks)
        + len(jcl_jobs)
        + len(store.get("idcams_definitions") or {})
        + len(store.get("catalog_files") or {})
    )
    if summary.get("total_files"):
        total_files = max(total_files, summary.get("total_files", 0))

    has_schema_inputs = bool(copybooks)
    has_dataset_mapping = bool(datasets)
    has_relationships = bool(relationships)

    score = 20
    if total_files:
        score += 15
    if has_schema_inputs:
        score += 20
    if programs:
        score += 15
    if jcl_jobs:
        score += 10
    if has_dataset_mapping:
        score += 10
    if has_relationships:
        score += 10
    score = min(score, 100)

    if has_dataset_mapping and has_schema_inputs and (programs or jcl_jobs):
        readiness = "Ready for modernization review"
    elif has_schema_inputs and not has_dataset_mapping:
        readiness = "Copybooks inventoried - upload JCL, LISTCAT, or COBOL to map datasets"
    elif has_dataset_mapping:
        readiness = "Datasets inventoried - add copybooks for schema design"
    elif total_files:
        readiness = "Inventory complete - more mainframe context needed"
    else:
        readiness = "No repository artifacts found"

    normalized = {
        **summary,
        "repository_name": summary.get("repository_name") or os.path.basename(str(store.get("repository_id") or repo_id)) or repo_id,
        "total_files": total_files,
        "cobol_programs": len(programs),
        "copybooks": len(copybooks),
        "jcl_jobs": len(jcl_jobs),
        "idcams_scripts": len(store.get("idcams_definitions") or {}),
        "catalog_files": summary.get("catalog_files", 0),
        "datasets": len(datasets),
        "business_rules": len(business_rules),
        "relationships": len(relationships),
        "schema_generation_readiness": has_schema_inputs and has_dataset_mapping,
        "migration_readiness": readiness,
        "repository_health_score": score,
    }
    return normalized

def _local_assistant_response(query: str, store: dict) -> str:
    query_upper = query.upper()
    summary = _normalize_summary(store, str(store.get("repository_id") or "repository"))
    programs = store.get("programs") or {}
    copybooks = store.get("copybooks") or {}
    datasets = store.get("datasets") or {}
    relationships = store.get("relationships") or []

    for copybook_id, copybook in copybooks.items():
        filepath = str(copybook.get("filepath") or copybook.get("traceability", {}).get("source_file") or "")
        if copybook_id.upper() in query_upper or filepath.upper() in query_upper:
            field_count = len(copybook.get("fields") or [])
            return (
                f"{copybook_id} is a copybook artifact from {filepath or 'an uploaded source file'}.\n\n"
                f"Fields parsed: {field_count}.\n"
                f"Linked datasets: none detected yet.\n\n"
                "To complete dataset mapping, upload the COBOL programs, JCL, or LISTCAT output that references this copybook."
            )

    for program_id, program in programs.items():
        if program_id.upper() in query_upper:
            datasets_accessed = program.get("datasets_accessed") or []
            copybooks_used = program.get("copybooks_used") or []
            return (
                f"{program_id} is a {program.get('language', 'mainframe')} program at {program.get('filepath')}.\n\n"
                f"Datasets accessed: {', '.join(datasets_accessed) if datasets_accessed else 'none detected'}.\n"
                f"Copybooks used: {', '.join(copybooks_used) if copybooks_used else 'none detected'}."
            )

    if "READINESS" in query_upper or "HEALTH" in query_upper or "SUMMARY" in query_upper:
        return (
            f"Repository health score is {summary['repository_health_score']}/100.\n"
            f"Migration readiness: {summary['migration_readiness']}.\n\n"
            f"Inventory: {summary['total_files']} files, {summary['cobol_programs']} COBOL programs, "
            f"{summary['copybooks']} copybooks, {summary['jcl_jobs']} JCL jobs, "
            f"{summary['datasets']} datasets, and {summary['relationships']} relationships."
        )

    if datasets:
        dataset_names = ", ".join(list(datasets.keys())[:10])
    else:
        dataset_names = "none detected"

    return (
        f"I can answer from the local Repository Knowledge Store.\n\n"
        f"Health score: {summary['repository_health_score']}/100.\n"
        f"Migration readiness: {summary['migration_readiness']}.\n"
        f"Known datasets: {dataset_names}.\n"
        f"Relationships detected: {len(relationships)}."
    )

def get_knowledge_store(repo_id: str) -> dict:
    store_path = os.path.join(OUTPUT_BASE_DIR, repo_id, "knowledge_store.json")
    if not os.path.exists(store_path):
        raise HTTPException(status_code=404, detail="Repository Knowledge Store not found")
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            return _augment_store_from_uploads(repo_id, json.load(f))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load knowledge store: {e}")

@router.get("/{id}/summary")
async def get_summary(id: str):
    store = get_knowledge_store(id)
    summary = _normalize_summary(store, id)
    return {
        "repository_id": store.get("repository_id"),
        "repository_name": store.get("repository_name") or summary.get("repository_name") or id,
        "statistics": summary
    }

@router.get("/{id}/structure")
async def get_structure(id: str):
    store = get_knowledge_store(id)
    return {
        "programs": store.get("programs", {}),
        "copybooks": store.get("copybooks", {})
    }

@router.get("/{id}/datasets")
async def get_datasets(id: str):
    store = get_knowledge_store(id)
    return store.get("datasets", {})

@router.get("/{id}/relationships")
async def get_relationships(id: str):
    store = get_knowledge_store(id)
    return store.get("relationships", [])

@router.get("/{id}/schema")
async def get_schema(id: str):
    store = get_knowledge_store(id)
    return {
        "ready_for_generation": store.get("summary", {}).get("schema_generation_readiness", False),
        "database_schema": store.get("database_schema", {})
    }

class ChatRequest(BaseModel):
    query: str

@router.post("/{id}/chat")
async def chat_with_assistant(id: str, request: ChatRequest):
    store_dict = get_knowledge_store(id)
    try:
        knowledge_store = RepositoryKnowledge(**store_dict)
        assistant = ModernizationAssistant(knowledge_store)
        response = assistant.chat(request.query)
        if response:
            return {"response": response}
    except Exception:
        pass

    return {"response": _local_assistant_response(request.query, store_dict)}
