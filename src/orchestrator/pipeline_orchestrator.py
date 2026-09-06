import logging
from typing import Optional
from src.metadata.session import DiscoverySession
from src.orchestrator.context import PipelineContext
from src.orchestrator.stages.repository_discovery_stage import RepositoryDiscoveryStage
from src.orchestrator.stages.artifact_classification_stage import ArtifactClassificationStage
from src.orchestrator.stages.supabase_ingestion_stage import SupabaseIngestionStage
from src.orchestrator.stages.parser_execution_stage import ParserExecutionStage
from src.orchestrator.stages.metadata_normalization_stage import MetadataNormalizationStage
import os
import time
import config.settings
from src.orchestrator.pipeline_debug import log as debug_log
from src.metadata.audit import AuditEvent, AuditTrail, summarize_audit_events

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    """
    Lightweight execution engine responsible ONLY for coordinating pipeline stages.
    """
    
    def __init__(self):
        self.stages = [
            RepositoryDiscoveryStage(),
            ArtifactClassificationStage(),
            SupabaseIngestionStage(),
            ParserExecutionStage(),
            MetadataNormalizationStage()
        ]

    def _write_checkpoint(self, output_dir: str, current_stage: str, completed_stages: list, failed: bool):
        import json
        from datetime import datetime
        state = {
            "current_stage": current_stage,
            "completed": completed_stages,
            "failed": failed,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "pipeline_state.json"), "w") as f:
            json.dump(state, f, indent=2)

    def run(self, input_dir: str, repository_id: Optional[str] = None) -> None:
        if not repository_id:
            repository_id = input_dir.split('/')[-1] if '/' in input_dir else input_dir.split('\\')[-1]
            if not repository_id:
                repository_id = "default_repo"
        
        output_dir = os.path.join(os.environ.get("OUTPUT_DIR", config.settings.OUTPUT_DIR), repository_id)
        os.makedirs(output_dir, exist_ok=True)

        logger.info("Pipeline Started")
        
        session = DiscoverySession(repository_id=repository_id)
        session.compatibility_mode = True
        session.execution_metadata["input_dir"] = input_dir
        session.execution_metadata["output_dir"] = output_dir
        context = PipelineContext(session=session)
        audit = AuditTrail(session)
        audit.record(
            stage="SYSTEM", component="PipelineOrchestrator", action="start",
            event_type="pipeline_started", summary="Repository analysis pipeline started.",
            details={"input_reference": "repository input", "pipeline_version": session.pipeline_version},
        )
        # Surface incompatible persisted structures before replacing them. This
        # is especially important for pre-hierarchy JCL metadata.
        prior_store = os.path.join(output_dir, "knowledge_store.json")
        try:
            import json
            with open(prior_store, "r", encoding="utf-8") as source:
                previous = json.load(source)
            prior_jcl = previous.get("jcl_jobs") or {}
            if prior_jcl and any(not (item.get("properties") or {}).get("jcl_hierarchy") for item in prior_jcl.values()):
                audit.record(stage="VALIDATION", component="PipelineOrchestrator", action="check_persisted_versions",
                             event_type="stale_metadata_detected", status="REVIEW_REQUIRED", severity="WARNING",
                             summary="Persisted JCL metadata predates hierarchical DD ownership support; re-analysis is required.",
                             details={"knowledge_model_version": previous.get("audit_model_version")})
            prior_copybooks = previous.get("copybooks") or {}
            if prior_copybooks and any(not (item.get("properties") or {}).get("copybook_model_version") for item in prior_copybooks.values()):
                audit.record(stage="VALIDATION", component="PipelineOrchestrator", action="check_persisted_versions",
                             event_type="stale_metadata_detected", status="REVIEW_REQUIRED", severity="WARNING",
                             summary="Persisted copybook metadata predates the hierarchical semantic model; re-analysis is required.",
                             details={"copybook_model_version": "2.0.0"})
            prior_programs = previous.get("programs") or {}
            if prior_programs and any(not (item.get("properties") or {}).get("cobol_structure_version") for item in prior_programs.values()):
                audit.record(stage="VALIDATION", component="PipelineOrchestrator", action="check_persisted_versions",
                             event_type="stale_metadata_detected", status="REVIEW_REQUIRED", severity="WARNING",
                             summary="Persisted COBOL metadata predates hierarchical ownership structure; re-analysis is required.",
                             details={"cobol_structure_version": "2.0.0"})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        completed_stages = []

        for stage in self.stages:
            stage_name = stage.__class__.__name__
            logger.info(f"{stage_name} Started")
            stage_started = time.perf_counter()
            audit.record(stage="SYSTEM", component=stage_name, action="start", event_type="stage_started",
                         summary=f"{stage_name} started.")
            self._write_checkpoint(output_dir, stage_name, completed_stages, False)
            
            try:
                stage.execute(context)
            except Exception as e:
                logger.exception(f"Error executing {stage_name}")
                audit.record(stage="SYSTEM", component=stage_name, action="execute", event_type="stage_failed",
                             status="FAILED", severity="ERROR", summary=f"{stage_name} failed.",
                             details={"reason": str(e), "duration_ms": round((time.perf_counter() - stage_started) * 1000, 2)})
                audit.record(stage="SYSTEM", component="PipelineOrchestrator", action="finish", event_type="pipeline_failed",
                             status="FAILED", severity="ERROR", summary="Repository analysis pipeline failed.", details={"stage": stage_name})
                audit.persist(output_dir)
                self._write_checkpoint(output_dir, stage_name, completed_stages, True)
                raise
            
            logger.info(f"{stage_name} Finished")
            completed_stages.append(stage_name)
            audit.record(stage="SYSTEM", component=stage_name, action="complete", event_type="stage_completed",
                         summary=f"{stage_name} completed.", details={"duration_ms": round((time.perf_counter() - stage_started) * 1000, 2), "metrics": dict(context.metrics)})
            self._write_checkpoint(output_dir, stage_name, completed_stages, False)

        # Run Engines
        try:
            logger.info("Engines Started")
            
            # Artifact Structure Builder
            self._write_checkpoint(output_dir, "ArtifactStructureBuilderStage", completed_stages, False)
            from src.orchestrator.stages.artifact_structure_builder_stage import ArtifactStructureBuilderStage
            builder = ArtifactStructureBuilderStage()
            builder.execute(context)
            completed_stages.append("ArtifactStructureBuilderStage")

            # AutoReconciliation Engine
            self._write_checkpoint(output_dir, "AutoReconciliationEngine", completed_stages, False)
            from src.metadata.auto_reconciliation_engine import AutoReconciliationEngine
            recon = AutoReconciliationEngine()
            recon.reconcile()
            completed_stages.append("AutoReconciliationEngine")

            # Schema Generation Engine
            self._write_checkpoint(output_dir, "SchemaGenerationEngine", completed_stages, False)
            from src.metadata.schema_generation_engine import SchemaGenerationEngine
            schema_gen = SchemaGenerationEngine()
            schema_gen.generate(audit_trail=audit, knowledge=context.session.repository_knowledge)
            completed_stages.append("SchemaGenerationEngine")
            
            self._write_checkpoint(output_dir, "Completed", completed_stages, False)
        except Exception as e:
            logger.exception("Error executing Engines")
            audit.record(stage="SYSTEM", component="PipelineOrchestrator", action="engines", event_type="pipeline_failed",
                         status="FAILED", severity="ERROR", summary="Repository analysis engines failed.", details={"reason": str(e)})
            audit.persist(output_dir)
            self._write_checkpoint(output_dir, "Engines", completed_stages, True)
            raise
            
        audit.record(stage="SYSTEM", component="PipelineOrchestrator", action="complete", event_type="pipeline_completed",
                     summary="Repository analysis pipeline completed.", details={"completed_stages": completed_stages})
        all_audit_events = audit.persist(output_dir)
        if context.session.repository_knowledge is not None:
            context.session.repository_knowledge.audit_events = [AuditEvent.model_validate(event) for event in all_audit_events]
            context.session.repository_knowledge.audit_summary = summarize_audit_events(all_audit_events)
            builder = getattr(context, "knowledge_builder", None)
            if builder:
                builder.save(output_dir)

        logger.info(f"Pipeline execution completed for {repository_id}")
        debug_log("Status", f"Pipeline completed successfully for {repository_id}")
