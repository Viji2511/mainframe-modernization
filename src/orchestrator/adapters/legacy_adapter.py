import logging
from src.orchestrator.context import PipelineContext
from src.orchestrator.adapters.output_adapter import output_adapter
from models.metadata import Repository, PipelineResult, VSAMDataset, VSAMType

# Import legacy agents
from agents.step1_vsam_discovery import VSAMDiscoveryAgent
from agents.step2_copybook_locator import CopyBookLocatorAgent as CopybookLocatorAgent
from agents.step3_source_analyzer import SourceCodeAnalyzerAgent

logger = logging.getLogger(__name__)

class LegacyCompatibilityAdapter:
    """
    Translates normalized evidence into the format expected by legacy components,
    executes existing discovery agents, and produces output artifacts for the UI.
    """
    def execute(self, context: PipelineContext) -> None:
        try:
            logger.info("Running LegacyCompatibilityAdapter to preserve UI/API functionality.")
            
            repo_id = context.session.repository_id
            inventory = context.session.artifact_inventory
            
            if not inventory:
                logger.warning("No artifact inventory found. Legacy adapter skipping.")
                return
    
            # Initialize Legacy Agents
            discovery_agent = VSAMDiscoveryAgent()
            locator_agent = CopybookLocatorAgent(list(inventory.copybook_files.values()))
            analyzer_agent = SourceCodeAnalyzerAgent()
            
            # 1. Fallback VSAM Classification logic (Legacy)
            legacy_datasets = []
            for dsn in inventory.vsam_dsn_candidates:
                # Re-running the LLM classification for legacy UI support
                classification = discovery_agent.classify_dataset(dsn, inventory)
                
                if classification.get("is_vsam", False):
                    legacy_datasets.append(VSAMDataset(
                        dsn=dsn,
                        vsam_type=VSAMType(classification.get("vsam_type", "KSDS")),
                        confidence_score=classification.get("confidence", 0.8),
                        confidence_reasons=classification.get("reasons", []),
                        cluster_name=classification.get("cluster_name"),
                        data_component=classification.get("data_component"),
                        index_component=classification.get("index_component")
                    ))
    
            # 2. Legacy Copybook & Code Analysis
            repo = Repository(id=repo_id)
            repo.datasets = legacy_datasets
            
            for ds in repo.datasets:
                locator_result = locator_agent.locate_copybook(ds.dsn, list(inventory.copybook_files.keys()))
                if locator_result.get("match_found"):
                    cb_path = locator_result.get("best_match_path")
                    cb_content = inventory.copybook_files.get(cb_path, "")
                    analysis = analyzer_agent.analyze(cb_content, ds.vsam_type.value)
                    # Map to legacy models
                    from models.metadata import Copybook as CanonicalCopybook
                    ds.copybook = CanonicalCopybook(
                        id=cb_path,
                        filepath=cb_path,
                        language="COBOL"
                    )
    
            # 3. Output Generation
            result = PipelineResult(
                repository_id=repo_id,
                status="success",
                repository=repo
            )
            
            output_adapter.write_output(repo_id, result)
            logger.info(f"Legacy outputs generated for {repo_id}")
        except Exception as e:
            logger.exception("Exception occurred in LegacyCompatibilityAdapter.execute")
            raise
