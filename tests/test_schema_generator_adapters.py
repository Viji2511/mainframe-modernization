import pytest
from api.repository_api import _generate_cobol_schema, _generate_jcl_schema, _generate_idcams_schema, _generate_dataset_schema

def test_cobol_schema():
    struct = {
        "structure": {
            "data_structures": ["TRANSACTION-RECORD"]
        },
        "semantic_structure": {
            "program": {
                "execution_flow": ["OPEN", "READ"]
            }
        },
        "components": {
            "files": {
                "read": ["CUSTOMER.KSDS"]
            }
        }
    }
    deps = {
        "datasets": ["CUSTOMER.KSDS", "TRANSACTION.KSDS"],
        "copybooks": ["COTTL01Y"],
        "calledPrograms": ["CUST01C"]
    }
    schema = _generate_cobol_schema("COTRN02C", struct, deps)
    assert schema["schema_type"] == "PROGRAM_SCHEMA"
    assert schema["program_name"] == "COTRN02C"
    assert schema["data_structures"] == ["TRANSACTION-RECORD"]
    assert "CUSTOMER.KSDS" in schema["datasets"]
    assert "COTTL01Y" in schema["copybooks"]
    assert "CUST01C" in schema["called_programs"]
    assert "OPEN" in schema["operations"]
    assert "CUSTOMER.KSDS" in schema["files"]["read"]

def test_jcl_schema():
    struct = {
        "semantic_structure": {
            "workflow": {
                "job": {
                    "job_name": "DBPAUTP0",
                    "job_card": {"class": "A"}
                },
                "steps": [
                    {
                        "step_name": "STEP01",
                        "exec": [{"program": "DBPAUTP0"}],
                        "dd": [{"dd_name": "INPUT", "dataset": "CUSTOMER.KSDS", "disp": "SHR"}]
                    }
                ]
            }
        }
    }
    schema = _generate_jcl_schema("DBPAUTP0", struct)
    assert schema["schema_type"] == "JOB_SCHEMA"
    assert schema["job_name"] == "DBPAUTP0"
    assert schema["job_card"]["class"] == "A"
    assert schema["steps"][0]["step_name"] == "STEP01"
    assert schema["steps"][0]["exec"][0]["program"] == "DBPAUTP0"
    assert schema["steps"][0]["dd"][0]["dataset"] == "CUSTOMER.KSDS"
    assert schema["steps"][0]["dd"][0]["disp"] == "SHR"

def test_idcams_schema():
    struct = {
        "dataset_name": "CUSTOMER.KSDS",
        "organization": "KSDS",
        "key_length": 9,
        "key_offset": 0,
        "record_length": 150
    }
    schema = _generate_idcams_schema("IDCAMS01", struct)
    assert schema["schema_type"] == "DATASET_SCHEMA"
    assert schema["dataset_name"] == "CUSTOMER.KSDS"
    assert schema["organization"] == "KSDS"
    assert schema["key_length"] == 9
    assert schema["key_offset"] == 0
    assert schema["record_length"] == 150

def test_dataset_schema():
    struct = {
        "dataset_name": "CUSTOMER.VSAM",
        "organization": "ESDS",
        "key_length": None,
        "key_offset": None,
        "record_length": 200
    }
    schema = _generate_dataset_schema("CUSTOMER.VSAM", struct)
    assert schema["schema_type"] == "DATASET_SCHEMA"
    assert schema["dataset_name"] == "CUSTOMER.VSAM"
    assert schema["organization"] == "ESDS"
    assert schema["key_length"] is None
    assert schema["record_length"] == 200
