# LLM context extraction - validation rules v1.1 (Step 2.5)

Supersedes the v1.0 rules for all NEW extractions; pilot outputs
validated under v1.0 remain as recorded (traceable via the
rules/prompt version stamps in each outputs file). Enforced by
`src/llm_extraction/validate_context.py` (`RULES_VERSION =
rules-v1.1-2026-07-26`), deterministic in both layers.

## Layer 1 - structural (unchanged shape, two additions)

- `taxonomy_version` accepts `issues-v1.1` OR `issues-v1.2` - old
  records keep validating under their own stamp;
- the issue-code enum includes `election_administration`;
- the leakage object gains an OPTIONAL nullable `explanation`
  (>= 10 chars when present).

## Layer 2 - cross-field rules

| rule | statement | status |
|---|---|---|
| R1 | evidence spans verbatim in body/title | unchanged |
| R2 | offsets, when present, must slice exactly | unchanged (prompt v1.1 stops the model emitting offsets; the rule still guards any that appear) |
| R3 | claim confidence < 0.5 forces review_status flagged | unchanged |
| R4 | empty extractions must be explicit + explained | unchanged |
| R5 | not_attempted must be empty | unchanged |
| R6 | Reform UK consistency | unchanged |
| **R7 (upgraded)** | any contains_poll / contains_prediction / contains_election_result requires an evidence span **AND an explanation** | unsupported leakage classification is now doubly impossible |
| R8 | one party_context row per party | unchanged |
| **R9 (new)** | `election_administration` is only valid when `taxonomy_version` is `issues-v1.2` | a record can never claim a vocabulary it predates - old outputs stay traceable |

## Determinism and Stage M

Both layers remain pure functions of (record, body, title) with
sorted error output - repeated validation is byte-identical. Future
Stage M articles validate against the same pinned schema, taxonomy
v1.2 and rules v1.1; any further change ships as a new version
alongside, never as an edit.
