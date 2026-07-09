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


def add_ward_history(winners):
    """Attach each ward's previous result (same council + ward name).

    Ward boundaries changed for some 2023 elections, so not every ward
    has a findable predecessor; those get NaN rather than a guess.
    """
    winners = winners.sort_values(["council", "ward", "year"])
    prev = winners.groupby(["council", "ward"])
    winners["prev_winning_party"] = prev["winning_party"].shift(1)
    winners["prev_margin"] = prev["margin"].shift(1)
    return winners


def main():
    winners = pd.read_csv(WINNERS)
    news = pd.read_csv(NEWS)

    winners = add_ward_history(winners)
    dataset = winners.merge(pre_election_features(news), on="year", how="left")
    dataset.to_csv(OUT, index=False)

    matched = dataset["prev_winning_party"].notna().mean()
    print(f"{len(dataset)} ward contests -> {OUT}")
    print(f"ward history available for {matched:.0%} of contests")

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
