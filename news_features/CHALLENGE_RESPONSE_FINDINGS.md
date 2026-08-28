# Findings from the supervisor challenge, 2026-08-05

Every figure below was re-derived from a committed artefact during this
review. Where an earlier claim of mine turned out to be wrong it is recorded
as wrong rather than quietly replaced.

Sources used, all committed:

- `production_news_experiment_v1/experiment_results.json` and
  `validation_predictions.csv` (2021 validation)
- `per_party_bootstrap_v1/per_party_bootstrap_results.json`
- `local_v3_rerun_v1/rerun_results.json` (2026 holdout)
- `minimal_detectable_effect_v1/mde_results.json`
- `synthetic_scenarios_v1/scenario_results.json`
- `news_feature_table_v2.csv` and its metadata

---

## 1. The four challenges

### 1.1 Headroom — the challenge holds, and more sharply than it was put

Reform's signed level error under the recalibrated control, before any news
feature enters, combined arm, 90-31 days:

| island | Reform signed bias, control | after news | change in \|bias\| |
|---|---:|---:|---:|
| 2021 validation | **+12.2087** | +3.0670 | −9.1417 |
| 2026 holdout v2 | **−1.3288** | −3.1645 | +1.8357 |

The two starting points are 9.2x apart in magnitude and lie on **opposite
sides of zero**. News moves Reform in the **same direction on both islands,
downward**. On 2021 that direction is corrective; on 2026 the identical push
is an overshoot.

A layer whose only behaviour is "predict Reform lower" therefore earns about
nine points on 2021 and loses 1.8 on 2026 without carrying any information
about news. The observed result cannot be distinguished from that.

Full control-vs-news table for the same specification:

| party | control bias | news bias | change in \|bias\| |
|---|---:|---:|---:|
| 2021 conservative | +5.2917 | +9.2168 | +3.9251 |
| 2021 green | −7.8808 | −12.5861 | +4.7053 |
| 2021 labour | −4.1426 | +5.1971 | +1.0545 |
| 2021 liberal_democrat | −1.4008 | −7.6448 | +6.2440 |
| 2021 reform_uk | +12.2087 | +3.0670 | −9.1417 |
| 2021 ukip | +6.0088 | +1.2961 | −4.7127 |
| 2026 conservative | +2.8424 | +1.1462 | −1.6962 |
| 2026 green | +0.2468 | +1.2976 | +1.0508 |
| 2026 labour | +3.7393 | +3.1905 | −0.5488 |
| 2026 liberal_democrat | −5.8508 | −3.0987 | −2.7521 |
| 2026 reform_uk | −1.3288 | −3.1645 | +1.8357 |

### 1.2 The 2021 Reform result is a clipping floor

`negative_raw_shares_clipped` counts predictions forced up to zero. Across
the 18 confirmatory-window specifications on 2021 the news arm clips between
0 and **195 of 279** rows. Across all six 2026 windows it clips **zero** rows.

In four 2021 specifications Reform's MAE is exactly **2.8333**. Reading
`validation_predictions.csv` for combined / 30-15 days shows why: all six
Reform predictions are exactly `0.0`, against observed shares of 3, 1, 4, 2,
5 and 2 per cent, whose mean is 2.8333. The recalibrated control had
predicted 11.6 to 19.1 per cent for those same contests.

So in those specifications the "win" is the model being clamped to zero
against a party that really did poll near zero. **The mechanism cannot
operate on the 2026 holdout at all**, because nothing is clipped there.

### 1.3 The 2021 Reform gain is a transfer, not a gain

The recalibrated control's overall MAE is **7.5872** in all 18
specifications. Four of the 18 carry a delta of exactly 0.0000 because their
window admitted no articles, making news and control the same model; those
are not live tests.

**In all 14 live specifications the news layer made election-wide MAE worse**,
7.5872 rising to between 8.4559 and 20.5740, while the Reform sub-metric
improved by 7.40 to 10.26 points. Worst case is local / 14-8 days: overall
MAE 20.5740, a 12.99-point deterioration, with 195 of 279 rows clipped.

### 1.4 Component mixing — the challenge holds

The Reform-versus-group contrast is Reform's change in |bias| minus the plain
mean of the same quantity over the other fitted parties.

