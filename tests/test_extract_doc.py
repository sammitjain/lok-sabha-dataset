"""
Integration tests for the extract pipeline covering .doc, .docx, and .pdf source files,
plus the --retry-low-confidence --engine easyocr path used in the production recipe.

These tests call the exact same CLI commands used in production:
    1. uv run python -m lok_sabha_dataset.pipeline.extract run --lok 16 --sessions 5 --engine docling
    2. uv run python -m lok_sabha_dataset.pipeline.extract run --lok 16 --sessions 5 --engine easyocr --retry-low-confidence

Test data lives in tests/fixtures/16/pdfs/session_5/ (15 files total).
Golden reference outputs live in:
    - tests/golden/16/session_5/          — docling-pass outputs (13 files)
    - tests/golden/16/session_5_easyocr/  — easyocr-retry outputs (2 files)

Workflow:
    1. Run tests:
           uv run --extra dev pytest tests/test_extract_doc.py -v
    2. After implementation changes, regenerate goldens:
           uv run python tests/update_golden.py
    3. Re-run tests — all should pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
GOLDEN_DIR = TESTS_DIR / "golden"
PROJECT_ROOT = TESTS_DIR.parent

LOK = 16
SESSION = 5

# Stable fields to compare in golden (excludes volatile timestamps/timing)
STABLE_FIELDS = ["pdf_filename", "engine", "ocr_fallback", "full_markdown"]
STABLE_META_FIELDS = ["num_pages"]


def _run_extract(engine: str = "docling", retry_low_confidence: bool = False) -> subprocess.CompletedProcess:
    """Run the exact extract CLI command used in production, pointed at fixture data.

    When retry_low_confidence=True, runs without --overwrite (only re-processes unusable outputs).
    Otherwise runs with --overwrite (fresh extraction of every file).
    """
    cmd = [
        "uv", "run", "python", "-m",
        "lok_sabha_dataset.pipeline.extract", "run",
        "--lok", str(LOK),
        "--sessions", str(SESSION),
        "--data-dir", str(FIXTURES_DIR),
        "--output-dir", str(FIXTURES_DIR),
        "--engine", engine,
    ]
    if retry_low_confidence:
        cmd.append("--retry-low-confidence")
    else:
        cmd.append("--overwrite")
    return subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)


# ── Test case definitions ─────────────────────────────────────────────────────
#
# Each entry: (filename, description)
#
# .doc cases — all 10 from the experiment
DOC_CASES = [
    ("AU3712.doc", "binary OLE2"),
    ("AU408.doc",  "binary OLE2"),
    ("AU352.doc",  "binary OLE2 with embedded objects (garbled expected)"),
    ("AU2960.doc", "binary OLE2 — Hindi content"),
    ("AU2547.doc", "binary OLE2"),
    ("AU1267.doc", "OLE2 with embedded theme zip"),
    ("AU3470.doc", "OLE2 with embedded theme zip — proper OOXML structure"),
    ("AU3302.doc", "OLE2 with embedded theme zip"),
    ("AU637.doc",  "OLE2 with embedded theme zip"),
    ("AU179.doc",  "OLE2 with embedded theme zip — proper OOXML structure"),
]

# Control cases — verify .docx and .pdf handling is unaffected
CONTROL_CASES = [
    ("AS10.docx",  "standard OOXML docx"),
    ("AS100.docx", "standard OOXML docx"),
    ("AS1.pdf",    "standard PDF"),
]

# Low-confidence PDFs — empty/unusable under docling, need easyocr retry pass
LOW_CONFIDENCE_CASES = [
    ("AU642.pdf", "scanned PDF — empty under docling, needs OCR"),
    ("AU646.pdf", "scanned PDF — empty under docling, needs OCR"),
]

ALL_CASES = DOC_CASES + CONTROL_CASES
ALL_BASIC_CASES = ALL_CASES + LOW_CONFIDENCE_CASES  # for tests that just check existence/validity


# ── Shared fixture: run docling extract + easyocr retry once per module ───────

@pytest.fixture(scope="module")
def extract_run():
    """
    Run the full production recipe once for all tests in this module:
      1. docling extract --overwrite                       (fresh pass on all files)
      2. snapshot the docling-only state to a sibling dir  (for assertions about pre-OCR state)
      3. easyocr extract --retry-low-confidence            (only touches unusable files)

    Returns a dict with both CompletedProcess results and the relevant directories.
    """
    parsed_dir = FIXTURES_DIR / str(LOK) / "parsed" / f"session_{SESSION}"
    snapshot_dir = FIXTURES_DIR / str(LOK) / "parsed" / f"session_{SESSION}_docling_snapshot"

    if parsed_dir.exists():
        shutil.rmtree(parsed_dir)
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)

    docling_result = _run_extract(engine="docling")

    # Snapshot the docling-only state before the easyocr retry overwrites low-confidence outputs
    if parsed_dir.exists():
        shutil.copytree(parsed_dir, snapshot_dir)

    easyocr_result = _run_extract(engine="easyocr", retry_low_confidence=True)

    return {
        "docling_result": docling_result,
        "easyocr_result": easyocr_result,
        "parsed_dir": parsed_dir,           # post-easyocr-retry state
        "snapshot_dir": snapshot_dir,       # docling-only state
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_matches_golden(actual_path: Path, golden_path: Path, filename: str) -> None:
    """Strict golden comparison on STABLE_FIELDS + STABLE_META_FIELDS."""
    with actual_path.open() as f:
        actual = json.load(f)
    with golden_path.open() as f:
        expected = json.load(f)

    for field in STABLE_FIELDS:
        assert actual.get(field) == expected.get(field), (
            f"{filename}: '{field}' mismatch\n"
            f"  expected: {str(expected.get(field))[:120]!r}\n"
            f"  actual:   {str(actual.get(field))[:120]!r}"
        )
    for field in STABLE_META_FIELDS:
        assert actual.get("metadata", {}).get(field) == expected.get("metadata", {}).get(field), (
            f"{filename}: metadata.{field} mismatch"
        )


# ── Tests: docling pass (DOC + CONTROL + LOW_CONFIDENCE all produce *some* output) ─

@pytest.mark.parametrize("filename,description", ALL_BASIC_CASES, ids=[c[0] for c in ALL_BASIC_CASES])
def test_extract_produces_output(extract_run, filename, description):
    """Every source file should produce a parsed JSON in the output directory."""
    parsed_dir = extract_run["parsed_dir"]
    docling_result = extract_run["docling_result"]
    out_file = parsed_dir / f"{Path(filename).stem}.json"

    assert out_file.exists(), (
        f"{filename} ({description}): no parsed JSON produced.\n"
        f"docling stdout (last 2000 chars):\n{docling_result.stdout[-2000:]}\n"
        f"docling stderr:\n{docling_result.stderr[-500:]}"
    )


@pytest.mark.parametrize("filename,description", ALL_BASIC_CASES, ids=[c[0] for c in ALL_BASIC_CASES])
def test_extract_output_is_valid_json(extract_run, filename, description):
    """Parsed output must be valid JSON with required top-level keys."""
    parsed_dir = extract_run["parsed_dir"]
    out_file = parsed_dir / f"{Path(filename).stem}.json"

    if not out_file.exists():
        pytest.skip(f"Output missing for {filename} — see test_extract_produces_output")

    with out_file.open() as f:
        data = json.load(f)

    required_keys = {"pdf_filename", "engine", "full_markdown", "metadata", "ocr_fallback"}
    missing = required_keys - data.keys()
    assert not missing, f"{filename}: missing keys in output: {missing}"


# ── Tests: docling-pass golden match (DOC + CONTROL only — these are usable under docling) ─

@pytest.mark.parametrize("filename,description", ALL_CASES, ids=[c[0] for c in ALL_CASES])
def test_extract_matches_golden(extract_run, filename, description):
    """
    Compare docling-pass extract output against the stored golden reference.
    Uses snapshot_dir so we read the docling state, not state mutated by easyocr retry.
    """
    snapshot_dir = extract_run["snapshot_dir"]
    stem = Path(filename).stem
    out_file = snapshot_dir / f"{stem}.json"
    golden_file = GOLDEN_DIR / str(LOK) / f"session_{SESSION}" / f"{stem}.json"

    if not golden_file.exists():
        pytest.skip(f"No golden file for {filename} — run: uv run python tests/update_golden.py")
    if not out_file.exists():
        pytest.fail(f"Output missing for {filename} but golden exists — extract failed")

    _assert_matches_golden(out_file, golden_file, filename)


# ── Tests: low-confidence handling (docling unusable → easyocr retry → usable + golden) ─

@pytest.mark.parametrize("filename,description", LOW_CONFIDENCE_CASES, ids=[c[0] for c in LOW_CONFIDENCE_CASES])
def test_low_confidence_unusable_under_docling(extract_run, filename, description):
    """After the docling-only pass, low-confidence PDFs should be flagged as unusable."""
    from lok_sabha_dataset.pipeline.extract import _parsed_is_usable

    snapshot_dir = extract_run["snapshot_dir"]
    out_file = snapshot_dir / f"{Path(filename).stem}.json"

    assert out_file.exists(), f"{filename}: no docling output produced"
    assert not _parsed_is_usable(out_file), (
        f"{filename} ({description}): expected docling output to be unusable "
        "(empty / image-comments only / <15 words) so retry-low-confidence kicks in"
    )


@pytest.mark.parametrize("filename,description", LOW_CONFIDENCE_CASES, ids=[c[0] for c in LOW_CONFIDENCE_CASES])
def test_low_confidence_usable_after_easyocr_retry(extract_run, filename, description):
    """After --retry-low-confidence --engine easyocr, the same files should now be usable."""
    from lok_sabha_dataset.pipeline.extract import _parsed_is_usable

    parsed_dir = extract_run["parsed_dir"]
    easyocr_result = extract_run["easyocr_result"]
    out_file = parsed_dir / f"{Path(filename).stem}.json"

    assert out_file.exists(), f"{filename}: easyocr retry produced no output"
    assert _parsed_is_usable(out_file), (
        f"{filename} ({description}): expected usable text after easyocr retry.\n"
        f"easyocr stdout (last 1000 chars):\n{easyocr_result.stdout[-1000:]}"
    )

    with out_file.open() as f:
        data = json.load(f)
    assert "easyocr" in data.get("engine", ""), (
        f"{filename}: expected 'easyocr' in engine field after retry, got {data.get('engine')!r}"
    )


@pytest.mark.parametrize("filename,description", LOW_CONFIDENCE_CASES, ids=[c[0] for c in LOW_CONFIDENCE_CASES])
def test_low_confidence_matches_easyocr_golden(extract_run, filename, description):
    """Strict golden match for the easyocr-retry output of low-confidence PDFs."""
    parsed_dir = extract_run["parsed_dir"]
    stem = Path(filename).stem
    out_file = parsed_dir / f"{stem}.json"
    golden_file = GOLDEN_DIR / str(LOK) / f"session_{SESSION}_easyocr" / f"{stem}.json"

    if not golden_file.exists():
        pytest.skip(f"No easyocr golden for {filename} — run: uv run python tests/update_golden.py")
    if not out_file.exists():
        pytest.fail(f"Output missing for {filename} but golden exists — easyocr retry failed")

    _assert_matches_golden(out_file, golden_file, filename)
