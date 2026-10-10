"""llm_eval: evaluate an LLM classification task end to end.

Six stages, one command: load (with label provenance) -> audit the reference
labels -> estimate cost -> run (budget guard, cache, batches) -> score
(bootstrap CIs, subgroups) -> report. Design:
v2_design/llm_eval_toolkit_design.md.
"""
