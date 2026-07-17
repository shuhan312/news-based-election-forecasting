"""Generate the local audit that permits limited 2026 historical references."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Direct execution imports only the checked-out project.  It reads the
    # completed geographic crosswalk and never rewrites election extraction.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.historical_baseline import load_crosswalk_resolution
from election_extractor.historical_reference_permissions import (
    build_historical_reference_permission_audit,
    historical_reference_permission_markdown,
)


CROSSWALK_PATH = (
    PROJECT_ROOT
    / "outputs/geographic_crosswalk_resolution/geographic_crosswalk_resolution_dataset.json"
)
LOCAL_OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs/historical_reference_permissions"
TRACKED_REPORT_PATH = PROJECT_ROOT / "docs/historical_reference_permission_audit.md"


def run(
    *,
    crosswalk_path: Path = CROSSWALK_PATH,
    local_output_directory: Path = LOCAL_OUTPUT_DIRECTORY,
    report_path: Path = TRACKED_REPORT_PATH,
) -> tuple[dict[str, Path], dict[str, object]]:
    """Rebuild additive permission records from existing reviewed GIS evidence."""

    # This reads the recorded resolution output rather than recalculating GIS
    # topology.  The output is an audit of approval, not a new boundary rule.
    audit = build_historical_reference_permission_audit(
        load_crosswalk_resolution(crosswalk_path)
    )
    local_output_directory.mkdir(parents=True, exist_ok=True)
    local_json = local_output_directory / "historical_reference_permission_audit.json"
    local_json.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(historical_reference_permission_markdown(audit), encoding="utf-8")
    return {"local_json": local_json, "report": report_path}, audit


def main() -> None:
    """Print only compact reproducibility information, not source payloads."""

    outputs, audit = run()
    print(
        json.dumps(
            {
                "local_json": str(outputs["local_json"]),
                "report": str(outputs["report"]),
                "summary": audit["summary"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
