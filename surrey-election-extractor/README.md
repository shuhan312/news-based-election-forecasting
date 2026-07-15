# Surrey Election Results Extractor

This project will use indexed search results to extract Surrey election data without bypassing Surrey County Council website access controls.

## Reproducing the 2017 Surrey County Council extraction

From the `surrey-election-extractor` directory, run:

```bash
PYTHONPATH=. python scripts/run_configured_election_pipeline.py \
  --election-id surrey-county-council-2017 \
  --output-directory outputs/2017_full_extraction
```

This runs the configured 2017 election through discovery, official-page extraction,
validation, and workbook generation. The pipeline preserves published source values
and leaves fields missing when the official source does not publish them.

## Generated outputs

Generated workbooks and audit files are reproducible intermediate research outputs.
They are stored outside this Git repository in OneDrive, in accordance with the IRP
data-sharing guidance. The 2017 full-extraction output folder is available to
Imperial College London users here:

[2017 Full Extraction (OneDrive)](https://imperiallondon-my.sharepoint.com/:f:/r/personal/sl1425_ic_ac_uk/Documents/IRP%20Surrey%20Election%20Extractor/2017%20Full%20Extraction?csf=1&web=1&e=DFwaAb)
