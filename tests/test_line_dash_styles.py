"""Line style menu fixes and dashed-line support (EC/XY/operando).

Covers:
* the marker-size prompt applying once and returning (no endless re-apply loop),
* new da/dd dashed styles in the EC line submenu,
* the operando EC-line style submenu (s),
* custom dash patterns surviving p/i/s/b via the ``_bp_dash_pattern`` tag
  (matplotlib's ``get_linestyle()`` cannot return custom dash tuples).
"""

import numpy as np
import matplotlib.pyplot as plt

from batplot import session as S
from conftest import loaded
from batplot.plot_modes.common.line_dash import (
    capture_dash_pattern,
    clear_dash_pattern,
    restore_dash_pattern,
    set_dash_pattern,
)
from batplot.plot_modes.electrochem.line_style import run_ec_line_style_menu
from batplot.plot_modes.operando.line_style import run_ec_line_style_menu as run_op_ec_line_style_menu


def _feed(*vals):
    it = iter(vals)

    def _in(*_a, **_k):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _in


def _identity(s):
    return s


def _noop(*_a, **_k):
    pass


def _build_ec_figure():
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, color="#ff0000", lw=2.0, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, color="#0000ff", lw=1.5, label="cycle 1 discharge")
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    return fig, ax, cycle_lines


def _iter_cycle_lines(cl):
    for cyc, seg in (cl or {}).items():
        if isinstance(seg, dict):
            for role, ln in seg.items():
                if ln is not None:
                    yield cyc, role, ln
        else:
            yield cyc, "line", seg


def _run_ec_menu(fig, ax, cycle_lines, keys, push_counter=None):
    def _push(_note):
        if push_counter is not None:
            push_counter.append(_note)

    run_ec_line_style_menu(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=[{"cycle_lines": cycle_lines, "visible": True, "filename": "Data"}],
        current_file_idx=0,
        is_multi_file=False,
        is_dqdv=False,
        print_file_list=_noop,
        iter_cycle_lines=_iter_cycle_lines,
        rebuild_legend=_noop,
        apply_stored_smooth_settings=_noop,
        push_state=_push,
        safe_input=_feed(*keys),
        colorize_menu=_identity,
        colorize_prompt=_identity,
    )


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

def test_dash_helpers_round_trip():
    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1], [0, 1])
    set_dash_pattern(ln, (6.0, 3.0))
    dp = capture_dash_pattern(ln)
    assert dp == [0.0, [6.0, 3.0]]

    ln2, = ax.plot([0, 1], [1, 0])
    restore_dash_pattern(ln2, dp)
    assert getattr(ln2, "_bp_dash_pattern") == (0.0, (6.0, 3.0))

    clear_dash_pattern(ln)
    assert capture_dash_pattern(ln) is None
    plt.close(fig)


def test_restore_dash_pattern_noop_on_missing():
    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1], [0, 1])
    restore_dash_pattern(ln, None)  # old sessions have no dash_pattern key
    assert capture_dash_pattern(ln) is None
    assert ln.get_linestyle() == "-"
    plt.close(fig)


# ---------------------------------------------------------------------------
# EC line submenu behavior
# ---------------------------------------------------------------------------

def test_ec_dots_only_applies_once_and_returns():
    """Blank marker size must apply once and return, not re-prompt forever."""
    fig, ax, cycle_lines = _build_ec_figure()
    pushes = []
    # d -> blank (auto size) -> back at submenu -> q. If the old loop were
    # still present, the feed exhaustion 'q' answers would be eaten by the
    # marker prompt and only one apply would still occur, so also assert
    # exactly one push_state.
    _run_ec_menu(fig, ax, cycle_lines, ["d", "", "q"], push_counter=pushes)
    assert pushes == ["dots-only"]
    for _c, _r, ln in _iter_cycle_lines(cycle_lines):
        assert ln.get_linestyle() == "None"
        assert ln.get_marker() == "o"
    plt.close(fig)


def test_ec_dots_only_custom_marker_size():
    fig, ax, cycle_lines = _build_ec_figure()
    pushes = []
    _run_ec_menu(fig, ax, cycle_lines, ["d", "3", "q"], push_counter=pushes)
    assert pushes == ["dots-only"]
    charge = cycle_lines[1]["charge"]
    assert charge.get_markersize() == 3.0
    plt.close(fig)


def test_ec_dashed_line_applies_and_tags():
    fig, ax, cycle_lines = _build_ec_figure()
    pushes = []
    _run_ec_menu(fig, ax, cycle_lines, ["da", "", "q"], push_counter=pushes)
    assert pushes == ["dashed-line"]
    for _c, _r, ln in _iter_cycle_lines(cycle_lines):
        assert getattr(ln, "_bp_dash_pattern") == (0.0, (6.0, 3.0))
        assert ln.get_marker() in ("None", None, "")
    plt.close(fig)


