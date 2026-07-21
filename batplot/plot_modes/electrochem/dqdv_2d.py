"""dQ/dV 2D contour axis helpers for electrochemistry interactive mode."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib.ticker import FuncFormatter, NullFormatter  # type: ignore[import-untyped]

from ...ui import capture_axes_tick_locators, restore_axes_tick_locators, set_spine_side_color
from ...utils import natural_sort_key
from ...ec_common import _default_ec_figsize
from ..common.font_extras import apply_font_extras_from_cfg, apply_session_font_cfg, font_extras_export_dict
from ..common.fonts import collect_operando_font_artists


def _dqdv_2d_row_tick_indices(n_rows: int, max_ticks: int = 24) -> np.ndarray:
    """Row indices for readable y-axis ticks."""
    n_rows = int(max(0, n_rows))
    if n_rows <= 0:
        return np.array([], dtype=int)
    cap = int(max(4, max_ticks))
    if n_rows <= cap:
        return np.arange(n_rows, dtype=int)
    return np.unique(np.round(np.linspace(0, n_rows - 1, cap)).astype(int))


def _dqdv_2d_voltage_tick_formatter(v_lo: float, v_hi: float, dv: float):
    """Map internal butterfly x coordinates to displayed voltage labels."""
    v_lo = float(v_lo)
    v_hi = float(v_hi)
    dv = float(dv)

    def _fmt(x, pos=None):
        try:
            x_value = float(x)
        except Exception:
            return ""
        if not np.isfinite(x_value) or dv <= 0:
            return ""
        eps = 1e-9 * max(dv, 1e-12)
        if x_value < -eps or x_value > 2 * dv + eps:
            return ""
        if x_value <= dv + eps:
            voltage = v_hi + (x_value / dv) * (v_lo - v_hi)
        else:
            voltage = v_lo + ((x_value - dv) / dv) * (v_hi - v_lo)
        if not np.isfinite(voltage):
            return ""
        return f"{voltage:g}"

    return _fmt


def _dqdv_2d_ensure_voltage_formatter(cax, v_lo: float, v_hi: float, dv: float) -> None:
    """Keep butterfly x tick labels in voltage on the internal axis."""
    cax.xaxis.set_major_formatter(FuncFormatter(_dqdv_2d_voltage_tick_formatter(v_lo, v_hi, dv)))
    try:
        cax.xaxis.set_minor_formatter(NullFormatter())
    except Exception:
        pass


def _dqdv_2d_set_row_y_ticks(cax, row_labels: List[str], Zm: Any) -> None:
    n_rows = int(Zm.shape[0])
    y_idx = _dqdv_2d_row_tick_indices(n_rows, max_ticks=24)
    cax.set_yticks(y_idx)
    cax.set_yticklabels([row_labels[i] for i in y_idx])


def _dqdv_2d_ensure_center_lines(cax, dv: float) -> None:
    try:
        previous = getattr(cax, "_dqdv_center_lines", None)
        if previous:
            for line in previous:
                try:
                    line.remove()
                except Exception:
                    pass
        white = cax.axvline(
            float(dv), color="1.0", ls="--", lw=3.0, alpha=1.0, zorder=25, clip_on=False
        )
        dark = cax.axvline(
            float(dv), color="0.1", ls=":", lw=1.2, alpha=0.9, zorder=24, clip_on=False
        )
        cax._dqdv_center_lines = (white, dark)
    except Exception:
        pass


def _dqdv_2d_restore_custom_labels(cax) -> None:
    """Re-apply user-renamed axis labels after a data-only refresh."""
    labels = getattr(cax, "_custom_labels", None)
    if not isinstance(labels, dict):
        return
    try:
        if labels.get("x"):
            cax.set_xlabel(str(labels["x"]))
        if labels.get("y"):
            cax.set_ylabel(str(labels["y"]))
    except Exception:
        pass


def _dqdv_2d_style_axes(
    cax,
    v_lo: float,
    v_hi: float,
    dv: float,
    row_labels: List[str],
    Zm: Any,
    *,
    style_mode: str = "full",
) -> None:
    """Style dQ/dV 2D butterfly axes."""
    mode = str(style_mode or "full").lower()
    if mode == "full":
        cax.set_xlabel("Potential (V) (left: discharge right: charge)")
        cax.set_ylabel("Cycle (visible traces)")
        base_fs = float(plt.rcParams.get("font.size", 10))
        cax.tick_params(axis="both", which="major", labelsize=base_fs)
        try:
            cax.xaxis.label.set_fontsize(base_fs)
            cax.yaxis.label.set_fontsize(base_fs)
        except Exception:
            pass
    if mode in ("full", "data"):
        _dqdv_2d_set_row_y_ticks(cax, row_labels, Zm)
    _dqdv_2d_ensure_voltage_formatter(cax, v_lo, v_hi, dv)
    if mode in ("full", "data", "minimal"):
        _dqdv_2d_ensure_center_lines(cax, dv)
        try:
            cax.set_xlim(0.0, float(2 * dv))
        except Exception:
            pass
    if mode == "data":
        _dqdv_2d_restore_custom_labels(cax)


def _dqdv_interp_unique_sorted_x(x: np.ndarray, z: np.ndarray, gx: np.ndarray) -> np.ndarray:
    """Interpolate z(x) onto grid gx; duplicate x are averaged. Out-of-range -> NaN."""
    x = np.asarray(x, dtype=float)
    z = np.asarray(z, dtype=float)
    m = np.isfinite(x) & np.isfinite(z)
    if not np.any(m):
        return np.full_like(gx, np.nan, dtype=float)
    x = x[m]
    z = z[m]
    order = np.argsort(x, kind="mergesort")
    x = x[order]
    z = z[order]
    xu: List[float] = []
    zu: List[float] = []
    i = 0
    n = len(x)
    while i < n:
        j = i + 1
        while j < n and x[j] == x[i]:
            j += 1
        xu.append(float(x[i]))
        zu.append(float(np.nanmean(z[i:j])))
        i = j
    xu_arr = np.asarray(xu, dtype=float)
    zu_arr = np.asarray(zu, dtype=float)
    if xu_arr.size == 0:
        return np.full_like(gx, np.nan, dtype=float)
    if xu_arr.size == 1:
        out = np.full_like(gx, np.nan, dtype=float)
        out[np.abs(gx - xu_arr[0]) < 1e-12] = zu_arr[0]
        return out
    return np.interp(gx, xu_arr, zu_arr, left=np.nan, right=np.nan)


def _dqdv_butterfly_xz_from_line(
    ln,
    role: str,
    v_lo: float,
    v_hi: float,
    dv: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Map dQ/dV samples to display x in [0, 2*dv] (matches imshow extent).

    Left panel [0, dv]: discharge V_hi → V_lo (high potential at left edge).
    Right panel [dv, 2*dv]: charge V_lo → V_hi (low at center divider, high at right).
    """
    xv = np.asarray(ln.get_xdata(), dtype=float)
    yv = np.asarray(ln.get_ydata(), dtype=float)
    n = int(min(xv.size, yv.size))
    if n < 2:
        return np.array([]), np.array([])
    xv = xv[:n]
    yv = yv[:n]
    m = (xv >= v_lo) & (xv <= v_hi) & np.isfinite(yv)
    if not np.any(m):
        return np.array([]), np.array([])
    v_sub = xv[m]
    z_sub = yv[m]
    if dv <= 0 or not np.isfinite(dv):
        return np.array([]), np.array([])
    if role == "charge":
        xb = float(dv) + (v_sub - v_lo)
    else:
        xb = (v_hi - v_sub)
    return xb.astype(float), z_sub.astype(float)


