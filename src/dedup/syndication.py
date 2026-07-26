"""Phase 5 / Step 4 - syndicated-copy identification (pure logic;
the runner does the IO).

Contract: classify CROSS-PUBLISHER shared-content relationships with
multiple named evidence types, decide direction only on strong
evidence, delete nothing. Same-publisher duplicate pairs (double
captures, revision trails) are deliberately OUT of scope - they are
Step 5's updated-version inbox, and touching them here would blur two
different questions.

Evidence types, each computed and recorded separately so the
classification is an argument, not a verdict from a black box:

    text        jaccard/containment carried over from Step 3 - the
                strength of the overlap.
    paragraphs  identical full paragraphs (>= 40 chars) shared by the
                two bodies - wholesale reuse leaves whole paragraphs
                intact, while independent reporting shares at most a
                quoted sentence.
    attribution regex scan of both bodies for explicit reuse markers:
                agency credits (PA Media / Press Association /
                Reuters / AFP), "this article (was) (originally)
                (published|appeared)", "courtesy of", "reproduced
                with permission", "press release". A marker is
                EVIDENCE, never proof by itself.
    byline      identical non-empty author strings across different
                publishers - typical of wire copy.
    chronology  publication dates (upstream effective dates) and
                capture timestamps. Chronology NEVER assigns
                direction alone: the earliest capture is not
                necessarily the original (specification boundary).

Classification (cross-publisher pairs only; thresholds versioned):

    wholesale text reuse (jaccard >= 0.70 or containment >= 0.85):
        with an explicit attribution marker  -> confirmed_syndicated_copy
        with a matching byline               -> probable_syndicated_copy
        otherwise                            -> probable_syndicated_copy
    partial overlap (>= 2 shared paragraphs, jaccard < 0.45):
        with a wire/release marker or byline -> shared_wire_or_press_release
        otherwise                            -> manual_review (could be
                                                heavy quotation)
    same declared publisher network          -> same_publisher_network_
                                                republication (the network
                                                map is empty for this
                                                corpus and documented)
    low overlap (jaccard < 0.25, no shared paragraphs)
                                             -> independent_reporting_
                                                same_event
    missing bodies/dates                     -> insufficient_evidence
    anything else                            -> manual_review

Direction: assigned ONLY when (a) one body carries an attribution
marker naming the other publisher or an agency AND (b) the
publication dates are consistent with that reading (copy not earlier
than source by more than one day). Everything else is recorded as an
undirected shared-content relationship - saying "these share text"
without pretending to know who copied whom.

Family ids: SYN-<sha12 of the lexicographically smallest member id>
over the union of confirmed/probable/wire relationships. Step 1-3
cluster ids are never altered.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict

RULE_VERSION = "syndication-v1.0-2026-07-26"

# Publisher networks that share content by arrangement. None are
# declared for this corpus - the mechanism exists so a future tranche
# can add one without a rule change.
PUBLISHER_NETWORKS: dict[str, str] = {}

ATTRIBUTION = re.compile(
    r"(pa media|press association|reuters|afp|agence france"
    r"|this article (was )?(originally )?(published|appeared)"
    r"|courtesy of|reproduced with permission|republished from"
    r"|press release)", re.I)

MIN_SHARED_PARA_CHARS = 40


def shared_paragraphs(paras_a: list[str], paras_b: list[str]) -> list[str]:
    """Identical full paragraphs above the length floor - the
    footprint of wholesale reuse."""
    a = {p for p in paras_a if len(p) >= MIN_SHARED_PARA_CHARS}
    return sorted(p for p in paras_b
                  if len(p) >= MIN_SHARED_PARA_CHARS and p in a)


def attribution_markers(body: str) -> list[str]:
    return sorted({m.group(0).lower()
                   for m in ATTRIBUTION.finditer(body or "")})


def classify_pair(pair: dict, a: dict, b: dict) -> dict:
    """Classify one cross-publisher pair.

    ``pair``: Step 3 scores (jaccard, containment...). ``a``/``b``:
    per-article evidence dicts (source, body, paragraphs, author,
    pub_date, capture_ts). Returns the full relationship record."""
    j = float(pair.get("jaccard") or 0)
    c = float(pair.get("containment") or 0)
    shared = shared_paragraphs(a["paragraphs"], b["paragraphs"])
    marks_a, marks_b = (attribution_markers(a["body"]),
                        attribution_markers(b["body"]))
    byline_match = bool(a["author"]) and a["author"] == b["author"]

    same_network = (PUBLISHER_NETWORKS.get(a["source"])
                    and PUBLISHER_NETWORKS.get(a["source"])
                    == PUBLISHER_NETWORKS.get(b["source"]))

    evidence = {"jaccard": j, "containment": c,
                "shared_paragraphs": len(shared),
                "shared_paragraph_sample": shared[0][:120] if shared else "",
                "attribution_a": ";".join(marks_a),
                "attribution_b": ";".join(marks_b),
                "byline_match": byline_match}

    reason = ""
    if not a["body"] or not b["body"]:
        cls = "insufficient_evidence"
        reason = "a body is missing"
    elif same_network:
        cls = "same_publisher_network_republication"
    elif j >= 0.70 or c >= 0.85:
        if marks_a or marks_b:
            cls = "confirmed_syndicated_copy"
        else:
            cls = "probable_syndicated_copy"
            reason = "wholesale overlap without explicit attribution"
    elif len(shared) >= 2 and j < 0.45:
        if marks_a or marks_b or byline_match:
            cls = "shared_wire_or_press_release"
        else:
            cls = "manual_review"
            reason = ("blocks of identical paragraphs without wire "
                      "markers - heavy quotation or hidden reuse")
    elif j < 0.25 and not shared:
        cls = "independent_reporting_same_event"
    else:
        cls = "manual_review"
        reason = "overlap pattern fits no rule cleanly"

    # ---- direction: attribution + consistent chronology only --------
    direction, d_conf = "undirected", ""
    if cls in ("confirmed_syndicated_copy", "shared_wire_or_press_release"):
        for src, dst, marks in ((a, b, marks_b), (b, a, marks_a)):
            # dst carries the marker -> dst is the reuser, src the origin
            if marks and src["pub_date"] and dst["pub_date"] \
                    and dst["pub_date"] >= src["pub_date"]:
                direction = f"{src['article_id']}->{dst['article_id']}"
                d_conf = "attribution_plus_chronology"
                break

    return {"article_id_a": a["article_id"], "article_id_b": b["article_id"],
            "publisher_a": a["source"], "publisher_b": b["source"],
            "pub_date_a": a["pub_date"], "pub_date_b": b["pub_date"],
            "capture_a": a["capture_ts"], "capture_b": b["capture_ts"],
            **evidence, "classification": cls,
            "direction": direction, "direction_confidence": d_conf,
            "review_reason": reason, "rule_version": RULE_VERSION}


FAMILY_CLASSES = {"confirmed_syndicated_copy", "probable_syndicated_copy",
                  "shared_wire_or_press_release",
                  "same_publisher_network_republication"}


def build_families(relationships: list[dict]) -> list[dict]:
    """Union-find over syndication-grade relationships; family ids
    derive from the smallest member id, leaving Step 1-3 ids alone."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in relationships:
        if r["classification"] in FAMILY_CLASSES:
            ra, rb = find(r["article_id_a"]), find(r["article_id_b"])
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    members: dict[str, list[str]] = defaultdict(list)
    for aid in parent:
        members[find(aid)].append(aid)
    return [{"family_id": "SYN-" + hashlib.sha256(
                 root.encode()).hexdigest()[:12],
             "size": len(ms), "member_ids": sorted(ms)}
            for root, ms in sorted(members.items()) if len(ms) > 1]
