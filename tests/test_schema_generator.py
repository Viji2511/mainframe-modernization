"""Integration tests for the API-layer schema generator.

Tests cover _parse_pic_to_sql, _calculate_pic_length, and
_generate_schema_from_structure, including REDEFINES handling.
"""
import pytest
from api.repository_api import (
    _generate_schema_from_structure,
    _parse_pic_to_sql,
    _calculate_pic_length,
)


# ---------------------------------------------------------------------------
# _parse_pic_to_sql — thin adapter over PostgresMapper
# ---------------------------------------------------------------------------

def test_parse_pic_to_sql():
    assert _parse_pic_to_sql("X(10)") == "VARCHAR(10)"
    assert _parse_pic_to_sql("A(5)") == "VARCHAR(5)"
    assert _parse_pic_to_sql("9(4)") == "SMALLINT"
    assert _parse_pic_to_sql("9(9)") == "INTEGER"
    assert _parse_pic_to_sql("9(10)") == "BIGINT"
    assert _parse_pic_to_sql("9(5)V9(2)") == "NUMERIC(7, 2)"
    # COMP-3 with no explicit digit count: PostgresMapper defaults l=4
    # → NUMERIC(4, 0)  (packed-decimal representation)
    assert _parse_pic_to_sql("COMP-3") == "NUMERIC(4, 0)"


# ---------------------------------------------------------------------------
# _calculate_pic_length
# ---------------------------------------------------------------------------

def test_calculate_pic_length():
    assert _calculate_pic_length("X(10)") == 10
    assert _calculate_pic_length("9(4)") == 4
    assert _calculate_pic_length("9(5)V9(2)") == 7
    assert _calculate_pic_length("9(7) COMP-3") == 4
    assert _calculate_pic_length("9(9) COMP") == 4
    assert _calculate_pic_length("9(10) BINARY") == 8


# ---------------------------------------------------------------------------
# _generate_schema_from_structure — baseline REDEFINES + OCCURS
# ---------------------------------------------------------------------------

def test_generate_schema_from_structure():
    """Baseline test: simple scalar REDEFINES and OCCURS handling.

    CUST-FILLER REDEFINES CUST-NAME is a scalar-vs-scalar case (both have
    field_count <= 1).  RedefinesResolutionEngine resolves it as SAME_TABLE.
    The schema_status therefore reads "REVIEW_REQUIRED: REDEFINES (SAME_TABLE)".
    """
    struct1 = {
        "artifact_type": "COPYBOOK",
        "records": [
            {
                "level": 1,
                "name": "CUSTOMER-REC",
                "pic": "GROUP",
                "children": [
                    {
                        "level": 5,
                        "name": "CUST-ID",
                        "pic": "9(9)",
                    },
                    {
                        "level": 5,
                        "name": "CUST-NAME",
                        "pic": "X(50)",
                    },
                    {
                        "level": 5,
                        "name": "CUST-FILLER",
                        "pic": "X(10)",
                        "redefines": "CUST-NAME",
                    },
                    {
                        "level": 5,
                        "name": "ORDER-LINES",
                        "pic": "GROUP",
                        "occurs": 10,
                        "children": [
                            {
                                "level": 10,
                                "name": "ORDER-ID",
                                "pic": "9(4)",
                            }
                        ],
                    },
                ],
            }
        ],
    }

    datasets = [{"dataset_name": "CUST.KSDS", "key_offset": 0, "key_length": 9}]

    schema1 = _generate_schema_from_structure("CUST", struct1, datasets)

    assert schema1["table_name"] == "CUST"
    cols = schema1["columns"]

    # --- CUST-ID ---
    assert cols[0]["name"] == "CUSTOMER_REC_CUST_ID"
    assert cols[0]["sql_type"] == "INTEGER"
    assert cols[0]["offset"] == 0
    assert cols[0]["length"] == 9
    assert cols[0]["primary_key"] is True
    assert cols[0]["key_evidence"]["source_dataset"] == "CUST.KSDS"

    # --- CUST-NAME ---
    assert cols[1]["name"] == "CUSTOMER_REC_CUST_NAME"
    assert cols[1]["sql_type"] == "VARCHAR(50)"
    assert cols[1]["offset"] == 9
    assert cols[1]["length"] == 50
    assert cols[1]["primary_key"] is False

    # --- CUST-FILLER (simple scalar REDEFINES → SAME_TABLE strategy) ---
    assert cols[2]["name"] == "CUSTOMER_REC_CUST_FILLER"
    assert cols[2]["redefines_target"] == "CUST-NAME"
    # Strategy suffix is included from the current _flatten_records implementation
    assert cols[2]["schema_status"] == "REVIEW_REQUIRED: REDEFINES (SAME_TABLE)"
    assert cols[2].get("is_excluded") is True

    # --- ORDER-LINES / ORDER-ID (OCCURS) ---
    assert cols[3]["name"] == "CUSTOMER_REC_ORDER_LINES_ORDER_ID"
    assert cols[3]["occurs"] == 10
    assert cols[3]["schema_status"] == "TRANSFORMATION_REQUIRED: OCCURS"


