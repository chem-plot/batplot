"""CPC session dump/load (mode-owned implementation).

Moved from :mod:`batplot.session` to keep the root session module as a thin
compatibility facade. Shared helpers remain in ``batplot.session`` and are
imported here to avoid duplicating version/tick/bbox logic.
"""

from __future__ import annotations

import os
import pickle
import traceback
from typing import Any, Dict, cast

import numpy as np  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.colors import to_hex  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    AutoMinorLocator,
    NullFormatter,
    NullLocator,
)

from ...utils import _confirm_overwrite
from ...ui import (
    set_spine_side_color as _set_spine_side_color,
    finalize_spine_colors_cpc,
)
from ..common.font_extras import apply_session_font_cfg, merge_session_font_dump
from ..common.session_helpers import (
    _try_extract_version_from_pickle,
    _package_versions_stamp,
    _get_current_numpy_version,
    _current_tick_width,
    _current_tick_length,
    _apply_session_tick_lengths,
    _apply_axes_bbox,
    _capture_session_tick_locator,
    _restore_session_tick_locator,
)


# --------------------- CPC (Capacity-Per-Cycle) session helpers -----------------

def dump_cpc_session(
    filename: str,
    *,
    fig,
    ax,
    ax2,
    sc_charge,
    sc_discharge,
    sc_eff,
    file_data=None,
    skip_confirm: bool = False,
):
    """Serialize CPC plot including scatter data, styles, axes, and legend position.

    Stores arrays for charge/discharge capacities and efficiency vs cycle number,
    marker styles, axis labels/limits, figure size/dpi, legend position, WASD states,
    tick widths, spines, frame size, and all visual styling.
    
    Args:
        file_data: Optional list of multi-file data dictionaries
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).
    """
    try:
        fig_w, fig_h = map(float, fig.get_size_inches())
        dpi = int(fig.dpi)
        
        # Extract scatter data
        def _scatter_xy(sc):
            try:
                offs = sc.get_offsets()
                arr = np.asarray(offs, float)
                if arr.ndim == 2 and arr.shape[1] >= 2:
                    return np.array(arr[:,0], float), np.array(arr[:,1], float)
            except Exception:
                pass
            return np.array([]), np.array([])
        x_c, y_c = _scatter_xy(sc_charge)
        x_d, y_d = _scatter_xy(sc_discharge)
        x_e, y_e = _scatter_xy(sc_eff)
        
        # Colors and sizes (for hollow markers use edgecolor)
        def _color_and_hollow(sc):
            """Return (color_hex, is_hollow). For hollow scatter use edgecolor."""
            try:
                fc = getattr(sc, 'get_facecolors', lambda: None)()
                ec = getattr(sc, 'get_edgecolors', lambda: None)()
                is_hollow = False
                if fc is not None and len(fc):
                    a = fc[0]
                    if len(a) >= 4 and (a[3] == 0 or (hasattr(a[3], '__float__') and float(a[3]) < 0.01)):
                        is_hollow = True
                else:
                    # facecolors='none' returns empty array; use edgecolor as hollow
                    if ec is not None and len(ec):
                        is_hollow = True
                if is_hollow and ec is not None and len(ec):
                    return (to_hex(ec[0]), True)
                if fc is not None and len(fc):
                    return (to_hex(fc[0]), False)
                c = getattr(sc, 'get_color', lambda: None)()
                if c is not None:
                    if isinstance(c, (list, tuple)) and c and not isinstance(c, str):
                        return (to_hex(c[0]), False)
                    try:
                        return (to_hex(cast(Any, c)), False)
                    except Exception:
                        return (c, False)
            except Exception:
                pass
            return (None, False)

        def _color_of(sc):
            col, _ = _color_and_hollow(sc)
            return col
        
        def _size_of(sc, default=32.0):
            try:
                arr = sc.get_sizes()
                if arr is not None and len(arr):
                    return float(arr[0])
            except Exception:
                pass
            return float(default)
        
        # Axes frame size (in inches)
        bbox = ax.get_position()
        frame_w_in = bbox.width * fig_w
        frame_h_in = bbox.height * fig_h
        
        # Save spines state for both ax and ax2
        spines_state = {}
        for name, sp in ax.spines.items():
            spines_state[f'ax_{name}'] = {
                'linewidth': sp.get_linewidth(),
                'color': sp.get_edgecolor(),
                'visible': sp.get_visible(),
            }
        for name, sp in ax2.spines.items():
            spines_state[f'ax2_{name}'] = {
                'linewidth': sp.get_linewidth(),
                'color': sp.get_edgecolor(),
                'visible': sp.get_visible(),
            }
        
        # Helper to capture tick widths
        def _tick_width(axis, which: str):
            return _current_tick_width(axis, which)
        
        tick_widths = {
            'x_major': _tick_width(ax.xaxis, 'major'),
            'x_minor': _tick_width(ax.xaxis, 'minor'),
            'ly_major': _tick_width(ax.yaxis, 'major'),
            'ly_minor': _tick_width(ax.yaxis, 'minor'),
            'ry_major': _tick_width(ax2.yaxis, 'major'),
            'ry_minor': _tick_width(ax2.yaxis, 'minor'),
        }
        tick_lengths = {
            'x_major': _current_tick_length(ax.xaxis, 'major'),
            'x_minor': _current_tick_length(ax.xaxis, 'minor'),
            'ly_major': _current_tick_length(ax.yaxis, 'major'),
            'ly_minor': _current_tick_length(ax.yaxis, 'minor'),
            'ry_major': _current_tick_length(ax2.yaxis, 'major'),
            'ry_minor': _current_tick_length(ax2.yaxis, 'minor'),
        }
        
        # Subplot margins
        sp = fig.subplotpars
        subplot_margins = {
            'left': float(sp.left),
            'right': float(sp.right),
            'bottom': float(sp.bottom),
            'top': float(sp.top),
        }
        
        # Capture WASD state: start from figure attr when present, then reconcile with
        # current axes + saved tick keys so every save path stays accurate.
        wasd_state_raw = getattr(fig, '_cpc_wasd_state', None)
        wasd_state: Dict[str, Any] = wasd_state_raw if isinstance(wasd_state_raw, dict) else {}
        ts = dict(getattr(ax, '_saved_tick_state', {}) or {})
        def _merged_side(side_name, default_ticks, default_labels, default_spine, default_minor):
            side_state = wasd_state.get(side_name, {})
            s = side_state if isinstance(side_state, dict) else {}
            alias_map = {'top': 'tx', 'bottom': 'bx', 'left': 'ly', 'right': 'ry'}
            prefix_map = {'top': 't', 'bottom': 'b', 'left': 'l', 'right': 'r'}
            pref = prefix_map[side_name]
            tick_default = bool(s.get('ticks', default_ticks))
            label_default = bool(s.get('labels', default_labels))
            return {
                'spine': bool(s.get('spine', default_spine)),
                'ticks': bool(ts.get(f'{pref}_ticks', ts.get(alias_map[side_name], tick_default))),
                'minor': bool(ts.get(f'm{pref}x' if pref in ('t', 'b') else f'm{pref}y',
                                     s.get('minor', default_minor))),
                'labels': bool(ts.get(f'{pref}_labels', ts.get(alias_map[side_name], label_default))),
                'title': bool(s.get('title', True)),
            }
        wasd_state = {
            'top': _merged_side(
                'top',
                default_ticks=False,
                default_labels=False,
                default_spine=bool(ax.spines.get('top').get_visible() if ax.spines.get('top') else False),
                default_minor=False,
            ),
            'bottom': _merged_side(
                'bottom',
                default_ticks=True,
                default_labels=True,
                default_spine=bool(ax.spines.get('bottom').get_visible() if ax.spines.get('bottom') else True),
                default_minor=False,
            ),
            'left': _merged_side(
                'left',
                default_ticks=True,
                default_labels=True,
                default_spine=bool(ax.spines.get('left').get_visible() if ax.spines.get('left') else True),
                default_minor=False,
            ),
            'right': _merged_side(
                'right',
                default_ticks=True,
                default_labels=True,
                default_spine=bool(ax2.spines.get('right').get_visible() if ax2.spines.get('right') else True),
                default_minor=False,
            ),
        }
        # Titles and spines should reflect current figure at save time.
        wasd_state['top']['title'] = bool(
            getattr(ax, '_top_xlabel_text', None) and getattr(ax, '_top_xlabel_text').get_visible()
        )
        wasd_state['bottom']['title'] = bool(ax.get_xlabel())
        wasd_state['left']['title'] = bool(ax.get_ylabel())
        wasd_state['right']['title'] = bool(ax2.yaxis.get_label().get_text()) and bool(sc_eff.get_visible())
        wasd_state['top']['spine'] = bool(ax.spines.get('top').get_visible() if ax.spines.get('top') else False)
        wasd_state['bottom']['spine'] = bool(ax.spines.get('bottom').get_visible() if ax.spines.get('bottom') else True)
        wasd_state['left']['spine'] = bool(ax.spines.get('left').get_visible() if ax.spines.get('left') else True)
        wasd_state['right']['spine'] = bool(ax2.spines.get('right').get_visible() if ax2.spines.get('right') else True)
        
        # Capture stored title texts
        stored_titles = {
            'xlabel': getattr(ax, '_stored_xlabel', ax.get_xlabel()),
            'ylabel': getattr(ax, '_stored_ylabel', ax.get_ylabel()),
            'top_xlabel': getattr(ax, '_stored_top_xlabel', ''),
            'right_ylabel': getattr(ax2, '_stored_ylabel', ax2.get_ylabel()),
        }
        # Title offsets
        title_offsets = {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax2, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax2, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        }
        
        meta = {
            'kind': 'cpc',
            'version': 2,  # Incremented version for new format
            'figure': {
                'size': (fig_w, fig_h),
                'dpi': dpi,
                'frame_size': (frame_w_in, frame_h_in),
                'axes_bbox': {
                    'left': float(bbox.x0),
                    'bottom': float(bbox.y0),
                    'right': float(bbox.x0 + bbox.width),
                    'top': float(bbox.y0 + bbox.height),
                },
                'subplot_margins': subplot_margins,
                'spines': spines_state,
            },
            'axis': {
                'xlabel': ax.get_xlabel(),
                'ylabel_left': ax.get_ylabel(),
                'ylabel_right': ax2.get_ylabel(),
                'xlim': tuple(map(float, ax.get_xlim())),
                'ylim_left': tuple(map(float, ax.get_ylim())),
                'ylim_right': tuple(map(float, ax2.get_ylim())),
                'x_labelpad': float(getattr(ax.xaxis, 'labelpad', 0.0) or 0.0),
                'y_left_labelpad': float(getattr(ax.yaxis, 'labelpad', 0.0) or 0.0),
                'y_right_labelpad': float(getattr(ax2.yaxis, 'labelpad', 0.0) or 0.0),
            },
            'series': (lambda ch=_color_and_hollow(sc_charge), dh=_color_and_hollow(sc_discharge), ef=_color_and_hollow(sc_eff): {
                'charge': {
                    'x': x_c, 'y': y_c,
                    'color': ch[0],
                    'hollow': ch[1],
                    'size': _size_of(sc_charge, 32.0),
                    'alpha': (float(sc_charge.get_alpha()) if sc_charge.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_charge, 'get_visible', lambda: True)()),
                    'label': getattr(sc_charge, 'get_label', lambda: 'Charge capacity')() or 'Charge capacity',
                    'marker': 's',  # CPC default: square for capacity
                },
                'discharge': {
                    'x': x_d, 'y': y_d,
                    'color': dh[0],
                    'hollow': dh[1],
                    'size': _size_of(sc_discharge, 32.0),
                    'alpha': (float(sc_discharge.get_alpha()) if sc_discharge.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_discharge, 'get_visible', lambda: True)()),
                    'label': getattr(sc_discharge, 'get_label', lambda: 'Discharge capacity')() or 'Discharge capacity',
                    'marker': 's',  # CPC default: square for capacity
                },
                'efficiency': {
                    'x': x_e, 'y': y_e,
                    'color': ef[0] or '#2ca02c',
                    'hollow': ef[1],
                    'size': _size_of(sc_eff, 40.0),
                    'alpha': (float(sc_eff.get_alpha()) if sc_eff.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_eff, 'get_visible', lambda: True)()),
                    'label': getattr(sc_eff, 'get_label', lambda: 'Coulombic efficiency')() or 'Coulombic efficiency',
                    'marker': '^',  # CPC default: triangle for efficiency
                },
            })(),
            'legend': {
                'xy_in': getattr(fig, '_cpc_legend_xy_in', None),
                'visible': (
                    bool((ax.get_legend() or ax2.get_legend()).get_visible())
                    if (ax.get_legend() is not None or ax2.get_legend() is not None)
                    else False
                ),
                'title': getattr(fig, '_cpc_legend_title', None),
            },
            'wasd_state': wasd_state,
            'tick_widths': tick_widths,
            'tick_lengths': tick_lengths,
            'tick_direction': getattr(fig, '_tick_direction', 'out'),
            'tick_locator_state_ax': _capture_session_tick_locator(ax),
            'tick_locator_state_ax2': _capture_session_tick_locator(ax2),
            'stored_titles': stored_titles,
            'title_offsets': title_offsets,
            'font': merge_session_font_dump(fig, include_mathtext=False),
            'grid': ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else (
                any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()) if hasattr(ax, 'get_xgridlines') else False
            ),
            'display_mode': getattr(fig, '_cpc_display_mode', 'both'),
            'spine_colors_auto': bool(getattr(fig, '_cpc_spine_auto', False)),
            'ro_active': bool(getattr(fig, '_ro_active', False)),
        }
        
        # Add multi-file data if available
        if file_data and isinstance(file_data, list) and len(file_data) > 0:
            multi_files = []
            for f in file_data:
                def _marker_of(sc, default_val):
                    # PathCollection (scatter) has no get_marker(); use CPC defaults: s=square, ^=triangle
                    try:
                        m = getattr(sc, 'get_marker', lambda: default_val)()
                        if m is None:
                            return default_val
                        return m
                    except Exception:
                        return default_val
                def _alpha_of(sc, default_val=None):
                    try:
                        a = sc.get_alpha()
                        return float(a) if a is not None else default_val
                    except Exception:
                        return default_val
                def _visible_of(sc, default_val=True):
                    try:
                        return bool(sc.get_visible())
                    except Exception:
                        return default_val
                def _label_of(sc, default_val=""):
                    try:
                        return sc.get_label() or default_val
                    except Exception:
                        return default_val
                sc_ch = f.get('sc_charge', sc_charge)
                sc_dh = f.get('sc_discharge', sc_discharge)
                sc_ef = f.get('sc_eff', sc_eff)
                ch_col, ch_hollow = _color_and_hollow(sc_ch)
                dh_col, dh_hollow = _color_and_hollow(sc_dh)
                ef_col, ef_hollow = _color_and_hollow(sc_ef)
                file_info = {
                    'filename': f.get('filename', 'unknown'),
                    'display_name': f.get('display_name', f.get('filename', 'unknown')),
                    'visible': f.get('visible', True),
                    'charge': {
                        'x': np.array(_scatter_xy(sc_ch)[0]),
                        'y': np.array(_scatter_xy(sc_ch)[1]),
                        'color': ch_col,
                        'hollow': ch_hollow,
                        'size': _size_of(sc_ch, 32.0),
                        'alpha': _alpha_of(sc_ch),
                        'marker': _marker_of(sc_ch, 's'),
                        'label': _label_of(sc_ch, 'Charge capacity'),
                        'visible': _visible_of(sc_ch),
                    },
                    'discharge': {
                        'x': np.array(_scatter_xy(sc_dh)[0]),
                        'y': np.array(_scatter_xy(sc_dh)[1]),
                        'color': dh_col,
                        'hollow': dh_hollow,
                        'size': _size_of(sc_dh, 32.0),
                        'alpha': _alpha_of(sc_dh),
                        'marker': _marker_of(sc_dh, 's'),
                        'label': _label_of(sc_dh, 'Discharge capacity'),
                        'visible': _visible_of(sc_dh),
                    },
                    'efficiency': {
                        'x': np.array(_scatter_xy(sc_ef)[0]),
                        'y': np.array(_scatter_xy(sc_ef)[1]),
                        'color': ef_col,
                        'hollow': ef_hollow,
                        'size': _size_of(sc_ef, 40.0),
                        'alpha': _alpha_of(sc_ef),
                        'marker': _marker_of(sc_ef, '^'),
                        'label': _label_of(sc_ef, 'Coulombic efficiency'),
                        'visible': _visible_of(sc_ef),
                    }
                }
                multi_files.append(file_info)
            meta['multi_files'] = multi_files
        
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("CPC session save canceled.")
                return
        meta['package_versions'] = _package_versions_stamp()
        with open(target, 'wb') as f:
            pickle.dump(meta, f)
        print(f"CPC session saved to {target}")
    except Exception as e:
        print(f"Error saving CPC session: {e}")


