"""Catalogue the Haslemere campaign's non-news digital trail (descriptive).

    python3 -m src.news_collection.catalogue_haslemere_nonnews_trail

The collection-gap audit found that the 92 undated (E1) Haslemere
records hide no missed press coverage but do hold the campaign's own
digital footprint. This module turns that one-off audit into a citable
artefact: a per-record catalogue of every politically-flagged undated
record, classified by channel type from its stored URL and headline.

Three boundaries keep this honest and inside the protocol:

- DESCRIPTIVE ONLY. Nothing here assigns dates, revives records into
  any corpus, or feeds any model. E1 exclusions stay excluded; the
  catalogue reads the already-collected raw records and writes a table.
- CLASSIFICATION IS MECHANICAL AND STATED. Channel type comes from the
  URL's domain against the explicit rule list below - no judgement
  calls hide inside; a domain the rules do not know is labelled
  ``unclassified`` rather than guessed.
- THE POLITICAL FILTER IS RECALL-ORIENTED. The same term list the
  audit used flags anything plausibly political; the two pages of an
  American ministry sharing a candidate's name match it ("witt") and
  are kept visibly as ``namesake_false_positive`` rather than silently
  dropped. NOTE: this catalogue flags 56 records where the register's
  audit paragraph said 54 - the audit's headline count used a 200-
  character extract window while its composition breakdown (which
  already summed to 56) and this catalogue use 300 characters. The
  register carries an explicit correction; 56 is the durable figure.

Why this exists for the report: the probe's finding is that the local
PRESS did not cover the July campaign; the refined finding is that the
campaign was nonetheless visible in non-news channels (candidate
social media, civic databases, a tactical-voting site). This table is
the evidence for the second half of that sentence - a future-work
data-source class, observed, counted and cited, never modelled here.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ASSESSMENT = Path("news_collection/haslemere_probe/eligibility_assessment.csv")
RECORDS = Path("data/raw/news/records")
OUT_JSON = Path("news_collection/haslemere_probe/nonnews_trail_catalogue.json")
OUT_MD = Path("news_collection/haslemere_probe/nonnews_trail_catalogue.md")

# Same recall-oriented term list the register's audit used - kept
# identical so the catalogue's 54-record denominator is the audit's.
POLITICAL = re.compile(
    r"reform uk|conservativ|labour|liberal democrat|lib dem|green party|"
    r"by-?election|candidate|councillor|election|vote|polls|witt|weldon|"
    r"shrive|byfield|robini|county council", re.I)

# Channel classification: first matching rule wins, checked in order.
# Every rule names real domains observed in the audit; anything not
# matched is "unclassified", never guessed.
CHANNEL_RULES: tuple[tuple[str, str], ...] = (
    (r"barbwitt\.org", "namesake_false_positive"),
    (r"facebook\.com|instagram\.com|twitter\.com|x\.com|tiktok\.com",
     "candidate_or_party_social_media"),
    (r"electionleaflets\.org", "campaign_leaflet_archive"),
    (r"libdems|greenparty|conservatives\.com|reformparty|labour\.org",
     "party_site"),
    (r"whocanivotefor\.co\.uk|local-democracy\.uk", "civic_database"),
    (r"stopreformuk\.vote", "tactical_voting_site"),
    (r"\.gov\.uk|modgov", "council_or_government_page"),
    (r"publicnoticeportal\.uk", "public_notice_portal"),
    (r"proboards\.com", "discussion_forum"),
    # A press DOMAIN can still be a non-article page: the one Farnham
    # Herald hit here is its /topic/ index, not a written article.
    (r"farnhamherald\.com/topic/", "press_topic_index_page"),
)

# Which contest a record references, where the URL itself says so -
# the July by-election slug or the May principal slug. Anything else
# is "undetermined": these records have no usable date by definition,
# and the catalogue does not infer one.
JULY = re.compile(r"2026-07-07|by-?election", re.I)
MAY = re.compile(r"2026-05-07|west-surrey", re.I)


def classify(url: str, headline: str) -> str:
    text = url.lower()
    for pattern, label in CHANNEL_RULES:
        if re.search(pattern, text):
            return label
    if "leaflet" in headline.lower():
        return "campaign_leaflet_archive"
    return "unclassified"


def main() -> None:
    e1_ids = [row["article_id"] for row in csv.DictReader(ASSESSMENT.open())
              if row["exclusion_code"] == "E1"]

    rows = []
    for article_id in e1_ids:
        record = json.loads((RECORDS / f"{article_id}.json").read_text())
        headline = record.get("identity", {}).get("headline") or ""
        extract = (record.get("content", {}).get("extract") or "")[:300]
        if not POLITICAL.search(headline + " " + extract):
            continue
        url = record.get("identity", {}).get("canonical_url") or ""
        contest = ("july_byelection" if JULY.search(url + " " + headline)
                   else "may_principal" if MAY.search(url + " " + headline)
                   else "undetermined")
        rows.append({
            "article_id": article_id,
            "channel": classify(url, headline),
            "contest_reference": contest,
            "headline": headline[:120],
            "url": url[:160],
        })

    by_channel = Counter(row["channel"] for row in rows)
    press_articles = sum(
        1 for row in rows
        if row["channel"] in ("unclassified",)
        and "farnhamherald" in row["url"])
    payload = {
        "status": ("DESCRIPTIVE catalogue of undated politically-flagged "
                   "records. Nothing here re-enters any corpus, feature "
                   "table or model."),
        "e1_records_total": len(e1_ids),
        "politically_flagged": len(rows),
        "by_channel": dict(by_channel.most_common()),
        "by_contest_reference": dict(Counter(
            row["contest_reference"] for row in rows)),
        "editorial_press_articles_found": press_articles,
        "records": sorted(rows, key=lambda row: (row["channel"],
                                                 row["article_id"])),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n",
                        encoding="utf-8")

    lines = [
        "# The non-news digital trail of the Haslemere campaign",
        "", f"**{payload['status']}**", "",
        f"Of the {len(e1_ids)} records excluded for unresolvable dates, "
        f"{len(rows)} carry political terms. Their channels:", "",
        "| channel | records |", "| --- | ---: |",
    ]
    lines += [f"| {channel} | {count} |"
              for channel, count in by_channel.most_common()]
    lines += [
        "",
        f"Editorial press articles among them: "
        f"**{press_articles}** - the audit finding this catalogue "
        "preserves. The campaign's visibility lived in candidates' own "
        "social media, civic databases (WhoCanIVoteFor's July listing of "
        "all four candidates), council pages and one tactical-voting "
        "site; none of it is a news article under the design's I4/E8 "
        "definition, and none of it carries a recoverable publication "
        "date. A data-source class for future work, not an input to any "
        "model in this project.", "",
        "| channel | contest ref | headline |", "| --- | --- | --- |",
    ]
    lines += [
        f"| {row['channel']} | {row['contest_reference']} | "
        f"{row['headline'].replace('|', '/')} |"
        for row in payload["records"]
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"E1 records: {len(e1_ids)}; politically flagged: {len(rows)}")
    for channel, count in by_channel.most_common():
        print(f"  {channel}: {count}")
    print(f"editorial press articles: {press_articles}")
    print(f"-> {OUT_JSON}\n-> {OUT_MD}")


if __name__ == "__main__":
    main()
