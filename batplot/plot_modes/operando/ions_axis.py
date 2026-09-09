"""EC ions-mode helpers: overlays + status readout (time spine unchanged)."""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np
from matplotlib.axes import Axes  # type: ignore[import-untyped]
from matplotlib.ticker import ScalarFormatter  # type: ignore[import-untyped]

IONS_STATUS_PRECISION = 4
# Kept for callers/tests that format ion values; axis ticks stay on time.
IONS_TICK_PRECISION = 3
# Ion tags stay smaller than axis tick labels so they do not look like a 2nd scale.
IONS_ANNOT_SIZE_FRAC = 0.55
IONS_ANNOT_SIZE_MIN = 8.0
IONS_ANNOT_SIZE_MAX = 11.0


def nice_ions_step(rng: float, approx: int = 6) -> float:
    """Legacy helper retained for API compatibility."""
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
    """Format ion count for status bar / annotations."""
    if not np.isfinite(val):
        return "nan"
    text = f"{val:.{precision}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def make_ions_tick_formatter(t, ions_abs) -> Callable[[float, float], str]:
    """Legacy: format a time tick as ion count (not used for axis chrome)."""
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


def charge_segment_bounds(current_mA, *, atol: float = 1e-9) -> list[int]:
    """Indices where charge/discharge current sign changes (plus start/end)."""
    i_mA = np.asarray(current_mA, float)
    if i_mA.size == 0:
        return [0]
    sgn = np.sign(i_mA)
    sgn[np.isclose(i_mA, 0.0, atol=atol)] = 0.0
    last = 0.0
    seg_bounds = [0]
    for k in range(1, len(sgn)):
        cur = sgn[k] if sgn[k] != 0 else last
        prev = sgn[k - 1] if sgn[k - 1] != 0 else last
        if k == 1:
            last = prev
        if cur != prev:
            seg_bounds.append(k)
        last = cur
    seg_bounds.append(len(sgn) - 1)
    return seg_bounds


def clear_ec_ion_overlays(ec_ax) -> None:
    """Remove ion guide lines and segment annotations."""
    for a in getattr(ec_ax, "_ion_annots", []) or []:
        try:
            a.remove()
        except Exception:
            pass
    ec_ax._ion_annots = []
    for gl in getattr(ec_ax, "_ion_guides", []) or []:
        try:
            gl.remove()
        except Exception:
            pass
    ec_ax._ion_guides = []


def _axis_tick_fontsize(ec_ax) -> float:
    try:
        for tick in ec_ax.yaxis.get_major_ticks():
            for lab in (tick.label2, tick.label1):
                if lab is not None and lab.get_visible():
                    return float(lab.get_fontsize())
    except Exception:
        pass
    try:
        return float(plt.rcParams.get("font.size", 12))
    except Exception:
        return 12.0


def _axis_tick_fontfamily(ec_ax) -> str | None:
    try:
        for tick in ec_ax.yaxis.get_major_ticks():
            for lab in (tick.label2, tick.label1):
                if lab is not None and lab.get_visible():
                    fam = lab.get_fontfamily()
                    if isinstance(fam, (list, tuple)):
                        return str(fam[0]) if fam else None
                    return str(fam) if fam else None
    except Exception:
        pass
    try:
        chain = plt.rcParams.get("font.sans-serif", ["DejaVu Sans"])
        return str(chain[0]) if chain else None
    except Exception:
        return None


def ion_annot_fontsize(ec_ax) -> float:
    """Annotation size: same family as ticks, always smaller than tick labels."""
    base = _axis_tick_fontsize(ec_ax)
    return float(max(IONS_ANNOT_SIZE_MIN, min(IONS_ANNOT_SIZE_MAX, base * IONS_ANNOT_SIZE_FRAC)))


def style_ion_annotation(txt, ec_ax) -> None:
    """Apply consistent annotation chrome (not axis-tick size/weight)."""
    try:
        txt._bp_ion_annot = True  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        txt.set_fontsize(ion_annot_fontsize(ec_ax))
    except Exception:
        pass
    try:
        txt.set_fontweight("normal")
    except Exception:
        pass
    fam = _axis_tick_fontfamily(ec_ax)
    if fam:
        try:
            txt.set_fontfamily(fam)
        except Exception:
            pass
    try:
        txt.set_bbox(dict(boxstyle="round,pad=0.2", fc="white", ec="0.7", alpha=0.8))
    except Exception:
        pass


