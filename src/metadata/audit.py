"""Persistent, evidence-backed audit events for repository analysis."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field


AUDIT_MODEL_VERSION = "1.0.0"
_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*([:=])\s*([^\s,;]+)"
)


def sanitize_audit_value(value: Any) -> Any:
    """Remove credentials and absolute local paths before persistence."""
    if isinstance(value, str):
        value = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", value)
        # Source paths are repository-relative throughout the audit API.  Do
        # not persist a local drive path from a caught exception.
        return re.sub(r"(?i)[a-z]:\\[^\r\n]*", "[LOCAL_PATH]", value)
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if re.search(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)", str(key)) else sanitize_audit_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [sanitize_audit_value(item) for item in value]
    return value


class AuditEvent(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    repository_id: str
    run_id: Optional[str] = None
    artifact_id: Optional[str] = None
    artifact_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stage: str
    component: str
    action: str
    event_type: str
    status: str = "SUCCESS"
    severity: str = "INFO"
    confidence: Optional[str] = None
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    input_reference: Optional[str] = None
    output_reference: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    rule_id: Optional[str] = None
    strategy: Optional[str] = None
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    source_end_line: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    audit_model_version: str = AUDIT_MODEL_VERSION


def summarize_audit_events(events: Iterable[AuditEvent | dict[str, Any]]) -> dict[str, Any]:
    values = [event.model_dump(mode="json") if isinstance(event, AuditEvent) else event for event in events]
    by_stage: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0, "warnings": 0, "review_required": 0, "failed": 0})
    event_types = Counter()
    counts = {"total": len(values), "success": 0, "warnings": 0, "review_required": 0, "failed": 0}
    for event in values:
        status = str(event.get("status", "")).upper()
        severity = str(event.get("severity", "")).upper()
        bucket = by_stage[str(event.get("stage", "UNKNOWN"))]
        bucket["total"] += 1
        event_types[str(event.get("event_type", "unknown"))] += 1
        if status == "FAILED":
            counts["failed"] += 1
            bucket["failed"] += 1
        elif status == "REVIEW_REQUIRED":
            counts["review_required"] += 1
            bucket["review_required"] += 1
        elif severity in {"WARNING", "ERROR", "CRITICAL"}:
            counts["warnings"] += 1
            bucket["warnings"] += 1
        elif status == "SUCCESS":
            counts["success"] += 1
            bucket["success"] += 1
    return {**counts, "by_stage": dict(by_stage), "by_event_type": dict(event_types), "audit_model_version": AUDIT_MODEL_VERSION}


class AuditTrail:
    """Append-only audit collector bound to one real pipeline session."""

    def __init__(self, session):
        self.session = session
        self.session.execution_metadata.setdefault("audit_run_id", str(uuid.uuid4()))

    def record(self, *, stage: str, component: str, action: str, event_type: str,
               summary: str, status: str = "SUCCESS", severity: str = "INFO",
               confidence: Optional[str] = None, artifact_id: Optional[str] = None,
               artifact_name: Optional[str] = None, source_file: Optional[str] = None,
               source_line: Optional[int] = None, source_end_line: Optional[int] = None,
               evidence_ids: Optional[list[str]] = None, rule_id: Optional[str] = None,
               strategy: Optional[str] = None, details: Optional[dict[str, Any]] = None,
               input_reference: Optional[str] = None, output_reference: Optional[str] = None,
               metadata: Optional[dict[str, Any]] = None) -> AuditEvent:
        event = AuditEvent(
            job_id=str(self.session.execution_metadata.get("job_id") or self.session.repository_id),
            repository_id=self.session.repository_id, run_id=self.session.execution_metadata["audit_run_id"], artifact_id=artifact_id,
            artifact_name=artifact_name, stage=stage, component=component,
            action=action, event_type=event_type, status=status, severity=severity,
            confidence=confidence, summary=sanitize_audit_value(summary),
            details=sanitize_audit_value(details or {}), input_reference=input_reference,
            output_reference=output_reference, evidence_ids=list(evidence_ids or []),
            rule_id=rule_id, strategy=strategy, source_file=sanitize_audit_value(source_file),
            source_line=source_line, source_end_line=source_end_line,
            metadata=sanitize_audit_value(metadata or {}),
        )
        self.session.audit_events.append(event)
        # Keep existing EventBus observability; persistence remains owned by the
        # session/output store, not by an in-memory subscriber.
        from src.orchestrator.event_bus import event_bus
        event_bus.publish("AuditEventRecorded", event.model_dump(mode="json"))
        return event

    def persist(self, output_dir: str) -> list[dict[str, Any]]:
        """Append this run to repository audit history and return all events."""
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, "audit_events.json")
        prior: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as source:
                prior = json.load(source)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        current = [event.model_dump(mode="json") for event in self.session.audit_events]
        known = {event.get("audit_id") for event in prior if isinstance(event, dict)}
        all_events = prior + [event for event in current if event["audit_id"] not in known]
        with open(path, "w", encoding="utf-8") as target:
            json.dump(all_events, target, indent=2)
        return all_events

    def record_schema_decisions(self, knowledge) -> None:
        """Observe real schema output and resolution-engine decisions.

        This deliberately does not alter mapping rules. It invokes the same
        deterministic resolution engines on the canonical field data and
        records their returned strategy, reason, and evidence references.
        """
        from src.analyzers.redefines_resolution_engine import RedefinesResolutionEngine
        from src.analyzers.occurs_resolution_engine import OccursResolutionEngine
        from src.metadata.script_generator import PostgresScriptGenerator

        evidence = list(getattr(self.session, "extracted_evidence", []) or [])

        def field_dict(field):
            return field.model_dump() if hasattr(field, "model_dump") else dict(field)

        def matching_evidence(field_name, source_file):
            matched = [item for item in evidence if item.entity_name == field_name and item.source_file == source_file]
            lines = [item.source_line for item in matched if item.source_line is not None]
            if not lines and source_file and field_name:
                # Older copybook extractors do not emit one Evidence object per
                # field. Preserve source traceability without inventing an
                # evidence reference by locating the real declaration line.
                try:
                    path = os.path.join(self.session.execution_metadata.get("input_dir", ""), source_file)
                    with open(path, "r", encoding="utf-8", errors="replace") as source:
                        for line_number, text in enumerate(source, start=1):
                            if re.search(rf"\b{re.escape(str(field_name))}\b", text, re.IGNORECASE):
                                lines.append(line_number)
                                break
                except OSError:
                    pass
            return [item.evidence_id for item in matched], (min(lines) if lines else None), (max(lines) if lines else None)

        self.record(stage="SCHEMA", component="SchemaGenerator", action="generate_schema",
                    event_type="schema_generation_started", summary="Generating relational schema from copybook structures.")
        for copybook_id, copybook in (getattr(knowledge, "copybooks", {}) or {}).items():
            source_file = getattr(copybook, "filepath", None)

            def walk(fields):
                siblings = {field_dict(item).get("name"): field_dict(item) for item in fields}
                for item in fields:
                    node = field_dict(item)
                    field_name = node.get("name")
                    evidence_ids, start_line, end_line = matching_evidence(field_name, source_file)
                    common = {"artifact_id": copybook_id, "artifact_name": copybook_id, "source_file": source_file,
                              "source_line": start_line, "source_end_line": end_line, "evidence_ids": evidence_ids}
                    if node.get("redefines"):
                        decision = RedefinesResolutionEngine.resolve(siblings.get(node.get("redefines")), node)
                        review = decision.get("strategy") == "REVIEW_REQUIRED"
                        self.record(stage="REDEFINES", component="RedefinesResolutionEngine", action="detect_redefines",
                                    event_type="redefines_detected", summary=f"REDEFINES detected for {field_name} over {node.get('redefines')}.",
                                    details={"original_field": node.get("redefines"), "redefining_field": field_name}, **common)
                        self.record(stage="REDEFINES", component="RedefinesResolutionEngine", action="resolve_redefines",
                                    event_type="redefines_review_required" if review else "redefines_resolved",
                                    status="REVIEW_REQUIRED" if review else "SUCCESS", severity="WARNING" if review else "INFO",
                                    confidence=decision.get("confidence"), strategy=decision.get("strategy"), rule_id="REDEFINES",
                                    summary=f"REDEFINES strategy {decision.get('strategy')} selected for {field_name}.",
                                    details={"reason": decision.get("reason"), "result": decision}, **common)
                    if node.get("occurs"):
                        decision = OccursResolutionEngine.resolve(node)
                        review = decision.get("needs_manual_review")
                        self.record(stage="OCCURS", component="OccursResolutionEngine", action="detect_occurs",
                                    event_type="occurs_detected", summary=f"OCCURS detected for {field_name}.",
                                    details={"occurs": node.get("occurs")}, **common)
                        self.record(stage="OCCURS", component="OccursResolutionEngine", action="resolve_occurs",
                                    event_type="occurs_review_required" if review else "occurs_resolved",
                                    status="REVIEW_REQUIRED" if review else "SUCCESS", severity="WARNING" if review else "INFO",
                                    confidence=decision.get("confidence"), strategy=decision.get("strategy"), rule_id="OCCURS",
                                    summary=f"OCCURS strategy {decision.get('strategy')} selected for {field_name}.",
                                    details={"reason": decision.get("reason"), "result": decision}, **common)
                    if node.get("children"):
                        walk(getattr(item, "children", node.get("children") or []))

            walk(getattr(copybook, "fields", []) or [])

        schema = getattr(knowledge, "database_schema", {}) or {}
        # Audit observes canonical scripts produced earlier by
        # PostgresScriptGenerator. It must never regenerate competing DDL.
        for generated in schema.get("generated_schemas", []):
            status = generated.get("status", "FAILED")
            event_type = "ddl_generation_failed" if status == "FAILED" else "ddl_generation_warning" if generated.get("warnings") else "ddl_generated"
            self.record(stage="DDL", component="PostgresScriptGenerator", action="observe_generated_schema", event_type=event_type,
                        status=status, severity="ERROR" if status == "FAILED" else "WARNING" if generated.get("warnings") else "INFO",
                        artifact_id=generated.get("artifact_id"), artifact_name=generated.get("artifact_id"), output_reference=generated.get("schema_id"),
                        summary=f"Observed canonical PostgreSQL DDL for {generated.get('artifact_id')}.",
                        details={"generated_schema_id": generated.get("generated_schema_id"), "table_names": generated.get("table_names"),
                                 "ddl_hash": generated.get("ddl_hash"), "warnings": generated.get("warnings", []), "status": status})
        self.record(stage="SCHEMA", component="SchemaGenerator", action="complete", event_type="schema_generation_completed",
                    summary="Schema generation observation completed.", details={"table_count": len(schema.get("tables", []))})