def _dqdv_build_butterfly_contour_stack(
    file_data: List[Dict[str, Any]],
    v_lo: float,
    v_hi: float,
    nx: int = 320,
) -> Optional[Tuple[np.ndarray, np.ndarray, List[str]]]:
    """Stack (smoothed) dQ/dV into 2D array for butterfly potential axis. Returns (Z, gx, row_labels) or None."""
    v_lo, v_hi = float(min(v_lo, v_hi)), float(max(v_lo, v_hi))
    dv = v_hi - v_lo
    if dv <= 0 or not np.isfinite(dv):
        return None
    gx = np.linspace(0.0, 2.0 * dv, int(max(32, nx)))
    row_keys: List[Tuple[int, Any]] = []
    for fi, f in enumerate(file_data):
        if not f.get("visible", True):
            continue
        cl = f.get("cycle_lines") or {}
        for cyc, parts in cl.items():
            if not isinstance(parts, dict):
                continue
            chg = parts.get("charge")
            dch = parts.get("discharge")
            vis = (
                (chg is not None and chg.get_visible())
                or (dch is not None and dch.get_visible())
            )
            if vis:
                row_keys.append((fi, cyc))
    if not row_keys:
        return None

    def _sort_key(t: Tuple[int, Any]):
        fi, cyc = t
        if isinstance(cyc, (int, float)):
            return (fi, float(cyc))
        return (fi, natural_sort_key(str(cyc)))

    row_keys = sorted(set(row_keys), key=_sort_key)
    z_rows: List[np.ndarray] = []
    row_labels: List[str] = []
    for (fi, cyc) in row_keys:
        f = file_data[fi]
        parts = (f.get("cycle_lines") or {}).get(cyc)
        if not isinstance(parts, dict):
            continue
        xs: List[float] = []
        zs: List[float] = []
        for role in ("discharge", "charge"):
            ln = parts.get(role)
            if ln is None or not ln.get_visible():
                continue
            xb, zb = _dqdv_butterfly_xz_from_line(ln, role, v_lo, v_hi, dv)
            if xb.size:
                xs.extend(xb.tolist())
                zs.extend(zb.tolist())
        if not xs:
            continue
        x_arr = np.asarray(xs, dtype=float)
        z_arr = np.asarray(zs, dtype=float)
        row_z = _dqdv_interp_unique_sorted_x(x_arr, z_arr, gx)
        if not np.any(np.isfinite(row_z)):
            continue
        z_rows.append(row_z)
        disp = f.get("display_name") or f.get("filename") or str(fi + 1)
        if len(file_data) > 1:
            row_labels.append(f"{disp} c{cyc}")
        else:
            row_labels.append(str(cyc))
    if not z_rows:
        return None
    Z = np.vstack(z_rows)
    return Z, gx, row_labels


