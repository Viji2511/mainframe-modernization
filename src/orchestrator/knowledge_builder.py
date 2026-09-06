import os
import json
import logging
import uuid
from typing import Dict, Any, List
from src.metadata.session import DiscoverySession
from src.models.knowledge_store import (
    RepositoryKnowledge, ProgramKnowledge, CopybookKnowledge, DatasetKnowledge, 
    Relationship, RepositorySummary, Traceability, JCLJobKnowledge, IDCAMSKnowledge,
    CatalogKnowledge, DiscoveredArtifactKnowledge, FieldSchema
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
            self.knowledge.summary.total_files = self._inventory_file_count(inventory)
            
            # 2. Add Programs
            for path in inventory.cobol_files.keys():
                prog_name = self._unique_artifact_key(path, self.knowledge.programs)
                self.knowledge.programs[prog_name] = ProgramKnowledge(
                    id=prog_name,
                    name=prog_name,
                    language="COBOL",
                    filepath=path,
                    traceability=Traceability(source_file=path, parser="InventoryClassification")
                )
                structure = self.session.execution_metadata.get("cobol_structures", {}).get(path, {})
                self.knowledge.programs[prog_name].properties.update(structure)
                self.knowledge.programs[prog_name].copybooks_used.extend(structure.get("copybooks", []))
                self.knowledge.summary.cobol_programs += 1
                
            # 3. Add Copybooks. New runs use the parser-produced tree; the
            # old regex method is compatibility-only for legacy/direct callers.
            parsed_copybooks = self.session.execution_metadata.get("copybook_structures", {})
            for path, content in inventory.copybook_files.items():
                cb_name = self._unique_artifact_key(path, self.knowledge.copybooks)
                parsed = parsed_copybooks.get(path)
                if parsed:
                    fields = [FieldSchema.model_validate(item) for item in parsed.get("records", [])]
                    properties = {
                        "copybook_model_version": parsed.get("copybook_model_version"),
                        "parser_version": parsed.get("parser_version"),
                        "record_length_min": parsed.get("record_length_min"),
                        "record_length_max": parsed.get("record_length_max"),
                        "copybook_fragment_hierarchy": parsed.get("copybook_fragment_hierarchy", []),
                    }
                    parser_name = "CopybookParser"
                else:
                    fields = self._parse_copybook_fields(content)
                    properties = {"legacy_flat_fallback": True, "stale_copybook_model": True}
                    parser_name = "LegacyFlatCopybookFallback"
                self.knowledge.copybooks[cb_name] = CopybookKnowledge(
                    id=cb_name,
                    name=cb_name,
                    filepath=path,
                    fields=fields,
                    properties=properties,
                    traceability=Traceability(source_file=path, parser=parser_name)
                )
                self.knowledge.summary.copybooks += 1
                
            # Add JCL Jobs
            for path in inventory.jcl_files.keys():
                jcl_name = self._unique_artifact_key(path, self.knowledge.jcl_jobs)
                self.knowledge.jcl_jobs[jcl_name] = JCLJobKnowledge(
                    id=jcl_name,
                    name=jcl_name,
                    filepath=path,
                    traceability=Traceability(source_file=path, parser="InventoryClassification")
                )
                self.knowledge.summary.jcl_jobs += 1

            # Add IDCAMS control statements even when they do not define a
            # cluster. Their existence is still part of repository inventory.
            for path in inventory.idcams_files.keys():
                idcams_name = self._unique_artifact_key(path, self.knowledge.idcams_definitions)
                self.knowledge.idcams_definitions[idcams_name] = IDCAMSKnowledge(
                    id=idcams_name,
                    name=idcams_name,
                    filepath=path,
                    traceability=Traceability(source_file=path, parser="InventoryClassification")
                )
                self.knowledge.summary.idcams_scripts += 1

            # LISTCAT is a structural repository artifact, not merely a source
            # of inferred datasets. Preserve it for the artifact explorer.
            for path in inventory.listcat_files.keys():
                catalog_name = self._unique_artifact_key(path, self.knowledge.catalogs)
                self.knowledge.catalogs[catalog_name] = CatalogKnowledge(
                    id=catalog_name,
                    name=catalog_name,
                    filepath=path,
                    traceability=Traceability(source_file=path, parser="InventoryClassification"),
                )
                self.knowledge.summary.catalog_files += 1

            # Keep discovery-only artifacts visible. They intentionally do not
            # receive a fabricated structure; the UI reports their limitation.
            for artifact_type, items in (
                ("PLI", inventory.pli_files),
                ("NATURAL", inventory.natural_files),
                ("RPG", inventory.rpg_files),
                ("METADATA", inventory.metadata_files),
                ("OTHER", inventory.other_files),
            ):
                for path in items.keys():
                    artifact_name = self._unique_artifact_key(path, self.knowledge.other_artifacts)
                    classification = inventory.classification_details.get(path, {})
                    self.knowledge.other_artifacts[artifact_name] = DiscoveredArtifactKnowledge(
                        id=artifact_name,
                        name=artifact_name,
                        filepath=path,
                        artifact_type=artifact_type,
                        classification_reason=classification.get("reason"),
                        traceability=Traceability(source_file=path, parser="InventoryClassification"),
                    )

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
            self.session.execution_metadata.setdefault("audit_run_id", str(uuid.uuid4()))
            self.knowledge.database_schema = schema_gen.generate(self.knowledge)
            self.knowledge.database_schema["run_id"] = self.session.execution_metadata["audit_run_id"]
            # Generated schemas were built before this assignment; attach the
            # stable run id to each canonical persistence object.
            for generated in self.knowledge.database_schema.get("generated_schemas", []):
                generated["run_id"] = self.session.execution_metadata["audit_run_id"]
            
            self._finalize_summary()
            from src.orchestrator.canonical_structure import build_all_canonical_structures
            self.knowledge.canonical_structures = build_all_canonical_structures(self.knowledge)
                
            return self.knowledge
        except Exception as e:
            logger.exception("Exception occurred in RepositoryKnowledgeBuilder.build")
            raise

    def _process_evidence(self, evidence: Any) -> None:
        """Process a single piece of evidence from the deterministic pipeline."""
        if evidence.artifact_type == "COBOL" and evidence.evidence_type == "SELECT":
            prog_name = self._find_key_by_source(self.knowledge.programs, evidence.source_file)
            if prog_name:
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

        elif evidence.artifact_type == "COBOL" and evidence.evidence_type in {"DIVISION", "SECTION", "PARAGRAPH", "OPERATION", "CALL", "COPY"}:
            prog_name = self._find_key_by_source(self.knowledge.programs, evidence.source_file)
            if prog_name:
                properties = self.knowledge.programs[prog_name].properties
                if evidence.evidence_type == "DIVISION":
                    properties.setdefault("divisions", []).append(str(evidence.value))
                elif evidence.evidence_type == "SECTION":
                    properties.setdefault("sections", []).append(str(evidence.value))
                elif evidence.evidence_type == "PARAGRAPH":
                    properties.setdefault("paragraphs", []).append(str(evidence.value))
                elif evidence.evidence_type == "OPERATION":
                    properties.setdefault("operations", []).append(str(evidence.value))
                elif evidence.evidence_type == "CALL":
                    properties.setdefault("called_programs", []).append(str(evidence.value))
                elif evidence.evidence_type == "COPY":
                    self.knowledge.programs[prog_name].copybooks_used.append(str(evidence.value))
                
        elif evidence.artifact_type == "JCL" and evidence.evidence_type == "DD":
            # Map JCL to Dataset
            dd_properties = evidence.properties or {}
            dsn = dd_properties.get("dataset")
            if dsn and dsn not in self.knowledge.datasets:
                self.knowledge.datasets[dsn] = DatasetKnowledge(
                    id=dsn, 
                    name=dsn,
                    dsn=dsn,
                    traceability=Traceability(source_file=evidence.source_file, parser=evidence.parser_name, originating_evidence_id=evidence.evidence_id)
                )
                self.knowledge.summary.datasets += 1

            # Create a relationship from JCL file to Dataset
            jcl_name = self._find_key_by_source(self.knowledge.jcl_jobs, evidence.source_file)
            if jcl_name:
                dd_data = {
                    "dd_name": evidence.entity_name,
                    **dd_properties,
                }
                if dsn:
                    self.knowledge.jcl_jobs[jcl_name].allocated_datasets.append(dsn)
                self.knowledge.jcl_jobs[jcl_name].dd_statements.append(dd_data)

                hierarchy = self.knowledge.jcl_jobs[jcl_name].properties.setdefault("jcl_hierarchy", {
                    "job_level_dds": [], "steps": []
                })
                scope = dd_data.get("scope")
                step_name = dd_data.get("step_name")
                dd_group = hierarchy["job_level_dds"]
                if scope == "step" and step_name:
                    step = next((item for item in hierarchy["steps"] if item.get("name") == step_name), None)
                    if step is None:
                        step = {"name": step_name, "exec": [], "dds": []}
                        hierarchy["steps"].append(step)
                    dd_group = step["dds"]

                if dd_data.get("is_concatenation"):
                    parent = next((item for item in reversed(dd_group) if item.get("name") == dd_data["dd_name"]), None)
                    if parent is not None:
                        parent.setdefault("concatenations", []).append(dd_data)
                    else:
                        # Keep malformed/incomplete parser output visible as a
                        # standalone DD rather than pretending it has an owner.
                        dd_group.append({"name": dd_data["dd_name"], **dd_data, "concatenations": []})
                else:
                    dd_group.append({"name": dd_data["dd_name"], **dd_data, "concatenations": []})
            if dsn:
                self.knowledge.relationships.append(Relationship(
                    source_id=jcl_name,
                    target_id=dsn,
                    rel_type="ALLOCATES",
                    properties={"dd_name": evidence.entity_name, "evidence_id": evidence.evidence_id}
                ))
                self.knowledge.summary.relationships += 1

        elif evidence.artifact_type == "JCL" and evidence.evidence_type == "EXEC":
            jcl_name = self._find_key_by_source(self.knowledge.jcl_jobs, evidence.source_file)
            if jcl_name:
                exec_data = {
                    "step_name": (evidence.properties or {}).get("step_name"),
                    "program": str(evidence.value),
                    "kind": (evidence.properties or {}).get("kind", "PGM"),
                    **{key: value for key, value in (evidence.properties or {}).items() if key != "step_name"},
                }
                self.knowledge.jcl_jobs[jcl_name].executed_programs.append(str(evidence.value))
                self.knowledge.jcl_jobs[jcl_name].exec_statements.append(exec_data)
                hierarchy = self.knowledge.jcl_jobs[jcl_name].properties.setdefault("jcl_hierarchy", {
                    "job_level_dds": [], "steps": []
                })
                step_name = exec_data["step_name"] or "UNASSIGNED"
                step = next((item for item in hierarchy["steps"] if item.get("name") == step_name), None)
                if step is None:
                    step = {"name": step_name, "exec": [], "dds": []}
                    hierarchy["steps"].append(step)
                step["exec"].append(exec_data)

        elif evidence.artifact_type == "JCL" and evidence.evidence_type == "JOB":
            jcl_name = self._find_key_by_source(self.knowledge.jcl_jobs, evidence.source_file)
            if jcl_name:
                self.knowledge.jcl_jobs[jcl_name].job_card = {
                    "job_name": evidence.entity_name,
                    **(evidence.properties or {}),
                }

        elif evidence.artifact_type == "JCL" and evidence.evidence_type == "SYMBOL":
            jcl_name = self._find_key_by_source(self.knowledge.jcl_jobs, evidence.source_file)
            if jcl_name:
                self.knowledge.jcl_jobs[jcl_name].symbolic_parameters.append(str(evidence.value))

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

            idcams_name = self._find_key_by_source(self.knowledge.idcams_definitions, evidence.source_file)
            if idcams_name:
                self.knowledge.idcams_definitions[idcams_name].defined_clusters.append(dsn)
                self.knowledge.idcams_definitions[idcams_name].properties.setdefault("definitions", []).append({
                    "command": "DEFINE CLUSTER",
                    "name": dsn,
                    **(evidence.properties or {}),
                })

        elif evidence.artifact_type == "CATALOG" and evidence.evidence_type == "CATALOG_ENTRY":
            catalog_name = self._find_key_by_source(self.knowledge.catalogs, evidence.source_file)
            if catalog_name:
                self.knowledge.catalogs[catalog_name].entries.append({
                    "name": evidence.entity_name,
                    **(evidence.properties or {}),
                })

    def _parse_copybook_fields(self, content: str) -> List[FieldSchema]:
        import re
        fields = []
        for line in content.splitlines():
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("*"):
                continue
            
            match_level_name = re.match(r"^\s*(\d{1,2})\s+([A-Z0-9_-]+)", line, re.IGNORECASE)
            if not match_level_name:
                continue
                
            level = int(match_level_name.group(1))
            name = match_level_name.group(2).upper()
            
            pic_match = re.search(r"\bPIC(?:TURE)?\s+(?:IS\s+)?([A-Z0-9()VXS9+-]+)", line, re.IGNORECASE)
            pic = pic_match.group(1).upper() if pic_match else None
            
            usage_match = re.search(r"\bUSAGE\s+(?:IS\s+)?(COMP(?:-[12345])?|BINARY|DISPLAY|PACKED-DECIMAL|INDEX)\b", line, re.IGNORECASE)
            if not usage_match:
                usage_match = re.search(r"\b(COMP(?:-[12345])?|BINARY|DISPLAY|PACKED-DECIMAL|INDEX)\b", line, re.IGNORECASE)
            usage = usage_match.group(1).upper() if usage_match else None
            
            occurs_match = re.search(r"\bOCCURS\s+(\d+)\b", line, re.IGNORECASE)
            occurs = int(occurs_match.group(1)) if occurs_match else None
            
            redefines_match = re.search(r"\bREDEFINES\s+([A-Z0-9_-]+)", line, re.IGNORECASE)
            redefines = redefines_match.group(1).upper() if redefines_match else None
            
            value_match = re.search(r"\bVALUE\s+(?:IS\s+)?('[^']*'|\"[^\"]*\"|[A-Z0-9.+-]+)", line, re.IGNORECASE)
            val = value_match.group(1) if value_match else None
            if val and val.endswith(".") and not val.startswith(("'", '"')):
                val = val[:-1]
                
            data_type = pic if pic else "GROUP"
            length = self._compute_pic_length(pic)
            
            field_obj = FieldSchema(
                name=name,
                data_type=data_type,
                level=level,
                length=length,
                usage=usage,
                occurs=occurs,
                redefines=redefines,
                initial_value=val,
                is_key=any(token in name for token in ("ID", "KEY", "NUM", "NO"))
            )
            field_obj.derived_sql_type = self._field_to_sql_type(field_obj)
            fields.append(field_obj)
            
        return fields

    def _compute_pic_length(self, pic: str) -> int | None:
        if not pic:
            return None
        import re
        total = 0
        pic_clean = re.sub(r"(V|S|CR|DB)", "", pic.upper())
        tokens = re.findall(r"([X9AZB0*/+-])(?:\((\d+)\))?", pic_clean)
        for char, count in tokens:
            total += int(count) if count else 1
        return total if total > 0 else None

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

    def _finalize_summary(self) -> None:
        summary = self.knowledge.summary
        summary.total_files = self._inventory_file_count(self.session.artifact_inventory)
        summary.cobol_programs = len(self.knowledge.programs)
        summary.copybooks = len(self.knowledge.copybooks)
        summary.jcl_jobs = len(self.knowledge.jcl_jobs)
        summary.idcams_scripts = len(self.knowledge.idcams_definitions)
        summary.catalog_files = len(self.knowledge.catalogs)
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

    @staticmethod
    def _inventory_file_count(inventory) -> int:
        if not inventory:
            return 0
        return sum(len(getattr(inventory, name, {})) for name in (
            "cobol_files", "pli_files", "natural_files", "rpg_files",
            "jcl_files", "idcams_files", "copybook_files", "listcat_files",
            "metadata_files", "other_files",
        ))

    @staticmethod
    def _unique_artifact_key(path: str, existing: dict) -> str:
        """Keep same-named files from different directories as separate artifacts."""
        stem = os.path.basename(path).rsplit(".", 1)[0].upper()
        key = stem
        suffix = 2
        while key in existing:
            key = f"{stem}__{suffix}"
            suffix += 1
        return key

    @staticmethod
    def _find_key_by_source(items: dict, source_file: str) -> str | None:
        source_norm = os.path.normcase(os.path.normpath(source_file))
        for key, item in items.items():
            filepath = getattr(item, "filepath", "")
            if os.path.normcase(os.path.normpath(filepath)) == source_norm:
                return key
        # Evidence from older parsers may carry only a basename.
        source_stem = os.path.basename(source_file).rsplit(".", 1)[0].upper()
        return next((key for key in items if key == source_stem), None)

    def save(self, output_dir: str) -> None:
        try:
            os.makedirs(output_dir, exist_ok=True)
            out_path = os.path.join(output_dir, "knowledge_store.json")
            
            # Validation: JSON Output Serialization Check
            try:
                dumped_dict = self.knowledge.model_dump(mode="json") if hasattr(self.knowledge, "model_dump") else self.knowledge.dict()
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