| island | window | contrast | Reform component | group component | group n |
|---|---|---:|---:|---:|---:|
| 2021 | 180-91 | −12.9718 | −10.2570 | **+2.7148** | 5 |
| 2021 | 90-31 | −11.3849 | −9.1417 | **+2.2432** | 5 |
| 2026 | 180-91 | +5.3884 | +4.6328 | **−0.7556** | 4 |
| 2026 | 90-31 | +2.8223 | +1.8357 | **−0.9866** | 4 |

On both islands the two components carry **opposite signs**, so the
subtraction adds their magnitudes instead of netting out a shift common to
all parties. On 2021, 21 per cent of the −12.97 comes from the other five
parties getting worse. The contrast is therefore not a clean
"Reform versus the rest" statistic.

### 1.5 Independence — half the challenge holds

**The arms do overlap.** `combined = local + national` is an exact arithmetic
identity, enforced cell by cell by an assertion in `build_feature_table`
(`arm reconciliation failed for ...`). The combined mixture is 91.678 per
cent national by volume.

**The windows do not overlap.** The six confirmatory windows are strictly
disjoint by construction and their article counts sum exactly to
`previous_180_days`. This half of the challenge should not be conceded.

**Independence fails anyway, for a third reason.** The 18 specifications
produce only **14 distinct prediction vectors**. Two collision groups:

- combined/final-72h, national/7-4, national/final-72h and local/final-72h
  are all byte-identical to one another (four specifications, one vector);
- combined/7-4 and local/7-4 are byte-identical (two specifications, one
  vector).

The first group is exactly the set of four with `mde_80_power = null` in the
MDE annex, so that annex's "14 estimable" is not contaminated. But the second
group means the annex counts one prediction vector twice: **13 distinct
estimable comparisons, not 14**. That is a correction owed to
`minimal_detectable_effect_v1`.

#### A claim of mine that was wrong

I previously stated that all 18 specifications share a control constant of
+7.2637858384. **That is false.** The recalibrated-minus-baseline offset is
row-specific, not a single constant; the check that produced the number was
wrong. The non-independence conclusion stands on the 14 distinct prediction
vectors instead, which is directly measurable from
`validation_predictions.csv`.

---

## 2. The placebo

Committed as `placebo_specifications_v1/`, module
`news_modelling.placebo_specifications`. Every arm shares the 45 frozen
fitting cells and the frozen prediction and scoring code; only
`feature_columns` differs. The frozen arm reproduces its committed deltas to
a maximum absolute difference of **0.0000**, and the run aborts if it does
not - that gate is the licence for every other number in the file.

| arm | 180-91 | 90-31 | 30-15 | 14-8 |
|---|---:|---:|---:|---:|
| frozen (`party_article_share` + `net_portrayal_share`) | −0.5751 | +0.2404 | +0.1339 | −0.3252 |
| **placebo_volume** (`party_article_count` alone) | **+0.1684** | **+0.2247** | **+0.1259** | −0.0043 |
| **placebo_volume_tone** (count + raw `net_portrayal`) | +0.1892 | **+0.3413** | −0.0261 | +0.0742 |

A single count variable, needing no content judgement of any kind,
reproduces **93 per cent** of the certified 90-31 day result and **94 per
cent** of the 30-15 day result - and it avoids the frozen specification's
largest harm, turning 180-91 days from −0.5751 into +0.1684.

**The supervisor's reading of this is correct: most of the certified effect
is volume.**

### 2.1 The content features against the right bar

The bar is not zero and it is not the frozen pair. It is
**placebo_volume_tone = +0.3413**, the best arm carrying no judgement about
what any article was about. Beating the frozen pair while losing to a
counter would settle nothing.

Seven content features, added one at a time to the frozen pair, 90-31 days.
All seven were fixed before any was fitted, and all seven are reported:

| content feature | delta | 95% CI | beats the bar |
|---|---:|---|---|
| `party_frame_incumbent_judgement_share` | **+0.5718** | [+0.3864, +0.7533] | **yes, whole interval above it** |
| `party_issue_issue_other_share` | +0.3446 | [+0.1856, +0.4857] | yes, but within noise |
| `party_issue_immigration_share` | +0.3202 | [+0.1083, +0.5119] | no |
| `party_frame_challenger_emergence_share` | +0.3167 | [+0.1192, +0.5022] | no |
| `party_frame_local_impact_share` | +0.2903 | [+0.1326, +0.4374] | no |
| `party_issue_national_politics_share` | +0.2050 | [+0.0687, +0.3275] | no |
| `party_frame_voter_discontent_share` | +0.1761 | [+0.0095, +0.3331] | no |

