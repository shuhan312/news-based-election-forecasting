"""Phase 7 / Step 3 - local/national news scope separation (pure
logic; the runner does the IO; NO LLM call anywhere).

Design position: the CONTENT-BASED scope judgement already exists.
Phase 6 Step 8 extracted, per article and with verbatim evidence,
the geographic scope, geographic entities, mention flags, issue
scope and the two 0-1 relevance scores - and that layer is frozen.
Re-asking an LLM the same question here would cost money to create
a second, competing answer. This step therefore DERIVES the Step 3
classification deterministically from the frozen layer:

* the frozen geographic_scope enum maps one-to-one onto the five
  required categories (ward_specific_local, surrey_wide ->
  surrey_wide_local, regional, national -> national_political,
  mixed_national_local -> mixed_local_national);
* evidence, confidence and both relevance scores are carried over
  verbatim from the frozen record - never recomputed, never
  inflated;
* articles whose frozen relevance record is quarantined or missing
  become scope "uncertain" and stay that way - the spec forbids
  forcing a classification, and so does the project's
  evidence-or-nothing rule.

The publication source is used NOWHERE in this mapping - the frozen
judgement was made from article text alone (the LLM never saw the
source name as a classification instruction), which is exactly the
spec's requirement that scope reflect content, not outlet. The
collection arm (which search channel found the article) is carried
as provenance only, per decision D2.
"""

from __future__ import annotations

SCOPE_VERSION = "news-scope-v1.0-2026-07-27"

# frozen Step 8 enum -> this step's five required categories
SCOPE_MAP = {
    "ward_specific_local": "ward_specific_local",
    "surrey_wide": "surrey_wide_local",
    "regional": "regional",
    "national": "national_political",
    "mixed_national_local": "mixed_local_national",
}

# frozen issue_scope enum -> the spec's local/national/both values
ISSUE_MAP = {
    "local_issue": "local",
    "national_issue": "national",
    "both_local_and_national": "both",
}

FIVE_SCOPES = sorted(set(SCOPE_MAP.values()))


def affected_area(ge: dict) -> dict:
    """Most-specific affected area the frozen geographic entities
    support: named wards beat towns beat boroughs beat county beat
    UK. Pure reshaping of extracted entities - no gazetteer lookups,
    no inference beyond what the frozen record asserts."""
    for level, key in (("ward_division", "wards"),
                       ("ward_division", "divisions"),
                       ("town_village", "towns_villages"),
                       ("borough_district", "boroughs")):
        names = ge.get(key) or []
        if names:
            return {"level": level, "names": sorted(names)}
    if ge.get("surrey_county"):
        return {"level": "surrey_county", "names": ["Surrey"]}
    if ge.get("uk_wide"):
        return {"level": "uk_wide", "names": ["United Kingdom"]}
    return {"level": "unknown", "names": []}


def classify_article(card: dict, ward_ids: list[str],
                     party_ids: list[str]) -> dict:
    """One frozen context card -> one scope classification record.
    ward_ids/party_ids are the article's RESOLVED Step 1 alignment
    links, preserved so downstream features keep the join keys."""
    rec = {"article_id": card["article_id"],
           "election_id": card["article_metadata"]["election_id"],
           "collection_arm_provenance_only":
               card["article_metadata"]["arm"],
           "ward_links": ward_ids,
           "party_links": party_ids}

    rel = card.get("local_national_relevance")
    if not rel:
        # quarantined/missing frozen record: uncertain, not forced
        status = card["validation_status"]["per_layer"]["relevance"]
        rec.update({
            "scope_classification": "uncertain",
            "affected_area": {"level": "unknown", "names": []},
            "geographic_flags": None, "political_flags": None,
            "issue_scope": "uncertain",
            "local_relevance_score": None,
            "national_relevance_score": None,
            "evidence": None, "confidence": None,
            "review_status": "flagged",
            "uncertainty_reason": f"frozen relevance record {status}"})
        return rec

    flags = rel.get("mention_flags") or {}
    scores = rel.get("relevance") or {}
    span = rel.get("evidence_span") or {}
    rec.update({
        "scope_classification": SCOPE_MAP[rel["geographic_scope"]],
        "affected_area": affected_area(
            rel.get("geographic_entities") or {}),
        "geographic_flags": {
            "ward_mentioned": flags.get("ward_mentioned"),
            "surrey_mentioned": flags.get("surrey_mentioned"),
            "candidate_mentioned": flags.get("candidate_mentioned")},
        "political_flags": {
            "national_party_leader_mentioned":
                flags.get("national_leader_mentioned")},
        "issue_scope": ISSUE_MAP.get(rel.get("issue_scope"),
                                     "uncertain"),
        "local_relevance_score": scores.get("local_score"),
        "national_relevance_score": scores.get("national_score"),
        "evidence": {
            "text": span.get("text"),
            "evidence_source": "frozen loc-nat relevance layer "
                               + rel["schema_version"],
            "reasoning": scores.get("reasoning")},
        "confidence": rel.get("confidence"),
        "review_status": rel.get("review_status")})
    return rec


def check_record(rec: dict) -> list[str]:
    """Deterministic validation (rules L1-L5). Empty list = valid."""
    errs = []
    scope = rec.get("scope_classification")
    if scope not in FIVE_SCOPES + ["uncertain"]:            # L1
        errs.append(f"L1 invalid scope {scope!r}")
    for f in ("local_relevance_score", "national_relevance_score"):
        v = rec.get(f)                                      # L2
        if v is not None and not (isinstance(v, (int, float))
                                  and 0.0 <= v <= 1.0):
            errs.append(f"L2 {f} out of range: {v!r}")
    if scope != "uncertain":                                # L3
        ev = rec.get("evidence") or {}
        if not ev.get("text"):
            errs.append("L3 classified without evidence text")
        if rec.get("confidence") is None:
            errs.append("L3 classified without confidence")
    else:                                                   # L4
        if rec.get("evidence") is not None \
                or rec.get("confidence") is not None:
            errs.append("L4 uncertain record must not fake evidence")
        if rec.get("review_status") != "flagged":
            errs.append("L4 uncertain record must be flagged")
    if scope == "uncertain" and rec.get("issue_scope") not in \
            ("uncertain",):                                 # L5
        errs.append("L5 uncertain scope with confident issue_scope")
    return sorted(errs)
