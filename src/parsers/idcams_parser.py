import re
from typing import List
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence

class DefineClusterExtractor(BaseExtractor):
    target_artifact_type = "IDCAMS"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        # Look for DEFINE CLUSTER (NAME(DSN))
        pattern = re.compile(r'DEFINE\s+CLUSTER\s*\(\s*NAME\s*\(\s*([A-Z0-9.#$@]+)\s*\)', re.IGNORECASE)
        # Look for INDEXED vs NONINDEXED
        org_pattern = re.compile(r'\b(INDEXED|NONINDEXED|NUMBERED|LINEAR)\b', re.IGNORECASE)
        
        # We'll treat the entire block as one line to avoid multiline continuation parsing complexities for now
        # and just find all names
        block_text = content.replace('\n', ' ')
        for match in pattern.finditer(block_text):
            dsn = match.group(1)
            # Rough approximation of properties
            properties = {}
            org_match = org_pattern.search(block_text)
            if org_match:
                org_val = org_match.group(1).upper()
                vtype = "KSDS" if org_val == "INDEXED" else "ESDS" if org_val == "NONINDEXED" else "RRDS" if org_val == "NUMBERED" else "LDS"
                properties["organization"] = vtype
                
            evidence_list.append(Evidence(
                artifact_type="IDCAMS",
                entity_type="Cluster",
                entity_name=dsn,
                evidence_type="DEFINE_CLUSTER",
                value=True,
                properties=properties,
                severity="PRIMARY",
                source_file=file_path,
                source_line=1,
                parser_name="IDCAMSParser",
                parser_version="1.0.0"
            ))
        return evidence_list

class IDCAMSParser(BaseParser):
    artifact_type = "IDCAMS"
