"""Batch operando isolation locks unique to recent fixes.

Scoped ``oc``/``or``/``t``/``el``/``v``/``eg`` coverage lives in
``test_batch_scoped_sync_modes.py``. Menu listing lives in
``test_operando_batch_menu.py``.
"""

from __future__ import annotations

import inspect

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.load import OperandoPanel
from batplot.plot_modes.batch_session.menu_operando import run_operando_batch_menu
from batplot.plot_modes.batch_session.operando_batch_helpers import (
    apply_operando_ions_only,
    apply_operando_spine_colors_only,
    run_operando_batch_spine_color_menu,
)
import batplot.plot_modes.batch_session.menu_operando as menu_operando


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _operando_pair():
    panels = []
    for path, cmap, clim in (
        ("a.pkl", "viridis", (0.0, 1.0)),
        ("b.pkl", "plasma", (0.2, 0.8)),
    ):
        fig, ax = plt.subplots()
        Z = np.array([[0.0, 1.0], [0.5, 0.25]])
        im = ax.imshow(Z, cmap=cmap, vmin=clim[0], vmax=clim[1])
        im._operando_cmap_name = cmap  # type: ignore[attr-defined]
        cax = fig.add_axes([0.92, 0.1, 0.03, 0.8])
        cbar = fig.colorbar(im, cax=cax)
        ec_ax = fig.add_axes([0.1, 0.1, 0.2, 0.8])
        (ln,) = ec_ax.plot([3.0, 4.0], [0.0, 1.0], color="#00aa00", lw=1.0)
        ec_ax._ec_line = ln  # type: ignore[attr-defined]
        ec_ax._ec_y_mode = "time"
        ax.set_ylim(0.0, 10.0)
        panels.append(
            OperandoPanel(path=path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax)
        )
    return panels[0], panels[1]


def test_k_pane_scope_does_not_clobber_other_pane():
    p1, p2 = _operando_pair()
    try:
        p2.ax.spines["bottom"].set_color("#111111")
        p2.ax.spines["bottom"].set_linewidth(1.25)
        p2.ec_ax.spines["bottom"].set_color("#222222")
        assert apply_operando_spine_colors_only(
            p2,
            {
                "version": 2,
                "_batch_edited_pane": "operando",
                "operando": {"spines": {"bottom": {"color": "#ff0000", "linewidth": 9.0}}},
                "ec": {"spines": {"bottom": {"color": "#00ff00", "linewidth": 9.0}}},
            },
        )
        assert to_hex(p2.ax.spines["bottom"].get_edgecolor()) == "#ff0000"
        assert to_hex(p2.ec_ax.spines["bottom"].get_edgecolor()) == "#222222"
        assert p2.ax.spines["bottom"].get_linewidth() == pytest.approx(1.25)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_k_menu_uses_per_pane_sync():
    src = inspect.getsource(run_operando_batch_spine_color_menu)
    assert "fixed_pane" in src
    assert "_batch_edited_pane" in src
    assert "edit_ref_then_sync" in src
    assert "while True:" in src


def test_ey_preserves_peer_y_reversed():
    p1, p2 = _operando_pair()
    try:
        y0, y1 = p2.ax.get_ylim()
        p2.ax.set_ylim(y1, y0)
        ey0, ey1 = p2.ec_ax.get_ylim()
        p2.ec_ax.set_ylim(ey1, ey0)
        ok = apply_operando_ions_only(
            p2,
            {
                "version": 2,
                "operando": {"y_reversed": False, "intensity_range": [0.0, 99.0]},
                "ec": {"y_mode": "time", "y_reversed": False},
            },
        )
        assert ok is True
        assert p2.ax.get_ylim()[0] > p2.ax.get_ylim()[1]
        assert p2.ec_ax.get_ylim()[0] > p2.ec_ax.get_ylim()[1]
        assert p2.im.get_clim() == pytest.approx((0.2, 0.8))
        src = inspect.getsource(apply_operando_ions_only)
        assert "y_reversed" not in src.split("mini =")[1].split("result =")[0]
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_cif_add_rolls_back_partial_success():
    src = inspect.getsource(menu_operando.run_operando_batch_menu)
    assert "CIF add incomplete" in src
    assert "expected = len(picked) * len(panels)" in src
    assert "n_ok < expected" in src


def test_batch_u_rejected_with_message(monkeypatch, capsys):
    p1, p2 = _operando_pair()
    try:
        answers = iter(["u", "q"])
        monkeypatch.setattr(
            menu_operando, "prompt_menu_key", lambda *a, **k: next(answers)
        )
        monkeypatch.setattr(
            menu_operando, "batch_quit_or_save_all", lambda *_a, **_k: True
        )
        monkeypatch.setattr(menu_operando, "draw_panels", lambda *_a, **_k: None)
        run_operando_batch_menu([p1, p2])
        out = _strip_ansi(capsys.readouterr().out)
        assert "not available in batch mode" in out
        assert "Unknown command: 'u'" not in out
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_fixed_pane_spine_color_menu_skips_outer_picker(capsys):
    from batplot.plot_modes.operando.spine_colors import run_operando_spine_color_menu

    p1, p2 = _operando_pair()
    try:
        answers = iter(["q"])
        run_operando_spine_color_menu(
            fig=p1.fig,
            ax=p1.ax,
            ec_ax=p1.ec_ax,
            push_state=lambda *_a, **_k: None,
            safe_input=lambda *_a, **_k: next(answers),
            colorize_menu=lambda s: s,
            colorize_prompt=lambda s: s,
            fixed_pane="o",
        )
        out = _strip_ansi(capsys.readouterr().out)
        assert "choose pane" not in out
        assert "Set operando spine colors" in out
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)
