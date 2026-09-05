import pytest
from src.validators.postgres_mapper import PostgresMapper

def test_map_pic_to_postgres_string():
    assert PostgresMapper.map_pic_to_postgres("X(10)", "name")[:2] == ("VARCHAR(10)", "String")
    assert PostgresMapper.map_pic_to_postgres("A(5)", "alpha")[:2] == ("VARCHAR(5)", "String")
    assert PostgresMapper.map_pic_to_postgres("XXX", "foo")[:2] == ("VARCHAR(3)", "String")

def test_map_pic_to_postgres_numeric():
    assert PostgresMapper.map_pic_to_postgres("9(4)", "num")[:2] == ("SMALLINT", "Integer")
    assert PostgresMapper.map_pic_to_postgres("9(8)", "num")[:2] == ("INTEGER", "Integer")
    assert PostgresMapper.map_pic_to_postgres("9(12)", "num")[:2] == ("BIGINT", "Integer")
    assert PostgresMapper.map_pic_to_postgres("9(4)V9(2)", "num")[:2] == ("NUMERIC(6, 2)", "Decimal")

def test_map_pic_to_postgres_signed():
    assert PostgresMapper.map_pic_to_postgres("S9(4)", "num")[:2] == ("SMALLINT", "Integer")

def test_map_pic_to_postgres_comp():
    assert PostgresMapper.map_pic_to_postgres("9(4) COMP", "num")[:2] == ("SMALLINT", "Integer")
    assert PostgresMapper.map_pic_to_postgres("COMP-1", "num")[:2] == ("REAL", "Float")
    assert PostgresMapper.map_pic_to_postgres("COMP-2", "num")[:2] == ("DOUBLE PRECISION", "Double")
    assert PostgresMapper.map_pic_to_postgres("9(5) COMP-3", "num")[:2] == ("NUMERIC(5, 0)", "Packed Decimal")

def test_map_pic_to_postgres_date_heuristics():
    # Should infer date
    assert PostgresMapper.map_pic_to_postgres("9(8)", "BIRTH-DATE")[1] == "Date"
    assert PostgresMapper.map_pic_to_postgres("9(8)", "START_DT")[1] == "Date"
    
    # Should not infer date
    assert PostgresMapper.map_pic_to_postgres("9(8)", "ACCOUNT_NUM")[1] == "Integer"
    
def test_validate_postgres_type():
    assert PostgresMapper.validate_postgres_type("VARCHAR(100)") is True
    assert PostgresMapper.validate_postgres_type("NUMERIC(10, 2)") is True
    assert PostgresMapper.validate_postgres_type("INTEGER") is True
    
    # Invalid length/precision
    assert PostgresMapper.validate_postgres_type("VARCHAR(20000000)") is False
    assert PostgresMapper.validate_postgres_type("NUMERIC(1500, 2)") is False
    assert PostgresMapper.validate_postgres_type("NUMERIC(10, 20)") is False
    
    # Unknown type
    assert PostgresMapper.validate_postgres_type("INVALID_TYPE") is False
