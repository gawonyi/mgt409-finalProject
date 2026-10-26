"""Hand Up! server: `python3 app.py` → http://localhost:8000"""
import json
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import coach
import config
import costs
import llm
import pack as packmod
from agents import LLMAgents
from orchestrator import Orchestrator, make_classmates

STATIC = config.ROOT / "static"
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = FastAPI(title="Hand Up!")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

PACKS: dict[str, dict] = {}  # pack_id → {pack, budget, course}
SESSIONS: dict[str, dict] = {}  # session_id → {orch, lock, course}


def load_demo_course() -> dict:
    return json.loads((config.SAMPLES_DIR / "course_mgt411.json").read_text())


@app.get("/")
def root():
    index = STATIC / "index.html"
    return FileResponse(index) if index.exists() else RedirectResponse("/debug")


@app.get("/debug")
def debug_page():
    return FileResponse(STATIC / "debug.html")


COURSES_DIR = config.DATA_DIR / "courses"


def _builtin_course() -> dict:
    c = load_demo_course()
    for entry in c.get("schedule", []):
        qf = entry.get("questions_file")
        if qf and not entry.get("questions"):
            entry["questions"] = json.loads((config.SAMPLES_DIR / qf).read_text())["questions"]
    return c | {"builtin": True}


@app.get("/api/courses")
def list_courses():
    mine = []
    if COURSES_DIR.exists():
        mine = [json.loads(p.read_text()) for p in sorted(COURSES_DIR.glob("*.json"))]
    return mine + [_builtin_course()]


@app.post("/api/courses")
def save_course(course: dict):
    if not str(course.get("name", "")).strip():
        raise HTTPException(400, "Course name is required.")
    pol = course.get("ai_policy") or {}
    if pol.get("state") not in ("not_confirmed", "allowed", "not_allowed"):
        pol["state"] = "not_confirmed"
    if pol["state"] == "allowed" and not str(pol.get("source_note", "")).strip():
        raise HTTPException(400, "Policy 'allowed' needs a source note.")
    course["ai_policy"] = pol
    course["id"] = course.get("id") or uuid.uuid4().hex[:8]
    course.pop("builtin", None)
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    (COURSES_DIR / f"{course['id']}.json").write_text(json.dumps(course, indent=1))
    return course


@app.get("/api/demo")
def demo():
    _, questions = packmod.demo_materials()
    return {"course": load_demo_course(), "questions": questions}


# ---------- prepare: Integrity Gate → Pack Builder ----------
async def _save_upload(f: UploadFile, kind: str) -> packmod.Material:
    data = await f.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"{f.filename}: file is larger than 15 MB.")
    config.UPLOADS_DIR.mkdir(exist_ok=True)
    path = config.UPLOADS_DIR / f"{uuid.uuid4().hex[:8]}_{Path(f.filename or 'file').name}"
    path.write_bytes(data)
    try:
        text = packmod.extract_text(path)
    except Exception as e:
        raise HTTPException(400, f"Could not read {f.filename}: {e}")
    return packmod.Material(kind, f.filename or kind, text, path=path)


@app.post("/api/prepare")
async def prepare(
    course: str = Form(...),
    questions: str = Form("[]"),
    notes: str = Form(""),
    use_demo: bool = Form(False),
    slides: UploadFile | None = File(None),
    case: UploadFile | None = File(None),
):
    course_d = json.loads(course)
    policy = course_d.get("ai_policy", {}).get("state", "not_confirmed")
    source_note = course_d.get("ai_policy", {}).get("source_note", "")
    qs = [q for q in json.loads(questions) if q.strip()]

    materials: list[packmod.Material] = []
    if use_demo:
        demo_mats, demo_qs = packmod.demo_materials()
        materials += demo_mats
        qs = qs or demo_qs
    for f, kind in ((slides, "slides"), (case, "case")):
        if f is not None and f.filename:
            materials.append(await _save_upload(f, kind))
    if notes.strip():
        materials.append(packmod.Material("notes", "My notes", notes))

    prepared = packmod.run_gate(materials, policy, source_note)  # BEFORE any model call
    gate_view = [{"label": label, **r.model_dump()} for label, r in prepared.gate_results]
    if not prepared.materials and not qs:
        raise HTTPException(400, {"message": "Nothing allowed to build from. Add notes or change the material.",
                                  "gate": gate_view})

    budget = llm.Budget()
    pack_id = uuid.uuid4().hex[:10]
    try:
        p, rec = packmod.build_pack(prepared.materials, qs, code="S1", budget=budget, session_id=pack_id)
    except (llm.LLMError, llm.BudgetExceeded) as e:
        raise HTTPException(502, {"message": f"Pack Builder failed: {e}", "gate": gate_view})
    PACKS[pack_id] = {"pack": p, "budget": budget, "course": course_d, "usage": rec}
    return {"pack_id": pack_id, "pack": p.model_dump(), "gate": gate_view, "usage": rec,
            "spent_usd": round(budget.spent, 6)}


# ---------- class session ----------
class StartReq(BaseModel):
    pack_id: str
    roles: list[str] = ["consultant", "skeptic"]
    cost_cuts: dict | None = None
    confidence_before: int | None = None
    typing_mode: bool = True


