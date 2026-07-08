from pydantic import BaseModel, Field as PydanticField
from typing import List, Optional

class CanonicalModel(BaseModel):
    id: str
    confidence_score: float = 0.0
    confidence_level: str = "UNKNOWN"
    confidence_reasons: List[str] = PydanticField(default_factory=list)
    validation_result: Optional[dict] = None

class Artifact(CanonicalModel):
    filepath: str
    language: str

class Field(CanonicalModel):
    name: str
    pic_type: str
    length: Optional[int] = None
    offset: Optional[int] = None
    redefines: Optional[str] = None

class Copybook(Artifact):
    fields: List[Field] = PydanticField(default_factory=list)

class Dataset(CanonicalModel):
    dsn: str
    organization: str
    record_length: Optional[int] = None

class BusinessRule(CanonicalModel):
    rule_type: str
    description: str
    source_slice: str

class Program(Artifact):
    entry_point: str
    called_programs: List[str] = PydanticField(default_factory=list)

class Relationship(BaseModel):
    source_id: str
    target_id: str
    rel_type: str  # e.g., "READS", "INCLUDES", "EXECUTES", "DEFINES"
    state: str = "UNVERIFIED"
    confidence_score: float = 0.0
    confidence_reasons: List[str] = PydanticField(default_factory=list)
    validation_result: Optional[dict] = None

class Repository(BaseModel):
    repository_id: str
    artifacts: dict[str, Artifact] = PydanticField(default_factory=dict)
    datasets: dict[str, Dataset] = PydanticField(default_factory=dict)
    programs: dict[str, Program] = PydanticField(default_factory=dict)
    copybooks: dict[str, Copybook] = PydanticField(default_factory=dict)
    business_rules: dict[str, BusinessRule] = PydanticField(default_factory=dict)
    relationships: List[Relationship] = PydanticField(default_factory=list)
