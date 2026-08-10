import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.agents.modernization_assistant import ModernizationAssistant
from src.store.supabase_client import supabase_db
import re

def _calculate_pic_length(pic_str):
    if not pic_str or pic_str == "GROUP":
        return 0
    pic_str = pic_str.upper().strip()
    digits = 0
    if "V" in pic_str:
        p1, p2 = pic_str.split("V", 1)
        m1 = re.search(r'9\((\d+)\)', p1)
        d1 = int(m1.group(1)) if m1 else p1.count('9')
        m2 = re.search(r'9\((\d+)\)', p2)
        d2 = int(m2.group(1)) if m2 else p2.count('9')
        digits = d1 + d2
    elif "9" in pic_str:
        m = re.search(r'9\((\d+)\)', pic_str)
        digits = int(m.group(1)) if m else pic_str.count('9')
        
    if "COMP-3" in pic_str or "PACKED-DECIMAL" in pic_str:
        import math
        return math.ceil((digits + 1) / 2)
    elif "COMP-1" in pic_str:
        return 4
    elif "COMP-2" in pic_str:
        return 8
    elif "COMP" in pic_str or "BINARY" in pic_str:
        if digits <= 4: return 2
        if digits <= 9: return 4
        return 8
        
    if "X" in pic_str or "A" in pic_str:
        m = re.search(r'[XA]\((\d+)\)', pic_str)
        return int(m.group(1)) if m else pic_str.count('X') or pic_str.count('A') or 1
        
    if digits > 0:
        return digits
    return 0

def _parse_pic_to_sql(pic_str):
    if not pic_str or pic_str == "GROUP":
        return None
    pic_str = pic_str.upper().strip()
    
    if pic_str.startswith("X") or "X(" in pic_str or pic_str.startswith("A") or "A(" in pic_str:
        m = re.search(r'[XA]\((\d+)\)', pic_str)
        if m:
            return f"VARCHAR({m.group(1)})"
        return "VARCHAR(1)"
        
    elif "9" in pic_str or "S9" in pic_str or "V" in pic_str or "COMP" in pic_str or "BINARY" in pic_str:
        if "V" in pic_str:
            parts = pic_str.split("V")
            p1, p2 = parts[0], parts[1]
            m1 = re.search(r'9\((\d+)\)', p1)
            l1 = int(m1.group(1)) if m1 else p1.count('9')
            m2 = re.search(r'9\((\d+)\)', p2)
            l2 = int(m2.group(1)) if m2 else p2.count('9')
            total = l1 + l2
            return f"DECIMAL({total}, {l2})"
        else:
            m = re.search(r'9\((\d+)\)', pic_str)
            l = int(m.group(1)) if m else pic_str.count('9')
            if l == 0:
                l = 4
            if l <= 4:
                return "SMALLINT"
            elif l <= 9:
                return "INTEGER"
            else:
                return "BIGINT"
    
    return "VARCHAR(255)"

def _flatten_records(records, prefix="", current_offset=0, hierarchy=None, parent_occurs=None, parent_redefines=None):
    if hierarchy is None:
        hierarchy = []
    columns = []
    start_offset_ref = current_offset
    
    for r in records:
        name = r.get("name", "").replace("-", "_")
        col_name = f"{prefix}_{name}" if prefix else name
        pic = r.get("pic")
        children = r.get("children", [])
        redefines = r.get("redefines") or parent_redefines
        occurs = r.get("occurs") or parent_occurs
        
        length = r.get("length")
        if not length:
            length = _calculate_pic_length(pic)
            
        status = "OK"
        if redefines:
            status = "REVIEW_REQUIRED: REDEFINES"
        if occurs:
            status = "TRANSFORMATION_REQUIRED: OCCURS"
            
        if not children and pic and pic != "GROUP" and name != "FILLER":
            sql_type = _parse_pic_to_sql(pic)
            cols = {
                "name": col_name,
                "sql_type": sql_type,
                "source_field": r.get("name"),
                "primary_key": False,
                "offset": current_offset,
                "length": length,
                "source_hierarchy": ".".join(hierarchy),
                "schema_status": status,
                "pic": pic
            }
            if redefines:
                cols["redefines_target"] = redefines
            if occurs:
                cols["occurs"] = occurs
            columns.append(cols)
        
        child_len = 0
        if children:
            child_cols, child_len = _flatten_records(children, prefix=col_name, current_offset=current_offset, hierarchy=hierarchy + [r.get("name", "")], parent_occurs=occurs, parent_redefines=redefines)
            columns.extend(child_cols)
            if not length:
                length = child_len
                
        if not redefines:
            if occurs:
                m = re.search(r'\d+', str(occurs))
                if m:
                    length = length * int(m.group(0))
            current_offset += length
            
    return columns, current_offset - start_offset_ref

