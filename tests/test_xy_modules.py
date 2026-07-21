"""Focused tests for the extracted XY interactive helper modules.

The XY ``interactive.py`` dispatcher was split into single-purpose modules
(``game``, ``peaks``, ``data_ops``, ``line_style``, ``labels``, ``colors``,
``menu``, ``arrange``, ``axis_range``, ``derivative``, ``smoothing``,
``cif``) to match the taxonomy used by the other plot modes. These tests
guard the contracts so a future refactor cannot silently re-inline or break a
command, and verify the pure numeric helpers.
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from conftest import assert_allclose

from batplot.plot_modes.xy import data_ops as DO
from batplot.plot_modes.xy.game import play_jump_game
from batplot.plot_modes.xy.peaks import run_peak_finder_menu


ROOT = Path(__file__).resolve().parents[1]
XY_DIR = ROOT / "batplot" / "plot_modes" / "xy"


def _feeder(answers):
    """Return a safe_input-style callable that yields the given answers."""
    it = iter(answers)

    def _inp(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _inp


# --------------------------------------------------------------------------
# Pure numeric helpers (data_ops)
# --------------------------------------------------------------------------

def test_data_ops_first_derivative_matches_gradient():
    x = np.linspace(0.0, 10.0, 200)
    y = x ** 2
    d = DO._calculate_derivative(x, y, order=1)
    assert d.shape == y.shape
    # d/dx x^2 = 2x (interior points should be close)
    np.testing.assert_allclose(d[5:-5], (2 * x)[5:-5], rtol=1e-2, atol=1e-1)


def test_data_ops_second_derivative_shape_and_value():
    x = np.linspace(0.0, 10.0, 200)
    y = x ** 2
    d2 = DO._calculate_derivative(x, y, order=2)
    assert d2.shape == y.shape
    # d2/dx2 x^2 = 2 (interior)
    assert abs(float(np.mean(d2[10:-10])) - 2.0) < 0.1


def test_data_ops_reversed_derivative_is_inverse_slope():
    x = np.linspace(1.0, 5.0, 100)
    y = 2.0 * x  # dy/dx = 2 -> dx/dy = 0.5
    dx_dy = DO._calculate_reversed_derivative(x, y, order=1)
    assert dx_dy.shape == y.shape
    np.testing.assert_allclose(dx_dy[5:-5], np.full(dx_dy[5:-5].shape, 0.5), rtol=1e-3, atol=1e-3)


def test_data_ops_adjacent_average_preserves_constant():
    y = np.full(50, 7.0)
    out = DO._adjacent_average_smooth(y, points=5)
    assert out.shape == y.shape
    assert_allclose(out, y)


def test_data_ops_fft_smooth_returns_same_length():
    rng = np.random.default_rng(0)
    y = np.sin(np.linspace(0, 6 * np.pi, 256)) + 0.1 * rng.standard_normal(256)
    out = DO._fft_smooth(y, points=5, cutoff=0.1)
    assert out.shape == y.shape
    # low-pass output should have lower variance than the noisy input
    assert float(np.var(out)) <= float(np.var(y)) + 1e-9


# --------------------------------------------------------------------------
# Game smoke test (no plot state)
# --------------------------------------------------------------------------

def test_play_jump_game_quits_cleanly(capsys):
    # 'j' performs one step, then 'q' quits; must terminate without raising.
    play_jump_game(_feeder(["j", "q"]))
    out = capsys.readouterr().out
    assert "Jumping Bird" in out


def test_play_jump_game_immediate_quit():
    play_jump_game(_feeder(["q"]))  # should not raise


# --------------------------------------------------------------------------
# Peak finder (read-only analysis)
# --------------------------------------------------------------------------

def test_peak_finder_reports_known_peak(capsys):
    x = np.linspace(0.0, 10.0, 501)
    y = np.exp(-((x - 5.0) ** 2) / 0.5)  # single peak at x=5
    fig, ax = plt.subplots()
    ax.plot(x, y)
    ax.set_xlim(0.0, 10.0)

    # range='current', min frac default, no smoothing, do not export, then quit
    run_peak_finder_menu(
        ax=ax,
        x_data_list=[x],
        y_data_list=[y],
        offsets_list=[0.0],
        labels=["c1"],
        source_file_paths=[],
        safe_input=_feeder(["current", "", "", "n", "q"]),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    out = capsys.readouterr().out
    assert "Peak Report" in out
    assert "Peaks (x, y):" in out


def test_peak_finder_quits_immediately():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 0])
    run_peak_finder_menu(
        ax=ax,
        x_data_list=[np.array([0.0, 1.0, 2.0])],
        y_data_list=[np.array([0.0, 1.0, 0.0])],
        offsets_list=[0.0],
        labels=["c1"],
        source_file_paths=[],
        safe_input=_feeder(["q"]),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )


# --------------------------------------------------------------------------
# Module API / taxonomy contracts
# --------------------------------------------------------------------------

def test_extracted_modules_expose_expected_callables():
    import importlib

    expected = {
        "batplot.plot_modes.xy.game": "play_jump_game",
        "batplot.plot_modes.xy.peaks": "run_peak_finder_menu",
        "batplot.plot_modes.xy.line_style": "run_line_style_menu",
        "batplot.plot_modes.xy.labels": "run_xy_rename_menu",
        "batplot.plot_modes.xy.colors": "run_xy_color_menu",
        "batplot.plot_modes.xy.menu": "print_xy_menu",
        "batplot.plot_modes.xy.arrange": "run_rearrange_menu",
        "batplot.plot_modes.xy.axis_range": "run_x_range_menu",
        "batplot.plot_modes.xy.derivative": "run_derivative_menu",
        "batplot.plot_modes.xy.smoothing": "run_smoothing_menu",
        "batplot.plot_modes.xy.cif": "run_cif_ticks_menu",
    }
    for module_name, attr in expected.items():
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attr, None)), f"{module_name}.{attr} missing"
    # axis_range also exposes the y-range helper
    from batplot.plot_modes.xy import axis_range
    assert callable(getattr(axis_range, "run_y_range_menu", None))


def test_xy_dispatcher_delegates_each_command_to_its_module():
    """Guard against silently re-inlining an extracted submenu."""
    source = (XY_DIR / "interactive.py").read_text(encoding="utf-8")
    for call in (
        "run_cif_ticks_menu(",
        "run_xy_color_menu(",
        "run_xy_rename_menu(",
        "run_rearrange_menu(",
        "run_x_range_menu(",
        "run_y_range_menu(",
        "run_derivative_menu(",
        "run_line_style_menu(",
        "run_smoothing_menu(",
        "run_peak_finder_menu(",
        "play_jump_game(",
        "print_xy_menu(",
    ):
        assert call in source, f"dispatcher no longer calls {call}"


def test_xy_axis_style_roundtrip_session_and_style(session_path, fake_args):
    """Tick/label colors and labelpads must survive p/i/s/b."""
    from matplotlib import colors as mcolors

    from batplot import session as S
    from batplot import style as ST
    from batplot.plot_modes.xy.style import capture_xy_axis_style
    from conftest import loaded

    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    ax.set_xlabel("Scan", labelpad=7.5)
    ax.set_ylabel("Intensity", labelpad=11.0)
    ax.tick_params(axis="x", colors="red")
    ax.tick_params(axis="y", colors="blue")
    ax.xaxis.label.set_color("#00aa00")
    ax.yaxis.label.set_color("#0000ff")
    expected = capture_xy_axis_style(ax)

    pkl = session_path("axis_style.pkl")
    S.dump_session(
        pkl, fig=fig, ax=ax,
        x_data_list=[[0, 1]], y_data_list=[[1, 2]], orig_y=[[1, 2]],
        x_full_list=[[0, 1]], raw_y_full_list=[[1, 2]],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state={}, skip_confirm=True,
    )
    fig_s, ax_s, _ = loaded(S.load_xy_session(pkl))
    loaded_style = capture_xy_axis_style(ax_s)
    assert loaded_style["labelpads"]["x"] == expected["labelpads"]["x"]
    assert mcolors.to_hex(ax_s.xaxis.label.get_color()) == expected["axis_label_colors"]["x"]

    style_file = session_path("axis_style.bpsg")
    ST.export_style_config(
        style_file, fig, ax, [np.array([1, 2])], ["c1"], 0.0, fake_args, {},
        [0.0], overwrite_path=style_file, force_kind="psg",
    )
    fig2, ax2 = plt.subplots()
    ax2.plot([0, 1], [1, 2])
    labels = ["c1"]
    ST.apply_style_config(
        style_file, fig2, ax2, [np.array([0, 1])], [np.array([1, 2])],
        [np.array([1, 2])], [0.0], [ax2.text(0, 0, "c1")], fake_args, {},
        labels, update_labels_func=lambda *a, **k: None,
    )
    imported = capture_xy_axis_style(ax2)
    assert imported["labelpads"]["y"] == expected["labelpads"]["y"]
    assert mcolors.to_hex(ax2.xaxis.label.get_color()) == expected["axis_label_colors"]["x"]


def test_xy_spine_color_applies_tick_lines_and_pisb(tmp_path, session_path, fake_args):
    """Left spine color (a:red) must color ticks/labels like EC; survives p/i/s/b."""
    from matplotlib import colors as mcolors

    from batplot import session as S
    from batplot import style as ST
    from batplot.plot_modes.xy.spines import apply_xy_spine_color, get_xy_spine_colors
    from conftest import loaded

    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 3])
    tick_state = {"l_ticks": True, "l_labels": True, "ly": True, "b_ticks": True, "b_labels": True, "bx": True}
    ax._saved_tick_state = dict(tick_state)

    def _left_tick_red(target_ax) -> None:
        for tick in target_ax.yaxis.get_major_ticks():
            ln = getattr(tick, "tick1line", None)
            if ln is not None and ln.get_visible():
                assert mcolors.to_hex(mcolors.to_rgb(ln.get_color())) == "#ff0000"
                break
            lab = getattr(tick, "label1", None)
            if lab is not None and lab.get_visible():
                assert mcolors.to_hex(mcolors.to_rgb(lab.get_color())) == "#ff0000"

    apply_xy_spine_color(fig, ax, tick_state, "left", "red")
    _left_tick_red(ax)
    assert get_xy_spine_colors(fig).get("left") == "#ff0000"
    fig.canvas.draw()
    apply_xy_spine_color(fig, ax, tick_state, "left", "red")
    _left_tick_red(ax)

    pkl = session_path("xy_spine_color.pkl")
    S.dump_session(
        pkl, fig=fig, ax=ax,
        x_data_list=[[0, 1, 2]], y_data_list=[[1, 2, 3]], orig_y=[[1, 2, 3]],
        x_full_list=[[0, 1, 2]], raw_y_full_list=[[1, 2, 3]],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state=tick_state, skip_confirm=True,
    )
    fig_s, ax_s, _ = loaded(S.load_xy_session(pkl))
    _left_tick_red(ax_s)

    style_file = tmp_path / "xy_spine.bpsg"
    ST.export_style_config(
        str(style_file), fig, ax, [np.array([1, 2, 3])], ["c1"], 0.0, fake_args, tick_state,
        [0.0], overwrite_path=str(style_file), force_kind="psg",
    )
    fig2, ax2 = plt.subplots()
    ax2.plot([0, 1, 2], [1, 2, 3])
    ax2._saved_tick_state = dict(tick_state)
    ST.apply_style_config(
        str(style_file), fig2, ax2, [np.array([0, 1, 2])], [np.array([1, 2, 3])],
        [np.array([1, 2, 3])], [0.0], [ax2.text(0, 0, "c1")], fake_args, tick_state,
        ["c1"], update_labels_func=lambda *a, **k: None,
    )
    _left_tick_red(ax2)
    plt.close(fig)
    plt.close(fig_s)
    plt.close(fig2)


def test_batch_xy_sync_preserves_spine_tick_colors():
    """Batch XY WASD sync must not reset colored tick marks after tick_params."""
    from matplotlib import colors as mcolors

    from batplot.plot_modes.batch_session.load import XyPanel
    from batplot.plot_modes.batch_session.xy_batch_helpers import sync_ref_wasd_to_panels
    from batplot.plot_modes.common.spines import build_wasd_state
    from batplot.plot_modes.xy.spines import apply_xy_spine_color

    tick_state = {
        "b_ticks": True, "b_labels": True, "bx": True,
        "l_ticks": True, "l_labels": True, "ly": True,
        "t_ticks": False, "t_labels": False, "tx": False,
        "r_ticks": False, "r_labels": False, "ry": False,
    }

    fig1, ax1 = plt.subplots()
    ax1.plot([0, 1, 2], [1, 2, 3])
    fig1._bp_wasd_state = build_wasd_state(  # type: ignore[attr-defined]
        get_spine_visible=lambda s: ax1.spines[s].get_visible(),
        tick_state=tick_state,
        tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
        label_defaults={"top": False, "bottom": True, "left": True, "right": False},
    )
    ax1._saved_tick_state = dict(tick_state)
    apply_xy_spine_color(fig1, ax1, tick_state, "left", "red")

    fig2, ax2 = plt.subplots()
    ax2.plot([0, 1, 2], [1, 2, 3])
    fig2._bp_wasd_state = build_wasd_state(  # type: ignore[attr-defined]
        get_spine_visible=lambda s: ax2.spines[s].get_visible(),
        tick_state=tick_state,
        tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
        label_defaults={"top": False, "bottom": True, "left": True, "right": False},
    )
    ax2._saved_tick_state = dict(tick_state)

    ref = XyPanel("ref.pkl", fig1, ax1, {})
    other = XyPanel("other.pkl", fig2, ax2, {})
    sync_ref_wasd_to_panels(ref, [ref, other])

    fig2.canvas.draw()
    for tick in ax2.yaxis.get_major_ticks():
        ln = getattr(tick, "tick1line", None)
        if ln is not None and ln.get_visible():
            assert mcolors.to_hex(mcolors.to_rgb(ln.get_color())) == "#ff0000"
            break
    else:
        raise AssertionError("no visible left tick line on synced panel")

    plt.close(fig1)
    plt.close(fig2)


def test_apply_curve_color_syncs_dots_only_markers():
    """Dots-only curves must update marker colors when line color changes."""
    from matplotlib import colors as mcolors

    from batplot.plotting import apply_curve_color

    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1, 2], [1, 2, 3], color="#1f77b4")
    ln.set_linestyle("None")
    ln.set_marker("o")
    ln.set_markerfacecolor(ln.get_color())
    ln.set_markeredgecolor(ln.get_color())

    apply_curve_color(ln, "red")
    assert mcolors.to_hex(ln.get_color()) == "#ff0000"
    assert mcolors.to_hex(ln.get_markerfacecolor()) == "#ff0000"
    assert mcolors.to_hex(ln.get_markeredgecolor()) == "#ff0000"


def test_style_import_reapplies_viridis_palette_on_dots_only(session_path, fake_args):
    """Import (i) must re-apply palette colors to dots-only marker faces."""
    import json
    from matplotlib import colors as mcolors

    from batplot import style as ST
    from batplot.color_utils import get_colormap
    from batplot.plot_modes.common.palettes import sample_colormap
    from batplot.plotting import apply_curve_color

    fig, ax = plt.subplots()
    ln1, = ax.plot([0, 1, 2], [1, 2, 3], label="a")
    ln2, = ax.plot([0, 1, 2], [2, 3, 4], label="b")
    for ln in (ln1, ln2):
        ln.set_linestyle("None")
        ln.set_marker("o")
    cmap = get_colormap("viridis")
    for ln, color in zip((ln1, ln2), sample_colormap(cmap, 2)):
        apply_curve_color(ln, color)
    fig._curve_palette_history = [{
        "palette": "viridis",
        "indices": [1, 2],
        "low_clip": 0.08,
        "high_clip": 0.85,
    }]

    style_file = session_path("palette_dots.bpsg")
    ST.export_style_config(
        style_file, fig, ax, [np.array([1, 2, 3])] * 2, ["a", "b"], 0.0, fake_args, {},
        [0.0, 0.0], overwrite_path=style_file, force_kind="psg",
    )

    fig2, ax2 = plt.subplots()
    ln_a, = ax2.plot([0, 1, 2], [1, 2, 3], label="a")
    ln_b, = ax2.plot([0, 1, 2], [2, 3, 4], label="b")
    labels = ["a", "b"]
    ST.apply_style_config(
        style_file, fig2, ax2, [np.array([0, 1, 2])] * 2, [np.array([1, 2, 3]), np.array([2, 3, 4])],
        [np.array([1, 2, 3]), np.array([2, 3, 4])], [0.0, 0.0],
        [ax2.text(0, 0, "a"), ax2.text(0, 0, "b")], fake_args, {}, labels,
        update_labels_func=lambda *a, **k: None,
    )
    with open(style_file, encoding="utf-8") as fh:
        cfg = json.load(fh)
    assert cfg.get("curve_palettes")
    assert mcolors.to_hex(ln_a.get_markerfacecolor()) == mcolors.to_hex(ln1.get_markerfacecolor())
    assert mcolors.to_hex(ln_b.get_markerfacecolor()) == mcolors.to_hex(ln2.get_markerfacecolor())
    assert getattr(fig2, "_curve_palette_history", None)


def test_session_save_load_preserves_curve_palette_and_dots_colors(session_path, fake_args):
    """Save (s) / load must restore palette metadata and synced marker colors."""
    from matplotlib import colors as mcolors

    from batplot import session as S
    from batplot.color_utils import get_colormap
    from batplot.plot_modes.common.palettes import sample_colormap
    from batplot.plotting import apply_curve_color
    from conftest import loaded

    fig, ax = plt.subplots()
    ln1, = ax.plot([0, 1, 2], [1, 2, 3])
    ln2, = ax.plot([0, 1, 2], [2, 3, 4])
    for ln in (ln1, ln2):
        ln.set_linestyle("None")
        ln.set_marker("o")
    cmap = get_colormap("viridis")
    for ln, color in zip((ln1, ln2), sample_colormap(cmap, 2)):
        apply_curve_color(ln, color)
    fig._curve_palette_history = [{
        "palette": "viridis",
        "indices": [1, 2],
        "low_clip": 0.08,
        "high_clip": 0.85,
    }]

    p = session_path("palette_session.pkl")
    S.dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[[0, 1, 2], [0, 1, 2]],
        y_data_list=[[1, 2, 3], [2, 3, 4]],
        orig_y=[[1, 2, 3], [2, 3, 4]],
        x_full_list=[[0, 1, 2], [0, 1, 2]],
        raw_y_full_list=[[1, 2, 3], [2, 3, 4]],
        offsets_list=[0.0, 0.0],
        labels=["a", "b"],
        delta=0.0,
        args=fake_args,
        tick_state={},
        skip_confirm=True,
    )

    fig2, ax2, _ = loaded(S.load_xy_session(p))
    ln1_loaded = ax2.lines[0]
    ln2_loaded = ax2.lines[1]
    assert mcolors.to_hex(ln1_loaded.get_markerfacecolor()) == mcolors.to_hex(ln1.get_markerfacecolor())
    assert mcolors.to_hex(ln2_loaded.get_markerfacecolor()) == mcolors.to_hex(ln2.get_markerfacecolor())
    assert getattr(fig2, "_curve_palette_history", None)
    assert fig2._curve_palette_history[0]["palette"] == "viridis"


def test_style_import_dots_only_color_syncs_markers(session_path, fake_args):
    """Style export/import must keep dots-only marker colors aligned with curve color."""
    import json
    from matplotlib import colors as mcolors

    from batplot import style as ST
    from batplot.plotting import apply_curve_color

    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1, 2], [1, 2, 3], label="c1")
    ln.set_linestyle("None")
    ln.set_marker("o")
    apply_curve_color(ln, "blue")

    style_file = session_path("dots_only_style.bpsg")
    ST.export_style_config(
        style_file, fig, ax, [np.array([1, 2, 3])], ["c1"], 0.0, fake_args, {}, [0.0],
        overwrite_path=style_file, force_kind="psg",
    )

    fig2, ax2 = plt.subplots()
    ln2, = ax2.plot([0, 1, 2], [1, 2, 3], label="c1")
    labels = ["c1"]
    ST.apply_style_config(
        style_file, fig2, ax2, [np.array([0, 1, 2])], [np.array([1, 2, 3])],
        [np.array([1, 2, 3])], [0.0], [ax2.text(0, 0, "c1")], fake_args, {},
        labels, update_labels_func=lambda *a, **k: None,
    )
    assert mcolors.to_hex(ln2.get_color()) == "#0000ff"
    assert mcolors.to_hex(ln2.get_markerfacecolor()) == "#0000ff"
    with open(style_file, encoding="utf-8") as fh:
        cfg = json.load(fh)
    assert cfg["lines"][0]["linestyle"] == "None"
    assert cfg["lines"][0]["marker"] == "o"
