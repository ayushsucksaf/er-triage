# ER Triage

An ER triage assistant. You describe a patient in plain words, and it gives back an ESI triage level, where to send them, and whether there's a bed and a specialist.

The idea is simple: a local language model reads the text and writes the summary, and plain Python makes every actual decision. The model never picks the triage level.

This is an educational demo. It is not medical software and should not be used for real patients.

## How it works

1. You type something like: `45M, ambulance, BP 180/110, HR 122, SpO2 96, chest pain radiating to left arm`
2. A local model (running in Ollama) pulls out the details and asks for the `score_triage` tool.
3. Python scores the patient using simplified ESI rules and returns the level along with the reasons (`triggered_flags`).
4. The model then asks for `check_availability`, and Python looks up beds and the specialist on call.
5. The model writes a short summary. The final result is the tool output plus that summary.

The host in `app.py` keeps the model on a short leash:

- Only the two registered tools can be called.
- Tools must be called in order: score first, then availability.
- Arguments are checked against the tool's signature before anything runs.
- Errors stop the run. There are no retries.
- There's a hard limit of 5 steps.

`SKILL.md` holds the behaviour rules the model follows: no diagnosing, no treatment advice, no guessing missing values, and so on.

## Project layout

```
er-triage/
├── backend/
│   ├── app.py            agent host and tool dispatch loop
│   ├── tools.py          triage scoring and availability check
│   ├── SKILL.md          behaviour rules for the model
│   ├── api.py            FastAPI wrapper
│   └── requirements.txt
├── frontend/static
│   └── index.html        single-page UI
├── .gitignore
├── LICENSE
└── README.md
```

## Setup

You need Python 3.10+ and Ollama.

Install Ollama (Linux):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e4b
```

On macOS or Windows, grab the installer from ollama.com/download instead.

Then set up the Python side:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The model name lives at the top of `app.py` (`MODEL_NAME`). Change it there if you want to try a different one. It needs to support tool calling.

## Run

Make sure the Ollama server is running, then from the `backend` folder:

```bash
python app.py
```

That runs one sample patient and prints the result. To try your own, edit the `query` at the bottom of `app.py`.

Then open the given link from the terminal using `click + link`. It opens the local host on your default browser.

## Example output

```json
{
  "esi_level": 2,
  "urgency_label": "EMERGENT",
  "routed_to": "resus_bay",
  "triggered_flags": ["high_risk_complaint: chest pain"],
  "esi1_alert": false,
  "low_confidence": false,
  "can_admit": true,
  "specialist": "Dr. Mehta (Cardiologist)",
  "specialist_status": "on_call",
  "summary": "The patient, a 45M arriving by ambulance, has been assigned an ESI Level 2 (EMERGENT) and routed to the resus_bay..."
}
```

If something is missing or invalid, you get `{"error": "..."}` instead.

## Good to know

- Adults only. Anyone under 18 is rejected.
- The scoring is a simplified take on the published ESI handbook. The keyword lists and the resource estimates are demo assumptions, not clinical rules.
- Blood pressure is a demo rule of ours (systolic under 90 or over 180 can bump an ESI 3 up to 2). The real ESI danger zone doesn't use it.
- Complaint matching is plain keywords, so unusual phrasing may come back as low confidence.
- Hospital beds and staff are hard-coded in `tools.py`.

## Ideas if you want to contribute

- More complaint keywords and resource estimates
- Pediatric vital sign thresholds
- A nicer frontend

## License

See `LICENSE`.