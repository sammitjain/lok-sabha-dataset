"""
Integration tests for the curate pipeline (live sansad.in API).

These tests run the exact same CLI command used in production, scoped down via
``--page-size`` and ``--max-pages`` so each session fetches only ~5 records:

    uv run python -m lok_sabha_dataset.pipeline.curate run \\
        --lok 16 --sessions 5 --page-size 5 --max-pages 1 \\
        --data-dir tests/fixtures/curate

Two sessions are exercised to cover both eras of the API:
  - LS16 session 5 (Jul–Aug 2015) — older session, surfaced .doc-format quirks
  - LS18 session 2 (Jul–Aug 2024) — newer, more standardized

Output goes to tests/fixtures/curate/ (gitignored). These tests hit the live
API; expect failure if sansad.in is down or returns unexpected schemas — that's
the point.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
FIXTURES_ROOT = TESTS_DIR / "fixtures" / "curate"
PROJECT_ROOT = TESTS_DIR.parent

PAGE_SIZE = 5
MAX_PAGES = 1
EXPECTED_RECORDS = PAGE_SIZE * MAX_PAGES

# Sessions to test — one older (.doc era), one newer (standardized OOXML era)
CURATE_CASES = [
    (16, 5, "LS16 session 5 — older session, .doc-format era"),
    (18, 2, "LS18 session 2 — newer session, standardized era"),
]

REQUIRED_RECORD_FIELDS = {
    "key", "lok_no", "session_no", "ques_no", "type", "date",
    "subjects", "ministry", "members", "questionsFilePath",
}


def _run_curate(lok: int, session: int) -> subprocess.CompletedProcess:
    """Invoke the production curate CLI scoped to one session, ~5 records."""
    return subprocess.run(
        [
            "uv", "run", "python", "-m",
            "lok_sabha_dataset.pipeline.curate",
            "--lok", str(lok),
            "--sessions", str(session),
            "--data-dir", str(FIXTURES_ROOT),
            "--page-size", str(PAGE_SIZE),
            "--max-pages", str(MAX_PAGES),
            "--no-resume",  # always re-fetch in tests
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


# ── Module-scoped fixture: one fresh curate run per (lok, session) ────────────

@pytest.fixture(scope="module", params=CURATE_CASES, ids=[f"LS{c[0]}-S{c[1]}" for c in CURATE_CASES])
def curate_run(request):
    """Wipe per-lok dir, run curate, return (CompletedProcess, lok_dir)."""
    lok, session, _ = request.param
    lok_dir = FIXTURES_ROOT / str(lok)
    if lok_dir.exists():
        shutil.rmtree(lok_dir)

    result = _run_curate(lok, session)
    return {
        "result": result,
        "lok": lok,
        "session": session,
        "lok_dir": lok_dir,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_curate_exits_cleanly(curate_run):
    """The curate command should exit with returncode 0."""
    result = curate_run["result"]
    assert result.returncode == 0, (
        f"curate failed for LS{curate_run['lok']}-S{curate_run['session']}\n"
        f"stdout (last 1500 chars):\n{result.stdout[-1500:]}\n"
        f"stderr:\n{result.stderr[-500:]}"
    )


def test_curate_produces_index_file(curate_run):
    """A per-session JSONL index file should be created."""
    lok_dir = curate_run["lok_dir"]
    session = curate_run["session"]
    idx = lok_dir / f"index_session_{session}.jsonl"
    assert idx.exists(), f"missing index file: {idx}"
    assert idx.stat().st_size > 0, f"index file is empty: {idx}"


def test_curate_produces_master_files(curate_run):
    """members.json, ministries.json, loksabha_sessions.json, progress.json all present."""
    lok_dir = curate_run["lok_dir"]
    expected = ["members.json", "ministries.json", "loksabha_sessions.json", "progress.json"]
    for name in expected:
        path = lok_dir / name
        assert path.exists(), f"missing master file: {path}"
        # must be non-empty valid JSON
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        assert data, f"{name} loaded but is empty/falsy"


def test_curate_index_record_count_matches_page_limit(curate_run):
    """Index should have exactly page_size × max_pages records."""
    lok_dir = curate_run["lok_dir"]
    session = curate_run["session"]
    idx = lok_dir / f"index_session_{session}.jsonl"
    with idx.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    assert len(records) == EXPECTED_RECORDS, (
        f"expected {EXPECTED_RECORDS} records, got {len(records)}"
    )


def test_curate_index_records_have_required_fields(curate_run):
    """Every index record must have the fields downstream stages depend on."""
    lok_dir = curate_run["lok_dir"]
    session = curate_run["session"]
    lok = curate_run["lok"]
    idx = lok_dir / f"index_session_{session}.jsonl"
    with idx.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    for i, rec in enumerate(records):
        missing = REQUIRED_RECORD_FIELDS - rec.keys()
        assert not missing, f"record {i}: missing fields {missing}"
        # spot-check critical fields are populated correctly
        assert rec["lok_no"] == lok, f"record {i}: lok_no mismatch"
        assert rec["session_no"] == session, f"record {i}: session_no mismatch"
        assert rec["type"] in {"STARRED", "UNSTARRED"}, f"record {i}: bad type {rec['type']!r}"
        assert isinstance(rec["ques_no"], int), f"record {i}: ques_no not int"
        assert rec["key"].startswith(f"LS{lok}-S{session}-"), f"record {i}: bad key {rec['key']!r}"


def test_curate_progress_marks_session_complete(curate_run):
    """After a successful run, progress.json should list the session as complete."""
    lok_dir = curate_run["lok_dir"]
    session = curate_run["session"]
    progress_path = lok_dir / "progress.json"
    with progress_path.open(encoding="utf-8") as f:
        progress = json.load(f)
    completed = progress.get("completed_sessions", [])
    assert session in completed, (
        f"session {session} not marked complete; progress={progress}"
    )
