# Approach A feasibility: the join between Stage 1 and the news corpus

**Recorded 29 July 2026.** The supervisor's Prompt 2 names the residual model
as "the principal approach", because it directly measures whether news adds
information beyond the election-history baseline:

```
residual  = actual vote share − Stage 1 out-of-fold prediction
news model: predict that residual from pre-election news features
final      = baseline + predicted news adjustment
```

Every previous discussion of whether the news sample is large enough has run
on estimates. This is the measurement. It was produced by building the join
and counting, not by reasoning about it.

Reproduce with:

```bash
PYTHONPATH=src .venv/bin/python -m news_modelling.run_residual_feasibility
```

---

## The result

**Approach A cannot currently be estimated for Reform UK.** Not "estimated
imprecisely" — the Reform sample in the joinable data is **zero**.

| | |
| --- | ---: |
| Stage 1 out-of-fold rows | 792 |
| elections with an out-of-fold baseline | 19 |
| elections with news | 4 |
| **elections with both** | **2** (2017, 2021) |
| candidate rows with **division-level** news | **20** |
| of those, Reform UK | **0** |
| candidate rows reachable by **election-wide** news | 708 |
| of those, Reform UK | 6 |
| distinct election-wide feature values | **2** |

The twenty division-level rows are all from 2021 and all from five Guildford
divisions: Guildford East, South-East, South-West, West, and Shalford.

## Where the numbers go, and what each one counts

Three different quantities have been called "the news sample" at different
points, and conflating them is how an estimate of ~199 usable rows survived
until the join was actually built.

```
3,105  raw collected records
   |    deduplication, syndication merging, eligibility screening
  207  article-level observations   (one article x one entity)
   |    only articles naming a specific division can attach to a contest
   |      2013 -> 0 divisions    2017 -> 0 divisions
   |      2021 -> 5 divisions    2026 -> 43 divisions
   |    2026 is the untouched holdout; 2013 has no baseline
   |      -> only 2021's five Guildford divisions survive
   20  candidate rows            (one candidate x one contest)
```

**An article-level observation is not a training row.** The model's unit is
the candidate — "this party's candidate in this division polled this share" —
so 207 articles become 20 trainable rows once they are attached to candidates.
The earlier ~199 estimate multiplied the 17-division sample by a candidate
count; it was never measured.

Articles by election, and how many could be located to a division:

| election | article-level observations | divisions located |
| --- | ---: | ---: |
| 2013 | 34 | **0** |
| 2017 | 40 | **0** |
| 2021 | 48 | 5 |
| 2026 | 85 | 43 |

**Not one article from 2013 or 2017 could be pinned to a specific division.**
Everything from those two elections sits at whole-election level — coverage of
"the Surrey County Council election" rather than of a named ward. That is not
a processing failure; ward-level local political reporting is simply rare, and
the two earliest elections predate most of the online archives the collection
draws on.

The 17-division sample was drawn on **2026** ward boundaries and 2026 Reform
vote shares. 2021 used different boundaries and has much thinner archive
coverage, so five of those divisions have locatable 2021 articles and the rest
have none.

## Why the two sides barely overlap

The baseline and the news corpus were built to different coverage plans, and
the mismatch is close to total:

| election | out-of-fold baseline | news | usable |
| --- | :---: | :---: | :---: |
| 2013 | ✗ study start, nothing earlier to train on | ✓ | no |
| 2017 | ✓ 377 rows | election-wide only | no division-level |
| 2021 | ✓ 331 rows | ✓ 5 divisions | **20 rows** |
| 2026 | ✗ primary holdout | ✓ 43 divisions | no |
| 17 by-elections | ✓ ~84 rows | ✗ none collected | no |

Two structural facts do most of the damage.

**The elections with the most news have no baseline.** 2026 has news for 43
divisions and is the untouched holdout; using it to train would spend the
holdout. 2013 has news and is the study start, so no earlier election exists
to produce an out-of-fold prediction for it.

**The elections with the most baseline have no news.** All seventeen
by-elections have out-of-fold predictions and no news collection at all —
and the by-elections are where Reform UK's pre-2026 record actually lives.

