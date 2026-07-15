"""Tests for the additive election-structure metadata model."""

import json

import pytest

from election_extractor.election_structure_metadata import load_secondary_seats_audit
from election_extractor.models import ElectionStructureMetadata


SOURCE_URL = "https://www.legislation.gov.uk/uksi/2012/1872/contents/made"
SOURCE_TYPE = "The Surrey (Electoral Changes) Order 2012"
EVIDENCE = "Article 4 and the Schedule name Ash and provide for one councillor per division."


def metadata(**changes: object) -> ElectionStructureMetadata:
    """Build auditable metadata while allowing each test to change one field."""
    values = {
        "election_year": 2021,
        "election_name": "2021 Surrey County Council election",
        "authority": "Surrey County Council",
        "division_or_ward_name": "Ash",
        "official_number_of_seats": None,
        "secondary_number_of_seats": None,
        "seat_source_type": None,
        "seat_source_url": None,
        "seat_evidence_text": None,
        "confidence": None,
        "notes": None,
    }
    values.update(changes)
    return ElectionStructureMetadata(**values)


def test_official_seats_value_is_stored_in_its_own_field() -> None:
    record = metadata(official_number_of_seats=1)

    assert record.official_number_of_seats == 1
    assert record.secondary_number_of_seats is None


def test_secondary_seats_value_is_recorded_with_provenance() -> None:
    record = metadata(
        secondary_number_of_seats=1,
        seat_source_type=SOURCE_TYPE,
        seat_source_url=SOURCE_URL,
        seat_evidence_text=EVIDENCE,
        confidence="High",
    )

    assert record.official_number_of_seats is None
    assert record.secondary_number_of_seats == 1
    assert record.seat_source_url == SOURCE_URL
    assert record.seat_evidence_text == EVIDENCE


def test_secondary_value_cannot_overwrite_official_value() -> None:
    record = metadata(
        official_number_of_seats=2,
        secondary_number_of_seats=1,
        seat_source_type=SOURCE_TYPE,
        seat_source_url=SOURCE_URL,
        seat_evidence_text=EVIDENCE,
    )

    # A disagreement remains visible as two values for review; the model does
    # not choose one value or copy the secondary value into the official field.
    assert record.official_number_of_seats == 2
    assert record.secondary_number_of_seats == 1


def test_missing_secondary_evidence_remains_missing() -> None:
    record = metadata()

    assert record.official_number_of_seats is None
    assert record.secondary_number_of_seats is None


def test_secondary_value_requires_source_url_and_evidence_text() -> None:
    with pytest.raises(ValueError, match="seat_source_url"):
        metadata(
            secondary_number_of_seats=1,
            seat_source_type=SOURCE_TYPE,
            seat_evidence_text=EVIDENCE,
        )

    with pytest.raises(ValueError, match="seat_evidence_text"):
        metadata(
            secondary_number_of_seats=1,
            seat_source_type=SOURCE_TYPE,
            seat_source_url=SOURCE_URL,
        )


def test_completed_audit_is_loaded_without_replacing_official_seats(tmp_path) -> None:
    audit_path = tmp_path / "secondary_seats_audit.json"
    audit_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "division_name": "Ash",
                        "official_number_of_seats": None,
                        "secondary_seats_available": True,
                        "secondary_seats_value": 1,
                        "source_type": SOURCE_TYPE,
                        "source_title": "The Surrey (Electoral Changes) Order 2012 (UKSI 2012/1872)",
                        "source_url": SOURCE_URL,
                        "evidence_text": EVIDENCE,
                        "confidence": "High",
                        "notes": "Supplementary evidence only.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    (record,) = load_secondary_seats_audit(
        audit_path,
        election_year=2021,
        election_name="2021 Surrey County Council election",
        authority="Surrey County Council",
    )

    assert record.division_or_ward_name == "Ash"
    assert record.official_number_of_seats is None
    assert record.secondary_number_of_seats == 1
    assert record.seat_source_name == "The Surrey (Electoral Changes) Order 2012 (UKSI 2012/1872)"
    assert record.seat_source_url == SOURCE_URL
