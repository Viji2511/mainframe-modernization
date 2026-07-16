from src.metadata.metadata import *
from src.metadata.schemas import VSAMDataset, VSAMType, CopyBook, BusinessRule, SourceCodeAnalysis, Inventory
from pydantic import BaseModel

class PipelineResult(BaseModel):
    repository_id: str
    status: str
    repository: Repository
