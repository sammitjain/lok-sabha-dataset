"""Split Lok Sabha Q&A markdown into question_text and answer_text.

Strategy chain (ordered by reliability):
  1.  heading_answer           — split on `## ANSWER` line (~95.6% of docs)
  2.  spaced_heading_answer    — split on `## A N S W E R` (Docling artifact, ~0.8%)
  3.  standalone_answer        — split on `ANSWER` without ## prefix (~1.0%)
  4.  spaced_standalone_answer — split on `A N S W E R` without ## (~0.1%)
  5.  table_answer             — split on `| ANSWER` in table rows (~0.2%)
  6.  inline_answer            — split on mid-line `ANSWER MINISTER` after punctuation (~0.1%)
  7.  statement_referred       — split on `## STATEMENT REFERRED` (starred Qs)
  8.  minister_boundary        — split on `## MINISTER OF` line (~1.8%)
  9.  minister_boundary_bare   — split on `MINISTER OF STATE` without ## (~0.1%)
  10. table_minister           — split on `| MINISTER` in table rows
  11. hindi_answer             — split on Hindi `## उत्तर` marker (with spaced variants)
  12. hindi_standalone_answer  — split on Hindi `उत्तर` standalone (line-only)
  13. hindi_minister           — split on Hindi `## ...मंत्री` heading
  14. inline_minister          — split on mid-line `MINISTER OF` after `?`
  15. inline_answer_bare       — split on mid-line `ANSWER` after `?` (no MINISTER)
  16. unsplit                  — no split possible (remainder)

Each strategy also:
  - Strips the government header from the question portion
  - Strips trailing ***** footer separators
  - Decodes common HTML entities
"""

from __future__ import annotations

import html
import re

# ── Header / footer patterns ─────────────────────────────────────────────────

# Government header ends before the question number + asker line.
# We look for the first line that starts a question (number + asker name).
# Starred: `*39.`, `## *39.`, `*102. SHRI ...`, `† *140.`
# Unstarred: `727.`, `## 727.`, `## † 3419.`
_QUESTION_START_RE = re.compile(
    r"^(?:##\s*)?(?:[†*§]\s*)*(\d+)\.\s",
    re.MULTILINE,
)

# Footer: trailing asterisks
_FOOTER_RE = re.compile(r"\n[*]{3,}\s*$")

# Fallback question boundary for reversed documents where OCR garbles the
# question number (e.g. `t*326.` instead of `*326.`). We look for the canonical
# "pleased to state" phrase that appears in every parliamentary question.
_PLEASED_TO_STATE_RE = re.compile(
    r"pleased\s+to\s+state",
    re.IGNORECASE,
)


# ── Answer boundary patterns ─────────────────────────────────────────────────

# Strategy 1: `## ANSWER` or `## Answer` (case-insensitive, with or without minister name)
# Also handles Docling artifacts like `## \2\ ANSWER`
_HEADING_ANSWER_RE = re.compile(
    r"^(##\s*(?:\\[^\\]*\\\s*)?ANSWER\b.*)",
    re.MULTILINE | re.IGNORECASE,
)

# Strategy 2: `## A N S W E R` — Docling sometimes spaces out the letters
_SPACED_HEADING_ANSWER_RE = re.compile(
    r"^(##\s+A\s+N\s+S\s+W\s+E\s+R\b.*)",
    re.MULTILINE,
)

# Strategy 3: `ANSWER` without `##` prefix (standalone or with minister name)
_STANDALONE_ANSWER_RE = re.compile(
    r"^(ANSWER\s.*)",
    re.MULTILINE | re.IGNORECASE,
)

# Strategy 4: `A N S W E R` without ## prefix
_SPACED_STANDALONE_ANSWER_RE = re.compile(
    r"^(A\s+N\s+S\s+W\s+E\s+R\b.*)",
    re.MULTILINE,
)

# Strategy 5: ANSWER inside a markdown table row: `| ANSWER ...`
_TABLE_ANSWER_RE = re.compile(
    r"^(\|\s*ANSWER\b.*)",
    re.MULTILINE,
)

