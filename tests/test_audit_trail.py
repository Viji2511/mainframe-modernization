from src.metadata.audit import AuditTrail, sanitize_audit_value, summarize_audit_events
from src.metadata.session import DiscoverySession
from src.models.knowledge_store import CopybookKnowledge, FieldSchema, RepositoryKnowledge, Traceability
from api.repository_api import _filter_audit_events


def test_audit_events_persist_append_and_sanitize(tmp_path):
    session = DiscoverySession(repository_id="audit-repository")
    trail = AuditTrail(session)
    event = trail.record(
        stage="PARSING", component="ExampleParser", action="parse", event_type="parser_failed",
        status="FAILED", severity="ERROR", summary="Parser failed with token=private-value",
        details={"password": "do-not-store", "path": r"C:\private\source.cbl"},
    )
    persisted = trail.persist(str(tmp_path))
    assert persisted[0]["audit_id"] == event.audit_id
    assert "private-value" not in str(persisted)
    assert "do-not-store" not in str(persisted)
    assert "C:\\private" not in str(persisted)

    second_session = DiscoverySession(repository_id="audit-repository")
    second = AuditTrail(second_session)
    second.record(stage="SYSTEM", component="Pipeline", action="complete", event_type="pipeline_completed", summary="Done")
    assert len(second.persist(str(tmp_path))) == 2


def test_audit_filters_and_summary_use_real_event_values():
    session = DiscoverySession(repository_id="audit-repository")
    trail = AuditTrail(session)
    trail.record(stage="PARSING", component="Parser", action="parse", event_type="parser_completed", artifact_id="ONE", summary="One")
    trail.record(stage="OCCURS", component="OccursResolutionEngine", action="resolve", event_type="occurs_review_required", status="REVIEW_REQUIRED", severity="WARNING", artifact_id="TWO", summary="Two")
    events = [event.model_dump(mode="json") for event in session.audit_events]
    filtered = _filter_audit_events(events, stage="OCCURS", status="REVIEW_REQUIRED", artifact_id="TWO")
    assert len(filtered) == 1
    summary = summarize_audit_events(events)
    assert summary["total"] == 2
    assert summary["review_required"] == 1


def test_schema_observation_records_real_redefines_occurs_and_ddl(tmp_path):
    session = DiscoverySession(repository_id="audit-repository")
    session.execution_metadata["input_dir"] = str(tmp_path)
    source = tmp_path / "ACCOUNT.cpy"
    source.write_text("01 ACCOUNT.\n  05 ACCOUNT-ID PIC X(10).\n  05 PHONE PIC X(10) OCCURS 3 TIMES.\n", encoding="utf-8")
    knowledge = RepositoryKnowledge(repository_id="audit-repository")
    knowledge.copybooks["ACCOUNT"] = CopybookKnowledge(
        id="ACCOUNT", name="ACCOUNT", filepath="ACCOUNT.cpy",
        traceability=Traceability(source_file="ACCOUNT.cpy", parser="test"),
        fields=[
            FieldSchema(name="ACCOUNT-ID", data_type="X(10)"),
            FieldSchema(name="PHONE", data_type="X(10)", occurs=3),
        ],
    )
    knowledge.database_schema = {"tables": [{"name": "ACCOUNT", "columns": [{"name": "ACCOUNT_ID", "type": "VARCHAR(10)"}, {"name": "PHONE", "type": "VARCHAR(10)[]"}]}],
        "generated_schemas": [{"generated_schema_id": "GeneratedSchema:audit:ACCOUNT", "schema_id": "schema:audit:ACCOUNT", "artifact_id": "ACCOUNT", "status": "GENERATED", "table_names": ["ACCOUNT"], "ddl_hash": "test-hash", "ddl": 'CREATE TABLE "account" ();', "warnings": []}]}
    trail = AuditTrail(session)
    trail.record_schema_decisions(knowledge)
    events = session.audit_events
    assert any(event.event_type == "occurs_resolved" and event.strategy == "INLINE_ARRAY" for event in events)
    assert any(event.event_type == "ddl_generated" for event in events)
    occurs = next(event for event in events if event.event_type == "occurs_resolved")
    assert occurs.source_line == 3
    assert knowledge.database_schema["generated_schemas"][0]["schema_id"] == "schema:audit:ACCOUNT"


def test_sanitize_audit_value_redacts_nested_secrets():
    value = sanitize_audit_value({"authorization": "Bearer abc", "nested": ["API_KEY=abc"]})
    assert "abc" not in str(value)
