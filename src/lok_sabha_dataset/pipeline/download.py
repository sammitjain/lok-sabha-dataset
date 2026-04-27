"""Download Lok Sabha Q&A PDFs for a curated dataset.

Assumes you already ran metadata curation and have per-session JSONL files:
  <data-dir>/<lok>/index_session_<n>.jsonl

Downloads PDFs referenced by `questionsFilePath` (English by default) into:
  <data-dir>/<lok>/pdfs/session_<n>/

Usage:
  uv run python -m lok_sabha_dataset.pipeline.download --lok 18
  uv run python -m lok_sabha_dataset.pipeline.download --lok 18 --sessions 7
  uv run python -m lok_sabha_dataset.pipeline.download --lok 18 --sessions 5-7 --include-hindi
  uv run python -m lok_sabha_dataset.pipeline.download --lok 18 --skip-old  # skip questions already in HF

Notes:
- Idempotent: skips files that already exist.
- Polite crawling: sleeps a small random amount between downloads.
- Atomic writes: streams to .part then renames.
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Iterable, List, Optional

import httpx
import typer

from lok_sabha_dataset.config import DATA_DIR
from lok_sabha_dataset.pipeline.utils import parse_sessions

app = typer.Typer(no_args_is_help=True)


def _iter_index_files(data_dir: Path, sessions: Optional[List[int]]) -> Iterable[Path]:
    if sessions:
        for s in sessions:
            p = data_dir / f"index_session_{s}.jsonl"
            if p.exists():
                yield p
            else:
                print(f"[warn] missing index file: {p}")
    else:
        yield from sorted(data_dir.glob("index_session_*.jsonl"))


def _load_hf_ids(repo_id: str) -> set[str]:
    """Load IDs from HF dataset that already have full_text populated."""
    from datasets import load_dataset

    print(f"Loading existing dataset from HuggingFace: {repo_id}")
    ds = load_dataset(repo_id, split="train")
    ids = {row["id"] for row in ds if row.get("full_text")}
    print(f"  {len(ids)} questions already have full_text in HF")
    return ids


def _make_id(lok: int, session_no: int | str, row: dict) -> str:
    """Construct a record ID from an index row, matching build.py format."""
    return f"LS{lok}-S{session_no}-{row.get('type', '')}-{row.get('ques_no')}"


def _filename_from_url(url: str) -> str:
    """Extract the filename from a sansad.in download URL (PDF, DOCX, DOC, etc.)."""
    fname = url.split("/")[-1].split("?")[0]
    return fname if fname else "file.bin"


def download_file(
    client: httpx.Client,
    url: str,
    dest: Path,
    *,
    overwrite: bool = False,
) -> bool:
    """Download url to dest. Returns True if downloaded, False if skipped."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not overwrite:
        return False

    part = dest.with_suffix(dest.suffix + ".part")
    if part.exists():
        part.unlink(missing_ok=True)

    with client.stream("GET", url, timeout=120) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    part.replace(dest)
    return True


