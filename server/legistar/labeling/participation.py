"""
Derive participation_window from Legistar action history.

This is computed deterministically from crawl data — not inferred by the LLM.
The schema note: "derivable from Legistar's action history ... arguably the
highest civic value in the whole schema and the cheapest to populate."
"""


_ENACTED_ACTIONS = frozenset({"signed", "enacted", "vetoed", "overridden"})
_FAILED_RESULTS = frozenset({"failed", "lost", "withdrawn", "tabled"})
_HEARING_KEYWORDS = ("public hearing", "public comment", "hearing scheduled")
_COMMITTEE_KEYWORDS = ("committee", "select committee", "land use", "public safety")


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def derive_participation_window(legislation) -> str:
    """
    Return the participation window for a piece of legislation.

    Priority order:
    1. already-enacted — bill signed, enacted, or vetoed
    2. closed — bill failed, withdrawn, or tabled at full council
    3. hearing-scheduled — a public hearing action appears in recent rows
    4. amendable — bill is active in committee
    5. comment-open — default for any active bill

    Returns one of the PARTICIPATION_WINDOWS values.
    """
    try:
        crawl_data = legislation.crawl_data
        rows = crawl_data.rows if crawl_data else []
    except Exception:
        return "comment-open"

    if not rows:
        return "comment-open"

    rows_data = [
        {
            "action": _normalize(getattr(r, "action", "") or ""),
            "result": _normalize(getattr(r, "result", "") or ""),
            "action_by": _normalize(getattr(r, "action_by", "") or ""),
        }
        for r in rows
    ]

    # Check most recent rows first (reversed) for final dispositions.
    for row in reversed(rows_data):
        action = row["action"]
        result = row["result"]

        if any(kw in action for kw in _ENACTED_ACTIONS):
            return "already-enacted"

        if result in _FAILED_RESULTS:
            return "closed"

        # "Passed" at full council = enacted (awaiting mayor signature)
        if "passed" in result and "council" in row["action_by"]:
            return "already-enacted"

    # Check for hearing scheduled
    for row in rows_data:
        if any(kw in row["action"] for kw in _HEARING_KEYWORDS):
            return "hearing-scheduled"

    # Check if active in committee
    for row in reversed(rows_data):
        if any(kw in row["action_by"] for kw in _COMMITTEE_KEYWORDS):
            return "amendable"

    return "comment-open"
