"""Tests for the article store and the review state model.

The store exists to make one thing impossible: losing what the model said when
a human disagrees with it. So most of what follows checks that the original
survives, that the provenance of every value is visible, and that a few
specific mistakes are refused rather than accepted quietly.
"""

from __future__ import annotations

import sqlite3

import pytest

from news_store import PROVENANCE_AI, PROVENANCE_REVIEWED, NewsStore
from news_store.schema import SCHEMA_VERSION, current_version


@pytest.fixture
def store(tmp_path):
    with NewsStore(tmp_path / "project.sqlite") as store:
        store.add_raw_article({
            "article_id": "A1", "headline": "Council tax rise approved",
            "publisher": "SurreyLive", "published_date": "2021-04-20",
        })
        yield store


def extract(store, field="sentiment_label", value="negative", **kwargs):
    return store.record_extraction(
        "A1", record_type="article", field=field, value=value,
        model="claude-sonnet-5", prompt_version="v2", schema_version="1.0",
        **kwargs)


# ---------------------------------------------------------------------------
# Schema and migration
# ---------------------------------------------------------------------------


def test_a_new_store_is_at_the_current_schema_version(tmp_path):
    with NewsStore(tmp_path / "p.sqlite") as store:
        assert current_version(store.connection) == SCHEMA_VERSION


def test_reopening_a_store_does_not_re_migrate_it(tmp_path):
    path = tmp_path / "p.sqlite"
    with NewsStore(path) as store:
        store.add_raw_article({"article_id": "A1"})
    with NewsStore(path) as store:
        rows = store.connection.execute(
            "SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert rows == 1
        assert store.connection.execute(
            "SELECT COUNT(*) FROM raw_article").fetchone()[0] == 1


def test_a_store_from_a_newer_version_is_refused(tmp_path):
    """Reading it with the wrong assumptions is worse than not opening it."""

    path = tmp_path / "p.sqlite"
    with NewsStore(path):
        pass
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION + 5, "2030-01-01"))
    connection.commit()
    connection.close()
    with pytest.raises(RuntimeError, match="understands"):
        NewsStore(path)


# ---------------------------------------------------------------------------
# The original always survives
# ---------------------------------------------------------------------------


def test_before_review_the_value_is_the_model_s_and_says_so(store):
    extract(store)
    resolved = store.resolve("A1", "article", "sentiment_label")
    assert resolved.value == "negative"
    assert resolved.provenance == PROVENANCE_AI
    assert not resolved.is_reviewed


def test_a_correction_changes_the_value_in_force_but_not_the_ai_value(store):
    extract(store)
    store.record_review("A1", status="reviewed_and_corrected", reviewer="SL",
                        corrections=[{"record_type": "article",
                                      "field": "sentiment_label",
                                      "final_value": "mixed",
                                      "reason": "the quote is critical, the article is not"}])
    resolved = store.resolve("A1", "article", "sentiment_label")
    assert resolved.value == "mixed"
    assert resolved.ai_value == "negative"
    assert resolved.provenance == PROVENANCE_REVIEWED
    assert resolved.correction_reason.startswith("the quote")


def test_correcting_the_same_field_twice_keeps_both_corrections(store):
    """The change history the brief asks to be retained."""

    extract(store)
    for value in ("mixed", "neutral"):
        store.record_review("A1", status="reviewed_and_corrected",
                            corrections=[{"record_type": "article",
                                          "field": "sentiment_label",
                                          "final_value": value}])
    history = store.correction_history("A1")
    assert [h["final_value"] for h in history] == ["mixed", "neutral"]
    # The later one is in force, the earlier one is still readable.
    assert store.resolve("A1", "article", "sentiment_label").value == "neutral"
    assert history[0]["ai_value"] == "negative"


def test_the_ai_value_recorded_on_a_correction_is_read_from_the_store(store):
    """A caller cannot record an AI value the model never produced."""

    extract(store, value="positive")
    store.record_review("A1", status="reviewed_and_corrected",
                        corrections=[{"record_type": "article",
                                      "field": "sentiment_label",
                                      "final_value": "negative",
                                      "ai_value": "something the model never said"}])
    assert store.correction_history("A1")[0]["ai_value"] == "positive"


