# D4 validation gate - outcome and consequent decisions

Decided 2026-07-29, after the gate ran and before any full-corpus
extraction was submitted. This document is the record the final report
cites for which extraction layers appear in the model and why the rest
do not. Every experiment behind these decisions, including the two that
were superseded, is recorded with its numbers in `d4_findings_log.md`.

## 1. What was run

The D4 gate (decision D4 in `phase6_research_decisions_v1.md`) compares
the frozen extraction layers against a human gold standard on a
stratified 60-article sample drawn disjoint from the 67-article pilot
(`build_d4_sample.py`, sha256 ordering, election x arm quotas, Reform UK
topped up from 2 to 10).

Both a frozen `claude-sonnet-5` arm and a `claude-haiku-4-5` arm sat the
same exam against the same gold labels - the second arm exists because
Haiku's batch price is half Sonnet's introductory rate, and the model
choice is only defensible if the cheaper model clears the identical
pre-registered bar. Haiku has no adaptive thinking, so that arm ran with
a fixed 4,000-token thinking budget; prompts, validators, articles and
`max_tokens` were identical. Combined API cost: about $8 at batch
pricing.

Gate rule, unchanged from the eligibility protocol's approved section
8.2: Cohen's kappa >= 0.60, with Gwet's AC1 >= 0.60 plus percent
agreement >= 80% as a fallback only where a marginal is >= 90% and
kappa is therefore prevalence-broken.

## 2. Two scoring faults found and corrected before judging

Both faults were mine, in the D4 labelling instructions, not in the
extraction layers. Both were corrected in `compare_d4_agreement.py`
with the correction disclosed in the report output.

**Attribution.** The labelling sheet told the reviewer to record the
single principal attribution. `credit_blame.py` never instructs the
model to rank or order multiple attributions, so scoring the model's
first-listed attribution against the human's principal one tested a
rule only one side had been given. Corrected to set membership: the
human's type counts as agreement if it appears anywhere in that
article's attributions.

**Stance.** The labelling sheet said a bare candidate-list appearance
still counts as `neutral`. `stance_classification.py` rule 5 says the
opposite - "an entity mentioned without any evaluative representation
gets NO row", i.e. `not_mentioned`. The two specifications contradicted
each other and the human labels were collected under the wrong one.
Since the collected data cannot separate "evaluatively neutral" from
"named without evaluation" after the fact, both categories are
collapsed into one on both sides for scoring. The uncollapsed figure is
retained in the report as `raw_uncollapsed`.

## 3. Results

| Field | Sonnet kappa | Haiku kappa | Outcome |
|---|---|---|---|
| primary_issue | 0.641 | 0.729 | **passes** on both arms |
| attribution_type | 0.531 | 0.600 | **passes on Haiku only** |
| stance_per_party | 0.490 | 0.482 | fails both |
| frame_category | 0.407 | 0.483 | fails both |
| consequence_direction | 0.251 | 0.202 | fails both |
| impact_horizon | 0.229 | 0.184 | fails both |

Neither arm passes all six, so the gate's verdict is FAIL and the
full-corpus extraction does not proceed as originally scoped. Haiku
clears one more field than Sonnet at half the price.

Read honestly: the three worst-scoring fields are the three most
interpretive. `frame_category` is a 16-way judgement of narrative
framing; `consequence_direction` asks whether an article implies an
electoral consequence at all, which is a threshold judgement rather
than a categorisation; `impact_horizon` asks how long an effect
persists. Agreement in the 0.2-0.5 band on tasks of that kind is
ordinary in content analysis, and diagnosis of the residual
disagreements (after the two scoring faults above were removed) found
genuine coder-model disagreement rather than a further specification
bug: on `impact_horizon`, only 9 of 37 disagreements were between
adjacent categories, so they are not a granularity artefact.

## 3b. A second ruler: inter-model reliability

The section 3 verdicts rest on a single-pass human coding that was never
itself checked for reproducibility. The eligibility protocol does check -
it blind re-coded 34 of its 168 pilot articles and reported human-to-human
kappa (1.000 / 0.922 / 1.000 / 1.000) before comparing any LLM output.
**D4 skipped that step.** Two of the six fields also turned out to have
been scored against instructions that contradicted the extraction prompts
outright (section 2). A low human-machine kappa therefore cannot be
attributed to the model on its own evidence: it may equally reflect an
unstable or differently-scoped human construct.

