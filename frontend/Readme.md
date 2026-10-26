# ER Triage Severity Scorer

AI parses, Python decides. A nurse types patient details, the LLM extracts the vitals,
and deterministic Python scores the ESI level.

```
browser form ──POST /triage──▶ api.py ──▶ app.run_agent() ──▶ Ollama (llama3.1:8b)
 (index.html)                  (FastAPI)        │
                                                └──▶ tools.py  (pure-Python ESI scoring)
```

## Layout

```
er-triage/
├── api.py            FastAPI bridge (this file's owner: frontend/API)
├── mock_agent.py     Fake run_agent() for testing before the backend is ready
├── requirements.txt
├── static/
│   └── index.html    Put the frontend here
├── app.py            Agent loop + security gates   (teammate)
├── tools.py          ESI scoring                    (teammate)
├── demo_tools.py     Offline unit tests             (teammate)
└── SKILL.md          LLM behaviour rules            (teammate)
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# A) Backend not ready yet: use the mock
TRIAGE_MOCK=1 uvicorn api:app --reload --port 8000     # Windows PowerShell: $env:TRIAGE_MOCK=1; uvicorn ...

# B) Real backend (needs `ollama serve` running and the model pulled)
uvicorn api:app --reload --port 8000
```

Then open **http://localhost:8000/**. The API serves `static/index.html` itself, so the
page and the API share one origin and CORS never comes into play.

Quick check without the browser:

```bash
curl -s localhost:8000/health
curl -s -X POST localhost:8000/triage -H "Content-Type: application/json" \
  -d '{"query":"45M, ambulance, BP 180/110, HR 122, SpO2 96%, chest pain radiating to left arm, diaphoresis"}'
```

Interactive docs: http://localhost:8000/docs

## The contract

`POST /triage` takes `{ "query": "<text>" }` (1 to 2000 characters) and returns:

| Field | Type | Notes |
|---|---|---|
| `esi_level` | int 1–5 | required |
| `urgency_label` | string | e.g. `EMERGENT` |
| `routed_to` | string | `resus_bay`, `trauma_bay`, `main_ed`, `fast_track` |
| `triggered_flags` | string[] | rules that fired |
| `esi1_alert` | bool | true only for level 1 |
| `low_confidence` | bool | vague input |
| `can_admit` | bool or null | bed available |
| `specialist` | string or null | |
| `specialist_status` | string or null | `in_house` or `on_call` |
| `summary` | string | LLM-written |

`api.py` validates every agent reply against this shape. If `run_agent()` drifts from it,
the API returns a 500 and logs exactly which field is wrong, instead of sending the
browser something half-right.

| Status | Meaning |
|---|---|
| 200 | scored |
| 422 | bad request body, or the agent raised `ValueError` (input rejected by a security gate) |
| 500 | agent crashed or returned a malformed reply (see server log) |

## Integration checklist for the backend

- [ ] `app.py` exposes `run_agent(query: str) -> dict` matching the table above
- [ ] Input blocked by a security gate raises `ValueError("reason")` (becomes HTTP 422)
- [ ] Any other failure just raises; the API turns it into a 500
- [ ] `TRIAGE_MOCK` unset, then re-run the curl above and compare with the mock output

## Config (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `TRIAGE_MOCK` | unset | `1` = use `mock_agent.py` |
| `CORS_ORIGINS` | common localhost ports | comma-separated origins, only needed if the page is served elsewhere |
| `LOG_LEVEL` | `INFO` | |

## Notes

- Patient text is never logged, only its length.
- The first request after starting Ollama can take a while while the model loads. The
  frontend has no timeout, so the button just shows "Scoring…" until it answers.
- Not for real clinical use. Hackathon prototype.