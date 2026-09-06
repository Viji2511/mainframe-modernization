import os
import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from src.agents.modernization_assistant import ModernizationAssistant
from src.store.supabase_client import supabase_db
import re

def _calculate_pic_length(pic_str):
    if not pic_str or pic_str == "GROUP":
        return 0
    pic_str = pic_str.upper().strip()
    digits = 0
    if "V" in pic_str:
        p1, p2 = pic_str.split("V", 1)
        m1 = re.search(r'9\((\d+)\)', p1)
        d1 = int(m1.group(1)) if m1 else p1.count('9')
        m2 = re.search(r'9\((\d+)\)', p2)
        d2 = int(m2.group(1)) if m2 else p2.count('9')
        digits = d1 + d2
    elif "9" in pic_str:
        m = re.search(r'9\((\d+)\)', pic_str)
        digits = int(m.group(1)) if m else pic_str.count('9')
        
    if "COMP-3" in pic_str or "PACKED-DECIMAL" in pic_str:
        import math
        return math.ceil((digits + 1) / 2)
    elif "COMP-1" in pic_str:
        return 4
    elif "COMP-2" in pic_str:
        return 8
    elif "COMP" in pic_str or "BINARY" in pic_str:
        if digits <= 4: return 2
        if digits <= 9: return 4
        return 8
        
    if "X" in pic_str or "A" in pic_str:
        m = re.search(r'[XA]\((\d+)\)', pic_str)
        return int(m.group(1)) if m else pic_str.count('X') or pic_str.count('A') or 1
        
    if digits > 0:
        return digits
    return 0

from src.validators.postgres_mapper import PostgresMapper
from src.analyzers.redefines_resolution_engine import RedefinesResolutionEngine
from src.analyzers.occurs_resolution_engine import OccursResolutionEngine
from src.metadata.audit import summarize_audit_events
from src.security.safety import SecurityValidationError, safe_join, validate_artifact_id, validate_repository_id

logger = logging.getLogger(__name__)


def _parse_pic_to_sql(pic_str: str, field_name: str = "") -> str:
    """Thin public adapter: map a COBOL PIC clause to a PostgreSQL type string.

    Delegates to PostgresMapper.map_pic_to_postgres() so callers (including
    tests) have a single stable entry-point without importing PostgresMapper
    directly.
    """
    pg_type, _log, _conf, _reason = PostgresMapper.map_pic_to_postgres(pic_str, field_name)
    return pg_type

