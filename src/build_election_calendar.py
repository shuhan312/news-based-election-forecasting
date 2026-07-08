"""Build the Surrey election calendar by probing Wikipedia page titles.

UK local elections all have Wikipedia articles with a fixed title
pattern, e.g. "2022 Woking Borough Council election". For every
council x year combination this script asks the Wikipedia API whether
that page exists; an existing page means that election (very likely)
took place. The result is the calendar of elections whose results we
need to collect as prediction targets.

Wikipedia is not the official record — verify the rows against
council websites before relying on them, especially 2025-2026 where
local government reorganisation changed the schedule.

Output:  data/elections/election_calendar.csv
Usage:   python src/build_election_calendar.py
"""

import time
from pathlib import Path

import pandas as pd
import requests

API = "https://en.wikipedia.org/w/api.php"

COUNCILS = [
    "Surrey County Council",
    "Elmbridge Borough Council",
    "Epsom and Ewell Borough Council",
    "Guildford Borough Council",
    "Mole Valley District Council",
    "Reigate and Banstead Borough Council",
    "Runnymede Borough Council",
    "Spelthorne Borough Council",
    "Surrey Heath Borough Council",
    "Tandridge District Council",
    "Waverley Borough Council",
    "Woking Borough Council",
]
YEARS = range(2021, 2027)

# Confirmed on surreycc.gov.uk (8 Jul 2026): local government
# reorganisation replaced Surrey's 12 councils with two new unitary
# councils, elected on 7 May 2026. The Wikipedia probe cannot find
# these, so they are added from the official source directly.
# Results live on the Future Surrey website.
OFFICIAL_EXTRA = [
    {"year": 2026, "council": "East Surrey Council (new unitary)",
     "wikipedia_page": "", "url": "https://www.surreycc.gov.uk",
     "verified_official": "yes"},
    {"year": 2026, "council": "West Surrey Council (new unitary)",
     "wikipedia_page": "", "url": "https://www.surreycc.gov.uk",
     "verified_official": "yes"},
]

OUT_PATH = Path("data/elections/election_calendar.csv")


def existing_pages(titles):
    """Ask Wikipedia which of these article titles exist.

    The API accepts up to 50 titles per request, so we batch instead
    of asking one by one (single requests got rate limited).
    """
    found = set()
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        params = {
            "action": "query",
            "titles": "|".join(chunk),
            "redirects": 1,  # a redirect to the real article counts as existing
            "format": "json",
        }
        resp = requests.get(API, params=params, timeout=30,
                            headers={"User-Agent": "IRP election calendar builder"})
        resp.raise_for_status()
        query = resp.json()["query"]
        # map any redirected/normalised titles back to what we asked for
        redirect_from = {r["to"]: r["from"] for r in query.get("redirects", [])}
        normalised_from = {n["to"]: n["from"] for n in query.get("normalized", [])}
        for page in query["pages"].values():
            if "missing" in page:
                continue
            title = page["title"]
            title = redirect_from.get(title, title)
            title = normalised_from.get(title, title)
            found.add(title)
        time.sleep(1)
    return found


def main():
    candidates = [(year, council, f"{year} {council} election")
                  for year in YEARS for council in COUNCILS]
    found = existing_pages([t for _, _, t in candidates])

    rows = []
    for year, council, title in candidates:
        if title not in found:
            continue
        url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        rows.append({"year": year, "council": council,
                     "wikipedia_page": title, "url": url,
                     "verified_official": "no"})
        print(f"found: {title}")

    rows.extend(OFFICIAL_EXTRA)
    df = pd.DataFrame(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"\n{len(df)} elections -> {OUT_PATH}")
    print("\nElections per year:")
    print(df["year"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
