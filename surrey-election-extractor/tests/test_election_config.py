"""Tests for declarative Surrey election configuration loading."""

import json

import pytest

from election_extractor.election_config import (
    DEFAULT_CONFIG_PATH,
    ElectionConfigurationError,
    load_election_config,
)


EXISTING_2021_ARCHIVE_URL = (
    "https://mycouncil.surreycc.gov.uk/mgElectionResults.aspx?ID=16&RPID=0"
)


def test_valid_election_configuration_loads() -> None:
    configurations = load_election_config()

    assert len(configurations) == 5
    assert {configuration.election_id for configuration in configurations} == {
        "surrey-county-council-2013",
        "surrey-county-council-2017",
        "surrey-county-council-2021",
        "surrey-county-council-2026-east-surrey",
        "surrey-county-council-2026-west-surrey",
    }
    assert DEFAULT_CONFIG_PATH.name == "elections.json"


def test_missing_required_field_fails(tmp_path) -> None:
    path = tmp_path / "missing_field.json"
    path.write_text(
        json.dumps(
            {
                "elections": [
                    {
                        "election_id": "example",
                        "election_year": 2021,
                        "election_type": "County Council election",
                        "official_archive_url": EXISTING_2021_ARCHIVE_URL,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ElectionConfigurationError, match="election_name"):
        load_election_config(path)


def test_duplicate_election_identifier_fails(tmp_path) -> None:
    path = tmp_path / "duplicate_identifier.json"
    entry = {
        "election_id": "duplicate",
        "election_name": "Example election",
        "election_year": 2021,
        "election_type": "County Council election",
        "official_archive_url": EXISTING_2021_ARCHIVE_URL,
    }
    path.write_text(json.dumps({"elections": [entry, entry]}), encoding="utf-8")

    with pytest.raises(ElectionConfigurationError, match="duplicate election_id"):
        load_election_config(path)


def test_invalid_official_url_fails(tmp_path) -> None:
    path = tmp_path / "invalid_url.json"
    path.write_text(
        json.dumps(
            {
                "elections": [
                    {
                        "election_id": "invalid-url",
                        "election_name": "Example election",
                        "election_year": 2021,
                        "election_type": "County Council election",
                        "official_archive_url": "not-an-official-url",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ElectionConfigurationError, match="invalid official_archive_url"):
        load_election_config(path)


def test_2021_configuration_reproduces_existing_archive_url() -> None:
    configurations = load_election_config()
    configuration = next(
        item
        for item in configurations
        if item.election_id == "surrey-county-council-2021"
    )

    assert configuration.election_year == 2021
    assert configuration.official_url == EXISTING_2021_ARCHIVE_URL
    assert configuration.official_url_field == "official_archive_url"