# ---------------------------------------------------------------------------
# Integration: BIRTHDATE → B-M / B-D / B-Y  (alternate representation)
# ---------------------------------------------------------------------------

# COBOL source being modelled:
#
#   01 EMPLOYEE-REC.
#      05 EMP-ID              PIC 9(9).
#      05 BIRTHDATE           PIC X(10).
#      05 BIRTHDATE-DETAILS   REDEFINES BIRTHDATE.
#         10 B-M              PIC X(2).
#         10 FILLER           PIC X(1).
#         10 B-D              PIC X(2).
#         10 FILLER           PIC X(1).
#         10 B-Y              PIC X(4).

_BIRTHDATE_STRUCT = {
    "records": [
        {
            "level": 1, "name": "EMPLOYEE-REC", "pic": "GROUP",
            "children": [
                {"level": 5, "name": "EMP-ID",   "pic": "9(9)", "length": 9},
                {"level": 5, "name": "BIRTHDATE", "pic": "X(10)", "length": 10},
                {
                    "level": 5, "name": "BIRTHDATE-DETAILS",
                    "redefines": "BIRTHDATE", "length": 10,
                    "children": [
                        {"level": 10, "name": "B-M",    "pic": "X(2)", "length": 2},
                        {"level": 10, "name": "FILLER", "pic": "X(1)", "length": 1},
                        {"level": 10, "name": "B-D",    "pic": "X(2)", "length": 2},
                        {"level": 10, "name": "FILLER", "pic": "X(1)", "length": 1},
                        {"level": 10, "name": "B-Y",    "pic": "X(4)", "length": 4},
                    ],
                },
            ],
        }
    ]
}


def _birthdate_schema():
    return _generate_schema_from_structure("EMPLOYEE", _BIRTHDATE_STRUCT)


def test_birthdate_redefines_detected():
    """The pipeline must detect the REDEFINES relationship."""
    schema = _birthdate_schema()
    # BIRTHDATE-DETAILS children will be present with redefines_target set
    all_names = {c["name"] for c in schema["columns"]}
    # At minimum the canonical BIRTHDATE column must exist
    assert "EMPLOYEE_REC_BIRTHDATE" in all_names


def test_birthdate_no_duplicate_table():
    """BIRTHDATE-DETAILS must NOT produce a duplicate non-excluded group column.

    The group node itself is excluded (is_excluded=True).  No standalone
    BIRTHDATE_DETAILS column should exist as an active (non-excluded) column.
    """
    schema = _birthdate_schema()
    active = [c for c in schema["columns"] if not c.get("is_excluded")]
    active_names = {c["name"] for c in active}
    assert "EMPLOYEE_REC_BIRTHDATE_DETAILS" not in active_names, (
        "BIRTHDATE-DETAILS group must not appear as an active column"
    )


