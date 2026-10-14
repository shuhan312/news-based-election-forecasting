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

> **Superseded in part (2026-10-14).** The council row below rests on the
> power gate's tau² = 0, which came from Reform's small 2023 share. Power
> gate amendment A3 (`direction1_power/criteria.md`) re-estimated it at a
> large-party level and reopened H2 at council level (design A4). The ward
> row stands.

| level | finding | evidence |
|---|---|---|
| council | **wrong resolution:** Reform cold-start error is between wards, not councils (ICC 0%) | `direction1_power` (A2) |
| ward | **too sparse:** about two thirds of divisions get some ward-specific coverage, but it names incumbents. Kent's actual 2025 Reform candidates: 9.9% named by full name in the April 2025 campaign (18.5% on the looser rule), 1.2% named three or more times | this file, A1–A5 |
| measurement | **sound:** the LLM reads stance (κ 0.736) and issue (κ 0.616) to V1's bar | `llm_eval_stance`, `llm_eval_issue` |

The LLM can read local news accurately. In the setting where news had the
best case to add value (a new party's cold start), local news says too
little, at too coarse a level, for anything to be read from it. The
limit is the news, not the model.

---

## Follow-up (amendments A2–A5): the decisive measurement on 2025's actual Reform slate

Rules committed before each figure was computed (28c45ce, 694db78,
8029648). Outputs: `candidate_coverage_late.json` (2021, A2/A4) and
`reform_2025_coverage.json` (2025, A3–A5). 2025 results were never read:
the candidate list is stripped to ballot, person id, name and party at
read time (test-enforced).

### Three numbers

| measurement | with list articles | lists excluded (A4) |
|---|---:|---:|
| 2021 N1, main window (5 Feb – 5 Apr; before nominations) | 4.2% | — |
| 2021 N1, late window (6 Apr – 5 May; after nominations, A2) | 41.3% | **12.6%** |
| **2025 Kent Reform R1** (1–30 Apr 2025, A3) | 19.8% | 18.5% (any rule) / **9.9%** (full name only) |

2025 details: 1,270 KentLive and KentOnline articles published in the
window (earliest 1 April, latest 30 April; BBC Kent's 2025 URLs are not
in the Wayback lists), 2 list articles, 81 Reform candidates, 75 of them
new since 2021. 8 named by full name, 7 more only by surname near
"Reform". New Reform candidates: 16% named. **Named three or more times:
1.2% (1 of 81).**

### A5 match check: 7 of 20 false, so the full-name figure decides

20 matches drawn at random (seed 20261014) from those counting towards
R1, each read for whether the article names this candidate. Article text
stays in the gitignored data folder; only verdicts are recorded here.

| # | candidate | rule | verdict | reason |
|---:|---|---|---|---|
| 1 | Richard Palmer | full | true | Reform councillor quoted in a Swale story |
| 2 | Daniel Colin Taylor | surname | true | "Daniel Taylor is the Reform UK candidate" |
| 3 | Dirk Ross | full | true | listed at a hustings (5 candidates) |
| 4 | Chris Palmer | surname | **false** | the article's Palmer is Richard Palmer |
| 5 | Chris Palmer | surname | **false** | the same: Richard Palmer |
| 6 | Matthew Fraser Moat | surname | true | in a "SURNAME, First" list, which the list filter misses |
| 7 | Babychan Thomas | surname | **false** | "Thomas" is Thomas Mallon's first name |
| 8 | Thomas Mallon | full | true | Reform councillor, Dartford |
| 9 | David Wimble | full | true | Reform leaflet story |
| 10 | Paul Thomas | full | **false (doubtful)** | "Cllr Paul Thomas (Ind)" at a licensing meeting; likely a namesake |
| 11 | David Wimble | full | true | Reform leaflet story |
| 12 | Dirk Ross | full | true | Ashford's Reform councillor |
| 13 | Trevor Shonk | full | true | Thanet's Reform councillor |
| 14 | John Baker | full | true | candidate whose shop was vandalised |
| 15 | Paul Thomas | surname | **false** | "Thomas" is Thomas Mallon again |
| 16 | Stephen Charles Dean | surname | **false** | "Dean" is Dean Burns's first name |
| 17 | Dirk Ross | full | true | spoke at an event for Reform |
| 18 | Richard Palmer | full | true | Reform councillor, Sheppey car parks |
| 19 | John Graham Finch | surname | **false** | a different Finch (David), Medway by-election |
| 20 | Dean Edward Burns | surname | true | candidate whose campaign material was vandalised |

6 of 10 surname matches are false: the surname rule mostly hits another
person's first name or a namesake. 7 > 4 (6 > 4 even if #10 is counted
true), so by A5 **R1 = 9.9% (full name only)**.

### Pre-registered decision: stop, and the news strand closes

R1 = 9.9% < 25%. It would be "stop" on every reading: 18.5% on the looser
rule, 19.8% even with lists counted. By A2/A3 no further news angle is
opened.

The three numbers agree. Once lists are removed, local news names about
one new minor-party candidate in eight (2021) and about one Reform
candidate in ten (2025), even in the campaign month of Reform's breakthrough
year. Those it does name are mostly sitting councillors who had defected
(Ross, Shonk, Mallon, Palmer) or candidates in an incident story (leaflet,
vandalism). Only 1 of 81 is named three or more times, so a ward-level
feature would be zero for nearly every Reform ward.

### Limitations

- **Kent only.** Kent has one of the larger local news markets, so R1 is
  if anything optimistic for other 2025 councils.
- **Lower bound in two directions:** Wayback misses unarchived articles,
  and BBC Kent's 2025 articles are absent. Missing articles would need to
  raise R1 from 9.9% to 25%, an increase of about two and a half times,
  to change the decision.
- **Exact-name matching** misses nicknames and initials. The check shows
  that loosening the rule adds mainly false matches, not hidden coverage.
- A "SURNAME, First" candidate list escapes the list filter (#6). That
  only inflates R1.
