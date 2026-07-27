"""Phase 7 / Step 4 - article-level feature construction (pure
logic; the runner does the IO; NO LLM call anywhere).

Unit of observation: article x election x geographic target x focal
party. One row per validated combination:

* focal parties  = the article's RESOLVED Step 1 party links; an
  article with none keeps a single no-focal-party row so its
  non-party context (scope, issues, temporal) stays available to
  election-level aggregation later;
* geographic targets = the article's RESOLVED ward links; an
  article with none gets one election-wide target. National
  articles are NEVER fanned out across wards - a ward target exists
  only where Step 1 validated an explicit link.

Missing-value discipline (the spec's five states): every feature
group carries a *_status column distinguishing

    extracted            values are real extractions
    confirmed_absent     layer valid, focal actor simply not there
                         (zeros/False are genuine absence)
    no_focal_party       group needs a focal party, row has none
    not_applicable       group does not apply (e.g. Reform block on
                         a non-Reform focal row)
    quarantined          the frozen layer record failed validation
                         (values None - extraction failure)
    not_extracted        the frozen contract never captured this
                         field (values None - honest gap, e.g.
                         party-level mention counts)

Zeros are therefore only written where absence was actually
observed; every None is explained by its group status.

Evidence discipline: feature files carry confidence scores and
evidence AVAILABILITY, never quote text (keeps them Git-safe); the
verbatim spans stay in the frozen layer, addressable by article_id
+ layer + target name, which the columns preserve.

Focal matching uses the same conservative normalisation + explicit
synonym table as Step 1 (imported, not duplicated) plus the
name-as-mentioned strings Step 1 recorded per article - a layer row
counts for the focal party only when its target name resolves to
the SAME party_id. Reform UK and UKIP are distinct registry parties
and never share a focal row (tested).
"""

from __future__ import annotations

from .alignment import match_party, norm

FEATURES_VERSION = "article-features-v1.0-2026-07-27"

ELECTION_WIDE = "ELECTION_WIDE"

# prominence enum (frozen candidate_context) -> 0-1 score; the raw
# enum is kept alongside so the mapping is reversible
PROMINENCE_SCORE = {"headline": 1.0, "major": 0.75, "secondary": 0.5,
                    "passing": 0.25}

# consequence-layer enum -> feature indicators (documented mapping,
# no new vocabulary invented)
GROWTH_SIGNALS = {"support_growth"}
DECLINE_SIGNALS = {"support_decline"}
CHALLENGER_SIGNALS = {"challenger_emergence", "increased_credibility"}
SWITCH_SIGNALS = {"voter_switching_possibility"}
ANTI_INCUMBENT = {"incumbent_vulnerability"}


def _match_names(names: set[str], name: str | None,
                 registry: dict, focal_pid: str) -> bool:
    """Does ``name`` (a layer row's actor string) refer to the focal
    party? True when Step 1 recorded it as a mention of this party
    in this article, or when it resolves to the same party_id
    through the same registry+synonym path Step 1 used."""
    if not name:
        return False
    if norm(name) in names:
        return True
    hit = match_party(name, registry)
    return bool(hit and hit[0] == focal_pid)


# ---- per-group builders (each returns dict of columns) -------------

