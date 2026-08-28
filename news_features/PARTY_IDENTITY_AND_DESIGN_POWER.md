# Party identity, design power, and what the news layer is made of

**EXPLORATORY, post-unblinding, 2026-08-05.** Every number below was
computed in this session from committed artefacts. Where a claim of mine
turned out to be wrong it is recorded as wrong rather than quietly
replaced. Where a number could not be reproduced it is left out and said
to be left out.

Modules and artefacts produced here:

- `news_modelling.identity_placebos` -> `news_features/identity_placebos_v1/`
- the ward-resolution diagnostic discussed in Section 7 was a development
  route later removed from final `main`; its code and output remain in Git
  history and are not a source for the final report

Both run the frozen reproduction gate first: the committed specification
must reproduce its published deltas at the three decimal places the
reference records, or the run aborts.

---

## 1. The question this file answers

The confirmatory record says the news layer improved on the recalibrated
control by **+0.2404 MAE points [+0.078, +0.387]** on the 2026 holdout.
The supervisor's challenge asked what that improvement is made of, and
proposed two candidate explanations: coverage volume, and prior-election
share.

Volume is half right. Prior share is not. The mechanism is neither: it is
**party identity**, and the reason is an encoding gap in Stage 1.

---

## 2. Six party indicators beat the news layer

`identity_placebos_v1/identity_placebo_results.json`. Every arm shares the
45 frozen fitting cells and the frozen prediction and scoring code; only
`feature_columns` differs. Headline window 90-31 days, 2026 holdout, delta
against the recalibrated control (positive is better).

| arm | delta | 95% CI |
|---|---:|---|
| frozen (`party_article_share` + `net_portrayal_share`) | +0.2404 | [+0.0781, +0.3866] |
| **six party indicators, no news at all** | **+0.8342** | [+0.5208, +1.1597] |
| Reform indicator alone | −0.0302 | [−0.2216, +0.1731] |
| prior-election vote share alone | −0.0152 | [−0.0788, +0.0485] |
| party indicators + frozen pair | +0.8504 | [+0.4572, +1.2504] |
| party indicators + incumbent-judgement frame | +0.8734 | [+0.5838, +1.1643] |

Marginal contributions over the party-indicator control:

| added on top of six party indicators | marginal |
|---|---:|
| `party_frame_incumbent_judgement_share` (LLM content) | **+0.0392** |
| the frozen pair (volume + tone) | +0.0162 |
| `party_issue_immigration_share` | +0.0127 |
| volume alone | **−0.0731** |
| within-party-centred tone alone | **−0.1224** |
| tone trajectory (slope across windows) | **−0.0139** |

The design's own resolution (MDE80, 2026 v2 overall) is **0.216**. Every
marginal above is under it.

**Two of the supervisor's candidates are refuted directly.** A Reform-only
indicator scores −0.0302 and a prior-share feature −0.0152; neither
reproduces the certified result. Volume does: at 90-31 days a raw article
count alone reaches +0.2247, 93 per cent of +0.2404.

---

## 3. Why the indicators win: an encoding gap in Stage 1

`surrey-election-no-news-baseline/outputs/model_bundle_v1/feature_dictionary.csv`
and `feature_schema.json`. Stage 1 carries `is_reform_uk` and `is_ukip` as
individual indicators, as the brief required. Every other party is carried
only through `party_category`, whose levels are `established`, `emerging`,
`local`, `independent` and `unseen_level`. Conservative, Labour, Liberal
Democrat and Green all take `established`, so the baseline **cannot give
them different intercepts**.

Their systematic offsets therefore survive into the residual. Share of the
recalibrated control's 2026 error that is a fixed per-party offset
(|mean error| divided by mean |error|):

| party | Stage 1 encoding | fixed-offset share |
|---|---|---:|
| labour | collapsed into `established` | **96%** |
| liberal_democrat | collapsed into `established` | 78% |
| conservative | collapsed into `established` | 60% |
| **reform_uk** | **own indicator** | **41%** |
| green | collapsed into `established` | 10% |

The residual model's only party-varying inputs were the news features, so
they were asked to supply the offset Stage 1 could not encode, and were
credited for it.

### 3.1 The benchmark does not hold on the study party

Delta against the recalibrated control, Reform rows only (162 rows), all
six windows:

| arm | six-window mean | windows better than the control |
|---|---:|---:|
| six party indicators | **−0.2929** | 0 / 6 |
| frozen news pair | −1.2690 | 1 / 6 |
| frozen pair + incumbent-judgement | −0.9590 | 1 / 6 |

