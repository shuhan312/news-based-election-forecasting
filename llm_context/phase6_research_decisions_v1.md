# Phase 6 research decisions log (v1)

Methodological decisions taken during Phase 6, each recorded with
its method, rationale and reversal path. This log is written FOR
THE SUPERVISOR'S INFORMATION: the decisions are made and in effect;
each remains cheaply reversible if review suggests otherwise.
Contract versions make every decision auditable in the outputs.

## D1 - Taxonomy and vocabulary extensions: ADOPTED

**Decision.** Issue taxonomy v1.3 (adds `national_politics`,
`national_economy`) and credit/blame schema v1.1 (adds target type
`politician`) are adopted for all subsequent extraction.

**Method and evidence.** Both extensions came from measured pilot
gaps, not speculation: 23/67 articles had no codable issue under
the local-oriented v1.2 (a 29-article re-run showed 15 move to the
national codes and 9 stay honestly empty); 7 articles could not
attribute blame to ministers or party leaders under the v1.0 target
enum (the politician type was used 50 times once available). The
new national codes mirror the national search topics already in the
project brief.

**Reversal path.** All old records validate under their own version
stamps; rules S7/R9-style gates prevent stamp/vocabulary mixing.
Dropping the extensions means not using the new stamps - nothing
already produced depends on them.

## D2 - Analysis arms defined by content, not by search channel

**Decision.** The local-vs-national comparison uses the Step 8
extracted geographic scope (and the dual 0-1 relevance scores for
continuous treatments) to assign articles to analysis arms. The
collection arm (which search channel found the article) is retained
as provenance only.

**Method and evidence.** Cross-checking 67 pilot articles: the
national channel matched extracted scope 41/41, but 8 of 24
local-channel articles are nationally-scoped content (national
stories matched by local search terms). A channel label mismatches
content ~12% of the time; using it as the analysis arm would dilute
the local arm with national content and bias the comparison toward
finding no difference.

**Reversal path.** Both labels are stored per article; re-running
any analysis under the channel definition is a one-line change, and
reporting both is itself a robustness check.

## D3 - Result-containing articles: retained, excluded from the
## main news-feature windows, included in sensitivity analysis

**Decision.** The 6 pilot articles flagged
`contains_election_result` (pre-election articles reporting
historical/other election results) stay in the corpus and keep all
extraction layers, but are EXCLUDED from the main analysis's news
feature windows; a sensitivity re-run includes them.

**Method and rationale.** Direct leakage is impossible (upstream
eligibility already excludes post-polling publication); the risk is
indirect anchoring - features derived from articles that recite
past results partially encode the electoral history the baseline
model already holds, which would flatter the news model's apparent
contribution. Exclusion in the main run is the conservative
default; the sensitivity pair (with/without) measures whether the
choice matters and is reported either way.

**Reversal path.** The flag is deterministic and stored; flipping
the default is a config change.

## D4 - Human validation protocol for the extraction layers

**Decision.** Before full-corpus outputs feed any model, a human
validation gate mirrors the classification pipeline's precedent:
a stratified subset of ~50 articles (election x arm quotas, hash-
ordered - same method as the pilot sample, disjoint where
possible), human-labelled on the key per-layer fields (primary
issue; per-party stance; primary frame; attribution target+type;
consequence direction; impact horizon), compared against the LLM
outputs with agreement statistics (kappa / AC1), gate at >= 0.60.
Machine-vs-machine cross-layer agreement measured in the pilots
(0.6-0.8 band) is the calibration context: ~0.6 human-machine
agreement on these interpretive tasks is the realistic pass bar,
not 90%. Low-confidence (flagged) records are adjudicated
separately via the review-pool worksheet; a trial review of ~20
low-confidence consequence judgements calibrates the 0.5 routing
threshold before the full pass.

**Reversal path.** The gate can be tightened per layer if the trial
review suggests the threshold is too lenient; all thresholds are
constants in the validation code.

## D5 - Expectation note: national-to-local Reform connectors are
## rare

Not a decision but a recorded expectation: only 1 of 11 pilot
Reform articles explicitly connects national momentum to local
electoral competition and none carries ward-level conversion
signals. If full-corpus extraction confirms the scarcity, the
statistical power for the national-momentum-to-local-conversion
question is limited, and the write-up will treat that finding
descriptively rather than forcing an underpowered test. The G5
two-precondition rule keeps the connector subset uncontaminated
either way.

---

Standing execution parameters (unchanged): frozen model
claude-sonnet-5, Batches API, cached prompts; full-corpus
extraction (~$40-55 at intro pricing, ends 2026-08-31) proceeds
after the v2 corpus release so each article is extracted once.