def _flatten_records(records, prefix="", current_offset=0, hierarchy=None, parent_occurs=None, parent_redefines=None, _sibling_offsets=None, parent_occurs_resolution=None):
    """Flatten a hierarchical COBOL field tree into a list of column descriptors.

    REDEFINES handling
    ------------------
    The function calls RedefinesResolutionEngine.resolve() for every field that
    bears a REDEFINES clause (i.e. is the *root* of a redefining group/scalar).
    Child fields that inherit their parent's REDEFINES status carry
    parent_redefines instead.

    Four strategies are handled:

    SAME_TABLE
        Simple scalar type-cast (e.g. PIC X redefines PIC 9).
        The redefining field is marked is_excluded=True — one column exists.

    ALTERNATE_REPRESENTATION  (new)
        The redefining group decomposes the original field's storage into named
        child subfields (e.g. BIRTHDATE → B-M, B-D, B-Y).
        - The redefining *group node itself* is excluded (no duplicate table/column).
        - Each safe_child identified by the engine is emitted as a regular column
          annotated with is_alternate_repr=True and redefines_target pointing back
          to the original canonical field.
        - The original canonical field is left completely untouched.
        - Byte offsets for safe children are computed as:
            original_field_start_offset + child._byte_offset
          so they correctly reflect shared physical storage with the original.

    SEPARATE_TABLES
        Entirely distinct layout (large group or OCCURS inside alt).
        The redefining group is excluded; schema generator may create a separate
        table/view for it via a follow-up pipeline step.

    REVIEW_REQUIRED
        Structural ambiguity (nested REDEFINES, un-safe children, etc.).
        Excluded and annotated for manual review.

    OCCURS handling
    ---------------
    The function calls OccursResolutionEngine.resolve() for every field that
    bears an OCCURS clause directly (not inherited via parent_occurs).

    The resolved strategy is attached to every column emitted from that field
    and all its descendants via parent_occurs_resolution.  The existing
    schema_status = "TRANSFORMATION_REQUIRED: OCCURS" annotation and the
    occurs = <count> key are preserved for backward compatibility.

    Additional keys added to columns with OCCURS:
      occurs_strategy        INLINE_ARRAY | CHILD_TABLE | REVIEW_REQUIRED
      occurs_type            FIXED | VARIABLE | UNKNOWN
      occurs_min             int or None
      occurs_max             int or None
      occurs_is_variable     bool
      occurs_nesting_level   int
      occurs_child_sql_type  str or None  (e.g. "VARCHAR(10)[]")
      occurs_confidence      HIGH | MEDIUM | LOW
      occurs_reason          str
    """
    if hierarchy is None:
        hierarchy = []
    # _sibling_offsets: maps raw field name → byte offset at which it starts.
    # Used so REDEFINES children can anchor their offsets to the original field.
    if _sibling_offsets is None:
        _sibling_offsets = {}
    columns = []
    start_offset_ref = current_offset

    for r in records:
        name = r.get("name", "").replace("-", "_")
        col_name = f"{prefix}_{name}" if prefix else name
        pic = r.get("pic")
        children = r.get("children", [])
        redefines = r.get("redefines") or parent_redefines
        occurs = r.get("occurs") or parent_occurs

        # ------------------------------------------------------------------
        # OCCURS resolution: run at the root OCCURS node only (where the
        # field itself carries the occurs clause, not inherited from a parent).
        # Children inherit the parent's resolution via parent_occurs_resolution.
        # ------------------------------------------------------------------
        occurs_resolution = parent_occurs_resolution
        if r.get("occurs") and not parent_occurs:
            # This is the root OCCURS node — resolve it
            occurs_resolution = OccursResolutionEngine.resolve(r)
        elif r.get("occurs") and parent_occurs:
            # This node has its own OCCURS inside a parent OCCURS → nested
            # Re-resolve for this level; nesting is captured in nesting_level
            occurs_resolution = OccursResolutionEngine.resolve(r)

        strategy_info = None
        is_excluded = False
        reason_adj = "OK"

        if redefines:
            if r.get("redefines"):
                # This field is the *root* of a REDEFINES — resolve it
                siblings = {s.get("name"): s for s in records if s.get("name")}
                orig_node = siblings.get(r.get("redefines"))
                strategy_info = RedefinesResolutionEngine.resolve(orig_node, r)

            # All REDEFINES roots (and their descendants via parent_redefines)
            # are excluded from the primary DDL — the strategy controls what
            # happens to their semantic information, handled below.
            is_excluded = True

        length = r.get("length")
        if not length:
            length = _calculate_pic_length(pic)

        # Record the byte offset of every non-redefining field so that
        # REDEFINES children can later be anchored to the original.
        if not redefines and r.get("name"):
            _sibling_offsets[r.get("name")] = current_offset

        # ------------------------------------------------------------------
        # Build schema_status: REDEFINES check runs first; OCCURS overrides
        # the status string (preserving existing behaviour).
        # ------------------------------------------------------------------
        status = "OK"
        if redefines:
            strat_label = strategy_info["strategy"] if strategy_info else "INHERITED"
            status = f"REVIEW_REQUIRED: REDEFINES ({strat_label})"
        if occurs:
            # Keep the existing status string for backward compatibility.
            # The rich OCCURS metadata is in the occurs_* keys below.
            status = "TRANSFORMATION_REQUIRED: OCCURS"

        # ------------------------------------------------------------------
        # ALTERNATE_REPRESENTATION: emit safe children as annotated columns.
        # We do this at the root REDEFINES node (strategy_info present) only.
        # The group node itself is still excluded; only its resolved children
        # are surfaced.
        # ------------------------------------------------------------------
        if (
            strategy_info
            and strategy_info.get("strategy") == "ALTERNATE_REPRESENTATION"
            and strategy_info.get("safe_children")
        ):
            orig_field_name = strategy_info.get("original_field_name", r.get("redefines", ""))
            # Anchor offsets to the *original* field's start byte, not the
            # current traversal offset (which has already advanced past it).
            orig_start_offset = _sibling_offsets.get(orig_field_name, current_offset)
            for sc in strategy_info["safe_children"]:
                sc_raw_name = sc.get("name", "")
                sc_col_name = f"{prefix}_{sc_raw_name.replace('-', '_')}" if prefix else sc_raw_name.replace("-", "_")
                sc_pic = sc.get("pic") or sc.get("data_type") or ""
                sc_byte_offset = orig_start_offset + sc.get("_byte_offset", 0)
                sc_length = sc.get("_byte_length") or _calculate_pic_length(sc_pic)

                pg_type, log_type, conf, reason = PostgresMapper.map_pic_to_postgres(sc_pic, sc_raw_name)

                alt_col = {
                    "name": sc_col_name,
                    "sql_type": pg_type,
                    "postgres_type": pg_type,
                    "logical_type": log_type,
                    "source_field": sc_raw_name,
                    "source_pic": sc_pic,
                    "primary_key": False,
                    "nullable": True,
                    "key_status": "NONE",
                    "confidence": conf,
                    "conversion_reason": (
                        f"ALTERNATE_REPRESENTATION of {orig_field_name}. "
                        f"Child field from redefining group {r.get('name', '')}. "
                        + reason
                    ),
                    "offset": sc_byte_offset,
                    "length": sc_length,
                    "source_hierarchy": ".".join(hierarchy + [r.get("name", "")]),
                    "schema_status": f"ALTERNATE_REPRESENTATION: {orig_field_name}",
                    "pic": sc_pic,
                    # Semantic annotations — not is_excluded so DDL includes them
                    "is_alternate_repr": True,
                    "redefines_target": orig_field_name,
                    "alternate_group": r.get("name", ""),
                }
                columns.append(alt_col)

        # ------------------------------------------------------------------
        # Leaf scalar field (no children, has PIC, not FILLER)
        # ------------------------------------------------------------------
        if not children and pic and pic != "GROUP" and name != "FILLER":
            pg_type, log_type, conf, reason = PostgresMapper.map_pic_to_postgres(pic, name)

            if redefines:
                if strategy_info:
                    conf = strategy_info["confidence"]
                    reason_adj = f"Strategy: {strategy_info['strategy']}. Reason: {strategy_info['reason']}"
                else:
                    reason_adj = f"Excluded: REDEFINES {redefines}. " + reason
            else:
                reason_adj = reason

            cols = {
                "name": col_name,
                "sql_type": pg_type,
                "postgres_type": pg_type,
                "logical_type": log_type,
                "source_field": r.get("name"),
                "source_pic": pic,
                "primary_key": False,
                "nullable": True,
                "key_status": "NONE",
                "confidence": conf,
                "conversion_reason": reason_adj,
                "offset": current_offset,
                "length": length,
                "source_hierarchy": ".".join(hierarchy),
                "schema_status": status,
                "pic": pic,
            }
            if redefines:
                cols["redefines_target"] = redefines
                cols["is_excluded"] = is_excluded
            if occurs:
                # Backward-compatible key
                cols["occurs"] = occurs
                # Rich OCCURS resolution metadata
                if occurs_resolution:
                    cols["occurs_strategy"]       = occurs_resolution["strategy"]
                    cols["occurs_type"]           = occurs_resolution["occurs_type"]
                    cols["occurs_min"]            = occurs_resolution["min_occurs"]
                    cols["occurs_max"]            = occurs_resolution["max_occurs"]
                    cols["occurs_is_variable"]    = occurs_resolution["is_variable_length"]
                    cols["occurs_nesting_level"]  = occurs_resolution["nesting_level"]
                    cols["occurs_child_sql_type"] = occurs_resolution["child_sql_type"]
                    cols["occurs_confidence"]     = occurs_resolution["confidence"]
                    cols["occurs_reason"]         = occurs_resolution["reason"]
                    cols["occurs_needs_review"]   = occurs_resolution["needs_manual_review"]
            columns.append(cols)

        # ------------------------------------------------------------------
        # Group field: recurse into children.
        # For ALTERNATE_REPRESENTATION roots we still recurse so that the
        # group's children are available in the column list as excluded
        # rows (for audit / metadata), but we pass parent_redefines so they
        # are all properly annotated as excluded.
        # ------------------------------------------------------------------
        child_len = 0
        if children:
            child_cols, child_len = _flatten_records(
                children,
                prefix=col_name,
                current_offset=current_offset,
                hierarchy=hierarchy + [r.get("name", "")],
                parent_occurs=occurs,
                parent_redefines=redefines,
                _sibling_offsets={},   # each group level has its own sibling scope
                parent_occurs_resolution=occurs_resolution,
            )
            columns.extend(child_cols)
            if not length:
                length = child_len

        # ------------------------------------------------------------------
        # Advance offset only for fields that are NOT part of a REDEFINES
        # (redefining fields share storage with the original).
        # ------------------------------------------------------------------
        if not redefines:
            if occurs:
                m = re.search(r"\d+", str(occurs))
                if m:
                    length = (length or 0) * int(m.group(0))
            current_offset += (length or 0)

    return columns, current_offset - start_offset_ref

def _generate_schema_from_structure(artifact_id, artifact_struct, artifact_datasets=None):
    """Legacy flat-structure adapter.

    It is intentionally unreachable for version-2 copybooks, whose API
    responses use their persisted canonical GeneratedSchema instead.
    """
    records = []
    if "structure" in artifact_struct and isinstance(artifact_struct["structure"], dict):
        records = artifact_struct["structure"].get("records", [])
    elif "records" in artifact_struct:
        records = artifact_struct.get("records", [])
        
    if not records:
        return None
        
    columns, _ = _flatten_records(records)
    if not columns:
        return None
        
    # PK Resolution via VSAM datasets
    if artifact_datasets:
        for ds in artifact_datasets:
            key_offset = ds.get("key_offset")
            key_length = ds.get("key_length")
            if key_offset is not None and key_length is not None:
                matched_cols = [c for c in columns if c["offset"] == key_offset and c["length"] == key_length]
                if len(matched_cols) == 1:
                    matched_cols[0]["primary_key"] = True
                    matched_cols[0]["key_evidence"] = {
                        "source_dataset": ds.get("dataset_name"),
                        "source_type": "VSAM_CATALOG",
                        "reason": f"Matched by offset {key_offset} and length {key_length}"
                    }
                elif len(matched_cols) > 1:
                    for c in matched_cols:
                        c["key_status"] = "AMBIGUOUS"
                else:
                    for c in columns:
                        if c["offset"] == key_offset:
                            c["key_status"] = "UNRESOLVED_LENGTH_MISMATCH"
        
    # Compute summary
    # is_alternate_repr columns are NOT excluded — they are mapped columns derived
    # from a REDEFINES alternate representation.  Count them as active columns.
    active = [c for c in columns if not c.get("is_excluded")]
    summary = {
        "total_fields": len(columns),
        "postgres_compatible": sum(1 for c in active if c.get("confidence") == "HIGH"),
        "requires_review": sum(
            1 for c in active
            if c.get("confidence") in ["LOW", "MEDIUM"]
            or "REVIEW" in c.get("schema_status", "")
        ),
        "unsupported": sum(
            1 for c in active
            if c.get("logical_type") == "Unknown"
            or not PostgresMapper.validate_postgres_type(c.get("postgres_type", ""))
        ),
        "numeric_conversions": sum(
            1 for c in active
            if c.get("logical_type") in ["Integer", "Decimal", "Packed Decimal", "Large Integer", "Float", "Double"]
        ),
        "character_conversions": sum(1 for c in active if c.get("logical_type") == "String"),
        "date_conversions": sum(1 for c in active if c.get("logical_type") == "Date"),
        "redefines_handled": sum(1 for c in columns if c.get("is_excluded")),
        "alternate_repr_fields": sum(1 for c in columns if c.get("is_alternate_repr")),
        "occurs_fields": sum(1 for c in active if c.get("occurs") is not None),
        "occurs_needs_review": sum(1 for c in active if c.get("occurs_needs_review")),
        "occurs_inline_array": sum(1 for c in active if c.get("occurs_strategy") == "INLINE_ARRAY"),
        "occurs_child_table": sum(1 for c in active if c.get("occurs_strategy") == "CHILD_TABLE"),
    }

    return {
        "schema_type": "RECORD_SCHEMA",
        "table_name": artifact_id.upper(),
        "columns": columns,
        "validation_summary": summary
    }

