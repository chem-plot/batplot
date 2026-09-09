"""Hard gates for histogram style keys across p / i / s / b."""

from __future__ import annotations

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.histo.interactive import (
    _apply_state,
    _export_style,
    _restore_snapshot,
    _snapshot_for_json,
    _snapshot_state,
)
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import (
    build_histo_state,
    create_histo_figure,
    refresh_histo_figure,
)
from batplot.plot_modes.histo.session import apply_histo_style_snapshot, load_histo_session
from batplot.plot_modes.histo.wizard import HistoSetup


def _make_state(**style_kw):
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0, 4.0, 5.5])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    for key, val in style_kw.items():
        setattr(state.style, key, val)
    return state


def test_histo_empty_ylabel_survives_refresh_and_style_roundtrip(tmp_path):
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    state.style.ylabel = ""
    refresh_histo_figure(fig, ax, state)
    assert state.style.ylabel == ""
    assert ax.get_ylabel() == ""

    style_path = tmp_path / "empty_ylab.bpsh"
    _export_style(fig, ax, state, str(style_path), include_geometry=False)
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["style"]["ylabel"] == ""

    state2 = _make_state()
    fig2, ax2, _ = create_histo_figure(state2)
    assert state2.style.ylabel == "Count"
    apply_histo_style_snapshot(fig2, ax2, state2, payload)
    assert state2.style.ylabel == ""
    assert ax2.get_ylabel() == ""

    plt.close(fig)
    plt.close(fig2)


def test_histo_empty_ylabel_survives_session_roundtrip(tmp_path):
    state = _make_state(ylabel="")
    fig, ax, _ = create_histo_figure(state)
    refresh_histo_figure(fig, ax, state)
    assert ax.get_ylabel() == ""

    sess = tmp_path / "empty_ylab.pkl"
    from batplot.plot_modes.histo.interactive import _save_session

    _save_session(fig, ax, state, str(sess))
    loaded = load_histo_session(str(sess))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    assert state2.style.ylabel == ""
    assert ax2.get_ylabel() == ""
    plt.close(fig)
    plt.close(fig2)


def test_histo_density_toggle_preserves_custom_and_cleared_ylabel():
    state = _make_state(ylabel="Particles")
    assert state.style.density is False
    prev = state.style.ylabel
    # Simulate interactive density toggle logic
    prev_default = state.y_label_default()
    cur = state.style.ylabel
    state.style.density = not state.style.density
    if cur == prev_default:
        state.style.ylabel = state.y_label_default()
    assert state.style.ylabel == prev
    assert state.style.density is True

    state.style.ylabel = ""
    prev_default = state.y_label_default()
    cur = state.style.ylabel
    state.style.density = not state.style.density
    if cur == prev_default:
        state.style.ylabel = state.y_label_default()
    assert state.style.ylabel == ""
    assert state.style.density is False

    # Default label still tracks mode
    state.style.ylabel = state.y_label_default()  # Count
    prev_default = state.y_label_default()
    cur = state.style.ylabel
    state.style.density = not state.style.density
    if cur == prev_default:
        state.style.ylabel = state.y_label_default()
    assert state.style.density is True
    assert state.style.ylabel == "Density"


def test_histo_style_only_ps_does_not_resize(tmp_path):
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    fig.set_size_inches(11.0, 7.0)
    ax.set_position([0.2, 0.2, 0.55, 0.55])
    from batplot.plot_modes.histo.plot import sync_histo_geometry

    sync_histo_geometry(fig, ax, state)

    # Donor style with different geometry — stripped on style-only export
    donor = _make_state(bar_color="#112233", alpha=0.4)
    fig_d, ax_d, _ = create_histo_figure(donor)
    fig_d.set_size_inches(5.0, 4.0)
    ax_d.set_position([0.1, 0.1, 0.8, 0.8])
    sync_histo_geometry(fig_d, ax_d, donor)
    style_path = tmp_path / "style.bpsh"
    _export_style(fig_d, ax_d, donor, str(style_path), include_geometry=False)
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert "figsize" not in payload["style"]
    assert "axes_fraction" not in payload["style"]

    before_size = tuple(fig.get_size_inches())
    before_pos = tuple(ax.get_position().bounds)
    apply_histo_style_snapshot(fig, ax, state, payload)
    assert state.style.bar_color == "#112233"
    assert state.style.alpha == pytest.approx(0.4)
    assert tuple(fig.get_size_inches()) == pytest.approx(before_size, abs=1e-6)
    assert tuple(ax.get_position().bounds) == pytest.approx(before_pos, abs=1e-6)

    plt.close(fig)
    plt.close(fig_d)


