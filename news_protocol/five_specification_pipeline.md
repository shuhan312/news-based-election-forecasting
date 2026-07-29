# The five specifications, and two joins that were wrong

**Recorded 29 July 2026.** The comparison this project exists to make is
between five specifications:

```
1. no-news baseline      the frozen Stage 1 model, nothing added
2. local news            division-level coverage only
3. national news         election-wide coverage only
4. combined              both
5. full                  both, plus permitted baseline context
```

Local and national are kept apart throughout because they are hypothesised to
do different jobs — national coverage showing whether a party is rising at
all, local coverage showing which divisions convert that into votes. A pooled
"news" block would answer neither, since one coefficient cannot say which
mechanism produced it.

Building the pipeline produced two corrections to figures recorded earlier the
same day, and found two joins that were silently wrong. All four are here.

Reproduce with:

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.run_specification_coverage
```

---

## What each specification can currently be estimated from

| specification | rows | Reform rows | rows carrying news | Reform rows carrying news |
| --- | ---: | ---: | ---: | ---: |
| baseline | 792 | 14 | 0 | 0 |
| local | 792 | 14 | **17** | **0** |
| national | 792 | 14 | **708** | **6** |
| combined | 792 | 14 | 708 | 6 |
| full | 792 | 14 | 708 | 6 |

By feature source:

| source | rows reached |
| --- | ---: |
| `local_party` — coverage of this party in this division | 17 |
| `local_context` — coverage of this division, no party named | 0 |
| `national_party` — coverage of this party, election-wide | 500 |
| `national_context` — national political coverage, no party named | 708 |

### Correction: the Reform training sample is not zero

An earlier entry recorded that Reform UK has no news in the training period at
either tier. **That is wrong at the national tier.** The measurement then
counted only rows where Reform was the *focal party* of an election-wide
record, and all of those are 2026. It missed the second kind of national row.

Corrected: Reform has **0 rows with local news and 6 rows with national news**
in the training period. Six is still few enough that any Reform-specific
estimate must be quoted with it, but it is the difference between "cannot be
estimated at all" and "estimable with a very wide interval".

### Correction: the local sample is 17, not 20

The earlier figure of 20 came from a join that did not match on party — see
below. Once a candidate only sees coverage of their own party, 17 rows carry
local news.

---

## The two joins that were wrong

### 1. News was attached without matching the party

The first join keyed news rows on `(election, division)` alone. Each division
carries one aggregated row per party per window — five parties and three
windows in the 2021 sample, fifteen rows per division. Keying on the division
alone meant they overwrote each other in the index, and whichever survived was
attached to **every candidate in that division regardless of party**.

A Reform UK candidate would have been given the Conservatives' coverage. Every
figure produced that way was about the wrong thing, including the 20-row count
reported earlier.

The key is now `(election, division, party, window)`.

### 2. The coverage report read its schema off one row

Feature columns were attached only when a candidate's election had matching
news. The coverage report then derived the list of news columns from
`rows[0]`. The first row is a 2017 candidate, 2017 has no division-level news,
so that row carried no news columns at all — the report found an empty column
list and concluded there was no news anywhere.

It reported **zero news for all five specifications**, including `local`,
which had 17 rows of it.

The fix is not in the report. Every specification now emits its full column
set on every row, with `None` where nothing matched, for two reasons: a
training matrix needs the same columns on every row, and an all-`None` column
is itself a finding — it says an arm reached nothing — whereas an absent
column is indistinguishable from one that was never asked for.

---

## A design decision worth stating

News rows come in two kinds and cannot be treated the same way.

**Party-specific** rows name a focal party: coverage *of the Conservatives* in
Guildford East. These attach only to that party's candidates.

**Party-agnostic** rows carry `(no_focal_party)`: a planning dispute, a
council-finance story, coverage of the division rather than of anyone standing
in it. These attach to every candidate in the division, because they are
context that applies to the contest as a whole.

Discarding the second kind would throw away most of the local corpus.
Attaching it to one party would give an article a slant it does not have. Each
keeps its own feature prefix, so a model can distinguish "my party was
covered" from "this division was in the news".

The same split applies at the national tier, and it is where Reform's six
training rows come from: `national_context` reaches 708 rows because national
political coverage applies to the whole election, while `national_party`
reaches 500.

---

## Two properties the builder holds to

**Every candidate row appears, with or without news.** A contest nobody wrote
about is evidence about coverage. Dropping it would fit the model only on
divisions the press happened to notice, which is a selected sample rather than
a smaller one.

**Absent coverage is `None`, never zero.** Zero says an article count of
nothing was measured; `None` says nothing was found. A missingness indicator
can separate them, and a model given zeros cannot.

---

## What this does not yet do

No model is fitted. The pipeline builds the five feature matrices and reports
what each could be estimated from; the estimator itself waits on the
architecture decision for Stage 1, since the residual is defined against
whichever model ships.

The window set currently used is the four cumulative snapshots. The
non-overlapping windows are implemented and tested but not yet fed in, because
splitting 17 rows across six windows would leave two or three rows per window.

---

## Related records

- [`residual_model_feasibility.md`](residual_model_feasibility.md) — the join
  to the Stage 1 baseline, and the coverage measurement it corrects
- [`collection_faults_and_corrections.md`](collection_faults_and_corrections.md)
  — the collection-side faults found the same day
- `news_features/specification_coverage/specification_coverage.json` — the
  machine-readable form
