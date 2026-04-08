"""
Unit tests for the MCP server pipeline.

These tests cover:
  - CREATE statement parsing
  - Abstraction mapping construction
  - Abstract schema DDL generation
  - Requirements text abstraction
  - SQL restoration
  - Security: no real names leak through the abstraction layer
"""
import sys
import os

# Add the backend directory to sys.path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from abstractor import abstract_requirements, build_abstract_schema_ddl, build_mapping
from parser import parse_create_statements
from restorer import restore_sql, validate_no_real_names_leaked


# ─────────────────────────── Fixtures ───────────────────────────────────────

SAMPLE_DDL = """
CREATE TABLE users (
  user_id   INT          NOT NULL,
  user_no   VARCHAR(10)  NOT NULL,
  name      VARCHAR(100),
  dept_id   INT,
  PRIMARY KEY (user_id),
  FOREIGN KEY (dept_id) REFERENCES departments(dept_id)
);

CREATE TABLE departments (
  dept_id   INT          NOT NULL,
  dept_name VARCHAR(100) NOT NULL,
  PRIMARY KEY (dept_id)
);
"""

SAMPLE_REQUIREMENTS = """\
ユーザーID
ユーザー番号
部署名
ユーザー番号が1000以下なら「〇」、それ以外なら「×」
"""


@pytest.fixture
def parsed_tables():
    return parse_create_statements(SAMPLE_DDL)


@pytest.fixture
def mapping(parsed_tables):
    return build_mapping(parsed_tables)


# ─────────────────────────── Parser tests ───────────────────────────────────

class TestParser:
    def test_parses_two_tables(self, parsed_tables):
        assert len(parsed_tables) == 2

    def test_first_table_name(self, parsed_tables):
        assert parsed_tables[0].name == "users"

    def test_second_table_name(self, parsed_tables):
        assert parsed_tables[1].name == "departments"

    def test_users_column_count(self, parsed_tables):
        assert len(parsed_tables[0].columns) == 4

    def test_primary_key_detected(self, parsed_tables):
        pk_cols = [c for c in parsed_tables[0].columns if c.is_primary_key]
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "user_id"

    def test_foreign_key_detected(self, parsed_tables):
        fk_cols = [c for c in parsed_tables[0].columns if c.foreign_key_ref]
        assert len(fk_cols) == 1
        assert fk_cols[0].name == "dept_id"
        assert fk_cols[0].foreign_key_ref == "departments.dept_id"

    def test_not_null_columns(self, parsed_tables):
        users = parsed_tables[0]
        not_nullable = [c for c in users.columns if not c.nullable]
        # user_id is PK (not nullable), user_no has NOT NULL
        names = {c.name for c in not_nullable}
        assert "user_id" in names
        assert "user_no" in names

    def test_single_table_parse(self):
        ddl = "CREATE TABLE orders (order_id INT NOT NULL, amount DECIMAL(10,2), PRIMARY KEY (order_id));"
        tables = parse_create_statements(ddl)
        assert len(tables) == 1
        assert tables[0].name == "orders"
        assert len(tables[0].columns) == 2

    def test_decimal_type_parsed(self):
        ddl = "CREATE TABLE t (price DECIMAL(10,2));"
        tables = parse_create_statements(ddl)
        col = tables[0].columns[0]
        assert "DECIMAL" in col.data_type.upper()

    def test_empty_sql_returns_empty_list(self):
        assert parse_create_statements("") == []

    def test_no_create_table_returns_empty(self):
        assert parse_create_statements("SELECT * FROM foo;") == []


# ─────────────────────────── Abstractor tests ───────────────────────────────

class TestAbstractor:
    def test_table_count(self, mapping):
        assert len(mapping.tables) == 2

    def test_abstract_table_names(self, mapping):
        names = {t.abstract_name for t in mapping.tables}
        assert names == {"Table01", "Table02"}

    def test_real_table_names_preserved(self, mapping):
        names = {t.real_name for t in mapping.tables}
        assert names == {"users", "departments"}

    def test_forward_table_map(self, mapping):
        assert mapping.table_real_to_abstract["users"] == "Table01"
        assert mapping.table_real_to_abstract["departments"] == "Table02"

    def test_reverse_table_map(self, mapping):
        assert mapping.table_abstract_to_real["Table01"] == "users"
        assert mapping.table_abstract_to_real["Table02"] == "departments"

    def test_forward_column_map(self, mapping):
        assert mapping.column_real_to_abstract["users.user_id"] == "Table01.Column01"

    def test_reverse_column_map(self, mapping):
        assert mapping.column_abstract_to_real["Table01.Column01"] == "users.user_id"

    def test_fk_ref_abstracted(self, mapping):
        users_table = next(t for t in mapping.tables if t.real_name == "users")
        fk_col = next(c for c in users_table.columns if c.real_name == "dept_id")
        # FK should now reference Table02.Column01
        assert fk_col.foreign_key_ref == "Table02.Column01"


