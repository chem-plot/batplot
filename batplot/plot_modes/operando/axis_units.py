"""Operando Options ``u``: XRD axis unit convert (2θ ↔ Q ↔ d).

XRD contour data only — not PDF (r), user-defined axes, or dQ/dV 2D.
Reuses conversion math from ``xy.axis_units``; remeshes the imshow array
because Bragg transforms are nonlinear (endpoint-only extent remap would warp).
"""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np  # type: ignore[import]

from ..xy.axis_units import (
    AXIS_MODES,
    convert_x_array,
    default_xlabel,
    resolve_wavelength,
)

XRD_AXIS_MODES = ("2theta", "Q", "d")


def infer_operando_axis_mode_from_xlabel(xlabel: Optional[str]) -> Optional[str]:
    """Best-effort axis mode from an xlabel (for old sessions lacking axis_mode)."""
    raw = xlabel or ""
    xl = raw.lower()
    if not xl.strip():
        return None
    if (
        "2θ" in raw
        or "2theta" in xl
        or "2th" in xl
        or r"$2\theta$" in raw
        or re.search(r"two[\s_\-]*theta", xl) is not None
    ):
        return "2theta"
    # Non-XRD operando first (Energy / PDF-r / user) so Å⁻¹ heuristics cannot steal them
    if "energy" in xl or "ev" in xl or "kev" in xl:
        return "energy"
    if "user" in xl:
        return "user_defined"
    if (
        xl.startswith("r ")
        or xl.startswith("r (")
        or xl.startswith("r($")
        or xl.strip().startswith("r (")
        or "radial" in xl
    ):
        return "r"
    if "q (" in xl or "q ($" in xl or xl.strip() == "q" or xl.startswith("q "):
        return "Q"
    if xl.strip().startswith("d ") or xl.startswith("d (") or "d ($" in xl:
        return "d"
    return None


def ensure_operando_axis_mode(fig: Any, ax: Any = None) -> Optional[str]:
    """Ensure ``fig._operando_axis_mode`` when it can be known; never invent 2θ.

    Old sessions omit ``axis_mode``. Infer from the live xlabel when possible.
    If still unknown, leave the attribute unset (return ``None``) so XANES/PDF
    sessions are not mis-tagged as 2θ.
    """
    mode = getattr(fig, "_operando_axis_mode", None)
    if mode in XRD_AXIS_MODES or mode in ("r", "user_defined", "energy"):
        return str(mode)
    inferred = None
    if ax is not None:
        try:
            inferred = infer_operando_axis_mode_from_xlabel(ax.get_xlabel())
        except Exception:
            inferred = None
    if inferred is None:
        return None
    try:
        fig._operando_axis_mode = inferred  # type: ignore[attr-defined]
    except Exception:
        pass
    return inferred


def is_operando_xrd_axis(fig: Any, ax: Any = None) -> bool:
    """True when Options ``u`` is allowed for this figure."""
    if getattr(fig, "_is_dqdv_2d_contour", False):
        return False
    mode = getattr(fig, "_operando_axis_mode", None)
    if mode is None:
        if ax is None:
            try:
                axes = getattr(fig, "axes", None) or []
                ax = axes[0] if axes else None
            except Exception:
                ax = None
        if ax is not None:
            mode = ensure_operando_axis_mode(fig, ax)
    if mode is None:
        # Unknown (old session, blank xlabel): do not offer ``u``
        return False
    return mode in XRD_AXIS_MODES


def get_operando_axis_mode(fig: Any, ax: Any = None) -> str:
    mode = getattr(fig, "_operando_axis_mode", None)
    if mode in XRD_AXIS_MODES:
        return str(mode)
    if mode in ("r", "user_defined", "energy"):
        return str(mode)
    ensured = ensure_operando_axis_mode(fig, ax)
    if ensured:
        return str(ensured)
    return "unknown"


