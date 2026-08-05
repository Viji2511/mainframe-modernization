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
                    properties={
                        "disp": _keyword_value(line, "DISP"),
                        "space": _keyword_value(line, "SPACE"),
                        "unit": _keyword_value(line, "UNIT"),
                        "dcb": _keyword_value(line, "DCB"),
                    },
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="JCLParser",
                    parser_version="1.0.0"
                ))
        return evidence_list


def _keyword_value(line: str, keyword: str):
    match = re.search(rf"\b{keyword}\s*=\s*([^,\s]+|\([^)]*\))", line, re.IGNORECASE)
    return match.group(1) if match else None


class ExecExtractor(BaseExtractor):
    """Extract programs invoked by JCL EXEC statements."""
    target_artifact_type = "JCL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'//([A-Z0-9#$@]+)\s+EXEC\s+(?:PGM\s*=\s*([A-Z0-9#$@]+)|PROC\s*=\s*([A-Z0-9#$@]+))', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            for match in pattern.finditer(line):
                evidence_list.append(Evidence(
                    artifact_type="JCL",
                    entity_type="Program",
                    entity_name=(match.group(2) or match.group(3)).strip().upper(),
                    evidence_type="EXEC",
                    value=(match.group(2) or match.group(3)).strip().upper(),
                    properties={"step_name": match.group(1).strip().upper(), "kind": "PROC" if match.group(3) else "PGM"},
                    severity="PRIMARY",
                    source_file=file_path,
                    source_line=i,
                    parser_name="JCLParser",
                    parser_version="1.0.0"
                ))
        return evidence_list


class JobCardExtractor(BaseExtractor):
    target_artifact_type = "JCL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        pattern = re.compile(r'^//([A-Z0-9#$@]+)\s+JOB\s+(.*)$', re.IGNORECASE)
        for i, line in enumerate(content.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                evidence_list.append(Evidence(
                    artifact_type="JCL", entity_type="Job", entity_name=match.group(1).upper(),
                    evidence_type="JOB", value=match.group(2).strip(), properties={"job_card": match.group(2).strip()},
                    severity="PRIMARY", source_file=file_path, source_line=i,
                    parser_name="JCLParser", parser_version="1.0.0"
                ))
                break
        return evidence_list


class SymbolicParameterExtractor(BaseExtractor):
    target_artifact_type = "JCL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        evidence_list = []
        for i, line in enumerate(content.splitlines(), start=1):
            for parameter in sorted(set(re.findall(r'&([A-Z][A-Z0-9#$@]*)', line, re.IGNORECASE))):
                evidence_list.append(Evidence(
                    artifact_type="JCL", entity_type="SymbolicParameter", entity_name=parameter.upper(),
                    evidence_type="SYMBOL", value=parameter.upper(), properties={}, severity="SUPPORTING",
                    source_file=file_path, source_line=i, parser_name="JCLParser", parser_version="1.0.0"
                ))
        return evidence_list

class JCLParser(BaseParser):
    artifact_type = "JCL"
