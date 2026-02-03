"""Shared helpers for color previews and user-defined color management.

COLOR PALETTE SYSTEM OVERVIEW:
==============================
This module manages how colors are assigned to multiple curves/lines in batplot plots.

HOW COLOR PALETTES WORK:
------------------------
When you have many curves (e.g., 100 files in XY mode, or 50 cycles in EC mode), you want
each one to have a different color that smoothly transitions across a color palette.

Example: Using 'viridis' palette with 5 curves:
    Curve 1 → Dark purple (start of viridis)
    Curve 2 → Blue-purple
    Curve 3 → Green
    Curve 4 → Yellow-green
    Curve 5 → Bright yellow (end of viridis)

The system works by:
1. Getting a continuous colormap (e.g., 'viridis')
2. Sampling colors at evenly spaced points along the colormap
3. Assigning each sampled color to a different curve

For 100 curves, we sample 100 evenly spaced points from the colormap, ensuring each
curve gets a unique, smoothly varying color.

COLORMAP SOURCES:
----------------
1. Matplotlib built-in: 'viridis', 'plasma', 'inferno', 'magma', etc.
2. cmcrameri scientific colormaps: 'batlow', 'batlowk', 'batloww' (if installed)
3. Custom colormaps: Defined in _CUSTOM_CMAPS dictionary below

REVERSED COLORMAPS:
------------------
Colormaps can be reversed by adding '_r' suffix:
    'viridis' → normal (dark to bright)
    'viridis_r' → reversed (bright to dark)

This is useful when you want the color order flipped.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.colors import LinearSegmentedColormap

from .config import get_user_colors as _cfg_get_user_colors
from .config import save_user_colors as _cfg_save_user_colors

# ====================================================================================
# CUSTOM COLORMAP DEFINITIONS
# ====================================================================================
# These are custom color palettes designed for scientific visualization.
# Each colormap is defined as a list of hex color codes that smoothly transition
# from one color to the next.
#
# Format: List of hex color strings, ordered from start to end of colormap
# Example: ['#02121d', '#053061', ...] means start with very dark blue, end with light yellow
#
# These colormaps are registered with matplotlib so they can be used like built-in ones.
# ====================================================================================
_CUSTOM_CMAPS = {
    # 'batlow' - Scientific colormap optimized for colorblind accessibility
    # Colors transition: dark blue → teal → green → yellow
    'batlow': ['#02121d', '#053061', '#2b7a8b', '#7cbf7b', '#c7e6a2', '#f9f0c3'],
    
    # 'batlowk' - Variant with more purple tones
    # Colors transition: dark purple → purple → brown → yellow
    'batlowk': ['#150b2d', '#3d2e63', '#5f4f85', '#81718f', '#a6938e', '#cbb58f', '#efd78d'],
    
    # 'batloww' - Variant with more blue-green tones
    # Colors transition: dark blue → blue → teal → green → yellow
    'batloww': ['#0a1427', '#17385d', '#295f8d', '#4f8fa3', '#7db7a1', '#b2d39a', '#e3e6a8'],
}


def ensure_colormap(name: Optional[str]) -> bool:
    """
    Ensure that a named colormap exists and is registered with matplotlib.
    
    HOW IT WORKS:
    ------------
    This function checks if a colormap is available, and if not, tries to register it.
    It searches in this order:
    1. Built-in matplotlib colormaps (viridis, plasma, etc.)
    2. cmcrameri scientific colormaps (if package is installed)
    3. Custom colormaps defined in _CUSTOM_CMAPS
    4. Any other matplotlib-compatible colormap
    
    WHY THIS IS NEEDED:
    -------------------
    Different colormap sources need to be registered with matplotlib before they can
    be used. This function ensures the colormap is available regardless of its source.
    
    Args:
        name: Colormap name (e.g., 'viridis', 'batlow', 'viridis_r')
              '_r' suffix indicates reversed colormap
    
    Returns:
        True if colormap exists and is registered, False otherwise
    """
    if not name:
        return False
    
    # Handle reversed colormaps (remove '_r' suffix to get base name)
    # Example: 'viridis_r' → base = 'viridis', we'll reverse it later if needed
    base = name[:-2] if name.lower().endswith('_r') else name
    base_lower = base.lower()
    
    # STEP 1: Check if it's already a registered matplotlib colormap
    if base_lower in plt.colormaps():
        return True
    
    # STEP 2: Try to load from cmcrameri package (scientific colormaps)
    # cmcrameri is an optional package with colorblind-friendly colormaps
    try:
        import cmcrameri.cm as cmc
        if hasattr(cmc, base_lower):
            cmap_obj = getattr(cmc, base_lower)
            try:
                # Register it with matplotlib so it can be used like built-in colormaps
                plt.register_cmap(name=base_lower, cmap=cmap_obj)
            except ValueError:
                # Already registered, that's fine
                pass
            return True
    except Exception:
        # cmcrameri not installed or colormap not found, continue to next step
        pass
    
    # STEP 3: Check if it's a custom colormap defined in this module
    custom = _CUSTOM_CMAPS.get(base_lower)
    if custom:
        try:
            # Create a LinearSegmentedColormap from the list of colors
            # N=256 means create 256 intermediate colors by interpolating between the given colors
            # This creates a smooth gradient
            cmap_obj = LinearSegmentedColormap.from_list(base_lower, custom, N=256)
            try:
                # Register with matplotlib
                plt.register_cmap(name=base_lower, cmap=cmap_obj)
            except ValueError:
                # Already registered, that's fine
                pass
            return True
        except Exception:
            return False
    
    # STEP 4: Final fallback - try to get it directly from matplotlib
    # This handles any other matplotlib-compatible colormap
    try:
        plt.get_cmap(base_lower)
        return True
    except Exception:
        return False


def _ansi_color_block_from_rgba(rgba) -> str:
    """Return a two-space block with the given RGBA color."""
    try:
        r, g, b, _ = rgba
        r_i = max(0, min(255, int(round(r * 255))))
        g_i = max(0, min(255, int(round(g * 255))))
        b_i = max(0, min(255, int(round(b * 255))))
        return f"\033[48;2;{r_i};{g_i};{b_i}m  \033[0m"
    except Exception:
        return "[??]"


def color_block(color: Optional[str]) -> str:
    """Return a colored block (ANSI) for the supplied color string."""
    if not color:
        return "[--]"
    try:
        rgba = mcolors.to_rgba(color)
        return _ansi_color_block_from_rgba(rgba)
    except Exception:
        return "[??]"


def color_bar(colors: Sequence[str]) -> str:
    """Return a string of adjacent color blocks."""
    blocks = [color_block(col) for col in colors if col]
    return " ".join(blocks)


def palette_preview(name: str, steps: int = 8) -> str:
    """
    Return a visual preview of a colormap as colored blocks in the terminal.
    
    HOW IT WORKS:
    ------------
    This function samples colors from a colormap at evenly spaced intervals and
    displays them as colored blocks. This lets users see what the colormap looks
    like before applying it to their data.
    
    Example output for 'viridis' with 8 steps:
        [dark purple block] [purple block] [blue block] [green block] [yellow block] ...
    
    SAMPLING METHOD:
    ---------------
    For a colormap with N steps:
    - Step 0: Sample at position 0.0 (start of colormap)
    - Step 1: Sample at position 1/(N-1)
    - Step 2: Sample at position 2/(N-1)
    - ...
    - Step N-1: Sample at position 1.0 (end of colormap)
    
    This gives evenly distributed colors across the entire colormap range.
    
    Args:
        name: Colormap name (e.g., 'viridis', 'plasma', 'batlow')
        steps: Number of color samples to show (default 8)
               More steps = more detailed preview but longer output
    
    Returns:
        String of ANSI color codes that display as colored blocks in terminal
        Empty string if colormap not found
    """
    # Ensure colormap is registered
    ensure_colormap(name)
    
    # Try to get the colormap from matplotlib
    try:
        cmap = plt.get_cmap(name)
    except Exception:
        cmap = None
        # Fallback: try cmcrameri if it's a batlow variant
        lower = name.lower()
        if lower.startswith('batlow'):
            try:
                import cmcrameri.cm as cmc
                if hasattr(cmc, lower):
                    cmap = getattr(cmc, lower)
                elif hasattr(cmc, 'batlow'):
                    cmap = getattr(cmc, 'batlow')
            except Exception:
                return ""
        else:
            return ""
    
    # Ensure steps is at least 1 (avoid division by zero)
    if steps < 1:
        steps = 1
    
    # Special handling for tab10 to use hardcoded colors (matching EC and CPC interactive)
    if name.lower() == 'tab10':
        default_tab10_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                               '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        # Use first 'steps' colors from tab10
        samples = [default_tab10_colors[i % len(default_tab10_colors)] for i in range(steps)]
    else:
        # Sample colors at evenly spaced positions along the colormap
        # Position ranges from 0.0 (start) to 1.0 (end)
        samples = [
            mcolors.to_hex(cmap(i / max(steps - 1, 1)))  # Convert to hex color code
            for i in range(steps)
        ]
    
    # Convert color codes to visual blocks and return as string
    return color_bar(samples)


def _set_cached_colors(fig, colors: List[str]):
    """
    Store user colors in figure object for fast access (caching).
    
    HOW CACHING WORKS:
    -----------------
    Instead of reading from disk every time, we store colors in the figure object.
    This is faster because:
    - Reading from disk is slow (file I/O)
    - Figure object is already in memory (fast access)
    
    WHY STORE IN FIGURE OBJECT?
    ---------------------------
    The figure object persists throughout the interactive session, so we can
    cache colors there. This avoids repeated file reads.
    
    Args:
        fig: Matplotlib figure object (where we store the cache)
        colors: List of color codes to cache
    """
    if fig is not None:
        # setattr() dynamically adds an attribute to an object
        # This is like: fig._user_colors_cache = list(colors)
        # We use list() to create a copy (not a reference to original list)
        setattr(fig, '_user_colors_cache', list(colors))


def get_user_color_list(fig=None) -> List[str]:
    """
    Return cached user colors (persisted to ~/.batplot).
    
    HOW IT WORKS:
    ------------
    1. First check if colors are cached in figure object (fast path)
    2. If not cached, load from disk (~/.batplot/config.json)
    3. Cache the loaded colors in figure object for next time
    4. Return the color list
    
    WHY CACHING?
    -----------
    - Fast: Memory access is much faster than disk I/O
    - Efficient: Only reads from disk once per session
    - Persistent: Colors are saved to disk, so they persist between sessions
    
    Args:
        fig: Matplotlib figure object (optional, for caching)
    
    Returns:
        List of color codes (hex strings like '#FF0000' or named colors like 'red')
    """
    # Check if colors are already cached in figure object
    if fig is not None and hasattr(fig, '_user_colors_cache'):
        # Return cached colors (fast path - no disk access)
        # list() creates a copy so caller can't modify the cached version
        return list(getattr(fig, '_user_colors_cache'))
    
    # Not cached - load from disk
    colors = list(_cfg_get_user_colors())
    # Cache for next time
    _set_cached_colors(fig, colors)
    return colors


def _save_user_colors(colors: List[str], fig=None) -> List[str]:
    """
    Save user colors to disk and cache, removing duplicates and empty entries.
    
    HOW IT WORKS:
    ------------
    1. Remove empty/None colors (filter out invalid entries)
    2. Remove duplicates (keep only first occurrence of each color)
    3. Save cleaned list to disk (~/.batplot/config.json)
    4. Update cache in figure object
    5. Return cleaned list
    
    WHY CLEAN THE LIST?
    ------------------
    - Empty strings would cause errors when trying to use them as colors
    - Duplicates waste space and confuse users
    - Clean data = better user experience
    
    Args:
        colors: List of color codes (may contain duplicates or empty strings)
        fig: Matplotlib figure object (optional, for caching)
    
    Returns:
        Cleaned list (no duplicates, no empty entries)
    """
    cleaned: List[str] = []  # Type annotation: cleaned is a list of strings
    for col in colors:
        # Skip empty/None colors
        if not col:
            continue
        # Only add if not already in cleaned list (removes duplicates)
        if col not in cleaned:
            cleaned.append(col)
    # Save to disk (persists between sessions)
    _cfg_save_user_colors(cleaned)
    # Update cache (fast access for current session)
    _set_cached_colors(fig, cleaned)
    return cleaned


def add_user_color(color: str, fig=None) -> List[str]:
    """Append a user color (if not already present)."""
    colors = get_user_color_list(fig)
    if color and color not in colors:
        colors.append(color)
        colors = _save_user_colors(colors, fig)
    return colors


def remove_user_color(index: int, fig=None) -> List[str]:
    """Remove a user color by 0-based index."""
    colors = get_user_color_list(fig)
    if 0 <= index < len(colors):
        colors.pop(index)
        colors = _save_user_colors(colors, fig)
    return colors


def clear_user_colors(fig=None) -> None:
    _save_user_colors([], fig)


def resolve_color_token(token: str, fig=None) -> str:
    """
    Translate color references like '2' or 'u3' into actual color codes.
    
    HOW IT WORKS:
    ------------
    Users can reference saved colors in two ways:
    1. By number: '2' means the 2nd saved color (1-based indexing)
    2. By 'u' prefix: 'u3' means the 3rd saved color (1-based indexing)
    
    Examples:
        '2' → Returns colors[1] (2nd color, but 0-based index is 1)
        'u3' → Returns colors[2] (3rd color, but 0-based index is 2)
        'red' → Returns 'red' (not a reference, so return as-is)
        '#FF0000' → Returns '#FF0000' (not a reference, so return as-is)
    
    WHY TWO FORMATS?
    ---------------
    - '2' is shorter and easier to type
    - 'u3' is more explicit (clearly indicates user color)
    - Both are 1-based (user-friendly) but converted to 0-based (Python indexing)
    
    Args:
        token: Color reference string (e.g., '2', 'u3', 'red', '#FF0000')
        fig: Matplotlib figure object (optional, for accessing cached colors)
    
    Returns:
        Actual color code (hex string or named color), or original token if not a reference
    """
    # Empty token - return as-is
    if not token:
        return token
    
    # Remove whitespace
    stripped = token.strip()
    idx = None  # Will hold the 0-based index if token is a reference
    
    # Check if token is 'u' prefix format (e.g., 'u3')
    # stripped[1:] gets everything after the first character
    # .isdigit() checks if it's all digits
    if stripped.lower().startswith('u') and stripped[1:].isdigit():
        # Convert 'u3' → index 2 (3rd color, but 0-based)
        idx = int(stripped[1:]) - 1
    # Check if token is just a number (e.g., '2')
    elif stripped.isdigit():
        # Convert '2' → index 1 (2nd color, but 0-based)
        idx = int(stripped) - 1
    
    # If we found a valid index, look up the color
    if idx is not None:
        colors = get_user_color_list(fig)
        # Check if index is valid (within bounds of color list)
        if 0 <= idx < len(colors):
            return colors[idx]  # Return the actual color code
    
    # Not a reference, or invalid index - return token as-is
    return token


def print_user_colors(fig=None) -> None:
    """Print saved colors with indices and color blocks."""
    colors = get_user_color_list(fig)
    if not colors:
        print("No saved user colors.")
        return
    print("Saved colors:")
    for idx, color in enumerate(colors, 1):
        print(f"  {idx}: {color_block(color)} {color}")


def manage_user_colors(fig=None) -> None:
    """Interactive submenu for editing user-defined colors."""
    while True:
        colors = get_user_color_list(fig)
        print("\n\033[1mUser color list:\033[0m")
        if colors:
            for idx, color in enumerate(colors, 1):
                print(f"  {idx}: {color_block(color)} {color}")
        else:
            print("  (empty)")
        print("Options: a=add colors, d=delete numbers, c=clear, q=back")
        choice = input("User colors> ").strip().lower()
        if not choice:
            continue
        if choice == 'q':
            break
        if choice == 'a':
            line = input("Enter colors (space-separated names/hex codes) or q: ").strip()
            if not line or line.lower() == 'q':
                continue
            # List comprehension: splits line by spaces, keeps only non-empty tokens
            # Example: "red blue #FF0000" → ['red', 'blue', '#FF0000']
            # The 'if tok' part filters out empty strings (from multiple spaces)
            new_colors = [tok for tok in line.split() if tok]
            if new_colors:
                colors = get_user_color_list(fig)
                added = 0
                for col in new_colors:
                    if col not in colors:
                        colors.append(col)
                        added += 1
                _save_user_colors(colors, fig)
                print(f"Added {added} color(s).")
            continue
        if choice == 'd':
            if not colors:
                print("No colors to delete.")
                continue
            line = input("Enter number(s) to delete (e.g., 1 or 1,3,5): ").strip()
            if not line:
                continue
            tokens = line.replace(',', ' ').split()
            indices = []
            for tok in tokens:
                if tok.isdigit():
                    idx = int(tok) - 1
                    if 0 <= idx < len(colors):
                        indices.append(idx)
                    else:
                        print(f"Index out of range: {tok}")
                else:
                    print(f"Invalid entry: {tok}")
            if indices:
                # Sort indices in reverse order (largest first)
                # WHY? When deleting multiple items, we must delete from end to start.
                # If we delete index 1 first, then index 3 becomes index 2, and we'd delete the wrong item!
                # Example: colors = ['red', 'blue', 'green', 'yellow']
                #          Delete indices [1, 3] (blue and yellow)
                #          If we delete 1 first: ['red', 'green', 'yellow'] (index 3 is now out of bounds!)
                #          If we delete 3 first: ['red', 'blue', 'green'] (then delete 1: ['red', 'green'] ✓)
                for idx in sorted(indices, reverse=True):
                    colors.pop(idx)  # Remove color at this index
                _save_user_colors(colors, fig)
                print("Updated color list.")
            continue
        if choice == 'c':
            confirm = input("Clear all saved colors? (y/n): ").strip().lower()
            if confirm == 'y':
                clear_user_colors(fig)
                print("Cleared saved colors.")
            continue
        print("Unknown option.")


__all__ = [
    'add_user_color',
    'clear_user_colors',
    'color_bar',
    'color_block',
    'manage_user_colors',
    'palette_preview',
    'print_user_colors',
    'remove_user_color',
    'resolve_color_token',
    'get_user_color_list',
]
