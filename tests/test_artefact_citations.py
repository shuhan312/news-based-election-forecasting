"""Guard: every artefact the report surfaces cite must be committed.

The register's authority rests on one rule - every quoted number traces
to committed bytes. This audit used to be manual, and it found two
register citations pointing at files that existed only on one machine
(feature_selection_v1, residual_feasibility). This test closes the gap
forwards: it walks the two machine-readable citation surfaces - the
table pack's SOURCES map and the Streamlit app's load_json calls - and
fails if any cited path is missing from the git index. A new analysis
wired into the pack or app without committing its artefact now breaks
the suite instead of surfacing months later in an audit.

Scope note: the register itself cites paths in prose, which this test
does not parse; the pack and app are the surfaces the report and the
supervisor actually read, and everything they cite is asserted here.
"""

import re
import subprocess
from pathlib import Path

import pytest

from src.news_modelling.build_report_tables import SOURCES

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "news_app.py"

# Cited paths that are LOCAL BY DESIGN, with the design stated. These
# are asserted to exist on disk and to still be git-ignored: if one is
# later committed or deleted, the stale exception fails the suite and
# forces this table to be updated alongside the change.
LOCAL_BY_DESIGN = {
    "news_features/blinded_2026_predictions_v2/blinded_predictions.csv":
        "10.7 MB frozen prediction file; integrity is carried by the "
        "committed sha256_manifest.json beside it, and the unseal "
        "script refuses to run unless the bytes match",
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "holdout_predictions.csv":
        "Stage 1 bundle output; the subproject ignores outputs/ "
        "wholesale and the bundle regenerates from its tracked code",
    "surrey-election-no-news-baseline/outputs/model_bundle_v1/"
    "out_of_fold_predictions.csv":
        "Stage 1 bundle output; same wholesale outputs/ ignore",
}


def _tracked_files() -> set[str]:
    """Paths in the git index (committed or staged), repo-relative.

    Staged-but-uncommitted files count as tracked on purpose: the test
    must pass in the working tree where the artefact was just added,
    before the commit that carries both lands.
    """

    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("git unavailable - citation guard needs the index")
    return set(result.stdout.splitlines())


def test_every_pack_source_is_committed():
    tracked = _tracked_files()
    missing = [str(path) for path in SOURCES.values()
               if str(path) not in tracked
               and str(path) not in LOCAL_BY_DESIGN]
    assert not missing, (
        "table-pack SOURCES cite untracked files (commit the artefact "
        f"with the analysis that produced it): {missing}")


def test_local_by_design_exceptions_hold():
    """Each exception must exist, stay ignored and stay untracked -
    all three checks, so the table cannot silently rot in either
    direction (file vanished, or file was committed after all).

    On a fresh clone none of the local-by-design artefacts exist yet
    (they live on OneDrive; see the README large-artefacts table), so the
    whole check is skipped. A partial absence on a working machine still
    fails: that is the file-vanished case this test exists to catch."""

    if not any((ROOT / path).exists() for path in LOCAL_BY_DESIGN):
        pytest.skip("fresh clone: local-by-design artefacts live on OneDrive")

    tracked = _tracked_files()
    for path, reason in LOCAL_BY_DESIGN.items():
        assert (ROOT / path).exists(), f"{path} missing on disk ({reason})"
        assert path not in tracked, (
            f"{path} is now committed - remove its stale exception")
        ignored = subprocess.run(["git", "check-ignore", "-q", path],
                                 cwd=ROOT)
        assert ignored.returncode == 0, (
            f"{path} is neither tracked nor ignored - it must be one")


def test_every_app_artefact_is_committed():
    # The app reads artefacts through load_json("<literal path>"); the
    # literals may be split across adjacent string fragments, so strip
    # the quote-whitespace-quote seams before extracting the argument.
    source = APP.read_text(encoding="utf-8")
    joined = re.sub(r'"\s*\n\s*"', "", source)
    cited = re.findall(r'load_json\(\s*"([^"]+)"', joined)
    assert cited, "no load_json citations found - parser drifted from app"
    tracked = _tracked_files()
    missing = [path for path in cited if path not in tracked]
    assert not missing, f"app renders untracked artefacts: {missing}"
