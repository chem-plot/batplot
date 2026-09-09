"""Interactive XY axis unit conversion (``u``): 2θ ↔ Q ↔ d.

XRD data only (powder diffraction). Not for PDF (.gr), XAS (.nor / .chik /
.chir), or other non-XRD axes.

Keeps XRD data arrays, axis labels/limits, and CIF tick *display* in sync.
CIF peak storage stays in Q (existing schema); only the plotted domain and
per-entry wavelength metadata change with the axis mode.
"""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional, Sequence, Tuple

import numpy as np  # type: ignore[import]


AXIS_MODES = ("2theta", "Q", "d")


def infer_xy_axis_mode_from_xlabel(xlabel: Optional[str]) -> Optional[str]:
    """Best-effort axis mode from xlabel (old sessions with axis_mode unknown)."""
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
    if "energy" in xl or "ev" in xl or "kev" in xl:
        return "energy"
    if (
        xl.startswith("r ")
        or xl.startswith("r (")
        or xl.startswith("r($")
        or "radial" in xl
    ):
        return "r"
    if xl.startswith("k ") or xl.startswith("k (") or xl.startswith("k($"):
        return "k"
    if "q (" in xl or "q ($" in xl or xl.strip() == "q" or xl.startswith("q "):
        return "Q"
    if xl.strip().startswith("d ") or xl.startswith("d (") or "d ($" in xl:
        return "d"
    return None


def get_xy_axis_mode(
    fig: Any,
    *,
    use_Q: bool = False,
    use_r: bool = False,
    use_E: bool = False,
    use_k: bool = False,
    use_rft: bool = False,
    use_2th: bool = False,
    xaxis: Optional[str] = None,
    ax: Any = None,
) -> str:
    """Return current axis mode (``2theta`` / ``Q`` / ``d`` / ``other`` / ``unknown``).

    Never invents ``2theta`` for blank/unknown old sessions — that wrongly
    enabled Options ``u`` on non-XRD plots (e.g. Fe_edge with empty xlabel).
    """
    stored = getattr(fig, "_xy_axis_mode", None)
    if stored in AXIS_MODES:
        return str(stored)
    # Prefer explicit xaxis hint (args.xaxis) so ``d`` survives if fig attr is missing
    xa = xaxis
    if xa is None:
        try:
            xa = getattr(fig, "_xy_xaxis_hint", None)
        except Exception:
            xa = None
    if xa is not None:
        s = str(xa).strip()
        if s.upper() == "Q":
            return "Q"
        sl = s.lower()
        if sl in ("2theta", "2th", "tth", "two_theta"):
            return "2theta"
        if sl == "d":
            return "d"
        if sl in ("r", "energy", "k", "rft"):
            return "other"
    if use_Q:
        return "Q"
    if use_2th:
        return "2theta"
    if use_r or use_E or use_k or use_rft:
        return "other"
    # Old pkl / unset: infer from live xlabel when possible
    if ax is None and fig is not None:
        try:
            axes = getattr(fig, "axes", None) or []
            ax = axes[0] if axes else None
        except Exception:
            ax = None
    if ax is not None:
        try:
            inferred = infer_xy_axis_mode_from_xlabel(ax.get_xlabel())
        except Exception:
            inferred = None
        if inferred in AXIS_MODES:
            return inferred
        if inferred in ("r", "energy", "k", "rft"):
            return "other"
    return "unknown"


def set_xy_axis_mode(fig: Any, mode: str, *, wavelength: Optional[float] = None) -> None:
    """Persist axis mode (and optional λ) on the figure for session/style/CIF."""
    if mode in AXIS_MODES:
        fig._xy_axis_mode = mode  # type: ignore[attr-defined]
        try:
            fig._xy_xaxis_hint = mode  # type: ignore[attr-defined]
        except Exception:
            pass
    if wavelength is not None:
        try:
            fig._xy_wavelength = float(wavelength)  # type: ignore[attr-defined]
        except (TypeError, ValueError):
            pass


