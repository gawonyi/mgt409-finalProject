"""Turn-taking rules (PRD §6) and budget end types, with a fake agents object (no model calls)."""
import llm
import orchestrator as orc
from orchestrator import ME, Orchestrator, make_classmates
from schemas import PlainItem, ProfMove, SessionPack, SourcedItem


def make_pack(n_questions=5):
    return SessionPack(
        frameworks=[SourcedItem(id="F1", text="STP", source="case p.1")],
        questions=[PlainItem(id=f"Q{i}", text=f"Question {i}?") for i in range(1, n_questions + 1)],
        facts=[SourcedItem(id="S1-1a", text="Margin fell to 7.4%", source="case p.1")],
        takeaways=[PlainItem(id="T1", text="Segment by need")],
    )


class FixedRng:
    def __init__(self, value=0.0):
        self.value = value

    def random(self):
        return self.value

    def choice(self, seq):
        return seq[0]


class FakeAgents:
    """Scriptable stand-in for LLMAgents. Every method 'costs' `cost` through the real Budget."""

    def __init__(self, hands=None, pick=None, moves=None, cost=0.001, reserve=0.01, fail_on=None):
        self.hands_fn = hands or (lambda o: {})
        self.pick_fn = pick or (lambda o, eligible: eligible[0])
        self.moves = list(moves or [])
        self.cost, self.reserve = cost, reserve
        self.fail_on = fail_on
        self.calls: list[str] = []

    def _pay(self, o, name, phase="discussion"):
        if self.fail_on == name:
            raise llm.LLMError("simulated 500 from gateway")
        o.budget.check(self.cost, phase)
        o.budget.add(self.cost)
        self.calls.append(name)

    def hands(self, o):
        self._pay(o, "hands")
        return self.hands_fn(o)

    def select(self, o, eligible):
        self._pay(o, "select")
        return self.pick_fn(o, eligible), "Go ahead."

    def rephrase(self, o):
        self._pay(o, "rephrase")
        return "Let me put it another way. Hint: think about [F1]."

    def next_move(self, o, allowed):
        self._pay(o, "next_move")
        action = self.moves.pop(0) if self.moves else "next_question"
        return ProfMove(action=action, text="Probe: why?" if action == "follow_up" else "Good.")

    def remark(self, o, cid):
        self._pay(o, "remark")
        return f"{cid} says something [F1].", ["F1"]

    def wrap_up(self, o):
        self._pay(o, "wrap_up", phase="reserve")
        return "Today we learned [T1]. Thanks."

    def reserve_needed(self, o):
        return self.reserve


def new(agents, roles=("consultant", "skeptic"), sliders=None, rng=None, n_questions=5):
    o = Orchestrator("t", make_pack(n_questions), make_classmates(list(roles)), agents,
                     sliders={"cold_call": 0, "follow_up_pressure": 3, **(sliders or {})},
                     rng=rng or FixedRng(0.99))
    o.start()
    return o


def step(o, answer="My answer."):
    """Advance the class by one wait point."""
    if o.waiting in ("audio", "hands"):
        o.act("advance")
    elif o.waiting == "me":
        o.act("answer", answer)


def run_until(o, cond, limit=200):
    for _ in range(limit):
        if cond(o) or o.ended:
            return
        step(o)


def call_ons(o):
    return [l for l in o.lines if l.kind == "call_on"]


# ---------- starvation ----------
def test_starvation_rule_and_counter_not_reset_by_new_question():
    everyone = lambda o: {c.id: True for c in o.classmates}
    never_me = lambda o, eligible: next(e for e in eligible if e != ME)
    a = FakeAgents(hands=everyone, pick=never_me)
    o = new(a)
    o.act("raise")
    run_until(o, lambda o: o.waiting == "hands")
    o.act("advance")  # Q1: skipped once
    assert o.skip_count == 1
    run_until(o, lambda o: o.waiting == "hands" and o.q_index == 1)
    assert o.skip_count == 1  # new question does NOT reset the counter
    o.act("advance")  # Q2: skipped twice
    assert o.skip_count == 2
    run_until(o, lambda o: o.waiting == "hands" and o.q_index == 2)
    selects_before = a.calls.count("select")
    o.act("advance")  # Q3: I am the only eligible candidate
    assert o.flags.get("starvation") and o.speaker == ME
    assert a.calls.count("select") == selects_before  # no professor choice needed
    assert o.skip_count == 0 and not o.my_hand  # reset when picked


