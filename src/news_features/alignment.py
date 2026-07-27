"""Phase 7 / Step 1 - article-to-entity alignment (pure logic; the
runner does the IO; NO LLM call anywhere - alignment links what the
frozen layers already assert to the official election tables, it
never re-reads article text).

Design position:

* Evidence-only linking. Every link cites where its evidence lives
  (collection metadata, the frozen relevance layer's geographic
  entities, the frozen entity/stance/credit-blame layers) and every
  match is an EXACT match after conservative normalisation. Nothing
  is inferred: a town mention is recorded as a town reference, never
  promoted to a ward; a name that matches no registry row - or more
  than one - stays unresolved.
* The frozen context layer is read-only input (its sha256 is
  re-checked against the version manifest before aligning).
* Deterministic and reproducible: sorted output, no timestamps at
  runtime, rebuilds are byte-identical.

Name normalisation is deliberately minimal (case, '&'/'and',
trailing 'ward'/'division' suffixes, punctuation spacing, the
incumbency '*' marker) so that only true string variants unify;
anything beyond that is treated as a different name. Grammatical
party variants observed in the pilot cards ('Conservatives',
'Labour Party', 'Ukip', ...) map through an explicit, reviewable
synonym table - never through fuzzy matching.
"""

from __future__ import annotations

import re

ALIGNMENT_VERSION = "article-entity-alignment-v1.0-2026-07-27"

# ---- election registry ---------------------------------------------
# The four election windows the corpus was collected under. The
# election link's evidence is the collection metadata itself (each
# article was gathered inside exactly one election window and carries
# that election_id from Phase 3 onwards); polling dates were frozen
# into the deterministic temporal layer in Phase 6 Step 9.
ELECTIONS = {
    "SCC-2013-05": {"year": 2013, "type": "scheduled_county_council",
                    "polling_date": "2013-05-02"},
    "SCC-2017-05": {"year": 2017, "type": "scheduled_county_council",
                    "polling_date": "2017-05-04"},
    "SCC-2021-05": {"year": 2021, "type": "scheduled_county_council",
                    "polling_date": "2021-05-06"},
    "ESWS-2026-05": {"year": 2026,
                     "type": "scheduled_unitary_council",
                     "polling_date": "2026-05-07"},
}

# Explicit party synonym table for grammatical variants observed in
# the pilot cards. Values are names AS THEY APPEAR in the registry
# (published or standardised); absence from this table is not an
# error - unmatched names stay unresolved.
PARTY_SYNONYMS = {
    "conservatives": "conservative",
    "conservative party": "conservative",
    "local conservatives": "conservative",
    "labour party": "labour",
    "labour (welsh government)": "labour",
    "labour and co-operative": "labour",
    "labour co-op": "labour",
    "liberal democrat": "liberal democrats",
    "lib dems": "liberal democrats",
    "ukip": "uk independence party",
    "green party": "green",
    "the green party": "green",
    "greens": "green",
    "reform": "reform uk",
}