def _generate_cobol_schema(artifact_id, artifact_struct, deps):
    info = artifact_struct.get("general_information", {})
    meta = artifact_struct.get("metadata", {})
    comp = artifact_struct.get("components", {})
    struct = artifact_struct.get("structure", {})
    sem = artifact_struct.get("semantic_structure", {})
    
    data_structs = struct.get("data_structures", [])
    
    # Try to grab operations from semantic structure or metadata
    operations = meta.get("operations") or info.get("operations") or []
    if not operations and sem.get("program"):
        operations = sem["program"].get("execution_flow", [])
        
    ds = deps.get("datasets", [])
    if not ds:
        ds = info.get("datasets_accessed") or meta.get("datasets_accessed") or []
        
    files = comp.get("files", {})
        
    cbs = deps.get("copybooks", [])
    if not cbs:
        cbs = info.get("copybooks") or meta.get("copybooks") or comp.get("copybooks") or []
        
    calls = deps.get("calledPrograms", [])
    if not calls:
        calls = info.get("called_programs") or meta.get("called_programs") or []

    return {
        "schema_type": "PROGRAM_SCHEMA",
        "program_name": info.get("program_name") or artifact_id.upper(),
        "data_structures": data_structs,
        "datasets": ds,
        "files": files,
        "operations": operations,
        "copybooks": cbs,
        "called_programs": calls
    }

def _generate_jcl_schema(artifact_id, artifact_struct):
    sem = artifact_struct.get("semantic_structure", {}).get("workflow", {})
    job_info = sem.get("job", {})
    job_struct = artifact_struct.get("structure", {}).get("job", {})
    
    steps = sem.get("steps") or job_struct.get("steps") or []
    
    return {
        "schema_type": "JOB_SCHEMA",
        "job_name": job_info.get("job_name") or artifact_id.upper(),
        "job_card": job_info.get("job_card", {}),
        "steps": steps
    }

def _generate_idcams_schema(artifact_id, artifact_struct):
    info = artifact_struct.get("general_information", {}) or artifact_struct.get("metadata", {}) or artifact_struct
    sem = artifact_struct.get("semantic_structure", {}).get("dataset", {})
    
    return {
        "schema_type": "DATASET_SCHEMA",
        "dataset_name": info.get("dataset_name") or artifact_struct.get("dataset_name", artifact_id),
        "organization": info.get("organization") or artifact_struct.get("organization"),
        "key_length": info.get("key_length") if info.get("key_length") is not None else sem.get("key_length"),
        "key_offset": info.get("key_offset") if info.get("key_offset") is not None else sem.get("key_offset"),
        "record_length": info.get("record_length") if info.get("record_length") is not None else sem.get("record_length"),
        "primary_key": sem.get("primary_key"),
        "alternate_keys": sem.get("alternate_keys", []),
        "record_layout": sem.get("record_layout", [])
    }

def _generate_dataset_schema(artifact_id, ds_row):
    info = ds_row.get("general_information", {}) or ds_row.get("metadata", {}) or ds_row
    sem = ds_row.get("semantic_structure", {}).get("dataset", {})
    
    return {
        "schema_type": "DATASET_SCHEMA",
        "dataset_name": info.get("dataset_name") or ds_row.get("dataset_name", artifact_id),
        "organization": info.get("organization") or ds_row.get("organization"),
        "key_length": info.get("key_length") if info.get("key_length") is not None else sem.get("key_length"),
        "key_offset": info.get("key_offset") if info.get("key_offset") is not None else sem.get("key_offset"),
        "record_length": info.get("record_length") if info.get("record_length") is not None else sem.get("record_length"),
        "primary_key": sem.get("primary_key"),
        "alternate_keys": sem.get("alternate_keys", []),
        "record_layout": sem.get("record_layout", [])
    }

router = APIRouter(prefix="/api/repository", tags=["Repository"])


_KNOWLEDGE_CACHE = {}


def _validated_repository_id(repository_id: str) -> str:
    try:
        return validate_repository_id(repository_id)
    except SecurityValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid repository identifier.") from exc


def _validated_artifact_id(artifact_id: str) -> str:
    try:
        return validate_artifact_id(artifact_id)
    except SecurityValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid artifact identifier.") from exc

def _load_repository_knowledge(repository_id: str) -> dict | None:
    """Load the pipeline's repository-scoped store before using shared DB tables."""
    output_root = os.path.abspath(os.environ.get("OUTPUT_DIR", "outputs"))
    try:
        path = str(safe_join(safe_join(output_root, validate_repository_id(repository_id)), "knowledge_store.json"))
    except SecurityValidationError:
        return None
    try:
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        cached = _KNOWLEDGE_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            _KNOWLEDGE_CACHE[path] = (mtime, data)
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _load_audit_events(repository_id: str) -> list[dict]:
    """Read durable audit records without relying on process-local logs."""
    knowledge = _load_repository_knowledge(repository_id) or {}
    events = knowledge.get("audit_events") or []
    if events:
        return [event for event in events if isinstance(event, dict)]
    try:
        path = str(safe_join(safe_join(os.path.abspath(os.environ.get("OUTPUT_DIR", "outputs")), validate_repository_id(repository_id)), "audit_events.json"))
    except SecurityValidationError:
        return []
    try:
        with open(path, "r", encoding="utf-8") as source:
            return [event for event in json.load(source) if isinstance(event, dict)]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _filter_audit_events(events: list[dict], *, stage=None, severity=None, event_type=None,
                         status=None, artifact_id=None, run_id=None, from_time=None, to_time=None) -> list[dict]:
    def selected(event):
        checks = (
            (not stage or str(event.get("stage", "")).upper() == stage.upper()),
            (not severity or str(event.get("severity", "")).upper() == severity.upper()),
            (not event_type or str(event.get("event_type", "")).lower() == event_type.lower()),
            (not status or str(event.get("status", "")).upper() == status.upper()),
            (not artifact_id or artifact_id.upper() in {str(event.get("artifact_id", "")).upper(), str(event.get("artifact_name", "")).upper()}),
            (not run_id or run_id == "all" or str(event.get("run_id", "")) == run_id),
            (not from_time or str(event.get("timestamp", "")) >= from_time),
            (not to_time or str(event.get("timestamp", "")) <= to_time),
        )
        return all(checks)
    return sorted((event for event in events if selected(event)), key=lambda event: event.get("timestamp", ""), reverse=True)


def _latest_audit_run_id(events: list[dict]) -> str | None:
    recent = sorted(events, key=lambda event: event.get("timestamp", ""), reverse=True)
    return next((event.get("run_id") for event in recent if event.get("run_id")), None)


