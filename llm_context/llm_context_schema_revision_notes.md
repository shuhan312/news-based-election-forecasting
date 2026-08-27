# Schema and pipeline revision notes after the Step 2 pilot

> **Historical checkpoint.** This document preserves the project status at
> the time of this pilot-stage review. Statements such as "pending", "not
> yet run" and "provisional" describe that historical checkpoint, not the
> current repository state. Full-corpus extraction and the final D4 gate
> decisions were completed later. See `d4_findings_log.md`,
> `d4_gate_outcome_and_decisions.md` and
> `corpus_extraction_batch_digests.json` for the final status.
> The proposals below were later implemented through versioned
> schema, taxonomy and prompt updates; this file is retained as
> the pre-implementation decision record.


Status: PROPOSALS - none applied yet. Schema changes ship as
taxonomy/schema version bumps (never edits under the same version);
prompt changes take effect in the full-scale run's system prompt.
The pilot validated against `llm-context-v1.1-2026-07-26` unchanged.

## Schema changes (would create issues taxonomy v1.2)

1. **Add `election_administration` to the issue taxonomy.** Two
   pilot articles needed it (polling-day logistics stories); the
   code exists in the event-type enum but not the issue enum, so
   conformant outputs were impossible for that content. Low-risk
   additive change.

That is the only schema-level defect the pilot surfaced. All eleven
layers were populated correctly somewhere in the sample; no field
was systematically unusable, none needs removal or restructuring.

## Prompt changes (no schema version bump needed)

2. **Verbatim-span hardening**: add "copy evidence character-for-
   character; NEVER shorten a quote with ...; if a passage is long,
   choose a shorter contiguous span instead" - targets the dominant
   error (8 R1 rejections from ellipsis-abbreviated quotes).
3. **Drop offsets**: instruct the model to omit char_start/char_end
   (one R2 failure; offsets are recomputable deterministically from
   the verbatim text and add no value from the model).
4. **Leakage evidence**: "any contains_poll / contains_prediction /
   contains_election_result flag requires an evidence span" stated
   explicitly (one R7 failure).

## Pipeline parameters (already applied during the pilot)

5. `MAX_TOKENS` 16000 -> 40000 (fixed the 14 truncations).

## Cost levers for the full-scale run (decision pending)

6. Output length drives cost (~10.6k tokens/article). Worth testing
   `output_config.effort: "medium"` on a dozen pilot articles - if
   validation rates hold, the full-corpus cost drops meaningfully
   below the ~$85-95 projection. Intro batch pricing ends
   2026-08-31; the full run should land before then.
7. Keep: Batches API (50%), cached shared system prompt, single
   frozen model claude-sonnet-5.