def set_operando_axis_mode(fig: Any, mode: str, *, wavelength: Optional[float] = None) -> None:
    if mode in XRD_AXIS_MODES or mode in ("r", "user_defined", "energy"):
        fig._operando_axis_mode = mode  # type: ignore[attr-defined]
    if wavelength is not None:
        try:
            fig._operando_wl = float(wavelength)  # type: ignore[attr-defined]
        except (TypeError, ValueError):
            pass


def _image_array(im: Any) -> np.ndarray:
    arr = im.get_array()
    if hasattr(arr, "filled"):
        return np.ma.filled(arr, np.nan).astype(float, copy=True)
    return np.asarray(arr, dtype=float).copy()


def remesh_operando_imshow(
    im: Any,
    *,
    frm: str,
    to: str,
    wl: Optional[float],
) -> Tuple[np.ndarray, Tuple[float, float, float, float]]:
    """Convert column x-domain of an operando imshow; return (Z_new, extent).

    Reconstructs the current column centers from ``extent``, converts them,
    sorts into ascending target units, and reinterpolates each row onto a
    uniform grid with the same column count.
    """
    if frm == to:
        Z = _image_array(im)
        ext = tuple(float(v) for v in im.get_extent())
        return Z, (ext[0], ext[1], ext[2], ext[3])

    needs_wl = ("2theta" in (frm, to))
    if needs_wl and wl is None:
        raise ValueError("Wavelength (A) is required for conversions involving 2theta")

    Z = _image_array(im)
    if Z.ndim != 2 or Z.size == 0:
        raise ValueError("Operando image has no 2D data to convert")
    n_rows, n_cols = Z.shape
    if n_cols < 2:
        raise ValueError("Need at least 2 x-columns to convert axis")

    x0, x1, y0, y1 = (float(v) for v in im.get_extent())
    x_old = np.linspace(x0, x1, n_cols)
    # Bragg-clamp like XY so Q→2θ over-range stays finite (no mass column drop)
    x_new = convert_x_array(
        x_old, frm=frm, to=to, wl=wl, clip_bragg=(to == "2theta"),
    )
    order = np.argsort(x_new)
    x_sorted = np.asarray(x_new[order], dtype=float)
    Z_sorted = Z[:, order]
    ok = np.isfinite(x_sorted)
    if int(np.count_nonzero(ok)) < 2:
        raise ValueError("Conversion produced too few finite x values")
    x_sorted = x_sorted[ok]
    Z_sorted = Z_sorted[:, ok]
    # Drop duplicate x after sort (rare but breaks interp)
    if x_sorted.size >= 2:
        uniq = np.concatenate([[True], np.diff(x_sorted) > 1e-15])
        x_sorted = x_sorted[uniq]
        Z_sorted = Z_sorted[:, uniq]
    if x_sorted.size < 2:
        raise ValueError("Conversion collapsed to a single x value")

    x_lo = float(x_sorted[0])
    x_hi = float(x_sorted[-1])
    if abs(x_hi - x_lo) < 1e-30:
        raise ValueError("Converted x-range is empty")
    x_grid = np.linspace(x_lo, x_hi, n_cols)
    Z_out = np.empty((n_rows, n_cols), dtype=float)
    for i in range(n_rows):
        Z_out[i, :] = np.interp(x_grid, x_sorted, Z_sorted[i, :], left=np.nan, right=np.nan)
    return Z_out, (x_lo, x_hi, float(y0), float(y1))


