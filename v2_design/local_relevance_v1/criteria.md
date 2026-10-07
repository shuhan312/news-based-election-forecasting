# Local relevance classifier: evaluation criteria (written before any run)

**Status: fixed 2026-10-07, before any classifier output was compared with a
human label.** The split (`split.csv`, produced by
`src/v2_design/local_relevance_split.py`) is committed together with this
file. Neither is changed after results are seen. Later changes go under
Amendments, with their reasons.

## Why

The multi-council expansion needs local news screened automatically.
`v2_design/feasibility_probe_v1` locates the bottleneck there. V1's frozen v2
classifier (claude-sonnet-5) failed the local relevance rule decisively:
kappa 0.165 on 49 pairs, against a 0.60 bar (`news_protocol/
eligibility_manual_review_methodology.md` §9). Of the 30 disagreements, 26
were human-include → model-exclude, because the model did not know which
places lie in which Surrey division. The hypothesis under test is that
supplying that geography at classification time fixes the failure.

## The task

Binary local relevance under V1's unchanged rules
(`news_protocol/article_eligibility_rules.md`): **include** if the article
meets any of L1 (names a Surrey division, or a place within one), L2 (names
a candidate or sitting councillor in a civic context), L3 (a Surrey council
decision or service that identifiably affects a place) or L4 (Surrey-wide
political coverage). Otherwise **exclude** (E5). Any model output other than
include counts as exclude.

## Data

| | include | exclude | total |
|---|---:|---:|---:|
| dev | 99 | 115 | 214 |
| **test** | **60** | **106** | **166** |

- Reference labels are V1's manual local E5 decisions, made by one human
  reviewer. They are a reference standard, not ground truth. The single
  unresolved row is excluded.
- The test set is half of the 333 corpus rows, drawn by a salted hash within
  each label.
- Dev also holds the 47 resolved local rows of V1's validation sample. The
  frozen v2 classifier has already been scored on those, so they are not
  fresh.
- **The test set is used only for the final evaluations listed below.**
  Prompt and context design, error reading and model choice happen on dev
  only.

## Arms

- **B0, baseline (no API cost):** the archived output of V1's frozen v2
  classifier on the same articles
  (`news_collection/manual_review_llm_v2_corpus.csv`).
- **G1, geography-grounded:** the same rules, plus context retrieved
  deterministically before the call:
  1. Surrey place names found in the text, each mapped to its district and
     county electoral division (from an official gazetteer such as the ONS
     Index of Place Names or OS Open Names, cited at build time);
  2. candidate names found in the text, matched against the election's
     candidate list (names only; no vote or result column is read).

  The model is chosen on dev. Under the standing cost policy, a cheaper
  model must clear the same gate to be used.

## Test-set budget

At most **two** finalist configurations are evaluated on test, each exactly
once, plus B0. Every test result is reported, including any finalist that
fails.

## Gate

A configuration passes only if, on test:

| measure | bar | why |
|---|---|---|
| Cohen's kappa vs human (binary) | **≥ 0.60** | V1's pre-registered bar, unchanged |
| include recall | **≥ 0.75** | V1's failure was missed includes. A classifier that wins kappa by excluding liberally would silently empty the local feature layer |

95% bootstrap intervals (2,000 article resamples) are reported for both, but
the gate is read on the point estimates, as in V1.

## Decision

- **Pass:** G1 becomes the local screening step for the multi-council
  pilot. Before Kent results are used, a Kent transfer check follows: a
  fresh, human-labelled Kent sample of about 100 articles, the same gate,
  and a Kent gazetteer.
- **Fail:** record the result. Read dev errors to decide whether the gap is
  retrieval (missing places), the rules, or the reference labels. Do not
  re-test on test without a new, committed amendment and a fresh test
  sample.

## Known limitations, stated in advance

- One human reviewer. Agreement with that reviewer is the measurable target.
- Surrey only. Transfer to other councils is a separate check (above).
- The 248 Guardian rows in this set are national-outlet articles about
  Surrey places. Pilot data from local outlets may differ in mix.

## Amendments

(none)
