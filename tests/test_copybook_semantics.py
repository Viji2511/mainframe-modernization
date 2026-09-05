from pathlib import Path

from src.metadata.schemas import Inventory
from src.metadata.session import DiscoverySession
from src.models.knowledge_store import FieldSchema
from src.orchestrator.canonical_structure import build_canonical_structure
from src.orchestrator.knowledge_builder import RepositoryKnowledgeBuilder
from src.parsers.copybook_parser import CopybookParser, compute_physical_length, parse_pic


ROOT = Path(__file__).resolve().parents[1]


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.children)


def parse(text):
    return CopybookParser().parse_structure("layout.cpy", text)


def test_hierarchy_groups_and_source_provenance_are_preserved():
    roots = parse("""01 CUSTOMER.\n  05 CUSTOMER-ID PIC X(10).\n  05 CUSTOMER-NAME.\n    10 FIRST-NAME PIC X(20).\n    10 LAST-NAME PIC X(20).\n""")
    root = roots[0]
    assert [node.name for node in root.children] == ["CUSTOMER-ID", "CUSTOMER-NAME"]
    assert [node.name for node in root.children[1].children] == ["FIRST-NAME", "LAST-NAME"]
    assert root.children[1].node_type == "GROUP"
    assert root.children[1].source_line == 3
    assert root.byte_length == 50


def test_pic_semantics_distinguish_signed_implied_decimal_and_usage():
    semantic = parse_pic("S9(7)V99", "COMP-3")
    assert semantic == {
        "raw": "S9(7)V99", "category": "NUMERIC", "signed": True,
        "precision": 9, "scale": 2, "logical_length": 9, "usage": "COMP-3",
    }
    assert parse_pic("X(10)")["logical_length"] == 10
    assert parse_pic("9(5)V99")["logical_length"] == 7


def test_physical_lengths_use_display_packed_and_ibm_binary_rules():
    nodes = list(walk(parse("""01 R.\n 05 A PIC X(10).\n 05 B PIC S9(10)V99 COMP-3.\n 05 C PIC 9(11) COMP.\n 05 D PIC 9(5)V99.\n 05 E PIC 9(5) COMP-1.\n 05 F PIC 9(5) COMP-2.\n""")))
    by_name = {node.name: node for node in nodes}
    assert by_name["A"].byte_length == 10
    assert by_name["B"].byte_length == 7
    assert by_name["C"].byte_length == 8
    assert by_name["D"].byte_length == 7
    assert by_name["E"].byte_length == 4
    assert by_name["F"].byte_length == 8


def test_filler_is_physical_but_marked_non_business_and_affects_offset():
    nodes = {node.name: node for node in walk(parse("""01 R.\n 05 A PIC X(2).\n 05 FILLER PIC X(3).\n 05 B PIC X(2).\n"""))}
    assert nodes["FILLER"].is_filler is True
    assert nodes["A"].absolute_offset == 0
    assert nodes["FILLER"].absolute_offset == 2
    assert nodes["B"].absolute_offset == 5


def test_scalar_group_nested_and_odo_occurs_remain_hierarchical():
    roots = parse("""01 R.\n 05 PHONE PIC X(10) OCCURS 3 TIMES.\n 05 ROW OCCURS 1 TO 5 TIMES DEPENDING ON ROW-COUNT.\n   10 COLUMN OCCURS 10 TIMES.\n     15 VALUE PIC X.\n""")
    phone, row = roots[0].children
    assert (phone.occurs_min, phone.occurs_max, phone.byte_length, phone.physical_span_max) == (3, 3, 10, 30)
    assert (row.occurs_min, row.occurs_max, row.occurs_depending_on) == (1, 5, "ROW-COUNT")
    assert row.children[0].name == "COLUMN"
    assert row.children[0].children[0].name == "VALUE"
    assert row.byte_length == 10 and row.physical_span_min == 10 and row.physical_span_max == 50


def test_redefines_shares_storage_and_does_not_double_record_length():
    roots = parse("""01 R.\n 05 BIRTHDATE PIC X(10).\n 05 BIRTHDATE-DETAILS REDEFINES BIRTHDATE.\n   10 B-M PIC 99.\n   10 FILLER PIC X.\n   10 B-D PIC 99.\n   10 FILLER PIC X.\n   10 B-Y PIC 9(4).\n 05 NEXT PIC X(2).\n""")
    root = roots[0]
    birthdate, alternate, next_field = root.children
    assert alternate.redefines_target == "BIRTHDATE"
    assert alternate.absolute_offset == birthdate.absolute_offset == 0
    assert alternate.byte_length == birthdate.byte_length == 10
    assert next_field.absolute_offset == 10
    assert root.byte_length == 12
    assert len(alternate.children) == 5


