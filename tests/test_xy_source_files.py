"""Tests for XY source-file resolution after session reload."""

from types import SimpleNamespace

from batplot.plot_modes.common.sources import (
    cif_paths_from_tick_series,
    ensure_xy_args_files,
    resolve_xy_source_files,
)


def test_resolve_xy_source_files_from_args_subset_and_cif_series():
    args = SimpleNamespace()
    session = {
        "args_subset": {"files": ["/data/pattern.xy"]},
        "source_files": ["/data/phase.cif"],
    }
    cif_series = [("Phase A", "/data/phase.cif", [1.0, 2.0], 1.54, 5.0, "red")]

    files = resolve_xy_source_files(
        args,
        cif_tick_series=cif_series,
        session=session,
    )

    assert "/data/pattern.xy" in files
    assert "/data/phase.cif" in files


def test_ensure_xy_args_files_populates_minimal_args():
    args = type("Args", (), {"stack": False})()
    cif_series = [("Ref", "BM_ref.cif", [], None, 0.0, "k")]

    files = ensure_xy_args_files(
        args,
        labels=["BM_XRD.xy"],
        cif_tick_series=cif_series,
    )

    assert args.files == files
    assert any(str(p).endswith("BM_ref.cif") for p in files)


def test_cif_paths_from_tick_series_reads_filename_field():
    series = [("label", "/tmp/sample.cif", [1.0], 1.54, 2.0, "#000")]
    assert cif_paths_from_tick_series(series) == ["/tmp/sample.cif"]
