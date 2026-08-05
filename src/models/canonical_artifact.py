from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Identity(BaseModel):
    id: str
    name: str
    artifact_type: str
    source_file: Optional[str] = None
    parser: Optional[str] = None

class ArtifactStructure(BaseModel):
    divisions: List[Any] = Field(default_factory=list)
    sections: List[Any] = Field(default_factory=list)
    records: List[Any] = Field(default_factory=list)
    fields: List[Any] = Field(default_factory=list)
    steps: List[Any] = Field(default_factory=list)
    exec_statements: List[Any] = Field(default_factory=list)
    dd_statements: List[Any] = Field(default_factory=list)
    procedures: List[Any] = Field(default_factory=list)
    hierarchy: Dict[str, Any] = Field(default_factory=dict)
    # Generic catch-all for missing parts to ensure no data is lost
    extra_definitions: List[Any] = Field(default_factory=list)

class Datasets(BaseModel):
    input: List[str] = Field(default_factory=list)
    output: List[str] = Field(default_factory=list)
    temporary: List[str] = Field(default_factory=list)
    referenced: List[str] = Field(default_factory=list)

class Dependencies(BaseModel):
    copybooks: List[str] = Field(default_factory=list)
    called_programs: List[str] = Field(default_factory=list)
    datasets: List[str] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)
    transactions: List[str] = Field(default_factory=list)
    external_systems: List[str] = Field(default_factory=list)

class Semantics(BaseModel):
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    business_objects: List[Dict[str, Any]] = Field(default_factory=list)
    inferred_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    business_rules: List[Dict[str, Any]] = Field(default_factory=list)

class Metadata(BaseModel):
    confidence: float = 1.0
    parser_version: Optional[str] = None
    extraction_time: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    properties: Dict[str, Any] = Field(default_factory=dict)

class Relationships(BaseModel):
    parent: List[str] = Field(default_factory=list)
    children: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)
    referenced_by: List[str] = Field(default_factory=list)

class CanonicalArtifact(BaseModel):
    identity: Identity
    structure: ArtifactStructure = Field(default_factory=ArtifactStructure)
    datasets: Datasets = Field(default_factory=Datasets)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    semantics: Semantics = Field(default_factory=Semantics)
    metadata: Metadata = Field(default_factory=Metadata)
    relationships: Relationships = Field(default_factory=Relationships)
