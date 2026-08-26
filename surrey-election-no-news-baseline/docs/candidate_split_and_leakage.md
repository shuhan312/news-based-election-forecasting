# Chronological split and leakage audit (candidate estimand)

**Status:** adopted 28 July 2026. Steps 2 and 3 of the supervisor's ordering,
built on the candidate cohort established in
[`candidate_level_estimand.md`](candidate_level_estimand.md).

Nothing is fitted here. Fixing the folds and the permitted-predictor list
*before* any model exists is the point: the model then has no opportunity to
influence either, so neither can be a choice made after seeing a score.

## Split design

Every split is defined by **dates**, never by election names or list
positions:

```text
train = elections polled on or before train_end
test  = elections polled between test_start and test_end   (both inclusive)
```

with `train_end < test_start` asserted at construction. Two of the brief's
rules then hold by arithmetic rather than by care:

- *"All candidates from one contest must remain in the same split."* A contest
  belongs to one election, an election has one polling date, so a contest
  cannot straddle the boundary.
- *"Do not train on one event from 7 May 2026 and test on another event from
  the same date."* The primary holdout's `train_end` is 6 May 2026, so none of
  the three same-day events (East Surrey, West Surrey, the Warlingham
  by-election) can reach training.

By-elections need no special handling: a by-election is an election with its
own polling date and lands in training or test accordingly.

### The seven named splits

| split | role | train | test | train Reform | test Reform |
| --- | --- | ---: | ---: | ---: | ---: |
| `dev_through_2016_test_2017` | development | 379 | 377 | **0** | 0 |
| `dev_through_2020_test_2021` | development | 767 | 331 | **0** | 6 |
| `dev_through_2023_test_2025_by_elections` | development | 1,102 | 27 | 6 | 5 |
| `dev_through_first_2025_test_later_2025` | development | 1,113 | 16 | 8 | 3 |
| `primary_holdout_7_may_2026` | primary holdout | 1,129 | 838 | 11 | 163 |
| `secondary_holdout_haslemere_before_may` | secondary holdout | 1,129 | 4 | 11 | 1 |
| `secondary_holdout_haslemere_after_may` | secondary holdout | 1,967 | 4 | 174 | 1 |

The four development folds are the brief's own list, verbatim. The two
secondary holdouts differ *only* in `train_end`: the first withholds all 7 May
2026 results, as the brief requires for the honest evaluation; the second is
the brief's optional retrain-through-May variant, reported separately and
never as a headline, because by then the primary holdout has been opened.

### Rolling-origin folds

The brief also asks for rolling-origin evaluation, so stability over time can
be inspected rather than inferred from four hand-picked boundaries. Twelve
further folds are generated, one per polling day, training on every strictly
earlier day. Grouping is by **polling day**, not by election, so same-day
elections form one fold and cannot train on each other — the primary
holdout's rule applied everywhere.

Generation stops before 7 May 2026 by default, so routine development
evaluation cannot consume the untouched holdout by accident. Raising that
boundary is a deliberate act.

The first polling day (2 May 2013) has nothing earlier to train on and is not
evaluable. It stays available as training data for every later fold — the
release's own study-start boundary, reproduced without a special case.

### Reform UK by fold — the finding to report

**Ten of the nineteen splits train on zero Reform UK observations.** The first
fold with any Reform in training is `dev_through_2023_test_2025_by_elections`,
with six.

The primary holdout trains on **11** Reform rows and tests on **163**. No
Reform-specific coefficient or interaction estimated from eleven observations
across three election events should be reported without an uncertainty
interval, and the brief's instruction to "warn when Reform-specific estimates
are based on very small samples" applies to essentially every fold. Each
split summary therefore carries a `reform_estimable` flag, computed from the
same assignment the model uses, so the warning cannot drift from the numbers
actually trained on.

## Leakage audit

The brief's schema — field name, source sheet, permitted or excluded, reason,
earliest availability date, restrictions, relevant permission field — with two
deliberate additions (`table`, `role`, `allowed_as_predictor`) that make the
verdict machine-readable.

78 rows: **49 permitted** published feature columns, **14 excluded** target
columns, **15 excluded by construction**.