**Two of seven beat the bar; one does so with its whole interval above it.**

This must be read narrowly. Seven features were tried, so one clearing a bar
is a multiple-comparison result before it is anything else; the fit has 45
cells; and the holdout that could have certified an effect is spent. It is a
reason to look harder at that feature, not a certified effect.

**All seven at once give −0.6635 [−0.8436, −0.4841]** - worse than doing
nothing and worse than every single-feature arm. Nine features on 45 cells is
the overfitting the design expected to find, and finding it is the check
working rather than failing.

### 2.2 Only two windows could be tested at all

A content feature enters a window only if it clears the ten-value bar in that
window's own training rows. **The 30-15, 14-8, 7-4 and final-72-hour windows
admit none of the seven.** Coverage there is 6 to 18 articles per election
(section 4), so the near-campaign question the design was built to ask cannot
be answered by this corpus at any grain.

### 2.3 A counterweight that already exists in a committed artefact

`synthetic_scenarios_v1/scenario_results.json` injects ten articles about
Reform into the 30-15 day window, identical injection context both times
(7 window articles, 3 party articles before injection), varying only tone:

| tone | Reform mean share delta |
|---|---:|
| favourable | **+1.0030** |
| unfavourable | **−2.0029** |

Same volume, opposite tone, a 3.0-point swing. This is a **simulation of how
the frozen model responds**, not evidence about voters - the file's own
disclaimer says so - but it does establish that tone is not inert inside the
model, which the placebo result alone might be read to imply.

---

## 3. What was actually tested, which is narrower than "news"

The frozen specifications carry exactly two features: `party_article_share`
and `net_portrayal_share` - volume and tone. **Neither is a content feature.**
The issue and framing layers never entered a specification.

So the placebo result establishes that **volume plus tone does not beat
volume**, which is close to circular. Whether *what the news is about* adds
anything had not been asked.

### 3.1 Why the content layers were excluded, and why that reason was wrong

Both layers failed the reporting gate at **4 distinct training values within a
period** against a bar of 10, and were recorded as `fittable_not_reportable`.
I read that as data scarcity.

It was not. The same columns carry **26 distinct values pooled across
periods**. Sparse within a period and rich across them is the signature of a
per-election aggregation: all six parties of an election share one value, so
the only within-period variation left is between the four elections.

Measured directly on `news_feature_table_v2.csv`: **144 of 144**
election-period cells carry identical `issue_*` and `frame_*` values across
every party, while `party_article_share` in those same cells ranges from
0.011 to 0.614.

Stance escaped because a stance record names a party in every judgement.
Issues and framing do not - but the extraction records
`political_relevance.affected_actors` on **68.1 per cent** of issue records,
and the builder never read it.

### 3.2 The rebuild, and what it produced

Committed as `news_feature_table_v3party.csv`. Attribution reuses
`stance_rescue.PARTY_ALIASES`, extended with fourteen leaders whose party is
unambiguous over the corpus window, plus a date-resolved mapping for Nigel
Farage (421 mentions across six elections, the only actor whose party changes
inside the window).

Framing needs no re-extraction: **2,559 of 2,576** framing records share an
article with an issue record, so a frame inherits the actor set established
for its own article.

Attribution outcome: **1,368 of 2,138** articles carrying an issue record
were attributed to at least one party (64.0 per cent); 770 named no
recognised party. Mean parties per attributed article, 2.3999.

Distinct training values, per window, training side, bar of 10:

