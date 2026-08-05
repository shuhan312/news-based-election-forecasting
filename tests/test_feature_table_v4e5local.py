"""Guards on the E5-local wrapper and the human E5 decision file.

The wrapper exists because `e5local1` was extracted on 2026-08-02 while its
E5 gate was still open, so the tranche on disk is a superset of what any
release admits. Loading it therefore trips the builder's corpus assertion,
and the wrapper answers that with an admission filter.

An admission filter is exactly the kind of thing that quietly turns into a
way to smuggle articles past a guard, so these tests pin down what it is
allowed to remove: only articles this release's own decision file names and
declines. Anything from another corpus must still reach the frozen assertion
and still stop the build.

The remaining tests pin the claims the findings document makes about the
pass - that only E5 was re-judged, that the four zero-coverage by-elections
gained cells, and that none of the cells v3party already had were lost.
"""

import csv
from pathlib import Path

import pytest

DECISIONS = Path("news_collection/byelection_eligibility_decisions_e5human_v1.csv")
V3PARTY = Path("news_features/news_feature_table_v3party.csv")
V4 = Path("news_features/news_feature_table_v4e5local.csv")

TARGET_BYELECTIONS = (
    "surrey-county-council-by-election-caterham-valley-2025-10-16",
    "surrey-county-council-by-election-guildford-south-east-2025-10-16",
    "surrey-county-council-by-election-hinchley-wood-claygate-oxshott-2025-08-21",
    "surrey-county-council-by-election-weybridge-2015-05-07",
)

needs_v4 = pytest.mark.skipif(
    not V4.exists(), reason="v4e5local table not built")


# Everything the v4 wrapper rebinds, plus everything the v3party wrapper it
# imports rebinds. `SPLIT_ROLE` is mutated in place, so it needs a copy.
# `PARTY_CONTENT_ATTRIBUTION` is the one that bites: v3party turns it on and
# the v1 and v2 wrappers never turn it off, so leaking it makes their rebuild
# tests fail on bytes with nothing in their own file to explain why.
_REBOUND = ("OUT_CSV", "OUT_META", "EXCLUDED_TRANCHES", "load_records",
            "build_release", "CANONICAL_MANIFEST", "GRID_ELECTIONS",
            "PARTY_CONTENT_ATTRIBUTION")


def _pristine_builder_globals():
    """The builder's settings as they stand before any wrapper is imported.

    Captured at collection time, which is the only moment they are reliably
    clean: Python caches modules, so once any wrapper has been imported its
    assignments are already in place and saving "the current values" would
    save the mutation.
    """

    from src.news_collection import canonical_corpus_release_v2 as release_v2
    from src.news_features import build_feature_table as frozen

    return ({n: getattr(frozen, n) for n in _REBOUND},
            dict(frozen.SPLIT_ROLE),
            release_v2.BYELECTION_DECISIONS)


_PRISTINE = _pristine_builder_globals()


@pytest.fixture
def wrapper():
    """The wrapper, with the builder globals it rebinds put back afterwards.

    Importing it configures the builder by assignment - output paths, the
    decision file, the exclusion set, the record loader. Left in place those
    make `test_feature_table_rebuild` rebuild v1 and v2 from the wrong
    corpus, and only when the two files run in the same session.
    """

    from src.news_collection import canonical_corpus_release_v2 as release_v2
    from src.news_features import build_feature_table as frozen

    from src.news_features import build_feature_table_v4e5local as module

    try:
        module.configure()
        yield module
    finally:
        settings, split_role, decisions = _PRISTINE
        for name, value in settings.items():
            setattr(frozen, name, value)
        frozen.SPLIT_ROLE.clear()
        frozen.SPLIT_ROLE.update(split_role)
        release_v2.BYELECTION_DECISIONS = decisions


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _covered(path):
    """(election, party) carrying party-level news in any window."""

    covered = set()
    for row in _rows(path):
        count = str(row.get("party_article_count", "")).strip()
        if count not in ("", "0") and float(count) != 0:
            covered.add((row["election_id"], row["standard_party_key"]))
    return covered


def test_only_the_e5_gate_carries_human_verdicts():
    """E5 failed its validation at kappa 0.4762. The other gates did not.

    If a human verdict ever appears on E4, E6 or E8 it means someone
    re-judged a gate that was already settled, which is how the pipeline's
    own `include/E8-EDITORIAL-CONFIRMED` verdicts would get overwritten.
    """

    rows = _rows(DECISIONS)
    human = [r for r in rows if r.get("e5_source") == "human"]
    assert human, "no human E5 verdicts in the decision file"
    for row in rows:
        for gate in ("e4_source", "e6_source", "e8_source"):
            if gate in row:
                assert row[gate] != "human", (
                    f"{row['article_id']}: {gate} carries a human verdict; "
                    "only E5 was re-judged")


def test_decision_file_admits_more_than_the_frozen_one():
    """627 terminal includes become 656. A drop means the pass lost rows."""

    includes = [r for r in _rows(DECISIONS) if r["overall_decision"] == "include"]
    assert len(includes) == 656, (
        f"{len(includes)} includes; the human pass recorded 656")


def test_admission_filter_drops_only_articles_the_release_declines(wrapper):
    """The filter may remove an unadmitted article and nothing else.

    An article from a different corpus carries no row in this decision file,
    so `decisions.get` returns None and the filter must leave it in place -
    where the frozen corpus assertion still catches it.
    """

    decisions = wrapper._decisions_index()
    declined = {a for a, v in decisions.items() if v != "include"}
    assert declined, "nothing declined; the filter would be untested"

    records = {"stance": {a: object() for a in list(decisions)[:50]}}
    records["stance"]["NEWS-from-another-corpus"] = object()
    kept_before = set(records["stance"])

    saved = wrapper._frozen_load_records
    try:
        wrapper._frozen_load_records = lambda: (records, {})
        kept_after = set(wrapper.load_records()[0]["stance"])
    finally:
        wrapper._frozen_load_records = saved

    assert "NEWS-from-another-corpus" in kept_after, (
        "an article the decision file does not name was dropped; it must "
        "reach the frozen corpus assertion instead")
    for article in kept_before - kept_after:
        assert decisions[article] != "include", (
            f"{article} is admitted by the decision file and was dropped")


@needs_v4
def test_wrapper_did_not_overwrite_the_other_tables(wrapper):
    """Each wrapper writes beside the others, never onto them."""

    from src.news_features import build_feature_table as frozen

    assert frozen.OUT_CSV.name == "news_feature_table_v4e5local.csv"
    assert wrapper.__doc__ and "v3party" in wrapper.__doc__
    for other in ("v1", "v2", "v3exp", "v3party"):
        assert Path(f"news_features/news_feature_table_{other}.csv").exists()


@needs_v4
def test_the_four_zero_coverage_byelections_gained_cells():
    """The point of the exercise. Zero here means the release did not admit
    what the decision file says it admits."""

    before, after = _covered(V3PARTY), _covered(V4)
    for election in TARGET_BYELECTIONS:
        was = {k for k in before if k[0] == election}
        now = {k for k in after if k[0] == election}
        assert not was, f"{election} already had coverage in v3party"
        assert now, f"{election} still carries no party-level news"


@needs_v4
def test_no_covered_cell_was_lost():
    """Admitting articles must not remove coverage from anywhere else."""

    lost = _covered(V3PARTY) - _covered(V4)
    assert not lost, f"cells lost against v3party: {sorted(lost)}"
