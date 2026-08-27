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

## The two gates, and which is which

This log has been using "the gate" for two different things. They answer
different questions, run at different times, and one of them has no answer key
to overfit to. Stated here because a reader cannot otherwise tell which is
meant in a given paragraph.

### Gate 1 - the D4 validation gate: *may this layer be used at all?*

**Question:** does the model's judgement agree with a human coder's well
enough to claim the extraction measures the construct it names?

**How:** 60 articles were drawn from the corpus and hand-coded by the reviewer
across six field groups. The model read the same 60 blind. Agreement is scored
per field.

**The bar,** pre-registered before any scoring: Cohen's kappa >= 0.60 on the
primary route, or Gwet's AC1 >= 0.60 with raw agreement >= 80% on a fallback
route that only opens when a marginal reaches 0.90 - the fallback exists for
the kappa paradox under skewed prevalence, and its trigger exists so that AC1
cannot be reached for whenever kappa is inconvenient. 0.60 is a convention, not
a supervisor requirement: `llm_v2_feasibility_plan.md` §D3 records that the
supervisor's brief specifies neither kappa nor 0.60, and the figure comes from
the conventional reading in which 0.61 and above is substantial agreement.

**What it decides:** whether a layer's features enter the model at all. It
killed attribution, consequence and impact_horizon, and it forced the stance
and framing redesigns. Experiments 1 to 14.

**It has an answer key.** The reviewer's labels are the gold standard, so
repeated attempts on those same 60 articles would be selection. That is why
each layer got at most two attempts and why every scoring rule was declared
before its batch was submitted.

### Gate 2 - the tranche health check: *may the full corpus run proceed?*

**Question:** on articles the production configuration has never seen, does it
produce records that are usable at all?

**How:** a small tranche - 89 articles - is extracted with the exact prompts,
models and validators the full run will use, and four thresholds are applied.
`src/llm_extraction/health_check_tranche.py`.

**The four thresholds:**

| check | bar | why |
|---|---|---|
| schema failure | at most 5% per layer | a record the validator rejects has no data downstream; precedent is the eligibility batch at 0.8% |
| **verbatim quote verification** | at least 95% | a span that cannot be found in the article means the model reconstructed a quotation, and the extraction is untraceable - the single most important check |
| empty records | at most 15 points above that layer's own D4 rate | catches a layer that has stopped finding anything, without failing it for the corpus simply being sparse |
| cost | within twice the estimate | catches a runaway |

**What it decides:** whether to spend on 1,374 articles. It stopped four
submissions, one of them mid-flight, and it is why the corpus was extracted on
a configuration whose failure modes were measured rather than assumed.
Experiments 11 to 16.

**It has no answer key,** and this is the crucial difference. "Is this span
present in the article" and "does this output satisfy the schema" are objective
facts, not judgements. There is nothing to overfit to, which is why re-running
the same 89 articles after fixing a fault is legitimate here and would not be
for Gate 1. What would be illegitimate is re-running until it passes.

**Once the full corpus has run, the same four checks become a report rather
than a gate** - the money is spent, so they describe what was produced instead
of deciding whether to produce it. The response to a bad report was stated
before the run: at or under 3% schema failure proceed, 3 to 8% record as a
limitation and check whether failures concentrate in one kind of article, over
8% stop and do not build features. Quote verification below 95% stops it
outright.

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
minimum was written after seeing that the subset was five; that ordering was
disclosed in the comparison script (retired from main with the sub-field
addendum; in Git history).

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

**Result, both arms, n=60 each. They land on the same figure to three
decimal places.**

| test | arm | n | agreement | kappa | verdict |
|---|---|---|---|---|---|
| **presence (primary)** | Haiku | 60 | 0.850 | **0.598** | **fails by 0.002** |
| **presence (primary)** | Sonnet | 60 | 0.850 | **0.598** | **fails by 0.002** |
| frozen layer, same test | Haiku | 29 | 0.724 | 0.318 | fails |
| frozen layer, same test | Sonnet | 55 | - | 0.400 | fails |
| direction (secondary) | Haiku | 5 | 1.000 | 1.000 | n too small |
| direction (secondary) | Sonnet | 5 | - | 0.000 | n too small |

