# ✋ Hand Up!

*Raise your hand before the real class does.*

Hand Up! is a voice-first mock class discussion. Pick your course, and an AI professor (styled like
your real one) and 1–3 AI classmates run a case discussion in an isometric pixel classroom. You raise
your hand to speak, sometimes get cold-called, answer follow-ups out loud, and afterwards see how to
say every line better.

MGT 409 final project · Gawon Yi.

## Setup (fresh clone, under 10 minutes)

Requirements: Python 3.11+ and Chrome (for voice). There is no Node and no build step.

```bash
git clone https://github.com/gawonyi/hand-up.git
cd hand-up
python3 -m pip install -r requirements.txt
```

**API key.** Hand Up! reads `PORTKEY_API_KEY` from a `.env` file. It looks in the repo folder first,
then **one folder above**, so a `.env` placed next to the `hand-up/` folder works without copying:

```
your-folder/
  .env            ← PORTKEY_API_KEY=...   (works)
  hand-up/
    .env          ← or here (git-ignored)
```

See `.env.example`. Optional: `python3 scripts/check_model.py` makes one tiny call. It prints
token usage, shows which structured-output method works, and checks whether prompt caching hits.

**Run:**

```bash
python3 app.py
```

Then open **http://localhost:8000**.

**Use Chrome for voice; other browsers use typing mode.** Typing mode has full parity: the whole
class and the evaluation work without a microphone. If speech recognition is unavailable or fails,
Hand Up! switches to typing automatically and shows why.

## Try the demo

1. On Home, click **Try the demo**. This loads the fictional *Brightloaf Bakery* case
   (`samples/demo_case.md`, 2 pages + Exhibit 1), its 3 questions, and `samples/course_mgt411.json`.
   The professor style there is a short default drawn from the syllabus's participation and case-prep
   guidance; describe your own professor in **Edit course**.
2. Wait for "Pack ready" (≈10 s), tap your confidence (1–10), and click **Start class**.
3. Press **Space** or **✋ Hand Up!** to raise your hand. Answer when it's your turn (speak, or type),
   or press **Pass**. **End class** ends at any time.
4. Click **See my evaluation**. Your first session in a course is a baseline. Later sessions
   compare with the previous session only.

`/debug` is a plain typing-mode page that shows the state machine and the agent trace.

## Tests

```bash
python3 -m pytest -q
```

40 offline tests (no API calls) cover:

- **Integrity Gate.** A case file is blocked when the policy is not confirmed. The bundled demo
  passes via the allowlist. A modified demo file, or a copy of it uploaded by the user, is blocked.
- **Coach.** It refuses write-up requests.
- **Injection.** Text in materials or transcripts is treated as data.
- **Citations.** Unknown cited IDs are rejected and regenerated once.
- **Turn rules.** The starvation rule and its counter reset. No hands leads to one rephrase, then
  the fallback. Cold calls never come twice in a row and never target a classmate. A follow-up keeps
  the same speaker. Pass counts as a turn.
- **Budget.** Turn cap 14. Reaching $0.40 gives a normal end with evaluation. A reserve that is too
  small gives a budget end with zero model calls. The total never exceeds $0.50.
- **Cost projections.**

One live test runs the Pack Builder with injected text. It is skipped by default; run it with
`HANDUP_LIVE=1 python3 -m pytest -q`.

## How it works

| Agent | Kind | Job | Output (Pydantic) |
|---|---|---|---|
| Integrity Gate | plain Python | applies the course AI policy **before** any uploaded text leaves the machine | `GateResult` |
| Pack Builder | LLM | material → Session Pack with IDs (`F#`, `Q#`, facts like `S1-2a` with a source, `T#`) | `SessionPack` |
| Orchestrator | plain Python | turn-taking state machine, eligibility, cold call, starvation, no-hands fallback, caps, budget, end types | — |
| Professor | LLM | picks **only** from the eligible list; asks, follows up, rephrases, moves on, wraps up | `ProfMove` |
| Classmates ×1–3 | LLM | hand decisions in **one batched call** per turn; remarks citing pack IDs | `HandDecisions`, `Remark` |
| Coach | LLM | rubric, needs-work points with fixes, every line polished, 5–8 expressions | `Evaluation` |

The model is `gpt-6-luna` via the Portkey gateway with the OpenAI SDK, using structured outputs
(`chat.completions.parse`, with a `json_object` + Pydantic fallback). No sampling parameters are
sent.

