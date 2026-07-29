"""Shared session dump/load helpers (version stamps, ticks, axes bbox).

Owned by ``plot_modes.common`` so mode-specific session modules can import
these without depending on the root ``batplot.session`` facade (avoids
circular imports during extraction).
"""

from __future__ import annotations

import pickle
import subprocess
import sys
from typing import Any, Dict, cast

import numpy as np  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...ui import (
    capture_axes_tick_locators,
    restore_axes_tick_locators,
)


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


def _package_versions_stamp() -> Dict[str, str]:
    """Versions recorded into every session pickle for mismatch diagnostics."""
    out: Dict[str, str] = {
        "numpy": _get_current_numpy_version(),
    }
    try:
        import matplotlib as _mpl  # type: ignore[import-untyped]
        out["matplotlib"] = str(getattr(_mpl, "__version__", "unknown"))
    except Exception:
        out["matplotlib"] = "unknown"
    try:
        out["python"] = sys.version.split()[0]
    except Exception:
        pass
    return out


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
    """Return configured tick width for an X/Y axis (delegates to shared helper)."""
    from .spines import current_tick_width

    return current_tick_width(axis_obj, which)


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


def _capture_session_tick_locator(ax):
    """Capture tick spacing/minor-count locator state for session serialization."""
    return capture_axes_tick_locators(ax, ('x', 'y'))


def _restore_session_tick_locator(ax, state):
    """Restore tick spacing/minor-count locator state saved by _capture_session_tick_locator."""
    restore_axes_tick_locators(ax, state, ('x', 'y'))



__all__ = [
    "_try_extract_version_from_pickle",
    "_package_versions_stamp",
    "_get_current_numpy_version",
    "_current_tick_width",
    "_current_tick_length",
    "_apply_session_tick_lengths",
    "_apply_axes_bbox",
    "_capture_session_tick_locator",
    "_restore_session_tick_locator",
]