def _knowledge_structure(knowledge: dict) -> dict:
    canonical = knowledge.get("canonical_structures") or {}
    grouped = {
        "programs": {}, "copybooks": {}, "jcl_jobs": {}, "idcams_definitions": {},
        "catalogs": {}, "other_artifacts": {}, "datasets": {},
    }
    if canonical:
        type_to_group = {
            "COBOL": "programs", "COPYBOOK": "copybooks", "JCL": "jcl_jobs",
            "IDCAMS": "idcams_definitions", "CATALOG": "catalogs",
            "OTHER": "other_artifacts", "PLI": "other_artifacts",
            "NATURAL": "other_artifacts", "RPG": "other_artifacts",
            "METADATA": "other_artifacts", "DATASET": "datasets",
        }
        for artifact_id, structure in canonical.items():
            identity = structure.get("identity", {})
            artifact_type = identity.get("artifact_type") or structure.get("artifact_type") or ""
            group = type_to_group.get(artifact_type.upper())
            if group:
                if "filepath" not in structure:
                    filepath = identity.get("source_file") or structure.get("filepath")
                    if filepath:
                        structure["filepath"] = filepath
                item_id = identity.get("id") or structure.get("id") or artifact_id
                grouped[group][item_id] = structure

        # A repository can contain a mix of canonical and older parser output.
        # Keep every discovered artifact visible even when it has not yet been
        # materialised as a canonical artifact.
        for group_name, knowledge_key in (
            ("programs", "programs"), ("copybooks", "copybooks"),
            ("jcl_jobs", "jcl_jobs"), ("idcams_definitions", "idcams_definitions"),
            ("catalogs", "catalogs"), ("other_artifacts", "other_artifacts"),
            ("datasets", "datasets"),
        ):
            for artifact_id, artifact in (knowledge.get(knowledge_key) or {}).items():
                grouped[group_name].setdefault(artifact_id, artifact)
        return grouped
    for group_name in grouped:
        grouped[group_name] = knowledge.get(group_name) or {}
    return grouped


def _structure_node(node_type: str, name: str, properties: dict | None = None, children: list | None = None) -> dict:
    """A small API view-model built solely from already parsed structures."""
    return {
        "type": node_type,
        "name": name,
        "properties": {key: value for key, value in (properties or {}).items() if value not in (None, "", [], {})},
        "children": children or [],
    }