class TestAbstractSchemaDDL:
    def test_no_real_names_in_ddl(self, mapping):
        ddl = build_abstract_schema_ddl(mapping)
        assert "users" not in ddl
        assert "departments" not in ddl
        assert "user_id" not in ddl
        assert "dept_name" not in ddl

    def test_abstract_names_present(self, mapping):
        ddl = build_abstract_schema_ddl(mapping)
        assert "Table01" in ddl
        assert "Table02" in ddl
        assert "Column01" in ddl

    def test_primary_key_in_ddl(self, mapping):
        ddl = build_abstract_schema_ddl(mapping)
        assert "PRIMARY KEY" in ddl

    def test_foreign_key_in_ddl(self, mapping):
        ddl = build_abstract_schema_ddl(mapping)
        assert "FOREIGN KEY" in ddl
        assert "REFERENCES Table02" in ddl


# ─────────────────────────── Restorer tests ─────────────────────────────────

SAMPLE_ABSTRACT_SQL = """\
SELECT
  Table01.Column01,
  Table01.Column02,
  Table02.Column02,
  CASE WHEN Table01.Column02 <= 1000 THEN '〇' ELSE '×' END AS user_flag
FROM Table01
INNER JOIN Table02 ON Table01.Column04 = Table02.Column01
"""

EXPECTED_REAL_SQL_FRAGMENTS = [
    "users.user_id",
    "users.user_no",
    "departments.dept_name",
    "FROM users",
    "INNER JOIN departments",
    "users.dept_id = departments.dept_id",
]


class TestRestorer:
    def test_restored_sql_contains_real_names(self, mapping):
        real_sql = restore_sql(SAMPLE_ABSTRACT_SQL, mapping)
        for fragment in EXPECTED_REAL_SQL_FRAGMENTS:
            assert fragment in real_sql, f"Expected '{fragment}' in restored SQL"

    def test_restored_sql_has_no_abstract_names(self, mapping):
        real_sql = restore_sql(SAMPLE_ABSTRACT_SQL, mapping)
        assert "Table01" not in real_sql
        assert "Table02" not in real_sql
        assert "Column01" not in real_sql

    def test_validate_no_real_names_leaked_clean(self, mapping):
        # Abstract SQL should have no real names
        leaks = validate_no_real_names_leaked(SAMPLE_ABSTRACT_SQL, mapping)
        assert leaks == []

    def test_validate_no_real_names_leaked_detects_leak(self, mapping):
        # Inject a real name into the abstract SQL
        leaked_sql = SAMPLE_ABSTRACT_SQL + "\n-- users"
        leaks = validate_no_real_names_leaked(leaked_sql, mapping)
        assert "users" in leaks

    def test_restore_idempotent_table_names(self, mapping):
        """Table names should only be replaced once (no double-replacement)."""
        abstract_sql = "SELECT Table01.Column01 FROM Table01"
        real_sql = restore_sql(abstract_sql, mapping)
        # "users" should appear exactly twice (in SELECT and FROM)
        assert real_sql.count("users") == 2


# ─────────────────────────── Requirements abstraction tests ─────────────────

class TestRequirementsAbstraction:
    def test_table_name_replaced(self, mapping):
        text = "users.user_id が必要"
        result = abstract_requirements(text, mapping)
        assert "users" not in result
        assert "Table01" in result

    def test_multi_table_replaced(self, mapping):
        text = "users と departments を JOIN する"
        result = abstract_requirements(text, mapping)
        assert "users" not in result
        assert "departments" not in result


# ─────────────────────────── Integration (pipeline sans Claude) ──────────────

class TestPipelineWithoutClaude:
    """
    Tests the full pipeline up to the Claude call, then verifies restoration
    using a manually supplied abstract SQL (simulating Claude's response).
    """

    def test_full_round_trip(self, mapping):
        """Abstract SQL → restore → no abstract names remain."""
        abstract_sql = (
            "SELECT Table01.Column01, Table02.Column02 "
            "FROM Table01 "
            "INNER JOIN Table02 ON Table01.Column04 = Table02.Column01"
        )
        real_sql = restore_sql(abstract_sql, mapping)

        assert "users.user_id" in real_sql
        assert "departments.dept_name" in real_sql
        assert "users" in real_sql
        assert "departments" in real_sql
        assert "Table01" not in real_sql
        assert "Table02" not in real_sql

    def test_case_expression_preserved(self, mapping):
        abstract_sql = (
            "SELECT CASE WHEN Table01.Column02 <= 1000 THEN '〇' ELSE '×' END AS flag "
            "FROM Table01"
        )
        real_sql = restore_sql(abstract_sql, mapping)
        # CASE logic should survive, column replaced
        assert "CASE WHEN" in real_sql
        assert "users.user_no" in real_sql
        assert "Table01" not in real_sql
