"""Orchestrator: the §6 turn-taking state machine. Plain Python, no LLM.

Owns eligibility, hand-raise state, cold call (ME only, never twice in a row), the
starvation rule, the no-hands fallback, follow-ups, turn cap, budget and end types.
LLM work is delegated to an `agents` object (agents.LLMAgents, or a fake in tests).

The client drives it with actions and waits:
  waiting == "audio"  → client plays the last line, then sends "advance" (TTS end/error/cancel/timeout,
                        or immediately in typing mode)
  waiting == "hands"  → hands window is open; client sends "advance" when it closes
  waiting == "me"     → my turn: "answer" (text) or "pass"
  waiting == "end"    → class over
"raise", "lower" and "end" are accepted at any time.
"""
import random
import re
import time
from dataclasses import dataclass, field

import config
import llm
from schemas import SessionPack

ME = "me"
PROF = "prof"

# PROF_SPEAKING → HANDS_OPEN → SELECTING → SPEAKER_TURN → AFTER_ANSWER → ...
PROF_SPEAKING = "PROF_SPEAKING"
HANDS_OPEN = "HANDS_OPEN"
SELECTING = "SELECTING"
SPEAKER_TURN = "SPEAKER_TURN"
AFTER_ANSWER = "AFTER_ANSWER"
FOLLOW_UP = "FOLLOW_UP"
WRAP_UP = "WRAP_UP"
NORMAL_END = "NORMAL_END"
BUDGET_ERROR_END = "BUDGET_ERROR_END"

PERSONAS = {
    "consultant": "Consultant: structured, frames the problem with course frameworks, proposes a clear recommendation.",
    "skeptic": "Skeptic: challenges assumptions, points out risks and what could break.",
    "practitioner": "Practitioner: thinks about execution, operations and how customers really behave.",
    "quant": "Quant: goes to the numbers in the exhibits and does quick math.",
}
NAMES = {"consultant": "Priya", "skeptic": "Ben", "practitioner": "Carlos", "quant": "Lena"}
CHARACTERS = {"consultant": "blonde", "skeptic": "brown", "practitioner": "dark", "quant": "ginger"}  # fixed sprite per role (layout.json)


@dataclass
class Classmate:
    id: str
    role: str
    name: str
    character: str

    @property
    def persona(self) -> str:
        return PERSONAS[self.role]


def make_classmates(roles: list[str]) -> list[Classmate]:
    roles = [r for r in roles if r in PERSONAS][:3] or ["consultant", "skeptic"]
    return [Classmate(f"cm{i}", r, NAMES[r], CHARACTERS[r]) for i, r in enumerate(roles, 1)]


def max_followups(pressure: int) -> int:
    """Follow-up pressure slider 1–5 → 0–2 follow-ups in a row."""
    return {1: 0, 2: 1, 3: 1, 4: 2, 5: 2}.get(int(pressure), 1)


