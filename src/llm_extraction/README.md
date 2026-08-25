# `src/llm_extraction/` — LLM context extraction (Layer 3, Phase 6)

Turn each canonical article into structured labels with Claude, validate those
labels against human coding, and freeze only what passes. This is the layer that
answers "why trust the LLM labels?" — they are gated and frozen, never used raw.
This directory is **code only**; its outputs and decision records live at the
repository root in [`llm_context/`](../../llm_context/README.md).

## What it extracts

Candidate context layers, each a Phase 6 step run over the pilot sample first:

```text
Step 3  issue classification        Step 7  electoral consequence
Step 4  entity stance               Step 8  local / national relevance
Step 5  framing detection           Step 9  temporal horizon
Step 6  credit / blame attribution  Step 10 confidence + evidence audit
```

## The validation gate (D4) and freeze

Extraction layers are not trusted on faith. `build_d4_sample.py` draws a
human-validation sample; `run_d4_validation.py` runs the compared layers over it;
the `compare_*` modules measure Claude-vs-human agreement. **Only the layers that
cleared the agreement gate survive** — `run_corpus_extraction.py` runs "the three
layers that survived the gate" over the full corpus, and `run_freeze.py` (Step
12) freezes them. Reform UK is validated in its own sub-field sample
(`build_reform_subfield_sample.py`) and never merged with UKIP.

## Running and reproducibility

The pipeline calls the **Claude API in batches**, so like collection it is not
bit-for-bit re-runnable and would cost API budget to repeat. The extracted
outputs are therefore a **frozen batch**: the raw per-article responses are kept
local/OneDrive (copyright — they reproduce article quotes), while the **batch
digests, prompt versions, agreement scorecards and a `sha256` manifest are
committed** to `llm_context/`, so which frozen outputs were used stays verifiable
and every agreement figure recomputes from them. Representative entry points:

```bash
python3 -m src.llm_extraction.run_pilot                 # Step 2: pilot extraction
python3 -m src.llm_extraction.run_d4_validation         # D4: compared layers over the human sample
python3 -m src.llm_extraction.run_corpus_extraction     # the surviving layers over the full corpus
python3 -m src.llm_extraction.run_freeze                # Step 12: freeze the context layer
```

Case-study holdouts reuse the frozen three-layer extraction on new paths:
`run_byelection_extraction.py`, `run_haslemere_probe_extraction.py`,
`run_woking_south_blind_extraction.py`.

## Discipline

Labels are accepted only after human-agreement validation and then frozen;
downstream features read only the frozen layer. Raw model responses are not
committed (copyright); Reform UK and UKIP are validated and kept separate. See
`REPO_MAP.md` for how the frozen labels feed the feature layer.
