"""Configuration management for batplot.

Handles persistent user preferences like custom color lists.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import List, Optional, Dict, Any


def get_config_dir() -> Path:
    """Get batplot configuration directory, creating it if needed.
    
    Returns:
        Path to ~/.batplot directory
    """
    config_dir = Path.home() / '.batplot'
    config_dir.mkdir(exist_ok=True)
    return config_dir


def get_config_file() -> Path:
    """Get path to main config file.
    
    Returns:
        Path to ~/.batplot/config.json
    """
    return get_config_dir() / 'config.json'


def load_config() -> Dict[str, Any]:
    """Load configuration from file.
    
    Returns:
        Dictionary with config values, or empty dict if file doesn't exist
    """
    config_file = get_config_file()
    if not config_file.exists():
        return {}
    
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file.
    
    Args:
        config: Dictionary with config values to save
    """
    config_file = get_config_file()
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    except IOError:
        pass


def get_user_colors() -> List[str]:
    """Get user-defined color list.
    
    Returns:
        List of color codes (hex or named colors)
    """
    config = load_config()
    return config.get('user_colors', [])


def save_user_colors(colors: List[str]) -> None:
    """Save user-defined color list.
    
    Args:
        colors: List of color codes to save
    """
    config = load_config()
    config['user_colors'] = colors
    save_config(config)


__all__ = [
    'get_user_colors',
    'save_user_colors',
]
