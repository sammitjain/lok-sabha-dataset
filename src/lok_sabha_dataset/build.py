"""Build a Parquet dataset from pipeline data.

Usage:
    uv run python -m lok_sabha_dataset.build
    uv run python -m lok_sabha_dataset.build --data-dir /path/to/data
    uv run python -m lok_sabha_dataset.build --lok 18 --sessions 6-7
    uv run python -m lok_sabha_dataset.build --reconcile   # merge with existing HF dataset
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

import typer
from datasets import Dataset

from lok_sabha_dataset.config import DATA_DIR, OUTPUT_DIR, SESSIONS
from lok_sabha_dataset.pipeline.utils import parse_sessions
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


def _write_issues_log(issues: list[dict], output_dir: Path) -> Path:
    """Write detailed issue entries to a JSONL file."""
    path = output_dir / "build_issues.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for entry in issues:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def _reconcile_with_hf(
    local_records: list[dict],
    local_issues: set[str],
    repo_id: str,
) -> list[dict]:
    """Merge locally-built records with the existing HuggingFace dataset.

    Logic:
    - Start with all rows from the HF dataset as a base.
    - Overwrite with locally-built records that have no issues (successful parse).
    - Keep HF version for records where local build had issues (missing/empty).
    - Add any fresh local rows not present in HF.
    """
    from datasets import load_dataset

    logger.info("Downloading existing dataset from HuggingFace: %s", repo_id)
    try:
        hf_ds = load_dataset(repo_id, split="train")
    except Exception as e:
        logger.warning("Could not load HF dataset (%s). Using local build only.", e)
        return local_records

    # Columns that exist in local build but are dropped before HF publish.
    # Backfill with None so schemas align when preserving HF rows.
    _INTERNAL_COLS = [
        "answering_minister", "pdf_filename", "extraction_engine",
        "qa_split_method", "full_text_word_count",
    ]

    # Index HF rows by id, backfilling missing internal columns
    hf_by_id: dict[str, dict] = {}
    for row in hf_ds:
        d = dict(row)
        for col in _INTERNAL_COLS:
            d.setdefault(col, None)
        hf_by_id[d["id"]] = d

    logger.info("HF dataset has %d rows", len(hf_by_id))

    # Index local rows by id
    local_by_id: dict[str, dict] = {}
    for rec in local_records:
        local_by_id[rec["id"]] = rec

    # Build merged result
    merged: dict[str, dict] = {}

    # Start with all HF rows
    merged.update(hf_by_id)

    # Overwrite with local records that have no issues
    overwritten = 0
    kept_hf = 0
    fresh = 0
    for rec_id, rec in local_by_id.items():
        if rec_id in local_issues:
            # Local build had issues — keep HF version if available
            if rec_id in merged:
                kept_hf += 1
            else:
                # No HF version either, use local (with issues)
                merged[rec_id] = rec
        else:
            # Successful local build — overwrite
            if rec_id in merged:
                overwritten += 1
            else:
                fresh += 1
            merged[rec_id] = rec

    logger.info(
        "Reconciliation: %d overwritten, %d preserved from HF, %d fresh, %d total",
        overwritten, kept_hf, fresh, len(merged),
    )

    return list(merged.values())


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


def _discover_loks(source_dir: Path) -> list[int]:
    """Auto-discover Lok Sabha numbers from numbered subdirectories in source_dir."""
    loks = []
    for d in sorted(source_dir.iterdir()):
        if d.is_dir() and d.name.isdigit():
            # Must have at least one index file to be a valid lok directory
            if list(d.glob("index_session_*.jsonl")):
                loks.append(int(d.name))
    return loks


@app.command()
def build(
    source_dir: Path = typer.Option(DATA_DIR, "--data-dir", help="Root data directory (contains <lok_no>/ subdirectories)"),
    output_dir: Path = typer.Option(OUTPUT_DIR, help="Output directory for Parquet files"),
    lok: Optional[int] = typer.Option(None, help="Lok Sabha number (omit to auto-discover all)"),
    sessions: Optional[str] = typer.Option(None, help="Sessions (e.g. '2-7', '6', '2,5-7'). Default: all configured sessions"),
    reconcile: bool = typer.Option(False, help="Reconcile with existing HuggingFace dataset, preserving rows not rebuilt locally"),
    repo_id: str = typer.Option("opensansad/lok-sabha-qa", help="HuggingFace repo ID (used with --reconcile)"),
) -> None:
    """Build a Parquet dataset from index + parsed data."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Determine which loks to process
    if lok is not None:
        loks = [lok]
    else:
        loks = _discover_loks(source_dir)
        if not loks:
            logger.error("No Lok Sabha data directories found in %s", source_dir)
            raise typer.Exit(1)
        logger.info("Auto-discovered Lok Sabhas: %s", loks)

    logger.info("Source: %s", source_dir)

    records: list[dict] = []
    issues: list[dict] = []
    total_index = 0

    for current_lok in loks:
        # Determine sessions to process for this lok
        if sessions:
            session_list = parse_sessions(sessions)
        else:
            session_list = SESSIONS.get(current_lok, [])
            if not session_list:
                # Fallback: discover sessions from index files
                session_list = sorted(
                    int(m.group(1))
                    for f in (source_dir / str(current_lok)).glob("index_session_*.jsonl")
                    if (m := re.search(r"index_session_(\d+)\.jsonl$", f.name))
                )
            if not session_list:
                logger.warning("No sessions found for Lok Sabha %d, skipping", current_lok)
                continue

        logger.info("Lok Sabha %d: sessions %s", current_lok, session_list)

        for sess in session_list:
            index_rows = load_index_session(source_dir, current_lok, sess)
            sess_issues = 0

            for row in index_rows:
                total_index += 1
                pdf_fname = pdf_filename_from_url(row.get("questionsFilePath"))
                parsed = None
                if pdf_fname:
                    parsed = load_parsed_json(source_dir, current_lok, sess, pdf_fname)

                issue = _classify_issue(row, parsed)
                if issue:
                    sess_issues += 1
                    issues.append({
                        "id": f"LS{current_lok}-S{sess}-{row.get('type', '')}-{row.get('ques_no')}",
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
        logger.error("No records found. Check --data-dir and --lok/--sessions.")
        raise typer.Exit(1)

    # Q/A split distribution
    from collections import Counter
    split_counts = Counter(r["qa_split_method"] for r in records)
    logger.info("Q/A split distribution:")
    for method, count in split_counts.most_common():
        pct = count / len(records) * 100
        logger.info("  %-25s %6d  (%5.1f%%)", method, count, pct)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write build report and issues log
    report_path = _write_build_report(
        issues, output_dir, total_index, split_distribution=dict(split_counts),
    )
    if issues:
        issues_path = _write_issues_log(issues, output_dir)
        # Print summary by issue type instead of one line per issue
        issue_counts = Counter(e["issue"] for e in issues)
        logger.warning(
            "%d issues across %d records — details in %s",
            len(issues), total_index, issues_path,
        )
        for issue_type, count in issue_counts.most_common():
            logger.warning("  %-25s %d", issue_type, count)
    else:
        logger.info("Build report written to %s (no issues)", report_path)

    # Reconcile with existing HF dataset if requested
    if reconcile:
        issue_ids = {e["id"] for e in issues}
        records = _reconcile_with_hf(records, issue_ids, repo_id)

    # Build HuggingFace Dataset and write Parquet
    ds = Dataset.from_list(records)
    parquet_path = output_dir / "lok_sabha_qa.parquet"
    ds.to_parquet(str(parquet_path))

    logger.info("Dataset written to %s (%d rows)", parquet_path, len(ds))
    logger.info("Columns: %s", ds.column_names)


if __name__ == "__main__":
    app()
