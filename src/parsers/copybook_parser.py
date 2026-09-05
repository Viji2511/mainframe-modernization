"""Authoritative hierarchical COBOL copybook parser.

This module owns source semantics only: hierarchy, PIC/USAGE facts, layout,
and source provenance. It deliberately makes no relational or DDL decision.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, Optional

from src.metadata.session import Evidence
from src.models.knowledge_store import FieldSchema
from src.orchestrator.event_bus import event_bus
from src.parsers.base_parser import BaseParser


COPYBOOK_MODEL_VERSION = "2.0.0"
COPYBOOK_PARSER_VERSION = "2.0.0"

_DECLARATION = re.compile(
    r"^\s*(?:\d{6}\s+)?(?P<level>\d{2})\s+(?P<name>[A-Z0-9_-]+)\b(?P<body>.*)$",
    re.IGNORECASE,
)
_PIC = re.compile(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(?P<pic>[A-Z0-9()V+*/$-]+)", re.IGNORECASE)
_REDEFINES = re.compile(r"\bREDEFINES\s+(?P<target>[A-Z0-9_-]+)", re.IGNORECASE)
_OCCURS = re.compile(
    r"\bOCCURS\s+(?P<minimum>\d+)(?:\s+TO\s+(?P<maximum>\d+))?\s+TIMES?"
    r"(?:\s+DEPENDING\s+ON\s+(?P<depending>[A-Z0-9_-]+))?",
    re.IGNORECASE,
)
_USAGE = re.compile(
    r"\b(?:USAGE\s+(?:IS\s+)?)?(?P<usage>"
    r"COMP(?:UTATIONAL)?(?:-[12345])?|BINARY|PACKED-DECIMAL|INDEX|DISPLAY)\b",
    re.IGNORECASE,
)


def normalize_usage(value: Optional[str]) -> str:
    """Normalize only storage aliases the prototype deliberately supports."""
    source = (value or "DISPLAY").upper().replace(" ", "")
    aliases = {
        "COMPUTATIONAL": "COMP", "COMPUTATIONAL-1": "COMP-1",
        "COMPUTATIONAL-2": "COMP-2", "COMPUTATIONAL-3": "COMP-3",
        "PACKED-DECIMAL": "COMP-3",
    }
    return aliases.get(source, source)


def _count_symbols(value: str, symbols: str) -> int:
    total = 0
    for match in re.finditer(rf"([{re.escape(symbols)}])(?:\((\d+)\))?", value.upper()):
        total += int(match.group(2) or 1)
    return total


def parse_pic(pic: Optional[str], usage: Optional[str] = None) -> dict[str, Any]:
    """Parse PIC logical semantics once, independently from storage sizing."""
    raw = (pic or "").upper().replace(" ", "")
    normalized_usage = normalize_usage(usage)
    if not raw:
        return {"raw": None, "category": "GROUP", "signed": False,
                "precision": None, "scale": 0, "logical_length": None,
                "usage": normalized_usage}
    before_decimal, separator, after_decimal = raw.partition("V")
    alpha = _count_symbols(raw, "XA")
    integer_digits = _count_symbols(before_decimal, "9Z")
    fractional_digits = _count_symbols(after_decimal, "9Z") if separator else 0
    numeric_digits = integer_digits + fractional_digits
    if alpha:
        category = "ALPHANUMERIC" if "X" in raw else "ALPHABETIC"
        logical_length, precision = alpha, None
    elif numeric_digits:
        category = "NUMERIC"
        logical_length = precision = numeric_digits
    else:
        category = "UNSUPPORTED"
        logical_length = precision = None
    return {"raw": raw, "category": category, "signed": raw.startswith("S"),
            "precision": precision, "scale": fractional_digits,
            "logical_length": logical_length, "usage": normalized_usage}


def compute_physical_length(node: FieldSchema) -> Optional[int]:
    """Return one occurrence's bytes using documented IBM COBOL assumptions.

    DISPLAY signed numerics use an overpunch sign and use the same positions as
    their digits. COMP is IBM Enterprise COBOL binary (2/4/8 bytes by decimal
    digit range). Unknown compiler-specific usages remain explicit but have no
    guessed physical length.
    """
    if node.node_type in {"CONDITION", "RENAMES"}:
        return 0
    if node.node_type == "GROUP" and node.children:
        return node.byte_length
    semantic = parse_pic(node.pic or node.data_type, node.usage)
    logical, usage = semantic["logical_length"], semantic["usage"]
    if logical is None:
        return None
    if usage == "DISPLAY":
        return logical
    if usage == "COMP-3":
        return math.ceil((int(semantic["precision"] or 0) + 1) / 2)
    if usage in {"COMP", "BINARY"}:
        digits = int(semantic["precision"] or 0)
        if digits <= 4:
            return 2
        if digits <= 9:
            return 4
        if digits <= 18:
            return 8
        return None
    if usage == "COMP-1":
        return 4
    if usage == "COMP-2":
        return 8
    return None


class CopybookParser(BaseParser):
    artifact_type = "COPYBOOK"

    def parse(self, file_path: str, content: str, session) -> list[Evidence]:
        roots = self.parse_structure(file_path, content)
        evidence = self._evidence_for_nodes(file_path, roots)
        evidence_by_node = {item.properties["node_id"]: item.evidence_id for item in evidence}
        for node in self._walk(roots):
            if node.node_id in evidence_by_node:
                node.evidence_ids.append(evidence_by_node[node.node_id])

        record_max = max(((item.absolute_offset or 0) + (item.physical_span_max or 0) for item in roots), default=0)
        record_min = max(((item.absolute_offset or 0) + (item.physical_span_min or 0) for item in roots), default=0)
        session.execution_metadata.setdefault("copybook_structures", {})[file_path] = {
            "copybook_model_version": COPYBOOK_MODEL_VERSION,
            "parser_version": COPYBOOK_PARSER_VERSION,
            "records": [item.model_dump() for item in roots],
            "record_length_min": record_min,
            "record_length_max": record_max,
            "source_file": file_path,
        }
        session.parser_versions["COPYBOOK"] = COPYBOOK_PARSER_VERSION
        if evidence:
            event_bus.publish("CopybookMetadataExtracted", evidence)
        return evidence

    def parse_structure(self, file_path: str, content: str) -> list[FieldSchema]:
        roots: list[FieldSchema] = []
        stack: list[FieldSchema] = []
        for line_number, source in enumerate(content.splitlines(), start=1):
            if self._is_comment(source):
                continue
            match = _DECLARATION.match(source)
            if not match:
                continue
            level, name, body = int(match.group("level")), match.group("name").upper(), match.group("body")
            node = self._node_from_declaration(file_path, line_number, level, name, body)
            if level in {66, 88}:
                node.node_type = "RENAMES" if level == 66 else "CONDITION"
                # 88 belongs to the preceding elementary declaration.  66 is
                # a non-storage alias within the nearest enclosing group, not
                # a child that should alter the preceding field's layout.
                parent = stack[-1] if level == 88 and stack else next((item for item in reversed(stack) if item.node_type == "GROUP"), None)
                if parent:
                    node.parent_id = parent.node_id
                    parent.children.append(node)
                else:
                    roots.append(node)
                continue
            if level == 77:
                stack.clear()
                roots.append(node)
                stack.append(node)
                continue
            while stack and (stack[-1].level or 0) >= level:
                stack.pop()
            if stack:
                node.parent_id = stack[-1].node_id
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
        self._layout(roots, 0)
        return roots

    @staticmethod
    def _is_comment(line: str) -> bool:
        stripped = line.lstrip()
        return not stripped or stripped.startswith("*") or stripped.startswith("/*")

    @staticmethod
    def _node_from_declaration(file_path: str, line: int, level: int, name: str, body: str) -> FieldSchema:
        pic_match, usage_match, occurrence, redefine = _PIC.search(body), _USAGE.search(body), _OCCURS.search(body), _REDEFINES.search(body)
        pic = pic_match.group("pic").upper() if pic_match else None
        semantic = parse_pic(pic, usage_match.group("usage") if usage_match else None)
        minimum = int(occurrence.group("minimum")) if occurrence else None
        maximum = int(occurrence.group("maximum") or occurrence.group("minimum")) if occurrence else None
        value = re.search(r"\bVALUE\s+(?:IS\s+)?([^.]*)", body, re.IGNORECASE)
        target = redefine.group("target").upper() if redefine else None
        return FieldSchema(
            node_id=f"{file_path}:{line}:{name}", name=name, data_type=pic or "GROUP", pic=pic,
            level=level, node_type="ELEMENTARY" if pic else "GROUP", usage=semantic["usage"],
            pic_category=semantic["category"], signed=semantic["signed"], precision=semantic["precision"],
            scale=semantic["scale"], logical_length=semantic["logical_length"], occurs=minimum,
            occurs_min=minimum, occurs_max=maximum,
            occurs_depending_on=occurrence.group("depending").upper() if occurrence and occurrence.group("depending") else None,
            redefines=target, redefines_target=target, is_filler=name == "FILLER",
            source_file=file_path, source_line=line, source_end_line=line,
            initial_value=value.group(1).strip() if value else None,
            parser_metadata={"copybook_model_version": COPYBOOK_MODEL_VERSION, "parser": "CopybookParser"},
        )

    def _layout(self, nodes: list[FieldSchema], start: int) -> int:
        cursor, max_end, by_name = start, start, {}
        for node in nodes:
            if node.node_type in {"CONDITION", "RENAMES"}:
                node.absolute_offset, node.relative_offset, node.byte_length = cursor, cursor - start, 0
                node.physical_span_min = node.physical_span_max = 0
                continue
            target = by_name.get(node.redefines_target or "")
            node_start = target.absolute_offset if target and target.absolute_offset is not None else cursor
            node.absolute_offset, node.relative_offset = node_start, node_start - start
            if node.node_type == "GROUP" and node.children:
                node.byte_length = self._layout(node.children, node_start) - node_start
            else:
                # Condition names are child metadata for an elementary field;
                # they do not turn that field into a group or consume storage.
                if node.children:
                    self._layout(node.children, node_start)
                node.byte_length = compute_physical_length(node)
            node.length = node.byte_length
            minimum, maximum = node.occurs_min or 1, node.occurs_max or node.occurs_min or 1
            if node.byte_length is None:
                node.physical_span_min = node.physical_span_max = None
            else:
                node.physical_span_min, node.physical_span_max = node.byte_length * minimum, node.byte_length * maximum
            if not node.redefines_target:
                cursor = node_start + (node.physical_span_max or 0)
            max_end = max(max_end, node_start + (node.physical_span_max or 0))
            by_name[node.name] = node
        return max(cursor, max_end)

    def _evidence_for_nodes(self, file_path: str, roots: list[FieldSchema]) -> list[Evidence]:
        result: list[Evidence] = []
        for node in self._walk(roots):
            if node.node_type in {"CONDITION", "RENAMES"}:
                continue
            result.append(Evidence(
                artifact_type="COPYBOOK", entity_type="CopybookNode", entity_name=node.name,
                evidence_type="COPYBOOK_NODE", value=node.node_type,
                properties={"node_id": node.node_id, "level": node.level, "pic": node.pic, "usage": node.usage,
                            "occurs_min": node.occurs_min, "occurs_max": node.occurs_max,
                            "occurs_depending_on": node.occurs_depending_on, "redefines_target": node.redefines_target,
                            "is_filler": node.is_filler, "byte_length": node.byte_length,
                            "absolute_offset": node.absolute_offset},
                severity="PRIMARY", source_file=file_path, source_line=node.source_line,
                parser_name="CopybookParser", parser_version=COPYBOOK_PARSER_VERSION,
            ))
        return result

    @staticmethod
    def _walk(nodes: Iterable[FieldSchema]) -> Iterable[FieldSchema]:
        for node in nodes:
            yield node
            yield from CopybookParser._walk(node.children)
