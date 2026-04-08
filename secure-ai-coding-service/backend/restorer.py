"""
Restoration layer.

Takes the abstract SQL produced by Claude and replaces every abstract
identifier (Table01, Column01 …) with the corresponding real name,
using the AbstractionMapping kept internally by the MCP server.

Security guarantee:
    Only abstract→real substitutions defined in the mapping are performed.
    No guessing, no inference, no pattern extrapolation.
"""
import re

from models import AbstractionMapping


def restore_sql(abstract_sql: str, mapping: AbstractionMapping) -> str:
    """
    Replace abstract table/column names in *abstract_sql* with real names.

    Parameters
    ----------
    abstract_sql : str
        The SQL string returned by Claude, containing only abstract identifiers.
    mapping : AbstractionMapping
        The internal mapping built by abstractor.build_mapping().

    Returns
    -------
    str
        SQL with all abstract identifiers replaced by real names.

    Raises
    ------
    ValueError
        If an abstract identifier found in the SQL is not present in the
        mapping (this should never happen if Claude respects the schema).
    """
    result = abstract_sql

    # ── 1. Replace "TableXX.ColumnYY" compound references ──────────────────
    # Must be done before individual token replacement to avoid partial matches.
    for abs_key, real_key in sorted(
        mapping.column_abstract_to_real.items(), key=lambda kv: -len(kv[0])
    ):
        real_table, real_col = real_key.split(".", 1)
        # Use word-boundary-aware regex so "Table01" doesn't match "Table010"
        pattern = r"\b" + re.escape(abs_key) + r"\b"
        result = re.sub(pattern, f"{real_table}.{real_col}", result)

    # ── 2. Replace standalone table names ───────────────────────────────────
    for abs_table, real_table in sorted(
        mapping.table_abstract_to_real.items(), key=lambda kv: -len(kv[0])
    ):
        pattern = r"\b" + re.escape(abs_table) + r"\b"
        result = re.sub(pattern, real_table, result)

    return result


def validate_no_real_names_leaked(sql: str, mapping: AbstractionMapping) -> list[str]:
    """
    Utility: verify that *sql* does NOT contain any real table or column names.
    Returns a list of offending names (empty list = clean).

    Used in tests and for internal audit logging.
    """
    offenders: list[str] = []
    for table in mapping.tables:
        if re.search(r"\b" + re.escape(table.real_name) + r"\b", sql, re.IGNORECASE):
            offenders.append(table.real_name)
        for col in table.columns:
            if re.search(r"\b" + re.escape(col.real_name) + r"\b", sql, re.IGNORECASE):
                offenders.append(col.real_name)
    return offenders
