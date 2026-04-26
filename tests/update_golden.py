"""
Capture the current extract outputs as golden reference files.

Run after the test fixture has executed (it produces the parsed/ tree):
    uv run --extra dev pytest tests/test_extract_doc.py -v   # creates parsed/ outputs
    uv run python tests/update_golden.py                      # snapshots them as goldens

Golden files are stripped of volatile fields (timestamps, timing, file paths)
so they remain stable across machines and runs.

Two golden directories are produced:
    tests/golden/16/session_5/          — docling-pass outputs (read from snapshot dir)
    tests/golden/16/session_5_easyocr/  — easyocr-retry outputs for low-confidence PDFs
"""

from __future__ import annotations

import json
from pathlib import Path

TESTS_DIR = Path(__file__).parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
GOLDEN_DIR = TESTS_DIR / "golden"

LOK = 16
SESSION = 5

# Fields to strip — volatile across runs/machines
STRIP_FIELDS = {"extracted_at_unix", "processing_time_sec", "pdf_relpath"}

# Files whose easyocr-retry output should be captured separately
LOW_CONFIDENCE_STEMS = {"AU642", "AU646"}


def _strip_volatile(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in STRIP_FIELDS}


def _snapshot_dir(src: Path, dest: Path, *, only_stems: set[str] | None = None,
                  exclude_stems: set[str] | None = None) -> int:
    """Copy *.json from src into dest as cleaned goldens. Returns count written."""
    if not src.exists():
        print(f"[error] No parsed output at {src}")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    for json_file in sorted(src.glob("*.json")):
        stem = json_file.stem
        if only_stems is not None and stem not in only_stems:
            continue
        if exclude_stems is not None and stem in exclude_stems:
            continue

        with json_file.open(encoding="utf-8") as f:
            data = json.load(f)
        cleaned = _strip_volatile(data)
        golden_file = dest / json_file.name

        existed = golden_file.exists()
        with golden_file.open("w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)

        status = "updated" if existed else "created"
        words = len((cleaned.get("full_markdown") or "").split())
        print(f"  [{status}] {dest.name}/{json_file.name}  ({words} words)")
        written += 1
    return written


def main() -> None:
    snapshot_dir = FIXTURES_DIR / str(LOK) / "parsed" / f"session_{SESSION}_docling_snapshot"
    parsed_dir = FIXTURES_DIR / str(LOK) / "parsed" / f"session_{SESSION}"
    docling_golden_dir = GOLDEN_DIR / str(LOK) / f"session_{SESSION}"
    easyocr_golden_dir = GOLDEN_DIR / str(LOK) / f"session_{SESSION}_easyocr"

    if not parsed_dir.exists():
        print(f"[error] No parsed output at {parsed_dir}")
        print("Run the tests first to produce outputs:")
        print("  uv run --extra dev pytest tests/test_extract_doc.py")
        return

    # Docling-pass goldens — exclude low-confidence stems (their docling output is empty/unusable)
    print("=== docling-pass goldens (from snapshot) ===")
    if snapshot_dir.exists():
        n_doc = _snapshot_dir(snapshot_dir, docling_golden_dir, exclude_stems=LOW_CONFIDENCE_STEMS)
    else:
        # Fall back to parsed_dir if snapshot wasn't produced (e.g. ran extract manually)
        print(f"[warn] no snapshot dir; using {parsed_dir} for docling goldens")
        n_doc = _snapshot_dir(parsed_dir, docling_golden_dir, exclude_stems=LOW_CONFIDENCE_STEMS)

    # Easyocr-retry goldens — only for low-confidence stems
    print("\n=== easyocr-retry goldens (from parsed dir, post-retry) ===")
    n_ocr = _snapshot_dir(parsed_dir, easyocr_golden_dir, only_stems=LOW_CONFIDENCE_STEMS)

    print(f"\n{n_doc} docling golden(s) written to {docling_golden_dir}")
    print(f"{n_ocr} easyocr golden(s) written to {easyocr_golden_dir}")
    print("Commit the golden/ directory to lock in the reference outputs.")


if __name__ == "__main__":
    main()