| column | 180-91 | **90-31** | 30-15 | 14-8 | 7-4 | final 72h |
|---|---:|---:|---:|---:|---:|---:|
| issue_immigration_share | 4 | 4 | 3 | 2 | 1 | 2 |
| **party_**issue_immigration_share | 19 | **10** | 4 | 3 | 1 | 1 |
| issue_national_politics_share | 4 | 4 | 3 | 3 | 2 | 2 |
| **party_**issue_national_politics_share | 20 | **12** | 5 | 4 | 1 | 1 |
| issue_issue_other_share | 4 | 4 | 3 | 3 | 1 | 1 |
| **party_**issue_issue_other_share | 19 | **12** | 3 | 7 | 1 | 1 |
| issue_council_services_share | 4 | 4 | 1 | 3 | 2 | 1 |
| **party_**issue_council_services_share | 14 | 8 | 1 | 5 | 1 | 1 |
| frame_incumbent_judgement_share | 4 | 4 | 3 | 4 | 2 | 2 |
| **party_**frame_incumbent_judgement_share | 20 | **12** | 4 | 6 | 1 | 0 |
| frame_challenger_emergence_share | 4 | 4 | 3 | 4 | 1 | 1 |
| **party_**frame_challenger_emergence_share | 20 | **10** | 3 | 6 | 1 | 0 |
| frame_voter_discontent_share | 4 | 4 | 3 | 4 | 2 | 2 |
| **party_**frame_voter_discontent_share | 20 | **12** | 5 | 6 | 1 | 0 |
| frame_local_impact_share | 4 | 4 | 3 | 2 | 2 | 2 |
| **party_**frame_local_impact_share | 20 | **11** | 3 | 5 | 1 | 0 |

**Seven columns clear the bar at the 90-31 day confirmatory window** - three
issue categories and all four frames. `council_services` clears only at
180-91 days.

Grain check on the rebuilt table, restricted to cells where the layer coded
anything: per-election columns are constant across parties in **32 of 32**
cells; party columns are constant in **0 of 29** (issues) and **0 of 28**
(frames).

### 3.3 What the rebuild cannot fix

- **crime_policing** and **housing_planning** carry 1 distinct value before
  and after. They are genuinely near-absent from this corpus.
- **issue_none** moves from 4 distinct values to 2. It is residual
  bookkeeping - an article with no political issue usually names no actors -
  and it is not a content feature.
- Attributing an **article-level** frame or issue to every party the article
  names is an approximation. An article framed as "voter discontent" that
  touches both Labour and Reform credits both. This is a real limitation and
  it applies equally to the issue layer.

**Nothing in this section shows the content features are informative.** It
shows they are now estimable. The test that matters is against the
volume-only placebo, not against zero.

---

## 4. Coverage, which bounds everything above

Articles per training election per window, summed over parties, from
`news_feature_table_v2.csv`:

| election | 180-91 | 90-31 | 30-15 | 14-8 | 7-4 | final 72h |
|---|---:|---:|---:|---:|---:|---:|
| SCC-2013-05 | 731 | 70 | 6 | 8 | 0 | 0 |
| SCC-2017-05 | 748 | 57 | 18 | 42 | 17 | 0 |
| Addlestone 2025 | 763 | 114 | 7 | 1 | 0 | 0 |
| Camberley West 2025 | 537 | 40 | 17 | 12 | 0 | 4 |
| Caterham Valley 2025 | 0 | 0 | 0 | 0 | 0 | 0 |
| Guildford SE 2025 | 0 | 0 | 0 | 0 | 0 | 0 |
| Hinchley Wood 2025 | 0 | 0 | 0 | 0 | 0 | 0 |
| Nork Tattenhams 2025 | 0 | 0 | 0 | 0 | 0 | 0 |
| Warlingham 2019 | 0 | 0 | 0 | 0 | 0 | 0 |
| Weybridge 2015 | 0 | 0 | 0 | 0 | 0 | 0 |

**Six of the ten training elections carry zero articles in every window.** In
the 30-15 day window - where campaign coverage should matter most - the four
elections that do have coverage carry 6, 18, 7 and 17 articles.

The enrichment that added eight by-elections added **two** with any coverage.

### 4.1 The extraction itself is not the bottleneck

Validation results for the layers in use, from the register:

| layer | agreement | status |
|---|---|---|
| revised three-level stance | inter-model kappa **0.848**, human 0.741 / 0.736 | in use |
| issues | human kappa **0.616**, inter-model 0.742 | in use |
| revised incumbent-judgement frame | inter-model kappa 0.705 | in use |
| revised local-impact frame | inter-model kappa 0.635 | in use |
| consequence | kappa 0.259 | excluded |
| credit/blame | human kappa 0.521 / 0.516 | excluded |
| E5 local triage | kappa **0.4762** against a 0.600 bar | **failed** |

Re-running the extraction on the same articles would relabel work that
already passed validation, some of it comfortably. It cannot create articles
that do not exist.

The one gate that failed is the E5 local triage, and it is the gate that
would have let **local** coverage into the corpus. Its failure is why the
corpus is 91.7 per cent national, and national coverage of a county election
is largely national politics - which is a plausible route to features that
behave like volume.

---

## 5. Historical rebuild failure and its resolution

