"""Hard gates for Round-9 title helper parity + zero-value fidelity."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.common.session_helpers import _artist_linewidth


def test_artist_linewidth_preserves_zero():
    fig, ax = plt.subplots()
    try:
        (ln,) = ax.plot([0, 1], [0, 1], linewidth=0.0)
        assert _artist_linewidth(ln) == 0.0
    finally:
        plt.close(fig)


def test_xy_ec_session_empty_dumped_tick_state_authoritative():
    for path in (
        "batplot/plot_modes/xy/session.py",
        "batplot/plot_modes/electrochem/session.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "isinstance(dumped_ts, dict) and dumped_ts" not in src
        assert "dict(dumped_ts) if not dumped_ts" in src


def test_modes_use_set_primary_axis_title_for_wasd_titles():
    for path in (
        "batplot/plot_modes/xy/interactive.py",
        "batplot/plot_modes/xy/session.py",
        "batplot/plot_modes/xy/style.py",
        "batplot/plot_modes/histo/spines.py",
        "batplot/plot_modes/cpc/session.py",
        "batplot/plot_modes/cpc/style.py",
        "batplot/plot_modes/operando/style_apply.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "set_primary_axis_title(" in src, path


def test_dual_labelpad_preserves_zero():
    for path in (
        "batplot/plot_modes/electrochem/style.py",
        "batplot/plot_modes/electrochem/interactive.py",
        "batplot/plot_modes/batch_session/ec_batch_helpers.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "labelpad', 4.0) or 4.0" not in src
        assert 'labelpad", 4.0) or 4.0' not in src
        assert "4.0 if _pad is None else _pad" in src


def test_linewidth_dumps_use_artist_helper():
    for path in (
        "batplot/plot_modes/electrochem/session.py",
        "batplot/plot_modes/electrochem/style.py",
        "batplot/plot_modes/operando/session.py",
        "batplot/plot_modes/operando/undo_state.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "get_linewidth() or 1.0" not in src
        assert "_artist_linewidth" in src


def test_xy_cif_color_validate_then_push():
    src = Path("batplot/plot_modes/xy/colors.py").read_text(encoding="utf-8")
    region = src[src.find("if any(':' in t for t in cif_tokens):") :]
    region = region[:1600]
    assert "planned" in region
    assert "planned.append" in region
    assert region.find("planned.append") < region.find('push_state("cif-color")')
    assert "if not planned" in region
    assert region.find("if not planned") < region.find('push_state("cif-color")')


def test_operando_ec_style_apply_bottom_title_uses_helper():
    src = Path("batplot/plot_modes/operando/style_apply.py").read_text(encoding="utf-8")
    assert "ec_ax.xaxis.label.set_visible(bool(ec_wasd.get('bottom'" not in src
    idx = src.find("ec_ax._top_xlabel_on = bool(ec_wasd")
    assert idx >= 0
    assert "set_primary_axis_title(" in src[idx : idx + 500]
