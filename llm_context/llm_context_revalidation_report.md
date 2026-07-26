# Step 2.5 re-validation report

Prompt `prompt-v1.1-2026-07-26` | rules `rules-v1.1-2026-07-26` |
taxonomy `issues-v1.2` | model `claude-sonnet-5` | MAX_TOKENS 40000 |
batch `msgbatch_01Wz6WcxTEabstXwRpgiXjw8` (19 requests, ~$1.5).
Raw outputs: `llm_context_revalidation_outputs.json` (out of Git -
verbatim quotes). Sample list: `llm_context_revalidation_sample_v1.csv`.

## Validation set (deterministic, recorded)

19 articles: ALL 9 pilot validation failures + 3 review-flagged +
3 Reform-active + 2 leakage-flagged pilot records + 3 longest pilot
articles (truncation regression) + 2 corpus articles with election-
administration title keywords. Ties broken by sha256(article_id);
overlaps kept once.

## Before / after

| | pilot (prompt v1.0) | re-validation (prompt v1.1) |
|---|---|---|
| the 9 previously failing articles | 9 FAIL | **9 PASS** |
| previously-passing articles rerun (8) | pass | all still pass (no regression) |
| new articles (2 admin-keyword) | - | 1 pass, 1 R1 (caught) |
| ellipsis in evidence spans | 8 claims | **0** |
| character offsets emitted | present | **0** |
| leakage flags with evidence + explanation | 1 unsupported flag | **7/7 supported** |
| election_administration usable | impossible (2 articles blocked) | used correctly in 4 records |
| truncation at 40k | - | 0 (longest articles completed) |

Overall: **18/19 valid (95%)**, up from 87% on a set deliberately
stacked with the hardest cases. The single remaining failure is one
non-verbatim quote in a new article - caught by R1 and quarantined,
which is the designed behaviour for the residual model error rate.

## Checks against the specification

- **Schema compliance**: 19/19 parseable JSON; 18/19 fully valid;
  taxonomy v1.2 stamps on all records; v1.1 pilot outputs untouched
  and still traceable under their own stamps (regression-tested).
- **Evidence quality**: zero ellipsis spans, zero reconstructed
  quotes detected; every accepted span string-matched the article.
- **Leakage detection**: all 7 records that flagged polls/
  predictions/results carried both a verbatim span and an
  explanation (upgraded R7 satisfied; unsupported classification
  now impossible by construction).
- **Political context quality**: party rows, candidate rows, Reform
  UK fields, blame/credit and consequence fields populated with
  grounded quotes across the re-validation set (3 Reform records
  re-activated correctly).
- **Reproducibility**: validators are pure functions with sorted
  output (tested); sample selection deterministic; version metadata
  (schema / taxonomy / prompt / rules / model / batch id) embedded
  in every outputs file.

## Remaining risks

1. Residual non-verbatim quotes (~1 article in 19 here) will occur
   at full scale - mitigated by design: R1 quarantines them into
   the review pool, they never enter usable data.
2. LLM outputs are not byte-reproducible across reruns; the frozen
   prompt/model/rules versions plus stored outputs are the
   reproducibility surface, as in the classification pipeline.
3. Intro batch pricing ends 2026-08-31; the ~$85-95 full-corpus run
   should land before then (supervisor sign-off pending).

## Verdict

All three pilot issues are fixed and verified on targeted cases.
The extraction framework is ready for full-scale processing. Full
corpus extraction was NOT started.
