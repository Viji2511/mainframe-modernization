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

    def parse(self, file_path: str, content: str, session) -> List[Evidence]:
        # Keep the existing evidence contract stable while capturing the
        # structural facts in the same one-time parser pass.
        evidence = super().parse(file_path, content, session)
        structures = session.execution_metadata.setdefault("cobol_structures", {})
        structures[file_path] = self._extract_structure(content)
        return evidence

    @staticmethod
    def _extract_structure(content: str) -> dict:
        divisions, sections, paragraphs, operations, called_programs = [], [], [], [], []
        copybooks = []
        division = re.compile(r'^\s*([A-Z][A-Z-]*)\s+DIVISION\.', re.IGNORECASE)
        section = re.compile(r'^\s*([A-Z][A-Z0-9-]*)\s+SECTION\.', re.IGNORECASE)
        paragraph = re.compile(r'^\s{7}([A-Z][A-Z0-9-]*)\.$', re.IGNORECASE)
        for line in content.splitlines():
            match = division.search(line)
            if match: divisions.append(match.group(1).upper())
            match = section.search(line)
            if match: sections.append(match.group(1).upper())
            match = paragraph.match(line)
            if match and not division.search(line) and not section.search(line): paragraphs.append(match.group(1).upper())
            operations.extend(token.upper() for token in re.findall(r'\b(OPEN|READ|WRITE|REWRITE|DELETE|START|CLOSE|SORT|MERGE)\b', line, re.IGNORECASE))
            called_programs.extend(token.upper() for token in re.findall(r"\bCALL\s+['\"]?([A-Z0-9#$@-]+)", line, re.IGNORECASE))
            copybooks.extend(token.upper() for token in re.findall(r'\bCOPY\s+([A-Z0-9#$@-]+)', line, re.IGNORECASE))
        return {
            "divisions": list(dict.fromkeys(divisions)), "sections": list(dict.fromkeys(sections)),
            "paragraphs": list(dict.fromkeys(paragraphs)), "operations": list(dict.fromkeys(operations)),
            "called_programs": list(dict.fromkeys(called_programs)), "copybooks": list(dict.fromkeys(copybooks)),
        }
