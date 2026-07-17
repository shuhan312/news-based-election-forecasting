"""Generate the small, citable pre-2024 legal-continuity audit report."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # Direct execution must use this checkout's reviewed configuration and code.
    sys.path.insert(0, str(PROJECT_ROOT))

from election_extractor.principal_election_continuity import (
    build_principal_election_continuity_audit,
    principal_election_continuity_markdown,
)


OUTPUT_PATH = PROJECT_ROOT / "docs/principal_election_continuity_audit.md"


def main() -> None:
    """Write documentation only; raw election audits and source values stay untouched."""

    audit = build_principal_election_continuity_audit()
    OUTPUT_PATH.write_text(principal_election_continuity_markdown(audit), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
