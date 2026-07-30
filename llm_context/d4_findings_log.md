# D4 validation: every experiment run, and what each one showed

A complete record of the D4 gate and its follow-up experiments, written so
the final report can cite specific numbers rather than a summary, and so a
reader can see what was tried that did *not* work as well as what did.
Seven experiments, 2026-07-29 to 2026-07-30, total API spend about $14 at
batch pricing.

Findings are recorded in the order they happened, including the two that
were later superseded, because the sequence is itself part of the evidence:
two of the six failing verdicts turned out to be artefacts of how the exam
was written, and one turned out to be a design fault in the layer being
examined. A summary that showed only the final numbers would make the gate
look cleaner than it was.

---

## Experiment 1: the gate as originally specified

**What ran.** Six extraction layers scored against the reviewer's coding
of a stratified 60-article sample (`build_d4_sample.py`: election x arm
quotas, sha256 ordering, disjoint from the 67-article pilot, Reform UK
topped up from 2 to 10). Two model arms, `claude-sonnet-5` and
`claude-haiku-4-5`, on identical prompts, articles and `max_tokens`; the
Haiku arm ran a fixed 4,000-token thinking budget because it has no
adaptive thinking. Gate: Cohen's kappa >= 0.60, with the pre-registered
Gwet AC1 fallback where a marginal exceeds 90%. Cost about $8.

**Result.** Neither arm passed all six.

| Field | Sonnet | Haiku |
|---|---|---|
| primary_issue | 0.641 pass | 0.729 pass |
| attribution_type | 0.531 fail | 0.600 pass |
| stance_per_party | 0.490 fail | 0.482 fail |
| frame_category | 0.407 fail | 0.483 fail |
| consequence_direction | 0.251 fail | 0.202 fail |
| impact_horizon | 0.229 fail | 0.184 fail |

**Also recorded.** One `temporal` layer response failed to parse on the
Sonnet arm and is excluded from that field's pairs rather than counted as
disagreement (59 pairs, not 60). Haiku had no parse failures. Haiku's
`stance_negative` coarse kappa was later found to be *negative*
(-0.114), which is what prompted experiment 4.

---

## Experiment 2: two faults in the exam, not the layers

**What prompted it.** A negative kappa is unusual enough to be a signal
about the measurement rather than the thing measured, so the individual
disagreements were inspected rather than accepted.

**What was found.** Two of the six fields had been scored against
instructions that contradicted the extraction prompts. Both faults were in
the D4 labelling sheet, which I wrote.

*Attribution.* The sheet told the reviewer to record "the single principal
attribution". `credit_blame.py` never instructs the model to rank or order
multiple attributions, so comparing the model's first-listed attribution
against the human's principal one tested a rule only one side had been
given. Of 22 first-position mismatches, 5 would have matched at another
position.

*Stance.* The sheet said a bare candidate-list appearance still counts as
`neutral`. `stance_classification.py` rule 5 says the opposite: "an entity
mentioned without any evaluative representation gets NO row". The human
labels were collected under the wrong specification. Of 49 stance
disagreements, 26 were this mention-versus-not dispute rather than a
disagreement about direction.

**Corrections applied.** Attribution scored by set membership (the human's
type counts as agreement if it appears anywhere in that article's
attributions); stance scored with `neutral` and `not_mentioned` collapsed
into one category on both sides, with the uncollapsed figure retained in
the output as `raw_uncollapsed`.

**Result after correction.** attribution_type 0.531 -> 0.600 on Haiku
(crossing the bar), stance_per_party 0.482 -> 0.482 on Haiku and 0.490 ->
0.490 on Sonnet (unchanged; the collapse fixed the mention disputes but
the remaining direction disputes still failed). Two other fields moved
slightly. **The faults were real but only one verdict changed.**

---

## Experiment 3: coarsened granularity

**Why.** Dropping the four failing fields removes the tonal and mechanism
signals the research question is largely about, so a later null result
could not be told apart from "the retained features were too thin". Content
analysis has a standard response when fine-grained coding fails
reliability: coarsen the scheme and re-test. Free - the outputs and labels
already existed.

**Discipline.** One pre-stated collapse per field, chosen for what the
modelling needs, not searched for the best-scoring partition. Disclosed as
post-hoc in `test_coarsened_agreement.py`.

**Result: all four still failed on both arms.**

| Coarsened field | Sonnet | Haiku |
|---|---|---|
| frame_category -> 3 thematic groups | 0.496 | 0.523 |
| consequence_direction -> has/has-no implication | 0.398 | 0.310 |
| impact_horizon -> transient/persistent | 0.324 | 0.419 |
| stance -> negative/not-negative | **-0.182** | **-0.114** |

