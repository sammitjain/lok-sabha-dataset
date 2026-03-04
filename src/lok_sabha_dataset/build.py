"""Build a Parquet dataset from lok-sabha-rag data.

Usage:
    uv run python -m lok_sabha_dataset.build
    uv run python -m lok_sabha_dataset.build --source-dir /path/to/lok-sabha-rag/data
    uv run python -m lok_sabha_dataset.build --lok 18 --sessions 6-7
"""

from __future__ import annotations

import json
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
from lok_sabha_dataset.splitter import split_question_answer

app = typer.Typer(add_completion=False)
logger = logging.getLogger(__name__)


# ── Issue tracking ────────────────────────────────────────────────────────────

def _classify_issue(row: dict, parsed: dict | None) -> str | None:
    """Return a short issue label, or None if the record is fine."""
    if parsed is None:
        return "parsed_file_missing"
    full_text = parsed.get("full_markdown") or parsed.get("full_text")
    if not full_text:
        return "empty_text"
    return None


def _write_build_report(
    issues: list[dict],
    output_dir: Path,
    total: int,
    *,
    split_distribution: dict[str, int] | None = None,
) -> Path:
    """Write a JSON build report listing all problematic records."""
    report = {
        "total_records": total,
        "total_issues": len(issues),
        "qa_split_distribution": split_distribution or {},
        "issues": issues,
    }
    path = output_dir / "build_report.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return path


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

    # Q/A separation
    question_text = None
    answer_text = None
    qa_split_method = "empty"
    if full_text:
        question_text, answer_text, qa_split_method = split_question_answer(full_text)

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
        "question_text": question_text,
        "answer_text": answer_text,
        "qa_split_method": qa_split_method,
        # Placeholder for Phase 3+
        "answering_minister": None,
        "question_word_count": len(question_text.split()) if question_text else None,
        "answer_word_count": len(answer_text.split()) if answer_text else None,
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
    issues: list[dict] = []
    total_index = 0

    for sess in session_list:
        index_rows = load_index_session(source_dir, lok, sess)
        sess_issues = 0

        for row in index_rows:
            total_index += 1
            pdf_fname = pdf_filename_from_url(row.get("questionsFilePath"))
            parsed = None
            if pdf_fname:
                parsed = load_parsed_json(source_dir, lok, sess, pdf_fname)

            issue = _classify_issue(row, parsed)
            if issue:
                sess_issues += 1
                issues.append({
                    "id": f"LS{lok}-S{sess}-{row.get('type', '')}-{row.get('ques_no')}",
                    "session": sess,
                    "pdf_filename": pdf_fname,
                    "issue": issue,
                    "engine": parsed.get("engine") if parsed else None,
                })

            records.append(_build_record(row, parsed))

        logger.info(
            "  Session %d: %d questions, %d issues",
            sess, len(index_rows), sess_issues,
        )

    logger.info("Total: %d records, %d with issues", total_index, len(issues))

    if not records:
        logger.error("No records found. Check --source-dir and --lok/--sessions.")
        raise typer.Exit(1)

    # Q/A split distribution
    from collections import Counter
    split_counts = Counter(r["qa_split_method"] for r in records)
    logger.info("Q/A split distribution:")
    for method, count in split_counts.most_common():
        pct = count / len(records) * 100
        logger.info("  %-25s %6d  (%5.1f%%)", method, count, pct)

    # Build HuggingFace Dataset and write Parquet
    ds = Dataset.from_list(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = output_dir / "lok_sabha_qa.parquet"
    ds.to_parquet(str(parquet_path))

    logger.info("Dataset written to %s (%d rows)", parquet_path, len(ds))
    logger.info("Columns: %s", ds.column_names)

    # Write build report
    report_path = _write_build_report(
        issues, output_dir, total_index, split_distribution=dict(split_counts),
    )
    if issues:
        logger.warning("Build report: %d issues written to %s", len(issues), report_path)
        for entry in issues:
            logger.warning("  %s — %s (engine=%s)", entry["id"], entry["issue"], entry["engine"])
    else:
        logger.info("Build report written to %s (no issues)", report_path)


if __name__ == "__main__":
    app()