**On Reform the party-indicator control is harmful in every window.** Its
whole advantage lies in the four parties Stage 1 collapses. It is a repair
for a documented encoding gap, not a general competitor to the news layer,
and the gap does not exist for the study party.

For completeness, on all supported parties (753 rows) the news arms beat
the indicators in **0 of 6** windows.

---

## 4. Design power: what could have been detected

The 45 fitting cells are means over very different numbers of contests.
**34 of the 45 are single-contest by-election cells.**

Variance decomposition of the fitting target:

| quantity | value |
|---|---:|
| pooled within-cell variance, sigma^2 | 96.238 |
| variance of the cell means | 95.256 |
| mean sampling variance, mean(sigma^2 / n) | 73.798 |
| between-cell signal, tau^2 | 21.458 |
| **reliability, tau^2 / Var** | **0.2253** |
| pooled within-cell standard deviation | 9.81 share points |

Reliability is **not** uniform across subsets, and conflating them is an
error I made and corrected mid-session:

| subset | cells | mean contests per cell | reliability |
|---|---:|---:|---:|
| all fitting cells | 45 | 14.7 | **0.225** |
| cells carrying news coverage at 90-31 days | 18 | 32.2 | **0.594** |
| 2017 and 2021 only (no by-elections) | 11 | 56.9 | **0.938** |

### 4.1 The detection threshold

A correlation measured through a target of reliability rho is attenuated by
sqrt(rho). Using exact two-sided t critical values at alpha = 0.05:

| subset | attenuation | critical r | **true r required** |
|---|---:|---:|---:|
| covered cells (n = 18, df = 16) | 0.7708 | 0.4683 | **0.608** |
| all cells (n = 45, df = 43) | 0.4746 | 0.2940 | **0.619** |

The two subsets agree: **this design needs a true correlation of about
0.61 to detect anything.** That is a very large effect by social-science
standards, but it is not impossible, and the null therefore cannot be read
as evidence against news.

**A correction on record.** An earlier version of this calculation applied
the 45-cell reliability (0.225) to the 18-cell sample, producing a required
true correlation of 1.089 and the conclusion that the design "could not
have detected a perfect relationship". That was wrong: it mixed two
subsets. The corrected figure is 0.61 and the design is underpowered, not
incapable. The error was communicated to the supervisor and corrected
within the hour.

### 4.2 The by-election enrichment reduced measurement quality

Restricted to 2017 and 2021 the fitting target's reliability is **0.938**.
Adding the eight by-election cells took it to **0.225** while appearing to
quadruple the sample from 11 cells to 45. Each of those cells is a single
contest carrying a within-cell standard deviation of 9.81 share points.

### 4.3 What would raise the threshold

Holding tau^2 fixed and adding covered cells:

| covered cells | mean contests | reliability | true r required |
|---:|---:|---:|---:|
| 18 (current) | 32.2 | 0.594 | **0.608** |
| 24 (one more covered by-election) | 24.4 | 0.533 | 0.554 |
| 30 | 19.7 | 0.503 | 0.509 |
| 42 (four more) | 14.4 | 0.472 | **0.443** |

Adding single-contest cells helps despite lowering reliability, because
the critical value falls faster than the attenuation does. This corrects an
earlier claim of mine that by-election cells are useless: they are useless
for reliability and useful for the threshold.

The E5-local queue holds 1,576 unjudged rows, of which the four
zero-coverage training by-elections account for 39 (Caterham Valley 3,
Hinchley Wood 6, Weybridge 14, Guildford South East 16).

---

## 5. Stance beats counting, on both islands

The one comparison that separates the language model from mere counting.
`party_article_count` needs no model: it is how many articles mention a
party. `net_portrayal` is favourable minus unfavourable articles, which
requires the model to judge each article's stance toward each party. Both
are counts over the same article set, on the same scale, scored by the same
harness against the same control.

| island | periods where stance beats the count |
|---|---|
| 2026 holdout | **11 of 12** |
| 2021 validation | **10 of 12**, and the two exceptions are the empty windows where both arms score exactly 0.0000 - so 10 of 10 among live periods |

At `previous_14_days` on 2026 the count gives +0.0058 and stance alone
+0.3394 [+0.2519, +0.4226]. On 2021 the margins are larger and in the same
direction: at `previous_7_days`, −0.698 for stance against −12.705 for the
count.

