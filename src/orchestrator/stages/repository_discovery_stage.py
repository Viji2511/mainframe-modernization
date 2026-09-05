from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.agents.repository_discovery import RepositoryDiscoveryAgent
from src.orchestrator.pipeline_debug import log as debug_log
from src.metadata.audit import AuditTrail

import logging

logger = logging.getLogger(__name__)

class RepositoryDiscoveryStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        try:
            # In a real system, the input_dir would come from the session/repo mapping
            # We assume repository_id is the input path for now to keep it simple
            agent = RepositoryDiscoveryAgent()
            input_dir = context.session.execution_metadata.get("input_dir", context.session.repository_id)
            raw_files = agent.discover(input_dir)
            audit = AuditTrail(context.session)
            audit.record(stage="DISCOVERY", component="RepositoryDiscoveryAgent", action="discover_repository",
                         event_type="repository_discovered", summary="Repository contents discovered.",
                         details={"file_count": len(raw_files)})
            for path in sorted(raw_files):
                audit.record(stage="DISCOVERY", component="RepositoryDiscoveryAgent", action="discover_file",
                             event_type="file_discovered", artifact_name=path, source_file=path,
                             summary=f"Discovered repository artifact {path}.")
            
            # We store the raw files temporarily in context to pass to the next stage
            context.session._raw_files = raw_files
            context.metrics['files_discovered'] = len(raw_files)
            debug_log("Repository Upload", f"Repository root: {input_dir}")
            debug_log("Repository Upload", f"Files discovered: {len(raw_files)}")
            for path in sorted(raw_files):
                debug_log("Repository Upload", f"Discovered: {path}")
        except Exception as e:
            logger.exception("Exception occurred in RepositoryDiscoveryStage")
            raise