## Election-wide news is not a way round this

708 rows can be reached by election-wide news, and 6 of them are Reform UK.
That looks like a usable sample and is not.

An election-wide feature takes **one value per election**. Across the two
shared elections it therefore takes two distinct values, which is exactly the
information content of "is this 2017 or 2021". A model given that feature
cannot separate it from every other thing that differed between 2017 and
2021 — the national political context, the pandemic, boundary changes, the
rise of the Liberal Democrats in Surrey. Any coefficient it produced would be
a between-election difference wearing a news feature's name.

This is not a small-sample problem that more careful fitting would fix. It is
collinearity with the fold structure itself, and the diagnostic refuses to
present it as a news effect for that reason.

## What was built anyway, and why

The pipeline is complete and tested even though it currently has almost
nothing to run on:

- `src/news_modelling/stage1_bundle.py` — loads the frozen Stage 1 bundle
  read-only, verifies every file against its manifest hashes, and refuses a
  bundle that is incomplete, that contains in-sample rather than out-of-fold
  predictions, that gives one candidate two baselines, or that labels any row
  as both Reform UK and UKIP.
- `src/news_modelling/residual_dataset.py` — the join, the coverage diagnosis
  and the residual matrix.
- 31 tests, most of which construct a broken input and assert that it is
  refused.

Building it produced the number in the first place, and the number is the
deliverable. When collection extends, the same command produces the updated
count with no further work.

### Two things the join gets right that are easy to get wrong

**Names are normalised conservatively.** Case, a trailing "Ward"/"Division",
ampersands and whitespace only. No fuzzy matching: a wrongly matched division
attaches an article to the wrong contest, which is worse than not matching it,
and "Guildford East" must never match "Guildford West".

**A candidate with no news is absent, not zero.** A contest with no coverage
is an observation about coverage, and giving it a news count of zero would
tell the model that nothing was written when the truth is that nothing was
looked for.

### A correction to this diagnostic

The first run reported "43 news division names did not match any Stage 1
division", which reads as a broken join. All 43 were 2026 wards — an election
with no out-of-fold baseline, so there was nothing for them to match against.
The count now separates "unmatched within a shared election" (currently zero)
from "in an election with no baseline" (43), and a test asserts the
distinction.

---

## What this means for the project

The blocker is **coverage, not method**. Three options, in the order they
should be considered:

1. **Extend news collection to the by-elections.** Seventeen of them have
   out-of-fold baselines and no news. They are also where Reform UK's
   pre-2026 record is: Reform contested 6 of 81 divisions in 2021 and the
   by-elections of 2025 are the only contests where it has a substantial
   record before the holdout. This is the only option that puts Reform rows
   into the training period.

2. **Extend division coverage within 2021.** The current sample is 5
   divisions of 81. Widening it increases the row count but does not by
   itself add Reform rows, since Reform stood in only 6 divisions in 2021.

3. **Borough elections.** Outside the current scope and a question for the
   supervisor, but they would multiply the Reform observations available.

Until at least one of these happens, the honest position is: **the residual
model is implemented, tested, and has nothing to say about Reform UK, because
no Reform UK candidate in the training period has news attached to them.**

### A correction to how this was described beforehand

An earlier plan said "run Approach A on the existing 207 rows". That conflated
article-level observations with training rows and made the position sound
better than it is: the 207 were never candidate rows, and the trainable count
was 20 all along. The measurement is what established that, which is the
argument for running the join rather than continuing to reason about it.

Reporting that is more useful than reporting a coefficient fitted on twenty
rows of five Guildford divisions.

---

## Related records

- `news_features/residual_feasibility/coverage_diagnosis.json` — the machine
  readable form, regenerated by the command above
- [`../surrey-election-no-news-baseline/docs/technical_report.md`](../surrey-election-no-news-baseline/docs/technical_report.md)
  — §9(b), which raised this as a question and now has the number
- [`news_research_protocol.md`](news_research_protocol.md) — the collection
  plan that produced the current coverage
- [`division_sample.md`](division_sample.md) — how the 17 divisions were chosen
