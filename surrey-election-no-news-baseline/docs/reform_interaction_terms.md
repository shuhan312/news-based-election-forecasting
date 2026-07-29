# Reform UK interaction terms: the experiment, and what it exposed

**Recorded 29 July 2026.** The brief asks to "permit interactions between
Reform UK and relevant historical predictors". By the time they were built the
data had asked twice as well. This records the experiment, its result, and a
flaw it exposed in the architecture-selection design - which the same session
then fixed, changing the selected architecture back.

---

## Why they were built: two independent pieces of evidence

**First.** SHAP on the tree model showed `previous_party_vote_share`
contributing **+0.0498 to Conservative predictions and −0.0880 to Reform
ones** — one feature moving two parties in opposite directions.

**Second.** Adding county-level strength features made the linear
architectures substantially *worse* on Reform, the opposite of their purpose:

| | Reform vs equal split, before | after strength |
| --- | ---: | ---: |
| A regularised linear | −16.7% | **−42.6%** |
| C partial pooling | −15.8% | **−31.6%** |

Both observations have one explanation. County strength and division share
move together for almost every party; Reform is the exception, at 20.67 per
cent county-wide from single-member by-elections against 10.80 per cent in
two-member wards where its support splits across two ballot lines. A linear
model fits one global slope per feature and applies it to every party, so
Reform is dragged along a relationship it does not follow. A tree can
condition on party.

An interaction column lets a linear model hold a second slope for one party.
It adds no information — every value is the product of two columns already in
the matrix — only the ability to express a conditional effect.

## The result: the hypothesis is confirmed

Primary holdout, 838 rows, observed Reform mean 10.80 per cent.

| architecture | | MAE | winner | Reform predicted | Reform vs equal split |
| --- | --- | ---: | ---: | ---: | ---: |
| A | baseline | 4.78 | 29.3% | 8.40% | −16.7% |
| A | + strength | 5.09 | 28.0% | 6.96% | −42.6% |
| A | **+ interactions** | **4.75** | 28.0% | **9.28%** | **−8.8%** |
| C | baseline | 4.89 | 30.5% | 8.91% | −15.8% |
| C | + strength | 4.65 | 41.5% | 7.53% | −31.6% |
| C | **+ interactions** | **4.39** | **42.7%** | **10.17%** | **−7.0%** |
| B | baseline | 4.78 | 32.9% | 9.44% | −12.4% |
| B | + strength | 4.53 | 30.5% | 9.35% | −11.1% |
| B | **+ interactions** | **4.53** | **30.5%** | **9.35%** | **−11.1%** |

Three things in that table, in order of how much they establish.

**Architecture B does not move at all.** Its three rows for strength and
strength-plus-interactions are identical to the digit. This is the strongest
evidence in the experiment: the diagnosis said linear models need an explicit
interaction while a tree already conditions on party implicitly, and the
interaction terms accordingly did nothing for the tree. Had they merely been
four extra columns that happened to help, B would have moved too.

**The linear damage is reversed and then some.** A goes from −42.6 back past
its −16.7 baseline to −8.8. C goes from −31.6 to −7.0, better than its −15.8
baseline.

**C's Reform prediction lands at 10.17 per cent against 10.80 observed** — a
gap of 0.63 points, against 2.96 at the start of the day.

### Which interaction is doing the work

| interaction | non-zero on Reform rows |
| --- | ---: |
| `reform_x_previous_party_vote_share` | **8 / 178** |
| `reform_x_party_county_strength_previous` | 172 / 178 |
| `reform_x_party_county_strength_trend` | 169 / 178 |
| `reform_x_party_contest_rate_previous` | 172 / 178 |

The interaction with division-level history is nearly empty, because Reform
has almost no division-level history. The county-strength interactions are
what recovered the models, which confirms the chain end to end: Reform's
problem was never that its history was used wrongly, but that it has only
county-level history and the model had no way to read it on a different slope.

## Scope of the terms

Reform UK and UKIP only. Interacting all 40 parties with all six historical
predictors would add roughly 240 columns to a 1,150-row training fold, which
fits noise reliably. UKIP's block is the brief's optional, clearly labelled
sensitivity feature and is **off by default**, so using it is always a
deliberate act. UKIP is never merged into Reform UK.

