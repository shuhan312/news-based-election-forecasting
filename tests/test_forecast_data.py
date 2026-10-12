"""Data tests for direction 1 (forecast.elections, forecast.polls).

Unit tests use hand-made ballots and HTML. They check the cleaning rules
(top-candidate method, by-elections and uncontested seats dropped, joint
party labels normalised, boundary fallback) and, above all, that no feature
can see the votes it is used to predict. The integration tests at the end
check the built units file and the committed poll table. They skip when the
gitignored election cache has not been built.
"""

import copy
import csv
import random
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from forecast import elections as el
from forecast.polls import end_date, expand_table, load_polls, poll_average


def cand(party, votes, elected=False, pid=None):
    return {"party": party, "votes": votes, "elected": elected,
            "person_id": pid if pid is not None else random.random()}


def ballot(ward, cands, seats=1, by=False):
    return {"ballot_id": f"local.x.{ward}{'.by' if by else ''}.2021",
            "by_election": by, "ward_id": ward, "ward_label": ward,
            "winner_count": seats, "candidates": cands}


# --- cleaning rules ------------------------------------------------------------------

def test_top_candidate_method_and_independents():
    b = ballot("w", [cand("PP52", 600, True), cand("PP52", 550, True),
                     cand("PP53", 400), cand("ynmp-party:2", 100, pid=1),
                     cand("ynmp-party:2", 100, pid=2)], seats=2)
    assert el.best_votes(b) == {"CON": 600, "LAB": 400, "OTH": 200}
    assert sum(el.ward_shares(b).values()) == pytest.approx(100)


def test_joint_labour_coop_label_counts_as_labour():
    assert el.party_code("joint-party:53-119") == "LAB"
    assert el.party_code("PP99999") == "OTH"


def test_missing_vote_count_makes_the_ward_unusable():
    assert el.ward_shares(ballot("w", [cand("PP52", None),
                                       cand("PP53", 3)])) is None


# --- unit construction ------------------------------------------------------------------

PREV = [
    ballot("w1", [cand("PP52", 600, True, pid="alice"), cand("PP53", 400)]),
    ballot("w2", [cand("PP52", 300), cand("PP53", 700, True, pid="bob")]),
    ballot("w9", [cand("PP90", 50, True)], by=True),     # by-election
]
CURR = [
    # w1: same ward; Reform stands for the first time; Alice re-stands.
    ballot("w1", [cand("PP52", 500, pid="alice"), cand("PP53", 300),
                  cand("PP7931", 200)]),
    # w3: a new ward (boundary change): no match, council fallback.
    ballot("w3", [cand("PP52", 450), cand("PP53", 550)]),
    # w4: uncontested, so no votes were cast and it is dropped.
    ballot("w4", [cand("PP90", 0, True)]),
    # A same-day by-election, dropped too.
    ballot("w5", [cand("PP52", 10), cand("PP53", 20)], by=True),
]


def units():
    return el.build_round("r", "x", "NMD", copy.deepcopy(PREV),
                          copy.deepcopy(CURR),
                          polls_prev={"CON": 40.0, "LAB": 35.0},
                          polls_curr={"CON": 30.0, "LAB": 40.0})


def test_by_elections_and_uncontested_wards_are_dropped():
    wards = {u["ward_id"] for u in units()}
    assert wards == {"w1", "w3"}


def test_matched_ward_uses_its_own_previous_result():
    w1 = {u["party"]: u for u in units() if u["ward_id"] == "w1"}
    assert w1["CON"]["share_prev"] == pytest.approx(60.0)
    assert w1["CON"]["boundary_fallback"] == 0


def test_boundary_change_falls_back_to_council_share_and_is_flagged():
    w3 = {u["party"]: u for u in units() if u["ward_id"] == "w3"}
    # Council-wide t-1: CON 900 / LAB 1100 of 2000 (by-election excluded).
    assert w3["CON"]["share_prev"] == pytest.approx(45.0)
    assert w3["CON"]["boundary_fallback"] == 1


def test_old_style_ids_match_by_name_but_gss_codes_never_do():
    prev = [ballot("KEN:ashford", [cand("PP52", 600), cand("PP53", 400)]),
            ballot("gss:E1", [cand("PP52", 100), cand("PP53", 900)])]
    for b, label in zip(prev, ("Ashford", "Dover")):
        b["ward_label"] = label
    curr = [ballot("gss:E9", [cand("PP52", 500), cand("PP53", 500)]),
            ballot("gss:E2", [cand("PP52", 500), cand("PP53", 500)])]
    curr[0]["ward_label"], curr[1]["ward_label"] = "Ashford", "Dover"
    rows = {(u["ward_id"], u["party"]): u
            for u in el.build_round("r", "x", "CTY", prev, curr)}
    # Old local id, same name: matched by name, keeps its own history.
    assert rows[("gss:E9", "CON")]["match_type"] == "label"
    assert rows[("gss:E9", "CON")]["share_prev"] == pytest.approx(60.0)
    # Both GSS, different codes: a real boundary change, not matched by name.
    assert rows[("gss:E2", "CON")]["match_type"] == "fallback"


