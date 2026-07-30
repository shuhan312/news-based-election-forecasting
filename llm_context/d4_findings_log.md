# D4 validation: every experiment run, and what each one showed

A complete record of the D4 gate and its follow-up experiments, written so
the final report can cite specific numbers rather than a summary, and so a
reader can see what was tried that did *not* work as well as what did.
Ten experiments, 2026-07-29 to 2026-07-30, at batch pricing.

Findings are recorded in the order they happened, including the ones later
superseded, because the sequence is itself part of the evidence: three of
the verdicts turned out to be artefacts of how the exam was written, and two
turned out to be design faults in the layer being examined. A summary that
showed only the final numbers would make the gate look cleaner than it was.

**Reading warning.** Experiments 1 to 7 were scored without checking whether
each record passed its own validator. Experiment 8 found that fault and
recomputed everything; where its figures differ from the earlier sections,
**Experiment 8 supersedes them**. The earlier numbers are left in place
rather than edited away, because the correction is part of the record.

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

## Experiment 8: the exam never checked whether the answers were admissible

**What prompted it.** A question about whether the issues layer had even
been part of the previous day's test. Checking that turned up something
larger.

**The fault.** Every kappa in Experiments 1 to 7 was computed from records
that *parsed*. None checked whether the record passed its own validator. The
three original layers require every `evidence_span.text` to appear
character-for-character in the article, and `is_eligible_for_downstream`
discards the whole record when one does not. But a record with a
reconstructed quotation still has a perfectly readable `primary_issue`. So
the exam was scoring answers that nothing downstream can use.

This is a different fault from the two in Experiment 2. Those were about how
the two sides were paired. This one is about which answers were admissible
at all, and it hit the arm with the worse span fidelity hardest.

**Span fidelity, measured directly.** Both arms, same 60 articles, same
prompts, same validator:

| layer | Sonnet exact | Haiku exact | Haiku opens then diverges | Haiku absent |
|---|---|---|---|---|
| issues | 183/184 (99%) | 122/193 (63%) | 52 | 19 |
| credit_blame | 270/271 (99%) | 135/255 (52%) | 87 | 33 |
| consequence | 165/167 (98%) | 76/134 (56%) | 45 | 13 |
| **total** | **618/622 (99.4%)** | **333/582 (57.2%)** | **184** | **65** |

An earlier note in this project described Haiku's failures as truncation.
That was wrong and is corrected here: 184 of the 249 failures open faithfully
and then diverge - a spliced or continued passage, ending in a full stop, not
a cut-off. 65 are absent from the article altogether.

Three alternative explanations were tested and rejected. Not an over-strict
validator: whitespace normalisation recovers exactly 1 span, and Sonnet
passes 99.4% on the same ruler. Not mismatched text: both arms read the same
body from `load_d4_articles()`. Not truncation, per the above.

**Validator rejections per layer, out of 60 articles:**

| layer | Sonnet rejected | Haiku rejected |
|---|---|---|
| issues | 7 | 35 |
| credit_blame | 3 | 33 |
| consequence | 5 | 31 |
| temporal | 12 (+1 unparseable) | 27 |
| framing | 4 | 37 |
| stance | 0 | 26 |

**Recomputed against the human gold labels, validator-gated.** These are the
figures that stand.

| field | n (Sonnet) | Sonnet kappa | Sonnet AC1 | max marginal | n (Haiku) | Haiku kappa | earlier figure now superseded |
|---|---|---|---|---|---|---|---|
| primary_issue | 53 | **0.616** | 0.627 | 0.189 | - | **0.602** | Haiku 0.729 |
| attribution_type | 57 | **0.521** | 0.647 | 0.579 | - | **0.516** | Haiku 0.600 - "passes" |
| consequence_direction | 55 | **0.259** | 0.449 | 0.727 | - | **0.136** | - |
| frame_category | - | 0.408 | 0.422 | - | - | 0.310 | - |
| stance_per_party | - | 0.490 | 0.530 | - | - | 0.537 | - |
| impact_horizon | - | 0.186 | 0.191 | - | - | 0.146 | - |

Inter-model figures moved too: consequence_direction 0.647 to **0.587**,
attribution 0.670 to **0.602**.

**What changed as a result.** Two verdicts flipped. Attribution had been
recorded as passing on Haiku at exactly 0.600; both arms now fail. And the
consequence layer's inter-model figure fell below the bar it had cleared.
Neither flip is a small-n artefact on the Sonnet arm, which lost only 3 and
5 records respectively.

