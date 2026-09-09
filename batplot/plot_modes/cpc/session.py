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

from ...utils import _confirm_overwrite, ensure_exact_case_filename
from ...ui import (
    set_spine_side_color as _set_spine_side_color,
    finalize_spine_colors_cpc,
)
from ..common.font_extras import apply_session_font_cfg, merge_session_font_dump
from ..common.axis_state import capture_axis_wasd_state, primary_axis_label_text
from ..common.spines import set_primary_axis_title, sync_tick_state_from_wasd
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
    capture_last_figure_export_path,
    restore_last_figure_export_path,
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
) -> bool:
    """Serialize CPC plot including scatter data, styles, axes, and legend position.

    Stores arrays for charge/discharge capacities and efficiency vs cycle number,
    marker styles, axis labels/limits, figure size/dpi, legend position, WASD states,
    tick widths, spines, frame size, and all visual styling.
    
    Args:
        file_data: Optional list of multi-file data dictionaries
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).

    Returns:
        True if the pickle was written successfully, else False.
    """
    if skip_confirm:
        target = filename
    else:
        target = _confirm_overwrite(filename)
        if not target:
            print("CPC session save canceled.")
            return False

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
        # Never-shrink masters (xlim/ylim are view-only; keep explicit full copies).
        from ..common.session_data_guarantee import install_cpc_series_master, install_scatter_xy_master

        x_c_full, y_c_full = install_cpc_series_master(fig, "charge", x_c, y_c)
        x_d_full, y_d_full = install_cpc_series_master(fig, "discharge", x_d, y_d)
        x_e_full, y_e_full = install_cpc_series_master(fig, "efficiency", x_e, y_e)
        install_scatter_xy_master(sc_charge, x_c_full, y_c_full)
        install_scatter_xy_master(sc_discharge, x_d_full, y_d_full)
        install_scatter_xy_master(sc_eff, x_e_full, y_e_full)
        
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
        
        # Save spines state for both ax and ax2 (prefer stored k colors)
        from ...ui import resolve_spine_dump_color

        spines_state = {}
        for name, sp in ax.spines.items():
            spines_state[f'ax_{name}'] = {
                'linewidth': sp.get_linewidth(),
                'color': resolve_spine_dump_color(ax, name, fig),
                'visible': sp.get_visible(),
            }
        for name, sp in ax2.spines.items():
            spines_state[f'ax2_{name}'] = {
                'linewidth': sp.get_linewidth(),
                'color': resolve_spine_dump_color(ax2, name, fig),
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
        
        # Prefer live axes position (``g`` / set_position) over fig.subplotpars.
        subplot_margins = {
            'left': float(bbox.x0),
            'right': float(bbox.x0 + bbox.width),
            'bottom': float(bbox.y0),
            'top': float(bbox.y0 + bbox.height),
        }
        
        # Capture WASD from on-screen artists (ax + ax2 twin) so stale
        # ``_cpc_wasd_state`` / ``_saved_tick_state`` cannot re-enable hidden labels.
        ts = dict(getattr(ax, '_saved_tick_state', {}) or {})
        wasd_state = capture_axis_wasd_state(
            ax,
            tick_state=ts,
            use_actual_major_visibility=True,
            right_axis=ax2,
        )
        def _label_visible(lbl):
            # Title on/off is visibility; empty text must not force title off.
            try:
                return bool(lbl.get_visible())
            except Exception:
                return bool(lbl.get_text()) if hasattr(lbl, 'get_text') else False

        # Prefer explicit WASD flag (artist may be missing while title is ON).
        wasd_state['top']['title'] = bool(getattr(ax, '_top_xlabel_on', False))
        wasd_state['bottom']['title'] = _label_visible(ax.xaxis.label)
        wasd_state['left']['title'] = _label_visible(ax.yaxis.label)
        wasd_state['right']['title'] = _label_visible(ax2.yaxis.label)
        sync_tick_state_from_wasd(
            ts,
            wasd_state,
            tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
            label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
        )
        ax._saved_tick_state = dict(ts)
        fig._cpc_wasd_state = wasd_state
        
        def _series_label(sc, default_val: str) -> str:
            """Artist legend label; keep intentional empty; default only if missing."""
            try:
                lab = sc.get_label()
            except Exception:
                return default_val
            if lab is None:
                return default_val
            return str(lab)

        # Capture title texts (visibility-aware for primary; top is duplicate artist)
        stored_titles = {
            'xlabel': primary_axis_label_text(ax, 'x'),
            'ylabel': primary_axis_label_text(ax, 'y'),
            'top_xlabel': getattr(ax, '_stored_top_xlabel', ''),
            'right_ylabel': primary_axis_label_text(ax2, 'y'),
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
                'xlabel': primary_axis_label_text(ax, 'x'),
                'ylabel_left': primary_axis_label_text(ax, 'y'),
                'ylabel_right': primary_axis_label_text(ax2, 'y'),
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
                    'x_full': x_c_full, 'y_full': y_c_full,
                    'color': ch[0],
                    'hollow': ch[1],
                    'size': _size_of(sc_charge, 32.0),
                    'alpha': (float(sc_charge.get_alpha()) if sc_charge.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_charge, 'get_visible', lambda: True)()),
                    'label': _series_label(sc_charge, 'Charge capacity'),
                    'marker': (getattr(sc_charge, 'get_marker', lambda: 's')() or 's'),
                },
                'discharge': {
                    'x': x_d, 'y': y_d,
                    'x_full': x_d_full, 'y_full': y_d_full,
                    'color': dh[0],
                    'hollow': dh[1],
                    'size': _size_of(sc_discharge, 32.0),
                    'alpha': (float(sc_discharge.get_alpha()) if sc_discharge.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_discharge, 'get_visible', lambda: True)()),
                    'label': _series_label(sc_discharge, 'Discharge capacity'),
                    'marker': (getattr(sc_discharge, 'get_marker', lambda: 's')() or 's'),
                },
                'efficiency': {
                    'x': x_e, 'y': y_e,
                    'x_full': x_e_full, 'y_full': y_e_full,
                    'color': ef[0] or '#2ca02c',
                    'hollow': ef[1],
                    'size': _size_of(sc_eff, 40.0),
                    'alpha': (float(sc_eff.get_alpha()) if sc_eff.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_eff, 'get_visible', lambda: True)()),
                    'label': _series_label(sc_eff, 'Coulombic efficiency'),
                    'marker': (getattr(sc_eff, 'get_marker', lambda: '^')() or '^'),
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
            # Compact multi-file legend display order (h→ra); 0-based indices into multi_files.
            'legend_file_order': (
                list(getattr(fig, '_cpc_legend_file_order', None) or [])
                if (file_data is not None and len(file_data) > 1)
                else None
            ),
            'wasd_state': wasd_state,
            'tick_widths': tick_widths,
            'tick_lengths': tick_lengths,
            'tick_direction': getattr(fig, '_tick_direction', 'out'),
            'tick_locator_state_ax': _capture_session_tick_locator(ax),
            'tick_locator_state_ax2': _capture_session_tick_locator(ax2),
            'stored_titles': stored_titles,
            'title_offsets': title_offsets,
            'font': merge_session_font_dump(fig),
            'grid': ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else (
                any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()) if hasattr(ax, 'get_xgridlines') else False
            ),
            'display_mode': getattr(fig, '_cpc_display_mode', 'both'),
            # Single-file invert flag (multi-file also stores per-entry flags).
            # Old pickles omit this key → load defaults False; Y arrays still win.
            'eff_inverted': bool(
                file_data[0].get('eff_inverted', False)
                if (file_data and isinstance(file_data, list) and len(file_data) > 0)
                else getattr(fig, '_cpc_eff_inverted', False)
            ),
            'is_epc': bool(getattr(fig, '_cpc_is_epc', False)),
            'spine_colors_auto': bool(getattr(fig, '_cpc_spine_auto', False)),
            # Explicit dict (matches style dump); figure.spines colors remain BC fallback.
            'spine_colors': dict(getattr(fig, '_cpc_spine_colors', {}) or {}),
            'ro_active': bool(getattr(fig, '_ro_active', False)),
            # Last exported figure path so 'oe' works after reopening the session.
            'last_figure_export_path': capture_last_figure_export_path(fig),
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
                    return _series_label(sc, default_val)
                sc_ch = f.get('sc_charge', sc_charge)
                sc_dh = f.get('sc_discharge', sc_discharge)
                sc_ef = f.get('sc_eff', sc_eff)
                ch_col, ch_hollow = _color_and_hollow(sc_ch)
                dh_col, dh_hollow = _color_and_hollow(sc_dh)
                ef_col, ef_hollow = _color_and_hollow(sc_ef)
                from ..common.session_data_guarantee import install_scatter_xy_master

                _ch_xy = _scatter_xy(sc_ch)
                _dh_xy = _scatter_xy(sc_dh)
                _ef_xy = _scatter_xy(sc_ef)
                _ch_xf, _ch_yf = install_scatter_xy_master(sc_ch, _ch_xy[0], _ch_xy[1])
                _dh_xf, _dh_yf = install_scatter_xy_master(sc_dh, _dh_xy[0], _dh_xy[1])
                _ef_xf, _ef_yf = install_scatter_xy_master(sc_ef, _ef_xy[0], _ef_xy[1])
                file_info = {
                    'filename': f.get('filename', 'unknown'),
                    'display_name': f.get('display_name', f.get('filename', 'unknown')),
                    # Optional BC fields (interactive add); ignored by older loaders.
                    'filepath': f.get('filepath'),
                    'mass_mg': f.get('mass_mg'),
                    'visible': f.get('visible', True),
                    'eff_inverted': bool(f.get('eff_inverted', False)),
                    'charge': {
                        'x': np.array(_ch_xy[0]),
                        'y': np.array(_ch_xy[1]),
                        'x_full': np.array(_ch_xf),
                        'y_full': np.array(_ch_yf),
                        'color': ch_col,
                        'hollow': ch_hollow,
                        'size': _size_of(sc_ch, 32.0),
                        'alpha': _alpha_of(sc_ch),
                        'marker': _marker_of(sc_ch, 's'),
                        'label': _label_of(sc_ch, 'Charge capacity'),
                        'visible': _visible_of(sc_ch),
                    },
                    'discharge': {
                        'x': np.array(_dh_xy[0]),
                        'y': np.array(_dh_xy[1]),
                        'x_full': np.array(_dh_xf),
                        'y_full': np.array(_dh_yf),
                        'color': dh_col,
                        'hollow': dh_hollow,
                        'size': _size_of(sc_dh, 32.0),
                        'alpha': _alpha_of(sc_dh),
                        'marker': _marker_of(sc_dh, 's'),
                        'label': _label_of(sc_dh, 'Discharge capacity'),
                        'visible': _visible_of(sc_dh),
                    },
                    'efficiency': {
                        'x': np.array(_ef_xy[0]),
                        'y': np.array(_ef_xy[1]),
                        'x_full': np.array(_ef_xf),
                        'y_full': np.array(_ef_yf),
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

        target = ensure_exact_case_filename(target)
        meta['package_versions'] = _package_versions_stamp()
        with open(target, 'wb') as f:
            pickle.dump(meta, f)
        try:
            fig._last_session_save_path = os.path.abspath(target)
        except Exception:
            pass
        print(f"CPC session saved to {target}")
        return True
    except Exception as e:
        print(f"Error saving CPC session: {e}")
        return False


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
        # Seed last figure export path so 'oe' overwrite is available immediately
        restore_last_figure_export_path(fig, sess, session_filename=filename)
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
        try:
            if 'is_epc' in sess:
                fig._cpc_is_epc = bool(sess.get('is_epc'))
        except Exception:
            pass
        # Fonts (is-not-None; do not skip size=0 via truthiness)
        try:
            from ..common.font_extras import sync_font_rcparams_from_cfg
            sync_font_rcparams_from_cfg(sess.get('font', {}))
        except Exception:
            pass
        # Labels and limits (key presence: empty string clears; missing key → defaults for BC)
        ax_meta = sess.get('axis', {})
        try:
            xlabel = (
                ax_meta['xlabel'] if 'xlabel' in ax_meta
                else 'Cycle number'
            )
            ylabel_left = (
                ax_meta['ylabel_left'] if 'ylabel_left' in ax_meta
                else r'Specific Capacity (mAh g$^{-1}$)'
            )
            ylabel_right = (
                ax_meta['ylabel_right'] if 'ylabel_right' in ax_meta
                else 'Efficiency (%)'
            )
            ax.set_xlabel('' if xlabel is None else str(xlabel))
            ax.set_ylabel('' if ylabel_left is None else str(ylabel_left))
            # Infer EPC for older sessions that lack is_epc.
            if not hasattr(fig, '_cpc_is_epc') or getattr(fig, '_cpc_is_epc', None) is None:
                ylab = str(ylabel_left or '').lower()
                fig._cpc_is_epc = ('energy' in ylab) or ('mwh' in ylab)
            ax2.set_ylabel('' if ylabel_right is None else str(ylabel_right))
            _xlim = ax_meta.get('xlim')
            if isinstance(_xlim, (list, tuple)) and len(_xlim) == 2:
                ax.set_xlim(float(_xlim[0]), float(_xlim[1]))
            _yl = ax_meta.get('ylim_left')
            if isinstance(_yl, (list, tuple)) and len(_yl) == 2:
                ax.set_ylim(float(_yl[0]), float(_yl[1]))
            _yr = ax_meta.get('ylim_right')
            if isinstance(_yr, (list, tuple)) and len(_yr) == 2:
                ax2.set_ylim(float(_yr[0]), float(_yr[1]))
            # Label pads
            try:
                lp = ax_meta.get('x_labelpad')
                if lp is not None:
                    ax.set_xlabel(ax.get_xlabel(), labelpad=float(lp))
            except Exception:
                pass
            try:
                lp = ax_meta.get('y_left_labelpad')
                if lp is not None:
                    ax.set_ylabel(ax.get_ylabel(), labelpad=float(lp))
            except Exception:
                pass
            try:
                lp = ax_meta.get('y_right_labelpad')
                if lp is not None:
                    ax2.set_ylabel(ax2.get_ylabel(), labelpad=float(lp))
            except Exception:
                pass
        except Exception:
            pass
        # Series
        sr = sess.get('series', {})
        ch = sr.get('charge', {})
        dh = sr.get('discharge', {})
        ef = sr.get('efficiency', {})
        try:
            from ..common.session_data_guarantee import install_cpc_series_master

            for _role, _rec in (("charge", ch), ("discharge", dh), ("efficiency", ef)):
                _xf = _rec.get("x_full", _rec.get("x"))
                _yf = _rec.get("y_full", _rec.get("y"))
                install_cpc_series_master(fig, _role, _xf, _yf)
        except Exception:
            pass
        def _mk_sc(axX, rec, default_marker='o'):
            x_val = rec.get('x')
            x = np.asarray(x_val if x_val is not None else [], float)
            y_val = rec.get('y')
            y = np.asarray(y_val if y_val is not None else [], float)
            col = rec.get('color') or 'tab:blue'
            _sz = rec.get('size', 32.0)
            s = float(32.0 if _sz is None else _sz)
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
            try:
                from ..common.session_data_guarantee import install_scatter_xy_master

                xf = rec.get('x_full', x)
                yf = rec.get('y_full', y)
                install_scatter_xy_master(sc, xf, yf)
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
                    'filepath': finfo.get('filepath'),
                    'mass_mg': finfo.get('mass_mg'),
                    'visible': vis_file,
                    'eff_inverted': bool(finfo.get('eff_inverted', False)),
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
            try:
                fig._cpc_eff_inverted = bool(file_data[0].get('eff_inverted', False))
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
            # Y arrays already store the displayed (possibly inverted) values —
            # restore the flag only; do not flip again.
            try:
                fig._cpc_eff_inverted = bool(sess.get('eff_inverted', False))
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
        
        # Restore spines state (version 2+): lw/visible now; COLORS after WASD
        # so tick_state exists and right-axis ticks on ax2 recolor correctly.
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
                        if 'color' in props and props['color'] is not None:
                            fig._cpc_spine_colors[name] = props['color']
                        if 'visible' in props:
                            sp.set_visible(props['visible'])
                elif key.startswith('ax2_'):
                    name = key[4:]  # Remove 'ax2_' prefix
                    if name in ax2.spines:
                        sp = ax2.spines[name]
                        if 'linewidth' in props:
                            sp.set_linewidth(props['linewidth'])
                        if 'color' in props and props['color'] is not None:
                            fig._cpc_spine_colors['right' if name == 'right' else name] = props['color']
                        if 'visible' in props:
                            sp.set_visible(props['visible'])
            # Prefer explicit spine_colors dict when present (style-parity / newer dumps).
            explicit = sess.get('spine_colors')
            if isinstance(explicit, dict) and explicit:
                for spine_name, color in explicit.items():
                    if spine_name in ('top', 'bottom', 'left', 'right') and color is not None:
                        fig._cpc_spine_colors[spine_name] = color
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
        
        # Prefer exact axes_bbox (XY parity). Margins/frame only when bbox absent.
        try:
            fig_meta = sess.get('figure', {})
            axes_bbox = fig_meta.get('axes_bbox')
            applied_axes_bbox = _apply_axes_bbox(ax, axes_bbox)
            if applied_axes_bbox:
                try:
                    ax2.set_position(ax.get_position())
                except Exception:
                    pass
            else:
                margins = fig_meta.get('subplot_margins', {})
                if isinstance(margins, dict) and margins:
                    fig.subplots_adjust(
                        left=margins.get('left', 0.125),
                        right=margins.get('right', 0.9),
                        bottom=margins.get('bottom', 0.11),
                        top=margins.get('top', 0.88),
                    )
                frame_size = fig_meta.get('frame_size')
                if frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                    target_w_in, target_h_in = map(float, frame_size)
                    canvas_w_in, canvas_h_in = fig.get_size_inches()
                    if canvas_w_in > 0 and canvas_h_in > 0:
                        bbox_live = ax.get_position()
                        center_x = (bbox_live.x0 + bbox_live.x1) / 2.0
                        center_y = (bbox_live.y0 + bbox_live.y1) / 2.0
                        new_w_frac = target_w_in / canvas_w_in
                        new_h_frac = target_h_in / canvas_h_in
                        new_left = center_x - new_w_frac / 2.0
                        new_right = center_x + new_w_frac / 2.0
                        new_bottom = center_y - new_h_frac / 2.0
                        new_top = center_y + new_h_frac / 2.0
                        fig.subplots_adjust(
                            left=new_left,
                            right=new_right,
                            bottom=new_bottom,
                            top=new_top,
                        )
                        try:
                            ax2.set_position(ax.get_position())
                        except Exception:
                            pass
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
                # Axis titles: store/clear text + visibility (match interactive t).
                try:
                    if 'bottom' in wasd_state:
                        set_primary_axis_title(
                            ax, "x",
                            on=bool(wasd_state['bottom'].get('title', True)),
                            stored_attr="_stored_xlabel",
                        )
                    if 'left' in wasd_state:
                        set_primary_axis_title(
                            ax, "y",
                            on=bool(wasd_state['left'].get('title', True)),
                            stored_attr="_stored_ylabel",
                        )
                    if 'right' in wasd_state:
                        set_primary_axis_title(
                            ax2, "y",
                            on=bool(wasd_state['right'].get('title', True)),
                            stored_attr="_stored_ylabel",
                        )
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
                # Store tick_state on axes — match dump (legacy = ticks AND labels).
                from ..common.spines import wasd_to_tick_state

                tick_state = wasd_to_tick_state(
                    wasd_state,
                    tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                    label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                )
                ax._saved_tick_state = tick_state
        except Exception:
            pass

        # Apply spine COLORS after WASD/tick_state so ticks match (old+new pkl).
        try:
            colors = getattr(fig, "_cpc_spine_colors", None) or {}
            if isinstance(colors, dict) and colors:
                ts = getattr(ax, "_saved_tick_state", None)
                axes_map = {
                    "top": [ax, ax2],
                    "bottom": [ax, ax2],
                    "left": [ax],
                    "right": [ax2],
                }
                for spine_name, color in colors.items():
                    if spine_name not in axes_map or color is None:
                        continue
                    for curr_ax in axes_map[spine_name]:
                        if curr_ax is None or spine_name not in curr_ax.spines:
                            continue
                        try:
                            _set_spine_side_color(
                                curr_ax, spine_name, color, fig=fig, tick_state=ts
                            )
                        except Exception:
                            pass
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
                if wasd.get('top', {}).get('title') and isinstance(ax._stored_top_xlabel, str):
                    ax._top_xlabel_text = ax.text(0.5, 1.02, ax._stored_top_xlabel,
                                                   transform=ax.transAxes,
                                                   ha='center', va='bottom',
                                                   fontsize=ax.xaxis.label.get_fontsize(),
                                                   fontfamily=ax.xaxis.label.get_fontfamily())
                    ax._top_xlabel_on = True
                    top_c = (
                        (getattr(fig, "_cpc_spine_colors", None) or {}).get("top")
                        or getattr(ax, "_stored_top_xlabel_color", None)
                    )
                    if top_c is not None:
                        try:
                            ax._top_xlabel_text.set_color(top_c)
                            ax._stored_top_xlabel_color = top_c
                        except Exception:
                            pass
        except Exception:
            pass
        
        # Legend: use CPC's _rebuild_legend for correct format (compact multi-file, square patches, etc.)
        try:
            leg_meta = sess.get('legend', {})
            xy_in = leg_meta.get('xy_in')
            vis = bool(leg_meta.get('visible', True))
            if 'title' in leg_meta:
                try:
                    title_val = leg_meta.get('title')
                    fig._cpc_legend_title = "" if title_val is None else str(title_val)
                except Exception:
                    pass
            try:
                fig._cpc_legend_xy_in = (float(xy_in[0]), float(xy_in[1])) if xy_in is not None else None
            except Exception:
                fig._cpc_legend_xy_in = None
            legend_file_order = sess.get('legend_file_order')
            if (
                legend_file_order
                and file_data
                and isinstance(legend_file_order, (list, tuple))
                and len(legend_file_order) == len(file_data)
            ):
                try:
                    from .legend_order import ensure_cpc_legend_file_order

                    fig._cpc_legend_file_order = list(legend_file_order)
                    ensure_cpc_legend_file_order(fig, file_data)
                except Exception:
                    fig._cpc_legend_file_order = list(legend_file_order)
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
