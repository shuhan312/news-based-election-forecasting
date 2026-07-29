# The UKIP contextual sensitivity run, and why it is not selected

**Recorded 29 July 2026.** The brief permits an optional experimental model
using UKIP as a separate contextual feature, on four conditions: Reform UK and
UKIP remain separate; the assumption is clearly labelled; performance is
compared with a model that does not use it; and **"it is not selected unless
it improves genuine unseen Reform predictions."**

This is that comparison. It was run, and the option is not selected.

---

## What the run does

The Reform interaction terms give a linear model a second slope for Reform UK
on four historical predictors. The UKIP block does the same for UKIP: four
further columns, `ukip_x_previous_party_vote_share` and the three county
strength terms, non-zero only on UKIP rows.

It is off by default in `config/baseline_model.yaml` and switched on
explicitly:

```bash
PYTHONPATH=surrey-election-no-news-baseline .venv/bin/python -m no_news_baseline.cli train --ukip-interactions --output surrey-election-no-news-baseline/outputs/model_bundle_ukip_sensitivity
```

**No merging happens anywhere.** UKIP keeps its own party identity, its own
indicator and its own columns. No UKIP row is counted as a Reform observation,
and no Reform metric includes a UKIP row. The block adds information *about
UKIP*; the question is whether having it helps predict Reform.

The code refuses to run the UKIP block without the Reform terms, in the
configuration and again in `attach_interactions` itself. A run with UKIP
history modelled conditionally and Reform's modelled globally would be the
opposite of the study's purpose.

## The result

Everything else identical — same rows, same folds, same seed, same gates.

| | without UKIP (shipped) | with UKIP block |
| --- | ---: | ---: |
| architecture selected | B_gradient_boosted_trees | **A_regularised_linear** |
| all candidates, out-of-fold MAE | 9.85 | **9.13** |
| all candidates, holdout MAE | 4.53 | 4.80 |
| holdout winner accuracy | 30.5% | 28.0% |
| **Reform out-of-fold MAE** | **10.18** | **15.10** |
| **Reform out-of-fold vs equal split** | **+5.0%** | **−41.0%** |
| Reform holdout MAE | 3.33 | 3.21 |
| Reform holdout vs equal split | −11.1% | −7.1% |

**The brief's own criterion is the out-of-fold Reform figure**, because that is
the genuine unseen Reform prediction: fourteen rolling-origin rows, each
predicted by a model trained only on elections before it. On that criterion
the UKIP block takes Reform from **5.0 per cent better than an equal split to
41.0 per cent worse**. The option fails the condition it was given, and is not
selected.

### The overall improvement is real, and is not a defence

Out-of-fold MAE across all candidates improves, 9.85 to 9.13. That is what the
block is doing: UKIP is a substantial party in the 2013–2019 period the
out-of-fold window covers, and giving it its own slopes fits UKIP rows better.
The improvement is UKIP's, and it is bought at Reform's expense.

This is exactly why the brief sets a Reform-specific condition rather than an
overall one. A feature that improves the pooled average while damaging the
study party is not an improvement for this project.

### It also destabilises the selection

| architecture, pooled development Reform MAE | without UKIP | with UKIP |
| --- | ---: | ---: |
| B_gradient_boosted_trees vs A | +8.3% (selected) | −9.1% |
| C_partial_pooling vs A | −2.6% | −1.9% |

With the block on, B stops being an improvement over A at all and the
selection falls back to the incumbent. An added feature that reverses which
architecture wins, while making the study party's unseen predictions worse, is
a feature that is doing something other than adding information.

### The holdout mildly disagrees, and is not the criterion

On the holdout, the UKIP block slightly helps: Reform MAE 3.21 against 3.33,
and −7.1 per cent against an equal split rather than −11.1. Per architecture:

| holdout Reform, vs equal split | without UKIP | with UKIP |
| --- | ---: | ---: |
| A regularised linear | −8.8% | −7.1% |
| C partial pooling | −7.0% | −8.9% |
| B boosted trees | −11.1% | −21.9% |

The direction is not even consistent across architectures — A improves, C and
B worsen — which is what a change of no real signal looks like. And the
holdout is not the criterion: selecting a feature because the holdout likes it
spends the holdout, the same rule that governs architecture selection.

## Verdict

The UKIP block stays **off**. It is retained in the code as a labelled,
reproducible option, because the brief asks for the experiment to be available
and because "we tried it and it hurt Reform" is a result worth being able to
re-run rather than a claim to be taken on trust.

The bundle is at `outputs/model_bundle_ukip_sensitivity/` and is regenerated
by the command above.

---

## Related records

- [`reform_interaction_terms.md`](reform_interaction_terms.md) — the Reform
  terms this block extends, and why they were built
- [`candidate_model_card.md`](candidate_model_card.md) — the shipped model
- `config/baseline_model.yaml` — the switch, off by default
