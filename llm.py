"""Model access: Portkey client, structured output, budget pre-check, run logging."""
import json
import os
import time
from datetime import datetime, timezone
from typing import Literal, TypeVar

from pydantic import BaseModel, ValidationError

import config

T = TypeVar("T", bound=BaseModel)
Method = Literal["parse", "json_object"]

# "auto" tries parse() and falls back to json_object once on a 400.
# check_model.py (2026-10-26): parse() and json_object both work on Portkey;
# prompt cache hits (1880/1883 tokens on the 2nd identical-prefix call).
STRUCTURED_METHOD: Literal["auto", "parse", "json_object"] = "auto"
_working_method: Method | None = None


class LLMError(Exception):
    """Model call failed; message carries the real error body (never a made-up answer)."""


class BudgetExceeded(Exception):
    """Worst-case cost of the next call does not fit the budget."""


_client = None


def get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        key = os.environ.get("PORTKEY_API_KEY")
        if not key:
            raise LLMError(
                "PORTKEY_API_KEY is not set. Put it in .env in the repo folder or in the folder above."
            )
        _client = OpenAI(
            api_key=key,
            base_url=os.getenv("PORTKEY_BASE_URL") or config.PORTKEY_BASE_URL_DEFAULT,
            default_headers={"x-portkey-api-key": key},
        )
    return _client


# ---------- token counting (for the worst-case pre-check) ----------
_enc = None


def count_tokens(messages: list[dict]) -> int:
    global _enc
    text = "".join(str(m.get("content", "")) for m in messages)
    try:
        if _enc is None:
            import tiktoken

            _enc = tiktoken.get_encoding("o200k_base")
        n = len(_enc.encode(text))
    except Exception:
        n = len(text) // 3  # conservative fallback if the encoding cannot load
    return n + 4 * len(messages) + 16


# ---------- budget ----------
class Budget:
    """Per-session spend. Discussion calls stop at $0.40; reserve calls may use up to $0.50."""

    def __init__(self):
        self.spent = 0.0

    def check(self, worst_usd: float, phase: Literal["discussion", "reserve"]) -> None:
        limit = config.DISCUSSION_BUDGET_USD if phase == "discussion" else config.HARD_CAP_USD
        if self.spent + worst_usd > limit:
            raise BudgetExceeded(
                f"{phase} call needs up to ${worst_usd:.4f}; spent ${self.spent:.4f} of ${limit:.2f}"
            )

    def add(self, usd: float) -> None:
        self.spent += usd


# ---------- logging ----------
def _usage(resp) -> tuple[int, int, int]:
    u = getattr(resp, "usage", None)
    if u is None:
        return 0, 0, 0
    details = getattr(u, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    return u.prompt_tokens or 0, cached, u.completion_tokens or 0


def log_run(record: dict) -> None:
    config.LOG_DIR.mkdir(exist_ok=True)
    with open(config.RUNS_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


def _error_text(e: Exception) -> str:
    body = getattr(e, "body", None)
    status = getattr(e, "status_code", None)
    if body is not None:
        return f"{type(e).__name__} {status or ''}: {json.dumps(body) if not isinstance(body, str) else body}"
    return f"{type(e).__name__}: {e}"


# ---------- structured call ----------
def _call_once(messages, schema: type[T], max_out: int, method: Method):
    """Return (response, parsed or None, error text or None). API errors propagate."""
    client = get_client()
    common = dict(
        model=config.MODEL,
        max_completion_tokens=max_out,
        reasoning_effort="none",
    )
    if method == "parse":
        resp = client.chat.completions.parse(messages=messages, response_format=schema, **common)
        msg = resp.choices[0].message
        if msg.parsed is None:
            return resp, None, f"no parsed output (refusal={msg.refusal!r}, finish={resp.choices[0].finish_reason})"
        return resp, msg.parsed, None
    # json_object fallback: schema goes into the prompt, Pydantic validates
    hint = {
        "role": "system",
        "content": "Reply with ONE JSON object only, matching this JSON schema:\n"
        + json.dumps(schema.model_json_schema()),
    }
    resp = client.chat.completions.create(
        messages=[*messages, hint], response_format={"type": "json_object"}, **common
    )
    try:
        return resp, schema.model_validate_json(resp.choices[0].message.content or ""), None
    except ValidationError as e:
        return resp, None, f"invalid structured output: {e}"


def call_structured(
    agent: str,
    messages: list[dict],
    schema: type[T],
    *,
    max_out: int | None = None,
    budget: Budget | None = None,
    phase: Literal["discussion", "reserve"] = "discussion",
    session_id: str | None = None,
) -> tuple[T, dict]:
    """Return (parsed output, usage record). Raises LLMError / BudgetExceeded."""
    global _working_method
    max_out = max_out or config.MAX_OUTPUT_TOKENS.get(agent, 300)
    worst = config.worst_case_usd(count_tokens(messages), max_out)

    last_err = "unknown error"
    for attempt in range(config.MAX_RETRIES + 1):
        if budget is not None:
            budget.check(worst, phase)  # before EVERY call, retries included
        method: Method = _working_method or (
            "parse" if STRUCTURED_METHOD in ("auto", "parse") else "json_object"
        )
        t0 = time.time()
        try:
            resp, parsed, err = _call_once(messages, schema, max_out, method)
        except Exception as e:  # openai.APIStatusError, network errors, parse() validation
            last_err = _error_text(e)
            status = getattr(e, "status_code", None)
            if method == "parse" and STRUCTURED_METHOD == "auto" and status == 400:
                _working_method = "json_object"  # gateway rejected parse(); switch once
            elif status is not None and status < 500 and status != 429 and status != 400:
                raise LLMError(last_err) from e
            continue
        latency = time.time() - t0

        inp, cached, out = _usage(resp)
        cost = config.cost_usd(inp, cached, out)
        if budget is not None:
            budget.add(cost)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": session_id,
            "agent": agent,
            "method": method,
            "attempt": attempt,
            "input_tokens": inp,
            "cached_input_tokens": cached,
            "output_tokens": out,
            "cost_usd": round(cost, 6),
            "latency_s": round(latency, 3),
            "ok": parsed is not None,
        }
        log_run(record)
        if parsed is not None:
            _working_method = method
            return parsed, record
        last_err = err
    raise LLMError(f"{agent}: failed after {config.MAX_RETRIES + 1} attempts: {last_err}")