Haiku's AC1 is 0.763 at a largest marginal of 0.817. Records accepted 60 of
60 on both arms, validator rejections 0 - against 31 of 60 rejected on the
frozen layer's Haiku arm. 8 articles excluded from the direction test (human
`mixed_impact` 5, `unclear` 3). Haiku usage 150,117 in / 34,173 out.

**Inter-model agreement on the revised layer: presence kappa 0.889,
three-value kappa 0.842, on all 60 shared articles.** The frozen layer
managed 0.587.

The direction test is the clearest demonstration in this whole log of why a
minimum sample size matters: on the same five pairs, one arm returns kappa
1.000 and the other 0.000. Neither is evidence of anything.

**What the replication means, stated plainly because it cuts both ways.** Two
models, one on adaptive thinking and one on a fixed 4,000-token budget, at
different price tiers, agree with each other on 89% of presence judgements and
both land on 0.598 against the reviewer. Their model-side marginals are nearly
identical - 49 of 60 "none" on both arms. So the residual disagreement with
the reviewer is **systematic and replicated, not sampling noise**: the
redesigned instrument is highly reproducible and reproducibly 0.002 short of
agreeing with the human coding well enough to pass.

That is the strongest evidence in this project for the possibility that the
remaining gap sits on the human side rather than the model's, and it does not
change the decision. The gate is human-referenced by pre-registration; two
models sharing training data and one prompt are not two independent coders,
so their agreement establishes reproducibility and not validity; and the
reviewer's own test-retest reliability on this field was never measured, so
the human side cannot be shown to be the wrong one either. What can be said
is that nobody can demonstrate which side is right, which is precisely why a
feature built on this layer could not be defended.

Marginals, which is where the redesign visibly worked:

| | none | asserts a consequence |
|---|---|---|
| model, revised | 49 of 60 (81.7%) | 11 (damage 6, benefit 5) |
| human | 42 of 60 (70.0%) | 18 |
| model, frozen | 22 of 55 (40.0%) | 33 |

**What this shows, stated without softening.** The redesign did what the
diagnosis said it would. It closed the threshold gap - the model went from
calling 60% of articles consequential to 18%, against the human's 30%. It
eliminated the validator losses, taking n from 29 to 60 on both arms. On the
identical test it moved kappa from 0.318 to 0.598 on Haiku and 0.400 to 0.598
on Sonnet, and took inter-model agreement from 0.587 to 0.889. **And it lands
0.002 below the gate, on both arms.**

**The near-miss was not resolved in the layer's favour.** Recorded
explicitly because the temptation is legible in the numbers: AC1 is 0.763
and agreement is 85%, so both *conditions* of the fallback route are
satisfied. The route's *trigger* is not - it requires a marginal at or above
0.90 and the largest here is 0.817. The trigger exists precisely so that AC1
cannot be reached for whenever kappa is inconvenient, and 0.598 against a
0.600 bar is exactly the case it was written for. The direction test's
kappa of 1.000 is likewise not evidence of anything at n=5.

**The Sonnet arm reported and the pre-stated rule fired.** The handling of
each possible figure was written into
`d4_gate_outcome_and_decisions.md` §4c before the arm returned: clear at 0.65
or above and the layer is adopted; land in 0.600 to 0.649 and it is adopted
but marked secondary; fall below 0.600 and it is dropped and recorded as an
instructive near miss. Sonnet returned 0.598. **The layer is dropped.** The
three consequence features are `unavailable`, not pending.

No further scoring variant was computed, per the pre-statement. AC1 and raw
agreement both satisfy the fallback route's conditions and its trigger does
not fire, needing a marginal at 0.90 against 0.817. Two arms were two attempts
at one bar and both missed it, which at least removes the multiple-comparison
concern the pre-statement was written to handle.

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

## Experiment 12: the attribution layer, and a five-way field hiding two faults

**What prompted it.** Whether the two excluded layers were really beyond
rescue, and whether the reason had been stated clearly. Re-checking it found
that one of my own conclusions was wrong.

