"""Inspect Q/A split outputs from the built dataset.

Usage:
    # Show 5 samples per split method
    uv run python -m lok_sabha_dataset.inspect

    # Show 10 samples for a specific method
    uv run python -m lok_sabha_dataset.inspect --method unsplit --n 10

    # Show a specific record by ID
    uv run python -m lok_sabha_dataset.inspect --id LS18-S2-STARRED-39

    # Preview longer text (default 300 chars)
    uv run python -m lok_sabha_dataset.inspect --preview-len 500
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from datasets import load_dataset

from lok_sabha_dataset.config import OUTPUT_DIR

app = typer.Typer(add_completion=False)


def _preview(text: str | None, max_len: int) -> str:
    if not text:
        return "(empty)"
    t = text[:max_len].replace("\n", "\n    ")
    if len(text) > max_len:
        t += f"\n    ... ({len(text)} chars total)"
    return t


def _print_record(r: dict, preview_len: int) -> None:
    print(f"  ID:       {r['id']}")
    print(f"  Subject:  {r['subject']}")
    print(f"  Ministry: {r['ministry']}")
    print(f"  Members:  {r['members']}")
    print(f"  Method:   {r['qa_split_method']}")
    print(f"  Words:    Q={r['question_word_count']}  A={r['answer_word_count']}  Full={r['full_text_word_count']}")
    print()
    print(f"  ── Question ──")
    print(f"    {_preview(r['question_text'], preview_len)}")
    print()
    print(f"  ── Answer ──")
    print(f"    {_preview(r['answer_text'], preview_len)}")
    print()


@app.command()
def inspect(
    parquet: Path = typer.Option(
        None, help="Path to Parquet file. Default: output/lok_sabha_qa.parquet"
    ),
    method: Optional[str] = typer.Option(
        None, help="Filter by qa_split_method (e.g. 'unsplit', 'heading_answer', 'minister_boundary')"
    ),
    id: Optional[str] = typer.Option(None, help="Show a specific record by ID"),
    n: int = typer.Option(5, help="Number of samples per method"),
    preview_len: int = typer.Option(300, "--preview-len", help="Max chars to show per field"),
) -> None:
    """Inspect Q/A split outputs from the built Parquet dataset."""
    parquet_path = parquet or (OUTPUT_DIR / "lok_sabha_qa.parquet")
    if not parquet_path.exists():
        raise typer.BadParameter(f"Parquet not found: {parquet_path}. Run the build first.")

    ds = load_dataset("parquet", data_files=str(parquet_path), split="train")

    # Single record lookup
    if id:
        for r in ds:
            if r["id"] == id:
                print(f"\n{'='*70}")
                _print_record(r, preview_len)
                return
        print(f"Record not found: {id}")
        raise typer.Exit(1)

    # Group by method
    from collections import defaultdict
    by_method: dict[str, list[dict]] = defaultdict(list)
    for r in ds:
        by_method[r["qa_split_method"]].append(r)

    methods_to_show = [method] if method else sorted(by_method.keys())

    for m in methods_to_show:
        rows = by_method.get(m, [])
        if not rows:
            print(f"\nNo records with method '{m}'")
            continue

        print(f"\n{'='*70}")
        print(f"  METHOD: {m}  ({len(rows)} records)")
        print(f"{'='*70}")

        for i, r in enumerate(rows[:n]):
            print(f"\n  --- Sample {i+1}/{min(n, len(rows))} ---")
            _print_record(r, preview_len)


if __name__ == "__main__":
    app()
