import re
from typing import Dict, Any
from src.models.knowledge_store import RepositoryKnowledge, CopybookKnowledge, FieldSchema

class SchemaGenerator:
    """
    Generates a relational database schema from copybooks.
    """
    def __init__(self, target_db: str = "postgresql"):
        self.target_db = target_db

    def map_pic_to_sql(self, pic: str) -> str:
        pic = pic.upper()
        if not pic or pic == "GROUP":
            return "JSON"
        
        length = 1
        length_match = re.search(r'\((\d+)\)', pic)
        if length_match:
            length = int(length_match.group(1))
        elif "X" in pic or "9" in pic:
             # simple counting if no parentheses e.g. XXX or 999
             length = max(pic.count("X"), pic.count("9"), 1)
            
        if "X" in pic or "A" in pic:
            return f"VARCHAR({length})"
        elif "9" in pic:
            if "V" in pic:
                v_split = pic.split("V")
                dec_len = 1
                if len(v_split) > 1:
                    dec_match = re.search(r'9\((\d+)\)', v_split[1])
                    if dec_match:
                        dec_len = int(dec_match.group(1))
                    elif "9" in v_split[1]:
                        dec_len = v_split[1].count("9")
                return f"NUMERIC({length + dec_len}, {dec_len})"
            elif length <= 4:
                return "SMALLINT"
            elif length <= 9:
                return "INTEGER"
            else:
                return "BIGINT"
        
        return "VARCHAR(255)"

    def generate(self, knowledge: RepositoryKnowledge) -> Dict[str, Any]:
        schema = {
            "tables": [],
            "relations": []
        }
        
        for cb_id, cb in knowledge.copybooks.items():
            table_name = cb_id.replace(".CPY", "").replace(".COPY", "").replace("-", "_").upper()
            table = {
                "name": table_name,
                "columns": [],
                "primary_keys": [],
                "foreign_keys": []
            }
            
            for field in cb.fields:
                if field.data_type == "GROUP":
                    continue
                
                col_name = field.name.replace("-", "_")
                sql_type = self.map_pic_to_sql(field.data_type)
                
                is_pk = field.is_key or col_name.endswith("_ID") or col_name.endswith("_KEY")
                is_nullable = not is_pk
                
                col = {
                    "name": col_name,
                    "type": sql_type,
                    "nullable": is_nullable,
                    "is_primary": is_pk,
                    "original_pic": field.data_type
                }
                table["columns"].append(col)
                if is_pk:
                    table["primary_keys"].append(col_name)
                    
            if table["columns"]:
                schema["tables"].append(table)
            
        knowledge.database_schema = schema
        return schema
