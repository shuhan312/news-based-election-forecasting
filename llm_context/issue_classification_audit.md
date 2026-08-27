# Issue / topic classification - audit (Phase 6 Step 3)

> **Historical checkpoint.** This document preserves the project status at
> the time of this pilot-stage review. Statements such as "pending", "not
> yet run" and "provisional" describe that historical checkpoint, not the
> current repository state. Full-corpus extraction and the final D4 gate
> decisions were completed later. See `d4_findings_log.md`,
> `d4_gate_outcome_and_decisions.md` and
> `corpus_extraction_batch_digests.json` for the final status.
> The v1.3 taxonomy was subsequently adopted for production.


Contract `issue-cls-v1.0-2026-07-27` | prompt
`issue-cls-prompt-v1.0-2026-07-27` | rules
`issue-cls-rules-v1.0-2026-07-27` | taxonomy `issues-v1.2` (the
approved 25 codes + other; no invented categories - enforced by
enum) | model `claude-sonnet-5` | batch
`msgbatch_01Du9za8v81VBqv233EqmeZ2`, 67 articles, ~$0.9. Raw outputs
with verbatim quotes: `issue_classification_outputs.json` (out of
Git under the copyright policy).

## Scope decision (recorded)

Small-scale first, mirroring Step 2: the classification ran on the
SAME 67-article stratified pilot sample (method already versioned in
`llm_context_pilot_sample_v1.csv`). The full-corpus run (1,535
articles, ~$25-30) is specified and ready
(`run_issue_classification submit full`) and awaits the budget
conversation with the supervisor. Reusing the Step 2 sample also
enables the cross-layer stability check below.

**Design decision - inputs.** The classifier reads the article TEXT
and metadata only. Step 2's entity output is deliberately NOT fed in
(not even as an auxiliary hint): an entity list would anchor the
model toward entity-adjacent codes ("Reform UK appears, so the issue
must be new_party_emergence") - exactly the error mode to avoid.
Step 2's issues are used only AFTER the fact, as an independent
cross-check.

## Schema compliance

| outcome | articles |
|---|---|
| fully valid (structure + S1-S6) | **57 (85%)** |
| validation errors (all caught, quarantined) | 10 |
| unparseable | 0 |

## Taxonomy consistency and coverage

- Zero invented categories (the enum makes them structurally
  impossible; none attempted as values - three records instead
  invented extra FIELDS, rejected by additionalProperties).
- All 67 records stamp taxonomy issues-v1.2;
  `election_administration` (the Step 2.5 addition) served as
  primary in 3 records.
- Primary-issue distribution (valid records): healthcare 8, other
  6, immigration 4, social_care 4, council_finance 3,
  election_administration 3, then a long tail across 12 further
  codes; **22 records legitimately empty** (letters pages,
  non-political editorials - honest None, no forced codes).
- Coverage note for the supervisor: 23 records have no primary
  issue, mostly NATIONAL-arm articles - the approved taxonomy is
  local-issue oriented and has no national-politics codes. Options
  for the full run: accept None/other as "not locally codable"
  (current behaviour, defensible) or propose a v1.3 with national
  codes. Decision deferred; no code invented meanwhile.

## Evidence completeness and confidence

157 issue assignments across valid records, every one carrying a
verbatim-matched quote and an explanation (both structurally
required). Confidence mean 0.706, min 0.40; 8 records self-flagged
for review, and rule S2 caught 5 more that under-flagged - low
confidence cannot pass silently. Political relevance: 18 records
election-competition-related, each with supporting evidence (S4).

## Cross-layer stability (Step 3 vs Step 2, same 67 articles)

Two independent prompts read the same articles: primary-issue exact
agreement **61%**, primary-appears-in-other's-set **67%**, any
code overlap **72%**. Half the disagreements are Step 3 returning
None where Step 2's full-schema pass gave a weak "other" - the
focused prompt with the hardened never-force rule is MORE
conservative, which is the intended direction. Remaining
disagreements are adjacent-code choices (e.g. candidate_party_conduct
vs crime_policing for a misconduct story) - flagged as inherent
taxonomy ambiguity for the human-review protocol at full scale.

## Manual review (representative subset)

Read closely against the articles: a LOCAL multi-issue campaign
piece (Davey/Reform: voter_switching primary + five grounded
secondaries incl. potholes, sewage, fly-tipping - all quotes
verified), a NATIONAL live blog (social_care primary + five
secondaries, correct primary/secondary hierarchy), a REFORM article
(relevance actors listed from the text), and a letters page
(correct None + not relevant). No unsupported assignment found in
the reviewed subset.

## Verdict

The issue layer validates at pilot scale with the same safeguards
holding as in Step 2, and is ready to support the later stance,
framing, blame/credit and consequence layers. Full-corpus run
pending budget sign-off. No downstream prediction or embedding
stages were started.

---

# Addendum: taxonomy v1.3 gap re-run (Step 3 follow-up)

Following the two decisions in `issue_layer_decisions_v1.md`, the 29
pilot articles whose primary issue was None or "other" were re-run
under prompt issue-cls-prompt-v1.1 / taxonomy issues-v1.3 (batch
`msgbatch_01Nzzj8GHJZCPGxcb8iqhDgm`, ~$0.35). Outputs:
`issue_classification_gap_rerun_outputs.json` (out of Git).

## Primary-issue movement (old -> new)

| movement | n | reading |
|---|---|---|
| None -> national_politics | 7 | the gap the new codes exist for |
| None/other -> national_economy | 6 | ditto |
| other -> national_politics | 2 | ditto |
| None -> healthcare / scandal | 3 | second reading found a SPECIFIC code - the "prefer a specific code" instruction working |
| None -> None | 9 | genuinely apolitical (letters, colour pieces) - honest emptiness preserved |
| stayed other / None -> other | 2 | residual true "other" |

15 of 29 formerly-uncodable articles now carry a national code; the
9 that stayed None are correctly None. The national-arm issue
composition is no longer blank, so the local-vs-national comparison
in the research design is fully supported.

## Validation

23/29 fully valid. 6 caught errors: 4 records misplaced an
issue_other_label-style field at the issues level (structural
rejection - a prompt nit to fold into the full-scale prompt), 2
under-flagged low confidence (S2 forced them to review, as
designed). Zero invented category values; zero S7 violations - the
new codes only ever appeared under the v1.3 stamp.

## Status

Taxonomy v1.3 remains provisional pending supervisor ratification
(Friday). If declined, the v1.2 pilot outputs stand unchanged and
the gap re-run is discarded; nothing downstream depends on it yet.
