"""Pydantic output schemas for every agent (PRD §9)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Policy = Literal["not_confirmed", "allowed", "not_allowed"]
MaterialKind = Literal["slides", "case", "notes", "questions"]


# ---------- Integrity Gate (plain code) ----------
class GateResult(BaseModel):
    allowed: bool
    reason: str
    bundled_demo: bool = False


# ---------- Pack Builder ----------
class SourcedItem(BaseModel):
    id: str
    text: str
    source: str


class PlainItem(BaseModel):
    id: str
    text: str


class SessionPack(BaseModel):
    frameworks: list[SourcedItem]
    questions: list[PlainItem]
    facts: list[SourcedItem]
    takeaways: list[PlainItem]
    decision: str | None = None


# ---------- Professor ----------
class ProfMove(BaseModel):
    action: Literal["ask", "rephrase", "call_on", "follow_up", "next_question", "wrap_up"]
    target_id: str | None = None  # must be in the eligible list for call_on
    text: str
    question_id: str | None = None


# ---------- Classmates ----------
class HandDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    raise_hand: bool = Field(alias="raise")
    reason: str


class HandDecisions(BaseModel):
    decisions: list[HandDecision]


class Remark(BaseModel):
    text: str
    builds_on: str | None = None
    cited_ids: list[str]


# ---------- Coach ----------
class RubricScore(BaseModel):
    criterion: str
    score: int  # 1–5; clamped in code (strict schemas reject min/max)
    reason: str

    @field_validator("score")
    @classmethod
    def _clamp(cls, v: int) -> int:
        return min(max(v, 1), 5)


class NeedsWork(BaseModel):
    point: str
    fix: str


class PolishedLine(BaseModel):
    said: str
    polished: str
    cited_ids: list[str]


class Evaluation(BaseModel):
    refused: bool  # true when asked to write graded work
    scores: list[RubricScore]
    vs_previous: list[str] | None = None
    improved: list[str]
    needs_work: list[NeedsWork]
    polished_lines: list[PolishedLine]
    expressions: list[str]
