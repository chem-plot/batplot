"""Hard gates for histogram geometry keys across p / i / s / b.

Geometry surface: ``figsize``, ``axes_fraction``, ``ylim`` (menu ``g`` / ``y``).
Setup range/bins (``x``) is data geometry for ``s``/``b`` only.
"""

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
    _save_session,
    _snapshot_for_json,
    _snapshot_state,
)
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import (
    build_histo_state,
    create_histo_figure,
    refresh_histo_figure,
    sync_histo_geometry,
)
from batplot.plot_modes.histo.session import (
    apply_histo_snapshot,
    apply_histo_style_snapshot,
    capture_histo_snapshot,
    load_histo_session,
)
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.histo.y_range import _set_ylim


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


def test_histo_snapshot_prefers_live_set_position_over_stale_state():
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    sync_histo_geometry(fig, ax, state)
    # Stale state vs live GUI-like move
    state.style.figsize = (3.0, 3.0)
    state.style.axes_fraction = (0.05, 0.05, 0.4, 0.4)
    fig.set_size_inches(10.0, 7.0, forward=True)
    ax.set_position([0.22, 0.28, 0.50, 0.45])
    live = ax.get_position().bounds
    snap = _snapshot_state(state, fig, ax)
    assert snap["style"]["figsize"] == pytest.approx([10.0, 7.0])
    assert snap["style"]["axes_fraction"] == pytest.approx(list(live), abs=1e-9)
    # State itself must be updated (live authority)
    assert state.style.figsize == pytest.approx((10.0, 7.0))
    assert state.style.axes_fraction == pytest.approx(live, abs=1e-9)
    plt.close(fig)


def test_histo_session_dump_matches_live_frame_after_set_position(tmp_path):
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    fig.set_size_inches(9.0, 6.5, forward=True)
    ax.set_position([0.25, 0.30, 0.55, 0.50])
    live = ax.get_position().bounds
    path = tmp_path / "live_frame.pkl"
    _save_session(fig, ax, state, str(path))
    with open(path, "rb") as fh:
        raw = pickle.load(fh)
    af = raw["state"]["style"]["axes_fraction"]
    assert af == pytest.approx(list(live), abs=1e-9)
    assert raw["state"]["style"]["figsize"] == pytest.approx([9.0, 6.5])
    plt.close(fig)


