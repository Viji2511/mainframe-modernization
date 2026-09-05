from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.agents.artifact_classification import ArtifactClassificationAgent
from src.orchestrator.pipeline_debug import log as debug_log
from src.metadata.audit import AuditTrail
import os

import logging

logger = logging.getLogger(__name__)

class ArtifactClassificationStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        try:
            raw_files = getattr(context.session, '_raw_files', {})
            if not raw_files:
                raw_files = context.metrics.get('raw_files', {})
                
            agent = ArtifactClassificationAgent()
            
            inventory = agent.classify(raw_files, context.session.repository_id)
            context.session.artifact_inventory = inventory
            audit = AuditTrail(context.session)
            
            context.metrics['artifacts_classified'] = sum([
                len(inventory.cobol_files),
                len(inventory.jcl_files),
                len(inventory.idcams_files) if hasattr(inventory, 'idcams_files') else 0,
                len(inventory.listcat_files),
                len(inventory.copybook_files)
            ])
            for path, details in sorted(inventory.classification_details.items()):
                artifact_type = details["artifact_type"]
                unsupported = artifact_type == "OTHER"
                audit.record(
                    stage="CLASSIFICATION", component="ArtifactClassificationAgent", action="classify_artifact",
                    event_type="unsupported_file_discovered" if unsupported else "artifact_classified",
                    status="SKIPPED" if unsupported else "SUCCESS", severity="WARNING" if unsupported else "INFO",
                    artifact_id=os.path.basename(path).rsplit(".", 1)[0].upper(), artifact_name=path,
                    source_file=path, summary=(f"{path} has no supported parser." if unsupported else f"{path} classified as {artifact_type}."),
                    details={"artifact_type": artifact_type, "reason": details["reason"]},
                    confidence="HIGH" if not unsupported else "LOW",
                )
                debug_log(
                    "Artifact Discovery",
                    f"{path} -> {details['artifact_type']} ({details['reason']})"
                )
        except Exception as e:
            logger.exception("Exception occurred in ArtifactClassificationStage")
            raise
