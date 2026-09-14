"""Deep gates for XY ``.bps`` / ``.bpsg`` key matrix (export strip + apply).

Locks:
- ps keeps/applies canvas/frame; strips curve offsets / dual-y / CIF stack offsets
- psg keeps offsets + CIF stack offsets + geometry limits
- palette history restore does not clobber ``lines[].color``
- restored axes_fraction is not stomped by ``adjust_margins_cb``
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.xy import style as ST


class _Args:
    stack = False
    xaxis = "Q"
    wl = 1.54
    files = []


def _noop(*_a, **_k):
    return None


def _export(path: Path, fig, ax, *, kind: str, offsets, cif_series=None, labels=None, stack=False):
    labels = list(labels) if labels is not None else [f"c{i+1}" for i in range(len(offsets))]
    y = [np.array([1.0, 2.0]) for _ in labels]
    ST.export_style_config(
        str(path),
        fig,
        ax,
        y,
        labels,
        0.0,
        _Args(),
        {
            "b_ticks": True, "b_labels": True, "bx": True,
            "l_ticks": True, "l_labels": True, "ly": True,
            "t_ticks": True, "t_labels": True, "tx": True,
            "r_ticks": False, "r_labels": False, "ry": False,
        },
        list(offsets),
        cif_tick_series=cif_series,
        overwrite_path=str(path),
        force_kind=kind,
    )
    # Ensure args.stack is reflected: re-set layout if needed via args on _Args
    return json.loads(path.read_text(encoding="utf-8"))


def _apply(path: Path, fig, ax, *, offsets, cif_series=None, adjust_margins_cb=None, labels=None):
    labels = list(labels) if labels is not None else [f"c{i+1}" for i in range(len(offsets))]
    ys = [np.array([1.0, 2.0]) for _ in labels]
    xs = [np.array([0.0, 1.0]) for _ in labels]
    return ST.apply_style_config(
        str(path),
        fig,
        ax,
        xs,
        ys,
        ys,
        offsets,
        [],
        _Args(),
        {},
        labels,
        update_labels_func=_noop,
        cif_tick_series=cif_series,
        adjust_margins_cb=adjust_margins_cb,
    )


def test_ps_strips_geometry_hitchhikers_keeps_style_keys(tmp_path):
    fig, ax = plt.subplots(figsize=(10.0, 6.0))
    (ln0,) = ax.plot([0, 1], [1, 2], color="#112233")
    (ln1,) = ax.plot([0, 1], [2, 3], color="#445566")
    fig._xy_lines_by_curve = [ln0, ln1]
    fig._xy_right_y_curve_indices = frozenset({1})
    fig._xy_use_top_x = True
    ax.set_position([0.085, 0.135, 0.83, 0.73])
    fig._bp_cif_stack_y_offsets = [-0.04]
    cif = [("Li2FeSeO.cif", "/tmp/x.cif", [1.0], 1.54, 10.0, "#ff0000")]
    path = tmp_path / "style.bps"
    payload = _export(path, fig, ax, kind="ps", offsets=[0.0, -1.0], cif_series=cif)

    assert payload["kind"] == "xy_style"
    assert "geometry" not in payload
    assert "right_y_curve_indices" not in payload
    assert "txaxis" not in payload
    assert "cif_stack_y_offsets" not in payload
    assert all("offset" not in e for e in payload["lines"])
    figb = payload["figure"]
    assert "size" in figb and "canvas_size" in figb
    assert "frame_size" in figb and "axes_fraction" in figb
    assert "wasd_state" in payload and "spines" in payload
    assert "font" in payload and "ticks" in payload
    plt.close(fig)


def test_psg_keeps_offsets_cif_stack_and_geometry(tmp_path):
    fig, ax = plt.subplots(figsize=(10.0, 6.0))
    (ln0,) = ax.plot([0, 1], [1, 2])
    (ln1,) = ax.plot([0, 1], [2, 3])
    fig._xy_lines_by_curve = [ln0, ln1]
    ax.set_xlim(1.0, 7.0)
    ax.set_ylim(-1.5, 1.5)
    fig._bp_cif_stack_y_offsets = [-0.0419]
    cif = [("Li2FeSeO.cif", "/tmp/x.cif", [1.0], 1.54, 10.0, "#ff0000")]
    path = tmp_path / "style.bpsg"
    payload = _export(path, fig, ax, kind="psg", offsets=[0.0, -1.0], cif_series=cif)

    assert payload["kind"] == "xy_style_geom"
    assert "geometry" in payload
    assert payload["geometry"]["xlim"] == [1.0, 7.0]
    assert payload["cif_stack_y_offsets"] == [-0.0419]
    assert [e.get("offset") for e in payload["lines"]] == [0.0, -1.0]
    plt.close(fig)


def test_ps_does_not_apply_curve_or_cif_stack_offsets(tmp_path):
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    (ln0,) = ax.plot([0, 1], [0.0, 0.0], color="red")
    (ln1,) = ax.plot([0, 1], [0.0, 0.0], color="blue")
    fig._xy_lines_by_curve = [ln0, ln1]
    fig._bp_cif_stack_y_offsets = [-0.5]
    cif = [("a.cif", "/tmp/a.cif", [1.0], None, None, "k")]
    path = tmp_path / "style.bps"
    _export(path, fig, ax, kind="ps", offsets=[0.0, -2.0], cif_series=cif)
    # Hand-inject hitchhikers into an otherwise valid xy_style file.
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["lines"][1]["offset"] = -2.0
    payload["cif_stack_y_offsets"] = [-0.9]
    path.write_text(json.dumps(payload), encoding="utf-8")
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(5.0, 5.0))
    (ln0,) = ax2.plot([0, 1], [0.0, 0.0])
    (ln1,) = ax2.plot([0, 1], [0.0, 0.0])
    fig2._xy_lines_by_curve = [ln0, ln1]
    fig2._bp_cif_stack_y_offsets = [0.0]
    cif2 = [("a.cif", "/tmp/a.cif", [1.0], None, None, "k")]
    offsets = [0.0, 0.0]
    _apply(path, fig2, ax2, offsets=offsets, cif_series=cif2)
    assert offsets == [0.0, 0.0]
    assert list(fig2._bp_cif_stack_y_offsets) == [0.0]
    plt.close(fig2)


def test_psg_applies_curve_and_cif_stack_offsets(tmp_path):
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    (ln0,) = ax.plot([0, 1], [0.0, 0.0])
    (ln1,) = ax.plot([0, 1], [0.0, 0.0])
    fig._xy_lines_by_curve = [ln0, ln1]
    fig._bp_cif_stack_y_offsets = [-0.25]
    cif = [("a.cif", "/tmp/a.cif", [1.0], None, None, "k")]
    path = tmp_path / "style.bpsg"
    _export(path, fig, ax, kind="psg", offsets=[0.0, -1.25], cif_series=cif)
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(5.0, 5.0))
    (ln0,) = ax2.plot([0, 1], [0.0, 0.0])
    (ln1,) = ax2.plot([0, 1], [0.0, 0.0])
    fig2._xy_lines_by_curve = [ln0, ln1]
    cif2 = [("a.cif", "/tmp/a.cif", [1.0], None, None, "k")]
    offsets = [0.0, 0.0]
    _apply(path, fig2, ax2, offsets=offsets, cif_series=cif2)
    assert abs(offsets[1] + 1.25) < 1e-9
    assert abs(fig2._bp_cif_stack_y_offsets[0] + 0.25) < 1e-9
    plt.close(fig2)


def test_palette_history_does_not_recolor_manual_line_colors(tmp_path):
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2], color="#aa0000")
    (ln1,) = ax.plot([0, 1], [2, 3], color="#00aa00")
    fig._xy_lines_by_curve = [ln0, ln1]
    fig._curve_palette_history = [
        {"palette": "viridis", "indices": [1, 2], "low_clip": 0.08, "high_clip": 0.85}
    ]
    path = tmp_path / "style.bps"
    payload = _export(path, fig, ax, kind="ps", offsets=[0.0, 0.0])
    assert payload.get("curve_palettes")
    # Manual colors must remain authoritative in the file.
    assert payload["lines"][0]["color"].lower() in ("#aa0000", "#aa0000")
    plt.close(fig)

    fig2, ax2 = plt.subplots()
    (ln0,) = ax2.plot([0, 1], [1, 2], color="black")
    (ln1,) = ax2.plot([0, 1], [2, 3], color="white")
    fig2._xy_lines_by_curve = [ln0, ln1]
    _apply(path, fig2, ax2, offsets=[0.0, 0.0])
    c0 = ln0.get_color()
    # Matplotlib may return hex or rgba; compare via to_hex if needed.
    from matplotlib.colors import to_hex

    assert to_hex(c0).lower() == "#aa0000"
    hist = getattr(fig2, "_curve_palette_history", None)
    assert hist and hist[0]["palette"] == "viridis"
    plt.close(fig2)


def test_adjust_margins_cb_does_not_stomp_restored_axes_fraction(tmp_path):
    fig, ax = plt.subplots(figsize=(10.0, 6.0))
    (ln0,) = ax.plot([0, 1], [1, 2])
    fig._xy_lines_by_curve = [ln0]
    ax.set_position([0.20, 0.25, 0.55, 0.50])
    path = tmp_path / "style.bps"
    _export(path, fig, ax, kind="ps", offsets=[0.0])
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(5.0, 5.0))
    (ln0,) = ax2.plot([0, 1], [1, 2])
    fig2._xy_lines_by_curve = [ln0]
    fig2.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.95)
    stomped = {"called": False}

    def _bad_adjust():
        stomped["called"] = True
        # Simulate stale-subplotpars adjust that would wipe imported frame.
        fig2.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.99)

    # Force overflow path by patching ensure_text_visibility via callback gate:
    # apply only skips adjust when applied_canvas_or_frame; still call ensure.
    # Monkeypatch at module level for check_only=True → True.
    import batplot.plot_modes.xy.style as style_mod

    real_ensure = style_mod._ui_ensure_text_visibility

    def _fake_ensure(fig, ax, labels, check_only=False, **kw):
        if check_only:
            return True
        return real_ensure(fig, ax, labels, check_only=check_only, **kw)

    style_mod._ui_ensure_text_visibility = _fake_ensure
    try:
        _apply(path, fig2, ax2, offsets=[0.0], adjust_margins_cb=_bad_adjust)
    finally:
        style_mod._ui_ensure_text_visibility = real_ensure

    assert stomped["called"] is False
    b = ax2.get_position().bounds
    assert abs(b[0] - 0.20) < 1e-6
    assert abs(b[2] - 0.55) < 1e-6
    plt.close(fig2)


def test_ps_roundtrip_wasd_spines_font_grid_titles(tmp_path):
    fig, ax = plt.subplots(figsize=(9.0, 5.5))
    (ln0,) = ax.plot([0, 1], [1, 2], color="#ff7f0e", linewidth=2.0, alpha=0.7)
    fig._xy_lines_by_curve = [ln0]
    ax.set_xlabel("Q")
    ax.set_ylabel("I")
    ax._top_xlabel_on = True
    ax._top_xlabel_text_override = "Q top"
    ax.grid(True)
    fig._tick_direction = "in"
    fig._tick_lengths = {"major": 6.0, "minor": 3.0}
    fig._curve_names_visible = False
    fig._stack_label_at_bottom = True
    path = tmp_path / "style.bps"
    payload = _export(path, fig, ax, kind="ps", offsets=[0.0])
    assert payload["grid"] is True
    assert payload["ticks"]["direction"] == "in"
    assert payload["axis_titles"]["top_x"] is True
    assert payload["axis_title_texts"]["top_x"] == "Q top"
    assert payload["curve_names_visible"] is False
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(4.0, 4.0))
    (ln0,) = ax2.plot([0, 1], [0, 1], color="k", linewidth=1.0)
    fig2._xy_lines_by_curve = [ln0]
    _apply(path, fig2, ax2, offsets=[0.0])
    assert abs(float(fig2.get_size_inches()[0]) - 9.0) < 1e-6
    assert bool(getattr(ax2, "_top_xlabel_on", False)) is True
    assert getattr(ax2, "_top_xlabel_text_override", None) == "Q top"
    assert getattr(fig2, "_curve_names_visible", True) is False
    assert getattr(fig2, "_tick_direction", "out") == "in"
    from matplotlib.colors import to_hex

    assert to_hex(ln0.get_color()).lower() == "#ff7f0e"
    plt.close(fig2)