@dataclass
class Line:
    speaker: str
    name: str
    text: str
    kind: str  # ask, rephrase, call_on, follow_up, remark, answer, pass, wrap_up
    cited_ids: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class Orchestrator:
    def __init__(
        self,
        sid: str,
        pack: SessionPack,
        classmates: list[Classmate],
        agents,
        *,
        sliders: dict | None = None,
        prof_name: str = "Professor",
        my_name: str = "You",
        budget: llm.Budget | None = None,
        rng: random.Random | None = None,
    ):
        self.sid = sid
        self.pack = pack
        self.classmates = classmates
        self.agents = agents
        self.sliders = {"cold_call": 3, "follow_up_pressure": 3, **(sliders or {})}
        self.prof_name = prof_name
        self.my_name = my_name
        self.budget = budget or llm.Budget()
        self.rng = rng or random.Random()

        self.state = "INIT"
        self.waiting = None
        self._after_audio_next = None
        self.lines: list[Line] = []
        self.trace: list[dict] = []
        self.flags: dict = {}  # UI flags for the latest step: cold_call, no_hands, starvation

        self.my_hand = False
        self.hands: dict[str, bool] = {c.id: False for c in classmates}
        self.skip_count = 0
        self.last_was_cold = False
        self.rephrased: set[int] = set()
        self.followups_in_row = 0
        self.turn = 0
        self.q_index = -1
        self.speaker: str | None = None
        self.end_type: str | None = None  # "normal" | "budget_error"
        self.end_reason: str | None = None
        self.stats = {"hands_raised": 0, "times_spoken": 0, "cold_calls": 0}

    # ---------- helpers ----------
    def name_of(self, sid: str) -> str:
        if sid == ME:
            return self.my_name
        if sid == PROF:
            return self.prof_name
        return next(c.name for c in self.classmates if c.id == sid)

    def note(self, event: str, **data) -> None:
        self.trace.append({"t": round(time.time(), 3), "turn": self.turn, "state": self.state,
                           "event": event, **data})

    def _say(self, speaker: str, text: str, kind: str, then: str, cited=None, **meta) -> None:
        self.lines.append(Line(speaker, self.name_of(speaker), text, kind, list(cited or []), meta))
        self.waiting = "audio"
        self._after_audio_next = then

    @property
    def current_question(self):
        return self.pack.questions[self.q_index] if 0 <= self.q_index < len(self.pack.questions) else None

    @property
    def ended(self) -> bool:
        return self.state in (NORMAL_END, BUDGET_ERROR_END)

    # ---------- public API ----------
    def start(self) -> None:
        self._guard(lambda: self._ask_question(0, intro="Let's get started."))

    def act(self, action: str, text: str | None = None, meta: dict | None = None) -> None:
        if self.ended and action != "end":
            return
        if action == "raise":
            if not self.my_hand and self.waiting != "me":
                self.my_hand = True
                self.stats["hands_raised"] += 1
                self.note("my_hand", up=True)
        elif action == "lower":
            if self.my_hand:
                self.my_hand = False
                self.skip_count = 0  # reset when I lower my hand
                self.note("my_hand", up=False, skip_count=0)
        elif action == "end":
            if not self.ended and self.state != WRAP_UP:
                self._guard(lambda: self._normal_end("end_class"))
        elif action == "advance":
            # a stale advance (sent for an earlier line, e.g. right before End class) is ignored
            if meta and meta.get("at") is not None and meta["at"] != len(self.lines):
                self.note("stale_advance_ignored", at=meta["at"], lines=len(self.lines))
                return
            if self.waiting == "audio":
                self._guard(self._after_audio)
            elif self.waiting == "hands":
                self._guard(self._close_hands)
        elif action in ("answer", "pass") and self.waiting == "me":
            self._guard(lambda: self._my_answer(text or "", action == "pass", meta or {}))

    # ---------- error / budget handling ----------
    def _guard(self, fn) -> None:
        try:
            fn()
        except llm.BudgetExceeded as e:
            self.note("budget_exceeded", detail=str(e))
            if self.state in (WRAP_UP,):
                self._budget_end(f"reserve: {e}")
            else:
                self._guard_end_normal("discussion budget $0.40 reached")
        except llm.LLMError as e:
            self.note("model_error", detail=str(e))
            self._budget_end(f"model error: {e}")

    def _guard_end_normal(self, reason: str) -> None:
        try:
            self._normal_end(reason)
        except (llm.BudgetExceeded, llm.LLMError) as e:
            self._budget_end(f"wrap-up failed: {e}")

    # ---------- flow ----------
    def _after_audio(self) -> None:
        nxt, self._after_audio_next = self._after_audio_next, None
        self.waiting = None
        if nxt == "hands_open":
            self._hands_open()
        elif nxt == "speaker_turn":
            self._speaker_turn()
        elif nxt == "after_answer":
            self._after_answer(passed=False)
        elif nxt == "end_normal":
            self.state = NORMAL_END
            self.waiting = "end"
            self.note("normal_end", reason=self.end_reason)

    def _ask_question(self, idx: int, intro: str = "") -> None:
        self.state = PROF_SPEAKING
        self.q_index = idx
        self.followups_in_row = 0
        self.speaker = PROF
        self.flags = {}
        q = self.pack.questions[idx]
        text = f"{intro.strip()} {q.text}".strip()
        self.note("ask", question_id=q.id)
        self._say(PROF, text, "ask", then="hands_open", question_id=q.id)

    def _hands_open(self) -> None:
        self.state = HANDS_OPEN
        self.speaker = None
        decisions = self.agents.hands(self)  # ONE batched call
        self.hands = {c.id: bool(decisions.get(c.id, False)) for c in self.classmates}
        self.note("hands", hands=self.hands)
        self.waiting = "hands"

    def _close_hands(self) -> None:
        self.waiting = None
        self.flags = {}
        # 3. cold call check — applies to ME only, never twice in a row
        cold = False
        if not self.my_hand and not self.last_was_cold:
            p = int(self.sliders["cold_call"]) * config.COLD_CALL_BASE_RATE
            cold = self.rng.random() < p
            self.note("cold_call_check", p=round(p, 3), hit=cold)
        self.last_was_cold = cold
        if cold:
            self.flags["cold_call"] = True
            self.stats["cold_calls"] += 1
            return self._call_on(ME, "cold_call")

        raised = [c.id for c in self.classmates if self.hands.get(c.id)]
        if self.my_hand:
            raised.append(ME)

        # 5. no hands: rephrase once, then the no-hands fallback
        if not raised:
            if self.q_index not in self.rephrased:
                self.rephrased.add(self.q_index)
                self.state = PROF_SPEAKING
                self.speaker = PROF
                text = self.agents.rephrase(self)
                self.note("rephrase")
                return self._say(PROF, text, "rephrase", then="hands_open")
            pick = self.rng.choice([ME] + [c.id for c in self.classmates])
            self.flags["no_hands"] = True
            self.note("no_hands_fallback", pick=pick)
            return self._call_on(pick, "no_hands")

        # 4. starvation rule
        if self.my_hand and self.skip_count >= 2:
            self.flags["starvation"] = True
            self.note("starvation", skip_count=self.skip_count)
            return self._select([ME], "starvation")
        self._select(raised, "hands")

    def _select(self, eligible: list[str], reason: str) -> None:
        self.state = SELECTING
        text = None
        if len(eligible) == 1:
            target = eligible[0]  # nothing to choose; no model call
        else:
            target, text = self.agents.select(self, eligible)
            if target not in eligible:  # the professor may ONLY pick from the eligible list
                self.note("invalid_pick_replaced", picked=target, eligible=eligible)
                target, text = eligible[0], None
        if self.my_hand and target != ME:
            self.skip_count += 1
        self.note("selected", target=target, eligible=eligible, reason=reason, skip_count=self.skip_count)
        self._call_on(target, reason, text)

    def _call_on(self, target: str, reason: str, text: str | None = None) -> None:
        if target == ME:
            self.skip_count = 0  # reset when I am picked
            self.my_hand = False
        self.hands = {c.id: False for c in self.classmates}
        self.speaker = target
        # address me as "you" unless the student set a name
        name = "you" if target == ME and self.my_name == "You" else self.name_of(target)
        if not text:
            text = {
                "cold_call": f"I'd like to hear from {name} on this one." if name == "you"
                else f"{name}, I'd like to hear from you on this one.",
                "no_hands": f"No hands, so… {name}, what do you think?",
                "starvation": "You've been patient. Go ahead." if name == "you"
                else f"{name}, you've been patient. Go ahead.",
            }.get(reason, f"{name[:1].upper()}{name[1:]}, go ahead.")
        self.state = PROF_SPEAKING
        self._say(PROF, text, "call_on", then="speaker_turn", target=target, reason=reason)

    def _speaker_turn(self) -> None:
        self.state = SPEAKER_TURN
        self.stats["times_spoken"] += self.speaker == ME
        if self.speaker == ME:
            self.waiting = "me"
            return
        text, cited = self.agents.remark(self, self.speaker)
        self._say(self.speaker, text, "remark", then="after_answer", cited=cited)

    def _my_answer(self, text: str, passed: bool, meta: dict) -> None:
        self.waiting = None
        if passed:
            self.lines.append(Line(ME, self.my_name, "(passed)", "pass"))
        else:
            self.lines.append(Line(ME, self.my_name, text.strip(), "answer", meta=meta))
        self._after_answer(passed)

    def _after_answer(self, passed: bool) -> None:
        self.state = AFTER_ANSWER
        self.flags = {}
        self.turn += 1
        self.note("turn_done", passed=passed)
        if self.turn >= config.TURN_CAP:
            return self._normal_end("turn cap")
        if self.budget.spent >= config.DISCUSSION_BUDGET_USD:
            return self._normal_end("discussion budget $0.40 reached")

        allowed = []
        if not passed and self.followups_in_row < max_followups(self.sliders["follow_up_pressure"]):
            allowed.append("follow_up")
        has_next = self.q_index + 1 < len(self.pack.questions)
        if has_next:
            allowed.append("next_question")
        allowed.append("wrap_up")

        move = self.agents.next_move(self, allowed)
        action = move.action if move.action in allowed else ("next_question" if has_next else "wrap_up")
        self.note("next_move", action=action, proposed=move.action, allowed=allowed)

        if action == "follow_up":  # follow-up keeps the floor: same speaker, no hands, no selection
            self.followups_in_row += 1
            self.state = FOLLOW_UP
            return self._say(PROF, move.text, "follow_up", then="speaker_turn", target=self.speaker)
        if action == "next_question":
            # the transition is one short sentence; the question text is added verbatim
            intro = re.split(r"(?<=[.!])\s", move.text.strip(), maxsplit=1)[0] if move.text else ""
            if intro.endswith("?"):
                intro = ""
            return self._ask_question(self.q_index + 1, intro=intro)
        self._normal_end("questions done" if not has_next else "professor wrapped up")

    # ---------- ends ----------
    def _normal_end(self, reason: str) -> None:
        """Professor wrap-up (+ Coach later), paid from the $0.10 reserve."""
        if self.ended or self.state == WRAP_UP:
            return
        self.end_reason = reason
        self.state = WRAP_UP
        self.waiting = None
        worst = self.agents.reserve_needed(self)
        if self.budget.spent + worst > config.HARD_CAP_USD:
            return self._budget_end(f"reserve too small (need ${worst:.4f}) after: {reason}")
        self.end_type = "normal"
        self.speaker = PROF
        text = self.agents.wrap_up(self)
        self._say(PROF, text, "wrap_up", then="end_normal")

    def _budget_end(self, reason: str) -> None:
        """No model calls from here on: show takeaways + saved lines; evaluation unavailable."""
        self.state = BUDGET_ERROR_END
        self.end_type = "budget_error"
        self.end_reason = reason
        self.waiting = "end"
        self.speaker = None
        self.note("budget_error_end", reason=reason)

    # ---------- view ----------
    def snapshot(self) -> dict:
        return {
            "id": self.sid,
            "state": self.state,
            "waiting": self.waiting,
            "speaker": self.speaker,
            "flags": self.flags,
            "my_hand": self.my_hand,
            "hands": self.hands,
            "skip_count": self.skip_count,
            "turn": self.turn,
            "turn_cap": config.TURN_CAP,
            "question": self.current_question.model_dump() if self.current_question else None,
            "lines": [vars(l) for l in self.lines],
            "classmates": [vars(c) | {"persona": c.persona} for c in self.classmates],
            "prof_name": self.prof_name,
            "my_name": self.my_name,
            "spent_usd": round(self.budget.spent, 6),
            "end_type": self.end_type,
            "end_reason": self.end_reason,
            "takeaways": [t.model_dump() for t in self.pack.takeaways] if self.ended else [],
            "stats": self.stats,
            "trace": self.trace[-60:],
        }
