import json
from pathlib import Path

from api.repository_api import _artifact_structure_view, _knowledge_structure
from src.agents.artifact_classification import ArtifactClassificationAgent
from src.parsers.catalog_parser import CatalogMetadataExtractor


ROOT = Path(__file__).resolve().parents[1]


def _real_repository_knowledge():
    candidates = []
    for path in (ROOT / "outputs").rglob("knowledge_store.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("copybooks") and data.get("programs") and data.get("jcl_jobs") and data.get("idcams_definitions"):
            candidates.append(data)
    assert candidates, "Expected a discovered repository knowledge store with multiple artifact types"
    return candidates[0]


def _artifact(structure, artifact_type, name="TEST"):
    return {"type": artifact_type, "name": name, "physicalFile": f"{name}.member"}, structure


def test_real_repository_copybooks_remain_visible_and_structured():
    knowledge = _real_repository_knowledge()
    grouped = _knowledge_structure(knowledge)
    # CardDemo currently contains 29 copybooks.  The old fixed 46 threshold
    # depended on whichever stale output directory happened to be found first.
    assert len(grouped["copybooks"]) >= 29
    views = [_artifact_structure_view(copybook, {"type": "COPYBOOK", "name": "COPYBOOK"}) for copybook in grouped["copybooks"].values()]
    view = next(item for item in views if item["available"])
    assert view["artifact_type"] == "COPYBOOK"
    assert view["available"]
    assert view["nodes"]


def test_real_repository_jcl_cobol_and_idcams_views_use_parsed_facts():
    grouped = _knowledge_structure(_real_repository_knowledge())
    expected = {
        "jcl_jobs": ("JCL", {"job", "step", "dd", "exec"}),
        "programs": ("COBOL", {"program", "division", "section", "paragraph"}),
        "idcams_definitions": ("IDCAMS", {"command"}),
    }
    for group_name, (artifact_type, node_types) in expected.items():
        structure = next(iter(grouped[group_name].values()))
        view = _artifact_structure_view(structure, {"type": artifact_type, "name": group_name})
        assert view["artifact_type"] == artifact_type
        assert view["available"]

        def types(nodes):
            return {node["type"] for node in nodes} | {child_type for node in nodes for child_type in types(node.get("children", []))}

        assert types(view["nodes"]) & node_types


def test_real_listcat_file_is_parsed_as_catalog_structure():
    listcat = next((path for path in (ROOT / "data").rglob("*") if path.is_file() and "LISTCAT" in path.name.upper()), None)
    assert listcat, "Expected the real LISTCAT sample in data/"
    evidence = CatalogMetadataExtractor().extract(str(listcat), listcat.read_text(encoding="utf-8"))
    entries = [{"name": item.entity_name, **item.properties} for item in evidence]
    view = _artifact_structure_view(
        {"artifact_type": "CATALOG", "filepath": str(listcat), "entries": entries},
        {"type": "CATALOG", "name": listcat.stem},
    )
    assert view["available"]
    assert {node["type"] for node in view["nodes"]} & {"cluster", "data", "index", "nonvsam", "path"}


def test_unknown_partial_and_malformed_artifacts_fail_gracefully():
    for structure, artifact_type in (({"artifact_type": "OTHER"}, "OTHER"), ({"artifact_type": "JCL"}, "JCL"), ({}, "UNKNOWN")):
        view = _artifact_structure_view(structure, {"type": artifact_type, "name": "UNKNOWN"})
        assert not view["available"]
        assert view["message"]


def test_extensionless_classification_is_used_before_any_extension_fallback():
    classification, _reason = ArtifactClassificationAgent()._classify_file(
        "EXTENSIONLESS_MEMBER", "       IDENTIFICATION DIVISION.\n       PROCEDURE DIVISION."
    )
    assert classification == "cobol"
    view = _artifact_structure_view(
        {"artifact_type": "COBOL", "properties": {"divisions": ["IDENTIFICATION", "PROCEDURE"]}},
        {"type": classification.upper(), "name": "EXTENSIONLESS_MEMBER", "physicalFile": "EXTENSIONLESS_MEMBER"},
    )
    assert view["artifact_type"] == "COBOL"
    assert view["available"]


def test_legacy_noncanonical_artifacts_are_not_filtered():
    knowledge = {
        "copybooks": {"LEGACY": {"id": "LEGACY", "filepath": "legacy.cpy", "fields": []}},
        "jcl_jobs": {"JOB": {"id": "JOB", "filepath": "job.jcl", "exec_statements": []}},
        "programs": {}, "idcams_definitions": {}, "catalogs": {}, "other_artifacts": {}, "datasets": {},
    }
    grouped = _knowledge_structure(knowledge)
    assert set(grouped["copybooks"]) == {"LEGACY"}
    assert set(grouped["jcl_jobs"]) == {"JOB"}
