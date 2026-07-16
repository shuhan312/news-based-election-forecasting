# Historical Baseline Feature Layer

This component prepares the historical-election-only comparison baseline required before any later news-context experiment. Its purpose is to make a future model comparison meaningful: a news-aware model must be compared with what election history already provides.

The layer is read-only over completed official election extraction, party standardisation and geographic crosswalk outputs. It creates structure features, exact-label party-presence features, candidate-history infrastructure and a 2026 ward readiness dataset. It does not collect news, train a model or predict an outcome.

An `accepted_direct` geographic relationship is necessary but not sufficient for
direct historical-reference features. The reviewed row must also explicitly set
`previous_winner_allowed=true`; this keeps a technical GIS decision separate
from permission to transfer electoral history. `partial_crosswalk_available`,
`not_comparable`, `requires_review` and unpermitted direct relationships remain
documented but block electoral comparisons. No votes are redistributed and no
candidate, incumbent or predecessor relationship is inferred from names.

Run `PYTHONPATH=surrey-election-extractor .venv/bin/python surrey-election-extractor/scripts/generate_historical_baseline_features.py` from the repository root to recreate the local baseline outputs.
