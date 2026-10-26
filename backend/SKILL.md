# ER Triage

## Purpose
Assign an ESI triage level to an adult emergency patient and check bed and specialist availability. Educational demo only, not clinical guidance.

## Required inputs
age, sex, arrival, systolic_bp, diastolic_bp, heart_rate, spo2, chief_complaint

## Workflow
1. Request score_triage once.
2. After success, request check_availability once, using the esi_level returned by score_triage.
3. Write a short summary of both results in clear language.

## Constraints
Never diagnose. Never suggest medications or treatments.
Never guess missing input values. A vital that is not given is unknown, not normal.
Use only the values returned by the tools. Do not invent ESI levels, flags, bed counts or specialists.
Explain the ESI level using only triggered_flags. Do not comment on the patient's likely condition.
If esi1_alert is true, state "IMMEDIATE ESCALATION REQUIRED" first, before anything else.
If low_confidence is true, say the complaint was not recognized and a nurse must review it.
If can_admit is false, report clearly that the department has no free bed.
Request one tool per turn. Never repeat a completed tool.
State that this is an educational demo, not for clinical use.

## Summary format
One short paragraph: who the patient is (for example "45M arriving by ambulance"), the ESI level and urgency label, the flags that triggered it, the department, whether a bed is available, and the specialist and their status.

## Missing inputs and errors
Ask for missing inputs instead of inventing them.
Patients under 18 are not supported. Say so.
On a tool error, report it. Do not retry in the same run.