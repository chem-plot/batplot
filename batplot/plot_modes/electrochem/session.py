"""Electrochemistry session dump/load (mode-owned implementation).

Moved from :mod:`batplot.session`. Shared helpers come from
``plot_modes.common.session_helpers``.
"""

from __future__ import annotations

import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.colors import to_hex, to_rgba  # type: ignore[import-untyped]
from matplotlib.ticker import AutoMinorLocator, NullFormatter  # type: ignore[import-untyped]

from ...utils import _confirm_overwrite
from ...ui import (
    set_spine_side_color as _set_spine_side_color,
    finalize_spine_colors,
    apply_wasd_minor_ticks,
)
from ..common.font_extras import apply_session_font_cfg, merge_session_font_dump
from ..common.axis_state import capture_axis_wasd_state
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


def _axis_label_text(ax, attr_name: str, getter):
    """
    Get axis label text, trying stored value first, then current label.
    
    HOW IT WORKS:
    ------------
    Sometimes axis labels are hidden but we still want to know what they were.
    This function tries two sources:
    
    1. **Stored attribute**: Check if label was saved in a special attribute
       - Example: ax._stored_xlabel might contain "Potential (V)" even if label is hidden
       - This preserves the label text when labels are temporarily hidden
    
    2. **Current label**: Get text from the actual label object
       - Example: ax.xaxis.label.get_text()
       - This is the "live" label that's currently displayed
    
    WHY TWO SOURCES?
    ---------------
    When labels are hidden (via WASD menu), the label object might be empty,
    but we saved the text in a stored attribute. This function ensures we can
    always retrieve the label text, even when hidden.
    
    Args:
        ax: Matplotlib axes object
        attr_name: Name of stored attribute (e.g., '_stored_xlabel')
        getter: Function to call to get current label (e.g., lambda: ax.get_xlabel())
    
    Returns:
        Label text string, or empty string if not found
    """
    # Try stored attribute first (preserves text even when label is hidden)
    try:
        stored = getattr(ax, attr_name)
        if isinstance(stored, str) and stored:
            return stored
    except Exception:
        pass
    
    # Fallback: get from current label object
    try:
        return getter() or ''  # getter() returns current label text
    except Exception:
        return ''



def _ec_attach_line_data_extras(ln, payload: Dict[str, Any]) -> None:
    """Persist recoverable pre-filter / dual-axis backups on a line payload."""
    try:
        if hasattr(ln, '_orig_xdata_gc'):
            payload['orig_xdata_gc'] = np.asarray(getattr(ln, '_orig_xdata_gc'), float)
    except Exception:
        pass
    try:
        if hasattr(ln, '_original_xdata') and hasattr(ln, '_original_ydata'):
            payload['original_xdata'] = np.asarray(getattr(ln, '_original_xdata'), float)
            payload['original_ydata'] = np.asarray(getattr(ln, '_original_ydata'), float)
    except Exception:
        pass
    try:
        if bool(getattr(ln, '_smooth_applied', False)):
            payload['smooth_applied'] = True
    except Exception:
        pass


def _ec_restore_line_data_extras(ln_obj, rec: Dict[str, Any]) -> None:
    """Restore pre-filter / dual-axis backups onto a reloaded line artist."""
    try:
        if rec.get('orig_xdata_gc') is not None:
            setattr(ln_obj, '_orig_xdata_gc', np.asarray(rec.get('orig_xdata_gc'), float))
    except Exception:
        pass
    try:
        ox = rec.get('original_xdata')
        oy = rec.get('original_ydata')
        if ox is not None and oy is not None:
            setattr(ln_obj, '_original_xdata', np.asarray(ox, float))
            setattr(ln_obj, '_original_ydata', np.asarray(oy, float))
    except Exception:
        pass
    try:
        if rec.get('smooth_applied'):
            setattr(ln_obj, '_smooth_applied', True)
    except Exception:
        pass