def restyle_ec_ion_annotations(ec_ax) -> None:
    """Re-apply annotation style after session/font restore (all tags identical)."""
    for txt in getattr(ec_ax, "_ion_annots", []) or []:
        try:
            style_ion_annotation(txt, ec_ax)
        except Exception:
            pass


def _tag_anchor_and_offset(ec_ax, end_v: float, end_t: float) -> tuple[tuple[float, float], tuple[float, float], str]:
    """Place tag at the curve point, offset toward the plot interior (away from Time spine)."""
    try:
        x0, x1 = ec_ax.get_xlim()
    except Exception:
        x0, x1 = 0.0, 1.0
    span = (x1 - x0) if x1 != x0 else 1.0
    # Keep anchors away from the right Time-spine strip and left edge.
    x_lo = x0 + 0.12 * span
    x_hi = x0 + 0.78 * span
    x_anchor = float(min(max(end_v, x_lo), x_hi))
    mid = 0.5 * (x0 + x1)
    if x_anchor >= mid:
        return (x_anchor, end_t), (-6.0, 4.0), "right"
    return (x_anchor, end_t), (6.0, 4.0), "left"


def place_ec_ion_segment_labels(
    ec_ax,
    t,
    ions_abs,
    voltage=None,
    seg_bounds: Sequence[int] | None = None,
    *,
    current_mA=None,
) -> None:
    """Add dashed guides + ion-count tags at segment ends. Does not touch spines/ticks."""

    def _fmt2(x: float) -> str:
        return format_ions_value(float(x), precision=2)

    t_arr = np.asarray(t, float)
    ions_arr = np.asarray(ions_abs, float)
    if t_arr.size == 0 or ions_arr.size != t_arr.size:
        return
    if seg_bounds is None:
        if current_mA is None:
            current_mA = getattr(ec_ax, "_ec_current_mA", None)
        if current_mA is None:
            seg_bounds = [0, len(t_arr) - 1]
        else:
            seg_bounds = charge_segment_bounds(current_mA)
    if voltage is None:
        voltage = getattr(ec_ax, "_ec_voltage_v", None)
    v_arr = None if voltage is None else np.asarray(voltage, float)

    clear_ec_ion_overlays(ec_ax)
    # Nudge tags that share nearly the same time so they do not stack.
    placed_y: list[float] = []
    y_span = float(np.nanmax(t_arr) - np.nanmin(t_arr)) if t_arr.size else 1.0
    min_dy = 0.025 * y_span if y_span > 0 else 0.05

    for si in range(len(seg_bounds) - 1):
        a = int(seg_bounds[si])
        b = int(seg_bounds[si + 1])
        if b < a:
            continue
        end_i = float(ions_arr[b])
        end_t = float(t_arr[b])
        if v_arr is not None and v_arr.size == t_arr.size:
            end_v = float(v_arr[b])
        else:
            try:
                x0, x1 = ec_ax.get_xlim()
                end_v = float(x0 + 0.55 * (x1 - x0))
            except Exception:
                end_v = 0.0
        try:
            guide = ec_ax.axhline(
                y=end_t, color="0.7", linestyle="--", linewidth=0.8, alpha=0.5, zorder=0,
            )
            ec_ax._ion_guides.append(guide)
        except Exception:
            pass
        y_text = end_t
        for py in placed_y:
            if abs(y_text - py) < min_dy:
                y_text = py + min_dy
        placed_y.append(y_text)
        xy, xytext, ha = _tag_anchor_and_offset(ec_ax, end_v, y_text)
        try:
            txt = ec_ax.annotate(
                _fmt2(end_i),
                xy=xy,
                xytext=xytext,
                textcoords="offset points",
                ha=ha,
                va="bottom",
            )
            style_ion_annotation(txt, ec_ax)
            ec_ax._ion_annots.append(txt)
        except Exception:
            pass


