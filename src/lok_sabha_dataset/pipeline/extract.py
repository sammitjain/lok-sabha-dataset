"""Extract text from downloaded Lok Sabha PDFs.

Reads PDFs under:
  <data-dir>/<lok>/pdfs/session_<n>/

Writes parsed JSON under:
  <data-dir>/<lok>/parsed/session_<n>/

Extraction strategy:
  1. Docling (structure-aware markdown) — fast, handles text-layer PDFs
  2. If Docling returns empty text → fallback to Docling + EasyOCR
     (handles scanned / image-only PDFs)

Idempotent + resumable:
- skips if output JSON already exists (unless --overwrite)
- logs failures to <data-dir>/<lok>/failed_parse.txt
- lightweight progress print every few seconds

Usage:
  # Batch extraction
  uv run python -m lok_sabha_dataset.pipeline.extract run --lok 18 --sessions 7
  uv run python -m lok_sabha_dataset.pipeline.extract run --lok 18 --sessions 7 --max-files 10

  # Dry-run: test extraction on a single file (prints output, does not write)
  uv run python -m lok_sabha_dataset.pipeline.extract test data/18/pdfs/session_2/AS39_0OzSlM.pdf
  uv run python -m lok_sabha_dataset.pipeline.extract test data/18/pdfs/session_2/AS39_0OzSlM.pdf --engine easyocr
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional

import typer

from lok_sabha_dataset.config import DATA_DIR
from lok_sabha_dataset.pipeline.utils import parse_sessions

app = typer.Typer(no_args_is_help=True)


# ── Lazy-loaded converters ────────────────────────────────────────────────────
# All docling/easyocr imports are deferred to avoid loading heavy libs
# until actually needed.  Running with --engine docling never touches EasyOCR.

_converter_default = None
_converter_ocr = None


def _get_default_converter():
    """Docling converter without OCR — fast, for text-layer PDFs."""
    global _converter_default
    if _converter_default is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        _converter_default = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=PdfPipelineOptions(do_ocr=False)
                )
            }
        )
    return _converter_default


def _get_ocr_converter():
    """Docling converter with EasyOCR — slower, for scanned/image PDFs."""
    global _converter_ocr
    if _converter_ocr is None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            EasyOcrOptions,
            PdfPipelineOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        _converter_ocr = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=PdfPipelineOptions(
                        do_ocr=True,
                        ocr_options=EasyOcrOptions(
                            lang=["en"],
                            force_full_page_ocr=True,
                        ),
                    )
                )
            }
        )
    return _converter_ocr


# ── Core extraction ───────────────────────────────────────────────────────────


def _docling_convert(converter: DocumentConverter, pdf_path: Path) -> tuple[str, int, float]:
    """Run a Docling converter and return (markdown, num_pages, elapsed_sec)."""
    t0 = time.time()
    result = converter.convert(str(pdf_path))
    doc = result.document
    markdown = doc.export_to_markdown()
    num_pages = len(doc.pages) if hasattr(doc, "pages") else 0
    return markdown, num_pages, round(time.time() - t0, 2)


def extract_single_pdf(
    pdf_path: Path,
    *,
    engine: str = "auto",
) -> dict:
    """Extract text from a single PDF and return a parsed-JSON-ready dict.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file.
    engine : str
        "auto"    — Docling first, EasyOCR fallback if empty (default)
        "docling" — Docling only, no OCR fallback
        "easyocr" — Force EasyOCR (skip Docling-only pass)

    Returns
    -------
    dict with keys: pdf_filename, pdf_relpath, engine, engine_version,
    extracted_at_unix, processing_time_sec, full_markdown, metadata, ocr_fallback
    """
    total_start = time.time()
    ocr_fallback = False

    if engine in ("auto", "docling"):
        markdown, num_pages, elapsed = _docling_convert(_get_default_converter(), pdf_path)

        if engine == "auto" and not markdown.strip():
            # Empty text — likely a scanned PDF, retry with OCR
            ocr_fallback = True
            markdown, num_pages, ocr_elapsed = _docling_convert(_get_ocr_converter(), pdf_path)
            elapsed += ocr_elapsed

    elif engine == "easyocr":
        markdown, num_pages, elapsed = _docling_convert(_get_ocr_converter(), pdf_path)
        ocr_fallback = True

    else:
        raise ValueError(f"Unknown engine: {engine!r}. Use 'auto', 'docling', or 'easyocr'.")

    engine_label = "docling+easyocr" if ocr_fallback else "docling"

    return {
        "pdf_filename": pdf_path.name,
        "pdf_relpath": str(pdf_path.as_posix()),
        "engine": engine_label,
        "engine_version": "2.x",
        "extracted_at_unix": int(time.time()),
        "processing_time_sec": round(time.time() - total_start, 2),
        "full_markdown": markdown,
        "metadata": {
            "title": None,
            "num_pages": num_pages,
        },
        "ocr_fallback": ocr_fallback,
    }


# ── CLI helpers ───────────────────────────────────────────────────────────────


def _iter_pdf_files(pdf_dir: Path) -> Iterable[Path]:
    yield from sorted(pdf_dir.glob("*.pdf"))


_IMAGE_COMMENT_RE = re.compile(r"<!--\s*image\s*-->")

MIN_USABLE_WORDS = 15


def _parsed_has_text(out_path: Path) -> bool:
    """Check if a parsed JSON file has non-empty extracted text."""
    try:
        with out_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        text = data.get("full_markdown") or data.get("full_text") or ""
        return bool(text.strip())
    except Exception:
        return False


def _parsed_is_usable(out_path: Path) -> bool:
    """Check if a parsed JSON file has meaningful extracted text.

    Returns False for:
    - Empty text
    - Text that is only HTML image comments (``<!-- image -->``)
    - Text with fewer than MIN_USABLE_WORDS real words
    """
    try:
        with out_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        text = data.get("full_markdown") or data.get("full_text") or ""
        stripped = text.strip()
        if not stripped:
            return False
        # Strip HTML comments and check what's left
        without_comments = _IMAGE_COMMENT_RE.sub("", stripped).strip()
        if not without_comments:
            return False
        if len(without_comments.split()) < MIN_USABLE_WORDS:
            return False
        return True
    except Exception:
        return False


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command()
def run(
    lok: int = typer.Option(..., help="Lok Sabha number"),
    sessions: str = typer.Option(..., help="Sessions like '7' or '1-7' or '1,3,7'"),
    base_dir: str = typer.Option(str(DATA_DIR), "--data-dir", help="Base data directory"),
    engine: str = typer.Option("auto", help="Engine: 'auto' (docling + OCR fallback), 'docling' (no OCR), 'easyocr' (force OCR)"),
    retry_empty: bool = typer.Option(False, "--retry-empty", help="Re-process files whose parsed JSON has empty text (use with --engine easyocr)"),
    retry_low_confidence: bool = typer.Option(False, "--retry-low-confidence", help="Re-process files with empty or low-quality text (e.g. only '<!-- image -->')"),
    overwrite: bool = typer.Option(False, help="Re-extract even if parsed JSON exists"),
    sleep_min: float = typer.Option(0.0, help="Optional min seconds between PDFs"),
    sleep_max: float = typer.Option(0.0, help="Optional max seconds between PDFs"),
    max_files: Optional[int] = typer.Option(None, help="Stop after processing N PDFs (for testing)"),
) -> None:
    """Batch-extract text from all PDFs for the given Lok Sabha sessions."""
    base = Path(base_dir) / str(lok)
    if not base.exists():
        raise typer.BadParameter(f"Missing data directory: {base}")

    sess_list = parse_sessions(sessions)
    failed_log = base / "failed_parse.txt"

    processed = 0
    extracted = 0
    skipped = 0
    retried = 0
    errors = 0
    ocr_fallbacks = 0

    last_report = time.time()
    report_interval = 15

    retry_mode = " (retry-low-confidence)" if retry_low_confidence else (" (retry-empty)" if retry_empty else "")
    print(f"Engine: {engine}{retry_mode}")

    for sess in sess_list:
        pdf_dir = base / "pdfs" / f"session_{sess}"
        out_dir = base / "parsed" / f"session_{sess}"
        out_dir.mkdir(parents=True, exist_ok=True)

        if not pdf_dir.exists():
            print(f"[warn] missing pdf dir: {pdf_dir}")
            continue

        print(f"Session {sess}: {pdf_dir} -> {out_dir}")

        for pdf_path in _iter_pdf_files(pdf_dir):
            processed += 1
            out_path = out_dir / f"{pdf_path.stem}.json"

            # Decide whether to process this file
            should_process = False
            if overwrite:
                should_process = True
            elif retry_low_confidence:
                # Re-process files with empty or low-quality extractions
                if out_path.exists() and not _parsed_is_usable(out_path):
                    should_process = True
                    retried += 1
            elif retry_empty:
                # Only re-process files that exist but have empty text
                if out_path.exists() and not _parsed_has_text(out_path):
                    should_process = True
                    retried += 1
            elif not out_path.exists():
                should_process = True

            if not should_process:
                skipped += 1
            else:
                try:
                    parsed = extract_single_pdf(pdf_path, engine=engine)

                    if parsed.get("ocr_fallback"):
                        ocr_fallbacks += 1
                        print(f"  [ocr] {pdf_path.name} — EasyOCR fallback ({parsed['processing_time_sec']}s)")

                    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
                    tmp.write_text(
                        json.dumps(parsed, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    tmp.replace(out_path)
                    extracted += 1
                except Exception as e:
                    errors += 1
                    print(f"[error] {pdf_path.name} -> {e}")
                    with failed_log.open("a", encoding="utf-8") as f:
                        f.write(f"{sess}\t{pdf_path.name}\t{repr(e)}\n")

            now = time.time()
            if now - last_report >= report_interval:
                print(
                    f"Progress: processed={processed} extracted={extracted} "
                    f"skipped={skipped} retried={retried} errors={errors} ocr_fallbacks={ocr_fallbacks}"
                )
                last_report = now

            if max_files is not None and processed >= max_files:
                print("Reached --max-files limit")
                break

            # optional sleep between PDFs (usually keep 0; parsing is local)
            if sleep_max > 0:
                lo = max(0.0, sleep_min)
                hi = max(lo, sleep_max)
                time.sleep(lo + random.random() * (hi - lo))

    print("\nDone.")
    print(
        f"Processed={processed} extracted={extracted} skipped={skipped} "
        f"retried={retried} errors={errors} ocr_fallbacks={ocr_fallbacks}"
    )
    print(f"Failed log: {failed_log}")


@app.command()
def test(
    pdf_path: str = typer.Argument(..., help="Path to a single PDF file"),
    engine: str = typer.Option(
        "auto",
        help="Engine: 'auto' (Docling + OCR fallback), 'docling' (no OCR), 'easyocr' (force OCR)",
    ),
) -> None:
    """Dry-run: extract a single PDF and print the results (does not write any files)."""
    path = Path(pdf_path)
    if not path.exists():
        raise typer.BadParameter(f"File not found: {path}")

    print(f"PDF:    {path}")
    print(f"Engine: {engine}")
    print()

    parsed = extract_single_pdf(path, engine=engine)

    md = parsed["full_markdown"]
    words = len(md.split()) if md else 0
    chars = len(md) if md else 0

    print(f"Engine used:   {parsed['engine']}")
    print(f"OCR fallback:  {parsed['ocr_fallback']}")
    print(f"Time:          {parsed['processing_time_sec']}s")
    print(f"Pages:         {parsed['metadata']['num_pages']}")
    print(f"Characters:    {chars}")
    print(f"Words:         {words}")
    print()

    if md:
        print("─── Text preview (first 500 chars) ─────────────────────────────────")
        print(md[:500])
        print("────────────────────────────────────────────────────────────────────")
    else:
        print("(empty — no text extracted)")


if __name__ == "__main__":
    app()