def apply_operando_axis_unit_conversion(
    *,
    fig: Any,
    ax: Any,
    im: Any,
    frm: str,
    to: str,
    wl: Optional[float],
    update_xlabel: bool = True,
    redraw_cif: bool = True,
) -> None:
    """Convert operando contour X from ``frm`` to ``to`` (mutates imshow + CIF display meta)."""
    if frm == to:
        return
    if frm not in XRD_AXIS_MODES or to not in XRD_AXIS_MODES:
        raise ValueError(f"Unsupported operando axis conversion {frm} -> {to}")

    # Lock pre-remesh Z/extent as never-shrink masters before mutating imshow.
    try:
        from ..common.session_data_guarantee import install_operando_array_master

        cur = np.array(im.get_array(), copy=True)
        install_operando_array_master(fig, cur)
        if getattr(fig, "_operando_extent_master", None) is None and hasattr(im, "get_extent"):
            fig._operando_extent_master = tuple(map(float, im.get_extent()))
        if getattr(fig, "_operando_axis_mode_master", None) is None:
            fig._operando_axis_mode_master = str(frm)
    except Exception:
        pass
    Z_out, extent = remesh_operando_imshow(im, frm=frm, to=to, wl=wl)
    im.set_data(Z_out)
    im.set_extent(extent)
    try:
        ax.set_xlim(extent[0], extent[1])
    except Exception:
        pass

    # CIF peaks stay in Q; store λ on entries only while displaying 2θ
    series = getattr(ax, "_operando_cif_tick_series", None)
    if isinstance(series, list):
        for i, entry in enumerate(list(series)):
            try:
                lab, fname, peaksQ, _wl_e, qmax, col = entry
                wl_e = float(wl) if (to == "2theta" and wl is not None) else None
                series[i] = (lab, fname, peaksQ, wl_e, qmax, col)
            except Exception:
                continue

    set_operando_axis_mode(fig, to, wavelength=wl)

    if update_xlabel:
        try:
            lab = default_xlabel(to)
            ax.set_xlabel(lab)
            ax._stored_xlabel = lab  # type: ignore[attr-defined]
            try:
                custom = getattr(ax, "_custom_labels", None)
                if isinstance(custom, dict):
                    custom["x"] = lab
            except Exception:
                pass
            top = getattr(ax, "_top_xlabel_artist", None)
            if top is not None:
                try:
                    top.set_text(lab)
                except Exception:
                    pass
        except Exception:
            pass

    if redraw_cif:
        try:
            from .plot import _draw_operando_cif_ticks

            cif_series = list(getattr(ax, "_operando_cif_tick_series", None) or [])
            cif_hkl = dict(getattr(ax, "_operando_cif_hkl_label_map", None) or {})
            _draw_operando_cif_ticks(
                ax,
                fig,
                cif_series,
                cif_hkl,
                axis_mode=to,
                wl=wl,
                show_hkl=bool(getattr(fig, "_operando_cif_show_hkl", False)),
                show_titles=bool(getattr(fig, "_operando_cif_show_titles", True)),
                placement=str(getattr(fig, "_operando_cif_placement", "below")),
                y_positions=list(getattr(fig, "_operando_cif_y_positions", None) or []),
            )
        except Exception:
            pass
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def resolve_operando_wavelength(
    *,
    fig: Any,
    cif_series: Optional[Sequence] = None,
) -> Optional[float]:
    """Best-effort λ (Å) for operando Bragg conversions."""
    for candidate in (getattr(fig, "_operando_wl", None),):
        if candidate is not None:
            try:
                return float(candidate)
            except (TypeError, ValueError):
                pass
    # Reuse XY helper shape with a tiny args stub
    class _Args:
        wl = None

    return resolve_wavelength(
        fig=fig,
        args=_Args(),
        cif_series=cif_series,
        file_wavelength_info=None,
    )


