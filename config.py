"""Settings for Hand Up!: .env loading, model, prices, budget, caps, cost-cut toggles."""
import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent

# .env from the repo folder first, then ONE folder above (graders put it there).
# A value already set (and non-empty) wins, so an empty key copied from
# .env.example does not hide the key in the folder above.
ENV_FILES = [ROOT / ".env", ROOT.parent / ".env"]
for _env in ENV_FILES:
    if _env.is_file():
        for _k, _v in dotenv_values(_env).items():
            if _v and not os.environ.get(_k):
                os.environ[_k] = _v

PORTKEY_BASE_URL_DEFAULT = "https://api.portkey.ai/v1"
MODEL = "gpt-6-luna"  # course key allows only this model

# USD per 1M tokens. One place to change prices.
# TODO(user): confirm gpt-6-luna prices; these are conservative placeholders.
PRICES = {
    "input": 1.25,
    "cached_input": 0.125,
    "output": 10.00,
}

# Budget (PRD §6 rule 9, §10)
HARD_CAP_USD = 0.50
DISCUSSION_BUDGET_USD = 0.40
RESERVE_USD = HARD_CAP_USD - DISCUSSION_BUDGET_USD  # wrap-up + evaluation

# Turn rules
TURN_CAP = 14
MAX_RETRIES = 2
COLD_CALL_BASE_RATE = 0.083  # × slider level 1–5 (level 3 ≈ 25% per question)

# Output caps (max_completion_tokens per agent; word caps go in the prompts)
MAX_OUTPUT_TOKENS = {
    "pack_builder": 2000,
    "professor": 160,    # ≤ 60 words + JSON
    "hands": 200,
    "classmate": 220,    # ≤ 80 words + JSON
    "coach": 1800,
    "check_model": 60,
}
WORD_CAPS = {"professor": 60, "classmate": 80}

# Cost-cut toggles (PRD §10); the UI can flip them per session
COST_CUTS = {
    "shared_prefix": True,      # identical system prompt + pack first (cache-friendly)
    "batched_hands": True,      # one hand-decision call per turn
    "recent_turns_only": True,  # send only the last N turns
    "output_caps": True,
    "compact_prev_summary": True,
}
RECENT_TURNS = 8

LOG_DIR = ROOT / "logs"
RUNS_LOG = LOG_DIR / "runs.jsonl"
DATA_DIR = ROOT / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SAMPLES_DIR = ROOT / "samples"
UPLOADS_DIR = ROOT / "uploads"


def cost_usd(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    uncached = max(input_tokens - cached_tokens, 0)
    return (
        uncached * PRICES["input"]
        + cached_tokens * PRICES["cached_input"]
        + output_tokens * PRICES["output"]
    ) / 1_000_000


def worst_case_usd(input_tokens: int, max_output_tokens: int) -> float:
    """Pre-check cost: all input uncached, full output cap used."""
    return cost_usd(input_tokens, 0, max_output_tokens)
