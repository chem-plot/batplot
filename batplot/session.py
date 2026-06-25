"""Session helpers for batplot interactive mode.

This module provides functions to save and load interactive plotting sessions.
Sessions allow you to save your current plot state (colors, labels, ranges, etc.)
and restore it later, so you don't have to recreate your styling from scratch.

HOW SESSIONS WORK:
-----------------
A session file (.pkl) contains a complete snapshot of your plot state:
- Data: Original x/y data, labels, offsets
- Styling: Colors, line widths, fonts, tick settings
- Geometry: Axis ranges, figure size, axes position
- State: Which curves are visible, label positions, etc.

When you save a session:
1. All plot state is collected into a dictionary
2. Dictionary is serialized using pickle (Python's object serialization)
3. Saved to a .pkl file

When you load a session:
1. .pkl file is read and deserialized
2. Plot is recreated from saved data
3. All styling and state is restored exactly as it was

This is different from style files (.bps/.bpsg):
- Style files: Save only styling (colors, fonts, ticks) - can be applied to different data
- Session files: Save everything including data - exact recreation of a specific plot
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import traceback
from functools import wraps
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast

import numpy as np  # type: ignore[import-untyped]
from numpy import ma as _ma
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.colorbar import Colorbar as _Colorbar  # type: ignore[import-untyped]
from matplotlib.colors import to_hex, to_rgba  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    MultipleLocator, AutoLocator, AutoMinorLocator,
    NullFormatter, NullLocator,
)

from .utils import (
    _confirm_overwrite,
    ensure_exact_case_filename,
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
)
from .color_utils import ensure_colormap
from .ui import (
    set_spine_side_color as _set_spine_side_color,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    capture_axes_tick_locators,
    restore_axes_tick_locators,
    apply_wasd_minor_ticks,
)
from .plot_modes.common.interactive_state import build_saved_tick_state
from .plot_modes.common.axis_state import (
    capture_axis_spines_and_tick_widths,
    capture_axis_wasd_state,
)
from .plotting import apply_curve_color, update_labels


def _capture_xy_axis_style_for_session(ax) -> Dict[str, Any]:
    from .plot_modes.xy.style import capture_xy_axis_style
    return capture_xy_axis_style(ax)


def _restore_xy_axis_style_from_session(ax, axis_cfg: Dict[str, Any], *, fig=None, spines_cfg=None) -> None:
    from .plot_modes.xy.style import apply_xy_axis_style
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
    from .plot_modes.xy.style import serialize_curve_palette_history
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


def _try_extract_version_from_pickle(filename: str) -> Dict[str, str]:
    """Try to extract package_versions from a pickle file even if it fails to fully load.
    
    Note: This may not work if pickle.load() fails completely due to missing modules.
    In that case, we can't extract version info, but we can still show current version.
    
    Returns:
        dict with package versions, or empty dict if extraction fails
    """
    try:
        with open(filename, 'rb') as f:
            # Try to load the pickle
            # This will fail if numpy._core is missing, but we try anyway
            sess = pickle.load(f)
            if isinstance(sess, dict):
                return sess.get('package_versions', {})
    except Exception:
        # If loading fails completely (e.g., ModuleNotFoundError for numpy._core),
        # we can't extract version info. This is expected in version mismatch cases.
        pass
    return {}


def _get_current_numpy_version() -> str:
    """Get current numpy version, even if import fails.
    
    Tries multiple methods:
    1. Direct import (fastest)
    2. pip show (works even if import fails)
    3. Returns 'unknown' if all fail
    
    Returns:
        Version string or 'unknown'
    """
    # Method 1: Try direct import
    try:
        return np.__version__
    except Exception:
        pass
    
    # Method 2: Try pip show
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'numpy'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    return line.split(':', 1)[1].strip()
    except Exception:
        pass
    
    return 'unknown'


def _current_tick_width(axis_obj, which: str):
    """
    Return the configured tick width for the given X/Y axis.
    
    HOW IT WORKS:
    ------------
    Tick widths can be set in two places:
    1. **Per-axis setting**: Stored in axis object's internal dictionary
       - This is set when you use ax.tick_params(axis='x', which='major', width=2.0)
       - Stored in axis_obj._major_tick_kw or axis_obj._minor_tick_kw
    
    2. **Global matplotlib setting**: Stored in plt.rcParams
       - This is the default used when per-axis setting isn't specified
       - Key format: 'xtick.major.width' or 'ytick.minor.width'
    
    This function checks both locations (per-axis first, then global) to find
    the actual width being used.
    
    Args:
        axis_obj: Matplotlib axis object (ax.xaxis or ax.yaxis)
        which: 'major' or 'minor' (which type of ticks)
    
    Returns:
        Tick width as float, or None if not found
    """
    try:
        # Try to get width from axis object's internal settings
        # _major_tick_kw and _minor_tick_kw are dictionaries storing tick parameters
        tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
        width = tick_kw.get('width')  # Get 'width' key from dictionary
        
        # If not found in axis object, check global matplotlib settings
        if width is None:
            # Get axis name ('x' or 'y') - defaults to 'x' if not found
            axis_name = getattr(axis_obj, 'axis_name', 'x')
            # Build rcParams key: 'xtick.major.width' or 'ytick.minor.width'
            rc_key = f"{axis_name}tick.{which}.width"
            width = plt.rcParams.get(cast(Any, rc_key))  # Get from global settings
        
        # Convert to float if found
        if width is not None:
            return float(width)
    except Exception:
        # If anything fails (attribute error, type error, etc.), return None
        pass
    return None


def _current_tick_length(axis_obj, which: str):
    """Return the configured/displayed tick length for the given X/Y axis."""
    try:
        tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
        length = tick_kw.get('size') or tick_kw.get('length')
        if length is not None:
            return float(length)
    except Exception:
        pass
    try:
        ticks = axis_obj.get_major_ticks() if which == 'major' else axis_obj.get_minor_ticks()
        if ticks:
            line = ticks[0].tick1line
            if line is not None:
                return float(line.get_markersize())
    except Exception:
        pass
    try:
        axis_name = getattr(axis_obj, 'axis_name', 'x')
        rc_key = f"{axis_name}tick.{which}.size"
        length = plt.rcParams.get(cast(Any, rc_key))
        return float(length) if length is not None else None
    except Exception:
        return None


def _apply_session_tick_lengths(fig, axes, lengths: Dict[str, Any] | None) -> None:
    """Apply saved major/minor tick lengths to one or more axes."""
    if not lengths:
        return
    major = lengths.get('major')
    minor = lengths.get('minor')
    if major is None:
        major = lengths.get('x_major', lengths.get('y_major', lengths.get('ly_major', lengths.get('ry_major'))))
    if minor is None:
        minor = lengths.get('x_minor', lengths.get('y_minor', lengths.get('ly_minor', lengths.get('ry_minor'))))
    try:
        if major is not None:
            for axis in axes:
                if axis is not None:
                    axis.tick_params(axis='both', which='major', length=float(major))
        if minor is not None:
            for axis in axes:
                if axis is not None:
                    axis.tick_params(axis='both', which='minor', length=float(minor))
        if major is not None or minor is not None:
            if not hasattr(fig, '_tick_lengths') or not isinstance(getattr(fig, '_tick_lengths', None), dict):
                fig._tick_lengths = {}
            if major is not None:
                fig._tick_lengths['major'] = float(major)
            if minor is not None:
                fig._tick_lengths['minor'] = float(minor)
    except Exception:
        pass


def _grid_enabled(ax) -> bool:
    """Return True if any gridline is currently visible."""
    try:
        return any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines())
    except Exception:
        return bool(ax.xaxis._gridOnMajor) if hasattr(ax.xaxis, '_gridOnMajor') else False


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


def _apply_axes_bbox(ax, bbox) -> bool:
    """
    Apply stored axes bounding box (position and size) to restore plot geometry.
    
    HOW IT WORKS:
    ------------
    The bounding box (bbox) defines where the plot area is positioned within
    the figure. It's stored as fractions (0.0 to 1.0) of the figure size.
    
    COORDINATE SYSTEM:
    -----------------
    Figure coordinates (fractions):
    - (0.0, 0.0) = bottom-left corner of figure
    - (1.0, 1.0) = top-right corner of figure
    - left, right, bottom, top are all between 0.0 and 1.0
    
    Example bbox:
        left=0.15, right=0.95, bottom=0.15, top=0.95
        This means plot occupies 80% of figure width (0.95-0.15) and 80% of height,
        centered with 15% margins on all sides.
    
    CALCULATION:
    -----------
    - width = right - left (horizontal size)
    - height = top - bottom (vertical size)
    - Position = [left, bottom, width, height]
    
    Args:
        ax: Matplotlib axes object
        bbox: Dictionary with keys 'left', 'right', 'bottom', 'top' (all floats 0.0-1.0)
    
    Returns:
        True if bbox was successfully applied, False if invalid or error occurred
    """
    # Validate input: must be a dictionary
    if not isinstance(bbox, dict):
        return False
    
    # Check that all required keys are present
    required = ('left', 'right', 'bottom', 'top')
    if not all(k in bbox for k in required):
        return False
    
    try:
        # Extract and convert to floats
        left = float(bbox['left'])
        right = float(bbox['right'])
        bottom = float(bbox['bottom'])
        top = float(bbox['top'])
        
        # Calculate dimensions
        width = right - left   # Horizontal size
        height = top - bottom  # Vertical size
        
        # Validate dimensions (must be positive)
        if width <= 0 or height <= 0:
            return False
        
        # Apply position and size to axes
        # set_position([left, bottom, width, height]) sets plot area within figure
        ax.set_position([left, bottom, width, height])
        return True
    except Exception:
        # If any conversion or application fails, return False
        return False


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


def _capture_session_tick_locator(ax):
    """Capture tick spacing/minor-count locator state for session serialization."""
    return capture_axes_tick_locators(ax, ('x', 'y'))


def _restore_session_tick_locator(ax, state):
    """Restore tick spacing/minor-count locator state saved by _capture_session_tick_locator."""
    restore_axes_tick_locators(ax, state, ('x', 'y'))


# ------------------------- Generic XY session (existing) -------------------------


def _dump_session_impl(
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
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
                'mathtext_fontset': plt.rcParams.get('mathtext.fontset'),
            },
            'args_subset': {
                'stack': bool(getattr(args, 'stack', False)),
                'autoscale': bool(getattr(args, 'autoscale', False)),
                'norm': bool(getattr(args, 'norm', False)),
            },
            'cif_tick_series': [tuple(t) for t in (cif_tick_series or [])],
            'cif_hkl_map': {k: [tuple(v) for v in val] for k, val in (cif_hkl_map or {}).items()},
            'cif_hkl_label_map': {k: dict(v) for k, v in (cif_hkl_label_map or {}).items()},
            'show_cif_hkl': bool(show_cif_hkl),
            'show_cif_titles': bool(show_cif_titles) if show_cif_titles is not None else True,
            'cif_stack_y_offsets': list(getattr(fig, '_bp_cif_stack_y_offsets', []) or []),
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
        
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"Session saved to {target}")
    except Exception as e:  # pragma: no cover - defensive path
        print(f"Error saving session: {e}")

# --------------------- Operando + EC combined session helpers --------------------

def _dump_operando_session_impl(
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
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
                'mathtext_fontset': plt.rcParams.get('mathtext.fontset'),
            },
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
        
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"Operando session saved to {target}")
    except Exception as e:  # pragma: no cover - defensive path
        print(f"Error saving operando session: {e}")


def _load_operando_session_impl(filename: str):
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
            from .plot_modes.operando.layout import _update_custom_colorbar
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
                    from .plot_modes.operando.ions_axis import install_ec_ions_y_display  # lazy: avoid operando→session cycle
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
            from .plot_modes.operando.layout import _apply_group_layout_inches, _ensure_fixed_params
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
            from .plot_modes.operando.plot import _draw_operando_cif_ticks
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
        from .plot_modes.operando.layout import _finalize_operando_session_axes
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
    return fig, ax, im, cbar, ec_ax


__all__ = [
    "dump_session",
    "dump_operando_session",
    "load_operando_session",
    "dump_ec_session",
    "load_ec_session",
    "dump_cpc_session",
    "load_cpc_session",
    "load_xy_session",
]
 
# --------------------- Electrochem GC session helpers ---------------------------

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
                try:
                    if hasattr(ln, '_orig_xdata_gc'):
                        payload['orig_xdata_gc'] = np.asarray(getattr(ln, '_orig_xdata_gc'), float)
                except Exception:
                    pass
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
            try:
                if hasattr(ln, '_orig_xdata_gc'):
                    payload['orig_xdata_gc'] = np.asarray(getattr(ln, '_orig_xdata_gc'), float)
            except Exception:
                pass
            entry['line'] = payload
        lines_state[int(cyc)] = entry
    return lines_state


def _dump_ec_session_impl(
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
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
                'mathtext_fontset': plt.rcParams.get('mathtext.fontset'),
            },
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
        except Exception:
            pass
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"EC session saved to {target}")
    except Exception as e:
        print(f"Error saving EC session: {e}")


def _load_ec_session_impl(
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
                        if rec.get('orig_xdata_gc') is not None:
                            try:
                                setattr(ln_obj, '_orig_xdata_gc', np.asarray(rec.get('orig_xdata_gc'), float))
                            except Exception:
                                pass
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
                            if rec.get('orig_xdata_gc') is not None:
                                try:
                                    setattr(ln_obj, '_orig_xdata_gc', np.asarray(rec.get('orig_xdata_gc'), float))
                                except Exception:
                                    pass
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
        # Restore display_mode (charge/discharge/both) for consistency
        try:
            dm = sess.get('display_mode', 'both')
            if dm in ('charge', 'discharge', 'both'):
                setattr(fig, '_ec_display_mode', dm)
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
                            if top_axis_cfg.get('xlabel') is not None:
                                secax.set_xlabel(str(top_axis_cfg.get('xlabel') or ''))
                            secax.xaxis.label.set_visible(bool(top_axis_cfg.get('xlabel_visible', True)))
                            if top_axis_cfg.get('label_color'):
                                secax.xaxis.label.set_color(top_axis_cfg['label_color'])
                            sp = secax.spines.get('top')
                            if sp is not None:
                                if top_axis_cfg.get('spine_visible') is not None:
                                    sp.set_visible(bool(top_axis_cfg.get('spine_visible')))
                                if top_axis_cfg.get('spine_color'):
                                    sp.set_edgecolor(top_axis_cfg['spine_color'])
                                    secax.tick_params(axis='x', which='both', colors=top_axis_cfg['spine_color'])
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
    if not embed:
        try:
            blob = sess.get('dqdv_2d')
            if isinstance(blob, dict) and blob.get('Z') is not None:
                from .plot_modes.electrochem.interactive import restore_dqdv_2d_companion_figure
                cbundle = restore_dqdv_2d_companion_figure(blob)
                if cbundle:
                    setattr(fig, '_dqdv_2d_companion_bundle', cbundle)
        except Exception as _e2d:
            print(f"Warning: could not restore dQ/dV 2D companion: {_e2d}")
    if file_data_out is not None:
        return (fig, ax, None, file_data_out)
    return (fig, ax, cycle_lines)

# --------------------- CPC (Capacity-Per-Cycle) session helpers -----------------

def _dump_cpc_session_impl(
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
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
            },
            'grid': ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else (
                any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()) if hasattr(ax, 'get_xgridlines') else False
            ),
            'display_mode': getattr(fig, '_cpc_display_mode', 'both'),
            'spine_colors_auto': bool(getattr(fig, '_cpc_spine_auto', False)),
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
        with open(target, 'wb') as f:
            pickle.dump(meta, f)
        print(f"CPC session saved to {target}")
    except Exception as e:
        print(f"Error saving CPC session: {e}")


def _load_cpc_session_impl(filename: str):
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
            from .plot_modes.cpc.legend import _rebuild_legend
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
            if not vis:
                leg = ax.get_legend() or ax2.get_legend()
                if leg is not None:
                    leg.set_visible(False)
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
        return fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data
    except Exception as e:
        print(f"Error loading CPC session: {e}")
        traceback.print_exc()
        return None


def _load_xy_session_impl(filename: str) -> tuple[Any, Any, dict[str, Any]] | None:  # pyright: ignore[reportGeneralTypeIssues]
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
                    if 'color' in spec and spec['color'] is not None:
                        spn.set_edgecolor(spec['color'])
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
            _ui_position_bottom_xlabel(ax, fig, tick_state)
            _ui_position_left_ylabel(ax, fig, tick_state)
        except Exception:
            pass

        args_subset = sess.get('args_subset', {})
        Args = type('Args', (), {
            'stack': saved_stack,
            'autoscale': bool(args_subset.get('autoscale', True)),
            'norm': bool(args_subset.get('norm', False)),
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
        return fig, ax, menu_kwargs
    except Exception as e:
        print(f"Error loading XY session: {e}")
        traceback.print_exc()
        return None


# Public facade -------------------------------------------------------------
#
# Keep the stable batplot.session API while routing ownership through the
# per-mode session modules. The mode modules currently call the private
# implementations above; future extraction can move those implementations into
# the mode modules without changing callers or pickle schemas.

@wraps(_dump_session_impl)
def dump_session(*args, **kwargs):
    from .plot_modes.xy.session import dump_session as _dump
    return _dump(*args, **kwargs)


@wraps(_load_xy_session_impl)
def load_xy_session(*args, **kwargs):
    from .plot_modes.xy.session import load_xy_session as _load
    return _load(*args, **kwargs)


@wraps(_dump_ec_session_impl)
def dump_ec_session(*args, **kwargs):
    from .plot_modes.electrochem.session import dump_ec_session as _dump
    return _dump(*args, **kwargs)


@wraps(_load_ec_session_impl)
def load_ec_session(*args, **kwargs):
    from .plot_modes.electrochem.session import load_ec_session as _load
    return _load(*args, **kwargs)


@wraps(_dump_cpc_session_impl)
def dump_cpc_session(*args, **kwargs):
    from .plot_modes.cpc.session import dump_cpc_session as _dump
    return _dump(*args, **kwargs)


@wraps(_load_cpc_session_impl)
def load_cpc_session(*args, **kwargs):
    from .plot_modes.cpc.session import load_cpc_session as _load
    return _load(*args, **kwargs)


@wraps(_dump_operando_session_impl)
def dump_operando_session(*args, **kwargs):
    from .plot_modes.operando.session import dump_operando_session as _dump
    return _dump(*args, **kwargs)


@wraps(_load_operando_session_impl)
def load_operando_session(*args, **kwargs):
    from .plot_modes.operando.session import load_operando_session as _load
    return _load(*args, **kwargs)
