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
import config.settings

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
        context = PipelineContext(session=session)

        completed_stages = []

        for stage in self.stages:
            stage_name = stage.__class__.__name__
            logger.info(f"{stage_name} Started")
            self._write_checkpoint(output_dir, stage_name, completed_stages, False)
            
            try:
                stage.execute(context)
            except Exception as e:
                logger.exception(f"Error executing {stage_name}")
                self._write_checkpoint(output_dir, stage_name, completed_stages, True)
                raise
            
            logger.info(f"{stage_name} Finished")
            completed_stages.append(stage_name)
            self._write_checkpoint(output_dir, stage_name, completed_stages, False)

        # Run Engines
        try:
            logger.info("Engines Started")
            self._write_checkpoint(output_dir, "AutoReconciliationEngine", completed_stages, False)
            from src.metadata.auto_reconciliation_engine import AutoReconciliationEngine
            engine = AutoReconciliationEngine()
            engine.reconcile()
            completed_stages.append("AutoReconciliationEngine")
            
            self._write_checkpoint(output_dir, "SchemaGenerationEngine", completed_stages, False)
            from src.metadata.schema_generation_engine import SchemaGenerationEngine
            schema_engine = SchemaGenerationEngine()
            schema_engine.generate()
            completed_stages.append("SchemaGenerationEngine")
            
            self._write_checkpoint(output_dir, "Completed", completed_stages, False)
        except Exception as e:
            logger.exception("Error executing Engines")
            self._write_checkpoint(output_dir, "Engines", completed_stages, True)
            raise
            
        logger.info(f"Pipeline execution completed for {repository_id}")
