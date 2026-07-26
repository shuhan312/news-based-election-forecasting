"""Phase 5 / Step 6 - duplicate-cluster validation (pure logic; the
runner does the IO).

Contract: integrate the evidence produced by Steps 1-5 into ONE typed
evidence graph, test every provisional connected component for
internal coherence, and prevent unsafe transitive merging - WITHOUT
deleting, merging or suppressing any record, without selecting
canonical articles and without touching Step 5's temporal decisions.

The cardinal failure mode is FALSE TRANSITIVITY: A resembles B and B
resembles C does not make A and C the same article. A middling
overlap chain can silently weld independent reporting into one
"article" and destroy the coverage counts downstream. The defences:

    typed edges     every relationship keeps its source step, class,
                    evidence, confidence and review status - nothing
                    is flattened into a generic "duplicate" link:
                        exact_duplicate      (Step 1)
                        same_canonical_url   (Step 2 multi-groups)
                        near_duplicate       (Step 3)
                        syndication          (Step 4)
                        version              (Step 5)
                        same_event_independent / rejected_or_ambiguous
                                             (non-linking evidence)
    edge-level conflict rules (deterministic, each application
    recorded as a conflict row):
        1. a human resolution or same-event/independent classification
           on a pair BLOCKS every merge-grade edge on that pair -
           independent-reporting evidence beats similarity;
        2. an exact-duplicate edge supersedes weaker near-duplicate
           labels on the same pair (recorded, not deleted);
        3. syndication edges live in their OWN layer: cross-publisher
           shared content never merges into a same-article family -
           an article may legitimately sit in one family of each kind;
        4. a same-canonical-URL edge with differing content hashes
           links only when a version-grade edge on the same pair
           confirms same-article identity, otherwise it goes to
           review ("same page" claims are not text evidence);
        5. snippet or not-usable records cannot carry near-duplicate
           or version links - a 40-word stub bridging two full
           articles is exactly the weak-bridge failure mode;
        6. anything ambiguous or unresolved stays non-linking and
           visible - never guessed.
    component checks  after union-find over the SURVIVING linking
                      edges, every member pair of a component must be
                      supported: a direct linking edge, or textual
                      overlap (best recorded jaccard/containment
                      >= 0.25) on some recorded edge. Chains whose
                      endpoints share nothing are flagged as
                      unsupported bridges and the family goes to
                      review, not into the validated set. A blocking
                      edge BETWEEN members of one component is a
                      contradiction -> ambiguous_family, review.
    temporal safety   member availability records from Step 5 are
                      copied through verbatim - validation never
                      rewrites availability, never substitutes later
                      text, and flags families whose members have
                      different availability so downstream cannot
                      collapse them into one time point.

Family ids: VAL-<sha12 of the sorted member list> - stable under
rerun, input reordering and unrelated additions; any change of
membership changes the id, so a materially changed cluster can never
silently reuse an old one.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

RULE_VERSION = "cluster-validation-v1.0-2026-07-26"

SUPPORT_MIN_OVERLAP = 0.25   # weakest textual overlap accepted as
                             # pair support inside a component
SNIPPET_MAX_WORDS = 80       # below this a record cannot bridge

# classifications that make an edge merge-grade, per edge type
LINK_GRADE = {
    "exact_duplicate": {"exact_duplicate"},
    "near_duplicate": {"high_confidence_near_duplicate",
                       "probable_near_duplicate",
                       "partial_full_text_match"},
    "version": {"identical_recapture", "minor_update",
                "substantive_update", "partial_to_full_version",
                "archive_current_version"},
    "syndication": {"confirmed_syndicated_copy",
                    "probable_syndicated_copy",
                    "shared_wire_or_press_release",
                    "same_publisher_network_republication"},
    "same_canonical_url": {"url_variant_probable_same_page",
                           "url_variant_same_page"},
}

# classifications that positively assert "NOT the same article"
BLOCKING = {"same_event_independent_reporting",
            "independent_reporting_same_event",
            "same_event_separate_article", "not_near_duplicate"}


def _pair(e: dict) -> frozenset:
    return frozenset((e["a"], e["b"]))


def _is_snippet(info: dict) -> bool:
    return (info.get("words", 0) < SNIPPET_MAX_WORDS
            or info.get("quality") == "not_usable")


def _family_id(members: set[str]) -> str:
    return "VAL-" + hashlib.sha256(
        ",".join(sorted(members)).encode()).hexdigest()[:12]


def _overlap(e: dict) -> float:
    ev = e.get("evidence") or {}
    return max(float(ev.get("jaccard") or 0),
               float(ev.get("containment") or 0))


def apply_conflict_rules(articles: dict[str, dict],
                         edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Annotate every edge with its disposition (linking / blocked /
    non_linking) and record every conflict-rule application. No edge
    is ever dropped - a blocked edge stays in the output with its
    blocking reason, which is the auditable answer to 'why are these
    two articles NOT one family'."""
    conflicts: list[dict] = []
    by_pair: dict[frozenset, list[dict]] = defaultdict(list)
    for e in edges:
        by_pair[_pair(e)].append(e)

    def conflict(e, rule, resolution):
        conflicts.append({"article_id_a": min(e["a"], e["b"]),
                          "article_id_b": max(e["a"], e["b"]),
                          "edge_type": e["edge_type"],
                          "classification": e["classification"],
                          "rule": rule, "resolution": resolution,
                          "rule_version": RULE_VERSION})

    for pair, pes in by_pair.items():
        blocked = [e for e in pes
                   if e["classification"] in BLOCKING
                   or (e.get("review_status") or "").startswith(
                       "human_resolved")
                   and e.get("human_decision", "") in BLOCKING]
        has_exact = any(e["edge_type"] == "exact_duplicate"
                        and e["classification"]
                        in LINK_GRADE["exact_duplicate"] for e in pes)
        has_version = any(e["edge_type"] == "version"
                          and e["classification"]
                          in LINK_GRADE["version"] for e in pes)
        for e in pes:
            grade = e["classification"] in LINK_GRADE.get(e["edge_type"],
                                                          set())
            if not grade:
                e["disposition"] = "non_linking"
                continue
            # rule 1 - independent/separate evidence blocks the merge
            if blocked and e["edge_type"] != "exact_duplicate":
                e["disposition"] = "blocked"
                e["block_reason"] = "independent_decision_blocks_merge"
                conflict(e, "independent_reporting_blocks_merge",
                         "edge blocked; pair stays unmerged")
                continue
            # rule 2 - exact supersedes weaker labels (kept, annotated)
            if has_exact and e["edge_type"] == "near_duplicate":
                e["disposition"] = "superseded"
                e["block_reason"] = "superseded_by_exact_duplicate"
                conflict(e, "exact_overrides_near_duplicate",
                         "near-duplicate label superseded, pair still "
                         "linked via the exact edge")
                continue
            # rule 4 - same URL + different hashes needs version proof
            if e["edge_type"] == "same_canonical_url" and not has_version:
                e["disposition"] = "blocked"
                e["block_reason"] = "same_url_requires_version_evidence"
                conflict(e, "same_url_changed_content_needs_version",
                         "URL edge sent to review, no automatic link")
                continue
            # rule 5 - snippet records cannot carry text-based links
            if e["edge_type"] in ("near_duplicate", "version") and (
                    _is_snippet(articles.get(e["a"], {}))
                    or _is_snippet(articles.get(e["b"], {}))):
                e["disposition"] = "blocked"
                e["block_reason"] = "snippet_bridge_blocked"
                conflict(e, "snippet_cannot_bridge",
                         "edge blocked; too little text to merge on")
                continue
            e["disposition"] = "linking"
    return edges, conflicts


