from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.metadata.audit import AuditEvent, AUDIT_MODEL_VERSION

class Traceability(BaseModel):
    source_file: str
    line_numbers: List[int] = Field(default_factory=list)
    parser: str = "Unknown"
    originating_evidence_id: Optional[str] = None

class KnowledgeObject(BaseModel):
    id: str
    name: str
    traceability: Traceability
    properties: Dict[str, Any] = Field(default_factory=dict)

class EntityMetadata(KnowledgeObject):
    type: str
    
class FieldSchema(BaseModel):
    """Authoritative parsed Copybook node for new repository analyses."""
    node_id: Optional[str] = None
    name: str
    data_type: str
    level: Optional[int] = None
    node_type: str = "ELEMENTARY"
    parent_id: Optional[str] = None
    length: Optional[int] = None
    offset: Optional[int] = None
    decimals: Optional[int] = None
    usage: Optional[str] = None
    occurs: Optional[int] = None
    redefines: Optional[str] = None
    initial_value: Optional[str] = None
    children: List["FieldSchema"] = Field(default_factory=list)
    pic: Optional[str] = None
    pic_category: Optional[str] = None
    signed: bool = False
    precision: Optional[int] = None
    scale: int = 0
    occurs_min: Optional[int] = None
    occurs_max: Optional[int] = None
    occurs_depending_on: Optional[str] = None
    redefines_target: Optional[str] = None
    is_filler: bool = False
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    source_end_line: Optional[int] = None
    logical_length: Optional[int] = None
    byte_length: Optional[int] = None
    physical_span_min: Optional[int] = None
    physical_span_max: Optional[int] = None
    relative_offset: Optional[int] = None
    absolute_offset: Optional[int] = None
    parser_metadata: Dict[str, Any] = Field(default_factory=dict)
    evidence_ids: List[str] = Field(default_factory=list)
    is_key: bool = False
    derived_sql_type: Optional[str] = None


FieldSchema.model_rebuild()

class DatasetKnowledge(KnowledgeObject):
    dsn: str
    type: str = "UNKNOWN"
    organization: Optional[str] = None
    record_length: Optional[int] = None
    key_length: Optional[int] = None
    key_offset: Optional[int] = None
    associated_jcl: List[str] = Field(default_factory=list)
    fields: List[FieldSchema] = Field(default_factory=list)

class CopybookKnowledge(KnowledgeObject):
    filepath: str
    fields: List[FieldSchema] = Field(default_factory=list)

class BusinessRuleKnowledge(KnowledgeObject):
    description: str
    source_program: str
    related_fields: List[str] = Field(default_factory=list)
    logic: str
    
class ProgramKnowledge(KnowledgeObject):
    language: str
    filepath: str
    datasets_accessed: List[str] = Field(default_factory=list)
    copybooks_used: List[str] = Field(default_factory=list)
    business_rules: List[str] = Field(default_factory=list) # IDs to BusinessRuleKnowledge

class JCLJobKnowledge(KnowledgeObject):
    filepath: str
    executed_programs: List[str] = Field(default_factory=list)
    allocated_datasets: List[str] = Field(default_factory=list)
    exec_statements: List[Dict[str, Any]] = Field(default_factory=list)
    dd_statements: List[Dict[str, Any]] = Field(default_factory=list)
    symbolic_parameters: List[str] = Field(default_factory=list)
    procedures_used: List[str] = Field(default_factory=list)
    job_card: Dict[str, Any] = Field(default_factory=dict)

class IDCAMSKnowledge(KnowledgeObject):
    filepath: str
    defined_clusters: List[str] = Field(default_factory=list)


class CatalogKnowledge(KnowledgeObject):
    """Parsed LISTCAT/Catalog entries retained as a first-class artifact."""
    filepath: str
    entries: List[Dict[str, Any]] = Field(default_factory=list)


class DiscoveredArtifactKnowledge(KnowledgeObject):
    """Inventory-only artifact with no structural parser yet available."""
    filepath: str
    artifact_type: str
    classification_reason: Optional[str] = None

class Relationship(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class Dependency(BaseModel):
    source_id: str
    target_id: str
    dependency_type: str

class RepositorySummary(BaseModel):
    repository_name: str = "default_repo"
    total_files: int = 0
    cobol_programs: int = 0
    copybooks: int = 0
    jcl_jobs: int = 0
    idcams_scripts: int = 0
    catalog_files: int = 0
    datasets: int = 0
    business_rules: int = 0
    relationships: int = 0
    schema_generation_readiness: bool = False
    migration_readiness: str = "Evaluating"
    repository_health_score: int = 0

class RepositoryKnowledge(BaseModel):
    repository_id: str
    summary: RepositorySummary = Field(default_factory=RepositorySummary)
    programs: Dict[str, ProgramKnowledge] = Field(default_factory=dict)
    copybooks: Dict[str, CopybookKnowledge] = Field(default_factory=dict)
    datasets: Dict[str, DatasetKnowledge] = Field(default_factory=dict)
    jcl_jobs: Dict[str, JCLJobKnowledge] = Field(default_factory=dict)
    idcams_definitions: Dict[str, IDCAMSKnowledge] = Field(default_factory=dict)
    catalogs: Dict[str, CatalogKnowledge] = Field(default_factory=dict)
    other_artifacts: Dict[str, DiscoveredArtifactKnowledge] = Field(default_factory=dict)
    business_rules: Dict[str, BusinessRuleKnowledge] = Field(default_factory=dict)
    relationships: List[Relationship] = Field(default_factory=list)
    database_schema: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[Dependency] = Field(default_factory=list)
    statistics: Dict[str, Any] = Field(default_factory=dict)
    knowledge_graph_reference: str = ""
    canonical_structures: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    audit_events: List[AuditEvent] = Field(default_factory=list)
    audit_summary: Dict[str, Any] = Field(default_factory=dict)
    audit_model_version: str = AUDIT_MODEL_VERSION
