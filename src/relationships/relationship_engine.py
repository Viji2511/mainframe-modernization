from models.metadata import Repository, Relationship
from models.schemas import VSAMDataset, CopyBook, SourceCodeAnalysis

class RelationshipEngine:
    """
    Constructs graph edges (Relationships) between Canonical Metadata Models.
    Instead of nested JSON, relationships explicitly define the architecture 
    (e.g. Program -> READS -> Dataset).
    """
    def __init__(self):
        pass

    def build_relationships(self, repository: Repository, vsam: VSAMDataset, copybook: CopyBook, analyses: list[SourceCodeAnalysis]):
        """
        Infers relationships from the pipeline stage outputs and appends them to the Canonical Repository.
        """
        dsn_id = vsam.dsn
        
        # Dataset -> Copybook
        if copybook and copybook.filename != "NOT_FOUND":
            copybook_id = copybook.filename
            repository.relationships.append(Relationship(
                source_id=dsn_id,
                target_id=copybook_id,
                rel_type="FORMATTED_BY"
            ))
            
            # Dataset -> Field (implied by copybook)
            for field in copybook.fields:
                repository.relationships.append(Relationship(
                    source_id=copybook_id,
                    target_id=field.name,
                    rel_type="CONTAINS_FIELD"
                ))
        
        # Programs
        for analysis in analyses:
            prog_id = analysis.program_name
            
            # Program -> Dataset
            # We can use the operations (e.g. READ, WRITE) as the relationship type, 
            # but for simplicity, we map Program -> ACCESSES -> Dataset.
            rel_type = "ACCESSES"
            if "WRITE" in str(analysis.operations).upper() or "REWRITE" in str(analysis.operations).upper():
                rel_type = "MODIFIES"
            elif "READ" in str(analysis.operations).upper():
                rel_type = "READS"
                
            repository.relationships.append(Relationship(
                source_id=prog_id,
                target_id=dsn_id,
                rel_type=rel_type
            ))
            
            # Program -> Copybook
            if copybook and copybook.filename != "NOT_FOUND":
                repository.relationships.append(Relationship(
                    source_id=prog_id,
                    target_id=copybook.filename,
                    rel_type="INCLUDES"
                ))

            # Program -> BusinessRule
            for rule in analysis.business_rules:
                rule_id = f"{rule.field_name}_{rule.usage}"
                repository.relationships.append(Relationship(
                    source_id=prog_id,
                    target_id=rule_id,
                    rel_type="IMPLEMENTS_RULE"
                ))

            # Program -> Program (called programs if any could be traced here)
            # JCL -> Dataset (source_jcl -> DSN)
            if vsam.source_jcl:
                repository.relationships.append(Relationship(
                    source_id=vsam.source_jcl,
                    target_id=dsn_id,
                    rel_type="ALLOCATES"
                ))
