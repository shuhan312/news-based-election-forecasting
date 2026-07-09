"""Aggregate candidate-level election results into ward-level outcomes.

Turns results_2021_2024.csv (one row per candidate) into the tables a
prediction model actually needs:

  data/elections/ward_party_results.csv   one row per ward x party
  data/elections/ward_winners.csv         one row per ward, with the
                                          winning party, margin and turnout

In multi-seat wards a party fields several candidates, so summing their
votes would double-count voters. The usual convention is to score each
party by its best-placed candidate, and that is what we do here.

Usage:  python src/aggregate_results.py
"""

import re

import pandas as pd

IN_PATH = "data/elections/results_2017_2024.csv"
PARTY_OUT = "data/elections/ward_party_results.csv"
WINNER_OUT = "data/elections/ward_winners.csv"

# By-elections held after the scheduled election appear on the same
# Wikipedia page with the date in the table caption, e.g.
# "Addlestone South by-election, 21 August 2025". A date in the ward
# name is the reliable marker; the plain phrase "due to by-election"
# also appears on ordinary wards that elected an extra seat, so we
# must not filter on the word alone.
DATE_IN_NAME = re.compile(r"\d{1,2}\s+\w+\s+\d{4}")


def main():
    df = pd.read_csv(IN_PATH)
    before = len(df)

    df = df[~df["ward"].str.contains(DATE_IN_NAME, na=False)]
    print(f"dropped {before - len(df)} by-election rows, {len(df)} remain")

    # "Chertsey Meads (2 seats)" and "Ash Vale (top 2 candidates
    # elected)" are the same wards as their plain names
    df["ward"] = df["ward"].str.replace(
        r"\s*\((top\s+)?\d+\s*(seats?|candidates?)[^)]*\)", "",
        regex=True).str.strip()

    # party result in a ward = its best-placed candidate
    party = (df.groupby(["year", "council", "ward", "party"])
               .agg(votes=("votes", "max"), turnout=("turnout", "first"))
               .reset_index())
    ward_total = party.groupby(["year", "council", "ward"])["votes"].transform("sum")
    party["vote_share"] = (party["votes"] / ward_total * 100).round(1)

    party = party.sort_values(["year", "council", "ward", "votes"],
                              ascending=[True, True, True, False])
    party["won"] = ~party.duplicated(["year", "council", "ward"])  # top row per ward

    party.to_csv(PARTY_OUT, index=False)

    # one row per ward: winner, runner-up and the gap between them
    def summarise(g):
        return pd.Series({
            "winning_party": g.iloc[0]["party"],
            "winner_share": g.iloc[0]["vote_share"],
            "second_party": g.iloc[1]["party"] if len(g) > 1 else None,
            "margin": (g.iloc[0]["vote_share"] - g.iloc[1]["vote_share"]).round(1)
                      if len(g) > 1 else None,
            "n_parties": len(g),
            "turnout": g.iloc[0]["turnout"],
        })

    winners = (party.groupby(["year", "council", "ward"])
                    .apply(summarise, include_groups=False).reset_index())
    winners.to_csv(WINNER_OUT, index=False)

    print(f"{len(party)} ward x party rows -> {PARTY_OUT}")
    print(f"{len(winners)} wards -> {WINNER_OUT}")

    print("\nWards won per party per year:")
    table = (winners.groupby(["year", "winning_party"]).size()
                    .unstack(fill_value=0).T
                    .sort_values(2023, ascending=False))
    print(table.head(8).to_string())


if __name__ == "__main__":
    main()
