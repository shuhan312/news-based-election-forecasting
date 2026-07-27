# Context Extraction Layer Changelog

Versions never overwrite: every record validates under the stamps
it was produced with, and gate rules (S7/R9-style) forbid new
vocabulary under old stamps. This file records what changed between
versions and why; the final freeze closes the v1 line.

## Schema

* `llm-context-v1.0-2026-07-26` - initial 11-section contract
  (Step 1): mandatory evidence spans, confidence in [0, 1],
  uncertain/null as honest defaults, leakage self-check.
* `llm-context-v1.1-2026-07-26` (Step 2.5) - evidence spans became
  quote-only: character offsets removed from the model's job after
  the pilot showed ellipsis-shortened quotes were the dominant error
  (8 of 9 rejections); verbatim string-match became the sole
  evidence gate. Leakage flags now require evidence + explanation.
* `llm-context-schema-v1-final-2026-07-27` (Step 12) - aggregation
  freeze, no field changes: fixes the eight component contracts, the
  card composition, and the rule that any future change is a new
  version.

## Taxonomy

* `issues-v1.1` - supervisor's approved local issue list.
* `issues-v1.2` - added `election_administration` (pilot articles
  about polling logistics had no code).
* `issues-v1.3` - added `national_politics`, `national_economy`
  (decision D1): 23/67 pilot records had no codable issue because
  national coverage had no home; the codes mirror the project
  brief's own national search topics. Rule S7 forbids national codes
  under pre-v1.3 stamps.

## Per-layer contracts

* `issue-cls v1.0 -> v1.1` - prompt and rules follow taxonomy v1.3.
* `credit-blame v1.0 -> v1.1` - target type `politician` added:
  7 pilot articles could not attribute blame to ministers or party
  leaders under the v1.0 enum (used 50 times once available).
* `elect-consq rules v1.0 -> v1.1` - E3 duplicate key extended from
  (actor, direction, mechanism) to include the electoral signal:
  the narrower key wrongly rejected rows differing only by signal.
  Stored outputs re-validated offline at zero cost.
* `stance v1.0`, `framing v1.0`, `loc-nat v1.0`, `temporal v1.0` -
  unchanged since first release.

## Prompts

* `prompt-v1.0` -> `prompt-v1.1-2026-07-26` - CHARACTER-FOR-CHARACTER
  quoting rule (never shorten with "..."), offsets removed, leakage
  evidence required. Frozen verbatim (all eight layers) in
  `context_extraction_prompt_v1_final.md`; per-layer prompt stamps
  in the version manifest.

## Dataset

* `context-cards-v1.0-pilot67-2026-07-27` - this freeze: 67 pilot
  cards, the reference implementation of the frozen method.
* (planned) `context-cards-v2.0` - full-corpus extraction under the
  SAME frozen schema/prompt/model contracts, released alongside
  after the v2 corpus build; gated by the D4 human validation
  protocol before modelling.
