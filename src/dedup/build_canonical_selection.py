"""Phase 5 / Step 7 runner: canonical article selection over the
validated Step 6 families.

Per-member evidence assembly (all read-only):

    full_text / clean       Phase 4 layer quality_status and flags
    pub_date_usable         Step 5 availability table (published_at)
    stable_url              Step 2 canonical URL present
    temporal_confirmed      archived_at exists and its UTC date is on
                            or before the article's election polling
                            day (protocol ELECTIONS table) - the
                            pre-election archive pin
    available_from          Step 5 version_available_at / lower bound
    is_origin               Step 4 directed syndication links (none
                            exist in this corpus; the rule is live
                            for future tranches)

Outputs (versioned _v1_provisional, all tracked):

    news_collection/canonical_article_mapping_v1_provisional.csv
        one row per Phase 4 article (1:1 with the layer) - the
        downstream lookup: which record to extract from, which to
        keep but not count
    news_collection/canonical_selection_report_v1_provisional.md
    news_collection/canonical_review_queue_v1_provisional.csv

Usage:
    python3 -m src.dedup.build_canonical_selection
"""

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from .canonical_selection import RULE_VERSION, select_canonical
from ..news_collection.resolve_publication_dates import ELECTIONS

LAYER = Path("news_collection/normalised_text_layer_v1_provisional.jsonl")
CLUSTERS = Path(
    "news_collection/validated_duplicate_clusters_v1_provisional.jsonl")
VER_REL = Path(
    "news_collection/article_version_relationships_v1_provisional.csv")
SYN = Path("news_collection/syndication_relationships_v1_provisional.csv")
URL_MAP = Path("news_collection/url_duplicate_mapping_v1_provisional.csv")
AVAIL = Path("news_collection/"
             "article_version_temporal_availability_v1_provisional.csv")

OUT_MAP = Path(
    "news_collection/canonical_article_mapping_v1_provisional.csv")
OUT_MD = Path(
    "news_collection/canonical_selection_report_v1_provisional.md")
OUT_REVIEW = Path(
    "news_collection/canonical_review_queue_v1_provisional.csv")

INPUT_REFS = ("layer=normalised-text-v1_provisional;"
              "clusters=cluster-validation-v1.0-2026-07-26;"
              "version=version-link-v1.0-2026-07-26;"
              "availability=version-link-v1.0-2026-07-26;"
              "syndication=syndication-v1.0-2026-07-26")

MAP_FIELDS = ["article_id", "family_id", "family_type",
              "canonical_article_id", "canonical_status",
              "selection_reason", "selection_evidence",
              "temporal_validity_status", "downstream_usage",
              "review_required", "rule_version", "input_refs"]


