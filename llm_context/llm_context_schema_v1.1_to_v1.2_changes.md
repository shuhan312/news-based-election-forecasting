# Schema changes: v1.1 -> Step 2.5 refinement

Scope discipline: the schema STRUCTURE is unchanged - same eleven
layers, same record shape, `schema_version` still
`llm-context-v1.1-2026-07-26`. What changed is exactly what the
pilot demanded: the taxonomy version, the prompt version and the
validation rules. Every change is versioned; nothing from the pilot
was rewritten.

## 1. Issue taxonomy: issues-v1.1 -> issues-v1.2

- `election_administration` added (polling arrangements, voting
  procedures, counting arrangements, administration issues). Two
  pilot articles needed it and had no conformant code.
- The schema's `taxonomy_version` field now accepts BOTH stamps -
  old records stay valid and traceable under their own stamp - and
  new rule R9 forbids the new code under the v1.1 stamp, so a
  record can never claim a vocabulary it predates.
- Full code list with definitions: `issue_taxonomy_v1.2.json`.
- v1.1 pilot outputs are untouched.

## 2. Prompt: prompt-v1.0 -> prompt-v1.1

See `llm_prompt_version_v1.1.md`. Three refinements, each targeting
a measured pilot failure: character-for-character quotation (no
ellipsis, no splicing, no reconstruction - 8 R1 rejections), offsets
removed from the model's job (1 R2 failure; recomputable
deterministically), leakage flags require evidence AND explanation
(1 R7 failure).

## 3. Validation rules: v1.0 -> rules-v1.1

See `llm_context_validation_rules_v1.1.md`. R7 upgraded
(explanation required), R9 added (taxonomy-version gating). R1-R6,
R8 unchanged.

## 4. Leakage `explanation` field (additive, optional-nullable)

One new OPTIONAL field on the leakage object so the refined R7 has
somewhere to point. Old records without it still validate
structurally; only records that SET a contains_* flag must supply
it. This is the minimum structural footprint that satisfies the
"leakage flag + evidence + explanation" requirement.

## 5. Output configuration (retained, with pilot justification)

- model: claude-sonnet-5 (unchanged - the project's frozen model);
- MAX_TOKENS: 40000 (retained: the pilot's 16k limit truncated 14
  long extractions because adaptive thinking and the JSON share one
  output budget; at 40k all retried articles completed with
  headroom - observed peak usage ~24k);
- Batches API + cached shared system prompt (unchanged cost
  configuration);
- extraction logic and pipeline code paths unchanged apart from the
  new re-validation subcommands.
