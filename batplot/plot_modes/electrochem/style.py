"""Style and geometry helpers for EC interactive mode."""

from __future__ import annotations

from typing import Any, Dict, Optional
import json
import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib import colors as mcolors  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    AutoMinorLocator,
    MultipleLocator,
    NullFormatter,
    NullLocator,
)

from ..common.font_extras import font_extras_export_dict
from ..common.line_dash import capture_dash_pattern, clear_dash_pattern, restore_dash_pattern
from ..common.session_helpers import _artist_linewidth, _current_tick_length, _first_defined
from ..common.spines import current_tick_width, set_primary_axis_title
from ...color_utils import color_block, format_color_listing
from ...plotting import apply_curve_color
from ...ui import capture_axes_tick_locators, resolve_spine_dump_color, set_spine_side_color
from ...utils import _colorize_option_keys, _confirm_overwrite, get_organized_path, list_files_in_subdirectory
from ..common.terminal import safe_input as _safe_input
from ..common.axis_state import capture_axis_wasd_state
from .colors import (
    _apply_visible_cycle_numbers,
    _iter_cycle_lines,
    _selected_cycle_numbers_for_file,
    _visible_cycle_numbers,
)
from .legend import _get_legend_title


def _geom_label_text(ax, stored_attr: str, live_getter) -> str:
    """Prefer ``_stored_*`` when present (including intentional "").

    EC treats a present store as authoritative for dump/psg so cleared titles
    round-trip even if the live artist briefly lags. Mode switches must keep
    the store in sync (see ``dual_axis_menu._set_bottom_xlabel``).
    """
    if hasattr(ax, stored_attr):
        val = getattr(ax, stored_attr)
        return "" if val is None else str(val)
    try:
        return live_getter() or ""
    except Exception:
        return ""


def _get_geometry_snapshot(fig, ax) -> Dict:
    """Collects a snapshot of geometry settings (axes labels and limits)."""
    out = {
        'xlim': list(ax.get_xlim()),
        'ylim': list(ax.get_ylim()),
        # Prefer stored text so hidden/cleared titles still round-trip via psg.
        'xlabel': _geom_label_text(ax, '_stored_xlabel', ax.get_xlabel),
        'ylabel': _geom_label_text(ax, '_stored_ylabel', ax.get_ylabel),
    }
    try:
        dm = getattr(fig, '_ec_display_mode', 'both')
        if dm in ('charge', 'discharge', 'both'):
            out['display_mode'] = dm
    except Exception:
        pass
    return out


def _line_color_hex(ln) -> Optional[str]:
    try:
        return mcolors.to_hex(ln.get_color())
    except Exception:
        col = ln.get_color()
        if isinstance(col, str):
            return col
        try:
            return mcolors.to_hex(mcolors.to_rgba(col))
        except Exception:
            return None


def _line_style_snapshot(ln) -> Dict:
    style: Dict = {}
    color_hex = _line_color_hex(ln)
    if color_hex:
        style['color'] = color_hex
    try:
        style['linewidth'] = float(ln.get_linewidth())
    except Exception:
        pass
    try:
        style['linestyle'] = ln.get_linestyle()
        dp = capture_dash_pattern(ln)
        if dp:
            style['dash_pattern'] = dp
    except Exception:
        pass
    try:
        style['marker'] = ln.get_marker()
        style['markersize'] = float(ln.get_markersize())
        style['markerfacecolor'] = ln.get_markerfacecolor()
        style['markeredgecolor'] = ln.get_markeredgecolor()
    except Exception:
        pass
    try:
        style['alpha'] = ln.get_alpha()
    except Exception:
        pass
    style['visible'] = bool(ln.get_visible())
    return style


def capture_cycle_styles_snapshot(cycle_lines: Dict, file_data: Optional[list] = None):
    """Capture per-cycle line styles for undo / export parity."""
    cycle_styles: Dict = {}
    for cyc, parts in cycle_lines.items():
        entry: Dict = {}
        if isinstance(parts, dict):
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is None:
                    continue
                style = _line_style_snapshot(ln)
                if style:
                    entry[role] = style
        else:
            ln = parts
            if ln is not None:
                style = _line_style_snapshot(ln)
                if style:
                    entry['line'] = style
        if entry:
            cycle_styles[str(cyc)] = entry

    cycle_styles_per_file = None
    if file_data is not None and len(file_data) > 1:
        cycle_styles_per_file = []
        for f in file_data:
            cl = f.get('cycle_lines')
            if not cl:
                cycle_styles_per_file.append({})
                continue
            per_file: Dict = {}
            for cyc, parts in cl.items():
                entry = {}
                if isinstance(parts, dict):
                    for role in ("charge", "discharge"):
                        ln = parts.get(role)
                        if ln is None:
                            continue
                        style = _line_style_snapshot(ln)
                        if style:
                            entry[role] = style
                else:
                    ln = parts
                    if ln is not None:
                        style = _line_style_snapshot(ln)
                        if style:
                            entry['line'] = style
                if entry:
                    per_file[str(cyc)] = entry
            cycle_styles_per_file.append(per_file)
    return cycle_styles, cycle_styles_per_file


def capture_ec_curve_marker_defaults(cycle_lines: Dict):
    curve_linewidth = None
    curve_marker_props: Dict = {}
    try:
        for _cyc, _role, ln in _iter_cycle_lines(cycle_lines):
            try:
                curve_linewidth = float(ln.get_linewidth())
            except Exception:
                pass
            try:
                curve_marker_props = {
                    'linestyle': ln.get_linestyle(),
                    'marker': ln.get_marker(),
                    'markersize': ln.get_markersize(),
                    'markerfacecolor': ln.get_markerfacecolor(),
                    'markeredgecolor': ln.get_markeredgecolor(),
                }
                dp = capture_dash_pattern(ln)
                if dp:
                    curve_marker_props['dash_pattern'] = dp
            except Exception:
                pass
            if curve_marker_props:
                break
    except Exception:
        pass
    if curve_linewidth is None:
        curve_linewidth = 1.0
    return curve_linewidth, curve_marker_props