def test_birthdate_canonical_field_intact():
    """The original BIRTHDATE column must be present, active, and unmodified."""
    schema = _birthdate_schema()
    bd = next(
        (c for c in schema["columns"] if c["name"] == "EMPLOYEE_REC_BIRTHDATE"),
        None,
    )
    assert bd is not None, "BIRTHDATE column missing"
    assert not bd.get("is_excluded"), "BIRTHDATE must not be excluded"
    assert bd["offset"] == 9
    assert bd["length"] == 10
    assert bd["sql_type"] == "VARCHAR(10)"


def test_birthdate_safe_children_not_silently_discarded():
    """B-M, B-D, and B-Y must appear as active alternate-representation columns."""
    schema = _birthdate_schema()
    alt_cols = {c["name"] for c in schema["columns"] if c.get("is_alternate_repr")}
    assert "EMPLOYEE_REC_B_M" in alt_cols, f"B-M missing; alt_cols={alt_cols}"
    assert "EMPLOYEE_REC_B_D" in alt_cols, f"B-D missing; alt_cols={alt_cols}"
    assert "EMPLOYEE_REC_B_Y" in alt_cols, f"B-Y missing; alt_cols={alt_cols}"


def test_birthdate_filler_not_emitted():
    """FILLER nodes must not appear as active columns."""
    schema = _birthdate_schema()
    active = [c for c in schema["columns"] if not c.get("is_excluded")]
    for c in active:
        assert "FILLER" not in c["name"].upper(), (
            f"FILLER leaked into active columns: {c['name']}"
        )


def test_birthdate_child_offsets_share_original_storage():
    """B-M, B-D, B-Y offsets must be anchored to BIRTHDATE's start (byte 9).

    Physical layout inside the 10-byte BIRTHDATE storage:
      B-M   bytes 0-1  → absolute offset  9
      FILLER byte  2   → (omitted from output)
      B-D   bytes 3-4  → absolute offset 12
      FILLER byte  5   → (omitted from output)
      B-Y   bytes 6-9  → absolute offset 15
    """
    schema = _birthdate_schema()
    by_name = {c["name"]: c for c in schema["columns"] if c.get("is_alternate_repr")}
    assert by_name["EMPLOYEE_REC_B_M"]["offset"] == 9,  f"B-M offset wrong: {by_name['EMPLOYEE_REC_B_M']['offset']}"
    assert by_name["EMPLOYEE_REC_B_D"]["offset"] == 12, f"B-D offset wrong: {by_name['EMPLOYEE_REC_B_D']['offset']}"
    assert by_name["EMPLOYEE_REC_B_Y"]["offset"] == 15, f"B-Y offset wrong: {by_name['EMPLOYEE_REC_B_Y']['offset']}"


def test_birthdate_child_lengths():
    """Each safe child must have the correct byte length."""
    schema = _birthdate_schema()
    by_name = {c["name"]: c for c in schema["columns"] if c.get("is_alternate_repr")}
    assert by_name["EMPLOYEE_REC_B_M"]["length"] == 2
    assert by_name["EMPLOYEE_REC_B_D"]["length"] == 2
    assert by_name["EMPLOYEE_REC_B_Y"]["length"] == 4


def test_birthdate_child_schema_status():
    """Alternate-representation columns must carry the correct schema_status."""
    schema = _birthdate_schema()
    for c in schema["columns"]:
        if c.get("is_alternate_repr"):
            assert c["schema_status"] == "ALTERNATE_REPRESENTATION: BIRTHDATE", (
                f"Unexpected schema_status on {c['name']}: {c['schema_status']}"
            )


def test_birthdate_child_redefines_target():
    """Each safe child must point back to the canonical BIRTHDATE field."""
    schema = _birthdate_schema()
    for c in schema["columns"]:
        if c.get("is_alternate_repr"):
            assert c["redefines_target"] == "BIRTHDATE", (
                f"{c['name']} has wrong redefines_target: {c['redefines_target']}"
            )


def test_birthdate_redefines_handled_count():
    """The validation summary must count excluded REDEFINES entries correctly."""
    schema = _birthdate_schema()
    # 3 INHERITED children of BIRTHDATE-DETAILS are truly excluded
    assert schema["validation_summary"]["redefines_handled"] == 3