class ActReq(BaseModel):
    action: str
    text: str | None = None
    meta: dict | None = None


def _save(sid: str) -> None:
    s = SESSIONS[sid]
    config.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    o = s["orch"]
    s.setdefault("ended_at", time.time())
    view = s.get("evaluation_view") or {}
    (config.SESSIONS_DIR / f"{sid}.json").write_text(json.dumps({
        "course_id": s["course"].get("id"), "ended_at": s["ended_at"],
        "confidence_before": s.get("confidence_before"), "confidence_after": s.get("confidence_after"),
        "typing_mode": s.get("typing_mode"), "cost_cuts": s.get("cost_cuts"), "pack_usage": s.get("pack_usage"),
        "stats": view.get("stats") or coach.compute_stats(o),
        "evaluation": view.get("evaluation"),
        "snapshot": o.snapshot() | {"trace": o.trace},
        "pack": o.pack.model_dump(),
    }, indent=1))


@app.post("/api/session")
def start_session(req: StartReq):
    entry = PACKS.get(req.pack_id)
    if entry is None:
        raise HTTPException(404, "Pack not found. Prepare the session again.")
    course = entry["course"]
    sid = uuid.uuid4().hex[:10]
    o = Orchestrator(
        sid, entry["pack"], make_classmates(req.roles), LLMAgents(course, req.cost_cuts),
        sliders=course.get("professor", {}).get("sliders"),
        prof_name=course.get("professor", {}).get("name") or "Professor",
        budget=entry["budget"],  # pack building counts toward the same $0.50
    )
    SESSIONS[sid] = {"orch": o, "lock": threading.Lock(), "course": course,
                     "confidence_before": req.confidence_before, "typing_mode": req.typing_mode,
                     "pack_usage": entry.get("usage"), "cost_cuts": o.agents.cuts}
    with SESSIONS[sid]["lock"]:
        o.start()
    return o.snapshot()


@app.get("/api/session/{sid}")
def get_session(sid: str):
    if sid not in SESSIONS:
        raise HTTPException(404, "Session not found.")
    return SESSIONS[sid]["orch"].snapshot()


@app.post("/api/session/{sid}/act")
def act(sid: str, req: ActReq):
    s = SESSIONS.get(sid)
    if s is None:
        raise HTTPException(404, "Session not found.")
    with s["lock"]:
        s["orch"].act(req.action, req.text, req.meta)
        if s["orch"].ended:
            _save(sid)
        return s["orch"].snapshot()


def _confidence_history(course_id: str | None) -> list[dict]:
    out = []
    if config.SESSIONS_DIR.exists():
        for p in config.SESSIONS_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if d.get("course_id") == course_id and d.get("ended_at") and d.get("confidence_before") is not None:
                out.append({"ended_at": d.get("ended_at", 0), "before": d.get("confidence_before"),
                            "after": d.get("confidence_after")})
    return sorted(out, key=lambda x: x["ended_at"])


@app.post("/api/session/{sid}/evaluate")
def evaluate(sid: str):
    s = SESSIONS.get(sid)
    if s is None:
        raise HTTPException(404, "Session not found.")
    with s["lock"]:
        o = s["orch"]
        if not o.ended:
            raise HTTPException(400, "Class is not over yet.")
        if "evaluation_view" not in s:  # Coach runs once per session
            s["evaluation_view"] = coach.evaluate(o, s["course"].get("id"))
            _save(sid)
        return s["evaluation_view"] | {
            "confidence_before": s.get("confidence_before"), "confidence_after": s.get("confidence_after"),
            "confidence_history": _confidence_history(s["course"].get("id")),
            "spent_usd": round(o.budget.spent, 6), "trace": o.trace[-60:],
        }


@app.get("/api/costs")
def cost_report(sid: str | None = None):
    out = {"projections": costs.projections(), "defaults": config.COST_CUTS,
           "budget": {"hard_cap": config.HARD_CAP_USD, "discussion": config.DISCUSSION_BUDGET_USD,
                      "reserve": config.RESERVE_USD}}
    s = SESSIONS.get(sid) if sid else None
    if s:
        o = s["orch"]
        last_turn = max([t["turn"] for t in o.trace if t["event"] == "llm"], default=0)
        out["this_turn"] = costs.totals([c for c in costs._calls(o.trace, None) if c["turn"] == last_turn])
        out["this_turn"]["turn"] = last_turn
        out["this_session"] = costs.session_summary(o.trace, s.get("pack_usage"), o.turn)
        out["cost_cuts"] = s.get("cost_cuts")
    return out


class ConfReq(BaseModel):
    after: int


@app.post("/api/session/{sid}/confidence")
def confidence(sid: str, req: ConfReq):
    s = SESSIONS.get(sid)
    if s is None:
        raise HTTPException(404, "Session not found.")
    with s["lock"]:
        s["confidence_after"] = max(1, min(10, req.after))
        if s["orch"].ended:
            _save(sid)
    return {"ok": True, "history": _confidence_history(s["course"].get("id"))}


if __name__ == "__main__":
    import uvicorn

    print("Hand Up! → http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
