"""Session routing / p-i-s-b stability: contour reload and os overwrite."""

from __future__ import annotations

import pickle
from pathlib import Path
from unittest.mock import MagicMock

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.electrochem.dqdv_2d import (
    build_dqdv_2d_snapshot,
    restore_dqdv_2d_companion_figure,
)
from batplot.plot_modes.operando.actions import handle_quick_overwrite_session
from batplot.plot_modes.session_routing import (
    _VALID_SESSION_KINDS,
    _is_valid_session_header,
)


def _tiny_contour_fig():
    fig, ax = plt.subplots()
    Z = np.linspace(0, 1, 12).reshape(3, 4)
    im = ax.imshow(Z, origin="lower", aspect="auto", cmap="viridis")
    cbar = fig.colorbar(im, ax=ax, fraction=0.05)
    fig._is_dqdv_2d_contour = True
    fig._dqdv_2d_v_lo = 2.0
    fig._dqdv_2d_v_hi = 3.5
    fig._dqdv_2d_row_labels = ["a", "b", "c"]
    fig._dqdv_2d_zlabel = "dQ/dV"
    im._operando_cmap_name = "viridis"
    return fig, ax, im, cbar


def test_dqdv_2d_contour_is_valid_session_kind():
    assert "dqdv_2d_contour" in _VALID_SESSION_KINDS
    assert _is_valid_session_header({"kind": "dqdv_2d_contour", "version": 1}) is True
    assert _is_valid_session_header({"kind": "histo", "state": {}}) is True


def test_standalone_contour_reload_import_path(tmp_path):
    """``batplot contour.pkl`` must import dqdv_2d from the correct package path."""
    import batplot.plot_modes.session_routing as sr

    src = Path(sr.__file__).read_text(encoding="utf-8")
    assert "from .electrochem.dqdv_2d import restore_dqdv_2d_companion_figure" in src
    assert "from .plot_modes.electrochem.dqdv_2d" not in src

    fig, ax, im, cbar = _tiny_contour_fig()
    try:
        snap = build_dqdv_2d_snapshot(
            fig, ax, im, 2.0, 3.5, ["a", "b", "c"], "dQ/dV", cbar
        )
        assert snap is not None
        assert snap["kind"] == "dqdv_2d_contour"
        pkl = tmp_path / "contour.pkl"
        with open(pkl, "wb") as fh:
            pickle.dump(snap, fh)
        with open(pkl, "rb") as fh:
            loaded = pickle.load(fh)
        restored = restore_dqdv_2d_companion_figure(loaded)
        assert restored is not None
        plt.close(restored[0])
    finally:
        plt.close(fig)


def test_os_on_contour_writes_dqdv_2d_kind_not_operando(tmp_path, monkeypatch):
    """``os`` after contour ``s`` must overwrite with kind=dqdv_2d_contour."""
    fig, ax, im, cbar = _tiny_contour_fig()
    pkl = tmp_path / "contour.pkl"
    snap0 = build_dqdv_2d_snapshot(fig, ax, im, 2.0, 3.5, ["a", "b", "c"], "dQ/dV", cbar)
    assert snap0 is not None
    with open(pkl, "wb") as fh:
        pickle.dump(snap0, fh)
    fig._last_session_save_path = str(pkl)

    monkeypatch.setattr(
        "batplot.plot_modes.operando.actions.confirm_previous_path",
        lambda *a, **k: str(pkl),
    )

    def _fail_operando(*_a, **_k):
        raise AssertionError("must not dump operando_ec for contour figures")

    monkeypatch.setattr(
        "batplot.plot_modes.operando.actions.dump_operando_session",
        _fail_operando,
    )

    ctx = MagicMock()
    ctx.fig = fig
    ctx.ax = ax
    ctx.im = im
    ctx.cbar = cbar
    ctx.ec_ax = None
    ctx.print_menu = lambda: None
    handle_quick_overwrite_session(ctx)

    with open(pkl, "rb") as fh:
        overwritten = pickle.load(fh)
    assert overwritten.get("kind") == "dqdv_2d_contour"
    assert "Z" in overwritten
    plt.close(fig)
