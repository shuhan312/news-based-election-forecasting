"""Tests for source-preserving candidate-name display standardisation."""

import pytest

from election_extractor.candidate_name_standardisation import (
    standardise_candidate_name,
)


def test_reorders_explicit_surname_comma_format() -> None:
    """A single explicit comma supports a deterministic display reordering."""

    result = standardise_candidate_name("Adams, Les")
    assert result.value == "Les Adams"
    assert result.status == "surname_comma_order_reformatted"


def test_all_uppercase_comma_surname_gets_readable_display_case() -> None:
    """The analytical copy may fix all-caps display without changing source text."""

    result = standardise_candidate_name("PERSAND, Karandeo")
    assert result.value == "Karandeo Persand"
    assert result.status == "surname_comma_order_reformatted"


def test_mixed_case_apostrophe_is_preserved() -> None:
    """Known mixed casing is retained rather than overwritten by title casing."""

    result = standardise_candidate_name("D'Avray, Christopher David")
    assert result.value == "Christopher David D'Avray"


def test_name_without_explicit_separator_keeps_published_order() -> None:
    """No surname order is inferred from an unpunctuated sequence of tokens."""

    result = standardise_candidate_name("Clarke Matthew David")
    assert result.value == "Clarke Matthew David"
    assert result.status == "published_order_retained"


def test_whitespace_is_normalised_only_in_the_analytical_copy() -> None:
    """Repeated source whitespace does not propagate to the standard display."""

    result = standardise_candidate_name("  Jane   Smith  ")
    assert result.value == "Jane Smith"
    assert result.status == "published_order_retained"


def test_empty_name_is_rejected() -> None:
    """A missing source name cannot be repaired by a standardisation rule."""

    with pytest.raises(ValueError, match="non-empty"):
        standardise_candidate_name("  ")
