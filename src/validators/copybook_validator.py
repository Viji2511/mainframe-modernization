from typing import Any
from .base_validator import BaseValidator, ValidationResult
from src.metadata.schemas import CopyBook

class CopybookValidator(BaseValidator):
    @property
    def validator_name(self) -> str:
        return "CopybookValidator"

    def validate(self, copybook: CopyBook, **kwargs) -> ValidationResult:
        errors = []
        warnings = []
        evidence = []

        if not copybook or copybook.filename == "NOT_FOUND":
            errors.append("No matched copybook found.")
        else:
            evidence.append(f"Copybook resolved: {copybook.filename}")
            
            if not copybook.fields:
                warnings.append("Copybook parsed but no fields were extracted.")
            else:
                evidence.append(f"Parsed {len(copybook.fields)} fields.")

            if not copybook.dsn_match:
                warnings.append("DSN match not explicit in copybook mapping.")
            else:
                evidence.append(f"Mapped to DSN: {copybook.dsn_match}")

        status = "PASS"
        if errors:
            status = "FAIL"
        elif warnings:
            status = "WARNING"

        result = ValidationResult(
            status=status,
            confidence=copybook.confidence_score if copybook else 0.0,
            errors=errors,
            warnings=warnings,
            evidence=evidence,
            validator=self.validator_name
        )
        
        if copybook:
            copybook.validation_result = result.model_dump()
            
        return result
