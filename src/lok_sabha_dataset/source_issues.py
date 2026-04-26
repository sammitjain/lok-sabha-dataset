"""Aggregate upstream source-data issues into a public-facing list.

Scans across all ``<data-dir>/<lok>/`` directories and surfaces:
  - download_failed : URLs that failed to download (broken/missing protocol, 5xx, etc.)
  - no_url          : index rows where ``questionsFilePath`` is null upstream
  - nil_only        : parsed source files whose entire content is just ``NIL`` / ``**NIL**``
  - manual          : hand-curated entries from ``<data-dir>/source_issues_manual.jsonl``

Outputs:
  - ``<data-dir>/source_issues.jsonl`` — machine-readable, one issue per line
  - ``SOURCE_ISSUES.md``               — human-readable summary at repo root

Usage:
  uv run python -m lok_sabha_dataset.source_issues
  uv run python -m lok_sabha_dataset.source_issues --data-dir data --md-out SOURCE_ISSUES.md
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import typer

from lok_sabha_dataset.config import DATA_DIR

app = typer.Typer(add_completion=False)


# ── Detection patterns ────────────────────────────────────────────────────────

# Matches text whose entire content (after stripping markdown/whitespace) is just NIL.
# Permissive on case, asterisks, surrounding whitespace, leading list-markers.
_NIL_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?\*{0,2}\s*nil\s*\*{0,2}\s*$",
    re.IGNORECASE,
)

# LS<lok>-S<session>-<TYPE>-<ques_no>[-<date>]
_KEY_RE = re.compile(r"^LS(\d+)-S([A-Za-z0-9]+)-([A-Z]+)-([0-9A-Za-z]+)(?:-.*)?$")

# Filename stems like AS101, AU3712 → ques_type + ques_no
_STEM_RE = re.compile(r"^(AS|AU)(\d+)$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_key(key: str) -> dict[str, Any]:
    """Parse 'LS16-S9-UNSTARRED-4435-12.08.2016' → {lok, session, ques_type, ques_no}."""
    m = _KEY_RE.match(key)
    if not m:
        return {}
    lok, sess, qtype, qno = m.groups()
    return {
        "lok": int(lok),
        "session": int(sess) if sess.isdigit() else sess,
        "ques_type": qtype,
        "ques_no": qno,
    }


def _ques_type_from_stem(stem: str) -> tuple[str | None, str | None]:
    """AS101 → ('STARRED', '101'); AU3712 → ('UNSTARRED', '3712')."""
    m = _STEM_RE.match(stem)
    if not m:
        return None, None
    prefix, num = m.groups()
    return ("STARRED" if prefix == "AS" else "UNSTARRED"), num


def _sort_key(issue: dict) -> tuple:
    qno_raw = issue.get("ques_no") or ""
    qno_int = int(qno_raw) if str(qno_raw).isdigit() else 0
    return (
        issue.get("lok") or 0,
        issue.get("session") or 0,
        issue.get("ques_type") or "",
        qno_int,
        issue.get("kind") or "",
    )


# ── Scanners ──────────────────────────────────────────────────────────────────

def scan_failed_downloads(data_root: Path) -> list[dict]:
    """Read every <data-root>/<lok>/failed_downloads.txt, dedupe entries within each lok."""
    issues: list[dict] = []
    for log in sorted(data_root.glob("*/failed_downloads.txt")):
        try:
            lok = int(log.parent.name)
        except ValueError:
            continue
        seen: set[tuple] = set()
        with log.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) < 4:
                    continue
                session_no, key, url, detail_tail = parts[0], parts[1], parts[2].strip(), "\t".join(parts[3:])
                # Errors can span multiple lines (e.g. httpx adds doc URL); take only the headline
                detail = detail_tail.split("\n")[0].strip()
                dedupe = (key, url, detail[:100])
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                meta = _parse_key(key) or {
                    "lok": lok,
                    "session": int(session_no) if session_no.isdigit() else None,
                    "ques_type": None,
                    "ques_no": None,
                }
                issues.append({
                    **meta,
                    "id": key,
                    "kind": "download_failed",
                    "url": url or None,
                    "filename": None,
                    "detail": detail,
                })
    return issues


def scan_no_url(data_root: Path) -> list[dict]:
    """Read every <data-root>/<lok>/skipped_downloads.txt, surface the no_url rows."""
    issues: list[dict] = []
    for log in sorted(data_root.glob("*/skipped_downloads.txt")):
        try:
            lok = int(log.parent.name)
        except ValueError:
            continue
        seen: set[str] = set()
        with log.open(encoding="utf-8") as f:
            for raw in f:
                parts = raw.rstrip("\n").split("\t")
                if len(parts) < 4 or parts[3] != "no_url":
                    continue
                key = parts[1]
                if key in seen:
                    continue
                seen.add(key)
                meta = _parse_key(key) or {
                    "lok": lok,
                    "session": int(parts[0]) if parts[0].isdigit() else None,
                    "ques_type": None,
                    "ques_no": None,
                }
                issues.append({
                    **meta,
                    "id": key,
                    "kind": "no_url",
                    "url": None,
                    "filename": None,
                    "detail": "questionsFilePath is null in source index",
                })
    return issues


def scan_nil_only(data_root: Path) -> list[dict]:
    """Scan parsed JSONs whose extracted text is just 'NIL' / '**NIL**' (any case)."""
    issues: list[dict] = []
    for parsed_file in sorted(data_root.glob("*/parsed/session_*/*.json")):
        try:
            lok = int(parsed_file.parents[2].name)
        except ValueError:
            continue
        sess_part = parsed_file.parent.name.split("_", 1)
        if len(sess_part) != 2 or not sess_part[1].isdigit():
            continue
        session = int(sess_part[1])

        try:
            with parsed_file.open(encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        text = (data.get("full_markdown") or "").strip()
        if not text or not _NIL_RE.match(text):
            continue

        stem = parsed_file.stem
        qtype, qno = _ques_type_from_stem(stem)
        rec_id = f"LS{lok}-S{session}-{qtype}-{qno}" if qtype and qno else stem
        issues.append({
            "lok": lok,
            "session": session,
            "ques_type": qtype,
            "ques_no": qno,
            "id": rec_id,
            "kind": "nil_only",
            "url": None,
            "filename": data.get("pdf_filename"),
            "detail": f"Source file content is only '{text}'",
        })
    return issues


def load_manual(data_root: Path) -> list[dict]:
    """Read hand-curated entries from <data-root>/source_issues_manual.jsonl (if present)."""
    manual_log = data_root / "source_issues_manual.jsonl"
    if not manual_log.exists():
        return []
    out: list[dict] = []
    with manual_log.open(encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print(f"[warn] skipping malformed manual entry: {line[:80]!r}")
                continue
            entry.setdefault("kind", "manual")
            out.append(entry)
    return out


# ── Output ────────────────────────────────────────────────────────────────────

_KIND_DESCRIPTIONS = {
    "download_failed": (
        "URLs that failed to download from sansad.in (broken protocol, 5xx server "
        "errors, missing files, etc.). The dataset cannot include text for these "
        "questions until the source becomes accessible."
    ),
    "no_url": (
        "Index rows where the `questionsFilePath` field is null in the upstream "
        "metadata — i.e. the question was scheduled but no document was ever published."
    ),
    "nil_only": (
        "Source files whose entire extracted content is the literal string `NIL` "
        "(or `**NIL**`). The document was published but contains no actual "
        "question/answer text."
    ),
    "manual": (
        "Hand-curated entries flagging upstream issues observed during data review — "
        "e.g. duplicate URLs serving different content across question IDs, mismatched "
        "filenames, or known content errors. See `data/source_issues_manual.jsonl`."
    ),
}


def write_markdown(issues: list[dict], out_path: Path) -> None:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        by_kind[issue.get("kind", "unknown")].append(issue)

    by_kind_lok: dict[str, Counter] = {k: Counter(i.get("lok") for i in v) for k, v in by_kind.items()}

    lines: list[str] = []
    lines.append("# Lok Sabha Q&A — Upstream Source Issues")
    lines.append("")
    lines.append(
        "This document tracks upstream-source data issues observed while building the "
        "[opensansad/lok-sabha-qa](https://huggingface.co/datasets/opensansad/lok-sabha-qa) "
        "dataset. These are **not** bugs in our extraction pipeline — they are issues "
        "with the original documents published on [sansad.in](https://sansad.in/)."
    )
    lines.append("")
    lines.append(
        "The full machine-readable list is at "
        "[`data/source_issues.jsonl`](data/source_issues.jsonl) "
        f"({len(issues)} entries total)."
    )
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Issue kind | Total | Per Lok Sabha |")
    lines.append("|---|---:|---|")
    for kind in sorted(by_kind):
        total = len(by_kind[kind])
        per_lok = ", ".join(f"LS{lok}: {n}" for lok, n in sorted(by_kind_lok[kind].items()) if lok is not None)
        lines.append(f"| `{kind}` | {total} | {per_lok or '—'} |")
    lines.append("")

    for kind in sorted(by_kind):
        lines.append(f"## `{kind}`")
        lines.append("")
        lines.append(_KIND_DESCRIPTIONS.get(kind, "_(no description available)_"))
        lines.append("")
        lines.append(f"**Count:** {len(by_kind[kind])}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by `uv run python -m lok_sabha_dataset.source_issues`. "
        "Re-run after each pipeline iteration to refresh."
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ── CLI ───────────────────────────────────────────────────────────────────────

@app.command()
def build(
    data_dir: str = typer.Option(str(DATA_DIR), "--data-dir", help="Root data directory"),
    md_out: str = typer.Option("SOURCE_ISSUES.md", "--md-out", help="Output path for the markdown summary"),
) -> None:
    """Scan all data and rewrite source_issues.jsonl + SOURCE_ISSUES.md from scratch."""
    data_root = Path(data_dir)
    if not data_root.exists():
        raise typer.BadParameter(f"Missing data directory: {data_root}")

    print(f"Scanning {data_root}...")

    print("  failed downloads...", end=" ", flush=True)
    fd = scan_failed_downloads(data_root)
    print(f"{len(fd)}")

    print("  no-URL skips...", end=" ", flush=True)
    nu = scan_no_url(data_root)
    print(f"{len(nu)}")

    print("  parsed files for NIL-only content...", end=" ", flush=True)
    nil = scan_nil_only(data_root)
    print(f"{len(nil)}")

    print("  manual entries...", end=" ", flush=True)
    man = load_manual(data_root)
    print(f"{len(man)}")

    all_issues = sorted(fd + nu + nil + man, key=_sort_key)

    out_jsonl = data_root / "source_issues.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for issue in all_issues:
            f.write(json.dumps(issue, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(all_issues)} issues to {out_jsonl}")

    md_path = Path(md_out)
    write_markdown(all_issues, md_path)
    print(f"Wrote markdown summary to {md_path}")


if __name__ == "__main__":
    app()
