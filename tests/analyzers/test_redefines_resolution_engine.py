import pytest
from src.analyzers.redefines_resolution_engine import RedefinesResolutionEngine

def test_simple_scalar_redefines():
    orig = {"name": "FIELD-A", "pic": "X(10)", "length": 10, "children": []}
    alt = {"name": "FIELD-B", "pic": "9(10)", "length": 10, "children": [], "redefines": "FIELD-A"}
    
    result = RedefinesResolutionEngine.resolve(orig, alt)
    assert result["strategy"] == "SAME_TABLE"
    assert result["confidence"] == "HIGH"
    assert result["storage_overlap"] is True

def test_complex_redefines_separate_tables():
    orig = {
        "name": "BASE-RECORD", "length": 100,
        "children": [{"name": f"F{i}", "pic": "X(10)", "length": 10} for i in range(10)]
    }
    alt = {
        "name": "ALT-RECORD", "length": 100, "redefines": "BASE-RECORD",
        "children": [{"name": f"A{i}", "pic": "9(10)", "length": 10} for i in range(10)]
    }
    
    result = RedefinesResolutionEngine.resolve(orig, alt)
    assert result["strategy"] == "SEPARATE_TABLES"
    assert result["confidence"] == "MEDIUM"

def test_redefines_with_occurs():
    orig = {"name": "FIELD-A", "pic": "X(100)", "length": 100}
    alt = {
        "name": "FIELD-B", "length": 100, "redefines": "FIELD-A", "occurs": "10 TIMES",
        "children": [{"name": "SUB-FIELD", "pic": "X(10)", "length": 10}]
    }
    
    result = RedefinesResolutionEngine.resolve(orig, alt)
    assert result["strategy"] == "SEPARATE_TABLES"
    assert result["confidence"] == "MEDIUM"

def test_nested_redefines_review_required():
    orig = {"name": "FIELD-A", "length": 20}
    alt = {
        "name": "FIELD-B", "length": 20, "redefines": "FIELD-A",
        "children": [
            {"name": "SUB-1", "pic": "X(10)", "length": 10},
            {"name": "SUB-2", "pic": "9(10)", "length": 10, "redefines": "SUB-1"}
        ]
    }
    
    result = RedefinesResolutionEngine.resolve(orig, alt)
    assert result["strategy"] == "REVIEW_REQUIRED"
    assert result["confidence"] == "LOW"

def test_missing_data():
    result = RedefinesResolutionEngine.resolve(None, None)
    assert result["strategy"] == "REVIEW_REQUIRED"
    assert result["confidence"] == "LOW"


# ---------------------------------------------------------------------------
# BIRTHDATE → B-M / B-D / B-Y  (alternate representation)
# ---------------------------------------------------------------------------

# COBOL source being modelled:
#
#   01 BIRTHDATE              PIC X(10).
#   01 BIRTHDATE-DETAILS      REDEFINES BIRTHDATE.
#      05 B-M                 PIC X(2).
#      05 FILLER              PIC X(1).
#      05 B-D                 PIC X(2).
#      05 FILLER              PIC X(1).
#      05 B-Y                 PIC X(4).

_BIRTHDATE_ORIG = {
    "name": "BIRTHDATE",
    "pic": "X(10)",
    "length": 10,
    "children": [],
}

_BIRTHDATE_ALT = {
    "name": "BIRTHDATE-DETAILS",
    "redefines": "BIRTHDATE",
    "length": 10,
    "children": [
        {"name": "B-M",    "pic": "X(2)", "length": 2},
        {"name": "FILLER", "pic": "X(1)", "length": 1},
        {"name": "B-D",    "pic": "X(2)", "length": 2},
        {"name": "FILLER", "pic": "X(1)", "length": 1},
        {"name": "B-Y",    "pic": "X(4)", "length": 4},
    ],
}


