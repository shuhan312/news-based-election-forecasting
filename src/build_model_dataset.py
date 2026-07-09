"""Join ward election outcomes with the pre-election news environment.

Produces the first model-ready dataset: one row per ward contest, holding
the outcome (y) plus two kinds of features (X):

  - national news climate: the monthly Guardian features summed over the
    three months before polling (February to April). May itself is left
    out because polling day sits inside it, and counting articles from
    after the vote would leak the answer into the features.
  - ward history: who won this ward last time, from the results table
    itself. National features cannot tell two wards apart in the same
    year; this column can.

Output:  data/processed/model_dataset.csv

Usage:   python src/build_model_dataset.py
"""

import re

import pandas as pd

WINNERS = "data/elections/ward_winners.csv"
NEWS = "data/processed/news_features_monthly.csv"
OUT = "data/processed/model_dataset.csv"

WINDOW = ["02", "03", "04"]  # months before a May election


def pre_election_features(news):
    """Sum each year's February-April news counts into one row per year."""
    news = news.copy()
    news["year"] = news["month"].str[:4].astype(int)
    windowed = news[news["month"].str[5:].isin(WINDOW)]
    feats = windowed.drop(columns="month").groupby("year").sum().reset_index()
    return feats.rename(columns={c: f"{c}_pre3m" for c in feats.columns
                                 if c != "year"})


def ward_key(name):
    """Normalise a ward name for matching across years.

    Wikipedia editors write the same ward differently in different
    years ("Cobham & Downside" / "Cobham and Downside", "St John's" /
    "St Johns"), so we match on a cleaned-up key but keep the original
    name for display.
    """
    key = name.lower().replace("&", " and ")
    key = re.sub(r"[.'’]", "", key)
    return re.sub(r"\s+", " ", key).strip()


def add_ward_history(winners):
    """Attach each ward's previous result (same council + ward).

    Ward boundaries genuinely changed for some 2023 elections, so not
    every ward has a findable predecessor; those get NaN rather than
    a guess.
    """
    winners = winners.copy()
    winners["ward_key"] = winners["ward"].map(ward_key)
    winners = winners.sort_values(["council", "ward_key", "year"])
    prev = winners.groupby(["council", "ward_key"])
    winners["prev_winning_party"] = prev["winning_party"].shift(1)
    winners["prev_margin"] = prev["margin"].shift(1)
    return winners.drop(columns="ward_key")


def main():
    winners = pd.read_csv(WINNERS)
    news = pd.read_csv(NEWS)

    winners = add_ward_history(winners)
    dataset = winners.merge(pre_election_features(news), on="year", how="left")
    dataset.to_csv(OUT, index=False)

    matched = dataset["prev_winning_party"].notna().mean()
    print(f"{len(dataset)} ward contests -> {OUT}")
    print(f"ward history available for {matched:.0%} of contests")

    # break the match rate down by year: 2021 has no earlier data to
    # match against, and the 2023 all-out councils last voted in 2019,
    # also out of range, so low years here point to a data-coverage
    # gap rather than a matching bug
    by_year = dataset.groupby("year").agg(
        contests=("ward", "count"),
        matched=("prev_winning_party", lambda s: s.notna().sum()))
    by_year["match_rate"] = (by_year["matched"] / by_year["contests"] * 100).round(0)
    print("\nWard history match rate by year:")
    print(by_year.to_string())

    # first look: national climate vs how the two big parties fared
    per_year = dataset.groupby("year").agg(
        wards=("ward", "count"),
        con_won=("winning_party", lambda s: (s == "Conservative").sum()),
        ld_won=("winning_party", lambda s: (s == "Liberal Democrats").sum()),
        con_mentions=("conservative_pre3m", "first"),
        energy_articles=("energy_pre3m", "first"),
        housing_articles=("housing_pre3m", "first"),
    )
    per_year["con_won_pct"] = (per_year["con_won"] / per_year["wards"] * 100).round(0)
    print("\nPre-election news climate vs wards won:")
    print(per_year.to_string())


if __name__ == "__main__":
    main()
