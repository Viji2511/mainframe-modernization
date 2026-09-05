from pathlib import Path

from src.metadata.schema_generator import RESOLVED_SCHEMA_VERSION, SchemaGenerator
from src.models.knowledge_store import CopybookKnowledge, FieldSchema, RepositoryKnowledge, Traceability
from src.parsers.copybook_parser import CopybookParser


def _knowledge(name, fields):
    copybook = CopybookKnowledge(id=name, name=name, filepath=f"{name}.cpy", fields=fields,
        properties={"copybook_model_version": "2.0.0"}, traceability=Traceability(source_file=f"{name}.cpy"))
    return RepositoryKnowledge(repository_id="resolved-test", copybooks={name: copybook})


def _node(name, *, pic="X(10)", node_type="ELEMENTARY", children=None, **facts):
    semantic = CopybookParser._node_from_declaration("test.cpy", facts.pop("line", 1), facts.pop("level", 5), name, f"PIC {pic}." if pic else ".")
    semantic.node_type, semantic.children = node_type, children or []
    for key, value in facts.items():
        setattr(semantic, key, value)
    return semantic


def test_resolved_schema_consumes_field_schema_without_pic_reparse():
    field = _node("BALANCE", pic="S9(10)V99", usage="COMP-3", precision=12, scale=2, logical_length=12, byte_length=7)
    # The downstream mapper has only parser semantics; raw PIC text is not an
    # input to this authoritative path.
    field.pic = None
    field.data_type = ""
    schema = SchemaGenerator().generate(_knowledge("BAL", [field]))
    column = next(column for column in schema["tables"][0]["columns"] if column.get("source_name") == "BALANCE")
    assert schema["resolved_schema_version"] == RESOLVED_SCHEMA_VERSION
    assert column["sql_type"] == "NUMERIC(12,2)"
    assert column["physical_length"] == 7
    assert column["mapping_quality"] == "EXACT"


def test_scalar_occurs_is_one_array_column_and_no_business_pk_guess():
    phone = _node("PHONE", occurs=3, occurs_min=3, occurs_max=3)
    table = SchemaGenerator().generate(_knowledge("PHONE", [phone]))["tables"][0]
    assert next(column for column in table["columns"] if column.get("source_name") == "PHONE")["sql_type"] == "VARCHAR(10)[]"
    assert table["primary_keys"] == ["RECORD_ID"]
    assert table["key_policy"] == "GENERATED_TECHNICAL_RECORD_KEY"


def test_group_occurs_creates_one_child_table_with_direct_parent_relation():
    street, city = _node("STREET", pic="X(30)"), _node("CITY", pic="X(20)")
    address = _node("ADDRESS", pic=None, node_type="GROUP", children=[street, city], occurs=3, occurs_min=3, occurs_max=3)
    schema = SchemaGenerator().generate(_knowledge("ADDRESS", [address]))
    parent, child = schema["tables"]
    assert parent["primary_keys"] == ["RECORD_ID"]
    assert child["primary_keys"] == ["PARENT_RECORD_ID", "OCCURRENCE_INDEX"]
    assert {c["name"] for c in child["columns"]} >= {"STREET", "CITY"}
    assert schema["relations"][0]["type"] == "OCCURS_CHILD_TABLE"


def test_filler_is_retained_in_layout_but_never_becomes_a_column():
    parser = CopybookParser()
    fields = parser.parse_structure("F.cpy", "01 REC.\n  05 A PIC X(2).\n  05 FILLER PIC X(3).\n  05 B PIC X(2).")
    table = SchemaGenerator().generate(_knowledge("F", fields))["tables"][0]
    assert {column["name"] for column in table["columns"] if not column.get("is_technical")} == {"A", "B"}
    assert any(item["strategy"] == "EXCLUDE_FILLER" for item in table["resolutions"])


def test_alternate_redefines_uses_real_offsets_and_excludes_filler():
    parser = CopybookParser()
    fields = parser.parse_structure("D.cpy", "01 REC.\n  05 BIRTHDATE PIC X(10).\n  05 BIRTHDETAIL REDEFINES BIRTHDATE.\n    10 MM PIC 9(2).\n    10 FILLER PIC X.\n    10 DD PIC 9(2).\n    10 FILLER PIC X.\n    10 YYYY PIC 9(4).")
    table = SchemaGenerator().generate(_knowledge("D", fields))["tables"][0]
    alternate = [c for c in table["columns"] if c.get("is_alternate_repr")]
    assert {c["source_name"] for c in alternate} == {"MM", "DD", "YYYY"}
    assert [c["physical_offset"] for c in alternate] == [0, 3, 6]


def test_odo_and_occurs_redefines_propagate_review_required():
    parser = CopybookParser()
    odo = parser.parse_structure("O.cpy", "01 REC.\n 05 COUNT PIC 9.\n 05 ITEM PIC X(3) OCCURS 1 TO 5 TIMES DEPENDING ON COUNT.")
    table = SchemaGenerator().generate(_knowledge("O", odo))["tables"][0]
    assert table["review_warnings"] and not any(c.get("source_name") == "ITEM" for c in table["columns"])


def test_real_carddemo_copybooks_use_the_same_resolved_pipeline():
    root = Path("data/carddemo_samples")
    for name in ("COCOM01Y", "CODATECN", "CVEXPORT", "CVCRD01Y", "COMEN02Y"):
        source = root / f"{name}.cpy"
        fields = CopybookParser().parse_structure(str(source), source.read_text())
        schema = SchemaGenerator().generate(_knowledge(name, fields))
        assert schema["resolved_schema_version"] == "2.0.0"
        assert schema["generator"] == "SchemaGenerator"
        assert all("FILLER" not in column.get("source_name", "") for table in schema["tables"] for column in table["columns"])
