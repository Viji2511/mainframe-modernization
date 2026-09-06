from api.repository_api import _artifact_structure_view
from src.agents.artifact_classification import ArtifactClassificationAgent
from src.metadata.session import DiscoverySession
from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
from src.parsers.cobol_parser import COBOLParser
from src.parsers.copybook_parser import CopybookParser


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.get("children") or [])


def test_fixed_format_cobol_preserves_divisions_and_fields():
    path = "fixed.cbl"
    source = """000100 IDENTIFICATION DIVISION.
000200 PROGRAM-ID. FIXED.
000300 DATA DIVISION.
000400 WORKING-STORAGE SECTION.
000500 01 WS-COUNT PIC 9(4).
000600 PROCEDURE DIVISION.
000700 MAIN-LOGIC.
000800     MOVE 1 TO WS-COUNT.
"""
    hierarchy = COBOLParser._extract_structure(path, source)
    assert [node["name"] for node in hierarchy] == ["IDENTIFICATION DIVISION", "DATA DIVISION", "PROCEDURE DIVISION"]
    assert any(node["name"] == "01 WS-COUNT" for node in _walk(hierarchy))
    assert any(node["name"].startswith("MOVE 1 TO WS-COUNT") for node in _walk(hierarchy))


def test_cpy_procedure_fragment_remains_copybook_and_has_structure():
    path = "fragment.cpy"
    source = """      * Reusable procedure copybook
000100 EDIT-DATE.
000200     SET DATE-INVALID TO TRUE.
000300     MOVE 1 TO WS-COUNT.
"""
    inventory = ArtifactClassificationAgent().classify({path: source}, "test")
    assert path in inventory.copybook_files
    session = DiscoverySession(repository_id="test", artifact_inventory=inventory)
    CopybookParser().parse(path, source, session)
    knowledge = RepositoryKnowledgeBuilder(session).build()
    artifact_id = next(iter(knowledge.copybooks))
    canonical = knowledge.canonical_structures[f"COPYBOOK:{artifact_id}"]
    view = _artifact_structure_view(canonical, {"type": "COPYBOOK", "name": artifact_id})

    assert view["available"]
    assert view["nodes"][0]["name"] == "Procedure Fragment"
    assert any(node["name"] == "EDIT-DATE" for node in _walk(view["nodes"]))