**Neither field qualifies for the pre-registered fallback route.** It needs a
marginal at or above 0.90 to trigger, so that Gwet's AC1 can only be reached
for when skewed prevalence genuinely depresses kappa. Attribution's largest
marginal is 0.579 and consequence's is 0.727. Attribution's AC1 of 0.647
would clear 0.60 if the route were open. It is not open, and it was not
opened.

**Consequence of the span finding for production.** The three original layers
moved to Sonnet for the corpus run. On the 89-article narrow tranche this
was verified rather than assumed: issues on Sonnet parsed 88 of 89 and
verified **327 of 327 spans (100%)**, against 31 of 89 clean on the earlier
all-Haiku submission of the same tranche. The two revised layers stayed on
Haiku and were clean there (stance 56/57, framing 88/89).

---

## Experiment 9: what the disagreements actually look like

**Why.** Kappa is symmetric. It says two coders disagree; it does not say
which is wrong. And unlike the eligibility layer - blind re-coded at kappa
0.922 to 1.000 on 34 articles - these six content fields have **no human
test-retest estimate**, so there is no bound on the human side either. Before
concluding anything about the model, the disagreements were tabulated.

**Consequence direction, human rows against Sonnet columns, n=55:**

| human \ model | none | potential_benefit | potential_damage | total |
|---|---|---|---|---|
| none | 22 | 2 | 16 | 40 |
| potential_damage | 0 | 0 | 7 | 7 |
| unclear | 0 | 0 | 3 | 3 |
| mixed_impact | 0 | 1 | 2 | 3 |
| potential_benefit | 0 | 0 | 2 | 2 |
| **total** | **22** | **3** | **30** | **55** |

Diagonal 29 of 55. **Eighteen of the twenty-six disagreements sit in one
place**: the human recorded no consequence, the model found one. The
marginals are far apart - human "none" 40 of 55, model "none" 22 of 55, and
the model chose potential_damage on 30 of 55. This is a disagreement about
whether a consequence is present, not about which direction it runs.

Supporting evidence that this is definitional rather than random: the two
models agree with each other far better than either agrees with the human
(0.587 against 0.259 and 0.136). Models drawing arbitrary answers would not
converge on each other. That pattern is what the stance layer showed before
its redesign.

**Attribution type, human rows against Sonnet columns, n=57:**

| human \ model | blame | credit | none | total |
|---|---|---|---|---|
| blame | 24 | 4 | 5 | 33 |
| credit | 1 | 3 | 1 | 5 |
| mixed | 2 | 1 | 0 | 3 |
| none | 1 | 2 | 8 | 11 |
| unclear | 1 | 1 | 3 | 5 |
| **total** | **29** | **11** | **17** | **57** |

Diagonal 35 of 57 (61.4%). The shape is the opposite of consequence's on
every count. The marginals broadly match - human blame 33 of 57, model 29.
The disagreements scatter across seven cells rather than concentrating in
one. The presence axis accounts for only 12 of 57 disagreements, against
consequence's 18 of 26. And inter-model agreement is itself only 0.602, so
there is no shared model reading distinct from the human's to point at.

**One asymmetry that is worth recording.** The human used `mixed` on 3
articles and `unclear` on 5 - 8 of 57, 14%. The model used neither, once,
across all 57 records; on those 8 articles it answered blame 3, credit 2,
none 3. Both values are in the prompt's enum, so this is the model declining
options it was offered, not an instrument fault, and the human labels are
not excused from pairing against it. As a diagnostic only: setting those 8
aside leaves n=49, agreement 71.4%, kappa 0.490, AC1 0.605. That is recorded
to show where the headroom is, and was **not** used as a verdict.

---

## Experiment 10: the consequence layer redesigned

**The diagnosis acted on.** Experiment 9 located the fault in the threshold,
not the direction. The frozen prompt asked for "the possible electoral
reading AS THE ARTICLE SUGGESTS IT", which leaves the model to decide how
much suggestion is enough, and it set that bar far lower than the reviewer
did. `src/llm_extraction/consequence_rescue.py` replaces the matter of
degree with a testable condition: an electoral consequence requires a clause
about an electoral quantity - votes, seats, a majority, control of the
council, winning or losing, a party's support level, turnout. A problem being
reported, a service failing or a politician being criticised is explicitly
not one, however strongly it might imply one. Three values, not five
(`mixed` and `unclear` removed). No verbatim span. One judgement per article,
so no positional rule applies to one side only.

