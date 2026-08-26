# Context Extraction Layer Freeze Report

Phase 6, Step 12. Freeze date: 2026-07-27.
Dataset version: `context-cards-v1.0-pilot67-2026-07-27`
Schema version: `llm-context-schema-v1-final-2026-07-27`
Prompt version: `context-extraction-prompt-v1-final-2026-07-27`

## What is frozen

One context card per article, composing the eight validated
extraction layers (political entities / issues / stance / framing /
credit-blame / expected electoral consequence / local-national
relevance / temporal horizon), the deterministic election windows,
and the Step 10 confidence-and-evidence audit summary. Every card
carries article_id, the final schema version and the dataset
version; every judgement inside a card keeps its own evidence span
and confidence score under its layer's own contract stamp.

The freeze is a contract, not a copy: the eight stored layer output
files are byte-untouched (their sha256 hashes are recorded in the
version manifest and re-checked by the test suite), and the frozen
card file is built from them by a deterministic offline pass
(the legacy `src/llm_extraction/run_freeze.py`, now retained in Git history)
whose recorded rebuild was byte-identical. This pilot freeze is not read by
the final v1/v2 feature builders.
An overwrite guard refuses to replace any frozen file with different
bytes - any future change is a new version released alongside.

## Methodology (summary)

* Corpus: the 67-article stratified pilot sample
  (`llm_context_pilot_sample_v1.csv`), drawn hash-ordered with
  election x arm quotas from the Phase 5 frozen mapping layer
  (canonical, valid-full-text articles only).
* Model: `claude-sonnet-5` (pinned), Anthropic Message Batches API,
  prompt caching on shared system prompts, adaptive thinking;
  per-layer max_tokens in the manifest. The model never saw
  publication dates - temporal separation is by construction.
* Every layer enforced evidence-or-nothing: verbatim quote spans
  validated by string match, honest uncertain/null defaults, and
  confidence < 0.5 forcing review_status = flagged.
* Validation: deterministic per-layer rule series (R1-R9, S1-S7,
  T1-T6, F1-F6, C1-C6, E1-E6, G1-G6, H1-H6) plus freeze rules Z1-Z6.
* Human validation: the protocol is decision D4 (50-article
  stratified human labelling, kappa/AC1 gate >= 0.60); applied at
  pilot scale via close-reading adjudications that produced class
  rulings D6 (inherently-ambiguous genres) and D7 (absence values
  never inherit row confidence). The full D4 kappa pass runs after
  full-corpus extraction, before modelling.

## Validation results

Articles processed: 67 (all eight layers ran on all 67).

Per-layer schema-compliant outputs (of 67; the remainder are
quarantined records kept with their validation errors, contributing
status - never data - to the cards):

| layer | valid | layer | valid |
|---|---|---|---|
| full schema (entities) | 58 | credit/blame | 64 |
| issues | 57 | consequence | 59 |
| stance | 66 | relevance | 65 |
| framing | 64 | temporal | 59 |

Card-level compliance: 67/67 frozen cards pass Z1-Z6 (100%).

Evidence: 2,229 evidence spans in the frozen cards re-verified
verbatim at freeze time - 2,229/2,229 (100%). At the Step 10 claim
level: 5,335 flattened claims, 5,231 evidence-supported (98.1%);
104 claims carry explicitly-recorded absence or span-less values
(63 recorded-missing + 41 span-less definite values), never dropped.

Confidence distribution (5,335 claims): high 828 / medium 3,938 /
low 396 / missing 173.

Manually reviewed: 4 most-flagged articles close-read line-by-line
(ruling D6); the 104-claim weak-evidence-high-confidence class
adjudicated as a class (ruling D7); Guardian version pairs
adjudicated in the Phase 5 freeze.

Review pool at freeze (recorded, not resolved by the freeze):
1,414 claims flagged for review - 875 close under D6, 104 under D7;
remaining open items: 394 genuinely low-confidence claims (routed to
the D4 trial-review + post-full-scale adjudication), 41 evidence
items (31 issue-layer boolean-granularity, fixed in the next prompt
version; 10 genuine, in the adjudication pool), and 2 quarantined
records (1 unparseable, 1 unflagged low-confidence).

## Limitations

* Pilot scale: 67 articles, not the full corpus. Full-corpus
  extraction under these frozen contracts produces dataset v2.0
  alongside; this freeze fixes the METHOD, and the pilot cards are
  the reference implementation of it.
* The D4 human kappa gate has not yet run (by design: it gates
  full-corpus outputs before modelling, and burning its 50-article
  budget on the pilot would double-spend).
* Known contract debts carried openly: issue-layer
  election_competition_related is a span-less boolean under the
  frozen prompt (31 flags); machine cross-layer agreement sits in
  the 0.6-0.8 band, which is the calibration context for the human
  gate, not a defect claim.
* Copyright: the frozen card file contains verbatim quote spans and
  is therefore gitignored (local + OneDrive only); Git carries the
  code, schema, prompts, manifest (with hashes) and this report.

## Downstream contract

Later stages (representation learning, prediction) read
`llm_context_layer_final.json` as fixed input, identified by
dataset version + manifest hashes. No embeddings, contrastive
learning, prediction modelling or feature engineering were started
in this step.
