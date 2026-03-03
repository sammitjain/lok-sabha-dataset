"""Build a Parquet dataset from lok-sabha-rag data.

Usage:
    uv run python -m lok_sabha_dataset.build
    uv run python -m lok_sabha_dataset.build --source-dir /path/to/lok-sabha-rag/data
    uv run python -m lok_sabha_dataset.build --lok 18 --sessions 6-7
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from datasets import Dataset

from lok_sabha_dataset.config import OUTPUT_DIR, SESSIONS, SOURCE_DATA_DIR
from lok_sabha_dataset.loader import (
    convert_date,
    load_index_session,
    load_parsed_json,
    pdf_filename_from_url,
)

app = typer.Typer(add_completion=False)
logger = logging.getLogger(__name__)


def _parse_session_range(raw: str) -> list[int]:
    """Parse '6-7' -> [6, 7] or '3' -> [3]."""
    if "-" in raw:
        lo, hi = raw.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(raw)]


def _build_record(
    row: dict,
    parsed: dict | None,
) -> dict:
    """Build a single flat dataset record from an index row and its parsed JSON."""
    pdf_fname = pdf_filename_from_url(row.get("questionsFilePath"))

    # Full text from parsed JSON
    full_text = None
    extraction_engine = None
    num_pages = None
    if parsed:
        full_text = parsed.get("full_markdown") or parsed.get("full_text")
        extraction_engine = parsed.get("engine")
        meta = parsed.get("metadata") or {}
        num_pages = meta.get("num_pages")

    lok_no = row.get("lok_no")
    session_no = row.get("session_no")
    ques_no = row.get("ques_no")
    qtype = row.get("type", "")

    return {
        "id": f"LS{lok_no}-S{session_no}-{qtype}-{ques_no}",
        "lok_no": lok_no,
        "session_no": session_no,
        "ques_no": ques_no,
        "type": qtype,
        "date": convert_date(row.get("date")),
        "subject": row.get("subjects"),
        "ministry": row.get("ministry"),
        "members": row.get("members", []),
        "full_text": full_text,
        # Placeholders for Phase 2+
        "question_text": None,
        "answer_text": None,
        "qa_split_method": "unsplit",
        "answering_minister": None,
        "question_word_count": None,
        "answer_word_count": None,
        "full_text_word_count": len(full_text.split()) if full_text else None,
        "pdf_url": row.get("questionsFilePath"),
        "pdf_url_hindi": row.get("questionsFilePathHindi"),
        "pdf_filename": pdf_fname,
        "extraction_engine": extraction_engine,
        "num_pages": num_pages,
    }


@app.command()
def build(
    source_dir: Path = typer.Option(SOURCE_DATA_DIR, help="Path to lok-sabha-rag data/ directory"),
    output_dir: Path = typer.Option(OUTPUT_DIR, help="Output directory for Parquet files"),
    lok: int = typer.Option(18, help="Lok Sabha number to process"),
    sessions: Optional[str] = typer.Option(None, help="Session range (e.g. '2-7' or '6'). Default: all configured sessions"),
) -> None:
    """Build a Parquet dataset from lok-sabha-rag index + parsed data."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Determine sessions to process
    if sessions:
        session_list = _parse_session_range(sessions)
    else:
        session_list = SESSIONS.get(lok, [])
        if not session_list:
            logger.error("No sessions configured for Lok Sabha %d", lok)
            raise typer.Exit(1)

    logger.info("Building dataset for Lok Sabha %d, sessions %s", lok, session_list)
    logger.info("Source: %s", source_dir)

    records: list[dict] = []
    missing_parsed = 0
    total_index = 0

    for sess in session_list:
        index_rows = load_index_session(source_dir, lok, sess)
        sess_missing = 0

        for row in index_rows:
            total_index += 1
            pdf_fname = pdf_filename_from_url(row.get("questionsFilePath"))
            parsed = None
            if pdf_fname:
                parsed = load_parsed_json(source_dir, lok, sess, pdf_fname)
            if parsed is None:
                sess_missing += 1

            records.append(_build_record(row, parsed))

        missing_parsed += sess_missing
        logger.info(
            "  Session %d: %d questions, %d missing parsed text",
            sess, len(index_rows), sess_missing,
        )

    logger.info("Total: %d records, %d missing parsed text", total_index, missing_parsed)

    if not records:
        logger.error("No records found. Check --source-dir and --lok/--sessions.")
        raise typer.Exit(1)

    # Build HuggingFace Dataset and write Parquet
    ds = Dataset.from_list(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "lok_sabha_qa.parquet"
    ds.to_parquet(str(parquet_path))

    logger.info("Dataset written to %s (%d rows)", parquet_path, len(ds))
    logger.info("Columns: %s", ds.column_names)


if __name__ == "__main__":
    app()
