from dataclasses import dataclass, field
from src.metadata.session import DiscoverySession
from src.orchestrator.event_bus import EventBus, event_bus

@dataclass
class PipelineContext:
    session: DiscoverySession
    event_bus: EventBus = event_bus
    metrics: dict = field(default_factory=dict)
    
    @property
    def compatibility_mode(self) -> bool:
        return self.session.compatibility_mode
