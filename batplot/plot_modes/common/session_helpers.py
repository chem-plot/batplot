"""Shared session dump/load helpers (version stamps, ticks, axes bbox).

Owned by ``plot_modes.common`` so mode-specific session modules can import
these without depending on the root ``batplot.session`` facade (avoids
circular imports during extraction).
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
from typing import Any, Dict, Optional, cast

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
        run_kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": 5,
            "check": False,
        }
        # Avoid a flashing console window on Windows when pip is spawned.
        if sys.platform.startswith("win"):
            run_kwargs["creationflags"] = int(
                getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            )
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'numpy'],
            **run_kwargs,
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
    """Return the configured/displayed tick length for the given X/Y axis.

    Length ``0`` is valid (WASD ``l`` / hide ticks by size) and must not be
    discarded by truthiness on ``size``/``length``.
    """
    try:
        tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
        length = tick_kw.get('size')
        if length is None:
            length = tick_kw.get('length')
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


def _first_defined(*values):
    """Return the first value that is not ``None`` (keeps ``0`` / ``""``)."""
    for value in values:
        if value is not None:
            return value
    return None


def _artist_linewidth(artist, default: float = 1.0) -> float:
    """Return artist linewidth; ``0`` is valid and must not coerce to ``default``."""
    try:
        lw = artist.get_linewidth()
    except Exception:
        return float(default)
    return float(default if lw is None else lw)


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


def capture_last_figure_export_path(fig):
    """Return the figure's last exported-figure path for session serialization.

    Persisting this path lets the ``oe`` (overwrite figure) shortcut reappear
    when the session is reopened later. Always absolute (``os.path.abspath``)
    so Windows drive letters and POSIX paths round-trip the same way.
    """
    path = getattr(fig, '_last_figure_export_path', None)
    if isinstance(path, str) and path.strip():
        try:
            return os.path.abspath(path)
        except Exception:
            return path
    return None


_FIGURE_EXTS = ('.svg', '.png', '.pdf', '.jpg', '.jpeg', '.eps', '.tif', '.tiff')


def _casefold_name(name: str) -> str:
    """Case-fold a path segment for Windows / macOS default FS + Linux safety."""
    try:
        return str(name).casefold()
    except Exception:
        return str(name).lower()


def _find_named_file_ci(directory: str, wanted_name: str) -> Optional[str]:
    """Return ``directory/wanted_name`` if present, case-insensitive on the name.

    Uses ``os.path.join`` / ``os.listdir`` only — no hardcoded ``/`` or ``\\``.
    On case-sensitive Linux this still finds ``Plot.SVG`` when looking for
    ``plot.svg``; on Windows/macOS ``isfile`` already matches ignoring case.
    """
    if not directory or not wanted_name:
        return None
    direct = os.path.join(directory, wanted_name)
    try:
        if os.path.isfile(direct):
            return os.path.abspath(direct)
    except Exception:
        pass
    try:
        if not os.path.isdir(directory):
            return None
        want = _casefold_name(wanted_name)
        for entry in os.listdir(directory):
            if _casefold_name(entry) == want:
                full = os.path.join(directory, entry)
                if os.path.isfile(full):
                    return os.path.abspath(full)
    except Exception:
        return None
    return None


def discover_companion_figure_path(session_filename: Optional[str]) -> Optional[str]:
    """Find an existing figure file that matches a session basename.

    Looks for ``Figures/<stem>.<ext>`` next to the ``.pkl`` (batplot's usual
    organized export layout) and ``<stem>.<ext>`` in the same folder. Path
    joins use ``os.path`` so this is correct on Windows, macOS, and Linux.
    Name matching is case-insensitive (``.SVG`` / ``.svg``, ``Figures`` /
    ``figures``).
    """
    if not session_filename:
        return None
    try:
        sess = os.path.abspath(session_filename)
        base_dir = os.path.dirname(sess)
        stem = os.path.splitext(os.path.basename(sess))[0]
        if not stem:
            return None
        # Prefer organized Figures/ (any case), then same directory as the .pkl.
        search_dirs = []
        figures_dir = _find_named_dir_ci(base_dir, 'Figures')
        if figures_dir:
            search_dirs.append(figures_dir)
        search_dirs.append(base_dir)
        for directory in search_dirs:
            for ext in _FIGURE_EXTS:
                found = _find_named_file_ci(directory, stem + ext)
                if found:
                    return found
    except Exception:
        return None
    return None


def _find_named_dir_ci(parent: str, wanted_name: str) -> Optional[str]:
    """Return ``parent/wanted_name`` directory, matching the name case-insensitively."""
    if not parent or not wanted_name:
        return None
    direct = os.path.join(parent, wanted_name)
    try:
        if os.path.isdir(direct):
            return direct
    except Exception:
        pass
    try:
        if not os.path.isdir(parent):
            return None
        want = _casefold_name(wanted_name)
        for entry in os.listdir(parent):
            if _casefold_name(entry) == want:
                full = os.path.join(parent, entry)
                if os.path.isdir(full):
                    return full
    except Exception:
        return None
    return None


def restore_last_figure_export_path(
    fig,
    sess,
    session_filename: Optional[str] = None,
) -> None:
    """Seed ``fig._last_figure_export_path`` so ``oe`` appears after reopen.

    Order:
    1. Explicit ``last_figure_export_path`` from the session (if the file still
       exists, or if no companion fallback is available).
    2. Companion figure next to the ``.pkl`` (same stem under ``Figures/``).
    Old sessions without the key still load; ``oe`` then appears only when a
    companion figure is found. Paths are always stored absolute via
    ``os.path.abspath`` (drive-letter safe on Windows).
    """
    path = None
    try:
        if sess is not None:
            path = sess.get('last_figure_export_path')
    except Exception:
        path = None

    stored = path if isinstance(path, str) and path.strip() else None
    stored_exists = False
    if stored:
        try:
            stored_exists = os.path.isfile(stored)
        except Exception:
            stored_exists = False
    if stored and stored_exists:
        chosen = os.path.abspath(stored)
    else:
        companion = discover_companion_figure_path(session_filename)
        if companion:
            chosen = companion
        elif stored:
            # Keep the remembered path even if the file is temporarily missing
            # so ``oe`` can still offer overwrite / report missing.
            chosen = os.path.abspath(stored)
        else:
            return
    try:
        fig._last_figure_export_path = chosen
    except Exception:
        pass


def resolve_session_save_path(name: str, folder: str | None = None) -> str:
    """Expand ``~``, join folder if relative, abspath, preserve exact case.

    Used by interactive ``s`` filename prompts (batch already expands ``~``).
    """
    from ...utils import ensure_exact_case_filename

    name = os.path.expanduser(str(name).strip())
    if not os.path.splitext(name)[1]:
        name = name + ".pkl"
    if folder and not os.path.isabs(name):
        target = os.path.join(folder, name)
    else:
        target = name
    return ensure_exact_case_filename(os.path.abspath(os.path.normpath(target)))


__all__ = [
    "_try_extract_version_from_pickle",
    "_package_versions_stamp",
    "_get_current_numpy_version",
    "_current_tick_width",
    "_current_tick_length",
    "_first_defined",
    "_artist_linewidth",
    "_apply_session_tick_lengths",
    "_apply_axes_bbox",
    "_capture_session_tick_locator",
    "_restore_session_tick_locator",
    "capture_last_figure_export_path",
    "discover_companion_figure_path",
    "restore_last_figure_export_path",
    "resolve_session_save_path",
]
