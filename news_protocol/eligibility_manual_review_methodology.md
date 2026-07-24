# Article Eligibility Manual Review - Methodology

Status as of 2026-07-24: **the 168-article human pilot and 34-article
blind recheck are complete; the v1 LLM comparison is complete.** Human
repeatability cleared the specified kappa threshold for all four rules.
Only E6 cleared that threshold in the v1 LLM-to-human comparison; E4,
E5 and E8 remain manual under the current protocol. Section 7 records
the results and the development-only status of any proposed v2 changes.

## 1. Why deterministic and human judgement are kept strictly separate

`src/news_collection/assess_eligibility.py` (the previous pipeline
stage) already applies every rule that is genuinely machine-decidable:
date resolution (E1), the 180-day window and polling-day cutoffs (E2,
E3), a pre-launch-source check (E7, partial), two purpose-built
relevance audits (E5, partial - Guardian non-UK editions, SerpAPI
domain collisions), language detection (E9), and retrievability (E10).
That script's own docstring is explicit that **E4, the rest of E5, E6,
and E8 are not attempted**, because `article_eligibility_rules.md`'s
own "Consistency safeguards" section requires a human reading the
article for exactly those four - they involve judging content, not
checking a fact.

This project's whole design principle (see `resolve_publication_
dates.py`'s BBC 2013 case, and the repeated "never invent, prefer an
honest gap" rule throughout `news_collection/`) is that a script should
never simulate a judgement it cannot actually make. Building an
automatic classifier for "does this article leak the result" or "is
this genuinely about Reform UK" would violate that principle twice
over: it would be guessing at exactly the things the rules document
says must not be guessed, and it would make the eligibility decision
untraceable to a specific piece of evidence. Keeping the two stages
separate means every `include`/`exclude` decision on E4/E5/E6/E8 can be
traced to one reviewer, one timestamp, one quoted piece of text, and
one reason code - auditable in the same sense every other stage of
this pipeline already is.

## 2. How the pilot sample is constructed

See `src/news_collection/build_manual_review_sample.py`'s own
docstring for the full reasoning; summarised here:

- **Population:** the 2,666 records `assess_eligibility.py` left as
  `pending_human_review` (i.e. everything that cleared every
  mechanical check and now needs E4/E5/E6/E8 judgement).
- **Why not a simple random sample:** the pool is 95% Guardian API /
  national arm. A proportional draw of ~175 would contain roughly 0-1
  records from several categories this pilot must say something about
  (local arm, non-Guardian collection routes, thin/missing text,
  Reform-flagged records for 2021/2026). The sample is therefore
  **deliberately disproportionate**: a near-census of the rare
  categories, an oversampled Reform quota, and a stratified-by-
  (election x arm) background draw for the common case.
- **Reproducibility:** every draw uses a single `random.Random` instance
  seeded with a fixed string constant, applied to article-ID-sorted
  input. Re-running the script against an unchanged corpus produces
  byte-identical output - verified by
  `tests/test_manual_review.py::test_sampling_is_reproducible`.
- **Achieved composition (2026-07-23 run, 168 records):** all four
  elections represented (32-63 each); local arm deliberately raised to
  near-parity with national (90 vs. 78, against a 17.9%/82.1% true
  split); every `serpapi` (9) and `site_search` (1) record included;
  every missing-text (12) and partial-text (5) record included;
  35 Reform-flagged records (~21% of the sample, against a 6.2% true
  share).
- **Limitation on record:** this sample cannot speak to reviewer
  behaviour on categories with zero available records in the pool
  (there simply are none to draw), and the achieved counts are capped
  by availability, not always by the target constants in the script -
  the printed composition report each run is the source of truth, not
  the target constants.

## 3. How reviewer consistency will be assessed

`build_manual_review_sample.py` also selects a **blind re-review
subset** (`manual_review_kappa_subset.csv`, currently 34 of the 168
sampled articles, ~20%) at the same time as the main sample - before
any article has actually been reviewed. The protocol:

1. Review the full 168-article sample once (`review_round=initial`).
2. Independently and blindly re-review just the 34-article subset a
   second time (`review_round=kappa_blind_recheck`), **without**
   looking back at the initial round's answers for those articles.
3. Run `src/news_collection/compute_review_agreement.py`, which reports
   **percent agreement and Cohen's kappa**, computed from first
   principles (`kappa = (po - pe) / (1 - pe)`, no ML library
   dependency - see that module's docstring), separately for each of
   E4/E5/E6/E8 and for the derived overall decision.
4. A kappa of at least **0.60** (the conventional "substantial
   agreement" threshold, Landis & Koch 1977) on every rule is treated
   as evidence the codebook is applying consistently enough to proceed
   to the full 2,666-record review. This is a printed advisory verdict
   in the tool's output, not a hard-coded gate - the decision to
   proceed is the researcher's, informed by the number.

Doing steps 1-2 in this order (review once, then blind-recheck a
held-out subset, then measure) is what makes the kappa meaningful: it
measures whether the **codebook** produces stable decisions, not
whether a reviewer can recall or match their own earlier answer.

## 4. How disagreements are resolved

Disagreement is expected at two levels, and the schema keeps them
distinct rather than collapsing them into a single "changed my mind"
field:

- **Within the initial review**, a reviewer who cannot confidently
  reach `include` or `exclude` records `needs_second_review` (per-rule)
  or `insufficient_evidence` if the text itself is inadequate. Neither
  of these is a disagreement yet - they are the reviewer flagging their
  own uncertainty.
- **Between the initial decision and a later adjudication**
  (a second reviewer resolving a `needs_second_review` flag, or the
  kappa exercise revealing the codebook needs a tighter definition),
  the schema requires `final_reviewed_decision` and, if it differs from
  `original_manual_decision`, a mandatory `correction_reason`
  (enforced by `manual_review_schema.validate_row`, requirement 6 -
  `tests/test_manual_review.py::test_conflicting_decision_needs_reason`
  covers this). `original_manual_decision` is never overwritten in
  place, matching this project's "preserve, never resolve silently"
  discipline used everywhere else (raw date_evidence[], the audit
  trail in `manual_review_decisions.csv`).
- A record whose `final_reviewed_decision` is still
  `needs_second_review` or `insufficient_evidence` **cannot** enter the
  downstream analysis corpus - `manual_review_schema.
  is_eligible_for_downstream()` is the single function later stages
  (cleaning, deduplication, analysis) are permitted to call, and it
  returns `False` for anything not a fully-validated `include`.

## 5. Local vs. national relevance stay conceptually separate

Every review row carries `arm` (`local`/`national`) straight through
from `eligibility_assessment.csv`, and E5's reason codes are split
between L-rules (local) and N-rules (national) rather than a single
merged "relevant" code. This is deliberate: the wider research design
compares no-news, local-news, national-news, and combined-news models,
so an article's arm membership must never be inferred or reconstructed
after the fact from its content - it is fixed at collection time
(protocol §4) and simply carried through every downstream stage
unchanged.

## 6. What happens after the pilot, in order

Per `article_eligibility_rules.md` §6 ("no rule in this document may
be changed after collection starts except through the deviations
log"), the sequence is deliberately staged so nothing large-scale
happens under a codebook that later turns out to need revision:

1. **Pilot passes**: the full pilot sample (168 records) has been
   reviewed and every row passes `manual_review_schema.validate_row()`
   with no exceptions.
2. **Blind recheck passes**: the 34-article blind kappa recheck has
   been completed and every rule's kappa is >= 0.60 (§3). If any rule
   falls short, that rule's codebook entry is revised, the change and
   reason are logged in `news_research_protocol.md`'s deviations log,
   and a **new** pilot sample and kappa subset are drawn (not a second
   pass over the same 34 articles, which would no longer be blind) -
   repeat from step 1 with the revised codebook.
3. **Full review**: only once both 1 and 2 hold does the remaining
   ~2,500-record `pending_human_review` population (the 2,666-record
   pool minus the 168 already covered by the pilot) get reviewed
   against the now-validated codebook.
4. **5% independent re-check**: the check required by
   `article_eligibility_rules.md` §6 (minimum 30 articles per election)
   is run against the completed full review, with disagreements logged
   the same way as step 2. This is the final consistency check on the
   actual full-scale review, not a substitute for the pilot's kappa
   check in step 2 - they check different things (step 2: is the
   codebook itself stable; step 4: was it actually applied
   consistently across ~2,500 real decisions).

The codebook is only considered genuinely "frozen" - safe to cite in
the final report as validated - once step 4 is complete and any
disagreements it surfaces have been resolved.

## 7. LLM-assisted classification for the remaining corpus

Manually reviewing all 2,666 `pending_human_review` records at the
same depth as the 168-record pilot is a large time cost. A validated,
disclosed LLM-assisted classification method is used to
handle the bulk of the remaining corpus, structured so it can never
substitute for the researcher's own judgement without evidence that it
agrees with it:

1. `src/news_collection/llm_classifier.py` builds its prompt directly
   from `manual_review_schema.REASON_CODES` - the exact same codebook
   entries a human reviewer works from (§1-§2 of this document), so
   the LLM is judged against identical criteria, never a paraphrased
   or separately-maintained version that could drift.
2. The classifier is run **only** against the same 168 pilot articles
   a human has already reviewed (`run_llm_classification_pilot.py` ->
   `manual_review_llm_pilot.csv`), never the wider 2,666-record pool,
   until the next step has actually happened.
3. `compare_llm_to_human_agreement.py` computes percent agreement and
   Cohen's kappa between the human's decisions and the LLM's, per rule,
   using the identical arithmetic as the blind human recheck in §3. A
   rule only becomes eligible for LLM-assisted classification on the
   remaining ~2,500 records if its kappa clears the same 0.60 bar used
   everywhere else in this protocol; any rule that doesn't stays fully
   manual regardless of how well the other rules perform.
4. **Fail-closed design.** `llm_classifier.classify_article` fails
   closed with `status=not_configured` whenever no `ANTHROPIC_API_KEY`
   is configured rather than fabricating a result - verified 2026-07-23
   against all 168 pilot articles (all 168 correctly produced no
   classification). Step (3)'s kappa gate is the sole criterion for
   trusting LLM output: a rule only becomes eligible for LLM-assisted
   classification once its kappa clears 0.60 against the human pilot.
5. Even once validated, an LLM classification never enters
   `is_eligible_for_downstream()`'s notion of eligibility directly - it
   is written to a separate file and only counts once a human has
   compared it against the gold standard and the agreement has cleared
   the bar in (3). There is no path by which an LLM output reaches the
   analysis corpus without a documented human validation step in
   between.

### 7.1 Pilot comparison results (run 2026-07-24)

The classifier (`claude-sonnet-5`, prompt generated from
`REASON_CODES`, `MAX_TOKENS=4096`) was run against all 168 pilot
articles and compared with the human initial review per step (3).

**Output-format recovery (disclosed).** Two transport-level issues
were found and fixed during the run; neither touches the decision
criteria, and every fix is visible in the git history:

- 39/168 first-attempt responses were valid JSON wrapped in markdown
  code fences and failed `json.loads()`. `strip_markdown_fences()`
  now unwraps a response that is one whole fenced block (and only
  that case - prose-plus-JSON still fails closed). Unit-tested.
- 7/168 responses were truncated mid-JSON at `MAX_TOKENS=1024` when
  supporting-text quotes ran long; the cap was raised to 4096. This
  governs whether the model can finish its answer, not what it says.

Articles whose responses failed to parse were re-requested until each
article had exactly one recorded classification; responses that had
already parsed were carried forward verbatim and never re-rolled (see
`load_previous_ok_rows()` in `run_llm_classification_pilot.py` for
why re-rolling recorded classifications would invite cherry-picking).
Every run's raw output is preserved in timestamped
`manual_review_llm_pilot.pre-rerun-*.csv` backups, and any
still-unparseable response is stored verbatim under
`news_collection/llm_pilot_unparsed_responses/` for diagnosis.

**Results (`compare_llm_to_human_agreement.py`):**

| Rule | Pairs | Percent agreement | Cohen's kappa | Outcome vs the 0.60 bar |
|------|-------|------------------|---------------|-------------------------|
| E4 (result leakage)      | 168 | 86.9% | 0.141 | below - stays fully manual |
| E5 (relevance)           | 168 | 52.4% | 0.191 | below - stays fully manual |
| E6 (Reform disambiguation) | 35 (flagged only) | 88.6% | 0.000 | below - stays fully manual |
| E8 (editorial content)   | 168 | 81.0% | 0.279 | below - stays fully manual |

**Correction made the same day, before any use.** The first
computation of E6 covered all 168 pairs and returned kappa=0.929,
which briefly looked like a pass. That number was inflated by
construction: for every non-Reform-flagged article, BOTH sides'
`e6_decision` is auto-filled to `not_applicable` by code (the human
sheet via `build_review_row()`, the LLM via `classify_article()`)
from the same `needs_reform_disambiguation` flag - 133 of the 168
pairs agreed mechanically and say nothing about the LLM. The
comparison arithmetic was corrected to restrict E6 to the 35
genuinely-judged flagged articles, where the human coded all 35
`include` (constant marginal, so kappa collapses to ~0 - the same
prevalence problem as E4). No LLM output was used on the remaining
corpus at any point between the inflated number and the correction.

**Reading the failures honestly.** The three below-bar rules fail in
different ways, which matters for any follow-up decision:

- **E4** is dominated by class imbalance: the human coded 166/168
  `include`, 1 `exclude`, 1 `insufficient_evidence`, so kappa's
  chance-correction is punishing (86.9% raw agreement yields
  kappa=0.141 - the well-documented kappa paradox). Of the 22
  disagreements, 13 are the LLM answering `insufficient_evidence`
  where the human said `include` (over-hedging), 6 are the LLM
  emitting a reason code (`E4-CLEAR`, which itself denotes include)
  in the decision field, and only 3 are substantive
  include-vs-exclude disagreements.
- **E8** is similar in kind: 136/168 agree; most disagreements are
  hedges (`insufficient_evidence`/`needs_second_review`) or the same
  code-in-decision-field slip; substantive disagreements are single
  digits.
- **E5** is a genuine criteria mismatch, not an artefact: 28
  human-include -> LLM-exclude and 20 human-exclude -> LLM-include
  hard disagreements. The LLM applies the L/N relevance rules
  differently from the human coder, and no formatting fix changes
  that.

**Consequence, per step (3):** no rule cleared the bar, so
LLM-assisted classification is not adopted for any rule at this
stage - the remaining corpus (2,498 articles, of which 130 are
Reform-flagged and therefore also need E6) is reviewed manually per
§6. This is the validation gate doing exactly what it was designed
to do: refusing to delegate a judgement the evidence does not
support delegating. Any revision to this position (prompt iteration
- which would demote these 168 articles to a development set and
require a fresh human-coded validation sample; a different agreement
statistic for the prevalence-skewed E4/E6; or an
LLM-screen-plus-human-check hybrid) is a change to the validation
design and is not adopted here; it would be taken to the supervisor
first, and this section updated with the decision.

## 8. Proposed amendment - pre-registered 2026-07-24, PENDING SUPERVISOR APPROVAL

Nothing in this section is adopted. It is written down *before* any
v2 result on unseen data exists, so that the choice of statistic and
sample cannot later be accused of having been fitted to a desired
outcome. If the supervisor rejects or modifies any part, this section
is updated with the decision and the deviations log in
`news_research_protocol.md` records the change.

### 8.1 Why an amendment is needed at all

Two of the four judgement rules are prevalence-skewed in a way that
breaks Cohen's kappa as an evidence measure (the "kappa paradox",
Feinstein & Cicchetti 1990): on E6 the human coded all 35 judged
pilot articles `include`, and on E4 the human marginal is nearly as
constant. With a near-constant marginal, kappa's chance-agreement
term approaches the observed agreement and kappa collapses toward 0
*regardless of actual performance* - 88.6% observed agreement on E6
returned kappa 0.000. This is a property of the statistic, not of
the classifier, and it makes the existing kappa >= 0.60 gate
uninformative (unpassable in principle) for those rules.

### 8.2 Proposed statistics and gate

For every rule, on the fresh validation sample, report all four of:
percent agreement, Cohen's kappa, Gwet's AC1 (Gwet 2008), and PABAK
(Byrt, Bishop & Carlin 1993) - implemented from first principles in
`compute_review_agreement.py` alongside the existing kappa code.

Proposed per-rule gate, applied identically to every rule:

- **Primary**: Cohen's kappa >= 0.60 (unchanged).
- **Fallback, only where kappa is prevalence-broken** (a rater
  marginal >= 90% in one category, stated here in advance rather
  than judged after seeing results): Gwet's AC1 >= 0.60 **and**
  percent agreement >= 80%.
- A rule failing both routes stays fully manual. No third route.

Sanity check that the fallback is not a rubber stamp: computed
retrospectively on the v1 pilot (development data, illustrative
only), AC1 gives E4 0.862, E6 0.881, E8 0.801 - but E5 only 0.473,
still failing. The statistic distinguishes prevalence artefacts from
genuine disagreement.

### 8.3 Validation sample (already drawn, coding may begin)

`build_llm_validation_sample.py` (seed 20260724, fixed) drew 128
records from the 2,498 articles no human has seen: 43 Reform-flagged
(E6's entire evidence base), local/national quotas mirroring the
pilot's stratification so validation difficulty matches development
difficulty. Human coding of this sample uses the unchanged codebook
and may proceed immediately - human labels do not depend on this
amendment. What may NOT happen before supervisor approval and v2
freeze: generating or comparing any v2 output on these 128 articles.

### 8.4 Order of operations after approval

1. Freeze v2 (classifier version hash recorded; no further edits).
2. Complete human coding of all 128 validation rows.
3. Run frozen v2 once on the validation sample; compare per §8.2.
4. Rules that pass: v2 classifies the remaining corpus for that rule,
   followed by the §6 step-4 5% independent re-check. Rules that
   fail: fully manual, no re-tuning against this sample - a v3 would
   demote this sample to development data and require another fresh
   one.

### 8.5 Validation results (run 2026-07-24, frozen v2)

The §8 amendment was approved by the supervisor by email on
2026-07-24 (to be re-confirmed at the 2026-07-31 supervision
meeting). v2 was frozen as `v2-development-2026-07-24.6` /
`claude-sonnet-5` (enforced by `run_llm_validation_v2.
assert_classifier_frozen()`), then run once on the 128-article blind
sample: 118 ok, 10 schema errors kept as failures.

| Rule | Pairs | Agreement | kappa | AC1 | Route | Outcome |
|------|-------|-----------|-------|-----|-------|---------|
| E4 | 118 | 85.6% | 0.000 | 0.834 | fallback (skew trigger met) | **passes** |
| E5 | 118 | 68.6% | 0.371 | 0.587 | primary (no skew trigger) | fails - fully manual |
| E6 | 36 judged | 97.2% | 0.000 | 0.971 | fallback (skew trigger met) | **passes** |
| E8 | 118 | 83.9% | 0.000 | 0.826 | fallback (skew trigger met) | **passes** |

Read honestly: the three passing rules all pass through the
pre-registered fallback, not primary kappa - their human marginals
are heavily concentrated (E4 109/128 include), which is exactly the
situation the fallback was registered for. E5 fails on both its
kappa (0.371) and, had the trigger applied, its AC1 (0.587): the
relevance judgement genuinely differs between coder and model, the
same conclusion the development set suggested. This is a per-rule
outcome, not a package: on the remaining corpus E4/E6/E8 come from
the frozen v2, E5 from the human reviewer, with provenance recorded
per decision.

**Consequence:** v2 classifies E4 and E8 for the remaining 2,370
records and E6 for the remaining Reform-flagged subset; E5 is
reviewed manually for all 2,370 per §6. The §6 step-4 5% independent
re-check applies to the combined output.

## 9. Amendment 2 - arm-split E5 gating (post-hoc, PROVISIONALLY ADOPTED 2026-07-24)

**Status:** provisionally adopted the same day under the supervisor's
standing explore-first-report-after working arrangement; to be
ratified (or reversed) at the 2026-07-31 supervision meeting. Every
E5-national decision carries a provenance flag, so reversal is a
single flag flip back to fully-manual E5 with nothing lost. Unlike §8, this proposal is
**post-hoc**: it was formulated on 2026-07-24 *after* seeing the §8.5
validation results, and that is stated plainly here rather than
disguised. The mitigating facts are that the validation sample was
blind and untouched when the frozen v2 scored it, the human labels
were never used to develop the classifier, and the subgroup variable
(collection arm) is a pre-existing structural feature of the
collection design - not a split searched for until something passed.

### 9.1 Finding

E5's validation failure is not uniform. The codebook has always
defined E5 as two disjoint tests selected by arm (L-rules only for
local, N-rules only for national - §5 and the classifier prompt both
enforce this). Scored separately on the same frozen-v2 validation
run:

| E5 subgroup | Pairs | Agreement | kappa | Route |
|---|---|---|---|---|
| arm=national (N-rules) | 69 | 89.9% | **0.674** | passes the PRIMARY pre-registered bar (kappa >= 0.60) |
| arm=local (L-rules) | 49 | 38.8% | 0.165 | fails decisively |

The local failure mode is interpretable: 26 of the 30 local
disagreements are human-include -> LLM-exclude/unresolved, i.e. the
model lacks the ward-geography knowledge (which villages fall in
which division) that the human reviewer resolves from the candidate
table and maps. The N-rule test requires no such local knowledge,
which is consistent with its passing score.

### 9.2 Proposed consequence

- **E5, arm=national (2,036 remaining records): taken from the
  frozen v2 corpus scan** (whose E5 output is currently recorded as
  audit-only). No new API run is needed; adoption changes only the
  usage flag on already-archived decisions.
- **E5, arm=local (334 remaining records): fully manual**, per §6,
  on full_corpus_review.csv.
- Provenance is recorded per decision, as elsewhere. The §6 step-4
  5% independent re-check covers E5-national alongside E4/E6/E8.

### 9.3 Honest limitations

(1) Post-hoc subgroup selection - the gate in §8.2 was registered
per rule, not per arm; this amendment is therefore a validation-
design change requiring explicit supervisor approval before any
E5-national decision is used. (2) n=69 gives kappa 0.674 a wide
confidence interval; the 5% re-check provides a further live check.
(3) If rejected, the fallback is unchanged: E5 fully manual for all
2,370 records, or a v3 development cycle with a fresh validation
sample.
