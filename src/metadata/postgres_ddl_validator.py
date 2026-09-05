"""Real PostgreSQL validation for persisted canonical GeneratedSchema objects.

The validator executes the exact stored DDL inside a transaction-local,
per-script schema. It never regenerates or rewrites SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import os
import re
import time
from typing import Any

from src.metadata.audit import sanitize_audit_value


VALIDATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class PostgresValidationConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str = "prefer"

    @classmethod
    def from_environment(cls) -> "PostgresValidationConfig | None":
        if os.getenv("ALLOW_SCHEMA_VALIDATION", "").lower() != "true":
            return None
        values = {key: os.getenv(f"POSTGRES_VALIDATION_{key}") for key in ("HOST", "PORT", "DB", "USER", "PASSWORD")}
        if not all(values.values()):
            return None
        return cls(host=str(values["HOST"]), port=int(str(values["PORT"])), database=str(values["DB"]),
                   user=str(values["USER"]), password=str(values["PASSWORD"]), sslmode=os.getenv("POSTGRES_VALIDATION_SSLMODE", "prefer"))


class PostgresDDLValidator:
    """Executes and verifies canonical DDL against an explicit validation DB."""
    def __init__(self, config: PostgresValidationConfig | None = None):
        self.config = config or PostgresValidationConfig.from_environment()

    def validate_all(self, generated_schemas: list[dict[str, Any]], audit=None) -> list[dict[str, Any]]:
        return [self.validate(generated, audit=audit) for generated in generated_schemas]

    def validate(self, generated: dict[str, Any], audit=None) -> dict[str, Any]:
        ddl, expected_hash = generated.get("ddl", ""), generated.get("ddl_hash")
        computed_hash = sha256(ddl.encode("utf-8")).hexdigest() if ddl else None
        base = {"validator_version": VALIDATOR_VERSION, "generated_schema_id": generated.get("generated_schema_id"),
                "schema_id": generated.get("schema_id"), "artifact_id": generated.get("artifact_id"),
                "repository_id": generated.get("repository_id"), "run_id": generated.get("run_id"),
                "ddl_hash": expected_hash, "validated_ddl_hash": computed_hash, "tables_expected": generated.get("table_names", []),
                "tables_created": [], "validation_checks": [], "errors": [], "warnings": list(generated.get("warnings", [])),
                "executed": False, "postgres_version": None, "validated_at": datetime.now(timezone.utc).isoformat()}
        if generated.get("status") == "FAILED":
            return self._complete(base, "NOT_EXECUTED_GENERATION_FAILED", audit)
        if not ddl:
            base["errors"].append("Canonical generated DDL is empty.")
            return self._complete(base, "FAILED_VALIDATION", audit)
        if computed_hash != expected_hash:
            base["errors"].append("Persisted DDL hash does not match the exact execution candidate.")
            return self._complete(base, "FAILED_VALIDATION", audit)
        if not self.config:
            base["warnings"].append({"status": "SKIPPED_CONFIGURATION", "reason": "Validation requires ALLOW_SCHEMA_VALIDATION=true and POSTGRES_VALIDATION_* configuration."})
            return self._complete(base, "SKIPPED_CONFIGURATION", audit)
        self._audit(audit, "ddl_validation_started", generated, "SUCCESS", {"ddl_hash": expected_hash})
        start = time.perf_counter()
        schema_name = f"mfm_validation_{computed_hash[:16]}"
        try:
            import psycopg
            from psycopg import sql
            with psycopg.connect(host=self.config.host, port=self.config.port, dbname=self.config.database,
                                 user=self.config.user, password=self.config.password, sslmode=self.config.sslmode) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT version()")
                    base["postgres_version"] = cursor.fetchone()[0]
                    cursor.execute(sql.SQL("CREATE SCHEMA {} ").format(sql.Identifier(schema_name)))
                    cursor.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema_name)))
                    # Exact canonical text: no formatting, splitting, or repair.
                    cursor.execute(ddl)
                    base["executed"] = True
                    self._verify_catalog(cursor, generated, base)
                    connection.rollback()  # deterministic per-script cleanup
        except Exception as exc:
            base["errors"].append({"message": sanitize_audit_value(str(exc)), "sqlstate": getattr(exc, "sqlstate", None)})
        base["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 2)
        status = "FAILED_VALIDATION" if base["errors"] else "REVIEW_REQUIRED_VALIDATED_SAFE_SUBSET" if generated.get("status") == "REVIEW_REQUIRED" else "VALIDATED"
        return self._complete(base, status, audit)

    def _verify_catalog(self, cursor, generated: dict[str, Any], result: dict[str, Any]) -> None:
        expected_tables = list(generated.get("table_names", []))
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
        actual = {row[0].upper() for row in cursor.fetchall()}
        result["tables_created"] = [table for table in expected_tables if table.upper() in actual]
        self._check(result, "tables", set(table.upper() for table in expected_tables) == actual, {"actual": sorted(actual)})
        mappings = generated.get("column_mappings", {})
        for table in expected_tables:
            cursor.execute("SELECT column_name, data_type, udt_name, numeric_precision, numeric_scale FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s", (table.lower(),))
            columns = {row[0].upper(): row[1:] for row in cursor.fetchall()}
            for expected in mappings.get(table, []):
                name, observed = expected.get("name", "").upper(), columns.get(expected.get("name", "").upper())
                self._check(result, f"column:{table}.{name}", observed is not None and self._type_matches(expected.get("sql_type"), observed), {"expected": expected.get("sql_type"), "actual": observed})
            self._verify_keys(cursor, table, generated, result)

    def _verify_keys(self, cursor, table: str, generated: dict[str, Any], result: dict[str, Any]) -> None:
        cursor.execute("""SELECT a.attname FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN unnest(i.indkey) WITH ORDINALITY keys(attnum, ord) ON true JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=keys.attnum WHERE n.nspname=current_schema() AND c.relname=%s AND i.indisprimary ORDER BY keys.ord""", (table.lower(),))
        actual_pk = [row[0].upper() for row in cursor.fetchall()]
        expected_table = next((item for item in generated.get("resolved_tables", []) if item.get("name") == table), None)
        # GeneratedSchema retains mappings but not entire resolved tables. PK/FK
        # expectation is carried by generated metadata when available.
        expected_pk = (generated.get("table_constraints", {}).get(table, {}) or {}).get("primary_keys")
        if expected_pk is not None:
            self._check(result, f"pk:{table}", actual_pk == [str(item).upper() for item in expected_pk], {"actual": actual_pk})
        expected_fks = (generated.get("table_constraints", {}).get(table, {}) or {}).get("foreign_keys", [])
        for foreign_key in expected_fks:
            cursor.execute("""SELECT pg_get_constraintdef(con.oid) FROM pg_constraint con JOIN pg_class rel ON rel.oid=con.conrelid JOIN pg_namespace n ON n.oid=rel.relnamespace WHERE n.nspname=current_schema() AND rel.relname=%s AND con.contype='f'""", (table.lower(),))
            definitions = " ".join(row[0].upper() for row in cursor.fetchall())
            valid = all(token in definitions for token in (str(foreign_key["column"]).upper(), str(foreign_key["references_table"]).upper(), str(foreign_key["references_column"]).upper()))
            self._check(result, f"fk:{table}.{foreign_key['column']}", valid, {"definitions": definitions})

    @staticmethod
    def _type_matches(expected: str | None, observed: tuple[Any, ...]) -> bool:
        if not expected:
            return False
        data_type, udt_name, precision, scale = observed
        source = expected.upper()
        if source.endswith("[]"):
            return data_type == "ARRAY"
        if source == "BIGSERIAL":
            return data_type == "bigint"
        if source.startswith("VARCHAR"):
            return data_type == "character varying"
        if source.startswith("NUMERIC"):
            match = re.search(r"NUMERIC\((\d+),(\d+)\)", source)
            return data_type == "numeric" and (not match or (precision, scale) == (int(match.group(1)), int(match.group(2))))
        return data_type.upper() == source.lower().upper() or udt_name.upper() == source.lower().upper()

    @staticmethod
    def _check(result: dict[str, Any], name: str, passed: bool, details: dict[str, Any]) -> None:
        result["validation_checks"].append({"name": name, "passed": passed, **details})
        if not passed:
            result["errors"].append({"check": name, **details})

    def _complete(self, result: dict[str, Any], status: str, audit) -> dict[str, Any]:
        result["validation_status"] = status
        event = "ddl_validation_passed" if status == "VALIDATED" else "ddl_validation_warning" if "VALIDATED" in status or status.startswith("SKIPPED") else "ddl_validation_failed"
        self._audit(audit, event, result, status, {"ddl_hash": result.get("ddl_hash"), "checks": result.get("validation_checks"), "errors": result.get("errors"), "postgres_version": result.get("postgres_version")})
        return result

    @staticmethod
    def _audit(audit, event_type: str, item: dict[str, Any], status: str, details: dict[str, Any]) -> None:
        if audit:
            audit.record(stage="DDL_VALIDATION", component="PostgresDDLValidator", action="validate", event_type=event_type,
                         status=status, severity="ERROR" if status == "FAILED_VALIDATION" else "WARNING" if status != "VALIDATED" else "INFO",
                         artifact_id=item.get("artifact_id"), artifact_name=item.get("artifact_id"), output_reference=item.get("schema_id"),
                         summary=f"PostgreSQL validation status {status} for {item.get('artifact_id')}.", details=details)