def _artifact_structure_view(artifact_struct: dict, artifact: dict) -> dict:
    """Normalize parsed artifact facts for the UI without reading source files."""
    identity = artifact_struct.get("identity") or {}
    artifact_type = str(identity.get("artifact_type") or artifact_struct.get("artifact_type") or artifact.get("type") or "UNKNOWN").upper()
    source_file = identity.get("source_file") or artifact_struct.get("filepath") or artifact.get("physicalFile")
    raw = artifact_struct.get("structure") if isinstance(artifact_struct.get("structure"), dict) else artifact_struct
    metadata = artifact_struct.get("metadata") or artifact_struct.get("properties") or {}
    nodes = []

    if artifact_type == "COPYBOOK":
        hierarchy = raw.get("hierarchy") or {}
        fields = hierarchy.get("records") or raw.get("records") or raw.get("fields") or artifact_struct.get("fields") or []
        fragment_hierarchy = hierarchy.get("copybook_fragment_hierarchy") or (artifact_struct.get("properties") or {}).get("copybook_fragment_hierarchy") or []

        def copybook_node(field):
            return _structure_node("field", field.get("name", "UNKNOWN"), {
                "level": field.get("level"), "pic": field.get("pic") or field.get("data_type"),
                "node_type": field.get("node_type"), "length": field.get("length"),
                "logical_length": field.get("logical_length"), "byte_length": field.get("byte_length"),
                "absolute_offset": field.get("absolute_offset"), "usage": field.get("usage"),
                "occurs": field.get("occurs"), "occurs_min": field.get("occurs_min"),
                "occurs_max": field.get("occurs_max"), "occurs_depending_on": field.get("occurs_depending_on"),
                "redefines": field.get("redefines") or field.get("redefines_target"),
                "is_filler": field.get("is_filler"), "source_line": field.get("source_line"),
                "initial_value": field.get("initial_value"),
            }, [copybook_node(child) for child in field.get("children") or []])

        def fragment_node(item):
            return _structure_node(
                item.get("type") or "copybook_fragment", item.get("name") or "Source Fragment",
                item.get("properties") or {}, [fragment_node(child) for child in item.get("children") or []],
            )

        nodes = [copybook_node(field) for field in fields] or [fragment_node(item) for item in fragment_hierarchy]

    elif artifact_type == "JCL":
        extra = raw.get("extra_definitions") or []
        components = artifact_struct.get("components") or {}
        hierarchy = artifact_struct.get("hierarchy") or {}
        job_structure = raw.get("job") or {}
        parsed_hierarchy = next((item.get("jcl_hierarchy") for item in extra if isinstance(item, dict) and item.get("jcl_hierarchy")), None)
        parsed_hierarchy = parsed_hierarchy or (artifact_struct.get("properties") or {}).get("jcl_hierarchy")
        job_card = next((item.get("job_card") for item in extra if isinstance(item, dict) and item.get("job_card")), None)
        job_card = job_card or job_structure.get("job_card") or (artifact_struct.get("general_information") or {}).get("job_card") or artifact_struct.get("job_card") or {}
        execs = raw.get("exec_statements") or components.get("exec_statements") or hierarchy.get("exec_statements") or artifact_struct.get("exec_statements") or []
        dds = raw.get("dd_statements") or components.get("dd_statements") or hierarchy.get("dd_statements") or artifact_struct.get("dd_statements") or []

        def dataset_node(item):
            properties = {key: value for key, value in item.items() if key not in {"name", "dd_name", "concatenations", "dataset"}}
            dataset = item.get("dataset") or item.get("dataset_reference") or item.get("dsn")
            # Older persisted analysis could contain a synthetic dataset value
            # for a DD state.  A DD with SYSOUT, DUMMY, or in-stream data is
            # still a DD, but it does not have a dataset child.
            if not dataset or str(dataset).upper() in {"UNKNOWN", "DUMMY", "INSTREAM"}:
                return None
            return _structure_node("dataset", dataset, properties)

        def dd_node(item):
            child_nodes = []
            if item.get("dataset"):
                dataset = dataset_node(item)
                if dataset:
                    child_nodes.append(dataset)
            for child in item.get("concatenations") or []:
                dataset = dataset_node(child)
                if dataset:
                    child_nodes.append(dataset)
            properties = {key: value for key, value in item.items() if key not in {"name", "dd_name", "dataset", "dataset_reference", "dsn", "concatenations", "is_concatenation", "position"}}
            return _structure_node("dd", item.get("name") or item.get("dd_name") or "UNNAMED", properties, child_nodes)

        def exec_node(statement):
            program = statement.get("program") or statement.get("value")
            label = f"{program} EXEC" if program and str(program).upper() != "UNKNOWN" else "EXEC"
            return _structure_node("exec", label, {key: value for key, value in statement.items() if key != "step_name"})

        if parsed_hierarchy:
            root_children = []
            # JOBLIB/JCLLIB and other job-level DDs belong directly to JOB;
            # a synthetic bucket would hide their real ownership.
            root_children.extend(dd_node(item) for item in parsed_hierarchy.get("job_level_dds") or [])
            for step in parsed_hierarchy.get("steps") or []:
                step_children = [exec_node(statement) for statement in step.get("exec") or []]
                step_children.extend(dd_node(item) for item in step.get("dds") or [])
                root_children.append(_structure_node("step", step.get("name") or "UNASSIGNED", {}, step_children))
        else:
            parsed_steps = job_structure.get("steps") or components.get("steps") or []
            steps = []
            for step in parsed_steps:
                if not isinstance(step, dict):
                    continue
                step_children = []
                for statement in step.get("exec") or []:
                    step_children.append(exec_node(statement))
                for item in step.get("dd") or []:
                    step_children.append(dd_node(item))
                steps.append(_structure_node("step", step.get("step_name") or "UNASSIGNED", {}, step_children))
            if not steps:
                steps_by_name = {}

                def get_step(step_name):
                    key = step_name or "UNASSIGNED"
                    if key not in steps_by_name:
                        steps_by_name[key] = _structure_node("step", key, {}, [])
                        steps.append(steps_by_name[key])
                    return steps_by_name[key]

                for statement in execs:
                    if not isinstance(statement, dict):
                        continue
                    step_name = statement.get("step_name") or "UNASSIGNED"
                    exec_properties = {key: value for key, value in statement.items() if key != "step_name"}
                    get_step(step_name)["children"].append(exec_node({"step_name": step_name, **exec_properties}))

                job_dds = []
                for item in dds:
                    if not isinstance(item, dict):
                        continue
                    step_name = item.get("step_name") if item.get("scope") == "step" or item.get("step_name") else None
                    if step_name:
                        get_step(step_name)["children"].append(dd_node(item))
                    else:
                        job_dds.append(dd_node(item))
                root_children = job_dds + steps
            else:
                root_children = steps
        if raw.get("symbolic_parameters") or artifact_struct.get("symbolic_parameters") or (artifact_struct.get("constraints") or {}).get("symbolic_parameters"):
            symbols = raw.get("symbolic_parameters") or artifact_struct.get("symbolic_parameters") or (artifact_struct.get("constraints") or {}).get("symbolic_parameters")
            root_children.append(_structure_node("symbolic_parameters", "Symbolic Parameters", {"parameters": symbols}))
        if job_card or root_children:
            nodes = [_structure_node("job", job_card.get("job_name") or identity.get("name") or artifact.get("name") or "JOB", job_card, root_children)]

    elif artifact_type in {"COBOL", "CBL"}:
        properties = artifact_struct.get("properties") or raw.get("properties") or {}
        parsed_hierarchy = (
            (raw.get("hierarchy") or {}).get("cobol_hierarchy")
            or (artifact_struct.get("hierarchy") or {}).get("cobol_hierarchy")
            or properties.get("cobol_hierarchy")
            or ((artifact_struct.get("metadata") or {}).get("properties") or {}).get("cobol_hierarchy")
        )
        if parsed_hierarchy:
            def cobol_node(item):
                return _structure_node(
                    item.get("type") or "node", item.get("name") or "UNKNOWN", item.get("properties") or {},
                    [cobol_node(child) for child in item.get("children") or []],
                )
            nodes = [_structure_node("program", identity.get("name") or artifact.get("name") or "PROGRAM", {}, [cobol_node(item) for item in parsed_hierarchy])]
            return {
                "artifact_type": artifact_type,
                "structure_type": artifact_type.lower(),
                "source_file": source_file,
                "nodes": nodes,
                "metadata": metadata,
                "available": True,
                "message": None,
            }
        divisions = raw.get("divisions") or properties.get("divisions") or []
        sections = raw.get("sections") or properties.get("sections") or []
        paragraphs = raw.get("procedures") or raw.get("paragraphs") or properties.get("paragraphs") or []
        copies = artifact_struct.get("dependencies", {}).get("copybooks") or artifact_struct.get("copybooks_used") or properties.get("copybooks") or []
        files = artifact_struct.get("datasets_accessed") or artifact_struct.get("dependencies", {}).get("datasets") or []
        children = []
        if divisions:
            children.append(_structure_node("division_group", "Divisions", {}, [_structure_node("division", str(value)) for value in divisions]))
        if sections:
            children.append(_structure_node("section_group", "Sections", {}, [_structure_node("section", str(value)) for value in sections]))
        if paragraphs:
            children.append(_structure_node("paragraph_group", "Paragraphs", {}, [_structure_node("paragraph", str(value)) for value in paragraphs]))
        if copies:
            children.append(_structure_node("copy_group", "COPY References", {}, [_structure_node("copy_reference", str(value)) for value in copies]))
        if files:
            children.append(_structure_node("file_group", "File References", {}, [_structure_node("file_reference", str(value)) for value in files]))
        if children or properties.get("operations") or properties.get("called_programs"):
            nodes = [_structure_node("program", identity.get("name") or artifact.get("name") or "PROGRAM", {"operations": properties.get("operations"), "called_programs": properties.get("called_programs")}, children)]

    elif artifact_type == "IDCAMS":
        extra = raw.get("extra_definitions") or []
        components = artifact_struct.get("components") or {}
        definition_data = next((item for item in extra if isinstance(item, dict) and item.get("definitions")), {})
        definitions = definition_data.get("definitions") or (artifact_struct.get("properties") or {}).get("definitions") or []
        if not definitions:
            clusters = (
                artifact_struct.get("defined_clusters")
                or artifact_struct.get("datasets", {}).get("referenced")
                or artifact_struct.get("datasets", {}).get("defined")
                or components.get("cluster")
                or (artifact_struct.get("semantic_structure") or {}).get("vsam_definition", {}).get("cluster")
                or (artifact_struct.get("general_information") or {}).get("cluster_name")
                or raw.get("datasets", {}).get("referenced")
                or []
            )
            if isinstance(clusters, str):
                clusters = [clusters]
            definitions = [{"command": "DEFINE CLUSTER", "name": name} for name in clusters]
        for definition in definitions:
            if not isinstance(definition, dict):
                continue
            children = []
            for key, label, node_type in (("data_component", "DATA", "data"), ("index_component", "INDEX", "index")):
                value = definition.get(key) or components.get(key)
                if value:
                    children.append(_structure_node(node_type, label, value if isinstance(value, dict) else {"value": value}))
            properties = {key: value for key, value in definition.items() if key not in {"command", "data_component", "index_component"}}
            for key in ("key_definition", "storage_allocation"):
                if components.get(key):
                    properties[key] = components[key]
            nodes.append(_structure_node("command", definition.get("command") or "DEFINE CLUSTER", properties, children))

    elif artifact_type == "CATALOG":
        extra = raw.get("extra_definitions") or []
        entries = next((item.get("entries") for item in extra if isinstance(item, dict) and item.get("entries") is not None), None)
        entries = entries if entries is not None else artifact_struct.get("entries") or []
        nodes = [_structure_node(entry.get("entry_type", "CATALOG_ENTRY").lower(), entry.get("name", "UNKNOWN"), {key: value for key, value in entry.items() if key not in {"name", "entry_type"}}) for entry in entries if isinstance(entry, dict)]

    elif artifact_type == "DATASET":
        info = artifact_struct.get("general_information") or artifact_struct.get("metadata") or raw
        properties = {
            "organization": info.get("organization"),
            "dataset_type": info.get("dataset_type") or info.get("type"),
            "record_length": info.get("record_length"),
            "key_length": info.get("key_length"),
            "key_offset": info.get("key_offset"),
        }
        if any(value not in (None, "") for value in properties.values()):
            nodes = [_structure_node("dataset", info.get("dataset_name") or artifact.get("name") or "DATASET", properties)]

    return {
        "artifact_type": artifact_type,
        "structure_type": artifact_type.lower(),
        "source_file": source_file,
        "nodes": nodes,
        "metadata": metadata,
        "available": bool(nodes),
        "message": None if nodes else "Structured view is not currently available for this artifact type.",
    }

