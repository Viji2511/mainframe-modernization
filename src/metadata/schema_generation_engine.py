import logging
import json
import re
from typing import Dict, List, Any
from src.store.supabase_client import supabase_db
from src.validators.postgres_mapper import PostgresMapper
from src.analyzers.redefines_resolution_engine import RedefinesResolutionEngine
from src.analyzers.occurs_resolution_engine import OccursResolutionEngine
from src.metadata.script_generator import PostgresScriptGenerator

logger = logging.getLogger(__name__)

class SchemaGenerationEngine:
    """Deprecated persistence adapter.

    New repository analyses already receive their one resolved schema from
    ``SchemaGenerator`` during knowledge construction. This class must not
    re-read ArtifactMetadata and derive a competing schema for those runs.
    """
    def generate(self, audit_trail=None, knowledge=None) -> None:
        if knowledge is not None:
            if audit_trail:
                audit_trail.record(stage="SCHEMA", component="SchemaGenerationEngine", action="legacy_adapter",
                    event_type="schema_generation_adapter_used", summary="SchemaGenerationEngine deferred to persisted authoritative resolved schema.",
                    details={"resolved_schema_version": (knowledge.database_schema or {}).get("resolved_schema_version")})
            return knowledge.database_schema
        try:
            logger.info("Schema Generation Engine: Starting")
            if audit_trail:
                audit_trail.record(stage="SCHEMA", component="SchemaGenerationEngine", action="start",
                                   event_type="schema_generation_started", summary="Schema generation engine started.")
            
            # Fetch inputs
            artifacts = supabase_db.select("ArtifactMetadata")
            relationships = supabase_db.select("Relationships")
            
            # Build dataset mapping: copybook_id -> list of dataset_ids
            cb_to_datasets = {}
            for rel in relationships:
                if rel.get("rel_type") == "USES_RECORD_LAYOUT":
                    cb_id = rel.get("target_id")
                    ds_id = rel.get("source_id")
                    if cb_id and ds_id:
                        if cb_id not in cb_to_datasets:
                            cb_to_datasets[cb_id] = []
                        cb_to_datasets[cb_id].append(ds_id)

            # Process COPYBOOK structures
            for artifact in artifacts:
                artifact_id = artifact.get("artifact_id", "")
                if not artifact_id.startswith("COPYBOOK:"):
                    continue
                
                try:
                    structure = json.loads(artifact.get("structure", "{}"))
                    records = structure.get("records", [])
                    
                    if not records:
                        logger.warning(f"No records found in structure for {artifact_id}")
                        continue
                        
                    datasets = cb_to_datasets.get(artifact_id, [])
                    readiness = "READY"
                    
                    if not datasets:
                        readiness = "INSUFFICIENT_EVIDENCE"
                    
                    schema_status = self._derive_schema(records)
                    columns = schema_status["columns"]
                    
                    if schema_status["needs_review"] and readiness == "READY":
                        readiness = "REVIEW_REQUIRED"
                        
                    if not columns:
                        readiness = "NOT_MIGRATABLE"
                    
                    # Generate DDL
                    table_name = artifact_id.split(":")[-1].replace("-", "_").lower()
                    
                    if columns or schema_status.get("child_tables"):
                        ddl = PostgresScriptGenerator.generate_ddl(
                            table_name=table_name,
                            columns=columns,
                            child_tables=schema_status.get("child_tables", [])
                        )
                    else:
                        ddl = PostgresScriptGenerator.generate_ddl(table_name, [], [])
                        
                    supabase_db.insert("GeneratedSchema", {
                        "schema_id": artifact_id,
                        "file_id": artifact.get("file_id"),
                        "ddl": ddl,
                        "readiness_status": readiness,
                        "mapped_dataset": datasets[0] if datasets else None
                    })
                    if audit_trail:
                        audit_trail.record(stage="DDL", component="PostgresScriptGenerator", action="generate_ddl",
                                           event_type="ddl_table_generated", artifact_id=artifact_id,
                                           artifact_name=artifact_id, output_reference=artifact_id,
                                           summary=f"Generated DDL for {artifact_id}.",
                                           details={"readiness": readiness, "column_count": len(columns)})
                    
                except Exception as e:
                    logger.error(f"Error generating schema for {artifact_id}: {e}")
                    if audit_trail:
                        audit_trail.record(stage="SCHEMA", component="SchemaGenerationEngine", action="generate_schema",
                                           event_type="schema_generation_failed", status="FAILED", severity="ERROR",
                                           artifact_id=artifact_id, artifact_name=artifact_id,
                                           summary=f"Schema generation failed for {artifact_id}.", details={"reason": str(e)})
                    
            logger.info("Schema Generation Engine: Finished")
            if audit_trail:
                audit_trail.record(stage="SCHEMA", component="SchemaGenerationEngine", action="complete",
                                   event_type="schema_generation_completed", summary="Schema generation engine completed.")
        except Exception as e:
            logger.exception(f"Error in SchemaGenerationEngine: {e}")
            if audit_trail:
                audit_trail.record(stage="SCHEMA", component="SchemaGenerationEngine", action="generate_schema",
                                   event_type="schema_generation_failed", status="FAILED", severity="ERROR",
                                   summary="Schema generation engine failed.", details={"reason": str(e)})
            raise

    def _derive_schema(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Derive a column list from a hierarchical COBOL record tree.

        REDEFINES handling
        ------------------
        For each field that bears a REDEFINES clause the engine calls
        RedefinesResolutionEngine.resolve() and acts on the returned strategy:

        SAME_TABLE / REVIEW_REQUIRED / SEPARATE_TABLES
            The redefining field is excluded from the DDL (is_excluded=True).
            The strategy, confidence and reason are preserved in the column
            metadata for downstream audit.

        ALTERNATE_REPRESENTATION  (new)
            The redefining *group node* is excluded from the DDL.
            Each safe_child identified by the engine is emitted as a separate
            column entry annotated with is_alternate_repr=True so the DDL
            writer knows to include it.  The original canonical field is left
            completely untouched.
        """
        columns = []
        child_tables = []
        needs_review = False

        def traverse(fields: List[Dict[str, Any]], current_columns: List[Dict[str, Any]]) -> None:
            nonlocal needs_review
            siblings = {f.get("name"): f for f in fields if f.get("name")}

            for field in fields:
                has_children = bool(field.get("children"))

                if field.get("occurs") or field.get("redefines"):
                    needs_review = True

                is_redefines_root = bool(field.get("redefines"))
                strategy_info: Dict[str, Any] = {}
                occurs_info: Dict[str, Any] = {}

                if is_redefines_root:
                    orig_node = siblings.get(field.get("redefines"))
                    strategy_info = RedefinesResolutionEngine.resolve(orig_node, field)

                if field.get("occurs"):
                    occurs_info = OccursResolutionEngine.resolve(field)
                    if occurs_info.get("needs_manual_review"):
                        needs_review = True

                # ----------------------------------------------------------
                # ALTERNATE_REPRESENTATION: emit safe children as columns,
                # then skip further recursion for this group's children —
                # they are represented through the safe_children list only.
                # ----------------------------------------------------------
                if (
                    is_redefines_root
                    and strategy_info.get("strategy") == "ALTERNATE_REPRESENTATION"
                    and strategy_info.get("safe_children")
                ):
                    orig_name = strategy_info.get("original_field_name", field.get("redefines", ""))
                    for sc in strategy_info["safe_children"]:
                        sc_pic = sc.get("pic") or sc.get("data_type") or ""
                        pg_type, log_type, conf, reason = PostgresMapper.map_pic_to_postgres(
                            sc_pic, sc.get("name", "")
                        )
                        current_columns.append({
                            "name": sc.get("name", ""),
                            "sql_type": pg_type,
                            "postgres_type": pg_type,
                            "logical_type": log_type,
                            "source_pic": sc_pic,
                            "confidence": conf,
                            "conversion_reason": (
                                f"ALTERNATE_REPRESENTATION of {orig_name}. "
                                f"Child field from redefining group "
                                f"{field.get('name', '')}. " + reason
                            ),
                            "level": sc.get("level"),
                            "pic": sc_pic,
                            "length": sc.get("_byte_length") or sc.get("length"),
                            "is_excluded": False,
                            "is_alternate_repr": True,
                            "redefines_target": orig_name,
                            "alternate_group": field.get("name", ""),
                            "schema_status": f"ALTERNATE_REPRESENTATION: {orig_name}",
                        })
                    # The group node itself is excluded; do NOT recurse into its
                    # children via the normal path (they are already covered above).
                    current_columns.append({
                        "name": field.get("name", ""),
                        "sql_type": "TEXT",
                        "postgres_type": "TEXT",
                        "logical_type": "Group",
                        "source_pic": field.get("pic"),
                        "confidence": strategy_info["confidence"],
                        "conversion_reason": (
                            f"Strategy: {strategy_info['strategy']}. "
                            f"Reason: {strategy_info['reason']}"
                        ),
                        "level": field.get("level"),
                        "pic": field.get("pic"),
                        "length": field.get("length"),
                        "is_excluded": True,
                        "redefines_target": field.get("redefines"),
                        "schema_status": (
                            f"ALTERNATE_REPRESENTATION: {orig_name}"
                        ),
                    })
                    continue  # do not fall through to normal child recursion

                if occurs_info.get("strategy") == "CHILD_TABLE":
                    child_table_name = field.get("name", "unknown_child")
                    child_columns = []
                    
                    if has_children:
                        traverse(field["children"], child_columns)
                    else:
                        pg_type = occurs_info.get("child_sql_type", "TEXT")
                        log_type = "String" if "VARCHAR" in pg_type else "Unknown"
                        child_columns.append({
                            "name": field.get("name", ""),
                            "sql_type": pg_type,
                            "postgres_type": pg_type,
                            "logical_type": log_type,
                            "source_pic": field.get("pic"),
                            "confidence": occurs_info.get("confidence", "HIGH"),
                            "conversion_reason": f"Strategy: CHILD_TABLE. {occurs_info.get('reason', '')}",
                            "level": field.get("level"),
                            "pic": field.get("pic"),
                            "length": field.get("length"),
                            "is_excluded": False,
                        })
                    
                    child_tables.append({
                        "name": child_table_name,
                        "columns": child_columns,
                        "occurs_info": occurs_info
                    })
                    continue

                # ----------------------------------------------------------
                # Normal group recursion
                # ----------------------------------------------------------
                if has_children:
                    traverse(field["children"], current_columns)
                    continue

                # ----------------------------------------------------------
                # Leaf field
                # ----------------------------------------------------------
                if field.get("name"):
                    pg_type, log_type, conf, reason = PostgresMapper.map_pic_to_postgres(
                        field.get("pic", ""), field.get("name", "")
                    )
                    reason_adj = reason

                    if is_redefines_root and strategy_info:
                        reason_adj = (
                            f"Strategy: {strategy_info['strategy']}. "
                            f"Reason: {strategy_info['reason']}"
                        )
                        conf = strategy_info["confidence"]
                    elif occurs_info:
                        reason_adj = (
                            f"Strategy: {occurs_info['strategy']}. "
                            f"Reason: {occurs_info['reason']}"
                        )
                        conf = occurs_info["confidence"]
                        if occurs_info["strategy"] == "INLINE_ARRAY":
                            pg_type = occurs_info["child_sql_type"]

                    col: Dict[str, Any] = {
                        "name": field["name"],
                        "sql_type": pg_type,
                        "postgres_type": pg_type,
                        "logical_type": log_type,
                        "source_pic": field.get("pic"),
                        "confidence": conf,
                        "conversion_reason": reason_adj,
                        "level": field.get("level"),
                        "pic": field.get("pic"),
                        "length": field.get("length"),
                        "is_excluded": is_redefines_root,
                    }
                    if is_redefines_root and strategy_info:
                        col["redefines_target"] = field.get("redefines")
                        col["schema_status"] = (
                            f"REVIEW_REQUIRED: REDEFINES "
                            f"({strategy_info['strategy']})"
                        )
                    elif occurs_info:
                        if occurs_info["strategy"] == "INLINE_ARRAY":
                            col["schema_status"] = "INLINE_ARRAY"
                        else:
                            col["schema_status"] = f"REVIEW_REQUIRED: OCCURS ({occurs_info['strategy']})"
                    current_columns.append(col)

        traverse(records, columns)
        return {"columns": columns, "child_tables": child_tables, "needs_review": needs_review}
