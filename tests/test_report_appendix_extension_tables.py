"""Every report-used appendix table must come from the generated pack."""

import json
import re
from pathlib import Path

import pytest

from src.news_modelling import report_appendix_tables as tables
from src.news_modelling import stage2_fitting_cells_table as fitting_cells


ROOT = Path(__file__).resolve().parent.parent
CASES = [
    ("local_sensitivity", "a15_local_sensitivity.tex"),
    ("lopo_results", "a17_lopo_results.tex"),
    ("reform_attribution", "a18_reform_attribution.tex"),
    ("cumulative_results", "a12_cumulative_results.tex"),
]


@pytest.mark.parametrize(("generator", "filename"), CASES)
def test_extension_table_rebuilds_byte_identically(
        tmp_path, monkeypatch, generator, filename):
    monkeypatch.setattr(tables, "OUT", tmp_path)
    getattr(tables, generator)()

    expected = ROOT / "outputs" / "report_tables_v1" / "latex" / filename
    assert (tmp_path / filename).read_bytes() == expected.read_bytes()


def _report_table_paths() -> list[Path]:
    source = (ROOT / "report" / "report.tex").read_text(encoding="utf-8")
    names = re.findall(r"\\input\{([^}]+\.tex)\}", source)
    return [(ROOT / "report" / name).resolve() for name in names]


def test_all_sixteen_report_tables_rebuild_byte_identically(
        tmp_path, monkeypatch):
    """Run the real appendix entry point, then compare every report input.

    The Stage 1 feature schema is a local bundle output. For this table-only
    test, its predictor-name list is reconstructed from the builder's complete
    gloss mapping; the production builder still asserts that the restored
    Stage 1 schema has exactly this set when run normally.
    """
    schema = tmp_path / "feature_schema.json"
    schema.write_text(json.dumps({
        "source_predictors": sorted(tables.PREDICTOR_GLOSSES),
    }), encoding="utf-8")
    generated = tmp_path / "latex"
    generated.mkdir()
    monkeypatch.setattr(tables, "SCHEMA", schema)
    monkeypatch.setattr(tables, "OUT", generated)
    tables.main()

    report_paths = _report_table_paths()
    assert len(report_paths) == 16
    # The report source is the self-contained Overleaf layout: every table
    # is a local copy under report/, pinned byte-for-byte to the freshly
    # generated pack so the two can never drift apart.
    report_dir = (ROOT / "report").resolve()
    # a14 is the curated eligibility-rules table from the protocol document;
    # it has no generator and is pinned to the pack by the sync test below.
    static_tables = {"a14_eligibility_rules.tex"}
    separate_generators = {"a20_stage2_fitting_cells.tex"}
    for path in report_paths:
        assert path.parent == report_dir
        if path.name in static_tables | separate_generators:
            continue
        assert (generated / path.name).read_bytes() == path.read_bytes()


def test_stage2_fitting_cells_rebuilds_byte_identically(tmp_path, monkeypatch):
    """The separately derived chronology table matches both committed copies."""

    csv_path = tmp_path / "a20_stage2_fitting_cells.csv"
    tex_path = tmp_path / "a20_stage2_fitting_cells.tex"
    monkeypatch.setattr(fitting_cells, "OUT_CSV", csv_path)
    monkeypatch.setattr(fitting_cells, "OUT_TEX", tex_path)
    fitting_cells.main()

    pack = ROOT / "outputs" / "report_tables_v1"
    assert csv_path.read_bytes() == (pack / csv_path.name).read_bytes()
    assert tex_path.read_bytes() == (pack / "latex" / tex_path.name).read_bytes()
    assert tex_path.read_bytes() == (ROOT / "report" / tex_path.name).read_bytes()


def test_report_table_copies_match_the_generated_pack():
    """Every local report/a*.tex must equal its authoritative pack version."""

    pack = ROOT / "outputs" / "report_tables_v1" / "latex"
    local_tables = sorted((ROOT / "report").glob("a*.tex"))
    assert local_tables, "the report source carries no appendix tables"
    for path in local_tables:
        assert (pack / path.name).read_bytes() == path.read_bytes(), path.name