def capture_dual_top_axis(fig, ax) -> Optional[Dict]:
    try:
        secax = getattr(fig, '_xaxis_secondary', None)
        if secax is None:
            return None
        top_spine = secax.spines.get('top')
        try:
            _pad = getattr(secax.xaxis, 'labelpad', 4.0)
            _labelpad = float(4.0 if _pad is None else _pad)
        except Exception:
            _labelpad = 4.0
        _spine_c = (
            resolve_spine_dump_color(secax, "top", fig) if top_spine is not None else None
        )
        try:
            _spine_c_hex = mcolors.to_hex(_spine_c) if _spine_c is not None else None
        except Exception:
            _spine_c_hex = None
        return {
            'xlabel': secax.get_xlabel(),
            'xlabel_visible': bool(secax.xaxis.label.get_visible()),
            'label_color': mcolors.to_hex(secax.xaxis.label.get_color()),
            'labelpad': _labelpad,
            'spine_visible': bool(top_spine.get_visible()) if top_spine is not None else True,
            'spine_color': _spine_c_hex,
            'major_tick_color': (secax.xaxis.get_tick_params() or {}).get('color'),
        }
    except Exception:
        return None


def ec_dual_secax(fig) -> Any:
    """Return SecondaryAxis when fig is in GC dual mode, else None."""
    try:
        if getattr(fig, '_xaxis_mode', 'capacity') == 'dual':
            return getattr(fig, '_xaxis_secondary', None)
    except Exception:
        return None
    return None


def xaxis_dual_export_dict(fig, ax=None, *, top_axis: Optional[Dict] = None) -> Dict:
    """Serialize ``a``-menu state for p/i/s/b. ``swapped`` only meaningful in dual."""
    mode = getattr(fig, '_xaxis_mode', 'capacity') or 'capacity'
    if top_axis is None and ax is not None and mode == 'dual':
        top_axis = capture_dual_top_axis(fig, ax)
    return {
        'mode': mode,
        'c_theoretical': getattr(fig, '_xaxis_c_theoretical', None),
        'swapped': bool(getattr(fig, '_xaxis_swapped', False)) if mode == 'dual' else False,
        'top_axis': top_axis,
    }


def sanitize_fig_xaxis_swapped(fig, *, mode=None, swapped=None) -> bool:
    """Set ``fig._xaxis_swapped``; force False unless mode is dual (load/import/undo)."""
    if mode is None:
        mode = getattr(fig, '_xaxis_mode', 'capacity') or 'capacity'
    if swapped is None:
        swapped = getattr(fig, '_xaxis_swapped', False)
    val = bool(swapped) if mode == 'dual' else False
    try:
        fig._xaxis_swapped = val
    except Exception:
        pass
    return val


def ec_dual_width_axes(fig, ax) -> list:
    """Axes that must receive frame/tick width updates (include SecondaryAxis)."""
    axes = [ax]
    sec = ec_dual_secax(fig)
    if sec is not None:
        axes.append(sec)
    return axes


def ec_dual_x_scale_factor(fig) -> float:
    """Primary→SecondaryAxis x scale: unswapped ions=cap/C_th; swapped cap=ions*C_th."""
    c_th = getattr(fig, '_xaxis_c_theoretical', None)
    try:
        c_th_f = float(c_th) if c_th is not None else 0.0
    except Exception:
        c_th_f = 0.0
    if c_th_f <= 0:
        return 1.0
    if bool(getattr(fig, '_xaxis_swapped', False)):
        return c_th_f
    return 1.0 / c_th_f


def _stored_dual_top_spine_color(fig, ax) -> Optional[str]:
    """Best-effort stored top color for SecondaryAxis tick re-force after tick_params."""
    for store in (
        getattr(ax, '_bp_spine_side_colors', None),
        getattr(fig, '_bp_spine_side_colors', None),
        getattr(getattr(fig, '_xaxis_secondary', None), '_bp_spine_side_colors', None),
    ):
        if isinstance(store, dict) and store.get('top'):
            try:
                return mcolors.to_hex(store['top'])
            except Exception:
                try:
                    return str(store['top'])
                except Exception:
                    pass
    return None


def reseal_ec_chrome(
    fig,
    ax,
    *,
    wasd=None,
    tick_state=None,
    apply_titles: bool = True,
) -> None:
    """Single post-touch funnel: WASD + dual locators + suppress duplicate + colors."""
    if wasd is None:
        wasd = getattr(fig, '_ec_wasd_state', None)
    apply_ec_wasd_chrome(fig, ax, wasd, apply_titles=apply_titles)
    try:
        sync_ec_dual_secax_x_locators(fig, ax, wasd)
    except Exception:
        pass
    try:
        suppress_ec_dual_duplicate_top_title(ax, fig)
    except Exception:
        pass
    try:
        from ...ui import finalize_spine_colors

        ts = tick_state
        if ts is None:
            ts = getattr(ax, '_saved_tick_state', None)
        finalize_spine_colors(fig, ax, tick_state=ts, draw=False)
    except Exception:
        pass


def suppress_ec_dual_duplicate_top_title(ax, fig=None) -> None:
    """In dual mode the top title is SecondaryAxis.xaxis.label — hide XY-style duplicate."""
    try:
        if fig is not None and ec_dual_secax(fig) is None:
            return
    except Exception:
        pass
    try:
        ax._top_xlabel_on = False
    except Exception:
        pass
    art = getattr(ax, '_top_xlabel_artist', None)
    if art is not None:
        try:
            art.set_visible(False)
        except Exception:
            pass


def force_ec_dual_primary_top_tick_chrome_off(ax) -> None:
    """Primary top must never show capacity-scale ticks/labels in dual mode.

    ``tick_state['t_ticks']`` / WASD ``top.ticks`` mean *ions SecondaryAxis*
    chrome when dual is on. Applying those flags to the primary axis via
    ``update_tick_visibility`` is the root cause of ghost ticks/labels.
    """
    try:
        ax.tick_params(axis='x', which='major', top=False, labeltop=False)
        ax.tick_params(axis='x', which='minor', top=False, labeltop=False)
    except Exception:
        pass


