import json
from typing import List
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence

class CatalogMetadataExtractor(BaseExtractor):
    target_artifact_type = "CATALOG"
    
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
                    evidence_list.append(Evidence(
                        artifact_type="CATALOG",
                        entity_type="Dataset",
                        entity_name=dsn,
                        evidence_type="ORGANIZATION",
                        value=org,
                        properties=item,
                        severity="PRIMARY",
                        source_file=file_path,
                        source_line=i,
                        parser_name="CatalogParser",
                        parser_version="1.0.0"
                    ))
        except json.JSONDecodeError:
            # If not JSON, we would put CSV parsing here...
            pass
            
        return evidence_list

class CatalogParser(BaseParser):
    artifact_type = "CATALOG"
