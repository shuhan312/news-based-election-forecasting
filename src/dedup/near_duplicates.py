"""Phase 5 / Step 3 - near-duplicate detection (pure logic; the
runner does the IO).

Contract: produce EVIDENCE-BASED candidate relationships, decide
nothing final. Nothing is deleted or merged; syndication and
updated-version adjudication belong to Step 4. The cardinal failure
mode this module is built against is FALSE MERGING of independent
reporting about the same political event - so classification rests
exclusively on overlapping TEXT (shared word sequences), never on
shared topic, names, election, location or date. Two reporters
covering the same count share vocabulary; they do not share
five-word sentences.

Candidate generation (deterministic blocking - no randomness, no
pair explosion):

    fingerprints   each body is shingled into 5-word windows; every
                   shingle is sha1-hashed and the numerically
                   smallest SKETCH_K hashes form the article's
                   sketch (a derandomised bottom-k MinHash). Articles
                   sharing >= SKETCH_SHARED sketch hashes become
                   candidates. Sharing k smallest hashes estimates
                   Jaccard overlap, and everything is a pure function
                   of the text.
    url_groups     members of the same Step 2 multi-member URL group
                   are always candidates (they claim to be one page).
    title_block    pairs sharing >= TITLE_BLOCK_TOKENS informative
                   title tokens are candidates - a cheap recall net
                   for retitled copies; NEVER duplicate evidence by
                   itself.

Similarity measures per candidate pair (all interpretable, all
recorded):

    jaccard       |shingles(A) & shingles(B)| / |A | B|   symmetric
    containment   |A & B| / min(|A|,|B|)   catches truncated copies
    title_sim     token Jaccard of titles
    seq_ratio     difflib ratio over the first 2,000 chars
    length_ratio  min(words)/max(words)

Classification thresholds (rule-versioned; every boundary chosen to
demand STRONG textual overlap before any automatic duplicate call):

    exact-duplicate pairs (Step 1)      excluded, reference retained
    either side < MIN_WORDS words       manual_review at most - short
                                        and snippet texts are never
                                        auto-classified
    jaccard >= 0.70                     high_confidence_near_duplicate
    containment >= 0.85 and
      length_ratio <= 0.75              partial_full_text_match
                                        (truncation/extension trail)
    jaccard >= 0.45                     probable_near_duplicate
    jaccard >= 0.25                     manual_review (grey zone)
    below, with title_sim >= 0.5        same_event_independent_reporting
    below, otherwise                    not_near_duplicate

Cross-publisher pairs at probable-or-above additionally carry the
possible_syndication_candidate flag - Step 4's inbox, not a verdict.

Provisional clusters: union-find over pairs classified probable or
stronger; cluster id NDC-<sha12 of the lexicographically smallest
member id>. Adding unrelated articles can never touch an existing
cluster; adding a member changes that cluster's membership by
definition, which is the intended semantics of "provisional".
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections import defaultdict

RULE_VERSION = "near-dup-v1.0-2026-07-26"

SHINGLE_W = 5
SKETCH_K = 64
SKETCH_SHARED = 6
TITLE_BLOCK_TOKENS = 4
MIN_WORDS = 80

STOP = frozenset("the a an of to in and for on with at by from as is "
                 "was are be has have had it its this that said".split())
TOKEN = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> list[str]:
    return TOKEN.findall((text or "").lower())


def shingles(text: str) -> set[int]:
    """5-word shingle hashes. sha1 (stable across runs and machines)
    truncated to 64 bits - collision odds are irrelevant at corpus
    scale and determinism is what matters."""
    toks = tokens(text)
    out = set()
    for i in range(len(toks) - SHINGLE_W + 1):
        sh = " ".join(toks[i:i + SHINGLE_W])
        out.add(int(hashlib.sha1(sh.encode()).hexdigest()[:16], 16))
    return out


def sketch(sh: set[int]) -> frozenset[int]:
    return frozenset(sorted(sh)[:SKETCH_K])


def informative_title_tokens(title: str) -> frozenset[str]:
    return frozenset(t for t in tokens(title)
                     if t not in STOP and len(t) > 2)


def pair_scores(a: dict, b: dict) -> dict:
    """All similarity measures for one candidate pair. ``a``/``b``
    carry precomputed shingle sets, tokens counts and titles."""
    sa, sb = a["shingles"], b["shingles"]
    inter = len(sa & sb)
    union = len(sa | sb) or 1
    smaller = min(len(sa), len(sb)) or 1
    ta, tb = a["title_tokens"], b["title_tokens"]
    t_union = len(ta | tb) or 1
    wa, wb = a["words"], b["words"]
    return {
        "jaccard": round(inter / union, 4),
        "containment": round(inter / smaller, 4),
        "title_sim": round(len(ta & tb) / t_union, 4),
        "seq_ratio": round(difflib.SequenceMatcher(
            None, a["body"][:2000], b["body"][:2000]).ratio(), 4),
        "length_ratio": round(min(wa, wb) / (max(wa, wb) or 1), 4),
        "shared_shingles": inter,
    }


def classify(scores: dict, a: dict, b: dict,
             exact_pair: bool) -> tuple[str, str]:
    """(classification, review_reason). Thresholds documented in the
    module docstring; text overlap is the only duplicate evidence."""
    if exact_pair:
        return "exact_duplicate_reference", "already confirmed in Step 1"
    if min(a["words"], b["words"]) < MIN_WORDS:
        if scores["containment"] >= 0.85:
            return "manual_review", ("short text with high containment - "
                                     "too little text for an automatic call")
        return "not_near_duplicate", ""
    j, c = scores["jaccard"], scores["containment"]
    # Containment first: a truncated/extended copy is a PARTIAL match
    # even when its jaccard is also high - the length ratio is what
    # distinguishes "same text cut down" from "same text lightly
    # edited", and the more specific relationship wins.
    if c >= 0.85 and scores["length_ratio"] <= 0.75:
        return "partial_full_text_match", ""
    if j >= 0.70:
        return "high_confidence_near_duplicate", ""
    if j >= 0.45:
        return "probable_near_duplicate", ""
    if j >= 0.25:
        return "manual_review", ("overlap in the grey zone between "
                                 "editing and independent reporting")
    if scores["title_sim"] >= 0.5:
        return "same_event_independent_reporting", ""
    return "not_near_duplicate", ""


DUP_CLASSES = {"high_confidence_near_duplicate",
               "probable_near_duplicate", "partial_full_text_match"}


def detect_near_duplicates(articles: list[dict],
                           exact_pairs: set[frozenset] | None = None,
                           url_group_pairs: set[frozenset] | None = None
                           ) -> dict:
    """Full pipeline over Phase-4 layer records.

    ``articles``: [{article_id, title, body_text, source_name}].
    ``exact_pairs``: Step 1 exact-duplicate pairs (excluded, kept as
    references). ``url_group_pairs``: Step 2 multi-member groups.
    Deterministic: sorted inputs, pure functions, stable ids.
    """
    exact_pairs = exact_pairs or set()
    url_group_pairs = url_group_pairs or set()

    prep = {}
    for a in articles:
        body = a.get("body_text") or ""
        sh = shingles(body)
        prep[a["article_id"]] = {
            "article_id": a["article_id"],
            "title": a.get("title") or "", "body": body,
            "source": a.get("source_name") or "",
            "words": len(body.split()),
            "shingles": sh, "sketch": sketch(sh),
            "title_tokens": informative_title_tokens(a.get("title") or ""),
        }

    # ---- blocking --------------------------------------------------
    cands: set[frozenset] = set(url_group_pairs)
    by_hash: dict[int, list[str]] = defaultdict(list)
    for aid in sorted(prep):
        for h in prep[aid]["sketch"]:
            by_hash[h].append(aid)
    shared: dict[frozenset, int] = defaultdict(int)
    for h, ids in by_hash.items():
        if 1 < len(ids) <= 50:          # ignore degenerate mega-buckets
            for i, x in enumerate(ids):
                for y in ids[i + 1:]:
                    shared[frozenset((x, y))] += 1
    cands |= {p for p, n in shared.items() if n >= SKETCH_SHARED}

    by_title_tok: dict[str, list[str]] = defaultdict(list)
    for aid in sorted(prep):
        for t in prep[aid]["title_tokens"]:
            by_title_tok[t].append(aid)
    t_shared: dict[frozenset, int] = defaultdict(int)
    for t, ids in by_title_tok.items():
        if 1 < len(ids) <= 30:
            for i, x in enumerate(ids):
                for y in ids[i + 1:]:
                    t_shared[frozenset((x, y))] += 1
    cands |= {p for p, n in t_shared.items() if n >= TITLE_BLOCK_TOKENS}

    # ---- score and classify ---------------------------------------
    pairs = []
    for pair in sorted(cands, key=sorted):
        x, y = sorted(pair)
        a, b = prep[x], prep[y]
        scores = pair_scores(a, b)
        cls, reason = classify(scores, a, b, pair in exact_pairs)
        flags = []
        if cls in DUP_CLASSES and a["source"] != b["source"]:
            flags.append("possible_syndication_candidate")
        if pair in url_group_pairs:
            flags.append("same_url_group")
        pairs.append({"article_id_a": x, "article_id_b": y,
                      "source_a": a["source"], "source_b": b["source"],
                      **scores, "classification": cls,
                      "review_reason": reason, "flags": sorted(flags),
                      "rule_version": RULE_VERSION})

    # ---- provisional clusters (union-find over dup-class pairs) ----
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        if p["classification"] in DUP_CLASSES:
            ra, rb = find(p["article_id_a"]), find(p["article_id_b"])
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

    members: dict[str, list[str]] = defaultdict(list)
    for aid in parent:
        members[find(aid)].append(aid)
    clusters = [{"cluster_id": "NDC-" + hashlib.sha256(
                    root.encode()).hexdigest()[:12],
                 "size": len(ms), "member_ids": sorted(ms)}
                for root, ms in sorted(members.items()) if len(ms) > 1]

    return {"pairs": pairs, "clusters": clusters,
            "rule_version": RULE_VERSION}