**The wrong conclusion.** Experiment 9 reported that attribution had no
diagnosable definitional gap: the disagreements scattered across seven cells,
the marginals broadly matched (human blame 33 of 57, model 29), and
inter-model agreement was itself only 0.602, so there was no shared model
reading distinct from the reviewer's to point at. Consequence, by contrast,
had 18 of 26 disagreements in one cell. On that basis attribution was
excluded outright while consequence was sent for redesign.

**What the five-way field was hiding.** The two binaries a redesign would ask
about can be derived from the frozen output already on disk -
`attribution_type_set` records every type the model used per article, so
`mixed` maps to both directions exactly as it does on the human side. No API
call was needed. Derived that way, on the arms' own accepted records:

| binary | Sonnet kappa | Haiku kappa | agreement | human positives | model positives |
|---|---|---|---|---|---|
| blame present | **0.564** (n=52) | **0.565** (n=24) | 0.808 / 0.792 | 36 / 10 | 34 / 9 |
| credit present | **0.181** (n=52) | 0.483 (n=24) | 0.558 / 0.792 | 8 / 5 | **29** / 8 |

Human `unclear` is excluded from both - the reviewer recorded that an
attribution exists whose direction is not determinable, which neither binary
can be paired against.

These are two different failures, not one uniform one. Blame is 0.036 short
of the bar with marginals that match closely, 36 human positives against 34
from the model. Credit has exactly the shape consequence had: the model finds
credit in 29 of 52 articles where the reviewer finds it in 8, a bar set some
three and a half times lower. The five-way average hid it because blame is 33
of 57 of the reviewer's labels - a nearly-competent majority class and an
incompetent minority class combined into 0.521 and read as one flat failure.

So Experiment 9's conclusion is corrected: the gap was there, and the
instrument was too coarse to show it. What was true is narrower - no gap is
visible *in a five-way confusion matrix*, which is not the same as no gap.

**The redesign, submitted 2026-07-30.**
`src/llm_extraction/attribution_rescue.py` asks the two binaries
independently, as the framing redesign asks its four frames. Both-yes is
`mixed` and both-no is `none`, so the 8 human labels using `mixed` or
`unclear` - 14% of the sample, against which the model used neither value once
in 57 records though both are in its enum - stop being structurally
unpairable. Nothing asks which attribution is principal, so the rule that only
the reviewer received disappears.

Beyond the split it states a bar, because the credit figures say the model's
bar is far below the reviewer's. An attribution requires all three of: a named
party or administration; a specific outcome that already exists; and a
statement in the article linking the two. Three exclusions name what
pre-election coverage is full of - a promise or manifesto pledge is not an
attribution because the outcome does not exist yet; a politician defending a
record or rejecting criticism is not being credited; and being named in a
candidate list or quoted on another subject is not being blamed or credited.

**The scoring rule was declared before submission,** this layer's verdict
having already moved twice under scoring corrections that were both real
faults. Each binary is judged alone. Human `mixed` is positive for both,
`unclear` excluded from both. A binary with fewer than 10 human positives is
`undetermined_insufficient_positives` rather than failed - the framing
rescue's minimum, for the framing rescue's reason.

**A prediction recorded in advance.** The reviewer's credit positives number
8, below that minimum, so **credit is expected to return undetermined rather
than pass or fail.** Blame, at 36 positives and a derived 0.564, is the binary
that can be settled on this sample. That matters for what is at stake:
`blame_count` and `recency_weighted_blame` need the blame binary only, while
`credit_count` and `net_attribution` need credit. Blame clearing on its own
recovers two of the layer's four pre-registered features and no more.

The derived 0.564 is a **lower bound**, not a forecast. It comes from a prompt
that was never asked "does this article blame someone, yes or no" - the answer
was reconstructed from a multi-way field. Asking directly is the intervention
that took stance from 0.32 to 0.85 and consequence's presence axis from 0.318
to 0.598.

**Result: the redesign failed, and made the working half worse.** Both arms
returned in three minutes, 60 of 60 clean on each.

