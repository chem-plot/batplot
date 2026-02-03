"""Version checking utility for batplot.

This module checks PyPI (Python Package Index) for newer versions of batplot
and notifies users when updates are available.

HOW VERSION CHECKING WORKS:
--------------------------
When you run batplot, it automatically (and silently) checks for updates:

1. **Check Cache**: First checks a local cache file to see if we've checked recently
   - Cache is valid for 1 hour (3600 seconds)
   - If cache is fresh, use cached result (no network request)

2. **Fetch from PyPI**: If cache is stale or missing:
   - Makes HTTP request to PyPI API (https://pypi.org/pypi/batplot/json)
   - Gets latest version number
   - Updates cache with new version and timestamp

3. **Compare Versions**: Compares current version vs latest version
   - If latest > current: Show update notification
   - If latest <= current: Do nothing (you're up to date)

4. **Show Notification**: If update available, prints a friendly message
   - Shows current and latest version numbers
   - Provides update command: `pip install --upgrade batplot`
   - Can be disabled with environment variable

DESIGN PRINCIPLES:
-----------------
- **Non-blocking**: 2 second timeout (won't slow down startup)
- **Cached**: Only checks once per hour (saves network requests)
- **Silent failure**: If check fails, program continues normally
- **Optional**: Can be disabled with BATPLOT_NO_VERSION_CHECK=1
- **User-friendly**: Clear, colored notification message

WHY CACHE?
---------
Checking PyPI on every run would:
- Slow down startup (network latency)
- Waste bandwidth (unnecessary requests)
- Annoy PyPI servers (too many requests)

Caching for 1 hour means:
- Fast startup (no network request if cache is fresh)
- Still timely (checks once per hour, not once per day)
- Respectful to PyPI (fewer requests)
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, Tuple

# ====================================================================================
# UPDATE INFO CONFIGURATION
# ====================================================================================
# Edit this section to customize update notification messages and add update info.
# 
# HOW TO USE:
# ----------
# When releasing a new version, edit the UPDATE_INFO dictionary below to include
# information about what's new or important in the update. This information will
# be displayed to users when they run batplot and a newer version is available.
#
# EXAMPLE:
# --------
# UPDATE_INFO = {
#     'custom_message': "This update includes important bug fixes and new features.",
#     'update_notes': [
#         "- Fixed colormap preservation issue in session files",
#         "- Improved legend positioning when toggling visibility",
#         "- Added superscript/subscript shortcuts for labels",
#         "- Enhanced version check notifications"
#     ],
#     'show_update_notes': True,
# }
#
# To disable custom messages, set 'custom_message' to None.
# To disable update notes, set 'update_notes' to None or an empty list [].
# ====================================================================================

UPDATE_INFO = {
    # Custom message to include in update notification
    # Set to None or empty string to disable
    # This will be displayed as an additional line in the update message box
    'custom_message': "This update includes important bug fixes",  # Example: "This update includes important bug fixes."
    
    # Additional notes about the update (list of strings)
    # Set to None or empty list [] to disable
    # Each item in the list will be displayed as a separate line
    'update_notes': None,  # Example: ["- Fixed colormap preservation issue", "- Improved legend positioning"]
    
    # Whether to show update notes if provided
    # Set to False to hide update notes even if they are defined
    'show_update_notes': True,
}

# ====================================================================================
# END OF UPDATE INFO CONFIGURATION
# ====================================================================================


def get_cache_file() -> Path:
    """Get the path to the version check cache file."""
    # Use user's cache directory
    if sys.platform == 'win32':
        cache_dir = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'batplot'
    elif sys.platform == 'darwin':
        cache_dir = Path.home() / 'Library' / 'Caches' / 'batplot'
    else:  # Linux and other Unix-like
        cache_dir = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'batplot'
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / 'version_check.json'


def get_latest_version() -> Optional[str]:
    """Fetch the latest version from PyPI.
    
    Returns:
        Latest version string, or None if check fails
    """
    try:
        import urllib.request
        import urllib.error
        
        # Set a short timeout to avoid blocking
        url = "https://pypi.org/pypi/batplot/json"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())
            return data['info']['version']
    except Exception:
        # Silently fail - don't interrupt user's work
        return None


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse version string into tuple of integers for comparison.
    
    Args:
        version_str: Version string like "1.4.8"
        
    Returns:
        Tuple of integers like (1, 4, 8)
    """
    try:
        return tuple(int(x) for x in version_str.split('.'))
    except Exception:
        return (0,)


