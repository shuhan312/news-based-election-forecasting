"""Phase 5 / Step 5 - updated-article and version linking (pure
logic; the runner does the IO).

Contract: link different captured or published states of the SAME
underlying article into auditable version families, decide when each
specific text version was demonstrably available, and expose
prediction-window flags so a later update can never leak into an
earlier pre-election feature window. Nothing is deleted; every
version keeps its own text, hashes and timestamps. Canonical-article
selection is Step 6's question and is not asked here.

The cardinal failure mode is TEMPORAL LEAKAGE: an article published
before an election but silently updated afterwards (result
paragraphs, revised headline) must not have its later text counted as
pre-election evidence. Three defences:

1.  Six temporal fields are carried SEPARATELY, each with timezone
    status, evidence source, resolution status, confidence and a
    provenance reference - and one kind is never substituted for
    another:

        published_at        upstream effective date (the page's
                            resolved publication claim; date-only)
        updated_at          explicit update metadata - none exists in
                            the v1 layer, recorded as such, never
                            faked from another kind
        retrieved_at        when our collector fetched the live page
        archived_at         the Wayback capture timestamp
        first_observed_at   earliest of archive/retrieval - the first
                            moment WE can prove this text existed
        version_available_at  the availability decision (below)

2.  Version ORDER inside a family is decided only by published_at /
    updated_at. Retrieval and archive order say when we looked, not
    when the newsroom wrote, and never order versions.

3.  Temporal availability per version:

        confirmed_available_at      an archive/retrieval capture
                                    pins this exact text to a moment
        bounded_available_interval  the text existed somewhere in
                                    [published_at, first_observed_at]
                                    - both bounds preserved, no exact
                                    time invented
        availability_uncertain      no usable date and no capture
        not_temporally_usable       nothing usable at all

    Prediction-window flags (per the project's configured elections;
    window lengths from the Step 5 specification) then answer "was
    THIS text state available inside window W before polling day":

        yes_confirmed               effective date in window AND an
                                    archive capture at/before polling
                                    day proves this text state
                                    pre-election
        yes_publication_claim_only  effective date in window but the
                                    text state is first observed only
                                    later (bounded interval) - for
                                    downstream sensitivity testing,
                                    NEVER silently usable
        no                          effective date outside the window
        excluded_uncertain          availability uncertain
        not_usable                  not temporally usable

Version-candidate evidence (the runner selects candidates; this
module classifies): same canonical URL with different hashes, strong
same-publisher near-duplicate relationships, archive/current
variants. Shared topic, party, candidate or event is NEVER linking
evidence - similarity is computed from overlapping word sequences
only. Syndication (cross-publisher) stays in Step 4's outputs and is
never folded into version families.

Pairwise classification (thresholds versioned; text overlap only):

    identical bodies (equal hash, or jaccard/seq_ratio ~ 1)
                                        -> identical_recapture
    same canonical URL, exactly one side an archive capture,
      jaccard >= 0.70                   -> archive_current_version
    containment >= 0.85, length_ratio <= 0.75
                                        -> partial_to_full_version
    jaccard >= 0.85, <= 2 changed paragraphs, titles similar
                                        -> minor_update (the paragraph
                                           count discriminates; the
                                           jaccard floor just demands
                                           overwhelming reuse)
    jaccard >= 0.55                     -> substantive_update
    jaccard >= 0.30                     -> ambiguous_version_relationship
    below                               -> same_event_separate_article
    missing body                        -> manual_review

Change analysis is DESCRIPTIVE only (counts, samples, booleans for
title/standfirst/number/quote changes) - no political-impact calls.

Families: union-find over version-grade relationships; family id
VER-<sha12 of smallest member id>. version_sequence and predecessor/
successor links are assigned only when every member carries a usable
publication/update timestamp and no two are equal - a linear chain by
construction, so circular version relationships cannot occur; anything
less stays explicitly unordered and flagged.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .near_duplicates import (informative_title_tokens, pair_scores,
                              shingles)
from ..news_collection.resolve_publication_dates import ELECTIONS

RULE_VERSION = "version-link-v1.0-2026-07-26"

# Prediction windows (days before polling day) from the Step 5
# specification; polling days come from the protocol's configured
# ELECTIONS table - never hard-coded here.
PREDICTION_WINDOWS = {"six_months": 180, "three_months": 90,
                      "one_month": 30, "two_weeks": 14,
                      "one_week": 7, "final_72_hours": 3}

MIN_PARA_CHARS = 40      # boilerplate floor, same as Step 4
MODIFIED_PARA_RATIO = 0.6  # difflib ratio pairing a rewritten paragraph

VERSION_CLASSES = {"identical_recapture", "minor_update",
                   "substantive_update", "partial_to_full_version",
                   "archive_current_version"}

_NUM = re.compile(r"\d[\d,.]*%?")
_QUOTE = re.compile(r'["“]([^"”]{10,300})["”]')


# ---------------------------------------------------------------- time

def normalise_ts(value: str) -> tuple[str, str]:
    """(normalised UTC string, timezone_status). Handles the three
    shapes in this corpus: date-only effective dates, ISO timestamps
    with an offset, and 14-digit Wayback UTC stamps. Anything else is
    passed through and marked unparsed rather than guessed."""
    v = (value or "").strip()
    if not v:
        return "", "absent"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return v, "date_only_no_time"
    if re.fullmatch(r"\d{14}", v):        # Wayback: UTC by definition
        dt = datetime.strptime(v, "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"), "utc"
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            return dt.isoformat(), "naive_assumed_utc"
        return dt.astimezone(timezone.utc).isoformat(), "utc"
    except ValueError:
        return v, "unparsed"


def ts_date(norm: str) -> date | None:
    """UTC calendar date of a normalised timestamp (None if absent)."""
    return date.fromisoformat(norm[:10]) if norm else None


def temporal_field(value: str, evidence_source: str,
                   provenance: str, confidence: str) -> dict:
    """One of the six temporal fields, with the provenance the
    specification requires kept next to the value."""
    norm, tz = normalise_ts(value)
    return {"value": norm, "tz_status": tz,
            "evidence_source": evidence_source if norm else "",
            "resolution_status": "resolved" if norm else "absent",
            "confidence": confidence if norm else "",
            "provenance": provenance if norm else ""}


def temporal_profile(ev: dict) -> dict:
    """All six temporal fields for one captured version. updated_at
    does not exist in the v1 layer and is recorded absent - never
    substituted from retrieval or archive time."""
    published = temporal_field(
        ev.get("pub_date", ""), "date_resolution_pipeline",
        "news_collection/effective_dates.csv",
        ev.get("pub_date_confidence", "usable"))
    updated = temporal_field(ev.get("update_ts", ""),
                             "page_update_metadata", "", "")
    if not updated["value"]:
        updated["resolution_status"] = "not_available_in_v1_layer"
    retrieved = temporal_field(
        ev.get("retrieved_at", ""), "collector_fetch",
        "news_collection/url_duplicate_mapping_v1_provisional.csv",
        "observed")
    archived = temporal_field(
        ev.get("capture_ts", ""), "wayback_capture",
        "news_collection/url_duplicate_mapping_v1_provisional.csv",
        "observed")
    observed = sorted(v["value"] for v in (archived, retrieved)
                      if v["value"])
    first_observed = {"value": observed[0] if observed else "",
                      "tz_status": "utc" if observed else "absent",
                      "evidence_source": "earliest_of_archive_retrieval"
                      if observed else "",
                      "resolution_status": "resolved" if observed
                      else "absent",
                      "confidence": "observed" if observed else "",
                      "provenance": "derived"}
    return {"published_at": published, "updated_at": updated,
            "retrieved_at": retrieved, "archived_at": archived,
            "first_observed_at": first_observed}


def availability(ev: dict) -> dict:
    """The temporal-availability decision for one captured version.

    A capture (archive or our retrieval) PINS this exact text to a
    moment -> confirmed_available_at. A publication date alone only
    bounds it: the text existed somewhere in [published_at,
    first_observed_at] and both bounds are preserved - no exact
    timestamp is ever invented from an interval."""
    t = temporal_profile(ev)
    cap = t["first_observed_at"]["value"]
    pub = t["published_at"]["value"]
    if cap:
        # the capture confirms the text STATE at capture time; the
        # publication claim, when present, gives the interval's lower
        # bound for when that state may have first appeared
        return {"availability_status": "confirmed_available_at",
                "version_available_at": cap,
                "available_lower_bound": pub or cap,
                "available_upper_bound": cap}
    if pub:
        return {"availability_status": "bounded_available_interval",
                "version_available_at": "",
                "available_lower_bound": pub,
                "available_upper_bound": ""}
    return {"availability_status": "availability_uncertain"
            if ev.get("body") else "not_temporally_usable",
            "version_available_at": "",
            "available_lower_bound": "", "available_upper_bound": ""}


def window_flags(ev: dict, election_id: str) -> dict:
    """Per-window availability flags for one version, using the
    project's configured polling days.

    A version may claim yes_confirmed for a pre-election window only
    when (a) its effective date falls inside the window AND (b) an
    archive capture at or before polling day proves this exact text
    state existed pre-election. If the text state is first observed
    only after polling day, the pre-election claim rests on the page's
    own publication date -> yes_publication_claim_only, which the
    downstream policy must sensitivity-test, never silently use."""
    flags = {}
    polling = ELECTIONS.get(election_id, (None, None))[1]
    avail = availability(ev)
    t = temporal_profile(ev)
    pub_d = ts_date(t["published_at"]["value"])
    arch_d = ts_date(t["archived_at"]["value"])
    for name, days in PREDICTION_WINDOWS.items():
        key = f"in_window_{name}"
        if polling is None or avail["availability_status"] \
                == "not_temporally_usable":
            flags[key] = "not_usable"
        elif avail["availability_status"] == "availability_uncertain" \
                or pub_d is None:
            flags[key] = "excluded_uncertain"
        elif not (0 <= (polling - pub_d).days <= days):
            flags[key] = "no"
        elif arch_d is not None and arch_d <= polling:
            flags[key] = "yes_confirmed"
        else:
            flags[key] = "yes_publication_claim_only"
    return flags


# ------------------------------------------------------------- change

def _prep(ev: dict) -> dict:
    body = ev.get("body") or ""
    return {**ev, "body": body,
            "shingles": shingles(body),
            "words": len(body.split()),
            "title_tokens": informative_title_tokens(ev.get("title") or "")}


def paragraph_changes(paras_a: list[str], paras_b: list[str]) -> dict:
    """Paragraph-level additions, deletions and MODIFICATIONS.

    Exact matches (length floor applied) are common; the remainder are
    greedily paired by difflib ratio >= 0.6 as modified paragraphs;
    what is left is a pure addition or deletion. One sample of each is
    kept as auditable evidence of what changed."""
    a = sorted(p for p in paras_a if len(p) >= MIN_PARA_CHARS)
    b = sorted(p for p in paras_b if len(p) >= MIN_PARA_CHARS)
    common = set(a) & set(b)
    only_a = [p for p in a if p not in common]
    only_b = [p for p in b if p not in common]
    modified = 0
    mod_sample = ""
    used_b: set[int] = set()
    remaining_a = []
    for pa in only_a:
        best, best_r = None, 0.0
        for i, pb in enumerate(only_b):
            if i in used_b:
                continue
            r = difflib.SequenceMatcher(None, pa, pb).ratio()
            if r > best_r:
                best, best_r = i, r
        if best is not None and best_r >= MODIFIED_PARA_RATIO:
            used_b.add(best)
            modified += 1
            mod_sample = mod_sample or only_b[best][:120]
        else:
            remaining_a.append(pa)
    added = [pb for i, pb in enumerate(only_b) if i not in used_b]
    return {"paragraphs_added": len(added),
            "paragraphs_deleted": len(remaining_a),
            "paragraphs_modified": modified,
            "paragraphs_common": len(common),
            "added_sample": added[0][:120] if added else "",
            "deleted_sample": remaining_a[0][:120] if remaining_a else "",
            "modified_sample": mod_sample}


def content_changes(a: dict, b: dict) -> dict:
    """Descriptive change booleans the specification asks for -
    whether numbers, quoted statements, title or standfirst differ
    between the two versions. Descriptive ONLY: what changed is
    recorded, its political meaning is not judged here."""
    nums_a, nums_b = (set(_NUM.findall(a["body"])),
                      set(_NUM.findall(b["body"])))
    quotes_a, quotes_b = (set(_QUOTE.findall(a["body"])),
                          set(_QUOTE.findall(b["body"])))
    return {"title_changed": (a.get("title") or "") != (b.get("title") or ""),
            "standfirst_changed": (a.get("standfirst") or "")
            != (b.get("standfirst") or ""),
            "numbers_changed": nums_a != nums_b,
            "quotes_changed": quotes_a != quotes_b,
            "word_count_diff": len(b["body"].split())
            - len(a["body"].split())}


# ----------------------------------------------------- classification

def classify_version_pair(a: dict, b: dict) -> dict:
    """Classify one same-publisher candidate pair into exactly one
    relationship class, with full change and temporal evidence.

    ``a``/``b``: evidence dicts with article_id, source, title,
    standfirst, body, paragraphs, author, body_hash, canonical_url,
    original_url, election_id, pub_date, update_ts, capture_ts,
    retrieved_at."""
    a, b = _prep(a), _prep(b)
    s = pair_scores(a, b)
    diff = paragraph_changes(a["paragraphs"], b["paragraphs"])
    changes = content_changes(a, b)
    same_url = bool(a.get("canonical_url")) \
        and a.get("canonical_url") == b.get("canonical_url")
    identical = (a.get("body_hash")
                 and a.get("body_hash") == b.get("body_hash")) \
        or (s["jaccard"] >= 0.995 and s["seq_ratio"] >= 0.995)
    archive_current = same_url and \
        bool(a.get("capture_ts")) != bool(b.get("capture_ts"))
    changed = (diff["paragraphs_added"] + diff["paragraphs_deleted"]
               + diff["paragraphs_modified"])

    reason, confidence = "", "high"
    if not a["body"] or not b["body"]:
        cls, confidence = "manual_review", "none"
        reason = "a body is missing - cannot compare versions"
    elif identical:
        cls = "identical_recapture"
    elif archive_current and s["jaccard"] >= 0.70:
        cls = "archive_current_version"
    elif s["containment"] >= 0.85 and s["length_ratio"] <= 0.75:
        cls = "partial_to_full_version"
    elif s["jaccard"] >= 0.85 and changed <= 2 and s["title_sim"] >= 0.7:
        cls = "minor_update"
    elif s["jaccard"] >= 0.55:
        cls = "substantive_update"
    elif s["jaccard"] >= 0.30:
        cls, confidence = "ambiguous_version_relationship", "low"
        reason = "overlap between editing and separate-article grades"
    else:
        cls = "same_event_separate_article"

    # ---- chronology: published_at / updated_at ONLY -----------------
    # (retrieval and archive order say when we looked, not when the
    # newsroom wrote - the specification forbids them here)
    order, basis = "unordered", ""
    pa = a.get("update_ts") or a.get("pub_date") or ""
    pb = b.get("update_ts") or b.get("pub_date") or ""
    if cls in VERSION_CLASSES:
        if pa and pb and pa != pb:
            first, second = (a, b) if pa < pb else (b, a)
            order = f"{first['article_id']}->{second['article_id']}"
            basis = "publication_dates"
        else:
            reason = reason or ("version pair unordered - publication "
                                "dates equal or missing")

    av_a, av_b = availability(a), availability(b)
    return {"article_id_a": a["article_id"], "article_id_b": b["article_id"],
            "publisher": a["source"],
            "byline_match": bool(a.get("author"))
            and a.get("author") == b.get("author"),
            "original_url_a": a.get("original_url", ""),
            "original_url_b": b.get("original_url", ""),
            "canonical_url_a": a.get("canonical_url", ""),
            "canonical_url_b": b.get("canonical_url", ""),
            "same_canonical_url": same_url,
            "body_hash_a": a.get("body_hash", ""),
            "body_hash_b": b.get("body_hash", ""),
            "pub_date_a": a.get("pub_date", ""),
            "pub_date_b": b.get("pub_date", ""),
            "update_ts_a": a.get("update_ts", ""),
            "update_ts_b": b.get("update_ts", ""),
            "capture_a": a.get("capture_ts", ""),
            "capture_b": b.get("capture_ts", ""),
            "retrieved_a": a.get("retrieved_at", ""),
            "retrieved_b": b.get("retrieved_at", ""),
            "jaccard": s["jaccard"], "containment": s["containment"],
            "title_sim": s["title_sim"], "seq_ratio": s["seq_ratio"],
            "length_ratio": s["length_ratio"],
            **diff, **changes,
            "classification": cls, "relationship_confidence": confidence,
            "chronology": order, "chronology_basis": basis,
            "availability_status_a": av_a["availability_status"],
            "availability_status_b": av_b["availability_status"],
            "available_from_a": av_a["version_available_at"]
            or av_a["available_lower_bound"],
            "available_from_b": av_b["version_available_at"]
            or av_b["available_lower_bound"],
            "review_reason": reason, "rule_version": RULE_VERSION}


# ----------------------------------------------------------- families

def build_version_families(relationships: list[dict],
                           evidence: dict[str, dict]) -> list[dict]:
    """Union-find over version-grade relationships into families.

    ``evidence``: article_id -> the evidence dicts given to
    classify_version_pair. Family id VER-<sha12 of smallest member
    id> - stable under unrelated additions. version_sequence and
    predecessor/successor links exist only when every member has a
    usable publication/update timestamp and no two are equal; the
    resulting chain is linear by construction, so no circular version
    relationship can be produced. Anything less stays explicitly
    unordered and flagged."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in relationships:
        if r["classification"] in VERSION_CLASSES:
            ra, rb = find(r["article_id_a"]), find(r["article_id_b"])
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

    members: dict[str, list[str]] = defaultdict(list)
    for aid in parent:
        members[find(aid)].append(aid)

    families = []
    for root, ids in sorted(members.items()):
        if len(ids) < 2:
            continue
        mems = []
        for aid in sorted(ids):
            ev = evidence.get(aid, {})
            av = availability(ev)
            mems.append({"article_id": aid,
                         "pub_date": ev.get("pub_date", ""),
                         "update_ts": ev.get("update_ts", ""),
                         "capture_ts": ev.get("capture_ts", ""),
                         "retrieved_at": ev.get("retrieved_at", ""),
                         "body_hash": ev.get("body_hash", ""),
                         "canonical_url": ev.get("canonical_url", ""),
                         "availability_status": av["availability_status"],
                         "available_from": av["version_available_at"]
                         or av["available_lower_bound"],
                         "predecessor": None, "successor": None})
        keys = [m["update_ts"] or m["pub_date"] for m in mems]
        ordered = all(keys) and len(set(keys)) == len(keys)
        flags = []
        if ordered:
            chain = sorted(mems, key=lambda m: (m["update_ts"]
                                                or m["pub_date"],
                                                m["article_id"]))
            for n, m in enumerate(chain, start=1):
                m["version_sequence"] = n
                if n > 1:
                    m["predecessor"] = chain[n - 2]["article_id"]
                    chain[n - 2]["successor"] = m["article_id"]
        else:
            for m in mems:
                m["version_sequence"] = None
            flags.append("unordered_timestamps_insufficient")
        if any(m["availability_status"] != "confirmed_available_at"
               for m in mems):
            flags.append("availability_not_fully_confirmed")
        families.append({
            "family_id": "VER-" + hashlib.sha256(
                min(ids).encode()).hexdigest()[:12],
            "size": len(mems), "ordered": ordered,
            "order_basis": "publication_dates" if ordered else "",
            "members": mems, "flags": sorted(flags),
            "rule_version": RULE_VERSION})
    return families