def test_skip_counter_resets_when_i_lower_my_hand():
    a = FakeAgents(hands=lambda o: {c.id: True for c in o.classmates},
                   pick=lambda o, el: next(e for e in el if e != ME))
    o = new(a)
    o.act("raise")
    run_until(o, lambda o: o.waiting == "hands")
    o.act("advance")
    assert o.skip_count == 1
    o.act("lower")
    assert o.skip_count == 0 and not o.my_hand


# ---------- no hands ----------
def test_no_hands_rephrase_once_then_fallback():
    a = FakeAgents()  # nobody raises; cold-call slider 0
    o = new(a)
    run_until(o, lambda o: o.waiting == "hands")
    o.act("advance")
    assert o.lines[-1].kind == "rephrase" and a.calls.count("rephrase") == 1
    run_until(o, lambda o: o.waiting == "hands")
    o.act("advance")
    assert o.flags.get("no_hands")
    assert o.lines[-1].kind == "call_on" and o.lines[-1].text.startswith("No hands, so…")
    assert a.calls.count("rephrase") == 1  # only once per question
    assert o.speaker in [ME] + [c.id for c in o.classmates]


# ---------- cold call ----------
def test_cold_call_targets_me_only_and_never_twice_in_a_row():
    a = FakeAgents(hands=lambda o: {c.id: True for c in o.classmates})
    o = new(a, sliders={"cold_call": 5}, rng=FixedRng(0.0), n_questions=8)  # every roll hits
    run_until(o, lambda o: o.turn >= 7)
    cold = [l.meta["reason"] == "cold_call" for l in call_ons(o)]
    assert any(cold)
    assert all(l.meta["target"] == ME for l in call_ons(o) if l.meta["reason"] == "cold_call")
    assert not any(x and y for x, y in zip(cold, cold[1:]))  # never twice in a row
    assert o.stats["cold_calls"] == sum(cold)


def test_no_cold_call_when_my_hand_is_up_or_slider_off():
    a = FakeAgents(hands=lambda o: {c.id: True for c in o.classmates})
    o = new(a, sliders={"cold_call": 0}, rng=FixedRng(0.0))
    run_until(o, lambda o: o.turn >= 3)
    assert not any(l.meta["reason"] == "cold_call" for l in call_ons(o))


# ---------- selection ----------
def test_professor_can_only_pick_from_eligible_list():
    a = FakeAgents(hands=lambda o: {"cm1": True, "cm2": True}, pick=lambda o, el: "cm9")
    o = new(a)
    run_until(o, lambda o: o.waiting == "hands")
    o.act("advance")
    assert o.speaker in ("cm1", "cm2")
    assert any(t["event"] == "invalid_pick_replaced" for t in o.trace)


# ---------- follow-up ----------
def test_follow_up_keeps_the_same_speaker_without_hands():
    a = FakeAgents(hands=lambda o: {"cm2": True}, moves=["follow_up"])
    o = new(a, sliders={"follow_up_pressure": 3})
    run_until(o, lambda o: o.turn == 1)
    assert o.speaker == "cm2"
    hands_calls = a.calls.count("hands")
    run_until(o, lambda o: o.turn == 2)
    remarks = [l for l in o.lines if l.kind == "remark"]
    assert [l.speaker for l in remarks] == ["cm2", "cm2"]
    assert [l.kind for l in o.lines if l.kind in ("follow_up", "call_on")][-1] == "follow_up"
    assert a.calls.count("hands") == hands_calls  # no hand-raise, no selection


