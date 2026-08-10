import json
import re

def parse_pic(pic_str):
    if not pic_str or pic_str == "GROUP":
        return None
    pic_str = pic_str.upper().strip()
    
    # Extract size
    if pic_str.startswith("X"):
        m = re.search(r'X\((\d+)\)', pic_str)
        if m:
            return f"VARCHAR({m.group(1)})"
        return "VARCHAR(1)"
    elif pic_str.startswith("9") or pic_str.startswith("S9"):
        # Handle implied decimal
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
            if l <= 4:
                return "SMALLINT"
            elif l <= 9:
                return "INTEGER"
            else:
                return "BIGINT"
    
    return "VARCHAR(255)"

def flatten_records(records, prefix=""):
    columns = []
    for r in records:
        name = r.get("name", "").replace("-", "_")
        col_name = f"{prefix}_{name}" if prefix else name
        pic = r.get("pic")
        children = r.get("children", [])
        redefines = r.get("redefines")
        
        # Skip redefines for base relational schema to avoid overlaps
        if redefines:
            continue
            
        if not children and pic and pic != "GROUP" and name != "FILLER":
            sql_type = parse_pic(pic)
            columns.append({
                "name": col_name,
                "sql_type": sql_type,
                "source_field": r.get("name"),
                "primary_key": False
            })
        
        if children:
            columns.extend(flatten_records(children, prefix=col_name))
            
    return columns

if __name__ == "__main__":
    d = json.load(open('struct.json'))
    records = d['copybooks']['COPAU01']['structure']['records']
    cols = flatten_records(records)
    print(json.dumps(cols, indent=2))
