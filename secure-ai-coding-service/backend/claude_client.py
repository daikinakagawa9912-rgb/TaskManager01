"""
Claude API client.

Sends the abstract schema + requirements to Claude and returns the
abstract SQL it generates.

Security contract:
    - Only abstract identifiers are ever included in the prompt.
    - The API key is read from the environment; never hard-coded.
"""
import os
import json
import logging

import anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-5"   # Update to the desired Claude model


PROMPT_TEMPLATE = """\
You are an expert SQL query builder.
You will be given:
1. An abstract database schema (CREATE TABLE statements using abstract names only).
2. A JSON object describing the SQL query requirements using the same abstract names.

Your task:
- Generate a single, syntactically correct SQL SELECT statement.
- Use ONLY the abstract table and column names from the schema.
- Do NOT invent, rename, or guess any identifiers.
- Do NOT output any explanation, markdown fences, or commentary – output the raw SQL only.

## Abstract Schema

{abstract_schema}

## Requirements (JSON)

{requirements_json}

## Output

Output the SQL SELECT statement only.
"""


def generate_abstract_sql(abstract_schema: str, requirements: dict) -> str:
    """
    Call Claude with the abstract schema and requirements JSON.

    Parameters
    ----------
    abstract_schema : str
        CREATE TABLE DDL using only abstract identifiers.
    requirements : dict
        The abstracted query requirements as a Python dict (will be
        JSON-serialised before being included in the prompt).

    Returns
    -------
    str
        The raw SQL string returned by Claude (still using abstract names).

    Raises
    ------
    RuntimeError
        If the ANTHROPIC_API_KEY environment variable is not set.
    anthropic.APIError
        On API-level errors.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Please configure it before starting the server."
        )

    client = anthropic.Anthropic(api_key=api_key)

    prompt = PROMPT_TEMPLATE.format(
        abstract_schema=abstract_schema,
        requirements_json=json.dumps(requirements, ensure_ascii=False, indent=2),
    )

    logger.info("Sending abstract prompt to Claude (schema + requirements only).")

    message = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    abstract_sql = message.content[0].text.strip()
    logger.info("Claude returned abstract SQL (%d chars).", len(abstract_sql))
    return abstract_sql
