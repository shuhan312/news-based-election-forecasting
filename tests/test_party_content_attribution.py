"""Tests for the party-grain content rebuild.

Two things need guarding, and they are different in kind.

The first is that nothing already committed moves. Every result in the
repository was computed from feature tables built with the per-election
aggregation, so `build_feature_table` must behave exactly as before whenever
`PARTY_CONTENT_ATTRIBUTION` is off. `test_feature_table_rebuild` carries the
byte-level half of that guarantee; what is asserted here is that the switch
defaults to off, which is what makes the byte test meaningful.

The second is that the rebuild actually changed the grain. A party-grain
column that still carries one value per election would mean the attribution
ran and found nothing, and the gate verdict would improve for the wrong
reason. The structural test therefore checks both directions in the same file:
per-election columns constant across the parties of a cell, party columns not.
"""

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from src.news_features.actor_party_attribution import (LEADERS,
                                                       parties_for_actors,
                                                       party_for_actor,
                                                       publication_date)

V2_CSV = Path("news_features/news_feature_table_v2.csv")
V3_CSV = Path("news_features/news_feature_table_v3party.csv")
V3_META = Path("news_features/news_feature_table_v3party_metadata.json")

# The corpus lives outside the index, so the build-dependent tests skip on a
# checkout that has the code but not the data.
needs_v3 = pytest.mark.skipif(not (V3_CSV.exists() and V3_META.exists()),
                              reason="v3party table not built")
needs_corpus = pytest.mark.skipif(
    not Path("llm_context/corpus_extraction_outputs_all.json").exists(),
    reason="extraction outputs not present")


# ---- actor mapping unit tests --------------------------------------

def test_party_names_come_from_the_repository_alias_table():
    assert party_for_actor("Labour") == "labour"
    assert party_for_actor("the Conservative Party") == "conservative"
    assert party_for_actor("Lib Dems") == "liberal_democrat"
    assert party_for_actor("Reform UK") == "reform_uk"


def test_an_unmatched_actor_maps_to_nothing():
    # SNP appears 77 times and is deliberately outside the six standard
    # parties; a mapping that quietly absorbed it would inflate a real party.
    assert party_for_actor("SNP") is None
    assert party_for_actor("") is None
    assert party_for_actor("   ") is None


def test_the_alias_table_is_not_widened_here():
    # PARTY_ALIASES matches "reform uk" and "reform party" but not a bare
    # "reform". Widening it for this feature would let a content column and a
    # portrayal column disagree about the same article.
    assert party_for_actor("Reform UK") == "reform_uk"
    assert party_for_actor("reform") is None


def test_leaders_resolve_to_their_party():
    assert party_for_actor("Keir Starmer") == "labour"
    assert party_for_actor("Theresa May") == "conservative"
    assert party_for_actor("Ed Davey") == "liberal_democrat"
    # Every leader listed must map to a party the alias table knows, or the
    # two rules would disagree about which parties exist.
    from src.llm_extraction.stance_rescue import PARTY_ALIASES
    assert set(LEADERS.values()) <= set(PARTY_ALIASES)


def test_farage_is_resolved_from_the_article_date():
    # UKIP leader, and UKIP's most identified figure through the 2017 county
    # election, which UKIP contested.
    assert party_for_actor("Nigel Farage", date(2013, 5, 2)) == "ukip"
    assert party_for_actor("Nigel Farage", date(2017, 5, 4)) == "ukip"
    # Brexit Party: registered 2019-02-08, not one of the six, so nobody.
    assert party_for_actor("Nigel Farage", date(2019, 6, 1)) is None
    # Reform UK from the 2021-01-06 rename onwards.
    assert party_for_actor("Nigel Farage", date(2021, 5, 6)) == "reform_uk"
    assert party_for_actor("Nigel Farage", date(2026, 5, 7)) == "reform_uk"
    # No date is no attribution: the whole point is that it depends on when.
    assert party_for_actor("Nigel Farage") is None


def test_actor_list_collapses_to_a_set_of_parties():
    # One article naming a party and its leader is one article about that
    # party, not two.
    assert parties_for_actors(["Labour", "Keir Starmer"]) == {"labour"}
    # Naming two parties counts for both: it genuinely bears on both.
    assert parties_for_actors(["Labour", "Reform UK"]) == {"labour", "reform_uk"}
    assert parties_for_actors([]) == set()
    assert parties_for_actors(None) == set()


def test_publication_date_is_parsed_or_refused():
    assert publication_date({"publication_datetime": "2021-05-02"}) == date(2021, 5, 2)
    assert publication_date({"publication_datetime": "2021-05-02T09:00:00Z"}) == date(2021, 5, 2)
    assert publication_date({"publication_datetime": ""}) is None
    assert publication_date({}) is None
    assert publication_date({"publication_datetime": "not-a-date"}) is None