def _calculate_health_score(stats: dict) -> dict:
    score = 20
    if stats["total_files"] > 0: score += 15
    if stats["copybooks"] > 0: score += 20
    if stats["cobol_programs"] > 0: score += 15
    if stats["jcl_jobs"] > 0: score += 10
    if stats["datasets"] > 0: score += 10
    if stats["relationships"] > 0: score += 10
    score = min(score, 100)
    
    if stats["datasets"] > 0 and stats["copybooks"] > 0 and (stats["cobol_programs"] > 0 or stats["jcl_jobs"] > 0):
        readiness = "Ready for modernization review"
    elif stats["copybooks"] > 0 and stats["datasets"] == 0:
        readiness = "Copybooks inventoried - upload JCL, LISTCAT, or COBOL to map datasets"
    elif stats["datasets"] > 0:
        readiness = "Datasets inventoried - add copybooks for schema design"
    elif stats["total_files"] > 0:
        readiness = "Inventory complete - more mainframe context needed"
    else:
        readiness = "No repository artifacts found"
        
    return {
        "repository_health_score": score,
        "migration_readiness": readiness,
        "schema_generation_readiness": stats["copybooks"] > 0 and stats["datasets"] > 0
    }

@router.get("/{id}/audit/summary")
async def get_audit_summary(id: str, stage: str | None = None, severity: str | None = None,
                            event_type: str | None = None, status: str | None = None,
                            from_time: str | None = None, to_time: str | None = None, run_id: str | None = None):
    id = _validated_repository_id(id)
    all_events = _load_audit_events(id)
    selected_run = run_id or _latest_audit_run_id(all_events)
    events = _filter_audit_events(all_events, stage=stage, severity=severity,
                                  event_type=event_type, status=status, run_id=selected_run, from_time=from_time, to_time=to_time)
    return {"repository_id": id, "summary": summarize_audit_events(events), "filters": {
        "stage": stage, "severity": severity, "event_type": event_type, "status": status,
        "from_time": from_time, "to_time": to_time, "run_id": selected_run,
    }}


@router.get("/{id}/audit")
async def get_repository_audit(id: str, stage: str | None = None, severity: str | None = None,
                               event_type: str | None = None, status: str | None = None,
                               artifact_id: str | None = None, from_time: str | None = None,
                               to_time: str | None = None, limit: int = 250, run_id: str | None = None):
    id = _validated_repository_id(id)
    if artifact_id:
        artifact_id = _validated_artifact_id(artifact_id)
    all_events = _load_audit_events(id)
    selected_run = run_id or _latest_audit_run_id(all_events)
    events = _filter_audit_events(all_events, stage=stage, severity=severity,
                                  event_type=event_type, status=status, artifact_id=artifact_id,
                                  run_id=selected_run, from_time=from_time, to_time=to_time)
    return {"repository_id": id, "events": events[:max(1, min(limit, 1000))],
            "total": len(events), "run_id": selected_run, "summary": summarize_audit_events(events)}


@router.get("/{id}/artifacts/{artifact_id}/audit")
async def get_artifact_audit(id: str, artifact_id: str, stage: str | None = None,
                             severity: str | None = None, event_type: str | None = None,
                             status: str | None = None, run_id: str | None = None):
    id = _validated_repository_id(id)
    artifact_id = _validated_artifact_id(artifact_id)
    all_events = _load_audit_events(id)
    selected_run = run_id or _latest_audit_run_id(all_events)
    events = _filter_audit_events(all_events, stage=stage, severity=severity,
                                  event_type=event_type, status=status, artifact_id=artifact_id, run_id=selected_run)
    return {"repository_id": id, "artifact_id": artifact_id, "events": events, "total": len(events),
            "run_id": selected_run, "summary": summarize_audit_events(events)}


@router.get("/{id}/summary")
async def get_summary(id: str):
    id = _validated_repository_id(id)
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        stats = knowledge.get("summary") or {}
        stats.update(_calculate_health_score({
            "total_files": stats.get("total_files", 0),
            "copybooks": stats.get("copybooks", 0),
            "cobol_programs": stats.get("cobol_programs", 0),
            "jcl_jobs": stats.get("jcl_jobs", 0),
            "datasets": stats.get("datasets", 0),
            "relationships": stats.get("relationships", 0),
        }))
        return {
            "repository_id": id,
            "repository_name": stats.get("repository_name", id),
            "statistics": stats,
        }

    # Fetch from Supabase
    repo = supabase_db.select("Repository", {"repository_id": id})
    if not repo:
        repo_name = id
    else:
        repo_name = repo[0].get("repository_name", id)

    files = supabase_db.select("Files", {"repository_id": id})
    file_ids = {file.get("file_id") for file in files}
    progs = [p for p in supabase_db.select("Programs") if p.get("file_id") in file_ids]
    cbs = [c for c in supabase_db.select("Copybooks") if c.get("file_id") in file_ids]
    rels = supabase_db.select("Relationships")
    brs = supabase_db.select("BusinessRules")

    program_ids = {program.get("program_id") for program in progs}
    source_ids = program_ids | {
        os.path.splitext(file.get("filename", ""))[0].upper() for file in files
    }
    rels = [relationship for relationship in rels if relationship.get("source_id") in source_ids]
    dataset_ids = {relationship.get("target_id") for relationship in rels if relationship.get("target_type") == "Dataset"}
    dss = [dataset for dataset in supabase_db.select("Datasets") if dataset.get("dataset_id") in dataset_ids]
    brs = [rule for rule in brs if rule.get("program_id") in program_ids]

    jcl_count = sum(1 for f in files if f.get("artifact_type") == "JCL")
    idcams_count = sum(1 for f in files if f.get("artifact_type") == "IDCAMS")
    catalog_count = sum(1 for f in files if f.get("artifact_type") == "CATALOG")

    folders = set()
    for f in files:
        p = f.get("path") or f.get("file_id") or ""
        dirname = os.path.dirname(p)
        if dirname:
            parts = dirname.replace("\\", "/").split("/")
            current = ""
            for part in parts:
                if part:
                    current = f"{current}/{part}" if current else part
                    folders.add(current)

    stats = {
        "repository_name": repo_name,
        "total_folders": len(folders),
        "total_files": len(files),
        "cobol_programs": len(progs),
        "copybooks": len(cbs),
        "jcl_jobs": jcl_count,
        "idcams_scripts": idcams_count,
        "catalog_files": catalog_count,
        "datasets": len(dss),
        "business_rules": len(brs),
        "relationships": len(rels),
    }
    health = _calculate_health_score(stats)
    stats.update(health)

    return {
        "repository_id": id,
        "repository_name": repo_name,
        "statistics": stats
    }

@router.get("/{id}/structure")
async def get_structure(id: str):
    id = _validated_repository_id(id)
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        return _knowledge_structure(knowledge)

    files = supabase_db.select("Files", {"repository_id": id})
    file_map = {f["file_id"]: f for f in files}
    
    # We now fetch the detailed structures directly from ArtifactMetadata in chunks
    file_ids = list(file_map.keys())
    repo_metadata = []
    chunk_size = 100
    for i in range(0, len(file_ids), chunk_size):
        chunk = file_ids[i:i+chunk_size]
        entries = supabase_db.select("ArtifactMetadata", {"file_id": {"in": chunk}})
        repo_metadata.extend(entries)
    
    programs_dict = {}
    copybooks_dict = {}
    datasets_dict = {}
    jcl_jobs_dict = {}
    idcams_dict = {}
    catalogs_dict = {}
    other_artifacts_dict = {}
    
    import json
    for m in repo_metadata:
        try:
            struct = m.get("structure")
            if isinstance(struct, str):
                struct = json.loads(struct)
            
            # Inject filepath from the DB into the structure so the frontend can build the tree
            file_row = file_map.get(m.get("file_id"))
            if file_row and "filepath" not in struct:
                struct["filepath"] = file_row.get("path") or file_row.get("file_id")

            identity = struct.get("identity", {})
            artifact_type = identity.get("artifact_type") or struct.get("artifact_type") or struct.get("language") or "UNKNOWN"
            item_id = identity.get("id") or struct.get("id") or m["artifact_id"]
            
            if artifact_type == "COBOL":
                programs_dict[item_id] = struct
            elif artifact_type == "JCL":
                jcl_jobs_dict[item_id] = struct
            elif artifact_type == "IDCAMS":
                idcams_dict[item_id] = struct
            elif artifact_type == "CATALOG":
                catalogs_dict[item_id] = struct
            elif "fields" in struct or artifact_type == "COPYBOOK":
                copybooks_dict[item_id] = struct
            elif artifact_type in {"PLI", "NATURAL", "RPG", "METADATA", "OTHER"}:
                other_artifacts_dict[item_id] = struct
            else:
                datasets_dict[item_id] = struct
        except Exception:
            pass

    return {
        "programs": programs_dict,
        "copybooks": copybooks_dict,
        "jcl_jobs": jcl_jobs_dict,
        "idcams_definitions": idcams_dict,
        "catalogs": catalogs_dict,
        "other_artifacts": other_artifacts_dict,
        "datasets": datasets_dict
    }

