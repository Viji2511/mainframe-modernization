import json
import re
from typing import List
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence

class CatalogMetadataExtractor(BaseExtractor):
    target_artifact_type = "CATALOG"

    @staticmethod
    def _evidence(file_path, line_number, name, properties):
        return Evidence(
            artifact_type="CATALOG",
            entity_type="CatalogEntry",
            entity_name=name,
            evidence_type="CATALOG_ENTRY",
            value=properties.get("entry_type"),
            properties=properties,
            severity="PRIMARY",
            source_file=file_path,
            source_line=line_number,
            parser_name="CatalogParser",
            parser_version="1.0.0",
        )
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        # Fallback to lines if not pure json
        try:
            # Try to parse if it's a JSON export for catalog
            data = json.loads(content)
            if isinstance(data, list):
                items = data
            else:
                items = [data]
                
            for i, item in enumerate(items, start=1):
                dsn = item.get("dsn")
                org = item.get("organization")
                if dsn and org:
                    properties = {**item, "entry_type": item.get("entry_type") or item.get("type") or "DATASET"}
                    evidence_list.append(self._evidence(file_path, i, dsn, properties))
        except json.JSONDecodeError:
            # LISTCAT text uses an entry header followed by ATTRIBUTES and
            # ASSOCIATIONS. Preserve only facts stated in the listing.
            current = None
            header = re.compile(r"^\s*[01](CLUSTER|DATA|INDEX|NONVSAM|PATH|AIX)\s*-+\s*([A-Z0-9.#$@-]+)", re.IGNORECASE)
            property_patterns = {
                "key_length": re.compile(r"\bKEYLEN\s*-+\s*(\d+)", re.IGNORECASE),
                "average_record_length": re.compile(r"\bAVGLRECL\s*-+\s*(\d+)", re.IGNORECASE),
                "maximum_record_length": re.compile(r"\bMAXLRECL\s*-+\s*(\d+)", re.IGNORECASE),
                "relative_key_position": re.compile(r"\bRKP\s*-+\s*(\d+)", re.IGNORECASE),
                "control_interval_size": re.compile(r"\bCISIZE\s*-+\s*(\d+)", re.IGNORECASE),
            }
            association = re.compile(r"^\s*(DATA|INDEX|CLUSTER|AIX)\s*-+\s*([A-Z0-9.#$@-]+)", re.IGNORECASE)

            def finish():
                if current:
                    evidence_list.append(self._evidence(file_path, current["line"], current["name"], current["properties"]))

            for line_number, line in enumerate(content.splitlines(), start=1):
                match = header.search(line)
                if match:
                    finish()
                    entry_type = match.group(1).upper()
                    current = {
                        "line": line_number,
                        "name": match.group(2).upper(),
                        "properties": {"entry_type": entry_type, "organization": "KSDS" if entry_type == "CLUSTER" and ".KSDS" in match.group(2).upper() else None, "associations": []},
                    }
                    continue
                if not current:
                    continue
                association_match = association.search(line)
                if association_match:
                    current["properties"]["associations"].append({
                        "type": association_match.group(1).upper(),
                        "name": association_match.group(2).upper(),
                    })
                for key, pattern in property_patterns.items():
                    value_match = pattern.search(line)
                    if value_match:
                        current["properties"][key] = int(value_match.group(1))
            finish()
            
        return evidence_list

class CatalogParser(BaseParser):
    artifact_type = "CATALOG"