The negative stance kappas are the informative result here: systematic
opposite-direction disagreement, not noise. That is a signature of a
construct problem, and it set up experiment 4.

---

## Experiment 4: inter-model reliability as a second ruler

**Why.** The gate rested on a single-pass human coding that was never
checked for reproducibility. The eligibility protocol does check - it blind
re-coded 34 of its 168 pilot articles and reported human-to-human kappa
(1.000 / 0.922 / 1.000 / 1.000) before comparing any LLM output. **D4
skipped that step.** With that gap, and with two fields shown by experiment
2 to have been scored against contradictory instructions, a low
human-machine kappa cannot be attributed to the model. Adding a second
round of coding from the same coder would have added another uncertain
measurement rather than resolved the first, so the two arms already run
were compared against each other instead. Free, no human input.

**Result.**

| Field | vs human (best arm) | Sonnet vs Haiku |
|---|---|---|
| primary_issue | 0.729 | 0.798 |
| attribution_type | 0.600 | 0.670 |
| consequence_direction | 0.251 | **0.647** |
| frame_category | 0.483 | 0.502 |
| impact_horizon | 0.229 | 0.339 |
| stance_per_party | 0.490 | 0.316 |

**`consequence_direction` is reproducible but construct-divergent** - two
independently prompted models agree at 0.647 while both disagree with the
human coding at 0.251. That is a stable instrument measuring something the
reviewer scoped differently, not an unreliable one.

The pattern was traced in the stance disagreements: an article reporting a
party's heavy electoral defeat was coded `negative` by both models (the
article represents that party unfavourably) and `neutral` by the reviewer
(factual reporting carries no editorial stance). Both readings are
defensible; the schema never resolved which it meant. For a research
question about coverage that makes a party look bad, the models' reading is
the construct-valid one.

**frame_category, impact_horizon and stance fail both rulers** - the models
disagree with each other as well as with the reviewer.

---

## Experiment 5: reform_uk sub-field block

**What ran.** The `reform_uk` block sits inside the consequence layer's
schema but is a sibling property of `consequence_direction`, not derived
from it, so that field's failure does not disqualify it. It had never been
validated: the D4 gold labels cover the six comparison fields only, and
`stance_reform_uk` belongs to the failed stance layer. 22 articles - the 14
the model marked `applicable` plus 8 controls it marked not - hash-shuffled,
carrying no model output, so the sheet was blind. Controls were included
deliberately: scoring only the positives would give the reviewer an all-yes
column, a constant marginal, and a kappa that collapses regardless of true
agreement.

**Result.**

| Field | pairs | Sonnet | Haiku |
|---|---|---|---|
| applicable | 22 | 0.288 fail | **0.680 pass** (86.4% agreement) |
| growth_suggested | 5 | undetermined | undetermined |
| credible_challenger | 5 | undetermined | undetermined |
| established_support_affected | 5 | undetermined | undetermined |
| switching_directions | 5 | undetermined | undetermined |
| signal_nature | 5 | undetermined | undetermined |

The five sub-fields are scored only where both sides say `applicable`,
because the schema forces them empty otherwise (rule E4), and the reviewer
marked just 5 of 22 articles applicable. **At five pairs a single
disagreement moves kappa by roughly 0.2, so neither verdict carries
information** - recording them as failures would overstate the evidence
exactly as much as recording them as passes. They are labelled
`undetermined_insufficient_sample`, distinct from
`excluded_not_validated`, because the remedy differs: a sample enriched
for Reform-applicable articles would settle them cheaply. The 20-pair
minimum was written after seeing that the subset was five; that ordering is
disclosed in `compare_reform_subfields.py`.

**Adopted:** the `applicable` flag on Haiku - a validated Reform-relevance
judgement, independent of the E6 keyword disambiguation at the eligibility
stage.

---

## Experiment 6: the stance layer redesigned

**Diagnosis first.** The inter-model stance disagreement was decomposed on
the 60 articles. Of 61 party-level comparisons only 30 agreed:

* **16 (26%) inclusion disputes** - one arm created a row for a party and
  the other did not. The layer leaves the choice of which entities to
  evaluate to the model, gated behind two subjective conditions (the
  representation must be evaluative, and it must carry a verbatim evidence
  span). Sonnet produced 168 rows to Haiku's 140 on identical input. **The
  two arms were answering different question sets.**
* **15 (25%) direction disputes, 11 of them involving `mixed`** -
  `mixed vs negative`, `mixed vs positive`, `negative vs mixed`. Not a
  disagreement about hostility; a disagreement about the threshold at
  which both valences present stop being "predominantly negative" and
  become "mixed".
