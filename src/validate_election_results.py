"""Run regression checks on the first-stage election cleaning pipeline.

This validator covers election type, party aliases, seat fields and turnout
fields used by the election pipeline.

Run after:
    python3 src/fetch_election_results.py
    python3 src/aggregate_results.py
"""

import re

import pandas as pd


RAW_PATH = "data/elections/results_2017_2024.csv"
PARTY_PATH = "data/elections/ward_party_results.csv"
WINNER_PATH = "data/elections/ward_winners.csv"

EVENT_TYPES = {"scheduled", "by_election"}
DUE_TO_BY_ELECTION = re.compile(
    r"\bdue\s+to\s+(?:an?\s+)?by[-\s]?election\b", re.IGNORECASE)
TURNOUT_COLUMNS = [
    "people_who_voted",
    "registered_voters",
    "turnout_percent",
    "turnout_data_source",
    "turnout_is_reliable",
]
TURNOUT_SOURCES = {
    "wikipedia_reported_turnout_percent",
    "wikipedia_reported_turnout_percent_needs_review",
    "calculated_from_people_and_registered_voters",
    "wikipedia_people_who_voted_only",
    "wikipedia_registered_voters_only",
    "missing",
    "conflicting_source_tables",
}


def ward_key(ward):
    """Match the same normalisation used before aggregating regular wards."""
    return re.sub(r"\s*\((top\s+)?\d+\s*(seats?|candidates?)[^)]*\)", "",
                  ward).strip()


def assert_event(raw, council, heading_text, expected):
    """Check a known tricky source table keeps its intended classification."""
    rows = raw.loc[(raw["council"] == council) &
                   raw["source_heading"].str.contains(heading_text,
                                                       case=False, na=False)]
    assert not rows.empty, f"Regression table not found: {heading_text}"
    assert set(rows["event_type"]) == {expected}, (
        heading_text, set(rows["event_type"]))


def assert_turnout_fields(frame, name, allow_conflicts=False):
    """Check the friendly turnout fields and their possible values."""
    assert set(TURNOUT_COLUMNS).issubset(frame.columns), (
        f"{name} turnout fields are incomplete")
    assert "turnout" not in frame.columns, (
        f"{name} still contains the ambiguous turnout column")

    people = frame["people_who_voted"].dropna()
    registered = frame["registered_voters"].dropna()
    percent = frame["turnout_percent"].dropna()
    assert (people.ge(0) & people.mod(1).eq(0)).all(), (
        f"{name} has an invalid people_who_voted value")
    assert (registered.gt(0) & registered.mod(1).eq(0)).all(), (
        f"{name} has an invalid registered_voters value")
    assert percent.between(0, 100).all(), (
        f"{name} has an invalid turnout_percent value")
    assert frame["turnout_is_reliable"].notna().all(), (
        f"{name} has a missing turnout_is_reliable value")
    assert frame.loc[frame["turnout_is_reliable"],
                     "turnout_percent"].notna().all(), (
        f"{name} marks a missing percentage as reliable")

    allowed_sources = TURNOUT_SOURCES.copy()
    if not allow_conflicts:
        allowed_sources.remove("conflicting_source_tables")
    assert set(frame["turnout_data_source"].dropna()).issubset(allowed_sources), (
        f"{name} has an unknown turnout_data_source")

    calculated = frame["turnout_data_source"].eq(
        "calculated_from_people_and_registered_voters")
    if calculated.any():
        rows = frame.loc[calculated]
        assert rows[["people_who_voted", "registered_voters",
                     "turnout_percent"]].notna().all().all()
        expected = rows["people_who_voted"] / rows["registered_voters"] * 100
        assert rows["turnout_percent"].sub(expected).abs().le(0.02).all()
        assert rows["turnout_is_reliable"].all()

    people_only = frame["turnout_data_source"].eq(
        "wikipedia_people_who_voted_only")
    if people_only.any():
        rows = frame.loc[people_only]
        assert rows["people_who_voted"].notna().all()
        assert rows["turnout_percent"].isna().all()
        assert (~rows["turnout_is_reliable"]).all()

    missing = frame["turnout_data_source"].eq("missing")
    if missing.any():
        rows = frame.loc[missing]
        assert rows[["people_who_voted", "registered_voters",
                     "turnout_percent"]].isna().all().all()
        assert (~rows["turnout_is_reliable"]).all()

    conflicts = frame["turnout_data_source"].eq("conflicting_source_tables")
    if conflicts.any():
        assert allow_conflicts, f"{name} has an unexpected source conflict"
        rows = frame.loc[conflicts]
        assert rows[["people_who_voted", "registered_voters",
                     "turnout_percent"]].isna().all().all()
        assert (~rows["turnout_is_reliable"]).all()