def apply_ec_wasd_chrome(
    fig,
    ax,
    wasd_state: Optional[Dict] = None,
    *,
    apply_titles: bool = True,
) -> None:
    """Apply WASD spine/tick/label/title chrome for **all four sides** (w/a/s/d).

    Single source of truth for EC interactive ``t``, batch ``t``, undo, and
    post-``update_tick_visibility`` sealing.

    Dual mode (capacity + ions SecondaryAxis):
    - bottom / left / right → primary axis only
    - top spine → both overlays; top ticks/labels/title → SecondaryAxis only
    - primary top ticks/labels always forced off (capacity ≠ ions locator)
    - SecondaryAxis bottom/left/right spines forced off (mpl default, reasserted)

    Non-dual: all four sides on the primary axis (standard WASD).

    Bottom/left titles use :func:`set_primary_axis_title` (store/clear + visibility).
    Dual top title stays visibility-only on the SecondaryAxis (text retained).
    Title keys are applied only when present in the WASD side dict (older styles).
    """
    from ..common.spines import apply_wasd_spines, apply_wasd_tick_params

    if wasd_state is None:
        wasd_state = getattr(fig, '_ec_wasd_state', None)
    if not isinstance(wasd_state, dict):
        return

    secax = ec_dual_secax(fig)
    if secax is not None:
        apply_wasd_spines(ax, wasd_state)
        apply_wasd_tick_params(
            ax, wasd_state, x_sides=('bottom',), y_sides=('left', 'right'),
        )
        # Keep SecondaryAxis from growing a second frame on a/s/d sides
        try:
            for side in ('bottom', 'left', 'right'):
                sp = secax.spines.get(side)
                if sp is not None:
                    sp.set_visible(False)
            secax.tick_params(
                axis='x', which='both', bottom=False, labelbottom=False,
            )
            secax.tick_params(
                axis='y', which='both',
                left=False, right=False, labelleft=False, labelright=False,
            )
        except Exception:
            pass
        apply_ec_dual_top_wasd(fig, ax, wasd_state)
    else:
        apply_wasd_spines(ax, wasd_state)
        apply_wasd_tick_params(ax, wasd_state)

    if not apply_titles:
        return

    bot = wasd_state.get('bottom') or {}
    left = wasd_state.get('left') or {}
    right = wasd_state.get('right') or {}
    top = wasd_state.get('top') or {}
    # Key-presence preserved: only touch sides that dump included (older styles).
    if isinstance(bot, dict) and 'title' in bot:
        set_primary_axis_title(
            ax, "x",
            on=bool(bot.get('title')),
            stored_attr="_stored_xlabel",
        )
    if isinstance(left, dict) and 'title' in left:
        set_primary_axis_title(
            ax, "y",
            on=bool(left.get('title')),
            stored_attr="_stored_ylabel",
        )
    if isinstance(right, dict) and 'title' in right:
        try:
            ax._right_ylabel_on = bool(right.get('title'))
        except Exception:
            pass
    if secax is not None:
        # top title owned by SecondaryAxis (apply_ec_dual_top_wasd)
        try:
            ax._top_xlabel_on = False
        except Exception:
            pass
    elif isinstance(top, dict) and 'title' in top:
        try:
            ax._top_xlabel_on = bool(top.get('title'))
        except Exception:
            pass

    # Re-color ticks after visibility/locator changes (k before w2/w3 used to leave
    # newly enabled ions ticks at matplotlib default black).
    try:
        from ...ui import finalize_spine_colors

        finalize_spine_colors(fig, ax, draw=False)
    except Exception:
        pass


def seal_ec_dual_top_chrome(fig, ax, wasd_state: Optional[Dict] = None) -> None:
    """Re-assert dual-aware WASD for **all sides** after tick_state / tick_params.

    Backward-compatible name (historically top-only). Now seals w/a/s/d.
    No-op when not in dual mode.
    """
    seal_ec_axis_chrome(fig, ax, wasd_state)


def seal_ec_axis_chrome(fig, ax, wasd_state: Optional[Dict] = None) -> None:
    """Re-assert correct chrome on all WASD sides after any tick_state apply.

    Dual: full :func:`apply_ec_wasd_chrome` with ``apply_titles=True`` so bottom/
    left titles stay store/clear-consistent via :func:`set_primary_axis_title`.
    Non-dual: no-op (primary ``update_tick_visibility`` is sufficient).
    """
    if ec_dual_secax(fig) is None:
        return
    if wasd_state is None:
        wasd_state = getattr(fig, '_ec_wasd_state', None)
    apply_ec_wasd_chrome(fig, ax, wasd_state, apply_titles=True)
    suppress_ec_dual_duplicate_top_title(ax, fig)