def mention_features(card, focal_pid, focal_names, registry):
    pe = card.get("political_entities")
    if focal_pid is None:
        return {"mention_status": "no_focal_party"}
    if pe is None:
        return {"mention_status": "quarantined"}
    out = {}
    prow = next((p for p in pe.get("party_context") or []
                 if _match_names(focal_names, p.get("party"),
                                 registry, focal_pid)), None)
    title = norm(card["article_metadata"].get("title") or "")
    out["party_mentioned"] = 1  # focal set comes FROM resolved links
    # party-level mention counts were never part of the frozen
    # contract (candidate rows carry counts, party rows do not)
    out["party_mention_count"] = None
    out["party_mention_count_status"] = "not_extracted"
    out["headline_party_mention"] = int(any(
        n in title for n in focal_names) or bool(
        prow and norm(prow["party"]) in title))
    # prominence = share of the party-bearing frozen layers that
    # carry a row for the focal party (0-1, construction documented)
    layers_present, layers_hit = 0, 0
    for rows, key in ((pe.get("party_context"), "party"),
                      ((card.get("stance") or {}).get("entity_stances"),
                       "target_name"),
                      ((card.get("credit_blame") or {})
                       .get("attributions"), "target_name"),
                      ((card.get("expected_electoral_consequence")
                        or {}).get("consequences"),
                       "affected_actor_name")):
        if rows is None:
            continue
        layers_present += 1
        if any(_match_names(focal_names, r.get(key), registry,
                            focal_pid) for r in rows):
            layers_hit += 1
    out["party_prominence_score"] = (round(layers_hit
                                           / layers_present, 3)
                                     if layers_present else None)
    out["party_directly_quoted"] = (None if prow is None
                                    else prow.get("directly_quoted"))
    # candidates OF the focal party, from the frozen candidate rows
    cands = [c for c in pe.get("candidate_context") or []
             if _match_names(focal_names, c.get("party"),
                             registry, focal_pid)
             or _match_names(focal_names, c.get("name"),
                             registry, focal_pid)]
    out["candidate_mentioned"] = int(bool(cands))
    out["candidate_mention_count"] = (sum(c.get("mention_count") or 0
                                          for c in cands) or None
                                      if cands else 0)
    out["candidate_prominence_level"] = max(
        (c.get("prominence") for c in cands if c.get("prominence")),
        key=lambda p: PROMINENCE_SCORE.get(p, 0), default=None)
    out["candidate_prominence_score"] = PROMINENCE_SCORE.get(
        out["candidate_prominence_level"])
    out["candidate_directly_quoted"] = (int(any(
        c.get("directly_quoted") for c in cands)) if cands else 0)
    out["mention_status"] = "extracted"
    return out


def scope_features(scope_rec, row_is_ward, unresolved_wards):
    s = scope_rec["scope_classification"]
    out = {f"{name}_indicator": int(s == name) for name in
           ("ward_specific_local", "surrey_wide_local", "regional",
            "national_political", "mixed_local_national")}
    out.update({
        "scope_classification": s,
        "valid_ward_link_indicator": int(row_is_ward),
        "unresolved_geography_indicator": int(
            s == "uncertain" or unresolved_wards > 0),
        "local_relevance_score": scope_rec["local_relevance_score"],
        "national_relevance_score":
            scope_rec["national_relevance_score"],
        "scope_confidence": scope_rec["confidence"],
        "scope_status": ("quarantined" if s == "uncertain"
                         else "extracted")})
    return out


def issue_features(card, taxonomy_codes, result_flagged):
    iss = card.get("issues")
    out = {f"sec_issue_{c}": None for c in taxonomy_codes}
    if iss is None:
        out.update({"primary_issue": None, "issues_status":
                    "quarantined", "poll_indicator": None})
    else:
        node = iss.get("issues") or {}
        prim = node.get("primary_issue") or {}
        secs = [x["issue_code"]
                for x in node.get("secondary_issues") or []]
        for c in taxonomy_codes:      # multi-hot, real zeros
            out[f"sec_issue_{c}"] = int(c in secs)
        codes = set(secs) | ({prim.get("issue_code")}
                             if prim else set())
        out.update({
            "primary_issue": prim.get("issue_code"),
            "primary_issue_confidence": prim.get("confidence"),
            "issues_taxonomy_version": node.get("taxonomy_version"),
            # no polling code exists in the frozen taxonomy as such;
            # voter_switching + anti_incumbent are separate features
            "poll_indicator": int(bool(
                codes & {"voter_switching", "polling"})),
            "issues_status": "extracted"})
    # event context from the full-schema layer
    pe = card.get("political_entities")
    ev = (pe or {}).get("event_context") or {}
    out["event_type"] = ev.get("event_type")
    out["event_status"] = ("quarantined" if pe is None
                           else "extracted" if ev.get("event_type")
                           else "confirmed_absent")
    # election prediction was never a frozen field - honest gap
    out["election_prediction_indicator"] = None
    out["election_prediction_status"] = "not_extracted"
    # result-reporting leakage: decision D3 - flagged, not silently
    # dropped; the modelling stage owns the exclusion switch
    out["election_result_indicator"] = int(result_flagged)
    return out


