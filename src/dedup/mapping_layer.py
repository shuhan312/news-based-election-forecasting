"""Phase 5 / Step 8 - duplicate mapping layer, provisional freeze
(pure logic; the runner does the IO).

Contract: consolidate Steps 1-7 into ONE per-article mapping table
that downstream LLM extraction reads directly, freeze it as a
versioned provisional snapshot, and delete nothing. This is not itself a
canonical corpus release. At the snapshot date, Stage M retrieval was still
running, so the layer was stamped v1_provisional. The later canonical corpus
releases pin this snapshot without overwriting it.

Design decisions:

    one row per article   the layer answers, for any article id, the
                          only questions downstream cares about: is
                          this record the one to extract from, who is
                          its canonical, what relationship put it
                          there, and can its text be trusted in a
                          pre-election window.
    types stay separate   relationship_status, family_type,
                          syndication_status and version_status are
                          FOUR columns, not one collapsed label -
                          exact duplicates, syndicated copies and
                          updated versions are different phenomena
                          with different downstream meaning.
    provenance intact     each row carries the originating steps, the
                          family id as the evidence key into the
                          Step 6 cluster file, the strongest recorded
                          similarity, the Step 7 selection evidence
                          string, availability timestamps and the
                          composite rule versions. The pairwise
                          evidence itself lives in the Step 1-7
                          outputs, which this layer references and
                          never rewrites.
    freeze guard          the runner refuses to overwrite an existing
                          snapshot whose bytes differ (rerunning an
                          identical build is fine; changing history
                          silently is not). A changed corpus means a
                          NEW version, not a rewritten old one.

relationship_status vocabulary (exactly one per article):

    canonical_article                    family member chosen in Step 7
    exact_duplicate                      non-canonical, exact family
    near_duplicate                       non-canonical, near-dup family
    syndicated_copy                      non-canonical, syndication fam.
    archive_version                      non-canonical version member
                                         that is a same-URL archive
                                         re-capture
    updated_version                      other non-canonical version
                                         member
    manual_review                        family held by Step 7
    non_duplicate_independent_article    everyone else

downstream_usage_status: use_as_canonical_input (canonicals and
independents), retain_as_evidence_only (non-canonical family
members - kept, auditable, never counted), manual_review_required
(held families - never silently included or excluded).
"""

from __future__ import annotations

from pathlib import Path

RULE_VERSION = "dup-mapping-v1.0-2026-07-26"

# the freeze is dated by the corpus snapshot, never by the wall
# clock - reruns must be byte-identical (Phase 4 Step 7 lesson)
SNAPSHOT_DATE = "2026-07-26"

FAMILY_STATUS = {"exact_duplicate_family": "exact_duplicate",
                 "near_duplicate_family": "near_duplicate",
                 "syndication_family": "syndicated_copy",
                 "shared_press_release_family": "syndicated_copy"}


def relationship_status(ctx: dict) -> str:
    """Derive the single relationship_status for one article.

    ``ctx``: {in_family, family_type, is_canonical, held,
    same_url_archive} - precomputed by the caller from the Step 6/7
    outputs. The order matters: review beats everything (uncertainty
    is never silently classified), canonical beats duplicate."""
    if not ctx.get("in_family"):
        return "non_duplicate_independent_article"
    if ctx.get("held"):
        return "manual_review"
    if ctx.get("is_canonical"):
        return "canonical_article"
    if ctx["family_type"] in FAMILY_STATUS:
        return FAMILY_STATUS[ctx["family_type"]]
    # same-article version family, non-canonical member
    if ctx.get("same_url_archive"):
        return "archive_version"
    return "updated_version"


def downstream_usage(status: str) -> str:
    """Map relationship_status to the downstream gate. Only canonical
    records and independents enter default LLM extraction; duplicates
    stay auditable; review cases block loudly."""
    if status in ("canonical_article",
                  "non_duplicate_independent_article"):
        return "use_as_canonical_input"
    if status == "manual_review":
        return "manual_review_required"
    return "retain_as_evidence_only"


def build_row(aid: str, ctx: dict) -> dict:
    """One mapping row. ``ctx`` additionally carries family_id,
    canonical_article_id, canonical_status, syndication_status,
    version_status, temporal_validity_status, originating_steps,
    best_similarity, selection_evidence, available_from,
    review_flags, input_refs."""
    status = relationship_status(ctx)
    canonical = ctx.get("canonical_article_id") or aid
    return {"article_id": aid,
            "canonical_article_id": canonical,
            "duplicate_family_id": ctx.get("family_id", ""),
            "relationship_status": status,
            "family_type": ctx.get("family_type",
                                   "independent_articles"),
            "canonical_status": ctx.get("canonical_status",
                                        "no_canonical_required_"
                                        "independent_articles"),
            "syndication_status": ctx.get("syndication_status",
                                          "not_syndicated"),
            "version_status": ctx.get("version_status",
                                      "single_version"),
            "source_article_id": canonical if canonical != aid else "",
            "temporal_validity_status": ctx.get(
                "temporal_validity_status", ""),
            "downstream_usage_status": downstream_usage(status),
            "review_status": "review_required"
            if status == "manual_review" else "clear",
            "originating_steps": ctx.get("originating_steps", ""),
            "evidence_ref": ctx.get("family_id", "")
            or "no_family_relationships",
            "best_similarity": ctx.get("best_similarity", ""),
            "selection_evidence": ctx.get("selection_evidence", ""),
            "available_from": ctx.get("available_from", ""),
            "review_flags": ctx.get("review_flags", ""),
            "rule_version": RULE_VERSION,
            "input_refs": ctx.get("input_refs", "")}


def validate_mapping(rows: list[dict],
                     expected_articles: set[str]) -> None:
    """Integrity gates, all hard failures:

    * exactly one row per current article, none missing, none extra;
    * every canonical id resolves to a row whose own canonical is
      itself (no dangling references, no circular chains);
    * review rows are never marked usable."""
    ids = [r["article_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate mapping rows"
    assert set(ids) == expected_articles, \
        "mapping must cover every article exactly once"
    by_id = {r["article_id"]: r for r in rows}
    for r in rows:
        canon = by_id.get(r["canonical_article_id"])
        assert canon is not None, \
            f"dangling canonical {r['canonical_article_id']}"
        if r["relationship_status"] != "manual_review":
            assert canon["canonical_article_id"] \
                == canon["article_id"], \
                f"circular/chained canonical via {r['article_id']}"
        if r["relationship_status"] == "manual_review":
            assert r["downstream_usage_status"] \
                == "manual_review_required"


def freeze_write(path: Path, content: str, force: bool = False) -> str:
    """Versioned-freeze write guard. Writing identical bytes is a
    no-op (idempotent rerun); writing DIFFERENT bytes over an
    existing snapshot is refused - history changes require a new
    version, never a silent rewrite. Returns 'unchanged', 'written'
    or raises."""
    if path.exists():
        if path.read_bytes() == content.encode():
            return "unchanged"
        if not force:
            raise RuntimeError(
                f"freeze guard: {path} already exists with different "
                "content - the corpus changed, so release a new "
                "version instead of overwriting the snapshot")
    path.write_text(content)
    return "written"
