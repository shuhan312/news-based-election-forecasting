"""Phase 6 / Step 10 - confidence + evidence audit layer (pure
logic; the runner does the IO; NO LLM call anywhere - this layer
consolidates what the previous layers already carry).

Design position: evidence spans and confidence scores were made
mandatory in Step 1 and enforced by every layer's validator, so
Step 10 does not create evidence - it FLATTENS every stored claim
from the seven extraction layers into one uniform audit table
(article_id, extraction_field, extracted_value, evidence_span,
confidence_score, uncertainty_flag, review_required), re-verifies
every span against the article text one final time, derives
uncertainty representations, and aggregates per-article and
corpus-level summaries. The layer answers: "why did the system make
this judgement, and how confident should we be?"

Confidence bands (per the specification - evidence quality, never
outcome probability):

    high    0.80-1.00  clear explicit evidence
    medium  0.50-0.79  reasonable interpretation, incomplete evidence
    low     0.00-0.49  requires inference / weak evidence

Consistency checks per claim:

    unsupported            a definite value with no evidence span
    evidence_not_verbatim  span fails the final string-match
    weak_evidence_high_confidence
                           confidence >= 0.80 on an uncertain/mixed
                           value or with no span - uncertainty must
                           not be forced into high confidence
    (missing evidence is recorded explicitly, never dropped)

Uncertainty representation per claim: uncertainty_flag +
uncertainty_reason + human_review_required. Article-level reasons
include the specification's two canonical cases: a national issue
without explicit local electoral linkage, and national Reform
momentum without local conversion evidence.

Provenance note (decision D1): the issue authority is the Step 3
focused layer; the pilot full-schema record contributes entities,
party/candidate/Reform context, event, geographic and leakage
claims but NOT its issues section.
"""

from __future__ import annotations

UNCERTAIN_VALUES = {"uncertain", "unclear", "mixed", "not_addressed",
                    "not_indicated", "none"}


def band(confidence: float | None) -> str:
    if not isinstance(confidence, (int, float)):
        return "missing"
    if confidence >= 0.80:
        return "high"
    if confidence >= 0.50:
        return "medium"
    return "low"


def _claim(field: str, value, span, conf, layer: str) -> dict:
    return {"extraction_field": field, "extracted_value": value,
            "evidence_span": span, "confidence_score": conf,
            "layer": layer}


def flatten_record(layer: str, record: dict) -> list[dict]:
    """Turn one layer's record into uniform claims. Row-level spans
    are shared by the row's judgement fields - the span supports the
    whole row, and each judgement is individually auditable."""
    claims: list[dict] = []

    def row_claims(prefix, row, fields, span_key="evidence_span"):
        span, conf = row.get(span_key), row.get("confidence")
        for f in fields:
            if f in row:
                claims.append(_claim(f"{prefix}.{f}", row[f], span,
                                     conf, layer))

    if layer == "pilot_full_schema":
        ev = record.get("event_context") or {}
        if ev:
            row_claims("event_context", ev,
                       ["event_type", "continuing_story"])
        for e in record.get("entities") or []:
            claims.append(_claim(f"entities[{e['name']}].entity_type",
                                 e["entity_type"], e.get("evidence_span"),
                                 e.get("confidence"), layer))
        for p in record.get("party_context") or []:
            row_claims(f"party_context[{p['party']}]", p,
                       ["overall_context", "stance", "blame", "credit",
                        "competence", "integrity", "support_trajectory",
                        "challenger_credibility",
                        "voter_switching_discussed"])
        for c in record.get("candidate_context") or []:
            row_claims(f"candidate_context[{c['name']}]", c,
                       ["stance", "blame", "credit", "credibility",
                        "momentum", "directly_quoted",
                        "protest_candidate"])
        ru = record.get("reform_uk") or {}
        if ru.get("reform_uk_present"):
            row_claims("reform_uk", ru,
                       ["gaining_support", "credible_challenger",
                        "local_campaign_activity", "national_momentum",
                        "switching_con_to_reform",
                        "switching_lab_to_reform",
                        "switching_ld_to_reform"])
        geo = record.get("geographic") or {}
        if geo:
            row_claims("geographic", geo, ["level"])
        lk = record.get("leakage") or {}
        if lk:
            row_claims("leakage", lk, ["leakage_risk"])
    elif layer == "issues":
        iss = record.get("issues") or {}
        p = iss.get("primary_issue")
        if p:
            claims.append(_claim("issues.primary_issue",
                                 p["issue_code"], p.get("evidence_span"),
                                 p.get("confidence"), layer))
        for i, s in enumerate(iss.get("secondary_issues") or []):
            claims.append(_claim(f"issues.secondary[{i}]",
                                 s["issue_code"], s.get("evidence_span"),
                                 s.get("confidence"), layer))
        rel = record.get("political_relevance") or {}
        if rel:
            claims.append(_claim(
                "issues.election_competition_related",
                rel.get("election_competition_related"),
                rel.get("evidence_span"), None, layer))
    elif layer == "stance":
        for r in record.get("entity_stances") or []:
            row_claims(f"stance[{r['target_name']}]", r,
                       ["stance", "stance_origin",
                        "competence_perception", "integrity_perception",
                        "support_trajectory", "challenger_perception",
                        "voter_switching_mentioned"])
    elif layer == "framing":
        p = record.get("primary_frame")
        if p:
            claims.append(_claim("framing.primary", p["frame_category"],
                                 p.get("evidence_span"),
                                 p.get("confidence"), layer))
        for i, f in enumerate(record.get("secondary_frames") or []):
            claims.append(_claim(f"framing.secondary[{i}]",
                                 f["frame_category"],
                                 f.get("evidence_span"),
                                 f.get("confidence"), layer))
    elif layer == "credit_blame":
        for r in record.get("attributions") or []:
            claims.append(_claim(
                f"credit_blame[{r['target_name']}]"
                f".{r['attribution_type']}",
                r.get("attributed_outcome"), r.get("evidence_span"),
                r.get("confidence"), layer))
    elif layer == "consequence":
        for r in record.get("consequences") or []:
            row_claims(
                f"consequence[{r['affected_actor_name']}]", r,
                ["direction", "impact_mechanism", "electoral_signal"])
    elif layer == "relevance":
        row_claims("relevance", record, ["geographic_scope",
                                         "electoral_interpretation"])
    elif layer == "temporal":
        claims.append(_claim("temporal.impact_horizon",
                             record.get("impact_horizon"),
                             record.get("evidence_span"),
                             record.get("confidence"), layer))
        tm = record.get("temporal_mechanism") or {}
        for f in ("persistence", "continuing_story", "expected_decay"):
            if f in tm:
                claims.append(_claim(f"temporal.{f}", tm[f],
                                     record.get("evidence_span"),
                                     record.get("confidence"), layer))
    return claims


