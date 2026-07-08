from pydantic import BaseModel, Field
from typing import List, Optional
from abc import ABC, abstractmethod

class ValidationResult(BaseModel):
    status: str  # "PASS", "WARNING", "FAIL"
    confidence: float = 0.0
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    validator: str

class BaseValidator(ABC):
    @property
    @abstractmethod
    def validator_name(self) -> str:
        pass

    @abstractmethod
    def validate(self, *args, **kwargs) -> ValidationResult:
        pass
