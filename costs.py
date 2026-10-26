"""Tokens & cost: this turn, this session, and projections from MEASURED usage (PRD §10).

Sources: each saved session file (data/sessions/*.json) holds its agent trace (every model
call's input / cached / output tokens and cost) plus the Pack Builder call. Every call is also
in logs/runs.jsonl. Projections use the average measured completed session.

Run `python3 costs.py` to print the report table.
"""
import json
import statistics

import config

SESSIONS_PER_MONTH = 3 * 4.3  # 3 sessions/week × 4.3 weeks
SCALES = [("1 user / month", 1), ("100 users / month", 100), ("10,000 users / month", 10_000)]
FIXED_AGENTS = {"pack_builder", "coach"}  # once per session; everything else scales with turns


def _calls(trace: list[dict], pack_usage: dict | None) -> list[dict]:
    calls = [{"agent": t["agent"], "input": t["input"], "cached": t["cached"], "output": t["output"],
              "cost": t["cost"], "turn": t.get("turn", 0)} for t in trace if t.get("event") == "llm"]
    if pack_usage:
        calls.insert(0, {"agent": "pack_builder", "input": pack_usage["input_tokens"],
                         "cached": pack_usage["cached_input_tokens"], "output": pack_usage["output_tokens"],
                         "cost": pack_usage["cost_usd"], "turn": 0})
    return calls


def totals(calls: list[dict]) -> dict:
    t = {k: sum(c[k] for c in calls) for k in ("input", "cached", "output")}
    t["cost"] = round(sum(c["cost"] for c in calls), 6)
    t["calls"] = len(calls)
    t["cache_share"] = round(t["cached"] / t["input"], 3) if t["input"] else 0.0
    return t


def session_summary(trace: list[dict], pack_usage: dict | None, turns: int) -> dict:
    calls = _calls(trace, pack_usage)
    fixed = [c for c in calls if c["agent"] in FIXED_AGENTS]
    per_turn = [c for c in calls if c["agent"] not in FIXED_AGENTS]
    return {"totals": totals(calls), "turns": turns,
            "fixed_cost": sum(c["cost"] for c in fixed), "turn_cost": sum(c["cost"] for c in per_turn),
            "by_agent": {a: totals([c for c in calls if c["agent"] == a]) for a in sorted({c["agent"] for c in calls})}}


def completed_sessions() -> list[dict]:
    """Measured sessions, including archived test runs (data/sessions_archive/): their usage is real
    even though they are excluded from the previous-session comparison."""
    out = []
    files = [p for d in (config.SESSIONS_DIR, config.SESSIONS_DIR.parent / "sessions_archive") if d.exists()
             for p in sorted(d.glob("*.json"))]
    for p in files:
        try:
            d = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        snap = d.get("snapshot", {})
        if not d.get("ended_at") or snap.get("end_type") != "normal":
            continue
        out.append(session_summary(snap.get("trace", []), d.get("pack_usage"), snap.get("turn", 0)))
    return out


def projections(sessions: list[dict] | None = None) -> dict:
    sessions = completed_sessions() if sessions is None else sessions
    if not sessions:
        return {"n_sessions": 0, "rows": [], "note": "No completed sessions measured yet."}
    avg = statistics.mean(s["totals"]["cost"] for s in sessions)
    tok = {k: round(statistics.mean(s["totals"][k] for s in sessions)) for k in ("input", "cached", "output")}
    # a full 14-turn session: fixed calls + measured per-turn cost × 14
    per_turn = [s["turn_cost"] / s["turns"] for s in sessions if s["turns"]]
    fixed = statistics.mean(s["fixed_cost"] for s in sessions)
    run14 = fixed + (statistics.mean(per_turn) * config.TURN_CAP if per_turn else 0)
    rows = [{"scale": "1 run (measured avg)", "sessions": 1, "usd": round(avg, 4), **tok},
            {"scale": "1 run (14 turns, est.)", "sessions": 1, "usd": round(min(run14, config.HARD_CAP_USD), 4)}]
    for label, users in SCALES:
        n = users * SESSIONS_PER_MONTH
        rows.append({"scale": label, "sessions": round(n), "usd": round(n * avg, 2),
                     "usd_14_turns": round(n * min(run14, config.HARD_CAP_USD), 2)})
    cache_share = round(sum(s["totals"]["cached"] for s in sessions) / max(1, sum(s["totals"]["input"] for s in sessions)), 3)
    return {
        "n_sessions": len(sessions), "rows": rows, "cache_share": cache_share,
        "avg_turns": round(statistics.mean(s["turns"] for s in sessions), 1),
        "note": (f"From {len(sessions)} measured session(s); {SESSIONS_PER_MONTH:.1f} sessions per user per month. "
                 f"Measured cache share {cache_share:.0%} of input tokens (not guaranteed). At 10,000 users "
                 f"(~{round(10_000 * SESSIONS_PER_MONTH / 30):,} sessions/day) the gateway's rate limits, not cost, "
                 "become the constraint; every session stays under the $0.50 hard cap."),
        "prices_per_1m": config.PRICES,
    }


if __name__ == "__main__":
    pr = projections()
    print(pr["note"])
    print(f"{'Scale':<26}{'Sessions':>10}{'$ (measured)':>15}{'$ (14 turns)':>15}")
    for r in pr["rows"]:
        print(f"{r['scale']:<26}{r['sessions']:>10}{r['usd']:>15}{r.get('usd_14_turns', ''):>15}")
