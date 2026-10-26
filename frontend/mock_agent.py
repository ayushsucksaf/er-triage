"""
MOCK agent: stands in for app.run_agent() so the API and UI can be tested end to end
before the real backend exists. The rules below are crude placeholders, NOT clinical
logic, and every summary is prefixed [MOCK]. Delete this file once app.py works.

It returns different levels on purpose, so every UI state can be exercised:
  "not breathing" / SpO2 below 90   -> ESI 1 (alert strip)
  chest pain, BP >= 180, HR >= 120  -> ESI 2
  very short complaint              -> low_confidence = True
"""
import re
import time

_DEPT = {1: "resus_bay", 2: "resus_bay", 3: "main_ed", 4: "fast_track", 5: "fast_track"}
_LABEL = {1: "RESUSCITATION", 2: "EMERGENT", 3: "URGENT", 4: "LESS URGENT", 5: "NON-URGENT"}


def _num(pattern: str, text: str):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def run_agent(query: str) -> dict:
    time.sleep(1.2)  # imitate model latency so the loading state is visible
    q = query.lower()
    sys_bp = _num(r"bp\s*(\d+)\s*/", q)
    hr = _num(r"hr\s*(\d+)", q)
    spo2 = _num(r"spo2\s*(\d+)", q)

    flags = []
    if "not breathing" in q or "unresponsive" in q:
        flags.append("high_risk_complaint: no breathing / unresponsive")
    if spo2 is not None and spo2 < 90:
        flags.append("spo2 < 90")

    if flags:
        level = 1
    else:
        if "chest pain" in q:
            flags.append("high_risk_complaint: chest pain")
        if sys_bp is not None and sys_bp >= 180:
            flags.append("systolic_bp >= 180")
        if hr is not None and hr >= 120:
            flags.append("heart_rate >= 120")
        level = 2 if flags else (3 if len(q) > 40 else 4)

    cardiac = "chest pain" in q
    return {
        "esi_level": level,
        "urgency_label": _LABEL[level],
        "routed_to": _DEPT[level],
        "triggered_flags": flags,
        "esi1_alert": level == 1,
        "low_confidence": len(q) < 25,
        "can_admit": level >= 3,
        "specialist": "Dr. Mehta (Cardiologist)" if cardiac else None,
        "specialist_status": "on_call" if cardiac else None,
        "summary": (
            "[MOCK] This is placeholder output from mock_agent.py, not a real assessment. "
            f"Input received: {query}"
        ),
    }