def bind_dqdv_2d_contour_figure(
    cfig,
    cax,
    im,
    v_lo: float,
    v_hi: float,
    row_labels: List[str],
    zlab: Optional[str] = None,
    file_data: Optional[List[Dict[str, Any]]] = None,
    nx: int = 320,
    style_mode: str = "full",
) -> None:
    """Tag a contour figure as dQ/dV 2D and apply butterfly axis styling."""
    v_lo, v_hi = float(min(v_lo, v_hi)), float(max(v_lo, v_hi))
    dv = float(v_hi - v_lo)
    cfig._is_dqdv_2d_contour = True
    cfig._dqdv_2d_v_lo = v_lo
    cfig._dqdv_2d_v_hi = v_hi
    if not hasattr(cfig, "_dqdv_2d_v_lo_orig"):
        cfig._dqdv_2d_v_lo_orig = v_lo
        cfig._dqdv_2d_v_hi_orig = v_hi
    cfig._dqdv_2d_row_labels = [str(s) for s in row_labels]
    cfig._dqdv_2d_zlabel = str(zlab or "dQ/dV")
    cfig._dqdv_2d_axis_mapping_version = 2
    if file_data is not None:
        cfig._dqdv_2d_file_data = file_data
    cfig._dqdv_2d_nx = int(max(32, nx))
    try:
        Zm = np.ma.masked_invalid(np.asarray(im.get_array(), dtype=float))
    except Exception:
        Zm = im.get_array()
    _dqdv_2d_style_axes(
        cax, v_lo, v_hi, dv, list(cfig._dqdv_2d_row_labels), Zm, style_mode=style_mode
    )


