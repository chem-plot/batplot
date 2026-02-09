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
# (Auto-filled from RELEASE_NOTES.txt when using batplot --dev-upgrade)
UPDATE_INFO = {
    # Custom message to include in update notification
    # (Auto-filled from RELEASE_NOTES.txt when using batplot --dev-upgrade)
    'custom_message': '- Add support for BatX GC plot',
    # Additional notes (auto-filled from RELEASE_NOTES.txt)
    'update_notes': [
        '- Add support for BatX GC plot'
    ],
    'show_update_notes': True,
}

# ====================================================================================
# END OF UPDATE INFO CONFIGURATION
# ====================================================================================
# URL for release notes of the latest version (so old installs can show "what's new").
# Updated by batplot --dev-upgrade; commit and push so users see notes.
LATEST_RELEASE_NOTES_URL = "https://raw.githubusercontent.com/TianDai1729/batplot/main/batplot/data/latest_release_notes.json"


def _fetch_latest_release_notes(latest_version: str) -> Optional[dict]:
    """Fetch release notes for the given version from the project URL.
    Returns dict with 'version' and 'update_notes' (list of str), or None on failure.
    """
    try:
        import urllib.request
        with urllib.request.urlopen(LATEST_RELEASE_NOTES_URL, timeout=3) as response:
            data = json.loads(response.read().decode())
            if isinstance(data, dict) and data.get('version') == latest_version:
                notes = data.get('update_notes')
                if isinstance(notes, list):
                    return data
    except Exception:
        pass
    return None


def _read_changelog_from_package() -> Optional[str]:
    """Read full changelog from the file shipped with the package (batplot/data/CHANGELOG.md).
    No network access. Returns None if file not found."""
    try:
        p = Path(__file__).resolve().parent / "data" / "CHANGELOG.md"
        if p.exists():
            return p.read_text(encoding='utf-8', errors='replace')
    except Exception:
        pass
    return None


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


def get_all_versions_from_pypi() -> Optional[list]:
    """Fetch all released versions from PyPI (sorted ascending).
    
    Returns:
        List of version strings, or None if check fails
    """
    try:
        import urllib.request
        url = "https://pypi.org/pypi/batplot/json"
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode())
            versions = list(data.get('releases', {}).keys())
            versions.sort(key=lambda v: parse_version(v))
            return versions
    except Exception:
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
                        _print_update_message(current_version, latest, 0)  # count unknown when from cache
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
        all_vers = get_all_versions_from_pypi()
        versions_behind = 0
        if all_vers:
            try:
                cur_tup = parse_version(current_version)
                lat_tup = parse_version(latest)
                versions_behind = sum(1 for v in all_vers if cur_tup < parse_version(v) <= lat_tup)
            except Exception:
                pass
        _print_update_message(current_version, latest, versions_behind)


def _print_update_message(current: str, latest: str, versions_behind: int = 0) -> None:
    """Print update notification message.
    
    Args:
        current: Current version
        latest: Latest available version
        versions_behind: Number of versions between current and latest (0 if unknown)
    """
    # Prefer release notes for this latest version from URL (so old installs show what's new)
    fetched = _fetch_latest_release_notes(latest)
    if fetched and fetched.get('update_notes'):
        custom_msg = (fetched.get('custom_message') or (fetched['update_notes'][0] if fetched['update_notes'] else '')) or None
        update_notes = fetched['update_notes']
        show_notes = True
    else:
        custom_msg = UPDATE_INFO.get('custom_message')
        update_notes = UPDATE_INFO.get('update_notes')
        show_notes = UPDATE_INFO.get('show_update_notes', True)
    
    # Calculate box width (minimum 68, expand if needed for longer messages)
    box_width = 68
    
    # Calculate required width based on content
    max_line_len = 68  # Default minimum width
    if custom_msg:
        max_line_len = max(max_line_len, len(custom_msg) + 4)
    if update_notes and show_notes:
        for note in update_notes:
            max_line_len = max(max_line_len, len(note) + 4)
    # Account for "Press 'v'..." and "(X versions behind..." lines
    max_line_len = max(max_line_len, 52, 48)
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
    if versions_behind > 1:
        print(f"\033[93m│\033[0m  \033[1m({versions_behind} versions behind — press 'v' for full release notes)\033[0m" + " " * max(0, box_width - 48) + "\033[93m│\033[0m")
    else:
        print(f"\033[93m│\033[0m  \033[1mPress 'v' for full release notes, or Enter to continue\033[0m" + " " * max(0, box_width - 48) + "\033[93m│\033[0m")
    print(f"\033[93m│\033[0m  To disable this check: \033[96mexport BATPLOT_NO_VERSION_CHECK=1\033[0m" + " " * max(0, box_width - 45) + "\033[93m│\033[0m")
    print(f"\033[93m╰{'─' * box_width}╯\033[0m\n")
    
    # Prompt for 'v' to show full changelog
    try:
        choice = input("\033[93m  [v] Release notes  [Enter] Continue: \033[0m").strip().lower()
        if choice == 'v':
            changelog = _read_changelog_from_package()
            if changelog:
                print("\n\033[1m--- Full release notes (CHANGELOG) ---\033[0m\n")
                print(changelog)
                print("\033[1m--- End of release notes ---\033[0m\n")
            else:
                print("\033[91m  Could not load release notes (changelog not included in this build).\033[0m\n")
    except (KeyboardInterrupt, EOFError):
        print()
        pass


if __name__ == '__main__':
    # Test the version checker
    from batplot import __version__
    check_for_updates(__version__, force=True)
