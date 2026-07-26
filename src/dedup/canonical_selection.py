"""Phase 5 / Step 7 - canonical article selection (pure logic; the
runner does the IO).

Contract: for every validated family from Step 6, choose ONE member
as the canonical record for downstream LLM extraction and feature
engineering - or refuse to choose when the evidence does not support
a safe choice. Selection is bookkeeping, not deletion: every member
stays in the mapping with its relationships intact, and the decision
itself must be reproducible from recorded evidence.

Ranking framework (deterministic; applied in this exact order, each
criterion recorded per member so the choice is an argument):

    1. text usability      full structured text outranks partial or
                           snippet records (a snippet is nearly
                           useless for LLM extraction, whatever its
                           timestamps say).
    2. temporal validity   among equally usable members, a version
                           whose text state is CONFIRMED to exist
                           before the election (pre-polling archive
                           capture) outranks one whose pre-election
                           existence rests only on the page's own
                           publication claim - a later state that is
                           only demonstrable after the election never
                           beats a confirmed pre-election sibling of
                           equal usability, which is what keeps
                           future information out.
    3. cleanliness         no quality/truncation flags outranks
                           flagged records.
    4. provenance          usable publication date, then a stable
                           canonical URL.
    5. tiebreak            earlier demonstrable availability (the
                           conservative anti-leakage default: prefer
                           the text state pinned earliest), then the
                           lexicographically smallest article id so
                           reruns are byte-identical.

    Deliberately ABSENT from the key: body length, publisher size,
    retrieval order, and "newest version" - the specification's
    forbidden shortcuts. An archive capture is availability EVIDENCE
    feeding criterion 1/5; being an archive copy neither wins nor
    loses by itself.

Refusal rules (conservative - uncertainty is recorded, not papered
over):

    * a family whose members differ substantively, whose version
      order is unknown AND where no member has confirmed pre-election
      availability -> canonical_uncertain_manual_review: picking
      blind between materially different texts is a research
      decision, not a tiebreak;
    * a family with no full-text member at all -> review;
    * syndication families: the ORIGIN member (from Step 4 direction
      evidence) is preferred when known; with origin unknown the best
      research-quality member is selected with confidence "low" and
      the uncertainty retained in the reason - never silently
      upgraded.

Independent articles never enter this module - they need no
canonical choice and the runner maps them straight through.
"""

from __future__ import annotations

RULE_VERSION = "canonical-v1.0-2026-07-26"

# relationship classes whose members differ materially in content -
# a blind pick between them is unsafe
SUBSTANTIVE_CLASSES = {"substantive_update", "partial_to_full_version"}


def member_rank_key(m: dict) -> tuple:
    """Sort key implementing the ranking framework. Larger is better
    for the boolean criteria, so they are negated for ascending sort;
    available_from sorts ascending (earlier pins win); article_id
    last for total determinism. ``available_from`` may be empty -
    empty sorts AFTER any real timestamp (chr(0x10FFFF) trick keeps
    the key type stable)."""
    return (not m.get("full_text", False),
            not m.get("temporal_confirmed", False),
            not m.get("clean", False),
            not m.get("pub_date_usable", False),
            not m.get("stable_url", False),
            m.get("available_from") or "\U0010ffff",
            m["article_id"])


def member_evidence(m: dict) -> str:
    """One auditable evidence string per member - the recorded basis
    of the ranking, mirroring member_rank_key term by term."""
    return (f"temporal_confirmed={m.get('temporal_confirmed', False)};"
            f"full_text={m.get('full_text', False)};"
            f"clean={m.get('clean', False)};"
            f"pub_date_usable={m.get('pub_date_usable', False)};"
            f"stable_url={m.get('stable_url', False)};"
            f"available_from={m.get('available_from', '')}")


