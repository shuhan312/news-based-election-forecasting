# Final election-data release protocol

This protocol is the final quality-control boundary for the Surrey election
database before any later analysis. It does not collect news, alter extraction,
or turn missing values into estimates.

## What is checked

1. The required master-table fields that are already supported by source
   evidence are present as explicit columns: candidate `notes` and `source_url`;
   official winner summaries; and the separate winning-margin status.
2. Every value still unavailable after the official, supplementary and governed
   derived layers has one reviewed-source entry in
   `config/final_missing_field_evidence_index.json`.
3. One deterministic source-to-database review target is prepared for every
   election event. It contains the exact result URL, a published candidate row,
   the available official Voting Summary fields, and the corresponding master
   rows.

## Evidence rule

The generated audit never changes the master payload. It reports four distinct
states:

- **Official:** directly published result-page or declaration value.
- **Supplementary:** separately cited authority evidence; it does not overwrite
  the official NULL.
- **Derived:** a formula using permitted inputs from the same official result
  page; its formula, inputs and source URL are retained separately.
- **Unresolved:** no accepted value exists in the reviewed scope. This is not a
  claim that no unindexed historic document exists anywhere.

## Reproduction

From `surrey-election-extractor` run:

```bash
PYTHONPATH=. ../.venv/bin/python scripts/generate_final_election_data_release_audit.py
```

The JSON and Markdown report are written under `outputs/` and ignored by Git.
They can be uploaded to the project's external data store when needed. The
script uses existing audited local inputs only and does not rerun web
discovery or extraction.
