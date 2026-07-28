"""Phase 7 / Step 7 - missing-news representation (pure logic; the
runner does the IO; NO LLM call anywhere).

The problem this layer exists to prevent: an empty cell in the
aggregated feature table looks exactly like "no news was published
about this party in this ward in this window". Usually it is not.
It is far more often "we never searched that ward", "the archive
refused the request", "those articles are collected but not yet
extracted", or "Stage M will add articles here later". Feeding all
of those to a model as zero teaches the model that silence means
absence of coverage, when it often means absence of *searching*.

So this layer builds the COMPLETE expected observation grid and
assigns every cell exactly one primary coverage state, backed by
documented evidence rather than by the emptiness of the feature
table:

    observed_news              >=1 eligible canonical article
                               contributes
    confirmed_zero_news        nothing contributes AND every
                               required coverage check passes
    insufficient_search_coverage
                               the search plan never covered this
                               cell (e.g. ward never searched at
                               ward tier)
    source_unavailable         searches ran but the source refused
                               (HTTP 4xx/429) or the archive was
                               inaccessible
    unresolved_processing      articles are collected but their
                               eligibility, extraction, date,
                               duplicate or alignment resolution is
                               incomplete
    pending_external_stage     Stage M (or another recorded
                               external stage) may still add
                               articles here
    not_applicable             the combination is politically or
                               structurally invalid

Precedence (documented, deterministic, applied top-down):

    1 not_applicable      - an invalid cell is never assessed
    2 observed_news       - observation is a fact and outranks any
                            pending state; the pending flag still
                            rides along as a separate indicator so
                            "this value may grow" is not lost
    3 insufficient_search_coverage
                          - the most fundamental gap: no amount of
                            later processing can create articles
                            from a search that never ran
    4 source_unavailable  - searching was attempted and refused
    5 pending_external_stage
                          - searched fine, but an external stage
                            still owes articles
    6 unresolved_processing
                          - collected, but not yet processed
    7 confirmed_zero_news - everything complete and still nothing

Only state 7 sets `zero_news_indicator = 1`. States 3-6 are
explicitly NOT zero, which is the entire point of the layer.

Validity rules for the expected grid (the "politically valid
combinations" requirement):

* ward targets carry only parties that actually contested that
  ward in that election (from the official results tables);
* ward targets are valid for local-bearing scopes only
  (ward_specific_local, surrey_wide_local, mixed_local_national).
  A purely national or regional article is never attributed to a
  single ward - the same rule the Step 4/5 layers enforce - so
  ward x national_political and ward x regional are materialised
  as not_applicable rather than silently dropped;
* election-wide targets carry every party that contested the
  election, plus Reform UK as an explicitly tracked emerging-party
  comparison even where it did not stand; Reform UK rows for
  elections predating the party are not_applicable.
"""

from __future__ import annotations

MISSING_NEWS_VERSION = "missing-news-v1.0-2026-07-27"

# scopes a ward-level target can legitimately receive
WARD_VALID_SCOPES = ("ward_specific_local", "surrey_wide_local",
                     "mixed_local_national")
ALL_SCOPES = ("ward_specific_local", "surrey_wide_local", "regional",
              "national_political", "mixed_local_national")

INDIVIDUAL_WINDOWS = ("180_to_91_days", "90_to_31_days",
                      "30_to_15_days", "14_to_8_days",
                      "7_to_4_days", "final_72_hours")
CUMULATIVE_WINDOWS = ("previous_180_days", "previous_90_days",
                      "previous_30_days", "previous_14_days",
                      "previous_7_days", "previous_72_hours")

# elections predating Reform UK's existence (the party was founded
# as the Brexit Party in 2018 and renamed in January 2021), tracked
# for comparison but structurally unobservable before then
REFORM_ABSENT_ELECTIONS = ("SCC-2013-05", "SCC-2017-05")

# the evidence checklist behind a confirmed zero; every item must
# hold, and the satisfied fraction becomes coverage_confidence
EVIDENCE_ITEMS = (
    "search_queries_executed",        # the cell's queries all ran
    "ward_tier_search_executed",      # ward cells were searched at
                                      # ward tier (True for
                                      # election-wide cells)
    "date_range_covered",             # queries span the 180-day
                                      # pre-election window
    "required_sources_checked",       # the arm's source set ran
    "no_search_failures",             # no 4xx/429 in this cell
    "external_stage_complete",        # Stage M ingested
    "eligibility_resolution_complete",
    "duplicate_resolution_complete",
    "extraction_complete",
)

STATES = ("observed_news", "confirmed_zero_news",
          "insufficient_search_coverage", "source_unavailable",
          "unresolved_processing", "pending_external_stage",
          "not_applicable")


