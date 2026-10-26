"""Integrity Gate: plain Python, no LLM. Runs BEFORE any uploaded text is sent to the model.

Course AI policy (PRD §11):
- not_confirmed (default): case PDFs blocked; slides and my notes allowed
- allowed: case allowed only with a source note (the user's statement, not verified approval)
- not_allowed: course files (case, slides) blocked; only my own notes

The bundled fictional demo is the ONLY exception, via a SHA-256 allowlist of files in samples/.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import config
from schemas import GateResult

ALLOWLIST_FILE = config.SAMPLES_DIR / "allowlist.json"
GATE_LOG = config.LOG_DIR / "gate.jsonl"

# Text that marks a document as a teaching case even if it was uploaded as "slides".
CASE_MARKERS = re.compile(
    r"(this case was (prepared|written)|harvard business (school|publishing)|"
    r"ivey publishing|case\s*(no\.|number)|teaching case|exhibit\s+\d)",
    re.IGNORECASE,
)

WRITEUP_REQUEST = re.compile(
    r"\b(write|draft|compose|generate|produce|do)\b.{0,40}\b(my|the|a|our)\b.{0,30}"
    r"\b(write-?up|case (analysis|memo|report|paper)|assignment|essay|memo|paper|deliverable)\b",
    re.IGNORECASE | re.DOTALL,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _allowlist() -> dict[str, str]:
    try:
        return json.loads(ALLOWLIST_FILE.read_text())["files"]
    except (OSError, KeyError, json.JSONDecodeError):
        return {}


def is_bundled_demo(path: Path) -> bool:
    """True only for an unmodified file shipped in samples/ and listed in the allowlist."""
    try:
        p = Path(path).resolve()
        samples = config.SAMPLES_DIR.resolve()
    except OSError:
        return False
    if p.parent != samples or not p.is_file():
        return False  # user uploads live elsewhere and never get the exception
    expected = _allowlist().get(p.name)
    return expected is not None and sha256_file(p) == expected


def _log(event: dict) -> None:
    config.LOG_DIR.mkdir(exist_ok=True)
    event = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with open(GATE_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def looks_like_case(text: str) -> bool:
    return bool(CASE_MARKERS.search(text or ""))


def check_material(
    kind: str,
    policy: str,
    *,
    source_note: str = "",
    text: str = "",
    path: Path | None = None,
) -> GateResult:
    """Decide whether one piece of material may be sent to the model."""
    if path is not None and is_bundled_demo(path):
        _log({"event": "bundled_demo_bypass", "file": Path(path).name, "kind": kind, "policy": policy})
        return GateResult(
            allowed=True,
            reason="Bundled fictional demo file (SHA-256 allowlist).",
            bundled_demo=True,
        )

    if kind == "notes":
        return GateResult(allowed=True, reason="Your own notes.")

    if policy == "none":  # v1 UI has no policy setting: every uploaded file is used
        _log({"event": "check", "kind": kind, "effective": kind, "policy": policy, "allowed": True})
        return GateResult(allowed=True, reason=f"Loaded ({len(text or ''):,} characters).")

    # Treat slides that look like a case as a case.
    effective = "case" if kind == "case" or looks_like_case(text) else kind

    if policy == "not_allowed":
        result = GateResult(
            allowed=False,
            reason="Course AI policy: not allowed. Course files cannot be sent to the model; use your own notes.",
        )
    elif effective == "case" and policy == "not_confirmed":
        reason = "Course AI policy is not confirmed, so case files are blocked."
        if kind != "case":
            reason = "This file looks like a teaching case (" + CASE_MARKERS.search(text).group(0) + "). " + reason
        result = GateResult(
            allowed=False,
            reason=reason + " Set the policy to Allowed (with a source note) or use your notes.",
        )
    elif effective == "case" and policy == "allowed" and not source_note.strip():
        result = GateResult(
            allowed=False,
            reason="Policy 'allowed' needs a source note (who said so, and where).",
        )
    elif policy not in ("not_confirmed", "allowed"):
        result = GateResult(allowed=False, reason=f"Unknown policy state: {policy!r}.")
    else:
        note = (
            f" Policy marked allowed by you (\"{source_note.strip()}\"); this is your statement, not verified approval."
            if policy == "allowed"
            else ""
        )
        result = GateResult(allowed=True, reason=f"{effective.capitalize()} allowed.{note}")

    _log({"event": "check", "kind": kind, "effective": effective, "policy": policy,
          "allowed": result.allowed})
    return result


def is_writeup_request(text: str) -> bool:
    """Requests to write graded work (case write-ups etc.) are refused."""
    return bool(WRITEUP_REQUEST.search(text or ""))


def write_allowlist() -> dict[str, str]:
    """Dev helper: hash the shipped demo files. Run after editing samples/."""
    files = {
        p.name: sha256_file(p)
        for p in sorted(config.SAMPLES_DIR.iterdir())
        if p.name.startswith("demo_")  # course_mgt411.json is edited by the user
    }
    ALLOWLIST_FILE.write_text(json.dumps({"files": files}, indent=2) + "\n")
    return files


if __name__ == "__main__":
    for name, digest in write_allowlist().items():
        print(name, digest)