def stance_features(card, focal_pid, focal_names, registry):
    if focal_pid is None:
        return {"stance_status": "no_focal_party"}
    st = card.get("stance")
    pe = card.get("political_entities")
    if st is None:
        return {"stance_status": "quarantined"}
    rows = [r for r in st.get("entity_stances") or []
            if _match_names(focal_names, r.get("target_name"),
                            registry, focal_pid)]
    prow = next((p for p in (pe or {}).get("party_context") or []
                 if _match_names(focal_names, p.get("party"),
                                 registry, focal_pid)), None)
    if not rows and prow is None:
        return {"stance_status": "confirmed_absent",
                "positive_stance": 0, "neutral_stance": 0,
                "negative_stance": 0, "mixed_stance": 0,
                "praise_indicator": 0, "criticism_indicator": 0,
                "competence_positive": 0, "competence_negative": 0,
                "integrity_positive": 0, "integrity_negative": 0}
    r = rows[0] if rows else {}
    stance = r.get("stance")
    comp = r.get("competence_perception") or (prow or {}).get(
        "competence")
    integ = r.get("integrity_perception") or (prow or {}).get(
        "integrity")
    return {
        "positive_stance": int(stance == "positive"),
        "neutral_stance": int(stance == "neutral"),
        "negative_stance": int(stance == "negative"),
        "mixed_stance": int(stance == "mixed"),
        "stance_raw": stance,
        # praise/criticism come from the entity layer's own
        # credit/blame booleans (the attribution layer's directed
        # rows feed the separate attribution group)
        "praise_indicator": int(bool((prow or {}).get("credit"))),
        "criticism_indicator": int(bool((prow or {}).get("blame"))),
        "competence_positive": int(comp == "portrayed_positively"),
        "competence_negative": int(comp == "portrayed_negatively"),
        "competence_raw": comp,
        "integrity_positive": int(integ == "portrayed_positively"),
        "integrity_negative": int(integ == "portrayed_negatively"),
        "integrity_raw": integ,
        "stance_confidence": r.get("confidence") or (prow or {}).get(
            "confidence"),
        "stance_evidence_available": int(bool(
            (r.get("evidence_span") or (prow or {}).get(
                "evidence_span") or {}).get("text"))),
        "stance_status": "extracted"}


def framing_features(card, frame_categories):
    fr = card.get("framing")
    out = {f"frame_{c}": None for c in frame_categories}
    if fr is None:
        out["framing_status"] = "quarantined"
        out["primary_frame"] = None
        return out
    prim = fr.get("primary_frame") or {}
    cats = {sf["frame_category"]
            for sf in fr.get("secondary_frames") or []}
    if prim:
        cats.add(prim.get("frame_category"))
    for c in frame_categories:
        out[f"frame_{c}"] = int(c in cats)
    out.update({"primary_frame": prim.get("frame_category"),
                "primary_frame_confidence": prim.get("confidence"),
                "framing_status": "extracted"})
    return out


def attribution_features(card, focal_pid, focal_names, registry):
    if focal_pid is None:
        return {"attribution_status": "no_focal_party"}
    cb = card.get("credit_blame")
    if cb is None:
        return {"attribution_status": "quarantined"}
    received = {"blame": 0, "credit": 0, "mixed": 0, "unclear": 0}
    assigned = {"blame": 0, "credit": 0}
    for a in cb.get("attributions") or []:
        t = a.get("attribution_type")
        # target and source stay separate, per the spec
        if _match_names(focal_names, a.get("target_name"),
                        registry, focal_pid) and t in received:
            received[t] += 1
        if _match_names(focal_names, a.get("source_name"),
                        registry, focal_pid) and t in assigned:
            assigned[t] += 1
    return {"blame_received": int(received["blame"] > 0),
            "blame_received_count": received["blame"],
            "credit_received": int(received["credit"] > 0),
            "credit_received_count": received["credit"],
            "blame_assigned": int(assigned["blame"] > 0),
            "credit_assigned": int(assigned["credit"] > 0),
            "responsibility_unclear": int(
                received["mixed"] + received["unclear"] > 0),
            "attribution_status": "extracted"}


