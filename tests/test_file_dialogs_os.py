"""Cross-OS file-dialog backend contracts (no real GUI)."""

from __future__ import annotations

import os
import sys

import pytest


def test_linux_tk_cancel_does_not_open_zenity(monkeypatch):
    """Cancel on tk must not fall through to a second zenity/kdialog picker."""
    from batplot import utils as U

    calls = []

    def _tk(*_a, **_k):
        calls.append("tk")
        return []  # dialog shown; user cancelled

    def _zen(*_a, **_k):
        calls.append("zen")
        return ["/tmp/should-not-be-used.cif"]

    monkeypatch.setattr(U.sys, "platform", "linux")
    monkeypatch.setattr(U, "_ask_files_dialog_tk", _tk)
    monkeypatch.setattr(U, "_ask_files_dialog_zenity", _zen)

    out = U._ask_files_dialog(filetypes=(".cif",), title="Select CIF file(s)", multiple=True)
    assert out == []
    assert calls == ["tk"]


def test_linux_tk_unavailable_falls_back_to_zenity(monkeypatch, tmp_path):
    from batplot import utils as U

    cif = tmp_path / "a.cif"
    cif.write_text("data_x\n", encoding="utf-8")
    calls = []

    def _tk(*_a, **_k):
        calls.append("tk")
        return None  # backend unavailable

    def _zen(*_a, **_k):
        calls.append("zen")
        return [str(cif)]

    monkeypatch.setattr(U.sys, "platform", "linux")
    monkeypatch.setattr(U, "_ask_files_dialog_tk", _tk)
    monkeypatch.setattr(U, "_ask_files_dialog_zenity", _zen)

    out = U._ask_files_dialog(filetypes=(".cif",), multiple=True)
    assert [os.path.abspath(p) for p in out] == [os.path.abspath(str(cif))]
    assert calls == ["tk", "zen"]


def test_windows_tk_cancel_stays_empty(monkeypatch):
    from batplot import utils as U

    calls = []

    def _tk(*_a, **_k):
        calls.append("tk")
        return []

    def _zen(*_a, **_k):
        calls.append("zen")
        return ["/tmp/no.cif"]

    monkeypatch.setattr(U.sys, "platform", "win32")
    monkeypatch.setattr(U, "_ask_files_dialog_tk", _tk)
    monkeypatch.setattr(U, "_ask_files_dialog_zenity", _zen)

    out = U._ask_files_dialog(multiple=True)
    assert out == []
    assert calls == ["tk"]


def test_kdialog_separate_output_keeps_paths_with_spaces(monkeypatch, tmp_path):
    """kdialog --separate-output newline paths must not be space-split."""
    from batplot import utils as U

    spaced = tmp_path / "My Files"
    spaced.mkdir()
    a = spaced / "a.cif"
    b = tmp_path / "b.cif"
    a.write_text("data_a\n", encoding="utf-8")
    b.write_text("data_b\n", encoding="utf-8")

    class _Res:
        returncode = 0
        stdout = f"{a}\n{b}\n"
        stderr = ""

    def _which(name):
        if name == "zenity":
            return None
        if name == "kdialog":
            return "/usr/bin/kdialog"
        return None

    seen_cmd = {}

    def _run(cmd, **_k):
        seen_cmd["cmd"] = list(cmd)
        return _Res()

    monkeypatch.setattr(U.shutil, "which", _which)
    monkeypatch.setattr(U.subprocess, "run", _run)

    out = U._ask_files_dialog_zenity(str(tmp_path), filetypes=(".cif",), multiple=True)
    assert "--separate-output" in seen_cmd["cmd"]
    assert "--multiple" in seen_cmd["cmd"]
    assert len(out) == 2
    assert os.path.basename(out[0]) == "a.cif"
    assert os.path.basename(out[1]) == "b.cif"


def test_linux_directory_tk_cancel_does_not_open_zenity(monkeypatch):
    from batplot import utils as U

    calls = []

    def _tk(_initialdir):
        calls.append("tk")
        return False  # shown; cancelled

    def _zen(_initialdir):
        calls.append("zen")
        return "/tmp/should-not"

    monkeypatch.setattr(U.sys, "platform", "linux")
    monkeypatch.setattr(U, "_ask_directory_dialog_tk", _tk)
    monkeypatch.setattr(U, "_ask_directory_dialog_zenity", _zen)

    assert U._ask_directory_dialog() is None
    assert calls == ["tk"]


