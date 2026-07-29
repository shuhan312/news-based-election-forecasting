# Seat and date validation, and which fields are official

**Recorded 29 July 2026.** Three items on the brief's data-validation list had
no implementation: "validate the number of seats", "validate election dates",
and "identify fields whose values are official, supplementary or derived".
This records what was built, what it found, and the one result worth arguing
about.

---

## Why these two checks and not others

The data-quality report already covered identifiers, share ranges and contest
reconciliation. Seats and dates were missing, and they are the two fields in
the contract that decide something structural rather than describing it.

**A seat count decides the prediction.** Predicted elected status is "top *N*
by predicted share", where *N* is the seat count. A wrong *N* does not degrade
a prediction — it produces a different prediction that looks equally valid. A
contest whose rows disagreed about *N* would allocate a different number of
seats depending on which row happened to be read first.

**A date decides the split.** Every fold boundary is a date comparison, so a
row dated wrongly does not merely carry a wrong feature: it moves between
training and test. A 2026 row dated 2021 would train on the holdout, which is
the single failure the whole split design exists to prevent.

### What is checked

Seats — four properties:

1. at least one seat;
2. one seat count per contest, rows agreeing;
3. no more seats than candidates, since top-*N* would otherwise return the
   whole ballot, and the declared `candidate_count_in_contest` matching the
   rows actually present;
4. `contest_structure` agreeing with the count, since the label is derived
   from it and a disagreement means one of the two is stale.

Dates — four more:

1. the date parses, since an unparseable date cannot be compared to a fold
   boundary and the row would land wherever the comparison happened to fall;
2. it lies inside the study period;
3. one date per `election_id`, and no contest spanning two dates;
4. `election_year` matching the date's year, since a mismatch means one was
   edited without the other.

Findings are returned as data rather than raised, because the data-quality
report is meant to describe the contract *including* its problems. A single
unparseable date should not stop the report describing the other 1,991 rows.

### What they found

Both pass on the current release.

| | |
| --- | --- |
| contests checked | 343 — 262 single-member, 81 two-member |
| elections checked | 24, over 19 distinct polling days |
| period | 2013-05-02 to 2026-07-07 |
| seat problems | none |
| date problems | none |

A validator that has only ever seen data that passes has not been tested, so
the failures are exercised directly: 23 tests construct each break — a contest
whose rows disagree about seats, three seats for two candidates, an election
with two polling days, a year that contradicts its date — and assert it is
reported.

---

## Which fields are official, supplementary or derived

The leakage audit answers *when* a column became available and *whether* it
may be modelled. It does not answer *what kind of evidence it is*, and
conflating the two would let a governed derived quantity be read as an
official one because it happened to be permitted.

Four layers, with every one of the 64 published columns classified and a
reason stored beside it. An unclassified column stops the build; "derived"
without a rule is an assertion.

| layer | meaning |
| --- | --- |
| `official` | appears on, or is counted from, an official source for the relevant election |
| `official_or_supplementary_per_row` | carries its own provenance column, because different rows rest on different evidence |
| `governed_derived` | computed by this project under a documented rule |
| `not_an_evidence_value` | identifiers, linkage keys, provenance strings, cohort labels |

The third layer exists because two fields — `analysis_number_of_seats` and
`analysis_previous_turnout` — genuinely differ row by row. Declaring one layer
for the whole field would be a claim about rows it is not true of, so the
distribution is published instead:

| field | official result page | supplementary | unavailable |
| --- | ---: | ---: | ---: |
| `analysis_number_of_seats` | 1,883 | 109 | — |
| `analysis_previous_turnout` | 662 | 398 | 932 |

### The result

**The shipped model runs on 35 predictors: 10 official, 2 per-row, and 23
governed derived.**

| | official | per-row | derived |
| --- | ---: | ---: | ---: |
| predictors in the shipped run | 10 | 2 | **23** |
| predictor columns classified | 10 | 2 | 27 |

The two rows differ by the four UKIP interaction columns, which are classified
but absent unless the sensitivity option is on. The report now computes the
present count from the rows rather than quoting the classified total, because
the two are not the same number and the difference is not noise.

**Roughly two thirds of the model's inputs are quantities this project
computed rather than values anyone published.** That is not a defect. A
party's county-wide strength, its contest rate, the years since its last
comparable contest — none can be read off a results page, and the brief asks
for them. But it does mean the model's quality depends more on the rules
documented in this repository than on the accuracy of published numbers, and
that is worth a reader knowing before they weigh a result.

### The classification worth arguing about

`standard_party_name` is classified **derived**, not official.

The name printed on an official result page is the *original* name, retained
as `original_party_name`. The standardised label is this project's own mapping
of that string onto a governed party list — and it is the mapping that keeps
Reform UK and UKIP separate, which is the requirement the brief is most
insistent about.

Calling it official would present a project decision as a source fact, and it
is precisely the decision most in need of being visible. `party_category`,
`is_reform_uk` and `is_ukip` are derived for the same reason.

---

## Related records

- [`candidate_split_and_leakage.md`](candidate_split_and_leakage.md) — the
  audit that answers the other question about every column
- [`technical_report.md`](technical_report.md) — §2, where this result is
  summarised for the review
- `data_quality_report.json` in the bundle — the machine-readable form
