from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class VSAMType(str, Enum):
    KSDS = "KSDS"
    ESDS = "ESDS"
    RRDS = "RRDS"
    LDS = "LDS"
    UNKNOWN = "UNKNOWN"


class VSAMDataset(BaseModel):
    dsn: str
    vsam_type: VSAMType
    record_length: Optional[int] = None
    key_length: Optional[int] = None
    key_offset: Optional[int] = None
    ci_size: Optional[int] = None
    record_count: Optional[int] = None
    source_jcl: Optional[str] = None
    notes: str = ""
    confidence: float = 1.0


class COBOLField(BaseModel):
    level: int
    name: str
    pic: Optional[str] = None
    cobol_type: str = "DISPLAY"
    occurs: Optional[int] = None
    redefines: Optional[str] = None
    offset: Optional[int] = None
    length: Optional[int] = None
    children: list["COBOLField"] = Field(default_factory=list)


COBOLField.model_rebuild()


class CopyBook(BaseModel):
    filename: str
    dsn_match: Optional[str] = None
    fields: list[COBOLField]
    raw_text: str
    language: str = "COBOL"


class BusinessRule(BaseModel):
    field_name: str
    usage: Literal["key", "lookup", "validation", "relationship", "output", "other"]
    description: str
    found_in: str


class SourceCodeAnalysis(BaseModel):
    program_name: str
    vsam_dsn: str
    operations: list[str]
    key_fields: list[str]
    business_rules: list[BusinessRule]
    related_files: list[str]


class Inventory(BaseModel):
    input_dir: str
    cobol_files: dict[str, str] = Field(default_factory=dict)
    pli_files: dict[str, str] = Field(default_factory=dict)
    natural_files: dict[str, str] = Field(default_factory=dict)
    rpg_files: dict[str, str] = Field(default_factory=dict)
    jcl_files: dict[str, str] = Field(default_factory=dict)
    copybook_files: dict[str, str] = Field(default_factory=dict)
    listcat_files: dict[str, str] = Field(default_factory=dict)
    metadata_files: dict[str, str] = Field(default_factory=dict)
    other_files: dict[str, str] = Field(default_factory=dict)
    detected_language: str = "Mixed"
    vsam_dsn_candidates: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    vsam_dataset: VSAMDataset
    copybook: Optional[CopyBook] = None
    source_analyses: list[SourceCodeAnalysis] = Field(default_factory=list)
    ready_for_schema_design: bool = False