def main():
    raw = pd.read_csv(RAW_PATH)
    party = pd.read_csv(PARTY_PATH)
    winners = pd.read_csv(WINNER_PATH)

    required = {
        "event_type", "polling_date", "source_url", "source_table_index",
        "source_caption", "source_heading", "source_section",
        "party_raw", "party_canonical", "candidate_vote_share",
        "candidate_rank", "candidate_elected", "seats_contested",
        *TURNOUT_COLUMNS,
    }
    assert required.issubset(raw.columns), "raw election metadata is incomplete"
    assert raw["event_type"].notna().all(), "event_type contains null values"
    assert set(raw["event_type"]).issubset(EVENT_TYPES), "unknown event type found"
    assert_turnout_fields(raw, "raw")

    # These aliases are the minimum contract for the canonical party field.
    # The raw spelling remains available for audit and future remapping.
    expected_aliases = {
        "Reform": "Reform UK",
        "Labour Co-op": "Labour",
        "Liberal Democrat": "Liberal Democrats",
        "Green Party": "Green",
    }
    for raw_label, canonical in expected_aliases.items():
        rows = raw.loc[raw["party_raw"].eq(raw_label)]
        if not rows.empty:
            assert rows["party_canonical"].eq(canonical).all(), raw_label

    # Candidate rows from one source table must never disagree about whether
    # that table is scheduled or a by-election.
    assert raw.groupby(["source_url", "source_table_index"])["event_type"].nunique().eq(1).all()

    # All candidates from one source table share the same turnout information.
    table_keys = ["source_url", "source_table_index"]
    turnout_consistency = raw.groupby(table_keys)[TURNOUT_COLUMNS].nunique(
        dropna=False)
    assert turnout_consistency.eq(1).all().all(), (
        "turnout fields disagree within a source table")

    # Regression checks for the layouts found by the turnout audit.
    rate_only = raw.loc[(raw["year"] == 2018) &
                        raw["council"].eq("Mole Valley District Council") &
                        raw["ward"].eq("Ashtead Common")]
    assert rate_only["people_who_voted"].isna().all()
    assert rate_only["turnout_percent"].eq(43.3).all()
    assert rate_only["turnout_is_reliable"].all()

    people_only = raw.loc[(raw["year"] == 2018) &
                          raw["council"].eq("Woking Borough Council") &
                          raw["ward"].eq("Byfleet and West Byfleet")]
    assert people_only["people_who_voted"].eq(2880).all()
    assert people_only["turnout_percent"].isna().all()
    assert (~people_only["turnout_is_reliable"]).all()

    onslow = raw.loc[(raw["year"] == 2023) &
                     raw["council"].eq("Guildford Borough Council") &
                     raw["ward"].eq("Onslow (3 seats)")]
    assert onslow["people_who_voted"].eq(2196).all()
    assert onslow["turnout_percent"].eq(43.6).all()
    assert onslow["votes"].sum() == 6335

    # Explicit by-election rows should have a usable date; scheduled tables
    # may legitimately have no date in their local Wikipedia heading/caption.
    by_elections = raw[raw["event_type"].eq("by_election")]
    assert by_elections["polling_date"].notna().all(), "a by-election lacks polling_date"

    # A vacancy note is not itself a by-election result table.
    due_to = raw["source_caption"].fillna("").str.contains(DUE_TO_BY_ELECTION)
    assert due_to.any(), "expected a scheduled vacancy-note regression case"
    assert raw.loc[due_to, "event_type"].eq("scheduled").all()

    # These cover the two historical failure modes: a plain caption under a
    # 'By-elections' section, and an explicit local by-election heading.
    assert_event(raw, "Surrey Heath Borough Council", r"Bagshot \(6 May 2021\)",
                 "by_election")
    assert_event(raw, "Elmbridge Borough Council", r"Cobham.*by-election",
                 "by_election")

    # An absent seat count is allowed when Wikipedia omits it, but a present
    # value must be a positive whole number.
    known_seats = raw["seats_contested"].dropna()
    assert (known_seats.ge(1) & known_seats.mod(1).eq(0)).all()

    table_seats = raw.dropna(subset=["seats_contested"])
    resolved_tables = table_seats.groupby(table_keys).filter(
        lambda group: group["candidate_elected"].notna().all())
    elected_per_table = resolved_tables.groupby(table_keys)["candidate_elected"].sum()
    seats_per_table = resolved_tables.groupby(table_keys)["seats_contested"].first()
    assert elected_per_table.eq(seats_per_table).all(), "candidate seats do not match table seats"

    # Aggregated outputs must contain only scheduled tables and retain the
    # one-party-result / one-top-polling-party invariants of this prototype.
    assert not party.duplicated(["year", "council", "ward", "party"]).any()
    ward_keys = ["year", "council", "ward"]
    assert_turnout_fields(party, "party results", allow_conflicts=True)
    assert_turnout_fields(winners, "ward results", allow_conflicts=True)
    assert party.groupby(ward_keys)[TURNOUT_COLUMNS].nunique(
        dropna=False).eq(1).all().all()
    assert party.groupby(ward_keys)["is_top_polling_party"].sum().eq(1).all()
    assert not winners.duplicated(["year", "council", "ward"]).any()
    assert winners["top_polling_party"].eq(winners["winning_party"]).all()
    assert winners["best_candidate_margin"].eq(winners["margin"]).all()
    known_party_seats = party.loc[party["seat_results_known"]]
    assert (known_party_seats.groupby(ward_keys)["party_seats_won"].sum()
            .eq(known_party_seats.groupby(ward_keys)["seats_contested"].first())).all()

    # A copied Wikipedia caption produces two source tables for this ward.
    # Aggregation must mark turnout as unresolved rather than choose one.
    banstead_party = party.loc[(party["year"] == 2022) &
                               party["council"].eq(
                                   "Reigate and Banstead Borough Council") &
                               party["ward"].eq("Banstead Village")]
    assert not banstead_party.empty
    assert banstead_party["turnout_data_source"].eq(
        "conflicting_source_tables").all()
    assert banstead_party["turnout_percent"].isna().all()
    assert (~banstead_party["turnout_is_reliable"]).all()

    scheduled = raw.loc[raw["event_type"].eq("scheduled")].copy()
    scheduled["ward"] = scheduled["ward"].map(ward_key)
    expected_party = (scheduled.groupby(["year", "council", "ward", "party_canonical"])
                       .agg(best_candidate_votes=("votes", "max"))
                       .reset_index()
                       .rename(columns={"party_canonical": "party"})
                       .sort_values(["year", "council", "ward", "party"])
                       .reset_index(drop=True))
    actual_party = (party[["year", "council", "ward", "party", "best_candidate_votes"]]
                    .sort_values(["year", "council", "ward", "party"])
                    .reset_index(drop=True))

    # Comparing party-level votes, rather than only ward keys, matters where
    # a scheduled contest and a later by-election share the same ward name.
    # Such a collision occurs for Hersham Village in the cached 2024 page.
    pd.testing.assert_frame_equal(actual_party, expected_party)

    print("PASS: election types, turnout fields and aggregation are consistent")
    print(raw["event_type"].value_counts().to_string())
    print(f"scheduled ward outcomes: {len(winners)}")


if __name__ == "__main__":
    main()
