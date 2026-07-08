from abc import ABC, abstractmethod
from typing import List
from src.metadata.session import Evidence

class BaseExtractor(ABC):
    """
    Base class for all deterministic specialized extractors.
    """
    
    target_artifact_type: str = ""

    @abstractmethod
    def extract(self, file_path: str, content: str) -> List[Evidence]:
        """
        Extract facts and emit a list of Evidence objects.
        """
        pass
