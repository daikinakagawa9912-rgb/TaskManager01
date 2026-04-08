"""
MCP Server core logic.

Orchestrates the full pipeline:
  parse → abstract → build requirements → call Claude → restore → return

All real names are kept within this module.  Nothing real is ever passed
to claude_client.generate_abstract_sql().
"""
import json
import logging
import re
from typing import Any

from abstractor import abstract_requirements, build_abstract_schema_ddl, build_mapping
from claude_client import generate_abstract_sql
from models import AbstractionMapping, GenerateSqlRequest, GenerateSqlResponse
from parser import parse_create_statements
from restorer import restore_sql, validate_no_real_names_leaked

logger = logging.getLogger(__name__)


# ─────────────────────── Requirements parser ────────────────────────────────

def _build_requirements_json(
    abstracted_text: str,
    mapping: AbstractionMapping,
) -> dict[str, Any]:
    """
    Convert the abstracted natural-language requirements into a structured
    JSON dict that can be sent to Claude.

    Strategy
    --------
    We attempt to detect the most common patterns:
      • "TableXX.ColumnYY" references  → SELECT items
      • "CASE WHEN … THEN … ELSE …"   → CASE expression
      • JOIN hints                      → joins array
      • GROUP BY / HAVING / ORDER BY   → respective clauses
      • DISTINCT keyword               → distinct flag

    For anything not detected automatically the caller may pass a pre-formed
    JSON string that already uses abstract names.
    """
    # 1. Try to parse the abstracted text as JSON directly (the Web UI may
    #    send a structured JSON requirements block already).
    try:
        parsed = json.loads(abstracted_text)
        # Normalise "from_table" key variants
        if "from" in parsed and "from_table" not in parsed:
            parsed["from_table"] = parsed.pop("from")
        return parsed
    except json.JSONDecodeError:
        pass

    # 2. Natural-language heuristic parsing.
    lines = [l.strip() for l in abstracted_text.splitlines() if l.strip()]
    select_items: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    from_table: str = ""
    group_by: list[str] = []
    order_by: list[str] = []
    having: str | None = None
    distinct = False

    col_ref_re = re.compile(r"(Table\d+)\.(Column\d+)", re.IGNORECASE)
    join_re = re.compile(
        r"(INNER|LEFT|RIGHT|FULL)?\s*JOIN\s+(Table\d+)\s+ON\s+(.+)", re.IGNORECASE
    )
    case_re = re.compile(
        r"CASE\s+WHEN\s+(.+?)\s+THEN\s+['\"]?(.+?)['\"]?\s+ELSE\s+['\"]?(.+?)['\"]?\s+END(?:\s+AS\s+(\w+))?",
        re.IGNORECASE,
    )

    for line in lines:
        # CASE expression
        m = case_re.search(line)
        if m:
            condition, then_val, else_val, alias = m.groups()
            select_items.append(
                {
                    "case": {
                        "when": [{"condition": condition.strip(), "value": then_val.strip()}],
                        "else": else_val.strip(),
                        "alias": alias.strip() if alias else "case_col",
                    }
                }
            )
            continue

        # JOIN clause
        m = join_re.search(line)
        if m:
            jtype, jtable, jon = m.groups()
            joins.append(
                {"type": (jtype or "INNER").upper(), "table": jtable, "on": jon.strip()}
            )
            continue

        # Regular column reference
        m = col_ref_re.search(line)
        if m:
            t, c = m.group(1), m.group(2)
            if not from_table:
                from_table = t
            select_items.append({"table": t, "column": c})
            continue

        # GROUP BY
        if re.search(r"\bGROUP\s+BY\b", line, re.IGNORECASE):
            cols = col_ref_re.findall(line)
            group_by.extend(f"{t}.{c}" for t, c in cols)
            continue

        # ORDER BY
        if re.search(r"\bORDER\s+BY\b", line, re.IGNORECASE):
            cols = col_ref_re.findall(line)
            order_by.extend(f"{t}.{c}" for t, c in cols)
            continue

        # HAVING
        if re.search(r"\bHAVING\b", line, re.IGNORECASE):
            having = line
            continue

        # DISTINCT
        if re.search(r"\bDISTINCT\b", line, re.IGNORECASE):
            distinct = True

    # Infer from_table from first select item if not set
    if not from_table and select_items:
        first = select_items[0]
        from_table = first.get("table", "Table01")

    result: dict[str, Any] = {
        "select": select_items,
        "from_table": from_table,
    }
    if joins:
        result["joins"] = joins
    if group_by:
        result["group_by"] = group_by
    if having:
        result["having"] = having
    if order_by:
        result["order_by"] = order_by
    if distinct:
        result["distinct"] = distinct

    return result