def twotheta_to_Q(x_2th: np.ndarray, wl: float) -> np.ndarray:
    theta = np.radians(np.asarray(x_2th, dtype=float) / 2.0)
    return (4.0 * np.pi * np.sin(theta)) / float(wl)


def Q_to_twotheta(x_Q: np.ndarray, wl: float) -> np.ndarray:
    q = np.asarray(x_Q, dtype=float)
    s = np.clip(q * float(wl) / (4.0 * np.pi), -1.0, 1.0)
    # Mark physically impossible |sin θ|==1 edge as nan when input was out of range
    out = 2.0 * np.degrees(np.arcsin(s))
    bad = np.abs(q * float(wl) / (4.0 * np.pi)) > 1.0 + 1e-12
    if np.any(bad):
        out = np.array(out, dtype=float, copy=True)
        out[bad] = np.nan
    return out


def Q_to_d(x_Q: np.ndarray) -> np.ndarray:
    q = np.asarray(x_Q, dtype=float)
    out = np.full_like(q, np.nan, dtype=float)
    mask = np.abs(q) > 1e-30
    out[mask] = (2.0 * np.pi) / q[mask]
    return out


def d_to_Q(x_d: np.ndarray) -> np.ndarray:
    d = np.asarray(x_d, dtype=float)
    out = np.full_like(d, np.nan, dtype=float)
    mask = np.abs(d) > 1e-30
    out[mask] = (2.0 * np.pi) / d[mask]
    return out


def format_xrd_crosshair_x_lines(
    x: float,
    *,
    axis_mode: str,
    wavelength: Optional[float] = None,
) -> List[str]:
    """Build Bragg crosshair lines for the current x (primary unit first).

    For XRD modes ``2theta`` / ``Q`` / ``d``:
    - With a positive ``wavelength`` (Å): include **2θ, Q, and d** together.
    - Without λ: keep Q↔d (or 2θ alone) — backward compatible with older
      sessions that never stored λ.

    Returns a list of text lines (no trailing y-value); callers append y/z.
    """
    mode = str(axis_mode or "").strip()
    if mode.lower() == "q":
        mode = "Q"
    try:
        xv = float(x)
    except (TypeError, ValueError):
        return [f"x={x}"]

    wl: Optional[float] = None
    if wavelength is not None:
        try:
            cand = float(wavelength)
            if np.isfinite(cand) and cand > 0.0:
                wl = cand
        except (TypeError, ValueError):
            wl = None

    def _q_line(q: float) -> str:
        return f"Q={q:.6g}"

    def _d_line(d: float) -> str:
        if not np.isfinite(d):
            return "d=∞"
        return f"d={d:.6g} Å"

    def _tth_line(tth: float) -> str:
        if not np.isfinite(tth):
            return "2θ=n/a"
        return f"2θ={tth:.6g}°"

    def _tth_from_q(q: float) -> float:
        assert wl is not None
        return float(Q_to_twotheta(np.asarray([q], dtype=float), wl)[0])

    def _q_from_tth(tth: float) -> float:
        assert wl is not None
        return float(twotheta_to_Q(np.asarray([tth], dtype=float), wl)[0])

    if mode == "Q":
        q = xv
        lines = [_q_line(q)]
        if wl is not None:
            lines.append(_tth_line(_tth_from_q(q)))
        if abs(q) > 1e-30 and np.isfinite(q):
            lines.append(_d_line(float(2.0 * np.pi / q)))
        else:
            lines.append("d=∞")
        return lines

    if mode == "d":
        d = xv
        lines = [_d_line(d) if np.isfinite(d) else "d=n/a"]
        if abs(d) > 1e-30 and np.isfinite(d):
            q = float(2.0 * np.pi / d)
            lines.append(_q_line(q))
            if wl is not None:
                lines.append(_tth_line(_tth_from_q(q)))
        else:
            lines.append("Q=∞")
        return lines

    if mode == "2theta":
        tth = xv
        lines = [_tth_line(tth)]
        if wl is not None:
            q = _q_from_tth(tth)
            lines.append(_q_line(q))
            if abs(q) > 1e-30 and np.isfinite(q):
                lines.append(_d_line(float(2.0 * np.pi / q)))
            else:
                lines.append("d=∞")
        return lines

    return [f"x={xv:.6g}"]


