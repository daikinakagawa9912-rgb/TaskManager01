"""
Pydantic data models for the Secure AI Coding Service.
"""
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────── Request / Response ────────────────────────────

class GenerateSqlRequest(BaseModel):
    """Request body sent from the Web UI."""
    create_statements: str  # Raw SQL CREATE TABLE statements (may contain multiple)
    requirements: str       # Natural-language extraction requirements (Japanese OK)


class GenerateSqlResponse(BaseModel):
    """Response returned to the Web UI."""
    sql: str                        # Restored (real) SQL
    abstracted_sql: Optional[str] = None   # For debug/demo only – never expose in prod
    error: Optional[str] = None


# ─────────────────────────── Internal structures ────────────────────────────

class ColumnInfo(BaseModel):
    abstract_name: str      # e.g. "Column01"
    real_name: str          # e.g. "user_id"
    data_type: str          # e.g. "VARCHAR(100)"
    nullable: bool = True
    is_primary_key: bool = False
    foreign_key_ref: Optional[str] = None   # "TableXX.ColumnYY" (abstracted)


class TableInfo(BaseModel):
    abstract_name: str      # e.g. "Table01"
    real_name: str          # e.g. "users"
    columns: list[ColumnInfo] = []


class AbstractionMapping(BaseModel):
    """Complete bidirectional mapping.  MCP-internal only – never sent to Claude."""
    tables: list[TableInfo] = []
    # Quick-lookup helpers (built at runtime, not serialised to the LLM)
    table_real_to_abstract: dict[str, str] = {}
    table_abstract_to_real: dict[str, str] = {}
    column_real_to_abstract: dict[str, str] = {}   # "real_table.real_col" -> "AbsTab.AbsCol"
    column_abstract_to_real: dict[str, str] = {}   # "AbsTab.AbsCol"       -> "real_table.real_col"


# ─────────────────────────── Claude I/O ────────────────────────────────────

class CaseWhenCondition(BaseModel):
    condition: str  # e.g. "Table01.Column02 <= 1000"
    value: str      # e.g. "〇"


class CaseExpression(BaseModel):
    # `else` is a Python reserved word; use alias so JSON uses "else" as the key.
    model_config = ConfigDict(populate_by_name=True)

    when: list[CaseWhenCondition]
    else_value: str = Field(alias="else")
    alias: str


class SelectItem(BaseModel):
    table: Optional[str] = None
    column: Optional[str] = None
    case: Optional[CaseExpression] = None


class JoinClause(BaseModel):
    type: str       # INNER / LEFT / RIGHT / FULL
    table: str      # Abstracted table name
    on: str         # Abstracted ON condition


class AbstractRequirements(BaseModel):
    """Abstracted requirements sent to Claude."""
    select: list[dict[str, Any]]
    from_table: str
    joins: list[dict[str, Any]] = []
    where: Optional[str] = None
    group_by: Optional[list[str]] = None
    having: Optional[str] = None
    order_by: Optional[list[str]] = None
    distinct: bool = False
