from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum
import src.metadata.metadata as canonical

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
    notes: Optional[str] = ""
    confidence: float = 1.0
    confidence_level: str = "UNKNOWN"
    confidence_reasons: list[str] = Field(default_factory=list)
    validation_result: Optional[dict] = None

    def to_canonical(self) -> canonical.Dataset:
        return canonical.Dataset(
            id=self.dsn,
            dsn=self.dsn,
            organization=self.vsam_type.value,
            record_length=self.record_length,
            confidence_score=self.confidence,
            confidence_level=self.confidence_level,
            confidence_reasons=self.confidence_reasons,
            validation_result=self.validation_result
        )


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

    def to_canonical(self) -> canonical.Field:
        return canonical.Field(
            id=self.name,
            name=self.name,
            pic_type=self.cobol_type,
            length=self.length,
            offset=self.offset,
            redefines=self.redefines
        )


COBOLField.model_rebuild()


class CopyBook(BaseModel):
    filename: str
    dsn_match: Optional[str] = None
    fields: list[COBOLField]
    raw_text: str
    language: str = "COBOL"
    confidence_score: float = 0.0
    confidence_level: str = "UNKNOWN"
    confidence_reasons: list[str] = Field(default_factory=list)
    validation_result: Optional[dict] = None

    def to_canonical(self) -> canonical.Copybook:
        return canonical.Copybook(
            id=self.filename,
            filepath=self.filename,
            language=self.language,
            fields=[f.to_canonical() for f in self.fields],
            confidence_score=self.confidence_score,
            confidence_level=self.confidence_level,
            confidence_reasons=self.confidence_reasons,
            validation_result=self.validation_result
        )


class BusinessRule(BaseModel):
    field_name: str
    usage: Literal["key", "lookup", "validation", "relationship", "output", "other"]
    description: str
    found_in: str
    confidence_score: float = 0.0
    confidence_level: str = "UNKNOWN"
    confidence_reasons: list[str] = Field(default_factory=list)
    validation_result: Optional[dict] = None

    def to_canonical(self) -> canonical.BusinessRule:
        return canonical.BusinessRule(
            id=f"{self.field_name}_{self.usage}",
            rule_type=self.usage,
            description=self.description,
            source_slice=self.found_in,
            confidence_score=self.confidence_score,
            confidence_level=self.confidence_level,
            confidence_reasons=self.confidence_reasons,
            validation_result=self.validation_result
        )


class SourceCodeAnalysis(BaseModel):
    program_name: str
    vsam_dsn: str
    operations: list[str]
    key_fields: list[str]
    business_rules: list[BusinessRule]
    related_files: list[str]
    confidence_score: float = 0.0
    confidence_level: str = "UNKNOWN"
    confidence_reasons: list[str] = Field(default_factory=list)
    validation_result: Optional[dict] = None

    def to_canonical_program(self) -> canonical.Program:
        return canonical.Program(
            id=self.program_name,
            filepath=f"{self.program_name}.cbl",  # Assumed for now
            language="Unknown",
            entry_point=self.program_name,
            called_programs=[],
            confidence_score=self.confidence_score,
            confidence_level=self.confidence_level,
            confidence_reasons=self.confidence_reasons,
            validation_result=self.validation_result
        )


class Inventory(BaseModel):
    input_dir: str
    cobol_files: dict[str, str] = Field(default_factory=dict)
    pli_files: dict[str, str] = Field(default_factory=dict)
    natural_files: dict[str, str] = Field(default_factory=dict)
    rpg_files: dict[str, str] = Field(default_factory=dict)
    jcl_files: dict[str, str] = Field(default_factory=dict)
    idcams_files: dict[str, str] = Field(default_factory=dict)
    copybook_files: dict[str, str] = Field(default_factory=dict)
    listcat_files: dict[str, str] = Field(default_factory=dict)
    metadata_files: dict[str, str] = Field(default_factory=dict)
    other_files: dict[str, str] = Field(default_factory=dict)
    detected_language: str = "Mixed"
    vsam_dsn_candidates: list[str] = Field(default_factory=list)
    classification_details: dict[str, dict[str, str]] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    vsam_dataset: VSAMDataset
    copybook: Optional[CopyBook] = None
    source_analyses: list[SourceCodeAnalysis] = Field(default_factory=list)
    ready_for_schema_design: bool = False