# ─────────────────────── Main pipeline ─────────────────────────────────────

def process_request(request: GenerateSqlRequest) -> GenerateSqlResponse:
    """
    Full MCP pipeline:
      1. Parse CREATE statements
      2. Build abstraction mapping (kept internal)
      3. Build abstract schema DDL
      4. Abstract the user requirements
      5. Build structured requirements JSON
      6. Call Claude (only abstract data)
      7. Validate Claude response has no real names
      8. Restore abstract SQL → real SQL
      9. Return result

    Parameters
    ----------
    request : GenerateSqlRequest
        Raw user input from the Web UI.

    Returns
    -------
    GenerateSqlResponse
        Contains the restored SQL (and abstract SQL for demo/debug mode).
    """
    try:
        # ── Step 1: Parse ────────────────────────────────────────────────
        parsed_tables = parse_create_statements(request.create_statements)
        if not parsed_tables:
            return GenerateSqlResponse(
                sql="",
                error="No valid CREATE TABLE statements found.",
            )
        logger.info("Parsed %d table(s).", len(parsed_tables))

        # ── Step 2: Build mapping ────────────────────────────────────────
        mapping = build_mapping(parsed_tables)
        logger.info(
            "Abstraction mapping built: %s",
            {t.real_name: t.abstract_name for t in mapping.tables},
        )

        # ── Step 3: Abstract schema DDL ──────────────────────────────────
        abstract_schema = build_abstract_schema_ddl(mapping)
        logger.debug("Abstract schema DDL:\n%s", abstract_schema)

        # ── Step 4: Abstract requirements ────────────────────────────────
        abstracted_text = abstract_requirements(request.requirements, mapping)
        logger.debug("Abstracted requirements text:\n%s", abstracted_text)

        # ── Step 5: Build structured requirements JSON ────────────────────
        requirements_json = _build_requirements_json(abstracted_text, mapping)
        logger.info(
            "Requirements JSON (abstract): %s",
            json.dumps(requirements_json, ensure_ascii=False),
        )

        # ── Step 6: Call Claude ──────────────────────────────────────────
        abstract_sql = generate_abstract_sql(abstract_schema, requirements_json)
        logger.debug("Abstract SQL from Claude:\n%s", abstract_sql)

        # ── Step 7: Validate – no real names must appear in Claude output ─
        leaks = validate_no_real_names_leaked(abstract_sql, mapping)
        if leaks:
            logger.warning("Claude output contained real name(s): %s", leaks)
            # Strip the leaked names as a safety measure (should not happen)
            for leak in leaks:
                abstract_sql = re.sub(
                    r"\b" + re.escape(leak) + r"\b", "[REDACTED]", abstract_sql
                )

        # ── Step 8: Restore ──────────────────────────────────────────────
        real_sql = restore_sql(abstract_sql, mapping)
        logger.info("Restored SQL generated successfully.")

        return GenerateSqlResponse(sql=real_sql, abstracted_sql=abstract_sql)

    except RuntimeError as exc:
        logger.error("Configuration error: %s", exc)
        return GenerateSqlResponse(sql="", error=str(exc))
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Unexpected error during SQL generation.")
        return GenerateSqlResponse(sql="", error=f"Internal error: {exc}")
