"""XY / 1D session dump/load (mode-owned implementation).

Moved from :mod:`batplot.session`. Shared helpers come from
``plot_modes.common.session_helpers``.
"""

from __future__ import annotations

import os
import pickle
import sys
import traceback
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast

import numpy as np  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    MultipleLocator, AutoLocator, AutoMinorLocator,
    NullFormatter, NullLocator,
)

from ...utils import (
    _confirm_overwrite,
    ensure_exact_case_filename,
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
)
from ...ui import (
    set_spine_side_color as _set_spine_side_color,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
)
from ...plotting import apply_curve_color, update_labels
from ..common.sources import resolve_xy_source_files
from ..common.font_extras import apply_session_font_cfg, merge_session_font_dump
from ..common.axis_state import (
    capture_axis_wasd_state,
)
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


def _capture_xy_axis_style_for_session(ax) -> Dict[str, Any]:
    from .style import capture_xy_axis_style
    return capture_xy_axis_style(ax)


def _restore_xy_axis_style_from_session(ax, axis_cfg: Dict[str, Any], *, fig=None, spines_cfg=None) -> None:
    from .style import apply_xy_axis_style
    style = {
        "tick_colors": axis_cfg.get("tick_colors"),
        "axis_label_colors": axis_cfg.get("axis_label_colors"),
        "labelpads": axis_cfg.get("labelpads") or {
            "x": axis_cfg.get("x_labelpad"),
            "y": axis_cfg.get("y_labelpad"),
        },
    }
    apply_xy_axis_style(ax, style, fig=fig, spines_cfg=spines_cfg or {})


def _serialize_xy_curve_palettes(fig) -> List[Dict[str, Any]]:
    """Serialize XY curve palette history for session files."""
    from .style import serialize_curve_palette_history
    return serialize_curve_palette_history(fig)


def _restore_xy_curve_palette_history(fig, palette_cfg) -> None:
    """Restore ``fig._curve_palette_history`` from a session/style record list."""
    if palette_cfg:
        history = []
        for rec in palette_cfg:
            palette_name = rec.get('palette')
            indices = rec.get('indices')
            if not palette_name or not indices:
                continue
            history.append({
                'palette': palette_name,
                'indices': list(indices),
                'low_clip': float(rec.get('low_clip', 0.08)),
                'high_clip': float(rec.get('high_clip', 0.85)),
            })
        if history:
            fig._curve_palette_history = history
            return
    if hasattr(fig, '_curve_palette_history'):
        delattr(fig, '_curve_palette_history')


def _grid_enabled(ax) -> bool:
    """Return True if any gridline is currently visible."""
    try:
        return any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines())
    except Exception:
        return bool(ax.xaxis._gridOnMajor) if hasattr(ax.xaxis, '_gridOnMajor') else False


def _get_primary_axis_label(ax, axis: str) -> str:
    """Get primary axis label text, falling back to stored value when hidden."""
    if axis == 'x':
        label = ax.xaxis.label
        stored_attr = '_stored_xlabel'
    else:
        label = ax.yaxis.label
        stored_attr = '_stored_ylabel'
    text = ''
    try:
        text = label.get_text() or ''
    except Exception:
        text = ''
    if not text and hasattr(ax, stored_attr):
        try:
            stored = getattr(ax, stored_attr)
            if stored:
                text = stored
        except Exception:
            text = ''
    return text or ''


def _get_duplicate_axis_label(ax, which: str, fallback: str = '') -> str:
    """Get duplicate axis label (top/right) text."""
    if which == 'top':
        artist_attr = '_top_xlabel_artist'
        override_attr = '_top_xlabel_text_override'
    else:
        artist_attr = '_right_ylabel_artist'
        override_attr = '_right_ylabel_text_override'
    if hasattr(ax, override_attr):
        try:
            override_val = getattr(ax, override_attr)
            if override_val:
                return override_val
        except Exception:
            pass
    artist = getattr(ax, artist_attr, None)
    if artist is not None and hasattr(artist, 'get_text'):
        try:
            txt = artist.get_text()
            if txt:
                return txt
        except Exception:
            pass
    return fallback or ''


# ------------------------- Generic XY session (existing) -------------------------


