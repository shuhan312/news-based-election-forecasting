"""Check how far back NewsAPI's Everything endpoint lets this subscription
query, against the actual 180-day pre-election windows the supervisor's
method requires.

This is a one-off diagnostic, not part of the collection pipeline: it prints
a plain report to be read (and shown to the supervisor), and also saves it to
data/raw/newsapi/coverage_check.txt.

Usage:
    python3 src/check_newsapi_coverage.py
"""

import os
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("NEWSAPI_KEY")
URL = "https://newsapi.org/v2/everything"
OUTPUT_PATH = Path("data/raw/newsapi/coverage_check.txt")

# The four elections this project covers, and the 180-day search window the
# supervisor's method specifies for each.
ELECTIONS = [
    ("2013 Surrey County Council election", date(2013, 5, 2)),
    ("2017 Surrey County Council election", date(2017, 5, 4)),
    ("2021 Surrey County Council election", date(2021, 5, 6)),
    ("2026 East/West Surrey Council election", date(2026, 5, 7)),
]


def query(from_date, to_date):
    """One Everything-endpoint call for a single day, to spend as little
    of the daily request quota as possible while still testing coverage."""
    response = requests.get(URL, params={
        "q": "Surrey",
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "language": "en",
        "pageSize": 1,
        "apiKey": API_KEY,
    }, timeout=30)
    return response.json()


def describe(result):
    if result.get("status") == "ok":
        return f"OK - {result.get('totalResults')} results available"
    return f"BLOCKED - {result.get('code')}: {result.get('message')}"


def main():
    if not API_KEY:
        raise SystemExit("NEWSAPI_KEY is not set in .env")

    lines = [
        f"NewsAPI Everything endpoint coverage check - run {date.today().isoformat()}",
        "=" * 72,
        "",
        "Control: can this key reach NewsAPI at all, for a recent date?",
    ]
    recent_from = date.today() - timedelta(days=20)
    recent_to = date.today() - timedelta(days=19)
    lines.append(f"  {recent_from} to {recent_to}: {describe(query(recent_from, recent_to))}")
    lines.append("")
    lines.append("Election-specific test: the first day of the supervisor's "
                  "180-day pre-election search window, for each election.")
    lines.append("")

    for name, polling_day in ELECTIONS:
        window_start = polling_day - timedelta(days=180)
        window_end = window_start + timedelta(days=1)
        result = query(window_start, window_end)
        lines.append(f"{name}")
        lines.append(f"  Polling day: {polling_day.isoformat()}")
        lines.append(f"  180 days before: {window_start.isoformat()}")
        lines.append(f"  Result: {describe(result)}")
        lines.append("")

    report = "\n".join(lines)
    print(report)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report + "\n", encoding="utf-8")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
