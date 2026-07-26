# Narrative framing detection - audit (Phase 6 Step 5)

Contract `framing-v1.0-2026-07-27` | prompt
`framing-prompt-v1.0-2026-07-27` | rules
`framing-rules-v1.0-2026-07-27` | model `claude-sonnet-5` | batch
`msgbatch_01SKYEpK5iV86mHDUbKGKGne`, 67 articles, ~$1.1. Raw
outputs with verbatim quotes: `framing_detection_outputs.json` (out
of Git under the copyright policy).

## Dataset (recorded)

The SAME 67-article stratified pilot sample as Steps 2-4 (method
versioned in `llm_context_pilot_sample_v1.csv`: election x arm
quotas, hash-ordered selection, Reform top-up to 10; no manual
selection). Full corpus was NOT run.

## Schema compliance

| outcome | articles |
|---|---|
| fully valid (structure + F1-F6) | **64 (96%)** |
| validation errors (caught, quarantined) | 3 |
| unparseable | 0 |

## Frame consistency and distributions

234 frames across valid records, all within the specification's
16-category taxonomy - zero invented categories, and notably ZERO
uses of "other": the taxonomy covered everything the sample
contained. Primary-frame distribution: governance_failure 9,
policy_conflict 8, financial_pressure 6, national_political_momentum
5, government_performance 5, leadership 4, integrity 4,
electoral_competition 4, then a tail; 17 records have no primary
frame (13 fully empty - letters, procedural notices - all honest
partial-with-note, zero F5 violations in the valid set).
benefits/damages named only where the article supports it (57 / 112
of 234 frames; the rest null) - the no-unsupported-interpretation
rule holding in the field where it matters most.

## Evidence and confidence

Every accepted frame's quote string-matched the article. Confidence
mean 0.647, min 0.40; 14 records review-flagged, all low-confidence
cases routed (F2). The three caught errors: two non-verbatim quotes
(F1, the familiar ~3% residual) and one primary frame repeated in
the secondaries (F3) - all quarantined.

## Cross-layer stability (vs the pilot's coarse 7-frame layer)

Mapping the pilot's 7 frame categories onto the 16-category
taxonomy, frame-set overlap is **78% (47/60)** - the highest
cross-layer agreement of any layer pair, expected since framing
vocabularies nest more cleanly than issue codes. Consistent with
the ~0.6-0.8 machine self-agreement band now established across
issues, stance and framing for calibrating the human-validation
gate.

## Manual review (representative subset)

- The Eastleigh byelection piece (2013, national): five
  well-differentiated frames - electoral_competition primary,
  with national_political_momentum, local_community_impact,
  challenger_emergence (UKIP's surge, historically apt) and an
  integrity frame for the scandal subplot; mechanisms descriptive,
  benefits/damages grounded.
- Local, Reform-related and empty-set records spot-checked: frames
  distinct from the articles' stance and issue readings (the layer
  is measuring narrative, not re-measuring sentiment), honest
  empties correct.
- One ambiguity class noted for the error analysis: momentum-vs-
  emergence boundary for insurgent parties.

## Verdict

The framing layer validates at pilot scale and is ready to support
the later blame/credit and electoral-consequence layers. Full-corpus
run awaits the budget conversation. No downstream prediction or
embedding stages were started.
