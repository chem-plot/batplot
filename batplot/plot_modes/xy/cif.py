"""CIF ticks submenu (``cif``/``z``/``j``) for the XY (diffraction) menu.

Manages CIF phase tick overlays: hkl/title visibility, reordering, per-row
vertical shift, colors, visibility, and phase renaming. CIF state lives on the
batplot module and figure attributes, so the dispatcher injects ``_bp`` plus the
CIF bridge callbacks; mutations go through ``push_state`` for undo parity.
"""

from __future__ import annotations

import os
import sys
import sys as _sys_vis
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib import colors as mcolors  # type: ignore[import]

from ...utils import (
    finalize_axis_label_text,
    normalize_xy_cif_stack_y_offsets,
    print_label_math_help,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
)
from ...cif import (
    cif_reflection_positions,
    list_reflections_with_hkl,
    build_hkl_label_map_from_list,
    simulate_cif_pattern_Q,
)
from ...color_utils import (
    color_block,
    format_color_listing,
    ensure_colormap,
    get_colormap,
    manage_user_colors,
    prompt_screen_color,
    blank_means_back,
    resolve_color_token,
    _CUSTOM_CMAPS,
)
from ..common.palettes import (
    build_xy_palette_options,
    parse_index_ranges,
    resolve_palette_token,
    sample_colormap,
)


def _parse_xy_cif_path_token(entry: str) -> Tuple[str, Optional[float]]:
    """Parse ``path.cif`` or ``path.cif:1.54`` (Windows drive / ``\\\\?\\C:`` preserved)."""
    from ..common.sources import split_path_token

    fname, rest = split_path_token(entry)
    wl_file = None
    if rest:
        try:
            wl_file = float(rest[0])
        except ValueError:
            pass
    return fname, wl_file


def _xy_cif_qmax(
    ax: Any,
    series: List[Any],
    *,
    use_2th: bool,
    fig: Any = None,
) -> float:
    """Estimate Qmax for CIF peak enumeration from existing series or axis window.

    After Options ``u`` the plot may be in 2θ / Q / d; map the visible xmax
    into Q via ``xmax_domain_to_Q`` so d-axis add/extend is not treated as Q.
    """
    qmaxes: List[float] = []
    for entry in series:
        try:
            if isinstance(entry, (list, tuple)) and len(entry) > 4 and entry[4] is not None:
                qmaxes.append(float(entry[4]))
        except Exception:
            pass
    if qmaxes:
        return max(qmaxes)
    try:
        xmin, xmax = ax.get_xlim()
        try:
            from .axis_units import get_xy_axis_mode, xmax_domain_to_Q

            axis_mode = get_xy_axis_mode(fig) if fig is not None else None
            if axis_mode not in ("2theta", "Q", "d"):
                axis_mode = "2theta" if use_2th else "Q"
            wl = None
            if fig is not None:
                wl = getattr(fig, "_xy_wavelength", None)
            return max(
                float(
                    xmax_domain_to_Q(
                        float(xmax), axis_mode, wl=wl, xlim=(float(xmin), float(xmax)),
                    )
                ),
                10.0,
            )
        except Exception:
            pass
        if use_2th:
            # Legacy fallback: rough 2θ upper bound → Q scale.
            return max(float(xmax) * 0.1, 10.0)
        return max(abs(float(xmax)) * 1.1, 10.0)
    except Exception:
        pass
    return 10.0


def _xy_cif_next_color(color_index: int) -> Any:
    """Match multi-CIF coloring used at launch (tab10 reordered; first set black)."""
    if color_index <= 0:
        return "k"
    try:
        tab10_cmap = get_colormap("tab10")
        tab10 = tab10_cmap.colors if tab10_cmap is not None and hasattr(tab10_cmap, "colors") else None
        if not tab10:
            raise ValueError("tab10 unavailable")
        order = [0, 3, 6, 1, 4, 7, 2, 5, 8, 9]
        idx = order[color_index] if color_index < len(order) else color_index % len(tab10)
        return tab10[idx]
    except Exception:
        return "k"


def _resolve_live_xy_cif_series(_bp: Any, fig: Any) -> List[Any]:
    """Return the live list object used by menu/session/redraw (mutate in place)."""
    series = None
    if _bp is not None:
        series = getattr(_bp, "cif_tick_series", None)
    if series is None:
        series = getattr(fig, "_batplot_cif_tick_series", None)
    if series is None:
        series = []
    if _bp is not None:
        setattr(_bp, "cif_tick_series", series)
    try:
        fig._batplot_cif_tick_series = series
    except Exception:
        pass
    return series


