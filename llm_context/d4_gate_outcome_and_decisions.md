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

## 4b. Decisions revised after the validator-gating fault

Everything in section 4 was decided on kappas computed without checking
whether each record passed its own validator. `d4_findings_log.md`
Experiment 8 found that fault and recomputed. Three of the four decisions
above change, and they are revised here rather than edited in place, because
the sequence is part of the evidence.

**D4a is revised: attribution and consequence leave the adopted set.**

| field | figure D4a relied on | validator-gated figure | n |
|---|---|---|---|
| primary_issue | 0.729 human (Haiku) | **0.616** (Sonnet), 0.602 (Haiku) | 53 |
| attribution_type | 0.600 human (Haiku) - "passes" | **0.521** (Sonnet), 0.516 (Haiku) | 57 |
| consequence_direction | 0.647 inter-model | **0.587** inter-model; 0.259 / 0.136 human | 55 |

`primary_issue` survives on both rulers and is the only original layer that
does. `attribution_type` is now `excluded_failed_gate`: both arms fail, on a
near-complete Sonnet sample (3 of 60 records rejected), and the fallback
route does not trigger at a largest marginal of 0.579. `consequence_direction`
is `excluded_failed_gate` in its frozen form; its redesign is at 4c below.

D4a's original clause that `consequence_direction` "enters on reproducibility
alone" is withdrawn. It rested on an inter-model figure of 0.647 that has
since fallen to 0.587, below the bar, and on a reading of the two rulers that
section 4c revisits.

**D4c is revised: the extraction model is chosen per layer, not once.** D4c
adopted Haiku throughout, on the strength of attribution at 0.600 and
reform-applicable at 0.680. Attribution's 0.600 did not survive the
recomputation. Measured directly on the same 60 articles, Haiku satisfies the
verbatim-span contract on 333 of 582 spans (57.2%) against Sonnet's 618 of
622 (99.4%), which the validator turns into a third of every original layer's
records being discarded. So:

| layer | model | measured reason |
|---|---|---|
| issues | `claude-sonnet-5` | span fidelity 99.4% against 57.2%; verified again on the narrow tranche at 327/327 |
| stance revised | `claude-haiku-4-5` | no span requirement; 56/57 and 34/34 clean; 0.741 human against Sonnet's 0.736 |
| framing revised | `claude-haiku-4-5` | no span requirement; format failure 0-1% against Sonnet's 8.3% (5 of 60) |

The cost consequence is smaller than the correctness one: the two revised
layers on Haiku rather than Sonnet is a difference of about $9 over 1,632
articles. The split is not a price decision.

**D4d stands unchanged.** The reform_uk block's validation in section 5 did
not depend on the gated fields.

## 4c. The redesign of the consequence layer, and its outcome

**Why a redesign was attempted at all.** The disagreement was tabulated
before it was attributed (`d4_findings_log.md` Experiment 9). Eighteen of the
twenty-six human-model disagreements sat in a single cell - the reviewer
recording no consequence where the model found one - and the two models
agreed with each other far better than either agreed with the reviewer
(0.587 against 0.259 and 0.136). That is the signature of a definitional gap,
and it is the pattern the stance layer showed before its redesign.

**Result, Haiku arm, n=60:** presence kappa **0.598**, agreement 0.850, AC1
0.763, largest marginal 0.817. The frozen layer on the identical test scores
0.318 at n=29. Validator rejections fell from 31 of 60 to 0.

**The layer does not pass.** 0.598 against a 0.600 bar. The fallback route's
two conditions are satisfied - AC1 0.763 and agreement 85% - but its trigger
requires a marginal at or above 0.90 and the largest is 0.817. The trigger
exists so that AC1 cannot be reached for whenever kappa is inconvenient, and
this is the case it was written for. The secondary direction test returns
kappa 1.000 on 5 pairs, which is not evidence at that n.

The Sonnet arm was submitted at the same time and, when this paragraph was
written, had not yet reported. Both arms and the scoring rule were declared
before either was scored; the verdict is per-arm, as it is for every other
layer. The paragraph is kept as written for chronology; the Sonnet outcome
is recorded below.

**Two arms are two attempts at the bar, and for this layer alone that
matters. Recorded before the second arm reports, so that the handling is not
chosen after seeing its figure.** Everywhere else the two-arm design carries
no selection effect, because both arms land on the same side of the line:
`primary_issue` clears on both (0.616 and 0.602), revised stance clears on
both (0.736 and 0.741), and `impact_horizon` fails on both (0.186 and 0.146).
Consequence is the only layer where one arm fails and the other could pass,
so it is the only place where "whichever arm clears its own gate" amounts to
two chances at a 0.60 threshold rather than one.

The rule, therefore:

* If the Sonnet arm clears **comfortably** - kappa at or above 0.65, a tenth
  clear of the bar and of the boundary the Haiku arm sat on - the layer is
  adopted on that arm, with the split arms noted.
* If it clears **marginally** - anywhere in 0.600 to 0.649 - the layer is
  adopted but its three features are marked secondary: they enter the
  robustness specifications and not the primary news specification, and the
  report states that the layer rests on one of two arms at the boundary.
  Adopting a boundary result on the second attempt and then presenting it
  beside stance's 0.741 as if the evidence were comparable would misrepresent
  what was measured.
* If it **fails**, the layer is dropped and the redesign is recorded as an
  instructive near miss: it closed the diagnosed gap and still did not reach
  the bar, which is a finding about the construct rather than about the
  prompt.

**Outcome: the third clause applies. Sonnet returned presence kappa 0.598,
the same figure as Haiku to three decimal places, at the same 85% agreement.
The consequence layer is dropped and its three features are `unavailable`.**