def check_for_updates(current_version: str, force: bool = False) -> None:
    """Check if a newer version is available and notify user.
    
    Args:
        current_version: Current installed version
        force: If True, ignore cache and always check
    """
    # Allow disabling version check via environment variable
    if os.environ.get('BATPLOT_NO_VERSION_CHECK', '').lower() in ('1', 'true', 'yes'):
        return
    
    cache_file = get_cache_file()
    now = time.time()
    
    # Check cache unless forced
    if not force and cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
                # Check once per hour (3600 seconds)
                if now - cache.get('timestamp', 0) < 3600:
                    # Use cached result
                    latest = cache.get('latest_version')
                    if latest and parse_version(latest) > parse_version(current_version):
                        _print_update_message(current_version, latest)
                    return
        except Exception:
            # Cache read failed, continue to check
            pass
    
    # Fetch latest version from PyPI
    latest = get_latest_version()
    
    # Update cache
    try:
        with open(cache_file, 'w') as f:
            json.dump({
                'timestamp': now,
                'latest_version': latest,
                'current_version': current_version
            }, f)
    except Exception:
        # Cache write failed, not critical
        pass
    
    # Notify user if newer version available
    if latest and parse_version(latest) > parse_version(current_version):
        _print_update_message(current_version, latest)


def _print_update_message(current: str, latest: str) -> None:
    """Print update notification message.
    
    Args:
        current: Current version
        latest: Latest available version
    """
    # Calculate box width (minimum 68, expand if needed for longer messages)
    box_width = 68
    custom_msg = UPDATE_INFO.get('custom_message')
    update_notes = UPDATE_INFO.get('update_notes')
    show_notes = UPDATE_INFO.get('show_update_notes', True)
    
    # Calculate required width based on content
    max_line_len = 68  # Default minimum width
    if custom_msg:
        max_line_len = max(max_line_len, len(custom_msg) + 4)
    if update_notes and show_notes:
        for note in update_notes:
            max_line_len = max(max_line_len, len(note) + 4)
    # Ensure box width is at least the calculated width
    box_width = max(68, min(max_line_len, 100))  # Cap at 100 for readability
    
    print(f"\n\033[93m╭{'─' * box_width}╮\033[0m")
    print(f"\033[93m│\033[0m  \033[1mA new version of batplot is available!\033[0m" + " " * max(0, box_width - 34) + "\033[93m│\033[0m")
    print(f"\033[93m│\033[0m  Current: \033[91m{current}\033[0m → Latest: \033[92m{latest}\033[0m" + " " * max(0, box_width - 20 - len(current) - len(latest)) + "\033[93m│\033[0m")
    
    # Add custom message if provided
    if custom_msg and custom_msg.strip():
        # Truncate if too long to fit in box
        msg = custom_msg[:box_width - 6] if len(custom_msg) > box_width - 6 else custom_msg
        print(f"\033[93m│\033[0m  {msg}" + " " * max(0, box_width - len(msg) - 4) + "\033[93m│\033[0m")
    
    # Add update notes if provided
    if update_notes and show_notes and isinstance(update_notes, list):
        for note in update_notes:
            if note and note.strip():
                # Truncate if too long to fit in box
                note_text = note[:box_width - 6] if len(note) > box_width - 6 else note
                print(f"\033[93m│\033[0m  {note_text}" + " " * max(0, box_width - len(note_text) - 4) + "\033[93m│\033[0m")
    
    print(f"\033[93m│\033[0m  Update with: \033[96mpip install --upgrade batplot\033[0m" + " " * max(0, box_width - 34) + "\033[93m│\033[0m")
    print(f"\033[93m│\033[0m  To disable this check: \033[96mexport BATPLOT_NO_VERSION_CHECK=1\033[0m" + " " * max(0, box_width - 45) + "\033[93m│\033[0m")
    print(f"\033[93m╰{'─' * box_width}╯\033[0m\n")


if __name__ == '__main__':
    # Test the version checker
    from batplot import __version__
    check_for_updates(__version__, force=True)
