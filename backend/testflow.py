"""
Offline workflow check. Needs NO Ollama.

Runs the real app.run_agent() (security gates, tool order, tools.py) with a scripted
stand-in for the language model, then checks the result against the API contract.
Only the model is faked: its tool calls are scripted and its summary is canned.

Run from the backend/ folder with the venv active:
    python test_flow.py
"""
import inspect
import json
import re
from types import SimpleNamespace

import app
from tools import check_availability, score_triage

QUERY = "45M, ambulance, BP 180/110, HR 122, SpO2 96%, chest pain radiating to left arm, diaphoresis"

# What a good model would extract from QUERY, matched to tool parameters by name.
FACTS = {
    "age": 45, "sex": "M", "arrival": "ambulance",
    "sys": 180, "dia": 110, "hr": 122, "heart": 122, "pulse": 122,
    "spo2": 96, "sat": 96, "oxygen": 96,
    "complaint": "chest pain radiating to left arm, diaphoresis",
    "symptom": "chest pain radiating to left arm, diaphoresis",
    "text": "chest pain radiating to left arm, diaphoresis",
    "query": QUERY,
}


def guess(param: str, prior: dict):
    p = param.lower()
    if "esi" in p and "esi_level" in prior:
        return prior["esi_level"]
    for key, val in FACTS.items():
        if key in p:
            return val
    raise SystemExit(f"\nCannot guess a value for parameter '{param}'. Add it to FACTS in test_flow.py.")


def call(name, args):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))


class FakeClient:
    """Mimics ollama.Client.chat for the two-tool plan."""

    def chat(self, model, messages, tools, options=None):
        if not tools:  # both tools already ran: write the summary
            msg = SimpleNamespace(content="[STAND-IN] Canned summary. The real model writes this part.", tool_calls=None)
            return SimpleNamespace(message=msg)

        prior = {}
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "tool":
                prior.update(json.loads(m["content"]))

        fn = tools[0]
        args = {p: guess(p, prior) for p in inspect.signature(fn).parameters}
        return SimpleNamespace(message=SimpleNamespace(content="", tool_calls=[call(fn.__name__, args)]))


print("Tool signatures the model must satisfy:")
print("  score_triage       ", inspect.signature(score_triage))
print("  check_availability ", inspect.signature(check_availability))
print()

result = app.run_agent(QUERY, client=FakeClient())
print("run_agent() returned:")
print(json.dumps(result, indent=2, default=str))
print()

if "error" in result:
    raise SystemExit("run_agent returned an error (see above). The API would map it to an HTTP error.")

# Contract check: same model the API uses.
from api import TriageResponse  # noqa: E402

expected = list(TriageResponse.model_fields)
missing = [k for k in expected if k not in result and TriageResponse.model_fields[k].is_required()]
absent = [k for k in expected if k not in result]
extra = [k for k in result if k not in expected]

print("Contract check against api.TriageResponse")
print("  required keys missing :", missing or "none")
print("  optional keys absent  :", [k for k in absent if k not in missing] or "none")
print("  extra keys (ignored)  :", extra or "none")
try:
    TriageResponse.model_validate(result)
    print("  RESULT: PASS. The API would return this to the form.")
except Exception as exc:
    print("  RESULT: FAIL.", re.sub(r"\s+", " ", str(exc))[:400])