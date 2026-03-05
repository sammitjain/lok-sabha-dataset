"""Shared utilities for pipeline stages."""

from __future__ import annotations

from typing import List


def parse_sessions(sessions: str) -> List[int]:
    """Parse session ranges like '1-7' or '1,2,5-8' into a unique ordered list.

    Examples
    --------
    >>> parse_sessions('7')
    [7]
    >>> parse_sessions('1-3')
    [1, 2, 3]
    >>> parse_sessions('1,3,5-7')
    [1, 3, 5, 6, 7]
    """
    out: List[int] = []
    parts = [p.strip() for p in sessions.split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a.strip())
            end = int(b.strip())
            if end < start:
                start, end = end, start
            out.extend(range(start, end + 1))
        else:
            out.append(int(part))

    seen: set[int] = set()
    uniq: List[int] = []
    for x in out:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq
