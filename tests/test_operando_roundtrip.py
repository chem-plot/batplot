"""Operando (+ EC side panel) session round-trip tests.

Includes a regression guard for the bug where undo/reload hid the EC right-axis
ticks and labels because the saved tick-state drifted out of sync with what was
actually displayed.
"""

import json
import pickle

import numpy as np
import matplotlib.pyplot as plt
import pytest
from matplotlib.ticker import MultipleLocator

from batplot import session as S
from batplot.plot_modes.operando import interactive as OI
from batplot.plot_modes.operando import actions as OA
from batplot.plot_modes.operando import colors as OC
from batplot.plot_modes.operando import line_style as OE
from batplot.plot_modes.operando import grid as OG
from batplot.plot_modes.operando import labels as OL
from batplot.plot_modes.operando import peaks as OP
from batplot.plot_modes.operando import visibility as OV
from batplot.plot_modes.operando.menu import print_operando_ec_menu
from batplot.plot_modes.operando import style as OS
from conftest import assert_allclose, loaded


def _build_operando_figure():
    fig, ax = plt.subplots()
    Z = np.random.default_rng(0).random((50, 80))
    im = ax.imshow(Z, aspect="auto", origin="lower", extent=[10.0, 40.0, 0.0, 20.0],
                   cmap="viridis")
    cbar = fig.colorbar(im, ax=ax)
    ec_ax = fig.add_axes([0.78, 0.1, 0.18, 0.8])
    ec_ax.plot(np.linspace(3.0, 4.2, 30), np.linspace(0.0, 20.0, 30))
    ec_ax.set_xlabel("Voltage (V)")
    ec_ax.set_ylabel("Time (h)")
    ec_ax.yaxis.tick_right()
    ec_ax.yaxis.set_label_position("right")
    return fig, ax, im, cbar, ec_ax


def test_dump_load_preserves_image_extent_and_limits(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    p = session_path("operando.pkl")
    S.dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax,
                            skip_confirm=True)

    result = S.load_operando_session(p)
    assert result is not None, "load_operando_session returned None"
    fig2, ax2, im2, cbar2, ec_ax2 = result

    assert im2 is not None, "operando image not restored"
    assert ec_ax2 is not None, "EC side panel not restored"
    # x-extent of the contour should match the saved extent.
    ext = im2.get_extent()
    assert_allclose((ext[0], ext[1]), (10.0, 40.0), "operando x-extent not restored")


def test_load_keeps_ec_right_ticks_consistent(session_path):
    """Regression: EC right ticks/labels must stay ON after reload.

    The EC y-axis is the panel's primary axis (right side). Even when the saved
    WASD dict records right ticks as off (a known drift), the loader must resolve
    them ON when the right title is shown, and store a *consistent* tick-state so
    a subsequent undo does not hide them.
    """
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    p = session_path("operando_ec.pkl")
    S.dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax,
                            skip_confirm=True)

    fig2, ax2, im2, cbar2, ec_ax2 = loaded(S.load_operando_session(p))
    assert ec_ax2 is not None, "operando EC axis not restored"

    saved = getattr(ec_ax2, "_saved_tick_state", {})
    assert saved.get("r_ticks") is True, (
        "EC right ticks recorded as off after load (would be hidden on undo)"
    )
    assert saved.get("r_labels") is True, (
        "EC right labels recorded as off after load"
    )

    major = ec_ax2.yaxis.get_major_ticks()
    assert any(t.tick2line.get_visible() for t in major), (
        "EC right ticks not visible after load"
    )
    assert any(t.label2.get_visible() for t in major), (
        "EC right tick labels not visible after load"
    )


def test_load_preserves_explicit_ec_right_ticks_off_with_title_on(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    p = session_path("operando_ec_ticks_off.pkl")
    S.dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax,
                            skip_confirm=True)

    with open(p, "rb") as fh:
        data = pickle.load(fh)
    data.setdefault("ec", {}).setdefault("wasd_state", {}).setdefault("right", {}).update({
        "ticks": False,
        "labels": False,
        "title": True,
    })
    data["ec"]["wasd_state"].setdefault("left", {}).update({
        "ticks": False,
        "labels": False,
    })
    with open(p, "wb") as fh:
        pickle.dump(data, fh)

    fig2, ax2, im2, cbar2, ec_ax2 = loaded(S.load_operando_session(p))
    assert ec_ax2 is not None, "operando EC axis not restored"

    saved = getattr(ec_ax2, "_saved_tick_state", {})
    assert saved.get("r_ticks") is False
    assert saved.get("r_labels") is False
    assert ec_ax2.yaxis.get_label_position() == "right"

    major = ec_ax2.yaxis.get_major_ticks()
    assert not any(t.tick2line.get_visible() for t in major)
    assert not any(t.label2.get_visible() for t in major)


def test_legacy_operando_session_labelpad_and_ec_ticks(session_path):
    """Regression for older operando+EC pkls with left-side EC tick drift."""
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    p = session_path("operando_legacy_ec_drift.pkl")
    S.dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax,
                            skip_confirm=True)

    with open(p, "rb") as fh:
        data = pickle.load(fh)
    op = data.setdefault("operando", {}).setdefault("labels", {})
    op["ylabel"] = "Scan index"
    op["y_labelpad"] = 4.0
    data["ec"].setdefault("wasd_state", {}).setdefault("left", {}).update({
        "ticks": True,
        "labels": True,
        "title": False,
    })
    data["ec"]["wasd_state"].setdefault("right", {}).update({
        "ticks": False,
        "labels": False,
        "title": True,
    })
    with open(p, "wb") as fh:
        pickle.dump(data, fh)

    fig2, ax2, im2, cbar2, ec_ax2 = loaded(S.load_operando_session(p))
    assert ax2.yaxis.labelpad >= 8.0
    assert ec_ax2.yaxis.get_tick_params()["labelright"] is True
    assert getattr(fig2, "_operando_session_loaded", False) is True


def test_operando_style_export_uses_displayed_ec_tick_state():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ec_ax._saved_tick_state = {
        "r_ticks": True,
        "r_labels": True,
        "l_ticks": True,
        "l_labels": True,
    }
    ec_ax.tick_params(axis="y", right=False, labelright=False, left=False, labelleft=False)
    fig.canvas.draw()

    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")

    assert cfg["ec"]["wasd_state"]["right"]["ticks"] is False
    assert cfg["ec"]["wasd_state"]["right"]["labels"] is False
    assert cfg["ec"]["wasd_state"]["left"]["ticks"] is False
    assert cfg["ec"]["wasd_state"]["left"]["labels"] is False


def test_operando_style_export_preserves_pane_tick_lengths():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax.tick_params(axis="both", which="major", length=9.0)
    ax.tick_params(axis="both", which="minor", length=6.3)
    ax.xaxis.set_major_locator(MultipleLocator(2.5))
    ec_ax.tick_params(axis="both", which="major", length=5.0)
    ec_ax.tick_params(axis="both", which="minor", length=3.5)
    ec_ax.xaxis.set_major_locator(MultipleLocator(0.25))
    ax.tick_params(axis="both", which="both", direction="in")
    ec_ax.tick_params(axis="both", which="both", direction="in")
    fig._tick_direction = "in"
    ec_ax._ec_y_mode = "ions"
    ec_ax._ion_params = {"mass_mg": 10.0, "cap_per_ion_mAh_g": 50.0, "start_ions": 1.0}
    ec_ax._ions_abs = np.linspace(1.0, 2.0, 30)
    ec_ax._prev_ec_xlim = (3.0, 4.2)
    ec_ax._ions_xlim_expanded = True
    ec_ax._ion_guides = [ec_ax.axhline(y=5.0)]
    ec_ax._ion_annots = [ec_ax.annotate("1.5", xy=(4.0, 5.0))]

    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")

    assert cfg["operando"]["ticks"]["lengths"]["x_major"] == 9.0
    assert cfg["operando"]["ticks"]["lengths"]["x_minor"] == 6.3
    assert cfg["operando"]["ticks"]["direction"] == "in"
    assert cfg["operando"]["ticks"]["locator_state"]["x_major_step"] == 2.5
    assert cfg["ec"]["ticks"]["lengths"]["x_major"] == 5.0
    assert cfg["ec"]["ticks"]["lengths"]["x_minor"] == 3.5
    assert cfg["ec"]["ticks"]["direction"] == "in"
    assert cfg["ec"]["ticks"]["locator_state"]["x_major_step"] == 0.25
    assert cfg["ec"]["ions_abs"] == list(np.linspace(1.0, 2.0, 30))
    assert cfg["ec"]["prev_ec_xlim"] == (3.0, 4.2)
    assert cfg["ec"]["ions_xlim_expanded"] is True
    assert cfg["ec"]["ion_guides"] == [5.0]
    assert cfg["ec"]["ion_annots"] == [{"text": "1.5", "xy": (4.0, 5.0)}]


def test_operando_session_preserves_pane_tick_lengths(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax.tick_params(axis="both", which="major", length=9.0)
    ax.tick_params(axis="both", which="both", direction="in")
    ec_ax.tick_params(axis="both", which="major", length=5.0)
    ec_ax.tick_params(axis="both", which="both", direction="in")
    fig._tick_direction = "in"
    plt.rcParams["mathtext.fontset"] = "stix"
    fig._colorbar_label_mode = "highlow"
    cbar.ax._colorbar_label = "Intensity"
    cbar.ax._colorbar_label_mode = "highlow"
    ec_ax._ec_time_h = np.linspace(0.0, 20.0, 30)
    ec_ax._ec_voltage_v = np.linspace(3.0, 4.2, 30)
    ec_ax._ec_current_mA = np.linspace(1.0, 2.0, 30)
    ec_ax._ec_y_mode = "ions"
    ec_ax._ion_params = {"mass_mg": 10.0, "cap_per_ion_mAh_g": 50.0, "start_ions": 1.0}
    ec_ax._ions_abs = np.linspace(1.0, 2.0, 30)
    ec_ax._prev_ec_xlim = (3.0, 4.2)
    ec_ax._ions_xlim_expanded = True
    ec_ax._ion_guides = [ec_ax.axhline(y=5.0)]
    ec_ax._ion_annots = [ec_ax.annotate("1.5", xy=(4.0, 5.0))]
    p = session_path("operando_tick_lengths.pkl")

    S.dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax,
                            skip_confirm=True)
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    fig2, ax2, im2, cbar2, ec_ax2 = loaded(S.load_operando_session(p))
    assert ec_ax2 is not None, "operando EC axis not restored"
    fig2.canvas.draw()

    assert ax2.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 9.0
    assert ec_ax2.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 5.0
    assert getattr(fig2, "_tick_direction") == "in"
    assert plt.rcParams["mathtext.fontset"] == "stix"
    assert getattr(cbar2.ax, "_colorbar_label_mode") == "highlow"
    assert {txt.get_text() for txt in cbar2.ax.texts} >= {"High", "Low"}
    assert getattr(ec_ax2, "_ec_y_mode") == "ions"
    assert_allclose(ec_ax2._ions_abs, np.linspace(1.0, 2.0, 30))
    assert getattr(ec_ax2, "_prev_ec_xlim") == (3.0, 4.2)
    assert getattr(ec_ax2, "_ions_xlim_expanded") is True
    assert [line.get_ydata()[0] for line in getattr(ec_ax2, "_ion_guides", [])] == [5.0]
    assert [ann.get_text() for ann in getattr(ec_ax2, "_ion_annots", [])] == ["1.5"]


def test_operando_style_import_applies_ec_tick_state(session_path, monkeypatch):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    cfg["ec"]["wasd_state"]["right"].update({"ticks": False, "labels": False, "title": True})
    cfg["operando"]["wasd_state"]["bottom"]["title"] = False
    cfg["operando"]["wasd_state"]["left"]["title"] = False
    cfg["ec"]["wasd_state"]["bottom"]["title"] = False
    cfg["ec"]["wasd_state"]["right"]["title"] = False
    cfg["operando"]["ticks"]["lengths"] = {"x_major": 8.0, "x_minor": 5.6}
    cfg["ec"]["ticks"]["lengths"] = {"x_major": 6.0, "x_minor": 4.2}
    cfg["operando"]["ticks"]["direction"] = "in"
    cfg["ec"]["ticks"]["direction"] = "in"
    cfg["operando"]["ticks"]["locator_state"] = {"x_major_step": 2.5}
    cfg["ec"]["ticks"]["locator_state"] = {"x_major_step": 0.25}
    style_path = session_path("operando_style.bps")
    with open(style_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)

    monkeypatch.setattr(OA, "choose_style_file", lambda *_args, **_kwargs: style_path)
    ctx = OA.OperandoActionContext(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        file_paths=[str(style_path)],
        print_menu=lambda: None,
        snapshot=lambda _note="": None,
        restore=lambda: None,
        run_save_operando_session=lambda: None,
        set_fonts=lambda **_kwargs: None,
        axis_tick_width=OS._axis_tick_width,
        format_file_timestamp=lambda _path: "",
        maybe_reapply_dqdv_2d_contour=lambda *_args, **_kwargs: None,
        restore_dqdv_2d_operando_labels=lambda *_args, **_kwargs: None,
        ax_w_in=3.0,
        ax_h_in=3.0,
        cb_w_in=0.2,
        cb_gap_in=0.1,
        ec_gap_in=0.2,
        ec_w_in=1.0,
    )

    OA.handle_import_style(ctx)
    fig.canvas.draw()

    saved = getattr(ec_ax, "_saved_tick_state", {})
    major = ec_ax.yaxis.get_major_ticks()
    assert saved.get("r_ticks") is False
    assert saved.get("r_labels") is False
    assert not any(t.tick2line.get_visible() for t in major)
    assert not any(t.label2.get_visible() for t in major)
    assert ec_ax.yaxis.get_label_position() == "right"
    assert ax.xaxis.label.get_visible() is False
    assert ax.yaxis.label.get_visible() is False
    assert ec_ax.xaxis.label.get_visible() is False
    assert ec_ax.get_ylabel() == ""
    assert ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 8.0
    assert ec_ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 6.0
    assert getattr(fig, "_tick_direction") == "in"
    assert type(ax.xaxis.get_major_locator()).__name__ == "MultipleLocator"
    assert type(ec_ax.xaxis.get_major_locator()).__name__ == "MultipleLocator"


def test_operando_style_roundtrip_preserves_cif_labels(session_path, monkeypatch):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax._operando_cif_tick_series = [
        ("Renamed phase", "phase.cif", [1.0, 2.0], None, 5.0, "#ff0000"),
    ]
    fig._operando_cif_show_hkl = False
    fig._operando_cif_show_titles = True
    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    ax._operando_cif_tick_series = [
        ("Original phase", "phase.cif", [1.0, 2.0], None, 5.0, "#0000ff"),
    ]
    style_path = session_path("operando_cif_labels.bps")
    with open(style_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)

    monkeypatch.setattr(OA, "choose_style_file", lambda *_args, **_kwargs: style_path)
    ctx = OA.OperandoActionContext(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        file_paths=[str(style_path)],
        print_menu=lambda: None,
        snapshot=lambda _note="": None,
        restore=lambda: None,
        run_save_operando_session=lambda: None,
        set_fonts=lambda **_kwargs: None,
        axis_tick_width=OS._axis_tick_width,
        format_file_timestamp=lambda _path: "",
        maybe_reapply_dqdv_2d_contour=lambda *_args, **_kwargs: None,
        restore_dqdv_2d_operando_labels=lambda *_args, **_kwargs: None,
        ax_w_in=3.0,
        ax_h_in=3.0,
        cb_w_in=0.2,
        cb_gap_in=0.1,
        ec_gap_in=0.2,
        ec_w_in=1.0,
    )

    OA.handle_import_style(ctx)

    assert ax._operando_cif_tick_series[0][0] == "Renamed phase"
    assert ax._operando_cif_tick_series[0][-1] == "#ff0000"


def test_operando_colormap_helpers_apply_numeric_and_reverse_choice():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()

    assert OC.resolve_operando_colormap_choice("1_r").endswith("_r")
    OC.apply_operando_colormap(im, "1_r")

    assert getattr(im, "_operando_cmap_name") == "viridis_r"
    assert im.get_cmap().name.endswith("_r")