def test_there_is_no_way_to_update_an_extraction(store):
    """The guarantee is structural, so the method simply does not exist."""

    assert not hasattr(store, "update_extraction")
    assert not hasattr(store, "set_value")


def test_re_adding_an_article_does_not_overwrite_the_original(store):
    store.add_raw_article({"article_id": "A1", "headline": "Different headline"})
    row = store.connection.execute(
        "SELECT headline FROM raw_article WHERE article_id='A1'").fetchone()
    assert row["headline"] == "Council tax rise approved"


# ---------------------------------------------------------------------------
# Review status
# ---------------------------------------------------------------------------


def test_an_untouched_article_is_not_reviewed(store):
    assert store.review_status("A1") == "not_reviewed"


def test_a_review_that_changed_nothing_is_distinguishable_from_no_review(store):
    """The reason review events exist separately from corrections."""

    extract(store)
    store.record_review("A1", status="reviewed_unchanged", reviewer="SL")
    assert store.review_status("A1") == "reviewed_unchanged"
    assert store.correction_history("A1") == []
    # And the value is still the model's, correctly labelled.
    assert store.resolve("A1", "article", "sentiment_label").provenance == PROVENANCE_AI


def test_the_latest_review_wins(store):
    extract(store)
    store.record_review("A1", status="needs_review")
    store.record_review("A1", status="reviewed_unchanged")
    assert store.review_status("A1") == "reviewed_unchanged"


def test_an_unknown_status_is_refused(store):
    with pytest.raises(ValueError, match="Unknown review status"):
        store.record_review("A1", status="looks_fine_to_me")


def test_corrections_under_the_wrong_status_are_refused(store):
    """Otherwise a change would be invisible to a status filter."""

    extract(store)
    with pytest.raises(ValueError, match="reviewed_and_corrected"):
        store.record_review("A1", status="reviewed_unchanged",
                            corrections=[{"record_type": "article",
                                          "field": "sentiment_label",
                                          "final_value": "mixed"}])


# ---------------------------------------------------------------------------
# Record types other than the article itself
# ---------------------------------------------------------------------------


def test_ward_links_and_entity_mentions_use_the_same_review_path(store):
    """One addressing scheme, so no record type gets a weaker review path."""

    store.record_extraction("A1", record_type="ward_link", record_key="Addlestone",
                            field="relevance_score", value=0.4,
                            model="m", prompt_version="v2", schema_version="1.0")
    store.record_extraction("A1", record_type="entity_mention", record_key="Reform UK",
                            field="sentiment_label", value="positive",
                            model="m", prompt_version="v2", schema_version="1.0")
    store.record_review("A1", status="reviewed_and_corrected", corrections=[
        {"record_type": "ward_link", "record_key": "Addlestone",
         "field": "relevance_score", "final_value": 0.9},
    ])
    ward = store.resolve("A1", "ward_link", "relevance_score", "Addlestone")
    entity = store.resolve("A1", "entity_mention", "sentiment_label", "Reform UK")
    assert ward.value == "0.9" and ward.is_reviewed
    assert entity.value == "positive" and not entity.is_reviewed


def test_correcting_one_ward_does_not_touch_another(store):
    for ward in ("Addlestone", "Ashtead"):
        store.record_extraction("A1", record_type="ward_link", record_key=ward,
                                field="relevance_score", value=0.5,
                                model="m", prompt_version="v2", schema_version="1.0")
    store.record_review("A1", status="reviewed_and_corrected", corrections=[
        {"record_type": "ward_link", "record_key": "Addlestone",
         "field": "relevance_score", "final_value": 1.0}])
    assert store.resolve("A1", "ward_link", "relevance_score", "Ashtead").value == "0.5"