The two islands use different harnesses and different fits - 2021 is fitted
on 2017 alone with zero Reform rows, 2026 on 45 pooled cells - so this is a
replication rather than one result read twice.

**Note the feature.** This holds for `net_portrayal`, the raw count
difference. Using `net_portrayal_share`, the proportion, stance wins 9 of
12 on 2026. The count-scale comparison is the like-for-like one, because
`party_article_count` is also a count.

---

## 6. Content against the party-unreachable residual

Decomposing the 45-cell target: **32.1 per cent of its variance is between
parties and 67.9 per cent is within a party across elections.** A party
indicator can only reach the first.

Correlations against the party-demeaned residual, 18 covered cells at 90-31
days (noise scale 1/sqrt(15) = 0.258; exact critical r = 0.468):

| feature | needs the LLM? | r | variance explained |
|---|---|---:|---:|
| `party_frame_incumbent_judgement_share` | yes | **+0.509** | 25.9% |
| `party_frame_local_impact_share` | yes | +0.218 | 4.7% |
| `net_portrayal_share` (tone) | partly | +0.127 | 1.6% |
| `tone_trajectory` (slope across windows) | partly | −0.041 | 0.2% |
| `party_article_count` (volume) | **no** | +0.016 | **0.0%** |
| `party_article_share` | **no** | −0.011 | **0.0%** |

Permutation test, 4,000 draws: single-feature **p = 0.0145**; family-wise
over the fifteen features tested **p = 0.1817**.

### 6.1 Three reasons not to promote this

1. **Fifteen features were tried.** The family-wise p is 0.18. Reporting
   the best of fifteen as though it were the only one tried is the failure
   mode this project exists to avoid.
2. **It does not survive restricting to well-measured cells.** Correlation
   by denominator threshold: all 18 cells r = +0.509; denominator >= 4
   (n = 16) r = +0.483; >= 5 (n = 12) r = +0.481; **>= 8 (n = 8) r =
   −0.021**. A real signal should strengthen on better-measured cells, not
   vanish. Weighting by the feature's own denominator also drops it, from
   +0.509 to +0.313.
3. **It does not convert into out-of-sample prediction.** On
   leave-one-election-out, averaged over all six windows, its marginal over
   a party-indicator control is −0.024.

The share's denominator is `party_framing_coded`, not
`party_article_count`: the two counters come from different LLM layers over
different article populations, so a cell can carry framing coverage without
stance coverage. Using the correct filter moves the correlation from +0.539
to +0.509. Denominators run from 2 to 48 articles, so several cells admit
only the values 0, 0.5 and 1.

### 6.2 A family-level contrast that does survive

Leave-one-election-out, averaged over all six windows, twelve features
split into families **before** scoring, all twelve reported, each added
singly to an identical six-indicator control:

| family | mean marginal | positive |
|---|---:|---:|
| LLM content (7 issue and framing shares) | **−0.047** | 0 / 7 |
| content-free (5 volume, tone, locality) | **−0.137** | 0 / 5 |
| **separation** | **+0.090** | |
| exact 792-split permutation | **p = 0.024** | |

Both families degrade accuracy on top of party identity; the content family
degrades it significantly less. This is a statement about **relative harm**,
not about news improving prediction. It survives dropping any single content
feature (p between 0.009 and 0.041) but falls to **p = 0.058** when
`party_article_count` is dropped from the other family, so the article count
carries a large part of the contrast.

---

## 7. Historical ward-grain diagnostic

This section records a retired development diagnostic. Its
`ward_resolution_v1/` output and ward-level pilot table were removed from final
`main` after the production feature design replaced that route; they remain in
Git history. The final report's area-grain limitation is instead reproduced by
`src/news_features/diagnose_article_area_attribution.py` and
`news_features/article_area_attribution_summary.json`.

A party indicator is constant for a party across every contest it stands in,
so the only variation it can never reproduce is variation between wards inside
one election. The retired ward-grain table was used here to test that
distinction before the production design was fixed.

Ward resolution rate - the share of covered (election, party) groups whose
feature takes more than one value across that election's wards:

| arm | covered group-column pairs | varying across wards | rate |
|---|---:|---:|---:|
| local | 107 | 0 | **0.0%** |
| national | 3,531 | 0 | **0.0%** |
| combined | 3,524 | 49 | 1.4% |
| coverage bookkeeping | 1,546 | 121 | 7.8% |

The coverage ledger explains why. Of 18,138 ward-tier cells:

