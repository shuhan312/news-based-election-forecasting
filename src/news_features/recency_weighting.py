"""Phase 7 / Step 6 - recency weighting (pure logic; the runner does
the IO; NO LLM call anywhere).

What this layer is: a SECOND, parallel version of the Step 5
aggregates in which each contributing article is weighted by how
close to polling day it was published. The Step 5 unweighted layer
is never touched - the two exist side by side precisely so a later
model can test whether recency adds predictive value.

Weight function (the specification's default, adopted unchanged):

    weight = exp(-lambda * days_before_polling)

with lambda expressed through an interpretable HALF-LIFE:

    lambda = ln(2) / half_life_days

so an article published `half_life_days` before polling counts half
as much as one published on the eve of the poll. Reporting the
half-life rather than the bare lambda is the whole point: 0.0231 is
unreadable, "30-day half-life" is a statement a supervisor or
examiner can agree or disagree with.

Lambda is NEVER tuned against election outcomes (an explicit
boundary of this step, and the reason the layer is built before any
model exists). Instead the layer emits a fixed, pre-registered GRID
of half-lives computed blind:

    7, 14, 30 (primary), 60, 90 days

The primary value is 30 days: UK local-election campaigning
concentrates in the final month (candidate nomination closes ~19
working days before the poll and the "short campaign" is the
conventional reference period), so a 30-day half-life keeps the
final month dominant while leaving articles from the 91-180 day
window a small but non-zero voice (weight ~0.016 at 180 days).
Shorter half-lives (7, 14) test a sharper campaign-only reading;
longer ones (60, 90) test a slow-burn reading. If a later modelling
stage selects among them, the selection must happen inside training
folds only - never against held-out outcomes.

Weights are strictly in (0, 1]: an article published on polling eve
(days_before_polling = 1) scores exp(-lambda) just under 1, and
weight decreases monotonically with age (asserted by the tests).
Post-polling articles cannot appear: Step 2 excludes them, and
days_before_polling > 0 is re-checked here.

Missing dates: an article without a reliable publication date gets
NO weight (None) and is EXCLUDED from the weighted aggregates with
its reason recorded - the specification forbids artificial weights,
and inventing one would silently promote an undated article to
"published today". The pilot corpus has zero such articles; the
path is implemented and tested on synthetic cases because the full
corpus will contain them.
"""

from __future__ import annotations

import math

WEIGHTING_VERSION = "recency-weighting-v1.0-2026-07-27"

# pre-registered half-life grid (days); primary first in the docs,
# ascending here for deterministic output ordering
HALF_LIVES = (7, 14, 30, 60, 90)
PRIMARY_HALF_LIFE = 30


def lambda_for(half_life_days: float) -> float:
    """Decay constant from an interpretable half-life."""
    if half_life_days <= 0:
        raise ValueError("half-life must be positive")
    return math.log(2) / half_life_days


def recency_weight(days_before_polling, half_life_days: float):
    """exp(-lambda * days). Returns (weight, exclusion_reason).

    A missing, non-numeric or non-positive day count yields
    (None, reason) - never a fabricated weight."""
    d = days_before_polling
    if d is None or not isinstance(d, (int, float)) or d != d:
        return None, "incomplete_publication_date"
    if d <= 0:
        return None, "post_or_on_polling_day"
    return math.exp(-lambda_for(half_life_days) * d), None


# ---- weighted aggregation helpers ----------------------------------

def _wsum(rows, weights, col) -> float:
    """Weighted count: sum of weights of rows whose flag is 1."""
    return sum(w for r, w in zip(rows, weights) if r.get(col) == 1)


def _wprop(num: float, denom: float):
    """Weighted proportion. None when the weighted denominator is 0
    (no eligible weighted articles observed); a real 0.0 only when
    articles were observed and the signal never fired - the same
    zero-versus-absent discipline as the unweighted layer."""
    return round(num / denom, 6) if denom > 0 else None