def main() -> None:
    arts = {}
    for line in LAYER.open():
        a = json.loads(line)
        arts[a["article_id"]] = a
    avail = {r["article_id"]: r for r in csv.DictReader(AVAIL.open())}
    urls = {r["article_id"]: r for r in csv.DictReader(URL_MAP.open())}
    families = [json.loads(line) for line in CLUSTERS.open()]

    # relationship classes per family (from the Step 5 pair table -
    # tells the selector whether members differ substantively)
    ver_classes: dict[frozenset, str] = {}
    for r in csv.DictReader(VER_REL.open()):
        ver_classes[frozenset((r["article_id_a"],
                               r["article_id_b"]))] = r["classification"]
    # directed syndication origins (Step 4; empty in this corpus)
    origins: set[str] = set()
    for r in csv.DictReader(SYN.open()):
        if r["direction"] and r["direction"] != "undirected":
            origins.add(r["direction"].split("->")[0])

    def member_info(aid: str) -> dict:
        art, av = arts.get(aid, {}), avail.get(aid, {})
        polling = ELECTIONS.get(art.get("election_id", ""),
                                (None, None))[1]
        archived = av.get("archived_at", "")
        confirmed = bool(archived) and polling is not None \
            and date.fromisoformat(archived[:10]) <= polling
        return {"article_id": aid,
                "full_text": art.get("quality_status")
                == "valid_full_text",
                "clean": not (art.get("flags") or []),
                "pub_date_usable": bool(av.get("published_at")),
                "stable_url": bool(urls.get(aid, {}).get(
                    "canonical_url")),
                "temporal_confirmed": confirmed,
                "available_from": av.get("version_available_at")
                or av.get("available_lower_bound", ""),
                "is_origin": aid in origins}

    # ---- decide every validated family ------------------------------
    decisions = []
    member_to_family = {}
    for f in families:
        classes = {ver_classes[frozenset(p)]
                   for i, x in enumerate(f["members"])
                   for p in [(x, y) for y in f["members"][i + 1:]]
                   if frozenset(p) in ver_classes}
        fam = {"family_id": f["family_id"],
               "family_type": f["family_type"],
               "ordered": f.get("ordered", False),
               "relationship_classes": classes}
        d = select_canonical(fam, [member_info(a) for a in f["members"]])
        decisions.append(d)
        for aid in f["members"]:
            member_to_family[aid] = (f, d)

    # ---- one mapping row per Phase 4 article ------------------------
    rows = []
    for aid in sorted(arts):
        if aid in member_to_family:
            f, d = member_to_family[aid]
            selected = d["canonical_status"] == "canonical_selected"
            is_canon = selected and aid == d["canonical_article_id"]
            rows.append({
                "article_id": aid, "family_id": f["family_id"],
                "family_type": f["family_type"],
                "canonical_article_id": d["canonical_article_id"],
                "canonical_status": d["canonical_status"],
                "selection_reason": d["selection_reason"]
                if selected else d["rejected_reasons"].get(aid, ""),
                "selection_evidence": d["member_evidence"][aid],
                "temporal_validity_status":
                    d["temporal_validity_status"],
                "downstream_usage": "llm_extraction_primary"
                if is_canon else ("duplicate_retained_not_counted"
                                  if selected else
                                  "held_pending_review"),
                "review_required": not selected,
                "rule_version": RULE_VERSION, "input_refs": INPUT_REFS})
        else:
            rows.append({
                "article_id": aid, "family_id": "",
                "family_type": "independent_articles",
                "canonical_article_id": aid,
                "canonical_status":
                    "no_canonical_required_independent_articles",
                "selection_reason": "not a member of any validated "
                "family - the article represents itself",
                "selection_evidence": "",
                "temporal_validity_status": avail.get(aid, {}).get(
                    "availability_status", ""),
                "downstream_usage": "llm_extraction_primary",
                "review_required": False,
                "rule_version": RULE_VERSION, "input_refs": INPUT_REFS})

    # ---- temporal-leakage validation over the actual selections -----
    leakage_violations = []
    for d in decisions:
        if d["canonical_status"] != "canonical_selected":
            continue
        ev = d["member_evidence"]
        canon = ev[d["canonical_article_id"]]
        canon_confirmed = "temporal_confirmed=True" in canon
        for alt in d["alternatives"]:
            # a confirmed pre-election member of EQUAL usability must
            # never lose to an unconfirmed canonical - that would be
            # the leakage door this whole phase exists to close
            if ("temporal_confirmed=True" in ev[alt]
                    and "full_text=True" in ev[alt]
                    and "full_text=True" in canon
                    and not canon_confirmed):
                leakage_violations.append(d["family_id"])
    assert not leakage_violations, \
        f"canonical without confirmed availability chosen over a " \
        f"confirmed member: {leakage_violations}"
    assert len(rows) == len(arts), "mapping must cover every article"

    with OUT_MAP.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MAP_FIELDS, lineterminator="\n")
        w.writeheader(); w.writerows(rows)

    review = [d for d in decisions
              if d["canonical_status"] == "canonical_uncertain_manual_review"]
    with OUT_REVIEW.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "family_id", "family_type", "members", "reason",
            "member_evidence", "rule_version"], lineterminator="\n")
        w.writeheader()
        for d in review:
            w.writerow({"family_id": d["family_id"],
                        "family_type": d["family_type"],
                        "members": ";".join(sorted(d["member_evidence"])),
                        "reason": d["selection_reason"],
                        "member_evidence": " | ".join(
                            f"{k}: {v}" for k, v in sorted(
                                d["member_evidence"].items())),
                        "rule_version": RULE_VERSION})

    status = Counter(r["canonical_status"] for r in rows)
    usage = Counter(r["downstream_usage"] for r in rows)
    OUT_MD.write_text(
        "# Canonical article selection - Step 7 report "
        "(v1 provisional)\n\n"
        f"* rules: `{RULE_VERSION}`\n"
        f"* authoritative inputs: `{INPUT_REFS}`\n"
        f"* families processed: {len(families)} -> "
        f"{sum(1 for d in decisions if d['canonical_status'] == 'canonical_selected')} "
        f"canonical selected, {len(review)} in review\n"
        f"* mapping rows: {len(rows)} (one per Phase 4 article)\n"
        f"* status distribution: {dict(status)}\n"
        f"* downstream usage: {dict(usage)}\n"
        f"* temporal-leakage check: 0 violations (a canonical without "
        "confirmed pre-election availability is never chosen over a "
        "confirmed member; asserted at build time)\n\n"
        "Ranking order: temporal validity, text usability, "
        "cleanliness, provenance, earlier-availability tiebreak, "
        "deterministic id order. Body length, publisher size, "
        "retrieval order and newest-version are deliberately not "
        "criteria. Archive captures are availability evidence, not "
        "automatic canonicals. All members remain mapped with their "
        "relationships; nothing was deleted or merged, and the final "
        "duplicate layer is not frozen here.\n")

    print(f"{len(families)} families -> "
          f"{sum(1 for d in decisions if d['canonical_status'] == 'canonical_selected')} selected, "
          f"{len(review)} review | mapping rows: {len(rows)}")
    print("status:", dict(status))
    print("usage:", dict(usage))


if __name__ == "__main__":
    main()