def sync_ec_dual_secax_x_locators(fig, ax, wasd_state: Optional[Dict] = None) -> None:
    """Sync SecondaryAxis major+minor locators from primary (bottom units × scale).

    ``x`` spacing in ``t``→``n``/``m`` is always primary/bottom units. Top axis
    ticks are transform-scaled so marks align. Respects ``_xaxis_swapped``.
    """
    secax = ec_dual_secax(fig)
    if secax is None:
        return
    if wasd_state is None:
        wasd_state = getattr(fig, '_ec_wasd_state', None)
    top_s = (wasd_state or {}).get('top') if isinstance(wasd_state, dict) else {}
    if not isinstance(top_s, dict):
        top_s = {}
    factor = ec_dual_x_scale_factor(fig)
    # Major: always mirror primary so dual ticks stay aligned after n
    try:
        maj = ax.xaxis.get_major_locator()
        if isinstance(maj, MultipleLocator):
            try:
                step = float(maj._edge.step)  # type: ignore[attr-defined]
            except Exception:
                step = None
            if step is not None and step > 0 and factor > 0:
                secax.xaxis.set_major_locator(MultipleLocator(step * factor))
        # AutoLocator / others: leave SecondaryAxis default (still functional)
    except Exception:
        pass
    # Minor: only when top.minor (w3) is on
    want_minor = bool(top_s.get('minor', False))
    try:
        if not want_minor:
            secax.xaxis.set_minor_locator(NullLocator())
            secax.xaxis.set_minor_formatter(NullFormatter())
            secax.tick_params(axis='x', which='minor', top=False, labeltop=False)
            return
        loc = ax.xaxis.get_minor_locator()
        if isinstance(loc, AutoMinorLocator):
            try:
                ndivs = int(
                    getattr(loc, 'ndivs', None)
                    or getattr(loc, '_ndivs', None)
                    or 4
                )
            except Exception:
                ndivs = 4
            secax.xaxis.set_minor_locator(AutoMinorLocator(ndivs))
        elif isinstance(loc, MultipleLocator):
            try:
                step = float(loc._edge.step)  # type: ignore[attr-defined]
            except Exception:
                step = None
            if step is not None and step > 0 and factor > 0:
                secax.xaxis.set_minor_locator(MultipleLocator(step * factor))
            else:
                secax.xaxis.set_minor_locator(AutoMinorLocator())
        else:
            # Primary may have NullLocator when only w3 (top) is on
            secax.xaxis.set_minor_locator(AutoMinorLocator())
        secax.xaxis.set_minor_formatter(NullFormatter())
        secax.tick_params(axis='x', which='minor', top=True, labeltop=False)
    except Exception:
        try:
            secax.xaxis.set_minor_locator(AutoMinorLocator())
            secax.xaxis.set_minor_formatter(NullFormatter())
            secax.tick_params(axis='x', which='minor', top=True, labeltop=False)
        except Exception:
            pass


def sync_ec_dual_secax_x_minor(fig, ax, wasd_state: Optional[Dict] = None) -> None:
    """Backward-compatible alias — syncs major+minor (see locators helper)."""
    sync_ec_dual_secax_x_locators(fig, ax, wasd_state)


def apply_ec_dual_top_wasd(fig, ax, wasd_state: Optional[Dict] = None) -> None:
    """Apply WASD top chrome for GC dual (capacity + ions SecondaryAxis).

    Authoritative layer rules (single source of truth):
    - ``w1`` spine: BOTH primary + SecondaryAxis (same physical line).
    - ``w2``/``w3`` ticks, ``w4`` labels, ``w5`` title: SecondaryAxis ONLY.
      Primary top always forced off (capacity locator ≠ ions locator).
    - ``w3`` also installs a minor locator on SecondaryAxis (see
      :func:`sync_ec_dual_secax_x_minor`).

    Bookkeeping note: ``wasd['top']['ticks']`` / ``tick_state['t_ticks']`` stay
    True when the user enables top ticks — but those flags must be applied to
    the SecondaryAxis, never the primary. Use :func:`seal_ec_dual_top_chrome`
    after any primary ``update_tick_visibility``.
    """
    secax = ec_dual_secax(fig)
    if secax is None:
        return
    if wasd_state is None:
        wasd_state = getattr(fig, '_ec_wasd_state', None)
    if not isinstance(wasd_state, dict):
        force_ec_dual_primary_top_tick_chrome_off(ax)
        suppress_ec_dual_duplicate_top_title(ax, fig)
        return
    top_s = wasd_state.get('top') or {}
    if not isinstance(top_s, dict):
        force_ec_dual_primary_top_tick_chrome_off(ax)
        suppress_ec_dual_duplicate_top_title(ax, fig)
        return
    # Always kill primary capacity top chrome first
    force_ec_dual_primary_top_tick_chrome_off(ax)
    try:
        if 'spine' in top_s:
            vis = bool(top_s['spine'])
            for target in (ax, secax):
                sp = target.spines.get('top')
                if sp is not None:
                    sp.set_visible(vis)
        # Ions SecondaryAxis only — omit keys leave that aspect unchanged
        maj_kw = {}
        if 'ticks' in top_s:
            maj_kw['top'] = bool(top_s['ticks'])
        if 'labels' in top_s:
            maj_kw['labeltop'] = bool(top_s['labels'])
        if maj_kw:
            secax.tick_params(axis='x', which='major', **maj_kw)
        if 'minor' in top_s:
            # Locator + visibility (visibility alone is a no-op with NullLocator)
            sync_ec_dual_secax_x_locators(fig, ax, wasd_state)
        # tick_params can leave marks black — re-force stored top color
        top_c = _stored_dual_top_spine_color(fig, ax)
        if top_c:
            try:
                from ...ui import _force_ec_dual_secax_tick_colors

                _force_ec_dual_secax_tick_colors(secax, top_c)
            except Exception:
                pass
    except Exception:
        force_ec_dual_primary_top_tick_chrome_off(ax)
    if 'title' in top_s:
        try:
            secax.xaxis.label.set_visible(bool(top_s['title']))
        except Exception:
            pass
    suppress_ec_dual_duplicate_top_title(ax, fig)


def dual_top_spine_visible(fig, ax) -> bool:
    """True if either dual top overlay spine is visible (what the user sees)."""
    secax = ec_dual_secax(fig)
    vis = False
    try:
        sp = ax.spines.get('top')
        if sp is not None and sp.get_visible():
            vis = True
    except Exception:
        pass
    if secax is not None:
        try:
            sp2 = secax.spines.get('top')
            if sp2 is not None and sp2.get_visible():
                vis = True
        except Exception:
            pass
    return vis


def dual_top_title_visible(fig, ax) -> bool:
    """SecondaryAxis ions title visibility (authoritative in dual mode)."""
    secax = ec_dual_secax(fig)
    if secax is None:
        return bool(getattr(ax, '_top_xlabel_on', False))
    try:
        return bool(secax.xaxis.label.get_visible())
    except Exception:
        return False