def test_operando_rename_helpers_store_custom_labels():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    states = []
    inputs = iter(["x", "New X", "y", "New Y", "q"])

    OL.run_operando_rename_menu(
        fig=fig,
        ax=ax,
        snapshot=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert states == ["rename-op-x", "rename-op-y"]
    assert ax.get_xlabel() == "New X"
    assert ax.get_ylabel() == "New Y"
    assert ax._custom_labels == {"x": "New X", "y": "New Y"}


def test_operando_ec_rename_helper_tracks_y_mode():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ec_ax._ec_y_mode = "ions"
    states = []
    inputs = iter(["y", "Li content", "q"])

    OL.run_operando_ec_rename_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert states == ["rename-ec-y"]
    assert ec_ax.get_ylabel() == "Li content"
    assert ec_ax._custom_labels["y_ions"] == "Li content"


def test_operando_ec_grid_helper_updates_persisted_state():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    states = []
    inputs = iter(["t", "a", "0.75", "s", "3", "w", "both", "q"])

    OG.run_ec_grid_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
    )

    assert states == ["ec-grid", "ec-grid", "ec-grid", "ec-grid"]
    assert ec_ax._ec_grid == {
        "visible": True,
        "alpha": 0.75,
        "linestyle": ":",
        "color": "0.6",
        "which": "both",
    }


def test_operando_ec_line_style_helper_updates_line():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    line = ec_ax.lines[0]
    ec_ax._ec_line = line
    states = []
    inputs = iter(["c", "red", "l", "2.5", "q"])

    OE.run_ec_line_style_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert states == ["ec-line-color", "ec-line-width"]
    assert line.get_color() == "red"
    assert line.get_linewidth() == 2.5


def test_operando_peak_helper_finds_and_writes_positions(tmp_path):
    data = np.array([[0.0, 1.0, 0.0], [0.0, 2.0, 0.0]])
    x_axis = np.array([10.0, 20.0, 30.0])

    def fake_find_peaks(_profile, **_kwargs):
        return np.array([1]), {}

    results = OP.find_operando_peaks(
        data,
        x_axis,
        x_range_min=10.0,
        x_range_max=30.0,
        include_intensity=True,
        find_peaks_func=fake_find_peaks,
    )

    assert [(row[0], round(row[1], 6), round(row[2], 6)) for row in results] == [
        (0, 20.0, 1.0),
        (1, 20.0, 2.0),
    ]
    target = tmp_path / "peaks.txt"
    OP.write_peak_results(str(target), results, include_intensity=True)
    assert "Peak position" in target.read_text(encoding="utf-8")
    assert "20.000000" in target.read_text(encoding="utf-8")


def test_operando_ions_mode_status_bar_shows_full_precision():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    t = np.linspace(0.0, 20.0, 30)
    ions_abs = np.linspace(1.0, 2.0, 30)
    ec_ax._ec_time_h = t
    ec_ax._ec_y_mode = "ions"
    ec_ax._ions_abs = ions_abs

    from batplot.plot_modes.operando.ions_axis import (
        format_ions_value,
        install_ec_ions_y_display,
        ions_value_at_time,
    )

    install_ec_ions_y_display(ec_ax, t, ions_abs)

    y_time = 12.345
    expected = ions_value_at_time(t, ions_abs, y_time)
    status = ec_ax.format_coord(2.8663, y_time)
    assert f"{expected:.3f}" in status or format_ions_value(expected) in status
    assert status.startswith("x=2.8663")
    assert "y=1.8," not in status

    # Tick label at a time position must not round 1.746 -> "1.8"
    t_arr = np.asarray(t, float)
    ions_arr = np.asarray(ions_abs, float)
    y_tick = float(t_arr[15])
    ions_at_tick = ions_value_at_time(t_arr, ions_arr, y_tick)
    fmt = ec_ax.yaxis.get_major_formatter()
    tick_label = fmt(y_tick, 0)
    assert tick_label != "1.8" or abs(ions_at_tick - 1.8) < 0.05
    assert format_ions_value(ions_at_tick, precision=3) == tick_label