# ---------------------------------------------------------------------------
# Credentials never enter the store
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["api_key", "OPENAI_API_KEY", "Authorization", "token"])
def test_a_credential_shaped_field_is_refused(store, field):
    with pytest.raises(ValueError, match="credentials must never"):
        extract(store, field=field, value="sk-should-never-be-here")


def test_no_credential_string_survives_a_normal_session(store, tmp_path):
    extract(store)
    store.record_review("A1", status="reviewed_unchanged", reviewer="SL")
    store.connection.commit()
    blob = (tmp_path / "project.sqlite").read_bytes()
    for marker in (b"sk-", b"api_key", b"Bearer "):
        assert marker not in blob


def test_the_credential_check_can_actually_fail(tmp_path):
    """Proof the test above is not vacuous.

    Planting a credential-shaped value and finding it establishes that the
    byte search works. It also documents the guard's real limit: field names
    are checked, values are not, because refusing every value that looks like
    a key would refuse article text that quotes one.
    """

    with NewsStore(tmp_path / "leak.sqlite") as store:
        store.add_raw_article({"article_id": "A1"})
        store.record_extraction("A1", record_type="article", field="headline",
                                value="sk-planted-for-this-test",
                                model="m", prompt_version="v", schema_version="1")
        store.connection.commit()
    assert b"sk-" in (tmp_path / "leak.sqlite").read_bytes()


# ---------------------------------------------------------------------------
# Traceability and export
# ---------------------------------------------------------------------------


def test_a_feature_can_be_traced_back_to_its_articles(store):
    store.add_raw_article({"article_id": "A2"})
    store.record_feature_provenance(
        "SCC-2021-05|Guildford East|Reform UK|previous_30_days|article_count",
        ["A1", "A2"], weights={"A1": 1.0, "A2": 0.5})
    assert store.articles_behind(
        "SCC-2021-05|Guildford East|Reform UK|previous_30_days|article_count"
    ) == ["A1", "A2"]


def test_window_assignments_are_kept_per_scheme(store):
    """Three incompatible schemes exist, so an assignment must name its own."""

    for scheme, window in (("original_email_180d", "final_72_hours"),
                           ("prompt_1_and_2_30d", "7_to_2_days")):
        store.record_window_assignment("A1", "SCC-2021-05", {
            "window_scheme": scheme, "days_before_polling": 3,
            "window": window, "cumulative_windows": ["previous_7_days"],
            "included_in_influence_features": True, "exclusion_reason": None})
    rows = store.connection.execute(
        "SELECT window_scheme, window FROM window_assignment"
        " WHERE article_id='A1' ORDER BY window_scheme").fetchall()
    assert [(r["window_scheme"], r["window"]) for r in rows] == [
        ("original_email_180d", "final_72_hours"),
        ("prompt_1_and_2_30d", "7_to_2_days"),
    ]


def test_the_export_carries_both_values_and_the_provenance(store):
    extract(store)
    store.record_review("A1", status="reviewed_and_corrected",
                        corrections=[{"record_type": "article",
                                      "field": "sentiment_label",
                                      "final_value": "mixed"}])
    row = store.export_rows()[0]
    assert row["AI Value"] == "negative"
    assert row["Final Value"] == "mixed"
    assert row["provenance"] == PROVENANCE_REVIEWED


def test_the_dashboard_separates_reviewed_fields_from_model_only_ones(store):
    extract(store, field="sentiment_label")
    extract(store, field="primary_topic", value="council tax", confidence=0.3)
    store.record_review("A1", status="reviewed_and_corrected",
                        corrections=[{"record_type": "article",
                                      "field": "sentiment_label",
                                      "final_value": "mixed"}])
    dashboard = store.review_dashboard()
    assert dashboard["fields_currently_human_reviewed"] == 1
    assert dashboard["fields_still_model_only"] == 1
    assert dashboard["articles_with_a_low_confidence_field"] == 1
    assert dashboard["by_review_status"]["reviewed_and_corrected"] == 1
    assert dashboard["by_review_status"]["not_reviewed"] == 0
