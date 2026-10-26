"""ESI triage tools. Educational demo only, not for clinical use."""

import re

LEVELS = {
    1: ("IMMEDIATE", "resus_bay"),
    2: ("EMERGENT", "resus_bay"),
    3: ("URGENT", "main_ed"),
    4: ("LESS URGENT", "fast_track"),
    5: ("NON-URGENT", "fast_track"),
}

HOSPITAL_STATE = {
    "resus_bay": {"total_beds": 3, "occupied": 2,
                  "specialist": "Dr. Mehta (Cardiologist)", "specialist_status": "on_call"},
    "main_ed": {"total_beds": 12, "occupied": 9,
                "specialist": "Dr. Rao (Emergency Physician)", "specialist_status": "in_house"},
    "fast_track": {"total_beds": 6, "occupied": 2,
                   "specialist": "Dr. Iyer (General Physician)", "specialist_status": "in_house"},
}

# Decision point A -> ESI 1
ESI1_KEYWORDS = ("cardiac arrest", "not breathing", "stopped breathing", "no pulse",
                 "pulseless", "unresponsive", "unconscious")

# Decision point B -> ESI 2
ESI2_KEYWORDS = ("chest pain", "chest pressure", "stroke", "facial droop", "slurred speech",
                 "seizure", "difficulty breathing", "trouble breathing", "shortness of breath",
                 "severe pain", "confusion", "confused", "overdose", "heavy bleeding")

# Decision point C: how many resources (labs, imaging, IV fluids, IV meds) are needed
MANY_RESOURCES = ("abdominal pain", "fracture", "fever", "vomiting", "head injury",
                  "dehydration")                                       # -> ESI 3
ONE_RESOURCE = ("twisted ankle", "sprain", "laceration", "urinary")    # -> ESI 4
NO_RESOURCES = ("sore throat", "cough", "runny nose", "cold", "earache",
                "prescription refill")                                 # -> ESI 5


def _require_int(name: str, value: int, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def _match(text: str, keywords: tuple) -> str | None:
    for k in keywords:
        if re.search(r"\b" + re.escape(k) + r"\b", text):
            return k
    return None


def score_triage(
    age: int,
    sex: str,
    arrival: str,
    systolic_bp: int,
    diastolic_bp: int,
    heart_rate: int,
    spo2: int,
    chief_complaint: str,
) -> dict:
    """Assign an ESI triage level (1-5) to an adult emergency patient.

    Args:
        age: Age in years (18 or older).
        sex: "M", "F" or "other".
        arrival: "ambulance" or "walk-in".
        systolic_bp: Systolic blood pressure in mmHg.
        diastolic_bp: Diastolic blood pressure in mmHg.
        heart_rate: Heart rate in beats per minute.
        spo2: Oxygen saturation in percent.
        chief_complaint: Main complaint in plain words.
    """
    _require_int("age", age, 18, 120)
    _require_int("systolic_bp", systolic_bp, 40, 300)
    _require_int("diastolic_bp", diastolic_bp, 20, 200)
    _require_int("heart_rate", heart_rate, 20, 300)
    _require_int("spo2", spo2, 50, 100)
    # sex and arrival do not affect the ESI level; they are validated for the summary only
    if not isinstance(sex, str) or sex.strip().lower() not in ("m", "f", "male", "female", "other"):
        raise ValueError('sex must be "M", "F" or "other"')
    if not isinstance(arrival, str) or arrival.strip().lower() not in ("ambulance", "walk-in", "walk in"):
        raise ValueError('arrival must be "ambulance" or "walk-in"')
    if not isinstance(chief_complaint, str) or not chief_complaint.strip():
        raise ValueError("chief_complaint must be a non-empty string")

    text = " ".join(chief_complaint.lower().split())
    flags = []
    low_confidence = False

    if k := _match(text, ESI1_KEYWORDS):
        level = 1
        flags.append(f"lifesaving_intervention_needed: {k}")
    elif k := _match(text, ESI2_KEYWORDS):
        level = 2
        flags.append(f"high_risk_complaint: {k}")
    elif k := _match(text, MANY_RESOURCES):
        level = 3
        flags.append(f"many_resources_expected: {k}")
    elif k := _match(text, ONE_RESOURCE):
        level = 4
        flags.append(f"one_resource_expected: {k}")
    elif k := _match(text, NO_RESOURCES):
        level = 5
        flags.append(f"no_resources_expected: {k}")
    else:
        level = 3
        low_confidence = True
        flags.append("unrecognized_complaint: defaulted to ESI 3")

    # Decision point D: danger-zone vitals can move ESI 3 up to ESI 2
    if level == 3:
        danger = []
        if heart_rate > 100:
            danger.append(f"heart_rate {heart_rate} > 100")
        if spo2 < 92:
            danger.append(f"spo2 {spo2} < 92")
        if systolic_bp < 90 or systolic_bp > 180:  # demo rule, not part of the ESI danger zone
            danger.append(f"systolic_bp {systolic_bp} outside 90-180")
        if danger:
            level = 2
            flags.extend(f"danger_zone_vitals: {d}" for d in danger)

    label, department = LEVELS[level]
    return {
        "esi_level": level,
        "urgency_label": label,
        "routed_to": department,
        "triggered_flags": flags,
        "esi1_alert": level == 1,
        "low_confidence": low_confidence,
    }


def check_availability(esi_level: int) -> dict:
    """Check bed availability and the specialist for the department an ESI level routes to.

    Args:
        esi_level: The ESI level (1 to 5) returned by score_triage.
    """
    _require_int("esi_level", esi_level, 1, 5)
    state = HOSPITAL_STATE[LEVELS[esi_level][1]]
    return {
        "can_admit": state["total_beds"] - state["occupied"] > 0,
        "specialist": state["specialist"],
        "specialist_status": state["specialist_status"],
    }