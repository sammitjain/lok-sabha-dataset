"""Utilities for loading data from the lok-sabha-rag data directory."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


def convert_date(raw: str | None) -> str | None:
    """Convert DD.MM.YYYY -> YYYY-MM-DD.  Pass through anything else as-is."""
    if not raw:
        return None
    m = _DATE_RE.match(raw.strip())
    if not m:
        return raw.strip() or None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def pdf_filename_from_url(url: str | None) -> str | None:
    """Extract PDF filename from a sansad.in download URL.

    >>> pdf_filename_from_url("https://sansad.in/getFile/.../AS280_6OmUWJ.pdf?source=pqals")
    'AS280_6OmUWJ.pdf'
    """
    if not url:
        return None
    fname = url.split("/")[-1].split("?")[0]
    return fname if fname else None


def load_index_session(base_dir: Path, lok_no: int, session_no: int) -> list[dict[str, Any]]:
    """Load all records from an index_session_N.jsonl file."""
    path = base_dir / str(lok_no) / f"index_session_{session_no}.jsonl"
    if not path.exists():
        logger.warning("Index file not found: %s", path)
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Malformed JSON at %s:%d", path, line_no)
    return records


def load_parsed_json(
    base_dir: Path, lok_no: int, session_no: int, pdf_filename: str
) -> dict[str, Any] | None:
    """Load the parsed text JSON for a given PDF.

    The parsed JSON lives at: base_dir/<lok>/parsed/session_<N>/<stem>.json
    """
    stem = pdf_filename.rsplit(".", 1)[0]  # "AS280_6OmUWJ.pdf" -> "AS280_6OmUWJ"
    path = base_dir / str(lok_no) / "parsed" / f"session_{session_no}" / f"{stem}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load parsed JSON %s: %s", path, exc)
        return None


def load_members(base_dir: Path, lok_no: int) -> list[dict[str, Any]]:
    """Load members.json for a Lok Sabha."""
    path = base_dir / str(lok_no) / "members.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_ministries(base_dir: Path, lok_no: int) -> list[dict[str, Any]]:
    """Load ministries.json for a Lok Sabha."""
    path = base_dir / str(lok_no) / "ministries.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)
