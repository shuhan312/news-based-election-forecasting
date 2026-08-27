# LLM Eligibility Classifier v2 — Development and Supervisor Decision Plan

> **Historical pre-freeze plan.** The v2 classifier this plan proposes was
> subsequently validated blind on the fresh 128-article sample, approved,
> and frozen as the production classifier used in final corpus assembly
> (`src/news_collection/llm_classifier_v2.py`).

**Status:** development-only feasibility plan

**Date:** 2026-07-24

**Does this amend the research protocol?** No

**May it be applied to the remaining corpus?** No

This document records a proposed response to the first LLM eligibility
pilot. It preserves the v1 outputs and does not change the current formal
go/no-go conclusion in `eligibility_manual_review_methodology.md`. Any
adoption requires supervisor agreement, a dated protocol deviation/version
change, a frozen classifier, and an independent validation sample.

## 1. Research question and supervisor alignment

The supervisor's primary question is whether pre-election news context
improves prediction of election outcomes beyond prior election results. The
supervisor requirement further specifies:

- separate local, national, and combined-news analyses;
- manual removal of search hits where *reform* does not mean Reform UK;
- linkage of local articles to a ward, town, candidate, or council issue;
- full publisher text where lawfully and practically available;
- supporting passages for important classifications;
- article-, party-, candidate-, and Reform-specific context variables.

E4/E5/E6/E8 are an **eligibility gate**, not the requested context analysis
itself. A publishable workflow therefore has two distinct validation
problems:

1. **Eligibility validity:** which articles may enter the analysis?
2. **Context-extraction validity:** are topic, geography, parties,
   candidates, blame/credit, switching, and new-party-emergence variables
   extracted accurately?

Passing the first does not establish the second.

## 2. Observed v1 results

The 168-article human pilot and 34-article blind human recheck are complete.
Human-to-human agreement cleared the internally specified 0.60 kappa
threshold for every rule:

| Rule | Human recheck agreement | Cohen's kappa |
|---|---:|---:|
| E4 | 100.0% | 1.000 |
| E5 | 97.1% | 0.922 |
| E6 | 100.0% | 1.000 |
| E8 | 100.0% | 1.000 |

The v1 LLM-to-human comparison was:

| Rule | Agreement | Cohen's kappa | v1 protocol outcome |
|---|---:|---:|---|
| E4 | 86.9% | 0.141 | below threshold |
| E5 | 52.4% | 0.191 | below threshold |
| E6 | 97.6% | 0.929 | above threshold |
| E8 | 81.0% | 0.279 | below threshold |

These figures remain the historical v1 result. They must not be replaced by
post-hoc corrected values.

## 3. Why v1 is a development baseline, not a clean final validation

### 3.1 The model did not receive the complete operational codebook

V1 generated a prompt from `REASON_CODES`, which contains code names and
decision polarities but not the definitions in the human codebook. This is
especially consequential for E5. A label such as
`E5-L3-COUNCIL-ISSUE` does not communicate the requirements that the issue
be a Surrey council matter and identifiably affect the sampled area.

### 3.2 E5 was not constrained by collection arm

The supervisor's design distinguishes local and national news. V1 exposed
both L- and N-codes without expressly prohibiting national criteria on a
local record or local criteria on a national record. Observed disagreements
confirm that this happened.

### 3.3 Human and model inputs were not equivalent

The model received a 1,500-character spreadsheet excerpt. Human reviewers
could open the full-text path. In the 168-article set:

- 145 excerpts are marked as truncated;
- 156 records have an existing full-text file;
- at least seven E5 hard disagreements rely on human evidence found only
  beyond the model's excerpt.

This does not explain all E5 disagreement, but it prevents the comparison
from isolating judgement quality from input availability.

### 3.4 Parse success was treated as schema validity

Eight v1 rows marked `status=ok` contain at least one decision value that is
actually a reason code. The comparison script treated those strings as new
categories. A publishable classifier must distinguish:

- transport/API completion;
- JSON parse success;
- schema validity;
- codebook consistency;
- substantive classification.

### 3.5 Metric prevalence

E4 and E8 have highly concentrated human marginals. Cohen's kappa can be low
despite high observed agreement under such prevalence. Gwet's AC1 was
developed as a more stable chance-corrected alternative in high-agreement
settings:

> Gwet, K. L. (2008). Computing inter-rater reliability and its variance in
> the presence of high agreement. *British Journal of Mathematical and
> Statistical Psychology, 61*, 29–48.
> https://doi.org/10.1348/000711006X126600

Metric selection must nevertheless be specified before a new validation
result is examined. Selecting AC1 only after seeing an unfavourable kappa
would be outcome-dependent analysis.

## 4. v2 technical design

The development implementation is deliberately separated from v1:

