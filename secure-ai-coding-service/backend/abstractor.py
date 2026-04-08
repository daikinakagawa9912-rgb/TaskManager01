"""
Abstraction layer.

Converts real table/column names into opaque identifiers (Table01, Column01 …)
and builds a bidirectional mapping that is kept entirely inside the MCP server.
Claude never receives the real names.
"""
import re

from models import AbstractionMapping, ColumnInfo, TableInfo
from parser import ParsedTable


def build_mapping(parsed_tables: list[ParsedTable]) -> AbstractionMapping:
    """
    Build an AbstractionMapping from a list of ParsedTable objects.

    The mapping is purely internal to the MCP server.  The only thing
    Claude ever sees is Abstract names such as Table01 / Column01.

    Parameters
    ----------
    parsed_tables : list[ParsedTable]
        Output from parser.parse_create_statements().

    Returns
    -------
    AbstractionMapping
        Fully populated mapping with forward + reverse look-up dicts.
    """
    mapping = AbstractionMapping()

    for t_idx, pt in enumerate(parsed_tables, start=1):
        abs_table = f"Table{t_idx:02d}"

        columns: list[ColumnInfo] = []
        for c_idx, pc in enumerate(pt.columns, start=1):
            abs_col = f"Column{c_idx:02d}"

            # Resolve foreign-key references – they are real names at parse time;
            # we must translate them to abstract names AFTER all tables are processed.
            # Store raw real ref for now and fix up below.
            columns.append(
                ColumnInfo(
                    abstract_name=abs_col,
                    real_name=pc.name,
                    data_type=pc.data_type,
                    nullable=pc.nullable,
                    is_primary_key=pc.is_primary_key,
                    foreign_key_ref=pc.foreign_key_ref,   # still real at this point
                )
            )

            # Forward maps
            real_key = f"{pt.name}.{pc.name}"
            abs_key = f"{abs_table}.{abs_col}"
            mapping.column_real_to_abstract[real_key] = abs_key
            mapping.column_abstract_to_real[abs_key] = real_key

        mapping.tables.append(
            TableInfo(abstract_name=abs_table, real_name=pt.name, columns=columns)
        )
        mapping.table_real_to_abstract[pt.name] = abs_table
        mapping.table_abstract_to_real[abs_table] = pt.name

    # Fix-up foreign key refs: translate real "OtherTable.other_col" → "TableXX.ColumnYY"
    for table_info in mapping.tables:
        for col_info in table_info.columns:
            if col_info.foreign_key_ref:
                real_ref = col_info.foreign_key_ref   # "OtherTable.other_col"
                abs_ref = mapping.column_real_to_abstract.get(real_ref)
                if abs_ref:
                    col_info.foreign_key_ref = abs_ref   # now abstract

    return mapping


def build_abstract_schema_ddl(mapping: AbstractionMapping) -> str:
    """
    Produce a CREATE TABLE DDL string that uses only abstract names.
    This is the text that gets sent to Claude.
    """
    lines: list[str] = []
    for table in mapping.tables:
        lines.append(f"CREATE TABLE {table.abstract_name} (")
        col_lines: list[str] = []
        pk_cols: list[str] = []
        for col in table.columns:
            parts = [f"  {col.abstract_name}", col.data_type]
            if not col.nullable:
                parts.append("NOT NULL")
            col_lines.append(" ".join(parts))
            if col.is_primary_key:
                pk_cols.append(col.abstract_name)

        if pk_cols:
            col_lines.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

        # Foreign keys
        for col in table.columns:
            if col.foreign_key_ref:
                ref_parts = col.foreign_key_ref.split(".")
                if len(ref_parts) == 2:
                    ref_table, ref_col = ref_parts
                    col_lines.append(
                        f"  FOREIGN KEY ({col.abstract_name}) REFERENCES {ref_table}({ref_col})"
                    )

        lines.append(",\n".join(col_lines))
        lines.append(");\n")

    return "\n".join(lines)


def abstract_requirements(
    raw_requirements: str,
    mapping: AbstractionMapping,
) -> str:
    """
    Replace every occurrence of real table/column names in the requirements
    text with their abstract counterparts.

    Returns the abstracted requirements as a plain string.  The caller
    (mcp_server.py) converts this into the structured JSON that Claude receives.
    """
    result = raw_requirements

    # Sort by length descending to avoid partial replacements
    for real_name, abs_name in sorted(
        mapping.table_real_to_abstract.items(), key=lambda kv: -len(kv[0])
    ):
        result = re.sub(re.escape(real_name), abs_name, result, flags=re.IGNORECASE)

    # Replace "TableXX.real_col" with "TableXX.ColumnYY"
    for real_key, abs_key in sorted(
        mapping.column_real_to_abstract.items(), key=lambda kv: -len(kv[0])
    ):
        # Also match abstracted-table + real column patterns that may appear after
        # the table-name pass above (e.g. "Table01.user_number")
        real_table, real_col = real_key.split(".", 1)
        abs_table = mapping.table_real_to_abstract.get(real_table, real_table)
        # Pattern: "Table01.user_number" -> "Table01.Column02"
        pattern = re.escape(abs_table) + r"\." + re.escape(real_col)
        abs_table_col = abs_key.split(".")[1]
        result = re.sub(pattern, f"{abs_table}.{abs_table_col}", result, flags=re.IGNORECASE)

    return result
