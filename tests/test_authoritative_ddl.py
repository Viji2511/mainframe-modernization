import hashlib
import json

from api.repository_api import _canonical_generated_schema
from src.metadata.script_generator import DDL_GENERATOR_VERSION, PostgresScriptGenerator


def _resolved(warnings=None):
    parent = {"name": "ACCOUNT", "copybook_id": "ACCOUNT", "columns": [
        {"name": "RECORD_ID", "sql_type": "BIGSERIAL", "nullable": False, "is_technical": True},
        {"name": "PHONE", "sql_type": "VARCHAR(10)[]", "nullable": True, "source_path": "REC.PHONE", "strategy": "INLINE_ARRAY"},
    ], "primary_keys": ["RECORD_ID"], "foreign_keys": [], "review_warnings": warnings or []}
    child = {"name": "ACCOUNT_ADDRESS", "parent_table": "ACCOUNT", "columns": [
        {"name": "PARENT_RECORD_ID", "sql_type": "BIGINT", "nullable": False},
        {"name": "OCCURRENCE_INDEX", "sql_type": "INTEGER", "nullable": False},
        {"name": "CITY", "sql_type": "VARCHAR(20)", "nullable": True},
    ], "primary_keys": ["PARENT_RECORD_ID", "OCCURRENCE_INDEX"],
    "foreign_keys": [{"column": "PARENT_RECORD_ID", "references_table": "ACCOUNT", "references_column": "RECORD_ID"}], "review_warnings": []}
    return {"resolved_schema_version": "2.0.0", "tables": [parent, child]}


def test_canonical_ddl_uses_resolved_types_keys_arrays_and_child_order_only():
    generated = PostgresScriptGenerator.generate_resolved_schemas(_resolved(), "repo", "run")[0]
    ddl = generated["ddl"]
    assert generated["ddl_generator_version"] == DDL_GENERATOR_VERSION
    assert '"record_id" BIGSERIAL NOT NULL' in ddl
    assert ddl.count("PRIMARY KEY") == 2  # one parent constraint, one child composite constraint
    assert 'PRIMARY KEY ("parent_record_id", "occurrence_index")' in ddl
    assert 'FOREIGN KEY ("parent_record_id") REFERENCES "account" ("record_id")' in ddl
    assert '"phone" VARCHAR(10)[]' in ddl
    assert ddl.index('CREATE TABLE "account"') < ddl.index('CREATE TABLE "account_address"')
    assert generated["ddl_hash"] == hashlib.sha256(ddl.encode()).hexdigest()


def test_preflight_rejects_duplicate_columns_and_invalid_foreign_key():
    bad = _resolved()
    bad["tables"][0]["columns"].append({"name": "PHONE", "sql_type": "TEXT"})
    bad["tables"][1]["foreign_keys"][0]["references_column"] = "MISSING"
    generated = PostgresScriptGenerator.generate_resolved_schemas(bad, "repo")[0]
    assert generated["status"] == "FAILED"
    assert generated["ddl"] == ""
    assert generated["warnings"]


def test_review_warnings_are_preserved_without_emitting_excluded_columns():
    schema = _resolved([{"status": "REVIEW_REQUIRED", "reason": "Ambiguous REDEFINES"}])
    schema["tables"][0]["columns"].append({"name": "UNSAFE", "sql_type": "TEXT", "is_excluded": True})
    generated = PostgresScriptGenerator.generate_resolved_schemas(schema, "repo")[0]
    assert generated["status"] == "REVIEW_REQUIRED"
    assert "unsafe" not in generated["ddl"].lower()
    assert generated["warnings"][0]["reason"] == "Ambiguous REDEFINES"


def test_canonical_lookup_returns_the_persisted_object_unchanged():
    generated = PostgresScriptGenerator.generate_resolved_schemas(_resolved(), "repo")[0]
    knowledge = {"database_schema": {"generated_schemas": [generated]}}
    assert _canonical_generated_schema(knowledge, "ACCOUNT") == generated
