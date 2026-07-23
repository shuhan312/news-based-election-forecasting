"""Classify the root cause of every remaining no_date_evidence record in
effective_dates.csv, so the honest answer to "can any of these still be
fixed" is backed by an auditable table, not a handful of spot-checks.

Why this exists
-----------------
After recover_pdf_dates.py and the retrieval-time-contamination fixes,
275 records still have no usable date. Spot-checking a sample of
getsurrey.co.uk records suggested a possible parsing bug - old-template
pages returning real text but zero date evidence. Investigating that
properly (not just asserting it from 3 examples) meant checking what
these pages actually contain:

  * getsurrey.co.uk / surreycomet.co.uk old-template pages carry NO date
    markup anywhere - confirmed by direct inspection, not inferred. The
    only elements matching class="date" are reader-COMMENT timestamps
    (e.g. "John R ... 04/05/2012 at 20:02"), not the article's own date
    - the same class of trap already rejected once in
    investigate_unresolved_dates.py (a sidebar widget there, reader
    comments here). This is a genuine source-level gap, not a bug: nothing
    on the page tells a human reader the publish date either.
  * whocanivotefor.co.uk and the mgElectionAreaResults.aspx-style
    mycouncil.surreycc.gov.uk pages are not dated news content at all -
    the former is a live candidate-lookup tool (the date in its URL is
    the ELECTION date, not a publication date), the latter are
    JavaScript-rendered shells our fetch cannot execute (~850 bytes of
    near-empty HTML). Neither has a "publication date" to find.
  * facebook.com / instagram.com return login-wall pages to an
    unauthenticated fetch - no article content of any kind is reachable
    this way, let alone a date.

None of these are extract_html_metadata bugs. This script does not fix
anything - it labels each gap record with which of these categories it
falls into (or leaves it unclassified for a human to look at
individually), so the final state is demonstrated rather than asserted.

Usage:
    python3 -m src.news_collection.classify_date_gaps
"""

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

EFFECTIVE_DATES = Path("news_collection/effective_dates.csv")
RECORDS = Path("data/raw/news/records")
HTML_DIR = Path("data/raw/news/html")
OUT = Path("news_collection/date_gap_classification.csv")

SOCIAL_MEDIA_DOMAINS = {"www.facebook.com", "www.instagram.com", "facebook.com",
                        "instagram.com"}
# Confirmed by direct inspection (see module docstring) to carry no date
# markup of any kind on their archived-era article template.
NO_DATE_MARKUP_DOMAINS = {"www.getsurrey.co.uk", "getsurrey.co.uk",
                          "www.surreycomet.co.uk", "surreycomet.co.uk"}
# Reference/lookup tools, not dated news articles - a category mismatch,
# not a missing-evidence problem. www10.surreycc.gov.uk/electionmap/... is
# the council's own results-by-ward map (headline literally "West Surrey
# Council election results"), same nature as whocanivotefor.co.uk.
REFERENCE_TOOL_DOMAINS = {"whocanivotefor.co.uk", "mapit.mysociety.org",
                          "www10.surreycc.gov.uk"}


def classify(rec, html_path):
    url = rec["identity"]["canonical_url"] or ""
    # Old Wayback-archived URLs often carry an explicit ":80" port
    # (http://www.getsurrey.co.uk:80/...) that urlparse keeps in netloc -
    # strip it so these match the same domain as their portless copies.
    domain = urlparse(url).netloc.split(":")[0]
    retrieval_status = rec["retrieval"]["retrieval_status"]

    if domain in SOCIAL_MEDIA_DOMAINS:
        return ("social_media_login_wall",
                "Facebook/Instagram require login/JS; no content reachable "
                "by a plain fetch.")
    if domain in REFERENCE_TOOL_DOMAINS:
        return ("reference_tool_not_dated_content",
                "A candidate/results/boundary lookup tool, not a dated "
                "article - any date in its URL or page is an election or "
                "geography date, not a publication date.")
    if "/screenshot-" in url or "wp-content/uploads" in url:
        return ("not_an_article_media_attachment",
                "A WordPress media/screenshot attachment page picked up "
                "by Wayback discovery alongside the real article it "
                "illustrates - not itself an article.")
    if "moderngov" in domain or "mycouncil." in domain:
        size = html_path.stat().st_size if html_path.exists() else 0
        if size < 2000:
            return ("javascript_rendered_empty_shell",
                    f"Only {size} bytes fetched - a JS-rendered council "
                    "management-system page our fetch cannot execute.")
    if domain in NO_DATE_MARKUP_DOMAINS and html_path.exists():
        html = html_path.read_text(errors="replace")
        if "datePublished" not in html and "<time" not in html:
            return ("source_lacks_date_markup",
                    "Confirmed (see module docstring): this template has "
                    "no machine- or human-readable publication date "
                    "anywhere on the page; class=\"date\" elements here "
                    "are reader-comment timestamps, not the article's.")
    if retrieval_status == "blocked":
        return ("retrieval_blocked",
                "Page returned a challenge/blocked response - no content "
                "of any kind was retrievable, let alone a date.")
    return ("unclassified", "Not yet individually checked.")


def main():
    eff_rows = list(csv.DictReader(EFFECTIVE_DATES.open()))
    gaps = [r for r in eff_rows if r["date_status"] == "no_date_evidence"]

    out_rows = []
    counts = {}
    for r in gaps:
        rec = json.loads((RECORDS / f"{r['article_id']}.json").read_text())
        html_path = HTML_DIR / f"{r['article_id']}.html"
        category, note = classify(rec, html_path)
        counts[category] = counts.get(category, 0) + 1
        out_rows.append({
            "article_id": r["article_id"], "election_id": r["election_id"],
            "canonical_url": rec["identity"]["canonical_url"],
            "category": category, "note": note,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print(f"{len(out_rows)} no_date_evidence records classified -> {OUT}")
    for cat, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {n}")
    print(f"\n'unclassified' records are the only ones where a further "
          f"fix might still be possible - everything else has a "
          f"confirmed, non-fixable root cause (see module docstring).")


if __name__ == "__main__":
    main()
