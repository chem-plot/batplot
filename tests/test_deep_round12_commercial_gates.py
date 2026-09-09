"""Round 12 commercial-ship gates: GC ions labels, histo t widths, OS paths/CIF."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.ec_batch_helpers import ec_tick_state_from_fig
from batplot.plot_modes.common.sources import (
    cif_present,
    normalize_source_paths,
    path_token_without_suffix,
)
from batplot.plot_modes.electrochem.dqdv_2d import (
    build_dqdv_2d_snapshot,
    restore_dqdv_2d_companion_figure,
)
from batplot.plot_modes.electrochem.style import _geom_label_text
from batplot.plot_modes.histo.spines import (
    capture_histo_spine_snapshot,
    persist_histo_spine_before_redraw,
)


def test_ec_dual_set_bottom_xlabel_keeps_store_in_sync():
    from batplot.plot_modes.electrochem.dual_axis_menu import _set_bottom_xlabel

    fig, ax = plt.subplots()
    ax._stored_xlabel = "Specific Capacity (mAh g$^{-1}$)"
    ions = "Number of ions (C / 100 mAh g$^{-1}$)"
    _set_bottom_xlabel(ax, ions)
    assert ax.get_xlabel() == ions
    assert ax._stored_xlabel == ions
    # EC dump prefers store when present — sync is what makes ions round-trip.
    assert _geom_label_text(ax, "_stored_xlabel", ax.get_xlabel) == ions
    plt.close(fig)


def test_ec_tick_state_infers_labels_from_legacy_when_omitted():
    fig, ax = plt.subplots()
    ax._saved_tick_state = {
        "bx": True,
        "tx": True,
        "ly": False,
        "ry": False,
        "mbx": True,
        "b_ticks": True,
        "t_ticks": True,
        "l_ticks": False,
        "r_ticks": False,
    }
    ts = ec_tick_state_from_fig(fig, ax)
    assert ts["tx"] is True
    assert ts["t_labels"] is True
    assert ts["mbx"] is True
    assert ts["ly"] is False
    plt.close(fig)


def test_dqdv_custom_ylabel_survives_wasd_restore():
    fig, ax = plt.subplots()
    Z = np.linspace(0, 1, 20).reshape(4, 5)
    im = ax.imshow(Z, origin="lower", extent=(0, 2, -0.5, 3.5), aspect="auto")
    ax.set_xlabel("Potential")
    ax.set_ylabel("Cycle")
    ax.xaxis.label.set_visible(False)
    ax._custom_labels = {"x": "", "y": "Rows"}
    cbar_ax = fig.add_axes((0.9, 0.1, 0.02, 0.8))

    class _CB:
        def __init__(self, cax):
            self.ax = cax

    try:
        snap = build_dqdv_2d_snapshot(
            fig, ax, im, 2.0, 4.0, ["1", "2", "3", "4"], "dQ/dV", cbar=_CB(cbar_ax)
        )
        restored = restore_dqdv_2d_companion_figure(snap)
        assert restored is not None
        _cfig, cax, _im, _cbar = restored
        assert cax.get_ylabel() == "Rows"
        assert getattr(cax, "_stored_ylabel", None) == "Rows"
        plt.close(_cfig)
    finally:
        plt.close(fig)


def test_persist_histo_spine_before_redraw_strips_peer_widths():
    fig, ax = plt.subplots()
    peer_fig, peer_ax = plt.subplots()
    ax.spines["bottom"].set_linewidth(3.5)
    peer_ax.spines["bottom"].set_linewidth(0.8)
    snap = capture_histo_spine_snapshot(fig, ax)
    assert "spine_linewidths" in snap
    persist_histo_spine_before_redraw(fig, ax, sync_targets=[(peer_fig, peer_ax)])
    # Peer must keep its own width (``l``), not inherit from reference ``t`` sync.
    assert peer_ax.spines["bottom"].get_linewidth() == pytest.approx(0.8)
    plt.close(fig)
    plt.close(peer_fig)


def test_path_token_and_cif_present_windows_drive_and_wl():
    assert path_token_without_suffix(r"C:\data\phase.cif").lower().endswith(".cif")
    assert path_token_without_suffix(r"C:\data\phase.cif:1.54").lower().endswith(".cif")
    assert path_token_without_suffix(r"\\?\C:\data\phase.cif:1.54").lower().endswith(".cif")
    assert path_token_without_suffix("phase.cif:1.54").lower().endswith(".cif")
    assert cif_present([r"C:\data\phase.cif:1.5406"]) is True
    assert cif_present([r"\\?\C:\data\phase.cif:1.5406"]) is True
    assert cif_present(["phase.cif:CuKa"]) is True


def test_normalize_source_paths_expanduser(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    target = home / "curve.xy"
    target.write_text("1 2\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    # On Windows expanduser uses USERPROFILE; also set that for parity.
    monkeypatch.setenv("USERPROFILE", str(home))
    out = normalize_source_paths([os.path.join("~", "curve.xy")])
    assert out == [str(target.resolve())]