- `src/news_collection/llm_classifier_v2.py`
- `src/news_collection/llm_v2_io.py` (shared frozen validation/production I/O)
- `tests/test_llm_classifier_v2.py`

The development-only sequential runner was removed from final main after the
classifier was frozen; its implementation and smoke outputs remain in Git
history. The blind validation and production batches use `llm_v2_io.py`.

### 4.1 Complete machine-readable criteria

`manual_review_schema.py` now contains:

- `REASON_CODES`: legal code and decision polarity;
- `REASON_CODE_DEFINITIONS`: operational prose;
- `RULE_DEFINITIONS`: rule purpose.

The definitions do not change a polarity. Editing them before formal
validation would be a codebook/prompt version change and must be recorded.

### 4.2 Structured response

V2 uses the Claude Messages API `output_config.format` JSON-schema
interface. The schema constrains decisions and reason codes to separate legal
enums for the requested rule and arm, preventing a reason code from entering
the decision field. A development smoke test showed that encoding every
decision/code pair as nested schema branches exceeded the provider's compiled
grammar limit when all four rules applied. Polarity is therefore enforced by
the mandatory local validation layer, which rejects:

- unknown/missing/extra rules;
- missing/extra fields;
- invalid decisions or codes;
- decision/code polarity mismatch;
- E5 code from the wrong arm;
- missing evidence where evidence is required;
- confidence values inconsistent with decision state.

Refusal or `max_tokens` stops are failures even if some text was returned.

### 4.3 Arm-specific E5 decision tree

1. Read the fixed collection arm.
2. If local, apply only L1–L4.
3. If national, apply only N1–N3.
4. Apply the explicit arm-appropriate failure or uncertainty code.
5. Use `insufficient_evidence` only when input limitations prevent the
   arm-appropriate test.

Originating ward, query, query family, and geographic scope are included.

### 4.4 Input parity

The development runner (since removed from the final `main`; it remains in the
commit history) reads `article_text_path` when available. The stored
excerpt is an explicit fallback and `text_source` is recorded. Input,
complete prompt, schema, model, version, and requested-rule hashes prevent
silent mixing or reuse.

### 4.5 Reproducibility and raw audit

For every attempted response the runner archives:

- classifier/model/version;
- input, prompt, and schema hashes;
- requested rules;
- API response ID;
- stop reason and token usage;
- raw response text;
- final status and error note.

V1 files are never overwritten.

### 4.6 Real-API smoke test

A five-record smoke set was fixed from the existing development sample before
any v2 output was inspected. It covers a local article, a national policy
article, a Reform-flagged article, an excerpt-only fallback and a readable
national exclusion. The smoke output is stored separately from both v1 and
the possible 168-record v2 development run.

The transport-development history on 2026-07-24 was:

| Classifier version | Operational outcome | Interpretation |
|---|---|---|
| initial v2 | 0/5 requests accepted | The current model rejected the deprecated `temperature` parameter. No classification was produced. |
| `v2-development-2026-07-24.1` | 4/5 successful | The Reform record, for which all four rules apply, exceeded the provider's compiled-grammar limit under the nested decision/code schema. |
| `v2-development-2026-07-24.2` | 0/5 requests accepted | The provider rejected the first nullable-confidence schema representation before generation. |
| `v2-development-2026-07-24.3` | 5/5 passed the then-current checks | Separate decision/code enums plus mandatory local polarity validation completed for all five records. A subsequent audit found that the evidence check established only non-empty text, not a verbatim source passage. |
| versions `.4`–`.5` | 4/5 passed each stricter run | Verbatim-substring validation correctly rejected first an ellipsis-shortened quote and then a headline used in place of article-body evidence. Both failures were preserved rather than repaired after the fact. |
| `v2-development-2026-07-24.6` | **5/5 successful** | All five completed under the final smoke-test contract, including verbatim evidence drawn from the article-text block. |

The final run exercised four full-text inputs, one explicit excerpt fallback,
both E5 arms, an E5 exclusion and conditional E6 classification. Every final
response ended normally, passed the JSON schema, used a verbatim body-text
passage where evidence was required and passed all local codebook-consistency
checks. These five purposively selected records establish only that the v2
pipeline operates end to end. They are not an accuracy estimate, an agreement
statistic or independent validation.

## 5. What may be done before the supervisor meeting

The following are exploratory development and do not consume an independent
validation sample:

1. Unit-test schema, validation, input loading, and audit behaviour.
2. Produce a transparent E5 disagreement taxonomy from the 168 records.
3. Draft a deterministic E5 decision tree.
4. Select possible boundary examples for discussion.
5. Run v2 on the 168 development articles, if API access and cost permit.
6. Report any v2 agreement only as **development-set diagnostic**.
7. Preserve every prompt version and run, including worse versions.

The following should not happen before approval:

