"""Build the repository's parser-independent canonical file structure."""

from __future__ import annotations
from typing import Any

from src.models.canonical_artifact import (
    CanonicalArtifact, Identity, ArtifactStructure, Datasets,
    Dependencies, Semantics, Metadata, Relationships
)

def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _field(field: Any) -> dict:
    raw = _dump(field) or {}
    return {
        "level": raw.get("level"),
        "name": raw.get("name", "UNKNOWN"),
        "pic": raw.get("data_type") or raw.get("pic"),
        "length": raw.get("length"),
        "usage": raw.get("usage"),
        "occurs": raw.get("occurs"),
        "redefines": raw.get("redefines"),
        "initial_value": raw.get("initial_value"),
        "children": raw.get("children", []),
        "derived_sql_type": raw.get("derived_sql_type"),
    }


def build_canonical_structure(artifact_id: str, artifact_type: str, item: Any, knowledge: Any) -> dict:
    raw = _dump(item) or {}
    artifact_type = artifact_type.upper()
    source_file = raw.get("filepath") or (raw.get("traceability") or {}).get("source_file")
    
    identity = Identity(
        id=artifact_id,
        name=raw.get("name") or artifact_id,
        artifact_type=artifact_type,
        source_file=source_file,
        parser=raw.get("parser_name") or artifact_type,
    )
    
    structure = ArtifactStructure()
    datasets_model = Datasets()
    dependencies = Dependencies()
    semantics = Semantics()
    metadata = Metadata(
        properties=raw.get("properties") or {}
    )
    relationships_model = Relationships()

    # Process relationships
    raw_rels = [
        _dump(rel) for rel in knowledge.relationships
        if getattr(rel, "source_id", None) == artifact_id
        or (_dump(rel) or {}).get("source_id") == artifact_id
        or getattr(rel, "target_id", None) == artifact_id
        or (_dump(rel) or {}).get("target_id") == artifact_id
    ]
    
    for rel in raw_rels:
        s_id = rel.get("source_id")
        t_id = rel.get("target_id")
        rel_type = rel.get("rel_type") or rel.get("relationship_type") or ""
        
        if s_id == artifact_id:
            relationships_model.references.append(t_id)
            if "COPYBOOK" in rel_type or "COPY" in rel_type:
                dependencies.copybooks.append(t_id)
            elif "DATASET" in rel_type or "READ" in rel_type or "WRITE" in rel_type:
                dependencies.datasets.append(t_id)
            elif "PROGRAM" in rel_type or "CALL" in rel_type:
                dependencies.called_programs.append(t_id)
            elif "FILE" in rel_type:
                dependencies.files.append(t_id)
        elif t_id == artifact_id:
            relationships_model.referenced_by.append(s_id)

    # Dedup lists
    dependencies.copybooks = list(dict.fromkeys(dependencies.copybooks))
    dependencies.datasets = list(dict.fromkeys(dependencies.datasets))
    dependencies.called_programs = list(dict.fromkeys(dependencies.called_programs))
    relationships_model.references = list(dict.fromkeys(relationships_model.references))
    relationships_model.referenced_by = list(dict.fromkeys(relationships_model.referenced_by))

    if artifact_type == "COBOL":
        raw_datasets = raw.get("datasets_accessed") or []
        raw_copybooks = raw.get("copybooks_used") or []
        
        structure.divisions = (raw.get("properties") or {}).get("divisions", [])
        structure.sections = (raw.get("properties") or {}).get("sections", [])
        structure.procedures = (raw.get("properties") or {}).get("paragraphs", [])
        
        variables = (raw.get("properties") or {}).get("variables", {})
        structure.fields = [
            {"working_storage": variables.get("working_storage", [])},
            {"constants": variables.get("constants", [])},
            {"local": variables.get("local", [])},
            {"file_records": variables.get("file_records", [])},
            {"linkage": variables.get("linkage", [])}
        ]
        
        structure.exec_statements = (raw.get("properties") or {}).get("operations", [])
        
        dependencies.copybooks.extend(raw_copybooks)
        dependencies.datasets.extend(raw_datasets)
        dependencies.called_programs.extend((raw.get("properties") or {}).get("called_programs", []))
        
        semantics.business_rules = raw.get("business_rules") or []
        
        semantics.entities.append({"id": artifact_id, "type": "Program", "name": identity.name})
        
    elif artifact_type == "COPYBOOK":
        fields = [_field(field) for field in raw.get("fields", [])]
        roots = []
        stack = []
        for field in fields:
            level = field.get("level") or 0
            field["children"] = []
            while stack and (stack[-1].get("level") or 0) >= level:
                stack.pop()
            if stack:
                stack[-1].setdefault("children", []).append(field)
            else:
                roots.append(field)
            stack.append(field)
            
        structure.fields = fields
        structure.hierarchy = {
            "record_name": (raw.get("properties") or {}).get("record_name"),
            "records": roots,
        }
        
        semantics.entities.append({"id": artifact_id, "type": "Copybook", "name": identity.name})
        if (raw.get("properties") or {}).get("record_name"):
            semantics.entities.append({"id": f"{artifact_id}_RECORD", "type": "Record", "name": (raw.get("properties") or {}).get("record_name")})

    elif artifact_type == "JCL":
        structure.extra_definitions.append({"job_card": raw.get("job_card") or {}})
        
        for statement in raw.get("exec_statements") or []:
            structure.exec_statements.append(statement)
            
        for statement in raw.get("dd_statements") or []:
            # Deduplication: Strip full dataset representation from DD if present, store only reference
            dd_clean = dict(statement)
            dsn = dd_clean.get("dsn") or dd_clean.get("dataset_name")
            if dsn:
                datasets_model.referenced.append(dsn)
                dd_clean["dataset_reference"] = dsn
                # Remove full dataset payload to prevent duplication
                dd_clean.pop("dataset", None)
            structure.dd_statements.append(dd_clean)
            
        dependencies.called_programs.extend(raw.get("executed_programs") or [])
        datasets_model.referenced.extend(raw.get("allocated_datasets") or [])
        
        semantics.entities.append({"id": artifact_id, "type": "Job", "name": identity.name})

    elif artifact_type == "IDCAMS":
        clusters = raw.get("defined_clusters") or []
        datasets_model.referenced.extend(clusters)
        
        structure.extra_definitions.append({
            "organization": (raw.get("properties") or {}).get("organization", "UNKNOWN"),
            "data_component": (raw.get("properties") or {}).get("data_component", {}),
            "index_component": (raw.get("properties") or {}).get("index_component", {}),
            "key_definition": (raw.get("properties") or {}).get("key_definition", {}),
            "storage_allocation": (raw.get("properties") or {}).get("storage_properties", {}),
        })
        structure.exec_statements = (raw.get("properties") or {}).get("definitions", ["DEFINE CLUSTER"])
        
        semantics.entities.append({"id": artifact_id, "type": "VSAMDefinition", "name": identity.name})

    elif artifact_type == "DATASET":
        ds_name = raw.get("dsn") or raw.get("name") or artifact_id
        datasets_model.referenced.append(ds_name)
        
        structure.extra_definitions.append({
            "organization": raw.get("organization"),
            "dataset_type": raw.get("type"),
            "record_length": raw.get("record_length"),
            "key_length": raw.get("key_length"),
            "cluster": (raw.get("properties") or {}).get("cluster"),
            "volume": (raw.get("properties") or {}).get("volume"),
            "access_method": (raw.get("properties") or {}).get("access_method"),
            "primary_key": (raw.get("properties") or {}).get("primary_key"),
            "alternate_keys": (raw.get("properties") or {}).get("alternate_keys", []),
        })
        structure.records = (raw.get("properties") or {}).get("record_layout", [])
        structure.fields = raw.get("fields") or []
        
        dependencies.called_programs.extend((raw.get("properties") or {}).get("programs", []))
        dependencies.copybooks.extend((raw.get("properties") or {}).get("copybooks", []))
        
        semantics.entities.append({"id": artifact_id, "type": "Dataset", "name": ds_name})

    # Final Dedup for datasets and dependencies
    dependencies.copybooks = list(dict.fromkeys(dependencies.copybooks))
    dependencies.called_programs = list(dict.fromkeys(dependencies.called_programs))
    dependencies.datasets = list(dict.fromkeys(dependencies.datasets))
    datasets_model.referenced = list(dict.fromkeys(datasets_model.referenced))
    
    # Generate final Canonical Artifact
    canonical = CanonicalArtifact(
        identity=identity,
        structure=structure,
        datasets=datasets_model,
        dependencies=dependencies,
        semantics=semantics,
        metadata=metadata,
        relationships=relationships_model
    )
    
    return canonical.model_dump()


def build_all_canonical_structures(knowledge: Any) -> dict[str, dict]:
    structures = {}
    for artifact_type, items in (
        ("COBOL", knowledge.programs), ("COPYBOOK", knowledge.copybooks),
        ("JCL", knowledge.jcl_jobs), ("IDCAMS", knowledge.idcams_definitions),
        ("DATASET", knowledge.datasets),
    ):
        for artifact_id, item in items.items():
            structure = build_canonical_structure(artifact_id, artifact_type, item, knowledge)
            structures[f"{artifact_type}:{artifact_id}"] = structure
    return structures
