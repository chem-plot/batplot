"""Style import (``i``) integrity: no junk undo, no hitchhiking, rollback on fail."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.batch_panel_state import _export_ec_style
from batplot.plot_modes.histo import actions as HA
from batplot.plot_modes.histo.interactive import _apply_style_file
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure, refresh_histo_figure
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config


class _Feed:
    def __init__(self, *lines):
        self._it = iter(lines)

    def __call__(self, *_a, **_k):
        return next(self._it)


def test_histo_wrong_kind_rejects_and_restores(tmp_path, monkeypatch):
    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 3.0, 4.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    state = build_histo_state(
        HistoSetup(
            column_index=1,
            column_name="Length",
            values=values,
            xmin=float(edges[0]),
            xmax=float(edges[-1]),
            bin_edges=edges,
        ),
        source_path=str(tmp_path / "data.csv"),
    )
    refresh_histo_figure(fig, ax, state)
    history = [{"base": True}]
    restores = []

    bad = tmp_path / "ec.bps"
    bad.write_text(json.dumps({"kind": "ec_style", "version": 2}), encoding="utf-8")
    monkeypatch.setattr(HA, "choose_style_file", lambda *a, **k: str(bad))

    def _restore():
        restores.append(1)
        if history:
            history.pop()

    ctx = HA.HistoActionContext(
        fig=fig,
        ax=ax,
        state=state,
        source_file_paths=[state.source_path],
        safe_input=_Feed("y"),
        colorize_prompt=lambda s: s,
        format_file_timestamp=lambda *_a, **_k: "",
        push_state=lambda: history.append({"pushed": True}),
        pop_undo=lambda: history.pop() if history else None,
        restore_state=_restore,
        save_session=lambda *_a, **_k: None,
        export_style=lambda *_a, **_k: None,
        export_figure=lambda *_a, **_k: None,
        apply_style_file=lambda path: _apply_style_file(fig, ax, state, path),
    )
    before = len(history)
    HA.handle_style_import(ctx)
    assert len(history) == before
    assert restores == [1]
    plt.close(fig)


def test_operando_ions_style_preflight_before_chrome_mutate():
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((4, 4)), origin="lower")
    cbar = fig.colorbar(im)
    ec_ax = ax.twinx()
    # No _ec_current_mA → ions import must abort before chrome changes.
    ax.set_xlabel("KEEP_X")
    cfg = {
        "kind": "operando_ec_style",
        "version": 2,
        "operando": {"xlabel": "MUTATED_X"},
        "ec": {
            "y_mode": "ions",
            "ion_params": {
                "mass_mg": 1.0,
                "cap_per_ion_mAh_g": 1.0,
                "start_ions": 0.0,
                "material": "cathode",
            },
        },
    }
    ok = apply_operando_ec_style_config(
        cfg, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, silent=True
    )
    assert ok is False
    assert ax.get_xlabel() == "KEEP_X"
    plt.close(fig)


def test_batch_ec_ps_export_strips_xaxis_dual(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [3.0, 3.5])

    class _Panel:
        def __init__(self):
            self.fig = fig
            self.ax = ax
            self.cycle_lines = {}
            self.file_data = None
            self.tick_state = {}
            self.is_multi_file = False

    # Capture path uses menu helpers; stub via direct cfg write through exporter
    # by monkeypatching capture inside batch_panel_state.
    import batplot.plot_modes.batch_session.batch_panel_state as bps

    def _fake_capture(_panel):
        return {
            "kind": "ec_style_geom",
            "xaxis_dual": {"mode": "dual", "c_theoretical": 100.0},
            "geometry": {"xlim": [0, 1]},
            "figure": {"canvas_size": [8, 6]},
        }

    bps._capture_ec = _fake_capture  # type: ignore[attr-defined]
    out = tmp_path / "ec_ps.bps"
    _export_ec_style(_Panel(), str(out), "ps")
    cfg = json.loads(out.read_text(encoding="utf-8"))
    assert cfg["kind"] == "ec_style"
    assert "xaxis_dual" not in cfg
    assert "geometry" not in cfg
    plt.close(fig)
