from pathlib import Path

from api.repository_api import _artifact_structure_view
from src.agents.artifact_classification import ArtifactClassificationAgent
from src.metadata.session import DiscoverySession
from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
from src.parsers.cobol_parser import COBOLParser


ROOT = Path(__file__).resolve().parents[1]


def _child(node, name):
    return next(item for item in node["children"] if item["name"] == name)


def _view_for(path):
    content = path.read_text(encoding="utf-8")
    inventory = ArtifactClassificationAgent().classify({path.name: content}, str(path.parent))
    session = DiscoverySession(repository_id="cobol-structure-test", artifact_inventory=inventory)
    # Persist exactly the parser-owned tree, as the pipeline does after parse.
    hierarchy = COBOLParser._extract_structure(path.name, content)
    session.execution_metadata["cobol_structures"] = {
        path.name: {
            "cobol_structure_version": "2.0.0", "cobol_hierarchy": hierarchy,
            "divisions": [node["name"].replace(" DIVISION", "") for node in hierarchy],
        }
    }
    knowledge = RepositoryKnowledgeBuilder(session).build()
    artifact_id = next(iter(knowledge.programs))
    canonical = knowledge.canonical_structures[f"COBOL:{artifact_id}"]
    return _artifact_structure_view(canonical, {"type": "COBOL", "name": artifact_id}), canonical


def _all_nodes(nodes):
    for node in nodes:
        yield node
        yield from _all_nodes(node.get("children") or [])


def test_cobol_extensions_are_case_insensitive():
    classifier = ArtifactClassificationAgent()
    source = "       IDENTIFICATION DIVISION.\n       PROCEDURE DIVISION."
    assert classifier._classify_file("sample.cbl", source)[0] == "cobol"
    assert classifier._classify_file("sample.CBL", source)[0] == "cobol"
    assert classifier._classify_file("sample.cob", source)[0] == "cobol"
    assert classifier._classify_file("sample.COB", source)[0] == "cobol"
    assert classifier._classify_file("sample.jcl", "//JOB JOB CLASS=A")[0] == "jcl"
    assert classifier._classify_file("sample.JCL", "//JOB JOB CLASS=A")[0] == "jcl"


def test_real_cobol_tree_preserves_file_control_fd_copy_data_and_procedure_ownership():
    path = ROOT / "data" / "carddemo_samples" / "CBACT01C.cbl"
    view, canonical = _view_for(path)
    assert view["available"]
    program = view["nodes"][0]
    assert [node["name"] for node in program["children"]] == [
        "IDENTIFICATION DIVISION", "ENVIRONMENT DIVISION", "DATA DIVISION", "PROCEDURE DIVISION"
    ]
    environment = _child(program, "ENVIRONMENT DIVISION")
    file_control = _child(_child(environment, "INPUT-OUTPUT SECTION"), "FILE-CONTROL")
    account_select = _child(file_control, "SELECT ACCTFILE-FILE")
    assert account_select["properties"]["assign_to"] == "ACCTFILE"
    assert account_select["properties"]["organization"] == "INDEXED"
    data = _child(program, "DATA DIVISION")
    file_section = _child(data, "FILE SECTION")
    fd = next(node for node in file_section["children"] if node["type"] == "fd")
    assert fd["name"].startswith("FD ")
    working = _child(data, "WORKING-STORAGE SECTION")
    assert any(node["type"] == "data_item" for node in _all_nodes([working]))
    procedure = _child(program, "PROCEDURE DIVISION")
    assert any(node["type"] == "paragraph" for node in procedure["children"])
    assert any(node["type"] == "operation" for node in _all_nodes([procedure]))
    assert all(node["properties"].get("source_file") for node in _all_nodes(program["children"]))
    assert canonical["structure"]["hierarchy"]["cobol_structure_version"] == "2.0.0"


def test_three_real_cobol_members_have_persisted_backend_trees():
    names = ("CBACT01C.cbl", "CBEXPORT.cbl", "CBSTM03A.CBL")
    for name in names:
        view, canonical = _view_for(ROOT / "data" / "carddemo_samples" / name)
        assert view["available"], name
        assert canonical["structure"]["hierarchy"]["cobol_hierarchy"], name
        assert view["nodes"][0]["type"] == "program"
