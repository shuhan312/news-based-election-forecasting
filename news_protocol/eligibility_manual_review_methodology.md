# Article Eligibility Manual Review - Methodology

Status as of 2026-07-23: **pilot infrastructure built, no articles
reviewed yet.** This document describes the design; it is not a record
of results, because there are none yet. Section 6 states exactly what
must happen before that changes.

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

## 7. Proposed LLM-assisted classification for the remaining corpus (not yet approved)

Manually reviewing all 2,666 `pending_human_review` records at the
same depth as the 168-record pilot is a large time cost. A validated,
disclosed LLM-assisted classification method is proposed as a way to
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
4. **This is not authorised to run for real yet.** No `ANTHROPIC_API_KEY`
   is configured in this environment (`llm_classifier.classify_article`
   fails closed with `status=not_configured` rather than fabricating a
   result - verified 2026-07-23 against all 168 pilot articles, all 168
   correctly produced no classification). The method is raised with the
   supervisor at the 2026-07-31 meeting before any real key is added or
   any real classification is produced. If approved, this section is
   updated with the decision and any conditions attached; if not
   approved, the full corpus is reviewed manually per §6 instead.
5. Even once approved and validated, an LLM classification never enters
   `is_eligible_for_downstream()`'s notion of eligibility directly - it
   is written to a separate file and only counts once a human has
   compared it against the gold standard and the agreement has cleared
   the bar in (3). There is no path by which an LLM output reaches the
   analysis corpus without a documented human validation step in
   between.
