"""Cross-OS path contracts for ``oe`` companion discovery / restore.

Uses only ``os.path`` joins (no hardcoded ``/``). Also exercises case-insensitive
name matching so Windows, default macOS, and case-sensitive Linux all behave.
"""

from __future__ import annotations

import os
import sys

import matplotlib.pyplot as plt

from batplot.plot_modes.common.session_helpers import (
    capture_last_figure_export_path,
    discover_companion_figure_path,
    restore_last_figure_export_path,
)
from batplot.plot_modes.electrochem.menu import build_electrochem_menu_columns


def _same(a: str, b: str) -> bool:
    """True if both paths name the same file (handles case-insensitive FS)."""
    try:
        return os.path.samefile(a, b)
    except Exception:
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def test_discover_nested_figures_dir(tmp_path):
    sess_dir = tmp_path / "project" / "Figures"
    sess_dir.mkdir(parents=True)
    sess = sess_dir / "GC_P_BM30.pkl"
    sess.write_bytes(b"x")
    fig_dir = sess_dir / "Figures"
    fig_dir.mkdir()
    svg = fig_dir / "GC_P_BM30.svg"
    svg.write_text("<svg/>", encoding="utf-8")

    found = discover_companion_figure_path(str(sess))
    assert found is not None
    assert _same(found, str(svg))
    assert os.path.isabs(found)
    assert os.path.isfile(found)


def test_discover_same_folder_and_case_insensitive_ext(tmp_path):
    sess = tmp_path / "plot.pkl"
    sess.write_bytes(b"x")
    # Unusual case on the extension — must still resolve on every OS.
    png = tmp_path / "plot.PNG"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    found = discover_companion_figure_path(str(sess))
    assert found is not None
    assert _same(found, str(png))


def test_discover_case_insensitive_figures_dirname(tmp_path):
    sess = tmp_path / "cell.pkl"
    sess.write_bytes(b"x")
    # Lowercase folder name (common accidental rename / Linux tools)
    fig_dir = tmp_path / "figures"
    fig_dir.mkdir()
    svg = fig_dir / "cell.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    found = discover_companion_figure_path(str(sess))
    assert found is not None
    assert _same(found, str(svg))


def test_restore_prefers_existing_stored_over_companion(tmp_path):
    sess = tmp_path / "a.pkl"
    sess.write_bytes(b"x")
    companion = tmp_path / "Figures"
    companion.mkdir()
    (companion / "a.svg").write_text("<svg/>", encoding="utf-8")
    stored = tmp_path / "explicit.png"
    stored.write_bytes(b"\x89PNG\r\n\x1a\n")

    class _Fig:
        pass

    fig = _Fig()
    restore_last_figure_export_path(
        fig,
        {"last_figure_export_path": str(stored)},
        session_filename=str(sess),
    )
    assert _same(fig._last_figure_export_path, str(stored))


def test_restore_falls_back_when_stored_missing(tmp_path):
    sess = tmp_path / "b.pkl"
    sess.write_bytes(b"x")
    fig_dir = tmp_path / "Figures"
    fig_dir.mkdir()
    svg = fig_dir / "b.svg"
    svg.write_text("<svg/>", encoding="utf-8")

    class _Fig:
        pass

    fig = _Fig()
    restore_last_figure_export_path(
        fig,
        {"last_figure_export_path": str(tmp_path / "gone.svg")},
        session_filename=str(sess),
    )
    assert _same(fig._last_figure_export_path, str(svg))


def test_restore_none_key_uses_companion_and_enables_menu_oe(tmp_path):
    sess = tmp_path / "GC_P_BM30.pkl"
    sess.write_bytes(b"x")
    fig_dir = tmp_path / "Figures"
    fig_dir.mkdir()
    svg = fig_dir / "GC_P_BM30.svg"
    svg.write_text("<svg/>", encoding="utf-8")

    fig = plt.figure()
    restore_last_figure_export_path(
        fig, {"last_figure_export_path": None}, session_filename=str(sess)
    )
    assert _same(fig._last_figure_export_path, str(svg))
    _c1, _c2, col3 = build_electrochem_menu_columns(1, fig=fig)
    assert any(item.startswith("oe:") for item in col3)
    plt.close(fig)


def test_capture_always_absolute():
    class _Fig:
        pass

    fig = _Fig()
    fig._last_figure_export_path = os.path.join("relative", "out.svg")
    cap = capture_last_figure_export_path(fig)
    assert cap is not None
    assert os.path.isabs(cap)


def test_abspath_roundtrip_uses_native_separators(tmp_path):
    """Stored paths must not embed foreign separators."""
    sess = tmp_path / "x.pkl"
    sess.write_bytes(b"x")
    fig_dir = tmp_path / "Figures"
    fig_dir.mkdir()
    svg = fig_dir / "x.svg"
    svg.write_text("<svg/>", encoding="utf-8")
    found = discover_companion_figure_path(str(sess))
    assert found is not None
    # On Windows, path should use backslash (or be parseable by os.path);
    # on POSIX, forward slash. Never mix in a way that breaks isfile.
    assert os.path.isfile(found)
    # Reconstruct with join and compare via samefile (case-insensitive FS safe)
    rebuilt = os.path.join(os.path.dirname(str(sess)), "Figures", "x.svg")
    assert os.path.isfile(rebuilt)
    assert _same(found, rebuilt)
    assert isinstance(sys.platform, str)