**Turn states:**
`PROF_SPEAKING → HANDS_OPEN → SELECTING → SPEAKER_TURN → AFTER_ANSWER → (FOLLOW_UP | PROF_SPEAKING | NORMAL_END | BUDGET_ERROR_END)`.
The next step starts on the TTS end, error, or cancel event, or a safety timeout (estimated
duration + 3 s). In typing mode it starts right after the line is shown.

- **Cold call** applies to you only. Its probability comes from the professor's slider, and it never
  happens twice in a row.
- **Starvation rule.** If your hand was up and you were skipped twice, you are the only eligible
  speaker next. The counter resets when you are picked or lower your hand; it does not reset when
  the question changes.
- **No hands.** The professor rephrases once with a hint. If there are still no hands, the
  orchestrator picks you or a classmate ("No hands, so…").

**Two end types:**

- **Normal end** (turn cap 14, all questions done, End class, or $0.40 spent). The professor wraps
  up and the Coach evaluates, paid from a reserved $0.10.
- **Budget/error end** (model error, or the reserve can't cover the worst case). No model calls are
  made. You see the takeaways and your saved lines, and the Evaluation shows "Evaluation
  unavailable".

Before **every** call, the worst case (counted input tokens + max output × price) is checked
against the budget, so a session never exceeds **$0.50**.

## Tokens and cost

- Every model call is logged to `logs/runs.jsonl` with agent, input / cached / output tokens, cost,
  and latency. Prices are set in one place (`config.py`).
- In class, **Tokens & cost ▸** shows this turn, this session (by agent), and monthly projections
  for 1, 100, and 10,000 users (3 sessions/week). The projections are computed from measured
  sessions. `python3 costs.py` prints the same table.
- The same system prompt + Session Pack prefix comes first in every professor and classmate call,
  to make caching possible. This does not guarantee cache hits, so only measured
  `cached_tokens` are reported.
- The five cost cuts (shared prefix, batched hands, recent turns only, output caps, compact
  previous summary) can each be switched off on Home to compare cost and quality.
- Voice uses 0 model tokens.

## Safety and integrity

- **Course AI policy** has three states. *Not confirmed* (the default) blocks case files.
  *Allowed* needs a source note, which is the user's statement, not verified official approval.
  *Not allowed* uses only your own notes. The gate is plain code and runs before anything is sent
  to the model. A file uploaded as "slides" that looks like a teaching case is treated as a case.
- **Bundled demo exception.** The fictional demo case passes only because its SHA-256 hash is in
  `samples/allowlist.json` (`is_bundled_demo`). User uploads never get this exception, even if the
  bytes are identical. Every bypass is logged to `logs/gate.jsonl`.
- **No graded work.** Write-up requests are refused in code and never sent to the model to be
  "polished".
- **Prompt injection.** Materials and transcripts are wrapped in delimiters and treated as data,
  never as instructions.
- **Grounding.** Remarks and polished lines cite pack IDs; unknown IDs are rejected and regenerated
  once. **Limitation:** v1 only checks that cited IDs *exist*; checking whether the source really
  supports the sentence is limited.
- **Copyright.** Real course slides and cases stay local (`uploads/` and `cases/` are git-ignored).
  Only the fictional sample case is in the repo.

## Privacy

Hand Up! does not record, store, or send audio to its own server; it keeps only the text. The
browser's speech service (e.g., Google in Chrome) may process audio. The mic is on only during
your turn, with a visible "Listening…" indicator. WPM is approximate: words ÷ (speech end − speech
start).

## Project layout

```
app.py            FastAPI server + API          config.py   .env loading, prices, budget, caps
llm.py            Portkey client, budget, logs  schemas.py  Pydantic outputs
gate.py           Integrity Gate + allowlist    pack.py     Pack Builder, IDs, citation checks
orchestrator.py   turn-taking state machine     agents.py   Professor + Classmates
coach.py          evaluation                    costs.py    tokens & cost projections
static/           index.html, app.js, scene.js, voice.js, evaluation.js, app.css, img/
samples/          fictional demo case, questions, course profile, SHA-256 allowlist
scripts/check_model.py   tests/
```

## Known limits

- The gpt-6-luna prices in `config.py` are placeholders. Update them for exact dollar figures.
- Classmate remarks are capped at 50 words (the PRD allows 80) so a spoken turn takes about 15 s.
- Speech recognition quality depends on the browser; the Coach ignores obvious recognition errors.
- Comparison is with the previous session only. A running summary is out of scope for v1.