def _generate_schema_from_structure(artifact_id, artifact_struct, artifact_datasets=None):
    records = []
    if "structure" in artifact_struct and isinstance(artifact_struct["structure"], dict):
        records = artifact_struct["structure"].get("records", [])
    elif "records" in artifact_struct:
        records = artifact_struct.get("records", [])
        
    if not records:
        return None
        
    columns, _ = _flatten_records(records)
    if not columns:
        return None
        
    # PK Resolution via VSAM datasets
    if artifact_datasets:
        for ds in artifact_datasets:
            key_offset = ds.get("key_offset")
            key_length = ds.get("key_length")
            if key_offset is not None and key_length is not None:
                matched_cols = [c for c in columns if c["offset"] == key_offset and c["length"] == key_length]
                if len(matched_cols) == 1:
                    matched_cols[0]["primary_key"] = True
                    matched_cols[0]["key_evidence"] = {
                        "source_dataset": ds.get("dataset_name"),
                        "source_type": "VSAM_CATALOG",
                        "reason": f"Matched by offset {key_offset} and length {key_length}"
                    }
                elif len(matched_cols) > 1:
                    for c in matched_cols:
                        c["key_status"] = "AMBIGUOUS"
                else:
                    for c in columns:
                        if c["offset"] == key_offset:
                            c["key_status"] = "UNRESOLVED_LENGTH_MISMATCH"
        
    return {
        "schema_type": "RECORD_SCHEMA",
        "table_name": artifact_id.upper(),
        "columns": columns
    }

def _generate_cobol_schema(artifact_id, artifact_struct, deps):
    info = artifact_struct.get("general_information", {})
    meta = artifact_struct.get("metadata", {})
    comp = artifact_struct.get("components", {})
    struct = artifact_struct.get("structure", {})
    
    # Try multiple places for lists depending on parser version
    data_structs = struct.get("data_structures", [])
    if not data_structs and struct.get("program"):
        pass # Handle if needed
        
    ds = deps.get("datasets", [])
    if not ds:
        ds = info.get("datasets_accessed", []) or meta.get("datasets_accessed", []) or []
        
    cbs = deps.get("copybooks", [])
    if not cbs:
        cbs = info.get("copybooks", []) or meta.get("copybooks", []) or comp.get("copybooks", []) or []
        
    calls = deps.get("calledPrograms", [])
    if not calls:
        calls = info.get("called_programs", []) or meta.get("called_programs", []) or []

    return {
        "schema_type": "PROGRAM_SCHEMA",
        "program_name": info.get("program_name") or artifact_id.upper(),
        "data_structures": data_structs,
        "datasets": ds,
        "copybooks": cbs,
        "called_programs": calls
    }

def _generate_jcl_schema(artifact_id, artifact_struct):
    job_struct = artifact_struct.get("structure", {}).get("job", {})
    return {
        "schema_type": "JOB_SCHEMA",
        "job_name": artifact_id.upper(),
        "steps": job_struct.get("steps", [])
    }

def _generate_idcams_schema(artifact_id, artifact_struct):
    info = artifact_struct.get("general_information", {}) or artifact_struct.get("metadata", {}) or artifact_struct
    return {
        "schema_type": "DATASET_SCHEMA",
        "dataset_name": info.get("dataset_name") or artifact_struct.get("dataset_name", artifact_id),
        "organization": info.get("organization") or artifact_struct.get("organization"),
        "key_length": info.get("key_length") or artifact_struct.get("key_length"),
        "key_offset": info.get("key_offset") or artifact_struct.get("key_offset"),
        "record_length": info.get("record_length") or artifact_struct.get("record_length")
    }

