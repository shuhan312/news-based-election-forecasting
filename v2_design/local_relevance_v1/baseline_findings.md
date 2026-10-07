# Local relevance baseline (B0): findings

**2026-10-07.** Criteria and split were committed first (commit 6d1fd38).
Produced by `PYTHONPATH=src python -m v2_design.local_relevance_eval` →
`baseline_b0.json`. No API call was made.

## Headline

V1's frozen v2 classifier (claude-sonnet-5) **passes the pre-registered gate
on the held-out test set**:

| | n | kappa [95% CI] | include recall [95% CI] | agreement |
|---|---:|---|---|---:|
| **test** | 166 | **0.703** [0.579, 0.810] | **0.833** [0.732, 0.921] | 0.861 |
| dev, corpus rows | 167 | 0.662 [0.536, 0.772] | 0.867 | 0.838 |
| dev, V1 validation rows | 47 | 0.118 [0.037, 0.232] | 0.282 | 0.404 |

## Why V1 recorded a failure: the reference labels applied the wrong rule set

The codebook routes local-arm articles to the L-rules only. In the 47
resolved local rows of V1's validation sample, the human reviewer's reason
codes show that this was not followed:

| human reason | human label | model include | model exclude |
|---|---|---:|---:|
| L-rule | include | 7 | 1 |
| **N-rule** | **include** | 4 | **27** |
| N-rule | exclude | 0 | 8 |

31 of the 39 human includes were justified by **national** rules (party
politics, policy issues) on local-arm articles. The model applied the L-rules
as instructed and excluded 27 of them. Where the human used L-rules, the
model agreed 7 of 8 times. In the 333 later corpus rows the reviewer used
L-rule codes consistently, and agreement is high.

V1's §9 explanation ("26 of 30 disagreements are missing ward geography") is
therefore **not supported**. The dominant cause was a rule-set mismatch in the
reference labels, not model ignorance of geography. The geography-grounded
arm G1 loses its motivation and is not run (amendment A1).

## What this does not settle: local outlets

The test set is 72% Guardian articles that mention Surrey places. On the
local-outlet rows (SurreyLive, BBC Surrey, Guildford Dragon, Surrey Comet):

| | n | human include | kappa [95% CI] | include recall | agreement |
|---|---:|---:|---|---:|---:|
| dev | 43 | 36 | 0.235 [−0.12, 0.56] | 0.833 | 0.767 |
| test | 43 | 37 | 0.546 [0.16, 0.83] | 0.865 | 0.861 |

Kappa is unstable here because these rows are 84–86% include. They were
pre-filtered by V1's targeted searches. V2's outlet-first collection will
instead feed the classifier everything an outlet published (sport, crime,
weather), so the relevant base rate will be far lower and **precision**,
untested here, becomes the binding metric.

## Consequences for V2

1. **Local relevance screening is not the hard blocker V1 implied.** On
   consistently labelled data the frozen classifier already meets V1's bar.
2. **The remaining risk is population shift.** The next evaluation must use
   a random sample of unfiltered local-outlet articles, human-labelled
   blind to any model output, ideally from Surrey and Kent.
3. **A lesson worth keeping:** before fixing a model failure, audit the
   reference labels. Here the "model failure" was mostly in the labels.

## Caveats

- **The 333 corpus labels are AI-assisted human decisions, not independent
  ones.** The reviewer confirmed (2026-10-07) applying criteria an AI
  assistant had drafted and using AI help to analyse articles, while making
  every final decision personally. Agreement with B0 (also a Claude model)
  therefore partly measures AI-AI consistency and may be inflated by shared
  errors. The test pass is evidence that B0 matches the AI-assisted
  adjudication standard. It is not an independent validation. The N-rule
  explanation of V1's validation failure rests on the reviewer's own reason
  codes and is unaffected.
- Kappa CIs are wide at n = 166, and much wider on the local-outlet subsets.
