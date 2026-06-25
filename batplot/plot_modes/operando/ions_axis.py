"""EC ions-mode Y-axis helpers (time axis with ion readouts)."""

from __future__ import annotations

from typing import Callable

import numpy as np
from matplotlib.axes import Axes  # type: ignore[import-untyped]
from matplotlib.ticker import FuncFormatter, MaxNLocator, ScalarFormatter  # type: ignore[import-untyped]

IONS_STATUS_PRECISION = 4
# Slightly fewer decimals on axis ticks keeps labels readable; same underlying value.
IONS_TICK_PRECISION = 3


def nice_ions_step(rng: float, approx: int = 6) -> float:
    """Legacy helper; tick spacing is handled by ``MaxNLocator`` on the time axis."""
    if not np.isfinite(rng) or rng <= 0:
        return 1.0
    raw = rng / max(1, approx)
    exp = np.floor(np.log10(raw))
    base = raw / (10**exp)
    if base < 1.5:
        step = 1.0
    elif base < 3.5:
        step = 2.0
    elif base < 7.5:
        step = 5.0
    else:
        step = 10.0
    return float(step * (10**exp))


def ions_value_at_time(t, ions_abs, y_time: float) -> float:
    t_arr = np.asarray(t, float)
    ions_arr = np.asarray(ions_abs, float)
    return float(np.interp(y_time, t_arr, ions_arr, left=ions_arr[0], right=ions_arr[-1]))


def format_ions_value(val: float, *, precision: int = IONS_STATUS_PRECISION) -> str:
    """Format ion count for status bar / crosshair."""
    if not np.isfinite(val):
        return "nan"
    text = f"{val:.{precision}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def make_ions_tick_formatter(t, ions_abs) -> Callable[[float, float], str]:
    """Label each tick with the true ion count at that time (no 1-2-5 rounding)."""
    t_arr = np.asarray(t, float)
    ions_arr = np.asarray(ions_abs, float)

    def _fmt(y: float, _pos: float) -> str:
        if ions_arr.size == 0 or t_arr.size == 0:
            return ""
        try:
            val = ions_value_at_time(t_arr, ions_arr, y)
            return format_ions_value(val, precision=IONS_TICK_PRECISION)
        except Exception:
            return ""

    return _fmt


def install_ec_ions_y_display(ec_ax, t, ions_abs, *, step: float | None = None, save_prev: bool = True) -> None:
    """Install ions tick formatter and high-precision ``format_coord`` on ``ec_ax``.

    The EC curve stays plotted vs time on Y; ticks are placed in time by matplotlib
    but labeled with interpolated ion counts. Labels use the same values as the
    status bar (no extra rounding to 1.8 when the true value is 1.746).
    """
    del step  # spacing comes from MaxNLocator on time; kept for call-site compat
    t_arr = np.asarray(t, float)
    ions_arr = np.asarray(ions_abs, float)

    if save_prev:
        if not hasattr(ec_ax, "_prev_yformatter"):
            try:
                ec_ax._prev_yformatter = ec_ax.yaxis.get_major_formatter()
            except Exception:
                ec_ax._prev_yformatter = None
        if not hasattr(ec_ax, "_prev_ylocator"):
            try:
                ec_ax._prev_ylocator = ec_ax.yaxis.get_major_locator()
            except Exception:
                ec_ax._prev_ylocator = None
        if not hasattr(ec_ax, "_prev_format_coord"):
            ec_ax._prev_format_coord = ec_ax.format_coord

    ec_ax.yaxis.set_major_formatter(FuncFormatter(make_ions_tick_formatter(t_arr, ions_arr)))
    try:
        ec_ax.yaxis.set_major_locator(MaxNLocator(nbins="auto", steps=[1, 2, 5], min_n_ticks=4))
    except Exception:
        pass

    def format_coord(x: float, y: float) -> str:
        try:
            ions_val = ions_value_at_time(t_arr, ions_arr, y)
            return f"x={x:.4f}, y={format_ions_value(ions_val)}"
        except Exception:
            return f"x={x:.4g}, y={y:.4g}"

    ec_ax.format_coord = format_coord


def restore_ec_time_y_display(ec_ax) -> None:
    """Restore time-mode Y formatter/locator and default status-bar formatting."""
    prev_fmt = getattr(ec_ax, "_prev_yformatter", None)
    try:
        if prev_fmt is not None:
            ec_ax.yaxis.set_major_formatter(prev_fmt)
        else:
            ec_ax.yaxis.set_major_formatter(ScalarFormatter())
        prev_loc = getattr(ec_ax, "_prev_ylocator", None)
        if prev_loc is not None:
            ec_ax.yaxis.set_major_locator(prev_loc)
    except Exception:
        pass

    prev_fc = getattr(ec_ax, "_prev_format_coord", None)
    if prev_fc is not None:
        ec_ax.format_coord = prev_fc
    else:
        ec_ax.format_coord = Axes.format_coord.__get__(ec_ax, type(ec_ax))

    for attr in ("_prev_yformatter", "_prev_ylocator", "_prev_format_coord"):
        try:
            delattr(ec_ax, attr)
        except Exception:
            pass


__all__ = [
    "IONS_STATUS_PRECISION",
    "format_ions_value",
    "install_ec_ions_y_display",
    "ions_value_at_time",
    "make_ions_tick_formatter",
    "nice_ions_step",
    "restore_ec_time_y_display",
]
