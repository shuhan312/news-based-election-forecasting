"""Tests for explicit party-name lookup validation and provenance safeguards."""

import json

import pytest

from election_extractor.party_lookup import PartyLookupError, load_party_lookup


def write_lookup(tmp_path, mappings: list[dict[str, object]]):
    """Write a minimal local lookup fixture without using production settings."""

    path = tmp_path / "party_lookup.json"
    path.write_text(json.dumps({"party_mappings": mappings}), encoding="utf-8")
    return path


def test_lookup_loads_reviewed_exact_labels(tmp_path) -> None:
    """A reviewed mapping keeps the published label and its project category."""

    path = write_lookup(
        tmp_path,
        [
            {
                "original_party_name": "Farnham Residents",
                "standard_party_name": "Farnham Residents",
                "party_category": "local",
                "category_basis": "Published label identifies a local residents group.",
                "notes": "Exact-label mapping only.",
            }
        ],
    )

    lookup = load_party_lookup(path)

    assert lookup["Farnham Residents"].standard_party_name == "Farnham Residents"
    assert lookup["Farnham Residents"].party_category == "local"


def test_lookup_rejects_duplicate_published_labels(tmp_path) -> None:
    """One published label must have one reviewed mapping decision."""

    path = write_lookup(
        tmp_path,
        [
            {
                "original_party_name": "Independent",
                "standard_party_name": "Independent",
                "party_category": "independent",
            },
            {
                "original_party_name": "Independent",
                "standard_party_name": "Independent",
                "party_category": "independent",
            },
        ],
    )

    with pytest.raises(PartyLookupError, match="duplicate"):
        load_party_lookup(path)


def test_lookup_rejects_reform_uk_rename_to_ukip(tmp_path) -> None:
    """The supervisor-required Reform UK/UKIP separation is enforced in config."""

    path = write_lookup(
        tmp_path,
        [
            {
                "original_party_name": "Reform UK",
                "standard_party_name": "UK Independence Party",
                "party_category": "emerging",
            }
        ],
    )

    with pytest.raises(PartyLookupError, match="protected"):
        load_party_lookup(path)


def test_production_lookup_groups_ukip_labels_but_keeps_reform_separate() -> None:
    """Published UKIP variants share one standard name; Reform remains separate."""

    lookup = load_party_lookup()

    ukip_labels = {
        "UKIP",
        "UK Independence Party",
        "UK Independence Party (UKIP)",
    }
    assert {
        lookup[label].standard_party_name for label in ukip_labels
    } == {"UK Independence Party"}
    assert lookup["Reform UK"].standard_party_name == "Reform UK"


def test_lookup_rejects_ukip_label_mapped_to_reform(tmp_path) -> None:
    """A configuration edit cannot turn an older UKIP label into Reform UK."""

    path = write_lookup(
        tmp_path,
        [
            {
                "original_party_name": "UKIP",
                "standard_party_name": "Reform UK",
                "party_category": "established",
            }
        ],
    )

    with pytest.raises(PartyLookupError, match="must map UKIP label"):
        load_party_lookup(path)