def dump_session(
    filename: str,
    *,
    fig,
    ax,
    x_data_list: Sequence[np.ndarray],
    y_data_list: Sequence[np.ndarray],
    orig_y: Sequence[np.ndarray],
    x_full_list: Sequence[np.ndarray] | None = None,
    raw_y_full_list: Sequence[np.ndarray] | None = None,
    offsets_list: Sequence[float],
    labels: Sequence[str],
    delta: float,
    args,
    tick_state: Dict[str, bool],
    cif_tick_series: Iterable[Tuple[str, str, List[float], float | None, float, Any]] | None = None,
    cif_hkl_map: Dict[str, List[Tuple[float, int, int, int]]] | None = None,
    cif_hkl_label_map: Dict[str, Dict[float, str]] | None = None,
    show_cif_hkl: bool | None = None,
    show_cif_titles: bool | None = None,
    skip_confirm: bool = False,
) -> None:
    """
    Save current interactive session to a pickle file.
    
    HOW SESSION SAVING WORKS:
    ------------------------
    This function captures the complete state of your interactive plot and
    saves it to a .pkl file. When you load this file later, the plot will be
    recreated exactly as it was, including:
    
    - Data: All x/y data arrays, labels, file paths
    - Styling: Colors, line widths, fonts, tick settings, spine properties
    - Geometry: Figure size, axes position, axis ranges
    - State: Which curves are visible, label positions, CIF overlays, etc.
    
    SERIALIZATION PROCESS:
    ---------------------
    1. Collect all plot state into a dictionary
    2. Infer axis mode from current labels (Q, 2theta, r, etc.)
    3. Capture figure/axes geometry (size, position)
    4. Save spine properties (linewidth, color, visibility)
    5. Save tick properties (widths, lengths, directions)
    6. Save axis labels (including duplicate top/right labels)
    7. Save curve properties (colors, linewidths, visibility)
    8. Serialize everything using pickle and write to file
    
    WHY PICKLE?
    -----------
    Pickle is Python's built-in serialization format. It can save complex
    Python objects (numpy arrays, matplotlib objects, etc.) to disk and
    restore them exactly. This is perfect for saving complete plot state.
    
    Args:
        filename: Path to .pkl file where session will be saved
        fig: Matplotlib figure object
        ax: Matplotlib axes object
        x_data_list: List of x-data arrays (one per curve)
        y_data_list: List of y-data arrays (one per curve, with offsets applied)
        orig_y: List of original y-data arrays (before offsets)
        offsets_list: List of vertical offsets applied to each curve
        labels: List of curve labels (file names or custom labels)
        delta: Spacing between stacked curves (if stack mode)
        args: Command-line arguments namespace (for axis mode, etc.)
        tick_state: Dictionary of tick visibility states (top, bottom, left, right)
        cif_tick_series: Optional CIF overlay data (for diffraction patterns)
        cif_hkl_map: Optional CIF hkl indices mapping
        cif_hkl_label_map: Optional CIF hkl label mapping
        show_cif_hkl: Whether to show CIF hkl labels
        show_cif_titles: Whether to show CIF titles
        skip_confirm: If True, skip overwrite confirmation dialog
    """

    # Infer axis mode string
    if getattr(args, 'xaxis', None) in ("Q", "2theta", "r", "energy", "k", "rft"):
        axis_mode_session = args.xaxis
    else:
        # Best-effort inference from labels/units already set on axes
        xl = (ax.get_xlabel() or "").lower()
        if "q (" in xl:
            axis_mode_session = "Q"
        elif "$2\\theta$" in xl or "2" in xl and "theta" in xl:
            axis_mode_session = "2theta"
        elif xl.startswith("r ") or xl.startswith("r ("):
            axis_mode_session = "r"
        elif "energy" in xl:
            axis_mode_session = "energy"
        elif xl.startswith("k ") or xl.startswith("k ("):
            axis_mode_session = "k"
        elif "radial" in xl:
            axis_mode_session = "rft"
        else:
            axis_mode_session = "unknown"

    label_layout = 'stack' if getattr(args, 'stack', False) else 'block'

    # Axes frame size (in inches) to complement the canvas size
    bbox = ax.get_position()
    fw, fh = fig.get_size_inches()
    frame_w_in = bbox.width * fw
    frame_h_in = bbox.height * fh

    # Save spines state
    spines_state = {
        name: {
            'linewidth': sp.get_linewidth(),
            'color': sp.get_edgecolor(),
            'visible': sp.get_visible(),
        } for name, sp in ax.spines.items()
    }

    # Helper to capture a representative tick line width
    def _tick_width(axis, which: str):
        return _current_tick_width(axis, which)

    tick_widths = {
        'x_major': _tick_width(ax.xaxis, 'major'),
        'x_minor': _tick_width(ax.xaxis, 'minor'),
        'y_major': _tick_width(ax.yaxis, 'major'),
        'y_minor': _tick_width(ax.yaxis, 'minor'),
    }
    
    # Helper to get tick length
    def _tick_length(axis, which):
        try:
            ticks = axis.get_major_ticks() if which=='major' else axis.get_minor_ticks()
            for t in ticks:
                ln = t.tick1line
                if ln.get_visible():
                    return ln.get_markersize()
        except Exception:
            return None
        return None
    
    tick_lengths = {
        'x_major': _tick_length(ax.xaxis, 'major'),
        'x_minor': _tick_length(ax.xaxis, 'minor'),
        'y_major': _tick_length(ax.yaxis, 'major'),
        'y_minor': _tick_length(ax.yaxis, 'minor'),
    }

    sp = fig.subplotpars
    subplot_margins = {
        'left': float(sp.left),
        'right': float(sp.right),
        'bottom': float(sp.bottom),
        'top': float(sp.top),
    }
    
    wasd_state = capture_axis_wasd_state(ax)

    try:
        sess = {
            'kind': 'xy',
            'version': 3,
            'x_data': [np.array(a) for a in x_data_list],
            'y_data': [np.array(a) for a in y_data_list],
            'orig_y': [np.array(a) for a in orig_y],
            # Persist full untrimmed XY data so x-range edits remain reversible
            # after saving/reloading a .pkl, including Bruker .raw/.brml sessions.
            'x_full_data': ([np.array(a) for a in x_full_list]
                            if x_full_list is not None else [np.array(a) for a in x_data_list]),
            'raw_y_full_data': ([np.array(a) for a in raw_y_full_list]
                                if raw_y_full_list is not None else [np.array(a) for a in orig_y]),
            'offsets': list(offsets_list),
            'labels': list(labels),
            # Processed data (for smooth/reduce operations)
            'original_x_data_list': ([np.array(a) for a in getattr(fig, '_original_x_data_list', [])] 
                                     if hasattr(fig, '_original_x_data_list') else None),
            'original_y_data_list': ([np.array(a) for a in getattr(fig, '_original_y_data_list', [])] 
                                     if hasattr(fig, '_original_y_data_list') else None),
            'full_processed_x_data_list': ([np.array(a) for a in getattr(fig, '_full_processed_x_data_list', [])] 
                                            if hasattr(fig, '_full_processed_x_data_list') else None),
            'full_processed_y_data_list': ([np.array(a) for a in getattr(fig, '_full_processed_y_data_list', [])] 
                                            if hasattr(fig, '_full_processed_y_data_list') else None),
            'smooth_settings': (dict(getattr(fig, '_smooth_settings', {})) 
                               if hasattr(fig, '_smooth_settings') else None),
            'last_smooth_settings': (dict(getattr(fig, '_last_smooth_settings', {})) 
                                    if hasattr(fig, '_last_smooth_settings') else None),
            # Derivative data (for derivative operations)
            'pre_derivative_x_data_list': ([np.array(a) for a in getattr(fig, '_pre_derivative_x_data_list', [])] 
                                           if hasattr(fig, '_pre_derivative_x_data_list') else None),
            'pre_derivative_y_data_list': ([np.array(a) for a in getattr(fig, '_pre_derivative_y_data_list', [])] 
                                           if hasattr(fig, '_pre_derivative_y_data_list') else None),
            'pre_derivative_ylabel': (str(getattr(fig, '_pre_derivative_ylabel', '')) 
                                      if hasattr(fig, '_pre_derivative_ylabel') else None),
            'derivative_order': (int(getattr(fig, '_derivative_order', 0)) 
                                if hasattr(fig, '_derivative_order') else None),
            'derivative_reversed': (bool(getattr(fig, '_derivative_reversed', False)) 
                                   if hasattr(fig, '_derivative_reversed') else None),
            'line_styles': [
                {
                    'color': ln.get_color(),
                    'linewidth': ln.get_linewidth(),
                    'linestyle': ln.get_linestyle(),
                    'alpha': ln.get_alpha(),
                    'marker': ln.get_marker(),
                    'markersize': ln.get_markersize(),
                    'markerfacecolor': ln.get_markerfacecolor(),
                    'markeredgecolor': ln.get_markeredgecolor(),
                } for ln in (getattr(fig, '_xy_lines_by_curve', None) or ax.lines)
                if ln is not None
            ],
            'curve_palettes': _serialize_xy_curve_palettes(fig),
            'right_y_curve_indices': list(getattr(fig, '_xy_right_y_curve_indices', frozenset())),
            'txaxis': bool(getattr(fig, '_xy_use_top_x', False)),
            'delta': float(delta),
            'label_layout': label_layout,
            'axis_mode': axis_mode_session,
            'axis': {
                'xlabel': ax.get_xlabel(),
                'ylabel': ax.get_ylabel(),
                'xlim': ax.get_xlim(),
                'ylim': ax.get_ylim(),
                'norm_xlim': getattr(ax, '_norm_xlim', None),  # x-range used for normalization
                'norm_ylim': getattr(ax, '_norm_ylim', None),  # y-range used for normalization
                **{k: v for k, v in _capture_xy_axis_style_for_session(ax).items()},
            },
            'figure': {
                'size': tuple(map(float, fig.get_size_inches())),
                'dpi': int(fig.dpi),
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
            'wasd_state': wasd_state,
            'tick_state': dict(tick_state),
            'tick_widths': tick_widths,
            'tick_lengths': tick_lengths,
            'tick_direction': getattr(fig, '_tick_direction', 'out'),
            'tick_locator_state': _capture_session_tick_locator(ax),
            'font': merge_session_font_dump(fig),
            'args_subset': {
                'stack': bool(getattr(args, 'stack', False)),
                'autoscale': bool(getattr(args, 'autoscale', False)),
                'norm': bool(getattr(args, 'norm', False)),
                'files': [str(f) for f in (getattr(args, 'files', None) or [])],
            },
            'source_files': [str(f) for f in (getattr(args, 'files', None) or [])],
            'cif_tick_series': [tuple(t) for t in (cif_tick_series or [])],
            'cif_hkl_map': {k: [tuple(v) for v in val] for k, val in (cif_hkl_map or {}).items()},
            'cif_hkl_label_map': {k: dict(v) for k, v in (cif_hkl_label_map or {}).items()},
            'show_cif_hkl': bool(show_cif_hkl),
            'show_cif_titles': bool(show_cif_titles) if show_cif_titles is not None else True,
            'cif_stack_y_offsets': list(getattr(fig, '_bp_cif_stack_y_offsets', []) or []),
            # CIF row layout reference range. Without it, each save/load cycle
            # re-seeds _cif_initial_ylim from the already-extended limits and
            # the y-range creeps downward on every reload.
            'cif_initial_ylim': (tuple(map(float, getattr(ax, '_cif_initial_ylim')))
                                 if hasattr(ax, '_cif_initial_ylim') else None),
        }
        # 1D XY: per-set CIF visibility (__main__.cif_set_visible), same as undo snapshots
        try:
            if cif_tick_series:
                _m = sys.modules.get("__main__")
                if _m is not None and hasattr(_m, "cif_set_visible"):
                    _vis = list(getattr(_m, "cif_set_visible") or [])
                    if len(_vis) == len(list(cif_tick_series or [])):
                        sess["cif_set_visible"] = [bool(v) for v in _vis]
        except Exception:
            pass
        sess['axis_titles'] = {
            'top_x': bool(getattr(ax, '_top_xlabel_on', False)),
            'right_y': bool(getattr(ax, '_right_ylabel_on', False)),
            'has_bottom_x': bool(ax.xaxis.label.get_visible()),
            'has_left_y': bool(ax.yaxis.label.get_visible()),
        }
        sess['title_offsets'] = {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        }
        right_y_text = _get_duplicate_axis_label(ax, 'right', _get_primary_axis_label(ax, 'y'))
        ax2_xy = getattr(fig, '_xy_ax2', None)
        if ax2_xy is not None:
            right_y_text = ax2_xy.get_ylabel() or right_y_text
        sess['axis_title_texts'] = {
            'bottom_x': _get_primary_axis_label(ax, 'x'),
            'left_y': _get_primary_axis_label(ax, 'y'),
            'top_x': _get_duplicate_axis_label(ax, 'top', _get_primary_axis_label(ax, 'x')),
            'right_y': right_y_text,
        }
        # Save curve names visibility
        sess['curve_names_visible'] = bool(getattr(fig, '_curve_names_visible', True))
        # Save whether data were plotted with swapped axes via --ro
        sess['ro_active'] = bool(getattr(fig, '_ro_active', False))
        # Save stack/legend anchor preferences
        sess['stack_label_at_bottom'] = bool(getattr(fig, '_stack_label_at_bottom', False))
        sess['label_anchor_left'] = bool(getattr(fig, '_label_anchor_left', False))
        # Save grid state
        sess['grid'] = _grid_enabled(ax)
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
        print(f"Session saved to {target}")
    except Exception as e:  # pragma: no cover - defensive path
        print(f"Error saving session: {e}")

def load_xy_session(filename: str) -> tuple[Any, Any, dict[str, Any]] | None:  # pyright: ignore[reportGeneralTypeIssues]
    """Load an XY/1D session (sessions with 'version' and 'x_data' but no 'kind').

    Replicates the reconstruction logic from batplot.py for XY sessions.
    Returns (fig, ax, menu_kwargs) where menu_kwargs is a dict suitable for
    interactive_menu. Returns None on failure.
    """
    try:
        with open(filename, 'rb') as f:
            sess = pickle.load(f)
    except ModuleNotFoundError as e:
        if '_core' in str(e) or 'numpy' in str(e).lower():
            saved_versions = _try_extract_version_from_pickle(filename)
            current_numpy = _get_current_numpy_version()
            saved_numpy = saved_versions.get('numpy', 'unknown')
            print(f"\nERROR: NumPy version mismatch detected when loading: {filename}")
            print("This session was saved with a different NumPy version.")
            print(f"\nSession was saved with:  NumPy {saved_numpy}")
            print(f"Currently installed:     NumPy {current_numpy}")
            print("\nSolutions: pip install matching numpy version or recreate session.")
        else:
            print(f"\nERROR: Module import error when loading: {filename}\nError: {e}")
        return None
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None

    if not isinstance(sess, dict) or 'version' not in sess or 'x_data' not in sess:
        return None
    if sess.get('kind') not in (None, 'xy'):
        return None

    try:
        # Match saved canvas geometry (same as EC/CPC/operando loaders) so e.g. canvas mode gets correct panel sizes
        fig_cfg = sess.get('figure') or {}
        sz = fig_cfg.get('size')
        if sz and isinstance(sz, (list, tuple)) and len(sz) >= 2:
            try:
                fw, fh = float(sz[0]), float(sz[1])
                if fw <= 0 or fh <= 0:
                    fw, fh = 8.0, 6.0
            except (TypeError, ValueError):
                fw, fh = 8.0, 6.0
        else:
            fw, fh = 8.0, 6.0
        fig, ax = plt.subplots(figsize=(fw, fh), dpi=100)
        try:
            fig._ro_active = bool(sess.get('ro_active', False))
        except Exception:
            pass
        try:
            fig._last_session_save_path = os.path.abspath(filename)
        except Exception:
            pass
        try:
            fig.set_layout_engine('none')
        except AttributeError:
            try:
                fig.set_tight_layout(False)
            except Exception:
                pass

        y_data_list: List[np.ndarray] = []
        x_data_list: List[np.ndarray] = []
        labels_list: List[str] = []
        orig_y: List[np.ndarray] = []
        label_text_objects: List[Any] = []
        x_full_list: List[np.ndarray] = []
        raw_y_full_list: List[np.ndarray] = []
        offsets_list: List[float] = []

        wasd_loaded = sess.get('wasd_state')
        if wasd_loaded and isinstance(wasd_loaded, dict):
            tick_state: Dict[str, Any] = {}
            for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                s = wasd_loaded.get(side_key, {})
                tick_state[f'{prefix}_ticks'] = bool(s.get('ticks', side_key in ('bottom', 'left')))
                tick_state[f'{prefix}_labels'] = bool(s.get('labels', side_key in ('bottom', 'left')))
                tick_state[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
            tick_state['bx'] = tick_state.get('b_ticks', True)
            tick_state['tx'] = tick_state.get('t_ticks', False)
            tick_state['ly'] = tick_state.get('l_ticks', True)
            tick_state['ry'] = tick_state.get('r_ticks', False)
            tick_state['mbx'] = tick_state.get('mbx', False)
            tick_state['mtx'] = tick_state.get('mtx', False)
            tick_state['mly'] = tick_state.get('mly', False)
            tick_state['mry'] = tick_state.get('mry', False)
        else:
            tick_state = sess.get('tick_state', {
                'bx': True, 'tx': False, 'ly': True, 'ry': False,
                'mbx': False, 'mtx': False, 'mly': False, 'mry': False
            })

        saved_stack = bool(sess.get('args_subset', {}).get('stack', False))
        x_loaded = sess.get('x_data', [])
        y_loaded = sess.get('y_data', [])
        orig_loaded = sess.get('orig_y', [])
        offsets_saved = sess.get('offsets', [])

        original_x_data_list = sess.get('original_x_data_list')
        original_y_data_list = sess.get('original_y_data_list')
        saved_x_full_data = sess.get('x_full_data')
        saved_raw_y_full_data = sess.get('raw_y_full_data')
        smooth_settings = sess.get('smooth_settings')
        if original_x_data_list is not None:
            fig._original_x_data_list = [np.array(a) for a in original_x_data_list]
        elif saved_x_full_data is not None:
            fig._original_x_data_list = [np.array(a) for a in saved_x_full_data]
        if original_y_data_list is not None:
            fig._original_y_data_list = [np.array(a) for a in original_y_data_list]
        elif saved_raw_y_full_data is not None:
            fig._original_y_data_list = [np.array(a) for a in saved_raw_y_full_data]
        full_processed_x_data_list = sess.get('full_processed_x_data_list')
        full_processed_y_data_list = sess.get('full_processed_y_data_list')
        if full_processed_x_data_list is not None:
            fig._full_processed_x_data_list = [np.array(a) for a in full_processed_x_data_list]
        if full_processed_y_data_list is not None:
            fig._full_processed_y_data_list = [np.array(a) for a in full_processed_y_data_list]
        if smooth_settings is not None:
            fig._smooth_settings = dict(smooth_settings)
        last_smooth_settings = sess.get('last_smooth_settings')
        if last_smooth_settings is not None:
            fig._last_smooth_settings = dict(last_smooth_settings)

        pre_derivative_x_data_list = sess.get('pre_derivative_x_data_list')
        pre_derivative_y_data_list = sess.get('pre_derivative_y_data_list')
        pre_derivative_ylabel = sess.get('pre_derivative_ylabel')
        derivative_order = sess.get('derivative_order')
        if pre_derivative_x_data_list is not None:
            fig._pre_derivative_x_data_list = [np.array(a) for a in pre_derivative_x_data_list]
        if pre_derivative_y_data_list is not None:
            fig._pre_derivative_y_data_list = [np.array(a) for a in pre_derivative_y_data_list]
        if pre_derivative_ylabel is not None:
            fig._pre_derivative_ylabel = str(pre_derivative_ylabel)
        if derivative_order is not None:
            fig._derivative_order = int(derivative_order)
        derivative_reversed = sess.get('derivative_reversed')
        if derivative_reversed is not None:
            fig._derivative_reversed = bool(derivative_reversed)

        n_curves = len(x_loaded)
        right_y_loaded = frozenset(sess.get('right_y_curve_indices', []))
        ax2_loaded = None
        for i in range(n_curves):
            x_arr = np.asarray(x_loaded[i], dtype=float).flatten()
            off = offsets_saved[i] if i < len(offsets_saved) else 0.0
            if orig_loaded and i < len(orig_loaded):
                base = np.asarray(orig_loaded[i], dtype=float).flatten()
            else:
                y_arr_full = np.asarray(y_loaded[i], dtype=float).flatten() if i < len(y_loaded) else np.array([], dtype=float)
                base = y_arr_full - off
            if x_arr.size != base.size:
                min_len = min(x_arr.size, base.size)
                x_arr = x_arr[:min_len]
                base = base[:min_len]
            y_plot = base + off
            x_data_list.append(x_arr)
            orig_y.append(base)
            y_data_list.append(y_plot)
            is_right = i in right_y_loaded
            if is_right:
                if ax2_loaded is None:
                    ax2_loaded = ax.twinx()
                    if sess.get('txaxis', False):
                        ax2_loaded = ax2_loaded.twiny()
                ax2_loaded.plot(x_arr, y_plot, lw=1)
            else:
                ax.plot(x_arr, y_plot, lw=1)
            if saved_x_full_data is not None and i < len(saved_x_full_data):
                x_full_arr = np.asarray(saved_x_full_data[i], dtype=float).flatten()
            else:
                x_full_arr = x_arr.copy()
            if saved_raw_y_full_data is not None and i < len(saved_raw_y_full_data):
                y_full_arr = np.asarray(saved_raw_y_full_data[i], dtype=float).flatten()
            else:
                y_full_arr = base.copy()
            if x_full_arr.size != y_full_arr.size:
                min_len_full = min(x_full_arr.size, y_full_arr.size)
                x_full_arr = x_full_arr[:min_len_full]
                y_full_arr = y_full_arr[:min_len_full]
            x_full_list.append(x_full_arr)
            raw_y_full_list.append(y_full_arr)
        offsets_list[:] = offsets_saved if offsets_saved else [0.0] * n_curves

        try:
            axes_bbox = sess.get('figure', {}).get('axes_bbox')
            if _apply_axes_bbox(ax, axes_bbox):
                try:
                    fig._skip_initial_text_visibility = True
                except Exception:
                    pass
        except Exception:
            pass

        if ax2_loaded is not None:
            fig._xy_ax2 = ax2_loaded
            fig._xy_use_top_x = bool(sess.get('txaxis', False))
            fig._xy_right_y_curve_indices = right_y_loaded
            _left_idx = sorted(i for i in range(n_curves) if i not in right_y_loaded)
            _right_idx = sorted(right_y_loaded)
            _lines_by_curve = []
            for i in range(n_curves):
                if i in right_y_loaded:
                    k = _right_idx.index(i)
                    _lines_by_curve.append(ax2_loaded.lines[k] if k < len(ax2_loaded.lines) else None)
                else:
                    k = _left_idx.index(i)
                    _lines_by_curve.append(ax.lines[k] if k < len(ax.lines) else None)
            fig._xy_lines_by_curve = _lines_by_curve
        else:
            fig._xy_ax2 = None
            fig._xy_right_y_curve_indices = frozenset()
            fig._xy_lines_by_curve = None

        try:
            stored_styles = sess.get('line_styles', [])
            lines_to_style = (fig._xy_lines_by_curve if fig._xy_lines_by_curve else ax.lines)
            for ln, st in zip(lines_to_style, stored_styles):
                if ln is None:
                    continue
                if 'linewidth' in st:
                    ln.set_linewidth(st['linewidth'])
                if 'linestyle' in st:
                    try:
                        ln.set_linestyle(st['linestyle'])
                    except Exception:
                        pass
                if 'alpha' in st and st['alpha'] is not None:
                    ln.set_alpha(st['alpha'])
                if 'marker' in st and st['marker'] is not None:
                    try:
                        ln.set_marker(st['marker'])
                    except Exception:
                        pass
                if 'markersize' in st and st['markersize'] is not None:
                    try:
                        ln.set_markersize(st['markersize'])
                    except Exception:
                        pass
                if 'color' in st:
                    apply_curve_color(ln, st['color'])
                else:
                    if 'markerfacecolor' in st and st['markerfacecolor'] is not None:
                        try:
                            ln.set_markerfacecolor(st['markerfacecolor'])
                        except Exception:
                            pass
                    if 'markeredgecolor' in st and st['markeredgecolor'] is not None:
                        try:
                            ln.set_markeredgecolor(st['markeredgecolor'])
                        except Exception:
                            pass
        except Exception:
            pass

        try:
            _restore_xy_curve_palette_history(fig, sess.get('curve_palettes', []))
        except Exception:
            pass

        labels_list[:] = sess.get('labels', [f"Curve {i+1}" for i in range(len(y_data_list))])
        delta = sess.get('delta', 0.0)
        try:
            ax.tick_params(axis='x',
                          bottom=tick_state.get('b_ticks', tick_state.get('bx', True)),
                          labelbottom=tick_state.get('b_labels', tick_state.get('bx', True)),
                          top=tick_state.get('t_ticks', tick_state.get('tx', False)),
                          labeltop=tick_state.get('t_labels', tick_state.get('tx', False)))
            ax.tick_params(axis='y',
                          left=tick_state.get('l_ticks', tick_state.get('ly', True)),
                          labelleft=tick_state.get('l_labels', tick_state.get('ly', True)),
                          right=tick_state.get('r_ticks', tick_state.get('ry', False)),
                          labelright=tick_state.get('r_labels', tick_state.get('ry', False)))
        except Exception:
            pass
        ax.set_xlabel(sess.get('axis', {}).get('xlabel', 'X'))
        ax.set_ylabel(sess.get('axis', {}).get('ylabel', 'Intensity'))
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass

        axis_cfg = sess.get('axis', {})
        if 'norm_xlim' in axis_cfg and axis_cfg['norm_xlim'] is not None:
            ax._norm_xlim = tuple(axis_cfg['norm_xlim'])
        if 'norm_ylim' in axis_cfg and axis_cfg['norm_ylim'] is not None:
            ax._norm_ylim = tuple(axis_cfg['norm_ylim'])
        if 'xlim' in axis_cfg:
            ax.set_xlim(*axis_cfg['xlim'])
        if 'ylim' in axis_cfg:
            ax.set_ylim(*axis_cfg['ylim'])
        # Restore the CIF layout reference range saved by dump_session so CIF
        # tick rows land exactly where they were before saving (no y drift).
        try:
            _cif_init = sess.get('cif_initial_ylim')
            if _cif_init is not None and len(_cif_init) == 2:
                ax._cif_initial_ylim = (float(_cif_init[0]), float(_cif_init[1]))
        except Exception:
            pass

        fig_cfg = sess.get('figure', {})
        try:
            spine_specs = fig_cfg.get('spines', {})
            if spine_specs:
                for name, spec in spine_specs.items():
                    spn = ax.spines.get(name)
                    if not spn:
                        continue
                    if 'linewidth' in spec:
                        spn.set_linewidth(spec['linewidth'])
                    if 'visible' in spec:
                        spn.set_visible(bool(spec['visible']))
            else:
                legacy_vis = fig_cfg.get('spine_vis', {})
                for name, vis in legacy_vis.items():
                    spn = ax.spines.get(name)
                    if spn:
                        spn.set_visible(bool(vis))
            spm = fig_cfg.get('subplot_margins')
            if spm and all(k in spm for k in ('left', 'right', 'bottom', 'top')):
                fig.subplots_adjust(left=spm['left'], right=spm['right'], bottom=spm['bottom'], top=spm['top'])
                try:
                    fig._skip_initial_text_visibility = True
                except Exception:
                    pass
            frame_size = fig_cfg.get('frame_size')
            if frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
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
                    try:
                        fig._skip_initial_text_visibility = True
                    except Exception:
                        pass
        except Exception:
            pass

        font_cfg = sess.get('font', {})
        if font_cfg.get('chain'):
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = font_cfg['chain']
        if font_cfg.get('size'):
            plt.rcParams['font.size'] = font_cfg['size']
        if font_cfg.get('mathtext_fontset'):
            plt.rcParams['mathtext.fontset'] = font_cfg['mathtext_fontset']

        saved_tick = sess.get('tick_state', {})
        for k, v in saved_tick.items():
            if k in tick_state:
                tick_state[k] = v
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass

        try:
            tw = sess.get('tick_widths', {})
            if tw.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=float(tw['x_major']))
            if tw.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
            if tw.get('y_major') is not None:
                ax.tick_params(axis='y', which='major', width=float(tw['y_major']))
            if tw.get('y_minor') is not None:
                ax.tick_params(axis='y', which='minor', width=float(tw['y_minor']))
        except Exception:
            pass

        try:
            tl = sess.get('tick_lengths', {})
            if tl.get('x_major') is not None or tl.get('y_major') is not None:
                major_len = tl.get('x_major') or tl.get('y_major')
                ax.tick_params(axis='both', which='major', length=major_len)
                if not hasattr(fig, '_tick_lengths'):
                    fig._tick_lengths = {}
                fig._tick_lengths['major'] = major_len
            if tl.get('x_minor') is not None or tl.get('y_minor') is not None:
                minor_len = tl.get('x_minor') or tl.get('y_minor')
                ax.tick_params(axis='both', which='minor', length=minor_len)
                if not hasattr(fig, '_tick_lengths'):
                    fig._tick_lengths = {}
                fig._tick_lengths['minor'] = minor_len
        except Exception:
            pass

        try:
            tick_direction = sess.get('tick_direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
        except Exception:
            pass

        try:
            wasd = sess.get('wasd_state', {})
            if wasd:
                stored_xlabel = ax.get_xlabel()
                stored_ylabel = ax.get_ylabel()
                for side in ('top', 'bottom', 'left', 'right'):
                    state = wasd.get(side, {})
                    sp = ax.spines.get(side)
                    if sp and 'spine' in state:
                        sp.set_visible(bool(state['spine']))
                for side in ('top', 'bottom'):
                    state = wasd.get(side, {})
                    # x-axis: tick2/label2 = top, tick1/label1 = bottom
                    tick_key = 'tick2On' if side == 'top' else 'tick1On'
                    label_key = 'label2On' if side == 'top' else 'label1On'
                    if 'ticks' in state:
                        ax.tick_params(axis='x', which='major', **{tick_key: bool(state['ticks'])})
                    if 'labels' in state:
                        ax.tick_params(axis='x', which='major', **{label_key: bool(state['labels'])})
                    if 'minor' in state:
                        ax.tick_params(axis='x', which='minor', **{tick_key: bool(state['minor'])})
                for side in ('left', 'right'):
                    state = wasd.get(side, {})
                    tick_key = 'tick1On' if side == 'left' else 'tick2On'
                    label_key = 'label1On' if side == 'left' else 'label2On'
                    if 'ticks' in state:
                        ax.tick_params(axis='y', which='major', **{tick_key: bool(state['ticks'])})
                    if 'labels' in state:
                        ax.tick_params(axis='y', which='major', **{label_key: bool(state['labels'])})
                    if 'minor' in state:
                        ax.tick_params(axis='y', which='minor', **{tick_key: bool(state['minor'])})
                bottom_title_on = wasd.get('bottom', {}).get('title', True)
                if bottom_title_on:
                    ax.set_xlabel(stored_xlabel)
                else:
                    ax.set_xlabel('')
                    if stored_xlabel:
                        setattr(ax, '_stored_xlabel', stored_xlabel)
                left_title_on = wasd.get('left', {}).get('title', True)
                if left_title_on:
                    ax.set_ylabel(stored_ylabel)
                else:
                    ax.set_ylabel('')
                    if stored_ylabel:
                        setattr(ax, '_stored_ylabel', stored_ylabel)
                setattr(ax, '_top_xlabel_on', wasd.get('top', {}).get('title', False))
                setattr(ax, '_right_ylabel_on', wasd.get('right', {}).get('title', False))
        except Exception:
            pass

        # Restore tick spacing / minor-count locators (saved as 'tick_locator_state').
        # Must run after WASD (which only toggles minor visibility) so custom MultipleLocator /
        # AutoMinorLocator settings from the t->n / t->m menus survive save+load like the other menus.
        try:
            _restore_session_tick_locator(ax, sess.get('tick_locator_state'))
        except Exception:
            pass

        for i, lab in enumerate(labels_list):
            txt = ax.text(1.0, 1.0, f"{i+1}: {lab}", ha='right', va='top', transform=ax.transAxes,
                          fontsize=plt.rcParams.get('font.size', 16))
            label_text_objects.append(txt)
        try:
            curve_names_visible = bool(sess.get('curve_names_visible', True))
            for txt in label_text_objects:
                txt.set_visible(curve_names_visible)
            fig._curve_names_visible = curve_names_visible
        except Exception:
            pass
        try:
            stack_label_at_bottom = bool(sess.get('stack_label_at_bottom', False))
            fig._stack_label_at_bottom = stack_label_at_bottom
        except Exception:
            pass
        try:
            fig._label_anchor_left = bool(sess.get('label_anchor_left', False))
        except Exception:
            pass
        try:
            grid_state = bool(sess.get('grid', False))
            if grid_state:
                ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
            else:
                ax.grid(False)
        except Exception:
            pass

        cif_tick_series = sess.get('cif_tick_series') or []
        cif_hkl_map = {k: [tuple(v) for v in val] for k, val in sess.get('cif_hkl_map', {}).items()}
        cif_hkl_label_map = {k: dict(v) for k, v in sess.get('cif_hkl_label_map', {}).items()}
        show_cif_hkl = bool(sess.get('show_cif_hkl', False))
        show_cif_titles = bool(sess.get('show_cif_titles', True))

        try:
            _bp_module = sys.modules.get('__main__')
            if _bp_module is not None and cif_tick_series:
                setattr(_bp_module, 'cif_tick_series', list(cif_tick_series))
                setattr(_bp_module, 'cif_hkl_map', cif_hkl_map)
                setattr(_bp_module, 'cif_hkl_label_map', cif_hkl_label_map)
                setattr(_bp_module, 'show_cif_hkl', bool(show_cif_hkl))
                setattr(_bp_module, 'show_cif_titles', bool(show_cif_titles))
                setattr(_bp_module, 'cif_extend_suspended', False)
        except Exception:
            pass
        try:
            co = sess.get('cif_stack_y_offsets')
            if co is not None and cif_tick_series:
                olist = []
                for x in list(co):
                    try:
                        olist.append(float(x))
                    except (TypeError, ValueError):
                        olist.append(0.0)
                while len(olist) < len(cif_tick_series):
                    olist.append(0.0)
                fig._bp_cif_stack_y_offsets = olist[: len(cif_tick_series)]
        except Exception:
            pass
        try:
            vis = sess.get("cif_set_visible")
            if vis is not None and cif_tick_series:
                vlist = [bool(v) for v in list(vis)]
                while len(vlist) < len(cif_tick_series):
                    vlist.append(True)
                vlist = vlist[: len(cif_tick_series)]
                _m = sys.modules.get("__main__")
                if _m is not None:
                    setattr(_m, "cif_set_visible", vlist)
        except Exception:
            pass

        axis_mode_restored = sess.get('axis_mode', 'unknown')
        use_Q = axis_mode_restored == 'Q'
        use_r = axis_mode_restored == 'r'
        use_E = axis_mode_restored == 'energy'
        use_k = axis_mode_restored == 'k'
        use_rft = axis_mode_restored == 'rft'
        use_2th = axis_mode_restored == '2theta'
        x_label = ax.get_xlabel() or 'X'

        def _update_tick_visibility_local():
            ax.tick_params(axis='x', bottom=tick_state['bx'], top=tick_state['tx'],
                          labelbottom=tick_state['bx'], labeltop=tick_state['tx'])
            ax.tick_params(axis='y', left=tick_state['ly'], right=tick_state['ry'],
                          labelleft=tick_state['ly'], labelright=tick_state['ry'])
            if tick_state.get('mbx') or tick_state.get('mtx'):
                ax.xaxis.set_minor_locator(AutoMinorLocator())
                ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor', bottom=tick_state.get('mbx', False),
                              top=tick_state.get('mtx', False), labelbottom=False, labeltop=False)
            else:
                ax.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
            if tick_state.get('mly') or tick_state.get('mry'):
                ax.yaxis.set_minor_locator(AutoMinorLocator())
                ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor', left=tick_state.get('mly', False),
                              right=tick_state.get('mry', False), labelleft=False, labelright=False)
            else:
                ax.tick_params(axis='y', which='minor', left=False, right=False, labelleft=False, labelright=False)
        _update_tick_visibility_local()

        stack_label_bottom = bool(sess.get('stack_label_at_bottom', False))
        update_labels(ax, y_data_list, label_text_objects, saved_stack, stack_label_bottom)

        if cif_tick_series:
            def _session_q_to_2theta(peaksQ, wl):
                if wl is None:
                    return []
                out = []
                for q in peaksQ:
                    s = q * wl / (4 * np.pi)
                    if 0 <= s < 1:
                        out.append(np.degrees(2 * np.arcsin(s)))
                return out

            def _session_ensure_wavelength(default_wl=1.5406):
                for _lab, _fname, _peaks, _wl, _qmax, _color in cif_tick_series:
                    if _wl is not None:
                        return _wl
                return default_wl

            def _session_cif_draw():
                if not cif_tick_series:
                    return
                try:
                    prev_xlim = ax.get_xlim()
                    prev_ylim = ax.get_ylim()
                    if not hasattr(ax, '_cif_initial_ylim'):
                        ax._cif_initial_ylim = tuple(prev_ylim)
                    fixed_ylim = ax._cif_initial_ylim
                    fixed_yr = fixed_ylim[1] - fixed_ylim[0]
                    if fixed_yr <= 0:
                        fixed_yr = 1.0
                    show_titles_local = bool(show_cif_titles)
                    try:
                        if hasattr(fig, '_bp_show_cif_titles'):
                            show_titles_local = bool(getattr(fig, '_bp_show_cif_titles', show_titles_local))
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None and hasattr(_bp_module, 'show_cif_titles'):
                            show_titles_local = bool(getattr(_bp_module, 'show_cif_titles', show_titles_local))
                    except Exception:
                        pass
                    show_hkl_local = False
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None and hasattr(_bp_module, 'show_cif_hkl'):
                            show_hkl_local = bool(getattr(_bp_module, 'show_cif_hkl', False))
                    except Exception:
                        pass
                    if not show_hkl_local:
                        show_hkl_local = bool(show_cif_hkl)
                    _stacked_xy = bool(saved_stack or len(y_data_list) > 1)
                    if _stacked_xy:
                        global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else fixed_ylim[0]
                        base = global_min - 0.08 * fixed_yr
                    else:
                        global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
                        base = global_min - 0.06 * fixed_yr
                    spacing = xy_cif_row_spacing_yr(
                        fixed_yr,
                        show_titles=show_titles_local,
                        show_hkl=show_hkl_local,
                        stacked_or_multi_y=_stacked_xy,
                    )
                    _cif_bottom_m = xy_cif_stack_bottom_margin_yr(fixed_yr, show_titles=show_titles_local)
                    needed_min = base - (len(cif_tick_series) - 1) * spacing - _cif_bottom_m
                    if not show_titles_local:
                        ylim_draw = tuple(prev_ylim)
                    elif needed_min >= prev_ylim[0]:
                        ylim_draw = tuple(prev_ylim)
                    else:
                        new_ymin = min(needed_min, prev_ylim[0])
                        ylim_draw = (new_ymin, prev_ylim[1])
                    ax.set_ylim(ylim_draw)
                    cur_ylim = ax.get_ylim()
                    yr = cur_ylim[1] - cur_ylim[0]
                    if yr <= 0:
                        yr = 1.0
                    for art in getattr(ax, '_cif_tick_art', []):
                        try:
                            art.remove()
                        except Exception:
                            pass
                    new_art = []
                    wl_any = _session_ensure_wavelength()
                    for i, (lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(cif_tick_series):
                        y_line = base - i * spacing + xy_cif_stack_y_offset(fig, i)
                        tick_h, hkl_y = xy_cif_tick_stack_layout(y_line, yr)
                        if use_2th:
                            wl_use = wl if wl is not None else wl_any
                            domain_peaks = _session_q_to_2theta(peaksQ, wl_use)
                        else:
                            domain_peaks = peaksQ
                        xlow, xhigh = ax.get_xlim()
                        domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
                        label_map = {}
                        if show_hkl_local:
                            label_map = cif_hkl_label_map.get(fname, {})
                        if show_hkl_local and len(domain_peaks) > 4000:
                            show_hkl_local = False
                            label_map = {}
                        for p in domain_peaks:
                            ln, = ax.plot([p, p], [y_line, y_line + tick_h], color=color, lw=1.0, alpha=0.9, zorder=3)
                            new_art.append(ln)
                            if show_hkl_local:
                                if use_2th and (wl or wl_any):
                                    theta = np.radians(p / 2.0)
                                    Qp = 4 * np.pi * np.sin(theta) / (wl if wl is not None else wl_any)
                                else:
                                    Qp = p
                                Qp_rounded = round(Qp, 6)
                                lbl = label_map.get(Qp_rounded)
                                if lbl:
                                    t_hkl = ax.text(p, hkl_y, lbl, ha='center', va='bottom',
                                                    fontsize=7, rotation=90, color=color)
                                    new_art.append(t_hkl)
                        if show_titles_local:
                            label_text = f" {lab}"
                            xy_cif_add_phase_title(
                                ax, prev_xlim[0], y_line, tick_h, label_text,
                                max(8, int(0.55 * plt.rcParams.get('font.size', 16))), color, new_art,
                            )
                    ax._cif_tick_art = new_art
                    ax.set_xlim(prev_xlim)
                    fig.canvas.draw_idle()
                except Exception:
                    pass

            ax._cif_extend_func = lambda xmax: None
            ax._cif_draw_func = _session_cif_draw
            ax._cif_draw_func()

        titles = sess.get('axis_titles', {})
        title_texts = sess.get('axis_title_texts', {})
        title_offsets = sess.get('title_offsets', {})
        bottom_text = title_texts.get('bottom_x') or title_texts.get('bottom')
        left_text = title_texts.get('left_y') or title_texts.get('left')
        top_text = title_texts.get('top_x') or title_texts.get('top')
        right_text = title_texts.get('right_y') or title_texts.get('right')
        try:
            if title_offsets:
                ax._top_xlabel_manual_offset_y_pts = float(title_offsets.get('top_y', 0.0) or 0.0)
                ax._top_xlabel_manual_offset_x_pts = float(title_offsets.get('top_x', 0.0) or 0.0)
                ax._bottom_xlabel_manual_offset_y_pts = float(title_offsets.get('bottom_y', 0.0) or 0.0)
                ax._left_ylabel_manual_offset_x_pts = float(title_offsets.get('left_x', 0.0) or 0.0)
                ax._right_ylabel_manual_offset_x_pts = float(title_offsets.get('right_x', 0.0) or 0.0)
                ax._right_ylabel_manual_offset_y_pts = float(title_offsets.get('right_y', 0.0) or 0.0)
            if bottom_text is not None:
                ax._stored_xlabel = bottom_text
            if left_text is not None:
                ax._stored_ylabel = left_text
            if top_text:
                ax._top_xlabel_text_override = top_text
            elif hasattr(ax, '_top_xlabel_text_override'):
                delattr(ax, '_top_xlabel_text_override')
            if right_text:
                ax._right_ylabel_text_override = right_text
            elif hasattr(ax, '_right_ylabel_text_override'):
                delattr(ax, '_right_ylabel_text_override')
            if titles.get('has_bottom_x') is False:
                ax.xaxis.label.set_visible(False)
            else:
                ax.xaxis.label.set_visible(True)
                if bottom_text is not None:
                    ax.set_xlabel(bottom_text)
                elif hasattr(ax, '_stored_xlabel'):
                    ax.set_xlabel(ax._stored_xlabel)
            try:
                _ui_position_bottom_xlabel(ax, fig, tick_state)
            except Exception:
                pass
            if titles.get('has_left_y') is False:
                ax.yaxis.label.set_visible(False)
            else:
                ax.yaxis.label.set_visible(True)
                if left_text is not None:
                    ax.set_ylabel(left_text)
                elif hasattr(ax, '_stored_ylabel'):
                    ax.set_ylabel(ax._stored_ylabel)
            try:
                _ui_position_left_ylabel(ax, fig, tick_state)
            except Exception:
                pass
            ax._top_xlabel_on = bool(titles.get('top_x', False))
            try:
                _ui_position_top_xlabel(ax, fig, tick_state)
            except Exception:
                pass
            if not ax._top_xlabel_on and hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                try:
                    ax._top_xlabel_artist.set_visible(False)
                except Exception:
                    pass
            ax._right_ylabel_on = bool(titles.get('right_y', False))
            try:
                _ui_position_right_ylabel(ax, fig, tick_state)
            except Exception:
                pass
            if not ax._right_ylabel_on and hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                try:
                    ax._right_ylabel_artist.set_visible(False)
                except Exception:
                    pass
            if ax2_loaded is not None and right_text:
                ax2_loaded.set_ylabel(right_text, fontsize=16)
        except Exception:
            pass

        try:
            fig_cfg_spines = sess.get('figure', {}).get('spines', {})
            _restore_xy_axis_style_from_session(ax, axis_cfg, fig=fig, spines_cfg=fig_cfg_spines)
            from .spines import apply_xy_spine_specs
            apply_xy_spine_specs(fig, ax, tick_state, fig_cfg_spines)
            # Spine re-apply may overwrite explicit axis title colors with spine edge color.
            label_style = {}
            if axis_cfg.get("axis_label_colors"):
                label_style["axis_label_colors"] = axis_cfg["axis_label_colors"]
            if label_style:
                from .style import apply_xy_axis_style
                apply_xy_axis_style(ax, label_style, fig=fig, spines_cfg={})
            # Spine re-apply may call label positioning; only consume pending pads once.
            if getattr(ax, '_pending_xlabelpad', None) is not None:
                _ui_position_bottom_xlabel(ax, fig, tick_state)
            if getattr(ax, '_pending_ylabelpad', None) is not None:
                _ui_position_left_ylabel(ax, fig, tick_state)
        except Exception:
            pass

        args_subset = sess.get('args_subset', {})
        source_files = resolve_xy_source_files(
            args=None,
            labels=labels_list,
            cif_tick_series=cif_tick_series,
            fig=fig,
            args_subset=args_subset,
            session=sess,
        )
        Args = type('Args', (), {
            'stack': saved_stack,
            'autoscale': bool(args_subset.get('autoscale', True)),
            'norm': bool(args_subset.get('norm', False)),
            'files': source_files,
        })
        args_minimal = Args()

        cif_globals_dict: Optional[Dict[str, Any]] = None
        if cif_tick_series:
            cif_globals_dict = {
                'cif_tick_series': list(cif_tick_series),
                'cif_hkl_map': cif_hkl_map,
                'cif_hkl_label_map': cif_hkl_label_map,
                'show_cif_hkl': bool(show_cif_hkl),
                'show_cif_titles': bool(show_cif_titles),
                'cif_extend_suspended': False,
                'keep_canvas_fixed': True,
            }

        menu_kwargs = {
            'y_data_list': y_data_list,
            'x_data_list': x_data_list,
            'labels': labels_list,
            'orig_y': orig_y,
            'label_text_objects': label_text_objects,
            'delta': delta,
            'x_label': x_label,
            'args': args_minimal,
            'x_full_list': x_full_list,
            'raw_y_full_list': raw_y_full_list,
            'offsets_list': offsets_list,
            'use_Q': use_Q,
            'use_r': use_r,
            'use_E': use_E,
            'use_k': use_k,
            'use_rft': use_rft,
            'cif_globals': cif_globals_dict,
        }
        try:
            apply_session_font_cfg(
                fig,
                sess.get('font', {}) or {},
                ax,
                extra_artists=label_text_objects,
            )
        except Exception:
            pass
        return fig, ax, menu_kwargs
    except Exception as e:
        print(f"Error loading XY session: {e}")
        traceback.print_exc()
        return None



__all__ = ["dump_session", "load_xy_session"]
