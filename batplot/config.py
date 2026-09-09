"""Configuration management for batplot.

This module handles persistent user preferences that are saved between sessions.
Currently, it manages user-defined color lists, but can be extended for other
preferences like default styles, font settings, etc.

HOW CONFIGURATION WORKS:
-----------------------
User preferences are stored in a JSON file at ~/.batplot/config.json.
This file persists between batplot sessions, so your custom colors are
remembered the next time you run batplot.

Example config.json structure:
    {
      "user_colors": [
        "#FF0000",
        "#00FF00",
        "#0000FF",
        "red",
        "blue"
      ],
      "recent_axis_names": [
        "Potential (V)",
        "dQ/dV (mAh V$^{-1}$)"
      ],
      "recent_axis_names_by_mode": {
        "xy": ["2$\\theta$ ($^\\circ$)"],
        "ec": ["Potential (V)"]
      }
    }

The config file is created automatically the first time you save a preference.
If the file doesn't exist or is corrupted, we return empty defaults (graceful degradation).
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any


def get_config_dir() -> Path:
    """
    Get batplot configuration directory, creating it if needed.
    
    HOW IT WORKS:
    ------------
    Returns the path to ~/.batplot directory (user's home directory + .batplot).
    If the directory doesn't exist, it's created automatically.
    
    WHY ~/.batplot?
    --------------
    The tilde (~) represents the user's home directory. This is a standard
    location for application configuration files on Unix-like systems (Linux, macOS).
    It keeps user data separate from system files and other users' data.
    
    Examples:
        Linux/macOS: /home/username/.batplot or /Users/username/.batplot
        Windows: C:\\Users\\username\\.batplot
    
    Returns:
        Path object pointing to ~/.batplot directory
    """
    config_dir = Path.home() / '.batplot'
    # mkdir(exist_ok=True) creates directory if it doesn't exist,
    # but doesn't raise error if it already exists
    config_dir.mkdir(exist_ok=True)
    return config_dir


def get_config_file() -> Path:
    """
    Get path to main configuration file.
    
    Returns:
        Path object pointing to ~/.batplot/config.json
    """
    return get_config_dir() / 'config.json'


def load_config() -> Dict[str, Any]:
    """
    Load configuration from JSON file.
    
    HOW IT WORKS:
    ------------
    1. Check if config file exists
    2. If not, return empty dictionary (defaults)
    3. If exists, read JSON and parse it
    4. If file is corrupted or unreadable, return empty dictionary (graceful failure)
    
    WHY GRACEFUL FAILURE?
    --------------------
    If the config file is corrupted (invalid JSON) or can't be read (permissions),
    we don't want to crash the program. Instead, we return empty defaults and
    let the user continue. The next time they save a preference, a new valid
    file will be created.
    
    Returns:
        Dictionary with configuration values, or empty dict if:
        - File doesn't exist (first run)
        - File is corrupted (invalid JSON)
        - File can't be read (permissions error)
    """
    config_file = get_config_file()
    
    # If file doesn't exist, return empty defaults (first run)
    if not config_file.exists():
        return {}
    
    # Try to read and parse JSON file
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)  # Parse JSON string into Python dictionary
    except (json.JSONDecodeError, IOError):
        # File exists but is corrupted or unreadable
        # Return empty defaults instead of crashing
        return {}


def save_config(config: Dict[str, Any]) -> bool:
    """
    Save configuration dictionary to JSON file.

    Returns True on success, False if the write failed (permissions/disk).
    """
    config_file = get_config_file()
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            # indent=2 makes JSON file human-readable (pretty-printed)
            json.dump(config, f, indent=2)
        return True
    except IOError:
        return False


def get_user_colors() -> List[str]:
    """
    Get user-defined color list from configuration file.
    
    HOW IT WORKS:
    ------------
    1. Load entire config file
    2. Extract 'user_colors' key (list of color codes)
    3. Return list, or empty list if not found
    
    WHAT ARE USER COLORS?
    --------------------
    Users can save custom color codes (hex like '#FF0000' or named like 'red')
    for quick access in interactive menus. These colors are stored persistently
    and can be referenced by index (e.g., 'u1' for first user color).
    
    Returns:
        List of color codes (hex strings like '#FF0000' or named colors like 'red').
        Empty list if no user colors have been saved yet.
    """
    config = load_config()
    # .get('user_colors', []) returns the list if key exists, or [] if not
    return config.get('user_colors', [])


def save_user_colors(colors: List[str]) -> bool:
    """
    Save user-defined color list to configuration file.
    
    Returns True if the config file write succeeded.
    """
    config = load_config()  # Load existing config (preserves other settings)
    config['user_colors'] = colors  # Update user_colors key
    return bool(save_config(config))


_RECENT_AXIS_NAMES_KEY = 'recent_axis_names'
_RECENT_AXIS_NAMES_BY_MODE_KEY = 'recent_axis_names_by_mode'
RECENT_AXIS_NAMES_MAX = 20


def _clean_recent_names(raw: Any) -> List[str]:
    """Normalize a stored list: strings only, stripped, deduped, capped."""
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        s = str(item).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= RECENT_AXIS_NAMES_MAX:
            break
    return out


def get_recent_axis_names(mode: Optional[str] = None) -> List[str]:
    """Return up to :data:`RECENT_AXIS_NAMES_MAX` recently typed axis labels (newest first).

    With ``mode`` (e.g. ``'xy'``, ``'ec'``, ``'cpc'``, ``'operando'``,
    ``'histo'``) the per-mode list is returned. On first access for a mode the
    list is lazily seeded from the legacy shared ``recent_axis_names`` list so
    history from older batplot versions is preserved. Without ``mode`` the
    legacy shared list is returned unchanged (backward compatible).
    """
    config = load_config()
    if mode is None:
        return _clean_recent_names(config.get(_RECENT_AXIS_NAMES_KEY, []))
    by_mode = config.get(_RECENT_AXIS_NAMES_BY_MODE_KEY)
    if isinstance(by_mode, dict) and mode in by_mode:
        return _clean_recent_names(by_mode.get(mode))
    # Lazy migration: seed this mode from the legacy shared list (once).
    legacy = _clean_recent_names(config.get(_RECENT_AXIS_NAMES_KEY, []))
    if legacy:
        if not isinstance(by_mode, dict):
            by_mode = {}
        by_mode[mode] = list(legacy)
        config[_RECENT_AXIS_NAMES_BY_MODE_KEY] = by_mode
        save_config(config)
    return legacy


def record_recent_axis_name(name: str, mode: Optional[str] = None) -> None:
    """Add an axis label to the recent list (dedupe, newest first, max 20).

    With ``mode`` the name is stored in that mode's own list (seeding it from
    the legacy shared list first, if needed). Without ``mode`` the legacy
    shared list is updated as before.
    """
    s = str(name or '').strip()
    if not s:
        return
    config = load_config()
    if mode is None:
        names = [t for t in _clean_recent_names(config.get(_RECENT_AXIS_NAMES_KEY, [])) if t != s]
        names.insert(0, s)
        config[_RECENT_AXIS_NAMES_KEY] = names[:RECENT_AXIS_NAMES_MAX]
        save_config(config)
        return
    by_mode = config.get(_RECENT_AXIS_NAMES_BY_MODE_KEY)
    if not isinstance(by_mode, dict):
        by_mode = {}
    if mode in by_mode:
        current = _clean_recent_names(by_mode.get(mode))
    else:
        # First per-mode write: seed from the legacy shared list.
        current = _clean_recent_names(config.get(_RECENT_AXIS_NAMES_KEY, []))
    names = [t for t in current if t != s]
    names.insert(0, s)
    by_mode[mode] = names[:RECENT_AXIS_NAMES_MAX]
    config[_RECENT_AXIS_NAMES_BY_MODE_KEY] = by_mode
    save_config(config)


__all__ = [
    'get_user_colors',
    'save_user_colors',
    'get_recent_axis_names',
    'record_recent_axis_name',
    'RECENT_AXIS_NAMES_MAX',
]