def test_operando_h_offset_pixel_nudge_persists_in_style(session_path, monkeypatch):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    fig.set_dpi(100.0)
    inputs = iter(["m", "e", "d", "q", "q"])

    OV.run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        snapshot=lambda _note: None,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
    )

    expected = 0.01  # one pixel at 100 dpi
    assert getattr(ec_ax, "_ec_h_offset_in") == pytest.approx(expected)

    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "psg")
    assert cfg["geometry"]["ec_h_offset"] == pytest.approx(expected)

    setattr(ec_ax, "_ec_h_offset_in", 0.0)
    style_path = session_path("operando_ec_offset.bpsg")
    with open(style_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)

    monkeypatch.setattr(OA, "choose_style_file", lambda *_args, **_kwargs: style_path)
    ctx = OA.OperandoActionContext(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        file_paths=[str(style_path)],
        print_menu=lambda: None,
        snapshot=lambda _note="": None,
        restore=lambda: None,
        run_save_operando_session=lambda: None,
        set_fonts=lambda **_kwargs: None,
        axis_tick_width=OS._axis_tick_width,
        format_file_timestamp=lambda _path: "",
        maybe_reapply_dqdv_2d_contour=lambda *_args, **_kwargs: None,
        restore_dqdv_2d_operando_labels=lambda *_args, **_kwargs: None,
        ax_w_in=3.0,
        ax_h_in=3.0,
        cb_w_in=0.2,
        cb_gap_in=0.1,
        ec_gap_in=0.2,
        ec_w_in=1.0,
    )
    OA.handle_import_style(ctx)
    assert getattr(ec_ax, "_ec_h_offset_in") == pytest.approx(expected)


def test_operando_colorbar_h_offset_pixel_nudge():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    fig.set_dpi(72.0)
    inputs = iter(["m", "c", "a", "d", "d", "q", "q"])

    OV.run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        snapshot=lambda _note: None,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
    )

    # -1 px then +2 px => net +1 px at 72 dpi
    expected = 1.0 / 72.0
    assert getattr(cbar.ax, "_cb_h_offset_in") == pytest.approx(expected)


def test_operando_visibility_helper_toggles_dual_panel_colorbar():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    states = []

    OV.run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        snapshot=states.append,
        safe_input=lambda _prompt: "1",
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
    )

    assert states == ["toggle-visibility"]
    assert cbar.ax.get_visible() is False


def test_operando_visibility_helper_updates_label_text():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    inputs = iter(["3", "New intensity"])

    OV.run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=None,
        snapshot=lambda _note: None,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
    )

    assert cbar.ax._colorbar_label == "New intensity"


def test_operando_menu_printer_dual_panel_includes_side_panel_and_overwrites(capsys):
    fig, ax = plt.subplots()
    ec_ax = fig.add_axes([0.8, 0.1, 0.15, 0.8])
    fig._last_session_save_path = "last.pkl"
    fig._last_style_export_path = "last.bpsg"
    fig._last_figure_export_path = "last.png"

    print_operando_ec_menu(fig, ec_ax)
    out = capsys.readouterr().out

    assert "Contourplot Interactive Menu" in out
    assert "(Side Panel)" in out
    assert "el" in out and "ec curve" in out
    assert "et" in out and "time range" in out
    assert "os" in out and "overwrite session" in out
    assert "ops" in out and "overwrite style" in out
    assert "opsg" in out and "overwrite style+geom" in out
    assert "oe" in out and "overwrite figure" in out


def test_operando_menu_printer_operando_only_excludes_ec_commands(capsys):
    fig, ax = plt.subplots()

    print_operando_ec_menu(fig, None)
    out = capsys.readouterr().out

    assert "Contourplot Interactive Menu" in out
    assert "(Side Panel)" not in out
    assert "ec curve" not in out
    assert "time range" not in out
    assert "toggle colorbar/ec" not in out
    assert "toggle colorbar" in out


def test_operando_axis_tick_width_surfaces_unexpected_failures():
    class MissingTickKw:
        pass

    class BrokenTickKw:
        def get_major_ticks(self):
            return []

        @property
        def _major_tick_kw(self):
            raise RuntimeError("unexpected axis failure")

    assert OI._axis_tick_width(MissingTickKw(), "major") is None
    assert OS._axis_tick_width(MissingTickKw(), "major") is None

    with pytest.raises(RuntimeError, match="unexpected axis failure"):
        OI._axis_tick_width(BrokenTickKw(), "major")
    with pytest.raises(RuntimeError, match="unexpected axis failure"):
        OS._axis_tick_width(BrokenTickKw(), "major")
