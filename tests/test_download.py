"""
Integration tests for the download pipeline (live sansad.in CDN).

These tests run the exact same CLI command used in production against a small
hand-crafted index file containing both known-good and known-bad URLs sourced
from data/source_issues.jsonl. Output goes to tests/fixtures/download/
(gitignored).

The index intentionally mixes:
  - Real PDFs/DOCX from LS16-S5 we know are stable (matches our extract fixtures)
  - A real failed download from data/source_issues.jsonl (server 500)
  - A whitespace-only URL (the "missing protocol" failure pattern observed
    in failed_downloads.txt)
  - A null URL row (no_url skip case)

If sansad.in changes file availability or response codes, these tests will
fail loudly — that's intentional. Treat any failure as a real signal worth
investigating, not a flaky test.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
FIXTURES_ROOT = TESTS_DIR / "fixtures" / "download"
PROJECT_ROOT = TESTS_DIR.parent

# Use a synthetic lok/session number so the test never collides with real data dirs.
TEST_LOK = 99
TEST_SESSION = 99
LOK_DIR = FIXTURES_ROOT / str(TEST_LOK)
INDEX_PATH = LOK_DIR / f"index_session_{TEST_SESSION}.jsonl"
PDF_DIR = LOK_DIR / "pdfs" / f"session_{TEST_SESSION}"

# Synthetic index — each tuple: (key, ques_no, type, url, expected_outcome)
#
# expected_outcome:
#   "success_pdf"      → file lands in pdfs/session_X/ as <name>.pdf
#   "success_docx"     → file lands in pdfs/session_X/ as <name>.docx
#   "fail_server"      → entry in failed_downloads.txt
#   "fail_no_protocol" → entry in failed_downloads.txt (whitespace-only URL)
#   "skip_no_url"      → entry in skipped_downloads.txt with reason 'no_url'
TEST_INDEX = [
    # — Success cases (real, small, stable LS16-S5 files) —
    ("TEST-S99-STARRED-1",    1,    "STARRED",   "https://sansad.in/getFile/loksabhaquestions/annex/5/AS1.pdf?source=pqals",   "success_pdf"),
    ("TEST-S99-STARRED-10",   10,   "STARRED",   "https://sansad.in/getFile/loksabhaquestions/annex/5/AS10.docx?source=pqals", "success_docx"),
    # — Failure: synthetic non-existent annex path; sansad.in returns 500 for these (verified via httpx) —
    ("TEST-S99-UNSTARRED-9999", 9999, "UNSTARRED",
     "https://sansad.in/getFile/loksabhaquestions/annex/9999/NONEXISTENT_TEST_FILE.pdf?source=pqals", "fail_server"),
    # — Failure: whitespace-only URL (mirrors the "missing protocol" pattern) —
    ("TEST-S99-UNSTARRED-7777", 7777, "UNSTARRED", " ", "fail_no_protocol"),
    # — Skip: null URL → no_url log —
    ("TEST-S99-UNSTARRED-8888", 8888, "UNSTARRED", None, "skip_no_url"),
]

EXPECTED_FILES_BY_OUTCOME = {
    "success_pdf":      "AS1.pdf",
    "success_docx":     "AS10.docx",
}


def _write_test_index() -> None:
    """Materialize the synthetic index file under tests/fixtures/download/<lok>/."""
    LOK_DIR.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        for key, qno, qtype, url, _outcome in TEST_INDEX:
            rec = {
                "key": key,
                "lok_no": TEST_LOK,
                "session_no": TEST_SESSION,
                "ques_no": qno,
                "type": qtype,
                "questionsFilePath": url,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _run_download() -> subprocess.CompletedProcess:
    """Invoke the production download CLI scoped to the synthetic index."""
    return subprocess.run(
        [
            "uv", "run", "python", "-m",
            "lok_sabha_dataset.pipeline.download",
            "--lok", str(TEST_LOK),
            "--sessions", str(TEST_SESSION),
            "--data-dir", str(FIXTURES_ROOT),
            # tight sleeps so the test isn't slow but still polite
            "--sleep-min", "0",
            "--sleep-max", "0.1",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )


# ── Module-scoped fixture: one fresh download run ─────────────────────────────

@pytest.fixture(scope="module")
def download_run():
    """Wipe fixture dir, write synthetic index, run download once."""
    if FIXTURES_ROOT.exists():
        shutil.rmtree(FIXTURES_ROOT)
    _write_test_index()
    result = _run_download()
    return {
        "result": result,
        "lok_dir": LOK_DIR,
        "pdf_dir": PDF_DIR,
        "failed_log": LOK_DIR / "failed_downloads.txt",
        "skipped_log": LOK_DIR / "skipped_downloads.txt",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_log(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            rows.append(line.split("\t"))
    return rows


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_download_exits_cleanly(download_run):
    """The download command should exit 0 even when individual URLs fail."""
    result = download_run["result"]
    assert result.returncode == 0, (
        f"download failed: stdout (last 1500):\n{result.stdout[-1500:]}\n"
        f"stderr:\n{result.stderr[-500:]}"
    )


@pytest.mark.parametrize(
    "key,qno,qtype,url,outcome",
    TEST_INDEX,
    ids=[f"{c[0]}-{c[4]}" for c in TEST_INDEX],
)
def test_download_per_record_outcome(download_run, key, qno, qtype, url, outcome):
    """Every index row should produce the expected on-disk artifact for its outcome."""
    pdf_dir = download_run["pdf_dir"]
    failed_log = download_run["failed_log"]
    skipped_log = download_run["skipped_log"]

    if outcome.startswith("success"):
        expected_filename = EXPECTED_FILES_BY_OUTCOME[outcome]
        out = pdf_dir / expected_filename
        assert out.exists(), f"{key}: expected downloaded file at {out}"
        assert out.stat().st_size > 0, f"{key}: downloaded file is empty"
        # Regression: filename must preserve real extension, not get coerced to .pdf
        if outcome == "success_docx":
            assert out.suffix == ".docx", (
                f"{key}: docx URL produced filename {out.name!r}; "
                "regression of the 'all docx saved as file.pdf' bug"
            )

    elif outcome in {"fail_server", "fail_no_protocol"}:
        rows = _read_log(failed_log)
        keys_logged = {r[1] for r in rows if len(r) >= 2}
        assert key in keys_logged, (
            f"{key}: expected entry in failed_downloads.txt, got keys {sorted(keys_logged)}"
        )

    elif outcome == "skip_no_url":
        rows = _read_log(skipped_log)
        no_url_keys = {r[1] for r in rows if len(r) >= 4 and r[3] == "no_url"}
        assert key in no_url_keys, (
            f"{key}: expected no_url entry in skipped_downloads.txt, got {sorted(no_url_keys)}"
        )

    else:
        pytest.fail(f"unhandled outcome: {outcome!r}")


def test_download_summary_counters(download_run):
    """Final summary line should reflect 2 downloads, 2 errors, 1 no_url skip."""
    stdout = download_run["result"].stdout
    # be tolerant of formatting; just check the relevant counts appear
    assert "Downloaded: 2" in stdout, f"expected 'Downloaded: 2' in stdout:\n{stdout[-800:]}"
    assert "Errors: 2" in stdout, f"expected 'Errors: 2' in stdout:\n{stdout[-800:]}"
    assert "Skipped (no URL in index): 1" in stdout, (
        f"expected 'Skipped (no URL in index): 1' in stdout:\n{stdout[-800:]}"
    )


def test_download_filename_extraction_no_file_pdf_collision(download_run):
    """
    Regression: before the _filename_from_url fix, every non-.pdf URL got
    saved as 'file.pdf', which then masked subsequent docx downloads as
    'already exists'. Ensure that bug is not back.
    """
    pdf_dir = download_run["pdf_dir"]
    bogus = pdf_dir / "file.pdf"
    assert not bogus.exists(), (
        "Found 'file.pdf' under pdfs/ — _filename_from_url regression: "
        "non-.pdf URLs are being collapsed to a generic name."
    )


# ── Idempotency: a second run should skip already-downloaded files ─────────────

def test_download_rerun_skips_existing_files():
    """
    Re-run download against the same index without overwrite. Successful
    files should NOT be re-downloaded; their entries should land in
    skipped_downloads.txt with reason 'disk_exists'.
    """
    # Sanity: the first run (via download_run fixture) already wrote the files
    assert (PDF_DIR / "AS1.pdf").exists(), "preconditions not met — run download_run first"

    # Snapshot mtimes to verify they don't change
    mtime_pdf = (PDF_DIR / "AS1.pdf").stat().st_mtime
    mtime_docx = (PDF_DIR / "AS10.docx").stat().st_mtime

    result = _run_download()
    assert result.returncode == 0, f"rerun failed: {result.stdout[-1000:]}"

    # Files should not have been rewritten
    assert (PDF_DIR / "AS1.pdf").stat().st_mtime == mtime_pdf, "AS1.pdf was re-downloaded"
    assert (PDF_DIR / "AS10.docx").stat().st_mtime == mtime_docx, "AS10.docx was re-downloaded"

    # Both should now be logged as disk_exists in skipped_downloads.txt
    rows = _read_log(LOK_DIR / "skipped_downloads.txt")
    disk_exists_keys = {r[1] for r in rows if len(r) >= 4 and r[3] == "disk_exists"}
    assert "TEST-S99-STARRED-1" in disk_exists_keys, "AS1.pdf success not logged as disk_exists on rerun"
    assert "TEST-S99-STARRED-10" in disk_exists_keys, "AS10.docx success not logged as disk_exists on rerun"

    # Counters should reflect 0 new downloads
    assert "Downloaded: 0" in result.stdout, f"expected 'Downloaded: 0' on rerun:\n{result.stdout[-600:]}"
