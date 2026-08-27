"""Aggregate scheduled-election candidate results into ward-level outcomes.

Turns results_2017_2024.csv (one row per candidate) into the tables a
prediction model actually needs:

  data/elections/ward_party_results.csv   one row per ward x party
  data/elections/ward_winners.csv         one row per ward, with its
                                          top-polling party and seat summary

In multi-seat wards a party fields several candidates, so summing their
votes would double-count voters. We therefore score each party by its
best-placed candidate. The resulting share is explicitly named a
best-candidate share; it is not a complete party vote share.

By-elections are deliberately excluded.  The extractor records an explicit
event_type from the Wikipedia table's caption and headings, which is safer
than trying to detect a by-election from the ward name.

Usage:  python src/aggregate_results.py
"""

import pandas as pd

IN_PATH = "data/elections/results_2017_2024.csv"
PARTY_OUT = "data/elections/ward_party_results.csv"
WINNER_OUT = "data/elections/ward_winners.csv"

TURNOUT_COLUMNS = [
    "people_who_voted",
    "registered_voters",
    "turnout_percent",
    "turnout_data_source",
    "turnout_is_reliable",
]


def resolve_ward_turnout(df, ward_keys):
    """Keep one turnout record per ward, or flag conflicting source tables."""
    table_keys = ward_keys + ["source_url", "source_table_index"]

    # Candidate rows from the same source table must carry the same values.
    consistency = (df.groupby(table_keys)[TURNOUT_COLUMNS]
                   .nunique(dropna=False))
    if consistency.gt(1).any().any():
        raise ValueError("Turnout fields disagree within a source table")

    by_table = (df.groupby(table_keys)[TURNOUT_COLUMNS]
                .first()
                .reset_index())

    def one_ward(group):
        if len(group) > 1:
            # Do not choose one value when two source tables have the same
            # year/council/ward key.  The audit file records these cases.
            return pd.Series({
                "people_who_voted": pd.NA,
                "registered_voters": pd.NA,
                "turnout_percent": pd.NA,
                "turnout_data_source": "conflicting_source_tables",
                "turnout_is_reliable": False,
            })
        return group.iloc[0][TURNOUT_COLUMNS]

    return (by_table.groupby(ward_keys)
            .apply(one_ward, include_groups=False)
            .reset_index())

def main():
    df = pd.read_csv(IN_PATH)
    # Fail rather than silently recreating the old, date-in-ward-name rule.
    # The raw file must be regenerated with fetch_election_results.py first.
    required = {
        "event_type", "polling_date", "party_raw", "party_canonical",
        "candidate_vote_share", "candidate_rank", "candidate_elected",
        "seats_contested", *TURNOUT_COLUMNS,
    }
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

    ward_keys = ["year", "council", "ward"]
    # A tie at the final available seat cannot be resolved from the cached
    # table alone.  Mark every party result in that ward as unknown rather
    # than reporting a partial, misleading seat allocation.
    seat_status = (df.groupby(ward_keys)["candidate_elected"]
                   .agg(seat_results_known=lambda values: values.notna().all())
                   .reset_index())
    df = df.merge(seat_status, on=ward_keys, how="left")
    ward_turnout = resolve_ward_turnout(df, ward_keys)

    # Party result in a ward = its best-placed candidate.  This avoids adding
    # several candidates' votes together in a multi-seat election.
    party_keys = ["year", "council", "ward", "party_canonical"]
    party = (df.groupby(party_keys)
               .agg(best_candidate_votes=("votes", "max"),
                    seats_contested=("seats_contested", "first"),
                    seat_results_known=("seat_results_known", "first"))
               .reset_index())
    party = party.merge(ward_turnout, on=ward_keys, how="left")

    elected_counts = (df.loc[df["candidate_elected"].eq(True)]
                      .groupby(party_keys).size()
                      .rename("party_seats_won").reset_index())
    party = party.merge(elected_counts, on=party_keys, how="left")
    party["party_seats_won"] = party["party_seats_won"].fillna(0).astype("Int64")
    party.loc[~party["seat_results_known"], "party_seats_won"] = pd.NA

    # Keep the raw spellings visible for audit, while using the canonical
    # label as the stable output name.  Multiple raw aliases can map to one
    # canonical party, so they are recorded as a semicolon-separated list.
    raw_labels = (df.groupby(party_keys)["party_raw"]
                   .agg(lambda values: "; ".join(sorted(set(values))))
                   .rename("party_raw_labels")
                   .reset_index())
    party = party.merge(raw_labels,
                        on=party_keys,
                        how="left")
    party = party.rename(columns={"party_canonical": "party"})
    ward_total = (party.groupby(ward_keys)["best_candidate_votes"]
                  .transform("sum"))
    party["best_candidate_share"] = (
        party["best_candidate_votes"] / ward_total * 100).round(1)

    party = party.sort_values(["year", "council", "ward", "best_candidate_votes"],
                              ascending=[True, True, True, False])
    party["is_top_polling_party"] = ~party.duplicated(
        ward_keys)  # one top candidate party per ward

    party.to_csv(PARTY_OUT, index=False)

    # One row per ward.  The explicit fields describe the best-candidate
    # proxy.  Legacy aliases are retained so the committed tables keep their
    # frozen byte-identical form; their original consumer
    # (build_model_dataset.py) is retired to Git history.
    def summarise(g):
        top_share = g.iloc[0]["best_candidate_share"]
        second_party = g.iloc[1]["party"] if len(g) > 1 else None
        margin = (top_share - g.iloc[1]["best_candidate_share"]).round(1) \
                 if len(g) > 1 else None
        return pd.Series({
            "top_polling_party": g.iloc[0]["party"],
            "top_party_best_candidate_share": top_share,
            "second_top_polling_party": second_party,
            "best_candidate_margin": margin,
            "n_parties": len(g),
            "seats_contested": g.iloc[0]["seats_contested"],
            "seat_results_known": g.iloc[0]["seat_results_known"],
            "seats_awarded": (int(g["party_seats_won"].sum())
                               if g.iloc[0]["seat_results_known"] else None),
            "top_party_seats_won": g.iloc[0]["party_seats_won"],
            "people_who_voted": g.iloc[0]["people_who_voted"],
            "registered_voters": g.iloc[0]["registered_voters"],
            "turnout_percent": g.iloc[0]["turnout_percent"],
            "turnout_data_source": g.iloc[0]["turnout_data_source"],
            "turnout_is_reliable": g.iloc[0]["turnout_is_reliable"],
            # Backwards-compatible aliases: these do not mean every seat was
            # won by one party in a multi-seat ward.
            "winning_party": g.iloc[0]["party"],
            "winner_share": top_share,
            "second_party": second_party,
            "margin": margin,
        })

    winners = (party.groupby(ward_keys)
                    .apply(summarise, include_groups=False).reset_index())
    winners.to_csv(WINNER_OUT, index=False)

    print(f"{len(party)} ward x party rows -> {PARTY_OUT}")
    print(f"{len(winners)} wards -> {WINNER_OUT}")

    print("\nWards with top-polling party per year:")
    table = (winners.groupby(["year", "top_polling_party"]).size()
                    .unstack(fill_value=0).T
                    .sort_values(2023, ascending=False))
    print(table.head(8).to_string())


if __name__ == "__main__":
    main()
