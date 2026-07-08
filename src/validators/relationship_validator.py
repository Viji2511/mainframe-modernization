from typing import Any
from .base_validator import BaseValidator, ValidationResult
from src.metadata.metadata import Relationship

class RelationshipValidator(BaseValidator):
    @property
    def validator_name(self) -> str:
        return "RelationshipValidator"

    def validate(self, relationship: Relationship, **kwargs) -> ValidationResult:
        errors = []
        warnings = []
        evidence = []

        if not relationship.source_id or not relationship.target_id:
            errors.append("Relationship missing source or target ID.")

        if not relationship.rel_type:
            errors.append("Relationship missing type.")

        if relationship.state == "UNVERIFIED":
            warnings.append(f"Relationship {relationship.source_id} -> {relationship.target_id} lacks concrete evidence.")
        else:
            evidence.append(f"Relationship {relationship.rel_type} verified.")

        status = "PASS"
        if errors:
            status = "FAIL"
        elif warnings:
            status = "WARNING"

        result = ValidationResult(
            status=status,
            confidence=relationship.confidence_score,
            errors=errors,
            warnings=warnings,
            evidence=evidence,
            validator=self.validator_name
        )
        
        relationship.validation_result = result.model_dump()
        return result
