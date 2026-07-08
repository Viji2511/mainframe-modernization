from src.utils.config_loader import get_validation_config

class ConfidenceEngine:
    """
    Computes confidence scores dynamically based on the configuration logic.
    """
    def __init__(self):
        self.config = get_validation_config()
        self.thresholds = self.config.get("thresholds", {"PASS": 90.0, "WARNING": 70.0, "FAIL": 0.0})

    def _determine_level(self, score: float) -> str:
        if score >= self.thresholds.get("PASS", 90.0):
            return "PASS"
        elif score >= self.thresholds.get("WARNING", 70.0):
            return "WARNING"
        return "FAIL"

    def evaluate_dataset(self, vsam_dataset, inventory) -> None:
        """
        Evaluate confidence score for Dataset Discovery.
        Updates the dataset object in place.
        """
        rules = self.config.get("dataset_discovery", {})
        score = 0.0
        reasons = []

        # Check evidence
        if vsam_dataset.source_jcl:
            score += rules.get("found_in_jcl", {}).get("score", 20.0)
            reasons.append(rules.get("found_in_jcl", {}).get("reason", "Found in JCL"))
            
        # Check if found in LISTCAT by looking at notes or evidence
        if "LISTCAT" in (vsam_dataset.notes or "").upper():
            score += rules.get("found_in_listcat", {}).get("score", 40.0)
            reasons.append(rules.get("found_in_listcat", {}).get("reason", "Found in LISTCAT"))

        # Since we decoupled, we might need to check inventory if it was found in COBOL
        # But for now, we just use the raw score initialized by the strategy
        if score == 0.0:
            score = vsam_dataset.confidence * 100.0  # Fallback to strategy confidence
            if score < 50.0:
                reasons.append(rules.get("llm_inferred_only", {}).get("reason", "Inferred by LLM"))

        vsam_dataset.confidence_score = min(score, 100.0)
        vsam_dataset.confidence_level = self._determine_level(vsam_dataset.confidence_score)
        vsam_dataset.confidence_reasons = reasons

    def evaluate_copybook(self, copybook) -> None:
        rules = self.config.get("copybook_resolution", {})
        score = 0.0
        reasons = []

        if copybook.filename != "NOT_FOUND":
            # Assume dependency traced if it was found via Phase 5 resolution
            score += rules.get("direct_copy_statement", {}).get("score", 80.0)
            reasons.append(rules.get("direct_copy_statement", {}).get("reason", "Direct COPY statement found"))

            if copybook.fields:
                score += rules.get("layout_fields_parsed", {}).get("score", 20.0)
                reasons.append(rules.get("layout_fields_parsed", {}).get("reason", "Fields successfully parsed"))
        else:
            score = 0.0
            reasons.append("No copybook matched.")

        copybook.confidence_score = min(score, 100.0)
        copybook.confidence_level = self._determine_level(copybook.confidence_score)
        copybook.confidence_reasons = reasons

    def evaluate_relationship(self, relationship) -> None:
        rules = self.config.get("relationships", {})
        score = 0.0
        reasons = []

        # If rel_type is UNVERIFIED, score is 0
        if relationship.state == "UNVERIFIED":
            score = rules.get("missing_evidence", {}).get("score", 0.0)
            reasons.append(rules.get("missing_evidence", {}).get("reason", "Missing evidence"))
        else:
            score = rules.get("evidence_found", {}).get("score", 100.0)
            reasons.append(rules.get("evidence_found", {}).get("reason", "Evidence traces relationship"))

        relationship.confidence_score = min(score, 100.0)
        # Relationship doesn't explicitly have confidence_level mapped yet, but we update its score
        relationship.confidence_reasons = reasons

    def aggregate_repository_confidence(self, repository) -> float:
        """
        Calculates a weighted average across the repository.
        """
        scores = []
        for ds in repository.datasets.values():
            scores.append(ds.confidence_score)
        for cb in repository.copybooks.values():
            scores.append(cb.confidence_score)
        for rel in repository.relationships:
            scores.append(rel.confidence_score)
            
        if not scores:
            return 0.0
        return sum(scores) / len(scores)
