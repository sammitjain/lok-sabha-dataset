"""Curate metadata for Lok Sabha Q&A (session-aware).

Uses the sansad.in API to discover sessions and fetch Q&A metadata.

Outputs (inside <data-dir>/<lok_no>/):
- members.json
- ministries.json
- loksabha_sessions.json      (session periods + dates)
- progress.json               (tracks completed sessions)
- index_session_<n>.jsonl     (per-session Q&A index)

Run:
  uv run python -m lok_sabha_dataset.pipeline.curate run --lok 18
  uv run python -m lok_sabha_dataset.pipeline.curate run --lok 18 --sessions 5-7

Notes:
- The Q&A feed gives display names; we map names -> canonical IDs using masters.
- Per-session JSONL is written to a .tmp file and atomically renamed on success.
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import typer

from lok_sabha_dataset.config import DATA_DIR
from lok_sabha_dataset.pipeline.utils import parse_sessions

app = typer.Typer(no_args_is_help=True)

API_Q = "https://sansad.in/api_ls/question/qetFilteredQuestionsAns"

API_MEMBERS = "https://sansad.in/api_ls/question/getMembers"

API_MINISTRY = "https://sansad.in/api_ls/question/getMinistry"
# Known ministry name variants across endpoints / time.
# Key and value are compared after _norm() (uppercase, whitespace-collapsed).
MINISTRY_ALIASES: Dict[str, str] = {
    "COMMUNICATION": "COMMUNICATIONS",
}

API_SESSIONS = "https://sansad.in/api_ls/business/AllLoksabhaAndSessionDates"


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def _fetch_json(client: httpx.Client, url: str, params: Optional[dict] = None):
    r = client.get(url, params=params or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _discover_sessions(client: httpx.Client, lok: int) -> tuple[List[int], dict]:
    """Return session numbers for a given Lok Sabha and the matching metadata blob."""
    payload = _fetch_json(client, API_SESSIONS)
    if not isinstance(payload, list):
        return [], {"raw": payload}

    for row in payload:
        if isinstance(row, dict) and row.get("loksabha") == lok:
            sessions = row.get("sessions") or []
            sess_nos = sorted({int(s.get("sessionNo")) for s in sessions if isinstance(s, dict) and s.get("sessionNo") is not None})
            return sess_nos, row

    return [], {"raw": payload}


def _build_member_lookup(members: List[dict]) -> Dict[str, int]:
    by_name: Dict[str, int] = {}
    for m in members:
        mp_no = m.get("mpNo")
        if mp_no is None:
            continue
        for key in ("mpName", "mpNameHindi"):
            name = m.get(key) or ""
            if name.strip():
                by_name[_norm(name)] = int(mp_no)
    return by_name


def _build_ministry_lookup(ministries: List[dict]) -> Dict[str, int]:
    by_name: Dict[str, int] = {}
    for m in ministries:
        code = m.get("minCode")
        if code is None:
            continue
        for key in ("minName", "minNameHindi"):
            name = m.get(key) or ""
            if name.strip():
                by_name[_norm(name)] = int(code)
    return by_name


def _derive_key(lok: int, q: dict) -> str:
    qno = q.get("quesNo")
    sess = q.get("sessionNo")
    qtype = (q.get("type") or "").strip()
    date = (q.get("date") or "").strip()
    return f"LS{lok}-S{sess}-{qtype}-{qno}-{date}"


def _normalize_record(lok: int, q: dict, mp_lookup: Dict[str, int], min_lookup: Dict[str, int]) -> dict:
    member_names = [m.strip() for m in (q.get("member") or []) if isinstance(m, str)]
    mp_nos: List[int] = []
    unmatched_members: List[str] = []
    for name in member_names:
        mp_no = mp_lookup.get(_norm(name))
        if mp_no is None:
            unmatched_members.append(name)
        else:
            mp_nos.append(mp_no)
    ministry_name = (q.get("ministry") or "").strip()
    mkey = _norm(ministry_name)
    mkey = MINISTRY_ALIASES.get(mkey, mkey)
    min_code = min_lookup.get(mkey)

    return {
        "key": _derive_key(lok, q),
        "lok_no": int(q.get("lokNo") or lok),
        "session_no": int(q.get("sessionNo")) if q.get("sessionNo") else None,
        "ques_no": int(q.get("quesNo")) if q.get("quesNo") is not None else None,
        "type": (q.get("type") or "").strip(),
        "date": (q.get("date") or "").strip(),
        "subjects": (q.get("subjects") or "").strip(),
        "mp_nos": mp_nos,
        "min_code": min_code,
        "members": member_names,
        "ministry": ministry_name,
        "unmatched_members": unmatched_members,
        "unmatched_ministry": None if min_code is not None else (ministry_name or None),
        "questionsFilePath": q.get("questionsFilePath"),
        "questionsFilePathHindi": q.get("questionsFilePathHindi"),
        "raw": q,
    }


def _extract_questions(payload: object) -> List[dict]:
    # Typical: [ { "listOfQuestions": [ ... ] } ]
    if isinstance(payload, dict):
        qs = payload.get("listOfQuestions") or []
        return [q for q in qs if isinstance(q, dict)]

    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            qs = first.get("listOfQuestions") or []
            return [q for q in qs if isinstance(q, dict)]

    return []


@app.command()
def run(
    lok: int = typer.Option(18, help="Lok Sabha number"),
    sessions: Optional[str] = typer.Option(None, help="Override sessions, e.g. '1-7' or '1,2,5-8'. If omitted, auto-discovered."),
    page_size: int = typer.Option(100, help="Page size for Q&A feed"),
    base_dir: str = typer.Option(str(DATA_DIR), "--data-dir", help="Base data directory"),
    locale: str = typer.Option("en", help="Locale for ministry endpoint and Q&A feed"),
    sleep_min: float = typer.Option(0.2, help="Min seconds between page requests"),
    sleep_max: float = typer.Option(0.6, help="Max seconds between page requests"),
    resume: bool = typer.Option(True, help="Skip sessions already marked complete in progress.json"),
    force: bool = typer.Option(False, help="Re-run sessions even if marked complete"),
) -> None:
    out_dir = Path(base_dir) / str(lok)
    _ensure_dir(out_dir)

    out_members = out_dir / "members.json"
    out_ministries = out_dir / "ministries.json"
    out_sessions = out_dir / "loksabha_sessions.json"
    progress_path = out_dir / "progress.json"

    def load_progress() -> dict:
        if progress_path.exists():
            try:
                return json.loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_progress(p: dict) -> None:
        progress_path.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

    progress = load_progress()
    completed_sessions = set(progress.get("completed_sessions", []))

    with httpx.Client(headers={"User-Agent": "opensansad/0.1"}) as client:
        # Session discovery
        discovered, session_blob = _discover_sessions(client, lok)
        out_sessions.write_text(json.dumps(session_blob, ensure_ascii=False, indent=2), encoding="utf-8")

        sessions_list = parse_sessions(sessions) if sessions else discovered
        if not sessions_list:
            raise typer.BadParameter(f"No sessions found for lok={lok}. (Saved raw response to {out_sessions})")

        # Master: members
        members = _fetch_json(client, API_MEMBERS, {"lkNo": lok})
        out_members.write_text(json.dumps(members, ensure_ascii=False, indent=2), encoding="utf-8")
        mp_lookup = _build_member_lookup(members if isinstance(members, list) else [])

        # Master: ministries
        ministries = _fetch_json(client, API_MINISTRY, {"lkNo": lok, "locale": locale})
        out_ministries.write_text(json.dumps(ministries, ensure_ascii=False, indent=2), encoding="utf-8")
        min_lookup = _build_ministry_lookup(ministries if isinstance(ministries, list) else [])

        total = 0
        unmatched_mp_recs = 0
        unmatched_min_recs = 0

        for sess in sessions_list:
            if resume and (sess in completed_sessions) and not force:
                print(f"Session {sess}... (already complete, skipping)")
                continue

            out_session = out_dir / f"index_session_{sess}.jsonl"
            tmp_session = out_dir / f"index_session_{sess}.jsonl.tmp"
            tmp_session.unlink(missing_ok=True)

            print(f"Session {sess}...")
            page_no = 1
            wrote_this_session = 0

            with tmp_session.open("a", encoding="utf-8") as f:
                while True:
                    payload = _fetch_json(
                        client,
                        API_Q,
                        {
                            "loksabhaNo": lok,
                            "sessionNumber": sess,
                            "pageNo": page_no,
                            "pageSize": page_size,
                            "locale": locale,
                        },
                    )

                    questions = _extract_questions(payload)
                    if not questions:
                        if page_no == 1:
                            print(f"  (no questions found, skipping session {sess})")
                        break

                    for q in questions:
                        rec = _normalize_record(lok, q, mp_lookup, min_lookup)
                        if rec["unmatched_members"]:
                            unmatched_mp_recs += 1
                        if rec["unmatched_ministry"]:
                            unmatched_min_recs += 1
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        total += 1
                        wrote_this_session += 1

                    print(f"  page {page_no}: {len(questions)}")

                    if sleep_max > 0:
                        lo = max(0.0, sleep_min)
                        hi = max(lo, sleep_max)
                        time.sleep(lo + random.random() * (hi - lo))

                    if len(questions) < page_size:
                        break
                    page_no += 1

            if wrote_this_session > 0:
                tmp_session.replace(out_session)
                completed_sessions.add(sess)
                progress["completed_sessions"] = sorted(completed_sessions)
                save_progress(progress)
                print(f"  session {sess} complete -> {out_session} ({wrote_this_session} records)")
            else:
                tmp_session.unlink(missing_ok=True)

    print(f"\nWrote {total} total records under {out_dir}")
    print(f"Saved members -> {out_members}")
    print(f"Saved ministries -> {out_ministries}")
    print(f"Saved session calendar -> {out_sessions}")
    print(f"Progress -> {progress_path}")
    print(f"Unmatched MP records: {unmatched_mp_recs}")
    print(f"Unmatched ministry records: {unmatched_min_recs}")


if __name__ == "__main__":
    app()
