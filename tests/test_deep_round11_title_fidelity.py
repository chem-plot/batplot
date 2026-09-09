"""Hard gates for Round-11 hidden-title / hitchhiker fidelity."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.common.axis_state import primary_axis_label_text
from batplot.plot_modes.common.spines import set_primary_axis_title


def test_primary_axis_label_text_prefers_stored_when_hidden():
    fig, ax = plt.subplots()
    try:
        ax.set_xlabel("Potential (V)")
        set_primary_axis_title(ax, "x", on=False, stored_attr="_stored_xlabel")
        assert ax.get_xlabel() == ""
        assert primary_axis_label_text(ax, "x") == "Potential (V)"
    finally:
        plt.close(fig)


def test_xy_dumps_use_primary_axis_label_helper():
    for path in (
        "batplot/plot_modes/xy/session.py",
        "batplot/plot_modes/xy/style.py",
        "batplot/plot_modes/xy/undo_state.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "primary_axis_label_text" in src or "_get_primary_axis_text" in src


def test_xy_undo_restore_uses_set_primary_axis_title():
    src = Path("batplot/plot_modes/xy/undo_state.py").read_text(encoding="utf-8")
    assert "set_primary_axis_title(" in src
    assert 'ax.xaxis.label.set_visible(bool(at["has_bottom_x"]))' not in src


def test_operando_persists_stored_xlabel():
    src = Path("batplot/plot_modes/operando/session.py").read_text(encoding="utf-8")
    assert "'stored_xlabel': getattr(ax, '_stored_xlabel', None)" in src
    assert "'stored_xlabel': getattr(ec_ax, '_stored_xlabel', None)" in src


def test_operando_ions_rename_does_not_overwrite_time_title():
    src = Path("batplot/plot_modes/operando/labels.py").read_text(encoding="utf-8")
    region = src[src.find("def _rename_ec_y") :]
    assert 'ec_ax._custom_labels["y_ions"] = label' in region
    ions = region[region.find('if mode == "ions"') : region.find("else:")]
    assert "set_ylabel" not in ions


def test_histo_batch_t_strips_l_widths():
    src = Path("batplot/plot_modes/histo/spines.py").read_text(encoding="utf-8")
    region = src[src.find("def sync_histo_spine_from_reference") :]
    region = region[:800]
    assert 'snap.pop("spine_linewidths"' in region
    assert 'snap.pop("tick_widths"' in region


def test_operando_l_validate_then_push():
    src = Path("batplot/plot_modes/operando/interactive.py").read_text(encoding="utf-8")
    region = src[src.find('Line widths (value or') :]
    region = region[:2000]
    assert region.find("parse_frame_tick_widths") < region.find('_snapshot("line-widths")')


def test_dual_axis_push_before_remove_secondary():
    src = Path("batplot/plot_modes/electrochem/dual_axis_menu.py").read_text(
        encoding="utf-8"
    )
    for label in ('push_state("x=n(ions)")', 'push_state("x=capacity")'):
        idx = src.find(label)
        assert idx >= 0
        before = src[max(0, idx - 400) : idx]
        assert "fig._xaxis_secondary = None" not in before


def test_xy_style_only_strips_dual_y():
    src = Path("batplot/plot_modes/xy/style.py").read_text(encoding="utf-8")
    assert "cfg.pop('right_y_curve_indices', None)" in src
    assert 'if kind != "xy_style":' in src


def test_cpc_interactive_seeds_flat_tick_state():
    src = Path("batplot/plot_modes/cpc/interactive.py").read_text(encoding="utf-8")
    assert "default_flat_tick_state(" in src


def test_batch_cpc_allows_marker_size_zero():
    src = Path("batplot/plot_modes/batch_session/menu_cpc.py").read_text(encoding="utf-8")
    assert "if num < 0:" in src
    assert "if num <= 0:" not in src


def test_dqdv_dumps_stored_axis_titles():
    src = Path("batplot/plot_modes/electrochem/dqdv_2d.py").read_text(encoding="utf-8")
    assert '"stored_xlabel"' in src
    assert "primary_axis_label_text(cax" in src
