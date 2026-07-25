"""Phase 5 / Step 1 - exact content duplicate detection (pure logic;
the runner does the IO).

Contract: DETECT relationships, decide nothing. Every article keeps
its identity and provenance; the output says only "these records
carry byte-identical normalised text". Deletion, merging, canonical
selection and anything fuzzy (near-duplicates, syndication chains,
URL reasoning) belong to later steps and are structurally absent
here.

Hashes (all sha256 over the Phase 4 normalised fields, so "exact"
means exact AFTER the audited cleaning pipeline - punctuation,
casing and whitespace differences were already canonicalised):

    title_hash       normalised title
    standfirst_hash  normalised standfirst (empty upstream, kept for
                     schema completeness)
    body_hash        normalised body_text - THE clustering key
    composite_hash   the documented downstream composition
                     (title+standfirst+body), recorded so later steps
                     can distinguish "same body, different headline"
                     from "same everything"

Clustering rules (conservative, per specification):

    * Only articles whose downstream status is ready_full_text or
      ready_partial_text AND whose body is non-empty participate in
      clustering. Strong evidence = matching non-empty body_hash.
    * snippet_only / not_usable / empty bodies NEVER cluster - a
      shared emptiness is not a shared article. They are mapped with
      an explicit not_clustered_* status instead.
    * Title equality alone is never duplicate evidence; it only
      raises a flag (same_title_different_body) for later steps.

Cluster identity: EXD-<first 12 hex of body_hash>. Because the ID is
a pure function of content, adding new articles in a future release
can create new clusters or ENLARGE an existing one, but can never
rename a cluster whose members did not change - the incremental-
stability requirement holds by construction, not by bookkeeping.

Flags raised (evidence for later steps / human eyes, never acted on
here):

    same_body_different_title   one cluster, >1 distinct titles
                                (classic syndication smell)
    same_title_different_body   same title across different bodies
                                (updated-version smell)
    snippet_match_ignored       snippet-only records sharing a hash -
                                recorded, deliberately not clustered
    duplicate_article_id        input integrity violation (should be
                                impossible; loud if it happens)
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

RULE_VERSION = "exact-dup-v1.0-2026-07-27"

CLUSTERABLE = {"ready_full_text", "ready_partial_text"}


def sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def article_hashes(article: dict) -> dict:
    """The four deterministic hashes for one Phase 4 layer record."""
    title = article.get("title") or ""
    standfirst = article.get("standfirst") or ""
    body = article.get("body_text") or ""
    composite = "\n\n".join(p for p in (title, standfirst, body) if p)
    return {"title_hash": sha256(title) if title else "",
            "standfirst_hash": sha256(standfirst) if standfirst else "",
            "body_hash": sha256(body) if body.strip() else "",
            "composite_hash": sha256(composite) if composite else ""}


def detect_exact_duplicates(articles: list[dict]) -> dict:
    """Map every article to exactly one duplicate-status record.

    Input: Phase 4 layer records (article_id, title, standfirst,
    body_text, downstream_status). Output: {"mapping": [...],
    "clusters": [...]} - both deterministically ordered by
    article_id / cluster_id. Pure function: same input, same output.
    """
    seen_ids: set[str] = set()
    rows = []
    by_body: dict[str, list[dict]] = defaultdict(list)
    by_title: dict[str, set[str]] = defaultdict(set)  # title_hash -> body hashes

    for art in sorted(articles, key=lambda a: a["article_id"]):
        aid = art["article_id"]
        flags = []
        if aid in seen_ids:
            flags.append("duplicate_article_id")
        seen_ids.add(aid)

        h = article_hashes(art)
        ds = art.get("downstream_status", "")
        clusterable = ds in CLUSTERABLE and bool(h["body_hash"])

        row = {"article_id": aid, "downstream_status": ds,
               "quality_status": art.get("quality_status", ""),
               **h, "clusterable": clusterable, "flags": flags}
        rows.append(row)
        if clusterable:
            by_body[h["body_hash"]].append(row)
            if h["title_hash"]:
                by_title[h["title_hash"]].add(h["body_hash"])

    # ---- clusters from shared non-empty body hashes ------------------
    clusters = []
    for body_hash, members in by_body.items():
        if len(members) < 2:
            members[0]["exact_duplicate_status"] = "unique"
            members[0]["cluster_id"] = ""
            members[0]["cluster_size"] = 1
            continue
        cid = "EXD-" + body_hash[:12]
        titles = {m["title_hash"] for m in members}
        for m in sorted(members, key=lambda r: r["article_id"]):
            m["exact_duplicate_status"] = "exact_duplicate"
            m["cluster_id"] = cid
            m["cluster_size"] = len(members)
            if len(titles) > 1:
                m["flags"].append("same_body_different_title")
        clusters.append({
            "cluster_id": cid, "size": len(members),
            "evidence": "identical non-empty normalised body_hash",
            "member_ids": sorted(m["article_id"] for m in members),
            "distinct_titles": len(titles)})

    # ---- non-clusterable statuses (explicit, never grouped) ----------
    for r in rows:
        if "exact_duplicate_status" not in r:
            if not r["clusterable"]:
                r["exact_duplicate_status"] = (
                    "not_clustered_unusable" if not r["body_hash"]
                    or r["downstream_status"]
                    == "not_usable_for_text_analysis"
                    else "not_clustered_restricted")
                r["cluster_id"], r["cluster_size"] = "", 0
            else:  # clusterable single already handled above
                r["exact_duplicate_status"] = "unique"
                r["cluster_id"], r["cluster_size"] = "", 1

    # ---- title-collision flag (never duplicate evidence) -------------
    for r in rows:
        if r["clusterable"] and r["title_hash"] and \
                len(by_title.get(r["title_hash"], set())) > 1:
            r["flags"].append("same_title_different_body")
    for r in rows:
        r["flags"] = sorted(set(r["flags"]))

    clusters.sort(key=lambda c: c["cluster_id"])
    return {"mapping": rows, "clusters": clusters,
            "rule_version": RULE_VERSION}