def test_follow_up_not_allowed_when_slider_gives_zero():
    a = FakeAgents(hands=lambda o: {"cm1": True}, moves=["follow_up", "follow_up"])
    o = new(a, sliders={"follow_up_pressure": 1})
    run_until(o, lambda o: o.turn == 2)
    assert not any(l.kind == "follow_up" for l in o.lines)


def test_pass_counts_as_turn_and_professor_moves_on():
    a = FakeAgents(moves=["follow_up"])
    o = new(a, sliders={"cold_call": 5}, rng=FixedRng(0.0))
    run_until(o, lambda o: o.waiting == "me")
    o.act("pass")
    assert o.turn == 1 and o.lines[-1].kind == "ask" and o.q_index == 1
    assert o.lines[-2].kind == "pass"


# ---------- ends ----------
def test_turn_cap_ends_normally_with_wrap_up():
    a = FakeAgents(hands=lambda o: {"cm1": True}, moves=["next_question"] * 30)
    o = new(a, n_questions=30)
    run_until(o, lambda o: False)
    assert o.turn == 14 and o.end_type == "normal" and o.state == orc.NORMAL_END
    assert o.end_reason == "turn cap" and a.calls[-1] == "wrap_up"


def test_discussion_budget_reached_gives_normal_end_with_wrap_up():
    a = FakeAgents(hands=lambda o: {"cm1": True}, cost=0.001)
    o = new(a)
    o.budget.spent = 0.3995  # next discussion call would cross $0.40
    run_until(o, lambda o: False)
    assert o.end_type == "normal" and o.state == orc.NORMAL_END
    assert "0.40" in o.end_reason and a.calls[-1] == "wrap_up"
    assert o.budget.spent <= 0.50


def test_reserve_too_small_gives_budget_end_with_zero_model_calls():
    a = FakeAgents(reserve=0.10)
    o = new(a)
    o.budget.spent = 0.45
    calls_before = len(a.calls)
    o.act("end")
    assert o.state == orc.BUDGET_ERROR_END and o.end_type == "budget_error"
    assert len(a.calls) == calls_before  # no model calls
    snap = o.snapshot()
    assert snap["takeaways"] and snap["waiting"] == "end"
    o.act("advance")
    assert len(a.calls) == calls_before


def test_model_error_gives_budget_error_end():
    a = FakeAgents(fail_on="hands")
    o = new(a)
    o.act("advance")
    assert o.state == orc.BUDGET_ERROR_END and "model error" in o.end_reason


def test_end_class_button_gives_normal_end():
    a = FakeAgents()
    o = new(a)
    o.act("end")
    assert o.state == orc.WRAP_UP and o.lines[-1].kind == "wrap_up"
    o.act("advance")
    assert o.state == orc.NORMAL_END and o.end_reason == "end_class"


def test_total_never_exceeds_hard_cap():
    for cost in (0.007, 0.013, 0.031, 0.049):
        a = FakeAgents(hands=lambda o: {"cm1": True, "cm2": True}, cost=cost, reserve=cost,
                       moves=["follow_up", "next_question"] * 20)
        o = new(a, n_questions=20)
        run_until(o, lambda o: False, limit=500)
        assert o.ended
        assert o.budget.spent <= 0.50 + 1e-9
        assert sum(1 for c in a.calls if c != "wrap_up") * cost <= 0.40 + 1e-9


def test_stale_advance_is_ignored():
    a = FakeAgents()
    o = new(a)
    n = len(o.lines)
    o.act("end")  # wrap-up line appended while the client still had an advance for line n
    o.act("advance", meta={"at": n})
    assert o.state == orc.WRAP_UP and o.waiting == "audio"
    o.act("advance", meta={"at": len(o.lines)})
    assert o.state == orc.NORMAL_END
