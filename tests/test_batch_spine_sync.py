"""Tests for batch spine/tick sync applying to all panels."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_wasd_chrome_only,
    ec_tick_state_from_fig,
)
from batplot.plot_modes.batch_session.load import EcPanel, XyPanel
from batplot.plot_modes.batch_session.menu_ec import _capture_panel
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
from batplot.plot_modes.batch_session.xy_batch_helpers import sync_ref_wasd_to_panels
from matplotlib.colors import to_hex


def test_ec_batch_spine_tick_spacing_syncs_without_overwriting_limits():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ln1 = ax1.plot([0, 10], [0, 1], color="#ff0000")[0]
    ln2 = ax2.plot([0, 100], [0, 1], color="#00aa00")[0]
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 1)
    ax2.set_xlim(0, 100)
    ax2.set_ylim(0, 10)
    p1 = EcPanel(
        path="a.pkl",
        fig=fig1,
        ax=ax1,
        cycle_lines={1: {"charge": ln1, "discharge": None}},
        file_data=None,
    )
    p2 = EcPanel(
        path="b.pkl",
        fig=fig2,
        ax=ax2,
        cycle_lines={1: {"charge": ln2, "discharge": None}},
        file_data=None,
    )
    ax1.yaxis.set_major_locator(MultipleLocator(1.0))
    p1.fig._dqdv_smooth_settings = {"window": 11, "polyorder": 3}
    p2.fig._dqdv_smooth_settings = {"window": 5, "polyorder": 2}
    try:
        sync_style_from_ref(
            p1,
            [p1, p2],
            capture_panel=_capture_panel,
            apply_cfg=apply_ec_wasd_chrome_only,
            include_geometry=False,
        )
        assert isinstance(ax2.yaxis.get_major_locator(), MultipleLocator)
        assert float(ax2.yaxis.get_major_locator()._edge.step) == pytest.approx(1.0)
        assert ax2.get_xlim() == pytest.approx((0, 100))
        assert ax2.get_ylim() == pytest.approx((0, 10))
        # WASD sync must not clobber peer colors / dQ/dV smooth.
        assert to_hex(ln2.get_color()) == "#00aa00"
        assert getattr(p2.fig, "_dqdv_smooth_settings", {}) == {"window": 5, "polyorder": 2}
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_ec_capture_includes_tick_spacing_for_pisb():
    fig, ax = plt.subplots()
    ln = ax.plot([0, 1], [0, 1])[0]
    ax.yaxis.set_major_locator(MultipleLocator(2.5))
    p = EcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": ln, "discharge": None}},
        file_data=None,
    )
    try:
        cfg = _capture_panel(p)
        spacing = cfg.get("ticks", {}).get("spacing", {})
        assert spacing.get("y_major_step") == pytest.approx(2.5)
        assert ec_tick_state_from_fig(fig) is not None
    finally:
        plt.close(fig)


def _xy_panel(path: str, *, with_twin: bool = False) -> XyPanel:
    fig, ax = plt.subplots()
    ax.plot([0, 10], [0, 1])
    if with_twin:
        ax2 = ax.twinx()
        ax2.plot([0, 10], [0, 100])
        fig._xy_ax2 = ax2
        fig._xy_use_top_x = False
    wasd = {
        "top": {"spine": False, "ticks": False, "minor": True, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": True, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": True, "labels": True, "title": True},
        "right": {"spine": True, "ticks": True, "minor": True, "labels": True, "title": False},
    }
    fig._bp_wasd_state = wasd
    return XyPanel(path=path, fig=fig, ax=ax, menu_kwargs={})


def test_batch_xy_wasd_sync_preserves_custom_minors_all_sides():
    """Batch ``t`` sync must keep custom minor locators for top/bottom/left/right."""
    ref = _xy_panel("a.pkl")
    peer = _xy_panel("b.pkl")
    ref.ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ref.ax.yaxis.set_minor_locator(MultipleLocator(0.25))
    peer.ax.xaxis.set_minor_locator(AutoMinorLocator())
    peer.ax.yaxis.set_minor_locator(AutoMinorLocator())
    try:
        sync_ref_wasd_to_panels(ref, [ref, peer])
        assert isinstance(peer.ax.xaxis.get_minor_locator(), AutoMinorLocator)
        assert int(peer.ax.xaxis.get_minor_locator().ndivs) == 5
        assert isinstance(peer.ax.yaxis.get_minor_locator(), MultipleLocator)
        assert float(peer.ax.yaxis.get_minor_locator()._edge.step) == pytest.approx(0.25)
        # All four minor sides remain enabled after sync.
        wasd = peer.fig._bp_wasd_state
        assert wasd["top"]["minor"] and wasd["bottom"]["minor"]
        assert wasd["left"]["minor"] and wasd["right"]["minor"]
    finally:
        plt.close(ref.fig)
        plt.close(peer.fig)


def test_batch_xy_twin_minor_spacing_syncs():
    ref = _xy_panel("a.pkl", with_twin=True)
    peer = _xy_panel("b.pkl", with_twin=True)
    ref_ax2 = ref.fig._xy_ax2
    peer_ax2 = peer.fig._xy_ax2
    ref_ax2.yaxis.set_minor_locator(MultipleLocator(5.0))
    peer_ax2.yaxis.set_minor_locator(AutoMinorLocator())
    try:
        sync_ref_wasd_to_panels(ref, [ref, peer])
        assert isinstance(peer_ax2.yaxis.get_minor_locator(), MultipleLocator)
        assert float(peer_ax2.yaxis.get_minor_locator()._edge.step) == pytest.approx(5.0)
    finally:
        plt.close(ref.fig)
        plt.close(peer.fig)


def test_xy_session_pkl_twin_locator_roundtrip_and_legacy_missing_key(tmp_path):
    """New key ``tick_locator_state_ax2``; old pkl without it still loads."""
    import pickle
    import types

    from batplot.plot_modes.xy import session as S

    fig, ax = plt.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax2 = ax.twinx()
    ax2.plot([0.0, 1.0], [0.0, 10.0])
    fig._xy_ax2 = ax2
    fig._xy_use_top_x = False
    fig._xy_right_y_curve_indices = frozenset({0})
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))
    ax2.yaxis.set_minor_locator(MultipleLocator(2.0))
    args = types.SimpleNamespace(stack=False, autoscale=False, norm=False, files=[])
    path = tmp_path / "xy_twin_ticks.pkl"
    ok = S.dump_session(
        str(path),
        fig=fig,
        ax=ax,
        x_data_list=[[0.0, 1.0]],
        y_data_list=[[0.0, 1.0]],
        orig_y=[[0.0, 1.0]],
        x_full_list=[[0.0, 1.0]],
        raw_y_full_list=[[0.0, 1.0]],
        offsets_list=[0.0],
        labels=["a"],
        delta=0.0,
        args=args,
        tick_state={},
        skip_confirm=True,
    )
    assert ok
    plt.close(fig)

    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    assert payload.get("tick_locator_state_ax2") is not None
    assert payload["tick_locator_state_ax2"].get("y_minor_step") == pytest.approx(2.0)

    loaded = S.load_xy_session(str(path))
    assert loaded is not None
    fig2, ax_l = loaded[0], loaded[1]
    ax2_l = getattr(fig2, "_xy_ax2", None)
    assert ax2_l is not None
    assert isinstance(ax_l.xaxis.get_minor_locator(), AutoMinorLocator)
    assert int(ax_l.xaxis.get_minor_locator().ndivs) == 5
    assert isinstance(ax2_l.yaxis.get_minor_locator(), MultipleLocator)
    assert float(ax2_l.yaxis.get_minor_locator()._edge.step) == pytest.approx(2.0)
    plt.close(fig2)

    # Legacy: strip ax2 locator key — load must not crash (BC).
    legacy = dict(payload)
    legacy.pop("tick_locator_state_ax2", None)
    legacy_path = tmp_path / "xy_twin_legacy.pkl"
    with open(legacy_path, "wb") as fh:
        pickle.dump(legacy, fh)
    loaded2 = S.load_xy_session(str(legacy_path))
    assert loaded2 is not None
    plt.close(loaded2[0])