| coverage status | cells | keyed to a named ward | keyed election-wide |
|---|---:|---:|---:|
| `not_applicable` (outside the pre-registered 17-division sample) | 16,116 | 16,092 | 24 |
| `source_unavailable` (ward-tier search failed at source) | 1,248 | **1,248** | 0 |
| `pending_external_stage` (could still receive articles) | 756 | **0** | 756 |
| `observed_news` | 18 | **0** | 18 |

**Every cell keyed to a named ward is either out of scope or a failed
search. None carries news and none is pending.** Every cell that carries
news or could still receive it is keyed `ELECTION_WIDE`, and the maximum
wards per unlockable (election, party) group is **1**. Variation across
wards inside a group is arithmetically impossible when the group carries
one ward, however many articles arrive.

The `coverage_status` column does vary by ward in 21 of 29 groups, which
proves the ward join works. The axis is empty for want of data, not for
want of machinery.

---

## 8. Routes tested and closed

Sixteen routes were investigated across two multi-agent runs, each running
its own experiments, with every non-dead result adversarially re-run. All
sixteen died, and all died on the same constraint: 18 to 19 informative
cells against a design needing a true correlation of 0.61.

Change the prediction target; per-party news slopes; the 4,218 unused
parquet feature columns; seat-call and rank accuracy; unmined earlier
artefacts; contest-grain refit on the 2021 island; candidate and place
attribution; single-contest case studies; leave-one-election-out; the 2021
island as a second surface; partial pooling and shrinkage; nonlinear and
threshold specifications; precision weighting; restricting the fit to
well-measured cells; per-party offset prediction; tone trajectory.

Three of these produced apparent wins that did not survive:

- **Precision weighting** inverted the party-indicator advantage
  (+0.8342 to −0.7097) and made the content marginal +1.1656. Refuted:
  `w = n` is the efficient weight only if tau^2 = 0, and tau^2 = 21.458.
  Under the correct random-effects weight the inversion vanishes. The
  weighting scheme was also selected on the 2026 holdout.
- **Restricting the fit to multi-contest cells** made the party indicators
  score −2.2788 and the marginal +2.4276. Refuted: 11 cells from 2
  elections, 3 residual degrees of freedom, and the content arm's absolute
  score falls from +0.8734 to +0.1488 - the marginal grows only because the
  control collapses faster.
- **Per-party offset prediction** had news+content beat the indicators at
  90-31 days (mean absolute error 1.633 against 1.857). Refuted: 1 of 6
  windows; the six-window mean is 2.936 against 1.857.

---

## 9. What can and cannot be claimed

**Can be claimed.**

- News improved on the recalibrated control by +0.2404 [+0.078, +0.387] on
  a protected 2026 holdout. Nothing in this file overturns it.
- Stance beats article count in 11 of 12 periods on 2026 and 10 of 10 live
  periods on 2021, across different harnesses and fits.
- The extraction layers in use passed validation at kappa 0.616 to 0.848;
  those that failed were excluded.
- The design requires a true correlation of about 0.61 to detect anything,
  so the null is a statement about resolution, not about news.
- Stage 1 collapses four parties into one category, and 60 to 96 per cent
  of the control's error for those parties is a fixed offset it cannot
  encode - against 41 per cent for Reform.

**Cannot be claimed.**

- That news or the LLM beats a six-party-indicator control. It does not, on
  any evaluation tested: 0 of 6 windows on all parties, 3 of 6 on Reform
  alone with a worse mean.
- That news content has no effect. The design cannot support that.
- That `party_frame_incumbent_judgement_share` is an effect. Family-wise
  p = 0.18, it vanishes on well-measured cells, and it does not predict
  out of sample.
- That the 2021 Reform gain is a news effect. Up to 195 of 279 rows are
  clipped to zero there, the fit has zero Reform rows, and all 14 live
  specifications worsen election-wide MAE.

---

## 10. Corrections made in this session

| claim | status |
|---|---|
| "the design could not have detected a perfect relationship" (true r 1.089) | **wrong** - mixed the 45-cell reliability with the 18-cell sample; correct figure is 0.61 |
| "tone is a Reform dummy" | **wrong** - a Reform-only indicator scores −0.0302; the mechanism is the full party structure, led by Lib Dem and UKIP |
| "the corpus is 90.958 per cent national, correct the 91.678 in the register" | **wrong** - 91.678 is the article-level figure over the six windows and is consistent with the project's 188 local articles; no change needed |
| "by-election cells are useless" | **wrong** - they lower reliability but lower the critical value faster; the 39 queued rows were projected to move the threshold from 0.608 to 0.443 |
| "judging the 39 queued rows would move the threshold to 0.443" | **wrong** - the rows were judged and the threshold moved to 0.573. The projection held tau^2 fixed and assumed the added cells would arrive at the reliability of existing ones; they arrived far worse. See section 11 |
| "the ward axis could be opened by judging E5" | **wrong** - every unlockable ward-tier cell is keyed election-wide; the axis cannot be opened from this corpus |