| arm | binary | n | human pos | model pos | revised kappa | frozen kappa | verdict |
|---|---|---|---|---|---|---|---|
| Sonnet | blame | 55 | 39 | **21** | **0.272** | 0.564 | fails, and 0.292 worse |
| Haiku | blame | 55 | 39 | **23** | **0.319** | 0.565 | fails, and 0.246 worse |
| Sonnet | credit | 55 | 8 | 15 | 0.302 | 0.181 | undetermined (8 positives < 10) |
| Haiku | credit | 55 | 8 | 13 | 0.245 | 0.483 | undetermined (8 positives < 10) |

Inter-model: blame 0.610, credit 0.442 over all 60 shared articles.

**The cause, which is a design error of mine and not a model failure.** I
wrote a symmetric bar for an asymmetric problem. Credit needed tightening -
the model over-called it three and a half times. Blame did not: its marginals
already matched at 36 human positives against 34 from the model. But the three
conditions and the three exclusions applied to *both* questions, so the rules
written to curb credit suppressed blame as well. The model's blame positives
fell from 34 of 52 under the frozen prompt to 21 of 55 under the redesign,
against the reviewer's 39. Everything the bar excluded - a promise, a
politician defending a record, a party merely being named - the reviewer
evidently was counting as blame in a fair number of cases.

Credit moved the direction the diagnosis predicted on Sonnet, 0.181 to 0.302,
which is the only part of this that behaved as designed. It cannot be a
verdict: the reviewer's 8 credit positives sit below the 10-positive minimum
declared before submission, so both arms report `undetermined` regardless of
their figures.

**The layer is dropped, and no third attempt is made.** Not because no further
idea exists - the obvious one is an asymmetric design, leaving blame
unconstrained and applying the bar only to credit. It is not run because that
prompt would be chosen entirely on what these 60 gold-labelled articles just
showed, which is fitting the instrument to the evaluation set. Attribution has
now had two attempts, the same as stance, framing and consequence; a third
would be one more than any other layer received, and chosen with the answers
in hand.

There is no salvage in the frozen output either. The derived blame binary at
0.564 is the best figure this layer produced on any instrument, and it is
still below 0.600.

**What is lost:** all four features - `blame_count`, `credit_count`,
`net_attribution`, `recency_weighted_blame`. The supervisor's brief lists
blame and credit attribution explicitly, so this is a gap the report has to
state rather than route around.

---

## Experiment 13: the far gate failed twice, and twice it was my fault

**far, first draw.** 89 articles from the two untested windows. issues failed
at 5.6% schema failure against a 5% bar - five records failing five different
ways: one unparseable, one span not verbatim, three where the model volunteered
a property the schema forbids. Six more were saved by the review-flag repair,
without which the layer would have failed at 12.4%. stance and framing passed
clean.

**The prediction in the code was wrong, in the opposite direction.** Empty
records were expected to rise on far articles; they fell. issues went 22.5% to
5.6% and framing 34.8% to 16.9%. Articles three to six months out carry more
codeable political content than the final weeks, which are thick with
candidate lists and election notices.

**far2, second draw, after a prompt fix. Worse: 12.4%.** The fix added a rule
naming the fields the schema provides for anything that will not fit - and it
named `issue_other`, which does not exist. The real field is
`issue_other_label`, and it sits inside each issue object, not at the top
level. Eight of the eleven failures were the model obediently using the field
I told it to use.

My verification was `'issue_other' in prompt`, a substring test, which passed
because `issue_other_label` contains `issue_other`. The check was incapable of
catching the error it was written to catch.

**far2 also reported quote verification at 0.0%, and that figure was an
artefact of my own checker.** The health check re-derived the tranche by
calling `load_tranche(tranche)`. But the far sampler now excludes articles that
previous far draws used, so re-deriving `far2` *after* collecting it returns a
third, different 89 articles - and the checker then looked for far2's evidence
spans in articles far2 had never seen. 0 of 314. Re-run against the articles
far2 actually extracted, verification is **99.4%**.

So far2's real result is one failure, not two: schema 12.4%, of which eight
records are traceable to my wrong field name.

**Two fixes, and what each is for.**

`load_tranche` takes an `only_ids` argument, and the health check passes the
article ids read from the tranche's own output. A gate must not re-compute its
own subject: the tranche rules are not stable over time, and any reader of a
tranche after the fact needs the articles it actually used. This is the
structural fault of the two, and it could have failed a sound extraction at any
point.

