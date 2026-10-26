# CLAUDE.md — Hand Up! (MGT 409 final project)

Hand Up! is a voice-first mock class-discussion app: an AI professor and AI classmates
run a case/lecture discussion in an isometric pixel classroom; the student raises a hand
to speak, gets cold-called sometimes, and receives an evaluation afterwards.
Solo project by Gawon Yi (GitHub: gawonyi). **Deadline: Mon 2026-10-26, 6:00 PM ET.**

## Source of truth (read in this order; earlier wins on conflict)
1. `PRD.md` (v4.1) — features, turn-taking rules (§6), voice (§7), safety (§11), scope (§13)
2. `DESIGN.md` — look and feel; `static/img/layout.json`; `design/scene_preview.png`
3. `BUILD_PROMPT.md` — hard rules and build order
4. Flowcharts: `flowchart_user.png`, `flowchart_turn.png`, `flowchart_data.png`

This project is NOT under `Documents/codex`, so that folder's AGENTS.md does not apply,
except for the model setup copied below. In particular, ignore its dark purple & mint
theme: Hand Up! uses the light-sky / cream theme in DESIGN.md.

## Model setup (copied from the course workspace — do not change)
All model calls go through the Portkey gateway with the **OpenAI Python SDK**.

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["PORTKEY_API_KEY"],
    base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"),
    default_headers={"x-portkey-api-key": os.environ["PORTKEY_API_KEY"]},
)
MODEL = "gpt-6-luna"   # course key allows only this model; plain name, no "@openai/" prefix
```

- **Never send `temperature`, `top_p` or other sampling params** — the gateway returns 400.
- If tool calling is used on `/chat/completions`, set `reasoning_effort="none"`
  (gpt-6-luna on Portkey only allows tool calls that way).
- Structured outputs: try `client.chat.completions.parse(..., response_format=PydanticModel)`
  in `scripts/check_model.py` first. If the gateway rejects it, fall back to
  `response_format={"type": "json_object"}` + Pydantic validation (max 2 retries).
- Wrap every call in try/except and surface the real error body; never invent a fallback answer.
- Read `usage.prompt_tokens`, `usage.prompt_tokens_details.cached_tokens`,
  `usage.completion_tokens` from every response and log them (PRD §10).

## Keys and .env
- Key name: `PORTKEY_API_KEY` (optional `OPENAI_API_KEY`, unused).
- Load `.env` from the repo folder first, then **one folder above** (the graders put it there).
  For local dev the user can copy their key into `.env` in the repo folder (git-ignored).
- Never print, log, or commit a key. Commit `.env.example` with empty values.

## Running (the user is on macOS, runs commands in the VS Code terminal)
- `python3 -m pip install -r requirements.txt`, then `python3 app.py` → http://localhost:8000
- Tests: `python3 -m pytest -q`
- Voice works best in Chrome; other browsers use typing mode (full parity required).

## Assets (already made — reuse, don't regenerate)
- `static/img/room.png` (desk removed; `room_original.png` is the untouched version)
- `static/img/sprites/*.png` — `<name>_back.png` (scene, flip horizontally), `<name>_front.png`
  (dialogue portraits), `prof.png`, `hand_icon.png`, `alert_icon.png`
- `static/img/layout.json` — viewport crop, chair anchors, scales, default seating;
  me = `brunette` in chair `c5`
- `design/mockup.html` — UI tokens, dialogue box, history drawer (its classroom drawing is
  only the no-image fallback)

## Working rules
- Follow the build order in BUILD_PROMPT.md and stop for the user's OK after each step.
  Time is tight: keep step summaries short.
- Typing mode end-to-end first; voice is a layer on top.
- Real course cases/slides stay local (`cases/`, `uploads/` are git-ignored). Only the
  fictional sample case goes into `samples/`.
- Do not add features beyond PRD §13 "Must" items.
- Git: repo `gawonyi/mgt409-finalProject`, public. Commit only when the user asks.