def test_condition_and_renames_levels_do_not_distort_layout():
    roots = parse("""01 R.\n 05 FLAG PIC X.\n  88 FLAG-ON VALUE 'Y'.\n 66 ALT RENAMES FLAG.\n 77 STANDALONE PIC X(2).\n""")
    root, standalone = roots
    assert root.children[1].node_type == "RENAMES"
    assert root.children[0].children[0].node_type == "CONDITION"
    assert root.byte_length == 1
    assert standalone.absolute_offset == 1


def test_parser_emits_per_node_evidence_and_model_evidence_links():
    parser = CopybookParser()
    session = DiscoverySession(repository_id="copybook-evidence")
    evidence = parser.parse("example.cpy", "01 R.\n 05 A PIC X(3).\n", session)
    structure = session.execution_metadata["copybook_structures"]["example.cpy"]
    assert len(evidence) == 2
    assert evidence[1].evidence_type == "COPYBOOK_NODE"
    assert structure["records"][0]["children"][0]["evidence_ids"] == [evidence[1].evidence_id]


def test_authoritative_tree_round_trips_through_knowledge_and_canonical_structure():
    content = "01 R.\n 05 G.\n  10 A PIC X(2).\n"
    session = DiscoverySession(repository_id="copybook-roundtrip", artifact_inventory=Inventory(input_dir="test", copybook_files={"round.cpy": content}))
    CopybookParser().parse("round.cpy", content, session)
    knowledge = RepositoryKnowledgeBuilder(session).build()
    copybook = knowledge.copybooks["ROUND"]
    assert copybook.properties["copybook_model_version"] == "2.0.0"
    assert copybook.properties.get("legacy_flat_fallback") is None
    dumped = copybook.model_dump(mode="json")
    restored = type(copybook).model_validate(dumped)
    assert restored.fields[0].children[0].children[0].name == "A"
    canonical = build_canonical_structure("ROUND", "COPYBOOK", restored, knowledge)
    assert canonical["structure"]["hierarchy"]["records"][0]["children"][0]["children"][0]["name"] == "A"


def test_legacy_flat_fallback_is_explicit_for_non_pipeline_callers():
    content = "01 R.\n 05 A PIC X(2).\n"
    session = DiscoverySession(repository_id="legacy-copybook", artifact_inventory=Inventory(input_dir="test", copybook_files={"legacy.cpy": content}))
    knowledge = RepositoryKnowledgeBuilder(session).build()
    assert knowledge.copybooks["LEGACY"].properties["legacy_flat_fallback"] is True
    assert knowledge.copybooks["LEGACY"].properties["stale_copybook_model"] is True


def test_real_repository_copybooks_preserve_real_layout_semantics():
    parser = CopybookParser()
    samples = {
        "COCOM01Y.cpy": 0, "CODATECN.cpy": 4, "CVEXPORT.cpy": 6,
        "CVCRD01Y.cpy": 3, "COMEN02Y.cpy": 1,
    }
    for filename, redefine_count in samples.items():
        roots = parser.parse_structure(filename, (ROOT / "data" / "carddemo_samples" / filename).read_text(encoding="utf-8", errors="replace"))
        nodes = list(walk(roots))
        assert roots[0].physical_span_max and roots[0].physical_span_max > 0
        assert len([node for node in nodes if node.redefines_target]) == redefine_count
    export = list(walk(parser.parse_structure("CVEXPORT.cpy", (ROOT / "data" / "carddemo_samples" / "CVEXPORT.cpy").read_text(encoding="utf-8"))))
    packed = next(node for node in export if node.name == "EXP-ACCT-CURR-BAL")
    occurs = next(node for node in export if node.name == "EXP-CUST-ADDR-LINES")
    assert (packed.precision, packed.scale, packed.byte_length) == (12, 2, 7)
    assert occurs.children[0].name == "EXP-CUST-ADDR-LINE" and occurs.physical_span_max == 150
    assert parser.parse_structure("CVEXPORT.cpy", (ROOT / "data" / "carddemo_samples" / "CVEXPORT.cpy").read_text(encoding="utf-8"))[0].physical_span_max == 500