def extend_xy_cif_series_for_xmax(
    fig: Any,
    ax: Any,
    xmax_domain: float,
    *,
    use_2th: bool = False,
    suspended: bool = False,
) -> bool:
    """Grow CIF peak lists when the X upper bound exceeds each set's simulated Qmax.

    Used by fresh plots, session reload, and interactive ``cif→a`` installs so
    expanding X after ``.pkl`` load still enumerates new reflections.
    Returns True if any set was extended (caller should redraw).
    """
    if suspended:
        return False
    series = getattr(fig, "_batplot_cif_tick_series", None)
    if not series:
        return False
    from .axis_units import get_xy_axis_mode, xmax_domain_to_Q

    axis_mode = get_xy_axis_mode(fig, use_2th=bool(use_2th), ax=ax)
    if axis_mode not in ("2theta", "Q", "d"):
        return False
    wl_any = None
    if axis_mode == "2theta":
        for entry in series:
            try:
                if entry[3] is not None:
                    wl_any = entry[3]
                    break
            except Exception:
                pass
        if wl_any is None:
            try:
                from .axis_units import resolve_cif_draw_wavelength
                wl_any = resolve_cif_draw_wavelength(
                    fig=fig, cif_series=series, axis_mode="2theta", warn=False,
                )
            except Exception:
                wl_any = getattr(fig, "_xy_wavelength", None)
    try:
        xlim_now = ax.get_xlim()
    except Exception:
        xlim_now = None
    updated = False
    for i, (lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(list(series)):
        wl_use = wl if wl is not None else wl_any
        try:
            Q_target = xmax_domain_to_Q(
                float(xmax_domain), axis_mode, wl=wl_use, xlim=xlim_now,
            )
        except Exception:
            continue
        try:
            qmax_f = float(qmax_sim) if qmax_sim is not None else 0.0
        except (TypeError, ValueError):
            qmax_f = 0.0
        if float(Q_target) <= qmax_f + 1e-6:
            continue
        new_Qmax = float(Q_target) + 0.25
        try:
            refl = cif_reflection_positions(
                fname,
                Qmax=new_Qmax,
                wavelength=(wl if (wl and axis_mode == "2theta") else None),
            )
            series[i] = (lab, fname, refl, wl, float(new_Qmax), color)
            updated = True
        except Exception as e:
            try:
                print(f"Warning: could not extend CIF peaks for {lab}: {e}")
            except Exception:
                pass
    if updated:
        try:
            fig._batplot_cif_tick_series = series
        except Exception:
            pass
    return updated


def ensure_xy_cif_draw_installed(
    fig: Any,
    ax: Any,
    *,
    use_2th: bool,
    cif_hkl_label_map: Optional[Dict[str, Any]] = None,
    y_data_list: Optional[List[Any]] = None,
) -> None:
    """Install a CIF redraw closure when the plot started without CLI CIF files."""
    # Always (re)install extend so session no-ops get replaced after cif→a.
    def _extend(xmax_domain):
        suspended = bool(getattr(fig, "_bp_cif_extend_suspended", False))
        try:
            _m = sys.modules.get("__main__")
            if _m is not None and hasattr(_m, "cif_extend_suspended"):
                suspended = bool(getattr(_m, "cif_extend_suspended", suspended))
        except Exception:
            pass
        if extend_xy_cif_series_for_xmax(
            fig, ax, float(xmax_domain), use_2th=bool(use_2th), suspended=suspended,
        ):
            draw = getattr(ax, "_cif_draw_func", None)
            if callable(draw):
                try:
                    draw()
                except Exception as exc:
                    print(f"Warning: CIF tick redraw failed: {exc}")

    ax._cif_extend_func = _extend
    if hasattr(ax, "_cif_draw_func") and callable(getattr(ax, "_cif_draw_func", None)):
        return

    # Keep a single live dict identity (no copy) so append/style/undo stay synced.
    hkl_map_ref: Dict[str, Any]
    existing = getattr(fig, "_batplot_cif_hkl_label_map", None)
    if isinstance(cif_hkl_label_map, dict):
        hkl_map_ref = cif_hkl_label_map
        if isinstance(existing, dict) and existing is not hkl_map_ref:
            hkl_map_ref.update(existing)
    elif isinstance(existing, dict):
        hkl_map_ref = existing
    else:
        hkl_map_ref = {}
    fig._batplot_cif_hkl_label_map = hkl_map_ref  # type: ignore[attr-defined]

    def _q_to_2theta(peaksQ, wl):
        if wl is None:
            return []
        out = []
        for q in peaksQ:
            s = q * wl / (4 * np.pi)
            if 0 <= s < 1:
                out.append(np.degrees(2 * np.arcsin(s)))
        return out

    def _ensure_wl(series):
        from .axis_units import resolve_cif_draw_wavelength
        return resolve_cif_draw_wavelength(
            fig=fig, cif_series=series, axis_mode="2theta",
        )

    def _clear_cif_art():
        for art in getattr(ax, "_cif_tick_art", []):
            try:
                art.remove()
            except Exception:
                pass
        ax._cif_tick_art = []
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _draw():
        series = getattr(fig, "_batplot_cif_tick_series", None) or []
        if not series:
            # Undo after first add must remove ticks (empty series).
            _clear_cif_art()
            return
        try:
            prev_xlim = ax.get_xlim()
            prev_ylim = ax.get_ylim()
            if not hasattr(ax, "_cif_initial_ylim"):
                ax._cif_initial_ylim = tuple(prev_ylim)
            fixed_ylim = ax._cif_initial_ylim
            fixed_yr = fixed_ylim[1] - fixed_ylim[0]
            if fixed_yr <= 0:
                fixed_yr = 1.0
            show_titles_local = True
            try:
                # Prefer figure attr (batch / reopened); __main__ is process-global.
                if hasattr(fig, "_bp_show_cif_titles"):
                    show_titles_local = bool(getattr(fig, "_bp_show_cif_titles", True))
                else:
                    _bp_module = sys.modules.get("__main__")
                    if _bp_module is not None and hasattr(_bp_module, "show_cif_titles"):
                        show_titles_local = bool(getattr(_bp_module, "show_cif_titles", True))
            except Exception:
                pass
            show_hkl_local = False
            try:
                # Prefer figure attr (batch / reopened session); __main__ is process-global.
                if hasattr(fig, "_bp_show_cif_hkl"):
                    show_hkl_local = bool(getattr(fig, "_bp_show_cif_hkl", False))
                else:
                    _bp_module = sys.modules.get("__main__")
                    if _bp_module is not None and hasattr(_bp_module, "show_cif_hkl"):
                        show_hkl_local = bool(getattr(_bp_module, "show_cif_hkl", False))
            except Exception:
                pass
            y_src = y_data_list
            if not y_src:
                try:
                    y_src = [np.asarray(ln.get_ydata()) for ln in ax.lines if ln.get_visible()]
                except Exception:
                    y_src = []
            _stacked_xy = bool(len(y_src or []) > 1)
            if _stacked_xy and y_src:
                global_min = min(float(np.asarray(a).min()) for a in y_src if len(np.asarray(a)))
                base = global_min - 0.08 * fixed_yr
            else:
                global_min = (
                    min(float(np.asarray(a).min()) for a in y_src if len(np.asarray(a)))
                    if y_src
                    else 0.0
                )
                base = global_min - 0.06 * fixed_yr
            spacing = xy_cif_row_spacing_yr(
                fixed_yr,
                show_titles=show_titles_local,
                show_hkl=show_hkl_local,
                stacked_or_multi_y=_stacked_xy,
            )
            _cif_bottom_m = xy_cif_stack_bottom_margin_yr(fixed_yr, show_titles=show_titles_local)
            needed_min = base - (len(series) - 1) * spacing - _cif_bottom_m
            if not show_titles_local:
                ylim_draw = tuple(prev_ylim)
            elif needed_min >= prev_ylim[0]:
                ylim_draw = tuple(prev_ylim)
            else:
                ylim_draw = (min(needed_min, prev_ylim[0]), prev_ylim[1])
            ax.set_ylim(ylim_draw)
            cur_ylim = ax.get_ylim()
            yr = cur_ylim[1] - cur_ylim[0]
            if yr <= 0:
                yr = 1.0
            for art in getattr(ax, "_cif_tick_art", []):
                try:
                    art.remove()
                except Exception:
                    pass
            new_art = []
            label_maps = getattr(fig, "_batplot_cif_hkl_label_map", None) or hkl_map_ref
            wl_any = _ensure_wl(series)
            from .axis_units import (
                domain_peak_to_Q,
                get_xy_axis_mode,
                peaks_Q_to_domain,
            )
            # Prefer live fig mode (axis-unit convert ``u``) over install-time use_2th
            axis_mode = get_xy_axis_mode(fig, use_2th=bool(use_2th), ax=ax)
            xrd_draw = axis_mode in ("2theta", "Q", "d")
            for i, (lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(series):
                y_line = base - i * spacing + xy_cif_stack_y_offset(fig, i)
                tick_h, hkl_y = xy_cif_tick_stack_layout(y_line, yr)
                if not xrd_draw:
                    domain_peaks = []
                else:
                    wl_use = wl if wl is not None else (wl_any if axis_mode == "2theta" else None)
                    domain_peaks = peaks_Q_to_domain(peaksQ, axis_mode, wl_use)
                xlow, xhigh = ax.get_xlim()
                domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
                label_map = {}
                if show_hkl_local:
                    label_map = (label_maps or {}).get(fname, {}) or {}
                for p in domain_peaks:
                    ln, = ax.plot(
                        [p, p], [y_line, y_line + tick_h],
                        color=color, lw=1.0, alpha=0.9, zorder=3,
                    )
                    new_art.append(ln)
                    if show_hkl_local:
                        Qp = domain_peak_to_Q(
                            p, axis_mode,
                            wl if wl is not None else (wl_any if axis_mode == "2theta" else None),
                        )
                        lbl = label_map.get(round(Qp, 6)) if Qp is not None else None
                        if lbl:
                            t_hkl = ax.text(
                                p, hkl_y, lbl, ha="center", va="bottom",
                                fontsize=7, rotation=90, color=color,
                            )
                            new_art.append(t_hkl)
                if show_titles_local:
                    xy_cif_add_phase_title(
                        ax, prev_xlim[0], y_line, tick_h, f" {lab}",
                        max(8, int(0.55 * plt.rcParams.get("font.size", 16))),
                        color, new_art,
                    )
            ax._cif_tick_art = new_art
            ax.set_xlim(prev_xlim)
            fig.canvas.draw_idle()
        except Exception as _exc:
            try:
                print(f"Warning: CIF tick redraw failed: {_exc}")
            except Exception:
                pass

    ax._cif_draw_func = _draw
    # Extend already installed at top of ensure_… (also when draw pre-existed).


def append_xy_cif_file(
    fig: Any,
    ax: Any,
    path_token: str,
    *,
    _bp: Any = None,
    use_2th: bool = False,
    default_wl: Optional[float] = None,
    redraw: bool = True,
    y_data_list: Optional[List[Any]] = None,
) -> Tuple[str, str]:
    """Append a CIF set to an XY figure. Returns ``(label, resolved_path)``."""
    fname, wl_from_token = _parse_xy_cif_path_token(path_token)
    path = Path(os.path.expanduser(str(fname))).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"CIF not found: {fname}")

    series = _resolve_live_xy_cif_series(_bp, fig)
    resolved = str(path)
    for existing in series:
        try:
            if str(Path(existing[1]).resolve()) == resolved:
                raise ValueError(f"CIF already loaded: {resolved}")
        except (TypeError, IndexError, OSError):
            continue

    # Prefer live axis mode from Options ``u`` over the install-time use_2th flag.
    try:
        from .axis_units import get_xy_axis_mode, resolve_cif_draw_wavelength

        _axis_mode = get_xy_axis_mode(fig, use_2th=bool(use_2th), ax=ax)
        if _axis_mode not in ("2theta", "Q", "d"):
            _axis_mode = "2theta" if use_2th else "Q"
    except Exception:
        _axis_mode = "2theta" if use_2th else "Q"
        resolve_cif_draw_wavelength = None  # type: ignore[assignment]
    need_2th = _axis_mode == "2theta"

    wl_file = wl_from_token if wl_from_token is not None else default_wl
    if need_2th:
        if wl_file is None:
            # Fall back to an existing series wavelength, then fig / --wl / Cu Kα.
            for _e in series:
                try:
                    if _e[3] is not None:
                        wl_file = float(_e[3])
                        break
                except Exception:
                    pass
        if wl_file is None and resolve_cif_draw_wavelength is not None:
            try:
                wl_file = resolve_cif_draw_wavelength(
                    fig=fig, cif_series=series, axis_mode="2theta",
                )
            except Exception:
                wl_file = getattr(fig, "_xy_wavelength", None)
        if wl_file is None:
            wl_file = getattr(fig, "_xy_wavelength", None)
        if wl_file is None:
            wl_file = 1.5406

    qmax_sim = _xy_cif_qmax(ax, series, use_2th=need_2th, fig=fig)
    try:
        Q_sim, _I_sim = simulate_cif_pattern_Q(str(path))
        if len(Q_sim):
            qmax_sim = max(qmax_sim, float(Q_sim[-1]))
    except Exception:
        pass

    refl_wl = float(wl_file) if need_2th and wl_file is not None else None
    refl = cif_reflection_positions(str(path), Qmax=float(qmax_sim), wavelength=refl_wl)
    hkl_list = list_reflections_with_hkl(str(path), Qmax=float(qmax_sim), wavelength=refl_wl)
    hkl_frag = {resolved: build_hkl_label_map_from_list(hkl_list)}

    label = path.name
    if need_2th and wl_file is not None:
        label += f" (λ={float(wl_file):.5f} Å)"
    color = _xy_cif_next_color(len(series))
    entry = (
        label,
        resolved,
        refl,
        float(wl_file) if need_2th and wl_file is not None else None,
        float(qmax_sim),
        color,
    )
    series.append(entry)

    # Mutate the live hkl map in place so pipeline draw closures (same object
    # via cif_globals) and fig/__main__ stay in sync. Never replace with a copy.
    hkl_map = None
    if _bp is not None:
        hkl_map = getattr(_bp, "cif_hkl_label_map", None)
    if not isinstance(hkl_map, dict):
        hkl_map = getattr(fig, "_batplot_cif_hkl_label_map", None)
    if not isinstance(hkl_map, dict):
        hkl_map = {}
        if _bp is not None:
            setattr(_bp, "cif_hkl_label_map", hkl_map)
    hkl_map.update(hkl_frag)
    if _bp is not None:
        setattr(_bp, "cif_hkl_label_map", hkl_map)
        if getattr(_bp, "show_cif_titles", None) is None:
            setattr(_bp, "show_cif_titles", True)
        if not hasattr(_bp, "show_cif_hkl"):
            setattr(_bp, "show_cif_hkl", False)
    try:
        fig._batplot_cif_hkl_label_map = hkl_map  # type: ignore[attr-defined]
        if not hasattr(fig, "_bp_show_cif_titles"):
            fig._bp_show_cif_titles = True  # type: ignore[attr-defined]
        if not hasattr(fig, "_bp_show_cif_hkl"):
            fig._bp_show_cif_hkl = False  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        _bp_module = sys.modules.get("__main__")
        if _bp_module is not None:
            # Point __main__ at the live session map (do not adopt a stale
            # __main__ dict — that breaks identity with _bp/fig and leaks
            # cross-test / cross-session keys).
            setattr(_bp_module, "cif_hkl_label_map", hkl_map)
            if not hasattr(_bp_module, "show_cif_hkl"):
                setattr(_bp_module, "show_cif_hkl", False)
            if not hasattr(_bp_module, "show_cif_titles"):
                setattr(_bp_module, "show_cif_titles", True)
    except Exception:
        pass

    # Visibility list length — prefer figure attr (batch/session), then __main__.
    vis: List[bool] = []
    try:
        vis = list(getattr(fig, "_bp_cif_set_visible", None) or [])
    except Exception:
        vis = []
    if not vis:
        try:
            _bp_module = sys.modules.get("__main__")
            if _bp_module is not None and hasattr(_bp_module, "cif_set_visible"):
                vis = list(getattr(_bp_module, "cif_set_visible") or [])
        except Exception:
            vis = []
    while len(vis) < len(series):
        vis.append(True)
    try:
        fig._bp_cif_set_visible = list(vis)  # type: ignore[attr-defined]
        _bp_module = sys.modules.get("__main__")
        if _bp_module is not None:
            setattr(_bp_module, "cif_set_visible", list(vis))
        if _bp is not None:
            setattr(_bp, "cif_set_visible", list(vis))
    except Exception:
        pass

    normalize_xy_cif_stack_y_offsets(fig, len(series))
    ensure_xy_cif_draw_installed(
        fig, ax, use_2th=need_2th, cif_hkl_label_map=hkl_map, y_data_list=y_data_list,
    )

    if redraw and hasattr(ax, "_cif_draw_func"):
        try:
            ax._cif_draw_func()
        except Exception as _exc:
            try:
                print(f"Warning: CIF tick redraw failed: {_exc}")
            except Exception:
                pass
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass
        # Helpful when CIF loaded OK but all reflections sit outside the current X window
        # (e.g. Q plot limited to 1–3 while first peak is at ~3.1).
        try:
            from .axis_units import get_xy_axis_mode, peaks_Q_to_domain

            _mode = get_xy_axis_mode(fig, use_2th=bool(need_2th), ax=ax)
            if _mode in ("2theta", "Q", "d") and refl:
                _wl_use = float(wl_file) if need_2th and wl_file is not None else None
                _dom = peaks_Q_to_domain(refl, _mode, _wl_use)
                _x0, _x1 = ax.get_xlim()
                _in = [p for p in _dom if _x0 <= p <= _x1]
                if not _in:
                    print(
                        f"Note: CIF '{label}' has {len(_dom)} reflection(s), but none fall in "
                        f"the current X range [{_x0:g}, {_x1:g}]. "
                        "Expand X (menu x) to see tick marks; the phase title still appears if titles are on."
                    )
        except Exception:
            pass
    return label, resolved


def run_cif_ticks_menu(
    *,
    ax: Any,
    fig: Any,
    _bp: Any,
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    _safe_input: Callable[[str], str],
    push_state: Callable[[str], Any],
    _print_cif_phase_list: Callable[[Any], Any],
    _apply_cif_phase_label_rename: Callable[[int, str], Any],
    _sync_fig_cif_tick_series: Callable[[], Any],
    use_2th: bool = False,
    default_wl: Optional[float] = None,
    y_data_list: Optional[List[Any]] = None,
    pop_undo: Optional[Callable[[], Any]] = None,
) -> None:
        # Unified CIF ticks submenu (mirrors operando 'c' → CIF menu).
        # Always expose the command; empty series can still use ``a`` to add.
        if _bp is None:
            print("\nCIF state unavailable in this session.")
            return
        cif_series = _resolve_live_xy_cif_series(_bp, fig)
        _sync_fig_cif_tick_series()

        def _add_cif_files_interactive():
            """One multi-select picker; return to the CIF menu after selection."""
            from ...utils import _ask_files_dialog, _parse_typed_path_list

            print("Select CIF file(s)… (cancel to return)")
            try:
                picked = _ask_files_dialog(
                    filetypes=(".cif", ".CIF"),
                    title="Select CIF file(s)",
                    multiple=True,
                )
            except Exception:
                picked = []
            if not picked:
                # Dialog cancel / unavailable (headless, SSH, broken GUI).
                line = _safe_input(colorize_prompt(
                    "No file selected. Type CIF path(s) (quote if spaces), q=back: "
                )).strip()
                if not line or line.lower() == "q":
                    return
                picked = _parse_typed_path_list(line)
                if not picked:
                    print("No file selected.")
                    return
            need_2th = bool(use_2th)
            try:
                from .axis_units import get_xy_axis_mode
                need_2th = get_xy_axis_mode(fig) == "2theta"
            except Exception:
                pass
            wl_suffix = ""
            if need_2th:
                wl_hint = _safe_input(colorize_prompt(
                    "Wavelength Å for 2θ (Enter=session default, q=cancel add): "
                )).strip()
                if wl_hint.lower() == "q":
                    return
                if wl_hint:
                    try:
                        wl_val = float(wl_hint)
                    except ValueError:
                        print("Invalid wavelength; using session default.")
                    else:
                        if wl_val > 0 and wl_val == wl_val:
                            wl_suffix = f":{wl_hint}"
                        else:
                            print("Wavelength must be > 0; using session default.")
            for path in picked:
                token = f"{path}{wl_suffix}"
                pushed = False
                try:
                    pushed = bool(push_state("cif-add"))
                except Exception:
                    pushed = False
                try:
                    lab, resolved = append_xy_cif_file(
                        fig,
                        ax,
                        token,
                        _bp=_bp,
                        use_2th=need_2th,
                        default_wl=default_wl,
                        redraw=True,
                        y_data_list=y_data_list,
                    )
                    _sync_fig_cif_tick_series()
                    n = len(getattr(_bp, "cif_tick_series", None) or [])
                    print(f"Added CIF set {n}: {lab}")
                    print(f"  ({resolved})")
                except Exception as exc:
                    # Callers pass restore_state as pop_undo so a partial mutate
                    # is rolled back (discard-only would leave cracked CIF).
                    if pushed and pop_undo is not None:
                        try:
                            pop_undo()
                        except Exception:
                            pass
                    print(f"Could not add CIF: {exc}")

        # Local state mirrors operando CIF submenu: hkl and title visibility flags.
        show_hkl = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else False
        show_titles = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
        while True:
            cif_series = list(getattr(_bp, "cif_tick_series", None) or [])
            show_hkl = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else False
            show_titles = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
            print("\n\033[1mCIF tick labels:\033[0m")
            if not cif_series:
                print("  (no CIF sets yet — use a to add)")
            print("  " + colorize_menu("a: add CIF file(s)"))
            if cif_series:
                hkl_desc = f"z: toggle hkl labels (currently {'on' if show_hkl else 'off'})"
                titles_desc = f"t: toggle CIF titles (currently {'on' if show_titles else 'off'})"
                order_desc = "v: change CIF vertical order (sequence of rows)"
                print("  " + colorize_menu(hkl_desc))
                # Accept both 'j' (legacy) and 't' (to match operando) for title toggle
                print("  " + colorize_menu(titles_desc))
                print("  " + colorize_menu(order_desc))
                print("  " + colorize_menu("p: shift all CIF ticks (w/s or type a value)"))
                print("  " + colorize_menu("c: CIF color (per set)"))
                print("  " + colorize_menu("x: show/hide CIF set"))
                print("  " + colorize_menu("r: rename CIF phase label (same as main menu r→t)"))
            print("  " + colorize_menu("q: back to main menu"))
            prompt_keys = "a/z/t/v/p/c/x/r/q" if cif_series else "a/q"
            sub = _safe_input(colorize_prompt(f"CIF ({prompt_keys}): ")).strip().lower()
            if not sub or sub == 'q':
                break
            if sub == 'a':
                _add_cif_files_interactive()
                continue
            if not cif_series:
                print("No CIF sets yet. Use a to add a CIF file.")
                continue
            if sub == 'z':
                try:
                    push_state("toggle-cif-hkl")
                except Exception:
                    pass
                try:
                    cur = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else False
                    new_state = not cur
                    if _bp is not None:
                        setattr(_bp, 'show_cif_hkl', new_state)
                    # Keep figure attr in sync so style export (p) / batch panels
                    # do not read a stale _bp_show_cif_hkl or process-global leftover.
                    fig._bp_show_cif_hkl = new_state  # type: ignore[attr-defined]
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None:
                            setattr(_bp_module, 'show_cif_hkl', new_state)
                    except Exception:
                        pass
                    prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', True)
                    if hasattr(ax, '_cif_draw_func'):
                        ax._cif_draw_func()
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', prev_ext)
                    n_labels = 0
                    if bool(getattr(_bp, 'show_cif_hkl', False)) and hasattr(ax, '_cif_tick_art'):
                        for art in getattr(ax, '_cif_tick_art'):
                            try:
                                if hasattr(art, 'get_text') and '(' in art.get_text():
                                    n_labels += 1
                            except Exception:
                                pass
                    show_hkl = bool(getattr(_bp, 'show_cif_hkl', False))
                    print(f"CIF hkl labels {'ON' if show_hkl else 'OFF'} (visible labels: {n_labels}).")
                except Exception as e:
                    print(f"Error toggling hkl labels: {e}")
            elif sub == 't':
                try:
                    push_state("toggle-cif-titles")
                except Exception:
                    pass
                try:
                    prev_xlim = ax.get_xlim()
                    prev_ylim = ax.get_ylim()
                    cur = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
                    new_state = not cur
                    if _bp is not None:
                        setattr(_bp, 'show_cif_titles', new_state)
                    fig._bp_show_cif_titles = new_state
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None:
                            setattr(_bp_module, 'show_cif_titles', new_state)
                    except Exception:
                        pass
                    prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', True)
                    if hasattr(ax, '_cif_draw_func'):
                        ax._cif_draw_func()
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', prev_ext)
                    # Restore limits to prevent drift if draw function adjusted them unexpectedly
                    try:
                        ax.set_xlim(prev_xlim)
                        ax.set_ylim(prev_ylim)
                    except Exception:
                        pass
                    show_titles = new_state
                    print(f"CIF title labels {'ON' if new_state else 'OFF'}.")
                except Exception as e:
                    print(f"Error toggling CIF titles: {e}")
            elif sub == 'v':
                # Reorder CIF series vertically by changing sequence in cif_tick_series.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets to reorder.")
                    else:
                        print("Current CIF order (top to bottom):")
                        for i, (lab, fname, *_rest) in enumerate(cts):
                            print(f"  {i+1}: {lab}")
                        seq = _safe_input("New order (comma-separated indices, e.g. 2,1,3; q=cancel): ").strip().lower()
                        if not seq or seq == 'q':
                            continue
                        try:
                            parts = [int(s.strip()) for s in seq.split(',') if s.strip()]
                        except ValueError:
                            print("Invalid sequence. Use numbers separated by commas, e.g. 2,1,3.")
                            continue
                        n = len(cts)
                        if len(parts) != n or sorted(parts) != list(range(1, n + 1)):
                            print(f"Sequence must be a permutation of 1..{n}.")
                            continue
                        try:
                            push_state("cif-reorder")
                        except Exception:
                            pass
                        new_cts = [cts[i - 1] for i in parts]
                        if _bp is not None:
                            setattr(_bp, 'cif_tick_series', new_cts)
                        _sync_fig_cif_tick_series()
                        prev_offs = getattr(fig, '_bp_cif_stack_y_offsets', None)
                        if prev_offs is not None and len(prev_offs) == len(cts):
                            fig._bp_cif_stack_y_offsets = [prev_offs[i - 1] for i in parts]
                        if hasattr(ax, '_cif_draw_func'):
                            ax._cif_draw_func()
                        print("Updated CIF vertical order.")
                except Exception as e:
                    print(f"Error reordering CIF sets: {e}")
            elif sub == 'p':
                # Same offset list length as CIF sets: apply one shared data-Y shift to every row,
                # or w/s nudge all stacks by fixed typographic points on screen (2 pt).
                _CIF_NUDGE_PT = 2.0
    
                def _dy_data_for_display_pts(ax_, dy_pts):
                    try:
                        x_ref = float(np.mean(ax_.get_xlim()))
                        y_ref = float(np.mean(ax_.get_ylim()))
                        p0 = np.asarray(ax_.transData.transform((x_ref, y_ref)), dtype=float)
                        fig_ = ax_.figure
                        d_pix = float(dy_pts) * (float(fig_.dpi) / 72.0)
                        p1 = p0 + np.array([0.0, d_pix], dtype=float)
                        y1 = float(ax_.transData.inverted().transform(tuple(p1))[1])
                        return y1 - y_ref
                    except Exception:
                        return 0.0
    
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets.")
                    else:
                        n = len(cts)
                        _Hi = '\033[1m'
                        _Cc = '\033[96m'
                        _Rn = '\033[0m'
                        while True:
                            normalize_xy_cif_stack_y_offsets(fig, n)
                            offs = list(fig._bp_cif_stack_y_offsets)
                            print(
                                f"\n{_Hi}All CIF ticks:{_Rn} {_Hi}{_Cc}w{_Rn}/{_Hi}{_Cc}s{_Rn} nudge all "
                                f"(±{_CIF_NUDGE_PT:g} pt), or a {_Hi}{_Cc}number{_Rn} for all; "
                                f"{_Hi}{_Cc}0{_Rn} clear; {_Hi}{_Cc}q{_Rn} leave."
                            )
                            line = _safe_input(colorize_prompt("(w/s/value/0/q): ")).strip().lower()
                            if not line or line == 'q':
                                break
                            dd = _dy_data_for_display_pts(ax, _CIF_NUDGE_PT)
                            if line == 'w':
                                try:
                                    push_state("cif-stack-y-offset")
                                except Exception:
                                    pass
                                fig._bp_cif_stack_y_offsets = [float(o) + dd for o in offs]
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                                continue
                            if line == 's':
                                try:
                                    push_state("cif-stack-y-offset")
                                except Exception:
                                    pass
                                fig._bp_cif_stack_y_offsets = [float(o) - dd for o in offs]
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                                continue
                            if line in ('reset', '0', 'zero'):
                                try:
                                    push_state("cif-stack-y-offset")
                                except Exception:
                                    pass
                                fig._bp_cif_stack_y_offsets = [0.0] * n
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                                continue
                            try:
                                val = float(line)
                            except ValueError:
                                print("w, s, a number, or q.")
                                continue
                            try:
                                push_state("cif-stack-y-offset")
                            except Exception:
                                pass
                            fig._bp_cif_stack_y_offsets = [float(val)] * n
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                except Exception as e:
                    print(f"Error setting CIF offsets: {e}")
            elif sub == 'c':
                # CIF colors: support per-set mappings and palette-like tokens, mirroring main color menu behavior.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets to recolor.")
                    else:
                        # Show current CIF sets and colors
                        while True:
                            _C = '\033[96m'; _R = '\033[0m'
                            print("CIF color (per set).")
                            print("How to set color:")
                            print(f"  {_C}1:red 2:#00FF00{_R}       (set colors directly)")
                            print(f"  {_C}1:2 2:3{_R}               (use saved user colors 2 and 3)")
                            print(f"  {_C}all viridis{_R}           (apply palette to all CIF sets)")
                            print(f"  {_C}1-2,4 magma_r{_R}         (apply palette to a subset)")
                            print(
                                f"Other: {_C}v{_R}: show current colors   "
                                f"{_C}u{_R}: edit saved colors   {_C}e{_R}: pick color from screen   {_C}q{_R}: back"
                            )
                            line = _safe_input("Enter mappings or range+palette (q=back): ").strip()
                            if line.lower() == 'q' or blank_means_back(line):
                                break
                            cif_low = line.lower()
                            if cif_low == 'v':
                                print("Current CIF colors:")
                                for i, (lab, fname, peaksQ, wl_e, qmax, col) in enumerate(cts):
                                    print(f"  {i+1}: {format_color_listing(col)}  {lab}")
                                continue
                            if cif_low == 'u':
                                manage_user_colors(fig)
                                continue
                            if cif_low == 'e':
                                prompt_screen_color(fig)
                                continue
                            tokens = line.split()
                            # Decide mode: if any token contains ':', treat as manual index:color pairs.
                            if any(':' in t for t in tokens):
                                # Manual CIF index:color pairs — validate then push (xy/colors parity).
                                planned: list[tuple[int, object]] = []
                                for tok in tokens:
                                    if ':' not in tok:
                                        print(f"Skip malformed token: {tok}")
                                        continue
                                    idx_str, color_spec = tok.split(":", 1)
                                    try:
                                        idx = int(idx_str) - 1
                                    except ValueError:
                                        print(f"Bad index: {idx_str}")
                                        continue
                                    if not (0 <= idx < len(cts)):
                                        print(f"Index out of range: {idx_str}")
                                        continue
                                    try:
                                        resolved = resolve_color_token(color_spec, fig)
                                    except Exception:
                                        resolved = color_spec
                                    planned.append((idx, resolved))
                                if not planned:
                                    continue
                                try:
                                    push_state("cif-color")
                                except Exception:
                                    pass
                                for idx, resolved in planned:
                                    lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
                                    cts[idx] = (lab, fname, peaksQ, wl_e, qmax, resolved)
                                if _bp is not None:
                                    setattr(_bp, 'cif_tick_series', cts)
                                _sync_fig_cif_tick_series()
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                            else:
                                # Palette mode: treat input as "<range> <palette>" similar to main color menu.
                                parts = tokens
                                if len(parts) < 2:
                                    print("Need range(s) and palette (e.g., '1-3 viridis' or 'all magma_r').")
                                    continue
                                range_part = " ".join(parts[:-1]).replace(" ", "")
                                palette_token = parts[-1]
                                # Resolve palette token: number or name, with optional _r suffix.
                                available = list(_CUSTOM_CMAPS.keys()) + list(plt.colormaps())
                                # If numeric, map to a small predefined list as in main menu
                                palette_options = build_xy_palette_options(ensure_colormap)
                                palette_index = {str(i): name for i, name in enumerate(palette_options, 1)}
                                palette_name = resolve_palette_token(palette_token, palette_index)
                                # Check palette availability
                                if palette_name not in available and not ensure_colormap(palette_name):
                                    print(f"Unknown palette '{palette_name}'.")
                                    continue
                                indices = parse_index_ranges(range_part, len(cts), warn_out_of_range=True)
                                if not indices:
                                    print("No valid indices parsed.")
                                    continue
                                try:
                                    cmap = get_colormap(palette_name)
                                except Exception:
                                    cmap = None
                                if cmap is None:
                                    print(f"Could not load palette '{palette_name}'.")
                                    continue
                                try:
                                    push_state("cif-color-palette")
                                except Exception:
                                    pass
                                nsel = len(indices)
                                colors = sample_colormap(cmap, nsel)
                                for c_idx, idx in enumerate(indices):
                                    lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
                                    col = colors[c_idx]
                                    # Convert RGBA to hex or keep as RGBA tuple
                                    try:
                                        col_val = mcolors.to_hex(col)
                                    except Exception:
                                        col_val = col
                                    cts[idx] = (lab, fname, peaksQ, wl_e, qmax, col_val)
                                if _bp is not None:
                                    setattr(_bp, 'cif_tick_series', cts)
                                _sync_fig_cif_tick_series()
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                except Exception as e:
                    print(f"Error changing CIF colors: {e}")
            elif sub == 'x':
                # Per-set CIF visibility: maintain a boolean list in __main__.cif_set_visible.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets to show/hide.")
                    else:
                        _bp_module = _sys_vis.modules.get('__main__')
                        vis = []
                        if _bp_module is not None and hasattr(_bp_module, 'cif_set_visible'):
                            try:
                                vis = list(getattr(_bp_module, 'cif_set_visible') or [])
                            except Exception:
                                vis = []
                        if len(vis) < len(cts):
                            vis = vis + [True] * (len(cts) - len(vis))
                        while True:
                            print("CIF set visibility (q=back):")
                            for i, (lab, fname, *_rest) in enumerate(cts):
                                state = "show" if vis[i] else "hide"
                                print(f"  {i+1}: {lab} ({state})")
                            idx_s = _safe_input("Set index to toggle (q=back): ").strip().lower()
                            if not idx_s or idx_s == 'q':
                                break
                            try:
                                idx = int(idx_s) - 1
                                if 0 <= idx < len(cts):
                                    try:
                                        push_state("cif-visibility")
                                    except Exception:
                                        pass
                                    vis[idx] = not vis[idx]
                                    if _bp_module is not None:
                                        setattr(_bp_module, 'cif_set_visible', list(vis))
                                    fig._bp_cif_set_visible = list(vis)  # type: ignore[attr-defined]
                                    if _bp is not None:
                                        setattr(_bp, 'cif_set_visible', list(vis))
                                    if hasattr(ax, '_cif_draw_func'):
                                        ax._cif_draw_func()
                                else:
                                    print("Invalid index.")
                            except ValueError:
                                print("Invalid index.")
                except Exception as e:
                    print(f"Error toggling CIF visibility: {e}")
            elif sub == 'r':
                # Rename CIF phase labels — same behavior as main menu r→t.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF phases to rename.")
                    else:
                        while True:
                            print("CIF phases (q=back to CIF menu)")
                            _print_cif_phase_list(cts)
                            idx_s = _safe_input(
                                "Phase number to rename (q=back): "
                            ).strip().lower()
                            if not idx_s or idx_s == 'q':
                                break
                            try:
                                idx = int(idx_s) - 1
                                if not (0 <= idx < len(cts)):
                                    print("Invalid index.")
                                    continue
                            except ValueError:
                                print("Invalid index.")
                                continue
                            print_label_math_help()
                            while True:
                                new_lab = _safe_input(
                                    f"New CIF phase label (m=math help, q=back): "
                                ).strip()
                                if not new_lab or new_lab.lower() == 'q':
                                    break
                                if new_lab.lower() == 'm':
                                    print_label_math_help()
                                    continue
                                new_lab = finalize_axis_label_text(new_lab)
                                _apply_cif_phase_label_rename(idx, new_lab)
                                print(f"Phase {idx + 1} label updated.")
                except Exception as e:
                    print(f"Error renaming CIF phase labels: {e}")
            else:
                print("Unknown option.")
        return


__all__ = [
    "append_xy_cif_file",
    "ensure_xy_cif_draw_installed",
    "extend_xy_cif_series_for_xmax",
    "run_cif_ticks_menu",
]