@router.get("/{id}/datasets")
async def get_datasets(id: str):
    id = _validated_repository_id(id)
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        return knowledge.get("datasets") or {}

    dss = supabase_db.select("Datasets")
    return {ds["dataset_id"]: ds for ds in dss}

@router.get("/{id}/relationships")
async def get_relationships(id: str):
    id = _validated_repository_id(id)
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        return knowledge.get("relationships") or []

    rels = supabase_db.select("Relationships")
    return rels

@router.get("/{id}/schema")
async def get_schema(id: str):
    id = _validated_repository_id(id)
    knowledge = _load_repository_knowledge(id)
    if knowledge:
        schema = knowledge.get("database_schema") or {
            "dialect": "none", "tables": {}, "relationships": [], "ddl": ""
        }
        return {
            "ready_for_generation": bool((knowledge.get("summary") or {}).get("schema_generation_readiness")),
            "database_schema": schema,
            "generated_schemas": schema.get("generated_schemas", []),
        }

    cbs = supabase_db.select("Copybooks")
    dss = supabase_db.select("Datasets")
    
    schema_dict = {
        "dialect": "none",
        "tables": {},
        "relationships": [],
        "ddl": ""
    }
    
    return {
        "ready_for_generation": False,
        "database_schema": schema_dict,
        "generated_schemas": [],
    }


def _canonical_generated_schema(knowledge: dict, artifact_id: str) -> dict | None:
    """Stable v2 lookup: artifact ID is the persisted GeneratedSchema key."""
    schema = knowledge.get("database_schema") or {}
    for generated in schema.get("generated_schemas", []):
        if str(generated.get("artifact_id", "")).upper() == str(artifact_id).upper():
            return generated
    return None

