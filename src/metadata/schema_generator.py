"""Authoritative Copybook-to-resolved-relational-schema transformation.

New analyses enter here only after ``CopybookParser`` has produced the
hierarchical FieldSchema model. This module deliberately does not parse source
or PIC strings: parser facts and resolution decisions are its sole inputs.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from src.analyzers.occurs_resolution_engine import OccursResolutionEngine
from src.analyzers.redefines_resolution_engine import RedefinesResolutionEngine
from src.models.knowledge_store import FieldSchema, RepositoryKnowledge
from src.validators.postgres_mapper import PostgresMapper

RESOLVED_SCHEMA_VERSION = "2.0.0"


def _identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9_]+", "_", value.upper().replace("-", "_")).strip("_") or "FIELD"


class SchemaGenerator:
    """The sole authoritative generator for newly analysed repositories."""
    def __init__(self, target_db: str = "postgresql"):
        self.target_db = target_db

    def map_pic_to_sql(self, pic: str, field_name: str = "") -> str:
        """Deprecated legacy compatibility helper; new generation never calls it."""
        return PostgresMapper.map_pic_to_postgres(pic, field_name)[0]

    def generate(self, knowledge: RepositoryKnowledge) -> dict[str, Any]:
        schema: dict[str, Any] = {"resolved_schema_version": RESOLVED_SCHEMA_VERSION,
            "generator": "SchemaGenerator", "source_model": "FieldSchema", "tables": [],
            "relations": [], "review_warnings": []}
        for copybook_id, copybook in knowledge.copybooks.items():
            if not copybook.properties.get("copybook_model_version"):
                schema["review_warnings"].append({"copybook_id": copybook_id, "reason": "Legacy flat copybook model; re-analysis required.", "status": "REVIEW_REQUIRED"})
                continue
            table = self._resolve_copybook(copybook_id, copybook, schema)
            if table["columns"] or table["child_tables"]:
                schema["tables"].append(table)
                schema["tables"].extend(table.pop("child_tables"))
        # Syntax emission is intentionally downstream of all resolution. The
        # resulting objects are the only DDL payload persisted for v2 runs.
        from src.metadata.script_generator import PostgresScriptGenerator
        schema["generated_schemas"] = PostgresScriptGenerator.generate_resolved_schemas(
            schema, knowledge.repository_id, schema.get("run_id")
        )
        knowledge.database_schema = schema
        return schema

    def _resolve_copybook(self, copybook_id: str, copybook: Any, schema: dict[str, Any]) -> dict[str, Any]:
        table_name = _identifier(copybook_id.replace(".CPY", "").replace(".COPY", ""))
        table: dict[str, Any] = {"name": table_name, "copybook_id": copybook_id, "source_file": copybook.filepath,
            "columns": [], "primary_keys": [], "foreign_keys": [], "child_tables": [], "resolutions": [],
            "review_warnings": [], "key_policy": "NO_BUSINESS_KEY_INFERRED"}
        self._walk(copybook.fields, [], table, schema, set(), table_name)
        # No business key is inferred from source names. Every safely emitted
        # record gets one explicit technical key, whether or not it currently
        # has an OCCURS child table; that keeps the relational identity policy
        # deterministic and makes future direct child relationships safe.
        table["columns"].insert(0, {"name": "RECORD_ID", "sql_type": "BIGSERIAL", "postgres_type": "BIGSERIAL",
            "logical_type": "Technical identifier", "nullable": False, "is_primary": True, "is_technical": True,
            "mapping_quality": "EXACT", "strategy": "TECHNICAL_RECORD_KEY"})
        table["primary_keys"] = ["RECORD_ID"]
        table["key_policy"] = "GENERATED_TECHNICAL_RECORD_KEY"
        return table

    def _walk(self, nodes: Iterable[FieldSchema], path: list[str], table: dict[str, Any], schema: dict[str, Any], used: set[str], parent_table: str) -> None:
        nodes = list(nodes); siblings = {node.name: node for node in nodes}
        for node in nodes:
            node_path, source_path = path + [node.name], ".".join(path + [node.name])
            if node.node_type in {"CONDITION", "RENAMES"}:
                continue
            if node.is_filler:
                table["resolutions"].append(self._resolution(node, source_path, "EXCLUDE_FILLER", False))
                continue
            if node.redefines_target:
                decision = RedefinesResolutionEngine.resolve(siblings.get(node.redefines_target), node)
                table["resolutions"].append(self._resolution(node, source_path, decision["strategy"], decision["strategy"] == "ALTERNATE_REPRESENTATION", decision))
                if decision["strategy"] == "ALTERNATE_REPRESENTATION":
                    for safe in decision["safe_children"]:
                        self._add_dict_column(safe, node_path + [safe.get("name", "FIELD")], table, used, decision)
                elif decision["strategy"] == "REVIEW_REQUIRED":
                    self._review(table, schema, node, source_path, decision["reason"])
                    self._mark_nested_constructs_for_review(node.children, node_path, table, schema, "Contained by unresolved REDEFINES layout.")
                else:
                    self._mark_nested_constructs_for_review(node.children, node_path, table, schema, "Contained by an alternate REDEFINES layout that is not automatically materialised.")
                # SAME_TABLE keeps canonical storage; SEPARATE_TABLES is advisory only.
                continue
            if node.occurs_min:
                decision = OccursResolutionEngine.resolve(node)
                table["resolutions"].append(self._resolution(node, source_path, decision["strategy"], decision["strategy"] != "REVIEW_REQUIRED", decision))
                if decision["strategy"] == "REVIEW_REQUIRED":
                    self._review(table, schema, node, source_path, decision["reason"]); continue
                if decision["strategy"] == "CHILD_TABLE":
                    self._add_child_table(node, node_path, table, schema, parent_table); continue
                self._add_column(node, node_path, table, used, "INLINE_ARRAY", decision); continue
            if node.children:
                self._walk(node.children, node_path, table, schema, used, parent_table)
            else:
                self._add_column(node, node_path, table, used)

    def _mark_nested_constructs_for_review(self, nodes: Iterable[FieldSchema], path: list[str], table: dict[str, Any], schema: dict[str, Any], reason: str) -> None:
        """Do not let OCCURS hidden by an alternate layout disappear downstream."""
        for node in nodes:
            node_path = path + [node.name]
            if node.occurs_min:
                decision = OccursResolutionEngine.resolve(node)
                combined = f"{reason} Engine candidate: {decision['strategy']}. {decision['reason']}"
                table["resolutions"].append(self._resolution(node, ".".join(node_path), "REVIEW_REQUIRED", False, {"reason": combined, "confidence": "LOW"}))
                self._review(table, schema, node, ".".join(node_path), combined)
            self._mark_nested_constructs_for_review(node.children, node_path, table, schema, reason)

    def _add_child_table(self, node: FieldSchema, node_path: list[str], table: dict[str, Any], schema: dict[str, Any], parent_table: str) -> None:
        child_name = f"{parent_table}_{_identifier('_'.join(node_path))}"
        child = {"name": child_name, "copybook_id": table.get("copybook_id"), "parent_table": parent_table, "columns": [
            {"name": "PARENT_RECORD_ID", "sql_type": "BIGINT", "postgres_type": "BIGINT", "nullable": False, "is_parent_reference": True, "strategy": "CHILD_TABLE"},
            {"name": "OCCURRENCE_INDEX", "sql_type": "INTEGER", "postgres_type": "INTEGER", "nullable": False, "is_occurrence_index": True, "strategy": "CHILD_TABLE"}],
            "primary_keys": ["PARENT_RECORD_ID", "OCCURRENCE_INDEX"], "foreign_keys": [{"column": "PARENT_RECORD_ID", "references_table": parent_table, "references_column": "RECORD_ID", "evidence": "OCCURS transformation"}],
            "source_node_id": node.node_id, "source_path": ".".join(node_path), "source_file": node.source_file, "source_line": node.source_line,
            "evidence_ids": node.evidence_ids, "strategy": "CHILD_TABLE", "resolutions": [], "review_warnings": []}
        self._walk(node.children, node_path, child, schema, {"PARENT_RECORD_ID", "OCCURRENCE_INDEX"}, child_name)
        table["child_tables"].append(child)
        schema["relations"].append({"type": "OCCURS_CHILD_TABLE", "parent_table": parent_table, "child_table": child_name,
            "source_node_id": node.node_id, "occurs_min": node.occurs_min, "occurs_max": node.occurs_max})

    def _add_column(self, node: FieldSchema, path: list[str], table: dict[str, Any], used: set[str], strategy: str = "DIRECT", occurs: dict[str, Any] | None = None) -> None:
        sql_type, logical, confidence, reason, quality = PostgresMapper.map_parsed_field(node)
        if not sql_type:
            self._review(table, schema={"review_warnings": table["review_warnings"]}, node=node, path=".".join(path), reason=reason); return
        if occurs: sql_type += "[]"
        self._store_column(table, used, self._column(node, path, sql_type, logical, confidence, reason, quality, strategy, occurs))

    def _add_dict_column(self, raw: dict[str, Any], path: list[str], table: dict[str, Any], used: set[str], decision: dict[str, Any]) -> None:
        sql_type, logical, confidence, reason, quality = PostgresMapper.map_parsed_field(raw)
        if not sql_type: return
        column = self._column(raw, path, sql_type, logical, confidence, reason, quality, "ALTERNATE_REPRESENTATION")
        column.update({"is_alternate_repr": True, "redefines_target": decision["original_field_name"], "alternate_group": path[-2] if len(path) > 1 else None})
        self._store_column(table, used, column)

    def _column(self, node: Any, path: list[str], sql_type: str, logical: str, confidence: str, reason: str, quality: str, strategy: str, occurs: dict[str, Any] | None = None) -> dict[str, Any]:
        get = node.get if isinstance(node, dict) else lambda key, default=None: getattr(node, key, default)
        return {"name": _identifier(path[-1]), "sql_type": sql_type, "postgres_type": sql_type, "logical_type": logical, "nullable": True, "is_primary": False, "is_excluded": False,
            "source_node_id": get("node_id"), "source_name": get("name"), "source_path": ".".join(path), "source_file": get("source_file"), "source_line": get("source_line"), "evidence_ids": get("evidence_ids", []),
            "physical_offset": get("absolute_offset"), "physical_length": get("byte_length") or get("length"), "original_pic": get("pic") or get("data_type"), "pic_category": get("pic_category"), "precision": get("precision"), "scale": get("scale"), "usage": get("usage"),
            "strategy": strategy, "confidence": confidence, "conversion_reason": reason, "mapping_quality": quality,
            "occurs_min": occurs.get("min_occurs") if occurs else None, "occurs_max": occurs.get("max_occurs") if occurs else None, "occurs_depending_on": get("occurs_depending_on")}

    @staticmethod
    def _store_column(table: dict[str, Any], used: set[str], column: dict[str, Any]) -> None:
        base = column["name"] if column["name"] not in used else _identifier(column["source_path"])
        candidate, count = base, 2
        while candidate in used: candidate, count = f"{base}_{count}", count + 1
        column["name"] = candidate; used.add(candidate); table["columns"].append(column)

    @staticmethod
    def _resolution(node: FieldSchema, path: str, strategy: str, include: bool, decision: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"source_node_id": node.node_id, "source_name": node.name, "source_path": path, "physical_offset": node.absolute_offset, "physical_length": node.byte_length,
            "strategy": strategy, "include_in_schema": include, "is_filler": node.is_filler, "redefines_target": node.redefines_target, "occurs_min": node.occurs_min, "occurs_max": node.occurs_max, "occurs_depending_on": node.occurs_depending_on,
            "review_required": strategy == "REVIEW_REQUIRED", "review_reason": (decision or {}).get("reason"), "confidence": (decision or {}).get("confidence", "HIGH"), "source_file": node.source_file, "source_line": node.source_line, "evidence_ids": node.evidence_ids}

    @staticmethod
    def _review(table: dict[str, Any], schema: dict[str, Any], node: FieldSchema, path: str, reason: str) -> None:
        warning = {"source_node_id": node.node_id, "source_path": path, "source_file": node.source_file, "source_line": node.source_line, "evidence_ids": node.evidence_ids, "reason": reason, "status": "REVIEW_REQUIRED"}
        table["review_warnings"].append(warning); schema.setdefault("review_warnings", []).append(warning)
