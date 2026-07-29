# Prompt 1 compliance: what was checked, and what three audits found

**Recorded 29 July 2026.** This exists because "is it finished?" was answered
wrongly twice before it was answered correctly, and the pattern in how it was
wrong is worth keeping.

---

## The three audits

| round | claimed remaining | actually remaining |
| --- | --- | --- |
| 1 | Streamlit and a technical report | those, **plus** seat validation, date validation and evidence-layer labelling |
| 2 | nothing | **four items**: `requirements.txt`, predicted winning party, predicted party seat totals, explainability artefacts |
| 3 | — | none found |

Both premature answers failed the same way: **the code existed, so the
requirement felt met.** Seat totals were computed — as an error statistic.
Feature importance was computed — inside a function, quoted in the model card,
recomputed live by the app. `requirements.txt` existed — listing four packages
of the eight the code imports.

The lesson is specific: *"can the pipeline do this"* and *"does the delivered
artefact contain this"* are different questions, and only the second one is
what the brief asks. Round 3 checked by opening the bundle and the file, not
by remembering what had been written.

### What round 2 missed, and why each mattered

**`requirements.txt` listed numpy, numpyro, pytest and lightgbm.** The code
also imports PyYAML, streamlit, pandas and openpyxl. The acceptance criterion
"the application runs from a clean installation using the README instructions"
would have failed at the first `import yaml`. numpyro, meanwhile, is a
leftover from the superseded N5a exploration and is now marked as such rather
than left looking current.

**Predicted winning party and predicted party seat totals** are two of the
seven outputs the brief lists under "produce the following outputs". Both were
computed far enough to score and no further, so `metrics.json` published
`party_seat_total_absolute_error` — the error in the seat totals — with no
artefact anywhere stating what the totals were. That is backwards: the
projection is the thing a reader can check against the real council; the error
statistic is downstream of it.

**Explainability artefacts.** The brief says "generate: global feature
importance; fold-level feature importance; Reform UK-specific feature
importance; coefficients; SHAP; example contest explanations; warnings where
feature effects are unstable." All seven existed as functions and several were
quoted in the model card, but the bundle contained no explainability file at
all. A figure that must be recomputed to be read will eventually be recomputed
differently.

---

## The seat projection, and what it shows

Adding the projection was meant to close a checklist item. It produced the
clearest single statement of the model's failure in the whole project.

**Primary holdout, 7 May 2026, 838 candidates across 82 contests:**

| party | predicted seats | actual seats |
| --- | ---: | ---: |
| Conservative | 118 | 30 |
| Liberal Democrats | 6 | 96 |
| **Reform UK** | **0** | **12** |

Party seat-total absolute error 232. The winning party set is exactly right in
23.2 per cent of contests. Four contests have a tie sitting on the seat
boundary, which the projection records rather than breaks — resolving it
arbitrarily would manufacture a prediction the model did not make.

**The model predicts Reform UK wins nothing, in the election where it won
twelve contests.** No error statistic in the bundle says that as plainly. MAE
of 3.33 on Reform rows sounds like a model that is roughly right; a seat
projection of zero against twelve is a model that missed the event.

The mechanism is not new — it is the under-prediction documented in
[`reform_interaction_terms.md`](reform_interaction_terms.md) — but its
consequence was not visible until the seats were counted. Reform's predicted
share sits near 9.35 per cent against 10.80 observed, which is close enough to
look acceptable and far enough to lose every seat, because a seat is won by
ranking above the boundary rather than by being close to the truth.

### The cross-check that came free

The new module computes `party_seat_total_absolute_error` from the exported
projection. It returns **232**, identical to the figure `metrics.json` had
been publishing from a separate calculation. Two independent paths to the same
number is weak evidence taken alone, but it does rule out the failure mode
that mattered: the published error was not describing a different allocation
from the one now exported. `metrics.json` now derives the figure from the
projection, so the two cannot drift apart in future.

### Instability, recomputed on the current features

Exporting fold-level coefficients showed **41 of 127 encoded features change
sign between folds**, including `previous_party_vote_share` and
`party_county_strength_previous` — the two predictors the entire Reform
interaction argument rests on. The model card had carried "31 of 106" from
before the strength and interaction features were added; that figure is now
corrected. The direction of the finding is unchanged and, if anything,
stronger: adding features did not stabilise the historical signal.

---

## Requirement coverage

| brief section | where it lives |
| --- | --- |
| application, package, CLI, config, tests, README, logging | `cli.py`, `configuration.py`, `logging_setup.py`, `config/baseline_model.yaml`, `README.md` |
| data validation, all 12 checks | `data_quality_report.json`, `candidate_data_validation.py`, `candidate_evidence_layers.py` |
| prediction targets, all 7 outputs | `holdout_predictions.csv`, `*_election_probabilities.csv`, `*_seat_projection.csv`, `holdout_party_seat_totals.csv`, `reform_metrics.json` |
| leakage rules and audit | `leakage_audit.csv`, `candidate_leakage_audit.py` |
| feature engineering | `feature_schema.json`, `feature_dictionary.csv` |
| splits, grouped and chronological | `split_manifest.csv`, `candidate_splits.py` |
| three architectures | `candidate_share_model.py`, `candidate_boosted_model.py`, `candidate_hierarchical_model.py` |
| Reform approach, UKIP kept separate | `reform_metrics.json`, [`ukip_contextual_sensitivity.md`](ukip_contextual_sensitivity.md) |
| selection, auto and manual | `architecture.json`, `architecture_comparison.csv` |
| evaluation, all 16 measures | `metrics.json` |
| explainability, all 7 outputs | `explainability.json` |
| six-page interface | `app/` |
| model bundle, all 16 required files | `outputs/model_bundle_v1/` — 29 files |
| model card, all 13 sections | [`candidate_model_card.md`](candidate_model_card.md) |
| acceptance tests | `tests/` — 444 tests |
| concise technical report | [`technical_report.md`](technical_report.md) |

### One requirement met in spirit rather than to the letter

The brief lists eight criteria for auto-selection, including "Reform UK
ranking and elected-status accuracy" and "calibration". The gate runs on **one
declared primary criterion** — Reform vote-share MAE, which the brief names
first — with a stability check, rather than combining eight measures into a
score.

That is deliberate. A composite of eight criteria over fourteen Reform rows
would produce a number nobody could interpret and that would move on noise.
But the omitted criteria are now recorded in `architecture_comparison.csv`
(`reform_rank_accuracy`, `reform_elected_accuracy`) so a reader who disagrees
with the choice of primary criterion has the columns to argue from. Calibration
is reported per architecture in `metrics.json` but is not part of the
selection record.

---

## Outside Prompt 1

Two things this repository does not have, and should not be assumed to:

- **A blinded 2026 prediction.** The brief asks for one and the split design
  supports it, but the holdout's metrics were read during development. The
  disclosure is in the model card; the discipline was weaker than the design.
- **Anything from Prompt 2.** No news is collected, classified or modelled
  here, and the baseline is deliberately frozen against it.

---

## Related records

- [`technical_report.md`](technical_report.md) — the report for the review
- [`architecture_selection_evidence.md`](architecture_selection_evidence.md) —
  why the shipped architecture is not the best on most measures
- [`run_configuration_and_reproducibility.md`](run_configuration_and_reproducibility.md)
  — the same "it existed but was not delivered" failure, one round earlier
