import re
from typing import List
from src.parsers.base_extractor import BaseExtractor
from src.metadata.session import Evidence

class CobolBusinessRuleExtractor(BaseExtractor):
    target_artifact_type = "COBOL"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'^\s*(IF|EVALUATE|PERFORM\s+UNTIL|WHEN)\b(.+)', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                evidence_list.append(Evidence(
                    artifact_type="COBOL",
                    entity_type="BusinessRule",
                    entity_name=match.group(1).strip().upper(),
                    evidence_type="BUSINESS_RULE",
                    value=match.group(2).strip(),
                    properties={"statement": match.group(1).strip().upper(), "condition": match.group(2).strip()},
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="CobolBusinessRuleExtractor",
                    parser_version="1.0.0"
                ))
        return evidence_list

class CobolAccessPatternExtractor(BaseExtractor):
    target_artifact_type = "COBOL"
    
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'^\s*(READ|WRITE|REWRITE|DELETE|START)\s+([A-Z0-9#$@-]+)', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                evidence_list.append(Evidence(
                    artifact_type="COBOL",
                    entity_type="AccessPattern",
                    entity_name=match.group(2).strip().upper(),
                    evidence_type="ACCESS_PATTERN",
                    value=match.group(1).strip().upper(),
                    properties={"operation": match.group(1).strip().upper(), "file": match.group(2).strip().upper()},
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="CobolAccessPatternExtractor",
                    parser_version="1.0.0"
                ))
        return evidence_list
