"""
FastAPI application – entry point for the Secure AI Coding Service.

Endpoints
---------
POST /api/generate-sql
    Accept CREATE statements + extraction requirements, run the MCP pipeline,
    and return the final (restored) SQL.

GET /api/health
    Simple liveness probe.

GET /
    Serve the frontend Web UI (index.html).
"""
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mcp_server import process_request
from models import GenerateSqlRequest, GenerateSqlResponse

# ─────────────────────── Logging ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────── App ────────────────────────────────────────────────
app = FastAPI(
    title="Secure AI Coding Service",
    description=(
        "MCP-based service that abstracts database schema before sending it to "
        "Claude for SQL generation, keeping real table/column names confidential."
    ),
    version="1.0.0",
)

# Allow the frontend (served from the same origin or a dev server) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict to specific origins in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─────────────────────── Static files (frontend) ────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_index():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Frontend not found. Use /docs for the API."}


# ─────────────────────── API endpoints ──────────────────────────────────────

@app.get("/api/health")
async def health():
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/api/generate-sql", response_model=GenerateSqlResponse)
async def generate_sql(request: GenerateSqlRequest):
    """
    Main MCP pipeline endpoint.

    Accepts raw CREATE TABLE SQL and natural-language (or JSON) extraction
    requirements, and returns a fully restored SQL SELECT statement.

    The Claude LLM is called with **abstracted** names only.
    Real schema information never leaves this server.
    """
    if not request.create_statements.strip():
        raise HTTPException(status_code=400, detail="create_statements must not be empty.")
    if not request.requirements.strip():
        raise HTTPException(status_code=400, detail="requirements must not be empty.")

    logger.info("Received /api/generate-sql request.")
    response = process_request(request)

    if response.error:
        logger.error("Pipeline returned error: %s", response.error)
        raise HTTPException(status_code=500, detail=response.error)

    return response
