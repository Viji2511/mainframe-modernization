import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.agents.modernization_assistant import ModernizationAssistant
from src.store.supabase_client import supabase_db

router = APIRouter(prefix="/api/repository", tags=["Repository"])

def _calculate_health_score(stats: dict) -> dict:
    score = 20
    if stats["total_files"] > 0: score += 15
    if stats["copybooks"] > 0: score += 20
    if stats["cobol_programs"] > 0: score += 15
    if stats["jcl_jobs"] > 0: score += 10
    if stats["datasets"] > 0: score += 10
    if stats["relationships"] > 0: score += 10
    score = min(score, 100)
    
    if stats["datasets"] > 0 and stats["copybooks"] > 0 and (stats["cobol_programs"] > 0 or stats["jcl_jobs"] > 0):
        readiness = "Ready for modernization review"
    elif stats["copybooks"] > 0 and stats["datasets"] == 0:
        readiness = "Copybooks inventoried - upload JCL, LISTCAT, or COBOL to map datasets"
    elif stats["datasets"] > 0:
        readiness = "Datasets inventoried - add copybooks for schema design"
    elif stats["total_files"] > 0:
        readiness = "Inventory complete - more mainframe context needed"
    else:
        readiness = "No repository artifacts found"
        
    return {
        "repository_health_score": score,
        "migration_readiness": readiness,
        "schema_generation_readiness": stats["copybooks"] > 0 and stats["datasets"] > 0
    }

@router.get("/{id}/summary")
async def get_summary(id: str):
    # Fetch from Supabase
    repo = supabase_db.select("Repository", {"repository_id": id})
    if not repo:
        repo_name = id
    else:
        repo_name = repo[0].get("repository_name", id)

    files = supabase_db.select("Files", {"repository_id": id})
    progs = supabase_db.select("Programs")
    cbs = supabase_db.select("Copybooks")
    dss = supabase_db.select("Datasets")
    rels = supabase_db.select("Relationships")
    brs = supabase_db.select("BusinessRules")

    jcl_count = sum(1 for f in files if f.get("artifact_type") == "JCL")
    idcams_count = sum(1 for f in files if f.get("artifact_type") == "IDCAMS")
    catalog_count = sum(1 for f in files if f.get("artifact_type") == "CATALOG")

    stats = {
        "repository_name": repo_name,
        "total_files": len(files),
        "cobol_programs": len(progs),
        "copybooks": len(cbs),
        "jcl_jobs": jcl_count,
        "idcams_scripts": idcams_count,
        "catalog_files": catalog_count,
        "datasets": len(dss),
        "business_rules": len(brs),
        "relationships": len(rels),
    }
    health = _calculate_health_score(stats)
    stats.update(health)

    return {
        "repository_id": id,
        "repository_name": repo_name,
        "statistics": stats
    }

@router.get("/{id}/structure")
async def get_structure(id: str):
    files = supabase_db.select("Files", {"repository_id": id})
    file_map = {f["file_id"]: f for f in files}
    
    progs = supabase_db.select("Programs")
    cbs = supabase_db.select("Copybooks")
    rels = supabase_db.select("Relationships")
    
    programs_dict = {}
    for p in progs:
        if p["file_id"] not in file_map: continue
        f_info = file_map[p["file_id"]]
        
        # Find relationships
        p_rels = [r for r in rels if r["source_id"] == p["program_id"]]
        datasets_accessed = [r["target_id"] for r in p_rels if r["target_type"] == "Dataset"]
        copybooks_used = [r["target_id"] for r in p_rels if r["target_type"] == "Copybook"]
        
        programs_dict[p["program_id"]] = {
            "id": p["program_id"],
            "name": p["program_name"],
            "traceability": {"source_file": f_info.get("file_name", p["program_name"])},
            "filepath": f_info.get("file_name", p["program_name"]),
            "language": "COBOL",
            "datasets_accessed": datasets_accessed,
            "copybooks_used": copybooks_used
        }
        
    copybooks_dict = {}
    for c in cbs:
        if c["file_id"] not in file_map: continue
        f_info = file_map[c["file_id"]]
        
        # In the real system, fields would be fetched if needed by UI structure, but UI might just need basic info.
        # Let's fetch fields just in case.
        fields = supabase_db.select("Fields", {"dataset_id": c["copybook_id"]})
        
        copybooks_dict[c["copybook_id"]] = {
            "id": c["copybook_id"],
            "name": c["copybook_name"],
            "traceability": {"source_file": f_info.get("file_name", c["copybook_name"])},
            "filepath": f_info.get("file_name", c["copybook_name"]),
            "fields": [
                {
                    "name": f.get("field_name", ""),
                    "data_type": f.get("picture_clause", "GROUP")
                } for f in fields
            ]
        }
    
    return {
        "programs": programs_dict,
        "copybooks": copybooks_dict
    }

@router.get("/{id}/datasets")
async def get_datasets(id: str):
    dss = supabase_db.select("Datasets")
    return {ds["dataset_id"]: ds for ds in dss}

@router.get("/{id}/relationships")
async def get_relationships(id: str):
    rels = supabase_db.select("Relationships")
    return rels

@router.get("/{id}/schema")
async def get_schema(id: str):
    cbs = supabase_db.select("Copybooks")
    dss = supabase_db.select("Datasets")
    schemas = supabase_db.select("GeneratedSchema")
    
    schema_dict = {
        "dialect": "postgresql",
        "tables": {},
        "relationships": [],
        "ddl": "\n\n".join(s["ddl"] for s in schemas)
    }
    
    return {
        "ready_for_generation": len(cbs) > 0 and len(dss) > 0,
        "database_schema": schema_dict
    }

class ChatRequest(BaseModel):
    query: str

@router.post("/{id}/chat")
async def chat_with_assistant(id: str, request: ChatRequest):
    try:
        assistant = ModernizationAssistant(repository_id=id)
        response = assistant.chat(request.query)
        if response:
            return {"response": response}
    except Exception as e:
        return {"response": f"Error interacting with Modernization Assistant: {str(e)}"}
