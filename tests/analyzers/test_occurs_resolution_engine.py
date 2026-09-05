from src.analyzers.occurs_resolution_engine import OccursResolutionEngine

def test_simple_fixed_occurs_inline_array():
    node = {
        "name": "PHONE",
        "pic": "X(10)",
        "occurs": 3
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "INLINE_ARRAY"
    assert res["occurs_type"] == "FIXED"
    assert res["min_occurs"] == 3
    assert res["max_occurs"] == 3
    assert res["child_sql_type"] == "VARCHAR(10)[]"
    assert res["is_group"] is False

def test_simple_fixed_occurs_child_table():
    node = {
        "name": "HISTORY",
        "pic": "X(10)",
        "occurs": 25  # > 20 threshold
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "CHILD_TABLE"
    assert res["occurs_type"] == "FIXED"
    assert res["min_occurs"] == 25
    assert res["max_occurs"] == 25
    assert res["child_sql_type"] == "VARCHAR(10)"

def test_group_occurs():
    node = {
        "name": "ADDRESS",
        "occurs": 3,
        "children": [
            {"name": "STREET", "pic": "X(30)"},
            {"name": "CITY", "pic": "X(20)"}
        ]
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "CHILD_TABLE"
    assert res["is_group"] is True
    assert res["occurs_type"] == "FIXED"
    assert res["max_occurs"] == 3

def test_nested_occurs():
    node = {
        "name": "ORDER",
        "occurs": 10,
        "children": [
            {
                "name": "ITEM",
                "occurs": 5,
                "pic": "X(10)"
            }
        ]
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "REVIEW_REQUIRED"
    assert res["nesting_level"] == 1
    assert res["reason"].startswith("Nested OCCURS detected")

def test_occurs_depending_on():
    node = {
        "name": "ITEMS",
        "occurs": "1 TO 10 TIMES DEPENDING ON ITEM-COUNT",
        "pic": "X(10)"
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "REVIEW_REQUIRED"
    assert res["is_variable_length"] is True
    assert res["occurs_type"] == "VARIABLE"
    assert res["min_occurs"] == 1
    assert res["max_occurs"] == 10

def test_occurs_with_redefines():
    node = {
        "name": "REPEATED-FIELD",
        "occurs": 5,
        "pic": "X(10)",
        "redefines": "OTHER-FIELD"
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "REVIEW_REQUIRED"
    assert res["has_redefines"] is True

def test_invalid_ambiguous_occurs():
    node = {
        "name": "BAD-OCCURS",
        "occurs": "TIMES",
        "pic": "X(10)"
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "REVIEW_REQUIRED"
    assert res["occurs_type"] == "UNKNOWN"

def test_unsafe_large_occurs():
    node = {
        "name": "HUGE-OCCURS",
        "occurs": 500,
        "pic": "X(10)"
    }
    res = OccursResolutionEngine.resolve(node)
    assert res["strategy"] == "REVIEW_REQUIRED"
    assert "exceeds the safe auto-mapping threshold" in res["reason"]