# ---- the switch must stay off by default ---------------------------

def test_the_attribution_switch_is_off_by_default():
    # v1 and v2 are built by importing this module and rebinding globals, so a
    # default of True would silently add columns to both.
    from src.news_features import build_feature_table as frozen
    assert frozen.PARTY_CONTENT_ATTRIBUTION is False
    assert frozen.EXCLUDED_TRANCHES == set()


# ---- the rebuild changed the grain ---------------------------------

def _window_cells(rows):
    cells = {}
    for r in rows:
        if r["period_kind"] == "window":
            cells.setdefault((r["election_id"], r["period"]), []).append(r)
    return cells


def _constant_across_parties(cells, prefix):
    """(cells whose columns are constant across parties, cells with data)."""
    columns = None
    constant = live = 0
    for group in cells.values():
        if columns is None:
            columns = [c for c in group[0]
                       if c.startswith(prefix) and c.endswith("_share")]
        if not any(r[c] != "" for r in group for c in columns):
            continue
        live += 1
        if all(len({r[c] for r in group}) == 1 for c in columns):
            constant += 1
    return constant, live


@needs_v3
def test_per_election_columns_stay_constant_across_parties():
    """The defect, still present in the columns that carry it.

    This is not a regression guard, it is the control: the per-election
    columns are meant to be identical for every party in a cell, and the
    party columns are compared against exactly this.
    """
    cells = _window_cells(list(csv.DictReader(V3_CSV.open())))
    for prefix in ("issue_", "frame_"):
        constant, live = _constant_across_parties(cells, prefix)
        assert live > 0
        assert constant == live, (
            f"{prefix}: {constant} of {live} cells constant across parties; "
            f"the per-election aggregation should make this all of them")


@needs_v3
def test_party_columns_vary_across_parties():
    cells = _window_cells(list(csv.DictReader(V3_CSV.open())))
    for prefix in ("party_issue_", "party_frame_"):
        constant, live = _constant_across_parties(cells, prefix)
        assert live > 0
        assert constant == 0, (
            f"{prefix}: {constant} of {live} cells still carry one value for "
            f"every party. The attribution did not change the grain.")


@needs_v3
def test_the_gate_verdict_improves_for_the_content_columns():
    """Every party-grain column must beat its per-election twin.

    Counted within a period, which is the rule the builder applies: a
    specification uses one window, so variation between windows is not
    variation the fit can see.
    """
    train = [r for r in csv.DictReader(V3_CSV.open())
             if r["split_role"] == "train"]
    by_period = {}
    for r in train:
        by_period.setdefault(r["period"], []).append(r)

    def best(column):
        return max(len({r[column] for r in group if r[column] != ""})
                   for group in by_period.values())

    twins = [(c, f"party_{c}") for c in train[0]
             if c.startswith(("issue_", "frame_")) and c.endswith("_share")]
    assert twins

    # `issue_none` counts articles the taxonomy gave no primary issue. It is
    # residual bookkeeping rather than a content feature, and it moves the
    # other way - 4 distinct values to 2 - because an article with no
    # political issue usually names no actors either, so attribution drops it.
    # That is the mechanism working, not failing, and the column is exempt by
    # name rather than by a threshold that would quietly cover a real failure.
    RESIDUAL = {"issue_none_share"}

    improved, empty = [], []
    for election_column, party_column in twins:
        if election_column in RESIDUAL:
            continue
        # A column with one distinct value at election grain has no content
        # to redistribute - crime_policing and housing_planning are genuinely
        # near-absent from this corpus, and re-grained they stay that way.
        # Asserting they improve would assert the corpus holds something it
        # does not; asserting they do NOT is what catches invented coverage.
        if best(election_column) <= 1:
            empty.append(election_column)
            assert best(party_column) <= 1, (
                f"{party_column} gained variation its per-election twin does "
                f"not have; the attribution is inventing coverage")
            continue
        improved.append(election_column)
        assert best(party_column) > best(election_column), (
            f"{party_column} has no more training variation than "
            f"{election_column}")

    # Guard the guard: if every column landed in an exempt bucket the test
    # would pass while proving nothing. Eight improve, two are empty.
    assert len(improved) == 8 and len(empty) == 2


@needs_v3
def test_attribution_rate_and_multiplier_are_recorded():
    """An attribution rate is not recoverable from the table afterwards."""
    meta = json.loads(V3_META.read_text())
    a = meta["party_content_attribution"]
    assert a["articles_attributed"] > 0
    assert (a["articles_attributed"] + a["articles_no_party_found"]
            == a["articles_with_issue_record"])
    # An article naming two parties counts for both, so the party-level cells
    # hold more coded articles than there are attributed articles.
    assert a["party_cell_multiplier"] > 1