Rather than add a second round of coding from the same coder - which
would add another uncertain measurement rather than resolve the first -
the two arms already run on the same 60 articles were compared against
each other. This asks a different question, and for a feature applied
uniformly to 3,584 articles a more directly relevant one: is the field
measured *reproducibly*? It needs no human input and was free.

| Field | vs human (best arm) | Sonnet vs Haiku |
|---|---|---|
| primary_issue | 0.729 pass | **0.798 pass** |
| attribution_type | 0.600 pass | **0.670 pass** |
| consequence_direction | 0.251 fail | **0.647 pass** |
| frame_category | 0.483 fail | 0.502 fail |
| impact_horizon | 0.229 fail | 0.339 fail |
| stance_per_party | 0.490 fail | 0.316 fail |

Two readings follow, and they are different in kind.

**`consequence_direction` is reproducible but construct-divergent.** Two
independently prompted models agree with each other at 0.647 while both
disagree with the human coding at around 0.2. That pattern is not an
unreliable instrument; it is a stable instrument measuring something the
human coder scoped differently. Inspection of the stance disagreements
found the same shape: an article reporting a party's heavy electoral
defeat was coded `negative` by both models - the article represents that
party unfavourably - and `neutral` by the reviewer, who read factual
reporting of an unfavourable outcome as carrying no editorial stance.
Both readings are defensible and the schema never resolved which it
meant. For the research question, which is about coverage that makes a
party look bad, the models' reading is arguably the construct-valid one.

**stance, framing and horizon fail both rulers.** The models disagree
with each other as well as with the human. No repair recovered them: two
scoring faults were fixed (section 2) and a coarsened re-test was run
(`test_coarsened_agreement.py` - one pre-stated collapse per field,
chosen for what the modelling needs, disclosed as post-hoc), and all
three still failed. Their exclusion rests on three independent attempts
rather than on one disagreement with one coder.

Adopting `consequence_direction` on reproducibility means its construct
is what the extractor measures, not what a human coder would call an
electoral implication. That is a legitimate position for a feature
applied at scale, and it is stated here so the report can state it too -
it is not a silent substitution.

## 4. Decisions taken

**D4a - four layers are adopted, two are excluded, one is undetermined.**
Revised twice: after section 3b, and again after the stance redesign
recorded in `d4_findings_log.md` experiment 6. `primary_issue` and
`attribution_type` enter feature engineering on both rulers.
`consequence_direction` enters on reproducibility alone, with its construct
divergence from the human coding documented rather than hidden. `stance`
enters through a **revised layer** that clears both rulers (0.848
inter-model, 0.741 human) after the original failed both - reported as
recovery at reduced granularity, never as if the original had passed.
`framing` enters
in part: a revised layer asking four independent binary presence questions
recovered two of its four frames (incumbent_judgement 0.705, local_impact
0.635 between arms), while `challenger_emergence` and `voter_discontent`
are `undetermined_insufficient_positives` - detected in 2-6 of 55 articles,
so their agreement rests on articles where both arms said absent.
`impact_horizon` is marked `excluded_not_validated`, having failed the
human comparison, the inter-model comparison, and a coarsened re-test.

The framing result carries the gate's sharpest limitation:
`challenger_emergence` is the frame closest to the thesis - Reform UK is
the insurgent under study - and it is the one the 60-article sample cannot
validate. A Reform-enriched draw would settle it cheaply, and that is
recorded as outstanding work rather than treated as a closed question. Consistent with the
project's practice everywhere else, the extracted values are not
deleted - they are retained, labelled, and simply not admitted to the
feature matrix, so the exclusion is reversible if a later revision
validates them.

*Why not revise the definitions and re-run instead:* that would mean a
new codebook, a fresh validation sample and another batch cycle for the
three most interpretive fields, while corpus freeze, the 366-article
tranche, full extraction, news modelling and the report all wait behind
it. The Sonnet introductory price also expires 2026-08-31. The
opportunity cost is not justified by three fields whose signal is
partly recoverable (below).

