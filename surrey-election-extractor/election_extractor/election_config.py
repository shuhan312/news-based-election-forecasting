"""Load and validate declarative Surrey election configurations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/elections.json"
REQUIRED_FIELDS = (
    "election_id",
    "election_name",
    "election_year",
    "election_type",
)
URL_FIELDS = ("official_archive_url", "official_url")


class ElectionConfigurationError(ValueError):
    """Raised when a configuration entry cannot safely drive a pipeline run."""


@dataclass(frozen=True)
class ElectionConfiguration:
    """Describe one election source without embedding election logic in code."""

    election_id: str
    election_name: str
    election_year: int
    election_type: str
    official_url: str
    official_url_field: str


def _non_empty_text(entry: object, field_name: str, index: int) -> str:
    """Require meaningful text rather than accepting blank configuration values."""
    if not isinstance(entry, str) or not entry.strip():
        raise ElectionConfigurationError(
            f"Election entry {index} requires a non-empty {field_name}."
        )
    return entry.strip()


def _valid_official_url(url: str, field_name: str, index: int) -> str:
    """Accept only absolute HTTP(S) URLs; credentials are not configuration data."""
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ElectionConfigurationError(
            f"Election entry {index} has an invalid {field_name}."
        )
    return url


def _configuration_from_entry(entry: object, index: int) -> ElectionConfiguration:
    """Validate one raw JSON entry and map its URL field to a common interface."""
    if not isinstance(entry, dict):
        raise ElectionConfigurationError(f"Election entry {index} must be an object.")

    values = {
        field_name: _non_empty_text(entry.get(field_name), field_name, index)
        for field_name in REQUIRED_FIELDS
        if field_name != "election_year"
    }
    election_year = entry.get("election_year")
    # A boolean is an int subclass in Python, so reject it explicitly.
    if isinstance(election_year, bool) or not isinstance(election_year, int):
        raise ElectionConfigurationError(
            f"Election entry {index} requires an integer election_year."
        )

    supplied_url_fields = [field_name for field_name in URL_FIELDS if field_name in entry]
    if len(supplied_url_fields) != 1:
        raise ElectionConfigurationError(
            f"Election entry {index} requires exactly one official URL field: "
            "official_archive_url or official_url."
        )
    official_url_field = supplied_url_fields[0]
    official_url = _valid_official_url(
        _non_empty_text(entry.get(official_url_field), official_url_field, index),
        official_url_field,
        index,
    )

    return ElectionConfiguration(
        election_id=values["election_id"],
        election_name=values["election_name"],
        election_year=election_year,
        election_type=values["election_type"],
        official_url=official_url,
        official_url_field=official_url_field,
    )


def load_election_config(path: str | Path = DEFAULT_CONFIG_PATH) -> tuple[ElectionConfiguration, ...]:
    """Load configured elections and reject missing, invalid or duplicate entries."""
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ElectionConfigurationError(f"Election configuration was not found: {config_path}") from error
    except json.JSONDecodeError as error:
        raise ElectionConfigurationError(f"Election configuration is not valid JSON: {config_path}") from error

    entries = payload.get("elections") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ElectionConfigurationError("Election configuration requires a non-empty elections list.")

    configurations = tuple(
        _configuration_from_entry(entry, index)
        for index, entry in enumerate(entries, start=1)
    )
    identifiers = [configuration.election_id for configuration in configurations]
    if len(identifiers) != len(set(identifiers)):
        raise ElectionConfigurationError("Election configuration contains duplicate election_id values.")
    return configurations