def test_birthdate_redefines_strategy_is_alternate_representation():
    """BIRTHDATE-DETAILS REDEFINES BIRTHDATE must resolve as ALTERNATE_REPRESENTATION."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    assert result["strategy"] == "ALTERNATE_REPRESENTATION", (
        f"Expected ALTERNATE_REPRESENTATION, got {result['strategy']}: {result['reason']}"
    )


def test_birthdate_redefines_storage_overlap_recognised():
    """Both BIRTHDATE (10) and BIRTHDATE-DETAILS (10) occupy the same storage."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    assert result["storage_overlap"] is True


def test_birthdate_redefines_no_duplicate_table():
    """ALTERNATE_REPRESENTATION must NOT be SEPARATE_TABLES — no second table created."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    assert result["strategy"] != "SEPARATE_TABLES"


def test_birthdate_redefines_meaningful_children_not_discarded():
    """safe_children must contain B-M, B-D, and B-Y (FILLER nodes excluded)."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    safe_names = {c["name"] for c in result["safe_children"]}
    assert "B-M" in safe_names, f"B-M missing from safe_children: {safe_names}"
    assert "B-D" in safe_names, f"B-D missing from safe_children: {safe_names}"
    assert "B-Y" in safe_names, f"B-Y missing from safe_children: {safe_names}"
    # FILLER must not appear
    assert "FILLER" not in safe_names, "FILLER should be excluded from safe_children"


def test_birthdate_redefines_child_lengths():
    """Each safe child carries the correct byte length derived from its PIC."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    by_name = {c["name"]: c for c in result["safe_children"]}
    assert by_name["B-M"]["_byte_length"] == 2
    assert by_name["B-D"]["_byte_length"] == 2
    assert by_name["B-Y"]["_byte_length"] == 4


def test_birthdate_redefines_child_offsets():
    """Child byte offsets relative to BIRTHDATE-DETAILS start must be correct.

    Layout inside the 10-byte field:
      B-M   [0..1]   offset 0
      FILLER[2]      offset 2  (not in safe_children)
      B-D   [3..4]   offset 3
      FILLER[5]      offset 5  (not in safe_children)
      B-Y   [6..9]   offset 6
    """
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    by_name = {c["name"]: c for c in result["safe_children"]}
    assert by_name["B-M"]["_byte_offset"] == 0
    assert by_name["B-D"]["_byte_offset"] == 3
    assert by_name["B-Y"]["_byte_offset"] == 6


def test_birthdate_redefines_original_field_name_recorded():
    """The result must record the canonical (original) field name."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    assert result["original_field_name"] == "BIRTHDATE"


