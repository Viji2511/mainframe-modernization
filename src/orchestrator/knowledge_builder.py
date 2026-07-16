import os
import json
import logging
from typing import Dict, Any, List
from src.metadata.session import DiscoverySession
from src.models.knowledge_store import (
    RepositoryKnowledge, ProgramKnowledge, CopybookKnowledge, DatasetKnowledge, 
    Relationship, RepositorySummary, Traceability, JCLJobKnowledge, IDCAMSKnowledge,
    FieldSchema
)
from src.relationships.relationship_engine import RelationshipEngine

logger = logging.getLogger(__name__)

class RepositoryKnowledgeBuilder:
    def __init__(self, session: DiscoverySession):
        self.session = session
        self.knowledge = RepositoryKnowledge(
            repository_id=session.repository_id,
            summary=RepositorySummary(repository_name=os.path.basename(session.repository_id) or "default_repo")
        )
        
    def build(self) -> RepositoryKnowledge:
        try:
            inventory = self.session.artifact_inventory
            if not inventory:
                return self.knowledge
            
            # Validate Evidence Input
            if self.session.extracted_evidence is None or not isinstance(self.session.extracted_evidence, list):
                logger.error("Validation failed: extracted_evidence is invalid or missing.")
                raise ValueError("Invalid evidence input for KnowledgeBuilder")
                
            # 1. Populate basic counts and items from inventory
            self.knowledge.summary.total_files = len(inventory.other_files) + len(inventory.cobol_files) + len(inventory.jcl_files) + len(inventory.copybook_files)
            
            # 2. Add Programs
            for path in inventory.cobol_files.keys():
                prog_name = os.path.basename(path).split(".")[0].upper()
                self.knowledge.programs[prog_name] = ProgramKnowledge(
                    id=prog_name,
                    name=prog_name,
                    language="COBOL",
                    filepath=path,
                    traceability=Traceability(source_file=path, parser="InventoryClassification")
                )
                self.knowledge.summary.cobol_programs += 1
                
            # 3. Add Copybooks
            for path, content in inventory.copybook_files.items():
                cb_name = os.path.basename(path).split(".")[0].upper()
                self.knowledge.copybooks[cb_name] = CopybookKnowledge(
                    id=cb_name,
                    name=cb_name,
                    filepath=path,
                    fields=self._parse_copybook_fields(content),
                    traceability=Traceability(source_file=path, parser="InventoryClassification")
                )
                self.knowledge.summary.copybooks += 1
                
            # Add JCL Jobs
            for path in inventory.jcl_files.keys():
                jcl_name = os.path.basename(path).split(".")[0].upper()
                self.knowledge.jcl_jobs[jcl_name] = JCLJobKnowledge(
                    id=jcl_name,
                    name=jcl_name,
                    filepath=path,
                    traceability=Traceability(source_file=path, parser="InventoryClassification")
                )
                self.knowledge.summary.jcl_jobs += 1

            # 4. Add Datasets from JCL and Listcat candidates
            for dsn in inventory.vsam_dsn_candidates:
                if dsn not in self.knowledge.datasets:
                    self.knowledge.datasets[dsn] = DatasetKnowledge(
                        id=dsn,
                        name=dsn,
                        dsn=dsn,
                        traceability=Traceability(source_file="unknown", parser="InventoryClassification")
                    )
                    self.knowledge.summary.datasets += 1
                    
            # 5. Process Evidence to enrich the Knowledge
            for evidence in self.session.extracted_evidence:
                self._process_evidence(evidence)
                
            # 6. Build the Knowledge Graph
            graph_engine = RelationshipEngine()
            self.knowledge = graph_engine.build_knowledge_graph(self.knowledge)
            
            from src.metadata.schema_generator import SchemaGenerator
            schema_gen = SchemaGenerator()
            self.knowledge.database_schema = schema_gen.generate(self.knowledge)
            
            self._finalize_summary()
                
            return self.knowledge
        except Exception as e:
            logger.exception("Exception occurred in RepositoryKnowledgeBuilder.build")
            raise

    def _process_evidence(self, evidence: Any) -> None:
        """Process a single piece of evidence from the deterministic pipeline."""
        if evidence.artifact_type == "COBOL" and evidence.evidence_type == "SELECT":
            prog_name = os.path.basename(evidence.source_file).split(".")[0].upper()
            if prog_name in self.knowledge.programs:
                # Value typically contains the dataset or logical file mapping
                self.knowledge.programs[prog_name].datasets_accessed.append(str(evidence.value))
                
                # Create a relationship
                self.knowledge.relationships.append(Relationship(
                    source_id=prog_name,
                    target_id=str(evidence.value),
                    rel_type="ACCESSES",
                    properties={"statement": "SELECT", "evidence_id": evidence.evidence_id}
                ))
                self.knowledge.summary.relationships += 1
                
        elif evidence.artifact_type == "JCL" and evidence.evidence_type == "DD":
            # Map JCL to Dataset
            dsn = str(evidence.value)
            if dsn not in self.knowledge.datasets:
                self.knowledge.datasets[dsn] = DatasetKnowledge(
                    id=dsn, 
                    name=dsn,
                    dsn=dsn,
                    traceability=Traceability(source_file=evidence.source_file, parser=evidence.parser_name, originating_evidence_id=evidence.evidence_id)
                )
                self.knowledge.summary.datasets += 1

            # Create a relationship from JCL file to Dataset
            jcl_name = os.path.basename(evidence.source_file).split(".")[0].upper()
            self.knowledge.relationships.append(Relationship(
                source_id=jcl_name,
                target_id=dsn,
                rel_type="ALLOCATES",
                properties={"dd_name": evidence.entity_name, "evidence_id": evidence.evidence_id}
            ))
            self.knowledge.summary.relationships += 1

        elif evidence.artifact_type == "IDCAMS" and evidence.evidence_type == "DEFINE_CLUSTER":
            dsn = evidence.entity_name
            if dsn in self.knowledge.datasets:
                ds = self.knowledge.datasets[dsn]
                ds.organization = evidence.properties.get("organization", "UNKNOWN")
                ds.type = ds.organization
            else:
                self.knowledge.datasets[dsn] = DatasetKnowledge(
                    id=dsn, 
                    name=dsn,
                    dsn=dsn,
                    type=evidence.properties.get("organization", "UNKNOWN"),
                    organization=evidence.properties.get("organization", "UNKNOWN"),
                    traceability=Traceability(source_file=evidence.source_file, parser=evidence.parser_name, originating_evidence_id=evidence.evidence_id)
                )
                self.knowledge.summary.datasets += 1

    def _parse_copybook_fields(self, content: str) -> List[FieldSchema]:
        import re
        fields = []
        pattern = re.compile(r"^\s*\d{2}\s+([A-Z0-9_-]+)(?:\s+PIC\s+([A-Z0-9()VXS9+-]+))?", re.IGNORECASE)
        for line in content.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            name = match.group(1).upper()
            pic = match.group(2)
            fields.append(FieldSchema(
                name=name,
                data_type=pic.upper() if pic else "GROUP",
                is_key=any(token in name for token in ("ID", "KEY", "NUM", "NO")),
            ))
        return fields

    def _field_to_sql_type(self, field: FieldSchema) -> str:
        data_type = (field.data_type or "").upper().rstrip(".")
        import re

        if data_type == "GROUP":
            return "TEXT"
        if data_type.startswith("X"):
            match = re.search(r"X\((\d+)\)", data_type)
            return f"VARCHAR({match.group(1)})" if match else "TEXT"
        if data_type.startswith("S9") or data_type.startswith("9"):
            match = re.search(r"9\((\d+)\)(?:V9\((\d+)\)|V(9+))?", data_type)
            if match:
                precision = int(match.group(1))
                scale = int(match.group(2) or len(match.group(3) or ""))
                if scale:
                    return f"NUMERIC({precision + scale},{scale})"
                if precision <= 9:
                    return "INTEGER"
                return "BIGINT"
            return "NUMERIC"
        return "TEXT"

    def _build_database_schema(self) -> Dict[str, Any]:
        tables = {}
        for copybook_id, copybook in self.knowledge.copybooks.items():
            columns = []
            key_fields = [field for field in copybook.fields if field.is_key]
            if not key_fields:
                key_fields = [field for field in copybook.fields if field.name.endswith("-ID") or field.name == "ID"]
            primary_key = key_fields[0].name if key_fields else None

            for field in copybook.fields:
                if field.data_type == "GROUP":
                    continue
                columns.append({
                    "name": field.name.lower().replace("-", "_"),
                    "source_field": field.name,
                    "source_pic": field.data_type,
                    "sql_type": self._field_to_sql_type(field),
                    "nullable": not field.is_key and field.name != primary_key,
                    "primary_key": field.name == primary_key,
                    "foreign_key": None,
                })

            tables[copybook_id.lower()] = {
                "table_name": copybook_id.lower(),
                "source_copybook": copybook.filepath,
                "columns": columns,
                "primary_key": primary_key.lower().replace("-", "_") if primary_key else None,
                "foreign_keys": [],
            }

        return {
            "dialect": "postgresql",
            "tables": tables,
            "relationships": [],
            "ddl": self._generate_ddl(tables),
        }

    def _generate_ddl(self, tables: Dict[str, Any]) -> str:
        statements = []
        for table in tables.values():
            column_lines = []
            for column in table["columns"]:
                line = f"  {column['name']} {column['sql_type']}"
                if not column["nullable"]:
                    line += " NOT NULL"
                column_lines.append(line)
            if table.get("primary_key"):
                column_lines.append(f"  PRIMARY KEY ({table['primary_key']})")
            if not column_lines:
                column_lines.append("  id BIGSERIAL PRIMARY KEY")
            statements.append(f"CREATE TABLE {table['table_name']} (\n" + ",\n".join(column_lines) + "\n);")
        return "\n\n".join(statements)

    def _finalize_summary(self) -> None:
        summary = self.knowledge.summary
        summary.total_files = (
            len(self.knowledge.programs)
            + len(self.knowledge.copybooks)
            + len(self.knowledge.jcl_jobs)
            + len(self.knowledge.idcams_definitions)
        )
        summary.cobol_programs = len(self.knowledge.programs)
        summary.copybooks = len(self.knowledge.copybooks)
        summary.jcl_jobs = len(self.knowledge.jcl_jobs)
        summary.datasets = len(self.knowledge.datasets)
        summary.relationships = len(self.knowledge.relationships)
        summary.business_rules = len(self.knowledge.business_rules)
        summary.schema_generation_readiness = bool(self.knowledge.database_schema.get("tables"))

        score = 20
        if summary.total_files:
            score += 15
        if self.knowledge.copybooks:
            score += 20
        if self.knowledge.programs:
            score += 15
        if self.knowledge.jcl_jobs:
            score += 10
        if self.knowledge.datasets:
            score += 10
        if self.knowledge.relationships:
            score += 10
        summary.repository_health_score = min(score, 100)

        if self.knowledge.datasets and self.knowledge.copybooks and (self.knowledge.programs or self.knowledge.jcl_jobs):
            summary.migration_readiness = "Ready for modernization review"
        elif self.knowledge.copybooks and not self.knowledge.datasets:
            summary.migration_readiness = "Copybooks inventoried - upload JCL, LISTCAT, or COBOL to map datasets"
        elif self.knowledge.datasets:
            summary.migration_readiness = "Datasets inventoried - add copybooks for schema design"
        elif summary.total_files:
            summary.migration_readiness = "Inventory complete - more mainframe context needed"
        else:
            summary.migration_readiness = "No repository artifacts found"

    def save(self, output_dir: str) -> None:
        try:
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, "knowledge_store.json")
            
            # Validation: JSON Output Serialization Check
            try:
                dumped_dict = self.knowledge.model_dump() if hasattr(self.knowledge, "model_dump") else self.knowledge.dict()
                json_str = json.dumps(dumped_dict, indent=2)
            except Exception as e:
                logger.error(f"Validation failed: JSON Serialization Error: {e}")
                raise ValueError(f"Knowledge Graph serialization failed: {e}")
                
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(json_str)
            logger.info(f"Saved Repository Knowledge Store to {out_path}")
        except Exception as e:
            logger.exception("Exception occurred in RepositoryKnowledgeBuilder.save")
            raise