def run_operando_axis_units_menu(
    *,
    fig: Any,
    ax: Any,
    im: Any,
    push_state: Callable[[str], Any],
    pop_undo: Optional[Callable[[], Any]] = None,
    _safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> Optional[str]:
    """Options ``u`` for operando: convert XRD axis among 2θ / Q / d.

    Returns the new mode string when conversion succeeds, else ``None``.
    """
    if getattr(fig, "_is_dqdv_2d_contour", False):
        print("Axis unit convert is for XRD data only (not dQ/dV 2D).")
        return None
    ensure_operando_axis_mode(fig, ax)
    current = get_operando_axis_mode(fig, ax)
    if current not in XRD_AXIS_MODES:
        print("Axis unit convert is for XRD data only (2θ / Q / d).")
        return None

    while True:
        current = get_operando_axis_mode(fig, ax)
        print("\n\033[1mAxis units (XRD only):\033[0m")
        print("  Convert XRD axis among 2θ ↔ Q ↔ d (needs λ for 2θ).")
        print(f"  Current: {current}")
        print("  " + colorize_menu("2: 2θ (deg)"))
        print("  " + colorize_menu("q: Q (Å⁻¹)"))
        print("  " + colorize_menu("d: d (Å)"))
        print("  " + colorize_menu("b: back"))
        choice = _safe_input(colorize_prompt("Axis units XRD (2/q/d/b): ")).strip().lower()
        if not choice or choice in ("b", "back"):
            return None
        target_map = {
            "2": "2theta", "2theta": "2theta", "2th": "2theta", "t": "2theta",
            "q": "Q", "d": "d",
        }
        to = target_map.get(choice)
        if to is None:
            print("Unknown option.")
            continue
        if to == current:
            print(f"Already in {to}.")
            continue

        cif_series = getattr(ax, "_operando_cif_tick_series", None)
        wl = resolve_operando_wavelength(fig=fig, cif_series=cif_series)
        needs_wl = ("2theta" in (current, to))
        if needs_wl and wl is None:
            wl_in = _safe_input(colorize_prompt(
                "Wavelength Å (required for 2θ conversion, q=cancel): "
            )).strip()
            if not wl_in or wl_in.lower() == "q":
                print("Canceled.")
                continue
            try:
                wl = float(wl_in)
            except ValueError:
                print("Invalid wavelength.")
                continue
            if not (wl > 0) or wl != wl:
                print("Wavelength must be > 0.")
                continue
        elif needs_wl and wl is not None:
            wl_in = _safe_input(colorize_prompt(
                f"Wavelength Å [Enter={wl:.6g}, q=cancel]: "
            )).strip()
            if wl_in.lower() == "q":
                print("Canceled.")
                continue
            if wl_in:
                try:
                    wl = float(wl_in)
                except ValueError:
                    print("Invalid wavelength; keeping previous.")
                else:
                    if not (wl > 0) or wl != wl:
                        print("Wavelength must be > 0; keeping previous.")
                        continue

        if needs_wl and (wl is None or not (wl > 0) or wl != wl):
            print("Valid wavelength (> 0) required for 2θ conversion.")
            continue

        pushed = False
        try:
            pushed = bool(push_state("axis-units"))
        except Exception:
            pushed = False
        if not pushed:
            print("Could not snapshot state for undo; conversion canceled.")
            return None
        try:
            apply_operando_axis_unit_conversion(
                fig=fig,
                ax=ax,
                im=im,
                frm=current,
                to=to,
                wl=wl,
                update_xlabel=True,
                redraw_cif=True,
            )
            print(
                f"Axis converted: {current} → {to}"
                + (f" (λ={wl:.6g} Å)" if wl and needs_wl else "")
            )
            return to
        except Exception as exc:
            if pushed and pop_undo is not None:
                try:
                    pop_undo()
                except Exception:
                    pass
            print(f"Could not convert axis: {exc}")
            return None


__all__ = [
    "XRD_AXIS_MODES",
    "apply_operando_axis_unit_conversion",
    "ensure_operando_axis_mode",
    "get_operando_axis_mode",
    "infer_operando_axis_mode_from_xlabel",
    "is_operando_xrd_axis",
    "remesh_operando_imshow",
    "resolve_operando_wavelength",
    "run_operando_axis_units_menu",
    "set_operando_axis_mode",
]
