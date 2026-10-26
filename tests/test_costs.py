import costs


def fake_session(turns, per_call, pack=0.01, coach=0.01):
    trace = [{"event": "llm", "agent": "professor", "input": 1000, "cached": 600, "output": 50,
              "cost": per_call, "turn": t} for t in range(turns)]
    trace.append({"event": "llm", "agent": "coach", "input": 2000, "cached": 0, "output": 700, "cost": coach, "turn": turns})
    pack_usage = {"input_tokens": 1700, "cached_input_tokens": 0, "output_tokens": 900, "cost_usd": pack}
    return costs.session_summary(trace, pack_usage, turns)


def test_session_totals_and_cache_share():
    s = fake_session(4, 0.002)
    assert s["totals"]["calls"] == 6
    assert round(s["totals"]["cost"], 4) == 0.028
    assert s["totals"]["cached"] == 2400 and 0 < s["totals"]["cache_share"] < 1
    assert round(s["fixed_cost"], 4) == 0.02 and round(s["turn_cost"], 4) == 0.008


def test_projections_scale_from_measured_sessions():
    p = costs.projections([fake_session(4, 0.002), fake_session(6, 0.002)])
    rows = {r["scale"]: r for r in p["rows"]}
    avg = (0.028 + 0.032) / 2
    assert abs(rows["1 run (measured avg)"]["usd"] - avg) < 1e-4
    assert abs(rows["1 run (14 turns, est.)"]["usd"] - (0.02 + 0.002 * 14)) < 1e-4
    assert abs(rows["100 users / month"]["usd"] - round(100 * 12.9 * avg, 2)) < 0.01
    assert rows["10,000 users / month"]["sessions"] == 129000


def test_no_sessions_gives_empty_projection():
    assert costs.projections([])["rows"] == []