def convert_x_array(
    x: np.ndarray,
    *,
    frm: str,
    to: str,
    wl: Optional[float],
    clip_bragg: bool = False,
) -> np.ndarray:
    """Convert one x array between ``2theta`` / ``Q`` / ``d``.

    When ``clip_bragg`` is True and the target is 2θ, Q is clipped to the
    physical Bragg limit ``4π/λ`` so values beyond |sin θ|≤1 stay finite
    (needed for interactive ``u`` limits/data).
    """
    if frm == to:
        return np.asarray(x, dtype=float).copy()
    x0 = np.asarray(x, dtype=float)
    # Normalize to Q first
    if frm == "Q":
        q = x0
    elif frm == "2theta":
        if wl is None:
            raise ValueError("Wavelength required for 2theta -> Q/d conversion")
        q = twotheta_to_Q(x0, wl)
    elif frm == "d":
        q = d_to_Q(x0)
    else:
        raise ValueError(f"Unsupported source axis mode: {frm}")
    # Q → target
    if to == "Q":
        return np.asarray(q, dtype=float)
    if to == "2theta":
        if wl is None:
            raise ValueError("Wavelength required for Q/d -> 2theta conversion")
        q_out = np.asarray(q, dtype=float)
        if clip_bragg:
            qmax = (4.0 * np.pi / float(wl)) * (1.0 - 1e-9)
            q_out = np.clip(np.where(np.isfinite(q_out), q_out, 0.0), -qmax, qmax)
        return Q_to_twotheta(q_out, wl)
    if to == "d":
        return Q_to_d(q)
    raise ValueError(f"Unsupported target axis mode: {to}")


def peaks_Q_to_domain(
    peaksQ: Sequence[float],
    axis_mode: str,
    wl: Optional[float] = None,
) -> List[float]:
    """Map stored CIF peaks (Q) into the current plot domain.

    Peaks are always stored as reciprocal-space magnitude
    ``Q = |G| = 2π/d = 4π sinθ / λ``. Unknown / non-XRD modes return no
    positions (never invent a Q domain — that misplaces ticks on 2θ axes).
    """
    if not peaksQ:
        return []
    mode = str(axis_mode or "")
    if mode == "2theta":
        if wl is None:
            return []
        arr = Q_to_twotheta(np.asarray(peaksQ, dtype=float), float(wl))
        return [float(v) for v in arr if np.isfinite(v)]
    if mode == "d":
        arr = Q_to_d(np.asarray(peaksQ, dtype=float))
        return [float(v) for v in arr if np.isfinite(v)]
    if mode == "Q":
        return [float(v) for v in peaksQ if v is not None and np.isfinite(float(v))]
    return []


def domain_peak_to_Q(p: float, axis_mode: str, wl: Optional[float] = None) -> Optional[float]:
    """Inverse of :func:`peaks_Q_to_domain` for a single tick position (hkl lookup)."""
    try:
        x = float(p)
    except (TypeError, ValueError):
        return None
    mode = str(axis_mode or "")
    if mode == "2theta":
        if wl is None:
            return None
        theta = np.radians(x / 2.0)
        return float(4.0 * np.pi * np.sin(theta) / float(wl))
    if mode == "d":
        if abs(x) <= 1e-30:
            return None
        return float((2.0 * np.pi) / x)
    if mode == "Q":
        return x
    return None


