"""Aggregate scheduled-election candidate results into ward-level outcomes.

Turns results_2021_2024.csv (one row per candidate) into the tables a
prediction model actually needs:

  data/elections/ward_party_results.csv   one row per ward x party
  data/elections/ward_winners.csv         one row per ward, with the
                                          winning party, margin and turnout

In multi-seat wards a party fields several candidates, so summing their
votes would double-count voters. The usual convention is to score each
party by its best-placed candidate, and that is what we do here.

By-elections are deliberately excluded.  The extractor records an explicit
event_type from the Wikipedia table's caption and headings, which is safer
than trying to detect a by-election from the ward name.

Usage:  python src/aggregate_results.py
"""

import pandas as pd

IN_PATH = "data/elections/results_2017_2024.csv"
PARTY_OUT = "data/elections/ward_party_results.csv"
WINNER_OUT = "data/elections/ward_winners.csv"

def main():
    df = pd.read_csv(IN_PATH)
    # Fail rather than silently recreating the old, date-in-ward-name rule.
    # The raw file must be regenerated with fetch_election_results.py first.
    required = {"event_type", "polling_date"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(
            "Missing election metadata " + ", ".join(sorted(missing)) +
            ". Rerun src/fetch_election_results.py before aggregating.")

    valid_types = {"scheduled", "by_election"}
    observed_types = set(df["event_type"].dropna())
    if df["event_type"].isna().any() or not observed_types.issubset(valid_types):
        raise ValueError(
            "event_type must contain only 'scheduled' or 'by_election'; "
            f"found {sorted(observed_types)}.")

    before = len(df)
    df = df.loc[df["event_type"].eq("scheduled")].copy()
    print(f"excluded {before - len(df)} by-election candidate rows; "
          f"{len(df)} scheduled-election rows remain")

    # "Chertsey Meads (2 seats)" and "Ash Vale (top 2 candidates
    # elected)" are the same wards as their plain names
    df["ward"] = df["ward"].str.replace(
        r"\s*\((top\s+)?\d+\s*(seats?|candidates?)[^)]*\)", "",
        regex=True).str.strip()

    # Party result in a ward = its best-placed candidate.
    # TODO (next data-quality stage): this is a best-candidate proxy, not a
    # literal party vote share in a multi-seat ward.
    party = (df.groupby(["year", "council", "ward", "party_canonical"])
               .agg(votes=("votes", "max"), turnout=("turnout", "first"))
               .reset_index())

    # Keep the raw spellings visible for audit, while using the canonical
    # label as the stable output name.  Multiple raw aliases can map to one
    # canonical party, so they are recorded as a semicolon-separated list.
    raw_labels = (df.groupby(["year", "council", "ward", "party_canonical"])["party_raw"]
                   .agg(lambda values: "; ".join(sorted(set(values))))
                   .rename("party_raw_labels")
                   .reset_index())
    party = party.merge(raw_labels,
                        on=["year", "council", "ward", "party_canonical"],
                        how="left")
    party = party.rename(columns={"party_canonical": "party"})
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