def validate_graph(articles: dict[str, dict],
                   edges: list[dict]) -> dict:
    """Full Step 6 validation.

    ``articles``: article_id -> {words, quality, pub_date,
    availability_status, available_from} (temporal fields verbatim
    from Step 5 - copied through, never altered).
    ``edges``: typed relationship dicts with a, b, edge_type,
    classification, source_step, confidence, evidence, review_status.

    Returns annotated relationships, validated families per layer
    (same-article vs syndication), conflicts, and one explicit status
    per article."""
    edges, conflicts = apply_conflict_rules(articles, edges)

    def components(kinds: set[str]) -> dict[str, set[str]]:
        parent: dict[str, str] = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for e in sorted(edges, key=lambda e: sorted(_pair(e))):
            if e["disposition"] == "linking" and e["edge_type"] in kinds:
                ra, rb = find(e["a"]), find(e["b"])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
        comps: dict[str, set[str]] = defaultdict(set)
        for aid in parent:
            comps[find(aid)].add(aid)
        return {r: m for r, m in comps.items() if len(m) > 1}

    # syndication is its OWN layer (rule 3): cross-publisher shared
    # content never merges into a same-article family
    same_article_comps = components({"exact_duplicate", "near_duplicate",
                                     "version", "same_canonical_url"})
    syn_comps = components({"syndication"})

    by_pair: dict[frozenset, list[dict]] = defaultdict(list)
    for e in edges:
        by_pair[_pair(e)].append(e)

    families = []

    def build_family(members: set[str], layer: str) -> dict:
        ms = sorted(members)
        inner = [e for e in edges if e["a"] in members
                 and e["b"] in members]
        linked_pairs = {_pair(e) for e in inner
                        if e["disposition"] in ("linking", "superseded")}
        # ---- pairwise support: catch false-transitivity chains ------
        unsupported = []
        min_support = 1.0
        for i, x in enumerate(ms):
            for y in ms[i + 1:]:
                pair = frozenset((x, y))
                best = max((_overlap(e) for e in by_pair.get(pair, [])),
                           default=0.0)
                if pair in linked_pairs:
                    best = max(best, SUPPORT_MIN_OVERLAP)
                min_support = min(min_support, best)
                if best < SUPPORT_MIN_OVERLAP:
                    unsupported.append(f"{x}|{y}")
        # ---- contradictions: blocking evidence INSIDE the family ----
        contradictions = sorted(
            "|".join(sorted(_pair(e))) for e in inner
            if e["classification"] in BLOCKING
            or e.get("block_reason") == "independent_decision_blocks_merge")
        # ---- family type from the surviving linking edge types ------
        link_types = {e["edge_type"] for e in inner
                      if e["disposition"] == "linking"}
        if layer == "syndication":
            classes = {e["classification"] for e in inner
                       if e["disposition"] == "linking"}
            ftype = ("shared_press_release_family"
                     if classes == {"shared_wire_or_press_release"}
                     else "syndication_family")
        elif contradictions:
            ftype = "ambiguous_family"
        elif "exact_duplicate" in link_types:
            ftype = "exact_duplicate_family"
        else:
            # several edge types on the SAME pair corroborate each
            # other (a Step 3 near-duplicate edge plus a Step 5
            # version edge is one well-evidenced relationship, not a
            # mixed structure); "mixed" means different pairs are held
            # together by different relationship kinds
            ver_pairs = {_pair(e) for e in inner
                         if e["disposition"] == "linking"
                         and e["edge_type"] == "version"}
            if "version" in link_types and all(
                    _pair(e) in ver_pairs for e in inner
                    if e["disposition"] == "linking"
                    and e["edge_type"] in ("near_duplicate",
                                           "same_canonical_url")):
                ftype = "same_article_version_family"
            elif link_types == {"near_duplicate"}:
                ftype = "near_duplicate_family"
            else:
                ftype = "mixed_relationship_family"
        # ---- temporal safety: copy Step 5's decisions verbatim ------
        member_records = []
        avail_values = set()
        for aid in ms:
            info = articles.get(aid, {})
            member_records.append(
                {"article_id": aid,
                 "availability_status": info.get("availability_status", ""),
                 "available_from": info.get("available_from", "")})
            avail_values.add(info.get("available_from", ""))
        warnings = []
        if len(avail_values) > 1:
            warnings.append("members_have_different_temporal_availability")
        if unsupported:
            warnings.append("unsupported_transitive_bridge")
        if contradictions:
            warnings.append("contradictory_relationship_classes")
        status = ("review" if unsupported or contradictions
                  else "validated_retained")
        return {"family_id": _family_id(members), "layer": layer,
                "family_type": ftype, "size": len(ms), "members": ms,
                "member_temporal": member_records,
                "validation_status": status,
                "decision": "retained" if status == "validated_retained"
                else "sent_to_review",
                "min_pairwise_support": round(min_support, 4),
                "unsupported_pairs": unsupported,
                "contradictions": contradictions,
                "temporal_safety": "preserved",
                "warnings": sorted(warnings),
                "rule_version": RULE_VERSION}

    for members in sorted(same_article_comps.values(), key=sorted):
        families.append(build_family(members, "same_article"))
    for members in sorted(syn_comps.values(), key=sorted):
        families.append(build_family(members, "syndication"))

    # ---- one explicit status per article (nothing unaccounted) ------
    membership: dict[str, list[str]] = defaultdict(list)
    for f in families:
        for aid in f["members"]:
            membership[aid].append(f["family_id"])
    article_status = {
        aid: {"families": sorted(membership.get(aid, [])),
              "status": "in_validated_family" if membership.get(aid)
              else "independent_article"}
        for aid in articles}

    return {"relationships": edges, "families": families,
            "conflicts": conflicts, "article_status": article_status,
            "rule_version": RULE_VERSION}