def restore_ion_overlays_from_state(
    ec_ax,
    *,
    ion_guides: Iterable[float] | None = None,
    ion_annots: Iterable[dict] | None = None,
) -> None:
    """Recreate saved guides/annotations without altering axis chrome.

    Prefer rebuilding from ``_ions_abs`` when available so tag style/placement
    matches a fresh ``ey``→``n`` (avoids legacy right-spine / tick-sized tags).
    """
    t = getattr(ec_ax, "_ec_time_h", None)
    ions = getattr(ec_ax, "_ions_abs", None)
    if t is not None and ions is not None:
        try:
            t_arr = np.asarray(t, float)
            ions_arr = np.asarray(ions, float)
            if t_arr.size and ions_arr.size == t_arr.size:
                place_ec_ion_segment_labels(ec_ax, t_arr, ions_arr)
                return
        except Exception:
            pass

    clear_ec_ion_overlays(ec_ax)
    for y_guide in ion_guides or []:
        try:
            ec_ax._ion_guides.append(
                ec_ax.axhline(
                    y=float(y_guide), color="0.7", linestyle="--",
                    linewidth=0.8, alpha=0.5, zorder=0,
                )
            )
        except Exception:
            pass
    for ann in ion_annots or []:
        try:
            raw_xy = tuple(ann.get("xy", (0.0, 0.0)))
            end_v = float(raw_xy[0]) if len(raw_xy) > 0 else 0.0
            end_t = float(raw_xy[1]) if len(raw_xy) > 1 else 0.0
            xy, xytext, ha = _tag_anchor_and_offset(ec_ax, end_v, end_t)
            txt = ec_ax.annotate(
                str(ann.get("text", "")),
                xy=xy,
                xytext=xytext,
                textcoords="offset points",
                ha=ha,
                va="bottom",
            )
            style_ion_annotation(txt, ec_ax)
            ec_ax._ion_annots.append(txt)
        except Exception:
            pass


def install_ec_ions_y_display(ec_ax, t, ions_abs, *, step: float | None = None, save_prev: bool = True) -> None:
    """Enable ions status-bar readout only — leave Y spine/ticks/labels untouched.

    The EC curve and axis stay in time. Segment ion numbers are drawn separately
    via ``place_ec_ion_segment_labels``.
    """
    del step  # API compat
    t_arr = np.asarray(t, float)
    ions_arr = np.asarray(ions_abs, float)

    if save_prev and not hasattr(ec_ax, "_prev_format_coord"):
        ec_ax._prev_format_coord = ec_ax.format_coord

    def format_coord(x: float, y: float) -> str:
        try:
            ions_val = ions_value_at_time(t_arr, ions_arr, y)
            return f"x={x:.4f}, y={format_ions_value(ions_val)}"
        except Exception:
            return f"x={x:.4g}, y={y:.4g}"

    ec_ax.format_coord = format_coord


def restore_ec_time_y_display(ec_ax) -> None:
    """Restore default status-bar formatting after leaving ions overlays."""
    # Strip any legacy ion tick formatter/locator from older sessions.
    prev_fmt = getattr(ec_ax, "_prev_yformatter", None)
    try:
        if prev_fmt is not None:
            ec_ax.yaxis.set_major_formatter(prev_fmt)
        else:
            # If a FuncFormatter was installed by an older build, reset to scalar.
            fmt = ec_ax.yaxis.get_major_formatter()
            if type(fmt).__name__ == "FuncFormatter":
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


def heal_ec_ions_right_label_wasd(wasd: dict | None) -> bool:
    """No-op: ions mode no longer remaps the Y spine / WASD labels.

    Kept for import compatibility; always returns False.
    """
    del wasd
    return False


def ensure_ec_ions_right_tick_labels(ec_ax, *, wasd: dict | None = None) -> None:
    """No-op: ions overlays must not force right tick numbers / WASD.

    Kept for import compatibility.
    """
    del ec_ax, wasd


__all__ = [
    "IONS_STATUS_PRECISION",
    "charge_segment_bounds",
    "clear_ec_ion_overlays",
    "ensure_ec_ions_right_tick_labels",
    "format_ions_value",
    "heal_ec_ions_right_label_wasd",
    "install_ec_ions_y_display",
    "ion_annot_fontsize",
    "ions_value_at_time",
    "make_ions_tick_formatter",
    "nice_ions_step",
    "place_ec_ion_segment_labels",
    "restyle_ec_ion_annotations",
    "restore_ec_time_y_display",
    "restore_ion_overlays_from_state",
    "style_ion_annotation",
]