def test_ec_dashdot_line_custom_pattern():
    fig, ax, cycle_lines = _build_ec_figure()
    _run_ec_menu(fig, ax, cycle_lines, ["dd", "4 2", "q"])
    charge = cycle_lines[1]["charge"]
    dash = getattr(charge, "_bp_dash_pattern")
    assert dash[0] == 0.0
    assert dash[1] == (4.0, 2.0, 0.8, 2.0)  # dot = min(dash*0.2, 2.0)
    plt.close(fig)


def test_ec_line_only_clears_dash():
    fig, ax, cycle_lines = _build_ec_figure()
    _run_ec_menu(fig, ax, cycle_lines, ["da", "", "l", "q"])
    for _c, _r, ln in _iter_cycle_lines(cycle_lines):
        assert capture_dash_pattern(ln) is None
        assert ln.get_linestyle() == "-"
    plt.close(fig)


def test_ec_dash_prompt_q_backs_out_without_change():
    fig, ax, cycle_lines = _build_ec_figure()
    pushes = []
    _run_ec_menu(fig, ax, cycle_lines, ["da", "q", "q"], push_counter=pushes)
    assert pushes == []
    for _c, _r, ln in _iter_cycle_lines(cycle_lines):
        assert ln.get_linestyle() == "-"
    plt.close(fig)


# ---------------------------------------------------------------------------
# Operando EC line style submenu
# ---------------------------------------------------------------------------

def _build_operando_ec():
    fig, ec_ax = plt.subplots()
    th = np.linspace(0.0, 10.0, 50)
    vv = np.linspace(3.0, 4.2, 50)
    ln, = ec_ax.plot(vv, th, color="tab:blue", lw=1.0)
    ec_ax._ec_line = ln
    return fig, ec_ax, ln


def test_operando_style_dashed():
    fig, ec_ax, ln = _build_operando_ec()
    run_op_ec_line_style_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=_noop,
        safe_input=_feed("s", "da", "", "q"),
        colorize_menu=_identity,
        colorize_prompt=_identity,
    )
    assert getattr(ln, "_bp_dash_pattern") == (0.0, (6.0, 3.0))
    assert ln.get_marker() in ("None", None, "")
    plt.close(fig)


def test_operando_style_dots_applies_once():
    fig, ec_ax, ln = _build_operando_ec()
    snaps = []
    run_op_ec_line_style_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=lambda note: snaps.append(note),
        safe_input=_feed("s", "d", "", "q"),
        colorize_menu=_identity,
        colorize_prompt=_identity,
    )
    assert snaps == ["ec-line-style"]
    assert ln.get_linestyle() == "None"
    assert ln.get_marker() == "o"
    plt.close(fig)


# ---------------------------------------------------------------------------
# Persistence (s = save session)
# ---------------------------------------------------------------------------

def test_ec_session_roundtrip_preserves_dash(session_path):
    fig, ax, cycle_lines = _build_ec_figure()
    _run_ec_menu(fig, ax, cycle_lines, ["da", "8 4", "q"])
    p = session_path("ec_dash.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    fig2, ax2, _meta = loaded(S.load_ec_session(p))
    assert len(ax2.lines) >= 2
    for ln in ax2.lines[:2]:
        assert getattr(ln, "_bp_dash_pattern", None) == (0.0, (8.0, 4.0))
    plt.close(fig)
    plt.close(fig2)


def test_xy_session_roundtrip_preserves_dash(session_path, fake_args):
    x = np.linspace(0.0, 100.0, 200)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ln, = ax.plot(x, y, label="c1")
    set_dash_pattern(ln, (5.0, 2.0))
    p = session_path("xy_dash.pkl")
    S.dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[x], y_data_list=[y], orig_y=[y],
        x_full_list=[x], raw_y_full_list=[y],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state={}, skip_confirm=True,
    )
    fig2, ax2, _mk = loaded(S.load_xy_session(p))
    ln2 = ax2.lines[0]
    assert getattr(ln2, "_bp_dash_pattern", None) == (0.0, (5.0, 2.0))
    plt.close(fig)
    plt.close(fig2)


def test_ec_lines_state_includes_dash_pattern():
    from batplot.plot_modes.electrochem.session import _ec_cycle_lines_to_lines_state

    fig, ax, cycle_lines = _build_ec_figure()
    set_dash_pattern(cycle_lines[1]["charge"], (6.0, 3.0))
    state = _ec_cycle_lines_to_lines_state(cycle_lines)
    st = state[1]["charge"]["style"]
    assert st["dash_pattern"] == [0.0, [6.0, 3.0]]
    assert state[1]["discharge"]["style"]["dash_pattern"] is None
    plt.close(fig)