def test_cold_start_and_incumbency():
    w1 = {u["party"]: u for u in units() if u["ward_id"] == "w1"}
    assert w1["REF"]["cold_start"] == 1 and w1["CON"]["cold_start"] == 0
    assert w1["CON"]["incumbent_standing"] == 1      # Alice won w1 at t-1
    assert w1["LAB"]["incumbent_standing"] == 0


def test_poll_features_and_blanks_for_unpolled_parties():
    w1 = {u["party"]: u for u in units() if u["ward_id"] == "w1"}
    assert w1["CON"]["poll_change"] == pytest.approx(-10.0)
    assert w1["REF"]["poll_curr"] == ""              # not in the poll map


def test_unit_shares_sum_to_100_per_contest():
    totals = {}
    for u in units():
        totals[u["ballot_id"]] = totals.get(u["ballot_id"], 0) + u["share"]
    assert all(t == pytest.approx(100, abs=0.01) for t in totals.values())


def test_no_feature_can_see_the_votes_it_predicts():
    """Scramble every vote at t: the outcome must change, every feature must
    not. This is the leakage test."""
    scrambled = copy.deepcopy(CURR)
    for b in scrambled:
        for c in b["candidates"]:
            c["votes"] = random.randint(1, 10_000)
    a = el.build_round("r", "x", "NMD", copy.deepcopy(PREV), copy.deepcopy(CURR))
    b = el.build_round("r", "x", "NMD", copy.deepcopy(PREV), scrambled)
    features = [k for k in a[0] if k != "share"]
    assert [{k: u[k] for k in features} for u in a] == \
           [{k: u[k] for k in features} for u in b]


def test_test_round_cannot_be_fetched_before_freeze():
    with pytest.raises(PermissionError):
        el.fetch_ballots("local.kent.2025-05-01")


# --- polls ----------------------------------------------------------------------------

def test_merged_cells_are_expanded_so_values_stay_under_their_header():
    html = """<table>
      <tr><th>Dates</th><th>Pollster</th><th>Area</th><th>Con</th><th>Lab</th></tr>
      <tr><td>1 May</td><td>A</td><td rowspan="2">GB</td><td>40%</td><td>30%</td></tr>
      <tr><td>2 May</td><td>B</td><td>41%</td><td>31%</td></tr>
    </table>"""
    grid = expand_table(BeautifulSoup(html, "html.parser").find("table"))
    assert grid[2] == ["2 May", "B", "GB", "41%", "31%"]


def test_end_date_takes_the_last_day_of_fieldwork():
    assert str(end_date("28– 30 Dec", 2023)) == "2023-12-30"
    assert str(end_date("29 Apr – 1 May", 2021)) == "2021-05-01"
    assert str(end_date("4 Jul 2024", 1999)) == "2024-07-04"
    assert end_date("Seat projection", 2020) is None


def test_poll_average_uses_only_polls_before_polling_day():
    polls = [{"end_date": "2021-04-24", "CON": "40"},
             {"end_date": "2021-05-05", "CON": "42"},
             {"end_date": "2021-05-06", "CON": "99"},    # polling day itself
             {"end_date": "2021-05-07", "CON": "99"},    # after the vote
             {"end_date": "2021-04-01", "CON": "99"}]    # outside 14 days
    assert poll_average(polls, "2021-05-06", "CON") == pytest.approx(41.0)


# --- integration: committed poll table and built units -------------------------------

def test_committed_polls_cover_every_polling_day():
    polls = load_polls()
    for day in ("2017-05-04", "2018-05-03", "2019-05-02", "2021-05-06",
                "2022-05-05", "2023-05-04", "2025-05-01"):
        assert poll_average(polls, day, "CON") is not None, day


UNITS = Path("data/forecast/units_train.csv")


@pytest.mark.skipif(not UNITS.exists(), reason="units not built locally")
def test_built_units_are_clean():
    with UNITS.open() as handle:
        rows = list(csv.DictReader(handle))
    keys = [(r["round"], r["ballot_id"], r["party"]) for r in rows]
    assert len(keys) == len(set(keys))                    # no duplicates
    assert not any(".by." in r["ballot_id"] for r in rows)
    assert all(int(r["ballot_id"][-10:-6]) < 2024 for r in rows)
    totals = {}
    for r in rows:
        totals[r["ballot_id"]] = totals.get(r["ballot_id"], 0) + float(r["share"])
    assert all(abs(t - 100) < 0.05 for t in totals.values())
