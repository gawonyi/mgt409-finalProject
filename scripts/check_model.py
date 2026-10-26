"""Check the Portkey + gpt-6-luna setup.

1. tiny structured call with client.chat.completions.parse()
2. the same with response_format={"type": "json_object"} + Pydantic validation
3. two calls with an identical ~1.3k-token prefix to see if cached_tokens > 0

Prints token usage (input, cached, output) for every call and which method works.
Run: python3 scripts/check_model.py      (cost: well under $0.01)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

import config  # noqa: E402  (loads .env)
import llm  # noqa: E402


class Ping(BaseModel):
    ok: bool
    word: str


MSGS = [
    {"role": "system", "content": "You are a health check. Answer briefly."},
    {"role": "user", "content": 'Return ok=true and word="hello".'},
]
MAX_OUT = config.MAX_OUTPUT_TOKENS["check_model"]


def run(label: str, method: str, messages=MSGS):
    t0 = time.time()
    try:
        resp, parsed, err = llm._call_once(messages, Ping, MAX_OUT, method)
    except Exception as e:
        print(f"[{label}] FAILED  {llm._error_text(e)}")
        return None
    inp, cached, out = llm._usage(resp)
    cost = config.cost_usd(inp, cached, out)
    llm.log_run({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": "check_model", "agent": "check_model",
        "method": method, "attempt": 0, "input_tokens": inp, "cached_input_tokens": cached,
        "output_tokens": out, "cost_usd": round(cost, 6),
        "latency_s": round(time.time() - t0, 3), "ok": parsed is not None,
    })
    status = "OK" if parsed is not None else f"BAD OUTPUT ({err})"
    print(f"[{label}] {status}  input={inp} cached={cached} output={out}  "
          f"${cost:.6f}  {time.time() - t0:.2f}s  -> {parsed}")
    return cached if parsed is not None else None


def main():
    try:
        llm.get_client()
    except llm.LLMError as e:
        print(e)
        sys.exit(1)
    print(f"model={config.MODEL}  .env searched: {[str(p) for p in config.ENV_FILES]}\n")

    parse_ok = run("1 parse()", "parse") is not None
    json_ok = run("2 json_object", "json_object") is not None

    method = "parse" if parse_ok else "json_object" if json_ok else None
    cache_note = "skipped (no working method)"
    if method:
        # Caching usually needs >= 1024 identical prefix tokens.
        prefix = "Session Pack (fixed prefix for cache test). " + " ".join(
            f"F{i}: segment customers by needs, behavior and benefits." for i in range(150)
        )
        msgs = [{"role": "system", "content": prefix}, *MSGS]
        print(f"\nprefix ≈ {llm.count_tokens(msgs)} tokens")
        run("3a cache warm", method, msgs)
        cached = run("3b cache hit?", method, msgs)
        cache_note = (
            f"YES (cached_tokens={cached})" if cached else "NO cached tokens measured on this setup"
        )

    print("\n=== Result ===")
    print(f"parse():      {'works' if parse_ok else 'rejected'}")
    print(f"json_object:  {'works' if json_ok else 'rejected'}")
    print(f"USE METHOD:   {method or 'NONE — see errors above'}")
    print(f"prompt cache: {cache_note}")
    print(f"log:          {config.RUNS_LOG}")
    sys.exit(0 if method else 1)


if __name__ == "__main__":
    main()
