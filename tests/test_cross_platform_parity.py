"""Cross-platform parity tests (macOS / Windows / Linux behavior)."""

from __future__ import annotations

import io
import sys

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

from batplot._mpl_backend import _gui_backend_order
from batplot.plot_modes.batch_session.batch_geom_helpers import apply_canvas_to_all, frame_inches
from batplot.plot_modes.batch_session.common import draw_panels
from batplot.plot_modes.batch_session.load import EcPanel
from batplot.plot_modes.common import terminal as T


@pytest.mark.parametrize("platform_name", ["linux", "win32", "cygwin"])
def test_imk_stderr_guard_is_noop_off_darwin(monkeypatch, platform_name):
    """Windows/Linux must not redirect stderr or alter interactive behavior."""
    monkeypatch.setattr(T.sys, "platform", platform_name)
    err_before = sys.stderr
    with T.imk_stderr_guard():
        assert sys.stderr is err_before
    assert sys.stderr is err_before


def test_imk_stderr_guard_nested_refcount_restores_stderr(monkeypatch):
    """Nested guards must restore stderr exactly once (all platforms)."""
    monkeypatch.setattr(T.sys, "platform", "linux")
    err = sys.stderr
    with T.imk_stderr_guard():
        with T.imk_stderr_guard():
            assert sys.stderr is err
    assert sys.stderr is err


def test_safe_input_cancel_on_interrupt_returns_empty(monkeypatch):
    monkeypatch.setattr(T.sys, "platform", "linux")
    monkeypatch.setattr("builtins.input", lambda _p="": (_ for _ in ()).throw(KeyboardInterrupt()))
    assert T.safe_input("> ", cancel_on_interrupt=True) == ""


def test_batch_canvas_resize_identical_on_agg_backend():
    """Canvas resize preserves frame inches the same way on every OS (Agg, no GUI)."""
    panels = []
    for i in range(2):
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot([0, 1], [0, i + 1])
        panels.append(EcPanel(path=f"p{i}.pkl", fig=fig, ax=ax, cycle_lines={}, file_data=None))
    apply_canvas_to_all(panels, 5.0, 4.0)
    draw_panels(panels)
    for panel in panels:
        w, h = panel.fig.get_size_inches()
        assert w == pytest.approx(5.0)
        assert h == pytest.approx(4.0)
        fw, fh = frame_inches(panel.fig, panel.ax)
        assert fw > 0.0 and fh > 0.0
        plt.close(panel.fig)


def test_gui_backend_order_is_platform_specific():
    order = _gui_backend_order()
    assert order
    if sys.platform == "darwin":
        assert order[0] == "MacOSX"
    elif sys.platform.startswith("win"):
        assert order[0] == "TkAgg"
    else:
        assert order[0] == "TkAgg"


def test_filter_imk_warning_never_drops_real_errors():
    out = io.StringIO()
    filt = T.FilterIMKWarning(out)
    filt.write("Traceback (most recent call last):\n")
    filt.write("ValueError: bad limit\n")
    assert "ValueError" in out.getvalue()
