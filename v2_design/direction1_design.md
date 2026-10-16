# Direction 1: England-wide local election forecasting, with a fair test of news

**2026-10-11. Design document, written before any direction 1 code or
any 2025 result is fetched.** Decisions here are fixed when committed.
Later changes are recorded at the end, with their reasons.

## 1. Goal, stated honestly

V1 forecast one county (Surrey) and found a news "gain" that turned out to be
party identity. V2's design work (`design_decision_v1.md` and the folders it
cites) showed that council-level news effects cannot be confirmed at
England's scale through party-named local coverage or incumbent performance.

Direction 1 has two goals:

1. **Build the forecasting system V1 should have been:** England-wide,
   compared against classical election baselines, and tested out of sample
   on an election it has never seen (May 2025).
2. **Give a credible answer on news,** using a pre-registered test in the
   setting where news has the best chance of adding information: a new
   party's **cold start**, where history is empty and national polls say how
   much, but not where.

The aim of goal 2 is a fair answer, not a positive one. Searching designs
until news "works" is exactly the multiplicity problem V1 was criticised for.
The test is fixed here, and its result is reported whatever it is.

## 2. V1's problems and what direction 1 does about each

| V1 problem | direction 1 |
|---|---|
| 45 election-party cells, one county | hundreds of councils, thousands of ward contests (926 elections already fetched) |
| news "gain" was party identity | party and national polling are in every model; news must add value on top of them |
| static party effects did not transfer between elections | time-varying national polling replaces static party indicators |
| validated on one election | temporal holdout: train on 2017–2023, test once on May 2025 |
| no classical baselines | persistence, uniform swing and proportional swing are compared first |
| 24 comparisons, no correction | two pre-registered primary hypotheses, Holm-corrected; everything else exploratory |
| local classifier "failure" | resolved as a label defect; `llm_eval` evaluates the news classifier |
| reproducibility | one command per stage, offline tests, data provenance recorded |

## 3. Data

**Elections (Democracy Club, free).**

- *Training and validation:* the three rounds already fetched (2017→2021,
  2018→2022, 2019→2023).
- *Test:* English whole-council elections on 1 May 2025, each paired with the
  same council's previous election. The same filters as `incumbent_power_v1`
  apply: at least 10 ballots, comparable ballot counts, and joint party
  labels normalised. Same-day by-elections are excluded. Several councils
  listed for 2025, Surrey among them, are by-elections only because their
  scheduled elections were postponed.
- **2025 results are fetched exactly once,** after the model freeze is
  committed (section 7).

**National polling.** Voting-intention polls from the Wikipedia tables of
national opinion polls, recorded with publication dates. A feature uses only
polls published before polling day: the mean of the last 14 days before
polling day, for each party. The source and the scraped table are committed
with a hash.