@app.command()
def run(
    lok: int = typer.Option(..., help="Lok Sabha number, e.g. 18"),
    sessions: Optional[str] = typer.Option(None, help="Sessions like '7' or '1-7' or '1,3,7'. If omitted, all session files in data/<lok>/ are used."),
    base_dir: str = typer.Option(str(DATA_DIR), "--data-dir", help="Base data directory"),
    include_hindi: bool = typer.Option(False, help="Also download questionsFilePathHindi"),
    sleep_min: float = typer.Option(0.2, help="Min seconds between downloads"),
    sleep_max: float = typer.Option(0.6, help="Max seconds between downloads"),
    overwrite: bool = typer.Option(False, help="Re-download even if file exists"),
    max_files: Optional[int] = typer.Option(None, help="Stop after downloading N files (for testing)"),
    skip_old: bool = typer.Option(False, help="Skip questions that already have full_text in the HF dataset"),
    repo_id: str = typer.Option("opensansad/lok-sabha-qa", help="HuggingFace repo ID (used with --skip-old)"),
) -> None:
    data_dir = Path(base_dir) / str(lok)
    if not data_dir.exists():
        raise typer.BadParameter(f"Missing data directory: {data_dir}")

    sess_list = parse_sessions(sessions) if sessions else None
    index_files = list(_iter_index_files(data_dir, sess_list))
    if not index_files:
        raise typer.BadParameter(f"No index_session_*.jsonl files found in {data_dir}")

    hf_ids: set[str] = _load_hf_ids(repo_id) if skip_old else set()

    pdf_root = data_dir / "pdfs"

    downloaded = 0
    skipped = 0
    skipped_hf = 0
    no_url = 0
    errors = 0
    processed = 0
    last_report = time.time()
    report_interval = 15  # seconds between progress prints
    failed_log = data_dir / "failed_downloads.txt"
    skipped_log = data_dir / "skipped_downloads.txt"

    with httpx.Client(headers={"User-Agent": "opensansad/0.1"}, follow_redirects=True) as client:
        for index_path in index_files:
            # infer session from filename
            m = re.search(r"index_session_(\d+)\.jsonl$", index_path.name)
            session_no = m.group(1) if m else "unknown"
            out_dir = pdf_root / f"session_{session_no}"

            print(f"Index: {index_path.name} -> {out_dir}")

            with index_path.open("r", encoding="utf-8") as f:
                for line in f:
                    obj = json.loads(line)
                    key = obj.get("key", f"S{session_no}-{obj.get('ques_no')}")

                    if hf_ids:
                        rec_id = _make_id(lok, session_no, obj)
                        if rec_id in hf_ids:
                            skipped_hf += 1
                            with skipped_log.open("a", encoding="utf-8") as sl:
                                sl.write(f"{session_no}\t{key}\t{obj.get('questionsFilePath', '')}\thf_exists\n")
                            continue

                    urls = []
                    url_en = obj.get("questionsFilePath")
                    if url_en:
                        urls.append((url_en, out_dir))
                    else:
                        no_url += 1
                        with skipped_log.open("a", encoding="utf-8") as sl:
                            sl.write(f"{session_no}\t{key}\t\tno_url\n")

                    if include_hindi:
                        url_hi = obj.get("questionsFilePathHindi")
                        if url_hi:
                            urls.append((url_hi, out_dir / "hi"))

                    for url, ddir in urls:
                        did = False
                        try:
                            fname = _filename_from_url(url)
                            dest = ddir / fname
                            did = download_file(client, url, dest, overwrite=overwrite)
                            if did:
                                downloaded += 1
                            else:
                                skipped += 1
                                with skipped_log.open("a", encoding="utf-8") as sl:
                                    sl.write(f"{session_no}\t{key}\t{url}\tdisk_exists\n")
                            processed += 1

                            # lightweight periodic progress update
                            now = time.time()
                            if now - last_report >= report_interval:
                                print(f"Progress: processed={processed} downloaded={downloaded} skipped={skipped} skipped_hf={skipped_hf} errors={errors}")
                                last_report = now
                        except Exception as e:
                            errors += 1
                            print(f"[error] {url} -> {e}")
                            with failed_log.open("a", encoding="utf-8") as fl:
                                fl.write(f"{session_no}\t{key}\t{url}\t{e}\n")
                        if max_files is not None and downloaded >= max_files:
                            print("Reached --max-files limit")
                            print(f"Downloaded: {downloaded}, skipped: {skipped}, errors: {errors}")
                            return

                        if did and sleep_max > 0:
                            lo = max(0.0, sleep_min)
                            hi = max(lo, sleep_max)
                            time.sleep(lo + random.random() * (hi - lo))

    print(f"\nDone.")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped (already on disk): {skipped}")
    if hf_ids:
        print(f"Skipped (already in HF):  {skipped_hf}")
    if no_url:
        print(f"Skipped (no URL in index): {no_url}")
    print(f"Errors: {errors}")
    print(f"PDF root: {pdf_root}")
    if skipped or skipped_hf or no_url:
        print(f"Skip log: {skipped_log}")


if __name__ == "__main__":
    app()
