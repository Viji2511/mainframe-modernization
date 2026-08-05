import logging
from typing import Dict, List, Type
from src.parsers.base_extractor import BaseExtractor

logger = logging.getLogger(__name__)

class ExtractorRegistry:
    """
    Automatically discovers and registers extractors inheriting from BaseExtractor.
    """
    def __init__(self):
        self._extractors: Dict[str, List[Type[BaseExtractor]]] = {}

    def discover_extractors(self) -> None:
        """
        Dynamically discover all BaseExtractor subclasses and group them by target_artifact_type.
        """
        # Import all parser modules to ensure extractors are loaded
        import src.parsers.cobol_parser
        import src.parsers.cobol_knowledge_extractors
        import src.parsers.jcl_parser
        import src.parsers.catalog_parser
        import src.parsers.idcams_parser
        
        self._extractors.clear()
        
        def _get_all_subclasses(cls):
            all_subclasses = []
            for subclass in cls.__subclasses__():
                all_subclasses.append(subclass)
                all_subclasses.extend(_get_all_subclasses(subclass))
            return all_subclasses

        for extractor_cls in _get_all_subclasses(BaseExtractor):
            if extractor_cls.target_artifact_type:
                target = extractor_cls.target_artifact_type
                if target not in self._extractors:
                    self._extractors[target] = []
                self._extractors[target].append(extractor_cls)
                logger.debug(f"Registered extractor {extractor_cls.__name__} for {target}")

    def get_extractors(self, artifact_type: str) -> List[BaseExtractor]:
        """
        Instantiate and return all extractors for a given artifact type.
        """
        extractor_classes = self._extractors.get(artifact_type, [])
        return [cls() for cls in extractor_classes]

# Global instance
extractor_registry = ExtractorRegistry()
