"""Deep behavioural coverage for ``p`` / ``i`` / ``s`` / ``b`` in every mode.

Goes beyond smoke: mutates a visible property, exports style, mutates again,
imports, undoes, and saves/loads a session. Also guards undo-stack integrity
when style import fails (corrupt JSON / pre-push errors).
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.batch_panel_state import (
    get_batch_state_handler,
    verify_panel_pisb_roundtrip,
)
from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.batch_session.load import load_batch_panels
from batplot.plot_modes.cpc import actions as CA
from batplot.plot_modes.cpc import interactive as CI
from batplot.plot_modes.electrochem import actions as EA
from batplot.plot_modes.histo import actions as HA
from batplot.plot_modes.histo.interactive import (
    _export_style,
    _save_session,
    histo_interactive_menu,
)
from batplot.plot_modes.histo.load import TableData, build_bin_edges
from batplot.plot_modes.histo.plot import HistoState, HistoStyle, refresh_histo_figure
from batplot.plot_modes.histo.session import apply_histo_style_snapshot, load_histo_session
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.operando import actions as OA
from batplot.plot_modes.xy import actions as XA
from batplot import session as S


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Feed:
    def __init__(self, *answers):
        self._a = list(answers)
        self._i = 0

    def __call__(self, *_a, **_k):
        if self._i < len(self._a):
            v = self._a[self._i]
            self._i += 1
            return v
        return "q"


def _noop(*_a, **_k):
    return None


# ---------------------------------------------------------------------------
# Undo-stack integrity on failed import (the bugs we just fixed)
# ---------------------------------------------------------------------------


def test_histo_corrupt_import_does_not_double_pop_undo(tmp_path, monkeypatch):
    from batplot.plot_modes.histo.interactive import _apply_style_file

    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 3.0, 4.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    state = HistoState(
        setup=HistoSetup(
            column_index=1,
            column_name="Length",
            values=values,
            xmin=float(edges[0]),
            xmax=float(edges[-1]),
            bin_edges=edges,
        ),
        style=HistoStyle(bar_color="#111111"),
        source_path=str(tmp_path / "data.csv"),
    )
    refresh_histo_figure(fig, ax, state)

    history = [{"style": {"bar_color": "#111111"}}, {"style": {"bar_color": "#222222"}}]
    pops = []

    bad = tmp_path / "bad.bpsh"
    bad.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(HA, "choose_style_file", lambda *a, **k: str(bad))

    restores = []

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
        pop_undo=lambda: pops.append(history.pop() if history else None),
        restore_state=_restore,
        save_session=_noop,
        export_style=_noop,
        export_figure=_noop,
        apply_style_file=lambda path: _apply_style_file(fig, ax, state, path),
    )
    before_len = len(history)
    HA.handle_style_import(ctx)
    # One push + one restore-pop → stack depth unchanged; never double-pop past baseline
    assert len(history) == before_len
    assert len(restores) == 1
    assert len(pops) == 0
    assert len(history) >= 2  # original baseline entries preserved
    plt.close(fig)


def test_ec_failed_json_before_push_does_not_pop(tmp_path, monkeypatch):
    fig, ax = plt.subplots()
    (chg,) = ax.plot([0, 1], [3.0, 3.5])
    (dch,) = ax.plot([1, 0], [3.5, 3.0])
    cycle_lines = {1: {"charge": chg, "discharge": dch}}
    pops = []
    pushes = []
    bad = tmp_path / "bad.bps"
    bad.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(EA, "choose_style_file", lambda *a, **k: str(bad))

    ctx = types.SimpleNamespace(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=None,
        source_paths=["a.mpt"],
        tick_state={},
        all_cycles=[1],
        is_dqdv=False,
        is_multi_file=False,
        menu_title="EC",
        canvas_mode=True,
        print_menu=lambda *a, **k: None,
        push_state=lambda note=None: pushes.append(note),
        pop_undo=lambda: pops.append(1),
        safe_input=_Feed(),
        colorize_prompt=lambda s: s,
    )
    EA.handle_import_style_command(ctx)
    assert pushes == []
    assert pops == []  # must not pop a prior undo entry
    plt.close(fig)


def test_operando_failed_json_before_push_does_not_pop(tmp_path, monkeypatch):
    fig, ax = plt.subplots()
    im = ax.imshow(np.random.rand(4, 4), origin="lower")
    cbar = fig.colorbar(im)
    pops = []
    snaps = []
    bad = tmp_path / "bad.bps"
    bad.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(OA, "choose_style_file", lambda *a, **k: str(bad))

    ctx = types.SimpleNamespace(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=None,
        file_paths=["a.npy"],
        print_menu=lambda: None,
        snapshot=lambda note=None: snaps.append(note),
        pop_undo=lambda: pops.append(1),
        restore=lambda: pops.append(1),
        ax_w_in=5.0,
        ax_h_in=4.0,
        cb_w_in=0.2,
        cb_gap_in=0.05,
        ec_gap_in=0.1,
        ec_w_in=1.0,
    )
    OA.handle_import_style(ctx)
    assert snaps == []
    assert pops == []
    plt.close(fig)


def test_cpc_failed_json_before_push_does_not_pop(tmp_path, monkeypatch):
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [100])
    sc_d = ax.scatter([1], [90])
    sc_e = ax2.scatter([1], [95])
    pops = []
    pushes = []
    bad = tmp_path / "bad.bps"
    bad.write_text("{broken", encoding="utf-8")

    ctx = types.SimpleNamespace(
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
        file_paths=["a.csv"],
        print_menu=lambda *_a: None,
        choose_style_file=lambda *a, **k: str(bad),
        push_state=lambda note=None: pushes.append(note),
        pop_undo=lambda: pops.append(1),
        apply_style=_noop,
    )
    CA.handle_style_import(ctx)
    assert pushes == []
    assert pops == []
    plt.close(fig)


# ---------------------------------------------------------------------------
# XY: p → i → b → s behavioural
# ---------------------------------------------------------------------------


def test_xy_pisb_style_roundtrip_and_undo_and_session(tmp_path, fake_args):
    from batplot import style as ST

    x = np.linspace(20.0, 40.0, 50)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1", color="#ff0000")
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    ax.set_xlim(20.0, 40.0)
    tick_state: dict = {}
    args = fake_args

    style_path = str(tmp_path / "xy_style.bpsg")
    out = ST.export_style_config(
        style_path,
        fig,
        ax,
        [y],
        ["c1"],
        0.0,
        args,
        tick_state,
        [0.0],
        overwrite_path=style_path,
        force_kind="psg",
    )
    assert out and out.endswith(".bpsg")
    payload = json.loads(Path(style_path).read_text(encoding="utf-8"))
    assert payload["kind"] == "xy_style_geom"

    # Mutate away from exported style on a fresh figure, then import
    fig2, ax2 = plt.subplots()
    ax2.plot(x, y, label="c1", color="#00ff00")
    ax2.set_xlim(25.0, 35.0)
    labels = ["c1"]
    ST.apply_style_config(
        style_path,
        fig2,
        ax2,
        [x],
        [y],
        [y],
        [0.0],
        [],
        args,
        tick_state,
        labels,
        update_labels_func=lambda *a, **k: None,
    )
    assert np.allclose(ax2.get_xlim(), (20.0, 40.0), atol=1e-6)

    # Session save/load
    pkl = tmp_path / "xy.pkl"
    S.dump_session(
        str(pkl),
        fig=fig,
        ax=ax,
        x_data_list=[x],
        y_data_list=[y],
        orig_y=[y],
        x_full_list=[x],
        raw_y_full_list=[y],
        offsets_list=[0.0],
        labels=["c1"],
        delta=0.0,
        args=args,
        tick_state=tick_state,
        skip_confirm=True,
    )
    fig3, ax3, mk = S.load_xy_session(str(pkl))
    assert ax3.get_xlabel() == "Two theta"
    assert "labels" in mk
    plt.close(fig)
    plt.close(fig2)
    plt.close(fig3)


# ---------------------------------------------------------------------------
# Histo: p → i → b → s through real snapshot helpers + interactive undo
# ---------------------------------------------------------------------------


def test_histo_pisb_visible_mutation_roundtrip(tmp_path):
    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    state = HistoState(
        setup=HistoSetup(
            column_index=1,
            column_name="Length",
            values=values,
            xmin=float(edges[0]),
            xmax=float(edges[-1]),
            bin_edges=edges,
        ),
        style=HistoStyle(bar_color="#4c72b0", show_grid=False),
        source_path=str(tmp_path / "data.csv"),
    )
    refresh_histo_figure(fig, ax, state)

    style_path = tmp_path / "h.bpsh"
    _export_style(fig, ax, state, str(style_path), include_geometry=True)
    assert style_path.exists()
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload.get("kind") == "histo_style"

    # Mutate
    state.style.bar_color = "#ff00ff"
    state.style.show_grid = True
    refresh_histo_figure(fig, ax, state)
    assert state.style.bar_color == "#ff00ff"

    apply_histo_style_snapshot(fig, ax, state, payload)
    assert state.style.bar_color.lower() in ("#4c72b0",)
    assert state.style.show_grid is False

    # Session
    pkl = tmp_path / "h.pkl"
    _save_session(fig, ax, state, str(pkl))
    fig2, ax2, state2 = load_histo_session(str(pkl))
    assert state2.style.bar_color.lower() in ("#4c72b0",)
    # data preserved
    assert np.allclose(state2.setup.values, values)
    plt.close(fig)
    plt.close(fig2)


def test_histo_interactive_b_undo_after_color_change(monkeypatch):
    """Drive histo menu: change color, then ``b`` restores previous color."""
    from batplot.plot_modes.common import menu_rendering as MR
    from batplot.plot_modes.common import terminal as T
    from batplot.plot_modes.histo import interactive as HI

    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    state = HistoState(
        setup=HistoSetup(
            column_index=1,
            column_name="Length",
            values=values,
            xmin=float(edges[0]),
            xmax=float(edges[-1]),
            bin_edges=edges,
        ),
        style=HistoStyle(bar_color="#4c72b0"),
        source_path="/tmp/histo.csv",
    )
    refresh_histo_figure(fig, ax, state)
    original = state.style.bar_color

    # c → set color via "bar:#00aa00" style prompts vary; use direct mutation path:
    # enter color menu and quit after we monkeypatch set — simpler: feed keys that
    # open color, then we patch run_histo_color_menu to mutate+push.
    from batplot.plot_modes.histo import colors as HC

    def _fake_color_menu(**kwargs):
        kwargs["push_state"]()
        kwargs["set_bar_color"]("#00aa00")
        kwargs["refresh"]()

    monkeypatch.setattr(HC, "run_histo_color_menu", _fake_color_menu)
    # Also patch the name bound into interactive if imported
    if hasattr(HI, "run_histo_color_menu"):
        monkeypatch.setattr(HI, "run_histo_color_menu", _fake_color_menu)

    answers = ["c", "b", "q", "y"]
    feed = _Feed(*answers)
    monkeypatch.setattr(T, "safe_input", feed)
    monkeypatch.setattr(HI, "safe_input", feed)
    monkeypatch.setattr(T, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(MR, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(HI, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(HA, "choose_save_path", lambda *a, **k: None)
    monkeypatch.setattr(HA, "choose_style_file", lambda *a, **k: None)

    histo_interactive_menu(fig, ax, state)
    assert state.style.bar_color == original
    plt.close(fig)


# ---------------------------------------------------------------------------
# Batch: mutate → push → undo; export/import contract for every registered kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind,sub", [
    ("xy", "ps"),
    ("xy", "psg"),
    ("histo", "ps"),
    ("operando_ec", "ps"),
    ("operando_ec", "psg"),
])
def test_batch_pisb_contract_kinds(kind, sub, tmp_path):
    if kind == "xy":
        from test_batch_session import _make_xy_pkl

        pkl = tmp_path / "p.pkl"
        _make_xy_pkl(str(pkl))
        result = load_batch_panels([str(pkl)])
        panel = result.panels[0]
    elif kind == "histo":
        values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
        edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
        setup = HistoSetup(
            column_index=1,
            column_name="Length",
            values=values,
            xmin=float(edges[0]),
            xmax=float(edges[-1]),
            bin_edges=edges,
        )
        from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
        from batplot.plot_modes.histo.session import save_histo_session

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("Length\n1\n2\n2.5\n3\n8\n", encoding="utf-8")
        state = build_histo_state(setup, source_path=str(csv_path))
        fig, ax, _meta = create_histo_figure(state)
        pkl = tmp_path / "h.pkl"
        save_histo_session(fig, ax, state, str(pkl))
        plt.close(fig)
        result = load_batch_panels([str(pkl)])
        panel = result.panels[0]
    else:
        from test_operando_batch_menu import _build_panel

        panel = _build_panel()

    try:
        handler = get_batch_state_handler(kind)
        undo = SyncUndoStacks(1)
        snap0 = handler.capture(panel)
        undo.push_all([snap0])

        # Visible mutation (histo stores labels in state.style, not only ax)
        if kind == "histo":
            original = panel.state.style.bar_color
            panel.state.style.bar_color = "#abcdef"
            from batplot.plot_modes.histo.plot import refresh_histo_figure

            refresh_histo_figure(panel.fig, panel.ax, panel.state)
            undo.push_all([handler.capture(panel)])
            panel.state.style.bar_color = "#000000"
            refresh_histo_figure(panel.fig, panel.ax, panel.state)
            assert undo.can_undo()
            undo.undo_all(lambda i, snap: handler.restore(panel, snap))
            assert panel.state.style.bar_color.lower() == "#abcdef"
            panel.state.style.bar_color = original
        else:
            panel.ax.set_xlabel("MUTATED_BATCH_X")
            assert panel.ax.get_xlabel() == "MUTATED_BATCH_X"
            undo.push_all([handler.capture(panel)])
            panel.ax.set_xlabel("MUTATED_AGAIN")
            assert undo.can_undo()
            undo.undo_all(lambda i, snap: handler.restore(panel, snap))
            assert panel.ax.get_xlabel() == "MUTATED_BATCH_X"

        verify_panel_pisb_roundtrip(panel, kind, sub=sub)

        out = tmp_path / f"saved_{kind}.pkl"
        handler.save(panel, str(out))
        assert out.exists()
    finally:
        plt.close(panel.fig)


def test_batch_ec_cpc_pisb_and_undo(tmp_path):
    """EC/CPC batch handlers: capture → mutate → undo → export/import → save."""
    from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel
    from test_cpc_roundtrip import _build_cpc_figure

    panels = []
    fig_ec, ax_ec = plt.subplots()
    (c,) = ax_ec.plot([0.0, 1.0], [0.0, 1.0])
    panels.append(
        (
            "ec_gc",
            EcPanel(
                path="a.pkl",
                fig=fig_ec,
                ax=ax_ec,
                cycle_lines={1: {"charge": c, "discharge": None}},
                file_data=None,
            ),
        )
    )
    fig_c, ax_c, ax2, sc_c, sc_d, sc_e, _ = _build_cpc_figure()
    panels.append(
        (
            "cpc",
            CpcPanel(
                path="cpc.pkl",
                fig=fig_c,
                ax=ax_c,
                ax2=ax2,
                sc_charge=sc_c,
                sc_discharge=sc_d,
                sc_eff=sc_e,
            ),
        )
    )

    for kind, panel in panels:
        try:
            handler = get_batch_state_handler(kind)
            undo = SyncUndoStacks(1)
            undo.push_all([handler.capture(panel)])
            panel.ax.set_xlabel("BATCH_MUT")
            undo.push_all([handler.capture(panel)])
            panel.ax.set_xlabel("BATCH_MUT2")
            undo.undo_all(lambda i, snap, p=panel, h=handler: h.restore(p, snap))
            assert panel.ax.get_xlabel() == "BATCH_MUT"

            verify_panel_pisb_roundtrip(panel, kind, sub="ps")
            verify_panel_pisb_roundtrip(panel, kind, sub="psg")
            out = tmp_path / f"{kind}.pkl"
            handler.save(panel, str(out))
            assert out.exists()
        finally:
            plt.close(panel.fig)


# ---------------------------------------------------------------------------
# Interactive menu key path: p / i / s / b for CPC (best dialog coverage)
# ---------------------------------------------------------------------------


def test_cpc_interactive_keys_p_i_s_b(tmp_path, monkeypatch):
    """Full CPC interactive loop: export style, mutate, import, undo, save."""
    from batplot.plot_modes.common import menu_rendering as MR
    from batplot.plot_modes.common import terminal as T
    from batplot.plot_modes.cpc import style as CS

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    cyc = np.arange(1, 6, dtype=float)
    sc_c = ax.scatter(cyc, np.linspace(150.0, 120.0, 5), c="red")
    sc_d = ax.scatter(cyc, np.linspace(148.0, 118.0, 5), c="blue")
    sc_e = ax2.scatter(cyc, np.linspace(95.0, 99.0, 5), c="green")
    ax.set_xlabel("Cycle number")
    ax.set_ylabel("Capacity (mAh/g)")

    styles_dir = tmp_path / "Styles"
    styles_dir.mkdir()
    exported = styles_dir / "cpc_deep.bpsg"

    # Pre-export a style while xlabel is original
    snap = CS._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e)
    snap["kind"] = "cpc_style_geom"
    snap["geometry"] = {
        "xlabel": "Cycle number",
        "ylabel_left": "Capacity (mAh/g)",
        "ylabel_right": ax2.get_ylabel() or "CE",
        "xlim": list(ax.get_xlim()),
        "ylim_left": list(ax.get_ylim()),
        "ylim_right": list(ax2.get_ylim()),
    }
    exported.write_text(json.dumps(snap), encoding="utf-8")

    # Mutate before import
    ax.set_xlabel("WILL_BE_OVERWRITTEN")

    # Script: i (import) → confirm path already chosen via patch → then b → then s → filename → q
    # CPC import uses choose_style_file (no y/n). Save asks for filename.
    answers = ["i", "b", "s", "cpc_saved", "q"]
    feed = _Feed(*answers)

    monkeypatch.setattr(T, "safe_input", feed)
    monkeypatch.setattr(CI, "_safe_input", feed)
    monkeypatch.setattr(T, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(MR, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(CI, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(CI, "choose_style_file", lambda *a, **k: str(exported))
    monkeypatch.setattr(CI, "choose_save_path", lambda *a, **k: str(tmp_path))

    CI.cpc_interactive_menu(fig, ax, ax2, sc_c, sc_d, sc_e, canvas_mode=True)

    # After import, xlabel should be restored from style; undo may revert import
    # Depending on whether import pushed and b undid it: either "Cycle number" or "WILL_BE_OVERWRITTEN"
    # Sequence: mutate → i (push pre-import=WILL_BE..., apply Cycle number) → b (restore WILL_BE...)
    assert ax.get_xlabel() == "WILL_BE_OVERWRITTEN"
    saved = tmp_path / "cpc_saved.pkl"
    assert saved.exists()
    plt.close(fig)


def test_xy_interactive_b_undo_xlim(monkeypatch):
    """XY interactive: change x range then ``b`` restores previous xlim."""
    from batplot.plot_modes.common import menu_rendering as MR
    from batplot.plot_modes.common import terminal as T
    from batplot.plot_modes.xy import interactive as XI
    from batplot.plot_modes.xy import axis_range as XR

    x = np.linspace(20.0, 40.0, 101)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    ax.set_xlim(20.0, 40.0)
    original = ax.get_xlim()

    def _fake_x_range(**kwargs):
        kwargs["push_state"]("x-range")
        kwargs["ax"].set_xlim(25.0, 35.0)

    monkeypatch.setattr(XR, "run_x_range_menu", _fake_x_range)
    if hasattr(XI, "run_x_range_menu"):
        monkeypatch.setattr(XI, "run_x_range_menu", _fake_x_range)

    feed = _Feed("x", "b", "q")
    monkeypatch.setattr(T, "safe_input", feed)
    monkeypatch.setattr(XI, "_safe_input", feed)
    monkeypatch.setattr(T, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(MR, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(XI, "prompt_menu_key", lambda *a, **k: feed().strip().lower())
    monkeypatch.setattr(XA, "choose_save_path", lambda *a, **k: None)
    monkeypatch.setattr(XA, "choose_style_file", lambda *a, **k: None)

    args = types.SimpleNamespace(
        stack=False, norm=False, ro=False, xrange=None, files=["a.xy"], autoscale=False
    )
    XI.interactive_menu(
        fig, ax, [y.copy()], [x.copy()], ["c1"], [y.copy()], [], 0.0, "Two theta",
        args, [x.copy()], [y.copy()], [0.0],
        False, False, False, False, False, canvas_mode=True,
    )
    assert np.allclose(ax.get_xlim(), original)
    plt.close(fig)
