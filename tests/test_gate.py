import json
import shutil

import config
import gate
import pack

CASE_TEXT = "This case was prepared by Professor X. ... Exhibit 1 shows sales by region."


def test_case_pdf_blocked_when_policy_not_confirmed(tmp_path):
    f = tmp_path / "uploads" / "real_case.pdf"
    f.parent.mkdir()
    f.write_bytes(b"%PDF-1.4 fake")
    r = gate.check_material("case", "not_confirmed", text=CASE_TEXT, path=f)
    assert not r.allowed and "not confirmed" in r.reason


def test_case_disguised_as_slides_is_blocked():
    r = gate.check_material("slides", "not_confirmed", text=CASE_TEXT)
    assert not r.allowed and "looks like a teaching case" in r.reason


def test_slides_allowed_when_not_confirmed():
    assert gate.check_material("slides", "not_confirmed", text="Segmentation: who, what, why").allowed


def test_allowed_policy_needs_source_note():
    assert not gate.check_material("case", "allowed", text=CASE_TEXT).allowed
    r = gate.check_material("case", "allowed", source_note="instructor, class 10/26", text=CASE_TEXT)
    assert r.allowed and "not verified" in r.reason


def test_not_allowed_blocks_course_files_but_not_notes():
    assert not gate.check_material("slides", "not_allowed", text="slides").allowed
    assert not gate.check_material("case", "not_allowed", text=CASE_TEXT).allowed
    assert gate.check_material("notes", "not_allowed", text="my notes").allowed


def test_bundled_demo_passes_via_allowlist(tmp_logs):
    case = config.SAMPLES_DIR / "demo_case.md"
    assert gate.is_bundled_demo(case)
    r = gate.check_material("case", "not_confirmed", text=case.read_text(), path=case)
    assert r.allowed and r.bundled_demo
    log = [json.loads(x) for x in (tmp_logs / "gate.jsonl").read_text().splitlines()]
    assert log[-1]["event"] == "bundled_demo_bypass"  # bypass is logged


def test_modified_demo_file_is_blocked(tmp_path, monkeypatch):
    samples = tmp_path / "samples"
    shutil.copytree(config.SAMPLES_DIR, samples)
    monkeypatch.setattr(config, "SAMPLES_DIR", samples)
    monkeypatch.setattr(gate, "ALLOWLIST_FILE", samples / "allowlist.json")
    case = samples / "demo_case.md"
    assert gate.is_bundled_demo(case)
    case.write_text(case.read_text() + "\nOne extra line.")
    assert not gate.is_bundled_demo(case)
    r = gate.check_material("case", "not_confirmed", text=case.read_text(), path=case)
    assert not r.allowed and not r.bundled_demo


def test_copy_of_demo_outside_samples_gets_no_exception(tmp_path):
    copy = tmp_path / "uploads" / "demo_case.md"
    copy.parent.mkdir()
    shutil.copy(config.SAMPLES_DIR / "demo_case.md", copy)  # identical bytes, user upload
    assert not gate.is_bundled_demo(copy)
    assert not gate.check_material("case", "not_confirmed", text=copy.read_text(), path=copy).allowed


def test_run_gate_drops_blocked_material():
    mats = [pack.Material("case", "Real case", CASE_TEXT), pack.Material("notes", "Notes", "my notes")]
    prepared = pack.run_gate(mats, "not_confirmed")
    assert [m.label for m in prepared.materials] == ["Notes"]
    assert [label for label, _ in prepared.blocked] == ["Real case"]


def test_writeup_requests_are_detected():
    assert gate.is_writeup_request("Can you write my case write-up for Brightloaf?")
    assert gate.is_writeup_request("Please draft the case memo for me")
    assert not gate.is_writeup_request("How can I say my point about segmentation more clearly?")
