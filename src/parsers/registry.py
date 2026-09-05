import logging
from typing import Dict, Type
from src.parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)

class ParserRegistry:
    """
    Automatically discovers and registers parsers inheriting from BaseParser.
    """
    def __init__(self):
        self._parsers: Dict[str, Type[BaseParser]] = {}

    def discover_parsers(self) -> None:
        """
        Dynamically discover all BaseParser subclasses and register them based on artifact_type.
        """
        # Ensure all parser modules are loaded here if they aren't imported elsewhere
        # For automatic subclass discovery to work, the modules containing the subclasses must be imported.
        # We will import them explicitly here to guarantee registration.
        import src.parsers.cobol_parser
        import src.parsers.jcl_parser
        import src.parsers.idcams_parser
        import src.parsers.catalog_parser
        import src.parsers.copybook_parser
        
        self._parsers.clear()
        
        def _get_all_subclasses(cls):
            all_subclasses = []
            for subclass in cls.__subclasses__():
                all_subclasses.append(subclass)
                all_subclasses.extend(_get_all_subclasses(subclass))
            return all_subclasses

        for parser_cls in _get_all_subclasses(BaseParser):
            if parser_cls.artifact_type:
                self._parsers[parser_cls.artifact_type] = parser_cls
                logger.info(f"Registered parser {parser_cls.__name__} for {parser_cls.artifact_type}")

    def get_parser(self, artifact_type: str) -> BaseParser:
        """
        Instantiate and return a parser for the given artifact_type.
        Returns None if no parser is found.
        """
        parser_cls = self._parsers.get(artifact_type)
        if parser_cls:
            return parser_cls()
        return None

# Global registry instance
parser_registry = ParserRegistry()
