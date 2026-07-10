"""Run regression checks on the first-stage election cleaning pipeline.

This validator covers only the explicit by-election metadata added in the
first cleaning stage.  It does not yet validate party-name normalisation,
official source reconciliation, turnout rates, or multi-seat outcomes.

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


def main():
    raw = pd.read_csv(RAW_PATH)
    party = pd.read_csv(PARTY_PATH)
    winners = pd.read_csv(WINNER_PATH)

    required = {
        "event_type", "polling_date", "source_url", "source_table_index",
        "source_caption", "source_heading", "source_section",
    }
    assert required.issubset(raw.columns), "raw election metadata is incomplete"
    assert raw["event_type"].notna().all(), "event_type contains null values"
    assert set(raw["event_type"]).issubset(EVENT_TYPES), "unknown event type found"

    # Candidate rows from one source table must never disagree about whether
    # that table is scheduled or a by-election.
    assert raw.groupby(["source_url", "source_table_index"])["event_type"].nunique().eq(1).all()

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

    # Aggregated outputs must contain only scheduled tables and retain the
    # one-party-result / one-top-polling-party invariants of this prototype.
    assert not party.duplicated(["year", "council", "ward", "party"]).any()
    assert party.groupby(["year", "council", "ward"])["won"].sum().eq(1).all()
    assert not winners.duplicated(["year", "council", "ward"]).any()

    scheduled = raw.loc[raw["event_type"].eq("scheduled")].copy()
    scheduled["ward"] = scheduled["ward"].map(ward_key)
    expected_party = (scheduled.groupby(["year", "council", "ward", "party"])
                       .agg(votes=("votes", "max"))
                       .reset_index()
                       .sort_values(["year", "council", "ward", "party"])
                       .reset_index(drop=True))
    actual_party = (party[["year", "council", "ward", "party", "votes"]]
                    .sort_values(["year", "council", "ward", "party"])
                    .reset_index(drop=True))

    # Comparing party-level votes, rather than only ward keys, matters where
    # a scheduled contest and a later by-election share the same ward name.
    # Such a collision occurs for Hersham Village in the cached 2024 page.
    pd.testing.assert_frame_equal(actual_party, expected_party)

    print("PASS: by-election metadata and scheduled-election aggregation are consistent")
    print(raw["event_type"].value_counts().to_string())
    print(f"scheduled ward outcomes: {len(winners)}")


if __name__ == "__main__":
    main()
