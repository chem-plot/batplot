"""Operando (+ optional EC) session dump/load (mode-owned implementation).

Moved from :mod:`batplot.session` to keep the root session module as a thin
compatibility facade. Shared helpers remain in ``batplot.session``.
"""

from __future__ import annotations

import os
import pickle
from typing import Any, Optional

import numpy as np  # type: ignore[import-untyped]
from numpy import ma as _ma
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.colorbar import Colorbar as _Colorbar  # type: ignore[import-untyped]

from ...utils import _confirm_overwrite, ensure_exact_case_filename
from ...color_utils import ensure_colormap
from ...ui import (
    set_spine_side_color as _set_spine_side_color,
    apply_wasd_minor_ticks,
    finalize_spine_colors_for_axes,
)
from ..common.font_extras import apply_session_font_cfg, merge_session_font_dump
from ..common.interactive_state import build_saved_tick_state
from ..common.axis_state import (
    capture_axis_spines_and_tick_widths,
    capture_axis_wasd_state,
)
from ..common.session_helpers import (
    _try_extract_version_from_pickle,
    _package_versions_stamp,
    _get_current_numpy_version,
    _current_tick_width,
    _current_tick_length,
    _apply_session_tick_lengths,
    _capture_session_tick_locator,
    _restore_session_tick_locator,
)


# --------------------- Operando + EC combined session helpers --------------------

