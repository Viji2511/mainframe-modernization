from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.agents.artifact_classification import ArtifactClassificationAgent

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
            
            context.metrics['artifacts_classified'] = sum([
                len(inventory.cobol_files),
                len(inventory.jcl_files),
                len(inventory.idcams_files) if hasattr(inventory, 'idcams_files') else 0,
                len(inventory.listcat_files),
                len(inventory.copybook_files)
            ])
        except Exception as e:
            logger.exception("Exception occurred in ArtifactClassificationStage")
            raise
