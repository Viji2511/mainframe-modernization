import logging
import json
import re
from typing import Dict, List, Any
from src.store.supabase_client import supabase_db

logger = logging.getLogger(__name__)

class SchemaGenerationEngine:
    def generate(self) -> None:
        try:
            logger.info("Schema Generation Engine: Starting")
            
            # Fetch inputs
            artifacts = supabase_db.select("ArtifactMetadata")
            relationships = supabase_db.select("Relationships")
            
            # Build dataset mapping: copybook_id -> list of dataset_ids
            cb_to_datasets = {}
            for rel in relationships:
                if rel.get("rel_type") == "USES_RECORD_LAYOUT":
                    cb_id = rel.get("target_id")
                    ds_id = rel.get("source_id")
                    if cb_id and ds_id:
                        if cb_id not in cb_to_datasets:
                            cb_to_datasets[cb_id] = []
                        cb_to_datasets[cb_id].append(ds_id)

            # Process COPYBOOK structures
            for artifact in artifacts:
                artifact_id = artifact.get("artifact_id", "")
                if not artifact_id.startswith("COPYBOOK:"):
                    continue
                
                try:
                    structure = json.loads(artifact.get("structure", "{}"))
                    records = structure.get("records", [])
                    
                    if not records:
                        logger.warning(f"No records found in structure for {artifact_id}")
                        continue
                        
                    datasets = cb_to_datasets.get(artifact_id, [])
                    readiness = "READY"
                    
                    if not datasets:
                        readiness = "INSUFFICIENT_EVIDENCE"
                    
                    schema_status = self._derive_schema(records)
                    columns = schema_status["columns"]
                    
                    if schema_status["needs_review"] and readiness == "READY":
                        readiness = "REVIEW_REQUIRED"
                        
                    if not columns:
                        readiness = "NOT_MIGRATABLE"
                    
                    # Generate DDL
                    table_name = artifact_id.split(":")[-1].replace("-", "_").lower()
                    
                    if columns:
                        col_defs = []
                        for col in columns:
                            col_def = f"  {col['name'].lower().replace('-', '_')} {col['sql_type']}"
                            if any(token in col['name'].upper() for token in ("ID", "KEY", "NUM", "NO")):
                                col_def += " PRIMARY KEY"
                            col_defs.append(col_def)
                        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(col_defs) + "\n);"
                    else:
                        ddl = f"CREATE TABLE {table_name} (\n  id BIGSERIAL PRIMARY KEY\n);"
                        
                    supabase_db.insert("GeneratedSchema", {
                        "schema_id": artifact_id,
                        "file_id": artifact.get("file_id"),
                        "ddl": ddl,
                        "readiness_status": readiness,
                        "mapped_dataset": datasets[0] if datasets else None
                    })
                    
                except Exception as e:
                    logger.error(f"Error generating schema for {artifact_id}: {e}")
                    
            logger.info("Schema Generation Engine: Finished")
        except Exception as e:
            logger.exception(f"Error in SchemaGenerationEngine: {e}")
            raise

    def _derive_schema(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        columns = []
        needs_review = False
        
        def traverse(fields: List[Dict[str, Any]]):
            nonlocal needs_review
            for field in fields:
                has_children = bool(field.get("children"))
                
                if field.get("occurs") or field.get("redefines"):
                    needs_review = True
                    
                if has_children:
                    traverse(field["children"])
                else:
                    if field.get("name"):
                        sql_type = self._pic_to_sql_type(field.get("pic", ""))
                        columns.append({
                            "name": field["name"],
                            "sql_type": sql_type,
                            "level": field.get("level"),
                            "pic": field.get("pic"),
                            "length": field.get("length")
                        })
        
        traverse(records)
        return {"columns": columns, "needs_review": needs_review}

    def _pic_to_sql_type(self, pic: str) -> str:
        if not pic:
            return "TEXT"
        
        pic = pic.upper().replace(" ", "")
        
        if pic.startswith("X") or pic.startswith("A"):
            match = re.search(r"[XA]\((\d+)\)", pic)
            return f"VARCHAR({match.group(1)})" if match else "TEXT"
            
        if "9" in pic or "S9" in pic or "Z" in pic or "V" in pic:
            if "V" in pic:
                match = re.search(r"9\((\d+)\)V9\((\d+)\)", pic)
                if match:
                    p = int(match.group(1))
                    s = int(match.group(2))
                    return f"NUMERIC({p+s},{s})"
                parts = pic.split("V")
                if len(parts) == 2:
                    p = parts[0].count("9") + parts[0].count("Z")
                    s = parts[1].count("9")
                    if p > 0 or s > 0:
                        return f"NUMERIC({p+s},{s})"
                        
            match = re.search(r"9\((\d+)\)", pic)
            if match:
                precision = int(match.group(1))
                if precision <= 4: return "SMALLINT"
                if precision <= 9: return "INTEGER"
                if precision <= 18: return "BIGINT"
                return f"NUMERIC({precision},0)"
                
            count = pic.count("9") + pic.count("Z")
            if count > 0:
                if count <= 4: return "SMALLINT"
                if count <= 9: return "INTEGER"
                if count <= 18: return "BIGINT"
                return f"NUMERIC({count},0)"
                
        return "TEXT"
