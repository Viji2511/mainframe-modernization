from typing import Any
from src.metadata.session import DiscoverySession
from src.orchestrator.context import PipelineContext
from models.metadata import Repository, PipelineResult

class OutputAdapter:
    """
    Standardizes final output format to ensure the UI is decoupled from 
    whether results originate from the legacy implementation or deterministic Rule Engine.
    """
    def write_output(self, repository_id: str, payload: PipelineResult) -> None:
        """
        Writes the standard PipelineResult JSON to outputs/{dsn}_result.json 
        as expected by the UI.
        """
        import os
        os.makedirs("outputs", exist_ok=True)
        out_path = os.path.join("outputs", f"{repository_id}_result.json")
        
        with open(out_path, "w", encoding='utf-8') as f:
            f.write(payload.model_dump_json(indent=2))

output_adapter = OutputAdapter()
