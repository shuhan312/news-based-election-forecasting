"""Phase 6 / Step 9 - temporal horizon (pure logic; the runner does
the IO).

TWO HALVES, STRICTLY SEPARATED - the specification's core demand:

1.  DETERMINISTIC election timing (this module, plain Python, no
    LLM): days_before_polling from the validated effective date and
    the protocol's polling day, the six non-overlapping election
    windows, the six cumulative memberships, and the leakage flags
    (post-voting publication, result-reporting content, unresolved
    dates). Identical inputs give identical outputs forever.
2.  LLM-derived expected impact horizon (prompt below): how long the
    CONTENT's political relevance persists. The separation is
    structural: the extractor is NEVER SHOWN the publication date,
    so publication distance cannot leak into the horizon judgement -
    the boundary the specification draws ("must reflect the article
    content, not merely its publication date") is enforced by
    construction, not by instruction alone.

Deterministic windows (day_index = polling_day - effective_date):

    91  <= d <= 180   -> 180_to_91_days
    31  <= d <= 90    -> 90_to_31_days
    15  <= d <= 30    -> 30_to_15_days
    8   <= d <= 14    -> 14_to_8_days
    4   <= d <= 7     -> 7_to_4_days
    1   <= d <= 3     -> final_72_hours
    d   <= 0          -> post_voting (leakage flag, never windowed)
    d   >  180        -> outside_collection_window (flag)
    no usable date    -> unassignable (flag)

Cumulative membership previous_N_days = 1 <= d <= N.

LLM validation rules (H-series; deterministic, sorted output):

    H1  every evidence span must appear VERBATIM in the article body
        (or title when from_title);
    H2  any confidence < 0.5 forces review_status = flagged;
    H3  a non-uncertain impact_horizon REQUIRES an evidence span; an
        uncertain horizon may leave it null - uncertainty is the
        honest default, never a shortcut around evidence;
    H4  Reform consistency: applicable=false forbids temporal
        characters; any character requires an evidence span;
    H5  not_attempted records carry no content;
    H6  story_type none_political requires impact_horizon uncertain
        or an ambiguity note - a non-political story has no
        political persistence to classify.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from ..news_collection.resolve_publication_dates import ELECTIONS

SCHEMA_PATH = Path("llm_context/temporal_horizon_schema_v1.json")

TH_SCHEMA_VERSION = "temporal-v1.0-2026-07-27"
TH_PROMPT_VERSION = "temporal-prompt-v1.0-2026-07-27"
TH_RULES_VERSION = "temporal-rules-v1.0-2026-07-27"
DETERMINISTIC_VERSION = "temporal-windows-v1.0-2026-07-27"
LOW_CONFIDENCE = 0.5

# (window_name, min_day, max_day) - non-overlapping, exhaustive over
# the collection's 1..180 day range
WINDOWS = (("final_72_hours", 1, 3), ("7_to_4_days", 4, 7),
           ("14_to_8_days", 8, 14), ("30_to_15_days", 15, 30),
           ("90_to_31_days", 31, 90), ("180_to_91_days", 91, 180))
CUMULATIVE = (("previous_72_hours", 3), ("previous_7_days", 7),
              ("previous_14_days", 14), ("previous_30_days", 30),
              ("previous_90_days", 90), ("previous_180_days", 180))


def assign_windows(pub_date: str, election_id: str,
                   contains_result: bool = False) -> dict:
    """The deterministic half. ``pub_date`` is the validated
    effective date (ISO, possibly empty); ``contains_result`` comes
    from the pilot leakage layer (provenance recorded by the
    runner). Pure date arithmetic - the LLM never touches this."""
    polling = ELECTIONS.get(election_id, (None, None))[1]
    out = {"deterministic_version": DETERMINISTIC_VERSION,
           "publication_date": pub_date or None,
           "polling_date": polling.isoformat() if polling else None,
           "days_before_polling": None,
           "hours_before_polling": None,
           "election_window": "unassignable",
           "cumulative_window_membership": {n: False
                                            for n, _ in CUMULATIVE},
           "flags": []}
    if contains_result:
        out["flags"].append("contains_election_result")
    if not pub_date or polling is None:
        out["flags"].append("unresolved_publication_date"
                            if not pub_date else "unknown_election")
        return out
    d = (polling - date.fromisoformat(pub_date)).days
    out["days_before_polling"] = d
    # date-only precision: hours are derivable only as a whole-day
    # bound; recorded as d*24 with the precision stated, never faked
    out["hours_before_polling"] = d * 24
    out["hours_precision"] = "date_only_lower_bound"
    if d <= 0:
        out["election_window"] = "post_voting"
        out["flags"].append("published_after_voting_began")
        return out
    if d > 180:
        out["election_window"] = "outside_collection_window"
        out["flags"].append("outside_180_day_window")
        return out
    for name, lo, hi in WINDOWS:
        if lo <= d <= hi:
            out["election_window"] = name
            break
    for name, n in CUMULATIVE:
        out["cumulative_window_membership"][name] = d <= n
    return out


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_structure(record: dict) -> list[str]:
    validator = Draft202012Validator(load_schema())
    return sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: "
                  f"{e.message}" for e in validator.iter_errors(record))


def validate_rules(record: dict, body: str, title: str = "") -> list[str]:
    errors: list[str] = []
    spans = [("impact_horizon", record.get("evidence_span"),
              record.get("confidence"))]
    reform = record.get("reform_uk") or {}
    if reform.get("evidence_span"):
        spans.append(("reform_uk", reform["evidence_span"],
                      reform.get("confidence")))
    for name, span, conf in spans:
        if isinstance(span, dict):
            haystack = title if span.get("from_title") else body
            text = span.get("text", "")
            if text and text not in haystack:
                errors.append(f"H1 {name}: evidence span not found "
                              f"verbatim: {text[:60]!r}")
        if isinstance(conf, (int, float)) and conf < LOW_CONFIDENCE \
                and record.get("review_status") != "flagged":
            errors.append(f"H2 {name}: confidence {conf} below "
                          f"{LOW_CONFIDENCE} but record not flagged")

    # ---- H3: a definite horizon needs evidence ----------------------
    if record.get("impact_horizon") != "uncertain" \
            and not record.get("evidence_span"):
        errors.append(f"H3: impact_horizon "
                      f"{record.get('impact_horizon')!r} without an "
                      "evidence span")

    # ---- H4: Reform consistency -------------------------------------
    chars = reform.get("temporal_character") or []
    if not reform.get("applicable") and chars:
        errors.append(f"H4 reform_uk: applicable is false but "
                      f"temporal_character set: {sorted(chars)}")
    if reform.get("applicable") and chars \
            and not reform.get("evidence_span"):
        errors.append("H4 reform_uk: temporal characters require an "
                      "evidence span")

    # ---- H5 / H6 ----------------------------------------------------
    if record.get("extraction_status") == "not_attempted" \
            and (record.get("evidence_span") or chars):
        errors.append("H5: not_attempted record carries content")
    if record.get("story_type") == "none_political" \
            and record.get("impact_horizon") != "uncertain" \
            and not record.get("ambiguity_notes"):
        errors.append("H6: none_political story with a definite "
                      "horizon and no explanatory note")
    return sorted(errors)


def validate_th_record(record: dict, body: str,
                       title: str = "") -> list[str]:
    errors = validate_structure(record)
    if errors:
        return errors
    return validate_rules(record, body, title)


def build_th_prompt() -> str:
    """Focused system prompt. Byte-stable. Deliberately tells the
    model it will NOT see the publication date - the horizon must
    come from content."""
    schema = SCHEMA_PATH.read_text().strip()
    return f"""You are a temporal-horizon extraction system for an academic study of \