def check_claim(claim: dict, body: str, title: str,
                record_flagged: bool) -> dict:
    """Consistency checks + uncertainty representation for one
    flattened claim. Missing evidence is explicitly recorded, never
    dropped."""
    span = claim.get("evidence_span")
    conf = claim.get("confidence_score")
    value = claim.get("extracted_value")
    val_uncertain = isinstance(value, str) \
        and value.lower() in UNCERTAIN_VALUES

    flags: list[str] = []
    text = (span or {}).get("text", "") if isinstance(span, dict) else ""
    if text:
        haystack = title if (span or {}).get("from_title") else body
        evidence_ok = text in haystack
        if not evidence_ok:
            flags.append("evidence_not_verbatim")
    else:
        evidence_ok = False
        if not val_uncertain:
            flags.append("unsupported")
        else:
            flags.append("missing_evidence_recorded")
    if isinstance(conf, (int, float)) and conf >= 0.80 \
            and (val_uncertain or not text):
        flags.append("weak_evidence_high_confidence")

    uncertainty_flag = val_uncertain or band(conf) == "low" \
        or not evidence_ok
    reasons = []
    if val_uncertain:
        reasons.append(f"value {value!r} expresses uncertainty or "
                       "absence")
    if band(conf) == "low":
        reasons.append("low confidence - requires inference or weak "
                       "evidence")
    if not evidence_ok and text:
        reasons.append("evidence failed verbatim verification")
    if not text:
        reasons.append("no evidence span recorded")
    review = record_flagged or band(conf) == "low" \
        or "unsupported" in flags or "evidence_not_verbatim" in flags \
        or "weak_evidence_high_confidence" in flags

    return {**claim,
            "evidence_supported": evidence_ok,
            "confidence_band": band(conf),
            "consistency_flags": sorted(flags),
            "uncertainty_flag": uncertainty_flag,
            "uncertainty_reason": "; ".join(reasons) or None,
            "human_review_required": review}


def article_uncertainty_reasons(records: dict) -> list[str]:
    """Article-level uncertainty narratives, including the two
    canonical cases from the specification."""
    reasons = []
    rel = (records.get("relevance") or {})
    if rel.get("geographic_scope") == "national" \
            and rel.get("electoral_interpretation") in ("none",
                                                        "national_political_trend"):
        reasons.append("National issue without explicit local "
                       "electoral linkage")
    ru = ((records.get("pilot_full_schema") or {}).get("reform_uk")
          or {})
    if ru.get("national_momentum") \
            and not ru.get("local_campaign_activity"):
        reasons.append("Coverage indicates national momentum but "
                       "local conversion uncertain")
    return reasons


def summarise(claims: list[dict]) -> dict:
    """Per-article (or corpus) aggregation."""
    total = len(claims)
    supported = sum(1 for c in claims if c["evidence_supported"])
    unsupported = sum(1 for c in claims
                      if "unsupported" in c["consistency_flags"]
                      or "evidence_not_verbatim"
                      in c["consistency_flags"])
    dist = {"high": 0, "medium": 0, "low": 0, "missing": 0}
    for c in claims:
        dist[c["confidence_band"]] += 1
    return {"total_claims": total, "supported_claims": supported,
            "unsupported_claims": unsupported,
            "missing_evidence_recorded": sum(
                1 for c in claims if "missing_evidence_recorded"
                in c["consistency_flags"]),
            "confidence_distribution": dist,
            "review_required": sum(
                1 for c in claims if c["human_review_required"])}