**The scoring rule was declared in the script's docstring before the batch
was submitted,** because this layer's verdict had already moved three times
under successive scoring corrections. Primary test: presence binary, human
`none` against everything else. Secondary: direction on jointly-present
articles, with human `mixed_impact` and `unclear` excluded because the
revised vocabulary offers no value they could match. No other variant to be
computed.

**Result, Haiku arm, n=60:**

| test | n | agreement | kappa | AC1 | max marginal | verdict |
|---|---|---|---|---|---|---|
| **presence (primary)** | 60 | 0.850 | **0.598** | 0.763 | 0.817 | **fails by 0.002** |
| frozen layer, same test | 29 | 0.724 | 0.318 | 0.565 | 0.897 | fails |
| direction (secondary) | 5 | 1.000 | 1.000 | 1.000 | 0.800 | passes, but n=5 |

Records accepted 60 of 60, validator rejections 0 - against 31 of 60
rejected on the frozen layer's Haiku arm. 8 articles excluded from the
direction test (human `mixed_impact` 5, `unclear` 3). Usage 150,117 in /
34,173 out, about $0.16.

Marginals, which is where the redesign visibly worked:

| | none | asserts a consequence |
|---|---|---|
| model, revised | 49 of 60 (81.7%) | 11 (damage 6, benefit 5) |
| human | 42 of 60 (70.0%) | 18 |
| model, frozen | 22 of 55 (40.0%) | 33 |

**What this shows, stated without softening.** The redesign did what the
diagnosis said it would. It closed the threshold gap - the model went from
calling 60% of articles consequential to 18%, against the human's 30%. It
eliminated the validator losses, taking n from 29 to 60. On the identical
test it nearly doubled kappa, 0.318 to 0.598. **And it lands 0.002 below the
gate.**

**The near-miss was not resolved in the layer's favour.** Recorded
explicitly because the temptation is legible in the numbers: AC1 is 0.763
and agreement is 85%, so both *conditions* of the fallback route are
satisfied. The route's *trigger* is not - it requires a marginal at or above
0.90 and the largest here is 0.817. The trigger exists precisely so that AC1
cannot be reached for whenever kappa is inconvenient, and 0.598 against a
0.600 bar is exactly the case it was written for. The direction test's
kappa of 1.000 is likewise not evidence of anything at n=5.

The Sonnet arm of the same experiment was submitted at the same time and is
pending. Both arms were declared before either was scored, and the verdict
is per-arm, as it has been throughout - the production model for a layer is
whichever arm clears its own gate.

**Attribution was not given the same treatment, and the reason was
initially overstated.** The first statement of it - that no fix exists - was
too strong. What Experiment 9 established is that no *diagnosis* is visible
in a 57-row matrix: no threshold gap, no dominant cell, no shared model
reading. But the design that worked three times over can be applied
mechanically without a diagnosis. Attribution asks for one value from five
while doing three jobs at once (is there an attribution, which direction, to
whom); the framing redesign's move was to split one many-way judgement into
independent binaries. Here that is two questions - does the article blame a
named party, does it credit one - under which both-yes is `mixed`, both-no is
`none`, the 14% vocabulary gap closes, and the "which is principal" rule
disappears. Whether it would work is untested. The decision taken was to
hold it until this experiment's Sonnet arm reports, because that arm tests
the same design pattern on a third layer, and its result is the best
available evidence on whether a fourth attempt is worth the run.

---

## Experiment 11: the tranche gate, and the one threshold that was wrong

**What the gate is for.** 89 articles in the windows within thirty days of
polling, extracted on the production prompts and models, checked on four
thresholds before the 1,632-article corpus is committed to. It reports and
stops; it does not retry.

**First run: FAIL.** Two of the three gating layers failed.

| layer | schema failure | empty records | quotes verified | verdict |
|---|---|---|---|---|
| issues | 10.1% (9 of 89) | 22.5% | 100.0% | fails schema and empty |
| stance_revised | 0.0% | 0.0% | n/a | pass |
| framing_revised | 0.0% | 34.8% | n/a | fails empty |
| consequence (excluded) | 15.7% | 43.8% | 100.0% | not gating |

**The nine issues failures, itemised.** Six were the same rule: a confidence
of 0.4 or 0.45 correctly reported, and `review_status` not set to `flagged`
as the contract requires. The issue code and every evidence span in those
six records were sound. The remaining three were real - one span not found
verbatim (a candidate-list headline), one unexpected property
(`issue_other_label`), one unparseable response.

