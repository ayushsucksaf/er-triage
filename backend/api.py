"""
ER Triage Scorer: HTTP bridge.

Exposes one endpoint, POST /triage, that the browser form calls. It does no clinical
work. It validates the request, hands the text to the teammate's run_agent(), checks
that the answer matches the agreed response contract, and returns it.

Run:
    pip install -r requirements.txt
    uvicorn api:app --reload --port 8000

Until app.py is ready, use the mock agent (labelled as such in every summary):
    TRIAGE_MOCK=1 uvicorn api:app --reload --port 8000
"""
import logging
import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("triage.api")


# ───────────── Agent loading ─────────────
def _load_agent():
    """Real agent from app.py, or the mock when TRIAGE_MOCK=1."""
    if os.getenv("TRIAGE_MOCK") == "1":
        mock_path = Path(__file__).resolve().parent / "mock_agent.py"
        if not mock_path.is_file():
            mock_path = mock_path.parent.parent / "frontend" / "mock_agent.py"
        spec = spec_from_file_location("triage_mock_agent", mock_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load mock agent from {mock_path}.")
        mock_module = module_from_spec(spec)
        spec.loader.exec_module(mock_module)
        run_agent = mock_module.run_agent
        log.warning("TRIAGE_MOCK=1: using the MOCK agent. Scores are fake. Never use for anything real.")
        return run_agent, True
    try:
        from app import run_agent
    except ImportError as exc:
        raise RuntimeError(f"Could not import run_agent from app.py ({exc}). Run from the backend/ folder with the venv active.") from exc
    return run_agent, False


run_agent, USING_MOCK = _load_agent()


# ───────────── Contract ─────────────
class TriageRequest(BaseModel):
    query: str = Field(..., max_length=2000, description="Free-text patient details built by the form.")

    @field_validator("query")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        return v


class TriageResponse(BaseModel):
    """The shape agreed with the frontend. run_agent() must return exactly this."""
    esi_level: int = Field(..., ge=1, le=5)
    urgency_label: str
    routed_to: str
    triggered_flags: list[str] = []
    esi1_alert: bool = False
    low_confidence: bool = False
    can_admit: Optional[bool] = None
    specialist: Optional[str] = None
    specialist_status: Optional[str] = None  # "in_house" | "on_call"
    summary: str = ""


# ───────────── App ─────────────
app = FastAPI(title="ER Triage Scorer API", version="1.0.0")

# Only needed when the page is served from a different origin than this API.
# Comma-separated list in CORS_ORIGINS. Defaults cover common local dev servers.
_default_origins = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8080,http://localhost:3000,http://localhost:8000"
ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# Plain `def` on purpose: FastAPI runs it in a worker thread, so a slow model call
# does not block other requests.
@app.post("/triage", response_model=TriageResponse)
def triage(req: TriageRequest):
    # Patient text is sensitive: log its size, never its content.
    log.info("triage request (%d chars)", len(req.query))

    try:
        raw = run_agent(req.query)
    except ValueError as exc:
        log.warning("input rejected by agent: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        log.exception("run_agent failed")
        raise HTTPException(status_code=500, detail="The triage agent failed. Check the server log.")

    # app.run_agent reports failures as {"error": "..."} instead of raising.
    if isinstance(raw, dict) and "error" in raw:
        msg = str(raw["error"])
        log.warning("agent returned error: %s", msg)
        if msg.startswith("Model request failed"):
            raise HTTPException(status_code=503, detail="The language model is unavailable. Is Ollama running?")
        if msg.startswith("Cannot load SKILL.md"):
            raise HTTPException(status_code=500, detail="Server configuration error. Check the server log.")
        if msg.startswith(("Plan incomplete", "Please provide")):
            raise HTTPException(status_code=422, detail=msg)   # the nurse can fix this
        raise HTTPException(status_code=502, detail=msg)       # the agent stopped itself

    try:
        result = TriageResponse.model_validate(raw)
    except ValidationError as exc:
        log.error("run_agent returned a response that breaks the contract: %s", exc)
        raise HTTPException(status_code=500, detail="The triage agent returned a malformed response.")

    log.info("scored ESI %d, routed to %s", result.esi_level, result.routed_to)
    return result


# Serve the frontend from the same origin (no CORS needed). Registered last so it
# never shadows the API routes.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
if not STATIC_DIR.is_dir():
    STATIC_DIR = FRONTEND_DIR
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    log.warning("Static directory not found at %s — frontend will not be served.", STATIC_DIR)