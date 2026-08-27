# Stage 2 feasibility: what the news layer can and cannot be asked

**Recorded 29 July 2026.** These findings were established while building the
Stage 1 baseline and are written down here because they determine whether
Stage 2 can answer the supervisor's central question at all. Until now they
existed only in working notes, which is not a record.

None of this is a modelling problem. It is a coverage problem in the news
corpus, and it has to be settled before the news layer is built rather than
discovered inside it.

---

## 1. The handover, and where it breaks

Prompt 2 requires the news layer to train on Stage 1's out-of-fold
predictions:

> "Use Stage 1 out-of-fold predictions rather than in-sample fitted
> predictions when training the historical news layer."

Stage 1 supplies **792 out-of-fold rows**. The residual model can only use
rows that also carry news features, and that intersection is much smaller.

| | rows |
| --- | ---: |
| Stage 1 out-of-fold predictions | 792 |
| Elections with any news collection | 4 (2013, 2017, 2021, 2026) |
| Divisions with ward-level news collection | 17 of 81 |
| **Candidate rows in both** (pre-2026, sampled divisions) | **199** |
| **of which Reform UK** | **1** |

The residual model's training set is 199 rows, not 792. Its Reform UK
training set is one row.

## 2. Two separate coverage gaps cause this

### Gap A — the division sample was selected on the wrong election

`news_protocol/division_sample.md` defines its Reform stratum as:

> Reform strong: highest **2026** Reform UK vote shares

The model needs rows to **train** on, which means divisions where Reform stood
**before** 2026. Those two sets barely overlap. Of the 14 pre-2026 Reform UK
candidate rows in the release, **2 fall inside the sampled divisions and 12
fall outside**, so the news collection never looked at the wards where Reform
had any history at all.

The eight divisions outside the sample where Reform stood before 2026:

- Bookham and Fetcham West
- Camberley West
- Caterham Valley
- Guildford South-East
- Hinchley Wood, Claygate and Oxshott
- Lightwater, West End and Bisley
- Sunbury Common and Ashford Common
- Waverley Western Villages

This is not a violation of the brief. To-do 7 asks for "an **initial** sample
of 15 to 25 divisions" covering, among other strata, "areas where Reform UK
performed strongly **or weakly**". The stratum was implemented against 2026
outcomes, which serves the test set and starves the training set.

### Gap B — by-elections have no news collection at all

The collection protocol covers four principal elections. It covers **none of
the 19 by-elections**. Of the 14 pre-2026 Reform rows, **8 are in
by-elections**, including the five 2025 contests where Reform polled 12 to 34
per cent and the two recovered in July 2026 where it finished second ahead of
the Conservatives.

The original brief asks for by-elections explicitly — "Please also extract all
Surrey County Council by-elections listed in the main archive" — so their
absence from the news protocol is an implementation gap rather than a design
decision.

### What closing each gap is worth

| action | Reform rows with news, pre-2026 |
| --- | ---: |
| current | 1 |
| add the eight divisions (Gap A) | ~6 |
| add by-election news (Gap B) | ~8 |
| both | **~14** |

## 3. Even at 14 rows, one question stays unanswerable

Fourteen rows cannot support a Reform-specific news interaction — a
coefficient on "negative coverage × Reform UK" estimated from fourteen
observations has a confidence interval wide enough to contain any conclusion.

What 14 rows *can* do is let Reform appear in a pooled all-party model with a
Reform indicator, which is what Prompt 1 already requires for the baseline:

> "do not train a narrow Reform-only model because there are relatively few
> pre-2026 Reform observations. Instead: Train the model using all candidates
> and parties."

So the honest statement of what Stage 2 can deliver:

| question | answerable |
| --- | --- |
| Does news improve candidate vote-share prediction overall? | yes, on ~199 rows now, ~290+ after Gap A |
| Does that improvement extend to Reform on the 2026 holdout? | yes, 163 holdout rows |
| What is the Reform-specific news elasticity? | **no** |
| Which news window matters most? | yes, but underpowered at current coverage |
| Local versus national predictive value? | see section 4 |

## 4. The local-versus-national comparison has its own bind

National articles are linked at election level, not copied across wards, which
is correct. The consequence is that a national feature is **constant within an
election**, so it can only explain variation *between* elections — and there
are four covered elections. Four observations cannot support a national-news
effect estimate.

Local features vary across wards but exist for 17 divisions only.

```
national news: varies over time, not across wards  -> 4 observations
local news:    varies across wards, 17 of 81       -> 199 rows
```

Closing Gap A widens the local arm. Nothing available widens the national arm
except adding more elections, which means either borough elections or
accepting that the national-versus-local comparison is descriptive rather than
inferential.

## 5. Recommended actions, and who decides each

| | action | decision |
| --- | --- | --- |
| A | Extend the division sample by the eight divisions above | **Self-directed.** Same sources, same 180-day windows, same eligibility rules, same protocol; the brief's own wording is "initial sample", and there is precedent in the collection deepening of 28 July. Record it and report it. |
| B | Extend news collection to by-elections | **Self-directed.** The brief asks for by-elections; their absence is an implementation gap. |
| C | Add Surrey borough and district elections | **Supervisor.** Different franchise, different elections, different salience. Prepare the figures and propose it. |
| D | State the power limit in the report | **Required regardless.** The Reform-specific elasticity is not estimable and the write-up must say so. |

A and B together move the Reform news-linked training set from 1 row to about
14, and the all-party training set from 199 rows to several hundred. Neither
changes what the project is measuring; both change whether it can measure it.

## 6. Cost, not yet estimated

Neither A nor B has been costed. Both add collection queries and, more
significantly, LLM extraction volume on top of the 3,584 articles already
awaiting extraction. A budget figure is required before either runs.

*Postscript (August 2026): the extraction subsequently ran to completion
under the batch-discount gates recorded in `llm_context/`; the Stage 2
pipeline and its frozen evaluation are documented in `src/news_modelling/`.*

---

## Related records

- [`candidate_level_estimand.md`](candidate_level_estimand.md) — why the
  modelling cohort is candidate-level
- [`candidate_split_and_leakage.md`](candidate_split_and_leakage.md) — the
  splits the out-of-fold predictions come from
- [`candidate_model_card.md`](candidate_model_card.md) — what the baseline
  achieves and where it fails
- `news_protocol/division_sample.md` — the sampling design discussed in Gap A
