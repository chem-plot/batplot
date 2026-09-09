"""XRD crosshair Bragg readout (XY + operando) with wavelength."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.operando.axis_units import (
    get_operando_axis_mode,
    resolve_operando_wavelength,
    set_operando_axis_mode,
)
from batplot.plot_modes.xy.axis_units import (
    format_xrd_crosshair_x_lines,
    set_xy_axis_mode,
    twotheta_to_Q,
)


def test_operando_session_attrs_drive_crosshair_bragg():
    """Mirrors .pkl restore: fig._operando_axis_mode + _operando_wl → full Bragg."""
    fig, ax = plt.subplots()
    set_operando_axis_mode(fig, "Q", wavelength=0.709)
    assert get_operando_axis_mode(fig, ax) == "Q"
    wl = resolve_operando_wavelength(fig=fig)
    assert wl == 0.709
    lines = format_xrd_crosshair_x_lines(1.5, axis_mode="Q", wavelength=wl)
    joined = "\n".join(lines)
    assert "Q=" in joined and "2θ=" in joined and "d=" in joined
    plt.close(fig)


def test_xy_session_attrs_drive_crosshair_bragg():
    fig, ax = plt.subplots()
    set_xy_axis_mode(fig, "Q", wavelength=0.709)
    lines = format_xrd_crosshair_x_lines(
        float(twotheta_to_Q(np.array([10.0]), 0.709)[0]),
        axis_mode=getattr(fig, "_xy_axis_mode"),
        wavelength=getattr(fig, "_xy_wavelength"),
    )
    assert any(s.startswith("2θ=") for s in lines)
    plt.close(fig)


def test_old_operando_without_wl_stays_q_d_only():
    fig, ax = plt.subplots()
    set_operando_axis_mode(fig, "Q")  # no wavelength (old session)
    fig._operando_wl = None  # type: ignore[attr-defined]
    wl = resolve_operando_wavelength(fig=fig)
    assert wl is None
    lines = format_xrd_crosshair_x_lines(2.0, axis_mode="Q", wavelength=wl)
    assert not any(s.startswith("2θ=") for s in lines)
    plt.close(fig)