def reapply_ec_dual_secondary_chrome(
    fig,
    ax,
    *,
    wasd_state: Optional[Dict] = None,
    tick_lengths: Optional[Dict] = None,
    tick_widths: Optional[Dict] = None,
    tick_direction: Optional[str] = None,
    xlabel_bottom: Optional[str] = None,
    top_axis_cfg: Optional[Dict] = None,
) -> None:
    """After SecondaryAxis create/recreate: WASD top, tick geom, labels, spine colors.

    Safe no-op when not in dual mode. Backward compatible: missing wasd/cfg keys
    use conservative defaults (ticks/labels off unless specified).

    Visibility always comes from ``wasd_state`` (applied last) so ``top_axis``
    colors/text cannot resurrect a spine/title the user hid.
    """
    secax = getattr(fig, '_xaxis_secondary', None)
    if secax is None:
        return
    if wasd_state is None:
        wasd_state = getattr(fig, '_ec_wasd_state', None)
    # Colors / custom top xlabel text first
    if isinstance(top_axis_cfg, dict):
        try:
            apply_dual_top_axis_style(secax, top_axis_cfg, fig=fig)
        except Exception:
            pass
    else:
        try:
            from ...ui import finalize_spine_colors

            finalize_spine_colors(fig, ax)
        except Exception:
            pass
    # WASD layer rules (wins over top_axis visibility flags)
    apply_ec_dual_top_wasd(fig, ax, wasd_state)
    # Tick geometry on SecondaryAxis (+ primary top already has lengths from caller)
    try:
        tl = tick_lengths if tick_lengths is not None else getattr(fig, '_tick_lengths', None)
        if isinstance(tl, dict):
            maj = tl.get('major', tl.get('x_major'))
            mnr = tl.get('minor', tl.get('x_minor'))
            for target in (ax, secax):
                if maj is not None:
                    target.tick_params(axis='x', which='major', length=float(maj))
                if mnr is not None:
                    target.tick_params(axis='x', which='minor', length=float(mnr))
    except Exception:
        pass
    try:
        tw = tick_widths if isinstance(tick_widths, dict) else None
        if tw:
            for target in (ax, secax):
                if tw.get('x_major') is not None:
                    target.tick_params(axis='x', which='major', width=float(tw['x_major']))
                if tw.get('x_minor') is not None:
                    target.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
    except Exception:
        pass
    try:
        tdir = tick_direction if tick_direction is not None else getattr(fig, '_tick_direction', None)
        if tdir:
            for target in (ax, secax):
                target.tick_params(axis='x', which='both', direction=str(tdir))
    except Exception:
        pass
    if xlabel_bottom is not None:
        try:
            ax.set_xlabel(str(xlabel_bottom))
            ax._stored_xlabel = str(xlabel_bottom)
        except Exception:
            pass
    # Re-assert after tick_params (length/width/dir can revive primary top on some mpl)
    seal_ec_dual_top_chrome(fig, ax, wasd_state)


def apply_dual_top_axis_style(secax, top_axis_cfg: Optional[Dict], fig=None) -> None:
    """Restore dual top SecondaryAxis title/spine/tick colors (p/i/s/b).

    Pass ``fig`` so :func:`set_spine_side_color` syncs primary top spine + stores
    for finalize/draw-hook durability.

    Old pickles/styles may omit ``top_axis`` entirely (caller skips), or omit
    individual keys — missing colors are left alone / spine falls back to label.
    ``label_color`` and ``spine_color`` may differ; both are preserved.
    """
    if secax is None or not isinstance(top_axis_cfg, dict):
        return
    try:
        if top_axis_cfg.get('xlabel') is not None:
            secax.set_xlabel(str(top_axis_cfg.get('xlabel') or ''))
        secax.xaxis.label.set_visible(bool(top_axis_cfg.get('xlabel_visible', True)))
        if top_axis_cfg.get('labelpad') is not None:
            try:
                secax.xaxis.labelpad = float(top_axis_cfg['labelpad'])
            except Exception:
                pass
        label_c = top_axis_cfg.get('label_color')
        if label_c:
            try:
                secax._bp_top_title_color = label_c
            except Exception:
                pass
            secax.xaxis.label.set_color(label_c)
            try:
                secax._stored_top_xlabel_color = label_c
            except Exception:
                pass
        sp = secax.spines.get('top')
        if sp is not None:
            if top_axis_cfg.get('spine_visible') is not None:
                sp.set_visible(bool(top_axis_cfg.get('spine_visible')))
            spine_c = top_axis_cfg.get('spine_color') or top_axis_cfg.get('major_tick_color') or label_c
            if spine_c:
                # title_color keeps label distinct when style stored both colors
                parent = getattr(secax, "_parent", None)
                set_spine_side_color(
                    secax,
                    'top',
                    spine_c,
                    fig=fig,
                    title_color=label_c or spine_c,
                    tick_state=getattr(parent, "_saved_tick_state", None)
                    if parent is not None
                    else None,
                )
    except Exception:
        pass


