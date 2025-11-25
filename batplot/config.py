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
      ]
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
        with open(config_file, 'r') as f:
            return json.load(f)  # Parse JSON string into Python dictionary
    except (json.JSONDecodeError, IOError):
        # File exists but is corrupted or unreadable
        # Return empty defaults instead of crashing
        return {}


def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration dictionary to JSON file.
    
    HOW IT WORKS:
    ------------
    1. Get path to config file (~/.batplot/config.json)
    2. Write dictionary as formatted JSON (indented for readability)
    3. If write fails (permissions, disk full, etc.), silently ignore
    
    WHY SILENT FAILURE?
    ------------------
    Configuration saving is not critical for program operation. If it fails,
    the program should continue working (just won't remember preferences).
    We don't want to interrupt the user's workflow with error messages about
    config file issues.
    
    Args:
        config: Dictionary with configuration values to save.
                Example: {'user_colors': ['#FF0000', '#00FF00']}
    """
    config_file = get_config_file()
    try:
        with open(config_file, 'w') as f:
            # indent=2 makes JSON file human-readable (pretty-printed)
            json.dump(config, f, indent=2)
    except IOError:
        # Silently ignore write errors (permissions, disk full, etc.)
        pass


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


def save_user_colors(colors: List[str]) -> None:
    """
    Save user-defined color list to configuration file.
    
    HOW IT WORKS:
    ------------
    1. Load existing config (to preserve other settings)
    2. Update 'user_colors' key with new list
    3. Save entire config back to file
    
    WHY UPDATE ENTIRE CONFIG?
    ------------------------
    The config file might contain other settings in the future (font preferences,
    default styles, etc.). We want to preserve those when updating colors.
    
    Args:
        colors: List of color codes to save.
                Example: ['#FF0000', '#00FF00', 'red', 'blue']
    """
    config = load_config()  # Load existing config (preserves other settings)
    config['user_colors'] = colors  # Update user_colors key
    save_config(config)  # Save entire config back to file


__all__ = [
    'get_user_colors',
    'save_user_colors',
]