* **Only 4 of 61 were substantive direction conflicts.**

**What the revised layer changes.** Two changes, one per diagnosed fault.
The party list is fixed by deterministic alias matching in code, so both
arms answer identical question sets and the inclusion boundary is
reproducible by construction. `mixed` is removed - three values only
(`unfavourable`, `favourable`, `neither`) with an instruction to name the
predominant direction. The verbatim evidence-span requirement is dropped
for this layer only, because it suppressed recall: a model that could see
hostile framing but could not isolate one clean quotable span was pushed
into omitting the row entirely.

**A configuration fault worth recording.** The first submission set
`max_tokens` to 2,000 while the Haiku arm reserves 4,000 for thinking. The
API requires `budget_tokens < max_tokens`, so all 34 Haiku requests errored
while all 34 Sonnet requests succeeded - Sonnet uses adaptive thinking and
has no fixed budget to exceed. Raised to 6,000 and resubmitted. The
asymmetry is a real trap for any future fixed-budget arm.

**Result: stance recovered, and on both rulers.**

| | original | revised |
|---|---|---|
| inter-model kappa | 0.316 | **0.848** (91.3% agreement, 92 pairs) |
| vs human kappa | 0.482 / 0.490 | **0.741 / 0.736** (71 pairs) |

Per party, inter-model:

| party | pairs | agreement | kappa |
|---|---|---|---|
| conservative | 27 | 0.926 | 0.800 |
| labour | 26 | 0.808 | 0.647 |
| liberal_democrat | 14 | 1.000 | 1.000 |
| reform_uk | 11 | 1.000 | 1.000 |
| green | 8 | 1.000 | 1.000 |
| ukip | 6 | 0.833 | 0.667 |

**Caveats that must travel with this result.** It is a post-hoc redesign of
a layer that failed, so it is "stance recovered at reduced granularity
under a revised layer", never "the original passed". Granularity is three
levels, not five: no `mixed`, no intensity, so features built on it must
not be described as five-level sentiment. The perfect kappas on Liberal
Democrat, Reform UK and Green rest on 14, 11 and 8 pairs - encouraging and
directionally clear, but thin. The human comparison drops `mixed` and
`not_mentioned` pairs as unmappable, leaving 71 of 92. And the layer is
less auditable than the others by design, having traded the verbatim
evidence requirement for a free-text reason.

---

## Experiment 7: the framing layer redesigned

**Same recipe, same reasoning.** `primary_frame` asks the model to pick the
one "primary" frame from sixteen. That is the identical shape of fault the
stance layer had: an unguided ranking. An article that both questions the
council's competence and portrays voters as fed up genuinely contains two
frames, and which is "primary" is a question the article does not answer -
so two models resolve it differently while agreeing completely about what
the article contains. The coarsened re-test could not detect this, because
collapsing a recorded `primary_frame` into a family still inherits the
ranking that produced it: you cannot recover "both were present" from a
field that only ever stored one winner.

**What changed.** One sixteen-way ranking became four independent binary
presence questions, the four frames fixed in advance and chosen from the
research question rather than from what scores well - incumbent judgement,
challenger emergence, voter discontent, local impact, each mapped from a
group of the original sixteen. No frame is "primary", they are not
mutually exclusive, and the verbatim evidence requirement is dropped as it
was for stance.

**Result: two of four frames recovered, and the two that matter most are
not among them.**

| Frame | positives (Sonnet / Haiku) | agreement | kappa | verdict |
|---|---|---|---|---|
| incumbent_judgement | 25 / 27 | 0.855 | 0.705 | **adopted** |
| local_impact | 20 / 18 | 0.836 | 0.635 | **adopted** |
| challenger_emergence | **6 / 2** | 0.927 | 0.471 | undetermined |
| voter_discontent | **5 / 4** | 0.945 | 0.637 | undetermined |
| pooled over all four | - | 0.891 | 0.695 | passes |

The pooled figure passes and is reported, but it is the wrong number to
act on. `challenger_emergence` was detected in 6 of 55 articles by one arm
and 2 by the other - a threefold difference in prevalence - and
`voter_discontent` in 5 and 4. Their high agreement rates are carried
almost entirely by the ~50 articles where both arms say absent. A minimum
of ten positive cases per arm was therefore applied, uniformly to all four
frames; the two thin frames fall below it and are recorded as
`undetermined_insufficient_positives`, the same category as the reform_uk
sub-fields and for the same reason. Recording them as passes on the AC1
fallback would misuse a route registered for prevalence-skewed but
genuinely tested fields. The threshold was written after seeing the
prevalence counts, and that ordering is disclosed in
`compare_frame_rescue.py`.

