# What the architecture selection actually bought, and what it cost

**Recorded 29 July 2026.** The bundle ships Architecture B. This records the
complete evidence behind that, including the parts that argue against it.

The short version: **B is worse than both A and C on every overall metric, on
every split role, without exception.** It is selected because the brief names
Reform UK vote-share MAE as the first selection criterion, and on Reform out
of fold B is not slightly better but dramatically better. That trade is real,
it is not free, and the advantage it rests on **does not appear in the primary
holdout at all**.

---

## The complete table

All three architectures, same rows, same folds, same features. Pooled by rows
within each split role, which for MAE is exact rather than an approximation:
a row-weighted mean of per-fold MAEs is the MAE over the pooled rows.

### Rolling-origin folds — the out-of-fold evidence, 792 rows

| architecture | MAE | winner | Reform rows | Reform MAE |
| --- | ---: | ---: | ---: | ---: |
| A regularised linear | 8.97 | 74.9% | 14 | 16.11 |
| C partial pooling | **8.87** | **76.1%** | 14 | 16.13 |
| **B boosted trees (shipped)** | 9.85 | 73.8% | 14 | **10.18** |

### Development folds — what selection reads, 762 rows

| architecture | MAE | winner | Reform rows | Reform MAE |
| --- | ---: | ---: | ---: | ---: |
| A regularised linear | 8.67 | 77.5% | 16 | 10.83 |
| C partial pooling | **8.47** | **78.2%** | 16 | 11.12 |
| **B boosted trees (shipped)** | 9.84 | 74.4% | 16 | **9.93** |

### Primary holdout — 7 May 2026, took no part in the decision, 838 rows

| architecture | MAE | winner | seat set | Reform rows | Reform MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| A regularised linear | 4.75 | 28.0% | 19.5% | 163 | 3.26 |
| C partial pooling | **4.39** | **42.7%** | **23.2%** | 163 | **3.21** |
| **B boosted trees (shipped)** | 4.53 | 30.5% | 22.0% | 163 | 3.33 |

---

## Reading the table honestly

**What B buys.** On the fourteen out-of-fold Reform rows, B's MAE is 10.18
against roughly 16.1 for both linear architectures — a 37 per cent reduction,
far outside anything the other differences resemble. On the pooled development
folds it is 9.93 against 10.83, the 8.3 per cent that cleared the selection
gate. B is also the only architecture in this project to beat an equal split
on out-of-fold Reform rows, by 5.0 per cent.

**What B costs.** Roughly one percentage point of overall MAE at every split
role — 9.85 against 8.87 out of fold, 9.84 against 8.47 on development folds
— and one to four points of winner accuracy. On the holdout it recovers some
of that against A but stays behind C on every column.

**Where the argument breaks down.** On the primary holdout, B's Reform
advantage does not merely shrink, it **inverts**: B is the *worst* of the
three on Reform, 3.33 against C's 3.21 and A's 3.26. The single criterion the
selection rests on is the one criterion that reverses on unseen data.

That is not a reason to switch to C. Choosing an architecture because the
holdout prefers it spends the holdout, which is the specific thing the
development-fold rule exists to prevent, and it would leave nothing untouched
to report the news layer against. But it is a reason to state plainly that
**the selection is not well supported.**

## Why the evidence is this weak

Fourteen distinct Reform rows in the development period. The contest-level
bootstrap on the out-of-fold Reform MAE runs from 7.42 to 12.74 — five and a
third percentage points wide. A 37 per cent gap is large enough to be visible
through that width, which is why B was selected at all; the 8.3 per cent gap
that actually cleared the gate is not.

Two structural facts compound it:

- **The out-of-fold and holdout Reform rows are not comparable populations.**
  Out of fold, all fourteen Reform rows are by-elections, single-member, where
  Reform's county-wide strength of 20.67 per cent applies directly. On the
  holdout, 163 Reform rows are mostly two-member wards where support splits
  across two ballot lines and the observed mean is 10.80 per cent. An
  architecture that handles the first well is not thereby shown to handle the
  second.
- **The holdout has 163 Reform rows against the development period's 14.**
  The holdout is by far the better evidence about Reform, and it is the one
  piece of evidence the selection may not use.

## What follows from this

1. **The selection stands.** B ships, on the stated criterion, decided on
   development folds only, with `decision_basis` and `decision_rows` recorded
   in `architecture.json`.
2. **The disagreement is published, not resolved.** `reform_metrics.json`
   carries every architecture's Reform figures on the holdout, and
   `architecture_comparison.csv` carries all three on every fold, so a reader
   can reach a different conclusion from the same evidence.
3. **This is a question for the supervisor review**, not something to settle
   silently. The honest summary is: the development evidence cannot reliably
   separate B from C, the holdout prefers C on every metric including Reform,
   and the rule that protects the holdout is what stops that from being acted
   on. Whether to re-designate the primary criterion — for example to overall
   MAE with Reform as a reported secondary — is a methodological decision that
   should be taken before the news layer is built, because the news layer
   trains on whichever architecture's out-of-fold predictions ship.

---

## Resolved 30 July 2026: the differences were measured, not argued

The section above says the development evidence "cannot reliably separate B
from C". That was an assumption. Nothing in this project had measured whether a
difference between two architectures survives resampling — the comparison
reported a point estimate per architecture per fold, and the selection rule read
those point estimates. So a 0.10-point gap and a 5.90-point gap were treated as
the same kind of evidence, differing only in whether they cleared a threshold.

