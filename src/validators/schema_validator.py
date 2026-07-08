from typing import Any
from .base_validator import BaseValidator, ValidationResult
from src.metadata.schemas import CopyBook, COBOLField

class SchemaValidator(BaseValidator):
    @property
    def validator_name(self) -> str:
        return "SchemaValidator"

    def _validate_fields(self, fields: list[COBOLField], seen_names: set, errors: list, warnings: list):
        for field in fields:
            # Check duplicates (excluding FILLER)
            if field.name and field.name.upper() != "FILLER":
                if field.name in seen_names:
                    errors.append(f"Duplicate field name detected: {field.name}")
                else:
                    seen_names.add(field.name)
            
            # Check PIC clause
            if not field.pic and not field.children:
                warnings.append(f"Field '{field.name}' has no PIC clause and no children.")
            
            # Recursively check children
            if field.children:
                self._validate_fields(field.children, seen_names, errors, warnings)

    def validate(self, copybook: CopyBook, **kwargs) -> ValidationResult:
        errors = []
        warnings = []
        evidence = []

        if not copybook or not copybook.fields:
            errors.append("No schema fields available to validate.")
            status = "FAIL"
        else:
            seen_names = set()
            self._validate_fields(copybook.fields, seen_names, errors, warnings)
            evidence.append(f"Validated {len(seen_names)} unique named fields.")
            
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
        return result