def test_histo_density_curve_dash_and_alpha_roundtrip_style_and_undo():
    state = _make_state(
        show_density_curve=True,
        density_curve_ls="--",
        density_curve_alpha=0.35,
        density_curve_color="#00aa00",
        density_curve_lw=2.5,
    )
    fig, ax, _ = create_histo_figure(state)
    refresh_histo_figure(fig, ax, state)
    snap = _snapshot_state(state, fig, ax)
    assert snap["style"]["density_curve_ls"] == "--"
    assert snap["style"]["density_curve_alpha"] == pytest.approx(0.35)

    # Mutate then undo via restore/_apply_state
    history = [snap]
    state.style.density_curve_ls = ":"
    state.style.density_curve_alpha = 1.0
    refresh_histo_figure(fig, ax, state)
    _apply_state(fig, ax, state, _restore_snapshot(history[-1]), snap=history[-1])
    assert state.style.density_curve_ls == "--"
    assert state.style.density_curve_alpha == pytest.approx(0.35)

    payload = _snapshot_for_json(state, fig, ax)
    payload["kind"] = "histo_style"
    state2 = _make_state()
    fig2, ax2, _ = create_histo_figure(state2)
    apply_histo_style_snapshot(fig2, ax2, state2, payload)
    assert state2.style.density_curve_ls == "--"
    assert state2.style.density_curve_alpha == pytest.approx(0.35)
    assert state2.style.show_density_curve is True

    plt.close(fig)
    plt.close(fig2)


def test_histo_font_extras_undo():
    state = _make_state(font_weight="bold", text_highlight=True, text_highlight_fc="yellow")
    fig, ax, _ = create_histo_figure(state)
    snap = _snapshot_state(state, fig, ax)
    state.style.font_weight = "normal"
    state.style.text_highlight = False
    state.style.text_highlight_fc = "white"
    _apply_state(fig, ax, state, _restore_snapshot(snap), snap=snap)
    assert state.style.font_weight == "bold"
    assert state.style.text_highlight is True
    assert state.style.text_highlight_fc == "yellow"
    plt.close(fig)


def test_histo_tick_lengths_in_style_payload():
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    fig._tick_lengths = {"major": 9.0, "minor": 4.5}
    ax.tick_params(axis="both", which="major", length=9.0)
    ax.tick_params(axis="both", which="minor", length=4.5)
    payload = _snapshot_for_json(state, fig, ax)
    assert payload.get("tick_lengths", {}).get("major") == pytest.approx(9.0)

    state2 = _make_state()
    fig2, ax2, _ = create_histo_figure(state2)
    apply_histo_style_snapshot(fig2, ax2, state2, payload)
    assert fig2._tick_lengths.get("major") == pytest.approx(9.0)
    plt.close(fig)
    plt.close(fig2)


def test_histo_batch_rename_syncs_title():
    """Batch ``r`` must copy plot title as well as axis labels."""
    # Inline the sync logic used by menu_histo._apply_ref_labels_to_all
    ref = _make_state(title="Ref Title", xlabel="X", ylabel="Y", top_xlabel="TopX")
    peer = _make_state(title="Old", xlabel="ox", ylabel="oy", top_xlabel="ot")
    rs = ref.style
    ps = peer.style
    ps.xlabel = rs.xlabel
    ps.ylabel = rs.ylabel
    ps.title = rs.title
    ps.top_xlabel = rs.top_xlabel
    assert peer.style.title == "Ref Title"
    assert peer.style.xlabel == "X"
    assert peer.style.top_xlabel == "TopX"


def test_histo_bar_alpha_in_style_export_import(tmp_path):
    state = _make_state(alpha=0.33, bar_color="#abcdef")
    fig, ax, _ = create_histo_figure(state)
    path = tmp_path / "alpha.bpsh"
    _export_style(fig, ax, state, str(path), include_geometry=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["style"]["alpha"] == pytest.approx(0.33)

    state2 = _make_state()
    fig2, ax2, _ = create_histo_figure(state2)
    apply_histo_style_snapshot(fig2, ax2, state2, payload)
    assert state2.style.alpha == pytest.approx(0.33)
    plt.close(fig)
    plt.close(fig2)


def test_histo_full_session_pickle_preserves_style_bundle(tmp_path):
    state = _make_state(
        bar_color="#101010",
        edge_color="#202020",
        alpha=0.55,
        bar_width_frac=0.7,
        show_grid=True,
        density=True,
        ylabel="Density",
        title="My histo",
        show_density_curve=True,
        density_curve_ls=":",
        density_curve_alpha=0.6,
        font_weight="bold",
        show_bar_labels=True,
        show_mean_line=True,
    )
    fig, ax, _ = create_histo_figure(state)
    path = tmp_path / "full.pkl"
    from batplot.plot_modes.histo.interactive import _save_session

    _save_session(fig, ax, state, str(path))
    with open(path, "rb") as fh:
        raw = pickle.load(fh)
    assert raw["kind"] == "histo"
    style = raw["state"]["style"]
    assert style["alpha"] == pytest.approx(0.55)
    assert style["density_curve_ls"] == ":"

    loaded = load_histo_session(str(path))
    assert loaded is not None
    _fig2, _ax2, state2 = loaded
    assert state2.style.alpha == pytest.approx(0.55)
    assert state2.style.bar_width_frac == pytest.approx(0.7)
    assert state2.style.density is True
    assert state2.style.title == "My histo"
    assert state2.style.density_curve_ls == ":"
    assert state2.style.density_curve_alpha == pytest.approx(0.6)
    assert state2.style.font_weight == "bold"
    assert state2.style.show_bar_labels is True
    assert state2.style.show_mean_line is True
    plt.close(fig)
    plt.close(_fig2)