def _get_style_snapshot(fig, ax, cycle_lines: Dict, tick_state: Dict, file_data: Optional[list] = None) -> Dict:
    """Collects a comprehensive snapshot of the current plot style (no curve data). If file_data is provided (multi-file), includes file_display_names."""
    # Figure and font properties
    fig_w, fig_h = fig.get_size_inches()
    ax_bbox = ax.get_position()
    frame_w_in = ax_bbox.width * fig_w
    frame_h_in = ax_bbox.height * fig_h
    
    font_fam = plt.rcParams.get('font.sans-serif', [''])
    font_fam0 = font_fam[0] if font_fam else ''
    font_size = plt.rcParams.get('font.size')

    # Spine properties (including color for k command)
    from ...ui import resolve_spine_dump_color

    spines = {}
    for name in ('bottom', 'top', 'left', 'right'):
        sp = ax.spines.get(name)
        if sp:
            try:
                raw = resolve_spine_dump_color(ax, name, fig)
                color = mcolors.to_hex(raw) if raw is not None else None
            except Exception:
                color = None
            spines[name] = {
                'linewidth': sp.get_linewidth(),
                'visible': sp.get_visible(),
                'color': color,
            }

    # Tick widths
    def _tick_width(axis_obj, which: str):
        return current_tick_width(axis_obj, which)

    tick_widths = {
        'x_major': _tick_width(ax.xaxis, 'major'),
        'x_minor': _tick_width(ax.xaxis, 'minor'),
        'y_major': _tick_width(ax.yaxis, 'major'),
        'y_minor': _tick_width(ax.yaxis, 'minor'),
    }
    # Tick direction
    tick_direction = getattr(fig, '_tick_direction', 'out')
    tick_lengths = dict(getattr(fig, '_tick_lengths', {}) or {})
    if tick_lengths.get('major') is None:
        tick_lengths['major'] = _first_defined(
            _current_tick_length(ax.xaxis, 'major'),
            _current_tick_length(ax.yaxis, 'major'),
        )
    if tick_lengths.get('minor') is None:
        tick_lengths['minor'] = _first_defined(
            _current_tick_length(ax.xaxis, 'minor'),
            _current_tick_length(ax.yaxis, 'minor'),
        )
    tick_spacing = capture_axes_tick_locators(ax, ('x', 'y'))

    # Curve linewidth: get from stored value or first visible curve
    curve_linewidth = getattr(fig, '_ec_curve_linewidth', None)
    if curve_linewidth is None:
        try:
            for cyc, parts in cycle_lines.items():
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is not None:
                        try:
                            curve_linewidth = _artist_linewidth(ln)
                            break
                        except Exception:
                            pass
                if curve_linewidth is not None:
                    break
        except Exception:
            pass
    if curve_linewidth is None:
        curve_linewidth = 1.0  # default

    if curve_linewidth is None:
        curve_linewidth, curve_marker_props = capture_ec_curve_marker_defaults(cycle_lines)
    else:
        _, curve_marker_props = capture_ec_curve_marker_defaults(cycle_lines)

    cycle_styles, cycle_styles_per_file = capture_cycle_styles_snapshot(cycle_lines, file_data)

    # Authoritative visible-cycle ids (same contract as session dump).
    visible_cycles = _visible_cycle_numbers(cycle_lines) if cycle_lines else None
    visible_cycles_per_file = None
    if file_data is not None and len(file_data) > 1:
        visible_cycles_per_file = [
            _selected_cycle_numbers_for_file(f) for f in file_data
        ]
        visible_cycles = None

    # On-screen major tick/label truth (same as session dump) so p/i cannot
    # re-enable labels the user hid when bookkeeping drifted.
    _sec = ec_dual_secax(fig)
    if _sec is not None:
        # Ensure both dual top overlays match fig._ec_wasd_state before capture
        try:
            apply_ec_dual_top_wasd(fig, ax, getattr(fig, '_ec_wasd_state', None))
        except Exception:
            pass
    wasd_state = capture_axis_wasd_state(
        ax,
        tick_state=tick_state,
        use_actual_major_visibility=True,
        top_axis=_sec,
    )
    if _sec is not None and isinstance(wasd_state, dict):
        # Prefer live bookkeeping for top toggles (actual tick artists can lag)
        live = getattr(fig, '_ec_wasd_state', None)
        if isinstance(live, dict) and isinstance(live.get('top'), dict):
            wasd_state['top'] = dict(live['top'])
    # Preserve title flags that capture_axis_wasd_state derives from artists /
    # attrs (top/right duplicate titles, bottom/left label visibility).

    # Legend visibility/location — always read fig prefs so p/i/s/b round-trip
    # even when the legend artist is missing/hidden (batch ``h`` sync, undo).
    legend_visible = False
    legend_xy_in = None
    try:
        leg = ax.get_legend()
        if leg is not None:
            legend_visible = bool(leg.get_visible())
        user_vis = getattr(fig, '_ec_legend_user_visible', None)
        if user_vis is not None:
            legend_visible = bool(user_vis)
        legend_xy_in = getattr(fig, '_ec_legend_xy_in', None)
    except Exception:
        pass

    # Grid state
    grid_enabled = False
    try:
        # Check if grid is currently on by looking at gridline visibility
        for line in ax.get_xgridlines() + ax.get_ygridlines():
            if line.get_visible():
                grid_enabled = True
                break
    except Exception:
        grid_enabled = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False

    dual_top_axis = capture_dual_top_axis(fig, ax)

    result = {
        'kind': 'ec_style',
        'version': 2,
        'figure': {
            'canvas_size': [fig_w, fig_h],
            'frame_size': [frame_w_in, frame_h_in],
            'axes_fraction': [ax_bbox.x0, ax_bbox.y0, ax_bbox.width, ax_bbox.height],
        },
        'font': {
            'family': font_fam0,
            'size': font_size,
            'mathtext_fontset': plt.rcParams.get('mathtext.fontset'),
            **font_extras_export_dict(fig),
        },
        'axis_label_colors': {
            'x': mcolors.to_hex(getattr(ax, '_stored_xlabel_color', None) or ax.xaxis.label.get_color()),
            'y': mcolors.to_hex(getattr(ax, '_stored_ylabel_color', None) or ax.yaxis.label.get_color()),
        },
        'legend': {
            'visible': legend_visible,
            'position_inches': legend_xy_in,
            'title': _get_legend_title(fig),
        },
        'spines': spines,
        'ticks': {
            'widths': tick_widths,
            'lengths': tick_lengths,
            'direction': tick_direction,
            # Full locator state (incl. minor_off) so ``i`` can clear custom spacing.
            'spacing': tick_spacing,
        },
        'grid': grid_enabled,
        'wasd_state': wasd_state,
        'title_offsets': {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        },
        'labelpads': {
            'x': getattr(ax.xaxis, 'labelpad', None),
            'y': getattr(ax.yaxis, 'labelpad', None),
        },
        'axis_labels': {
            # Prefer stored text (including intentional empty) like geometry snap.
            'xlabel': _geom_label_text(ax, '_stored_xlabel', ax.get_xlabel),
            'ylabel': _geom_label_text(ax, '_stored_ylabel', ax.get_ylabel),
        },
        'curve_linewidth': curve_linewidth,
        'curve_markers': curve_marker_props,
        'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),
        'display_mode': getattr(fig, '_ec_display_mode', 'both'),
        'capacity_mode': getattr(fig, '_gc_capacity_mode', 'per_cycle') or 'per_cycle',
        'cycle_styles': cycle_styles,
        'ro_active': bool(getattr(fig, '_ro_active', False)),
        'cycle_styles_per_file': cycle_styles_per_file,
        'visible_cycles': visible_cycles,
        'visible_cycles_per_file': visible_cycles_per_file,
        'xaxis_dual': xaxis_dual_export_dict(fig, ax, top_axis=dual_top_axis),
        '_dqdv_smooth_settings': dict(getattr(fig, '_dqdv_smooth_settings', {})),
    }
    if file_data is not None and len(file_data) > 0:
        result['file_display_names'] = [f.get('display_name', f.get('filename', str(i))) for i, f in enumerate(file_data)]
        result['file_visibility'] = [bool(f.get('visible', True)) for f in file_data]
        result['legend_file_order'] = list(getattr(fig, '_ec_legend_file_order', None) or range(len(file_data)))
    return result


