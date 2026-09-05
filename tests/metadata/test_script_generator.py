from src.metadata.script_generator import PostgresScriptGenerator

def test_normal_scalar_table():
    columns = [
        {"name": "CUST_ID", "sql_type": "INTEGER", "is_primary": True},
        {"name": "CUST_NAME", "sql_type": "VARCHAR(50)"}
    ]
    ddl = PostgresScriptGenerator.generate_ddl("CUSTOMER", columns, [])
    
    assert 'CREATE TABLE "customer"' in ddl
    assert 'PRIMARY KEY ("cust_id")' in ddl
    assert '"cust_name" VARCHAR(50)' in ddl

def test_reserved_identifier_quoting():
    columns = [
        {"name": "USER", "sql_type": "VARCHAR(20)"},
        {"name": "ORDER", "sql_type": "INTEGER"}
    ]
    ddl = PostgresScriptGenerator.generate_ddl("GROUP", columns, [])
    
    assert 'CREATE TABLE "group"' in ddl
    assert '"user" VARCHAR(20)' in ddl
    assert '"order" INTEGER' in ddl

def test_redefines_exclusion():
    columns = [
        {"name": "ID", "sql_type": "INTEGER"},
        {"name": "VAR1", "sql_type": "VARCHAR(10)", "is_excluded": True},
        {"name": "VAR2", "sql_type": "VARCHAR(10)"}
    ]
    ddl = PostgresScriptGenerator.generate_ddl("TEST_TABLE", columns, [])
    
    assert '"var1"' not in ddl
    assert '"var2"' in ddl

def test_birthdate_alternate_representation():
    columns = [
        {"name": "ID", "sql_type": "INTEGER"},
        {"name": "BIRTHDATE", "sql_type": "VARCHAR(8)"},
        {"name": "B-M", "sql_type": "VARCHAR(2)", "is_excluded": False, "is_alternate_repr": True},
        {"name": "B-D", "sql_type": "VARCHAR(2)", "is_excluded": False, "is_alternate_repr": True},
        {"name": "B-Y", "sql_type": "VARCHAR(4)", "is_excluded": False, "is_alternate_repr": True},
        {"name": "FILLER", "sql_type": "TEXT", "is_excluded": True},
        {"name": "BIRTHDATE-DETAILS", "sql_type": "TEXT", "is_excluded": True}
    ]
    ddl = PostgresScriptGenerator.generate_ddl("PERSON", columns, [])
    
    assert '"birthdate" VARCHAR(8)' in ddl
    assert '"b_m" VARCHAR(2)' in ddl
    assert '"b_d" VARCHAR(2)' in ddl
    assert '"b_y" VARCHAR(4)' in ddl
    assert '"filler"' not in ddl
    assert '"birthdate_details"' not in ddl

def test_inline_array():
    columns = [
        {"name": "ID", "sql_type": "INTEGER"},
        {"name": "PHONE", "sql_type": "VARCHAR(10)[]"}
    ]
    ddl = PostgresScriptGenerator.generate_ddl("CONTACT", columns, [])
    
    assert '"phone" VARCHAR(10)[]' in ddl
    assert 'phone_1' not in ddl

def test_child_table_and_foreign_keys():
    columns = [
        {"name": "CUST_ID", "sql_type": "INTEGER", "is_primary": True}
    ]
    child_tables = [
        {
            "name": "ADDRESS",
            "columns": [
                {"name": "STREET", "sql_type": "VARCHAR(30)"},
                {"name": "CITY", "sql_type": "VARCHAR(20)"}
            ]
        }
    ]
    ddl = PostgresScriptGenerator.generate_ddl("CUSTOMER", columns, child_tables)
    
    # Parent table
    assert 'CREATE TABLE "customer" (' in ddl
    assert 'PRIMARY KEY ("cust_id")' in ddl
    
    # Child table
    assert 'CREATE TABLE "customer_address" (' in ddl
    assert '"parent_cust_id" INTEGER NOT NULL' in ddl
    assert '"occurrence_index" INTEGER NOT NULL' in ddl
    assert '"street" VARCHAR(30)' in ddl
    assert '"city" VARCHAR(20)' in ddl
    
    # Constraints
    assert 'PRIMARY KEY ("parent_cust_id", "occurrence_index")' in ddl
    assert 'FOREIGN KEY ("parent_cust_id") REFERENCES "customer" ("cust_id")' in ddl
    
    # Ordering
    parent_pos = ddl.find('CREATE TABLE "customer"')
    child_pos = ddl.find('CREATE TABLE "customer_address"')
    assert parent_pos < child_pos

def test_review_required_fields_handled_safely():
    # If the engine marked something REVIEW_REQUIRED, it either excluded it or just provided standard mapping.
    # Script gen shouldn't fail or invent logic.
    columns = [
        {"name": "ID", "sql_type": "INTEGER"},
        {"name": "DYN_ARR", "sql_type": "TEXT"}
    ]
    ddl = PostgresScriptGenerator.generate_ddl("TEST", columns, [])
    assert '"dyn_arr" TEXT' in ddl
