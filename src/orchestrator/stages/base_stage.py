from abc import ABC, abstractmethod
from src.orchestrator.context import PipelineContext

class PipelineStage(ABC):
    @abstractmethod
    def execute(self, context: PipelineContext) -> None:
        """
        Executes the logic for this pipeline stage.
        """
        pass