**D4b - blame/credit substitutes for sentiment.** Losing
`stance_per_party` costs the per-party sentiment counts and net
sentiment that the supervisor's own brief lists. The revised stance layer
recovers direction at three levels, so per-party favourable and
unfavourable counts return - but not intensity, and not `mixed` as a
category. `attribution_type` and `consequence_direction` remain as
independent tonal signals alongside it. The report must state that the
sentiment features are three-level portrayal counts from a redesigned
layer, not the five-level scale the brief envisaged.

**D4c - Haiku 4.5 becomes the extraction model.** It clears both
human-scored adopted fields where Sonnet clears one, and the reform_uk
`applicable` flag besides, at half the price. Four of the eight layers
are extracted (issues, credit-blame, consequence, and the revised stance
layer), so the full-corpus cost is roughly $90-110 rather than $229 - the
excluded layers are not run at all rather than run and discarded.

**D4d - the reform_uk sub-field block is validated separately before it
is used.** That block sits inside the consequence layer's schema but is
structurally independent of `consequence_direction` (a sibling property,
not derived from it), so failing that field does not automatically
disqualify it. It has never been validated: the D4 gold labels cover the
six comparison fields only, and `stance_reform_uk` belongs to the failed
stance layer, not to this block. Until the separate validation in
section 5 runs, the block's status is *untested* - neither passed nor
failed - and it is not used.

## 5. reform_uk sub-field validation - result

Ran 2026-07-30 on the 22-article blind sample. **Haiku's `applicable`
judgement passes on the primary route: kappa 0.680, 86.4% agreement over
all 22 pairs.** Sonnet's does not (kappa 0.288). So "is this article
materially about Reform UK" is a reliable machine judgement on the
cheaper model - a validated Reform-relevance flag, independent of the
E6 keyword disambiguation that already exists at the eligibility stage.

The five sub-fields beneath it are **undetermined, not failed**. They are
scored only where both sides say `applicable`, because the schema forces
them empty otherwise (rule E4) - and the reviewer marked just 5 of the 22
articles applicable, so that intersection is five pairs. At five pairs a
single disagreement moves kappa by roughly 0.2, so neither verdict
carries information. Recording them as failures would overstate the
evidence exactly as much as recording them as passes. The threshold used
(20 pairs, the smallest subset this project has previously accepted a
verdict on, rounded down) was written after seeing that the subset was
five; that ordering is disclosed in `compare_reform_subfields.py` rather
than hidden.

Consequence: the `applicable` flag is adopted. The five sub-fields stay
unused, labelled `undetermined_insufficient_sample` rather than
`excluded_not_validated`, because the distinction matters - they can be
validated later by drawing a sample enriched for Reform-applicable
articles instead of a general one, which is a cheap fix if the modelling
stage turns out to need them.

## 5b. How the original section 5 plan was executed

`D4_ReformUK_Subfields_Labelling.xlsx` presents 22 articles - the 14 the
model marked `applicable` plus 8 controls it marked not applicable,
hash-shuffled and carrying no model output, so the sheet is blind.
Controls are included deliberately: scoring only the positives would
give the human an all-yes column, a constant marginal, and a kappa that
collapses regardless of true agreement - the prevalence problem recorded
in `eligibility_manual_review_methodology.md` section 8.1.

Six fields are coded: `applicable`, `growth_suggested`,
`credible_challenger`, `established_support_affected`,
`switching_directions`, `signal_nature`. The same gate applies. If it
passes, Reform-specific coverage features are retained and the block is
extracted alongside the two adopted layers; if it fails, it joins the
excluded set and the Reform signal is carried by article counts, E6
disambiguation and blame/credit attribution only.

## 6. What this costs the research question

The news layer can still measure coverage volume, issue composition,
local/national split, source counts, recency weighting, duplicate-
adjusted counts, Reform mention counts, and - through blame and credit -
a coarse tonal direction. It cannot measure five-level per-party
sentiment, narrative framing, mechanism-level electoral signals, or
effect duration. The central comparison (does news improve prediction of
Reform UK vote share over an election-history baseline) remains
answerable; the tonal half of it is answered at lower resolution than
the brief envisaged, and that limitation is a finding to report rather
than a gap to paper over.