An earlier check of this same batch reported "88 of 89 parsed, 327 of 327
spans verified". That was accurate for what it measured and incomplete as a
health verdict: it tested JSON parsing and span presence, while the
validator applies the layer's whole contract. The 100% span figure stands;
the 88 of 89 did not mean the layer passed.

**The six flag failures were repaired, not waived.** The flag is derivable
from a confidence value the model already supplied, so a validator
discarding the record for failing to derive it costs 6.7% of a corpus over
bookkeeping. The collector now sets the field, re-runs the *same* validator,
and keeps the record only if nothing else is wrong - a record failing this
rule and a span check is still rejected. Each repair is recorded per
article. The effect on the validated figures was measured before the repair
was adopted: on the D4 sample it admits one further Sonnet record and moves
the issues kappa from 0.616 to **0.622**, changing no verdict, and admits
none on Haiku. The 5% schema threshold was not moved.

**The empty-record threshold was wrong, and this is the one bar that
changed.** It was a flat 20% per layer and, alone among the four, cited no
precedent - because there was none. Checked against the D4 sample, the same
60 articles on which these layers were validated and adopted:

| layer | D4 Sonnet | D4 Haiku | narrow tranche | old 20% bar |
|---|---|---|---|---|
| framing_revised | 36.4% | 40.0% | 34.8% | rejects all three |
| issues | 18.3% | 8.3% | 22.5% | rejects the tranche |
| stance_revised | 0.0% | 0.0% | 0.0% | passes |

A bar that rejects the data on which two of the four frames were adopted is
measuring the corpus, not the extraction. An article three weeks before
polling can carry none of four narrative frames and no codeable political
issue and still belong in the corpus: eligibility means in scope, not about
the election. The replacement compares each layer against its own D4 rate on
the arm it runs on and fails on a regression of more than 15 points - the
same shape as the cost check, which allows twice the estimate rather than
naming a figure.

**This was a threshold changed after it failed, which is the move the gate
exists to prevent, so the distinction is stated rather than assumed.**
Relaxing a bar because the tranche failed it is selection on the evaluation
data. Finding that the bar was never consistent with the prior sample that
validated the layers, and recalibrating against that prior sample, is
correcting the instrument. The calibration figures above all come from D4,
which predates the tranche. What was *not* touched: the schema threshold and
the quote threshold, both of which the tranche also failed on the issues
layer, keep their original values.

**Second run: PASS**, on the three gating layers.

| layer | schema failure | empty records | allowance | quotes verified | verdict |
|---|---|---|---|---|---|
| issues | 3.4% (3 of 89) | 22.5% | 33.3% | 100.0% | pass |
| stance_revised | 0.0% | 0.0% | 15.0% | n/a | pass |
| framing_revised | 0.0% | 34.8% | 55.0% | n/a | pass |

**One finding that survives the pass and belongs in the report.** The human
reviewer recorded a primary issue in 60 of 60 D4 articles - `none` never
once. The model returns no primary issue on 18.3% of those same articles and
22.5% of the tranche. Every one of those is a disagreement with the
reviewer, and the layer still clears its gate at 0.616, which means
agreement on the articles where it does assign an issue is carrying the
figure. The layer under-calls issue presence relative to the reviewer, and
issue-share features built on it will be computed over a denominator that is
roughly a fifth smaller than the reviewer would have used.

**A note on the excluded layers' tranche figures.** `consequence` scores
13.5% schema failure and 43.8% empty here. It does not gate, and the layer
was already excluded on the D4 human comparison rather than on tranche
health, so these figures change no decision. The `credit_blame` batch was
**cancelled** while still in progress: it had run 68 minutes with none of its
89 requests complete, it was blocking the collector, and its output was not
going to be used. Cancelling avoids billing for unprocessed requests.
Collecting it would have added a completeness figure to this log and nothing
to any decision.

---

## Where this leaves the feature set

**Superseded twice.** The version of this table written after Experiment 7
listed credit_blame and consequence as available on figures of 0.600 and
0.647. Both were computed before the validator gate of Experiment 8. The
table below uses the gated figures.