pre-election news coverage in Surrey, England. For each article, produce ONE \
JSON object conforming exactly to the JSON Schema below: how long the \
article's POLITICAL relevance is expected to persist, judged from the \
CONTENT. Prompt version: {TH_PROMPT_VERSION}.

You are deliberately NOT given the publication date: the expected impact \
horizon must come from what the article describes, never from when it was \
published. Election-window arithmetic is computed elsewhere by code.

Operational definitions:
- immediate: relevance measured in days (a moment that passes);
- short_term: weeks (a story with a tail);
- medium_term: months (spans a campaign season);
- long_term: beyond the electoral cycle - structural conditions;
- mixed: clearly distinct components at different horizons;
- uncertain: the article does not support a reliable judgement.

Hard rules:
1. EVIDENCE OR UNCERTAIN. A definite horizon requires evidence_span.text \
copied CHARACTER-FOR-CHARACTER from the article body (or title, with \
from_title true) - NEVER shorten with "..." or any ellipsis, NEVER splice, \
NEVER reconstruct; choose a shorter contiguous span instead. If the article \
does not support a temporal judgement, say "uncertain" - uncertainty is the \
honest default, and only uncertain horizons may omit the evidence span.
2. MECHANISM, NOT VIBES. Fill impact_start, persistence, \
continuing_story, expected_decay and a grounded rationale; classify the \
story type (sudden shock / developing controversy / recurring service \
problem / sustained national trend / long-running issue / election-day \
administrative event).
3. LINKAGE ONLY WITH SUPPORT. Name affected actors, voter groups and the \
issue code only when the article supports them; say whether the consequence \
signal reads temporary or cumulative; set national_precedes_local true ONLY \
when the article itself suggests national momentum may precede local \
conversion.
4. REFORM UK. When applicable, choose among the four temporal characters \
(short-lived publicity / continuing national momentum / sustained local \
campaign development / long-term challenger emergence) with evidence. \
Coverage is never assumed to produce votes.
5. CONFIDENCE IS HONEST. Confidence in [0,1]; if any is below 0.5, set \
review_status to "flagged".
6. Output ONLY the JSON object - no markdown fences, no commentary.

The JSON Schema (contract {TH_SCHEMA_VERSION}):

{schema}"""
