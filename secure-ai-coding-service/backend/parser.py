"""
SQL CREATE TABLE statement parser.

Parses one or more CREATE TABLE statements and returns a list of
(table_name, [(column_name, data_type, constraints), ...]) tuples.
No external SQL-parse library is required – uses only the standard library.
"""
import re
from dataclasses import dataclass, field


@dataclass
class ParsedColumn:
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    foreign_key_ref: str | None = None   # "other_table.other_column"


@dataclass
class ParsedTable:
    name: str
    columns: list[ParsedColumn] = field(default_factory=list)


# ──────────────────────────── helpers ──────────────────────────────────────

_CREATE_HEADER_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?(\w+)[`\"\]]?\s*\(",
    re.IGNORECASE,
)

_FK_RE = re.compile(
    r"FOREIGN\s+KEY\s*\([`\"\[]?(\w+)[`\"\]]?\)\s*REFERENCES\s+[`\"\[]?(\w+)[`\"\]]?\s*\([`\"\[]?(\w+)[`\"\]]?\)",
    re.IGNORECASE,
)

_PK_INLINE_RE = re.compile(r"\bPRIMARY\s+KEY\b", re.IGNORECASE)
_NOT_NULL_RE = re.compile(r"\bNOT\s+NULL\b", re.IGNORECASE)
_TABLE_PK_RE = re.compile(
    r"PRIMARY\s+KEY\s?\(([^)]{1,500})\)",
    re.IGNORECASE,
)


def _find_table_body(sql: str, open_paren_pos: int) -> str | None:
    """
    Starting from the opening `(` at *open_paren_pos*, scan forward tracking
    parenthesis depth and return the inner content (everything between the
    outermost balanced parens).  Handles nested parens such as VARCHAR(10).

    Returns None if the SQL is malformed (unclosed paren).
    """
    depth = 0
    i = open_paren_pos
    in_single = False
    content_start = -1

    while i < len(sql):
        ch = sql[i]
        # Minimal string-literal handling (single-quoted strings)
        if in_single:
            if ch == "'" and (i == 0 or sql[i - 1] != "\\"):
                in_single = False
        elif ch == "'":
            in_single = True
        elif ch == "(":
            depth += 1
            if depth == 1:
                content_start = i + 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and content_start != -1:
                return sql[content_start:i]
        i += 1

    return None


def _split_column_defs(body: str) -> list[str]:
    """
    Split the body of a CREATE TABLE (everything between the outer parens)
    into individual column / constraint definitions.

    We cannot simply split on commas because data types may contain commas
    (e.g. DECIMAL(10,2)).
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(ch)
    if current:
        part = "".join(current).strip()
        if part:
            parts.append(part)
    return parts


def _parse_table(table_name: str, body: str) -> ParsedTable:
    table = ParsedTable(name=table_name)
    defs = _split_column_defs(body)

    # Collect table-level foreign key references: column -> (ref_table, ref_col)
    fk_map: dict[str, tuple[str, str]] = {}
    for d in defs:
        m = _FK_RE.search(d)
        if m:
            col, ref_table, ref_col = m.group(1), m.group(2), m.group(3)
            fk_map[col.lower()] = (ref_table, ref_col)

    # Collect table-level PRIMARY KEY columns
    pk_columns: set[str] = set()
    for d in defs:
        m = _TABLE_PK_RE.search(d)
        if m:
            for col in m.group(1).split(","):
                pk_columns.add(col.strip().strip("`\"[]").lower())

    for d in defs:
        d_stripped = d.strip()

        # Skip constraint-only lines (FOREIGN KEY, PRIMARY KEY, UNIQUE, INDEX, KEY, CHECK)
        if re.match(
            r"(CONSTRAINT|FOREIGN\s+KEY|PRIMARY\s+KEY|UNIQUE|INDEX|KEY|CHECK)\b",
            d_stripped,
            re.IGNORECASE,
        ):
            continue

        # Column definition: first token is column name, second is type
        tokens = d_stripped.split()
        if len(tokens) < 2:
            continue

        col_name = tokens[0].strip("`\"[]")
        # Reconstruct data type (may include size spec)
        rest = d_stripped[len(tokens[0]):].strip()
        # Data type ends at the first space after any closing paren
        type_match = re.match(r"(\w+(?:\s*\([^)]*\))?)", rest)
        data_type = type_match.group(1) if type_match else tokens[1]

        is_pk = bool(_PK_INLINE_RE.search(d_stripped)) or col_name.lower() in pk_columns
        nullable = not is_pk and not bool(_NOT_NULL_RE.search(d_stripped))
        fk_ref = None
        if col_name.lower() in fk_map:
            ref_table, ref_col = fk_map[col_name.lower()]
            fk_ref = f"{ref_table}.{ref_col}"

        table.columns.append(
            ParsedColumn(
                name=col_name,
                data_type=data_type,
                nullable=nullable,
                is_primary_key=is_pk,
                foreign_key_ref=fk_ref,
            )
        )

    return table


# ──────────────────────────── public API ───────────────────────────────────

def parse_create_statements(sql: str) -> list[ParsedTable]:
    """
    Parse one or more CREATE TABLE statements and return a list of ParsedTable
    objects.

    Parameters
    ----------
    sql : str
        Raw SQL text containing one or more CREATE TABLE statements.

    Returns
    -------
    list[ParsedTable]
        Ordered list of parsed tables (preserves declaration order).
    """
    tables: list[ParsedTable] = []
    for header_match in _CREATE_HEADER_RE.finditer(sql):
        table_name = header_match.group(1)
        # The opening `(` is the last character matched by the header regex.
        open_paren_pos = header_match.end() - 1
        body = _find_table_body(sql, open_paren_pos)
        if body is None:
            continue
        tables.append(_parse_table(table_name, body))
    return tables
