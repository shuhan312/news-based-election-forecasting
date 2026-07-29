# Run configuration, and the reproducibility defect the first clean rebuild found

**Recorded 29 July 2026.** The brief asks for configuration files rather than
hardcoded assumptions, a command-line training option, a settable random seed
and a manual architecture mode. Building those was routine. Running the result
into an empty directory for the first time was not: it exposed a defect in the
bundle that had been present for as long as the bundle had existed.

---

## What moved into configuration, and what deliberately did not

`config/baseline_model.yaml` now holds paths, the selection gates, the two
county-strength pooling parameters, the interaction switches, the boosting
seed and the bootstrap settings.

Three design decisions are worth stating because each rules out a failure that
configuration layers commonly have.

**Defaults are not duplicated.** The module constants remain the single source
of every default; the configuration overrides only the keys it names. A file
that restated its own defaults would acquire a second copy of every number and
the two would drift. The shipped file *does* state every value, because a file
a supervisor reads should be complete — and `test_configuration.py` asserts
that what it states still equals the code defaults, so the redundancy is
checked rather than trusted.

**An unknown key stops the run.** This is the single most valuable validation
in the module. A misspelled key that is silently ignored produces a run that
reports success, never applies the setting, and leaves no record anywhere of
the difference. `selection: {materal_improvement: 0.2}` now fails immediately
rather than training a model at the old threshold and reporting it as the new
one.

**The boosting hyperparameters are not exposed.** Only the seed is. Depth,
learning rate, leaf minimum and the rest were declared before any outer fold
was scored; letting a run tune them from the command line would convert a
fixed specification into a search, and a search whose results were then
reported as a single fit.

Precedence is flags → file → code defaults, and the fully resolved
configuration is written into `training_config.yaml`, so a bundle records what
it was built with rather than what any one layer said.

**Verification.** Rebuilding through the CLI reproduced the previous figures
to the digit: out-of-fold MAE 9.85 and winner accuracy 74.3 per cent, holdout
MAE 4.53 and winner accuracy 30.5 per cent, same architecture, same selection
reasons. A configuration layer that changed a number would have been a
configuration layer with a bug in it.

---

## The defect: the manifest hashed the directory, not the run

The first build into a fresh output directory produced **24 files**.
`model_bundle_v1`, built repeatedly into the same reused directory, held
**26**.

`bundle_manifest.json` existed to let a later stage prove it had loaded the
same bundle a set of metrics described. It built its hash table by listing
whatever files were in the output directory. Because the directory is reused
across rebuilds, files written by earlier versions of the build script were
never removed and were hashed into every subsequent manifest as though the
current code had produced them.

**The bundle therefore claimed files that a rebuild could not recreate**, and
the manifest — the artefact whose entire purpose is to establish that two
things are the same bundle — was the artefact carrying the false claim.

### The two files, which were not the same kind of problem

| file | what it was |
| --- | --- |
| `holdout_election_probabilities.csv` | a **real output the rewrite dropped** |
| `fold_summary.csv` | a genuine orphan from an earlier design |

The first is the serious one. The probability model still computes an election
probability for every holdout candidate, and `metrics.json` still reports
Brier score, log loss and a ten-bin reliability table for them. The rewrite
that reorganised the bundle stopped exporting the row-level file while
continuing to compute and summarise its contents — so the holdout's
probabilities were being *summarised with nothing to check the summary
against*. Anyone auditing the calibration table had no rows to recompute it
from. It is restored.

The second is redundant with `metrics.json`'s `by_split` block and is not
restored. It remains in the directory, is excluded from the manifest, and is
now named in `files_not_written_by_this_run`.

### The fix

The build tracks the set of files it writes. The manifest hashes that set.
Anything else found in the output directory is logged as a warning and listed
under `files_not_written_by_this_run`:

```
WARNING  1 file(s) in .../model_bundle_v1 were not written by this run and are
         excluded from the manifest: fold_summary.csv
```

Nothing is deleted. A stale file is reported rather than removed, because a
build script that silently deletes files in a directory a person may have put
something in is a worse failure than the one being fixed.

`model_bundle_v1` now holds **25 files**: the 24 a clean build produces, plus
the reported orphan.

### Why it survived so long

The same reason the three-row selection decision survived: nothing made the
discrepancy visible. Every rebuild wrote into a directory that already
contained a correct-looking bundle, the file count was never asserted
anywhere, and the manifest's own construction guaranteed it would agree with
the directory no matter what was in it. The defect was only ever going to
surface the first time somebody built into an empty directory — which is what
`--output` made cheap to do.

**This is an argument for the tests that check counts.** The acceptance
criteria include "model artefacts can be saved and reloaded"; they did not
include "a clean build produces the file set the bundle claims", and that gap
is exactly where this lived.

---

## Related records

- [`architecture_selection_evidence.md`](architecture_selection_evidence.md) —
  the complete architecture comparison, and what the selection cost
- [`ukip_contextual_sensitivity.md`](ukip_contextual_sensitivity.md) — the
  first experiment the CLI made cheap to run, and its result
- `config/baseline_model.yaml` — every value, with its reasoning
- `../README.md` — how to run it