def test_histo_psg_applies_figsize_axes_and_ylim(tmp_path):
    donor = _make_state(ylim=(0.0, 12.0), bar_color="#aabbcc")
    fig_d, ax_d, _ = create_histo_figure(donor)
    fig_d.set_size_inches(11.0, 7.5, forward=True)
    ax_d.set_position([0.18, 0.16, 0.70, 0.72])
    sync_histo_geometry(fig_d, ax_d, donor)
    path = tmp_path / "psg.bpsh"
    _export_style(fig_d, ax_d, donor, str(path), include_geometry=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "figsize" in payload["style"]
    assert "axes_fraction" in payload["style"]
    assert payload["style"]["ylim"] == pytest.approx([0.0, 12.0])

    target = _make_state(ylim=None)
    fig, ax, _ = create_histo_figure(target)
    fig.set_size_inches(5.0, 4.0, forward=True)
    ax.set_position([0.1, 0.1, 0.8, 0.8])
    sync_histo_geometry(fig, ax, target)
    apply_histo_style_snapshot(fig, ax, target, payload)
    assert target.style.figsize == pytest.approx((11.0, 7.5))
    assert target.style.axes_fraction == pytest.approx((0.18, 0.16, 0.70, 0.72), abs=1e-6)
    assert target.style.ylim == pytest.approx((0.0, 12.0))
    assert tuple(fig.get_size_inches()) == pytest.approx((11.0, 7.5), abs=1e-6)
    assert ax.get_ylim()[1] == pytest.approx(12.0)
    assert target.style.bar_color == "#aabbcc"
    plt.close(fig)
    plt.close(fig_d)


def test_histo_ps_preserves_ylim_and_does_not_resize(tmp_path):
    donor = _make_state(ylim=(0.0, 99.0), bar_color="#112233")
    fig_d, ax_d, _ = create_histo_figure(donor)
    fig_d.set_size_inches(4.0, 3.0, forward=True)
    ax_d.set_position([0.05, 0.05, 0.9, 0.9])
    sync_histo_geometry(fig_d, ax_d, donor)
    path = tmp_path / "ps.bpsh"
    _export_style(fig_d, ax_d, donor, str(path), include_geometry=False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "figsize" not in payload["style"]
    assert "axes_fraction" not in payload["style"]
    assert "ylim" not in payload["style"]

    target = _make_state(ylim=(0.0, 7.0))
    fig, ax, _ = create_histo_figure(target)
    fig.set_size_inches(10.0, 8.0, forward=True)
    ax.set_position([0.2, 0.2, 0.55, 0.55])
    sync_histo_geometry(fig, ax, target)
    before_size = tuple(fig.get_size_inches())
    before_pos = tuple(ax.get_position().bounds)
    apply_histo_style_snapshot(fig, ax, target, payload)
    assert target.style.bar_color == "#112233"
    assert target.style.ylim == pytest.approx((0.0, 7.0))
    assert tuple(fig.get_size_inches()) == pytest.approx(before_size, abs=1e-6)
    assert tuple(ax.get_position().bounds) == pytest.approx(before_pos, abs=1e-6)
    plt.close(fig)
    plt.close(fig_d)


def test_histo_psg_null_ylim_clears_fixed_to_auto(tmp_path):
    state = _make_state(ylim=(0.0, 40.0))
    fig, ax, _ = create_histo_figure(state)
    sync_histo_geometry(fig, ax, state)
    payload = _snapshot_for_json(state, fig, ax)
    payload["kind"] = "histo_style"
    payload["style"]["ylim"] = None
    assert "ylim" in payload["style"]

    apply_histo_style_snapshot(fig, ax, state, payload)
    assert state.style.ylim is None
    # Live axis must leave the forced 40.0 upper
    assert ax.get_ylim()[1] != pytest.approx(40.0)
    plt.close(fig)


def test_histo_undo_restores_figsize_and_axes_fraction():
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    fig.set_size_inches(8.0, 5.5, forward=True)
    ax.set_position([0.12, 0.12, 0.75, 0.75])
    sync_histo_geometry(fig, ax, state)
    snap = capture_histo_snapshot(state, fig, ax)

    fig.set_size_inches(12.0, 9.0, forward=True)
    ax.set_position([0.05, 0.05, 0.4, 0.4])
    sync_histo_geometry(fig, ax, state)
    assert state.style.figsize == pytest.approx((12.0, 9.0))

    apply_histo_snapshot(fig, ax, state, snap)
    assert state.style.figsize == pytest.approx((8.0, 5.5))
    assert state.style.axes_fraction == pytest.approx((0.12, 0.12, 0.75, 0.75), abs=1e-6)
    assert tuple(fig.get_size_inches()) == pytest.approx((8.0, 5.5), abs=1e-6)
    assert tuple(ax.get_position().bounds) == pytest.approx((0.12, 0.12, 0.75, 0.75), abs=1e-6)
    plt.close(fig)


def test_histo_undo_restores_setup_range_bins():
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    snap = capture_histo_snapshot(state, fig, ax)
    old_xmin = state.setup.xmin
    old_edges = state.setup.bin_edges.copy()

    new_edges = build_bin_edges(1.0, 9.0, bin_width=1.0, n_bins=None)
    state.setup.xmin = 1.0
    state.setup.xmax = 9.0
    state.setup.bin_edges = new_edges
    refresh_histo_figure(fig, ax, state)

    apply_histo_snapshot(fig, ax, state, snap)
    assert state.setup.xmin == pytest.approx(old_xmin)
    assert np.allclose(state.setup.bin_edges, old_edges)
    plt.close(fig)


def test_histo_ylim_either_order_stores_lo_hi():
    state = _make_state()
    _set_ylim(state, 20.0, 2.0)
    assert state.style.ylim == pytest.approx((2.0, 20.0))
    _set_ylim(state, 3.0, 15.0)
    assert state.style.ylim == pytest.approx((3.0, 15.0))


def test_histo_batch_entry_sync_preserves_live_frame():
    """Batch menu must sync live→state before refresh (not wipe GUI frame)."""
    state = _make_state()
    fig, ax, _ = create_histo_figure(state)
    # Stale state, live moved (as if GUI-resized before opening batch menu)
    state.style.axes_fraction = (0.05, 0.05, 0.3, 0.3)
    state.style.figsize = (4.0, 3.0)
    fig.set_size_inches(9.0, 6.0, forward=True)
    ax.set_position([0.2, 0.25, 0.6, 0.55])
    live_before = tuple(ax.get_position().bounds)

    # Exact order used by run_histo_batch_menu entry
    sync_histo_geometry(fig, ax, state)
    refresh_histo_figure(fig, ax, state)
    assert tuple(ax.get_position().bounds) == pytest.approx(live_before, abs=1e-6)
    assert state.style.axes_fraction == pytest.approx(live_before, abs=1e-6)
    assert state.style.figsize == pytest.approx((9.0, 6.0))
    plt.close(fig)


def test_histo_session_roundtrip_full_geometry_bundle(tmp_path):
    state = _make_state(ylim=(0.0, 18.0))
    fig, ax, _ = create_histo_figure(state)
    fig.set_size_inches(10.5, 7.25, forward=True)
    ax.set_position([0.15, 0.18, 0.68, 0.70])
    path = tmp_path / "geom_bundle.pkl"
    _save_session(fig, ax, state, str(path))
    loaded = load_histo_session(str(path))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    assert state2.style.figsize == pytest.approx((10.5, 7.25))
    assert state2.style.axes_fraction == pytest.approx((0.15, 0.18, 0.68, 0.70), abs=1e-6)
    assert state2.style.ylim == pytest.approx((0.0, 18.0))
    assert tuple(fig2.get_size_inches()) == pytest.approx((10.5, 7.25), abs=1e-6)
    assert ax2.get_ylim()[1] == pytest.approx(18.0)
    plt.close(fig)
    plt.close(fig2)


def test_histo_apply_state_restores_geometry_like_undo():
    state = _make_state(ylim=(0.0, 5.0))
    fig, ax, _ = create_histo_figure(state)
    fig.set_size_inches(8.0, 5.0, forward=True)
    ax.set_position([0.1, 0.1, 0.8, 0.8])
    sync_histo_geometry(fig, ax, state)
    snap = _snapshot_state(state, fig, ax)

    state.style.ylim = (0.0, 100.0)
    fig.set_size_inches(6.0, 4.0, forward=True)
    ax.set_position([0.3, 0.3, 0.4, 0.4])
    sync_histo_geometry(fig, ax, state)

    _apply_state(fig, ax, state, _restore_snapshot(snap), snap=snap)
    assert state.style.ylim == pytest.approx((0.0, 5.0))
    assert state.style.figsize == pytest.approx((8.0, 5.0))
    assert state.style.axes_fraction == pytest.approx((0.1, 0.1, 0.8, 0.8), abs=1e-6)
    plt.close(fig)