def update_dqdv_2d_potential_window(
    fig,
    ax,
    im,
    v_lo: float,
    v_hi: float,
    *,
    nx: Optional[int] = None,
) -> bool:
    """Rebuild 2D dQ/dV butterfly map for a new potential window (V_lo, V_hi).

    Display x runs 0..2*dv with discharge V_hi→V_lo on the left and charge V_lo→V_hi on the right.
    """
    if not getattr(fig, "_is_dqdv_2d_contour", False):
        return False
    file_data = getattr(fig, "_dqdv_2d_file_data", None)
    if not file_data:
        print("Cannot change potential window: source dQ/dV data is not available (re-open 2D from dQ/dV menu).")
        return False
    v_lo, v_hi = float(min(v_lo, v_hi)), float(max(v_lo, v_hi))
    dv = float(v_hi - v_lo)
    if dv <= 0 or not np.isfinite(dv):
        print("Invalid potential window: upper voltage must be greater than lower.")
        return False
    nx_use = int(nx if nx is not None else getattr(fig, "_dqdv_2d_nx", 320))
    nx_use = max(32, nx_use)
    try:
        built = _dqdv_build_butterfly_contour_stack(file_data, v_lo, v_hi, nx=nx_use)
    except Exception as e:
        print(f"Could not rebuild 2D map: {e}")
        return False
    if built is None:
        print("No dQ/dV points in that potential window (check range and cycle visibility).")
        return False
    Z, _gx, row_labels = built
    Zm = np.ma.masked_invalid(Z)
    n_rows = int(Zm.shape[0])
    extent = (0.0, float(2 * dv), -0.5, float(n_rows - 0.5))
    try:
        clim = im.get_clim()
    except Exception:
        clim = None
    im.set_data(Zm)
    im.set_extent(extent)
    ax.set_xlim(0.0, float(2 * dv))
    ax.set_ylim(-0.5, float(n_rows - 0.5))
    if clim is not None:
        try:
            im.set_clim(clim)
        except Exception:
            pass
    fig._dqdv_2d_v_lo = v_lo
    fig._dqdv_2d_v_hi = v_hi
    fig._dqdv_2d_row_labels = [str(s) for s in row_labels]
    bind_dqdv_2d_contour_figure(
        fig, ax, im, v_lo, v_hi, row_labels,
        zlab=str(getattr(fig, "_dqdv_2d_zlabel", "dQ/dV")),
        style_mode="data",
    )
    return True


def reapply_dqdv_2d_contour_axes(fig, ax, im, cbar=None, *, style_mode: str = "minimal") -> None:
    """Restore butterfly voltage formatter/center line without resetting user styling."""
    if not getattr(fig, "_is_dqdv_2d_contour", False):
        return
    try:
        v_lo = float(getattr(fig, "_dqdv_2d_v_lo"))
        v_hi = float(getattr(fig, "_dqdv_2d_v_hi"))
    except Exception:
        return
    dv = float(v_hi - v_lo)
    if dv <= 0 or not np.isfinite(dv):
        return
    row_labels = [str(s) for s in (getattr(fig, "_dqdv_2d_row_labels", None) or [])]
    zlab = str(getattr(fig, "_dqdv_2d_zlabel", None) or "dQ/dV")
    try:
        Zm = np.ma.masked_invalid(np.asarray(im.get_array(), dtype=float))
    except Exception:
        Zm = im.get_array()
    if len(row_labels) != int(getattr(Zm, "shape", (0,))[0]):
        row_labels = [str(i) for i in range(int(Zm.shape[0]))]
    _dqdv_2d_style_axes(ax, v_lo, v_hi, dv, row_labels, Zm, style_mode=style_mode)
    if cbar is not None:
        try:
            cbar.ax._colorbar_label = zlab
        except Exception:
            pass