> **Note (release version):** These counts describe the pre-model release fixed
> at adoption (49 published feature columns, 25 permitted predictors). The
> shipped model later adds the county-strength history and Reform/UKIP
> interaction features, reaching **64 published columns, 39 permitted predictors
> (35 used by default)** — see [`candidate_model_card.md`](candidate_model_card.md).
> The numbers here are not edited after the fact; the later figures are the
> current ones.

### Why permitted fields are listed too

An exclusion list alone cannot be checked. A reader seeing only what was
excluded cannot tell whether a permitted field was reasoned about or merely
never noticed. Every published column therefore appears exactly once with an
explicit verdict — and an unclassified column **stops the build** rather than
defaulting to permitted, because the failure mode of a leakage audit is
silently blessing something new.

### Why prohibited fields are listed even though they are absent

The 15 fields the brief names as prohibited are recorded as
`excluded_by_construction`, with the workbook sheet where they do live. That
is a stronger statement than silence: the field could not enter the feature
matrix because it is not in the feature table at all.

`change_in_vote_share` is the one worth pointing at. It looks historical, but
it is current minus previous share, so it contains the target by construction.
The workbook itself already identifies it as unsuitable as a baseline
predictor.

Two pairs are deliberately close-but-different, and the audit keeps them
apart: `analysis_previous_turnout` is permitted while `turnout` is prohibited;
`previous_electorate` is permitted while `electorate` is prohibited.

### Why "earliest availability" is an event, not a date

The brief asks for an earliest availability *date*. A field-level audit cannot
carry one, because it differs per row: the previous party vote share for a
2017 contest became available in May 2013, and for a 2026 contest in May 2021.
What is constant per field is the **event** at which the value first exists,
so the audit publishes a controlled event label plus the column carrying the
row's actual date. That is auditable; a single fabricated date would not be.

| event | meaning |
| --- | --- |
| `statutory_order_publication` | boundaries and seat structure, fixed well before polling |
| `previous_election_declaration` | a result of a strictly earlier election |
| `nomination_close` | who stood, for which party, how many candidates — about 19 working days out |
| `release_construction` | assigned when the release is built; carries no election information |
| `target_election_declaration` | exists only after the count. Never permitted |

### From 49 published columns to 25 permitted predictors

Publication and permission are different questions. Of 49 published columns:

| role | count | may be modelled |
| --- | ---: | --- |
| `predictor` | 25 | yes |
| `provenance` | 11 | no — describes evidence |
| `linkage_only` | 7 | no — person and area identity, for joining history |
| `identifier` | 5 | no |
| `cohort_label` | 1 | no — selecting rows is not predicting from them |

`permitted_predictors()` is the single source of truth. Modelling code selects
from it rather than from a list typed out again, so the audit and the model
cannot disagree. A model that wants a column not returned by it must first add
a classification, which forces the reasoning to be written down.

`assert_no_prohibited_column()` is the brief's requested automated guard,
callable at build time as well as in tests, so the guarantee holds in
production and not only under pytest. It rejects prohibited outcome columns
*and* non-predictor columns — including `candidate_id`, because the brief is
explicit that candidate names and IDs are for historical linkage, not
unrestricted high-cardinality predictors that allow memorisation.

## Integrity checks

Both run against the produced manifest, not against the split definitions, so
an assignment bug cannot pass merely because the definitions read correctly:

- `assert_contest_integrity` — no contest appears in two folds of one split.
- `assert_holdout_untouched` — no development or rolling fold trains on any
  row polled on or after 7 May 2026.

## Reproduction

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python \
  surrey-election-no-news-baseline/scripts/build_candidate_split_and_leakage.py
```

Outputs `split_manifest.csv` (37,449 rows: every cohort row in every split,
including `unused`, so the file accounts for every row rather than leaving
absence to be inferred), `leakage_audit.csv` and `split_summary.json`.

## What this does not yet do

No model is fitted. The next step is the brief's step 4 — the no-news
baseline model itself — which needs a feature matrix built from
`permitted_predictors()`, out-of-fold predictions for every eligible
historical row, and the architecture comparison (A regularised, B
gradient-boosted, C hierarchical). Architecture B requires a dependency the
environment does not currently carry; C can use the already-declared numpyro.
