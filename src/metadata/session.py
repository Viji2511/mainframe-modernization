import uuid
from datetime import datetime
from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field
from src.metadata.schemas import Inventory
from src.metadata.audit import AuditEvent, AUDIT_MODEL_VERSION

class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    artifact_type: str
    entity_type: str
    entity_name: str
    evidence_type: str
    value: Any = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    severity: str = "SUPPORTING" # "PRIMARY", "SECONDARY", or "SUPPORTING"
    source_file: str
    source_line: Optional[int] = None
    source_column: Optional[int] = None
    parser_name: str
    parser_version: str
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)

class RuleTrace(BaseModel):
    evidence_used: List[Evidence] = Field(default_factory=list)
    rule_name: str
    rule_description: str
    resulting_classification: str
    missing_evidence: List[str] = Field(default_factory=list)

class Classification(BaseModel):
    target: str
    type: str
    confidence: float
    trace: RuleTrace

class DiscoverySession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repository_id: str
    execution_timestamp: datetime = Field(default_factory=datetime.utcnow)
    pipeline_version: str = "1.0.0"
    compatibility_mode: bool = True
    parser_versions: Dict[str, str] = Field(default_factory=dict)
    artifact_inventory: Optional[Inventory] = None
    extracted_evidence: List[Evidence] = Field(default_factory=list)
    knowledge_graph: Any = None # Will store NetworkX Graph dict or similar
    executed_rules: List[RuleTrace] = Field(default_factory=list)
    classification_results: List[Classification] = Field(default_factory=list)
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    normalized_metadata: Any = None
    repository_knowledge: Any = None
    audit_events: List[AuditEvent] = Field(default_factory=list)
    audit_model_version: str = AUDIT_MODEL_VERSION
