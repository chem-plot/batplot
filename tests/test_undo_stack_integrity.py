"""Undo-stack integrity gates: multi-step histo, batch restore failure, dQ/dV ox."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.histo.interactive import _apply_state, _restore_snapshot, _snapshot_state
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import (
    build_histo_state,
    create_histo_figure,
    refresh_histo_figure,
    sync_histo_geometry,
)
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.histo.y_range import _set_ylim


def _make_histo_state():
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
    return build_histo_state(setup, source_path="test.csv")


def test_histo_multi_step_undo_restores_popped_pre_edit_snap():
    """Push-before-mutate: ``b`` must restore the popped tip, not peek under it.

    Edit A then B then one ``b`` must land on A (not baseline).
    """
    state = _make_histo_state()
    fig, ax, _ = create_histo_figure(state)
    sync_histo_geometry(fig, ax, state)
    refresh_histo_figure(fig, ax, state)

    # Mirror interactive: baseline tip, then push-before each mutate.
    history = [_snapshot_state(state, fig, ax)]

    history.append(_snapshot_state(state, fig, ax))  # pre-A
    _set_ylim(state, 0.0, 5.0)
    refresh_histo_figure(fig, ax, state)
    ylim_after_a = tuple(state.style.ylim)

    history.append(_snapshot_state(state, fig, ax))  # pre-B (== A)
    _set_ylim(state, 0.0, 20.0)
    refresh_histo_figure(fig, ax, state)
    assert tuple(state.style.ylim) == pytest.approx((0.0, 20.0))

    # Interactive ``b`` contract after fix: restore popped snap.
    assert len(history) > 1
    snap = history.pop()
    _apply_state(fig, ax, state, _restore_snapshot(snap), snap=snap)
    assert tuple(state.style.ylim) == pytest.approx(ylim_after_a)

    snap2 = history.pop()
    _apply_state(fig, ax, state, _restore_snapshot(snap2), snap=snap2)
    assert len(history) == 1
    plt.close(fig)


def test_batch_undo_all_reappends_snap_on_restore_failure():
    undo = SyncUndoStacks(2)
    undo.push_all([{"n": 0}, {"n": 0}])
    undo.push_all([{"n": 1}, {"n": 1}])
    assert undo.can_undo()

    def boom(i, snap):
        raise RuntimeError("restore boom")

    assert undo.undo_all(boom) is False
    # Level must still be undoable after a total failure.
    assert undo.can_undo() is True

    restored = []

    def ok(i, snap):
        restored.append((i, snap["n"]))

    assert undo.undo_all(ok) is True
    assert restored == [(0, 1), (1, 1)]
    assert undo.can_undo() is False


def test_batch_undo_all_partial_failure_keeps_failed_panel_level():
    undo = SyncUndoStacks(2)
    undo.push_all([{"n": 0}, {"n": 0}])
    undo.push_all([{"n": 1}, {"n": 1}])

    def maybe(i, snap):
        if i == 1:
            raise RuntimeError("panel 2 only")
        return None

    assert undo.undo_all(maybe) is True
    # Panel 0 undid; panel 1 kept its level.
    stacks = undo._stacks
    assert len(stacks[0]) == 1
    assert len(stacks[1]) == 2
    assert stacks[1][-1]["n"] == 1


def test_cpc_push_state_returns_false_on_failure(monkeypatch):
    from batplot.plot_modes.cpc import snapshots as cpc_snap
    import batplot.plot_modes.cpc.style as cpc_style

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(cpc_style, "_style_snapshot", _boom)
    history: list = []
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ok = cpc_snap.push_cpc_state(
        history,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=ax.scatter([1], [1]),
        sc_discharge=ax.scatter([1], [1]),
        sc_eff=ax2.scatter([1], [1]),
        file_data=[],
        tick_state={},
        note="x",
    )
    assert ok is False
    assert history == []
    plt.close(fig)


def test_operando_visibility_invalid_choice_does_not_snapshot():
    from batplot.plot_modes.operando import visibility as vis

    notes: list[str] = []
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((2, 2)))
    cbar = fig.colorbar(im)
    inputs = iter(["z", "q"])

    vis._run_operando_only_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=None,
        snapshot=lambda n="": notes.append(n),
        safe_input=lambda _p="": next(inputs),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        colorize_inline_commands=lambda s: s,
    )
    assert notes == []
    plt.close(fig)


def test_dqdv_ox_pops_junk_undo_when_rebuild_fails(monkeypatch):
    from batplot.plot_modes.operando import interactive as op_i

    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((4, 4)), origin="lower", aspect="auto")
    fig._dqdv_2d_v_lo = 2.0  # type: ignore[attr-defined]
    fig._dqdv_2d_v_hi = 4.0  # type: ignore[attr-defined]
    fig._dqdv_2d_v_lo_orig = 2.0  # type: ignore[attr-defined]
    fig._dqdv_2d_v_hi_orig = 4.0  # type: ignore[attr-defined]
    history: list[str] = []

    def snap(note=""):
        history.append(note or "snap")

    def pop():
        if history:
            history.pop()
            return True
        return False

    monkeypatch.setattr(
        "batplot.plot_modes.electrochem.dqdv_2d.update_dqdv_2d_potential_window",
        lambda *a, **k: False,
    )
    inputs = iter(["2.5 3.5", "q"])
    monkeypatch.setattr(op_i, "_safe_input", lambda _p="": next(inputs))
    monkeypatch.setattr(op_i, "_colorize_menu", lambda s: s)
    monkeypatch.setattr(op_i, "_colorize_prompt", lambda s: s)
    monkeypatch.setattr(op_i, "_colorize_inline_commands", lambda s: s)
    monkeypatch.setattr(op_i, "_dqdv_2d_print_potential_window", lambda _f: None)

    op_i._dqdv_2d_potential_window_menu(fig, ax, im, None, snap, pop_undo=pop)
    assert history == []
    plt.close(fig)
