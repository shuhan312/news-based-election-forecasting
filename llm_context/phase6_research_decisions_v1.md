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

## D6 - Inherently-ambiguous genres: retained, tagged, sensitivity-
## tested, never counted as extraction failures

**Decision (human ruling, 2026-07-27).** Digest/roundup pages, live
blogs, readers' letters, satirical/sketch columns and politics-
adjacent business stories are recognised as a GENRE class whose low
extraction confidence reflects the content itself, not model
failure. Records from these genres are retained with their flags,
the genre is noted, the main analysis includes them with a
with-and-without sensitivity pair, and their flagged records are
closed as a class rather than adjudicated item by item.

**Method and evidence.** The Step 10 audit traced the review pool's
largest component (875 of 1,414 claims) to 104 flagged records
concentrated in ~40 articles; close reading of the four most-
flagged articles (a Society daily links digest, a Digested-week
satirical column, a Dorries celebrity sketch, the Telegraph
takeover story) confirmed in each case that the model's hesitancy
was correct: multi-topic digests have no single issue or stance,
satire inverts stance signals, sketches are semi-fictional, and
media-business stories are politics-adjacent at best. The human
reviewer examined the excerpts and low-confidence triggers and
ruled all four as content-inherent ambiguity (option b), then
generalised the ruling to the genre class.

**Effect.** Roughly 70% of the flagged-record pool closes under
this ruling; the remainder (conventional news reporting with low
confidence) stays for the post-full-scale adjudication pass.

**Reversal path.** The genre tag is additive; dropping the rule
returns the records to the per-item pool unchanged.

## D7 - Absence values never inherit row confidence

**Decision (human ruling, 2026-07-27).** Extraction values that
declare absence or non-indication (not_addressed, not_indicated,
none and equivalents) are treated as MISSING INFORMATION in all
downstream feature engineering, regardless of the confidence score
of the row that carries them.

**Rationale.** Row-level confidence describes the evidence quality
of the row's substantive judgements; an absence field is an honest
statement that the article does not address that dimension. Letting
it inherit a confident row's score would turn "not discussed" into
"confidently established as absent" - a silent upgrade the audit
layer flags as weak_evidence_high_confidence precisely to prevent.

**Effect.** The 104 weak_evidence_high_confidence flags in the
Step 10 audit close as a class; downstream feature builders read
absence values as absence, full stop.

**Reversal path.** One feature-engineering configuration line.

## D8 - Deepening the approved collection stages

**Decision (2026-07-28).** Three collection settings that were
limiting the local arm are changed, without changing the approved
protocol's sources, windows or eligibility rules.

1. **Per-query fetch cap removed.** The stage D Wayback harvest ran
   with `--per-query-cap 8`, a bounded first pass. The CDX index had
   returned 2,994 archived local pages and 110 were fetched. The
   stage was re-run uncapped: +2,810 records (BBC Surrey 1,652,
   SurreyLive 777, Surrey Comet 355, Guildford Dragon 26), 97% with
   full text and 89% with a confirmed date.
2. **Three publishers re-routed.** Farnham Herald, Woking News &
   Mail and Epsom & Ewell Times were already in the protocol via
   site search, but two of them render search results with
   client-side JavaScript and returned zero links (collection report
   issue U1). They now also run through the Wayback CDX route:
   +1,254 records, all in the 2026 window.
3. **CDX URL filter broadened** for whole-domain sources, from
   `.*election.*` to `.*(election|council|vote|candidate|politic).*`.
   Measurement showed the narrow filter was the binding constraint:
   SurreyLive holds 3,000+ archived pages per election window, but
   only URLs literally containing "election" were harvested, so a
   story at `/surrey-council-tax-rise-approved` was dropped.

**Why this is deepening, not redesign.** Same sources, same 180-day
windows, same eligibility rules I1-I6 / E1-E10, same pre-registered
division sample. What changed is how much of an already-approved
search was actually fetched.

**Audit integrity.** Article writes are idempotent, so re-running a
query returns "exists" rather than duplicating. Re-runs append a new
search-log row and never edit the original, so the shallow first
pass stays visible. The frozen v1 corpus (1,546 articles) was
verified row by row as byte-unchanged; expanded date-resolution and
eligibility outputs are written as `*_v2.csv` alongside v1, never
over it.

**Reversal path.** The v1 corpus and its frozen Phase 5/6/7 chain
are untouched, so dropping the new material means simply not
building the v2 corpus.

## D9 - The ward grid is scoped by the pre-registered sample

**Decision (2026-07-28).** The Step 7 expected-observation grid now
marks ward cells outside the pre-registered 17-division sample as
`not_applicable`, not `insufficient_search_coverage`.

**Why.** The brief's to-do 7 asks for ward-tier collection on a
sample of 15-25 divisions, and the project pre-registered 17
(`news_protocol/division_sample.md`, strata: safe, marginal,
changed, Reform-strong, Reform-weak). Enumerating all 81 divisions
and reporting the other 64 as "insufficient search coverage"
described a sampling decision as a collection failure. Inside the
frame, ward-tier search executed for 100% of cells.

**Guard.** The sampling frame explains empty cells only; it never
erases an observation. A ward outside the frame that nonetheless has
eligible articles stays `observed_news` - tested.

**Reversal path.** One column (`in_division_sample`) and one
validity rule; widening the sample means re-running collection for
the added divisions and rebuilding the grid.

---

Standing execution parameters (unchanged): frozen model
claude-sonnet-5, Batches API, cached prompts; full-corpus
extraction (~$40-55 at intro pricing, ends 2026-08-31) proceeds
after the v2 corpus release so each article is extracted once.
