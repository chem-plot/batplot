"""Hard gates for residual PISB bugs found in deep verification."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.cpc.style import _style_snapshot
from batplot.plot_modes.electrochem.dqdv_2d import _dqdv_2d_restore_custom_labels
from batplot.plot_modes.electrochem.style import _get_style_snapshot
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config


def test_ec_style_geom_accepts_tuple_canvas_size():
    fig, ax = plt.subplots(figsize=(5.0, 4.0))
    try:
        cfg = {
            "kind": "ec_style_geom",
            "figure": {"canvas_size": (9.0, 7.0)},
            "wasd_state": {},
            "ticks": {},
            "spines": {},
        }
        apply_ec_style_config(
            cfg,
            fig=fig,
            ax=ax,
            cycle_lines={},
            file_data=None,
            tick_state={},
            silent=True,
        )
        w, h = fig.get_size_inches()
        assert w == pytest.approx(9.0)
        assert h == pytest.approx(7.0)
    finally:
        plt.close(fig)


def test_ec_style_snapshot_preserves_empty_stored_labels():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax._stored_xlabel = ""
    ax._stored_ylabel = ""
    ax.set_xlabel("live-x")
    ax.set_ylabel("live-y")
    try:
        snap = _get_style_snapshot(fig, ax, {}, {}, None)
        assert snap["axis_labels"]["xlabel"] == ""
        assert snap["axis_labels"]["ylabel"] == ""
    finally:
        plt.close(fig)


def test_cpc_style_snapshot_preserves_empty_stored_labels():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc = ax.scatter([1], [1])
    sc2 = ax.scatter([1], [2])
    sc3 = ax2.scatter([1], [90])
    ax._stored_xlabel = ""
    ax._stored_ylabel = ""
    ax2._stored_ylabel = ""
    ax.set_xlabel("live-x")
    ax.set_ylabel("live-y")
    ax2.set_ylabel("live-r")
    try:
        snap = _style_snapshot(fig, ax, ax2, sc, sc2, sc3, file_data=None)
        assert snap["axis_labels"]["xlabel"] == ""
        assert snap["axis_labels"]["ylabel_left"] == ""
        assert snap["axis_labels"]["ylabel_right"] == ""
    finally:
        plt.close(fig)


def test_dqdv_restore_applies_empty_custom_labels():
    fig, ax = plt.subplots()
    ax.set_xlabel("Voltage")
    ax.set_ylabel("Cycle")
    ax._custom_labels = {"x": "", "y": ""}
    try:
        _dqdv_2d_restore_custom_labels(ax)
        assert ax.get_xlabel() == ""
        assert ax.get_ylabel() == ""
    finally:
        plt.close(fig)


def test_cpc_interactive_wasd_wires_title_offset_handler():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "batplot/plot_modes/cpc/wasd_menu.py"
    text = src.read_text(encoding="utf-8")
    assert "title_offset_handler=_title_offsets" in text
    assert 'axis_by_side={"d": ax2}' in text


def test_ec_batch_wasd_scoped_includes_xaxis_dual():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "batplot/plot_modes/batch_session/ec_batch_helpers.py"
    )
    text = src.read_text(encoding="utf-8")
    assert '"xaxis_dual"' in text
    assert "initial_side=side" in text


def test_histo_batch_density_uses_state_y_label_default():
    """Regression: batch density must not call HistoStyle.y_label_default()."""
    import numpy as np

    from batplot.plot_modes.batch_session.load import HistoPanel
    from batplot.plot_modes.histo.load import build_bin_edges
    from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
    from batplot.plot_modes.histo.wizard import HistoSetup

    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="L",
        values=values,
        xmin=0.0,
        xmax=10.0,
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="a.csv")
    fig, ax, _ = create_histo_figure(state)
    # Mirror the fixed batch path: state method, not style method.
    prev = state.y_label_default()
    assert prev == "Count"
    state.style.density = not state.style.density
    state.style.ylabel = state.y_label_default()
    assert state.style.ylabel == "Density"
    assert not hasattr(state.style, "y_label_default")
    plt.close(fig)


def test_batch_import_prepare_pops_skipped_indices():
    from batplot.plot_modes.batch_session.batch_io import run_batch_import_style
    from batplot.plot_modes.batch_session.common import SyncUndoStacks, make_style_import_prepare

    class _P:
        def __init__(self, n):
            self.n = n
            self.val = 0

    panels = [_P(0), _P(1), _P(2)]
    undo = SyncUndoStacks(3)
    undo.push_all([{"n": i, "base": True} for i in range(3)])

    def capture(p):
        return {"n": p.n, "val": p.val}

    def restore(panel, snap):
        panel.val = snap["val"]

    prepare = make_style_import_prepare(undo, panels, capture, restore)

    # Monkeypatch prompts / loaders via direct call internals by injecting:
    # Use prepare+apply path by temporarily patching helpers.
    from batplot.plot_modes.batch_session import batch_io as bio

    orig_prompt = bio.prompt_panel_indices
    orig_safe = bio.safe_input
    try:
        bio.prompt_panel_indices = lambda panels, verb="": [0, 1, 2]
        bio.safe_input = lambda *a, **k: "dummy.json"

        def load_style(_path):
            return {"kind": "x"}

        def apply_style(panel, _cfg):
            # Soft-fail after mutate (operando ions-class crack).
            panel.val = 9
            if panel.n == 1:
                return False
            return True

        out = bio.run_batch_import_style(
            panels,
            path_prompt="x: ",
            load_style=load_style,
            apply_style=apply_style,
            prepare=prepare,
        )
        assert out == [0, 2]
        # Skipped panel 1 must not have an extra undo frame.
        assert len(undo._stacks[1]) == 1
        assert len(undo._stacks[0]) == 2
        assert len(undo._stacks[2]) == 2
        # Failed panel must be rolled back to pre-import value.
        assert panels[1].val == 0
        assert panels[0].val == 9
        assert panels[2].val == 9
    finally:
        bio.prompt_panel_indices = orig_prompt
        bio.safe_input = orig_safe


def test_xy_rejects_foreign_style_kind(tmp_path):
    import json

    from batplot.plot_modes.xy import style as ST

    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    path = tmp_path / "ec.bps"
    path.write_text(json.dumps({"kind": "ec_style", "version": 2}), encoding="utf-8")
    try:
        ok = ST.apply_style_config(
            str(path),
            fig,
            ax,
            [__import__("numpy").array([0, 1])],
            [__import__("numpy").array([1, 2])],
            [__import__("numpy").array([1, 2])],
            [0.0],
            [],
            type("A", (), {"stack": False, "xaxis": "2theta"})(),
            {},
            ["c1"],
            update_labels_func=lambda *a, **k: None,
        )
        assert ok is False
    finally:
        plt.close(fig)


def test_cpc_bottom_title_uses_label_visibility():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc = ax.scatter([1], [1])
    sc2 = ax.scatter([1], [2])
    sc3 = ax2.scatter([1], [90])
    ax.set_xlabel("Cycles")
    ax.xaxis.label.set_visible(False)
    try:
        snap = _style_snapshot(fig, ax, ax2, sc, sc2, sc3, file_data=None)
        assert snap["wasd_state"]["bottom"]["title"] is False
    finally:
        plt.close(fig)


def test_operando_ion_params_capture_is_copy():
    from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2

    fig, ax = plt.subplots()
    ec_ax = fig.add_axes([0.1, 0.1, 0.3, 0.3])
    live = {"mass_mg": 1.0, "mw": 100.0}
    ec_ax._ion_params = live
    ec_ax._ec_y_mode = "time"
    im = ax.imshow([[0, 1], [1, 0]])
    cbar = fig.colorbar(im, ax=ax)
    try:
        cfg, _ext = build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
        ip = (cfg.get("ec") or {}).get("ion_params")
        assert isinstance(ip, dict)
        assert ip is not live
        ip["mass_mg"] = 999.0
        assert live["mass_mg"] == 1.0
    finally:
        plt.close(fig)
