from src.orchestrator.stages.base_stage import PipelineStage
from src.orchestrator.context import PipelineContext
from src.agents.metadata_normalization import MetadataNormalizationAgent

class MetadataNormalizationStage(PipelineStage):
    def execute(self, context: PipelineContext) -> None:
        # The agent subscribes to the event bus in its init
        agent = MetadataNormalizationAgent(context.session)
        
        # We register it to the context's event bus explicitly just in case
        context.event_bus.subscribe("CobolMetadataExtracted", agent.handle_evidence)
        context.event_bus.subscribe("JCLMetadataExtracted", agent.handle_evidence)
        context.event_bus.subscribe("IDCAMSMetadataExtracted", agent.handle_evidence)
        context.event_bus.subscribe("CatalogMetadataExtracted", agent.handle_evidence)
        
        # Since the parsers have ALREADY run in the previous stage and published synchronously 
        # (if we didn't decouple execution), the events might already be missed if we subscribe late.
        # Wait, the orchestrator should register subscribers BEFORE invoking the parser stage.
        # So we actually just make sure it's initialized.
        pass