def _ec_cycle_lines_to_lines_state(cycle_lines: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Build serializable lines_state dict from cycle_lines (GC or CV mode)."""
    lines_state: Dict[int, Dict[str, Any]] = {}
    for cyc, parts in cycle_lines.items():
        entry: Dict[str, Any] = {}
        if isinstance(parts, dict):
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is None:
                    entry[role] = None
                    continue
                try:
                    x = np.asarray(ln.get_xdata(), float)
                    y = np.asarray(ln.get_ydata(), float)
                except Exception:
                    x = np.array([]); y = np.array([])
                try:
                    color_raw = ln.get_color()
                    try:
                        color_hex = to_hex(color_raw)
                    except Exception:
                        try:
                            color_hex = to_hex(to_rgba(color_raw))
                        except Exception:
                            color_hex = color_raw if isinstance(color_raw, str) else 'tab:blue'
                    st = {
                        'color': color_hex,
                        'linewidth': float(ln.get_linewidth() or 1.0),
                        'linestyle': ln.get_linestyle() or '-',
                        'alpha': ln.get_alpha(),
                        'visible': bool(ln.get_visible()),
                        'label': ln.get_label() or '',
                        'marker': ln.get_marker(),
                        'markersize': ln.get_markersize(),
                        'markerfacecolor': ln.get_markerfacecolor(),
                        'markeredgecolor': ln.get_markeredgecolor(),
                    }
                except Exception:
                    st = {'color': '#1f77b4', 'linewidth': 1.0, 'linestyle': '-', 'alpha': None, 'visible': True, 'label': ''}
                payload = {'x': x, 'y': y, 'style': st}
                _ec_attach_line_data_extras(ln, payload)
                entry[role] = payload
        else:
            ln = parts
            try:
                x = np.asarray(ln.get_xdata(), float)
                y = np.asarray(ln.get_ydata(), float)
            except Exception:
                x = np.array([]); y = np.array([])
            try:
                color_raw = ln.get_color()
                try:
                    color_hex = to_hex(color_raw)
                except Exception:
                    try:
                        color_hex = to_hex(to_rgba(color_raw))
                    except Exception:
                        color_hex = color_raw if isinstance(color_raw, str) else 'tab:blue'
                st = {
                    'color': color_hex,
                    'linewidth': float(ln.get_linewidth() or 1.0),
                    'linestyle': ln.get_linestyle() or '-',
                    'alpha': ln.get_alpha(),
                    'visible': bool(ln.get_visible()),
                    'label': ln.get_label() or '',
                    'marker': ln.get_marker(),
                    'markersize': ln.get_markersize(),
                    'markerfacecolor': ln.get_markerfacecolor(),
                    'markeredgecolor': ln.get_markeredgecolor(),
                }
            except Exception:
                st = {'color': '#1f77b4', 'linewidth': 1.0, 'linestyle': '-', 'alpha': None, 'visible': True, 'label': ''}
            payload = {'x': x, 'y': y, 'style': st}
            _ec_attach_line_data_extras(ln, payload)
            entry['line'] = payload
        lines_state[int(cyc)] = entry
    return lines_state


def dump_ec_session(
    filename: str,
    *,
    fig,
    ax,
    cycle_lines: Dict[int, Dict[str, Any]],
    file_data: Optional[List[Dict[str, Any]]] = None,
    skip_confirm: bool = False,
) -> None:
    """Serialize electrochem GC plot (capacity vs voltage) including data and styles.

    Stores figure size/dpi, axis labels/limits, and for each cycle the charge and
    discharge line data (x,y) and basic line styles. When file_data is provided
    and has more than one file, saves multi-file session (all files' curves and
    visibility).
    
    Args:
        file_data: Optional list of multi-file dicts (filename, filepath, visible, cycle_lines).
            When len(file_data) > 1, session is saved as multi-file.
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).
    """
    try:
        fig_w, fig_h = map(float, fig.get_size_inches())
        dpi = int(fig.dpi)
        # Capture axis state
        # Label pads
        try:
            _xlp = float(getattr(ax.xaxis, 'labelpad', 0.0))
        except Exception:
            _xlp = 0.0
        try:
            _ylp = float(getattr(ax.yaxis, 'labelpad', 0.0))
        except Exception:
            _ylp = 0.0
        axis = {
            'xlabel': _axis_label_text(ax, '_stored_xlabel', ax.get_xlabel),
            'ylabel': _axis_label_text(ax, '_stored_ylabel', ax.get_ylabel),
            'xlim': tuple(map(float, ax.get_xlim())),
            'ylim': tuple(map(float, ax.get_ylim())),
            'xscale': getattr(ax, 'get_xscale', lambda: 'linear')(),
            'yscale': getattr(ax, 'get_yscale', lambda: 'linear')(),
            'x_labelpad': _xlp,
            'y_labelpad': _ylp,
            'xlabel_visible': bool(ax.xaxis.label.get_visible()),
            'ylabel_visible': bool(ax.yaxis.label.get_visible()),
            'xlabel_color': ax.xaxis.label.get_color(),
            'ylabel_color': ax.yaxis.label.get_color(),
        }
        # Capture WASD state
        wasd_state = capture_axis_wasd_state(ax)
        
        # Tick visibility state (if present from interactive menu) - kept for backward compatibility
        tick_state = dict(getattr(ax, '_saved_tick_state', {
            'bx': True, 'tx': False, 'ly': True, 'ry': False,
            'mbx': False, 'mtx': False, 'mly': False, 'mry': False,
        }))
        # Representative tick widths
        def _tick_width(axis, which: str):
            return _current_tick_width(axis, which)
        tick_widths = {
            'x_major': _tick_width(ax.xaxis, 'major'),
            'x_minor': _tick_width(ax.xaxis, 'minor'),
            'y_major': _tick_width(ax.yaxis, 'major'),
            'y_minor': _tick_width(ax.yaxis, 'minor'),
        }
        tick_lengths = {
            'x_major': _current_tick_length(ax.xaxis, 'major'),
            'x_minor': _current_tick_length(ax.xaxis, 'minor'),
            'y_major': _current_tick_length(ax.yaxis, 'major'),
            'y_minor': _current_tick_length(ax.yaxis, 'minor'),
        }
        # Tick direction
        tick_direction = getattr(fig, '_tick_direction', 'out')
        # Spines state
        spines_state = {
            name: {
                'linewidth': (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None),
                'visible': (ax.spines.get(name).get_visible() if ax.spines.get(name) else None),
                'color': (ax.spines.get(name).get_edgecolor() if ax.spines.get(name) else None),
            } for name in ('bottom','top','left','right')
        }
        # Duplicate axis title flags
        titles = {
            'top_x': bool(getattr(ax, '_top_xlabel_on', False)),
            'right_y': bool(getattr(ax, '_right_ylabel_on', False)),
        }
        # Title offsets
        title_offsets = {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        }
        # Subplot margins
        sp = fig.subplotpars
        subplot_margins = {
            'left': float(sp.left),
            'right': float(sp.right),
            'bottom': float(sp.bottom),
            'top': float(sp.top),
        }
        # Plot frame size + exact axes bbox (same strategy as XY/CPC sessions)
        bbox = ax.get_position()
        fig_w, fig_h = fig.get_size_inches()
        frame_w_in = float(bbox.width) * float(fig_w)
        frame_h_in = float(bbox.height) * float(fig_h)
        # Capture cycles: single-file (lines_state) or multi-file (file_data with lines per file)
        file_data_saved: Optional[List[Dict[str, Any]]]
        if file_data is not None and len(file_data) > 1:
            file_data_saved = []
            for f in file_data:
                cl = f.get("cycle_lines") or {}
                lines_state_f = _ec_cycle_lines_to_lines_state(cl)
                file_data_saved.append({
                    "filename": f.get("filename", "Data"),
                    "display_name": f.get("display_name", f.get("filename", "Data")),
                    "filepath": f.get("filepath"),
                    "visible": bool(f.get("visible", True)),
                    "lines": lines_state_f,
                })
            lines_state = {}
        else:
            file_data_saved = None
            lines_state = _ec_cycle_lines_to_lines_state(cycle_lines)
        legend_visible = False
        legend_xy_in = None
        try:
            leg = ax.get_legend()
            if leg is not None:
                legend_visible = bool(leg.get_visible())
            xy = getattr(fig, '_ec_legend_xy_in', None)
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                legend_xy_in = (float(xy[0]), float(xy[1]))
        except Exception:
            legend_xy_in = None
        dual_top_axis = None
        try:
            secax = getattr(fig, '_xaxis_secondary', None)
            if secax is not None:
                top_spine = secax.spines.get('top')
                dual_top_axis = {
                    'xlabel': secax.get_xlabel(),
                    'xlabel_visible': bool(secax.xaxis.label.get_visible()),
                    'label_color': to_hex(secax.xaxis.label.get_color()),
                    'spine_visible': bool(top_spine.get_visible()) if top_spine is not None else True,
                    'spine_color': to_hex(top_spine.get_edgecolor()) if top_spine is not None else None,
                }
        except Exception:
            dual_top_axis = None
        sess = {
            'kind': 'ec_gc',
            'version': 2,
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
            },
            # Keep top-level aliases for backward compatibility with existing loader keys.
            'frame_size': (frame_w_in, frame_h_in),
            'axis': axis,
            'subplot_margins': subplot_margins,
            'lines': lines_state,
            'multi_file': file_data_saved is not None,
            'file_data': file_data_saved if file_data_saved is not None else None,
            'font': merge_session_font_dump(fig),
            'legend': {
                'visible': legend_visible,
                'position_inches': legend_xy_in,
                'title': getattr(fig, '_ec_legend_title', None) or "Cycle",
            },
            'legend_file_order': list(getattr(fig, '_ec_legend_file_order', None) or []) if (file_data is not None and len(file_data) > 1) else None,
            'wasd_state': wasd_state,
            'tick_state': tick_state,
            'tick_widths': tick_widths,
            'tick_lengths': tick_lengths,
            'tick_direction': tick_direction,
            'tick_locator_state': _capture_session_tick_locator(ax),
            'spines': spines_state,
            'titles': titles,
            'title_offsets': title_offsets,
            'mode': getattr(ax, '_is_dqdv_mode', None),  # Store dQdV mode flag
            'display_mode': getattr(fig, '_ec_display_mode', 'both'),  # charge/discharge/both
            'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),  # Store rotation angle
            'dqdv_smooth_settings': (
                dict(getattr(fig, '_dqdv_smooth_settings', {}))
                if hasattr(fig, '_dqdv_smooth_settings') else None
            ),
            'source_paths': list(getattr(fig, '_bp_source_paths', []) or []),
            'grid': ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else (
                any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()) if hasattr(ax, 'get_xgridlines') else False
            ),
            'xaxis_dual': {
                'mode': getattr(fig, '_xaxis_mode', 'capacity'),
                'c_theoretical': getattr(fig, '_xaxis_c_theoretical', None),
                'swapped': getattr(fig, '_xaxis_swapped', False),
                'top_axis': dual_top_axis,
            },
            'ro_active': bool(getattr(fig, '_ro_active', False)),
        }
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("EC session save canceled.")
                return
        try:
            snap = getattr(fig, '_dqdv_2d_snapshot', None)
            if isinstance(snap, dict) and snap.get('Z') is not None:
                sess['dqdv_2d'] = snap
        except Exception as e:
            print(f"Warning: could not embed dQ/dV 2D snapshot in EC session: {e}")
        sess['package_versions'] = _package_versions_stamp()
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"EC session saved to {target}")
    except Exception as e:
        print(f"Error saving EC session: {e}")


def load_ec_session(
    filename: str,
    parent_fig: Optional[Any] = None,
    rect: Optional[Tuple[float, float, float, float]] = None,
) -> Optional[Tuple[Any, ...]]:
    """Load an EC GC session and reconstruct figure, axes, and cycle_lines or file_data.

    Returns: (fig, ax, cycle_lines) for single-file sessions, or (fig, ax, None, file_data) for multi-file.

    If parent_fig and rect are provided, draws into parent_fig.add_axes(rect) instead of creating
    a new figure (for canvas embedding). rect is (left, bottom, width, height) in figure coords.
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
        print(f"Failed to load EC session: {e}")
        return None

    if not isinstance(sess, dict) or sess.get('kind') != 'ec_gc':
        print("Not an EC GC session file.")
        return None

    embed = parent_fig is not None and rect is not None

    if embed:
        assert parent_fig is not None and rect is not None
        fig = parent_fig
        ax = fig.add_axes(rect)
    else:
        # Use standard DPI of 100 instead of saved DPI to avoid display-dependent issues
        fig = plt.figure(figsize=tuple(sess['figure']['size']), dpi=100)
        try:
            fig.set_layout_engine('none')
        except Exception:
            try:
                fig.set_tight_layout(False)
            except Exception:
                pass
        ax = fig.add_subplot(111)

    # Seed last-session path so 'os' overwrite command is available immediately
    try:
        fig._last_session_save_path = os.path.abspath(filename)
    except Exception:
        pass
    try:
        fig._bp_source_paths = list(sess.get('source_paths', []) or [])
    except Exception:
        fig._bp_source_paths = []
    try:
        session_abs = os.path.abspath(filename)
        sources = list(getattr(fig, '_bp_source_paths', []) or [])
        if session_abs not in sources:
            sources.append(session_abs)
        fig._bp_source_paths = sources
    except Exception:
        pass

    def _sanitize_legend_offset(xy):
        if xy is None or not isinstance(xy, (list, tuple)) or len(xy) != 2:
            return None
        try:
            x_val = float(xy[0])
            y_val = float(xy[1])
        except Exception:
            return None
        fw, fh = fig.get_size_inches()
        if fw <= 0 or fh <= 0:
            return None
        max_offset = max(fw, fh) * 2.0
        if abs(x_val) > max_offset or abs(y_val) > max_offset:
            return None
        return (x_val, y_val)
    # Fonts
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

    # Apply subplot margins early (prevents label clipping on draw) - skip when embedding
    if not embed:
        try:
            spm = sess.get('subplot_margins', {})
            if all(k in spm for k in ('left','right','bottom','top')):
                fig.subplots_adjust(left=float(spm['left']), right=float(spm['right']), bottom=float(spm['bottom']), top=float(spm['top']))

            fig_meta = sess.get('figure', {}) if isinstance(sess.get('figure', {}), dict) else {}
            axes_bbox = fig_meta.get('axes_bbox')
            if axes_bbox:
                _apply_axes_bbox(ax, axes_bbox)

            frame_size = sess.get('frame_size') or fig_meta.get('frame_size')
            if (not axes_bbox) and frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                target_w_in, target_h_in = map(float, frame_size)
                canvas_w_in, canvas_h_in = fig.get_size_inches()
                if canvas_w_in > 0 and canvas_h_in > 0:
                    bbox = ax.get_position()
                    center_x = (bbox.x0 + bbox.x1) / 2.0
                    center_y = (bbox.y0 + bbox.y1) / 2.0
                    new_w_frac = target_w_in / canvas_w_in
                    new_h_frac = target_h_in / canvas_h_in
                    new_left = center_x - new_w_frac / 2.0
                    new_right = center_x + new_w_frac / 2.0
                    new_bottom = center_y - new_h_frac / 2.0
                    new_top = center_y + new_h_frac / 2.0
                    fig.subplots_adjust(left=new_left, right=new_right, bottom=new_bottom, top=new_top)
        except Exception:
            pass

    # Rebuild lines (single-file or multi-file)
    def _rebuild_lines_from_raw(raw: Dict) -> Dict[int, Any]:
        out: Dict[int, Any] = {}
        for k in sorted(raw.keys(), key=lambda x: int(x)):
            cyc = int(k)
            parts = raw.get(k) or {}
            if 'line' in parts:
                rec = parts.get('line')
                ln_obj = None
                if isinstance(rec, dict) and isinstance(rec.get('x'), np.ndarray) and isinstance(rec.get('y'), np.ndarray):
                    x = np.asarray(rec['x'], float)
                    y = np.asarray(rec['y'], float)
                    st = rec.get('style', {})
                    color = st.get('color', 'tab:blue')
                    lw = float(st.get('linewidth', 1.0))
                    ls = st.get('linestyle', '-') or '-'
                    alpha = st.get('alpha', None)
                    label = st.get('label', f'Cycle {cyc}')
                    marker = st.get('marker', None)
                    markersize = st.get('markersize', None)
                    markerfacecolor = st.get('markerfacecolor', None)
                    markeredgecolor = st.get('markeredgecolor', None)
                    try:
                        plot_kwargs = {
                            'linestyle': ls,
                            'linewidth': lw,
                            'color': color,
                            'alpha': alpha,
                            'label': label,
                        }
                        if marker is not None:
                            plot_kwargs['marker'] = marker
                        if markersize is not None:
                            plot_kwargs['markersize'] = markersize
                        ln_obj, = ax.plot(x, y, **plot_kwargs)
                        if markerfacecolor is not None:
                            ln_obj.set_markerfacecolor(markerfacecolor)
                        if markeredgecolor is not None:
                            ln_obj.set_markeredgecolor(markeredgecolor)
                        ln_obj.set_visible(bool(st.get('visible', True)))
                        _ec_restore_line_data_extras(ln_obj, rec)
                    except Exception:
                        pass
                out[cyc] = ln_obj
            else:
                cyc_entry: Dict[str, Any] = {}
                for role in ("charge", "discharge"):
                    rec = parts.get(role)
                    ln_obj = None
                    if isinstance(rec, dict) and isinstance(rec.get('x'), np.ndarray) and isinstance(rec.get('y'), np.ndarray):
                        x = np.asarray(rec['x'], float)
                        y = np.asarray(rec['y'], float)
                        st = rec.get('style', {})
                        color = st.get('color', 'tab:blue')
                        lw = float(st.get('linewidth', 1.0))
                        ls = st.get('linestyle', '-') or '-'
                        alpha = st.get('alpha', None)
                        label = st.get('label', f'Cycle {cyc}')
                        if role == 'discharge' and (not label or label.startswith('_')):
                            label = '_nolegend_'
                        marker = st.get('marker', None)
                        markersize = st.get('markersize', None)
                        markerfacecolor = st.get('markerfacecolor', None)
                        markeredgecolor = st.get('markeredgecolor', None)
                        try:
                            plot_kwargs = {
                                'linestyle': ls,
                                'linewidth': lw,
                                'color': color,
                                'alpha': alpha,
                                'label': label,
                            }
                            if marker is not None:
                                plot_kwargs['marker'] = marker
                            if markersize is not None:
                                plot_kwargs['markersize'] = markersize
                            ln_obj, = ax.plot(x, y, **plot_kwargs)
                            if markerfacecolor is not None:
                                ln_obj.set_markerfacecolor(markerfacecolor)
                            if markeredgecolor is not None:
                                ln_obj.set_markeredgecolor(markeredgecolor)
                            ln_obj.set_visible(bool(st.get('visible', True)))
                            _ec_restore_line_data_extras(ln_obj, rec)
                        except Exception:
                            pass
                    cyc_entry[role] = ln_obj
                out[cyc] = cyc_entry
        return out

    file_data_out: Optional[List[Dict[str, Any]]] = None
    if sess.get('multi_file') and sess.get('file_data'):
        file_data_out = []
        for f in sess['file_data']:
            raw_f = f.get('lines', {})
            cl = _rebuild_lines_from_raw(raw_f)
            file_data_out.append({
                'filename': f.get('filename', 'Data'),
                'display_name': f.get('display_name', f.get('filename', 'Data')),
                'filepath': f.get('filepath'),
                'visible': bool(f.get('visible', True)),
                'cycle_lines': cl,
            })
        cycle_lines = {}
    else:
        raw = sess.get('lines', {})
        cycle_lines = _rebuild_lines_from_raw(raw)

    # Axis labels/limits/scales
    # Store the labels first, then apply WASD state before actually setting them
    try:
        axis = sess.get('axis', {})
        stored_xlabel = axis.get('xlabel') or ''
        stored_ylabel = axis.get('ylabel') or ''
        xlabel_visible = axis.get('xlabel_visible', True)
        ylabel_visible = axis.get('ylabel_visible', True)
        xlabel_color = axis.get('xlabel_color')
        ylabel_color = axis.get('ylabel_color')
        
        # Scales first
        try:
            if axis.get('xscale'): ax.set_xscale(axis.get('xscale'))
            if axis.get('yscale'): ax.set_yscale(axis.get('yscale'))
        except Exception:
            pass
        if axis.get('xlim'): ax.set_xlim(*axis['xlim'])
        if axis.get('ylim'): ax.set_ylim(*axis['ylim'])
        # Label pads saved for later
        x_labelpad = axis.get('x_labelpad')
        y_labelpad = axis.get('y_labelpad')
    except Exception:
        stored_xlabel = ''
        stored_ylabel = ''
        x_labelpad = None
        y_labelpad = None
        xlabel_visible = True
        ylabel_visible = True
        xlabel_color = None
        ylabel_color = None
    if stored_xlabel:
        try:
            ax._stored_xlabel = stored_xlabel
        except Exception:
            pass
    if stored_ylabel:
        try:
            ax._stored_ylabel = stored_ylabel
        except Exception:
            pass
    try:
        if xlabel_color:
            ax._stored_xlabel_color = xlabel_color
        else:
            ax._stored_xlabel_color = ax.xaxis.label.get_color()
    except Exception:
        pass
    try:
        if ylabel_color:
            ax._stored_ylabel_color = ylabel_color
        else:
            ax._stored_ylabel_color = ax.yaxis.label.get_color()
    except Exception:
        pass
    if not hasattr(ax, '_stored_top_xlabel_color'):
        ax._stored_top_xlabel_color = ax.xaxis.label.get_color()
    if not hasattr(ax, '_stored_right_ylabel_color'):
        ax._stored_right_ylabel_color = ax.yaxis.label.get_color()

    # Spines
    try:
        sp_meta = sess.get('spines', {})
        for name, spec in sp_meta.items():
            sp = ax.spines.get(name)
            if not sp:
                continue
            if spec.get('linewidth') is not None:
                try:
                    sp.set_linewidth(float(spec['linewidth']))
                except Exception:
                    pass
            if spec.get('visible') is not None:
                try:
                    sp.set_visible(bool(spec['visible']))
                except Exception:
                    pass
            if spec.get('color') is not None:
                try:
                    _set_spine_side_color(ax, name, spec['color'], fig=fig)
                    if name == 'top':
                        ax._stored_top_xlabel_color = spec['color']
                    elif name == 'bottom':
                        ax._stored_xlabel_color = spec['color']
                    elif name == 'left':
                        ax._stored_ylabel_color = spec['color']
                    elif name == 'right':
                        ax._stored_right_ylabel_color = spec['color']
                except Exception:
                    pass
    except Exception:
        pass

    # Apply WASD state if version 2+
    version = sess.get('version', 1)
    wasd = None
    if version >= 2:
        wasd = sess.get('wasd_state')
        if wasd and isinstance(wasd, dict):
            try:
                # Apply spines
                for side in ('top', 'bottom', 'left', 'right'):
                    if side in wasd and 'spine' in wasd[side]:
                        sp = ax.spines.get(side)
                        if sp:
                            sp.set_visible(bool(wasd[side]['spine']))
                # Apply ticks
                ax.tick_params(axis='x', 
                              top=bool(wasd.get('top', {}).get('ticks', False)),
                              bottom=bool(wasd.get('bottom', {}).get('ticks', True)),
                              labeltop=bool(wasd.get('top', {}).get('labels', False)),
                              labelbottom=bool(wasd.get('bottom', {}).get('labels', True)))
                ax.tick_params(axis='y',
                              left=bool(wasd.get('left', {}).get('ticks', True)),
                              right=bool(wasd.get('right', {}).get('ticks', False)),
                              labelleft=bool(wasd.get('left', {}).get('labels', True)),
                              labelright=bool(wasd.get('right', {}).get('labels', False)))
                apply_wasd_minor_ticks(ax, wasd)
                # Store WASD state
                tick_state = {}
                for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                    s = wasd.get(side_key, {})
                    tick_state[f'{prefix}_ticks'] = bool(s.get('ticks', False))
                    tick_state[f'{prefix}_labels'] = bool(s.get('labels', False))
                    tick_state[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                ax._saved_tick_state = tick_state
                # Apply title flags
                ax._top_xlabel_on = bool(wasd.get('top', {}).get('title', False))
                ax._right_ylabel_on = bool(wasd.get('right', {}).get('title', False))
            except Exception as e:
                print(f"Warning: Could not apply WASD state: {e}")
        
        # Apply tick widths from version 2
        tw = sess.get('tick_widths', {})
        if tw:
            try:
                if tw.get('x_major') is not None: ax.tick_params(axis='x', which='major', width=float(tw['x_major']))
                if tw.get('x_minor') is not None: ax.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
                if tw.get('y_major') is not None: ax.tick_params(axis='y', which='major', width=float(tw['y_major']))
                if tw.get('y_minor') is not None: ax.tick_params(axis='y', which='minor', width=float(tw['y_minor']))
            except Exception:
                pass
        _apply_session_tick_lengths(fig, [ax], sess.get('tick_lengths'))
        
        # Apply tick direction from version 2
        try:
            tick_direction = sess.get('tick_direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
        except Exception:
            pass

        # Restore tick spacing and minor count (t > n and t > m commands)
        try:
            _restore_session_tick_locator(ax, sess.get('tick_locator_state'))
            if wasd and isinstance(wasd, dict):
                apply_wasd_minor_ticks(ax, wasd)
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
        
        # Apply rotation angle from version 2
        try:
            rotation_angle = sess.get('rotation_angle', 0)
            setattr(fig, '_ec_rotation_angle', rotation_angle)
        except Exception:
            pass
        # Restore display_mode (charge/discharge/both) and re-apply visibility
        try:
            dm = sess.get('display_mode', 'both')
            if dm in ('charge', 'discharge', 'both'):
                setattr(fig, '_ec_display_mode', dm)
                from .style_apply import _apply_display_mode

                _apply_display_mode(
                    dm,
                    cycle_lines=cycle_lines,
                    file_data=file_data_out,
                    is_multi_file=bool(file_data_out),
                    iter_cycle_lines=None,
                )
        except Exception:
            pass
        try:
            fig._ro_active = bool(sess.get('ro_active', False))
        except Exception:
            pass
    else:
        # Version 1 backward compatibility
        try:
            tick_state = sess.get('tick_state', {})
            # Persist on axes for interactive menu init
            ax._saved_tick_state = dict(tick_state)
            # Apply visibility
            ax.tick_params(axis='x',
                           bottom=tick_state.get('bx', True), labelbottom=tick_state.get('bx', True),
                           top=tick_state.get('tx', False),   labeltop=tick_state.get('tx', False))
            ax.tick_params(axis='y',
                           left=tick_state.get('ly', True),  labelleft=tick_state.get('ly', True),
                           right=tick_state.get('ry', False), labelright=tick_state.get('ry', False))
            # Minor ticks
            if tick_state.get('mbx') or tick_state.get('mtx'):
                ax.xaxis.set_minor_locator(AutoMinorLocator())
                ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor',
                               bottom=tick_state.get('mbx', False),
                               top=tick_state.get('mtx', False),
                               labelbottom=False, labeltop=False)
            else:
                ax.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
            if tick_state.get('mly') or tick_state.get('mry'):
                ax.yaxis.set_minor_locator(AutoMinorLocator())
                ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor',
                               left=tick_state.get('mly', False),
                               right=tick_state.get('mry', False),
                               labelleft=False, labelright=False)
            else:
                ax.tick_params(axis='y', which='minor', left=False, right=False, labelleft=False, labelright=False)
            # Widths
            tw = sess.get('tick_widths', {})
            if tw.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=tw['x_major'])
            if tw.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=tw['x_minor'])
            if tw.get('y_major') is not None:
                ax.tick_params(axis='y', which='major', width=tw['y_major'])
            if tw.get('y_minor') is not None:
                ax.tick_params(axis='y', which='minor', width=tw['y_minor'])
        except Exception:
            pass

    # Restore axis labels/visibility after WASD application
    def _title_pref(side_visible: bool, side_key: str):
        if wasd and isinstance(wasd, dict):
            entry = wasd.get(side_key, {})
            if 'title' in entry:
                return bool(entry.get('title'))
        return bool(side_visible)
    bottom_pref = _title_pref(xlabel_visible, 'bottom')
    left_pref = _title_pref(ylabel_visible, 'left')
    if bottom_pref and stored_xlabel:
        ax.set_xlabel(stored_xlabel)
        ax.xaxis.label.set_visible(True)
        color = getattr(ax, '_stored_xlabel_color', None)
        if color:
            ax.xaxis.label.set_color(color)
    else:
        ax.set_xlabel('')
        ax.xaxis.label.set_visible(False)
    if left_pref and stored_ylabel:
        ax.set_ylabel(stored_ylabel)
        ax.yaxis.label.set_visible(True)
        color = getattr(ax, '_stored_ylabel_color', None)
        if color:
            ax.yaxis.label.set_color(color)
    else:
        ax.set_ylabel('')
        ax.yaxis.label.set_visible(False)

    # Restore title offsets BEFORE positioning titles
    try:
        title_offsets = sess.get('title_offsets', {})
        if title_offsets:
            ax._top_xlabel_manual_offset_y_pts = float(title_offsets.get('top_y', 0.0) or 0.0)
            ax._top_xlabel_manual_offset_x_pts = float(title_offsets.get('top_x', 0.0) or 0.0)
            ax._bottom_xlabel_manual_offset_y_pts = float(title_offsets.get('bottom_y', 0.0) or 0.0)
            ax._left_ylabel_manual_offset_x_pts = float(title_offsets.get('left_x', 0.0) or 0.0)
            ax._right_ylabel_manual_offset_x_pts = float(title_offsets.get('right_x', 0.0) or 0.0)
            ax._right_ylabel_manual_offset_y_pts = float(title_offsets.get('right_y', 0.0) or 0.0)
    except Exception:
        pass
    
    # Duplicate titles
    try:
        titles = sess.get('titles', {})
        if titles.get('top_x'):
            lbl = ax.get_xlabel() or ''
            if lbl:
                txt = getattr(ax, '_top_xlabel_artist', None)
                if txt is None:
                    txt = ax.text(0.5, 1.02, lbl, ha='center', va='bottom', transform=ax.transAxes)
                    ax._top_xlabel_artist = txt
                else:
                    txt.set_text(lbl); txt.set_visible(True)
                ax._top_xlabel_on = True
                try:
                    color = getattr(ax, '_stored_top_xlabel_color', None)
                    if color and txt is not None:
                        txt.set_color(color)
                except Exception:
                    pass
        else:
            if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                try: ax._top_xlabel_artist.set_visible(False)
                except Exception: pass
            ax._top_xlabel_on = False
        if titles.get('right_y'):
            lbl = ax.get_ylabel() or ''
            if lbl:
                if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                    try: ax._right_ylabel_artist.remove()
                    except Exception: pass
                ax._right_ylabel_artist = ax.text(1.02, 0.5, lbl, rotation=90, va='center', ha='left', transform=ax.transAxes)
                ax._right_ylabel_on = True
                try:
                    color = getattr(ax, '_stored_right_ylabel_color', None)
                    if color and ax._right_ylabel_artist is not None:
                        ax._right_ylabel_artist.set_color(color)
                except Exception:
                    pass
        else:
            if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                try: ax._right_ylabel_artist.remove()
                except Exception: pass
                ax._right_ylabel_artist = None
            ax._right_ylabel_on = False
    except Exception:
        pass

    try:
        finalize_spine_colors(fig, ax, tick_state=getattr(ax, '_saved_tick_state', None))
    except Exception:
        pass

    # Restore mode flag (e.g., dQdV mode)
    try:
        mode = sess.get('mode')
        if mode is not None:
            ax._is_dqdv_mode = bool(mode)
    except Exception:
        pass
    try:
        smooth_cfg = sess.get('dqdv_smooth_settings')
        if isinstance(smooth_cfg, dict) and smooth_cfg:
            fig._dqdv_smooth_settings = dict(smooth_cfg)
    except Exception:
        pass

    # Restore dual x-axis (capacity bottom, ions top) for EC GC mode
    try:
        xd = sess.get('xaxis_dual')
        if xd and isinstance(xd, dict):
            xmode = xd.get('mode', 'capacity')
            c_th = xd.get('c_theoretical')
            swapped = bool(xd.get('swapped', False))
            fig._xaxis_mode = xmode
            fig._xaxis_c_theoretical = c_th
            fig._xaxis_swapped = swapped
            if xmode == 'dual' and c_th is not None:
                c_th = float(c_th)
                if swapped:
                    def _bottom_to_top_ions(ions):
                        return ions * c_th
                    def _top_to_bottom_capacity(capacity):
                        return capacity / c_th
                    bottom_to_top = _bottom_to_top_ions
                    top_to_bottom = _top_to_bottom_capacity
                else:
                    def _bottom_to_top_capacity(capacity):
                        return capacity / c_th
                    def _top_to_bottom_ions(ions):
                        return ions * c_th
                    bottom_to_top = _bottom_to_top_capacity
                    top_to_bottom = _top_to_bottom_ions
                try:
                    secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                    fig._xaxis_secondary = secax
                    capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                    ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                    if swapped:
                        ax.set_xlabel(ions_label)
                        secax.set_xlabel(capacity_label)
                    else:
                        ax.set_xlabel(capacity_label)
                        secax.set_xlabel(ions_label)
                    top_axis_cfg = xd.get('top_axis') if isinstance(xd, dict) else None
                    if isinstance(top_axis_cfg, dict):
                        try:
                            from .style import apply_dual_top_axis_style

                            apply_dual_top_axis_style(secax, top_axis_cfg)
                        except Exception:
                            pass
                    try:
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        font_size = plt.rcParams.get('font.size', None)
                        if font_fam_str:
                            secax.xaxis.label.set_family(font_fam_str)
                        if font_size is not None:
                            secax.xaxis.label.set_size(font_size)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Warning: Could not restore dual x-axis: {e}")
            elif xmode == 'ions' and c_th is not None:
                c_th = float(c_th)
                for ln in ax.lines:
                    try:
                        if not hasattr(ln, '_orig_xdata_gc'):
                            x0 = np.asarray(ln.get_xdata(), dtype=float)
                            setattr(ln, '_orig_xdata_gc', x0.copy())
                        x_orig = getattr(ln, '_orig_xdata_gc')
                        ln.set_xdata(x_orig / c_th)
                    except Exception:
                        continue
                ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                ax.set_xlabel(ions_label)
    except Exception as e:
        print(f"Warning: Could not restore xaxis_dual: {e}")

    try:
        # After dual-top create (which may run tick_params), re-apply primary spine/tick colors.
        finalize_spine_colors(fig, ax, tick_state=getattr(ax, '_saved_tick_state', None))
    except Exception:
        pass

    # Legend visibility/position
    try:
        legend_cfg = sess.get('legend', {}) or {}
        legend_visible = bool(legend_cfg.get('visible', True))
        legend_xy = _sanitize_legend_offset(legend_cfg.get('position_inches'))
        legend_title = legend_cfg.get('title')
        if legend_title:
            fig._ec_legend_title = legend_title
        else:
            fig._ec_legend_title = legend_title or getattr(fig, '_ec_legend_title', None)
        if not getattr(fig, '_ec_legend_title', None):
            fig._ec_legend_title = "Cycle"
        try:
            fig._ec_legend_user_visible = legend_visible
        except Exception:
            pass
        if legend_xy is not None:
            fig._ec_legend_xy_in = legend_xy
        legend_file_order = sess.get('legend_file_order')
        if legend_file_order and file_data_out and len(legend_file_order) == len(file_data_out):
            fig._ec_legend_file_order = list(legend_file_order)
        handles = []
        labels = []
        for ln in ax.lines:
            if ln.get_visible():
                lbl = ln.get_label() or ''
                if lbl.startswith('_'):
                    continue
                handles.append(ln)
                labels.append(lbl)
        if handles:
            if legend_xy is not None:
                fw, fh = fig.get_size_inches()
                if fw > 0 and fh > 0:
                    fx = 0.5 + legend_xy[0] / fw
                    fy = 0.5 + legend_xy[1] / fh
                    leg = ax.legend(handles, labels, loc='center',
                                    bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure,
                                    borderaxespad=1.0)
                else:
                    leg = ax.legend(handles, labels, loc='best', borderaxespad=1.0)
            else:
                leg = ax.legend(handles, labels, loc='best', borderaxespad=1.0)
            if leg is not None:
                try:
                    leg.set_frame_on(False)
                except Exception:
                    pass
                leg.set_visible(legend_visible)
                try:
                    title_text = getattr(fig, '_ec_legend_title', None) or "Cycle"
                    leg.set_title(title_text)
                except Exception:
                    pass
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
        apply_session_font_cfg(fig, sess.get('font', {}) or {}, ax)
    except Exception:
        pass
    if not embed:
        try:
            blob = sess.get('dqdv_2d')
            if isinstance(blob, dict) and blob.get('Z') is not None:
                from .dqdv_2d import restore_dqdv_2d_companion_figure
                cbundle = restore_dqdv_2d_companion_figure(blob)
                if cbundle:
                    setattr(fig, '_dqdv_2d_companion_bundle', cbundle)
        except Exception as _e2d:
            print(f"Warning: could not restore dQ/dV 2D companion: {_e2d}")
    if file_data_out is not None:
        return (fig, ax, None, file_data_out)
    return (fig, ax, cycle_lines)

__all__ = ["dump_ec_session", "load_ec_session"]