def build_dqdv_2d_snapshot(
    cfig,
    cax,
    im,
    v_lo: float,
    v_hi: float,
    row_labels: List[str],
    zlab: str,
    cbar=None,
) -> Optional[Dict[str, Any]]:
    """Serializable state for embedding in EC .pkl (dQ/dV 2D companion)."""
    try:
        arr = np.asarray(im.get_array(), dtype=float)
        if hasattr(arr, "mask"):
            arr = np.ma.filled(arr, np.nan)
    except Exception:
        return None
    if arr.ndim != 2 or arr.size == 0:
        return None
    cmap_name = getattr(im, "_operando_cmap_name", None)
    if not cmap_name:
        try:
            cmap_name = im.get_cmap().name  # type: ignore[union-attr]
        except Exception:
            cmap_name = "viridis"
    def _tick_width(axis_obj, which: str):
        try:
            tick_kw = axis_obj._major_tick_kw if which == "major" else axis_obj._minor_tick_kw
            width = tick_kw.get("width")
            if width is not None:
                return float(width)
        except Exception:
            pass
        try:
            ticks = axis_obj.get_major_ticks() if which == "major" else axis_obj.get_minor_ticks()
            if ticks:
                return float(ticks[0].tick1line.get_linewidth())
        except Exception:
            pass
        return None
    def _tick_length(axis_obj, which: str):
        try:
            tick_kw = axis_obj._major_tick_kw if which == "major" else axis_obj._minor_tick_kw
            length = tick_kw.get("size") or tick_kw.get("length")
            if length is not None:
                return float(length)
        except Exception:
            pass
        try:
            ticks = axis_obj.get_major_ticks() if which == "major" else axis_obj.get_minor_ticks()
            if ticks:
                return float(ticks[0].tick1line.get_markersize())
        except Exception:
            pass
        return None
    cbar_ax = getattr(cbar, "ax", None)
    snap: Dict[str, Any] = {
        "version": 1,
        "kind": "dqdv_2d_contour",
        "axis_mapping_version": 2,
        "v_lo": float(v_lo),
        "v_hi": float(v_hi),
        "Z": np.array(arr, dtype=float, copy=True),
        "row_labels": [str(s) for s in row_labels],
        "zlabel": str(zlab or "dQ/dV"),
        "cmap": str(cmap_name),
        "clim": tuple(float(x) for x in im.get_clim()),
        "figsize": [float(x) for x in cfig.get_size_inches()],
        "xlim": tuple(float(x) for x in cax.get_xlim()),
        "ylim": tuple(float(x) for x in cax.get_ylim()),
        "nx": int(getattr(cfig, "_dqdv_2d_nx", 320)),
        "v_lo_orig": float(getattr(cfig, "_dqdv_2d_v_lo_orig", v_lo)),
        "v_hi_orig": float(getattr(cfig, "_dqdv_2d_v_hi_orig", v_hi)),
        "axis": {
            "xlabel": cax.get_xlabel(),
            "ylabel": cax.get_ylabel(),
            "xlabel_visible": bool(cax.xaxis.label.get_visible()),
            "ylabel_visible": bool(cax.yaxis.label.get_visible()),
            "x_labelpad": getattr(cax.xaxis, "labelpad", None),
            "y_labelpad": getattr(cax.yaxis, "labelpad", None),
        },
        "spines": {
            name: {
                "linewidth": float(sp.get_linewidth()),
                "color": sp.get_edgecolor(),
                "visible": bool(sp.get_visible()),
            }
            for name, sp in cax.spines.items()
        },
        "ticks": {
            "widths": {
                "x_major": _tick_width(cax.xaxis, "major"),
                "x_minor": _tick_width(cax.xaxis, "minor"),
                "y_major": _tick_width(cax.yaxis, "major"),
                "y_minor": _tick_width(cax.yaxis, "minor"),
            },
            "lengths": {
                "x_major": _tick_length(cax.xaxis, "major"),
                "x_minor": _tick_length(cax.xaxis, "minor"),
                "y_major": _tick_length(cax.yaxis, "major"),
                "y_minor": _tick_length(cax.yaxis, "minor"),
            },
            "direction": getattr(cfig, "_tick_direction", "out"),
            "locator_state": capture_axes_tick_locators(cax, ("x", "y")),
        },
        "font": {
            "size": plt.rcParams.get("font.size"),
            "family": list(plt.rcParams.get("font.sans-serif", [])),
            "mathtext_fontset": plt.rcParams.get("mathtext.fontset"),
            **font_extras_export_dict(cfig),
        },
        "colorbar": {
            "label": str(getattr(cbar_ax, "_colorbar_label", zlab)) if cbar_ax is not None else str(zlab),
            "mode": getattr(cfig, "_colorbar_label_mode", "highlow"),
            "visible": bool(cbar_ax.get_visible()) if cbar_ax is not None else True,
        },
    }
    return snap


