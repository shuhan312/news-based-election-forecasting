# Entity stance / sentiment - audit (Phase 6 Step 4)

Contract `stance-cls-v1.0-2026-07-27` | prompt
`stance-cls-prompt-v1.0-2026-07-27` | rules
`stance-cls-rules-v1.0-2026-07-27` | model `claude-sonnet-5` | batch
`msgbatch_01FybMAQ9oKH5Yt9ntHUQpUF`, 67 articles, ~$1.7. Raw
outputs with verbatim quotes: `stance_classification_outputs.json`
(out of Git under the copyright policy).

## Dataset (recorded)

The SAME 67-article stratified pilot sample as Steps 2 and 3
(method versioned in `llm_context_pilot_sample_v1.csv`: election x
arm quotas, hash-ordered selection, Reform top-up to 10; no manual
selection). Coverage: all four elections, both arms, 10
Reform-mentioning articles. Full corpus was NOT run.

## Schema compliance

| outcome | articles |
|---|---|
| fully valid (structure + T1-T6) | **66 (99%)** |
| validation errors (caught, quarantined) | 1 |
| unparseable | 0 |

The best first-pass rate of any layer so far - the layers' shared
verbatim-evidence discipline appears to be compounding through the
prompt lineage.

## Stance completeness and distributions

263 entity-stance rows across valid records (parties 97, candidates
101, organisations 44, councils 21). Stance: negative 98, mixed 97,
positive 58, neutral 10 - the four-value scale is used across its
range, not collapsing to a binary. Stance origin: journalist
narration 113, both 107, direct quotation 43 - the
narration-vs-quotation distinction the specification demands is
populated throughout. 12 articles carry honest empty stance sets
(procedural notices, non-evaluative pieces). 14 rows record voter
switching, every one with the required from/to detail (T4). No
article-level sentiment exists anywhere - the schema cannot
represent it.

## Evidence and confidence

Every accepted row's quote string-matched the article. Confidence
mean 0.632, min 0.40; 5 rows below 0.5 and every affected record
review-flagged (6 records flagged in total) - T2 held. The single
caught error was one House-of-Lords row whose title quote was not
exact (T1) - quarantined.

## Cross-layer stability (Step 4 vs Step 2 party rows, same articles)

57 comparable (article, party) pairs: stance agreement **60%**
(exact, treating neutral~mixed as adjacent). The dominant
disagreement (15/23) is Step 2's quick pass defaulting to NEUTRAL
where the focused layer, with its richer rubric, reads a definite
positive or negative - the focused layer is more decisive, mirroring
the Step 3 pattern (focused layers read deeper than the
one-prompt-for-everything pass). ~0.6 machine self-agreement is now
a consistent calibration anchor across layers for the coming
human-validation gate.

## Manual review (representative subset)

- LOCAL multi-party (Davey/Reform, 8 rows): all quotes verified;
  stances, origins (Badenoch/Farage negative via direct quotation -
  correctly attributed to quoted attack lines), trajectories and
  challenger readings all defensible on close reading.
- One genuine ambiguity surfaced and is recorded in the error
  analysis: Reform's trajectory judged "losing" from Davey's
  "chances hurt" claim where Step 2 read "gaining" from the
  threat-framing - the article genuinely carries both signals.
- NATIONAL, REFORM and empty-set articles spot-checked: correct
  behaviour including honest empties.

## Verdict

The stance layer validates at pilot scale and is ready to support
the later framing, blame/credit and electoral-consequence layers.
Full-corpus run awaits the budget conversation. No downstream
prediction or embedding stages were started.