def _generate_dataset_schema(artifact_id, ds_row):
    info = ds_row.get("general_information", {}) or ds_row.get("metadata", {}) or ds_row
    return {
        "schema_type": "DATASET_SCHEMA",
        "dataset_name": info.get("dataset_name") or ds_row.get("dataset_name", artifact_id),
        "organization": info.get("organization") or ds_row.get("organization"),
        "key_length": info.get("key_length") or ds_row.get("key_length"),
        "key_offset": info.get("key_offset") or ds_row.get("key_offset"),
        "record_length": info.get("record_length") or ds_row.get("record_length")
    }

router = APIRouter(prefix="/api/repository", tags=["Repository"])


def _load_repository_knowledge(repository_id: str) -> dict | None:
    """Load the pipeline's repository-scoped store before using shared DB tables."""
    output_root = os.path.abspath(os.environ.get("OUTPUT_DIR", "outputs"))
    path = os.path.join(output_root, repository_id, "knowledge_store.json")
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _knowledge_structure(knowledge: dict) -> dict:
    canonical = knowledge.get("canonical_structures") or {}
    if canonical:
        grouped = {"programs": {}, "copybooks": {}, "jcl_jobs": {}, "idcams_definitions": {}, "datasets": {}}
        type_to_group = {
            "COBOL": "programs", "COPYBOOK": "copybooks", "JCL": "jcl_jobs",
            "IDCAMS": "idcams_definitions", "DATASET": "datasets",
        }
        for artifact_id, structure in canonical.items():
            group = type_to_group.get((structure.get("artifact_type") or "").upper())
            if group:
                grouped[group][structure.get("id") or artifact_id] = structure
        return grouped
    return {
        "programs": knowledge.get("programs") or {},
        "copybooks": knowledge.get("copybooks") or {},
        "jcl_jobs": knowledge.get("jcl_jobs") or {},
        "idcams_definitions": knowledge.get("idcams_definitions") or {},
        "datasets": knowledge.get("datasets") or {},
    }

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
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        stats = knowledge.get("summary") or {}
        stats.update(_calculate_health_score({
            "total_files": stats.get("total_files", 0),
            "copybooks": stats.get("copybooks", 0),
            "cobol_programs": stats.get("cobol_programs", 0),
            "jcl_jobs": stats.get("jcl_jobs", 0),
            "datasets": stats.get("datasets", 0),
            "relationships": stats.get("relationships", 0),
        }))
        return {
            "repository_id": id,
            "repository_name": stats.get("repository_name", id),
            "statistics": stats,
        }

    # Fetch from Supabase
    repo = supabase_db.select("Repository", {"repository_id": id})
    if not repo:
        repo_name = id
    else:
        repo_name = repo[0].get("repository_name", id)

    files = supabase_db.select("Files", {"repository_id": id})
    file_ids = {file.get("file_id") for file in files}
    progs = [p for p in supabase_db.select("Programs") if p.get("file_id") in file_ids]
    cbs = [c for c in supabase_db.select("Copybooks") if c.get("file_id") in file_ids]
    rels = supabase_db.select("Relationships")
    brs = supabase_db.select("BusinessRules")

    program_ids = {program.get("program_id") for program in progs}
    source_ids = program_ids | {
        os.path.splitext(file.get("filename", ""))[0].upper() for file in files
    }
    rels = [relationship for relationship in rels if relationship.get("source_id") in source_ids]
    dataset_ids = {relationship.get("target_id") for relationship in rels if relationship.get("target_type") == "Dataset"}
    dss = [dataset for dataset in supabase_db.select("Datasets") if dataset.get("dataset_id") in dataset_ids]
    brs = [rule for rule in brs if rule.get("program_id") in program_ids]

    jcl_count = sum(1 for f in files if f.get("artifact_type") == "JCL")
    idcams_count = sum(1 for f in files if f.get("artifact_type") == "IDCAMS")
    catalog_count = sum(1 for f in files if f.get("artifact_type") == "CATALOG")

    folders = set()
    for f in files:
        p = f.get("path") or f.get("file_id") or ""
        dirname = os.path.dirname(p)
        if dirname:
            parts = dirname.replace("\\", "/").split("/")
            current = ""
            for part in parts:
                if part:
                    current = f"{current}/{part}" if current else part
                    folders.add(current)

    stats = {
        "repository_name": repo_name,
        "total_folders": len(folders),
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
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        return _knowledge_structure(knowledge)

    files = supabase_db.select("Files", {"repository_id": id})
    file_map = {f["file_id"]: f for f in files}
    
    # We now fetch the detailed structures directly from ArtifactMetadata in chunks
    file_ids = list(file_map.keys())
    repo_metadata = []
    chunk_size = 100
    for i in range(0, len(file_ids), chunk_size):
        chunk = file_ids[i:i+chunk_size]
        entries = supabase_db.select("ArtifactMetadata", {"file_id": {"in": chunk}})
        repo_metadata.extend(entries)
    
    programs_dict = {}
    copybooks_dict = {}
    datasets_dict = {}
    jcl_jobs_dict = {}
    idcams_dict = {}
    
    import json
    for m in repo_metadata:
        try:
            struct = m.get("structure")
            if isinstance(struct, str):
                struct = json.loads(struct)
            
            # Inject filepath from the DB into the structure so the frontend can build the tree
            file_row = file_map.get(m.get("file_id"))
            if file_row and "filepath" not in struct:
                struct["filepath"] = file_row.get("path") or file_row.get("file_id")

            artifact_type = struct.get("artifact_type") or struct.get("language") or "UNKNOWN"
            if artifact_type == "COBOL":
                programs_dict[struct.get("id") or m["artifact_id"]] = struct
            elif artifact_type == "JCL":
                jcl_jobs_dict[struct.get("id") or m["artifact_id"]] = struct
            elif artifact_type == "IDCAMS":
                idcams_dict[struct.get("id") or m["artifact_id"]] = struct
            elif "fields" in struct:
                copybooks_dict[struct.get("id") or m["artifact_id"]] = struct
            else:
                datasets_dict[struct.get("id") or m["artifact_id"]] = struct
        except Exception:
            pass

    return {
        "programs": programs_dict,
        "copybooks": copybooks_dict,
        "jcl_jobs": jcl_jobs_dict,
        "idcams_definitions": idcams_dict,
        "datasets": datasets_dict
    }

@router.get("/{id}/datasets")
async def get_datasets(id: str):
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        return knowledge.get("datasets") or {}

    dss = supabase_db.select("Datasets")
    return {ds["dataset_id"]: ds for ds in dss}

@router.get("/{id}/relationships")
async def get_relationships(id: str):
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        return knowledge.get("relationships") or []

    rels = supabase_db.select("Relationships")
    return rels

@router.get("/{id}/schema")
async def get_schema(id: str):
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        schema = knowledge.get("database_schema") or {
            "dialect": "none", "tables": {}, "relationships": [], "ddl": ""
        }
        return {
            "ready_for_generation": bool((knowledge.get("summary") or {}).get("schema_generation_readiness")),
            "database_schema": schema,
        }

    cbs = supabase_db.select("Copybooks")
    dss = supabase_db.select("Datasets")
    
    schema_dict = {
        "dialect": "none",
        "tables": {},
        "relationships": [],
        "ddl": ""
    }
    
    return {
        "ready_for_generation": False,
        "database_schema": schema_dict
    }

@router.get("/{id}/artifact-details/{artifact_id}")
async def get_artifact_details(id: str, artifact_id: str):
    knowledge = _load_repository_knowledge(id)
    relationships = []
    
    # 1. Get Artifact Structure and Base Meta
    artifact_struct = None
    artifact_meta_row = None
    file_row = None
    
    if knowledge:
        rels = knowledge.get("relationships") or []
        relationships = rels
        # search for artifact in canonical_structures
        structs = _knowledge_structure(knowledge)
        for group in structs.values():
            if artifact_id in group:
                artifact_struct = group[artifact_id]
                break
    else:
        # DB mode
        files = supabase_db.select("Files", {"repository_id": id})
        file_map = {f["file_id"]: f for f in files}
        
        metadata_entries = supabase_db.select("ArtifactMetadata", {"artifact_id": artifact_id})
        repo_metadata = [m for m in metadata_entries if m.get("file_id") in file_map]
        
        for m in repo_metadata:
            struct = m.get("structure")
            if isinstance(struct, str):
                import json
                try:
                    struct = json.loads(struct)
                except Exception:
                    continue
            struct_id = struct.get("id") or m.get("artifact_id")
            # we do case insensitive match just in case
            if str(struct_id).upper() == str(artifact_id).upper():
                artifact_struct = struct
                artifact_meta_row = m
                file_row = file_map.get(m.get("file_id"))
                break
        
        # Fetch only relevant relationships instead of all
        relationships = supabase_db.select("Relationships")
        
        if not artifact_struct:
            # Try to find just by file name if structure not fully matched
            if not knowledge:
                for f in files:
                    fname_no_ext = os.path.splitext(f.get("filename", ""))[0]
                    if fname_no_ext.upper() == artifact_id.upper() or f.get("filename") == artifact_id:
                        file_row = f
                        artifact_struct = {"id": artifact_id, "name": fname_no_ext, "artifact_type": f.get("artifact_type")}
                        break
            
            # Check if it's a dataset
            if not artifact_struct:
                datasets = supabase_db.select("Datasets", {"dataset_id": artifact_id})
                if datasets:
                    d = datasets[0]
                    artifact_struct = {"id": artifact_id, "name": d.get("dataset_name"), "artifact_type": "DATASET"}
                    
        if not artifact_struct:
            raise HTTPException(status_code=404, detail="Artifact not found")
            
    # 2. Build details
    a_type = artifact_struct.get("artifact_type") or artifact_struct.get("language") or (file_row.get("artifact_type") if file_row else "UNKNOWN")
    a_name = artifact_struct.get("name") or artifact_id
    p_file = artifact_struct.get("filepath") or (file_row.get("filename") if file_row else "")
    r_path = artifact_struct.get("repository_path") or (file_row.get("filepath") if file_row else "/")
    
    artifact = {
        "id": artifact_id,
        "type": a_type,
        "name": a_name,
        "physicalFile": p_file,
        "repositoryPath": r_path,
        "language": artifact_struct.get("language") or a_type,
        "parser": artifact_struct.get("parser") or (artifact_meta_row.get("parser_name") if artifact_meta_row else ""),
        "metadata": artifact_struct.get("properties") or artifact_struct.get("metadata") or {}
    }
    
    # 3. Build Dependencies
    deps = {
        "copybooks": [],
        "datasets": [],
        "calledPrograms": [],
        "jclJobs": [],
        "utilities": [],
        "idcams": []
    }
    
    # Filter rels related to this artifact
    # Both source_id or target_id could be the artifact
    # Note: relationships could use file names or parsed IDs
    a_id_upper = str(artifact_id).upper()
    
    for r in relationships:
        s_id = str(r.get("source_id")).upper()
        t_id = str(r.get("target_id")).upper()
        rel_type = r.get("relationship_type", "").upper()
        
        if s_id == a_id_upper:
            # Outgoing dependency
            if "COPYBOOK" in rel_type or "COPY" in rel_type:
                deps["copybooks"].append(r.get("target_id"))
            elif "DATASET" in rel_type:
                deps["datasets"].append(r.get("target_id"))
            elif "PROGRAM" in rel_type or "CALL" in rel_type:
                deps["calledPrograms"].append(r.get("target_id"))
            elif "JCL" in rel_type:
                deps["jclJobs"].append(r.get("target_id"))
            elif "UTILITY" in rel_type:
                deps["utilities"].append(r.get("target_id"))
            elif "IDCAMS" in rel_type:
                deps["idcams"].append(r.get("target_id"))
        elif t_id == a_id_upper:
            # Incoming dependency
            if "COPYBOOK" in rel_type or "COPY" in rel_type:
                deps["copybooks"].append(r.get("source_id"))
            elif "DATASET" in rel_type:
                deps["datasets"].append(r.get("source_id"))
            elif "PROGRAM" in rel_type or "CALL" in rel_type:
                deps["calledPrograms"].append(r.get("source_id"))
            elif "JCL" in rel_type or "EXECUTE" in rel_type:
                deps["jclJobs"].append(r.get("source_id"))
            elif "UTILITY" in rel_type:
                deps["utilities"].append(r.get("source_id"))
            elif "IDCAMS" in rel_type:
                deps["idcams"].append(r.get("source_id"))
                
    # fallback to lists from artifact_struct if they exist (parser specific)
    if not deps["copybooks"] and artifact_struct.get("copybooks_used"):
        deps["copybooks"] = artifact_struct.get("copybooks_used", [])
    if not deps["datasets"] and artifact_struct.get("datasets_accessed"):
        deps["datasets"] = artifact_struct.get("datasets_accessed", [])
    if not deps["calledPrograms"] and artifact_struct.get("programs_called"):
        deps["calledPrograms"] = artifact_struct.get("programs_called", [])
        
    # Deduplicate dependencies
    for k in deps:
        deps[k] = list(set(deps[k]))

    # 4. Detailed Data for UI Tabs
    artifact_rels = []
    if knowledge:
        for r in relationships:
            s_id = str(r.get("source_id", "")).upper()
            t_id = str(r.get("target_id", "")).upper()
            if s_id == a_id_upper or t_id == a_id_upper:
                artifact_rels.append(r)
        
        evidence = []
        evidence_list = knowledge.get("evidence", [])
        if evidence_list:
            evidence = [e for e in evidence_list if os.path.basename(e.get("source_file", "")).upper() == os.path.basename(p_file or "").upper()]
            
        artifact_datasets = []
        for r in artifact_rels:
            ds_id = r.get("target_id") if str(r.get("source_id", "")).upper() == a_id_upper else r.get("source_id")
            ds = knowledge.get("datasets", {}).get(ds_id)
            if ds:
                artifact_datasets.append(ds)
                
        schema = {}
        schema = {}
    else:
        for r in relationships:
            if str(r.get("source_id")).upper() == a_id_upper or str(r.get("target_id")).upper() == a_id_upper:
                artifact_rels.append(r)
                
        # Datasets
        artifact_datasets = []
        for r in artifact_rels:
            if str(r.get("source_id")).upper() == a_id_upper:
                ds = supabase_db.select("Datasets", {"dataset_id": r.get("target_id")})
                if ds:
                    artifact_datasets.append(ds[0])
            elif str(r.get("target_id")).upper() == a_id_upper:
                ds = supabase_db.select("Datasets", {"dataset_id": r.get("source_id")})
                if ds:
                    artifact_datasets.append(ds[0])
                    
        # Evidence
        evidence = supabase_db.select("Evidence", {"source_file": p_file}) if p_file else []
        if not evidence and file_row:
             evidence = supabase_db.select("Evidence", {"file_id": file_row.get("file_id")})
             
        schema = None
        generated = supabase_db.select("GeneratedSchema", {"schema_id": artifact_id})
        if generated:
            schema = generated[0]
            
    if not schema and artifact_struct:
        atype = str(a_type).upper()
        if atype == "COPYBOOK":
            schema = _generate_schema_from_structure(a_id_upper, artifact_struct, artifact_datasets)
        elif atype in ["COBOL", "CBL"]:
            schema = _generate_cobol_schema(a_id_upper, artifact_struct, deps)
        elif atype == "JCL":
            schema = _generate_jcl_schema(a_id_upper, artifact_struct)
        elif atype == "IDCAMS":
            schema = _generate_idcams_schema(a_id_upper, artifact_struct)
        elif atype == "DATASET":
            schema = _generate_dataset_schema(a_id_upper, artifact_struct)

    return {
        "artifact": artifact,
        "dependencies": deps,
        "structure": artifact_struct,
        "detailed_relationships": artifact_rels,
        "detailed_datasets": artifact_datasets,
        "detailed_evidence": evidence,
        "detailed_schema": schema
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