# Strategy 6: Mid-line ANSWER (after punctuation like `;` or `?` or `)`)
# This catches cases where ANSWER runs inline with the last sub-question.
# Also matches spaced `A N S W E R` and `ANSWER` followed by newline then MINISTER.
_INLINE_ANSWER_RE = re.compile(
    r"[;?.)\s]\s*((?:A\s+N\s+S\s+W\s+E\s+R|ANSWER)\s+(?:THE\s+)?MINISTER\b.*)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

# Strategy 7: `## STATEMENT REFERRED` — used in Starred questions where the
# minister says "A statement is laid on the Table of the House" and the
# actual answer follows under the STATEMENT REFERRED heading.
_STATEMENT_REFERRED_RE = re.compile(
    r"^(##\s*STATEMENT\s+REFERRED\b.*)",
    re.MULTILINE | re.IGNORECASE,
)

# Strategy 8: `## MINISTER OF` or `## THE MINISTER OF` (no ANSWER marker at all)
# Also handles OCR artifacts: `MINISTEROF` (missing space), mixed case `oF`
_MINISTER_BOUNDARY_RE = re.compile(
    r"^(## (?:THE\s+)?MINISTER\s*(?:OF|FOR)\b.*)",
    re.MULTILINE | re.IGNORECASE,
)

# Strategy 9: `MINISTER OF ...` without `##` prefix (case-insensitive)
# Catches patterns like "MINISTER OF STEEL (SHRI ...)", "Minister of State in the Ministry of ...",
# "THE MINISTER OF LABOUR AND EMPLOYMENT (DR. ...)", etc.
# Also handles OCR artifact `MINISTEROF` (missing space)
_MINISTER_BOUNDARY_BARE_RE = re.compile(
    r"^((?:THE\s+)?MINISTER\s*OF\s+\w.*)",
    re.MULTILINE | re.IGNORECASE,
)

# Strategy 10: MINISTER inside a markdown table row: `| THE MINISTER` or `| MINISTER`
_TABLE_MINISTER_RE = re.compile(
    r"^(\|\s*(?:THE\s+)?MINISTER\s+(?:OF|FOR)\b.*)",
    re.MULTILINE | re.IGNORECASE,
)

# Strategy 11: Hindi answer marker `## उत्तर` — with spaced and garbled variants:
#   `## उत्तर`   — standard
#   `## उत्  तर`  — spaces inside
#   `## उ×  तर`   — × instead of त्
#   `## उत्  तय`  — garbled ending
_HINDI_ANSWER_RE = re.compile(
    r"^(##\s*उ[त×]्?\s*त[रय]\b.*)",
    re.MULTILINE,
)

# Strategy 12: Hindi `उत्तर` standalone on its own line (no ## prefix).
# Uses $ anchor to avoid matching `उत्तर प्रदेश` (Uttar Pradesh).
_HINDI_STANDALONE_ANSWER_RE = re.compile(
    r"^(उ[त×]्?\s*त[रय]\s*)$",
    re.MULTILINE,
)

# Strategy 13: Hindi minister heading — `## ... राज्य मंत्री` / `## ... मं�ी`
# The `मंत्री` (minister) at end-of-line distinguishes from `मंत्रालय` (ministry).
# Uses `.` to match replacement character U+FFFD in garbled encoding.
_HINDI_MINISTER_RE = re.compile(
    r"^(##\s+.*(?:मंत्री|मं.ी)\s*)$",
    re.MULTILINE,
)

# Strategy 14: Mid-line MINISTER after `?` — question ends with `?` then
# MINISTER OF STATE appears on the same line without any ANSWER marker.
_INLINE_MINISTER_RE = re.compile(
    r"[?]\s*((?:THE\s+)?MINISTER\s*(?:OF|FOR)\s.*)",
    re.DOTALL | re.IGNORECASE,
)

# Strategy 15: Mid-line `ANSWER` after `?` without requiring MINISTER.
# Catches table layouts where question column ends with `?` then `ANSWER` column starts.
# Negative lookahead excludes preamble text like `FOR ANSWER ON 18.12.2024`.
_INLINE_ANSWER_BARE_RE = re.compile(
    r"[?]\s*(ANSWER\b(?!\s+ON\s+\d).*)",
    re.DOTALL | re.IGNORECASE,
)


# ── Cleaning helpers ─────────────────────────────────────────────────────────

def _strip_header(text: str) -> str:
    """Strip the government header, keeping from the question number onwards.

    The header typically contains:
      ## GOVERNMENT OF INDIA ...
      ## LOK SABHA [UN]STARRED QUESTION NO. ...
      TO BE ANSWERED ON ...

    We keep from the question number line (e.g., `*39. SHRI ...` or `727. DR. ...`).
    If we can't find the question start, return the text as-is.
    """
    m = _QUESTION_START_RE.search(text)
    if m:
        # Walk back to the start of this line (or the subject heading above it)
        line_start = text.rfind("\n", 0, m.start())
        # Check if the line before is a subject heading (## SUBJECT or just a short line)
        if line_start > 0:
            prev_line_start = text.rfind("\n", 0, line_start)
            prev_line = text[prev_line_start + 1 : line_start].strip()
            # If the previous line looks like a subject heading, include it
            if prev_line and not any(
                kw in prev_line.upper()
                for kw in ["GOVERNMENT OF INDIA", "LOK SABHA", "TO BE ANSWERED", "MINISTRY OF"]
            ):
                return text[prev_line_start + 1 :].strip()
        return text[line_start + 1 :].strip()
    return text.strip()


def _strip_footer(text: str) -> str:
    """Remove trailing ***** separators."""
    return _FOOTER_RE.sub("", text).rstrip()


def _clean_text(text: str) -> str:
    """Apply common text cleanups."""
    # Decode HTML entities
    text = html.unescape(text)
    # Normalize whitespace (but keep newlines for structure)
    text = re.sub(r"[ \t]+", " ", text)
    # Remove trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()


# ── Main splitter ─────────────────────────────────────────────────────────────

def split_question_answer(full_markdown: str) -> tuple[str | None, str | None, str]:
    """Split parliamentary Q&A markdown into question and answer portions.

    Parameters
    ----------
    full_markdown : str
        The complete extracted markdown text from a Lok Sabha Q&A PDF.

    Returns
    -------
    (question_text, answer_text, method)
        question_text : cleaned question portion (or None if unsplittable)
        answer_text   : cleaned answer portion (or None if unsplittable)
        method        : which strategy was used
    """
    if not full_markdown or not full_markdown.strip():
        return None, None, "empty"

    text = full_markdown

    # Try each line-start strategy in order
    for strategy_name, pattern in [
        ("heading_answer", _HEADING_ANSWER_RE),
        ("spaced_heading_answer", _SPACED_HEADING_ANSWER_RE),
        ("standalone_answer", _STANDALONE_ANSWER_RE),
        ("spaced_standalone_answer", _SPACED_STANDALONE_ANSWER_RE),
        ("table_answer", _TABLE_ANSWER_RE),
        ("statement_referred", _STATEMENT_REFERRED_RE),
        ("minister_boundary", _MINISTER_BOUNDARY_RE),
        ("minister_boundary_bare", _MINISTER_BOUNDARY_BARE_RE),
        ("table_minister", _TABLE_MINISTER_RE),
        ("hindi_answer", _HINDI_ANSWER_RE),
        ("hindi_standalone_answer", _HINDI_STANDALONE_ANSWER_RE),
        ("hindi_minister", _HINDI_MINISTER_RE),
    ]:
        m = pattern.search(text)
        if m:
            raw_question = text[: m.start()]
            raw_answer = text[m.start() :]

            question_text = _clean_text(_strip_footer(_strip_header(raw_question)))
            answer_text = _clean_text(_strip_footer(raw_answer))

            # Sanity check: both parts should have some content
            if question_text and answer_text:
                return question_text, answer_text, strategy_name

            # Handle reversed documents: ANSWER at the top, question below.
            # If raw_question is empty but raw_answer contains the question text,
            # look for the question start inside the answer portion.
            if not question_text and answer_text:
                q_in_answer = _QUESTION_START_RE.search(raw_answer)
                # Fallback: look for "pleased to state" if question number not found
                # (OCR can garble question numbers like `t*326.` or `f 8322.`)
                if not q_in_answer:
                    q_in_answer = _PLEASED_TO_STATE_RE.search(raw_answer)
                if q_in_answer:
                    # Re-split: everything from question start onward is the question
                    # Walk back to the start of the line containing the match
                    q_line_start = raw_answer.rfind("\n", 0, q_in_answer.start())
                    q_line_start = q_line_start + 1 if q_line_start >= 0 else 0
                    answer_portion = raw_answer[:q_line_start]
                    question_portion = raw_answer[q_line_start:]
                    answer_text_rev = _clean_text(_strip_footer(answer_portion))
                    question_text_rev = _clean_text(_strip_footer(question_portion))
                    if answer_text_rev and question_text_rev:
                        return question_text_rev, answer_text_rev, strategy_name

    # Inline strategies — handled separately because we split at the
    # capture group (m.start(1)), not at m.start()
    for inline_name, inline_pattern in [
        ("inline_answer", _INLINE_ANSWER_RE),
        ("inline_minister", _INLINE_MINISTER_RE),
        ("inline_answer_bare", _INLINE_ANSWER_BARE_RE),
    ]:
        m = inline_pattern.search(text)
        if m:
            raw_question = text[: m.start(1)]
            raw_answer = text[m.start(1) :]

            question_text = _clean_text(_strip_footer(_strip_header(raw_question)))
            answer_text = _clean_text(_strip_footer(raw_answer))

            if question_text and answer_text:
                return question_text, answer_text, inline_name

    # No strategy matched — return unsplit
    cleaned = _clean_text(_strip_footer(_strip_header(text)))
    return cleaned, None, "unsplit"
