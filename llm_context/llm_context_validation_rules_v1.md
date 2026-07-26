# LLM context extraction - validation rules (v1.1)

Applies to records claiming `schema_version =
llm-context-v1.1-2026-07-26`. Enforced by
`src/llm_extraction/validate_context.py` in two deterministic layers.

## Layer 1 - structural (JSON Schema Draft 2020-12)

The schema file is the contract: required fields, enums, types,
`additionalProperties: false` everywhere (an unknown field is an
error, not an extension mechanism). Key structural guarantees:

* `schema_version` and `taxonomy_version` are pinned constants;
* every claim object REQUIRES `evidence_span` and `confidence` -
  a claim without evidence is structurally invalid;
* `primary_issue`, `voter_group`, `mechanism`, `linked_surrey_area`,
  `sentiment` are explicitly nullable - "not stated" is representable;
* evidence span text has a 10-character floor - a two-word fragment
  is not auditable evidence;
* confidence is a number in [0,1].

## Layer 2 - cross-field research-integrity rules

| rule | statement | rationale |
|---|---|---|
| R1 | every `evidence_span.text` must appear VERBATIM in the article body (or title when `from_title` is true) | the span is the audit trail; a non-matching span is a fabricated quote and fails hard - this is the anti-hallucination gate |
| R2 | when `char_start`/`char_end` are present, slicing the source text with them must reproduce `text` exactly | offsets that lie poison every downstream span-based analysis |
| R3 | any claim with confidence < 0.5 requires `review_status = flagged` on the record | low-confidence output is surfaced for human routing, never silently included or excluded |
| R4 | a record with no entities, no primary issue and no party context cannot claim `extraction_status = extracted`; an empty partial/failed record must carry an `ambiguity_notes` entry | "nothing found" must be an explicit, reasoned statement |
| R5 | `not_attempted` records must contain zero extracted claims | pipeline states and content must agree |
| R6 | `reform_uk_present: false` forbids positive Reform flags and scores; any positive Reform flag requires an evidence span | the specialised layer must never assert Reform UK emergence without a quote, and absence must be clean |
| R7 | `contains_poll` / `contains_prediction` / `contains_election_result` require an evidence span | a leakage-risk claim is a claim like any other |
| R8 | `party_context` rows are unique per party | one feature row per party keeps downstream joins unambiguous |

## Determinism

Both layers are pure functions of (record, body_text, title): error
lists are sorted, no clocks, no randomness - repeated validation of
identical input yields byte-identical output (tested).

## Versioning and Stage M

* future Stage M articles validate against this same pinned contract;
* extending the issue taxonomy or any enum requires a NEW schema
  version file alongside this one - existing records and their
  version stamps are never rewritten;
* the validator loads whichever schema version the record claims;
  records claiming an unknown version fail structural validation at
  the `schema_version` const.
