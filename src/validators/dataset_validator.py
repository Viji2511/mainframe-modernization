from typing import Any
from .base_validator import BaseValidator, ValidationResult
from src.metadata.schemas import VSAMDataset

class DatasetValidator(BaseValidator):
    @property
    def validator_name(self) -> str:
        return "DatasetValidator"

    def validate(self, dataset: VSAMDataset, **kwargs) -> ValidationResult:
        errors = []
        warnings = []
        evidence = []

        if not dataset.dsn or dataset.dsn == "UNKNOWN":
            errors.append("Dataset name (dsn) is missing or UNKNOWN.")
        else:
            evidence.append(f"Valid dataset name: {dataset.dsn}")

        if not dataset.vsam_type:
            errors.append("Organization (vsam_type) is missing.")
        
        if dataset.record_length is None or dataset.record_length <= 0:
            warnings.append("Record length is missing or invalid.")
        
        if dataset.source_jcl:
            evidence.append(f"Discovered via JCL: {dataset.source_jcl}")
        
        if "LISTCAT" in (dataset.notes or "").upper():
            evidence.append("Discovered via LISTCAT catalog.")

        status = "PASS"
        if errors:
            status = "FAIL"
        elif warnings:
            status = "WARNING"

        result = ValidationResult(
            status=status,
            confidence=dataset.confidence_score,
            errors=errors,
            warnings=warnings,
            evidence=evidence,
            validator=self.validator_name
        )
        
        dataset.validation_result = result.model_dump()
        return result
