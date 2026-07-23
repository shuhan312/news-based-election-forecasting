"""Flag Guardian records collected before the production-office=uk fix
(adapters.py, GuardianAdapter.search) that come from unambiguously
non-UK sections of the Guardian.

Why this exists
-----------------
The Guardian's national-topic query terms (party_leadership,
polling_switching, etc. in build_query_inventory.py's NATIONAL_FAMILIES)
are generic enough to match Guardian's US and Australia editions, which
use similar phrasing. This was discovered while investigating the
Publication Date Resolution stage's "needs_human_review" queue: 38/41
of those records were Guardian, and most were Australian/US political
live-blogs unrelated to Surrey or UK politics at all - a data-quality
problem bigger than the date conflicts that surfaced it. A full-corpus
count confirms the scale: 284 of 2,854 Guardian records (~10%) come
from the us-news or australia-news sections.

Verified fix (2026-07-23): adding production-office=uk to the Guardian
Content API call excludes this content going forward (a live
comparison query returned australia-news/US-related hits without the
parameter and only uk-news/politics/commentisfree hits with it).

This script does not delete or edit anything already collected - raw
records are immutable everywhere in this project. It only flags the
unambiguous cases (a section-path fact, not a guess) in a separate,
joinable table, for the Article Eligibility Assessment stage (E1-E10,
specifically the "irrelevant" test) to consume. Ambiguous sections
("world", "commentisfree", etc., which sometimes ARE genuinely
UK-relevant - e.g. a commentisfree piece about Reform UK) are
deliberately NOT flagged here: that judgment belongs to the
eligibility stage's per-article relevance test, not a blunt
section-name rule that could wrongly exclude real evidence.

Usage:
    python3 -m src.news_collection.audit_guardian_geographic_relevance
"""

import csv
import json
from collections import Counter
from pathlib import Path

RECORDS = Path("data/raw/news/records")
OUT = Path("news_collection/guardian_geographic_relevance_flags.csv")

# Only sections that are unambiguously a different country's edition -
# a hard fact from the URL path, not an inference about content. Every
# other Guardian section (world, commentisfree, society, business, ...)
# is left for the eligibility stage's own per-article judgement.
UNAMBIGUOUS_NON_UK_SECTIONS = {"us-news", "australia-news"}


def guardian_section(canonical_url):
    if not canonical_url or "theguardian.com/" not in canonical_url:
        return None
    return canonical_url.split("theguardian.com/")[-1].split("/")[0]


def main():
    flagged, total_guardian = [], 0
    by_election = Counter()
    by_section = Counter()

    for path in RECORDS.glob("NEWS-guardian_api-*.json"):
        rec = json.loads(path.read_text())
        total_guardian += 1
        section = guardian_section(rec["identity"]["canonical_url"])
        if section in UNAMBIGUOUS_NON_UK_SECTIONS:
            by_election[rec["discovered_for_election"]] += 1
            by_section[section] += 1
            flagged.append({
                "article_id": rec["article_id"],
                "election_id": rec["discovered_for_election"],
                "guardian_section": section,
                "headline": rec["identity"]["headline"],
                "canonical_url": rec["identity"]["canonical_url"],
                "geographic_relevance_flag": "likely_non_uk_edition",
                "reason": f"Guardian section '{section}' is a "
                         "different country's edition, not the UK "
                         "edition this project's national arm targets.",
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(flagged[0].keys()))
        w.writeheader()
        w.writerows(flagged)

    print(f"{len(flagged)}/{total_guardian} Guardian records "
          f"({100 * len(flagged) / total_guardian:.1f}%) flagged as "
          f"likely non-UK edition content -> {OUT}")
    print("by section:", dict(by_section))
    print("by election:", dict(by_election))
    print("\nThese records are NOT deleted or modified - the flag file "
          "is a separate, joinable input for Article Eligibility "
          "Assessment (E1-E10). Ambiguous sections (world, "
          "commentisfree, etc.) are intentionally left unflagged here.")


if __name__ == "__main__":
    main()
