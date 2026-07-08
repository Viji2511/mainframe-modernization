from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.agents.repository_discovery import RepositoryDiscoveryAgent

class RepositoryDiscoveryStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        # In a real system, the input_dir would come from the session/repo mapping
        # We assume repository_id is the input path for now to keep it simple
        agent = RepositoryDiscoveryAgent()
        raw_files = agent.discover(context.session.repository_id)
        
        # We store the raw files temporarily in context to pass to the next stage
        context.metrics['raw_files'] = raw_files
        context.metrics['files_discovered'] = len(raw_files)