def _apply_cycle_styles(cycle_lines: Dict[int, Dict[str, Optional[Any]]], style_cfg: Optional[Dict]) -> None:
    if not isinstance(style_cfg, dict):
        return
    try:
        from .colors import normalize_cycle_lines_keys
        normalized = normalize_cycle_lines_keys(cycle_lines)
        if normalized is not cycle_lines and isinstance(cycle_lines, dict):
            cycle_lines.clear()
            cycle_lines.update(normalized)
    except Exception:
        pass
    def _apply_one_line_style(ln, style):
        if 'linewidth' in style:
            try:
                ln.set_linewidth(style['linewidth'])
            except Exception:
                pass
        if 'linestyle' in style:
            try:
                ln.set_linestyle(style['linestyle'])
                clear_dash_pattern(ln)
            except Exception:
                pass
        if style.get('dash_pattern'):
            restore_dash_pattern(ln, style['dash_pattern'])
        if 'marker' in style:
            try:
                ln.set_marker(style['marker'])
            except Exception:
                pass
        if 'markersize' in style:
            try:
                ln.set_markersize(style['markersize'])
            except Exception:
                pass
        if 'color' in style:
            try:
                apply_curve_color(ln, style['color'])
            except Exception:
                pass
        else:
            if 'markerfacecolor' in style:
                try:
                    ln.set_markerfacecolor(style['markerfacecolor'])
                except Exception:
                    pass
            if 'markeredgecolor' in style:
                try:
                    ln.set_markeredgecolor(style['markeredgecolor'])
                except Exception:
                    pass
        if 'alpha' in style:
            try:
                ln.set_alpha(style['alpha'])
            except Exception:
                pass
        if 'visible' in style:
            try:
                ln.set_visible(bool(style['visible']))
            except Exception:
                pass

    for cyc_key, entry in style_cfg.items():
        try:
            cyc = int(cyc_key)
        except Exception:
            cyc = cyc_key
        target = None
        if cyc in cycle_lines:
            target = cycle_lines[cyc]
        elif str(cyc_key) in cycle_lines:
            target = cycle_lines[str(cyc_key)]
        elif str(cyc) in cycle_lines:
            target = cycle_lines[str(cyc)]
        if target is None:
            continue
        if isinstance(target, dict):
            for role in ("charge", "discharge"):
                ln = target.get(role)
                style = entry.get(role) if isinstance(entry, dict) else None
                if ln is None or not isinstance(style, dict):
                    continue
                _apply_one_line_style(ln, style)
        else:
            ln = target
            style = None
            if isinstance(entry, dict):
                style = entry.get('line', entry)
            elif isinstance(entry, (list, tuple)):
                continue
            else:
                style = entry
            if ln is None or not isinstance(style, dict):
                continue
            _apply_one_line_style(ln, style)


