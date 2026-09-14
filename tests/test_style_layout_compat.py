"""Layout compatibility gates for style ``.bps`` / ``.bpsg`` across modes."""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.common import layout_compat as LC
from batplot.plot_modes.xy import style as XYST


def test_xy_rejects_curve_count_mismatch(tmp_path):
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2])
    (ln1,) = ax.plot([0, 1], [2, 3])
    fig._xy_lines_by_curve = [ln0, ln1]
    path = tmp_path / "a.bps"
    XYST.export_style_config(
        str(path),
        fig,
        ax,
        [np.array([1.0, 2.0]), np.array([2.0, 3.0])],
        ["c1", "c2"],
        0.0,
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        [0.0, 0.0],
        overwrite_path=str(path),
        force_kind="ps",
    )
    plt.close(fig)

    fig2, ax2 = plt.subplots()
    (ln0,) = ax2.plot([0, 1], [0, 1])
    fig2._xy_lines_by_curve = [ln0]
    ok = XYST.apply_style_config(
        str(path),
        fig2,
        ax2,
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [0.0],
        [],
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        ["c1"],
        update_labels_func=lambda *_a, **_k: None,
    )
    assert ok is False
    plt.close(fig2)


def test_xy_bpsg_rejects_cif_presence_mismatch(tmp_path):
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2])
    fig._xy_lines_by_curve = [ln0]
    cif = [("a.cif", "/tmp/a.cif", [1.0], None, None, "k")]
    path = tmp_path / "a.bpsg"
    XYST.export_style_config(
        str(path),
        fig,
        ax,
        [np.array([1.0, 2.0])],
        ["c1"],
        0.0,
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        [0.0],
        cif_tick_series=cif,
        overwrite_path=str(path),
        force_kind="psg",
    )
    plt.close(fig)

    fig2, ax2 = plt.subplots()
    (ln0,) = ax2.plot([0, 1], [0, 1])
    fig2._xy_lines_by_curve = [ln0]
    ok = XYST.apply_style_config(
        str(path),
        fig2,
        ax2,
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [0.0],
        [],
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        ["c1"],
        update_labels_func=lambda *_a, **_k: None,
        cif_tick_series=[],  # no CIF live
    )
    assert ok is False
    plt.close(fig2)


def test_xy_stack_mismatch_rejected(tmp_path):
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2])
    fig._xy_lines_by_curve = [ln0]
    path = tmp_path / "stack.bps"
    XYST.export_style_config(
        str(path),
        fig,
        ax,
        [np.array([1.0, 2.0])],
        ["c1"],
        0.0,
        SimpleNamespace(stack=True, xaxis="Q", wl=None, files=[]),
        {},
        [0.0],
        overwrite_path=str(path),
        force_kind="ps",
    )
    plt.close(fig)

    fig2, ax2 = plt.subplots()
    (ln0,) = ax2.plot([0, 1], [0, 1])
    fig2._xy_lines_by_curve = [ln0]
    ok = XYST.apply_style_config(
        str(path),
        fig2,
        ax2,
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [0.0],
        [],
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        ["c1"],
        update_labels_func=lambda *_a, **_k: None,
    )
    assert ok is False
    plt.close(fig2)


def test_operando_ec_panel_mismatch():
    file_layout = LC.operando_layout_fingerprint(has_ec_panel=True, is_dqdv_2d=False)
    live_layout = LC.operando_layout_fingerprint(has_ec_panel=False, is_dqdv_2d=False)
    assert LC.operando_layouts_compatible(file_layout, live_layout, silent=True) is False


def test_operando_dqdv_vs_xrd_mismatch():
    file_layout = LC.operando_layout_fingerprint(has_ec_panel=False, is_dqdv_2d=True)
    live_layout = LC.operando_layout_fingerprint(has_ec_panel=False, is_dqdv_2d=False)
    assert LC.operando_layouts_compatible(file_layout, live_layout, silent=True) is False


def test_ec_multi_file_mismatch():
    file_layout = LC.ec_layout_fingerprint(is_multi_file=True, n_files=2, plot_family="gc")
    live_layout = LC.ec_layout_fingerprint(is_multi_file=False, n_files=1, plot_family="gc")
    assert LC.ec_layouts_compatible(file_layout, live_layout, silent=True) is False


def test_ec_family_mismatch():
    file_layout = LC.ec_layout_fingerprint(plot_family="dqdv")
    live_layout = LC.ec_layout_fingerprint(plot_family="gc")
    assert LC.ec_layouts_compatible(file_layout, live_layout, silent=True) is False


def test_cpc_multi_file_mismatch():
    file_layout = LC.cpc_layout_fingerprint(is_multi_file=True, n_files=2)
    live_layout = LC.live_cpc_layout(fig=SimpleNamespace(_ro_active=False), file_data=[{"a": 1}], is_multi_file=False)
    assert LC.cpc_layouts_compatible(file_layout, live_layout, silent=True) is False


def test_histo_density_mismatch():
    file_layout = LC.histo_layout_fingerprint(has_density=True)
    live_layout = LC.histo_layout_fingerprint(has_density=False)
    assert LC.histo_layouts_compatible(file_layout, live_layout, silent=True) is False


def test_infer_operando_without_ec_panel_ignores_bare_y_mode():
    cfg = {
        "kind": "operando_ec_style",
        "ec": {"wasd_state": {}, "spines": {}, "curve": {}, "y_mode": "time"},
    }
    layout = LC.infer_operando_layout_from_cfg(cfg)
    assert layout["has_ec_panel"] is False


def test_xy_matching_layout_allows_apply(tmp_path):
    fig, ax = plt.subplots(figsize=(6, 4))
    (ln0,) = ax.plot([0, 1], [1, 2], color="#123456")
    fig._xy_lines_by_curve = [ln0]
    path = tmp_path / "ok.bps"
    XYST.export_style_config(
        str(path),
        fig,
        ax,
        [np.array([1.0, 2.0])],
        ["c1"],
        0.0,
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        [0.0],
        overwrite_path=str(path),
        force_kind="ps",
    )
    plt.close(fig)

    fig2, ax2 = plt.subplots(figsize=(5, 5))
    (ln0,) = ax2.plot([0, 1], [0, 1], color="k")
    fig2._xy_lines_by_curve = [ln0]
    ok = XYST.apply_style_config(
        str(path),
        fig2,
        ax2,
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [0.0],
        [],
        SimpleNamespace(stack=False, xaxis="Q", wl=None, files=[]),
        {},
        ["c1"],
        update_labels_func=lambda *_a, **_k: None,
    )
    assert ok is not False
    from matplotlib.colors import to_hex

    assert to_hex(ln0.get_color()).lower() == "#123456"
    plt.close(fig2)