@router.get("/{id}/artifact-details/{artifact_id}")
async def get_artifact_details(id: str, artifact_id: str):
    id = _validated_repository_id(id)
    artifact_id = _validated_artifact_id(artifact_id)
    knowledge = _load_repository_knowledge(id)
    relationships = []
    
    # 1. Get Artifact Structure and Base Meta
    artifact_struct = None
    artifact_meta_row = None
    file_row = None
    
    if knowledge:
        rels = knowledge.get("relationships") or []
        relationships = rels
        structs = _knowledge_structure(knowledge)
        
        # 1. Direct match in groups
        group_type_hints = {
            "programs": "COBOL", "copybooks": "COPYBOOK", "jcl_jobs": "JCL",
            "idcams_definitions": "IDCAMS", "catalogs": "CATALOG",
            "other_artifacts": "OTHER", "datasets": "DATASET",
        }
        for group_name, group in structs.items():
            if artifact_id in group:
                artifact_struct = group[artifact_id]
                if not artifact_struct.get("artifact_type") and not artifact_struct.get("identity"):
                    artifact_struct = {**artifact_struct, "artifact_type": group_type_hints.get(group_name, "UNKNOWN")}
                break
                
        # 2. Case-insensitive and stem matching
        if not artifact_struct:
            target_norm = artifact_id.upper()
            target_stem = os.path.splitext(artifact_id)[0].upper()
            for group_name, group in structs.items():
                for k, v in group.items():
                    k_upper = str(k).upper()
                    k_stem = os.path.splitext(str(k))[0].upper()
                    v_id = str(v.get("id") or "").upper()
                    v_name = str(v.get("name") or "").upper()
                    v_file = os.path.basename(str(v.get("source_file") or v.get("filepath") or "")).upper()
                    
                    if (target_norm in (k_upper, v_id, v_name, v_file) or 
                        target_stem in (k_stem, v_id, v_name, os.path.splitext(v_file)[0])):
                        artifact_struct = v
                        if not artifact_struct.get("artifact_type") and not artifact_struct.get("identity"):
                            artifact_struct = {**artifact_struct, "artifact_type": group_type_hints.get(group_name, "UNKNOWN")}
                        break
                if artifact_struct:
                    break

        # 3. Canonical structures fallback
        if not artifact_struct:
            canonical = knowledge.get("canonical_structures") or {}
            for k, v in canonical.items():
                k_clean = k.upper().split(":")[-1]
                if (k.upper() == artifact_id.upper() or 
                    k_clean == artifact_id.upper() or
                    os.path.splitext(k_clean)[0] == os.path.splitext(artifact_id.upper())[0]):
                    artifact_struct = v
                    break
    else:
        # DB mode
        files = supabase_db.select("Files", {"repository_id": id})
        file_map = {f["file_id"]: f for f in files}
        
        metadata_entries = supabase_db.select("ArtifactMetadata", {"artifact_id": artifact_id})
        if not metadata_entries:
            # ArtifactMetadata storage keys are namespaced (for example
            # CATALOG:LISTCAT). Explorer selections use the stable artifact id.
            metadata_entries = [
                row for row in supabase_db.select("ArtifactMetadata")
                if str(row.get("artifact_id", "")).upper().split(":")[-1] == str(artifact_id).upper()
            ]
        repo_metadata = [m for m in metadata_entries if m.get("file_id") in file_map]
        
        for m in repo_metadata:
            struct = m.get("structure")
            if isinstance(struct, str):
                import json
                try:
                    struct = json.loads(struct)
                except Exception:
                    continue
            struct_id = struct.get("id") or m.get("artifact_id")
            # we do case insensitive match just in case
            if str(struct_id).upper() == str(artifact_id).upper():
                artifact_struct = struct
                artifact_meta_row = m
                file_row = file_map.get(m.get("file_id"))
                break
        
        # Fetch only relevant relationships instead of all
        relationships = supabase_db.select("Relationships")
        
        if not artifact_struct:
            # Try to find just by file name if structure not fully matched
            for f in files:
                fname_no_ext = os.path.splitext(f.get("filename", ""))[0]
                if fname_no_ext.upper() == artifact_id.upper() or f.get("filename") == artifact_id or f.get("filename", "").upper() == artifact_id.upper():
                    file_row = f
                    artifact_struct = {"id": artifact_id, "name": fname_no_ext, "artifact_type": f.get("artifact_type")}
                    break
        
        # Check if it's a dataset
        if not artifact_struct:
            datasets = supabase_db.select("Datasets", {"dataset_id": artifact_id})
            if datasets:
                d = datasets[0]
                artifact_struct = {"id": artifact_id, "name": d.get("dataset_name"), "artifact_type": "DATASET"}
                
    if not artifact_struct:
        raise HTTPException(status_code=404, detail="Artifact not found")
            
    # 2. Build details
    identity = artifact_struct.get("identity") or {}
    p_file = (
        artifact_struct.get("filepath")
        or identity.get("source_file")
        or (file_row.get("filename") if file_row else "")
    )
    a_type = (
        identity.get("artifact_type")
        or artifact_struct.get("artifact_type")
        or artifact_struct.get("language")
        or (file_row.get("artifact_type") if file_row else "UNKNOWN")
    )
    if os.path.splitext(str(p_file))[1].lower() in {".cpy", ".copy"}:
        a_type = "COPYBOOK"
    a_name = identity.get("name") or artifact_struct.get("name") or artifact_id
    r_path = artifact_struct.get("repository_path") or (file_row.get("filepath") if file_row else "/")
    
    artifact = {
        "id": artifact_id,
        "type": a_type,
        "name": a_name,
        "physicalFile": p_file,
        "repositoryPath": r_path,
        "language": artifact_struct.get("language") or a_type,
        "parser": artifact_struct.get("parser") or (artifact_meta_row.get("parser_name") if artifact_meta_row else ""),
        "metadata": artifact_struct.get("properties") or artifact_struct.get("metadata") or {}
    }
    if str(a_type).upper() == "COPYBOOK":
        canonical_properties = (artifact_struct.get("metadata") or {}).get("properties") or {}
        copybook_properties = artifact_struct.get("properties") or canonical_properties
        artifact["copybook_model_version"] = copybook_properties.get("copybook_model_version")
        artifact["stale_copybook_model"] = not bool(copybook_properties.get("copybook_model_version"))
    
    # 3. Build Dependencies
    deps = {
        "copybooks": [],
        "datasets": [],
        "calledPrograms": [],
        "jclJobs": [],
        "utilities": [],
        "idcams": []
    }
    
    # Filter rels related to this artifact
    # Both source_id or target_id could be the artifact
    # Note: relationships could use file names or parsed IDs
    a_id_upper = str(artifact_id).upper()
    
    for r in relationships:
        s_id = str(r.get("source_id")).upper()
        t_id = str(r.get("target_id")).upper()
        rel_type = r.get("relationship_type", "").upper()
        
        if s_id == a_id_upper:
            # Outgoing dependency
            if "COPYBOOK" in rel_type or "COPY" in rel_type:
                deps["copybooks"].append(r.get("target_id"))
            elif "DATASET" in rel_type:
                deps["datasets"].append(r.get("target_id"))
            elif "PROGRAM" in rel_type or "CALL" in rel_type:
                deps["calledPrograms"].append(r.get("target_id"))
            elif "JCL" in rel_type:
                deps["jclJobs"].append(r.get("target_id"))
            elif "UTILITY" in rel_type:
                deps["utilities"].append(r.get("target_id"))
            elif "IDCAMS" in rel_type:
                deps["idcams"].append(r.get("target_id"))
        elif t_id == a_id_upper:
            # Incoming dependency
            if "COPYBOOK" in rel_type or "COPY" in rel_type:
                deps["copybooks"].append(r.get("source_id"))
            elif "DATASET" in rel_type:
                deps["datasets"].append(r.get("source_id"))
            elif "PROGRAM" in rel_type or "CALL" in rel_type:
                deps["calledPrograms"].append(r.get("source_id"))
            elif "JCL" in rel_type or "EXECUTE" in rel_type:
                deps["jclJobs"].append(r.get("source_id"))
            elif "UTILITY" in rel_type:
                deps["utilities"].append(r.get("source_id"))
            elif "IDCAMS" in rel_type:
                deps["idcams"].append(r.get("source_id"))
                
    # fallback to lists from artifact_struct if they exist (parser specific)
    if not deps["copybooks"] and artifact_struct.get("copybooks_used"):
        deps["copybooks"] = artifact_struct.get("copybooks_used", [])
    if not deps["datasets"] and artifact_struct.get("datasets_accessed"):
        deps["datasets"] = artifact_struct.get("datasets_accessed", [])
    if not deps["calledPrograms"] and artifact_struct.get("programs_called"):
        deps["calledPrograms"] = artifact_struct.get("programs_called", [])
        
    # Deduplicate dependencies
    for k in deps:
        deps[k] = list(set(deps[k]))

    # 4. Detailed Data for UI Tabs
    artifact_rels = []
    if knowledge:
        for r in relationships:
            s_id = str(r.get("source_id", "")).upper()
            t_id = str(r.get("target_id", "")).upper()
            if s_id == a_id_upper or t_id == a_id_upper:
                artifact_rels.append(r)
        
        evidence = []
        evidence_list = knowledge.get("evidence", [])
        if evidence_list:
            evidence = [e for e in evidence_list if os.path.basename(e.get("source_file", "")).upper() == os.path.basename(p_file or "").upper()]
            
        artifact_datasets = []
        for r in artifact_rels:
            ds_id = r.get("target_id") if str(r.get("source_id", "")).upper() == a_id_upper else r.get("source_id")
            ds = knowledge.get("datasets", {}).get(ds_id)
            if ds:
                artifact_datasets.append(ds)
                
        schema = _canonical_generated_schema(knowledge, artifact_id)
    else:
        for r in relationships:
            if str(r.get("source_id")).upper() == a_id_upper or str(r.get("target_id")).upper() == a_id_upper:
                artifact_rels.append(r)
                
        # Datasets
        artifact_datasets = []
        for r in artifact_rels:
            if str(r.get("source_id")).upper() == a_id_upper:
                ds = supabase_db.select("Datasets", {"dataset_id": r.get("target_id")})
                if ds:
                    artifact_datasets.append(ds[0])
            elif str(r.get("target_id")).upper() == a_id_upper:
                ds = supabase_db.select("Datasets", {"dataset_id": r.get("source_id")})
                if ds:
                    artifact_datasets.append(ds[0])
                    
        # Evidence
        evidence = supabase_db.select("Evidence", {"source_file": p_file}) if p_file else []
        if not evidence and file_row:
             evidence = supabase_db.select("Evidence", {"file_id": file_row.get("file_id")})
             
        schema = None
        generated = supabase_db.select("GeneratedSchema", {"schema_id": artifact_id})
        if not generated and artifact_meta_row:
            generated = supabase_db.select("GeneratedSchema", {"schema_id": artifact_meta_row.get("artifact_id")})
        if not generated and file_row:
            generated = supabase_db.select("GeneratedSchema", {"file_id": file_row.get("file_id")})
            
        if generated:
            schema = generated[0]
            
    if not schema and artifact_struct and not (
        knowledge and str(a_type).upper() == "COPYBOOK" and artifact.get("copybook_model_version")
    ):
        atype = str(a_type).upper()
        try:
            if atype == "COPYBOOK":
                schema = _generate_schema_from_structure(a_id_upper, artifact_struct, artifact_datasets)
            elif atype in ["COBOL", "CBL"]:
                schema = _generate_cobol_schema(a_id_upper, artifact_struct, deps)
            elif atype == "JCL":
                schema = _generate_jcl_schema(a_id_upper, artifact_struct)
            elif atype == "IDCAMS":
                schema = _generate_idcams_schema(a_id_upper, artifact_struct)
            elif atype == "DATASET":
                schema = _generate_dataset_schema(a_id_upper, artifact_struct)
        except Exception as e:
            import traceback; traceback.print_exc()
            schema = None
    if not schema and knowledge and str(a_type).upper() == "COPYBOOK" and artifact.get("copybook_model_version"):
        schema = {"artifact_id": artifact_id, "status": "FAILED", "ddl": "", "warnings": [{"status": "FAILED", "reason": "No canonical GeneratedSchema was persisted for this resolved copybook."}]}

    return {
        "artifact": artifact,
        "dependencies": deps,
        "structure": artifact_struct,
        "structure_view": _artifact_structure_view(artifact_struct, artifact),
        "detailed_relationships": artifact_rels,
        "detailed_datasets": artifact_datasets,
        "detailed_evidence": evidence,
        "detailed_schema": schema
    }

class ChatRequest(BaseModel):
    query: str

@router.post("/{id}/chat")
async def chat_with_assistant(id: str, request: ChatRequest):
    id = _validated_repository_id(id)
    try:
        assistant = ModernizationAssistant(repository_id=id)
        response = assistant.chat(request.query)
        if response:
            return {"response": response}
    except Exception:
        logger.exception("Modernization assistant request failed")
        return {"response": "Modernization Assistant is temporarily unavailable."}