@pytest.mark.skipif(sys.platform.startswith("darwin"), reason="macOS uses osascript only")
def test_ask_files_dialog_tk_none_means_unavailable_on_non_darwin():
    """Contract: darwin path is separate; non-darwin None vs [] semantics."""
    from batplot import utils as U

    # Import-time sanity: function documents Optional[list] via None/[] split.
    assert callable(U._ask_files_dialog_tk)


def test_parse_typed_path_list_quoted_spaces(tmp_path):
    from batplot.utils import _parse_typed_path_list

    spaced = tmp_path / "My Files"
    spaced.mkdir()
    a = spaced / "a.cif"
    a.write_text("x\n", encoding="utf-8")
    b = tmp_path / "b.cif"
    b.write_text("y\n", encoding="utf-8")
    line = f'"{a}" {b}'
    out = _parse_typed_path_list(line)
    assert len(out) == 2
    assert os.path.basename(out[0]) == "a.cif"
    assert os.path.basename(out[1]) == "b.cif"


def test_parse_typed_path_list_windows_quoted_keeps_path(monkeypatch, tmp_path):
    """On Windows, shlex posix=False keeps quotes — must strip them."""
    import batplot.utils as U

    spaced = tmp_path / "My Files"
    spaced.mkdir()
    a = spaced / "a.cif"
    a.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(U.os, "name", "nt")
    out = U._parse_typed_path_list(f'"{a}"')
    assert len(out) == 1
    assert os.path.basename(out[0]) == "a.cif"
    assert '"' not in out[0]


def test_split_path_token_windows_drive_and_extended():
    from batplot.plot_modes.common.sources import path_token_without_suffix, split_path_token

    path, rest = split_path_token(r"C:\data\phase.cif:1.54")
    assert path.lower().endswith("phase.cif")
    assert rest == ["1.54"]

    path2, rest2 = split_path_token(r"\\?\C:\data\phase.cif:1.54")
    assert path2.lower().endswith("phase.cif")
    assert path2.startswith("\\\\?\\C:")
    assert rest2 == ["1.54"]

    assert path_token_without_suffix(r"\\?\C:\data\phase.cif:1.54").lower().endswith(".cif")

    path3, rest3 = split_path_token(r"\\server\share\a.cif:0.709")
    assert path3.lower().endswith("a.cif")
    assert rest3 == ["0.709"]


def test_xy_cif_typed_path_fallback_after_empty_dialog(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    import batplot.utils as U
    from batplot.plot_modes.xy.cif import run_cif_ticks_menu

    cif = tmp_path / "phase.cif"
    cif.write_text(
        "data_test\n"
        "_cell_length_a 3.0\n_cell_length_b 3.0\n_cell_length_c 3.0\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "_symmetry_space_group_name_H-M 'P 1'\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Li 0 0 0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(U, "_ask_files_dialog", lambda **_k: [])
    fig, ax = plt.subplots()
    ax.plot(np.linspace(1, 6, 20), np.ones(20))
    bp = SimpleNamespace(
        cif_tick_series=[],
        cif_hkl_label_map={},
        cif_hkl_map={},
        show_cif_hkl=False,
        show_cif_titles=True,
        cif_extend_suspended=False,
    )
    fig._batplot_cif_tick_series = bp.cif_tick_series  # type: ignore[attr-defined]
    feeds = iter(["a", str(cif), "q"])

    def _feed(*_a, **_k):
        try:
            return next(feeds)
        except StopIteration:
            return "q"

    run_cif_ticks_menu(
        ax=ax,
        fig=fig,
        _bp=bp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        _safe_input=_feed,
        push_state=lambda *_a, **_k: True,
        _print_cif_phase_list=lambda *_a, **_k: None,
        _apply_cif_phase_label_rename=lambda *_a, **_k: None,
        _sync_fig_cif_tick_series=lambda: setattr(fig, "_batplot_cif_tick_series", bp.cif_tick_series),
        use_2th=False,
        y_data_list=[np.asarray(ax.lines[0].get_ydata())],
    )
    assert len(bp.cif_tick_series) == 1
    plt.close(fig)
