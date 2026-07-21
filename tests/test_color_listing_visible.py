"""Color-menu listings should omit hidden files / invisible cycles."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import matplotlib.pyplot as plt

from batplot.plot_modes.electrochem.colors import (
    _MULTI_FILE_EXPAND_MAX,
    _cycle_is_visible,
    _print_ec_current_curves,
    _visible_cycle_keys,
)
from batplot.plot_modes.cpc.colors import _print_color_targets


def _fake_line(*, color="#112233", visible=True):
    ln = MagicMock()
    ln.get_color.return_value = color
    ln.get_visible.return_value = visible
    return ln


def test_cycle_is_visible_gc_and_cv():
    chg = _fake_line(visible=False)
    dch = _fake_line(visible=True)
    assert _cycle_is_visible({1: {"charge": chg, "discharge": dch}}, 1)
    assert not _cycle_is_visible({2: {"charge": chg, "discharge": _fake_line(visible=False)}}, 2)
    cv = _fake_line(visible=True)
    assert _cycle_is_visible({3: cv}, 3)
    assert not _cycle_is_visible({4: _fake_line(visible=False)}, 4)


def test_visible_cycle_keys_filters_hidden():
    cl = {
        1: {"charge": _fake_line(visible=True), "discharge": None},
        2: {"charge": _fake_line(visible=False), "discharge": _fake_line(visible=False)},
        5: {"charge": None, "discharge": _fake_line(visible=True)},
    }
    assert _visible_cycle_keys(cl) == [1, 5]


def test_print_ec_current_curves_skips_hidden_file_and_cycles():
    f1_cl = {
        1: {"charge": _fake_line(color="#aa0000", visible=True), "discharge": None},
        2: {"charge": _fake_line(color="#00aa00", visible=False), "discharge": None},
    }
    f2_cl = {
        1: {"charge": _fake_line(color="#0000aa", visible=True), "discharge": None},
    }
    f3_cl = {
        1: {"charge": _fake_line(color="#999999", visible=True), "discharge": None},
    }
    file_data = [
        {"visible": True, "display_name": "A", "cycle_lines": f1_cl},
        {"visible": True, "display_name": "B", "cycle_lines": f2_cl},
        {"visible": False, "display_name": "Hidden", "cycle_lines": f3_cl},
    ]
    buf = StringIO()
    with patch("sys.stdout", buf):
        _print_ec_current_curves(
            target_cycle_lines_list=[(f1_cl, [1, 2]), (f2_cl, [1])],
            is_multi_file=True,
            file_data=file_data,
        )
    out = buf.getvalue()
    assert "f1/1:" in out
    assert "f1/2:" not in out
    assert "f2/1:" in out
    assert "Hidden" not in out
    assert "f3" not in out


def test_print_ec_multi_file_compacts_when_many_visible_cycles():
    cl = {
        i: {"charge": _fake_line(color="#003070", visible=True), "discharge": None}
        for i in range(1, _MULTI_FILE_EXPAND_MAX + 5)
    }
    file_data = [{"visible": True, "display_name": "Pristine", "cycle_lines": cl}]
    buf = StringIO()
    with patch("sys.stdout", buf):
        _print_ec_current_curves(
            target_cycle_lines_list=[(cl, list(cl.keys()))],
            is_multi_file=True,
            file_data=file_data,
        )
    out = buf.getvalue()
    assert "f1:" in out
    assert "visible cycles)" in out
    assert "f1/1:" not in out
    assert "f1/2:" not in out


def test_print_ec_single_file_lists_only_visible_cycles():
    cl = {
        1: {"charge": _fake_line(color="#111111", visible=True), "discharge": None},
        2: {"charge": _fake_line(color="#222222", visible=False), "discharge": None},
        3: {"charge": _fake_line(color="#333333", visible=True), "discharge": None},
    }
    buf = StringIO()
    with patch("sys.stdout", buf):
        _print_ec_current_curves(
            target_cycle_lines_list=[(cl, [1, 2, 3])],
            is_multi_file=False,
            file_data=[],
        )
    out = buf.getvalue()
    assert "  1:" in out
    assert "  3:" in out
    assert "  2:" not in out


def test_cpc_print_color_targets_skips_hidden_files():
    fig, ax = plt.subplots()
    try:
        (ln_vis,) = ax.plot([0, 1], [0, 1], color="#ff0000")
        (ln_hid,) = ax.plot([0, 1], [1, 0], color="#00ff00")
        file_data = [
            {"visible": True, "filename": "a.csv", "sc_charge": ln_vis},
            {"visible": False, "filename": "b.csv", "sc_charge": ln_hid},
        ]
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_color_targets(
                fig=fig,
                file_data=file_data,
                series_key="capacity",
                colorize_menu=lambda s: s,
            )
        out = buf.getvalue()
        assert "a.csv" in out
        assert "b.csv" not in out
        assert "●" not in out
        assert "○" not in out
    finally:
        plt.close(fig)
