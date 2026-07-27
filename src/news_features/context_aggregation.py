"""Phase 7 / Step 5 - context aggregation (pure logic; the runner
does the IO; NO LLM call anywhere).

Aggregation unit: election x geographic target x focal party x
time window x news scope. Two window modes coexist as ordinary key
values, never mixed in one row:

    window_type=individual  the six disjoint windows - articles
                            partition, so counts ADD across windows
    window_type=cumulative  the six nested windows - an article
                            contributes to every window it falls in,
                            so counts OVERLAP and must never be
                            summed across windows (documented in the
                            dictionary and error analysis)

Scope is a key (each aggregate row is purely local, purely
national, regional, mixed or uncertain), which keeps the spec's
separate local/national/regional/mixed aggregations separable by
construction - nothing is ever pooled across scopes.

Denominator discipline: every proportion has an explicit *_denom
column beside it. A proportion is None when its denominator is 0
(no eligible articles for that signal group - "no news observed"),
and a real 0.0 only when the denominator is positive and the signal
genuinely never fired ("news observed, signal absent"). Zeros are
therefore observations; Nones are absence of observation. No
missing-news indicators are created here (next step's job).

All statistics are descriptive counts, proportions, means and
medians of extracted signals - none of them is a prediction or a
causal estimate.
"""

from __future__ import annotations

import statistics

AGG_VERSION = "context-aggregation-v1.0-2026-07-27"

KEY_COLS = ["election_id", "geographic_target_id", "focal_party_id",
            "window_type", "window", "scope_classification"]

CUM_COLS = ["cum_previous_180_days", "cum_previous_90_days",
            "cum_previous_30_days", "cum_previous_14_days",
            "cum_previous_7_days", "cum_previous_72_hours"]

STANCE_BINS = ["positive_stance", "neutral_stance", "negative_stance",
               "mixed_stance"]

CONSQ_BINS = ["potential_benefit", "potential_damage",
              "mixed_or_unclear_impact", "growth_signal",
              "decline_signal", "credible_challenger_signal",
              "anti_incumbent_signal", "voter_switching_signal"]

REFORM_COUNT_BINS = [
    "reform_in_headline", "reform_candidate_mentioned",
    "reform_candidate_quoted", "reform_local_campaign_activity",
    "reform_credible_challenger", "reform_threat_to_conservative",
    "reform_threat_to_labour", "reform_threat_to_liberal_democrats",
    "reform_con_to_reform_switching", "reform_lab_to_reform_switching",
    "reform_ld_to_reform_switching", "reform_protest_anti_incumbent",
    "reform_national_momentum"]


def _prop(count: int, denom: int) -> float | None:
    """None when nothing was eligible (no observation), a real
    number - including 0.0 - only when the denominator is positive."""
    return round(count / denom, 4) if denom > 0 else None


def _sum(rows: list[dict], col: str) -> int:
    return int(sum(1 for r in rows if r.get(col) == 1))


