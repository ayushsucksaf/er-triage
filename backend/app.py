"""A bounded host for a local ER triage agent (educational demo)."""

import inspect
import json
import logging
from pathlib import Path

import ollama

from tools import check_availability, score_triage

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL_NAME = "gemma4:e4b"
MAX_STEPS = 5

TOOLS = {
    "score_triage": score_triage,
    "check_availability": check_availability,
}
ORDER = ("score_triage", "check_availability")

SYSTEM_PROMPT = """You are an ER triage assistant (educational demo, not clinical).
Use the declared tools for scoring and availability checks.
First request score_triage, then check_availability with the esi_level it returned.
Request exactly one tool per turn, each tool only once.
Do not guess inputs. If inputs are missing, ask the user for them.
After both tools succeed, write the summary.
"""


def build_system_prompt() -> str:
    path = Path(__file__).resolve().with_name("SKILL.md")
    return SYSTEM_PROMPT + "\n" + path.read_text(encoding="utf-8")


def validate_args(name: str, args: object) -> str | None:
    """Gate 2: validate argument dictionary types and function signature."""
    if not isinstance(args, dict):
        return "Tool arguments must be a dictionary"
    if not all(isinstance(key, str) for key in args):
        return "Argument names must be strings"
    try:
        inspect.signature(TOOLS[name]).bind(**args)
    except TypeError as exc:
        return str(exc)
    return None


def dispatch(name: str, args: object) -> dict:
    """Gates 1-3: allowlist, argument check, safe execution."""
    if name not in TOOLS:
        return {"error": f"Unknown tool: {name}"}
    problem = validate_args(name, args)
    if problem:
        return {"error": problem}
    try:
        return TOOLS[name](**args)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def run_agent(user_query: str, client: ollama.Client | None = None) -> dict:
    """Return the merged tool results plus the LLM summary, or {"error": ...}."""
    if not isinstance(user_query, str) or not user_query.strip():
        return {"error": "Please provide a patient description."}

    try:
        system = build_system_prompt()
    except OSError as exc:
        return {"error": f"Cannot load SKILL.md: {exc}"}

    if client is None:
        client = ollama.Client(host="http://localhost:11434", timeout=120.0)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_query},
    ]
    completed = []
    results = {}

    for step in range(1, MAX_STEPS + 1):
        pending = ORDER[len(completed):len(completed) + 1]
        declarations = [TOOLS[name] for name in pending]

        try:
            response = client.chat(
                model=MODEL_NAME,
                messages=messages,
                tools=declarations,
                options={"temperature": 0},
            )
        except Exception as exc:
            return {"error": f"Model request failed: {type(exc).__name__}: {exc}"}

        message = response.message
        messages.append(message)
        calls = message.tool_calls or []

        if not calls:
            text = (message.content or "").strip()
            if len(completed) < len(ORDER):
                return {"error": "Plan incomplete; both tool checks are required. "
                                 + (text or "Please supply all required inputs.")}
            return {**results, "summary": text or "Both checks finished; model summary was empty."}

        if len(calls) != 1:
            return {"error": "Stopped: request exactly one tool per turn."}

        call = calls[0]
        name = call.function.name
        args = call.function.arguments

        if name not in TOOLS:
            return {"error": f"Stopped: unknown tool {name}."}
        if not pending or name != pending[0]:
            return {"error": f"Stopped: tool {name} is out of order or repeated."}

        # The model must pass the level score_triage actually returned.
        if name == "check_availability" and isinstance(args, dict) \
                and args.get("esi_level") != results.get("esi_level"):
            return {"error": "Stopped: esi_level does not match the score_triage result."}

        log.info("Step %d REQUEST %s %s", step, name, args)
        result = dispatch(name, args)
        log.info("Step %d RESULT %s %s", step, name, result)

        messages.append({
            "role": "tool",
            "tool_name": name,
            "content": json.dumps(result),
        })

        if "error" in result:
            return {"error": f"Stopped: {name}: {result['error']}"}

        results.update(result)
        completed.append(name)

    return {"error": "Stopped: reached MAX_STEPS without a final answer."}


if __name__ == "__main__":
    query = ("45M, ambulance, BP 180/110, HR 122, SpO2 96, "
             "chest pain radiating to left arm")
    print(json.dumps(run_agent(query), indent=2))