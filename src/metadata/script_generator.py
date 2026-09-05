"""Canonical PostgreSQL syntax emission from the resolved relational schema.

This module deliberately knows nothing about COBOL, PIC clauses, OCCURS, or
REDEFINES. Those decisions have already been persisted in the resolved schema.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import re
from typing import Any, Iterable


DDL_GENERATOR_VERSION = "2.0.0"


class PostgresScriptGenerator:
    """The only DDL generator used by version-2 repository analyses."""

    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_]+", "_", str(value).replace("-", "_"))
        return clean.strip("_").lower() or "unnamed"

    @classmethod
    def quote_identifier(cls, name: str) -> str:
        return f'"{cls.normalize_identifier(name)}"'

    @classmethod
    def generate_resolved_schemas(cls, resolved_schema: dict[str, Any], repository_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
        """Produce one canonical script object per resolved source copybook."""
        tables = list(resolved_schema.get("tables") or [])
        primary_tables = [table for table in tables if table.get("copybook_id")]
        output: list[dict[str, Any]] = []
        for parent in sorted(primary_tables, key=lambda table: str(table["name"])):
            ordered = cls._tables_for_source(parent, tables)
            warnings = [*parent.get("review_warnings", [])]
            for table in ordered[1:]:
                warnings.extend(table.get("review_warnings", []))
            issues = cls.preflight(ordered)
            warnings.extend({"status": "FAILED", "reason": issue} for issue in issues)
            status = "FAILED" if issues else "REVIEW_REQUIRED" if warnings else "GENERATED"
            ddl = "" if issues else "\n\n".join(cls._emit_table(table) for table in ordered)
            artifact_id = parent["copybook_id"]
            output.append({
                "generated_schema_id": f"GeneratedSchema:{repository_id}:{artifact_id}",
                "schema_id": f"schema:{repository_id}:{artifact_id}", "artifact_id": artifact_id,
                "repository_id": repository_id, "run_id": run_id,
                "resolved_schema_version": resolved_schema.get("resolved_schema_version"),
                "ddl_generator_version": DDL_GENERATOR_VERSION, "ddl": ddl,
                "ddl_hash": sha256(ddl.encode("utf-8")).hexdigest() if ddl else None,
                "generated_at": datetime.now(timezone.utc).isoformat(), "status": status,
                "warnings": warnings, "review_required": bool(warnings),
                "table_names": [table["name"] for table in ordered], "source_artifact": artifact_id,
                "column_mappings": {table["name"]: [column for column in table.get("columns", []) if not column.get("is_excluded")] for table in ordered},
                "table_constraints": {table["name"]: {"primary_keys": table.get("primary_keys", []), "foreign_keys": table.get("foreign_keys", [])} for table in ordered},
            })
        return output

    @classmethod
    def _tables_for_source(cls, parent: dict[str, Any], all_tables: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for table in all_tables:
            if table.get("parent_table"):
                by_parent.setdefault(str(table["parent_table"]), []).append(table)
        ordered: list[dict[str, Any]] = []
        def visit(table: dict[str, Any]) -> None:
            ordered.append(table)
            for child in sorted(by_parent.get(str(table["name"]), []), key=lambda item: str(item["name"])):
                visit(child)
        visit(parent)
        return ordered

    @classmethod
    def preflight(cls, tables: Iterable[dict[str, Any]]) -> list[str]:
        """Lightweight structural validation; intentionally not SQL execution."""
        values, issues, seen_tables = list(tables), [], set()
        by_name = {str(table.get("name")): table for table in values}
        for table in values:
            name = str(table.get("name") or "")
            normalized = cls.normalize_identifier(name)
            if not name or normalized in seen_tables:
                issues.append(f"Duplicate or missing table name: {name or '<missing>'}")
            seen_tables.add(normalized)
            columns = [column for column in table.get("columns", []) if not column.get("is_excluded")]
            names = [cls.normalize_identifier(column.get("name", "")) for column in columns]
            if len(names) != len(set(names)) or not all(names):
                issues.append(f"Duplicate or missing active column in {name}")
            if any(not column.get("sql_type") for column in columns):
                issues.append(f"Missing resolved SQL type in {name}")
            primary_keys = list(table.get("primary_keys") or [])
            if len(set(cls.normalize_identifier(item) for item in primary_keys)) != len(primary_keys):
                issues.append(f"Duplicate primary-key column in {name}")
            active = set(names)
            if any(cls.normalize_identifier(item) not in active for item in primary_keys):
                issues.append(f"Primary-key column missing from {name}")
            for foreign_key in table.get("foreign_keys") or []:
                column, target, target_column = foreign_key.get("column"), foreign_key.get("references_table"), foreign_key.get("references_column")
                target_table = by_name.get(str(target))
                if cls.normalize_identifier(column or "") not in active:
                    issues.append(f"Foreign-key column missing from {name}")
                elif not target_table or cls.normalize_identifier(target_column or "") not in {cls.normalize_identifier(c.get("name", "")) for c in target_table.get("columns", [])}:
                    issues.append(f"Foreign-key target missing for {name}.{column}")
        return issues

    @classmethod
    def _emit_table(cls, table: dict[str, Any]) -> str:
        defs: list[str] = []
        for column in table.get("columns", []):
            if column.get("is_excluded"):
                continue
            definition = f"    {cls.quote_identifier(column['name'])} {column['sql_type']}"
            if column.get("nullable") is False:
                definition += " NOT NULL"
            defs.append(definition)
        primary_keys = [cls.quote_identifier(column) for column in table.get("primary_keys", [])]
        if primary_keys:
            defs.append(f"    PRIMARY KEY ({', '.join(primary_keys)})")
        for foreign_key in table.get("foreign_keys", []):
            defs.append(f"    FOREIGN KEY ({cls.quote_identifier(foreign_key['column'])}) REFERENCES {cls.quote_identifier(foreign_key['references_table'])} ({cls.quote_identifier(foreign_key['references_column'])})")
        if not defs:
            # An empty source layout is valid only as review-required metadata;
            # do not manufacture a table/key that the resolved schema omitted.
            defs.append("    -- no automatically mappable columns")
        return f"CREATE TABLE {cls.quote_identifier(table['name'])} (\n" + ",\n".join(defs) + "\n);"

    @classmethod
    def generate_ddl(cls, table_name: str, columns: list[dict[str, Any]], child_tables: list[dict[str, Any]]) -> str:
        """Deprecated flat-input compatibility adapter for legacy callers/tests.

        Version-2 pipeline code uses :meth:`generate_resolved_schemas` only.
        """
        parent = {"name": table_name, "columns": columns, "primary_keys": [c["name"] for c in columns if c.get("is_primary")], "foreign_keys": []}
        legacy_children = []
        for child in child_tables:
            child_name = f"{table_name}_{child['name']}"
            parent_pk = parent["primary_keys"]
            child_columns = list(child.get("columns", []))
            if parent_pk:
                pk = parent_pk[0]
                child_columns = [{"name": f"PARENT_{pk}", "sql_type": next(c.get("sql_type") for c in columns if c["name"] == pk), "nullable": False}, {"name": "OCCURRENCE_INDEX", "sql_type": "INTEGER", "nullable": False}, *child_columns]
                fks = [{"column": f"PARENT_{pk}", "references_table": table_name, "references_column": pk}]
                keys = [f"PARENT_{pk}", "OCCURRENCE_INDEX"]
            else:
                fks, keys = [], []
            legacy_children.append({"name": child_name, "parent_table": table_name, "columns": child_columns, "primary_keys": keys, "foreign_keys": fks})
        return "\n\n".join(cls._emit_table(table) for table in [parent, *legacy_children])
