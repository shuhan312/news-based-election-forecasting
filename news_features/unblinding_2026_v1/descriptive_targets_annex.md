# Descriptive annex: the supervisor's prediction targets, item by item

**Post-unblinding descriptive reporting.** Every number here is computed
from the same frozen, hash-verified prediction files and the same
observed outcomes the one-time unblinding read; no model was changed and
no specification selected. The confirmatory endpoint remains overall MAE
(register §16). Seat-call accuracy was computed and recorded in the same
unblinding run and is reported as a **recorded secondary outcome**; the
remaining rows are descriptive accounting against the supervisor's
original target list.

## Vote shares (the confirmatory endpoint's grain)

Baseline per-party MAE on the 2026 principal elections: Green 2.55,
**Reform UK 3.23** (162 candidates), Labour 3.64, Conservative 4.74,
Liberal Democrats 7.54. Overall 4.51.

## Seats and winners — where the story reverses

Row-level seat-call accuracy of 0.7188 hides a directional failure. Seat
totals, predicted against actual:

| party | predicted seats | actual seats |
| --- | ---: | ---: |
| Conservative | **118** | **30** |
| Liberal Democrats | **6** | **96** |
| Reform UK | **0** | **14** |
| Green | 0 | 8 |
| residents' associations (all) | 26 | 10 |

Only **18 of 81** two-member wards had both seats exactly right. The
history-only baseline predicted a Conservative hold; 2026 was a Liberal
Democrat landslide with a Reform breakthrough. Small share errors near
the winning threshold, all in the same direction, flipped seats
wholesale — the realignment is precisely what election history cannot
see.

## Winning margin

Mean absolute error of the deciding margin (second seat versus third
place) under the baseline: **4.31 points** over 81 contests.

## Reform UK specifically

Mean predicted share 9.3% against 10.7% observed; ranks exactly right in
26 of 162 contests; predicted in the top two in **0** wards against
**14** observed. On the supervisor's "serious challenger" question the
baseline's answer was **no** and reality's answer was **yes** — the
share level was nearly right and every seat consequence of it was
missed.

## News and the seats (recorded secondary outcome)

Several v2 confirmatory specifications called seats **better than the
baseline's 0.7188**: combined final-72-hours 0.8558, both arms at
180-91 days 0.8317, both arms at 90-31 days 0.7909. Two observations,
both to be read under the no-promotion rule:

- the seat-accuracy and MAE endpoints **diverge** — the 180-91-day
  window worsened share MAE yet improved seat calls, so "did news help"
  has different answers at the two grains;
- seat accuracy was not the pre-declared primary endpoint. These figures
  were recorded in the one unblinding run and may be reported as
  secondary results, never promoted into the confirmatory verdict.

## Local, national and combined arms

The combined arm applies no weighting: its two features are computed
over the union of both collection streams, each article counted once.
Because the corpus is national-dominated — 1,444 of 1,632 principal
articles and all 627 by-election additions — the combined arm is in
practice the national arm with a small local admixture, and their
confirmatory results track each other throughout (for example +0.24
against +0.27 in the 90-31-day window). **The combination therefore did
not clearly outperform national-only news in 2026, because local volume
is too small to move the mixture** — the direct answer to whether
combining the two streams produces the strongest forecast.

The local arm was scored at unblinding under its pre-declared
sensitivity-only role (its features never cleared the ten-cell
reporting threshold: 5-9 distinct training values in v1, 7-9 in v2
after the local by-election backlog was deliberately left unadjudicated).
Its confirmed-window record, reportable only as sensitivity and without
bootstrap intervals:

| | local arm, news vs recalibrated |
| --- | --- |
| v1 (both variants) | 0 of 12 windows improved; worst -3.93 |
| v2 | 3 of 6 improved: 180-91 days +0.29, 90-31 days +0.19, 14-8 days +0.02 |

The v2 local pattern points the same way as the official arms
(mid-range windows helping), which is consistent but cannot be promoted.

## Targets that remain out of scope, and why

- **Change in vote share**: 2026 used new two-member wards; the brief's
  own rule forbids naive continuity across boundary changes. Computable
  only through the population-weighted crosswalk as report-stage work.
- **Candidate election probability**: the news layer emits shares and
  allocations, not probabilities; the baseline's probability model is
  the only source.
- **Turnout**: never modelled — the leakage rules class it as known
  only after the fact.
- **Effect of Reform standing on other parties**: causal, and stated as
  such by the supervisor ("association, not causation"); synthetic-news
  scenarios are the sanctioned exploratory route.
