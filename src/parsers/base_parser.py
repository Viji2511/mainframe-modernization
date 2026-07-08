from abc import ABC
from typing import List, Dict, Any
from src.metadata.session import DiscoverySession, Evidence
from src.orchestrator.event_bus import event_bus
from src.parsers.extractor_registry import extractor_registry

class BaseParser(ABC):
    """
    Base class for all deterministic parsers.
    Parsers extract metadata from specific artifact types and publish events.
    They perform NO reasoning. They rely on registered extractors.
    """
    
    # Must be overridden by subclasses (e.g., 'COBOL', 'JCL')
    artifact_type: str = ""

    def parse(self, file_path: str, content: str, session: DiscoverySession) -> List[Evidence]:
        """
        Parse the artifact using dynamically discovered extractors and return Evidence.
        """
        evidence_list = []
        metrics: Dict[str, Any] = {"file": file_path, "extractors_run": 0, "facts_extracted": 0}
        
        # Ensure extractors are loaded
        if not extractor_registry._extractors:
            extractor_registry.discover_extractors()
            
        extractors = extractor_registry.get_extractors(self.artifact_type)
        
        for extractor in extractors:
            metrics["extractors_run"] += 1
            extracted = extractor.extract(file_path, content)
            evidence_list.extend(extracted)
            
        metrics["facts_extracted"] = len(evidence_list)
        
        if evidence_list:
            event_type = f"{self.artifact_type.capitalize()}MetadataExtracted"
            event_bus.publish(event_type, evidence_list)
            
        # Optional metrics event could be published here
        event_bus.publish("ParserMetrics", metrics)
            
        return evidence_list