def xmax_domain_to_Q(
    xmax_domain: float,
    axis_mode: str,
    *,
    wl: Optional[float] = None,
    xlim: Optional[Tuple[float, float]] = None,
) -> float:
    """Map a domain xmax (or window) to a Q target for CIF peak extension."""
    mode = str(axis_mode or "")
    if mode == "2theta":
        if wl is None:
            # Degrees are not Q — never treat 2θ xmax as Qmax. Match legacy CIF
            # fallback (xmax*0.1) used when λ is unknown.
            try:
                return max(float(xmax_domain) * 0.1, 10.0)
            except (TypeError, ValueError):
                return 10.0
        theta_rad = np.radians(min(float(xmax_domain), 179.9) / 2.0)
        return float(4.0 * np.pi * np.sin(theta_rad) / float(wl))
    if mode == "d":
        # High-Q edge is the smaller positive d in the visible window.
        candidates: List[float] = []
        if xlim is not None:
            for v in xlim:
                try:
                    av = abs(float(v))
                    if av > 1e-30:
                        candidates.append(av)
                except (TypeError, ValueError):
                    pass
        try:
            av = abs(float(xmax_domain))
            if av > 1e-30:
                candidates.append(av)
        except (TypeError, ValueError):
            pass
        if not candidates:
            return 10.0
        return float((2.0 * np.pi) / min(candidates))
    if mode == "Q":
        return float(xmax_domain)
    # Unknown axis: safe enumeration floor (do not treat degrees as Q)
    return 10.0


CU_KA_ANGSTROM = 1.5406


def resolve_cif_draw_wavelength(
    *,
    fig: Any,
    args: Any = None,
    cif_series: Optional[Sequence] = None,
    file_wavelength_info: Optional[Sequence] = None,
    axis_mode: Optional[str] = None,
    allow_cu_ka_default: bool = True,
    warn: bool = True,
) -> Optional[float]:
    """λ (Å) for CIF tick placement on a 2θ axis.

    Prefer fig / ``--wl`` / ``file:wl`` / entry λ (same resolver as Options
    ``u``). Cu Kα (1.5406 Å) remains a last-resort BC default when lab XRD
    omitted λ — never prefer it over a known plot wavelength.
    """
    class _ArgsStub:
        wl = None

    wl = resolve_wavelength(
        fig=fig,
        args=args if args is not None else _ArgsStub(),
        cif_series=cif_series,
        file_wavelength_info=file_wavelength_info,
        axis_mode=axis_mode or "2theta",
    )
    if wl is not None:
        return float(wl)
    if not allow_cu_ka_default:
        return None
    if warn and fig is not None and not getattr(fig, "_cif_cu_ka_warned", False):
        try:
            print(
                "Note: CIF 2θ tick positions use default λ=1.5406 Å (Cu Kα). "
                "Pass --wl or file:wl if the plot uses a different wavelength."
            )
            fig._cif_cu_ka_warned = True  # type: ignore[attr-defined]
        except Exception:
            pass
    return float(CU_KA_ANGSTROM)


def default_xlabel(mode: str) -> str:
    if mode == "Q":
        return r"Q ($\mathrm{\AA}^{-1}$)"
    if mode == "d":
        return r"d ($\mathrm{\AA}$)"
    if mode == "2theta":
        return r"$2\theta$ (deg)"
    return "X"


