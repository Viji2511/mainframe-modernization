import logging
from typing import Optional
from src.metadata.session import DiscoverySession
from src.orchestrator.context import PipelineContext
from src.orchestrator.stages.repository_discovery_stage import RepositoryDiscoveryStage
from src.orchestrator.stages.artifact_classification_stage import ArtifactClassificationStage
from src.orchestrator.stages.parser_execution_stage import ParserExecutionStage
from src.orchestrator.stages.metadata_normalization_stage import MetadataNormalizationStage
from src.orchestrator.adapters.legacy_adapter import LegacyCompatibilityAdapter

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    """
    Lightweight execution engine responsible ONLY for coordinating pipeline stages.
    """
    
    def __init__(self):
        self.stages = [
            RepositoryDiscoveryStage(),
            ArtifactClassificationStage(),
            ParserExecutionStage(),
            MetadataNormalizationStage()
        ]
        self.legacy_adapter = LegacyCompatibilityAdapter()

    def run(self, input_dir: str, repository_id: Optional[str] = None) -> None:
        if not repository_id:
            repository_id = input_dir.split('/')[-1] if '/' in input_dir else input_dir.split('\\')[-1]
            if not repository_id:
                repository_id = "default_repo"

        logger.info(f"Starting pipeline for repository {repository_id}")
        
        # Initialize context and session
        session = DiscoverySession(repository_id=input_dir)
        # Assuming compatibility mode is defaulted to True for Phase 1
        session.compatibility_mode = True
        context = PipelineContext(session=session)

        # Execute stages
        for stage in self.stages:
            stage_name = stage.__class__.__name__
            logger.info(f"Executing stage: {stage_name}")
            try:
                stage.execute(context)
            except Exception as e:
                logger.error(f"Error executing {stage_name}: {e}", exc_info=True)
                # In this architecture, a failure might not stop everything, 
                # but for discovery we probably should break if discovery fails.
                break

        # Compatibility output generation
        if context.compatibility_mode:
            try:
                self.legacy_adapter.execute(context)
            except Exception as e:
                logger.error(f"Error executing legacy adapter: {e}", exc_info=True)
                
        logger.info(f"Pipeline execution completed for {repository_id}")
        
        # Here we could persist the session to a database, etc.
