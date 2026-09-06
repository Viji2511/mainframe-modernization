"""Evidence-backed, source-level COBOL program structure extraction.

This is intentionally not a compiler AST. It preserves the program facts the
repository already understands in an owned tree so consumers do not infer
ownership from flat lists.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from src.metadata.session import Evidence
from src.parsers.base_parser import BaseParser
from src.parsers.base_extractor import BaseExtractor
from src.parsers.copybook_parser import CopybookParser


COBOL_STRUCTURE_VERSION = "2.0.0"


class SelectExtractor(BaseExtractor):
    target_artifact_type = "COBOL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        result = []
        pattern = re.compile(r"SELECT\s+([A-Z0-9#$@-]+)\s+ASSIGN\s+TO\s+([A-Z0-9#$@-]+)", re.IGNORECASE)
        for line_number, line in enumerate(content.splitlines(), start=1):
            for match in pattern.finditer(line):
                result.append(Evidence(
                    artifact_type="COBOL", entity_type="LogicalFile", entity_name=match.group(1).upper(),
                    evidence_type="SELECT", value=match.group(2).upper(), severity="PRIMARY", source_file=file_path,
                    source_line=line_number, parser_name="COBOLParser", parser_version=COBOL_STRUCTURE_VERSION,
                ))
        return result


class FDExtractor(BaseExtractor):
    target_artifact_type = "COBOL"

    def extract(self, file_path: str, content: str) -> List[Evidence]:
        result = []
        pattern = re.compile(r"^.{0,6}\s*FD\s+([A-Z0-9#$@-]+)", re.IGNORECASE)
        for line_number, line in enumerate(content.splitlines(), start=1):
            match = pattern.search(line)
            if match:
                result.append(Evidence(
                    artifact_type="COBOL", entity_type="LogicalFile", entity_name=match.group(1).upper(),
                    evidence_type="FD", value=True, severity="SECONDARY", source_file=file_path,
                    source_line=line_number, parser_name="COBOLParser", parser_version=COBOL_STRUCTURE_VERSION,
                ))
        return result


class COBOLParser(BaseParser):
    artifact_type = "COBOL"

    _DIVISION = re.compile(r"^\s*(IDENTIFICATION|ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\.", re.IGNORECASE)
    _SECTION = re.compile(r"^\s*([A-Z][A-Z0-9-]*)\s+SECTION\.", re.IGNORECASE)
    _PARAGRAPH = re.compile(r"^\s{0,7}([A-Z0-9][A-Z0-9-]*)\.\s*$", re.IGNORECASE)
    _COPY = re.compile(r"^\s*COPY\s+([A-Z0-9#$@-]+)\b", re.IGNORECASE)
    _FD = re.compile(r"^\s*FD\s+([A-Z0-9#$@-]+)\b(?P<tail>.*)", re.IGNORECASE)
    _PROGRAM_ID = re.compile(r"^\s*PROGRAM-ID\.\s*([A-Z0-9#$@-]+)", re.IGNORECASE)
    _OPERATION = re.compile(r"^\s*(OPEN|READ|WRITE|REWRITE|DELETE|START|CLOSE|SORT|MERGE|PERFORM|CALL|MOVE|IF|EVALUATE)\b\s*(.*)", re.IGNORECASE)

    @staticmethod
    def _code_area(source: str) -> str:
        """Return the COBOL code area while retaining the original line number.

        Mainframe source commonly has a six-column sequence area followed by
        an indicator column.  The parser's expressions operate on the code
        area, but all nodes still retain their original physical line numbers.
        """
        if re.match(r"^\d{6}", source):
            return source[7:]
        return source

    def parse(self, file_path: str, content: str, session) -> List[Evidence]:
        evidence = super().parse(file_path, content, session)
        hierarchy = self._extract_structure(file_path, content)
        self._attach_existing_evidence(hierarchy, evidence)
        structures = session.execution_metadata.setdefault("cobol_structures", {})
        structures[file_path] = {
            "cobol_structure_version": COBOL_STRUCTURE_VERSION,
            "cobol_hierarchy": hierarchy,
            # Compatibility facts for old non-tree callers. The API treats
            # cobol_hierarchy as authoritative.
            "divisions": [node["name"].replace(" DIVISION", "") for node in hierarchy],
            "sections": [node["name"].replace(" SECTION", "") for node in self._walk(hierarchy) if node["type"] == "section"],
            "paragraphs": [node["name"] for node in self._walk(hierarchy) if node["type"] == "paragraph"],
            "operations": [node["properties"].get("operation") for node in self._walk(hierarchy) if node["type"] == "operation"],
            "called_programs": [node["properties"].get("target") for node in self._walk(hierarchy)
                                if node["type"] == "operation" and node["properties"].get("operation") == "CALL" and node["properties"].get("target")],
            "copybooks": [node["properties"].get("copybook") for node in self._walk(hierarchy) if node["type"] == "copy_reference"],
            "source_file": file_path,
        }
        session.parser_versions["COBOL"] = COBOL_STRUCTURE_VERSION
        return evidence

    @classmethod
    def _node(cls, node_type, name, file_path, source_line, properties=None, children=None):
        props = dict(properties or {})
        props.update({"source_file": file_path, "source_line": source_line})
        return {"node_id": f"{file_path}:{source_line or 0}:{node_type}:{name}", "type": node_type,
                "name": name, "properties": props, "children": children or []}

    @classmethod
    def _extract_structure(cls, file_path: str, content: str) -> list[dict]:
        lines = [cls._code_area(source) for source in content.splitlines()]
        divisions, division_by_name = [], {}
        current_division = current_section = current_fd = current_paragraph = None
        data_lines: set[int] = set()

        def start_division(name, line_number):
            nonlocal current_division, current_section, current_fd, current_paragraph
            current_division = division_by_name.get(name)
            if current_division is None:
                current_division = cls._node("division", f"{name} DIVISION", file_path, line_number, {"division": name})
                divisions.append(current_division)
                division_by_name[name] = current_division
            current_section = current_fd = current_paragraph = None

        def start_section(name, line_number, node_type="section"):
            nonlocal current_section, current_fd, current_paragraph
            if current_division is None:
                return None
            current_section = cls._node(node_type, name, file_path, line_number, {"section": name})
            current_division["children"].append(current_section)
            current_fd = current_paragraph = None
            return current_section

        for line_number, source in enumerate(lines, start=1):
            if cls._is_comment(source):
                continue
            match = cls._DIVISION.match(source)
            if match:
                start_division(match.group(1).upper(), line_number)
                continue
            if current_division and current_division["properties"]["division"] == "DATA":
                data_lines.add(line_number)

            match = cls._PROGRAM_ID.match(source)
            if match and current_division and current_division["properties"]["division"] == "IDENTIFICATION":
                current_division["children"].append(cls._node("program_id", "PROGRAM-ID", file_path, line_number, {"value": match.group(1).upper()}))
                continue
            match = cls._SECTION.match(source)
            if match:
                start_section(f"{match.group(1).upper()} SECTION", line_number)
                continue
            if current_division and current_division["properties"]["division"] == "ENVIRONMENT" and re.match(r"^\s*FILE-CONTROL\.", source, re.IGNORECASE):
                # FILE-CONTROL is a paragraph within INPUT-OUTPUT SECTION,
                # not a peer section. Preserve that source ownership.
                file_control = cls._node("file_control", "FILE-CONTROL", file_path, line_number, {"section": "FILE-CONTROL"})
                (current_section or current_division)["children"].append(file_control)
                current_section, current_fd, current_paragraph = file_control, None, None
                continue
            match = cls._FD.match(source)
            if match and current_division and current_division["properties"]["division"] == "DATA":
                if current_section is None:
                    current_section = start_section("FILE SECTION", line_number)
                tail = match.group("tail").strip().rstrip(".")
                props = {"file_name": match.group(1).upper()}
                if tail:
                    props["clauses"] = tail
                current_fd = cls._node("fd", f"FD {match.group(1).upper()}", file_path, line_number, props)
                current_section["children"].append(current_fd)
                continue
            match = cls._COPY.match(source)
            if match:
                owner = current_fd or current_section or current_division
                if owner is not None:
                    copybook = match.group(1).upper()
                    owner["children"].append(cls._node("copy_reference", f"COPY {copybook}", file_path, line_number, {"copybook": copybook}))
                continue
            if current_division and current_division["properties"]["division"] == "PROCEDURE":
                match = cls._PARAGRAPH.match(source)
                if match and not source.lstrip().upper().startswith(("END-", "ELSE", "WHEN")):
                    current_paragraph = cls._node("paragraph", match.group(1).upper(), file_path, line_number)
                    (current_section or current_division)["children"].append(current_paragraph)
                    continue
                operation = cls._operation_node(file_path, line_number, source)
                if operation:
                    (current_paragraph or current_section or current_division)["children"].append(operation)

        cls._add_selects(file_path, "\n".join(lines), division_by_name.get("ENVIRONMENT"))
        cls._add_data_items(file_path, lines, data_lines, division_by_name.get("DATA"))
        cls._sort_children(divisions)
        return divisions

    @classmethod
    def _add_selects(cls, file_path, content, environment):
        if environment is None:
            return
        target = next((node for node in cls._walk(environment["children"]) if node["type"] == "file_control"), None)
        pattern = re.compile(r"\bSELECT\s+([A-Z0-9#$@-]+)\b(?P<body>.*?)(?:\.|(?=\n\s*(?:SELECT|DATA\s+DIVISION)))", re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(content):
            line_number = content[:match.start()].count("\n") + 1
            if target is None:
                target = cls._node("file_control", "FILE-CONTROL", file_path, line_number)
                environment["children"].append(target)
            body, props = re.sub(r"\s+", " ", match.group("body")), {"file_name": match.group(1).upper()}
            for label, clause in (
                ("assign_to", r"\bASSIGN\s+TO\s+(?:DISK\s+)?([A-Z0-9#$@-]+)"),
                ("organization", r"\bORGANIZATION\s+(?:IS\s+)?([A-Z-]+)"),
                ("access_mode", r"\bACCESS\s+MODE\s+(?:IS\s+)?([A-Z-]+)"),
                ("record_key", r"\bRECORD\s+KEY\s+(?:IS\s+)?([A-Z0-9#$@-]+)"),
                ("file_status", r"\bFILE\s+STATUS\s+(?:IS\s+)?([A-Z0-9#$@-]+)"),
            ):
                clause_match = re.search(clause, body, re.IGNORECASE)
                if clause_match:
                    props[label] = clause_match.group(1).upper()
            target["children"].append(cls._node("select", f"SELECT {match.group(1).upper()}", file_path, line_number, props))

    @classmethod
    def _add_data_items(cls, file_path, lines, data_lines, data_division):
        if data_division is None or not data_lines:
            return
        # The authoritative copybook parser owns declaration semantics. Mask
        # non-DATA lines to retain original source line provenance.
        masked = "\n".join(line if number in data_lines else "" for number, line in enumerate(lines, start=1))
        roots = CopybookParser().parse_structure(file_path, masked)
        sections = [node for node in data_division["children"] if node["type"] == "section"]
        for root in roots:
            line_number = root.source_line or 0
            owner = next((node for node in reversed(sections) if (node["properties"].get("source_line") or 0) <= line_number), data_division)
            fds = [node for node in owner["children"] if node["type"] == "fd" and (node["properties"].get("source_line") or 0) <= line_number]
            (fds[-1] if fds else owner)["children"].append(cls._field_node(root.model_dump()))

    @classmethod
    def _field_node(cls, field):
        props = {key: field.get(key) for key in ("level", "pic", "data_type", "usage", "length", "logical_length", "byte_length", "occurs", "occurs_min", "occurs_max", "occurs_depending_on", "redefines", "redefines_target", "is_filler", "initial_value", "source_file", "source_line", "source_end_line", "evidence_ids") if field.get(key) not in (None, "", [], {})}
        level = field.get("level")
        return {"node_id": field.get("node_id"), "type": "data_item", "name": f"{int(level):02d} {field.get('name', 'UNKNOWN')}" if level is not None else field.get("name", "UNKNOWN"), "properties": props, "children": [cls._field_node(child) for child in field.get("children") or []]}

    @classmethod
    def _operation_node(cls, file_path, line_number, source):
        upper = source.strip().upper()
        if upper.startswith("EXEC CICS"):
            return cls._node("operation", "EXEC CICS", file_path, line_number, {"operation": "EXEC CICS"})
        if upper.startswith("EXEC SQL"):
            return cls._node("operation", "EXEC SQL", file_path, line_number, {"operation": "EXEC SQL"})
        match = cls._OPERATION.match(source)
        if not match:
            return None
        operation, remainder = match.group(1).upper(), match.group(2).strip().rstrip(".")
        props = {"operation": operation}
        if remainder:
            props["target"] = remainder.split()[0].strip("'\"").upper()
        return cls._node("operation", f"{operation}{(' ' + remainder) if remainder else ''}", file_path, line_number, props)

    @classmethod
    def _attach_existing_evidence(cls, roots, evidence):
        """Link SELECT/FD evidence that the established parser emits.

        We deliberately do not manufacture one evidence record per displayed
        node: source provenance remains available on all nodes, while evidence
        IDs appear precisely where the deterministic extractors have facts.
        """
        for node in cls._walk(roots):
            props = node.get("properties") or {}
            line = props.get("source_line")
            for item in evidence:
                if item.source_line != line:
                    continue
                if node["type"] == "select" and item.evidence_type == "SELECT":
                    props.setdefault("evidence_ids", []).append(item.evidence_id)
                elif node["type"] == "fd" and item.evidence_type == "FD":
                    props.setdefault("evidence_ids", []).append(item.evidence_id)

    @staticmethod
    def _is_comment(source):
        return not source.lstrip() or source.lstrip().startswith(("*", "/*"))

    @classmethod
    def _sort_children(cls, nodes: Iterable[dict]):
        for node in nodes:
            node["children"].sort(key=lambda item: ((item.get("properties") or {}).get("source_line") or 0, item["name"]))
            cls._sort_children(node["children"])

    @staticmethod
    def _walk(nodes: Iterable[dict]):
        for node in nodes:
            yield node
            yield from COBOLParser._walk(node.get("children") or [])