def resolve_wavelength(
    *,
    fig: Any,
    args: Any,
    cif_series: Optional[Sequence] = None,
    file_wavelength_info: Optional[Sequence] = None,
    axis_mode: Optional[str] = None,
) -> Optional[float]:
    """Best-effort λ (Å) for Bragg conversions.

    Dual-wl ``file:λ1:λ2``: Q (and d) were built with λ1; dual-remapped 2θ
    display uses λ2. Prefer the λ that matches the current domain so Options
    ``u`` / crosshair stay Bragg-correct.
    """
    mode = axis_mode
    if mode is None and fig is not None:
        mode = getattr(fig, "_xy_axis_mode", None)
    dual_display = bool(getattr(fig, "_xy_dual_wl_display", False)) if fig is not None else False

    # Domain-aware dual-wl pick (before possibly-stale fig λ from older builds)
    if file_wavelength_info:
        try:
            info0 = file_wavelength_info[0] or {}
            orig = info0.get("original_wl")
            conv = info0.get("conversion_wl")
            if orig is not None and conv is not None:
                if mode in ("Q", "d"):
                    return float(orig)
                if mode == "2theta" and dual_display:
                    return float(conv)
        except (TypeError, ValueError):
            pass

    for candidate in (
        getattr(fig, "_xy_wavelength", None),
        getattr(args, "wl", None),
    ):
        if candidate is not None:
            try:
                return float(candidate)
            except (TypeError, ValueError):
                pass
    if file_wavelength_info:
        try:
            info0 = file_wavelength_info[0] or {}
            if mode in ("Q", "d"):
                keys = ("original_wl", "final_wl", "conversion_wl")
            elif mode == "2theta" and dual_display:
                keys = ("conversion_wl", "final_wl", "original_wl")
            else:
                # Single-wl or 2θ from Q convert: prefer λ used for 2θ↔Q (original)
                keys = ("original_wl", "final_wl", "conversion_wl")
            for key in keys:
                if info0.get(key) is not None:
                    return float(info0[key])
        except Exception:
            pass
    for entry in cif_series or []:
        try:
            if entry[3] is not None:
                return float(entry[3])
        except Exception:
            continue
    return None


def _convert_list_copy(
    lst: Optional[List[Any]], frm: str, to: str, wl: Optional[float],
    *,
    clip_bragg: bool = False,
) -> Optional[List[Any]]:
    """Convert every array; raise on first failure (no partial mutation)."""
    if not lst:
        return lst
    out: List[Any] = []
    for arr in lst:
        out.append(
            convert_x_array(
                np.asarray(arr), frm=frm, to=to, wl=wl, clip_bragg=clip_bragg,
            )
        )
    return out


def _converted_axis_limits(
    x0: float,
    x1: float,
    *,
    frm: str,
    to: str,
    wl: Optional[float],
) -> Optional[Tuple[float, float]]:
    """Convert an xlim pair; clamp via Bragg limit when targeting 2θ."""
    raw = convert_x_array(
        np.array([x0, x1], dtype=float), frm=frm, to=to, wl=wl, clip_bragg=True,
    )
    if np.all(np.isfinite(raw)):
        return float(min(raw)), float(max(raw))
    finite = raw[np.isfinite(raw)]
    if finite.size >= 1:
        v = float(finite[0])
        return (v, v) if finite.size == 1 else (float(min(finite)), float(max(finite)))
    return None


