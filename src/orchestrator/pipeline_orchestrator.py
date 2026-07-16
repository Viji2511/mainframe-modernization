import logging
from typing import Optional
from src.metadata.session import DiscoverySession
from src.orchestrator.context import PipelineContext
from src.orchestrator.stages.repository_discovery_stage import RepositoryDiscoveryStage
from src.orchestrator.stages.artifact_classification_stage import ArtifactClassificationStage
from src.orchestrator.stages.parser_execution_stage import ParserExecutionStage
from src.orchestrator.stages.metadata_normalization_stage import MetadataNormalizationStage
from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
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
        
        # Initialize context and session
        session = DiscoverySession(repository_id=input_dir)
        # Assuming compatibility mode is defaulted to True for Phase 1
        session.compatibility_mode = True
        context = PipelineContext(session=session)

        completed_stages = []

        # Execute stages
        for stage in self.stages:
            stage_name = stage.__class__.__name__
            friendly_name = stage_name.replace("Stage", "")
            import re
            friendly_name = " ".join(re.findall('[A-Z][^A-Z]*', friendly_name))
            
            logger.info(f"{friendly_name} Started")
            self._write_checkpoint(output_dir, stage_name, completed_stages, False)
            
            try:
                stage.execute(context)
            except Exception as e:
                logger.exception(f"Error executing {friendly_name}")
                self._write_checkpoint(output_dir, stage_name, completed_stages, True)
                raise  # Re-raise to fail the pipeline properly
            
            logger.info(f"{friendly_name} Finished")
            completed_stages.append(stage_name)
            self._write_checkpoint(output_dir, stage_name, completed_stages, False)
            
            # Validation
            if session.session_id is None:
                logger.error(f"Validation failed: session_id is None after {friendly_name}")
                raise ValueError("session_id became None")
            if session.artifact_inventory is None and stage_name != "RepositoryDiscoveryStage":
                pass 
            if session.extracted_evidence is None:
                logger.error(f"Validation failed: extracted_evidence is None after {friendly_name}")
                raise ValueError("extracted_evidence became None")

        # Build and Save Repository Knowledge Store
        logger.info("Knowledge Builder Started")
        self._write_checkpoint(output_dir, "KnowledgeBuilder", completed_stages, False)
        try:
            knowledge_builder = RepositoryKnowledgeBuilder(session)
            knowledge_store = knowledge_builder.build()
            session.repository_knowledge = knowledge_store
            
            knowledge_builder.save(output_dir)
            completed_stages.append("KnowledgeBuilder")
            self._write_checkpoint(output_dir, "Completed", completed_stages, False)
        except Exception as e:
            logger.exception("Error executing Knowledge Builder")
            self._write_checkpoint(output_dir, "KnowledgeBuilder", completed_stages, True)
            raise  # Re-raise to fail the pipeline properly
            
        logger.info("Knowledge Builder Finished")
        
        # Final validation
        if session.repository_knowledge is None:
            logger.error("Validation failed: repository_knowledge is None")
            raise ValueError("repository_knowledge became None")
            
        # Validate Result Generation
        expected_output = os.path.join(output_dir, "knowledge_store.json")
        if not os.path.exists(expected_output):
            raise FileNotFoundError(f"Pipeline completed successfully but produced no output files. Missing {expected_output}")
                
        logger.info(f"Pipeline execution completed for {repository_id}")
