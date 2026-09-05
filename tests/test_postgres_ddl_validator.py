import hashlib
import os

import pytest

from src.metadata.postgres_ddl_validator import PostgresDDLValidator, PostgresValidationConfig


def _generated(**overrides):
    value = {"generated_schema_id": "GeneratedSchema:test:ACCOUNT", "schema_id": "schema:test:ACCOUNT", "artifact_id": "ACCOUNT", "repository_id": "test", "run_id": "run", "status": "GENERATED",
             "ddl": 'CREATE TABLE "account" (\n    "record_id" BIGSERIAL NOT NULL,\n    PRIMARY KEY ("record_id")\n);', "table_names": ["ACCOUNT"],
             "column_mappings": {"ACCOUNT": [{"name": "RECORD_ID", "sql_type": "BIGSERIAL"}]},
             "table_constraints": {"ACCOUNT": {"primary_keys": ["RECORD_ID"], "foreign_keys": []}}, "warnings": []}
    value["ddl_hash"] = hashlib.sha256(value["ddl"].encode()).hexdigest()
    value.update(overrides)
    return value


def test_validator_never_executes_when_persisted_hash_does_not_match():
    generated = _generated(ddl_hash="not-the-real-hash")
    result = PostgresDDLValidator(config=None).validate(generated)
    assert result["validation_status"] == "FAILED_VALIDATION"
    assert not result["executed"]


def test_failed_generation_is_not_executed():
    result = PostgresDDLValidator(config=None).validate(_generated(status="FAILED"))
    assert result["validation_status"] == "NOT_EXECUTED_GENERATION_FAILED"
    assert not result["executed"]


def test_missing_explicit_validation_configuration_is_visible_skip(monkeypatch):
    for key in ("ALLOW_SCHEMA_VALIDATION", "POSTGRES_VALIDATION_HOST", "POSTGRES_VALIDATION_PORT", "POSTGRES_VALIDATION_DB", "POSTGRES_VALIDATION_USER", "POSTGRES_VALIDATION_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    result = PostgresDDLValidator().validate(_generated())
    assert result["validation_status"] == "SKIPPED_CONFIGURATION"
    assert not result["executed"]


@pytest.mark.integration
def test_real_postgres_canonical_ddl_when_explicitly_configured():
    """Real-engine test; skipped rather than mocked when no validation DB is designated."""
    config = PostgresValidationConfig.from_environment()
    if config is None:
        pytest.skip("Set ALLOW_SCHEMA_VALIDATION=true and POSTGRES_VALIDATION_* for real PostgreSQL integration.")
    result = PostgresDDLValidator(config=config).validate(_generated())
    assert result["validation_status"] == "VALIDATED", result
    assert result["executed"] and result["postgres_version"]
