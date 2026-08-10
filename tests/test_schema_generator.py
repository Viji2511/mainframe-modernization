import pytest
from api.repository_api import _generate_schema_from_structure, _parse_pic_to_sql, _calculate_pic_length

def test_parse_pic_to_sql():
    assert _parse_pic_to_sql("X(10)") == "VARCHAR(10)"
    assert _parse_pic_to_sql("A(5)") == "VARCHAR(5)"
    assert _parse_pic_to_sql("9(4)") == "SMALLINT"
    assert _parse_pic_to_sql("9(9)") == "INTEGER"
    assert _parse_pic_to_sql("9(10)") == "BIGINT"
    assert _parse_pic_to_sql("9(5)V9(2)") == "DECIMAL(7, 2)"
    assert _parse_pic_to_sql("COMP-3") == "SMALLINT"  # default l=4

def test_calculate_pic_length():
    assert _calculate_pic_length("X(10)") == 10
    assert _calculate_pic_length("9(4)") == 4
    assert _calculate_pic_length("9(5)V9(2)") == 7
    assert _calculate_pic_length("9(7) COMP-3") == 4
    assert _calculate_pic_length("9(9) COMP") == 4
    assert _calculate_pic_length("9(10) BINARY") == 8

def test_generate_schema_from_structure():
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
                        "pic": "9(9)"
                    },
                    {
                        "level": 5,
                        "name": "CUST-NAME",
                        "pic": "X(50)"
                    },
                    {
                        "level": 5,
                        "name": "CUST-FILLER",
                        "pic": "X(10)",
                        "redefines": "CUST-NAME"
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
                                "pic": "9(4)"
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    datasets = [
        {"dataset_name": "CUST.KSDS", "key_offset": 0, "key_length": 9}
    ]
    
    schema1 = _generate_schema_from_structure("CUST", struct1, datasets)
    
    assert schema1["table_name"] == "CUST"
    cols = schema1["columns"]
    
    assert cols[0]["name"] == "CUSTOMER_REC_CUST_ID"
    assert cols[0]["sql_type"] == "INTEGER"
    assert cols[0]["offset"] == 0
    assert cols[0]["length"] == 9
    assert cols[0]["primary_key"] is True
    assert cols[0]["key_evidence"]["source_dataset"] == "CUST.KSDS"
    
    assert cols[1]["name"] == "CUSTOMER_REC_CUST_NAME"
    assert cols[1]["sql_type"] == "VARCHAR(50)"
    assert cols[1]["offset"] == 9
    assert cols[1]["length"] == 50
    assert cols[1]["primary_key"] is False
    
    assert cols[2]["name"] == "CUSTOMER_REC_CUST_FILLER"
    assert cols[2]["redefines_target"] == "CUST-NAME"
    assert cols[2]["schema_status"] == "REVIEW_REQUIRED: REDEFINES"
    
    assert cols[3]["name"] == "CUSTOMER_REC_ORDER_LINES_ORDER_ID"
    assert cols[3]["occurs"] == 10
    assert cols[3]["schema_status"] == "TRANSFORMATION_REQUIRED: OCCURS"

