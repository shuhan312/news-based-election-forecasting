"""Flag SerpAPI-sourced records whose domain proves they cannot be UK
local/national news, found as a side effect of investigating the
Publication Date Resolution stage's unresolved-evidence queue.

Why this exists
-----------------
Three of the 134 unresolvable_missing_evidence records (see
resolve_publication_dates.py, investigate_unresolved_dates.py) had no
stored HTML because they came back from SerpAPI's general web search
with content-types this pipeline never fetches as articles. Looking at
what they actually were:

  * middlesexcountynj.gov - Middlesex County, New Jersey's own planning
    department page
  * warrencountynj.gov - Warren County, New Jersey's own planning
    department page
  * whitepages.com/name/Daniel-Ward - a people-search listing for a
    person named Ward

None of these are UK news. This is the SerpAPI-adapter analogue of the
Guardian geographic-relevance problem found and fixed the same day
(audit_guardian_geographic_relevance.py): broad query terms (a query
built around a candidate surname such as "Ward", or a generic phrase
like "planning" or "council transportation") are generic enough to
match places and people that share a name with Surrey wards or
councillors without being remotely related to them. Unlike the Guardian
case, there is no reliable URL-path signal to generalise from (these
three just happen to be .gov county sites and a people-search site) -
so this is recorded as a specific, evidenced finding for these three
records, not a general SerpAPI domain rule.

This script does not delete or edit anything - it only documents what
was found, for the Article Eligibility Assessment stage (E1-E10) to
use alongside the Guardian flags. Kept separate from
guardian_geographic_relevance_flags.csv because the root cause and the
source (adapter) differ.

Usage:
    python3 -m src.news_collection.audit_serpapi_domain_relevance
"""

import csv
from pathlib import Path

OUT = Path("news_collection/serpapi_domain_relevance_flags.csv")

# Each entry evidenced individually during the 2026-07-23 date-resolution
# investigation (see manual_review_decisions.csv's sibling file,
# date_resolution_investigation.csv, defect_type=no_html_stored). Not a
# programmatic scan - a short, hand-verified list, because the underlying
# signal (domain proves non-UK/non-news) has no safe general rule yet.
FLAGGED = [
    {
        "article_id": "NEWS-google_dated_search-5b32da5cd752",
        "election_id": "ESWS-2026-05",
        "domain": "middlesexcountynj.gov",
        "canonical_url": "https://www.middlesexcountynj.gov/government/"
                          "departments/department-of-transportation/"
                          "office-of-planning",
        "reason": "Middlesex County, New Jersey (USA) government site - "
                 "not a UK source. A generic query term (transportation/"
                 "planning department) matched by coincidence.",
    },
    {
        "article_id": "NEWS-google_dated_search-cbbc4720ee86",
        "election_id": "ESWS-2026-05",
        "domain": "whitepages.com",
        "canonical_url": "https://www.whitepages.com/name/Daniel-Ward",
        "reason": "A people-search directory listing for a person named "
                 "Ward, not a news article - matched by a candidate "
                 "surname appearing in a query.",
    },
    {
        "article_id": "NEWS-google_dated_search-f73ecde34020",
        "election_id": "ESWS-2026-05",
        "domain": "warrencountynj.gov",
        "canonical_url": "https://www.warrencountynj.gov/government/"
                          "planning-department",
        "reason": "Warren County, New Jersey (USA) government site - "
                 "not a UK source. Same generic-term-collision pattern "
                 "as the Middlesex County NJ hit above.",
    },
    # Found in a second pass (2026-07-23) after Stage M's later collection
    # was run through the same investigation - same root cause, unrelated
    # topics matched by generic query terms.
    {
        "article_id": "NEWS-google_dated_search-eb477830e1b8",
        "election_id": "ESWS-2026-05",
        "domain": "akc.org",
        "canonical_url": "https://www.akc.org/wp-content/uploads/2026/05/"
                          "Current-List-of-AKC-Stewards-5-4-26.pdf",
        "reason": "American Kennel Club dog-show stewards list - not a "
                 "UK source and not news of any kind. Matched by an "
                 "incidental term collision.",
    },
    {
        "article_id": "NEWS-google_dated_search-89a4a43948a4",
        "election_id": "ESWS-2026-05",
        "domain": "ballotpedia.org",
        "canonical_url": "https://ballotpedia.org/Gregory_E._Smith_"
                          "(Pennsylvania)",
        "reason": "Ballotpedia covers US elections exclusively, and this "
                 "page is a Pennsylvania politician's biography - not a "
                 "UK source. Matched on a name/term collision.",
    },
]


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FLAGGED[0].keys()))
        w.writeheader()
        w.writerows(FLAGGED)
    print(f"{len(FLAGGED)} SerpAPI hits flagged as non-UK/non-news -> {OUT}")
    print("Hand-verified, not a general domain rule - see module "
          "docstring for why this differs from the Guardian audit.")


if __name__ == "__main__":
    main()
