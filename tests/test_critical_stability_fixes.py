"""Regression tests for critical stability fixes (2026-07-14)."""

from __future__ import annotations

import pickle
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np

from batplot.ec_common import _merge_dqdv_2d_into_ec_session
from batplot.plot_modes.electrochem.dqdv_2d import build_dqdv_2d_snapshot
from batplot.plot_modes.xy.derivative import update_ylabel_for_derivative
from batplot.session import _package_versions_stamp


def test_update_ylabel_for_derivative_basic():
    assert "d(" in update_ylabel_for_derivative(1, "Intensity", x_label="2theta")
    assert "d²" in update_ylabel_for_derivative(2, "Intensity", x_label="2theta")
    rev = update_ylabel_for_derivative(1, "Intensity", is_reversed=True, x_label="2theta")
    assert "d(2theta)" in rev


def test_xy_style_derivative_import_path_is_valid():
    """Style import must not use the broken ``.plot_modes.xy.interactive`` path."""
    src = Path("batplot/plot_modes/xy/style.py").read_text(encoding="utf-8")
    assert "from .derivative import update_ylabel_for_derivative" in src
    assert "from .plot_modes.xy.interactive" not in src


def test_package_versions_stamp_has_numpy():
    stamp = _package_versions_stamp()
    assert "numpy" in stamp
    assert stamp["numpy"]


def test_merge_dqdv_2d_into_ec_session(tmp_path):
    fig, ax = plt.subplots()
    try:
        Z = np.linspace(0, 1, 12).reshape(3, 4)
        im = ax.imshow(Z, origin="lower", aspect="auto")
        cbar = fig.colorbar(im, ax=ax, fraction=0.05)
        snap = build_dqdv_2d_snapshot(
            fig, ax, im, 2.0, 3.0, ["a", "b", "c"], "dQ/dV", cbar
        )
        assert snap is not None
        pkl = tmp_path / "ec.pkl"
        with open(pkl, "wb") as fh:
            pickle.dump({"kind": "ec_gc", "version": 2, "figure": {"size": [6, 4]}}, fh)
        assert _merge_dqdv_2d_into_ec_session(str(pkl), snap) is True
        with open(pkl, "rb") as fh:
            sess = pickle.load(fh)
        assert sess["kind"] == "ec_gc"
        assert "dqdv_2d" in sess
        assert sess["dqdv_2d"]["kind"] == "dqdv_2d_contour"
        assert "package_versions" in sess
    finally:
        plt.close(fig)


def test_merge_rejects_non_ec_pkl(tmp_path):
    pkl = tmp_path / "xy.pkl"
    with open(pkl, "wb") as fh:
        pickle.dump({"kind": "xy", "version": 3}, fh)
    assert _merge_dqdv_2d_into_ec_session(str(pkl), {"Z": np.zeros((2, 2))}) is False


def test_session_routing_no_dead_reconstruct():
    src = Path("batplot/plot_modes/session_routing.py").read_text(encoding="utf-8")
    assert "Not a recognized batplot session format." in src
    assert "Reconstruct minimal state and go to interactive" not in src


def test_xy_interactive_no_duplicate_h_handler():
    src = Path("batplot/plot_modes/xy/interactive.py").read_text(encoding="utf-8")
    # Executable handlers only (ignore comments that mention the old dead branch).
    handlers = [
        line for line in src.splitlines()
        if line.lstrip().startswith("elif key == 'h'") or line.lstrip().startswith('elif key == "h"')
    ]
    assert len(handlers) == 1
    assert "duplicate unreachable" in src


def test_operando_import_style_delegates_to_style_apply():
    src = Path("batplot/plot_modes/operando/actions.py").read_text(encoding="utf-8")
    assert "from .style_apply import apply_operando_ec_style_config" in src
    # The old inline 800-line apply body should be gone.
    assert src.count("_maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)") == 0