| Layer | Status | Basis |
|---|---|---|
| volume (7 features) | available | counted from the corpus, no LLM judgement, no gate applies |
| issues (6) | **available** | 0.616 human (Sonnet, n=53), 0.742 inter-model - the only original layer to clear both rulers |
| stance (3) | **available** | revised layer, 0.741 human, 0.848 inter-model |
| framing (2 of 4) | **available** | revised layer: incumbent_judgement 0.705, local_impact 0.635 inter-model; human recall 0.49-0.58 |
| reform_flag (2) | available | 0.680 on 22 blind articles |
| consequence (3) | **pending** | frozen layer fails (0.259 human, n=55). Redesign reaches 0.598 on presence, 0.002 below the gate, Haiku arm; Sonnet arm outstanding |
| credit_blame (4) | **unavailable** | 0.521 / 0.516 human at n=57; fallback route not triggered (marginal 0.579). Redesign identified but not run |
| framing (2 of 4) | **undetermined** | challenger_emergence (2-6 positives of 55) and voter_discontent (4-5) - too few positive cases for a verdict |
| horizon (1) | **unavailable** | 0.186 / 0.146 human, 0.303 inter-model - fails on all three rulers |
| reform_uk sub-fields (5) | **undetermined** | 5 pairs, below the 20-pair minimum |

**Production models, per layer, on measured compliance rather than one
global choice:** issues on `claude-sonnet-5` (99.4% span fidelity against
57.2%), stance and framing revised on `claude-haiku-4-5` (no span
requirement, 0-2% format failure, and Sonnet fails the framing layer's
format check at 8.3% against Haiku's 0-1%). The earlier recommendation of
Haiku for all layers rested on the pre-gate figures and on the two fields
where Haiku appeared decisive - attribution at 0.600 and reform-applicable
at 0.680. Attribution's 0.600 did not survive Experiment 8.

**On why the gate stays human-referenced.** The question was raised directly:
if the human labels may be wrong, why not gate on inter-model agreement
instead, where four of six fields score higher. Three reasons, recorded
because the answer belongs in the report.

First, the two rulers do not rank the layers the same way - the original
stance layer scores 0.291 inter-model against 0.490 and 0.537 human, the
reverse of consequence's pattern. Choosing per layer whichever ruler is
kinder is selection on the outcome, and the pre-registration exists to
prevent exactly that.

Second, two LLMs are not independent coders. They share training data and
read the same prompt. When both read the frozen consequence prompt's "as the
article suggests it" and both set the bar low, their 0.587 agreement is
produced by the shared prompt, not by two independent readings converging on
the truth. Inter-model agreement measures reproducibility; the gate is asked
to establish validity.

Third and decisively, the redesigns that worked cleared **both** rulers -
stance revised at 0.848 inter-model and 0.741 human. A layer that clears one
and fails the other is reporting a broken definition, and the fix is the
definition. That is what Experiment 10 did, and it moved the human figure
from 0.318 to 0.598 without the ruler changing at all.

What the human side's own reliability is on these six fields remains
unmeasured, and that is a stated limitation rather than a resolved question.
The eligibility layer was blind re-coded; D4 was not.

**What the research question can and cannot measure now.** Coverage volume,
issue composition, local/national split, independent-source counts, recency
weighting, Reform relevance and mention counts, three-level per-party
portrayal, and two narrative frames - whether the article judges the
incumbent's record, and whether it frames matters through local
consequences. It cannot measure blame and credit attribution, effect
duration, five-level sentiment intensity, the challenger-emergence or
voter-discontent frames, or the Reform sub-signals. Implied electoral
consequence is pending one outstanding arm.

Against the version written after Experiment 7, this loses the four
attribution features outright and puts the three consequence features in
doubt. The challenger-emergence frame remains the sharpest gap, being the
one closest to the thesis; it needs a Reform-enriched validation sample
rather than a better prompt.

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

The three rescue layers' outputs *are* in Git. They dropped the verbatim
evidence requirement, so their reasons are the model's own prose - 0 of 60
framing reasons and 1 of 34 stance reasons contain a quoted fragment - and
the files are 32-72KB rather than megabytes.

**Spend across ten experiments,** at batch pricing: about $14 through
Experiment 7, plus $0.16 for the consequence redesign's Haiku arm and its
outstanding Sonnet arm. The 89-article narrow tranche, which is a production
run rather than an experiment, cost $1.82 on the three layers being kept and
$1.66 on the consequence layer that Experiment 8 then excluded - that $1.66
is a real loss, incurred because the tranche was submitted before Experiment
9's confusion matrix had been built.

The gate stopped a full-corpus run that would have produced four unusable
feature blocks. Three redesigns it forced recovered the most theoretically
important of them (per-party portrayal, in full), half of another (framing),
and brought a third to within 0.002 of its bar without clearing it.