def is_valid_combination(target_level: str, scope: str,
                         election_id: str,
                         party_name: str | None,
                         in_division_sample: bool = True
                         ) -> tuple[bool, str]:
    """Politically/structurally valid? Returns (valid, reason).

    ``in_division_sample`` implements the protocol's own scope: the
    supervisor's brief (to-do 7) asks for ward-tier collection on a
    pre-registered sample of 15-25 divisions, and the project
    committed 17 in news_protocol/division_sample.md. Divisions
    outside that sample were never in scope for ward-tier search, so
    an empty cell there is NOT "insufficient search coverage" - it is
    simply outside the sampling frame, and must stay outside ordinary
    modelling denominators.
    """
    if target_level == "ward" and scope not in WARD_VALID_SCOPES:
        return False, (f"{scope} articles are never attributed to a "
                       "single ward (pipeline rule: national and "
                       "regional coverage stays election-wide)")
    if party_name == "Reform UK" \
            and election_id in REFORM_ABSENT_ELECTIONS:
        return False, ("Reform UK did not exist at this election; "
                       "tracked as emerging-party comparison only")
    if target_level == "ward" and not in_division_sample:
        return False, ("outside the pre-registered 17-division "
                       "sample (protocol division_sample.md, "
                       "supervisor to-do 7) - never in scope for "
                       "ward-tier collection")
    return True, ""


def assess_cell(*, valid: bool, invalid_reason: str,
                n_articles: int, evidence: dict) -> dict:
    """Assign the primary state and all indicators for one cell.

    ``evidence`` maps every EVIDENCE_ITEMS key to a bool. The
    function never inspects the feature table's emptiness alone -
    an empty cell only becomes confirmed_zero when every evidence
    item is True."""
    ind = {k: 0 for k in ("news_observed_indicator",
                          "zero_news_indicator",
                          "insufficient_coverage_indicator",
                          "source_unavailable_indicator",
                          "unresolved_processing_indicator",
                          "pending_stage_indicator",
                          "not_applicable_indicator")}

    # secondary flags are set regardless of which state wins, so no
    # information is collapsed away by the precedence order
    if not evidence.get("external_stage_complete", False):
        ind["pending_stage_indicator"] = 1
    if not evidence.get("ward_tier_search_executed", True) \
            or not evidence.get("search_queries_executed", True) \
            or not evidence.get("date_range_covered", True) \
            or not evidence.get("required_sources_checked", True):
        ind["insufficient_coverage_indicator"] = 1
    if not evidence.get("no_search_failures", True):
        ind["source_unavailable_indicator"] = 1
    if not (evidence.get("eligibility_resolution_complete", False)
            and evidence.get("duplicate_resolution_complete", False)
            and evidence.get("extraction_complete", False)):
        ind["unresolved_processing_indicator"] = 1

    satisfied = sum(1 for k in EVIDENCE_ITEMS if evidence.get(k))
    confidence = round(satisfied / len(EVIDENCE_ITEMS), 4)

    # ---- precedence ------------------------------------------------
    if not valid:
        state, reason = "not_applicable", invalid_reason
        ind = {k: 0 for k in ind}          # invalid cells assert
        ind["not_applicable_indicator"] = 1  # nothing else
        confidence = None
    elif n_articles > 0:
        state = "observed_news"
        reason = f"{n_articles} eligible canonical article(s) contribute"
        ind["news_observed_indicator"] = 1
    elif ind["insufficient_coverage_indicator"]:
        state = "insufficient_search_coverage"
        missing = [k for k in ("ward_tier_search_executed",
                               "search_queries_executed",
                               "date_range_covered",
                               "required_sources_checked")
                   if not evidence.get(k, True)]
        reason = "search plan incomplete: " + ", ".join(missing)
    elif ind["source_unavailable_indicator"]:
        state = "source_unavailable"
        reason = "one or more searches failed at the source"
    elif ind["pending_stage_indicator"]:
        state = "pending_external_stage"
        reason = ("Stage M results are collected but not yet "
                  "ingested; this cell may still receive articles")
    elif ind["unresolved_processing_indicator"]:
        state = "unresolved_processing"
        missing = [k for k in ("eligibility_resolution_complete",
                               "duplicate_resolution_complete",
                               "extraction_complete")
                   if not evidence.get(k, False)]
        reason = "processing incomplete: " + ", ".join(missing)
    else:
        state = "confirmed_zero_news"
        reason = ("no eligible article after complete search, "
                  "ingestion, eligibility, duplicate and extraction "
                  "coverage")
        ind["zero_news_indicator"] = 1

    return {**ind, "coverage_status": state,
            "coverage_confidence": confidence,
            "coverage_reason": reason,
            "evidence_items_satisfied": satisfied,
            "evidence_items_total": len(EVIDENCE_ITEMS)}