def select_canonical(family: dict, members: list[dict]) -> dict:
    """Choose (or refuse to choose) the canonical member of one
    validated family.

    ``family``: {family_id, family_type, ordered,
    relationship_classes}. ``members``: per-member evidence dicts
    with article_id, full_text, clean, pub_date_usable, stable_url,
    temporal_confirmed, available_from, is_origin (syndication only).

    Returns the full decision record: status, canonical id,
    confidence, per-member ranking evidence and per-alternative
    rejection reasons. Members are never dropped."""
    classes = set(family.get("relationship_classes") or [])
    ranked = sorted(members, key=member_rank_key)
    evidence = {m["article_id"]: member_evidence(m) for m in ranked}

    # ---- refusal rules ----------------------------------------------
    if not any(m.get("full_text") for m in members):
        return _decision(family, None, ranked, evidence, "review",
                         "no full-text member available", "none")
    if (classes & SUBSTANTIVE_CLASSES
            and not family.get("ordered", False)
            and not any(m.get("temporal_confirmed") for m in members)):
        return _decision(family, None, ranked, evidence, "review",
                         "members differ substantively, version order "
                         "unknown and no member has confirmed "
                         "pre-election availability - a blind pick is "
                         "unsafe", "none")

    # ---- syndication: origin first, else best quality + uncertainty -
    if family.get("family_type") in ("syndication_family",
                                     "shared_press_release_family"):
        origins = [m for m in ranked if m.get("is_origin")]
        if origins:
            chosen = origins[0]
            return _decision(family, chosen, ranked, evidence,
                             "selected",
                             "origin publisher established by Step 4 "
                             "attribution-plus-chronology evidence",
                             "high")
        chosen = ranked[0]
        return _decision(family, chosen, ranked, evidence, "selected",
                         "origin unknown - best research-quality "
                         "representation selected, origin uncertainty "
                         "retained", "low")

    # ---- general case: the ranking framework decides ----------------
    chosen = ranked[0]
    confidence = "high"
    reason = "ranked first on temporal validity, usability and provenance"
    if (classes & SUBSTANTIVE_CLASSES) and not family.get("ordered"):
        confidence = "medium"
        reason += ("; members differ substantively and order is "
                   "unknown, but the chosen text state is confirmed "
                   "pre-election so no future information can enter")
    return _decision(family, chosen, ranked, evidence, "selected",
                     reason, confidence)


def _decision(family, chosen, ranked, evidence, status, reason,
              confidence) -> dict:
    """Assemble the decision record shared by all paths."""
    alternatives = [m["article_id"] for m in ranked
                    if chosen is None or m["article_id"]
                    != chosen["article_id"]]
    rejected = {}
    for m in ranked:
        if chosen is not None and m["article_id"] == chosen["article_id"]:
            continue
        if chosen is None:
            rejected[m["article_id"]] = "family in review - no selection"
        elif not m.get("full_text") and chosen.get("full_text"):
            rejected[m["article_id"]] = "not a full-text record"
        elif not m.get("temporal_confirmed") \
                and chosen.get("temporal_confirmed"):
            rejected[m["article_id"]] = ("pre-election availability not "
                                         "confirmed for this member")
        elif not m.get("clean") and chosen.get("clean"):
            rejected[m["article_id"]] = "carries quality flags"
        else:
            rejected[m["article_id"]] = ("ranked lower on availability "
                                         "tiebreak or deterministic id "
                                         "order")
    return {"family_id": family["family_id"],
            "family_type": family.get("family_type", ""),
            "canonical_status": "canonical_selected" if status
            == "selected" else "canonical_uncertain_manual_review",
            "canonical_article_id": chosen["article_id"] if chosen
            else "",
            "confidence": confidence,
            "selection_reason": reason,
            "member_evidence": evidence,
            "alternatives": alternatives,
            "rejected_reasons": rejected,
            "temporal_validity_status": "confirmed_pre_election"
            if chosen and chosen.get("temporal_confirmed")
            else ("publication_claim_only" if chosen else "unresolved"),
            "rule_version": RULE_VERSION}