def restore_dqdv_2d_companion_figure(blob: Dict[str, Any]) -> Optional[Tuple[Any, Any, Any, Any]]:
    """Rebuild 2D dQ/dV figure from session blob. Returns (cfig, cax, im, cbar) or None."""
    if not isinstance(blob, dict) or blob.get("Z") is None:
        return None
    try:
        v_lo = float(blob["v_lo"])
        v_hi = float(blob["v_hi"])
    except Exception:
        return None
    dv = v_hi - v_lo
    if dv <= 0:
        return None
    Z = np.asarray(blob["Z"], dtype=float)
    row_labels = [str(x) for x in (blob.get("row_labels") or [])]
    zlab = str(blob.get("zlabel") or "dQ/dV")
    cmap = str(blob.get("cmap") or "viridis")
    figsize = blob.get("figsize")
    if not figsize:
        figsize = list(_default_ec_figsize())
    try:
        cfig, cax = plt.subplots(figsize=(float(figsize[0]), float(figsize[1])))
    except Exception:
        cfig, cax = plt.subplots(figsize=_default_ec_figsize())
    Zm = np.ma.masked_invalid(Z)
    extent = (0.0, float(2 * dv), -0.5, float(Zm.shape[0] - 0.5))
    im = cax.imshow(
        Zm,
        aspect="auto",
        origin="lower",
        extent=extent,
        cmap=cmap,
        interpolation="nearest",
    )
    setattr(im, "_operando_cmap_name", cmap)
    try:
        clim = blob.get("clim")
        if clim and len(clim) == 2:
            im.set_clim(float(clim[0]), float(clim[1]))
    except Exception:
        pass
    if len(row_labels) != Zm.shape[0]:
        row_labels = [str(i) for i in range(Zm.shape[0])]
    bind_dqdv_2d_contour_figure(
        cfig, cax, im, v_lo, v_hi, row_labels,
        zlab=str(blob.get("zlabel") or "dQ/dV"),
        nx=int(blob.get("nx", 320)),
    )
    cbar_ax = cfig.add_axes((0.0, 0.0, 0.01, 0.01))

    class _MockColorbar:
        def __init__(self, cax, im_ref):
            self.ax = cax
            self._im = im_ref

        def set_label(self, label):
            cax._colorbar_label = label

        def update_normal(self, im_ref):
            pass

    cbar = _MockColorbar(cbar_ax, im)
    cbar_ax._colorbar_label = zlab
    try:
        font_cfg = blob.get("font", {}) or {}
        fam = font_cfg.get("family") or font_cfg.get("chain")
        if fam:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = list(fam) if isinstance(fam, (list, tuple)) else [str(fam)]
        if font_cfg.get("size") is not None:
            plt.rcParams["font.size"] = float(font_cfg["size"])
        if font_cfg.get("mathtext_fontset"):
            plt.rcParams["mathtext.fontset"] = str(font_cfg["mathtext_fontset"])
    except Exception:
        pass
    try:
        axis_cfg = blob.get("axis", {})
        if axis_cfg.get("xlabel") is not None:
            cax.set_xlabel(str(axis_cfg.get("xlabel") or ""))
        if axis_cfg.get("ylabel") is not None:
            cax.set_ylabel(str(axis_cfg.get("ylabel") or ""))
        cax.xaxis.label.set_visible(bool(axis_cfg.get("xlabel_visible", True)))
        cax.yaxis.label.set_visible(bool(axis_cfg.get("ylabel_visible", True)))
        if axis_cfg.get("x_labelpad") is not None:
            cax.xaxis.labelpad = float(axis_cfg["x_labelpad"])
        if axis_cfg.get("y_labelpad") is not None:
            cax.yaxis.labelpad = float(axis_cfg["y_labelpad"])
    except Exception:
        pass
    try:
        # Visibility / widths first (tick_params below would wipe colors if applied after).
        for name, spec in (blob.get("spines", {}) or {}).items():
            sp = cax.spines.get(name)
            if sp is None or not isinstance(spec, dict):
                continue
            if spec.get("linewidth") is not None:
                sp.set_linewidth(float(spec["linewidth"]))
            if spec.get("visible") is not None:
                sp.set_visible(bool(spec["visible"]))
    except Exception:
        pass
    try:
        tick_cfg = blob.get("ticks", {}) or {}
        widths = tick_cfg.get("widths", {}) or {}
        if widths.get("x_major") is not None:
            cax.tick_params(axis="x", which="major", width=float(widths["x_major"]))
        if widths.get("x_minor") is not None:
            cax.tick_params(axis="x", which="minor", width=float(widths["x_minor"]))
        if widths.get("y_major") is not None:
            cax.tick_params(axis="y", which="major", width=float(widths["y_major"]))
        if widths.get("y_minor") is not None:
            cax.tick_params(axis="y", which="minor", width=float(widths["y_minor"]))
        lengths = tick_cfg.get("lengths", {}) or {}
        major_length = lengths.get("x_major")
        if major_length is None:
            major_length = lengths.get("y_major")
        if major_length is not None:
            cax.tick_params(axis="both", which="major", length=float(major_length))
        minor_length = lengths.get("x_minor")
        if minor_length is None:
            minor_length = lengths.get("y_minor")
        if minor_length is not None:
            cax.tick_params(axis="both", which="minor", length=float(minor_length))
        direction = tick_cfg.get("direction")
        if direction:
            cax.tick_params(axis="both", which="both", direction=direction)
            cfig._tick_direction = direction
        restore_axes_tick_locators(cax, tick_cfg.get("locator_state"), ("x", "y"))
    except Exception:
        pass
    try:
        # Spine/tick/label colors AFTER tick_params, then finalize for p/i/s/b stability.
        from ...ui import finalize_spine_colors

        for name, spec in (blob.get("spines", {}) or {}).items():
            if not isinstance(spec, dict) or spec.get("color") is None:
                continue
            if cax.spines.get(name) is None:
                continue
            set_spine_side_color(cax, name, spec["color"], fig=cfig)
        finalize_spine_colors(cfig, cax, draw=False)
    except Exception:
        pass
    try:
        cb_cfg = blob.get("colorbar", {}) or {}
        cbar_ax._colorbar_label = str(cb_cfg.get("label") or zlab)
        cfig._colorbar_label_mode = cb_cfg.get("mode", "highlow")
        cbar_ax.set_visible(bool(cb_cfg.get("visible", True)))
    except Exception:
        pass
    try:
        font_cfg = dict(blob.get("font") or {})
        if "weight" not in font_cfg:
            font_cfg["weight"] = "normal"
        if "highlight" not in font_cfg:
            font_cfg["highlight"] = False
        apply_session_font_cfg(
            cfig,
            font_cfg,
            cax,
            artists=collect_operando_font_artists(cfig, cax, cbar=cbar),
        )
    except Exception:
        pass
    try:
        xlim = blob.get("xlim")
        ylim = blob.get("ylim")
        if xlim and len(xlim) == 2:
            cax.set_xlim(float(xlim[0]), float(xlim[1]))
        if ylim and len(ylim) == 2:
            cax.set_ylim(float(ylim[0]), float(ylim[1]))
    except Exception:
        pass
    try:
        cfig.canvas.draw_idle()
    except Exception:
        pass
    return (cfig, cax, im, cbar)




__all__ = [
    "_dqdv_build_butterfly_contour_stack",
    "_dqdv_butterfly_xz_from_line",
    "_dqdv_2d_ensure_center_lines",
    "_dqdv_2d_ensure_voltage_formatter",
    "_dqdv_2d_restore_custom_labels",
    "_dqdv_2d_row_tick_indices",
    "_dqdv_2d_set_row_y_ticks",
    "_dqdv_2d_style_axes",
    "_dqdv_2d_voltage_tick_formatter",
    "_dqdv_interp_unique_sorted_x",
    "bind_dqdv_2d_contour_figure",
    "build_dqdv_2d_snapshot",
    "reapply_dqdv_2d_contour_axes",
    "restore_dqdv_2d_companion_figure",
    "update_dqdv_2d_potential_window",
]
