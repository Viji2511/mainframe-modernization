import logging
from src.models.knowledge_store import RepositoryKnowledge, Relationship

logger = logging.getLogger(__name__)

class RelationshipEngine:
    """
    Constructs the internal Repository Knowledge Graph edges.
    Connects programs, datasets, copybooks, and rules based on extracted evidence and metadata.
    """
    
    def build_knowledge_graph(self, knowledge: RepositoryKnowledge) -> RepositoryKnowledge:
        """
        Infers and builds explicit relationships across all objects in the RepositoryKnowledge.
        """
        try:
            logger.info(f"Building Repository Knowledge Graph for {knowledge.repository_id}")
            
            # We will iterate over the objects and synthesize deterministic edges
            
            # 1. Programs -> Datasets and Copybooks
            for prog_id, prog in knowledge.programs.items():
                for dsn in prog.datasets_accessed:
                    # Based on the evidence (e.g. READ, WRITE, SELECT), we determine edge type
                    # For this deterministic phase, we just default to ACCESSES unless specified in properties
                    knowledge.relationships.append(Relationship(
                        source_id=prog_id,
                        target_id=dsn,
                        rel_type="ACCESSES"
                    ))
                
                for cb in prog.copybooks_used:
                    knowledge.relationships.append(Relationship(
                        source_id=prog_id,
                        target_id=cb,
                        rel_type="USES_COPYBOOK"
                    ))
                    
                for rule_id in prog.business_rules:
                    knowledge.relationships.append(Relationship(
                        source_id=prog_id,
                        target_id=rule_id,
                        rel_type="IMPLEMENTS_RULE"
                    ))
    
            # 2. JCL -> Programs and Datasets
            for jcl_id, jcl in knowledge.jcl_jobs.items():
                for prog in jcl.executed_programs:
                    knowledge.relationships.append(Relationship(
                        source_id=jcl_id,
                        target_id=prog,
                        rel_type="EXECUTES_PROGRAM"
                    ))
                for dsn in jcl.allocated_datasets:
                    knowledge.relationships.append(Relationship(
                        source_id=jcl_id,
                        target_id=dsn,
                        rel_type="ALLOCATES_DATASET"
                    ))
                    
            # 3. Datasets -> Copybooks/Fields
            for dsn, ds in knowledge.datasets.items():
                for cb in ds.associated_jcl:
                    # If we mapped copybooks to datasets
                    knowledge.relationships.append(Relationship(
                        source_id=dsn,
                        target_id=cb,
                        rel_type="USES_RECORD_LAYOUT"
                    ))
                
                # If dataset has fields (keys)
                for field in ds.fields:
                    if field.is_key:
                        knowledge.relationships.append(Relationship(
                            source_id=dsn,
                            target_id=field.name,
                            rel_type="HAS_KEY"
                        ))
    
            # De-duplicate relationships based on source, target, and type
            unique_rels = {}
            for rel in knowledge.relationships:
                key = f"{rel.source_id}_{rel.target_id}_{rel.rel_type}"
                if key not in unique_rels:
                    unique_rels[key] = rel
                    
            knowledge.relationships = list(unique_rels.values())
            knowledge.summary.relationships = len(knowledge.relationships)
            
            logger.info(f"Generated {len(knowledge.relationships)} relationship edges for the Knowledge Graph.")
            
            # Mark graph reference
            knowledge.knowledge_graph_reference = "InternalRelationshipEngineGraph"
            
            return knowledge
        except Exception as e:
            logger.exception("Exception occurred in RelationshipEngine.build_knowledge_graph")
            raise