**Unit and outcome.** One unit is a **ward contest × party**. The outcome is
the party's vote share in that ward, using the top-candidate method in
multi-member wards (each party's best-placed candidate). This is the same
convention as `incumbent_power_v1`.

**Previous result.** A ward's previous result is matched by GSS code. Where
boundaries changed (no GSS match), the previous result falls back to the
party's council-wide share at t−1, and a flag records the fallback. Kent
2025: 12 of 72 divisions changed.

## 4. Features (all known before polling day)

| feature | note |
|---|---|
| party's previous share in the ward (or the council fallback) | history |
| change in the party's national poll average since the previous election | time-varying party signal |
| party, region, council type | categorical |
| standing in this ward for the first time (**cold-start flag**) | central to H2 |
| incumbent councillor standing for the party | from the candidate lists |
| number of candidates; parties absent this time | contest structure |
| party controls the council at t−1 | from the t−1 seat majority |

## 5. Models

**Classical baselines (they must be beaten first):**

1. *Persistence:* last share carries over.
2. *Uniform swing:* last share plus the party's national poll change.
3. *Proportional swing:* last share scaled by the party's national poll
   ratio.

Shares are renormalised to 100 within each contest. Cold-start rows, which
have no last share, take the party's national poll share, divided by the
number of contests it stands in, scaled to its national level. This is the
naive cold-start rule.

**Machine-learning models:** ridge regression (interpretable), LightGBM (as
in V1), and ridge with council-level random intercepts (councils share
information but keep their own level). They are fitted on the residual from
uniform swing, so each model learns corrections to a classical forecast,
not the forecast from scratch.

**Selection, on 2017–2023 only:** fit on 2017→2021 and 2018→2022, validate on
2019→2023. The model and its hyperparameters are chosen by validation MAE.
The chosen configuration is then refitted on all three rounds. 2025 plays no
part in any choice.

## 6. Pre-registered hypotheses (tested once, on 2025)

**H1, the system.** The selected model's ward × party MAE is lower than the
best classical baseline's.
*Estimand:* MAE(best baseline) − MAE(model), in pp. The 95% CI comes from a
bootstrap over councils, since contests within a council share shocks.

**H2, news, cold start.** It runs only if the power gate in section 8 passes.
On 2025 rows where **Reform UK stands in a ward for the first time**, content
features improve on volume:
*Estimand:* Δcontent = MAE(M1) − MAE(M2), where

- M0 = the selected model,
- M1 = M0 + Reform coverage volume in that council's local outlets,
- M2 = M1 + content features (tone toward Reform, issue and frame shares,
  incumbent-judgement frame), from the frozen V1 classifier and extraction
  layers.

The news window is fixed at 90–31 days before polling day.

**Multiplicity.** H1 and H2 are Holm-corrected at α = 0.05. Everything else
(other parties, other windows, embeddings, M1 vs M0) is labelled exploratory.

**Secondary, reported but not tested:** seat-winner accuracy, council-control
accuracy, calibration of predicted shares, and performance by council type.

## 7. Leakage and blindness

- Every feature uses only information published before polling day.
- **Freeze:** before 2025 results are fetched, the selected model, its
  hyperparameters, the feature code and (if H2 runs) the news features are
  committed together with a manifest of file hashes. The 2025 fetch then runs
  once. Scoring code reads the frozen files only.
- **Known limitation:** the broad 2025 outcome (Reform's surge) is public
  knowledge, so this is not a blind test in V1's sense. The mitigation is
  procedural: every modelling choice is made on 2017–2023 validation and
  committed before 2025 data enters the repository.

## 8. Stage gates

1. **H2 power gate (free, before any news spend).** Using election data only,
   estimate how large an effect on Reform cold-start MAE H2 could detect,
   given the 2025 cold-start rows and the council-level clustering. If the
   MDE80 exceeds 1.0 pp, H2 is not run. It is reported as underpowered and
   no money is spent on news. This is the same logic as `incumbent_power_v1`.
2. **News budget.** H2 collection uses outlet sitemaps (Wayback proved slow
   and noisy), prefilter v1, and the frozen classifier via Batches. The cap is
   **US$20**, enforced by `llm_eval`'s budget guard. The classifier is
   re-evaluated with `llm_eval` on a sample of the new outlets before its
   output is used.
3. **Training signal for news.** M1/M2 coefficients are fitted on 2021–2023
   Reform candidacies (759 in the fetched data) with news for the same
   councils and windows. If that training news cannot be collected within
   budget, H2 falls back to a zero-fit rule: the national Reform share is
   allocated across councils in proportion to coverage. This is decided at
   gate 1 and recorded.

## 9. Deliverables

1. A cleaned England-wide dataset with documented provenance and cleaning
   rules.
2. A forecasting system, with one command per stage: data, features, fit,
   freeze, test.
3. The 2025 out-of-sample result: H1, and H2 or the documented reason it
   was not run.
4. The news module, evaluated with `llm_eval`.
5. A V2 report and a README with conclusions first.

## 10. Plan

| stage | content | time | gate |
|---|---|---|---|
| 1 | this design | done | committed before code |
| 2 | data: units, previous results, boundary fallback, polls | 3–5 days | data tests pass |
| 3 | baselines + ML models, 2017–2023 validation, model selection | 4–6 days | H1 configuration committed |
| 4 | H2 power gate (free) | 1 day | MDE80 ≤ 1.0 pp, or H2 dropped |
| 5 | news collection and features (if gate passes) | 3–5 days | ≤ US$20 |
| 6 | freeze, fetch 2025 once, score H1 (and H2) | 1 day | — |
| 7 | report and README | 3–5 days | — |

## Amendments

**A1 (2026-10-12, stage 3, on validation data only; 2025 untouched). H2's M0
changes.** The design named "the selected model" as H2's M0. On 2019→2023
validation, the selected LightGBM over-predicts Reform: mean 10.3% against an
actual 6.8%, so its Reform cold-start MAE is 4.47 pp against 2.75 for uniform
swing. Its cold-start correction is learned mostly from other parties' first
candidacies (Greens, Liberal Democrats, independents), which tend to be
targeted and to beat the national poll. With a biased M0, news could look
useful merely by correcting that bias. **M0 is therefore the no-news model
with the lowest validation MAE on Reform cold-start rows, from any family.**
Currently that is uniform swing. M1/M2 add news on top of that M0. The rule
is recorded in `direction1_models/selected_config.json` (`h2_m0`). H1 is
unchanged.

**A2 (2026-10-12, stage 3b, validation data only; 2025 untouched). The
no-news system gets a Reform cold-start model before the freeze.** A1 only
protected H2. The H1 model still over-predicted Reform, the problem V1 set
out to study. Two pre-election, non-news features are added: the council's
2016 EU-referendum Leave share (`forecast.geography`; Electoral Commission
data) and the populist-right family's (UKIP + Reform) council-wide share at
t−1. Party-specific cold-start interactions stop Reform borrowing other
parties' first-candidacy pattern. A Leave-scaled rule, national poll ×
(council Leave / England Leave)^γ with γ fitted on training rows only, is
added as a baseline (`uniform_swing_leave`) and as a hybrid option for the
ML models. Selection rules for H1 and H2 are unchanged; they simply see more
candidates. Results are in `direction1_models/stage3b_findings.md`.

**A3 (2026-10-14). 2025 pre-election inputs may be read before the freeze;
2025 results still may not.** The ward-coverage check
(`ward_coverage_v1/criteria.md`, A3) reads Kent's 2025 candidate list and
local articles published 1–30 April 2025. Both are information available
before polling day, the same kind a real forecast would use. Democracy
Club's ballot response also carries results, so the code
(`forecast.reform_2025_coverage.strip_results`, test-enforced) keeps only
ballot, person id, name and party at read time; no vote count or elected
flag is stored or printed. The single post-freeze read of 2025 results is
unchanged.

**A4 (2026-10-14). H2 is reopened at council level and specified in full
before any 2025 result is read.** The power gate's A3
(`direction1_power/criteria.md`) found that A2's "no council-level error"
came from Reform's small 2023 share; at a large-party error level, MDE80 =
0.72 pp, under the 1.0 pp gate. The ward-level strand stays closed
(`ward_coverage_v1`, R1 = 9.9%). What changes from section 6:

- *Units:* 2025 Reform UK cold-start rows in the 23 councils of the power
  gate. News is measured per council.
- *News source:* one local outlet per council, chosen mechanically
  (`forecast.h2_news_2025`, recorded in `direction1_h2/outlets.json`).
  Articles are read **only from Wayback captures taken 1–30 April 2025**,
  each URL from its earliest capture; live pages are never read, because an
  article online today may have been edited after polling day. Only
  articles **published 1–30 April 2025** count.
- *Window:* 30–1 days before polling day, not 90–31. Statements of persons
  nominated were published in early April, so the 90–31 window ends before
  the candidate campaign starts. This is the reason recorded in
  `ward_coverage_v1/criteria.md` A2, and A2 already fixed 30–1 for any
  hypothesis designed after it.
- *Attribution:* an article belongs to council c if it is from c's outlet
  and its text names the council (its area name; "Durham" for County
  Durham). It is **about Reform** if it contains "Reform UK" or "Farage".
- *M1 (volume):* V_c = Reform articles / all articles attributed to c
  (among the downloaded politics-slug articles).
- *M2 (content):* M1 + S_c, the net portrayal of Reform: (favourable −
  unfavourable) / Reform articles, from V1's revised stance layer (same
  prompt and model, κ 0.736), run by Batches on Reform articles only.
  Issue shares are exploratory, not in M2: with 23 councils each extra
  feature costs power.
- *Fitting:* M1 and M2 add β·z(feature) to M0 on Reform rows. β is fitted
  on the other 22 councils' rows and applied to the held-out council
  (leave-one-council-out cross-fitting), exactly as in the power
  simulation. Section 8's gate 3 (fitting on 2021–2023 news) is dropped:
  Reform was too small in 2021–2023 to train on.
- *Estimand and test:* Δcontent = MAE(M1) − MAE(M2) on Reform cold-start
  rows, with a 95% council-bootstrap CI and a one-sided bootstrap p.
  H1 and H2 are Holm-corrected at α = 0.05. Exploratory: M1 vs M0 (news vs
  no news), issue shares.
- *Classifier check:* before its output is used, the stance layer's labels
  on 40 random Reform articles are compared with a second, stronger model.
  κ < 0.60 stops H2 (reported as a measurement failure). This is an
  agreement audit, not human validation; it is stated as such.
- *Budget:* US$20 cap, as in section 8.
- *Freeze:* outlets, news features, H2 code and the H1 model are committed
  with a hash manifest before 2025 results are fetched once.

*A4 implementation note (2026-10-14, before any H2 feature was computed).*
The URL keyword filter in `forecast.h2_news_2025` was widened after the
first download. Reach titles truncate URLs to the headline's first few
words, so the first list kept 1–3% of their article URLs against 3–5% of
Newsquest's, making article counts depend on the publisher. The widened
list (council and party-politics words) keeps 6,171 of 61,000 URLs. Outlets,
window and features are unchanged; per-council counts from the first list
were looked at (counts only, no stance and no 2025 result).

*A4 data-sufficiency rule (2026-10-14, fixed before the widened download
finishes; no stance computed, no 2025 result read).* After the download,
count each council's Reform articles (`h2_news_2025 count`). If **12 or
more of the 23 councils have fewer than 10**, each of those councils gets
a second outlet: the next candidate in its list that has at least 100
article captures in 1–7 April 2025 (the same rule as the first). Councils
with no second candidate in the list get one added from the other main
local publisher in the area, written into the code before it is probed. A
council with no qualifying second outlet is recorded as such. If 11 or
fewer councils fall under 10, no outlet is added. Article counts are not
outcomes (they say nothing about how news relates to M0's errors), so
adding data on this rule does not use any result. Fewer than 10 articles is
the point where one misjudged article moves a council's net portrayal by
more than 0.1.

*A4 exploratory measure (2026-10-14, fixed before any article is sent to an
LLM).* Alongside S_c, a separate LLM question asks of each Reform article:
does it report **specific local Reform campaign activity** (a named local
candidate, a local event or rally, a councillor defecting to Reform, a
campaign incident)? A_c = share of the council's Reform articles answering
yes. It is asked in its own request, so V1's validated stance prompt is
sent unchanged. A_c is **exploratory**: it has no human validation, it is
not in M2 and not Holm-tested, and its result cannot replace H2's. Why it
is added: in Kent, the Reform candidates local news named were mostly
defecting councillors and candidates in local incidents (`ward_coverage_v1`),
local information that polls and Leave share do not carry. It also tests a
finer text representation than V1's three-way portrayal without spending
H2's power on it.

*A4 exploratory robustness check (2026-10-15, fixed before any stance is
computed and before any 2025 result is read).* H2's estimand is recomputed
on the councils with at least 10 Reform articles only (same models,
cross-fitting and bootstrap). It is exploratory: it is reported next to H2
and cannot replace it. Why: many councils have few Reform articles, so S_c
is noisy there; the check shows whether H2's answer depends on them.

*A4 attribution diagnostic (2026-10-15, counts only).* Of 390 window
articles in the first outlets that mention Reform UK or Farage, 231 name
their council's area. 151 of the other 159 are national wire stories
(Newsquest `/news/national/`, Reach `/uk-world-news/`); 8 are local but
name another area or only "Northamptonshire". The attribution rule is kept:
it removes national coverage that would otherwise inflate Newsquest
councils' counts.

*A4 data-sufficiency rule, outcome (2026-10-16, counts only; no stance
computed, no 2025 result read).* With the widened URL filter and first
outlets only, 15 councils had fewer than 10 Reform articles
(`direction1_h2/coverage_counts_first_outlet.json`), so the rule was
triggered. Eleven got a second outlet (`direction1_h2/outlets.json`,
"second"); Leicestershire, Shropshire, Warwickshire and West
Northamptonshire had no candidate with 100 probe-week captures (best: 90,
78, 0, 85) and keep one outlet. KentOnline's whole-domain listing timed
out, so it is listed by town section as in `outlet_pilot_v1`. Result
(`direction1_h2/coverage_counts.json`): 326 Reform articles, median 13 per
council (was 9); 9 councils under 10 (was 15), 1 under 5 (Warwickshire, 3).
No further outlet is added.
