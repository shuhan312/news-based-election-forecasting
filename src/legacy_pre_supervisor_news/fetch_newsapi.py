"""Fetch the past month of Surrey local-politics news from NewsAPI.

Free plan limits that shape this script:
  - only ~1 month of history
  - max 100 results per query, so we slice the month into 7-day
    windows to stay under that cap
  - 100 requests/day

Raw API responses go to data/raw/newsapi/ untouched; a deduplicated
table of articles goes to data/processed/articles.csv.

Usage:  python src/fetch_newsapi.py
"""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("NEWSAPI_KEY")

URL = "https://newsapi.org/v2/everything"
DAYS_BACK = 28
WINDOW_DAYS = 7

RAW_DIR = Path("data/raw/newsapi")
PROCESSED_DIR = Path("data/processed")

# Restrict to UK outlets. The first run without this pulled in mostly
# Surrey, British Columbia (CBC, Daily Hive...) — "Surrey" alone can't
# tell the two places apart. getsurrey.co.uk is SurreyLive, the main
# local outlet; this run also tests whether NewsAPI indexes it at all.
DOMAINS = ",".join([
    "bbc.co.uk",
    "theguardian.com",
    "telegraph.co.uk",
    "independent.co.uk",
    "standard.co.uk",
    "news.sky.com",
    "itv.com",
    "getsurrey.co.uk",
    "inyourarea.co.uk",
    "dailymail.co.uk",
])

# Surrey's 11 boroughs/districts, so borough-level stories that never
# say "Surrey" still get caught.
BOROUGHS = ('(Woking OR Guildford OR Elmbridge OR Spelthorne OR Runnymede'
            ' OR Tandridge OR Waverley OR "Epsom and Ewell" OR "Mole Valley"'
            ' OR "Reigate and Banstead" OR "Surrey Heath")')

# Query set from the supervisor meeting: Surrey as the case study,
# the five parties of interest, and the local-government themes.
QUERIES = [
    '"Surrey County Council"',
    BOROUGHS + ' AND (council OR election)',
    'Surrey AND ("local election" OR "council election" OR by-election)',
    'Surrey AND ("Reform UK" OR Conservative OR Labour OR "Liberal Democrat" OR "Green Party")',
    'Surrey AND ("council tax" OR "council budget" OR "council finance")',
    'Surrey AND council AND (housing OR planning OR infrastructure OR roads)',
    'Surrey AND ("energy bills" OR "electricity prices" OR "gas prices")',
]


def windows():
    """Yield (from, to) pairs covering the past DAYS_BACK days."""
    start = date.today() - timedelta(days=DAYS_BACK)
    while start < date.today():
        end = min(start + timedelta(days=WINDOW_DAYS), date.today())
        yield start, end
        start = end


def fetch(query, from_date, to_date):
    params = {
        "q": query,
        "domains": DOMAINS,
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,
        "apiKey": API_KEY,
    }
    resp = requests.get(URL, params=params, timeout=30)
    body = resp.json()
    if resp.status_code != 200:
        print(f"  FAILED: HTTP {resp.status_code} [{body.get('code')}] {body.get('message')}")
        return None
    return body


def save_raw(body, query_idx, from_date):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{date.today()}_q{query_idx}_{from_date}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1))


def to_rows(body, query):
    for a in body["articles"]:
        yield {
            "url": a.get("url"),
            "published_at": a.get("publishedAt"),
            "source": (a.get("source") or {}).get("name"),
            "title": a.get("title"),
            "description": a.get("description"),
            "content": a.get("content"),  # free plan truncates this to ~200 chars
            "matched_query": query,
        }


def main():
    if not API_KEY:
        raise SystemExit("NEWSAPI_KEY not set — copy .env.example to .env and fill it in.")

    rows = []
    requests_used = 0

    for i, query in enumerate(QUERIES):
        print(f"[{i + 1}/{len(QUERIES)}] {query}")
        for from_date, to_date in windows():
            body = fetch(query, from_date, to_date)
            requests_used += 1
            if body is None:
                continue
            total = body["totalResults"]
            print(f"  {from_date} -> {to_date}: {total} articles" +
                  ("  (over 100, window too wide — some lost)" if total > 100 else ""))
            save_raw(body, i, from_date)
            rows.extend(to_rows(body, query))
            time.sleep(1)

    df = pd.DataFrame(rows)
    if df.empty:
        print("\nNo articles fetched.")
        return

    # The same article often matches several queries; keep one copy
    # but remember every query that found it.
    matched = df.groupby("url")["matched_query"].agg("; ".join)
    df = df.drop_duplicates("url").drop(columns="matched_query").merge(matched, on="url")
    df = df.sort_values("published_at")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / "articles.csv"
    df.to_csv(out, index=False)

    print(f"\n{requests_used} requests used, {len(df)} unique articles -> {out}")
    print("\nTop sources:")
    print(df["source"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