- apply v2 decisions to the remaining corpus;
- call development performance independent validation;
- alter the official metric or threshold;
- claim E6 satisfies the supervisor's literal manual-removal requirement;
- inspect human labels for a newly drawn validation sample before v2 is
  frozen;
- tune v2 on a new validation sample after seeing its result.

## 6. Decisions required from the supervisor

### D1. What counts as manual Reform disambiguation?

Choose one:

1. **Fully human:** every Reform-query hit is manually confirmed.
2. **Hybrid (recommended for discussion):** the LLM recommends; all
   exclusions/uncertainties and a risk-based sample of includes are checked
   by a human.
3. **Validated automation:** the LLM decision is used after an agreed
   independent validation gate.

The current wording most directly supports option 1. Options 2–3 need
explicit approval.

### D2. May the 168 records become a development set?

Recommended answer: yes, with complete disclosure, followed by a new frozen
validation. The alternative is to keep v1 as the only formal evaluation and
leave E4/E5/E8 manual.

### D3. What is the agreement/performance gate?

Pre-specify:

- primary statistic by prevalence condition;
- secondary statistics;
- confidence intervals;
- treatment of unresolved and invalid outputs;
- whether failure of one rule affects the others;
- whether a point estimate or lower confidence bound must exceed the gate.

The supervisor requirement does not itself specify kappa or 0.60. If these
were approved orally, that decision should be entered in the meeting log.

### D4. Is an E4 hybrid safety design acceptable?

Reviewing every non-include plus 10% of ordinary includes does not fully
protect against a leaked-results article incorrectly classified as include.
A stronger risk-based design reviews:

- all non-includes;
- polling-day/near-poll articles;
- live blogs and visibly updated pages;
- result/count/declaration/exit-poll keyword hits;
- a random sample of the remaining ordinary includes.

## 7. Proposed independent validation after approval

### 7.1 Freeze before sampling

Record:

- code commit;
- classifier and prompt version;
- exact model identifier and SDK version;
- JSON schema hash;
- decoding parameters;
- full-text/fallback rule;
- API/transport retry policy;
- evaluation code and thresholds.

### 7.2 Separate representative and challenge evidence

A single oversampled sample can distort prevalence-dependent agreement
statistics. A stronger design has two reported components:

1. **Representative stratified validation sample:** sampled across election,
   arm, source/route, and time band to estimate real-corpus performance.
2. **Rare/high-risk challenge set:** enriched for likely E4/E8 exclusions,
   thin text, Reform hits, live blogs, and close-to-polling-day records.

Do not pool the challenge set into the representative result without design
weights. Report it separately as sensitivity/stress-test evidence.

Sample size should be justified from desired precision and expected minority
cases rather than chosen solely as a round number. If approximately 100 is
the feasible human workload, report its limitations and confidence
intervals.

### 7.3 Blind coding and one-shot evaluation

- The human coder does not see v2 outputs.
- The frozen model is run once under the pre-specified transport-failure
  policy.
- No prompt change is evaluated on the same sample as a second attempt.
- If the classifier changes, draw a new validation sample.

### 7.4 Report more than one aggregate coefficient

For every rule report:

- full confusion matrix and category marginals;
- observed agreement;
- Cohen's kappa;
- AC1 where pre-specified;
- invalid/missing/refusal rate;
- include/exclude precision and recall;
- confidence intervals;
- performance by arm, election, source/route, text source, and time band
  where counts permit.

## 8. Context extraction is the next substantive research stage

Once eligibility treatment is approved, build a separate context schema
matching the supervisor requirement:

- event, place, primary/secondary issue;
- multi-label party and candidate mentions;
- praise, criticism, blame, credit, competence, integrity;
- controller of the relevant service/council;
- expected electoral beneficiary/damaged party;
- growth/decline/switching and switching direction;
- continuing-story and poll/prediction/result indicators;
- Reform headline/candidate/campaign/policy/threat/momentum/organisation;
- evidence passage for every important label.

That classifier requires its own labelled sample and metrics:

- entity/link extraction: precision, recall, F1;
- nominal categories: per-class metrics plus agreement;
- ordinal variables: weighted agreement;
- 0–1 relevance/credibility/momentum scores: error and reliability measures;
- evidence passages: human audit for textual support/entailment.

Eligibility agreement cannot be cited as validation of these downstream
variables.

## 9. Recommended immediate sequence

1. Complete and test the v2 development implementation.
2. Produce the E5 disagreement taxonomy.
3. Optionally run v2 on the existing 168 development records.
4. Prepare a two-page supervisor memo containing v1 results, v2 changes,
   workload implications, and decisions D1–D4.
5. Obtain and log the supervisor's decisions.
6. Amend/version the protocol if approved.
7. Freeze v2 and draw the independent validation sample.
8. Validate once.
9. Choose manual, hybrid, or automated handling separately by rule.
10. Only then classify the remaining corpus and begin validated context
    extraction.