Discovered while running this work, and not caused by it. Four extraction
tranches were written after the feature tables and hold articles no relevant
release admits:

| artefact | written |
|---|---|
| news_feature_table_v1.csv | 2026-08-01 12:26 |
| news_feature_table_v2.csv | 2026-08-01 16:23 |
| haslemere1 tranche | 2026-08-01 22:55 |
| e5local1 tranche | 2026-08-02 01:31 |
| wokingsouth1 tranche | 2026-08-02 17:23 |

Articles outside each release: **948** for v1 (the three above plus the
by-election enrichment, which v1 by definition does not admit), **321** for
v2, **272** for v3exp. All three builds stopped on the builder's corpus
assertion, which was behaving correctly.

Each wrapper now declares its own lineage. All three tables then rebuild
**byte-identically** to the committed CSVs, and the v2 metadata's
`provenance` block is unchanged as well - it was written on 2026-08-01 when
those tranches did not exist, so matching it is evidence the declared set is
right rather than merely sufficient.

---

## 6. Conclusions at the 5 August review checkpoint

**Can be claimed.**

- The 2021 zero-of-eighteen null stands.
- The 2026 confirmatory result stands as certified, but the placebo
  (`placebo_specifications_v1/`, now committed) indicates it is close to a
  volume effect, and it should not
  be reported without that caveat.
- The corpus carries 6 to 18 articles per election in the 30-15 day window,
  and six of ten training elections carry none.
- The layers in use passed validation at kappa 0.616 to 0.848.

- Most of the certified effect is volume: a raw article count reproduces 93
  per cent of it and avoids the frozen specification's largest harm.
- One content feature - the share of a party's coverage framed as a judgement
  on the incumbent record - beats every content-free arm at 90-31 days with
  its whole bootstrap interval above the bar, as one of seven tried.

**Cannot be claimed.**

- That the Reform contrast demonstrates a transfer failure. It mixes two
  components of opposite sign and its 2021 half is a clipping artefact.
- That the 18 specifications are 18 independent tests. There are 14 distinct
  prediction vectors, 13 of them estimable.
- That news content does not help. Six of seven content features lost to the
  bar, but the seventh beat it clearly, and the near windows could not be
  tested at all.
- That the incumbent-judgement result is an effect. Seven features were
  tried, the fit has 45 cells, and the holdout is spent. It is a lead.
- That the near-campaign windows show anything either way. No content
  feature clears the reporting bar in any of them.

**Open, and decided by work not yet done.**

- Whether the incumbent-judgement frame survives a design that could certify
  it. Nothing in this repository can, because the holdout has been unsealed.
  It is the obvious pre-registered hypothesis for a future election.
- Whether local coverage would change any of it. The E5 local triage failed
  at kappa 0.4762, which is why the corpus is 91.7 per cent national.

## Correction (2026-08-14): the "near-absent" issue buckets were a mapping defect

Section 3.3 above records that `crime_policing` and `housing_planning`
"carry 1 distinct value before and after" and calls them "genuinely
near-absent from this corpus". The first half is true; the diagnosis is
superseded. `ISSUE_GROUPS` in `src/news_features/build_feature_table.py`
was drafted from the feature plan's shorthand ("crime", "housing", ...)
rather than from the extraction prompt's `issue_code` enum, so the enum
values `crime_policing`, `planning_housing`, `waste_recycling` and
`schools_send` never matched any bucket. Across the deduplicated
extraction record that is 166 coded articles (61 / 50 / 5 / 50) routed
to `issue_other` - the coverage exists; the map could not see it.

Disposition, per the freeze rules:

- The frozen v1/v2 feature tables were built with the defective map and
  are **not regenerated**; their byte-identical rebuild tests pin the
  defective map in place, and `tests/test_issue_group_mapping.py` now
  asserts the defect explicitly so it cannot be "fixed" by accident.
- A corrected map (`ISSUE_GROUPS_CORRECTED`, member strings taken from
  the enum itself) is available to any post-freeze build, and the same
  test file pins every enum value's corrected routing.
- No committed analysis changes. The confirmatory arms never read issue
  columns; the exploratory content-feature results already excluded the
  empty buckets via the distinct-value gates. The affected claims are
  descriptive: `issue_other` (27.6% of v1 issue records) is inflated by
  the misrouted articles, and no statement that crime or housing
  coverage "was absent" survives this correction.
