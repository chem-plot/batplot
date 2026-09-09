"""Shared default figure/frame size (XY = EC = CPC) and 'oe' path persistence.

1. XY, GC/CV/dQdV (EC), and CPC must all start with the same default canvas
   size and plot-frame layout (single source of truth in ``ec_common``).
2. Sessions persist ``fig._last_figure_export_path`` so the ``oe`` (overwrite
   figure) shortcut reappears when a session is reopened. Old sessions
   without the key must load unchanged.
"""

import os
import pickle
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from batplot import session as S
from batplot.ec_common import (
    _EC_DEFAULT_LAYOUT,
    _default_cpc_figsize,
    _default_ec_figsize,
)
from conftest import loaded


# ---------------------------------------------------------------------------
# 1. Default size parity
# ---------------------------------------------------------------------------


def test_ec_and_cpc_share_default_figsize():
    assert _default_ec_figsize() == _default_cpc_figsize()


def test_xy_pipeline_uses_shared_default_size_and_layout():
    """XY must build its figure from the shared helpers, not local literals."""
    import batplot.plot_modes.xy.pipeline as pipeline

    src = Path(pipeline.__file__).read_text(encoding="utf-8")
    assert "_default_ec_figsize()" in src, "XY pipeline no longer uses the shared default figsize"
    assert "_apply_default_ec_layout(fig)" in src, "XY pipeline no longer uses the shared default layout"
    assert "figsize = (8, 6)" not in src
    assert "figsize = (9.5, 6.4)" not in src
    assert "left=0.125, right=0.9" not in src


def test_shared_default_layout_produces_same_frame_inches():
    """Canvas x layout must give the same plot-frame size for every mode."""
    from batplot.ec_common import _apply_default_ec_layout

    fig = plt.figure(figsize=_default_ec_figsize())
    _apply_default_ec_layout(fig)
    w, h = fig.get_size_inches()
    frame_w = w * (_EC_DEFAULT_LAYOUT["right"] - _EC_DEFAULT_LAYOUT["left"])
    frame_h = h * (_EC_DEFAULT_LAYOUT["top"] - _EC_DEFAULT_LAYOUT["bottom"])
    # The shared frame default derived in ec_common.
    from batplot.ec_common import _EC_DEFAULT_FRAME_SIZE

    assert abs(frame_w - _EC_DEFAULT_FRAME_SIZE[0]) < 1e-9
    assert abs(frame_h - _EC_DEFAULT_FRAME_SIZE[1]) < 1e-9
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2. 'oe' last-figure-export path persistence
# ---------------------------------------------------------------------------


def _build_ec_figure():
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, label="cycle 1 discharge")
    ax.set_xlabel("Capacity (mAh/g)")
    ax.set_ylabel("Voltage (V)")
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    return fig, ax, cycle_lines


def test_ec_session_roundtrips_last_figure_export_path(session_path):
    fig, ax, cycle_lines = _build_ec_figure()
    export = os.path.abspath(str(session_path("figure.png")))
    fig._last_figure_export_path = export
    p = session_path("ec_oe.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["last_figure_export_path"] == export

    fig2 = loaded(S.load_ec_session(p))[0]
    assert getattr(fig2, "_last_figure_export_path", None) == export
    plt.close(fig)
    plt.close(fig2)


def test_ec_old_session_without_key_loads_clean(session_path):
    """Old .pkl files (no key) must load fine and simply not enable 'oe'
    when no companion figure exists beside the session."""
    fig, ax, cycle_lines = _build_ec_figure()
    p = session_path("ec_old.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    sess.pop("last_figure_export_path", None)  # simulate a pre-feature session
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)

    fig2 = loaded(S.load_ec_session(p))[0]
    assert getattr(fig2, "_last_figure_export_path", None) is None
    plt.close(fig)
    plt.close(fig2)


def test_ec_session_seeds_oe_from_companion_figure(session_path):
    """Opening GC_P_BM30.pkl with Figures/GC_P_BM30.svg must enable oe."""
    from batplot.plot_modes.electrochem.menu import build_electrochem_menu_columns

    fig, ax, cycle_lines = _build_ec_figure()
    p = session_path("GC_P_BM30.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    sess["last_figure_export_path"] = None  # like the user's current pickle
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)

    figures_dir = Path(p).parent / "Figures"
    figures_dir.mkdir(exist_ok=True)
    companion = figures_dir / "GC_P_BM30.svg"
    companion.write_text("<svg/>", encoding="utf-8")

    fig2 = loaded(S.load_ec_session(p))[0]
    assert getattr(fig2, "_last_figure_export_path", None) == os.path.abspath(str(companion))
    _c1, _c2, col3 = build_electrochem_menu_columns(1, fig=fig2, is_multi_file=True)
    assert any(item.startswith("oe:") for item in col3)
    plt.close(fig)
    plt.close(fig2)


def test_xy_session_roundtrips_last_figure_export_path(session_path, fake_args):
    x = np.linspace(0.0, 100.0, 200)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    export = os.path.abspath(str(session_path("xy_figure.svg")))
    fig._last_figure_export_path = export
    p = session_path("xy_oe.pkl")
    S.dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[x], y_data_list=[y], orig_y=[y],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state={}, skip_confirm=True,
    )

    fig2 = loaded(S.load_xy_session(p))[0]
    assert getattr(fig2, "_last_figure_export_path", None) == export
    plt.close(fig)
    plt.close(fig2)


def test_cpc_session_roundtrips_last_figure_export_path(session_path):
    from test_cpc_roundtrip import _build_cpc_figure

    fig, ax, ax2, sc_c, sc_d, sc_e, _cyc = _build_cpc_figure()
    export = os.path.abspath(str(session_path("cpc_figure.png")))
    fig._last_figure_export_path = export
    p = session_path("cpc_oe.pkl")
    S.dump_cpc_session(p, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_c,
                       sc_discharge=sc_d, sc_eff=sc_e, skip_confirm=True)

    fig2 = loaded(S.load_cpc_session(p))[0]
    assert getattr(fig2, "_last_figure_export_path", None) == export
    plt.close(fig)
    plt.close(fig2)


def test_operando_session_roundtrips_last_figure_export_path(session_path):
    from test_operando_roundtrip import _build_operando_figure

    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    export = os.path.abspath(str(session_path("op_figure.png")))
    fig._last_figure_export_path = export
    p = session_path("op_oe.pkl")
    S.dump_operando_session(p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax,
                            skip_confirm=True)

    fig2 = loaded(S.load_operando_session(p))[0]
    assert getattr(fig2, "_last_figure_export_path", None) == export
    plt.close(fig)
    plt.close(fig2)


def test_histo_session_roundtrips_last_figure_export_path(tmp_path):
    from batplot.plot_modes.histo.load import build_bin_edges
    from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
    from batplot.plot_modes.histo.session import load_histo_session, save_histo_session
    from batplot.plot_modes.histo.wizard import HistoSetup

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
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("Length\n1\n2\n2.5\n3\n8\n", encoding="utf-8")
    state = build_histo_state(setup, source_path=str(csv_path))
    fig, ax, _meta = create_histo_figure(state)
    export = os.path.abspath(str(tmp_path / "histo_figure.png"))
    fig._last_figure_export_path = export
    p = tmp_path / "histo_oe.pkl"
    save_histo_session(fig, ax, state, str(p))

    fig2 = loaded(load_histo_session(str(p)))[0]
    assert getattr(fig2, "_last_figure_export_path", None) == export
    plt.close(fig)
    plt.close(fig2)