def weighted_group(rows: list[dict], weights: list[float],
                   issue_codes, frame_cats, stance_bins,
                   consq_bins, reform_bins) -> dict:
    """Weighted mirror of Step 5's aggregate_group.

    Group-eligibility rules are IMPORTED from the unweighted layer's
    conventions (same status filters), so the weighted and
    unweighted rows always describe the same underlying article set
    - they differ only in how each article is counted."""
    out: dict = {}
    W = sum(weights)

    def sub(pred):
        """Rows+weights of a group's eligible subset."""
        pairs = [(r, w) for r, w in zip(rows, weights) if pred(r)]
        return ([p[0] for p in pairs], [p[1] for p in pairs],
                sum(p[1] for p in pairs))

    # ---- coverage ---------------------------------------------------
    out["weighted_article_count"] = round(W, 6)
    out["unweighted_article_count"] = len(rows)   # comparison anchor
    # a publication's contribution decays with its MOST RECENT
    # article: max weight per distinct publication, then summed
    pub_max: dict[str, float] = {}
    arm_max: dict[str, float] = {}
    for r, w in zip(rows, weights):
        p, a = r.get("publication_id"), r.get("source_type")
        pub_max[p] = max(pub_max.get(p, 0.0), w)
        arm_max[a] = max(arm_max.get(a, 0.0), w)
    out["weighted_publication_count"] = round(sum(pub_max.values()), 6)
    out["weighted_source_arm_count"] = round(sum(arm_max.values()), 6)
    out["weighted_party_mentions"] = round(
        _wsum(rows, weights, "party_mentioned"), 6)
    out["weighted_candidate_mentions"] = round(sum(
        w * v for r, w in zip(rows, weights)
        if isinstance((v := r.get("candidate_mention_count")),
                      (int, float)) and v == v), 6)

    # ---- stance / sentiment baseline --------------------------------
    st_rows, st_w, st_d = sub(
        lambda r: r.get("stance_status") in ("extracted",
                                             "confirmed_absent"))
    out["w_stance_denom"] = round(st_d, 6)
    for b in stance_bins + ["praise_indicator", "criticism_indicator",
                            "competence_positive",
                            "competence_negative",
                            "integrity_positive",
                            "integrity_negative"]:
        n = _wsum(st_rows, st_w, b)
        out[f"w_{b}_n"] = round(n, 6)
        out[f"w_{b}_prop"] = _wprop(n, st_d)

    # ---- framing ----------------------------------------------------
    fr_rows, fr_w, fr_d = sub(
        lambda r: r.get("framing_status") == "extracted")
    out["w_framing_denom"] = round(fr_d, 6)
    for c in frame_cats:
        n = _wsum(fr_rows, fr_w, f"frame_{c}")
        out[f"w_frame_{c}_n"] = round(n, 6)
        out[f"w_frame_{c}_prop"] = _wprop(n, fr_d)
    out["w_frame_multi_n"] = round(sum(
        w for r, w in zip(fr_rows, fr_w)
        if sum(1 for c in frame_cats if r.get(f"frame_{c}") == 1)
        >= 2), 6)
    out["w_frame_unclear_or_missing_n"] = round(W - fr_d, 6)

    # ---- blame / credit ---------------------------------------------
    at_rows, at_w, at_d = sub(
        lambda r: r.get("attribution_status") == "extracted")
    out["w_attribution_denom"] = round(at_d, 6)
    for b in ("blame_received", "credit_received"):
        n = _wsum(at_rows, at_w, b)
        out[f"w_{b}_n"] = round(n, 6)
        out[f"w_{b}_prop"] = _wprop(n, at_d)
    for b in ("blame_assigned", "credit_assigned",
              "responsibility_unclear"):
        out[f"w_{b}_n"] = round(_wsum(at_rows, at_w, b), 6)
    out["w_net_credit_minus_blame_n"] = round(
        out["w_credit_received_n"] - out["w_blame_received_n"], 6)

    # ---- issues ------------------------------------------------------
    is_rows, is_w, is_d = sub(
        lambda r: r.get("issues_status") == "extracted")
    out["w_issues_denom"] = round(is_d, 6)
    for c in issue_codes:
        prim = sum(w for r, w in zip(is_rows, is_w)
                   if r.get("primary_issue") == c)
        anyn = sum(w for r, w in zip(is_rows, is_w)
                   if r.get("primary_issue") == c
                   or r.get(f"sec_issue_{c}") == 1)
        cont = sum(w for r, w in zip(is_rows, is_w)
                   if (r.get("primary_issue") == c
                       or r.get(f"sec_issue_{c}") == 1)
                   and r.get("continuing_story") == "yes")
        out[f"w_issue_{c}_primary_n"] = round(prim, 6)
        out[f"w_issue_{c}_any_n"] = round(anyn, 6)
        out[f"w_issue_{c}_any_prop"] = _wprop(anyn, is_d)
        out[f"w_issue_{c}_continuing_n"] = round(cont, 6)

    # ---- electoral consequence ---------------------------------------
    cq_rows, cq_w, cq_d = sub(
        lambda r: r.get("consequence_status") in ("extracted",
                                                  "confirmed_absent"))
    out["w_consequence_denom"] = round(cq_d, 6)
    for b in consq_bins:
        n = _wsum(cq_rows, cq_w, b)
        out[f"w_consq_{b}_n"] = round(n, 6)
        out[f"w_consq_{b}_prop"] = _wprop(n, cq_d)

    # ---- Reform UK ---------------------------------------------------
    rf_rows, rf_w, rf_d = sub(
        lambda r: r.get("reform_status") in ("extracted",
                                             "confirmed_absent"))
    if not rf_rows:          # non-Reform focal party
        out["w_reform_agg_status"] = "not_applicable"
        for b in reform_bins:
            out[f"w_{b}_n"] = None
        out["w_reform_credible_challenger_prop"] = None
        out["w_reform_org_strength_strong_n"] = None
        out["w_reform_credibility_weighted_mean"] = None
        out["w_reform_momentum_weighted_mean"] = None
        out["w_reform_denom"] = 0.0
    else:
        out["w_reform_agg_status"] = "aggregated"
        out["w_reform_denom"] = round(rf_d, 6)
        for b in reform_bins:
            out[f"w_{b}_n"] = round(_wsum(rf_rows, rf_w, b), 6)
        out["w_reform_credible_challenger_prop"] = _wprop(
            out["w_reform_credible_challenger_n"], rf_d)
        out["w_reform_org_strength_strong_n"] = round(sum(
            w for r, w in zip(rf_rows, rf_w)
            if r.get("reform_local_organisational_strength")
            == "strong"), 6)
        # weighted means: sum(w*score)/sum(w) over rows with a score
        for s in ("credibility", "momentum"):
            pairs = [(v, w) for r, w in zip(rf_rows, rf_w)
                     if isinstance((v := r.get(f"reform_{s}_score")),
                                   (int, float)) and v == v]
            wsum = sum(w for _, w in pairs)
            out[f"w_reform_{s}_weighted_mean"] = (
                round(sum(v * w for v, w in pairs) / wsum, 6)
                if wsum > 0 else None)
    return out
