# By-election enrichment: the six-stage walk-through

**Produced 1 August 2026 by `src/news_collection/walk_byelection_pipeline.py`.
Nothing was submitted and nothing was spent.** Every rate below is measured
from principal-election pipeline artifacts; every corpus figure is a count
over files on disk. Machine-readable detail: `walkthrough_report.json`.

## What the corpus actually offers

| measure | value |
| --- | ---: |
| by-election articles on disk | 3,122 across 10 by-elections |
| **excluded: holdout-period by-elections** | **381** (haslemere 2026-07-07, warlingham 2026-05-07) |
| usable for training | **2,741** (1,748 local / 993 national) across 8 by-elections |
| pre-holdout articles mentioning Reform UK (strict pattern) | **411** |
| mean article length | measured from stored text, per report |

The earlier register figure of 425 Reform mentions included the two
holdout-period by-elections; 411 is the trainable figure.

## The two scenarios

| | A: both arms | B: national only |
| --- | --- | --- |
| LLM cost (Batch + cached prompts) | **$12.10–16.49** | $10.49–14.25 |
| manual E5-local review | **~4.5 h** (~175 rows at 40 rows/h assumed) | none |
| projected eligible articles | ~637 | ~572 |
| wall-clock | 3–5 working days | 3–4 working days |
| gives up | — | the only area-attributable-by-construction local text |

The lower cost bound applies while Sonnet 5 introductory pricing lasts
(until 31 August 2026). Expected Reform training records under either
scenario: **~220** (an Estimate under the register's rules: measured
mentions × measured include rate × measured stance-validity rate).

## Rates used, and where each comes from

| rate | local | national | provenance |
| --- | ---: | ---: | --- |
| raw record → review pool | 10.4% | 88.0% | 1,394/13,411 and 2,190/2,488 |
| include among decided | 35.9% | 65.4% | 120/334 and 1,332/2,036 |
| valid stance per include | 81.7% | 81.7% | 1,187/1,452 (register §4) |

A blended "61%" would misprice this corpus: it is local-heavy, and the two
arms funnel completely differently.

## Risks that dollars do not capture

1. **E5-local stays manual.** The automated classifier failed validation
   (κ 0.476 < 0.600); the 4.5 hours are load-bearing and a revalidation
   attempt would be a separate, uncertain cost.
2. **Rate transfer.** All funnel rates come from principal elections; the
   local include rate rests on a 334-row decided subset.
3. **Only share features are safe** given 12–100% search-completeness
   variance — already the frozen feature sets' design, so no new work.
4. **Cross-corpus duplicates** with principal articles are unmeasured and
   would shrink the pool at dedup.
5. **Adaptation time.** The six stage implementations are
   principal-election-shaped; pointing them at by-election ids is
   development time, not dollars, and dominates the wall-clock estimate.

## What this buys the blocked questions

Eight pre-holdout by-elections move the per-election training grain from 2
cells toward 10 and give Reform its first news-training observations
(~220 against the current 0 news rows and the pooled fit's single 2021
residual row). Those are the two structural causes behind four of the seven
supervisor questions being unanswerable (capability findings §5).

## Decision status

The enrichment decision is **not taken here**. This walk-through exists so
it can be taken on numbers. If enrichment proceeds it becomes a
pre-registered model v2 with its own blinded 2026 prediction file; if not,
the project unblinds with v1 alone. Either way the unblinding happens once.