The issues prompt's rule 7 now lists the permitted keys explicitly at both
levels - eight at the top, five inside an issue object - and names
`ambiguity_notes` at the top level and `issue_other_label` inside the issue.
Verification is now a set comparison against the parsed schema rather than a
substring search: every name in the rule is checked to be in the schema, and
the two name sets are checked to be complete. Prompt version v1.3.

**far3 is the third draw, under v1.3, and is the real test of whether the
field name was the whole problem.** If schema failure returns to the 3.4% the
non-name failures imply, the diagnosis holds. If it does not, the diagnosis was
wrong and the layer needs a different answer.

**A note on how many attempts this layer has had.** Three far draws, each on
articles the previous draws had not seen, because both intervening changes were
corrections of my own errors rather than tuning against results. The
distinction matters and is not self-certifying: a reader should count three
attempts and discount accordingly.

---

## Experiment 14: what the Reform sample actually looks like

Not an extraction experiment, but the finding that bounds every result the
project can produce, so it belongs in the same record.

The baseline holds 1,613 party-contest rows, 97 of them Reform UK. The
distribution is the constraint:

| where | Reform rows |
|---|---|
| 2026 East Surrey | 36 |
| 2026 West Surrey | 45 |
| **2026 total - the protected holdout** | **83 (86%)** |
| 2021 | 6 |
| ten by-elections, one row each | 10 |

`new_party_indicator` is true for all 97. And the UKIP-predecessor bridge is
nearly empty: `previous_ukip_vote_share_in_area` is a non-zero observation on
**5 rows** (3, 3, 3, 4 and 8 per cent), an observed zero on 81, and
unavailable on 11. Reform's own prior share is observed on 40 rows. So by the
last comparable election UKIP had effectively vanished from Surrey, and the
inheritance hypothesis cannot be tested on this data. That is an empirical
finding to report, not a data problem to fix.

**What it constrains.** The evaluation sample for Reform is 83 held-out rows,
which is workable. The *training* sample for anything Reform-specific is 6
rows, which is not. So the model must be party-generic - one set of
coefficients learned across all 1,613 rows and applied to per-party feature
values - and Reform must be an evaluation target reported separately, never a
training subpopulation. Any Reform conclusion rests on one election and cannot
claim to generalise over time.

**Why this is the premise rather than a defect.** The question is whether news
improves on an election-history-only baseline. For Reform, election history is
close to empty by construction: a new party, in every ward, with no measurable
predecessor. That is precisely the party where news has room to add
information, and a baseline that predicts Reform poorly is the expected result
and a finding in itself. What cannot be improved is the row count. What can be
improved is how much news each 2026 contest has behind it.

**A correction to the corpus figures.** The claim that 918 articles remain
un-adjudicated, which appears in `run_corpus_extraction`'s docstring and was
repeated in conversation, does not reconcile. The decisions table holds 2,370
rows, all resolved - 1,452 include and **918 exclude**. The docstring's 918 is
`3,584 - 2,666`, a different quantity that shares a value by coincidence, and
its 2,666 does not match the table's 2,370 either. Whether any article cleared
the mechanical rules without receiving a judgement is **not yet established**,
and no estimate of outstanding review effort should be relied on until it is.

---

## Experiment 15: the gate passes, and three holes found before it did

**Three faults, all mine, all found by tracing the code path the full run
would actually take rather than by reasoning about the plan.**

**The retry would not have applied to the corpus.** It was written into the
synchronous path, and the corpus runs on batches, so the full run would have
reproduced the 10% issues failure rate the retry exists to remove. Wired into
the batch collector, sending the failed fraction at standard rate rather than
waiting on a second batch.

**The prompt fingerprint would have been false.** It was computed at collect
time while the prompt is used at submit time, and the issues prompt changed
three times in one afternoon - so records would have been labelled with a
prompt they never came from. Provenance that looks real and is not is worse
than none. The fingerprint is now written into the manifest at submit and read
from there; on a mismatch collect warns and refuses to retry, because a second
attempt on a different prompt is not the same attempt.