def consequence_features(card, focal_pid, focal_names, registry):
    if focal_pid is None:
        return {"consequence_status": "no_focal_party"}
    ec = card.get("expected_electoral_consequence")
    pe = card.get("political_entities")
    if ec is None:
        return {"consequence_status": "quarantined"}
    rows = [r for r in ec.get("consequences") or []
            if _match_names(focal_names, r.get("affected_actor_name"),
                            registry, focal_pid)]
    dirs = {r.get("direction") for r in rows}
    sigs = {r.get("electoral_signal") for r in rows}
    mechs = {r.get("impact_mechanism") for r in rows}
    # switching endpoints from the entity layer's party rows
    prow = next((p for p in (pe or {}).get("party_context") or []
                 if _match_names(focal_names, p.get("party"),
                                 registry, focal_pid)), None)
    def _pid(name):
        hit = match_party(name, registry) if name else None
        return hit[0] if hit else None
    out = {
        "potential_benefit": int("potential_benefit" in dirs),
        "potential_damage": int("potential_damage" in dirs),
        "mixed_or_unclear_impact": int(bool(
            dirs & {"mixed_impact", "unclear"})),
        "growth_signal": int(bool(sigs & GROWTH_SIGNALS)),
        "decline_signal": int(bool(sigs & DECLINE_SIGNALS)),
        "credible_challenger_signal": int(bool(
            sigs & CHALLENGER_SIGNALS)),
        "anti_incumbent_signal": int(
            bool(sigs & ANTI_INCUMBENT)
            or "anti_incumbent_sentiment" in mechs),
        "voter_switching_signal": int(
            bool(sigs & SWITCH_SIGNALS)
            or "voter_switching_signal" in mechs
            or bool((prow or {}).get("voter_switching_discussed"))),
        "switch_from_party_id": _pid((prow or {}).get(
            "switching_origin_party")),
        "switch_to_party_id": _pid((prow or {}).get(
            "switching_destination_party")),
        "consequence_confidence": (max(
            (r.get("confidence") for r in rows
             if r.get("confidence") is not None), default=None)),
        "consequence_status": ("extracted" if rows or prow
                               else "confirmed_absent")}
    return out


REFORM_FIELDS = {
    # spec name           -> frozen reform_uk field
    "reform_in_headline": "in_headline",
    "reform_candidate_mentioned": "candidate_mentioned",
    "reform_candidate_quoted": "candidate_quoted",
    "reform_local_campaign_activity": "local_campaign_activity",
    "reform_policy_mentioned": "policy_mentioned",
    "reform_gaining_support": "gaining_support",
    "reform_credible_challenger": "credible_challenger",
    "reform_con_to_reform_switching": "switching_con_to_reform",
    "reform_lab_to_reform_switching": "switching_lab_to_reform",
    "reform_ld_to_reform_switching": "switching_ld_to_reform",
    "reform_protest_anti_incumbent": "protest_anti_incumbent_support",
    "reform_national_momentum": "national_momentum",
    "reform_local_organisational_strength":
        "local_organisational_strength",
    "reform_credibility_score": "credibility_score",
    "reform_momentum_score": "momentum_score",
}


def reform_features(card, focal_is_reform):
    """Reform UK block. Explicit not_applicable on non-Reform focal
    rows; on Reform rows the frozen reform_uk section maps field-for-
    field (it was designed off the same brief). UKIP is a different
    registry party and never reaches this branch as Reform."""
    out = {k: None for k in REFORM_FIELDS}
    out.update({"reform_threat_to_conservative": None,
                "reform_threat_to_labour": None,
                "reform_threat_to_liberal_democrats": None,
                "reform_confidence": None})
    if not focal_is_reform:
        out["reform_status"] = "not_applicable"
        return out
    pe = card.get("political_entities")
    if pe is None:
        out["reform_status"] = "quarantined"
        return out
    ru = pe.get("reform_uk") or {}
    if not ru.get("reform_uk_present"):
        out["reform_status"] = "confirmed_absent"
        return out
    for feat, src in REFORM_FIELDS.items():
        v = ru.get(src)
        out[feat] = (int(v) if isinstance(v, bool) else v)
    threat = {norm(t) for t in ru.get("threat_to") or []}
    out.update({
        "reform_threat_to_conservative": int(bool(
            threat & {"conservative", "conservatives"})),
        "reform_threat_to_labour": int("labour" in threat),
        "reform_threat_to_liberal_democrats": int(bool(
            threat & {"liberal_democrat", "liberal_democrats"})),
        "reform_confidence": ru.get("confidence"),
        "reform_status": "extracted"})
    return out


def temporal_features(card, window_rec):
    out = {"publication_date": window_rec["publication_date"],
           "polling_date": window_rec["polling_date"],
           "days_before_polling": window_rec["days_before_polling"],
           "individual_time_window":
               window_rec["individual_time_window"]}
    for name, v in window_rec["cumulative_windows"].items():
        out[f"cum_{name}"] = int(v)
    th = (card.get("temporal_horizon") or {}).get("llm")
    if th is None:
        out.update({"impact_horizon": None, "persistence": None,
                    "continuing_story": None,
                    "temporal_llm_status": "quarantined"})
    else:
        tm = th.get("temporal_mechanism") or {}
        out.update({"impact_horizon": th.get("impact_horizon"),
                    "persistence": tm.get("persistence"),
                    "continuing_story": tm.get("continuing_story"),
                    "expected_decay": tm.get("expected_decay"),
                    "temporal_llm_status": "extracted"})
    return out