def dump_operando_session(
    filename: str,
    *,
    fig,
    ax,      # operando axes
    im,      # AxesImage for operando
    cbar,    # Colorbar object
    ec_ax=None,
    skip_confirm: bool = False,
) -> None:
    """Serialize the current operando+EC interactive session to a pickle file.

    Captures enough state to reconstruct the figure layout, operando image,
    colorbar, and optional EC panel including ions-mode formatting.
    
    Args:
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).
    """
    try:
        # Figure & inches geometry
        fig_w, fig_h = map(float, fig.get_size_inches())
        dpi = int(fig.dpi)
        # Layout in inches (group-centered on restore)
        ax_x0, ax_y0, ax_wf, ax_hf = ax.get_position().bounds
        cb_x0, cb_y0, cb_wf, cb_hf = cbar.ax.get_position().bounds
        if ec_ax is not None:
            ec_x0, ec_y0, ec_wf, ec_hf = ec_ax.get_position().bounds
        else:
            ec_x0 = ec_y0 = ec_wf = ec_hf = 0.0
        # Prefer using fixed attributes if they exist (more reliable than calculating from positions)
        cb_w_in = getattr(cbar.ax, '_fixed_cb_w_in', cb_wf * fig_w)
        cb_gap_in = getattr(cbar.ax, '_fixed_cb_gap_in', (ax_x0 - (cb_x0 + cb_wf)) * fig_w)
        ax_w_in = getattr(ax, '_fixed_ax_w_in', ax_wf * fig_w)
        ax_h_in = getattr(ax, '_fixed_ax_h_in', ax_hf * fig_h)
        if ec_ax is not None:
            ec_gap_in = getattr(ec_ax, '_fixed_ec_gap_in', (ec_x0 - (ax_x0 + ax_wf)) * fig_w)
            ec_w_in = getattr(ec_ax, '_fixed_ec_w_in', ec_wf * fig_w)
        else:
            ec_gap_in = 0.0
            ec_w_in = 0.0

        # Operando image state
        arr = im.get_array()
        # Use masked arrays to preserve NaNs if present
        data = np.array(arr)  # preserves mask where possible
        extent = tuple(map(float, im.get_extent())) if hasattr(im, 'get_extent') else None
        # Get colormap name: first check if we stored it explicitly, otherwise try to get from colormap object
        cmap_name = getattr(im, '_operando_cmap_name', None)
        if cmap_name is None:
            cmap_name = getattr(im.get_cmap(), 'name', None)
        clim = tuple(map(float, im.get_clim())) if hasattr(im, 'get_clim') else None
        origin = getattr(im, 'origin', 'upper')
        interpolation = getattr(im, 'get_interpolation', lambda: None)() or 'nearest'

        # Labels and limits for operando
        # Capture label text and padding (labelpad)
        try:
            _xlp = float(getattr(ax.xaxis, 'labelpad', 0.0))
        except Exception:
            _xlp = 0.0
        try:
            _ylp = float(getattr(ax.yaxis, 'labelpad', 0.0))
        except Exception:
            _ylp = 0.0
        op_labels = {
            'xlabel': ax.get_xlabel(),
            'ylabel': ax.get_ylabel(),
            'xlim': tuple(map(float, ax.get_xlim())),
            'ylim': tuple(map(float, ax.get_ylim())),
            'x_labelpad': _xlp,
            'y_labelpad': _ylp,
        }
        op_custom = getattr(ax, '_custom_labels', {'x': None, 'y': None})

        # Colorbar label (Colorbar lacks get_label in some versions; use its axes ylabel)
        try:
            cb_label = cbar.ax.get_ylabel()
        except Exception:
            cb_label = ''
        # Capture color scale limits (clim) through the mappable
        try:
            cb_clim = tuple(map(float, im.get_clim()))
        except Exception:
            cb_clim = None

        def _capture_tick_lengths(axis):
            return {
                'x_major': _current_tick_length(axis.xaxis, 'major'),
                'x_minor': _current_tick_length(axis.xaxis, 'minor'),
                'y_major': _current_tick_length(axis.yaxis, 'major'),
                'y_minor': _current_tick_length(axis.yaxis, 'minor'),
            }
        
        # Capture operando WASD state, spines, and tick widths
        op_wasd_state = capture_axis_wasd_state(
            ax,
            use_actual_major_visibility=True,
            use_right_ylabel_position=True,
        )
        op_spines, op_ticks = capture_axis_spines_and_tick_widths(ax, _current_tick_width)
        op_tick_lengths = _capture_tick_lengths(ax)
        
        # Capture operando title offsets
        op_title_offsets = {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        }

        # EC panel (optional)
        ec_state = None
        if ec_ax is not None:
            time_h = np.asarray(getattr(ec_ax, '_ec_time_h', []), float)
            volt_v = np.asarray(getattr(ec_ax, '_ec_voltage_v', []), float)
            curr_mA = np.asarray(getattr(ec_ax, '_ec_current_mA', []), float)
            mode = getattr(ec_ax, '_ec_y_mode', 'time')
            xlim = tuple(map(float, ec_ax.get_xlim()))
            ylim = tuple(map(float, ec_ax.get_ylim()))
            # Persist prior time-mode ylim and any ions array/params
            saved_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
            ions_abs = np.asarray(getattr(ec_ax, '_ions_abs', []), float) if getattr(ec_ax, '_ions_abs', None) is not None else None
            ion_params = getattr(ec_ax, '_ion_params', None)
            prev_ec_xlim = getattr(ec_ax, '_prev_ec_xlim', None)
            ions_xlim_expanded = bool(getattr(ec_ax, '_ions_xlim_expanded', False))
            ion_guides = []
            for gl in getattr(ec_ax, '_ion_guides', []) or []:
                try:
                    ydata = np.asarray(gl.get_ydata(), float)
                    if ydata.size:
                        ion_guides.append(float(ydata[0]))
                except Exception:
                    pass
            ion_annots = []
            for ann in getattr(ec_ax, '_ion_annots', []) or []:
                try:
                    ion_annots.append({'text': ann.get_text(), 'xy': tuple(float(v) for v in ann.xy)})
                except Exception:
                    pass
            custom = getattr(ec_ax, '_custom_labels', {'x': None, 'y_time': None, 'y_ions': None})
            # EC line style (if present)
            ln = getattr(ec_ax, '_ec_line', None)
            if ln is None and getattr(ec_ax, 'lines', None):
                try:
                    ln = ec_ax.lines[0]
                except Exception:
                    ln = None
            line_style = None
            if ln is not None:
                try:
                    line_style = {
                        'color': ln.get_color(),
                        'linewidth': float(ln.get_linewidth() or 1.0),
                        'linestyle': ln.get_linestyle() or '-',
                        'alpha': ln.get_alpha(),
                    }
                except Exception:
                    line_style = None
            
            # Capture EC WASD state, spines, and tick widths
            ec_wasd_state = capture_axis_wasd_state(
                ec_ax,
                use_actual_major_visibility=True,
                use_right_ylabel_position=True,
            )
            ec_spines, ec_ticks = capture_axis_spines_and_tick_widths(ec_ax, _current_tick_width)
            ec_tick_lengths = _capture_tick_lengths(ec_ax)
            
            # Capture EC title offsets
            ec_title_offsets = {
                'top_y': float(getattr(ec_ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
                'top_x': float(getattr(ec_ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
                'bottom_y': float(getattr(ec_ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
                'left_x': float(getattr(ec_ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
                'right_x': float(getattr(ec_ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
                'right_y': float(getattr(ec_ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
            }
            
            ec_state = {
                'time_h': time_h,
                'volt_v': volt_v,
                'curr_mA': curr_mA,
                'mode': mode,
                'xlim': xlim,
                'ylim': ylim,
                'saved_time_ylim': tuple(map(float, saved_time_ylim)) if isinstance(saved_time_ylim, (list, tuple)) else None,
                'ions_abs': ions_abs,
                'ion_params': ion_params,
                'prev_ec_xlim': tuple(map(float, prev_ec_xlim)) if isinstance(prev_ec_xlim, (list, tuple)) else None,
                'ions_xlim_expanded': ions_xlim_expanded,
                'ion_guides': ion_guides,
                'ion_annots': ion_annots,
                'custom_labels': custom,
                'line_style': line_style,
                'wasd_state': ec_wasd_state,
                'spines': ec_spines,
                'ticks': {
                    'widths': ec_ticks,
                    'lengths': ec_tick_lengths,
                    'direction': getattr(fig, '_tick_direction', 'out'),
                },
                'tick_locator_state': _capture_session_tick_locator(ec_ax),
                'title_offsets': ec_title_offsets,
                'stored_ylabel': getattr(ec_ax, '_stored_ylabel', None),  # Save hidden ylabel text
                'visible': bool(ec_ax.get_visible()),
                'grid': dict(getattr(ec_ax, '_ec_grid', None) or {}),
            }

        # Get horizontal offsets if they exist
        cb_h_offset = getattr(cbar.ax, '_cb_h_offset_in', 0.0)
        ec_h_offset = getattr(ec_ax, '_ec_h_offset_in', 0.0) if ec_ax is not None else None
        
        sess = {
            'kind': 'operando_ec',
            'version': 2,
            'figure': {'size': (fig_w, fig_h), 'dpi': dpi},
            'layout_inches': {
                'cb_w_in': cb_w_in,
                'cb_gap_in': cb_gap_in,
                'ax_w_in': ax_w_in,
                'ax_h_in': ax_h_in,
                'ec_gap_in': ec_gap_in,
                'ec_w_in': ec_w_in,
                'cb_h_offset': float(cb_h_offset),
                'ec_h_offset': float(ec_h_offset) if ec_h_offset is not None else None,
            },
            'operando': {
                'array': data,
                'extent': extent,
                'cmap': cmap_name,
                'clim': clim,
                'origin': origin,
                'interpolation': interpolation,
                'labels': op_labels,
                'custom_labels': op_custom,
                'wasd_state': op_wasd_state,
                'spines': op_spines,
                'ticks': {
                    'widths': op_ticks,
                    'lengths': op_tick_lengths,
                    'direction': getattr(fig, '_tick_direction', 'out'),
                },
                'tick_locator_state': _capture_session_tick_locator(ax),
                'title_offsets': op_title_offsets,
                'stored_ylabel': getattr(ax, '_stored_ylabel', None),  # Save hidden ylabel text
            },
            'colorbar': {
                'label': cb_label,
                'clim': cb_clim,
                'visible': bool(cbar.ax.get_visible()),
                'label_mode': getattr(fig, '_colorbar_label_mode', 'highlow'),
            },
            'ec': ec_state,
            'font': merge_session_font_dump(fig),
        }
        # CIF tick labels for operando (if present)
        if getattr(ax, '_operando_cif_tick_series', None):
            sess['cif'] = {
                'tick_series': list(ax._operando_cif_tick_series),
                'hkl_label_map': dict(getattr(ax, '_operando_cif_hkl_label_map', {})),
                'show_hkl': bool(getattr(fig, '_operando_cif_show_hkl', False)),
                'show_titles': bool(getattr(fig, '_operando_cif_show_titles', True)),
                'placement': str(getattr(fig, '_operando_cif_placement', 'below')),
                'y_positions': list(getattr(fig, '_operando_cif_y_positions', [])),
                'colormap': getattr(fig, '_operando_cif_colormap', None),
                'highlight': bool(getattr(fig, '_operando_cif_highlight', False)),
                'title_font': dict(getattr(fig, '_operando_cif_title_font', None) or {}),
                'title_visible': list(getattr(fig, '_operando_cif_title_visible', None) or []),
                'set_visible': list(getattr(fig, '_operando_cif_set_visible', None) or []),
                'axis_mode': str(getattr(fig, '_operando_axis_mode', '2theta')),
                'wl': getattr(fig, '_operando_wl', None),
            }
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("Session save canceled.")
                return
        # Ensure exact case is preserved (important for macOS case-insensitive filesystem)
        target = ensure_exact_case_filename(target)
        
        sess['package_versions'] = _package_versions_stamp()
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"Operando session saved to {target}")
    except Exception as e:  # pragma: no cover - defensive path
        print(f"Error saving operando session: {e}")


def load_operando_session(filename: str):
    """Load an operando+EC session (.pkl) and reconstruct figure and axes.

    Returns: (fig, ax, im, cbar, ec_ax)
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

    if not isinstance(sess, dict) or sess.get('kind') != 'operando_ec':
        print("Not an operando+EC session file.")
        return None

    # Use standard DPI of 100 instead of saved DPI to avoid display-dependent issues
    # (Retina displays, Windows scaling, etc. can cause saved DPI to differ)
    fig = plt.figure(figsize=tuple(sess['figure']['size']), dpi=100)
    # Seed last-session path so 'os' overwrite command is available immediately
    try:
        fig._last_session_save_path = os.path.abspath(filename)
    except Exception:
        pass
    # Disable automatic layout adjustments to preserve saved geometry
    try:
        fig.set_layout_engine('none')
    except Exception:
        try:
            fig.set_tight_layout(False)
        except Exception:
            pass
    W, H = map(float, fig.get_size_inches())
    li = sess['layout_inches']
    cb_wf = max(0.0, float(li['cb_w_in']) / W)
    cb_gap_f = max(0.0, float(li['cb_gap_in']) / W)
    ax_wf = max(0.0, float(li['ax_w_in']) / W)
    ax_hf = max(0.0, float(li['ax_h_in']) / H)
    ec_wf = max(0.0, float(li.get('ec_w_in', 0.0)) / W)
    ec_gap_f = max(0.0, float(li.get('ec_gap_in', 0.0)) / W)

    total_wf = cb_wf + cb_gap_f + ax_wf + ec_gap_f + ec_wf
    group_left = 0.5 - total_wf / 2.0
    y0 = 0.5 - ax_hf / 2.0

    # Axes positions
    cb_x0 = group_left
    ax_x0 = cb_x0 + cb_wf + cb_gap_f
    ec_x0 = ax_x0 + ax_wf + ec_gap_f if ec_wf > 0 else None

    # Create axes
    ax = fig.add_axes((ax_x0, y0, ax_wf, ax_hf))
    cbar_ax = fig.add_axes((cb_x0, y0, cb_wf, ax_hf))

    # Recreate operando image
    op = sess['operando']
    arr = _ma.masked_invalid(op['array'])
    extent = tuple(op['extent']) if op['extent'] is not None else None
    cmap_name = op.get('cmap') or 'viridis'
    try:
        if not ensure_colormap(cmap_name):
            cmap_name = 'viridis'
    except Exception:
        cmap_name = 'viridis'
    im = ax.imshow(arr, aspect='auto', origin=op.get('origin', 'upper'), extent=extent,
                   cmap=cmap_name, interpolation=op.get('interpolation', 'nearest'))
    # Store the colormap name explicitly so it can be retrieved reliably when saving
    setattr(im, '_operando_cmap_name', cmap_name)
    if op.get('clim'):
        try:
            im.set_clim(*op['clim'])
        except Exception:
            pass
    
    # Apply operando WASD state if version 2+ (BEFORE restoring labels!)
    version = sess.get('version', 1)
    if version >= 2:
        op_wasd = op.get('wasd_state')
        if op_wasd and isinstance(op_wasd, dict):
            try:
                # Apply spines
                for side in ('top', 'bottom', 'left', 'right'):
                    if side in op_wasd and 'spine' in op_wasd[side]:
                        sp = ax.spines.get(side)
                        if sp:
                            sp.set_visible(bool(op_wasd[side]['spine']))
                # Apply ticks
                ax.tick_params(axis='x', 
                              top=bool(op_wasd.get('top', {}).get('ticks', False)),
                              bottom=bool(op_wasd.get('bottom', {}).get('ticks', True)),
                              labeltop=bool(op_wasd.get('top', {}).get('labels', False)),
                              labelbottom=bool(op_wasd.get('bottom', {}).get('labels', True)))
                ax.tick_params(axis='y',
                              left=bool(op_wasd.get('left', {}).get('ticks', True)),
                              right=bool(op_wasd.get('right', {}).get('ticks', False)),
                              labelleft=bool(op_wasd.get('left', {}).get('labels', True)),
                              labelright=bool(op_wasd.get('right', {}).get('labels', False)))
                # Apply minor ticks (left y only when EC panel shares the figure)
                _op_y_minor = 'left' if ec_wf > 0 else 'both'
                apply_wasd_minor_ticks(ax, op_wasd, y_minor_mode=_op_y_minor)
                # Store WASD state with the same defaults used in tick_params above.
                op_defaults = {'top': False, 'bottom': True, 'left': True, 'right': False}
                op_ts = build_saved_tick_state(
                    op_wasd,
                    tick_defaults=op_defaults,
                    label_defaults=op_defaults,
                )
                ax._saved_tick_state = op_ts
                # Apply title flags (must be set before restoring labels below)
                ax._top_xlabel_on = bool(op_wasd.get('top', {}).get('title', False))
                ax._right_ylabel_on = bool(op_wasd.get('right', {}).get('title', False))
            except Exception as e:
                print(f"Warning: Could not apply operando WASD state: {e}")
    else:
        # For version 1 pkl files, assume default visibility
        op_wasd = None
    
    # Restore labels and labelpad (respecting WASD title state)
    # Bottom xlabel: restore if title is True (default) or if no WASD state
    bottom_title_on = op_wasd.get('bottom', {}).get('title', True) if op_wasd else True
    if bottom_title_on:
        ax.set_xlabel(op['labels'].get('xlabel') or '')
        try:
            lp = op['labels'].get('x_labelpad')
            if lp is not None:
                ax.set_xlabel(ax.get_xlabel(), labelpad=float(lp))
        except Exception:
            pass
    else:
        ax.set_xlabel('')  # Hidden by user via s5
    
    # Left ylabel: restore if title is True (default) or if saved text exists
    left_title_on = op_wasd.get('left', {}).get('title', True) if op_wasd else True
    saved_ylabel = (op['labels'].get('ylabel') or '').strip()
    if left_title_on or saved_ylabel:
        ax.set_ylabel(saved_ylabel or 'Scan index')
        try:
            lp = op['labels'].get('y_labelpad')
            if lp is not None:
                ax.set_ylabel(ax.get_ylabel(), labelpad=float(lp))
        except Exception:
            pass
    else:
        ax.set_ylabel('')  # Hidden by user via a5
    
    try:
        ax.set_xlim(*op['labels']['xlim'])
        ax.set_ylim(*op['labels']['ylim'])
    except Exception:
        pass
    # Persist custom labels
    setattr(ax, '_custom_labels', dict(op.get('custom_labels', {'x': None, 'y': None})))
    
    # Restore stored ylabel if present (for cases where ylabel was hidden with a5)
    stored_ylabel = op.get('stored_ylabel')
    if stored_ylabel is not None:
        setattr(ax, '_stored_ylabel', stored_ylabel)
    
    # Restore operando title offsets
    try:
        op_title_offsets = op.get('title_offsets', {})
        if op_title_offsets:
            ax._top_xlabel_manual_offset_y_pts = float(op_title_offsets.get('top_y', 0.0) or 0.0)
            ax._top_xlabel_manual_offset_x_pts = float(op_title_offsets.get('top_x', 0.0) or 0.0)
            ax._bottom_xlabel_manual_offset_y_pts = float(op_title_offsets.get('bottom_y', 0.0) or 0.0)
            ax._left_ylabel_manual_offset_x_pts = float(op_title_offsets.get('left_x', 0.0) or 0.0)
            ax._right_ylabel_manual_offset_x_pts = float(op_title_offsets.get('right_x', 0.0) or 0.0)
            ax._right_ylabel_manual_offset_y_pts = float(op_title_offsets.get('right_y', 0.0) or 0.0)
    except Exception:
        pass

    # Restore tick locator state for operando ax, then re-apply WASD minor visibility
    try:
        _restore_session_tick_locator(ax, op.get('tick_locator_state'))
        if op_wasd and isinstance(op_wasd, dict):
            apply_wasd_minor_ticks(ax, op_wasd, y_minor_mode='left' if ec_wf > 0 else 'both')
    except Exception:
        pass

    # Apply operando spines
    op_spines = op.get('spines', {})
    if op_spines:
        try:
            for name, props in op_spines.items():
                sp = ax.spines.get(name)
                if not sp:
                    continue
                if 'linewidth' in props and props['linewidth'] is not None:
                    try:
                        sp.set_linewidth(float(props['linewidth']))
                    except Exception:
                        pass
                if 'visible' in props and props['visible'] is not None:
                    try:
                        sp.set_visible(bool(props['visible']))
                    except Exception:
                        pass
                if 'color' in props and props['color'] is not None:
                    try:
                        _set_spine_side_color(ax, name, props['color'], fig=fig)
                    except Exception:
                        pass
        except Exception:
            pass

    # Apply operando tick widths
    op_tick_widths = op.get('ticks', {}).get('widths', {})
    if op_tick_widths:
        try:
            if op_tick_widths.get('x_major'): ax.tick_params(axis='x', which='major', width=op_tick_widths['x_major'])
            if op_tick_widths.get('x_minor'): ax.tick_params(axis='x', which='minor', width=op_tick_widths['x_minor'])
            if op_tick_widths.get('y_major'): ax.tick_params(axis='y', which='major', width=op_tick_widths['y_major'])
            if op_tick_widths.get('y_minor'): ax.tick_params(axis='y', which='minor', width=op_tick_widths['y_minor'])
        except Exception:
            pass
    _apply_session_tick_lengths(fig, [ax], op.get('ticks', {}).get('lengths'))
    try:
        tick_direction = op.get('ticks', {}).get('direction')
        if tick_direction:
            setattr(fig, '_tick_direction', tick_direction)
            ax.tick_params(axis='both', which='both', direction=tick_direction)
    except Exception:
        pass

    # Colorbar
    cbar = _Colorbar(cbar_ax, im)
    cbar.ax.yaxis.set_ticks_position('left')
    cbar.ax.yaxis.set_label_position('left')
    try:
        cb_meta = sess.get('colorbar', {})
        label_text = cb_meta.get('label')
        label_mode = cb_meta.get('label_mode', 'highlow')
        # Set label on the colorbar's axes for better compatibility
        try:
            cbar.ax.set_ylabel(label_text or '')
        except Exception:
            cbar.set_label(label_text or '')
        if cb_meta.get('clim'):
            try:
                im.set_clim(*cb_meta['clim'])
            except Exception:
                pass
        # Persist custom colorbar attributes for interactive mode
        setattr(cbar.ax, '_colorbar_label', label_text or (cbar.ax.get_ylabel() or 'Intensity'))
        setattr(cbar.ax, '_colorbar_label_mode', label_mode)
        setattr(cbar.ax, '_colorbar_im', im)
        setattr(fig, '_colorbar_label_mode', label_mode)
        try:
            from .layout import _update_custom_colorbar
            _update_custom_colorbar(cbar.ax, im, label=label_text, label_mode=label_mode)
        except Exception:
            pass
    except Exception:
        pass

    # Optional EC panel
    ec_ax = None
    if ec_wf > 0 and ec_x0 is not None:
        ec_ax = fig.add_axes((ec_x0, y0, ec_wf, ax_hf))
        # Basic line
        ec = sess.get('ec') or {}
        th = ec.get('time_h')
        vv = ec.get('volt_v')
        if th is not None and vv is not None and len(th) == len(vv) and len(th) > 0:
            # Apply saved style or defaults
            st = (ec.get('line_style') or {})
            color = st.get('color', 'tab:blue')
            lw = float(st.get('linewidth', 1.0) or 1.0)
            ls = st.get('linestyle', '-') or '-'
            alpha = st.get('alpha', None)
            ln, = ec_ax.plot(vv, th, lw=lw, color=color, linestyle=ls, alpha=alpha)
            setattr(ec_ax, '_ec_line', ln)
        
        # Stash arrays for interactivity
        setattr(ec_ax, '_ec_time_h', th)
        setattr(ec_ax, '_ec_voltage_v', vv)
        setattr(ec_ax, '_ec_current_mA', ec.get('curr_mA'))
        # Limits
        try:
            if ec.get('xlim'): ec_ax.set_xlim(*ec['xlim'])
            if ec.get('ylim'): ec_ax.set_ylim(*ec['ylim'])
        except Exception:
            pass
        # Ticks/labels on right
        try:
            ec_ax.yaxis.tick_right(); ec_ax.yaxis.set_label_position('right')
        except Exception:
            pass
        # Custom labels storage
        setattr(ec_ax, '_custom_labels', dict(ec.get('custom_labels', {'x': None, 'y_time': None, 'y_ions': None})))
        # Persist saved time ylim
        if isinstance(ec.get('saved_time_ylim'), (list, tuple)):
            setattr(ec_ax, '_saved_time_ylim', tuple(ec['saved_time_ylim']))
        if isinstance(ec.get('prev_ec_xlim'), (list, tuple)):
            setattr(ec_ax, '_prev_ec_xlim', tuple(ec['prev_ec_xlim']))
        setattr(ec_ax, '_ions_xlim_expanded', bool(ec.get('ions_xlim_expanded', False)))
        
        # Apply EC WASD state BEFORE setting labels (if version 2+)
        ec_wasd = None
        if version >= 2:
            ec_wasd = ec.get('wasd_state')
            if ec_wasd and isinstance(ec_wasd, dict):
                try:
                    # Apply spines
                    for side in ('top', 'bottom', 'left', 'right'):
                        if side in ec_wasd and 'spine' in ec_wasd[side]:
                            sp = ec_ax.spines.get(side)
                            if sp:
                                sp.set_visible(bool(ec_wasd[side]['spine']))
                    # Apply ticks
                    ec_ax.tick_params(axis='x',
                                     top=bool(ec_wasd.get('top', {}).get('ticks', False)),
                                     bottom=bool(ec_wasd.get('bottom', {}).get('ticks', True)),
                                     labeltop=bool(ec_wasd.get('top', {}).get('labels', False)),
                                     labelbottom=bool(ec_wasd.get('bottom', {}).get('labels', True)))
                    # For EC: ticks and labels are on RIGHT by default, not left!
                    # CRITICAL: EC y-axis defaults are: left=False, right=True (both ticks and labels)
                    # Old sessions may have saved wrong values, so we need to sanitize them
                    
                    # EC left side should ALWAYS be False (EC uses right side for y-axis)
                    left_ticks = False
                    left_labels = False
                    
                    # Preserve explicit saved right tick/label state. Older sessions
                    # may only have a right title flag, so use it as a fallback.
                    right_state = ec_wasd.get('right', {})
                    right_title = bool(right_state.get('title', True))
                    right_ticks_val = right_state.get('ticks')
                    right_labels_val = right_state.get('labels')
                    right_ticks = bool(right_ticks_val) if right_ticks_val is not None else right_title
                    right_labels = bool(right_labels_val) if right_labels_val is not None else right_title
                    # Legacy operando+EC sessions captured y ticks on the left side
                    # while the y-axis title lived on the right. Restore right ticks
                    # only for that drift pattern so intentional tick-off states remain.
                    if right_title and not right_ticks and not right_labels:
                        left_state = ec_wasd.get('left', {})
                        if bool(left_state.get('ticks')) or bool(left_state.get('labels')):
                            right_ticks = True
                            right_labels = True
                    
                    ec_ax.tick_params(axis='y',
                                     left=left_ticks,
                                     right=right_ticks,
                                     labelleft=left_labels,
                                     labelright=right_labels)
                    apply_wasd_minor_ticks(ec_ax, ec_wasd, y_minor_mode='right')
                    # Store WASD state using the resolved left/right values actually applied above.
                    ec_defaults = {'top': False, 'bottom': True, 'left': False, 'right': False}
                    ec_ts = build_saved_tick_state(
                        ec_wasd,
                        tick_defaults=ec_defaults,
                        label_defaults=ec_defaults,
                        overrides={
                            'l_ticks': left_ticks,
                            'l_labels': left_labels,
                            'r_ticks': right_ticks,
                            'r_labels': right_labels,
                        },
                    )
                    ec_ax._saved_tick_state = ec_ts
                    # Apply title flags
                    ec_ax._top_xlabel_on = bool(ec_wasd.get('top', {}).get('title', False))
                    ec_ax._right_ylabel_on = bool(ec_wasd.get('right', {}).get('title', False))
                except Exception as e:
                    print(f"Warning: Could not apply EC WASD state: {e}")
        
        # Set xlabel (respecting WASD title state for bottom)
        bottom_title_on = ec_wasd.get('bottom', {}).get('title', True) if ec_wasd else True
        if bottom_title_on:
            ec_ax.set_xlabel((ec.get('custom_labels') or {}).get('x') or 'Potential (V)')
        else:
            ec_ax.set_xlabel('')  # Hidden by user via s5
        
        # Handle ions mode
        mode = ec.get('mode', 'time')
        setattr(ec_ax, '_ec_y_mode', mode)
        if mode == 'ions':
            try:
                # Rebuild ions formatter based on stored ions array if present; else leave time labels
                t = np.asarray(th, float)
                ions_abs = ec.get('ions_abs')
                ion_params = ec.get('ion_params')
                if ions_abs is None and ion_params and t is not None:
                    # Fallback: recompute ions from params
                    i_mA = np.asarray(ec.get('curr_mA'), float)
                    v = np.asarray(vv, float)
                    dt = np.diff(t)
                    inc = np.empty_like(t); inc[0] = 0.0
                    if t.size > 1:
                        inc[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                    cap_mAh = np.cumsum(inc)
                    mass_g = float(ion_params.get('mass_mg', 0.0)) / 1000.0
                    with np.errstate(divide='ignore', invalid='ignore'):
                        cap_mAh_g = np.where(mass_g>0, cap_mAh / mass_g, np.nan)
                        ions_delta = np.where(ion_params.get('cap_per_ion_mAh_g', 0.0)>0,
                                               cap_mAh_g / float(ion_params['cap_per_ion_mAh_g']), np.nan)
                    ions_abs = float(ion_params.get('start_ions', 0.0)) + ions_delta
                if ions_abs is not None:
                    ions_abs_arr = np.asarray(ions_abs, float)
                    t_arr = np.asarray(t, float)
                    if ions_abs_arr.size != t_arr.size:
                        raise ValueError("stored ions array length does not match EC time array")
                    setattr(ec_ax, '_ions_abs', ions_abs_arr)
                    from .ions_axis import install_ec_ions_y_display  # lazy: avoid operando→session cycle
                    install_ec_ions_y_display(ec_ax, t_arr, ions_abs_arr)
                    # Label (custom if set) - respect WASD right title state
                    right_title_on = ec_wasd.get('right', {}).get('title', True) if ec_wasd else True
                    if right_title_on:
                        lab = (ec_ax._custom_labels.get('y_ions') if getattr(ec_ax, '_custom_labels', {}).get('y_ions') else 'Number of ions')
                        ec_ax.set_ylabel(lab)
                    else:
                        ec_ax.set_ylabel('')  # Hidden by user via d5
                    ec_ax._ion_guides = []
                    for y_guide in ec.get('ion_guides', []) or []:
                        try:
                            ec_ax._ion_guides.append(ec_ax.axhline(y=float(y_guide), color='0.7', linestyle='--', linewidth=0.8, alpha=0.5, zorder=0))
                        except Exception:
                            pass
                    ec_ax._ion_annots = []
                    for ann in ec.get('ion_annots', []) or []:
                        try:
                            txt = ec_ax.annotate(str(ann.get('text', '')), xy=tuple(ann.get('xy', (0.0, 0.0))), xytext=(0, 4), textcoords='offset points',
                                                 ha='right', va='bottom', fontsize=9,
                                                 bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='0.7', alpha=0.8))
                            ec_ax._ion_annots.append(txt)
                        except Exception:
                            pass
            except Exception:
                pass
        else:
            # Time mode label - respect WASD right title state
            right_title_on = ec_wasd.get('right', {}).get('title', True) if ec_wasd else True
            if right_title_on:
                lab = (ec_ax._custom_labels.get('y_time') if getattr(ec_ax, '_custom_labels', {}).get('y_time') else 'Time (h)')
                try:
                    ec_ax.set_ylabel(lab)
                except Exception:
                    pass
            else:
                ec_ax.set_ylabel('')  # Hidden by user via d5
        
        # Restore stored ylabel if present (for cases where ylabel was hidden)
        stored_ylabel = ec.get('stored_ylabel')
        if stored_ylabel is not None:
            setattr(ec_ax, '_stored_ylabel', stored_ylabel)
        
        # Restore EC title offsets
        try:
            ec_title_offsets = ec.get('title_offsets', {})
            if ec_title_offsets:
                ec_ax._top_xlabel_manual_offset_y_pts = float(ec_title_offsets.get('top_y', 0.0) or 0.0)
                ec_ax._top_xlabel_manual_offset_x_pts = float(ec_title_offsets.get('top_x', 0.0) or 0.0)
                ec_ax._bottom_xlabel_manual_offset_y_pts = float(ec_title_offsets.get('bottom_y', 0.0) or 0.0)
                ec_ax._left_ylabel_manual_offset_x_pts = float(ec_title_offsets.get('left_x', 0.0) or 0.0)
                ec_ax._right_ylabel_manual_offset_x_pts = float(ec_title_offsets.get('right_x', 0.0) or 0.0)
                ec_ax._right_ylabel_manual_offset_y_pts = float(ec_title_offsets.get('right_y', 0.0) or 0.0)
        except Exception:
            pass
        
        # Apply EC spines (WASD state already applied above)
        if version >= 2:
            # Apply EC spines
            ec_spines = ec.get('spines', {})
            if ec_spines:
                try:
                    for name, props in ec_spines.items():
                        sp = ec_ax.spines.get(name)
                        if not sp:
                            continue
                        if 'linewidth' in props and props['linewidth'] is not None:
                            try:
                                sp.set_linewidth(float(props['linewidth']))
                            except Exception:
                                pass
                        if 'visible' in props and props['visible'] is not None:
                            try:
                                sp.set_visible(bool(props['visible']))
                            except Exception:
                                pass
                        if 'color' in props and props['color'] is not None:
                            try:
                                _set_spine_side_color(ec_ax, name, props['color'], fig=fig)
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # Apply EC tick widths
            ec_tick_widths = ec.get('ticks', {}).get('widths', {})
            if ec_tick_widths:
                try:
                    if ec_tick_widths.get('x_major'): ec_ax.tick_params(axis='x', which='major', width=ec_tick_widths['x_major'])
                    if ec_tick_widths.get('x_minor'): ec_ax.tick_params(axis='x', which='minor', width=ec_tick_widths['x_minor'])
                    if ec_tick_widths.get('y_major'): ec_ax.tick_params(axis='y', which='major', width=ec_tick_widths['y_major'])
                    if ec_tick_widths.get('y_minor'): ec_ax.tick_params(axis='y', which='minor', width=ec_tick_widths['y_minor'])
                except Exception:
                    pass
            _apply_session_tick_lengths(fig, [ec_ax], ec.get('ticks', {}).get('lengths'))
            try:
                tick_direction = ec.get('ticks', {}).get('direction')
                if tick_direction:
                    setattr(fig, '_tick_direction', tick_direction)
                    ec_ax.tick_params(axis='both', which='both', direction=tick_direction)
            except Exception:
                pass
            # Restore tick locator state for ec_ax, then re-apply WASD minor visibility
            try:
                _restore_session_tick_locator(ec_ax, ec.get('tick_locator_state'))
                if ec_wasd and isinstance(ec_wasd, dict):
                    apply_wasd_minor_ticks(ec_ax, ec_wasd, y_minor_mode='right')
            except Exception:
                pass

    try:
        finalize_spine_colors_for_axes(
            fig,
            [
                (ax, getattr(ax, '_saved_tick_state', None)),
                (ec_ax, getattr(ec_ax, '_saved_tick_state', None) if ec_ax is not None else None),
            ],
        )
    except Exception:
        pass

    # Persist fixed inch parameters from loaded session to attributes
    # This ensures interactive menu can read correct values
    try:
        setattr(cbar_ax, '_fixed_cb_w_in', float(li['cb_w_in']))
        setattr(cbar_ax, '_fixed_cb_gap_in', float(li['cb_gap_in']))
        setattr(cbar_ax, '_cb_gap_adjusted', True)
        setattr(ax, '_fixed_ax_w_in', float(li['ax_w_in']))
        setattr(ax, '_fixed_ax_h_in', float(li['ax_h_in']))
        # Restore horizontal offsets
        cb_h_offset = li.get('cb_h_offset', 0.0)
        ec_h_offset = li.get('ec_h_offset')
        setattr(cbar_ax, '_cb_h_offset_in', float(cb_h_offset))
        if ec_ax is not None:
            setattr(ec_ax, '_fixed_ec_gap_in', float(li.get('ec_gap_in', 0.0)))
            setattr(ec_ax, '_fixed_ec_w_in', float(li.get('ec_w_in', 0.0)))
            # Set flags to prevent auto-adjustment of loaded session geometry
            setattr(ec_ax, '_ec_gap_adjusted', True)
            setattr(ec_ax, '_ec_op_width_adjusted', True)
            if ec_h_offset is not None:
                setattr(ec_ax, '_ec_h_offset_in', float(ec_h_offset))
            else:
                setattr(ec_ax, '_ec_h_offset_in', 0.0)
        elif ec_h_offset is not None:
            # EC panel doesn't exist but offset was saved - ignore it
            pass
        
        # Apply layout with loaded offsets to ensure visual position matches saved position
        # This must happen after all offsets and geometry parameters are set
        try:
            from .layout import _apply_group_layout_inches, _ensure_fixed_params
            # Get current geometry parameters (which should match what was just loaded)
            cb_w_i, cb_gap_i, ec_gap_i, ec_w_i, ax_w_i, ax_h_i = _ensure_fixed_params(fig, ax, cbar_ax, ec_ax)
            # Apply layout with loaded offsets (offsets are already set as attributes above)
            _apply_group_layout_inches(fig, ax, cbar_ax, ec_ax, ax_w_i, ax_h_i, cb_w_i, cb_gap_i, ec_gap_i, ec_w_i)
        except Exception:
            # If layout application fails, continue - better to have a slightly wrong layout than crash
            pass
    except Exception:
        pass

    # Apply saved fonts and trigger a refresh redraw
    try:
        f = sess.get('font', {})
        if f.get('chain'):
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = f['chain']
        if f.get('size'):
            plt.rcParams['font.size'] = f['size']
        if f.get('mathtext_fontset'):
            plt.rcParams['mathtext.fontset'] = f['mathtext_fontset']
    except Exception:
        pass

    # Restore visibility states for colorbar and EC panel
    try:
        cb_meta = sess.get('colorbar', {})
        cb_visible = cb_meta.get('visible', True)  # Default to visible if not saved
        cbar.ax.set_visible(bool(cb_visible))
    except Exception:
        pass
    
    try:
        if ec_ax is not None:
            ec = sess.get('ec') or {}
            ec_visible = ec.get('visible', True)  # Default to visible if not saved
            ec_ax.set_visible(bool(ec_visible))
            ec_grid = ec.get('grid') or {}
            if ec_grid:
                g = dict(ec_grid)
                g.setdefault('visible', False)
                g.setdefault('alpha', 0.3)
                g.setdefault('linestyle', '--')
                g.setdefault('color', '0.6')
                g.setdefault('which', 'major')
                ec_ax._ec_grid = g
                ec_ax.grid(
                    g['visible'],
                    which=g['which'],
                    axis='both',
                    alpha=float(g['alpha']),
                    color=str(g['color']),
                    linestyle=str(g['linestyle']),
                )
    except Exception:
        pass

    # Restore CIF tick labels (operando) if present
    try:
        cif = sess.get('cif')
        if cif and cif.get('tick_series'):
            ax._operando_cif_tick_series = cif['tick_series']
            ax._operando_cif_hkl_label_map = cif.get('hkl_label_map', {})
            fig._operando_cif_show_hkl = bool(cif.get('show_hkl', False))
            fig._operando_cif_show_titles = bool(cif.get('show_titles', True))
            fig._operando_cif_placement = str(cif.get('placement', 'below'))
            fig._operando_cif_y_positions = list(cif.get('y_positions', []) or [])
            fig._operando_cif_colormap = cif.get('colormap')
            fig._operando_cif_highlight = bool(cif.get('highlight', False))
            fig._operando_cif_title_font = dict(cif.get('title_font') or {})
            fig._operando_cif_title_visible = list(cif.get('title_visible') or [])
            fig._operando_cif_set_visible = list(cif.get('set_visible') or [])
            fig._operando_axis_mode = str(cif.get('axis_mode', '2theta'))
            fig._operando_wl = cif.get('wl')
            ax_pos = ax.get_position()
            y_base = ax_pos.ymin - 0.02 if fig._operando_cif_placement == 'below' else ax_pos.ymax + 0.02
            dy = -0.025 if fig._operando_cif_placement == 'below' else 0.025
            while len(fig._operando_cif_y_positions) < len(ax._operando_cif_tick_series):
                fig._operando_cif_y_positions.append(y_base + len(fig._operando_cif_y_positions) * dy)
            from .plot import _draw_operando_cif_ticks
            _draw_operando_cif_ticks(ax, fig, ax._operando_cif_tick_series, ax._operando_cif_hkl_label_map,
                                    axis_mode=fig._operando_axis_mode, wl=fig._operando_wl,
                                    show_hkl=fig._operando_cif_show_hkl, show_titles=fig._operando_cif_show_titles,
                                    placement=fig._operando_cif_placement, y_positions=fig._operando_cif_y_positions)
    except Exception:
        pass

    try:
        fig._operando_session_loaded = True
        if ec_ax is not None:
            setattr(ec_ax, '_xlim_expanded_default', True)
        from .layout import _finalize_operando_session_axes
        _finalize_operando_session_axes(fig, ax, ec_ax)
    except Exception:
        pass

    # Return tuple
    # Rebuild legend based on visible lines
    try:
        handles = []
        labels = []
        for ln in ax.lines:
            if ln.get_visible() and not (ln.get_label() or '').startswith('_'):
                handles.append(ln)
                labels.append(ln.get_label() or '')
        if handles:
            ax.legend(handles, labels)
        else:
            leg = ax.get_legend()
            if leg is not None:
                try:
                    leg.remove()
                except Exception:
                    pass
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
        from ..common.fonts import collect_operando_font_artists

        apply_session_font_cfg(
            fig,
            sess.get('font', {}) or {},
            ax,
            ec_ax,
            artists=collect_operando_font_artists(fig, ax, ec_ax, cbar),
        )
    except Exception:
        pass
    return fig, ax, im, cbar, ec_ax