def norm(s: str) -> str:
    """Conservative string normalisation shared by all matchers."""
    s = s.lower().strip().replace("&", "and")
    s = re.sub(r"[’`]", "'", s)
    s = re.sub(r"[.,]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_ward(s: str) -> str:
    """Ward names additionally drop the 'ward'/'division' suffix the
    press adds ('Shalford ward') and the results tables sometimes
    carry ('Ashtead Ward')."""
    return re.sub(r"\s+(ward|division)$", "", norm(s))


def norm_candidate(s: str) -> str:
    """Candidate names drop the results tables' incumbency marker
    ('John Furey*') and honorifics - nothing else."""
    s = s.replace("*", "")
    s = re.sub(r"^(sir|dame|dr|cllr)\s+", "", s.strip(),
               flags=re.IGNORECASE)
    return norm(s)


def _row(article_id: str, election_id: str, *, alignment_type: str,
         matched_entity: str | None = None, ward_id: str = None,
         party_id: str = None, candidate_id: str = None,
         matching_method: str, confidence: float | None,
         evidence_source: str, unresolved: bool = False) -> dict:
    """One alignment record in the required output schema."""
    return {"article_id": article_id, "election_id": election_id,
            "ward_id": ward_id, "party_id": party_id,
            "candidate_id": candidate_id,
            "alignment_type": alignment_type,
            "matched_entity": matched_entity,
            "matching_method": matching_method,
            "confidence_score": confidence,
            "evidence_source": [evidence_source],
            "unresolved_flag": unresolved}


# ---- 1. election alignment -----------------------------------------

def align_election(card: dict, windows: dict | None) -> dict:
    """Deterministic: the collection window IS the election. The
    deterministic temporal layer corroborates with the polling date
    (they must agree - a mismatch would mean upstream corruption)."""
    eid = card["article_metadata"]["election_id"]
    info = ELECTIONS[eid]
    if windows and windows.get("polling_date") != info["polling_date"]:
        raise ValueError(f"polling date mismatch for {eid}")
    return _row(card["article_id"], eid, alignment_type="election",
                matched_entity=eid, matching_method="collection_window",
                confidence=1.0,
                evidence_source="collection_metadata+deterministic"
                                "_temporal_layer")


# ---- 2. geographic alignment ---------------------------------------

def align_geography(card: dict, ward_index: dict,
                    borough_names: set) -> list[dict]:
    """Link ward/borough/county mentions from the frozen relevance
    layer's geographic_entities to the official tables. Methods, in
    the spec's vocabulary: exact_ward_mention, council_area,
    town_location_reference, unresolved. (candidate_location rows are
    produced by align_candidates, where the candidate evidence is.)"""
    aid = card["article_id"]
    eid = card["article_metadata"]["election_id"]
    rel = card.get("local_national_relevance")
    if not rel:
        return [_row(aid, eid, alignment_type="ward",
                     matching_method="unresolved", confidence=None,
                     evidence_source="relevance_layer_quarantined",
                     unresolved=True)]
    conf = rel.get("confidence")
    ge = rel.get("geographic_entities") or {}
    rows = []

    # exact ward/division mention against THIS election's ward list
    for name in (ge.get("wards") or []) + (ge.get("divisions") or []):
        key = norm_ward(name)
        official = ward_index.get(eid, {}).get(key)
        if official:
            rows.append(_row(aid, eid, alignment_type="ward",
                             ward_id=f"{eid}:{official}",
                             matched_entity=official,
                             matching_method="exact_ward_mention",
                             confidence=conf,
                             evidence_source="relevance_layer_"
                                             "geographic_entities"))
        else:   # mentioned but not in this election's official list
            rows.append(_row(aid, eid, alignment_type="ward",
                             matched_entity=name,
                             matching_method="unresolved",
                             confidence=conf,
                             evidence_source="relevance_layer_"
                                             "geographic_entities",
                             unresolved=True))

    # council area (borough/district) - recorded at its own level,
    # never promoted to a ward
    for name in ge.get("boroughs") or []:
        key = re.sub(r"\s+(borough|district)?\s*(council)?$", "",
                     norm(name)).strip()
        if key in borough_names:
            rows.append(_row(aid, eid, alignment_type="borough",
                             matched_entity=key,
                             matching_method="council_area",
                             confidence=conf,
                             evidence_source="relevance_layer_"
                                             "geographic_entities"))
        else:
            rows.append(_row(aid, eid, alignment_type="borough",
                             matched_entity=name,
                             matching_method="unresolved",
                             confidence=conf,
                             evidence_source="relevance_layer_"
                                             "geographic_entities",
                             unresolved=True))

    # town/village references: kept as references (boundary rule -
    # no town-to-ward gazetteer inference)
    for name in ge.get("towns_villages") or []:
        rows.append(_row(aid, eid, alignment_type="town_reference",
                         matched_entity=name,
                         matching_method="town_location_reference",
                         confidence=conf,
                         evidence_source="relevance_layer_"
                                         "geographic_entities",
                         unresolved=True))

    if ge.get("surrey_county"):
        rows.append(_row(aid, eid, alignment_type="county",
                         matched_entity="Surrey",
                         matching_method="council_area",
                         confidence=conf,
                         evidence_source="relevance_layer_"
                                         "geographic_entities"))
    return rows


# ---- 3. party alignment --------------------------------------------

def match_party(name: str, registry: dict) -> tuple | None:
    """registry: normalised published/standardised name ->
    (party_id, standardised name). Returns None when the name is not
    a Surrey-registry party (e.g. SNP, Plaid Cymru) - recorded, not
    guessed."""
    key = norm(name)
    key = PARTY_SYNONYMS.get(key, key)
    return registry.get(key)


def align_parties(card: dict, registry: dict) -> list[dict]:
    """One link per mentioned party, from every frozen layer that
    carries party actors. role_in_article records WHICH layer(s)
    mention it - the downstream feature stage decides how to weigh
    each role; alignment only preserves them."""
    aid = card["article_id"]
    eid = card["article_metadata"]["election_id"]
    mentions = []   # (party string, role, confidence, source)

    pe = card.get("political_entities") or {}
    for p in pe.get("party_context") or []:
        mentions.append((p["party"], "party_context:"
                         + str(p.get("overall_context")),
                         p.get("confidence"),
                         "entity_layer_party_context"))
    for s in (card.get("stance") or {}).get("entity_stances") or []:
        if s.get("target_type") == "party":
            mentions.append((s["target_name"],
                             "stance_target:" + str(s.get("stance")),
                             s.get("confidence"), "stance_layer"))
    for a in (card.get("credit_blame") or {}).get("attributions") or []:
        if a.get("target_type") == "party":
            mentions.append((a["target_name"], "attribution_target:"
                             + str(a.get("attribution_type")),
                             a.get("confidence"), "credit_blame_layer"))

    rows = []
    for name, role, conf, source in mentions:
        hit = match_party(name, registry)
        if hit:
            pid, std = hit
            r = _row(aid, eid, alignment_type="party", party_id=pid,
                     matched_entity=std,
                     matching_method="party_registry_exact",
                     confidence=conf, evidence_source=source)
        else:
            r = _row(aid, eid, alignment_type="party",
                     matched_entity=name,
                     matching_method="unresolved",
                     confidence=conf, evidence_source=source,
                     unresolved=True)
        r["party_name_as_mentioned"] = name
        r["role_in_article"] = role
        rows.append(r)
    return rows


# ---- 4. candidate alignment ----------------------------------------

def align_candidates(card: dict, cand_registry: dict,
                     results_index: dict) -> list[dict]:
    """Exact-name match against the candidate registry; where the
    matched candidate stood in THIS election, the results row also
    yields a candidate_location ward link. Zero matches or more than
    one distinct candidate ID -> unresolved (no identity inference)."""
    aid = card["article_id"]
    eid = card["article_metadata"]["election_id"]
    pe = card.get("political_entities") or {}
    rows = []
    for c in pe.get("candidate_context") or []:
        key = norm_candidate(c["name"])
        ids = cand_registry.get(key, set())
        if len(ids) == 1:
            cid, party = next(iter(ids))
            rows.append(_row(aid, eid, alignment_type="candidate",
                             candidate_id=cid, party_id=None,
                             matched_entity=c["name"],
                             matching_method="candidate_registry_exact",
                             confidence=c.get("confidence"),
                             evidence_source="entity_layer_candidate"
                                             "_context+candidate_"
                                             "registry"))
            # candidate stood in this election -> ward via candidate
            for ward in sorted(results_index.get(eid, {})
                               .get(key, set())):
                rows.append(_row(aid, eid, alignment_type="ward",
                                 ward_id=f"{eid}:{ward}",
                                 candidate_id=cid,
                                 matched_entity=ward,
                                 matching_method="candidate_location",
                                 confidence=c.get("confidence"),
                                 evidence_source="official_results_"
                                                 "candidate_row"))
        else:
            method = ("ambiguous_multiple_registry_matches"
                      if len(ids) > 1 else "unresolved")
            rows.append(_row(aid, eid, alignment_type="candidate",
                             matched_entity=c["name"],
                             matching_method=method,
                             confidence=c.get("confidence"),
                             evidence_source="entity_layer_candidate"
                                             "_context",
                             unresolved=True))
    return rows


# ---- dedup ----------------------------------------------------------

def dedupe(rows: list[dict]) -> list[dict]:
    """No duplicate entity links: same (article, type, entity) rows
    merge - evidence sources union, confidence takes the maximum,
    roles concatenate. Order is deterministic (first appearance)."""
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["article_id"], r["alignment_type"], r["ward_id"],
               r["party_id"], r["candidate_id"],
               norm(r["matched_entity"]) if r["matched_entity"]
               else None, r["matching_method"])
        if key in out:
            kept = out[key]
            for src in r["evidence_source"]:
                if src not in kept["evidence_source"]:
                    kept["evidence_source"].append(src)
            if r.get("role_in_article") and kept.get("role_in_article") \
                    and r["role_in_article"] not in kept["role_in_article"]:
                kept["role_in_article"] += "; " + r["role_in_article"]
            confs = [c for c in (kept["confidence_score"],
                                 r["confidence_score"])
                     if c is not None]
            kept["confidence_score"] = max(confs) if confs else None
        else:
            out[key] = r
    return list(out.values())