**`cmd_collect` would have extracted the wrong articles.** It called
`load_tranche(tranche)`, which re-derives - and the far sampler excludes
articles previous far draws used, so re-deriving far3 after collecting it
returns a fourth, different sample. Measured: **overlap with far3's real
articles was zero**. A re-collect would have extracted 89 unrelated articles
and overwritten the record of what was actually run. The manifest now carries
`article_ids` and collect loads by them, falling back to the outputs file and
warning if it must re-derive.

The second and third were found only because the plan was checked against the
code before running it. The first was found the same way. All three would have
been invisible in the output.

**Prompt provenance, backfilled and labelled.** The issues layer ran on three
prompts - v1.1 for narrow and far (170 accepted records), v1.2 for far2 (78),
v1.3 for far3 (89) - and until now the version sat only at the top of each
tranche file, so a merged feature table would have lost it. Verified against
git: v1.1 is byte-identical across all eight pre-rule-7 commits at 9,240
characters, and the backfill refuses to write anything if its reconstruction
fails to reproduce that hash. **v1.2 cannot be reconstructed** - it existed
only in the working tree between two edits and was never committed - so those
records carry a null hash and `unrecoverable_prompt_never_committed` rather
than an invented value. `max_tokens` is stamped separately because nine far3
records had come from a diagnostic run at 16,000 against production's 8,000.

**far3 re-run at production settings, through the retry path.**

| | first pass | after one retry |
|---|---|---|
| issues schema failure | **8 of 89 (9.0%)** | **1 of 89 (1.1%)** |
| recovered on retry | - | 7 of 8 |
| review-flag repairs | 5 | 5 |
| quote verification | - | **100.0%** |
| empty records | - | 4.5% |

stance_revised 0.0% / 0.0%; framing_revised 0.0% after recovering 2 of 2 on
retry, 24.7% empty against a D4 baseline of 40.0%. **Gate: PASS.**

The first-pass rate replicated the earlier run's 9 of 89, so the verdict turns
on the retry rather than on a lucky draw. All 89 records now carry v1.3 and
max_tokens 8,000 - the nine at 16,000 are gone, which is what made the
previous pass dishonest.

**Evidence the retry is not cherry-picking.** The one residual failure failed
**both** attempts, with different errors each time - a primary code repeated
in `secondary_issues`, then an invented `duplicate_note_unused` property -
both at `stop_reason: end_turn`. Both error sets are retained and the record
stays failed. A mechanism that preferred the nicer attempt would have passed
it.

**Why re-running the same 89 articles does not contaminate this gate.** The
gate measures format compliance and traceability, not agreement: "is this span
present in the article" is an objective fact and "does this output satisfy the
schema" is another. There is **no answer key to overfit to**, which is exactly
what distinguishes it from D4, where the reviewer's labels are a gold standard
and repeated attempts on the same articles would be selection. What would be
illegitimate is re-running until it passes; this was the first production-
settings run with retry, and it passed.

**The caveat that remains.** The record kept is the first attempt satisfying
the validator, which is selection over attempts. The validator checks that
evidence spans appear verbatim, so attempts with fewer or shorter quotations
are marginally likelier to pass, and retained records may under-represent long
or paraphrase-prone quotation. `attempts` is recorded per article, so the
affected records are identifiable.

---

## Experiment 16: the corpus extracted

**What ran.** 1,374 articles on three layers, prompt v1.3, 2026-07-30. The
tranche is 1,374 rather than 1,638 because 258 articles were already extracted
cleanly by the narrow, far and far3 tranches and are skipped, and 6 have no
text. far2's 89 articles re-entered: its `issues` layer is marked superseded
because the v1.2 prompt named a field the schema does not define, so the
records that passed were selected on content - articles whose issue fell
inside the taxonomy - with invented-field failures at 9 of 89 against 1-2 of
89 under v1.1.

**Batch latency, against everything the 89-article tranches suggested.** All
three batches ended in **7 to 9 minutes** with zero errors, on 1,374 / 1,006 /
1,374 requests. The same-day 89-article Sonnet batches took 15 to 90 minutes
and two sat at zero completions for over an hour. So batch latency is not a
function of size, and nothing about it can be predicted from a small tranche.

