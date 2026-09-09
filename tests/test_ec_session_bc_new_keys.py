"""Old EC .pkl sessions must load after capacity_mode / dual-top spine changes."""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.electrochem.session import dump_ec_session, load_ec_session
from batplot.plot_modes.electrochem.style import apply_dual_top_axis_style


def _line_rec(*, reverse: bool = False, label: str = "1"):
    x = np.linspace(0.0, 100.0, 8)
    y = np.linspace(3.0, 4.0, 8)
    if reverse:
        x = x[::-1]
    return {
        "x": x,
        "y": y,
        "style": {
            "color": "#1f77b4",
            "linewidth": 2.0,
            "linestyle": "-",
            "label": label,
            "visible": True,
            "alpha": 0.8,
            "marker": None,
            "markersize": None,
            "markerfacecolor": None,
            "markeredgecolor": None,
        },
    }


def _legacy_v2_session_dict(*, dual: bool = False, with_top_axis: bool = False):
    """Simulate a pre-capacity_mode EC session (keys that old batplot wrote)."""
    sess = {
        "kind": "ec_gc",
        "version": 2,
        "figure": {
            "size": (6.0, 4.0),
            "dpi": 100,
            "frame_size": (5.0, 3.5),
            "axes_bbox": {"left": 0.12, "bottom": 0.12, "right": 0.95, "top": 0.92},
        },
        "frame_size": (5.0, 3.5),
        "axis": {"xlim": (0.0, 100.0), "ylim": (3.0, 4.0)},
        "subplot_margins": {"left": 0.12, "right": 0.95, "bottom": 0.12, "top": 0.92},
        "lines": {
            1: {
                "charge": _line_rec(label="1"),
                "discharge": _line_rec(reverse=True, label="_nolegend_"),
            },
        },
        "visible_cycles": [1],
        "multi_file": False,
        "file_data": None,
        "font": {},
        "legend": {"visible": True, "position_inches": None, "title": "Cycle"},
        "wasd_state": {
            "top": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        },
        "tick_state": {
            "bx": True,
            "tx": True,
            "ly": True,
            "ry": False,
            "b_ticks": True,
            "t_ticks": True,
            "l_ticks": True,
            "r_ticks": False,
            "b_labels": True,
            "t_labels": True,
            "l_labels": True,
            "r_labels": False,
        },
        "tick_widths": {},
        "tick_lengths": {},
        "tick_direction": "out",
        "spines": {
            "bottom": {"linewidth": 1.0, "visible": True, "color": "#000000"},
            "top": {"linewidth": 1.0, "visible": True, "color": "#000000"},
            "left": {"linewidth": 1.0, "visible": True, "color": "#000000"},
            "right": {"linewidth": 1.0, "visible": True, "color": "#000000"},
        },
        "titles": {
            "xlabel": "Specific Capacity (mAh g$^{-1}$)",
            "ylabel": "Potential (V)",
            "xlabel_visible": True,
            "ylabel_visible": True,
        },
        "title_offsets": {},
        "display_mode": "both",
        # NOTE: deliberately no capacity_mode (old pickles)
        "source_paths": [],
        "grid": False,
        "ro_active": False,
    }
    if dual:
        xd = {
            "mode": "dual",
            "c_theoretical": 162.5,
            "swapped": False,
        }
        if with_top_axis:
            xd["top_axis"] = {
                "xlabel": "Number of ions",
                "xlabel_visible": True,
                "label_color": "#008000",
                "spine_visible": True,
                "spine_color": "#008000",
            }
        sess["xaxis_dual"] = xd
    else:
        sess["xaxis_dual"] = {"mode": "capacity", "c_theoretical": None, "swapped": False}
    return sess


def test_old_v2_session_without_capacity_mode_loads(tmp_path: Path):
    path = tmp_path / "legacy_ec.pkl"
    with path.open("wb") as fh:
        pickle.dump(_legacy_v2_session_dict(dual=False), fh, protocol=4)
    result = load_ec_session(str(path))
    assert result is not None
    fig, ax, _meta = result[:3]
    assert getattr(fig, "_gc_capacity_mode", "per_cycle") == "per_cycle"
    assert len(ax.lines) >= 1
    plt.close(fig)


def test_old_dual_session_without_top_axis_loads(tmp_path: Path):
    path = tmp_path / "legacy_dual.pkl"
    with path.open("wb") as fh:
        pickle.dump(_legacy_v2_session_dict(dual=True, with_top_axis=False), fh, protocol=4)
    result = load_ec_session(str(path))
    assert result is not None
    fig, ax, _meta = result[:3]
    assert getattr(fig, "_xaxis_mode", None) == "dual"
    assert getattr(fig, "_xaxis_secondary", None) is not None
    assert getattr(fig, "_gc_capacity_mode", "per_cycle") == "per_cycle"
    plt.close(fig)


def test_old_dual_session_with_top_axis_restores_color(tmp_path: Path):
    path = tmp_path / "legacy_dual_top.pkl"
    with path.open("wb") as fh:
        pickle.dump(_legacy_v2_session_dict(dual=True, with_top_axis=True), fh, protocol=4)
    result = load_ec_session(str(path))
    assert result is not None
    fig, ax, _meta = result[:3]
    sec = getattr(fig, "_xaxis_secondary", None)
    assert sec is not None
    from matplotlib.colors import to_rgb

    def _rgb(c):
        return tuple(round(v, 5) for v in to_rgb(c))

    assert _rgb(sec.spines["top"].get_edgecolor()) == _rgb("#008000")
    assert _rgb(sec.xaxis.label.get_color()) == _rgb("#008000")
    plt.close(fig)


def test_apply_dual_top_axis_style_tolerates_partial_cfg():
    fig, ax = plt.subplots()
    sec = ax.secondary_xaxis("top", functions=(lambda x: x, lambda x: x))
    apply_dual_top_axis_style(sec, {}, fig=fig)
    apply_dual_top_axis_style(sec, {"xlabel": "ions"}, fig=fig)
    apply_dual_top_axis_style(sec, None, fig=fig)
    assert sec.get_xlabel() == "ions"
    plt.close(fig)


def test_new_dump_still_roundtrips(tmp_path: Path):
    fig, ax = plt.subplots()
    (c,) = ax.plot([0.0, 1.0], [3.0, 4.0], label="1")
    (d,) = ax.plot([1.0, 0.0], [4.0, 3.0], label="_nolegend_")
    ax.set_xlabel("Q")
    ax.set_ylabel("V")
    fig._gc_capacity_mode = "cumulative"
    path = tmp_path / "new_ec.pkl"
    dump_ec_session(
        str(path),
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": c, "discharge": d}},
        skip_confirm=True,
    )
    result = load_ec_session(str(path))
    assert result is not None
    fig2, ax2, _meta = result[:3]
    assert getattr(fig2, "_gc_capacity_mode", None) == "cumulative"
    plt.close(fig)
    plt.close(fig2)