`no_news_baseline/architecture_paired_bootstrap.py` now measures it: paired
(both architectures predict the same rows, so their errors are correlated and
the difference has far smaller variance than either error alone), resampled by
contest (candidate shares within a contest sum to 100, so rows are not
independent), 2,000 resamples on seed 20260728 — the same unit and seed used
everywhere else in this repository. Input is each bundle's own
`out_of_fold_predictions.csv` and its own `absolute_error` column, so nothing is
recomputed and no second definition of the compared quantity can creep in.

### The result, on the 792 out-of-fold rows

| comparison | difference | 95% interval | verdict |
| --- | ---: | :---: | --- |
| A − C, all candidates | +0.103 | [−0.385, +0.597] | **not distinguishable** |
| A − C, Reform only (14 rows) | −0.022 | [−0.844, +0.789] | **not distinguishable** |
| A − B, all candidates | **−0.882** | [−1.342, −0.418] | **distinguishable — A better** |
| A − B, Reform only (14 rows) | **+5.934** | [+0.743, +12.658] | **distinguishable — B better** |

C is better than A in 67.3% of resamples and B is better than A on Reform in
99.0% of them.

### What that overturns

**Two of this project's working conclusions were wrong, and in opposite
directions.**

The first: C was described in working notes as beating A "on every adequately
sampled metric". It does not. C's overall advantage is 0.103 against an interval
half-width of roughly 0.49, and a third of resamples put A ahead. **A and C are
the same model to the precision this data supports** — which is unsurprising, as
C is the same closed-form ridge with one additional penalty on the party block.

The second, and the one that mattered: this document assumed 14 Reform rows
could not separate the architectures. **They can.** The effect is 5.93 points,
large enough that even 14 rows produce an interval excluding zero. A wide
interval is not the same as an interval containing zero, and the earlier
reasoning conflated them.

### What follows

1. **B remains the shipped architecture, and the reason is now measured rather
   than asserted.** The brief names Reform UK vote share as the study target,
   and B's advantage on it is distinguishable with a lower bound of +0.74
   points. The case for re-designating the primary criterion rested on that
   criterion being unmeasurable at this sample size; the measurement shows it is
   measurable, so the case falls.
2. **B's cost is also measured and also real:** 0.88 points of overall MAE,
   distinguishable, with not one resample of 2,000 favouring it. Selecting B
   buys accuracy on the study party by giving up accuracy on everyone else. That
   is a defensible trade for this research question and it is not a free one.
3. **The limitation that no measurement here can settle.** All 14 out-of-fold
   Reform rows are single-member by-elections, where Reform's county-wide
   strength of 20.67% applies directly. The 2026 target is two-member wards
   where support divides across two ballot lines and the observed mean is
   10.80%. B is therefore shown to predict Reform well **in single-member
   by-elections**; whether that transfers to two-member wards is untested, and
   testing it would require the holdout. This must be stated wherever B's Reform
   advantage is cited.
4. **The news comparison will report all three baselines, not one.** A primary
   result against B, with A and C as robustness rows. The reason is specific
   rather than a hedge: B has the lowest Reform error out of fold, so it is the
   hardest baseline for news to improve upon, while A and C carry roughly 5.9
   points more Reform error — news measured against them could appear useful
   simply by absorbing that error. If news improves on all three, the finding is
   robust to a choice this evidence cannot make cleanly. If it improves only
   against A and C, that is itself the result.
5. **The open supervisor question is closed.** Item 3 of the previous section
   asked whether to re-designate the primary criterion, noting it should be
   settled before the news layer is built. The supervisor's reply of 30 July
   delegates it — "this is your methodological decision… You can keep the tree
   model as primary and partial pooling as a robustness model, or choose a
   broader rule based on the pre-2026 results. Just explain the reasoning
   clearly" — subject to not using the 2026 holdout to choose retrospectively.
   The decision above uses out-of-fold evidence only. The holdout figures in the
   table further up this document were recorded before this decision and took no
   part in it; had they been absent, the same measurement would have produced the
   same choice.

Reproduce the measurement:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train \
  --architecture A_regularised_linear --output surrey-election-no-news-baseline/outputs/model_bundle_paired_A
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train \
  --architecture B_gradient_boosted_trees --output surrey-election-no-news-baseline/outputs/model_bundle_paired_B
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.architecture_paired_bootstrap \
  surrey-election-no-news-baseline/outputs/model_bundle_paired_A \
  surrey-election-no-news-baseline/outputs/model_bundle_paired_C
```

---

A manual run of C is reproducible for comparison and costs nothing to inspect:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train --architecture C_partial_pooling --output surrey-election-no-news-baseline/outputs/model_bundle_manual_c
```

---

## Related records

- [`reform_interaction_terms.md`](reform_interaction_terms.md) — the pooling
  fix that produced this selection, and the three-row decision it replaced
- [`ukip_contextual_sensitivity.md`](ukip_contextual_sensitivity.md) — a
  feature that improved overall accuracy while damaging Reform, refused for
  the same reason B is preferred here
- [`candidate_model_card.md`](candidate_model_card.md) — uncertainty
  intervals, and the sources no bootstrap covers
