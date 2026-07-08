import re
from typing import List
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence

class DDExtractor(BaseExtractor):
    target_artifact_type = "JCL"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        # Matches basic DD DSN patterns: //CUSTFILE DD DSN=PROD.CUSTOMER.MASTER
        # Real JCL parsing requires proper continuation handling, but we do basic regex here for prototype
        pattern = re.compile(r'//([A-Z0-9#$@]+)\s+DD\s+.*DSN=([A-Z0-9.#$@]+)', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            for match in pattern.finditer(line):
                evidence_list.append(Evidence(
                    artifact_type="JCL",
                    entity_type="DatasetBinding",
                    entity_name=match.group(1).strip(),
                    evidence_type="DD",
                    value=match.group(2).strip(),
                    properties={},
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="JCLParser",
                    parser_version="1.0.0"
                ))
        return evidence_list

class JCLParser(BaseParser):
    artifact_type = "JCL"