---

## 11. The human E5 pass, and what it settled

The 39 queued E5 rows were judged by hand on 2026-08-05, blind to any prior
labelling, against `news_protocol/eligibility_manual_review_codebook.md`.
Only the E5 gate was touched; E4, E6 and E8 kept the verdicts the pipeline
already held. Verdicts are in
`news_collection/byelection_eligibility_decisions_e5human_v1.csv`
(`e5_source = human`), and the table they produce is
`news_features/news_feature_table_v4e5local.csv`. **Exploratory: built after
the 2026 holdout was unsealed, so nothing here is confirmatory.**

### 11.1 The coverage arrived

All four zero-coverage by-elections gained local articles, and no existing
cell was lost. Cells carrying party-level news, any window: **34 -> 49.**

| election | new covered cells |
|---|---:|
| Guildford South East 2025-10-16 | 5 |
| Hinchley Wood, Claygate & Oxshott 2025-08-21 | 5 |
| Weybridge 2015-05-07 | 4 |
| Caterham Valley 2025-10-16 | 1 |

At the 90-31 day window used by every test in sections 4 and 6, covered
fitting cells go **19 -> 28**.

### 11.2 The detection threshold barely moved, and section 4.3 was wrong

| | covered cells | mean contests | reliability | true r required |
|---|---:|---:|---:|---:|
| v3party | 19 | 33.4 | 0.623 | **0.577** |
| v4e5local | 28 | 23.0 | 0.426 | **0.573** |
| section 4.3 projected for 4 more elections | 42 | 14.4 | 0.472 | 0.443 |

The projection was an extrapolation that held tau^2 fixed and assumed each
added cell would carry the reliability of the cells already there. The real
cells did not: reliability fell from 0.623 to 0.426, roughly cancelling the
gain from the larger n. **The design is no better powered than before.**
An honest reading of section 4.3 is that its right-hand column was never a
forecast of what judging would deliver.

### 11.3 The section-6 signal did not survive the new cells

Correlation with the party-demeaned residual at 90-31 days:

| | v3party (n=19) | v4e5local (n=28) |
|---|---:|---:|
| `party_frame_incumbent_judgement_share` | +0.520 | **+0.370** |
| exact critical r | 0.456 | 0.374 |
| within-party permutation r | +0.5617 | +0.3961 |
| single-feature p, 20,000 draws | 0.1268 | 0.0664 |
| family-wise p, the scan as run (k=25) | 0.4333 | **0.6675** |
| `party_article_count` (no LLM needed) | +0.066 | −0.010 |

It now sits below its own critical value. The single-feature p improved
only because n rose; the family-wise p, which is the one that governs a
signal found by scanning, got worse.

The denominator check that killed it at 19 cells is unchanged:

| subset | v3party | v4e5local |
|---|---:|---:|
| all covered | +0.520 | +0.370 |
| `party_framing_coded` >= 4 | +0.491 | +0.443 |
| `party_framing_coded` >= 8 | +0.005 | **−0.078** |

### 11.4 The one thing that did replicate, and why it does not rescue the signal

The nine new cells are a genuine out-of-sample test: they were gated by a
procedure blind to the residual and did not exist when the signal was found.
On those nine alone the correlation is **+0.498 (p = 0.17)** - the same sign
and nearly the same size as the original +0.520.

That is the strongest form of this signal available and it is still not
enough, for a reason visible in the cells themselves: **every one of the
nine has a framing denominator of 1 or 2.** Their share can only take the
values 0, 0.5 and 1. The signal continues to live entirely in cells measured
from one or two articles and to disappear wherever the measurement is good.
Nine more cells of the same kind cannot distinguish "a real effect the
design cannot resolve" from "an artefact of shares computed over n = 1".

**Net position after judging.** The coverage gap was real and is now closed;
closing it did not change any conclusion in sections 1 to 9. News still does
not beat the six-party-indicator control, the LLM content layer still adds
nothing over it, and `party_frame_incumbent_judgement_share` is now weaker
on every measure that matters than when it was first flagged.
