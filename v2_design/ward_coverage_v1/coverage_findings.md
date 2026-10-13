# Ward-level news coverage probe: findings

**2026-10-14.** Criteria committed before the run (13c03ea). Produced by
`PYTHONPATH=.:src python -m forecast.ward_coverage match`, with results in
`coverage_results.json` and `coverage_per_division.json`. 2021 training data
only; no LLM; cost zero.

## Pre-registered verdict: viable

10,064 window articles (Surrey 6,498, Kent 3,566) against 152 contested
divisions:

| measure | pooled | Surrey | Kent |
|---|---:|---:|---:|
| **W1** ≥ 1 covering article | **94.7%** | 90.1% | 100% |
| W2 ≥ 1 candidate-name article | 46.7% | 40.7% | 53.5% |
| W3 ≥ 3 covering articles | 84.2% | 70.4% | 100% |
| W4 median articles per covered division | 34 | 6 | 79 |

## Diagnostic, post-result: much of W1 is town-level, not ward-level

Kent's median of 79 articles per division exposed a matching artefact.
Several divisions share a town token ("maidstone", "ashford", "canterbury",
"dover", ...), so one article about Maidstone counts for every Maidstone
division. That measures **town** coverage. Counting only ward-specific
evidence (a candidate's name, or a place token that belongs to one
division only):

| | pre-registered rule | ward-specific only |
|---|---:|---:|
| ≥ 1 article | 94.7% | **64.5%** |
| ≥ 3 articles | 84.2% | **34.9%** |
| median articles per division | 34 | **1–2** |

The verdict is still **viable** on the stricter reading (64.5% ≥ 50%), but
the ward-level signal is thin: most divisions have one or two articles.

A random check of candidate-name matches found most genuine (councillors in
local civic stories), plus two failure types: **namesakes** (a Reform-era
Reigate candidate "Tony Robinson" matched a celebrity vaccine story) and
**county-wide figures** (the Surrey council leader appears in county stories
unrelated to his own division). True ward-specific coverage is therefore
somewhat below 64.5%.

## What this means for a ward-level news hypothesis

1. Ward-level news exists for roughly two thirds of divisions, but usually
   as one or two articles. Features will be sparse counts, often zero.
2. Names are mostly sitting councillors'. Reform's 2025 candidates were
   largely new and unknown, so their name coverage is likely far below the
   46.7% measured here for all candidates. That is the decisive unknown for
   a Reform cold-start test, and the next check must measure it before any
   design is fixed.
3. Name matching needs guards: exclude county-wide figures, and confirm with
   the LLM (relevance + stance) that an article is about that contest.

Next (within the two-day cap set in the criteria): measure name coverage
for first-time and minor-party candidates specifically, as the nearest
available analogue of 2025's Reform slate, then decide whether a pre-
registered ward-level hypothesis is worth its power check.

---

## Follow-up (amendment A1): who local news names — the news strand closes

Rule committed before the run (b57dc4f). Output: `candidate_coverage.json`.
Same 10,064 window articles and the same full-name rule; candidates
classified by Democracy Club person id against 2017.

| 2021 candidate type | candidates | named ≥ 1 | named ≥ 3 |
|---|---:|---:|---:|
| incumbent (won in 2017) | 104 | **36.5%** | 11.5% |
| past candidate (lost in 2017) | 142 | 12.7% | 4.9% |
| new, major party | 285 | 10.5% | 1.4% |
| **new, minor party (N1)** | **143** | **4.2%** | 1.4% |
| Reform or UKIP | 27 | **0%** | 0% |

**N1 = 4.2% < 25%: stop. By the pre-registered rule, the news strand
closes.**

Local news names candidates roughly in proportion to their prominence:
one sitting councillor in three, but 6 of 143 new minor-party candidates
and none of Kent and Surrey's 27 Reform/UKIP candidates. Reform's 2025
slate was mostly of the last kind, so ward-specific Reform coverage would
be absent for most 2025 Reform wards. Reform's 2025 profile was far
larger than in 2021, which could raise this, but reaching the 25% bar
would need a sixfold increase, and only 2025 data could show it.

## The complete news answer

| level | finding | evidence |
|---|---|---|
| council | **wrong resolution:** Reform cold-start error is between wards, not councils (ICC 0%) | `direction1_power` (A2) |
| ward | **too sparse:** about two thirds of divisions get some ward-specific coverage, but it names incumbents; new minor-party candidates 4%, Reform/UKIP 0% | this file |
| measurement | **sound:** the LLM reads stance (κ 0.736) and issue (κ 0.616) to V1's bar | `llm_eval_stance`, `llm_eval_issue` |

The LLM can read local news accurately. In the setting where news had the
best case to add value (a new party's cold start), local news says too
little, at too coarse a level, for anything to be read from it. The
limit is the news, not the model.
