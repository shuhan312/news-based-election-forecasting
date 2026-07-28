"""Turn candidate contract rows into a numeric design matrix.

This is the input end of the model and the last place a leakage rule can be
broken, so it is deliberately a separate module with its own tests rather than
a helper inside a model class.

Three rules it exists to enforce
--------------------------------
1. **Only permitted predictors.** Columns come from
   ``candidate_leakage_audit.permitted_predictors()``, never from whatever
   happens to be in the release. A new column in a future release is therefore
   ignored until it has been classified in the audit, which forces the
   reasoning to be written down.

2. **Unknown is never No, and missing is never zero.** The release keeps
   ``Unknown`` distinct from ``No`` for incumbency and candidature history,
   and keeps a missing previous vote share distinct from a proven zero. That
   distinction survives encoding: every nullable input contributes a value
   *and* an indicator column, so the model can learn a separate effect for
   "we do not know" instead of being told it means "no".

3. **Everything is fitted on training rows only.** Category levels, medians
   and standardisation are learned in ``fit`` from one fold's training rows
   and then applied unchanged in ``transform``. A test row can never influence
   the transformation applied to it. This is the fold-only-imputation rule
   already stated in ``docs/data_contract.md``.

Encoding scheme
---------------
========================  =====================================================
kind                      columns produced
========================  =====================================================
``numeric``               ``col`` (median-filled) and ``col__missing``
``yes_no``                ``col__yes`` and ``col__unknown``; ``No`` is the
                          reference level, so both are 0
``boolean``               ``col__true`` and ``col__unknown``
``categorical``           one column per level seen in training, plus
                          ``col__unseen_level`` for anything new at test time
``derived``               computed from a permitted column (see DERIVED)
========================  =====================================================

Why an unseen-level column rather than an error: a by-election can put a party
on the ballot that never appeared in training. Refusing to predict that row
would silently shrink the test set; mapping it to an existing party would be a
fabrication. A single explicit "this level was not in training" flag is the
honest option, and it also lets the model learn that such rows behave like
other first-appearances.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from no_news_baseline.candidate_leakage_audit import (
    assert_no_prohibited_column,
    permitted_predictors,
)
from no_news_baseline.election_dates import parse_election_date


NUMERIC = "numeric"
YES_NO = "yes_no"
BOOLEAN = "boolean"
CATEGORICAL = "categorical"

# How each permitted predictor is encoded. Every column returned by
# ``permitted_predictors()`` must appear here or in DERIVED_FROM; ``fit``
# raises otherwise, so a newly permitted column cannot be silently dropped
# from the matrix while still appearing in the audit as a predictor.
ENCODING: dict[str, str] = {
    # contest structure, all known at nomination close or earlier
    "election_year": NUMERIC,
    "analysis_number_of_seats": NUMERIC,
    "candidate_count_in_contest": NUMERIC,
    "party_count_in_contest": NUMERIC,
    "party_candidate_count_in_contest": NUMERIC,
    "election_type": CATEGORICAL,
    "authority": CATEGORICAL,
    "contest_structure": CATEGORICAL,
    # party identity
    "standard_party_name": CATEGORICAL,
    "party_category": CATEGORICAL,
    "is_reform_uk": BOOLEAN,
    "is_ukip": BOOLEAN,
    # area history
    "previous_party_vote_share": NUMERIC,
    "analysis_previous_turnout": NUMERIC,
    "previous_electorate": NUMERIC,
    "previous_winning_party": CATEGORICAL,
    "party_was_previous_winner": BOOLEAN,
    # candidate and party history
    "candidate_previously_stood": BOOLEAN,
    "incumbent_candidate_yes_no": YES_NO,
    "incumbent_party_yes_no": YES_NO,
    "party_previously_contested": BOOLEAN,
    "first_appearance_of_party_in_area": BOOLEAN,
    # evidence quality and missingness
    "historical_predictor_availability": CATEGORICAL,
    "geographic_reference_eligibility": CATEGORICAL,
}

# Features computed from a permitted column rather than taken from it whole.
# ``election_date`` is permitted but useless as a raw string; the brief lists
# "month or season" among candidate features, and month is what a polling date
# actually carries beyond the year already encoded above.
DERIVED_FROM: dict[str, str] = {
    "election_month": "election_date",
}


@dataclass(frozen=True)
class DesignMatrix:
    """A fitted encoding applied to a set of rows.

    ``row_ids`` is carried alongside the matrix so predictions can be joined
    back to contests without relying on positional order surviving a later
    refactor.
    """

    row_ids: tuple[str, ...]
    column_names: tuple[str, ...]
    matrix: np.ndarray

    def __post_init__(self) -> None:
        if self.matrix.shape != (len(self.row_ids), len(self.column_names)):
            raise ValueError("Design matrix shape does not match its labels.")


class CandidateFeatureEncoder:
    """Learns an encoding from training rows, then applies it unchanged.

    Deliberately not a general-purpose transformer. It knows about this one
    release's columns, so that "which columns may be used" is a question with
    a single answer in the codebase rather than a parameter each caller
    chooses for itself.
    """

    def __init__(self, *, standardise: bool = True) -> None:
        # Standardisation is on by default because the first architecture is
        # a penalised linear model, where an unscaled column would receive an
        # arbitrarily different amount of shrinkage purely because of its
        # units. Tree models do not need it, hence the switch.
        self._standardise = standardise
        self._predictors: tuple[str, ...] = ()
        self._levels: dict[str, tuple[str, ...]] = {}
        self._medians: dict[str, float] = {}
        self._column_names: tuple[str, ...] = ()
        self._means: np.ndarray | None = None
        self._scales: np.ndarray | None = None
        self._fitted = False

    # -- fitting ----------------------------------------------------------

    def fit(self, train_rows: Sequence[Mapping[str, object]]) -> "CandidateFeatureEncoder":
        """Learn category levels, medians and scaling from training rows only."""

        if not train_rows:
            raise ValueError("Cannot fit the encoder on an empty training set.")

        available = set(train_rows[0])
        self._predictors = tuple(
            column for column in permitted_predictors(sorted(available))
        )
        # The audit's own guard, run on the exact list about to be encoded.
        # If this ever raises, the failure is in the audit or the release, and
        # no matrix should be produced at all.
        assert_no_prohibited_column(self._predictors)

        unencoded = [
            column
            for column in self._predictors
            if column not in ENCODING and column not in DERIVED_FROM.values()
        ]
        if unencoded:
            raise ValueError(
                f"Permitted predictors with no encoding rule: {unencoded!r}. "
                "Add them to ENCODING or DERIVED_FROM before fitting."
            )

        # Category levels are the sorted distinct non-null values seen in
        # training. Sorting makes the column order deterministic, so two runs
        # on the same fold produce byte-identical matrices.
        for column in self._predictors:
            if ENCODING.get(column) != CATEGORICAL:
                continue
            self._levels[column] = tuple(
                sorted(
                    {
                        str(row[column])
                        for row in train_rows
                        if row.get(column) is not None
                    }
                )
            )

        # Medians fill missing numerics. A median rather than a mean because
        # electorate and turnout are skewed, and a median rather than zero
        # because zero is a meaningful vote share and would be a lie. The
        # paired __missing indicator means the fill value never has to carry
        # the information that the value was absent.
        for column in self._predictors:
            if ENCODING.get(column) != NUMERIC:
                continue
            observed = [
                float(row[column]) for row in train_rows if row.get(column) is not None
            ]
            self._medians[column] = float(np.median(observed)) if observed else 0.0

        for name in DERIVED_FROM:
            observed = [self._derive(name, row) for row in train_rows]
            observed = [value for value in observed if value is not None]
            self._medians[name] = float(np.median(observed)) if observed else 0.0

        self._column_names = self._build_column_names()
        raw = self._encode_rows(train_rows)

        if self._standardise:
            self._means = raw.mean(axis=0)
            scales = raw.std(axis=0)
            # A column with no training variation is left unscaled rather than
            # divided by zero. After centring it is all zeros and contributes
            # nothing, which is the correct behaviour for a feature the
            # training fold never varied.
            self._scales = np.where(scales == 0.0, 1.0, scales)
        else:
            self._means = np.zeros(raw.shape[1])
            self._scales = np.ones(raw.shape[1])

        self._fitted = True
        return self

    # -- application -------------------------------------------------------

    def transform(self, rows: Sequence[Mapping[str, object]]) -> DesignMatrix:
        """Apply the fitted encoding. Never learns anything new."""

        if not self._fitted:
            raise ValueError("The encoder must be fitted before transforming rows.")
        raw = self._encode_rows(rows)
        standardised = (raw - self._means) / self._scales
        return DesignMatrix(
            row_ids=tuple(str(row["candidate_contest_id"]) for row in rows),
            column_names=self._column_names,
            matrix=standardised,
        )

    def fit_transform(
        self, train_rows: Sequence[Mapping[str, object]]
    ) -> DesignMatrix:
        return self.fit(train_rows).transform(train_rows)

    @property
    def column_names(self) -> tuple[str, ...]:
        return self._column_names

    @property
    def source_predictors(self) -> tuple[str, ...]:
        """The release columns consumed, before encoding expands them."""

        return self._predictors

    def schema(self) -> dict[str, object]:
        """A description sufficient to rebuild compatible input rows later.

        The brief requires ``feature_schema.json`` to "allow a separate
        application to construct compatible input rows", which is exactly what
        the Stage 2 news layer and the synthetic-scenario tool will need. The
        learned levels and medians are included because without them a second
        application cannot reproduce this encoding.
        """

        return {
            "source_predictors": list(self._predictors),
            "encoded_columns": list(self._column_names),
            "encoding": {
                column: ENCODING[column]
                for column in self._predictors
                if column in ENCODING
            },
            "derived_from": dict(DERIVED_FROM),
            "categorical_levels": {
                column: list(levels) for column, levels in sorted(self._levels.items())
            },
            "numeric_fill_medians": dict(sorted(self._medians.items())),
            "standardised": self._standardise,
        }

    # -- internals ---------------------------------------------------------

    def _build_column_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for column in self._predictors:
            kind = ENCODING.get(column)
            if kind == NUMERIC:
                names.extend([column, f"{column}__missing"])
            elif kind == YES_NO:
                names.extend([f"{column}__yes", f"{column}__unknown"])
            elif kind == BOOLEAN:
                names.extend([f"{column}__true", f"{column}__unknown"])
            elif kind == CATEGORICAL:
                names.extend(
                    [f"{column}__{level}" for level in self._levels[column]]
                )
                names.append(f"{column}__unseen_level")
        for name in DERIVED_FROM:
            names.extend([name, f"{name}__missing"])
        return tuple(names)

    def _encode_rows(self, rows: Sequence[Mapping[str, object]]) -> np.ndarray:
        matrix = np.zeros((len(rows), len(self._column_names)), dtype=float)
        index = {name: position for position, name in enumerate(self._column_names)}

        for row_position, row in enumerate(rows):
            for column in self._predictors:
                kind = ENCODING.get(column)
                value = row.get(column)

                if kind == NUMERIC:
                    if value is None:
                        matrix[row_position, index[column]] = self._medians[column]
                        matrix[row_position, index[f"{column}__missing"]] = 1.0
                    else:
                        matrix[row_position, index[column]] = float(value)

                elif kind == YES_NO:
                    # "No" is the reference level: both indicators stay 0.
                    # Unknown gets its own column so it is never read as No.
                    if value == "Yes":
                        matrix[row_position, index[f"{column}__yes"]] = 1.0
                    elif value != "No":
                        matrix[row_position, index[f"{column}__unknown"]] = 1.0

                elif kind == BOOLEAN:
                    if value is None:
                        matrix[row_position, index[f"{column}__unknown"]] = 1.0
                    elif bool(value):
                        matrix[row_position, index[f"{column}__true"]] = 1.0

                elif kind == CATEGORICAL:
                    if value is None:
                        # A null category is a level the training data never
                        # names; it lands in the same explicit bucket as an
                        # unseen level rather than in a silent all-zero row.
                        matrix[row_position, index[f"{column}__unseen_level"]] = 1.0
                        continue
                    key = f"{column}__{value}"
                    if key in index:
                        matrix[row_position, index[key]] = 1.0
                    else:
                        matrix[row_position, index[f"{column}__unseen_level"]] = 1.0

            for name in DERIVED_FROM:
                derived = self._derive(name, row)
                if derived is None:
                    matrix[row_position, index[name]] = self._medians[name]
                    matrix[row_position, index[f"{name}__missing"]] = 1.0
                else:
                    matrix[row_position, index[name]] = float(derived)

        return matrix

    @staticmethod
    def _derive(name: str, row: Mapping[str, object]) -> float | None:
        if name == "election_month":
            value = row.get("election_date")
            if value is None:
                return None
            try:
                return float(parse_election_date(str(value)).month)
            except ValueError:
                return None
        raise ValueError(f"No derivation rule for {name!r}.")


def target_vector(
    rows: Sequence[Mapping[str, object]],
    targets: Mapping[str, Mapping[str, object]],
    *,
    field: str = "target_candidate_vote_share",
) -> np.ndarray:
    """Realised shares for these rows, in the same order as the matrix.

    Targets live in a separate table by design (the feature/target split is a
    leakage control), so they are looked up explicitly here rather than read
    off the feature rows. A row with no observed share raises: such rows are
    labelled ineligible upstream and should never have reached a model.
    """

    values: list[float] = []
    for row in rows:
        row_id = str(row["candidate_contest_id"])
        value = targets[row_id].get(field)
        if value is None:
            raise ValueError(
                f"Row {row_id} has no observed {field}; it is not an eligible "
                "prediction target and should have been filtered upstream."
            )
        values.append(float(value))
    return np.array(values, dtype=float)
