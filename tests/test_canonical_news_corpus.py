"""Regression tests for the corpus/version boundary of the news layer."""

from src.news_collection.canonical_corpus_release import build_release
from src.news_collection.measure_window_reach import classify
from src.news_modelling.window_schemes import ORIGINAL_EMAIL


def test_confirmed_six_windows_cover_every_day_in_collection_horizon():
    """No day in the 180-day collection horizon can fall between windows."""

    assignments = {day: classify(day) for day in range(1, 181)}
    assert set(assignments.values()) == {
        name for name, _first, _last in ORIGINAL_EMAIL.windows
    }
    assert classify(181) == "before_the_earliest_window"
    assert classify(0) == "on_or_after_polling_day"
    assert classify(None) == "undated"


def test_canonical_release_reconciles_all_funnel_counts():
    """The manifest must explain every terminal include exactly once."""

    release, articles = build_release()
    terminal = release["terminal_include_union"]["articles"]
    exclusions = release["excluded_after_terminal_include"]
    excluded_total = sum(
        exclusions[key]
        for key in (
            "no_effective_date",
            "not_a_principal_election",
            "outside_all_windows",
            "no_extracted_text",
        )
    )

    assert terminal == len(articles) + excluded_total
    assert len(articles) == release["usable_feature_corpus"]["articles"]
    assert sum(release["usable_feature_corpus"]["by_arm"].values()) == len(
        articles
    )
    assert release["window_scheme"] == ORIGINAL_EMAIL.key


def test_main_decision_table_is_labelled_as_a_subset():
    """Prevent the old 120-local figure being presented as the full corpus."""

    release, _ = build_release()
    main = release["main_decision_table_only"]
    canonical = release["usable_feature_corpus"]

    assert main["articles"] < release["terminal_include_union"]["articles"]
    assert main["by_arm"]["local"] < canonical["by_arm"]["local"]
