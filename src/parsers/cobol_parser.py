import re
from typing import List
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence

class SelectExtractor(BaseExtractor):
    target_artifact_type = "COBOL"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'SELECT\s+([A-Z0-9#$@-]+)\s+ASSIGN\s+TO\s+([A-Z0-9#$@-]+)', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            for match in pattern.finditer(line):
                evidence_list.append(Evidence(
                    artifact_type="COBOL",
                    entity_type="LogicalFile",
                    entity_name=match.group(1).strip(),
                    evidence_type="SELECT",
                    value=match.group(2).strip(),
                    properties={},
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="COBOLParser",
                    parser_version="1.0.0"
                ))
        return evidence_list

class FDExtractor(BaseExtractor):
    target_artifact_type = "COBOL"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'^.{6}\s*FD\s+([A-Z0-9#$@-]+)', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                evidence_list.append(Evidence(
                    artifact_type="COBOL",
                    entity_type="LogicalFile",
                    entity_name=match.group(1).strip(),
                    evidence_type="FD",
                    value=True,
                    properties={},
                    severity="SECONDARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="COBOLParser",
                    parser_version="1.0.0"
                ))
        return evidence_list

class COBOLParser(BaseParser):
    artifact_type = "COBOL"
    # Logic is now entirely handled by BaseParser invoking ExtractorRegistry
