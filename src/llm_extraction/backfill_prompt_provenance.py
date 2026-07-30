"""Stamp each already-extracted record with the prompt it came from.

## Why this is needed

`run_corpus_extraction` now records a prompt fingerprint on every record at
collect time, read from the manifest written at submit time. Everything
extracted before that change carries no fingerprint - the prompt version sits
only at the top of each tranche file, so a feature table assembled from
several tranches would lose it silently.

That matters because the corpus is not extracted on one prompt. The issues
layer ran on three:

    v1.1   narrow + far    170 accepted records
    v1.2   far2             78 accepted records
    v1.3   far3             89 accepted records

## What can be established, and what cannot

Verified against git rather than assumed:

* **v1.1 is unambiguous.** The issues prompt is byte-identical across all
  eight pre-rule-7 commits (e9ed6e6 through 9151893): sha256
  a4e3f61d2f345841..., 9,240 characters. So any tranche stamped v1.1 was
  produced from that exact prompt.
* **v1.3 is unambiguous.** sha256 715700666acac508..., 10,065 characters,
  identical at 4b9ac35 and HEAD, and identical to the working tree.
* **v1.2 cannot be reconstructed.** It existed only in the working tree
  between two edits and was never committed. Its records therefore get
  `prompt_sha256: null` and a source of
  `unrecoverable_prompt_never_committed`. No hash is invented for them: a
  fabricated fingerprint would look like provenance while being a guess, which
  is worse than an admitted gap. This is the reason those 78 records are
  scheduled for re-extraction rather than kept with a caveat.
* **stance_revised and framing_revised never changed.** Both modules are
  byte-identical from their commits (8f454fe, eb15b21) through HEAD and the
  working tree, with a zero-line diff at every step. One fingerprint therefore
  covers every tranche for those two layers.

## Two things the fingerprint does not capture

The prompt is not the whole generation contract. `max_tokens` is stamped
separately, because nine of far3's issues records were produced during a
diagnostic run at 16,000 while production is 8,000 - the same prompt under a
different budget. Under adaptive thinking a higher ceiling can permit more
thinking, so those nine are not interchangeable with the rest and are marked.

The model is already recorded per layer in each tranche's manifest and is
unchanged throughout, so it is not duplicated here.

## Honesty of the stamp itself

Every value written here is **derived after the fact**, not observed at
generation time, and each record says so via `prompt_sha256_source`. A reader
can tell a reconstructed fingerprint from one this pipeline recorded live: the
live ones read `manifest_at_submit`.

Idempotent - re-running overwrites the derived fields with the same values and
leaves live-recorded ones alone.

Usage:
    python3 -m src.llm_extraction.backfill_prompt_provenance
    python3 -m src.llm_extraction.backfill_prompt_provenance --dry-run
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.llm_extraction import (credit_blame, electoral_consequence,
                               issue_classification)
from src.llm_extraction.frame_rescue import build_prompt as build_frame_prompt
from src.llm_extraction.run_corpus_extraction import (FINGERPRINT_PARTY_SET,
                                                      _prompt_sha256)
from src.llm_extraction.stance_rescue import build_prompt as build_stance_prompt

# Verified above: identical across every pre-rule-7 commit.
V11_ISSUES_SHA = "a4e3f61d2f345841"      # prefix only; full value checked below
V11_ISSUES_CHARS = 9240
V11_REFERENCE_COMMIT = "9151893"

# Extraction version string in each tranche file, mapped to what produced it.
VERSION_TO_ISSUES_PROMPT = {
    "corpus-extraction-v1.1-2026-07-30": "v1.1",
    "corpus-extraction-v1.2-2026-07-30": "v1.2",
    "corpus-extraction-v1.3-2026-07-30": "v1.3",
}

# max_tokens per layer, unchanged for the whole project. The one exception is
# handled per record: far3's nine retried issues records ran at 16,000.
LAYER_MAX_TOKENS = {"issues": 8000, "credit_blame": 12000,
                    "consequence": 12000, "stance_revised": 6000,
                    "framing_revised": 6000}


def issues_prompt_from_commit(commit: str) -> tuple[str, int]:
    """Build the issues prompt as it stood at a commit, and hash it.

    Executed from the committed source rather than diffed, because the prompt
    is assembled at runtime from a schema and a taxonomy: reading the file
    would not tell us what bytes the model actually received.
    """
    src = subprocess.run(
        ["git", "show", f"{commit}:src/llm_extraction/issue_classification.py"],
        capture_output=True, text=True, check=True).stdout
    module = types.ModuleType(f"issue_classification_at_{commit}")
    exec(compile(src, f"<{commit}>", "exec"), module.__dict__)
    text = module.build_issue_prompt()
    return _prompt_sha256(text), len(text)


def main() -> None:
    dry = "--dry-run" in sys.argv

    v11_sha, v11_chars = issues_prompt_from_commit(V11_REFERENCE_COMMIT)
    if not v11_sha.startswith(V11_ISSUES_SHA) or v11_chars != V11_ISSUES_CHARS:
        raise SystemExit(
            f"v1.1 reconstruction does not match what was verified: got "
            f"{v11_sha[:16]} / {v11_chars} chars, expected {V11_ISSUES_SHA} / "
            f"{V11_ISSUES_CHARS}. Refusing to stamp records on a prompt that "
            f"is not the one this module was written against.")

    # Every layer any tranche file might hold, including the two the gate
    # later excluded. `_layer_prompt_fingerprints` filters those out, and using
    # it here stamped 89 consequence records in the narrow tranche with a null
    # hash under a source that claimed the template was unchanged - a false
    # label, and exactly the kind this module exists to prevent. Both excluded
    # modules are verified byte-identical from their commits (726d662,
    # edcce5d) through HEAD and the working tree, so their fingerprints are
    # real rather than absent.
    live = {
        "issues": _prompt_sha256(issue_classification.build_issue_prompt()),
        "credit_blame": _prompt_sha256(credit_blame.build_cb_prompt()),
        "consequence": _prompt_sha256(electoral_consequence.build_ec_prompt()),
        "framing_revised": _prompt_sha256(build_frame_prompt()),
        "stance_revised": _prompt_sha256(
            build_stance_prompt(list(FINGERPRINT_PARTY_SET))),
    }
    issues_sha = {"v1.1": v11_sha, "v1.2": None, "v1.3": live["issues"]}

    summary: dict[str, dict] = {}
    for path in sorted(Path("llm_context").glob(
            "corpus_extraction_outputs_*.json")):
        payload = json.loads(path.read_text())
        version = payload.get("version", "")
        which = VERSION_TO_ISSUES_PROMPT.get(version)
        if which is None:
            print(f"{path.name}: unknown version {version!r} - skipped")
            continue

        counts: dict[str, int] = {}
        for layer, rows in payload.get("layers", {}).items():
            for r in rows:
                if r.get("prompt_sha256_source") == "manifest_at_submit":
                    counts["live_left_alone"] = counts.get(
                        "live_left_alone", 0) + 1
                    continue
                if layer == "issues":
                    sha = issues_sha[which]
                    src = ("unrecoverable_prompt_never_committed"
                           if sha is None else
                           f"reconstructed_from_git:{V11_REFERENCE_COMMIT}"
                           if which == "v1.1" else "reconstructed_from_working_tree")
                elif layer in live:
                    # Byte-identical from its commit through the working tree,
                    # so the live fingerprint is the fingerprint it ran on.
                    sha = live[layer]
                    src = "template_unchanged_since_commit"
                else:
                    # A layer this module does not know how to fingerprint.
                    # Recorded as unknown rather than given a null hash under a
                    # label that would imply it had been checked.
                    sha = None
                    src = "no_fingerprint_available_layer_unknown"
                r["prompt_sha256"] = sha
                r["prompt_sha256_source"] = src
                r["prompt_version"] = (which if layer == "issues"
                                       else "unchanged_since_commit")
                # far3's nine retried issues records ran at a different budget
                # and already say so; everything else ran at the layer default.
                r["max_tokens"] = (r.get("retry_max_tokens")
                                   or LAYER_MAX_TOKENS.get(layer))
                counts[f"{layer}:{src}"] = counts.get(f"{layer}:{src}", 0) + 1

        payload["prompt_provenance"] = {
            "backfilled": True,
            "issues_prompt_version": which,
            "issues_prompt_sha256": issues_sha[which],
            "note": ("every field written by backfill_prompt_provenance is "
                     "derived after the fact; prompt_sha256_source on each "
                     "record says how. v1.2 is null because that prompt was "
                     "never committed and cannot be reconstructed."),
        }
        summary[path.name] = counts
        if not dry:
            path.write_text(json.dumps(payload, indent=2))

    print(f"v1.1 issues prompt: {v11_sha[:16]}... ({v11_chars:,} chars, "
          f"from {V11_REFERENCE_COMMIT})")
    print(f"v1.3 issues prompt: {live['issues'][:16]}... (working tree)")
    print("v1.2 issues prompt: unrecoverable\n")
    for name, counts in summary.items():
        print(f"{name}")
        for k, v in sorted(counts.items()):
            print(f"    {v:4d}  {k}")
    print("\n(dry run - nothing written)" if dry else "\nwritten")


if __name__ == "__main__":
    main()