def load_cpc_session(filename: str):
    """Load a CPC session and reconstruct fig, axes, scatter artists, and file_data.

    Returns: (fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
    """
    try:
        with open(filename, 'rb') as f:
            sess = pickle.load(f)
    except ModuleNotFoundError as e:
        # Handle numpy._core and other module import errors
        if '_core' in str(e) or 'numpy' in str(e).lower():
            # Try to extract version info before the error
            saved_versions = _try_extract_version_from_pickle(filename)
            current_numpy = _get_current_numpy_version()
            
            saved_numpy = saved_versions.get('numpy', 'unknown')
            
            print(f"\nERROR: NumPy version mismatch detected when loading: {filename}")
            print("This session was saved with a different NumPy version.")
            print()
            print(f"Session was saved with:  NumPy {saved_numpy}")
            print(f"Currently installed:     NumPy {current_numpy}")
            print()
            print("The error 'No module named numpy._core' indicates:")
            print("  - Session saved with NumPy 2.0+ but loading with NumPy <2.0, OR")
            print("  - Session saved with NumPy <2.0 but loading with NumPy 2.0+")
            print()
            print("Solutions:")
            if saved_numpy != 'unknown':
                print(f"  1. Install matching version: pip install 'numpy=={saved_numpy}'")
            else:
                print("  1. Try installing NumPy <2.0: pip install 'numpy<2.0'")
                print("     OR try installing NumPy 2.0+: pip install 'numpy>=2.0'")
            print("  2. Recreate the session from original data files")
        else:
            print(f"\nERROR: Module import error when loading: {filename}")
            print(f"Error: {e}")
            print("This usually indicates a package version mismatch.")
        return None
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None
    if not isinstance(sess, dict) or sess.get('kind') != 'cpc':
        print("Not a CPC session file.")
        return None
    try:
        # Use standard DPI of 100 instead of saved DPI to avoid display-dependent issues
        # (Retina displays, Windows scaling, etc. can cause saved DPI to differ)
        fig = plt.figure(figsize=tuple(sess['figure']['size']), dpi=100)
        # Seed last-session path so 'os' overwrite command is available immediately
        try:
            fig._last_session_save_path = os.path.abspath(filename)
        except Exception:
            pass
        # Disable auto layout
        try:
            fig.set_layout_engine('none')
        except Exception:
            try:
                fig.set_tight_layout(False)
            except Exception:
                pass
        ax = fig.add_subplot(111)
        ax2 = ax.twinx()
        try:
            fig._ro_active = bool(sess.get('ro_active', False))
        except Exception:
            pass
        # Fonts
        try:
            f = sess.get('font', {})
            if f.get('chain'):
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['font.sans-serif'] = f['chain']
            if f.get('size'):
                plt.rcParams['font.size'] = f['size']
        except Exception:
            pass
        # Labels and limits
        ax_meta = sess.get('axis', {})
        try:
            ax.set_xlabel(ax_meta.get('xlabel') or 'Cycle number')
            ax.set_ylabel(ax_meta.get('ylabel_left') or r'Specific Capacity (mAh g$^{-1}$)')
            ax2.set_ylabel(ax_meta.get('ylabel_right') or 'Efficiency (%)')
            if ax_meta.get('xlim'): ax.set_xlim(*ax_meta['xlim'])
            if ax_meta.get('ylim_left'): ax.set_ylim(*ax_meta['ylim_left'])
            if ax_meta.get('ylim_right'): ax2.set_ylim(*ax_meta['ylim_right'])
            # Label pads
            try:
                lp = ax_meta.get('x_labelpad')
                if lp is not None:
                    ax.set_xlabel(ax_meta.get('xlabel') or 'Cycle number', labelpad=float(lp))
            except Exception:
                pass
            try:
                lp = ax_meta.get('y_left_labelpad')
                if lp is not None:
                    ax.set_ylabel(ax_meta.get('ylabel_left') or r'Specific Capacity (mAh g$^{-1}$)', labelpad=float(lp))
            except Exception:
                pass
            try:
                lp = ax_meta.get('y_right_labelpad')
                if lp is not None:
                    ax2.set_ylabel(ax_meta.get('ylabel_right') or 'Efficiency (%)', labelpad=float(lp))
            except Exception:
                pass
        except Exception:
            pass
        # Series
        sr = sess.get('series', {})
        ch = sr.get('charge', {})
        dh = sr.get('discharge', {})
        ef = sr.get('efficiency', {})
        def _mk_sc(axX, rec, default_marker='o'):
            x_val = rec.get('x')
            x = np.asarray(x_val if x_val is not None else [], float)
            y_val = rec.get('y')
            y = np.asarray(y_val if y_val is not None else [], float)
            col = rec.get('color') or 'tab:blue'
            s = float(rec.get('size', 32.0) or 32.0)
            alpha = rec.get('alpha', None)
            marker = rec.get('marker', default_marker)
            lab = rec.get('label') or ''
            hollow = bool(rec.get('hollow', False))
            if hollow:
                sc = axX.scatter(x, y, facecolors='none', edgecolors=col, s=s, alpha=alpha,
                                 marker=marker, label=lab, zorder=3, linewidths=1.2)
            else:
                sc = axX.scatter(x, y, color=col, s=s, alpha=alpha, marker=marker, label=lab, zorder=3)
            try:
                sc.set_visible(bool(rec.get('visible', True)))
            except Exception:
                pass
            return sc
        # If multi_files exist, rebuild all files and pick the first as primary
        multi_files = sess.get('multi_files')
        file_data = []
        if multi_files and isinstance(multi_files, list) and len(multi_files) > 0:
            for idx, finfo in enumerate(multi_files):
                ch_info = finfo.get('charge', {})
                dh_info = finfo.get('discharge', {})
                ef_info = finfo.get('efficiency', {})
                _ch_m = ch_info.get('marker') or 's'
                if _ch_m == 'o':  # Legacy: PathCollection has no get_marker, old sessions saved 'o'
                    _ch_m = 's'
                sc_ch = _mk_sc(ax, ch_info, _ch_m)
                _dh_m = dh_info.get('marker') or 's'
                if _dh_m == 'o':
                    _dh_m = 's'
                sc_dh = _mk_sc(ax, dh_info, _dh_m)
                eff_marker = ef_info.get('marker', '^') or '^'
                sc_ef = _mk_sc(ax2, ef_info, eff_marker)
                # Respect overall file visibility
                try:
                    vis_file = bool(finfo.get('visible', True))
                except Exception:
                    vis_file = True
                for sc_tmp in (sc_ch, sc_dh, sc_ef):
                    try:
                        sc_tmp.set_visible(sc_tmp.get_visible() and vis_file)
                    except Exception:
                        pass
                ef_col = ef_info.get('color')
                file_data.append({
                    'filename': finfo.get('filename', f'File {idx+1}'),
                    'display_name': finfo.get('display_name', finfo.get('filename', f'File {idx+1}')),
                    'visible': vis_file,
                    'sc_charge': sc_ch,
                    'sc_discharge': sc_dh,
                    'sc_eff': sc_ef,
                    'eff_color': ef_col,
                })
            # Use the first file as primary artists for interactive menu
            sc_charge = file_data[0]['sc_charge']
            sc_discharge = file_data[0]['sc_discharge']
            sc_eff = file_data[0]['sc_eff']
            try:
                fig._cpc_is_multi_file = True
            except Exception:
                pass
            # Restore display_mode (charge/discharge/both)
            dm = sess.get('display_mode', 'both')
            if dm in ('charge', 'discharge', 'both'):
                try:
                    fig._cpc_display_mode = dm
                    for f in file_data:
                        sc_c = f.get('sc_charge')
                        sc_d = f.get('sc_discharge')
                        file_vis = bool(f.get('visible', True))
                        if sc_c is not None:
                            sc_c.set_visible(file_vis and (dm in ('charge', 'both')))
                        if sc_d is not None:
                            sc_d.set_visible(file_vis and (dm in ('discharge', 'both')))
                except Exception:
                    pass
        else:
            # No multi-file info: fall back to single-file series
            _ch_m = ch.get('marker') or 's'
            if _ch_m == 'o':
                _ch_m = 's'
            _dh_m = dh.get('marker') or 's'
            if _dh_m == 'o':
                _dh_m = 's'
            sc_charge = _mk_sc(ax, ch, _ch_m)
            sc_discharge = _mk_sc(ax, dh, _dh_m)
            if 'marker' not in ef:
                ef['marker'] = '^'
            sc_eff = _mk_sc(ax2, ef, '^')
            file_data = None
            try:
                fig._cpc_is_multi_file = False
            except Exception:
                pass
            # Restore display_mode for single-file
            dm = sess.get('display_mode', 'both')
            if dm in ('charge', 'discharge', 'both'):
                try:
                    fig._cpc_display_mode = dm
                    sc_charge.set_visible(dm in ('charge', 'both'))
                    sc_discharge.set_visible(dm in ('discharge', 'both'))
                except Exception:
                    pass
        
        # Restore spines state (version 2+)
        try:
            if not hasattr(fig, '_cpc_spine_colors') or not isinstance(fig._cpc_spine_colors, dict):
                fig._cpc_spine_colors = {}
            fig._cpc_spine_auto = bool(sess.get('spine_colors_auto', False))
            fig_meta = sess.get('figure', {})
            spines_state = fig_meta.get('spines', {})
            for key, props in spines_state.items():
                if key.startswith('ax_'):
                    name = key[3:]  # Remove 'ax_' prefix
                    if name in ax.spines:
                        sp = ax.spines[name]
                        if 'linewidth' in props:
                            sp.set_linewidth(props['linewidth'])
                        if 'color' in props:
                            try:
                                _set_spine_side_color(ax, name, props['color'], fig=fig)
                            except Exception:
                                pass
                            fig._cpc_spine_colors[name] = props['color']
                        if 'visible' in props:
                            sp.set_visible(props['visible'])
                elif key.startswith('ax2_'):
                    name = key[4:]  # Remove 'ax2_' prefix
                    if name in ax2.spines:
                        sp = ax2.spines[name]
                        if 'linewidth' in props:
                            sp.set_linewidth(props['linewidth'])
                        if 'color' in props:
                            try:
                                _set_spine_side_color(ax2, name, props['color'], fig=fig)
                            except Exception:
                                pass
                            fig._cpc_spine_colors['right' if name == 'right' else name] = props['color']
                        if 'visible' in props:
                            sp.set_visible(props['visible'])
        except Exception:
            pass
        
        # Restore tick widths (version 2+)
        try:
            tick_widths = sess.get('tick_widths', {})
            if tick_widths.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=tick_widths['x_major'])
            if tick_widths.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=tick_widths['x_minor'])
            if tick_widths.get('ly_major') is not None:
                ax.tick_params(axis='y', which='major', width=tick_widths['ly_major'])
            if tick_widths.get('ly_minor') is not None:
                ax.tick_params(axis='y', which='minor', width=tick_widths['ly_minor'])
            if tick_widths.get('ry_major') is not None:
                ax2.tick_params(axis='y', which='major', width=tick_widths['ry_major'])
            if tick_widths.get('ry_minor') is not None:
                ax2.tick_params(axis='y', which='minor', width=tick_widths['ry_minor'])
        except Exception:
            pass
        _apply_session_tick_lengths(fig, [ax, ax2], sess.get('tick_lengths'))
        
        # Restore tick direction (version 2+)
        try:
            tick_direction = sess.get('tick_direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
                ax2.tick_params(axis='both', which='both', direction=tick_direction)
        except Exception:
            pass

        # Restore grid state
        try:
            grid_enabled = sess.get('grid', False)
            if grid_enabled:
                ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
            else:
                ax.grid(False)
        except Exception:
            pass
        
        # Restore subplot margins/frame size (version 2+)
        try:
            fig_meta = sess.get('figure', {})
            margins = fig_meta.get('subplot_margins', {})
            if margins is not None and isinstance(margins, dict):
                fig.subplots_adjust(
                    left=margins.get('left', 0.125),
                    right=margins.get('right', 0.9),
                    bottom=margins.get('bottom', 0.11),
                    top=margins.get('top', 0.88)
                )
            axes_bbox = fig_meta.get('axes_bbox')
            applied_axes_bbox = _apply_axes_bbox(ax, axes_bbox)
            if applied_axes_bbox:
                try:
                    ax2.set_position(ax.get_position())
                except Exception:
                    pass

            # Restore exact frame size if stored (for precision)
            frame_size = fig_meta.get('frame_size')
            if (not applied_axes_bbox) and frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                target_w_in, target_h_in = map(float, frame_size)
                # Get current canvas size
                canvas_w_in, canvas_h_in = fig.get_size_inches()
                # Calculate needed fractions to achieve exact frame size
                if canvas_w_in > 0 and canvas_h_in > 0:
                    # Get current position to preserve centering
                    bbox = ax.get_position()
                    center_x = (bbox.x0 + bbox.x1) / 2.0
                    center_y = (bbox.y0 + bbox.y1) / 2.0
                    # Calculate new fractions
                    new_w_frac = target_w_in / canvas_w_in
                    new_h_frac = target_h_in / canvas_h_in
                    # Reposition to maintain centering
                    new_left = center_x - new_w_frac / 2.0
                    new_right = center_x + new_w_frac / 2.0
                    new_bottom = center_y - new_h_frac / 2.0
                    new_top = center_y + new_h_frac / 2.0
                    # Apply
                    fig.subplots_adjust(left=new_left, right=new_right, bottom=new_bottom, top=new_top)
        except Exception:
            pass
        
        # Restore WASD state (version 2+)
        try:
            wasd_state = sess.get('wasd_state', {})
            if wasd_state is not None and isinstance(wasd_state, dict) and wasd_state:
                # Store on figure for interactive menu
                fig._cpc_wasd_state = wasd_state
                
                # Apply WASD state
                
                # Spines
                if 'top' in wasd_state:
                    ax.spines['top'].set_visible(wasd_state['top'].get('spine', False))
                    ax2.spines['top'].set_visible(wasd_state['top'].get('spine', False))
                if 'bottom' in wasd_state:
                    ax.spines['bottom'].set_visible(wasd_state['bottom'].get('spine', True))
                    ax2.spines['bottom'].set_visible(wasd_state['bottom'].get('spine', True))
                if 'left' in wasd_state:
                    ax.spines['left'].set_visible(wasd_state['left'].get('spine', True))
                if 'right' in wasd_state:
                    ax2.spines['right'].set_visible(wasd_state['right'].get('spine', True))
                
                # Tick visibility
                if 'top' in wasd_state and 'bottom' in wasd_state:
                    ax.tick_params(axis='x',
                                   top=wasd_state['top'].get('ticks', False),
                                   bottom=wasd_state['bottom'].get('ticks', True),
                                   labeltop=wasd_state['top'].get('labels', False),
                                   labelbottom=wasd_state['bottom'].get('labels', True))
                if 'left' in wasd_state:
                    ax.tick_params(axis='y',
                                   left=wasd_state['left'].get('ticks', True),
                                   labelleft=wasd_state['left'].get('labels', True))
                if 'right' in wasd_state:
                    ax2.tick_params(axis='y',
                                    right=wasd_state['right'].get('ticks', True),
                                    labelright=wasd_state['right'].get('labels', True))
                # Axis title visibility
                try:
                    if 'bottom' in wasd_state:
                        ax.xaxis.label.set_visible(bool(wasd_state['bottom'].get('title', True)))
                    if 'left' in wasd_state:
                        ax.yaxis.label.set_visible(bool(wasd_state['left'].get('title', True)))
                    if 'right' in wasd_state:
                        ax2.yaxis.label.set_visible(bool(wasd_state['right'].get('title', True)))
                except Exception:
                    pass
                
                # Minor ticks (x/left on ax; right on ax2)
                top_m = bool(wasd_state.get('top', {}).get('minor', False))
                bot_m = bool(wasd_state.get('bottom', {}).get('minor', False))
                if top_m or bot_m:
                    ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                else:
                    ax.xaxis.set_minor_locator(NullLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor', top=top_m, bottom=bot_m)
                left_m = bool(wasd_state.get('left', {}).get('minor', False))
                if left_m:
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                else:
                    ax.yaxis.set_minor_locator(NullLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor', left=left_m, right=False)
                right_m = bool(wasd_state.get('right', {}).get('minor', False))
                if right_m:
                    ax2.yaxis.set_minor_locator(AutoMinorLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                else:
                    ax2.yaxis.set_minor_locator(NullLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                ax2.tick_params(axis='y', which='minor', right=right_m, left=False)
                # Store tick_state on axes for interactive menu
                tick_state = {}
                for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                    s = wasd_state.get(side_key, {})
                    tick_state[f'{prefix}_ticks'] = bool(s.get('ticks', side_key in ('bottom', 'left')))
                    tick_state[f'{prefix}_labels'] = bool(s.get('labels', side_key in ('bottom', 'left')))
                    tick_state[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                # Legacy keys
                tick_state['bx'] = tick_state.get('b_ticks', True)
                tick_state['tx'] = tick_state.get('t_ticks', False)
                tick_state['ly'] = tick_state.get('l_ticks', True)
                tick_state['ry'] = tick_state.get('r_ticks', True)  # CPC has right axis
                tick_state['mbx'] = tick_state.get('mbx', False)
                tick_state['mtx'] = tick_state.get('mtx', False)
                tick_state['mly'] = tick_state.get('mly', False)
                tick_state['mry'] = tick_state.get('mry', False)
                ax._saved_tick_state = tick_state
        except Exception:
            pass

        # Restore tick locator spacing after WASD, then re-sync minor visibility
        try:
            _restore_session_tick_locator(ax, sess.get('tick_locator_state_ax'))
            _restore_session_tick_locator(ax2, sess.get('tick_locator_state_ax2'))
            wasd_state = sess.get('wasd_state') or {}
            if wasd_state and isinstance(wasd_state, dict):
                top_m = bool(wasd_state.get('top', {}).get('minor', False))
                bot_m = bool(wasd_state.get('bottom', {}).get('minor', False))
                if top_m or bot_m:
                    ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                else:
                    ax.xaxis.set_minor_locator(NullLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor', top=top_m, bottom=bot_m)
                left_m = bool(wasd_state.get('left', {}).get('minor', False))
                if left_m:
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                else:
                    ax.yaxis.set_minor_locator(NullLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor', left=left_m, right=False)
                right_m = bool(wasd_state.get('right', {}).get('minor', False))
                if right_m:
                    ax2.yaxis.set_minor_locator(AutoMinorLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                else:
                    ax2.yaxis.set_minor_locator(NullLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                ax2.tick_params(axis='y', which='minor', right=right_m, left=False)
        except Exception:
            pass
        
        # Restore tick widths (version 2+)
        try:
            tw = sess.get('tick_widths', {})
            if tw:
                if tw.get('x_major') is not None:
                    ax.tick_params(axis='x', which='major', width=float(tw['x_major']))
                if tw.get('x_minor') is not None:
                    ax.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
                if tw.get('ly_major') is not None:
                    ax.tick_params(axis='y', which='major', width=float(tw['ly_major']))
                if tw.get('ly_minor') is not None:
                    ax.tick_params(axis='y', which='minor', width=float(tw['ly_minor']))
                if tw.get('ry_major') is not None:
                    ax2.tick_params(axis='y', which='major', width=float(tw['ry_major']))
                if tw.get('ry_minor') is not None:
                    ax2.tick_params(axis='y', which='minor', width=float(tw['ry_minor']))
        except Exception:
            pass
        
        # Restore title offsets BEFORE restoring titles
        try:
            title_offsets = sess.get('title_offsets', {})
            if title_offsets:
                ax._top_xlabel_manual_offset_y_pts = float(title_offsets.get('top_y', 0.0) or 0.0)
                ax._top_xlabel_manual_offset_x_pts = float(title_offsets.get('top_x', 0.0) or 0.0)
                ax._bottom_xlabel_manual_offset_y_pts = float(title_offsets.get('bottom_y', 0.0) or 0.0)
                ax._left_ylabel_manual_offset_x_pts = float(title_offsets.get('left_x', 0.0) or 0.0)
                ax2._right_ylabel_manual_offset_x_pts = float(title_offsets.get('right_x', 0.0) or 0.0)
                ax2._right_ylabel_manual_offset_y_pts = float(title_offsets.get('right_y', 0.0) or 0.0)
        except Exception:
            pass
        
        # Restore stored title texts (version 2+)
        try:
            stored_titles = sess.get('stored_titles', {})
            if stored_titles is not None and isinstance(stored_titles, dict) and stored_titles:
                ax._stored_xlabel = stored_titles.get('xlabel', '')
                ax._stored_ylabel = stored_titles.get('ylabel', '')
                ax._stored_top_xlabel = stored_titles.get('top_xlabel', '')
                ax2._stored_ylabel = stored_titles.get('right_ylabel', '')
                
                # Create top xlabel text if it was visible
                wasd = sess.get('wasd_state') or {}
                if wasd.get('top', {}).get('title') and ax._stored_top_xlabel:
                    ax._top_xlabel_text = ax.text(0.5, 1.02, ax._stored_top_xlabel,
                                                   transform=ax.transAxes,
                                                   ha='center', va='bottom',
                                                   fontsize=ax.xaxis.label.get_fontsize(),
                                                   fontfamily=ax.xaxis.label.get_fontfamily())
                    ax._top_xlabel_on = True
        except Exception:
            pass
        
        # Legend: use CPC's _rebuild_legend for correct format (compact multi-file, square patches, etc.)
        try:
            leg_meta = sess.get('legend', {})
            xy_in = leg_meta.get('xy_in')
            vis = bool(leg_meta.get('visible', True))
            if 'title' in leg_meta and leg_meta.get('title'):
                try:
                    fig._cpc_legend_title = str(leg_meta.get('title'))
                except Exception:
                    pass
            try:
                fig._cpc_legend_xy_in = (float(xy_in[0]), float(xy_in[1])) if xy_in is not None else None
            except Exception:
                fig._cpc_legend_xy_in = None
            from .legend import _rebuild_legend
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
            if not vis:
                leg = ax.get_legend() or ax2.get_legend()
                if leg is not None:
                    leg.set_visible(False)
        except Exception:
            pass
        try:
            finalize_spine_colors_cpc(
                fig, ax, ax2,
                tick_state=getattr(ax, '_saved_tick_state', None),
            )
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
        try:
            apply_session_font_cfg(fig, sess.get('font', {}) or {}, ax, ax2)
        except Exception:
            pass
        return fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data
    except Exception as e:
        print(f"Error loading CPC session: {e}")
        traceback.print_exc()
        return None

__all__ = ["dump_cpc_session", "load_cpc_session"]
