"""Version checking utility for batplot.

Checks PyPI for newer versions and notifies users.
Caches the check result to avoid excessive API calls.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, Tuple


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
                # Check once per day (86400 seconds)
                if now - cache.get('timestamp', 0) < 86400:
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
    print(f"\n\033[93m╭{'─' * 68}╮\033[0m")
    print(f"\033[93m│\033[0m  \033[1mA new version of batplot is available!\033[0m" + " " * 31 + "\033[93m│\033[0m")
    print(f"\033[93m│\033[0m  Current: \033[91m{current}\033[0m → Latest: \033[92m{latest}\033[0m" + " " * (42 - len(current) - len(latest)) + "\033[93m│\033[0m")
    print(f"\033[93m│\033[0m  Update with: \033[96mpip install --upgrade batplot\033[0m" + " " * 20 + "\033[93m│\033[0m")
    print(f"\033[93m│\033[0m  To disable this check: \033[96mexport BATPLOT_NO_VERSION_CHECK=1\033[0m" + " " * 7 + "\033[93m│\033[0m")
    print(f"\033[93m╰{'─' * 68}╯\033[0m\n")


if __name__ == '__main__':
    # Test the version checker
    from batplot import __version__
    check_for_updates(__version__, force=True)
