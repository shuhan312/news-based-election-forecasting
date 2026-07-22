"""Download Surrey-related news from the Guardian archive (Jan 2021 - May 2026).

Runs each query in QUERIES against the Guardian search API and pages
through all results. Output:

  data/raw/guardian/                     one JSON file per API response
  data/processed/guardian_articles.csv   deduplicated articles, full text included

Needs GUARDIAN_KEY in .env (free key from
https://open-platform.theguardian.com/access/).

Usage:  python src/fetch_guardian.py
"""

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GUARDIAN_KEY")

URL = "https://content.guardianapis.com/search"
FROM_DATE = "2021-01-01"   # training period starts with the 2021 local elections
TO_DATE = "2026-05-31"     # validation period ends with the May 2026 local elections
PAGE_SIZE = 50             # API maximum
MAX_CALLS = 450            # free keys have a daily quota; stop before hitting it

RAW_DIR = Path("data/raw/guardian")
PROCESSED_DIR = Path("data/processed")

# Surrey's 11 boroughs/districts. Local stories often name the borough
# but never the county, so "Surrey" alone would miss them.
BOROUGHS = ('(Woking OR Guildford OR Elmbridge OR Spelthorne OR Runnymede'
            ' OR Tandridge OR Waverley OR "Epsom and Ewell" OR "Mole Valley"'
            ' OR "Reigate and Banstead" OR "Surrey Heath")')

QUERIES = [
    '"Surrey County Council"',
    BOROUGHS + ' AND (council OR election)',
    'Surrey AND ("local election" OR "council election" OR by-election)',
    'Surrey AND ("Reform UK" OR Conservative OR Labour OR "Liberal Democrat" OR "Green Party")',
    'Surrey AND ("council tax" OR "council budget" OR "council finance")',
    'Surrey AND council AND (housing OR planning OR infrastructure OR roads)',
    'Surrey AND ("energy bills" OR "electricity prices" OR "gas prices")',
]


def fetch_page(query, page):
    """Request one page of search results (up to PAGE_SIZE articles).

    Returns the parsed response, "rate_limited" if the daily quota ran
    out, or None on any other error.
    """
    params = {
        "q": query,
        "from-date": FROM_DATE,
        "to-date": TO_DATE,
        "page": page,
        "page-size": PAGE_SIZE,
        # without show-fields the API returns metadata only;
        # bodyText is the full article text
        "show-fields": "trailText,bodyText,wordcount,byline",
        "order-by": "oldest",
        "api-key": API_KEY,
    }
    resp = requests.get(URL, params=params, timeout=30)
    if resp.status_code == 429:
        return "rate_limited"
    if resp.status_code != 200:
        print(f"  FAILED: HTTP {resp.status_code} {resp.text[:200]}")
        return None
    return resp.json()["response"]


def to_rows(response, query):
    """Flatten one API response into table rows, one per article."""
    for r in response["results"]:
        fields = r.get("fields") or {}
        yield {
            "url": r.get("webUrl"),
            "published_at": r.get("webPublicationDate"),
            "section": r.get("sectionName"),
            "title": r.get("webTitle"),
            "description": fields.get("trailText"),
            "body_text": fields.get("bodyText"),
            "wordcount": fields.get("wordcount"),
            "matched_query": query,
        }


def main():
    if not API_KEY:
        raise SystemExit("GUARDIAN_KEY not set — register at "
                         "https://open-platform.theguardian.com/access/ and add it to .env")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    calls = 0

    # Walk every query, page by page, until its results run out.
    for i, query in enumerate(QUERIES):
        print(f"[{i + 1}/{len(QUERIES)}] {query}")
        page, pages = 1, 1  # real page count arrives with the first response
        while page <= pages:
            if calls >= MAX_CALLS:
                print("  call budget reached — rerun tomorrow to continue")
                break
            response = fetch_page(query, page)
            calls += 1
            if response == "rate_limited":
                print("  rate limited — stopping, rerun later")
                break
            if response is None:
                break

            pages = response["pages"]
            if page == 1:
                print(f"  {response['total']} articles across {pages} pages")
            # keep the untouched response on disk, then collect the rows
            (RAW_DIR / f"q{i}_p{page}.json").write_text(
                json.dumps(response, ensure_ascii=False))
            rows.extend(to_rows(response, query))
            page += 1
            time.sleep(1)  # stay under the requests-per-second limit

    df = pd.DataFrame(rows)
    if df.empty:
        print("\nNo articles fetched.")
        return

    # An article often matches several queries; keep one copy but
    # remember every query that found it.
    matched = df.groupby("url")["matched_query"].agg("; ".join)
    df = df.drop_duplicates("url").drop(columns="matched_query").merge(matched, on="url")
    df = df.sort_values("published_at")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "guardian_articles.csv"
    df.to_csv(out, index=False)

    print(f"\n{calls} API calls, {len(df)} unique articles -> {out}")
    print("\nArticles per year:")
    print(df["published_at"].str[:4].value_counts().sort_index().to_string())
    print("\nTop sections:")
    print(df["section"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
