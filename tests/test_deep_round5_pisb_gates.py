"""Hard gates for Round-5 deep dig: key hitchhikers + empty-title fidelity."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.batch_session.batch_scoped_sync import merge_spines_props
from batplot.plot_modes.cpc.colors import apply_capacity_color_tokens
from batplot.plot_modes.operando.colors import _ensure_operando_colormap_ready


def test_merge_spines_linewidth_does_not_copy_visible():
    peer = {"left": {"linewidth": 1.0, "visible": True}}
    ref = {"left": {"linewidth": 3.0, "visible": False}}
    out = merge_spines_props(peer, ref, mode="linewidth")
    assert out["left"]["linewidth"] == 3.0
    assert out["left"]["visible"] is True


def test_operando_style_only_strips_limit_bookkeeping():
    src = Path("batplot/plot_modes/operando/style.py").read_text(encoding="utf-8")
    # Style-only export must null/omit geometry limit bookkeeping.
    assert 'ec_payload["saved_time_ylim"] = None' in src
    assert 'ec_payload["prev_ec_xlim"] = None' in src
    batch = Path("batplot/plot_modes/batch_session/operando_batch_helpers.py").read_text(
        encoding="utf-8"
    )
    assert 'ec_strip.pop("saved_time_ylim", None)' in batch
    apply = Path("batplot/plot_modes/operando/style_apply.py").read_text(encoding="utf-8")
    assert "operando_ec_style_geom" in apply
    assert "if apply_view_geom:" in apply


def test_operando_style_apply_prefers_y_time_not_y_ions():
    src = Path("batplot/plot_modes/operando/style_apply.py").read_text(encoding="utf-8")
    idx = src.find("Overlay ions: axis title stays time")
    assert idx >= 0
    region = src[idx : idx + 400]
    assert "ec_custom.get('y_time')" in region
    assert "ec_custom.get('y_ions')" not in region


def test_operando_y_time_empty_not_coerced_in_ions_path():
    src = Path("batplot/plot_modes/operando/style_apply.py").read_text(encoding="utf-8")
    assert "get('y_time') or 'Time (h)'" not in src
    assert "'y_time' in _cl and _cl['y_time'] is not None" in src


def test_cpc_wasd_seed_visibility_only():
    src = Path("batplot/plot_modes/cpc/wasd_menu.py").read_text(encoding="utf-8")
    assert "bool(ax.xaxis.label.get_visible()) and bool(ax.get_xlabel())" not in src
    assert "bool(ax.yaxis.label.get_visible()) and bool(ax.get_ylabel())" not in src


def test_cpc_ly_validate_before_push():
    src = Path("batplot/plot_modes/cpc/colors.py").read_text(encoding="utf-8")
    ly = src[src.find('if sub == "ly":') : src.find('if sub == "ry":')]
    assert "commit=False" in ly
    assert ly.find("commit=False") < ly.find('push_state("colors-ly")')


def test_cpc_capacity_tokens_reject_without_commit():
    fig, ax = plt.subplots()
    try:
        # Two bare tokens (not "all <palette>") hit the file:color reject path.
        ok = apply_capacity_color_tokens(
            ["foo", "bar"],
            fig=fig,
            file_data=[{"filename": "a"}],
            palette_opts=["viridis"],
            commit=False,
        )
        assert ok is False
    finally:
        plt.close(fig)


def test_operando_colormap_validates_before_snapshot():
    src = Path("batplot/plot_modes/operando/colors.py").read_text(encoding="utf-8")
    region = src[src.find("def run_operando_colormap_menu") :]
    region = region[:2500]
    assert region.find("_ensure_operando_colormap_ready") < region.find(
        'snapshot("operando-colormap")'
    )
    try:
        _ensure_operando_colormap_ready("not_a_real_colormap_zzz")
        assert False, "expected unknown colormap to raise"
    except ValueError:
        pass


def test_operando_range_menus_validate_before_snapshot():
    src = Path("batplot/plot_modes/operando/axes_limits_menu.py").read_text(encoding="utf-8")
    for label in ("ec-time-range", "ec-x-range", "operando-xrange", "operando-yrange"):
        # Two-number path: parse before snapshot(label)
        idx = 0
        found = False
        while True:
            snap = src.find(f'snapshot("{label}")', idx)
            if snap < 0:
                break
            # Look backward for map(float in the preceding ~200 chars of this branch
            window = src[max(0, snap - 250) : snap]
            if "map(float" in window:
                found = True
                break
            idx = snap + 1
        assert found, f"expected validate-then-push for {label}"


def test_ec_style_sets_curve_markers_template():
    src = Path("batplot/plot_modes/electrochem/style_apply.py").read_text(encoding="utf-8")
    assert "fig._ec_curve_markers = dict(curve_markers)" in src
    undo = Path("batplot/plot_modes/electrochem/undo_state.py").read_text(encoding="utf-8")
    assert "fig._ec_curve_markers = dict(curve_markers)" in undo


def test_dqdv_empty_zlabel_key_presence():
    src = Path("batplot/plot_modes/electrochem/dqdv_2d.py").read_text(encoding="utf-8")
    assert 'str(blob.get("zlabel") or "dQ/dV")' not in src
    assert '"zlabel" in blob and blob.get("zlabel") is not None' in src


def test_keep_yaxis_uses_right_ylabel_on_flag():
    for path in (
        "batplot/plot_modes/operando/style_apply.py",
        "batplot/plot_modes/operando/undo_state.py",
        "batplot/plot_modes/operando/interactive.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "visible=bool(ec_ax.get_ylabel())" not in src
        assert "visible=bool(axis.get_ylabel())" not in src


def test_batch_operando_er_uses_y_time_not_y_ions():
    src = Path("batplot/plot_modes/batch_session/operando_batch_helpers.py").read_text(
        encoding="utf-8"
    )
    idx = src.find("def apply_operando_ec_labels_only")
    assert idx >= 0
    region = src[idx : idx + 2500]
    assert 'ec_custom.get("y_ions")' not in region
    assert 'ec_custom.get("y_time")' in region
    assert "if not right_on and (ec_ax.get_ylabel()" not in region


def test_cpc_spine_auto_pushes_before_mutate():
    # Bare ``a`` is left-spine mapping; only ``auto`` toggles auto mode.
    for path in (
        "batplot/plot_modes/cpc/panel_menus.py",
        "batplot/plot_modes/cpc/colors.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        idx = src.find('line.lower() == "auto"')
        if idx < 0:
            idx = src.find("line.lower() == 'auto'")
        assert idx >= 0, path
        assert 'in ("a", "auto")' not in src
        assert "in ('a', 'auto')" not in src
        region = src[idx : idx + 500]
        push_idx = region.find('push_state("color-spine-auto")')
        assign_idx = region.find("_cpc_spine_auto = not")
        assert 0 <= push_idx < assign_idx, path