def test_birthdate_alternate_repr_count():
    """The validation summary must count alternate_repr_fields correctly."""
    schema = _birthdate_schema()
    assert schema["validation_summary"]["alternate_repr_fields"] == 3


def test_birthdate_resolution_metadata_in_column():
    """Each alternate-repr column must carry the alternate_group annotation."""
    schema = _birthdate_schema()
    for c in schema["columns"]:
        if c.get("is_alternate_repr"):
            assert c.get("alternate_group") == "BIRTHDATE-DETAILS", (
                f"{c['name']} missing or wrong alternate_group"
            )


# ---------------------------------------------------------------------------
# Integration: CTRTUPAI / CTRTUPAO  (large record-level REDEFINES regression)
# ---------------------------------------------------------------------------

def _make_ctrt_child_list(name, n, flen):
    return [
        {"level": 5, "name": f"{name}-F{i:02d}", "pic": f"X({flen})", "length": flen}
        for i in range(n)
    ]


_CTRT_STRUCT = {
    "records": [
        {
            "level": 1, "name": "CTRTUPAI", "length": 100,
            "children": _make_ctrt_child_list("CTRTUPAI", 10, 10),
        },
        {
            "level": 1, "name": "CTRTUPAO", "redefines": "CTRTUPAI", "length": 100,
            "children": _make_ctrt_child_list("CTRTUPAO", 10, 10),
        },
    ]
}


def _ctrt_schema():
    return _generate_schema_from_structure("CTRTUP", _CTRT_STRUCT)


def test_ctrtupai_all_columns_present():
    """All 10 CTRTUPAI columns must be active (not excluded)."""
    schema = _ctrt_schema()
    active = [c for c in schema["columns"] if not c.get("is_excluded") and not c.get("is_alternate_repr")]
    ctrtupai_active = [c for c in active if "CTRTUPAI" in c["name"]]
    assert len(ctrtupai_active) == 10, (
        f"Expected 10 active CTRTUPAI columns, got {len(ctrtupai_active)}"
    )


def test_ctrtupao_columns_all_excluded():
    """All CTRTUPAO columns must be excluded — SEPARATE_TABLES strategy."""
    schema = _ctrt_schema()
    ctrtupao_cols = [c for c in schema["columns"] if "CTRTUPAO" in c["name"]]
    assert len(ctrtupao_cols) == 10, f"Expected 10 CTRTUPAO cols, got {len(ctrtupao_cols)}"
    for c in ctrtupao_cols:
        assert c.get("is_excluded"), f"{c['name']} should be excluded"


def test_ctrtupao_no_alternate_repr_columns():
    """SEPARATE_TABLES must not emit any is_alternate_repr columns."""
    schema = _ctrt_schema()
    alt_cols = [c for c in schema["columns"] if c.get("is_alternate_repr")]
    assert alt_cols == [], (
        f"CTRTUPAO must not produce alternate_repr columns: {[c['name'] for c in alt_cols]}"
    )


def test_ctrtupao_redefines_handled_count():
    """All 10 CTRTUPAO columns must be counted in redefines_handled."""
    schema = _ctrt_schema()
    assert schema["validation_summary"]["redefines_handled"] == 10


def test_ctrtupao_alternate_repr_count_zero():
    """alternate_repr_fields must be 0 for the CTRTUPAI/CTRTUPAO case."""
    schema = _ctrt_schema()
    assert schema["validation_summary"]["alternate_repr_fields"] == 0


def test_ctrtupao_no_duplicate_ctrtupai_table():
    """CTRTUPAO must not produce any active non-CTRTUPAI active columns — no dup table."""
    schema = _ctrt_schema()
    active = [c for c in schema["columns"] if not c.get("is_excluded")]
    for c in active:
        assert "CTRTUPAO" not in c["name"], (
            f"CTRTUPAO column leaked into active columns: {c['name']}"
        )
