import re
from typing import Any, Tuple

class PostgresMapper:
    """
    Centralized PostgreSQL datatype mapping layer for COBOL PIC clauses.
    """
    
    @classmethod
    def map_pic_to_postgres(cls, pic_str: str, field_name: str = "") -> Tuple[str, str, str, str]:
        """
        Maps a COBOL PIC to a PostgreSQL datatype.
        Returns: (postgres_type, logical_type, confidence, conversion_reason)
        """
        if not pic_str or pic_str.upper() == "GROUP":
            return ("JSONB", "Group", "HIGH", "Mapped to JSONB to preserve nested structure")
            
        pic = pic_str.upper().strip().replace(" ", "")
        
        # Date heuristic
        if cls._is_date_field(field_name, pic):
            return ("DATE", "Date", "MEDIUM", f"Inferred DATE from field name '{field_name}' and PIC '{pic}'")
            
        if pic.startswith("X") or pic.startswith("A") or "X(" in pic or "A(" in pic:
            m = re.search(r'[XA]\((\d+)\)', pic)
            length = int(m.group(1)) if m else max(pic.count('X'), pic.count('A'), 1)
            if length > 10485760:
                length = 10485760 # PG max length roughly
            return (f"VARCHAR({length})", "String", "HIGH", f"Direct character map of length {length}")
            
        is_numeric = "9" in pic or "V" in pic or "S9" in pic or "COMP" in pic or "BINARY" in pic or "Z" in pic
        
        if is_numeric:
            if "V" in pic:
                parts = pic.split("V")
                p1, p2 = parts[0], parts[1]
                m1 = re.search(r'9\((\d+)\)', p1)
                l1 = int(m1.group(1)) if m1 else p1.count('9') + p1.count('Z')
                m2 = re.search(r'9\((\d+)\)', p2)
                l2 = int(m2.group(1)) if m2 else p2.count('9')
                total = l1 + l2
                if total > 1000:
                    return ("NUMERIC", "Decimal", "LOW", "Numeric scale too large, defaulting to open NUMERIC")
                if total == 0:
                    total = 4 # fallback
                return (f"NUMERIC({total}, {l2})", "Decimal", "HIGH", f"Exact numeric match precision {total} scale {l2}")
            else:
                m = re.search(r'9\((\d+)\)', pic)
                l = int(m.group(1)) if m else pic.count('9') + pic.count('Z')
                
                # Handling COMP and BINARY
                if "COMP-3" in pic or "PACKED-DECIMAL" in pic:
                    if l == 0: l = 4
                    return (f"NUMERIC({l}, 0)", "Packed Decimal", "HIGH", f"Mapped packed decimal to NUMERIC({l})")
                elif "COMP-1" in pic:
                    return ("REAL", "Float", "HIGH", "COMP-1 mapped to REAL")
                elif "COMP-2" in pic:
                    return ("DOUBLE PRECISION", "Double", "HIGH", "COMP-2 mapped to DOUBLE PRECISION")
                elif "COMP" in pic or "BINARY" in pic:
                    if l == 0: l = 4
                    if l <= 4: return ("SMALLINT", "Integer", "HIGH", "COMP binary mapped to SMALLINT")
                    if l <= 9: return ("INTEGER", "Integer", "HIGH", "COMP binary mapped to INTEGER")
                    if l <= 18: return ("BIGINT", "Integer", "HIGH", "COMP binary mapped to BIGINT")
                    return (f"NUMERIC({l}, 0)", "Large Integer", "HIGH", "Large binary mapped to NUMERIC")
                
                # Standard numeric
                if l == 0:
                    l = 4
                if l <= 4:
                    return ("SMALLINT", "Integer", "HIGH", f"Standard numeric length {l} mapped to SMALLINT")
                elif l <= 9:
                    return ("INTEGER", "Integer", "HIGH", f"Standard numeric length {l} mapped to INTEGER")
                elif l <= 18:
                    return ("BIGINT", "Integer", "HIGH", f"Standard numeric length {l} mapped to BIGINT")
                else:
                    return (f"NUMERIC({l}, 0)", "Large Integer", "HIGH", f"Large standard numeric length {l} mapped to NUMERIC")
                    
        return ("TEXT", "Unknown", "LOW", f"Unsupported PIC {pic} mapped to TEXT")

    @classmethod
    def map_parsed_field(cls, field: Any) -> Tuple[str | None, str, str, str, str]:
        """Map normalized FieldSchema semantics without reparsing a PIC string."""
        get = (lambda key, default=None: getattr(field, key, default)) if not isinstance(field, dict) else field.get
        category = get("pic_category")
        precision, scale = get("precision"), int(get("scale", 0) or 0)
        logical_length, usage = get("logical_length"), (get("usage") or "DISPLAY").upper()
        if category in {"ALPHANUMERIC", "ALPHABETIC"} and logical_length:
            return (f"VARCHAR({int(logical_length)})", "String", "HIGH", f"Parsed {category.lower()} length {logical_length}", "EXACT")
        if category == "NUMERIC" and precision:
            precision = int(precision)
            if usage == "COMP-1":
                return ("REAL", "Float", "HIGH", "Parsed COMP-1 semantic", "EXACT")
            if usage == "COMP-2":
                return ("DOUBLE PRECISION", "Double", "HIGH", "Parsed COMP-2 semantic", "EXACT")
            if scale:
                return (f"NUMERIC({precision},{scale})", "Decimal", "HIGH", f"Parsed numeric precision {precision} scale {scale}", "EXACT")
            if usage in {"COMP-3", "COMP", "BINARY"} and precision > 18:
                return (f"NUMERIC({precision}, 0)", "Decimal", "HIGH", f"Parsed {usage} precision {precision}", "EXACT")
            if precision <= 4:
                return ("SMALLINT", "Integer", "HIGH", f"Parsed numeric precision {precision}", "EXACT")
            if precision <= 9:
                return ("INTEGER", "Integer", "HIGH", f"Parsed numeric precision {precision}", "EXACT")
            if precision <= 18:
                return ("BIGINT", "Integer", "HIGH", f"Parsed numeric precision {precision}", "EXACT")
            return (f"NUMERIC({precision}, 0)", "Decimal", "HIGH", f"Parsed numeric precision {precision}", "EXACT")
        return (None, "Unknown", "LOW", "Unsupported parsed PIC/USAGE semantics require review", "REVIEW_REQUIRED")

    @classmethod
    def _is_date_field(cls, field_name: str, pic: str) -> bool:
        """Determines if a field is likely a date based on name and PIC."""
        field_name = field_name.upper()
        # Common date PICs: 9(8) for YYYYMMDD, 9(6) for YYMMDD
        if pic in ["9(8)", "9(6)", "99999999", "999999"]:
            date_keywords = ["DATE", "-DT", "DT-", "_DT", "DT_"]
            for kw in date_keywords:
                if kw in field_name:
                    return True
        return False

    @classmethod
    def validate_postgres_type(cls, pg_type: str) -> bool:
        """Validates if the generated PostgreSQL type is valid and standard."""
        valid_bases = [
            "SMALLINT", "INTEGER", "BIGINT", "NUMERIC", 
            "REAL", "DOUBLE PRECISION", "VARCHAR", "TEXT", 
            "DATE", "JSONB"
        ]
        base = pg_type.split("(")[0].upper()
        if base not in valid_bases:
            return False
            
        # check limits
        if base == "VARCHAR":
            m = re.search(r'VARCHAR\((\d+)\)', pg_type.upper())
            if m and int(m.group(1)) > 10485760:
                 return False
        if base == "NUMERIC":
            m = re.search(r'NUMERIC\((\d+)(?:,\s*(\d+))?\)', pg_type.upper())
            if m:
                p = int(m.group(1))
                s = int(m.group(2)) if m.group(2) else 0
                if p > 1000 or s > p:
                    return False
        return True
