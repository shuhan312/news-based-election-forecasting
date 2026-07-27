"""Phase 7 / Step 2 - election time window assignment (pure logic;
the runner does the IO; NO LLM call anywhere).

Design position: the six pre-election windows and six cumulative
memberships were already computed deterministically in Phase 6
Step 9 by ``assign_windows()`` and frozen in
``temporal_windows_deterministic.json``. This step does NOT build a
second, parallel window calculator - two implementations of the
same arithmetic would eventually drift. Instead it:

* re-derives every assignment by calling THE SAME frozen function
  and asserts byte-equality with the stored deterministic layer
  (consistency check W2, run for all articles at build time);
* reshapes the result into the alignment-layer record format the
  feature stage will consume (joined to the Step 1 election links);
* applies the exclusion rule: articles published on or after
  polling day, or outside the 180-day collection window, or with an
  unresolvable date, are EXCLUDED from window assignment and listed
  separately - never silently dropped, never force-assigned.

The six result-flagged articles (contains_election_result) stay
assigned with their flag visible: decision D3 excludes them from
the MAIN analysis windows at the modelling stage via configuration,
with a with/without sensitivity pair - the assignment layer records
the flag and takes no side.

Window boundaries (days before polling day, inclusive):

    180_to_91_days   91-180      14_to_8_days    8-14
    90_to_31_days    31-90       7_to_4_days     4-7
    30_to_15_days    15-30       final_72_hours  1-3

Cumulative membership: previous_180/90/30/14/7 days + previous_72
hours, each true when days_before_polling <= N (nested by
construction: membership of a smaller window implies every larger
one - checked, not assumed).
"""

from __future__ import annotations

from datetime import date

from ..llm_extraction.temporal_horizon import (CUMULATIVE, WINDOWS,
                                               assign_windows)

TW_VERSION = "article-time-window-v1.0-2026-07-27"

# The six individual windows, smallest-first, as (name, lo, hi).
# Imported from the frozen Phase 6 module so this file cannot state
# different boundaries than the ones already frozen.
WINDOW_NAMES = [name for name, _, _ in WINDOWS]
CUMULATIVE_NAMES = [name for name, _ in CUMULATIVE]


def build_assignment(article_id: str, election_id: str,
                     stored: dict) -> tuple[dict | None, dict | None]:
    """One article -> (assignment record, exclusion record). Exactly
    one of the two is non-None.

    ``stored`` is the article's frozen deterministic-window entry.
    The same arithmetic is re-run through assign_windows() and must
    agree with the stored layer field-for-field (rule W2) - any
    mismatch means an input was tampered with and raises."""
    fresh = assign_windows(stored.get("publication_date") or "",
                           election_id,
                           "contains_election_result"
                           in stored.get("flags", []))
    for field in ("publication_date", "polling_date",
                  "days_before_polling", "election_window",
                  "cumulative_window_membership", "flags"):
        if fresh[field] != stored.get(field):
            raise ValueError(f"W2 drift on {article_id}.{field}: "
                             f"{fresh[field]!r} != {stored.get(field)!r}")

    base = {"article_id": article_id, "election_id": election_id,
            "polling_date": stored["polling_date"],
            "publication_date": stored["publication_date"]}

    window = stored["election_window"]
    if window not in WINDOW_NAMES:
        # post_voting / outside_collection_window / unassignable:
        # excluded from window assignment, listed with the reason
        return None, {**base,
                      "exclusion_reason": window,
                      "flags": stored["flags"]}

    return {**base,
            "days_before_polling": stored["days_before_polling"],
            "individual_time_window": window,
            "cumulative_windows": dict(
                stored["cumulative_window_membership"]),
            "flags": list(stored["flags"])}, None


def check_assignment(rec: dict) -> list[str]:
    """Deterministic validation of one assignment record (rules
    W1-W5). Returns sorted error strings; empty = valid."""
    errs = []
    try:                                                    # W1
        pub = date.fromisoformat(rec["publication_date"])
        poll = date.fromisoformat(rec["polling_date"])
    except (TypeError, ValueError):
        return [f"W1 invalid date on {rec['article_id']}"]
    d = rec["days_before_polling"]
    if (poll - pub).days != d:                              # W2
        errs.append("W2 days_before_polling arithmetic wrong")
    if d <= 0:                                              # W5
        errs.append("W5 post-polling article not excluded")
    hits = [n for n, lo, hi in WINDOWS if lo <= d <= hi]
    if [rec["individual_time_window"]] != hits:             # W3
        errs.append("W3 not exactly one matching individual window")
    cum = rec["cumulative_windows"]
    if set(cum) != set(CUMULATIVE_NAMES):
        errs.append("W4 cumulative window set incomplete")
    else:
        for name, n in CUMULATIVE:
            if cum[name] != (d <= n):                       # W4
                errs.append(f"W4 {name} inconsistent with day count")
        # nesting: smaller-window membership implies every larger one
        ordered = sorted(CUMULATIVE, key=lambda x: x[1])
        for (small, _), (big, _) in zip(ordered, ordered[1:]):
            if cum[small] and not cum[big]:
                errs.append("W4 cumulative nesting violated")
    return sorted(errs)