def aggregate_group(rows: list[dict], issue_codes: list[str],
                    frame_cats: list[str]) -> dict:
    """Aggregate the article-level rows of ONE key group into one
    output row. ``rows`` all share the six key values; each row is
    one canonical article's focal-party record (article uniqueness
    within a group is guaranteed upstream and asserted by the
    runner)."""
    out: dict = {}

    # ---- 1. coverage and denominators -------------------------------
    out["cov_n_articles"] = len(rows)
    out["cov_n_publications"] = len({r["publication_id"]
                                     for r in rows})
    out["cov_n_source_arms"] = len({r["source_type"] for r in rows})
    out["cov_n_full_text"] = sum(1 for r in rows
                                 if r["full_text_availability"]
                                 == "valid_full_text")
    out["cov_n_review_flagged"] = sum(1 for r in rows
                                      if r["human_review_status"]
                                      == "flagged")
    def _num(v):
        """NaN-safe numeric read (NaN is truthy, so ``or 0`` fails)."""
        return v if isinstance(v, (int, float)) and v == v else 0

    out["cov_n_unresolved_alignment"] = sum(
        1 for r in rows if _num(r.get("unresolved_ward_mentions"))
        + _num(r.get("unresolved_party_mentions")) > 0)
    out["cov_total_party_mentions"] = _sum(rows, "party_mentioned")
    out["cov_total_candidate_mentions"] = int(sum(
        v for r in rows
        if isinstance((v := r.get("candidate_mention_count")),
                      (int, float)) and v == v))   # v==v filters NaN
    out["cov_n_result_flagged"] = _sum(rows,
                                       "election_result_indicator")

    # ---- 2+3. sentiment baseline == stance aggregation --------------
    # No independent sentiment layer exists in the frozen contract
    # and no documented label-to-number mapping was ever adopted, so
    # the sentiment baseline IS the stance distribution and the mean
    # numerical sentiment is honestly absent (None, not invented).
    st_rows = [r for r in rows
               if r.get("stance_status") in ("extracted",
                                             "confirmed_absent")]
    d = out["stance_denom"] = len(st_rows)
    for b in STANCE_BINS:
        n = _sum(st_rows, b)
        out[f"{b}_n"] = n
        out[f"{b}_prop"] = _prop(n, d)
    out["mean_sentiment_score"] = None
    out["mean_sentiment_score_status"] = "not_extracted"
    for b in ("praise_indicator", "criticism_indicator",
              "competence_positive", "competence_negative",
              "integrity_positive", "integrity_negative"):
        n = _sum(st_rows, b)
        out[f"{b}_n"] = n
        out[f"{b}_prop"] = _prop(n, d)

    # ---- 4. framing distribution ------------------------------------
    fr_rows = [r for r in rows
               if r.get("framing_status") == "extracted"]
    fd = out["framing_denom"] = len(fr_rows)
    for c in frame_cats:
        n = _sum(fr_rows, f"frame_{c}")
        out[f"frame_{c}_n"] = n
        out[f"frame_{c}_prop"] = _prop(n, fd)
    out["frame_multi_n"] = sum(
        1 for r in fr_rows
        if sum(1 for c in frame_cats
               if r.get(f"frame_{c}") == 1) >= 2)
    out["frame_unclear_or_missing_n"] = len(rows) - fd

    # ---- 5. blame / credit ------------------------------------------
    at_rows = [r for r in rows
               if r.get("attribution_status") == "extracted"]
    ad = out["attribution_denom"] = len(at_rows)
    for b in ("blame_received", "credit_received"):
        n = _sum(at_rows, b)
        out[f"{b}_n"] = n
        out[f"{b}_prop"] = _prop(n, ad)
    out["blame_assigned_n"] = _sum(at_rows, "blame_assigned")
    out["credit_assigned_n"] = _sum(at_rows, "credit_assigned")
    out["responsibility_unclear_n"] = _sum(at_rows,
                                           "responsibility_unclear")
    # descriptive only - the dictionary forbids causal reading
    out["net_credit_minus_blame_n"] = (out["credit_received_n"]
                                       - out["blame_received_n"])

    # ---- 6. issue distribution --------------------------------------
    is_rows = [r for r in rows
               if r.get("issues_status") == "extracted"]
    idn = out["issues_denom"] = len(is_rows)
    for c in issue_codes:
        prim = sum(1 for r in is_rows if r.get("primary_issue") == c)
        anyn = sum(1 for r in is_rows
                   if r.get("primary_issue") == c
                   or r.get(f"sec_issue_{c}") == 1)
        cont = sum(1 for r in is_rows
                   if (r.get("primary_issue") == c
                       or r.get(f"sec_issue_{c}") == 1)
                   and r.get("continuing_story") == "yes")
        out[f"issue_{c}_primary_n"] = prim
        out[f"issue_{c}_any_n"] = anyn
        out[f"issue_{c}_any_prop"] = _prop(anyn, idn)
        out[f"issue_{c}_continuing_n"] = cont

    # ---- 7. electoral-consequence signals ---------------------------
    cq_rows = [r for r in rows
               if r.get("consequence_status") in ("extracted",
                                                  "confirmed_absent")]
    cd = out["consequence_denom"] = len(cq_rows)
    for b in CONSQ_BINS:
        n = _sum(cq_rows, b)
        out[f"consq_{b}_n"] = n
        out[f"consq_{b}_prop"] = _prop(n, cd)
    # switching endpoints: counts per registry party id, serialised
    # as sorted "pid:count" pairs (sparse-safe for csv/parquet)
    for col, feat in (("switch_from_counts", "switch_from_party_id"),
                      ("switch_to_counts", "switch_to_party_id")):
        counts: dict[str, int] = {}
        for r in cq_rows:
            pid = r.get(feat)
            if isinstance(pid, str) and pid:   # NaN-safe
                counts[pid] = counts.get(pid, 0) + 1
        out[col] = ";".join(f"{k}:{v}" for k, v
                            in sorted(counts.items())) or None

    # ---- 8. Reform UK block -----------------------------------------
    rf_rows = [r for r in rows
               if r.get("reform_status") in ("extracted",
                                             "confirmed_absent")]
    if not rf_rows:      # non-Reform focal party: explicit N/A
        out["reform_agg_status"] = "not_applicable"
        for b in REFORM_COUNT_BINS:
            out[f"{b}_n"] = None
        out["reform_credible_challenger_prop"] = None
        out["reform_org_strength_reported_n"] = None
        out["reform_org_strength_strong_n"] = None
        for s in ("credibility", "momentum"):
            out[f"reform_{s}_mean"] = None
            out[f"reform_{s}_median"] = None
        out["reform_denom"] = 0
    else:
        rd = out["reform_denom"] = len(rf_rows)
        out["reform_agg_status"] = "aggregated"
        for b in REFORM_COUNT_BINS:
            out[f"{b}_n"] = _sum(rf_rows, b)
        out["reform_credible_challenger_prop"] = _prop(
            out["reform_credible_challenger_n"], rd)
        strengths = [r.get("reform_local_organisational_strength")
                     for r in rf_rows]
        out["reform_org_strength_reported_n"] = sum(
            1 for s in strengths if s)
        out["reform_org_strength_strong_n"] = sum(
            1 for s in strengths if s == "strong")
        for s in ("credibility", "momentum"):
            vals = [r.get(f"reform_{s}_score") for r in rf_rows
                    if r.get(f"reform_{s}_score") is not None]
            out[f"reform_{s}_mean"] = (round(statistics.mean(vals), 3)
                                       if vals else None)
            out[f"reform_{s}_median"] = (round(
                statistics.median(vals), 3) if vals else None)

    return out
