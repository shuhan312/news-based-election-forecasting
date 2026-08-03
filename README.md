# IRP Repository

Please familiarise yourself with and follow [GitHub repository instructions](https://ese-msc.github.io/irp/repos/).

Deleting or modifying the pre-existing GitHub Actions workflows or the directory structure in this repository is strictly prohibited. Your IRP files should "live" alongside pre-existing files.

## Inactivity Warnings

Scheduled workflows will periodically check whether `logbook.md` has been updated recently on `main` as well as whether **regular commits were made to the repository (to any branch)**. If an inactivity is detected, a warning will be automatically raised as an issue in this repository. **You must not close those issues.**

## Large local artefacts (per the IRP large-file rule)

The following generated artefacts are deliberately NOT tracked; every
one regenerates from tracked code, and copies live on OneDrive
(link: _to be added by SL_).

| artefact | size | regenerate with |
| --- | --- | --- |
| `news_features/ward_party_election_features_v1/` - the two ward-grain parquets, `final_feature_dictionary.csv`, `final_feature_leakage_audit.csv`, `feature_view_manifest.json`, `empty_feature_columns.csv` | ~51 MB + ~26 MB | `PYTHONPATH=src .venv/bin/python -m news_modelling.run_ward_party_features` |
| `news_features/blinded_2026_predictions_v2/blinded_predictions.csv` | 10.7 MB | frozen; integrity carried by the committed `sha256_manifest.json` beside it |
| `surrey-election-no-news-baseline/outputs/model_bundle_v1/` | Stage 1 bundle | the subproject's tracked Stage 1 workflow |
| `data/` (raw and processed inputs beyond `data/elections/`) | ~13 GB | collection pipelines under `src/` |

`tests/test_artefact_citations.py` guards the boundary: everything the
report table pack or the app cites must be committed, and the named
local-by-design exceptions must stay ignored.

---

**Tip:** After you have familiarised yourself with this repository, you may delete the content of this file and replace it with your project-specific information.