def test_birthdate_redefines_alternate_representation_flag():
    """alternate_representation boolean must be True for this case."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    assert result["alternate_representation"] is True


def test_birthdate_redefines_confidence():
    """Storage lengths are equal and explicit, so confidence must be HIGH."""
    result = RedefinesResolutionEngine.resolve(_BIRTHDATE_ORIG, _BIRTHDATE_ALT)
    assert result["confidence"] == "HIGH"


# ---------------------------------------------------------------------------
# CTRTUPAI / CTRTUPAO  (large record-level REDEFINES → SEPARATE_TABLES)
# ---------------------------------------------------------------------------

# CTRTUPAI and CTRTUPAO are both large 01-level records (> 5 leaf fields each)
# that share the same physical 100-byte storage.  The engine must continue to
# treat this as SEPARATE_TABLES — the enhancement must not regress this.

def _make_record(name: str, redefines: str | None, n_fields: int, field_len: int) -> dict:
    """Build a synthetic record with n_fields children, total length n*field_len."""
    total = n_fields * field_len
    return {
        "name": name,
        "redefines": redefines,
        "length": total,
        "children": [
            {"name": f"{name}-F{i:02d}", "pic": f"X({field_len})", "length": field_len}
            for i in range(n_fields)
        ],
    }


_CTRTUPAI = _make_record("CTRTUPAI", None,      10, 10)   # original, 100 bytes, 10 leaves
_CTRTUPAO = _make_record("CTRTUPAO", "CTRTUPAI", 10, 10)  # redefining, 100 bytes, 10 leaves


def test_ctrtupao_redefines_ctrtupai_strategy():
    """Large record-level REDEFINES must remain SEPARATE_TABLES."""
    result = RedefinesResolutionEngine.resolve(_CTRTUPAI, _CTRTUPAO)
    assert result["strategy"] == "SEPARATE_TABLES", (
        f"Expected SEPARATE_TABLES for large record REDEFINES, got "
        f"{result['strategy']}: {result['reason']}"
    )


def test_ctrtupao_redefines_ctrtupai_confidence():
    """SEPARATE_TABLES confidence for large records must be MEDIUM."""
    result = RedefinesResolutionEngine.resolve(_CTRTUPAI, _CTRTUPAO)
    assert result["confidence"] == "MEDIUM"


def test_ctrtupao_redefines_ctrtupai_storage_overlap():
    """Both records are 100 bytes — storage_overlap must be True."""
    result = RedefinesResolutionEngine.resolve(_CTRTUPAI, _CTRTUPAO)
    assert result["storage_overlap"] is True


def test_ctrtupao_redefines_no_safe_children_emitted():
    """SEPARATE_TABLES strategy must not emit safe_children (would imply an
    inline alternate representation, which is wrong for distinct layouts)."""
    result = RedefinesResolutionEngine.resolve(_CTRTUPAI, _CTRTUPAO)
    assert result["safe_children"] == []


def test_ctrtupao_redefines_alternate_representation_false():
    """alternate_representation flag must be False for SEPARATE_TABLES."""
    result = RedefinesResolutionEngine.resolve(_CTRTUPAI, _CTRTUPAO)
    assert result["alternate_representation"] is False


# ---------------------------------------------------------------------------
# Additional cases (C–F) specified in the requirements
# ---------------------------------------------------------------------------

# Case C: Nested REDEFINES (already tested above as test_nested_redefines_review_required)

# Case D: REDEFINES involving OCCURS (already tested above as test_redefines_with_occurs)

# Case E: Record/group-level REDEFINES (covered by CTRTUPAI tests above)

# Case F: Alternate representation where safe child extraction yields nothing
#         (all children are FILLER — cannot be safely mapped)

def test_filler_only_alternate_raises_review_required():
    """When the redefining group contains only FILLER children, no safe mapping
    exists.  The engine must return REVIEW_REQUIRED rather than inventing one."""
    orig = {"name": "RAW-BYTES", "pic": "X(6)", "length": 6, "children": []}
    alt = {
        "name": "RAW-DECODED",
        "redefines": "RAW-BYTES",
        "length": 6,
        "children": [
            {"name": "FILLER", "pic": "X(3)", "length": 3},
            {"name": "FILLER", "pic": "X(3)", "length": 3},
        ],
    }
    result = RedefinesResolutionEngine.resolve(orig, alt)
    assert result["strategy"] == "REVIEW_REQUIRED"
    assert result["safe_children"] == []
    assert result["alternate_representation"] is False


# Case A: Simple direct character-map REDEFINES
# (covered by the existing test_simple_scalar_redefines above — preserved)


# Result dict always contains all seven keys regardless of strategy
def test_result_always_has_all_keys():
    """Every resolve() call must return all required keys."""
    required_keys = {
        "strategy", "confidence", "reason", "storage_overlap",
        "alternate_representation", "safe_children", "original_field_name",
    }
    for orig, alt in [
        (_BIRTHDATE_ORIG, _BIRTHDATE_ALT),
        (_CTRTUPAI, _CTRTUPAO),
        (None, None),
        (
            {"name": "F", "pic": "X(10)", "length": 10, "children": []},
            {"name": "G", "pic": "9(10)", "length": 10, "children": [], "redefines": "F"},
        ),
    ]:
        result = RedefinesResolutionEngine.resolve(orig, alt)
        missing = required_keys - set(result.keys())
        assert not missing, f"Missing keys {missing} for orig={orig}, alt={alt}"