def _print_style_snapshot(cfg: Dict):
    """Prints the style configuration in a user-friendly format matching operando style."""
    def _onoff(v):
        return 'ON ' if bool(v) else 'off'

    print("\n" + "=" * 60)
    print("  EC STYLE SUMMARY")
    print("=" * 60)
    print("Commands (Styles): f, l, k, t, h, g, d, sm | Geometries: c, r, x, y, a, ra")
    print()

    # ---- Canvas & Geometry (g) ----
    canvas_size = cfg.get('figure', {}).get('canvas_size', ['?', '?'])
    frame_size = cfg.get('figure', {}).get('frame_size', ['?', '?'])
    print("--- Canvas & Geometry ---")
    print(f"Canvas size (g): {canvas_size[0]:.3f} x {canvas_size[1]:.3f} in")
    print(f"Plot frame: {frame_size[0]:.3f} x {frame_size[1]:.3f} in")

    # ---- Font (f) ----
    font = cfg.get('font', {})
    print(f"\n--- Font (f) ---")
    print(f"Family='{font.get('family', '')}', size={font.get('size', '')}")

    # ---- Data axes (--ro) ----
    ro_active = bool(cfg.get('ro_active', False))
    rotation_angle = cfg.get('rotation_angle', 0)
    print(f"\n--- Data axes ---")
    print(f"Swapped via --ro: {'YES' if ro_active else 'no'}")
    if rotation_angle != 0:
        print(f"Rotation angle: {rotation_angle}°")

    # ---- Legend (h) ----
    leg_cfg = cfg.get('legend', {})
    if leg_cfg:
        leg_vis = bool(leg_cfg.get('visible', False))
        leg_pos = leg_cfg.get('position_inches')
        if isinstance(leg_pos, (list, tuple)) and len(leg_pos) == 2:
            try:
                lx = float(leg_pos[0])
                ly = float(leg_pos[1])
                pos_str = f"position=({lx:.3f}, {ly:.3f}) in (rel. center)"
            except Exception:
                pos_str = "position=stored"
        else:
            pos_str = "position=auto"
        print(f"\n--- Legend (h) ---")
        print(f"Visible: {'ON' if leg_vis else 'off'}, {pos_str}")
        legend_title = leg_cfg.get('title')
        if legend_title:
            print(f"Legend title: {legend_title}")

    # ---- Toggle spines (t) ----
    wasd = cfg.get('wasd_state', {})
    if wasd:
        print(f"\n--- Toggle spines (t) ---")
        print("WASD (w=top, a=left, s=bottom, d=right): 1=spine 2=ticks 3=minor 4=labels 5=title")
        for side_key, side_label in [('top', 'w'), ('left', 'a'), ('bottom', 's'), ('right', 'd')]:
            s = wasd.get(side_key, {})
            spine_val = _onoff(s.get('spine', False))
            major_val = _onoff(s.get('ticks', False))
            minor_val = _onoff(s.get('minor', False))
            labels_val = _onoff(s.get('labels', False))
            title_val = _onoff(s.get('title', False))
            print(f"  {side_label}1:{spine_val} {side_label}2:{major_val} {side_label}3:{minor_val} {side_label}4:{labels_val} {side_label}5:{title_val}")

    # ---- Line widths (l) ----
    tick_widths = cfg.get('ticks', {}).get('widths', {})
    x_maj = tick_widths.get('x_major')
    x_min = tick_widths.get('x_minor')
    y_maj = tick_widths.get('y_major')
    y_min = tick_widths.get('y_minor')
    spines = cfg.get('spines', {})
    frame_lw = spines.get('bottom', {}).get('linewidth', '?') if spines else '?'
    tick_direction = cfg.get('ticks', {}).get('direction', 'out')
    print(f"\n--- Line widths (l) ---")
    print(f"Frame: {frame_lw}")
    print(f"Ticks: X=({x_maj}, {x_min})  Y=({y_maj}, {y_min})")
    print(f"Tick direction: {tick_direction}")

    # ---- Spines (k) ----
    if spines:
        print("\n--- Spines (k) ---")
        for name in ('bottom', 'top', 'left', 'right'):
            props = spines.get(name, {})
            lw = props.get('linewidth', '?')
            vis = props.get('visible', False)
            col = props.get('color')
            try:
                col_disp = format_color_listing(col) if col is not None else "--"
            except Exception:
                col_disp = col
            print(f"  {name:<6} lw={lw} visible={vis} color={col_disp}")

    # ---- Grid ----
    grid_enabled = cfg.get('grid', False)
    print(f"\n--- Grid ---")
    print(f"Grid: {'on' if grid_enabled else 'off'}")

    # ---- Curves (c, l) ----
    curve_linewidth = cfg.get('curve_linewidth')
    curve_markers = cfg.get('curve_markers', {})
    if curve_linewidth is not None or curve_markers:
        print(f"\n--- Curves (c, l) ---")
        if curve_linewidth is not None:
            print(f"Curve linewidth: {curve_linewidth:.3g}")
        if curve_markers:
            ls = curve_markers.get('linestyle', '-')
            mk = curve_markers.get('marker', 'None')
            ms = curve_markers.get('markersize', 0)
            print(f"Curve style: linestyle={ls} marker={mk} markersize={ms}")

    cycle_styles = cfg.get('cycle_styles', {})
    if cycle_styles:
        print("\n--- Cycle colors (c) ---")
        def _cycle_sort_key(key):
            try:
                return int(key)
            except Exception:
                return key
        for cyc_key in sorted(cycle_styles.keys(), key=_cycle_sort_key):
            entry = cycle_styles[cyc_key] or {}
            segments = []
            for role_label, role_key in (('charge', 'charge'), ('discharge', 'discharge'), ('line', 'line')):
                style = entry.get(role_key)
                if not isinstance(style, dict):
                    continue
                color = style.get('color', 'unknown')
                vis = 'ON' if style.get('visible', True) else 'off'
                # Show color block for better visualization
                try:
                    color_block_str = format_color_listing(color) if color != 'unknown' else ''
                    segments.append(f"{role_label}={color_block_str} ({vis})")
                except Exception:
                    segments.append(f"{role_label}={color} ({vis})")
            if segments:
                print(f"  Cycle {cyc_key}: {', '.join(segments)}")

    # ---- Legend file order (ra, multi-file) ----
    legend_order = cfg.get('legend_file_order')
    if legend_order and isinstance(legend_order, (list, tuple)):
        print("\n--- Legend order (ra) ---")
        print(f"Order: {[i+1 for i in legend_order]}")

    print("=" * 60 + "\n")


def _export_style_dialog(cfg: Dict, default_ext: str = '.bpcfg', base_path: Optional[str] = None):
    """Handles the dialog for exporting a style configuration to a file.
    
    Args:
        cfg: Configuration dictionary to export
        default_ext: Default file extension ('.bps' for style-only, '.bpsg' for style+geometry)
    """
    try:
        if base_path:
            print(f"\nChosen path: {base_path}")
        # List files with matching extension in Styles/ subdirectory
        file_list = list_files_in_subdirectory((default_ext, '.bpcfg'), 'style', base_path=base_path)
        bpcfg_files = [f[0] for f in file_list]
        if bpcfg_files:
            styles_root = base_path if base_path else os.getcwd()
            styles_dir = os.path.join(styles_root, 'Styles')
            print(f"Existing {default_ext} files in {styles_dir}:")
            for i, f in enumerate(bpcfg_files, 1):
                print(f"  \033[96m{i}\033[0m: {f}")
        
        n_files = len(bpcfg_files)
        exp_prompt = _colorize_option_keys(f"filename, 1-{n_files}: overwrite, q: cancel") if n_files else _colorize_option_keys("filename, q: cancel")
        choice = _safe_input(f"Export to file? ({exp_prompt}): ").strip()
        if not choice or choice.lower() == 'q':
            return

        target_path = ""
        if choice.isdigit() and bpcfg_files and 1 <= int(choice) <= len(bpcfg_files):
            target_path = file_list[int(choice) - 1][1]  # Full path from list
            if not _confirm_overwrite(target_path):
                return
        else:
            # Add default extension if no extension provided
            if not any(choice.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                filename_with_ext = f"{choice}{default_ext}"
            else:
                filename_with_ext = choice
            
            # Use organized path unless it's an absolute path
            if os.path.isabs(filename_with_ext):
                target_path = filename_with_ext
            else:
                target_path = get_organized_path(filename_with_ext, 'style', base_path=base_path)
            
            if not _confirm_overwrite(target_path):
                return
        
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Style exported to {target_path}")
        return target_path

    except Exception as e:
        print(f"Export failed: {e}")
        return None
