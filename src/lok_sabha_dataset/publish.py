"""Publish the Lok Sabha Q&A dataset to HuggingFace Hub.

Usage:
    uv run python -m lok_sabha_dataset.publish                    # dry-run (preview)
    uv run python -m lok_sabha_dataset.publish --push             # actually push
    uv run python -m lok_sabha_dataset.publish --push --private   # push as private
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from lok_sabha_dataset.config import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

app = typer.Typer()

# ── Config ───────────────────────────────────────────────────────────────────

REPO_ID = "opensansad/lok-sabha-qa"
PARQUET_PATH = Path("output/lok_sabha_qa.parquet")
DATASET_CARD_PATH = Path(__file__).resolve().parent.parent.parent / "DATASET_CARD.md"

# Supplementary JSON files to upload per Lok Sabha number
_SUPPLEMENTARY_FILES = ["members.json", "ministries.json"]

# Columns to drop before publishing (internal / empty)
_DROP_COLS = [
    "answering_minister",   # not yet populated
    "pdf_filename",         # internal build detail
    "extraction_engine",    # internal build detail
    "qa_split_method",      # internal build detail
    "full_text_word_count", # redundant (question + answer word counts exist)
]


def _load_and_clean(parquet_path: Path):
    """Load dataset from parquet, drop internal columns, return HF Dataset."""
    from datasets import Dataset

    ds = Dataset.from_parquet(str(parquet_path))
    for col in _DROP_COLS:
        if col in ds.column_names:
            ds = ds.remove_columns(col)
    return ds


def _read_dataset_card() -> str:
    """Read the dataset card from DATASET_CARD.md."""
    if not DATASET_CARD_PATH.exists():
        log.error(f"Dataset card not found: {DATASET_CARD_PATH}")
        raise FileNotFoundError(DATASET_CARD_PATH)
    return DATASET_CARD_PATH.read_text()


def _discover_supplementary(data_dir: Path) -> list[tuple[Path, str]]:
    """Find supplementary JSON files to upload, organized by Lok Sabha number.

    Returns a list of (local_path, path_in_repo) tuples.
    E.g., (data/18/members.json, "supplementary/18/members.json")
    """
    files: list[tuple[Path, str]] = []
    for lok_dir in sorted(data_dir.iterdir()):
        if not lok_dir.is_dir() or not lok_dir.name.isdigit():
            continue
        lok_no = lok_dir.name
        for fname in _SUPPLEMENTARY_FILES:
            fpath = lok_dir / fname
            if fpath.exists():
                repo_path = f"supplementary/{lok_no}/{fname}"
                files.append((fpath, repo_path))
    return files


@app.command()
def main(
    parquet: Path = typer.Option(PARQUET_PATH, help="Path to built parquet file"),
    data_dir: Path = typer.Option(DATA_DIR, "--data-dir", help="Data directory (for supplementary files)"),
    repo_id: str = typer.Option(REPO_ID, help="HuggingFace repo ID"),
    push: bool = typer.Option(False, help="Actually push to HuggingFace Hub"),
    private: bool = typer.Option(False, help="Make the dataset private"),
):
    """Preview or publish the dataset to HuggingFace Hub."""
    if not parquet.exists():
        log.error(f"Parquet file not found: {parquet}")
        log.error("Run `uv run python -m lok_sabha_dataset.build` first.")
        raise typer.Exit(1)

    ds = _load_and_clean(parquet)
    card = _read_dataset_card()
    supplementary = _discover_supplementary(data_dir)

    log.info(f"Dataset: {len(ds)} rows, {len(ds.column_names)} columns")
    log.info(f"Columns: {ds.column_names}")
    log.info(f"Target repo: {repo_id}")
    log.info(f"Supplementary files: {len(supplementary)}")
    for local, repo_path in supplementary:
        log.info(f"  {local} -> {repo_path}")

    if not push:
        log.info("")
        log.info("DRY RUN — showing what would be published:")
        log.info(f"  Rows: {len(ds)}")
        log.info(f"  Columns: {ds.column_names}")
        log.info(f"  Repo: {repo_id}")
        log.info(f"  Dataset card: {DATASET_CARD_PATH}")
        log.info(f"  Supplementary: {[rp for _, rp in supplementary]}")
        log.info("")
        log.info("To actually push, run with --push")
        return

    from huggingface_hub import HfApi

    api = HfApi()

    log.info("Pushing dataset to HuggingFace Hub...")
    ds.push_to_hub(
        repo_id,
        private=private,
        commit_message="Update Lok Sabha Q&A dataset",
    )

    # Upload the dataset card
    api.upload_file(
        path_or_fileobj=card.encode(),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Update dataset card",
    )

    # Upload supplementary files (members.json, ministries.json per lok)
    for local_path, repo_path in supplementary:
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=repo_path,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Update {repo_path}",
        )
        log.info(f"  Uploaded {repo_path}")

    log.info(f"Published to https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    app()
