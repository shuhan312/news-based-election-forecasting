# N4: cold-start shrunk-party-strength baseline

## Research role

The coverage report (`docs/coverage_aware_evaluation_methodology.md`)
quantified the structural gap in the existing no-news models: persistence
and ridge have zero coverage on Cohort B (party entry / no local history,
148 rows) and Cohort C (geographically non-comparable, 680 rows), because
both require a safe previous local party vote share. N4 exists to close as
much of that gap as a no-news model legitimately can. It predicts from
Surrey-wide party strength only, so a new entrant or a changed-boundary
2026 ward still receives a real prediction. It never reconstructs local
geography: on Cohort C it is explicitly a geography-agnostic baseline, not
recovered local history.

## Estimator (exactly as implemented)

For one target contest (election x area) with k contesting party rows:

```text
prior            = 100 / k
n                = count of strictly earlier Surrey-wide realised shares
                   for this standard party name
historical_mean  = mean of those n shares
w                = n / (n + lambda)          lambda = 5.0, fixed
strength         = w * historical_mean + (1 - w) * prior
predicted share  = strength / sum(contest strengths) * 100
```

- **Global prior**: the equal split of the target ballot (100/k). It uses
  only the publicly known list of contesting parties, never any target
  outcome.
- **lambda = 5.0, pre-specified**: the prior is worth five pseudo-elections
  of evidence. It was fixed before evaluation and NOT tuned on any data,
  full-dataset or otherwise; the ablation below reports what this choice
  costs or gains.
- **Zero-history parties receive the prior**, never a missing prediction.
- **Candidate-specific Independents** are excluded from the history pool
  and always scored as zero-history: unrelated independents do not form one
  continuing party whose strength could be pooled.
- **UKIP and Reform UK** are distinct keys in the history pool; Reform UK's
  history is only Reform UK's own results (verified by test).
- **No local-history field is read at all**: an invariance test proves the
  predictions are bit-identical when every `previous_party_vote_share` in
  the input is altered.
- Winner calls are made only for single-member contests with a unique
  strength leader; multi-member wards get no winner call (the repository's
  frozen rule against converting vote rankings into seat predictions).

## Temporal validation

History pools are built per fold via the existing
`temporal_validation.iter_temporal_folds` - strictly earlier elections
only, same-day elections never treated as history, 2013 never a test fold.
Each prediction records its information cutoff (the target election's own
date) and the number of training elections. Unlike ridge, N4 has no
training-fold cohort requirement, so the 2015 Weybridge bootstrapping gap
that leaves ridge at 99.5% eligibility-conditioned coverage does not occur:
N4 reaches 100%.

## Results (live release, lambda = 5.0)

### Coverage

| Scope | Target rows | Eligible | Valid predictions | Share-scored | Own-covered MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Overall | 1,603 | 1,245 | 1,245 | 781 | 10.96 |
| Cohort A | 775 | 775 | 775 | 775 | 11.00 |
| Cohort B | 148 | 148 | 148 | 6 | 6.11 |
| Cohort C | 680 | 322 | 322 | 0 | n/a |

Target-universe coverage is 77.7%, against 48% for persistence/ridge.
Every Cohort B row now has a valid prediction (previously zero). The 358
ineligible rows are all 2013 (study start, no earlier data). Cohort C's
scored count is zero because its evaluable rows are all 2026 multi-member
contests, whose party-share target is undefined by design - their
predictions exist and are auditable, but no share error can be computed.
This is the honest limit of what Cohort B/C evaluation can currently say
about share accuracy: only 6 Cohort B rows carry a defined share target.

### Five-model common sample (identical 740 contests)

| Model | MAE |
| --- | ---: |
| `previous_result_persistence_v1` | 9.23 |
| `ridge_fundamentals_v1` | 9.66 |
| `party_historical_mean_reference_v1` | 10.44 |
| `cold_start_shrunk_party_strength_v1` | 10.86 |
| `equal_share_reference_v1` | 15.60 |

On safe-history contests N4 is, as expected, weaker than the local-history
models - it deliberately refuses the information they use. Its value is
coverage, not Cohort A accuracy, and the two claims are kept separate.

### Winner prediction (single-member areas)

| Model | Coverage | Accuracy |
| --- | ---: | ---: |
| N4 cold start | 177/177 = 100% | 63.8% |
| persistence | 169/177 = 95.5% | 80.5% |
| party historical mean | 68.6% | 67.2% |

The coverage-accuracy trade-off is explicit: N4 calls every seat, including
the 8 persistence cannot call, at a substantially lower hit rate.

### Ablation: unsmoothed vs smoothed (identical 781 scored rows)

| Variant | MAE |
| --- | ---: |
| Unsmoothed Surrey-wide party mean (w=1 when n>0) | **10.21** |
| Smoothed N4 estimator (lambda=5) | 10.96 |

**The pre-specified shrinkage hurts on this data.** Pulling established
parties toward an equal-share prior degrades their predictions more than it
stabilises sparse-history parties. Because lambda was fixed in advance
rather than tuned, this negative result is reported as found; the smoothed
estimator remains the declared N4 (changing the specification after seeing
results would be exactly the kind of silent tuning this project's
methodology prohibits). The practical reading: the equal-share prior is a
weak prior for parties with any established Surrey record, and a future
model (N5 or a revised prior) should treat this ablation as evidence, not
noise.

### Zero-history performance

64 scored predictions were made for parties with no prior Surrey history at
all (pure prior), MAE 12.72. For Reform UK specifically: 94 predictions
issued, 13 scorable, MAE 12.89, of which 6 contests were true zero-history
cold starts. A no-news model can now always say *something* about a new
entrant; how much better a news-aware model can do on exactly these rows is
the comparison the supervisor's central question requires.

## Diagnostics and reproduction

Every prediction row records: identifiers, cohort-joinable ID, historical
observation count, raw historical mean, global prior, shrinkage weight,
smoothed strength, normalised share, information cutoff, training-election
count, actual share/error where defined, and the winner decision with its
status. Integrity checks assert: unique IDs, no negative shares, every
contest summing to 100 within 1e-6, and strictly-earlier history (a second
date assertion on top of the fold guarantee).

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/run_cold_start_report.py
```

Writes `n4_predictions.csv`, `n4_cohort_evaluation.json`,
`n4_model_comparison.csv` and `n4_ablation.json` under
`surrey-election-no-news-baseline/outputs/cold_start/`, deterministically
(verified by test) and without a network request.

## Limitations

1. Cohort B share-accuracy evidence is thin: 142 of its 148 rows are
   multi-member with no defined share target, leaving 6 scorable rows.
2. Cohort C share accuracy is currently unmeasurable (all evaluable rows
   are 2026 multi-member); N4 there is auditable but unscored until a
   multi-member evaluation convention is agreed.
3. The equal-share prior is demonstrably weak for established parties (see
   ablation); this is recorded evidence for any successor model.
4. 2026 winner/seat evaluation is out of scope by the frozen rule against
   converting vote rankings into seat predictions.
