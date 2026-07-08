from typing import List, Dict, Any
from src.orchestrator.event_bus import event_bus
from src.metadata.session import Evidence, DiscoverySession

class MetadataNormalizationAgent:
    """
    Consumes Evidence objects via Event Bus, groups them by entity,
    and converts them into normalized internal enterprise entities.
    """
    def __init__(self, session: DiscoverySession):
        self.session = session
        
        # Subscribe to all metadata extraction events
        event_bus.subscribe("CobolMetadataExtracted", self.handle_evidence)
        event_bus.subscribe("JCLMetadataExtracted", self.handle_evidence)
        event_bus.subscribe("IDCAMSMetadataExtracted", self.handle_evidence)
        event_bus.subscribe("CatalogMetadataExtracted", self.handle_evidence)

    def handle_evidence(self, evidence_list: List[Evidence]) -> None:
        """
        Callback for Evidence events. Normalizes the incoming evidence.
        """
        for evidence in evidence_list:
            self._normalize(evidence)
            self.session.extracted_evidence.append(evidence)

    def _normalize(self, evidence: Evidence) -> None:
        """
        Group by entity, normalize entity names, and convert into internal
        enterprise entities (Logical File -> Dataset -> Cluster -> VSAM Entity).
        For now, this just collects them in the session for downstream use.
        """
        # TODO: Implement strict normalization rules based on artifact_type
        # e.g., mapping COBOL LogicalFile to JCL DatasetBinding
        pass
