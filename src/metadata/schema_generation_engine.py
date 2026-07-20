import logging
import re
from src.store.supabase_client import supabase_db

logger = logging.getLogger(__name__)

class SchemaGenerationEngine:
    def generate(self) -> None:
        try:
            logger.info("Schema Generation Engine: Starting")
            
            # Since this is a prototype, we'll fetch all fields and copybooks
            # but wait, the fields aren't populated anywhere yet.
            # We need to ensure that fields are parsed from copybooks and inserted into Supabase.
            # But the prompt said: "Keep the existing deterministic parsers. Do NOT rewrite parser logic."
            # Our existing parsers don't parse fields in base_parser, they did it in knowledge_builder!
            # Let's add that logic here as part of schema generation or just parse it here directly.
            
            # Fetch copybooks from Supabase
            copybooks = supabase_db.select("Copybooks")
            files = {f["file_id"]: f for f in supabase_db.select("Files", {"artifact_type": "COPYBOOK"})}
            
            for cb in copybooks:
                file_id = cb["file_id"]
                file_info = files.get(file_id)
                if not file_info:
                    continue
                
                path = file_info["path"]
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    fields = self._parse_copybook_fields(content)
                    
                    columns = []
                    for field in fields:
                        # Insert field into Supabase
                        supabase_db.insert("Fields", {
                            "field_id": f"{cb['copybook_id']}_{field['name']}",
                            "dataset_id": cb['copybook_id'], # Using copybook as dataset for schema gen
                            "field_name": field["name"],
                            "picture_clause": field["data_type"],
                            "sql_type": self._field_to_sql_type(field),
                            "length": 0,
                            "nullable": not field["is_key"]
                        })
                        
                        if field["data_type"] != "GROUP":
                            sql_type = self._field_to_sql_type(field)
                            col_def = f"  {field['name'].lower().replace('-', '_')} {sql_type}"
                            if field["is_key"]:
                                col_def += " PRIMARY KEY"
                            columns.append(col_def)
                            
                    table_name = cb["copybook_name"].lower()
                    if columns:
                        ddl = f"CREATE TABLE {table_name} (\n" + ",\n".join(columns) + "\n);"
                    else:
                        ddl = f"CREATE TABLE {table_name} (\n  id BIGSERIAL PRIMARY KEY\n);"
                        
                    supabase_db.insert("GeneratedSchema", {
                        "schema_id": cb["copybook_id"],
                        "file_id": file_id,
                        "ddl": ddl
                    })
                    
                except Exception as e:
                    logger.error(f"Error parsing copybook {path}: {e}")
                    
            logger.info("Schema Generation Engine: Finished")
        except Exception as e:
            logger.exception(f"Error in SchemaGenerationEngine: {e}")
            raise

    def _parse_copybook_fields(self, content: str) -> list:
        fields = []
        pattern = re.compile(r"^\s*\d{2}\s+([A-Z0-9_-]+)(?:\s+PIC\s+([A-Z0-9()VXS9+-]+))?", re.IGNORECASE)
        for line in content.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            name = match.group(1).upper()
            pic = match.group(2)
            fields.append({
                "name": name,
                "data_type": pic.upper() if pic else "GROUP",
                "is_key": any(token in name for token in ("ID", "KEY", "NUM", "NO"))
            })
        return fields

    def _field_to_sql_type(self, field: dict) -> str:
        data_type = (field.get("data_type") or "").upper().rstrip(".")
        if data_type == "GROUP":
            return "TEXT"
        if data_type.startswith("X"):
            match = re.search(r"X\((\d+)\)", data_type)
            return f"VARCHAR({match.group(1)})" if match else "TEXT"
        if data_type.startswith("S9") or data_type.startswith("9"):
            match = re.search(r"9\((\d+)\)(?:V9\((\d+)\)|V(9+))?", data_type)
            if match:
                precision = int(match.group(1))
                scale = int(match.group(2) or len(match.group(3) or ""))
                if scale:
                    return f"NUMERIC({precision + scale},{scale})"
                if precision <= 9:
                    return "INTEGER"
                return "BIGINT"
            return "NUMERIC"
        return "TEXT"