**This is the sharpest limitation in the whole gate.**
`challenger_emergence` is the frame that speaks most directly to the
research question - Reform UK is the insurgent under study, and "does
coverage presenting Reform as a rising force predict its vote share" is
close to the thesis. It is the frame the 60-article sample cannot validate.
The remedy is not a better prompt but a bigger sample of the right
articles: a Reform-enriched draw would settle it, and it is cheap.

**Two further findings recorded.**

*Human recall is weak.* Against the reviewer's single label, the models
mark the implied frame present in only 58.3% (Sonnet) and 49.1% (Haiku) of
scored articles. The test is one-sided by construction - the reviewer chose
one frame from sixteen, so the labels cannot say whether a frame the model
reports would have been rejected - but a recall near a half is a real
divergence, larger than for any other adopted layer. Two readings are
available and the data cannot separate them: the models may be missing
frames a person saw, or the reviewer, forced to pick one of sixteen, may
have selected frames that are marginally present. That the two arms agree
with each other far better than either agrees with the reviewer is
consistent with the second, but does not establish it.

*Sonnet's output was less reliable than Haiku's here.* Five of 60 Sonnet
responses were malformed JSON (unescaped content inside the reason field),
against zero of 60 for Haiku. An 8.3% schema failure rate is above the 5%
ceiling set for the 366-article health check, and it is the second finding
in this gate favouring Haiku on grounds other than price.

---

## Where this leaves the feature set

27 of 30 pre-registered features available
(`news_features/preregistered_feature_specification.json`):

| Layer | Status | Basis |
|---|---|---|
| volume (7 features) | available | counted from the corpus, no LLM judgement, no gate applies |
| issues (6) | available | 0.729 human, 0.798 inter-model |
| credit_blame (4) | available | 0.600 human, 0.670 inter-model |
| consequence (3) | available | 0.647 inter-model; human divergence documented |
| reform_flag (2) | available | 0.680 on 22 blind articles |
| stance (3) | available | revised layer, 0.848 inter-model, 0.741 human |
| framing (2 of 4) | available | revised layer: incumbent_judgement 0.705, local_impact 0.635 inter-model; human recall only 0.49-0.58 |
| framing (2 of 4) | **undetermined** | challenger_emergence (2-6 positives of 55) and voter_discontent (4-5) - too few positive cases for a verdict |
| horizon (1) | **unavailable** | failed all three (0.229 / 0.339) |
| reform_uk sub-fields (5) | **undetermined** | 5 pairs, below the 20-pair minimum |

**Model:** `claude-haiku-4-5`, on its own gate results - it clears more
fields than Sonnet at half the price, and the two fields where it is
decisive (attribution at 0.600, reform applicable at 0.680) are ones
Sonnet fails.

**What the research question can and cannot measure now.** Coverage volume,
issue composition, local/national split, independent-source counts, recency
weighting, Reform relevance and mention counts, blame and credit
attribution, implied electoral consequence, and three-level per-party
portrayal. It also measures two narrative frames - whether the article judges the
incumbent's record, and whether it frames matters through local
consequences. It cannot measure effect duration, five-level sentiment
intensity, the challenger-emergence or voter-discontent frames, or the
Reform sub-signals (growth, challenger credibility, switching
direction). The challenger-emergence frame is the sharpest of these
gaps, being the one closest to the thesis; all of them need a
Reform-enriched validation sample rather than a better prompt.

## Where the raw answers live

The six-layer raw outputs (`d4_llm_outputs*.json`, 1.3MB and 1.5MB) are
excluded from Git under the same copyright three-tier policy that excludes
the Phase 6 pilot outputs: those layers require verbatim evidence spans, so
the files reproduce substantial article text. They are retained locally and
on OneDrive alongside the other generated research outputs.

`d4_llm_output_manifest.json` stays in Git in their place. It records, per
article and layer, whether the response parsed, its validation errors, and
a sha256 of the record - enough to prove that a figure in this log was
computed from those exact answers, without reproducing any article text.

The two rescue layers' outputs *are* in Git. They dropped the verbatim
evidence requirement, so their reasons are the model's own prose - 0 of 60
framing reasons and 1 of 34 stance reasons contain a quoted fragment - and
the files are 32-72KB rather than megabytes.

**Cost:** about $14 across seven experiments. The gate stopped a $229
full-corpus run that would have produced four unusable feature blocks. Two
redesigns it forced recovered the most theoretically important of them
(per-party portrayal, in full) and half of another (framing).