The replication is worth stating because it is the strongest evidence this
project has for the possibility the reviewer's coding, not the model's, is the
looser side - and it does not change the decision. Two models on different
thinking configurations and price tiers agreed with each other on 89% of
presence judgements (kappa 0.889, up from the frozen layer's 0.587) with
near-identical marginals, 49 of 60 "none" on both arms, and both sat at 0.598
against the reviewer's 42 of 60. The residual disagreement is therefore
systematic and replicated rather than sampling noise.

It still does not license adoption. Two models sharing training data and one
prompt are not independent coders, so their agreement measures reproducibility
and not validity; the gate is human-referenced by pre-registration; and the
reviewer's own test-retest reliability on this field was never measured, so
the human side cannot be shown to be wrong either. What the evidence supports
is that **neither side can be demonstrated correct**, and a feature whose
construct validity cannot be demonstrated in either direction is the case the
gate exists to catch.

Two arms were two attempts at one bar, and both missed. That removes the
multiple-comparison concern this pre-statement was written to handle, and it
also means no arm-selection was performed.

**A sensitivity specification is left open rather than built, and the reason
is recorded here so the option is not lost.** The 0.60 bar is a convention -
`llm_v2_feasibility_plan.md` §D3 records that the supervisor requirement does
not itself specify kappa or 0.60, and the figure comes from the conventional
reading of Cohen's kappa in which 0.61 and above is substantial agreement. A
layer sitting 0.002 below a conventional bar is exactly the case where the
honest move is to show what the conclusion rests on rather than to argue about
the third decimal place.

So the plan, if the primary result turns out to need it: fit the news
comparison twice, once on the 20 features that cleared the gate and once with
the three consequence features added, and report both. If the conclusion is
unchanged, it does not depend on where the line was drawn, which is a
robustness result worth having. If the conclusion changes, then most of the
news signal sits in a layer whose construct validity is contested, and that is
a finding the report must state rather than route around. Either outcome is
reportable, which is what separates a sensitivity analysis from choosing the
answer one prefers: both figures are published whichever way they fall.

It is not built now, for two reasons. The machinery would be speculative -
at model-fitting time the change is three additional columns and a second fit,
not a new status system, and it is better done with real coefficients in hand.
And it is not free: the consequence layer was excluded from the corpus
extraction, so those three features have no data behind them, and running the
sensitivity specification requires extracting that layer over the full corpus.
Committing to that before the primary result is known would be paying for a
robustness check on a question that may not arise. Deferring costs only a
later batch cycle, and the decision is revisited once the primary comparison
has a number.

**Attribution's redesign was run and the layer is excluded.** The design
was the framing redesign's, applied mechanically: two independent binary
questions - does the article blame a named party, does it credit one - under
which both-yes is `mixed`, both-no is `none`, the 14% of human labels using
`mixed`/`unclear` stop being unmatchable, and the "which attribution is
principal" rule that only the human side received disappears. Both arms ran
(`attribution_rescue_agreement.json`): blame fails the gate on both models
(kappa 0.272 Sonnet, 0.319 Haiku, against 0.600), and credit is
undetermined because the validation sample holds only 8 human positives
against the pre-declared minimum of 10. Neither binary clears, so the whole
attribution layer is excluded from the feature set. No third attempt was
made: the scoring rule was declared before submission and the pre-statement
allows no further scoring variant, which is what keeps this a validation
verdict rather than a prompt tuned against its own validation sample.

**Why the gate was not switched to inter-model agreement.** Raised directly,
since four of six fields score higher on that ruler. Not adopted, for three
reasons. The two rulers do not rank the layers the same way - the original
stance layer scores 0.291 inter-model against 0.490 and 0.537 human, the
reverse of consequence's pattern - so choosing per layer whichever ruler is
kinder is selection on the outcome. Two LLMs are not independent coders: they
share training data and read the same prompt, so agreement produced by a
shared vague instruction is not two readings converging on the truth.
Inter-model agreement measures reproducibility; the gate is asked for
validity. And decisively, the redesigns that worked cleared both rulers -
stance revised at 0.848 inter-model and 0.741 human - so a layer clearing one
and failing the other is reporting a broken definition, and the definition is
what gets fixed. Experiment 10 moved the human figure from 0.318 to 0.598
with the ruler unchanged.

The human side's own reliability on these six fields is unmeasured, and that
is recorded as a limitation of the study rather than as a resolved question.
The eligibility layer was blind re-coded at kappa 0.922-1.000 on 34 articles;
the D4 content fields never were.

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
five; that ordering was disclosed in the comparison script (retired from main
with the sub-field addendum; in Git history) rather than hidden.

Consequence: the `applicable` flag is adopted. The five sub-fields stay
unused, labelled `undetermined_insufficient_sample` rather than
`excluded_not_validated`, because the distinction matters - they can be
validated later by drawing a sample enriched for Reform-applicable
articles instead of a general one, which is a cheap fix if the modelling
stage turns out to need them. (Final status: the full-corpus run excluded
the consequence layer that hosts this block, so the flag was never
extracted at scale; production Reform features use the deterministic
mention indicator, and the addendum's scripts and scorecards are retired
from main into Git history.)

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
adjusted counts, Reform relevance and mention counts, three-level
per-party portrayal through the revised stance layer, and two narrative
frames - whether the article judges the incumbent's record, and whether
it frames matters through local consequences. It cannot measure blame
and credit attribution, five-level sentiment intensity, effect duration,
the challenger-emergence or voter-discontent frames, or the Reform
sub-signals. The central comparison (does news improve prediction of
Reform UK vote share over an election-history baseline) remains
answerable; the tonal half of it is answered at lower resolution than
the brief envisaged, and that limitation is a finding to report rather
than a gap to paper over.