**First-pass failure replicated the gate.**

| | first pass | after one retry |
|---|---|---|
| issues | **146 of 1,374 (10.6%)** | **28 (2.0%)** |
| stance_revised | 8 of 1,006 (0.8%) | 0 |
| framing_revised | 0 of 1,374 | 0 |

far3 measured 9.0% on 89 articles; the corpus gave 10.6% on 1,374. The gate's
estimate held, which is the first direct evidence that the 89-article tranche
was representative rather than lucky.

**The retry recovered 118 of 146 issues records, 80.8%,** and 8 of 8 on
stance. Its value is not the percentage but which articles it returned:
failure correlates with length, so without the retry the corpus would have
lost 118 disproportionately long articles' issue data.

**Post-run report - the same four checks, run as a report rather than a gate,
because the money was already spent.** issues 2.0% schema failure and 99.8%
quote verification; stance_revised 0.0%; framing_revised 0.0% with 21.2% empty
against a D4 baseline of 40.0%. Against the rule stated before the run - at or
under 3% proceed, 3 to 8% record as a limitation and check whether failures
concentrate, over 8% stop - **2.0% proceeds.** Cost $30.40, $0.0221 per
article.

**True coverage, after deduplicating by article.**

| layer | unique articles | of 1,632 |
|---|---|---|
| framing_revised | **1,632** | 100.0% |
| issues | **1,604** | 98.3% |
| stance_revised | 1,187 | 72.7% |

stance's 72.7% is not a shortfall: the layer is only asked about articles that
name a study party, and 445 name none, so its denominator is 1,187 by design.
issues loses 28 articles that failed both attempts.

**A duplicate-counting hazard found while checking those totals, and it is not
an extraction fault.** Concatenating the tranche files double-counts articles,
because far2's `stance_revised` and `framing_revised` records were left in
place while its articles were re-extracted - only `issues` was superseded.
Measured: **98 articles appear twice for framing and 66 for stance**, 89 and 58
of them from far2. Raw row counts therefore exceed the corpus - framing showed
1,730 rows against 1,632 articles.

Left uncorrected this would inflate every volume feature for the elections
those articles belong to. The fix belongs in the feature table rather than in
the extraction: deduplicate on `article_id`, preferring the most recent
tranche, and **assert that unique articles never exceed the corpus size** so
the same class of error cannot pass silently again.

**Provenance on these records is live rather than reconstructed.** Every
accepted record carries the prompt fingerprint written into the manifest at
submit time - `715700666aca` for issues, `bc2d5987b2d7` for stance,
`e90e50b3dcb2` for framing - not a hash derived afterwards. Two issues records
carry null because neither attempt produced a parseable record at all.

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
| consequence (3) | **unavailable** | frozen layer fails (0.259 human, n=55). Redesign reaches 0.598 on presence on both arms - Sonnet and Haiku alike - 0.002 below the gate; excluded |
| credit_blame (4) | **unavailable** | 0.521 / 0.516 human at n=57; fallback route not triggered (marginal 0.579). Redesign run on both arms: blame 0.272 / 0.319 against the 0.600 gate, credit undetermined at 8 human positives (minimum 10); excluded |
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
consequence is excluded: both redesign arms report kappa 0.598, 0.002 below
the gate.

Against the version written after Experiment 7, this loses the four
attribution features and the three consequence features outright. The challenger-emergence frame remains the sharpest gap, being the
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
Experiment 7, plus $0.16 for the consequence redesign's two arms, both reported,
and the attribution redesign's two arms, whose token usage is recorded in
`attribution_rescue_agreement.json`. The 89-article narrow tranche, which is a production
run rather than an experiment, cost $1.82 on the three layers being kept and
$1.66 on the consequence layer that Experiment 8 then excluded - that $1.66
is a real loss, incurred because the tranche was submitted before Experiment
9's confusion matrix had been built.

The gate stopped a full-corpus run that would have produced four unusable
feature blocks. Three redesigns it forced recovered the most theoretically
important of them (per-party portrayal, in full), half of another (framing),
and brought a third to within 0.002 of its bar without clearing it.