A missing base value produces a missing interaction, never zero. Zero is
correct for a non-Reform row — the indicator is off, the term does not apply —
and would be a lie for a Reform row whose base predictor is unknown.

---

## What this exposed: a three-row decision

Re-running architecture selection on the enriched features selects
**Architecture A**, the simplest, because no challenger clears the
five-per-cent gate:

```
C is not selected: improvement -1.4% does not exceed 5%; loses 2 of 4 folds
B is not selected: improvement  1.2% does not exceed 5%
```

On the decision fold, all three architectures sit within 1.4 per cent of each
other on Reform vote-share MAE: A 7.355, C 7.455, B 7.264.

**The decision fold contains three Reform UK rows.**
`dev_through_first_2025_test_later_2025` tests the three by-elections of 16
October 2025: 16 candidate rows, of which three are Reform. The primary
selection criterion is Reform vote-share MAE, and three rows cannot
distinguish three architectures, so they cluster inside the gate and the
incumbent survives by default.

The mechanism behaved exactly as designed. The design is underpowered.

This must not be resolved by noticing that C is clearly best on the holdout
and selecting it: choosing an architecture on the holdout spends the holdout,
which is the specific thing the decision-fold rule exists to prevent. The
selection currently on record is therefore A, and it is on record for a reason
that is visible.

### The fix, applied

Selection now pools the development folds by row instead of reading one.
Pooling is by rows rather than by folds because MAE is a mean of absolute
errors, so a row-weighted mean of per-fold MAEs is exactly the MAE over the
pooled rows. Weighting folds equally would let a three-row fold count as much
as a six-row one and has no answer for the fold containing no Reform rows.

Pooled Reform vote-share MAE across the four development folds:

| architecture | pooled | 2021 fold (6 rows) | 2025 by-elections (7) | later 2025 (3) |
| --- | ---: | ---: | ---: | ---: |
| A regularised linear | 10.833 | 15.66 | 8.19 | **7.36** |
| C partial pooling | 11.118 | 15.10 | 9.27 | 7.45 |
| **B boosted trees** | **9.931** | **12.84** | 8.58 | 7.26 |

The last column is why the single-fold decision failed: on those three rows
the architectures sit at 7.36, 7.45 and 7.26, within 1.4 per cent of each
other. Pooled, B leads A by 8.3 per cent and clears the gate. **B's advantage
comes almost entirely from the 2021 fold**, the one with six Reform rows —
which the single-fold decision had excluded.

Selection on the pooled basis:

```
B_gradient_boosted_trees displaces A_regularised_linear:
  improves reform_vote_share_mae by 8.3% (threshold 5%)
  loses on 1 of 4 development folds (limit 1)
C_partial_pooling is not selected:
  improvement -2.6% does not exceed 5%; loses on 2 of 4 folds
```

`decision_basis` and `decision_rows` are now recorded on the outcome and in
`architecture.json`, so the evidence a selection rests on is readable without
re-running it. The failure above happened partly because nobody could see that
the number was three.

### The pooled row count is not an independent sample size

The pool is 16 rows, and **those 16 are not 16 independent observations.**
`dev_through_2023_test_2025_by_elections` tests all five 2025 by-elections and
`dev_through_first_2025_test_later_2025` tests three of them, so three Reform
rows are counted twice. The overlap does not distort the comparison between
architectures, which are scored on identical rows, but 16 must not be quoted
as a sample size. The underlying distinct Reform rows in the development
period number 14.

### Selection and the holdout disagree

Pooled development evidence selects **B**. On the primary holdout, which took
no part in the decision, **C** is clearly better: MAE 4.39 against 4.53,
winner accuracy 42.7 against 30.5 per cent, Reform 7.0 against 11.1 per cent
worse than an equal split.

That disagreement is a result, not an error to be resolved. It says the
development folds — fourteen distinct Reform rows across four folds — cannot
reliably separate the two architectures, and that whichever is chosen rests on
evidence thinner than the holdout gap suggests. Selecting C because the
holdout prefers it would spend the holdout; reporting the disagreement costs
nothing and is true.

---

## Related records

- [`historical_strength_features.md`](historical_strength_features.md) — the
  features these terms interact with, and the damage that motivated them
- [`candidate_model_card.md`](candidate_model_card.md) — the SHAP finding that
  started the chain
- [`candidate_split_and_leakage.md`](candidate_split_and_leakage.md) — why the
  decision may not read the holdout