def apply_xy_axis_unit_conversion(
    *,
    fig: Any,
    ax: Any,
    frm: str,
    to: str,
    wl: Optional[float],
    x_data_list: List[Any],
    x_full_list: List[Any],
    y_data_list: List[Any],
    cif_series: Optional[List[Any]] = None,
    update_xlabel: bool = True,
) -> None:
    """Convert plotted x-domain from ``frm`` to ``to`` (mutates arrays in place)."""
    if frm == to:
        return
    needs_wl = ("2theta" in (frm, to))
    if needs_wl and wl is None:
        raise ValueError("Wavelength (A) is required for conversions involving 2theta")

    # Clip to Bragg when targeting 2θ so xlim/data stay finite (no Q leftovers)
    clip = to == "2theta"
    new_x = _convert_list_copy(x_data_list, frm, to, wl, clip_bragg=clip)
    new_full = _convert_list_copy(x_full_list, frm, to, wl, clip_bragg=clip)
    extra_new: dict = {}
    for attr in (
        "_original_x_data_list",
        "_full_processed_x_data_list",
        "_pre_derivative_x_data_list",
    ):
        arrs = getattr(fig, attr, None)
        if isinstance(arrs, list):
            extra_new[attr] = _convert_list_copy(arrs, frm, to, wl, clip_bragg=clip)

    if new_x is not None:
        for i, arr in enumerate(new_x):
            x_data_list[i] = arr
    if new_full is not None:
        for i, arr in enumerate(new_full):
            x_full_list[i] = arr
    for attr, arrs in extra_new.items():
        live = getattr(fig, attr, None)
        if isinstance(live, list) and arrs is not None:
            for i, arr in enumerate(arrs):
                live[i] = arr
    # Keep fig master full-X in the same units (Y intensities unchanged).
    try:
        from .full_data import install_master_full

        master_y = getattr(fig, "_xy_master_y_full", None)
        if new_full is not None and isinstance(master_y, list) and master_y:
            install_master_full(fig, x_full_list, master_y, force=True)
    except Exception:
        pass

    # Line x data (skip CIF tick artists — they are redrawn)
    cif_art = set(getattr(ax, "_cif_tick_art", None) or [])
    n_curves = len(x_data_list)
    lines_by_curve = getattr(fig, "_xy_lines_by_curve", None)
    if lines_by_curve:
        iterable = list(lines_by_curve)[:n_curves]
    else:
        iterable = [ln for ln in ax.lines if ln not in cif_art][:n_curves]
    for i, ln in enumerate(iterable):
        if ln is None or i >= len(x_data_list):
            continue
        try:
            y = ln.get_ydata()
            ln.set_data(np.asarray(x_data_list[i]), y)
        except Exception:
            pass

    # Axis limits (Bragg-clamp endpoints so mode flip never leaves Q units)
    try:
        x0, x1 = ax.get_xlim()
        new_lim = _converted_axis_limits(x0, x1, frm=frm, to=to, wl=wl)
        if new_lim is not None:
            ax.set_xlim(new_lim[0], new_lim[1])
            try:
                from .axis_range import _sync_xy_twin_xlim

                _sync_xy_twin_xlim(fig, ax)
            except Exception:
                pass
    except Exception:
        pass
    for attr in ("_norm_xlim",):
        try:
            lim = getattr(ax, attr, None)
            if lim is not None and len(lim) == 2:
                new_lim = _converted_axis_limits(
                    float(lim[0]), float(lim[1]), frm=frm, to=to, wl=wl
                )
                if new_lim is not None:
                    setattr(ax, attr, new_lim)
        except Exception:
            pass

    # CIF: peaks stay in Q; store λ on entries only while displaying 2θ
    if cif_series is not None:
        for i, entry in enumerate(list(cif_series)):
            try:
                lab, fname, peaksQ, _wl_e, qmax, col = entry
                wl_e = float(wl) if (to == "2theta" and wl is not None) else None
                cif_series[i] = (lab, fname, peaksQ, wl_e, qmax, col)
            except Exception:
                continue

    set_xy_axis_mode(fig, to, wavelength=wl)
    # Leaving dual-remapped 2θ (λ₂) domain — further Bragg math uses a single λ
    try:
        fig._xy_dual_wl_display = False  # type: ignore[attr-defined]
    except Exception:
        pass
    if update_xlabel:
        try:
            lab = default_xlabel(to)
            ax.set_xlabel(lab)
            # Keep spine-title restore (t menu) and top-x duplicate in sync
            ax._stored_xlabel = lab  # type: ignore[attr-defined]
            # Clear sticky override so top title cannot snap back to old units
            try:
                if hasattr(ax, "_top_xlabel_text_override"):
                    delattr(ax, "_top_xlabel_text_override")
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

    if hasattr(ax, "_cif_draw_func"):
        try:
            ax._cif_draw_func()
        except Exception:
            pass
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def run_axis_units_menu(
    *,
    fig: Any,
    ax: Any,
    args: Any,
    x_data_list: List[Any],
    x_full_list: List[Any],
    y_data_list: List[Any],
    use_Q: bool,
    use_r: bool,
    use_E: bool,
    use_k: bool,
    use_rft: bool,
    get_cif_series: Callable[[], Optional[List[Any]]],
    sync_fig_cif_tick_series: Callable[[], Any],
    file_wavelength_info: Optional[Sequence] = None,
    push_state: Callable[[str], Any],
    pop_undo: Optional[Callable[[], Any]] = None,
    set_use_Q: Optional[Callable[[bool], Any]] = None,
    use_2th: bool = False,
    set_use_2th: Optional[Callable[[bool], Any]] = None,
    _safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> Optional[str]:
    """Options ``u``: convert XRD axis among 2θ / Q / d (XRD data only).

    Returns the new mode string when conversion succeeds, else ``None``.
    Respects launch mode from ``--xaxis 2theta`` / ``--wl`` (via fig/args/use_2th).
    """
    if use_r or use_E or use_k or use_rft:
        print("Axis unit convert is for XRD data only (2θ / Q / d).")
        return None

    def _current_mode() -> str:
        return get_xy_axis_mode(
            fig,
            use_Q=use_Q,
            use_r=use_r,
            use_E=use_E,
            use_k=use_k,
            use_rft=use_rft,
            use_2th=bool(use_2th),
            xaxis=getattr(args, "xaxis", None),
            ax=ax,
        )

    current = _current_mode()
    if current not in AXIS_MODES:
        print("Axis unit convert is for XRD data only (2θ / Q / d).")
        return None

    while True:
        current = _current_mode()
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
        target_map = {"2": "2theta", "2theta": "2theta", "2th": "2theta", "t": "2theta",
                      "q": "Q", "d": "d"}
        to = target_map.get(choice)
        if to is None:
            print("Unknown option.")
            continue
        if to == current:
            print(f"Already in {to}.")
            continue

        cts = get_cif_series()
        wl = resolve_wavelength(
            fig=fig,
            args=args,
            cif_series=cts,
            file_wavelength_info=file_wavelength_info,
            axis_mode=current,
        )
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
            # Offer override but keep Enter = use current (--wl / session λ)
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
            live = cts if cts is not None else None
            apply_xy_axis_unit_conversion(
                fig=fig,
                ax=ax,
                frm=current,
                to=to,
                wl=wl,
                x_data_list=x_data_list,
                x_full_list=x_full_list,
                y_data_list=y_data_list,
                cif_series=live,
                update_xlabel=True,
            )
            sync_fig_cif_tick_series()
            if set_use_Q is not None:
                set_use_Q(to == "Q")
            if set_use_2th is not None:
                set_use_2th(to == "2theta")
            use_Q = to == "Q"
            use_2th = to == "2theta"
            # Keep args.xaxis in sync so session dump records the new mode
            try:
                setattr(args, "xaxis", to)
            except Exception:
                pass
            try:
                fig._xy_xaxis_hint = to  # type: ignore[attr-defined]
            except Exception:
                pass
            if wl is not None:
                try:
                    setattr(args, "wl", float(wl))
                except Exception:
                    pass
            print(f"Axis converted: {current} → {to}" + (f" (λ={wl:.6g} Å)" if wl and needs_wl else ""))
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
    "AXIS_MODES",
    "CU_KA_ANGSTROM",
    "Q_to_d",
    "Q_to_twotheta",
    "apply_xy_axis_unit_conversion",
    "convert_x_array",
    "d_to_Q",
    "default_xlabel",
    "domain_peak_to_Q",
    "format_xrd_crosshair_x_lines",
    "get_xy_axis_mode",
    "infer_xy_axis_mode_from_xlabel",
    "peaks_Q_to_domain",
    "resolve_cif_draw_wavelength",
    "resolve_wavelength",
    "run_axis_units_menu",
    "set_xy_axis_mode",
    "twotheta_to_Q",
    "xmax_domain_to_Q",
]
