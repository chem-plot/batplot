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

from typing import List, Optional, Sequence, cast

import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib import colors as mcolors  # type: ignore[import]
from matplotlib.colors import LinearSegmentedColormap, Colormap  # type: ignore[import]

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

    def _register_cmap_safe(cmap_name: str, cmap_obj) -> bool:
        """Register cmap across matplotlib API variants."""
        # matplotlib >= 3.5 style registry API
        try:
            reg = getattr(plt, "colormaps", None)
            if reg is not None and hasattr(reg, "register"):
                try:
                    reg.register(cmap_obj, name=cmap_name, force=True)
                except TypeError:
                    # Older signature may not support force kwarg
                    reg.register(cmap_obj, name=cmap_name)
                return True
        except Exception:
            pass
        # Older pyplot API fallback
        try:
            if hasattr(plt, "register_cmap"):
                plt.register_cmap(name=cmap_name, cmap=cmap_obj)
                return True
        except ValueError:
            # Already registered
            return True
        except Exception:
            pass
        # As a last resort, accept cmap object usability even if registration fails.
        try:
            _ = cmap_obj(0.5)
            return True
        except Exception:
            return False
    
    # Handle reversed colormaps (remove '_r' suffix to get base name)
    # Example: 'viridis_r' → base = 'viridis', we'll reverse it later if needed
    base = name[:-2] if name.lower().endswith('_r') else name
    base_lower = base.lower()
    
    # STEP 1: Check if it's already a registered matplotlib colormap.
    # Matplotlib colormap names are case-sensitive (e.g. 'Set2', 'Dark2'),
    # so check the exact name first, then the lowercase variant.
    try:
        registered = plt.colormaps()
        if base in registered or base_lower in registered:
            return True
        # Case-insensitive match: user typed 'set2' for registered 'Set2'.
        if base_lower in {n.lower() for n in registered}:
            return True
    except Exception:
        pass
    
    # STEP 2: Try to load from cmcrameri package (scientific colormaps)
    # cmcrameri is an optional package with colorblind-friendly colormaps
    try:
        import cmcrameri.cm as cmc
        if hasattr(cmc, base_lower):
            cmap_obj = getattr(cmc, base_lower)
            return _register_cmap_safe(base_lower, cmap_obj)
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
            return _register_cmap_safe(base_lower, cmap_obj)
        except Exception:
            return False
    
    # STEP 4: Final fallback - try to get it directly from matplotlib
    # This handles any other matplotlib-compatible colormap (case-sensitive
    # names like 'Set2' first, then the lowercase variant).
    try:
        from matplotlib import colormaps as mpl_colormaps

        for cand in (base, base_lower):
            try:
                _ = mpl_colormaps[cand]
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def get_colormap(name: Optional[str]) -> Optional[Colormap]:
    """Return a Colormap by name across matplotlib versions and custom maps.

    Prefer this over ``matplotlib.cm.get_cmap`` — that API was removed in
    matplotlib 3.11, which broke palette commands such as ``all viridis`` on
    Windows installs with newer matplotlib.
    """
    if not name:
        return None

    ensure_colormap(name)

    candidates: List[str] = []
    for candidate in (name, name.lower()):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    # Canonicalize case: matplotlib names are case-sensitive ('Set2'), so map
    # e.g. 'set2' → 'Set2' and 'set2_r' → 'Set2_r'.
    try:
        lower_map = {n.lower(): n for n in plt.colormaps()}
        canon = lower_map.get(name.lower())
        if canon and canon not in candidates:
            candidates.append(canon)
        if name.lower().endswith("_r"):
            canon_base = lower_map.get(name.lower()[:-2])
            if canon_base and f"{canon_base}_r" not in candidates:
                candidates.append(f"{canon_base}_r")
    except Exception:
        pass

    try:
        from matplotlib import colormaps as mpl_colormaps

        registry_get = getattr(mpl_colormaps, "get_cmap", None)
        if callable(registry_get):
            for candidate in candidates:
                try:
                    return cast(Colormap, registry_get(candidate))
                except Exception:
                    pass
        for candidate in candidates:
            try:
                return mpl_colormaps[candidate]
            except Exception:
                pass
    except Exception:
        pass

    for candidate in candidates:
        try:
            return plt.get_cmap(candidate)
        except Exception:
            pass

    reversed_flag = name.lower().endswith("_r")
    base = name[:-2] if reversed_flag else name
    base_lower = base.lower()

    custom = _CUSTOM_CMAPS.get(base_lower)
    if custom:
        try:
            cmap_obj = LinearSegmentedColormap.from_list(base_lower, custom, N=256)
            if reversed_flag:
                cmap_obj = cmap_obj.reversed()
            return cmap_obj
        except Exception:
            pass

    if base_lower.startswith("batlow"):
        try:
            import cmcrameri.cm as cmc  # type: ignore[import]

            cmap_obj = getattr(cmc, base_lower, None) or getattr(cmc, "batlow", None)
            if cmap_obj is not None:
                if reversed_flag and hasattr(cmap_obj, "reversed"):
                    return cmap_obj.reversed()
                return cmap_obj
        except Exception:
            pass

    return None


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


def to_display_hex(color) -> Optional[str]:
    """Normalize any matplotlib-accepted color to lowercase ``#rrggbb`` (no alpha)."""
    if color is None:
        return None
    try:
        return str(mcolors.to_hex(mcolors.to_rgba(color), keep_alpha=False)).lower()
    except Exception:
        return None


def color_block(color: Optional[str]) -> str:
    """Return a colored block (ANSI) for the supplied color string."""
    if not color:
        return "[--]"
    try:
        rgba = mcolors.to_rgba(color)
        return _ansi_color_block_from_rgba(rgba)
    except Exception:
        return "[??]"


def format_color_listing(color) -> str:
    """Return ``<swatch> <hex>`` for menu listings (curves, saved colors, etc.).

    Always prefers a hex code next to the ANSI color cube so every mode shows
    the same readable form (e.g. ``██ #1f77b4``), including named colors,
    ``C0`` cycle colors, and RGBA tuples from matplotlib artists.
    """
    if color is None:
        return f"{color_block(None)} --"
    hex_code = to_display_hex(color)
    if hex_code is None:
        text = str(color).strip()
        if not text:
            return f"{color_block(None)} --"
        return f"{color_block(None)} {text}"
    return f"{color_block(hex_code)} {hex_code}"


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
    cmap: Optional[Colormap] = get_colormap(name)

    # If we still don't have a colormap, bail out
    if cmap is None:
        return ""
    
    # Ensure steps is at least 1 (avoid division by zero)
    if steps < 1:
        steps = 1

    # Special handling for tab10 to use hardcoded colors (matching EC and CPC interactive)
    if name.lower() == 'tab10':
        default_tab10_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                               '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        samples = [default_tab10_colors[i % len(default_tab10_colors)] for i in range(steps)]
    else:
        # Sample colors at evenly spaced positions along the colormap
        samples = [
            mcolors.to_hex(cmap(i / max(steps - 1, 1)))
            for i in range(steps)
        ]

    # Use foreground-colored █ characters so the bar is visible on any terminal background
    result = ""
    for hex_color in samples:
        try:
            r, g, b, _ = mcolors.to_rgba(hex_color)
            r_i = max(0, min(255, int(round(r * 255))))
            g_i = max(0, min(255, int(round(g * 255))))
            b_i = max(0, min(255, int(round(b * 255))))
            result += f"\033[38;2;{r_i};{g_i};{b_i}m██\033[0m"
        except Exception:
            result += "??"
    return result


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
    Return user colors from ``~/.batplot/config.json`` (source of truth).

    Always reloads from disk so multiple figures (batch panels) and the
    eyedropper stay in sync. Optionally refreshes ``fig._user_colors_cache``.
    """
    colors = list(_cfg_get_user_colors())
    _set_cached_colors(fig, colors)
    return colors


def _save_user_colors(colors: List[str], fig=None) -> List[str]:
    """
    Save user colors to disk and cache, removing duplicates and empty entries.
    """
    cleaned: List[str] = []
    for col in colors:
        if not col:
            continue
        if col not in cleaned:
            cleaned.append(col)
    ok = _cfg_save_user_colors(cleaned)
    _set_cached_colors(fig, cleaned)
    if not ok:
        print("Warning: could not write ~/.batplot/config.json (colors may not persist).")
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
            token = colors[idx]

    # Normalize named / cycle / RGBA colors to lowercase hex for consistent
    # display and storage across modes. Unknown tokens pass through unchanged.
    hex_code = to_display_hex(token)
    return hex_code if hex_code is not None else token


def print_user_colors(fig=None) -> None:
    """Print saved colors with indices, color cubes, and hex codes."""
    colors = get_user_color_list(fig)
    if not colors:
        print("No saved user colors.")
        return
    print("Saved colors:")
    for idx, color in enumerate(colors, 1):
        print(f"  {idx}: {format_color_listing(color)}")


# After the screen picker, one accidental blank Enter must not exit color menus.
_ignore_next_blank_color_input = False
_last_screen_pick_count = 0


def arm_ignore_next_blank_color_input() -> None:
    """Arm a one-shot guard: next blank color-menu input is ignored (not back)."""
    global _ignore_next_blank_color_input
    _ignore_next_blank_color_input = True


def clear_blank_color_input_guard() -> None:
    """Disarm the post-picker blank guard (e.g. when leaving a color submenu)."""
    global _ignore_next_blank_color_input
    _ignore_next_blank_color_input = False


def consume_blank_color_input_guard() -> bool:
    """Return True if a blank input should be ignored (and clear the guard)."""
    global _ignore_next_blank_color_input
    if _ignore_next_blank_color_input:
        _ignore_next_blank_color_input = False
        return True
    return False


def last_screen_pick_count() -> int:
    """How many colors the last ``prompt_screen_color`` call saved (0 if none)."""
    return int(_last_screen_pick_count)


def blank_means_back(raw: str) -> bool:
    """True if empty input should leave a color prompt.

    After the screen picker, one blank Enter is ignored so a leftover or habit
    Enter does not quit the color menu (user must type ``q`` to leave).
    Any non-empty input clears the one-shot guard.
    """
    global _ignore_next_blank_color_input
    if (raw or "").strip():
        _ignore_next_blank_color_input = False
        return False
    if _ignore_next_blank_color_input:
        _ignore_next_blank_color_input = False
        return False
    return True


def prompt_screen_color(fig=None, *, add_to_saved: bool = True) -> Optional[str]:
    """Open the screen eyedropper; pick one or more colors; stay in the menu.

    Used by color menus via key ``e``. Magnifier stays open until ``q``.
    Each Enter saves a color into the user list. Returns the *last* picked
    ``#rrggbb`` (for single-target apply paths), or ``None`` if none picked.

    Call :func:`last_screen_pick_count` after return: if ``> 1``, apply-on-pick
    callers should *not* auto-apply (all picks were saved as ``u#`` only).
    """
    global _last_screen_pick_count
    _last_screen_pick_count = 0
    # Same dashed frame as other interactive key-description blocks.
    try:
        from .plot_modes.common.menu_rendering import (
            MENU_SEPARATOR_LINE,
            menu_block_begin,
            menu_block_end,
        )

        menu_block_begin(force_new=True)
        _sep = MENU_SEPARATOR_LINE
        _close = menu_block_end
    except Exception:
        _sep = "-" * 60
        print(_sep)

        def _close() -> None:
            print(_sep)

    print("Screen color picker (magnifier is preview only):")
    print("  Keep the mouse on a color.")
    print("  In THIS terminal:")
    print("    Enter        = pick this color (window stays — pick more)")
    print("    q then Enter = done (close magnifier, return to color menu)")
    print("  Or close the magnifier window (X) = done.")
    _close()
    try:
        from .screen_color import pick_screen_colors
    except Exception as exc:
        print(f"Screen color picker unavailable: {exc}")
        return None
    try:
        picked = pick_screen_colors(show_intro=False)
    except Exception as exc:
        print(f"Screen color picker failed: {exc}")
        return None
    # Always arm: even cancel/zero picks — leftover Enter must not quit menus.
    arm_ignore_next_blank_color_input()
    if not picked:
        print("No colors picked — still in the color menu (q to leave).")
        return None

    last: Optional[str] = None
    for raw in picked:
        hex_c = to_display_hex(raw) or raw
        last = hex_c
        if add_to_saved:
            colors = add_user_color(hex_c, fig)
            try:
                idx = colors.index(hex_c) + 1
            except ValueError:
                idx = len(colors)
            print(
                f"  Saved {format_color_listing(hex_c)} as user color {idx} "
                f"(use {idx} or u{idx})."
            )
        else:
            print(f"  Picked {format_color_listing(hex_c)}")
    _last_screen_pick_count = len(picked)
    n = len(picked)
    if n > 1:
        print(
            f"Done — {n} color(s) saved as u#. "
            "Enter a number/u#/name to apply, or q to leave."
        )
    else:
        print(f"Done — {n} color(s). Still in the color menu (q to leave).")
    return last


def run_color_token_input_loop(
    *,
    prompt,
    safe_input,
    colorize_prompt,
    process,
    fig=None,
    cancel_on_blank: bool = True,
) -> None:
    """Prompt for colors with shared ``e`` (screen pick) / ``u`` (manage) / ``q``.

    ``process(resolved_color)`` should apply the color and return ``True`` to
    continue, ``False`` on validation error. Blank/q exits. Tokens are resolved
    via ``resolve_color_token`` (saved indices, names, hex).

    Multi-pick via ``e``: all colors are saved as ``u#``; auto-apply only runs
    when exactly one color was picked (avoids silently recoloring after a
    palette grab).
    """
    try:
        while True:
            text = prompt() if callable(prompt) else prompt
            try:
                try:
                    raw = safe_input(colorize_prompt(text), cancel_on_interrupt=True).strip()
                except TypeError:
                    raw = safe_input(colorize_prompt(text)).strip()
            except (KeyboardInterrupt, EOFError):
                print("Canceled.")
                break
            low = raw.lower()
            if low == "q":
                break
            if not raw:
                if cancel_on_blank and blank_means_back(raw):
                    break
                continue
            # Real token: clear post-picker blank guard
            blank_means_back(raw)
            if low == "e":
                picked = prompt_screen_color(fig)
                if not picked:
                    continue
                if last_screen_pick_count() > 1:
                    # Saved only — do not apply last (user is building a palette).
                    continue
                try:
                    result = process(picked)
                except Exception as exc:
                    print(f"Error: {exc}")
                    continue
                if result is False:
                    continue
                continue
            if low == "u":
                manage_user_colors(fig)
                continue
            try:
                resolved = resolve_color_token(raw, fig)
            except Exception:
                resolved = raw
            try:
                result = process(resolved)
            except Exception as exc:
                print(f"Error: {exc}")
                continue
            if result is False:
                continue
    finally:
        clear_blank_color_input_guard()


def manage_user_colors(fig=None) -> None:
    """Interactive submenu for editing user-defined colors."""
    try:
        _manage_user_colors_inner(fig)
    finally:
        clear_blank_color_input_guard()


def _manage_user_colors_inner(fig=None) -> None:
    while True:
        colors = get_user_color_list(fig)
        print("\n\033[1mUser color list:\033[0m")
        if colors:
            for idx, color in enumerate(colors, 1):
                print(f"  {idx}: {format_color_listing(color)}")
        else:
            print("  (empty)")
        print(
            "Options: \033[96ma\033[0m=add colors  \033[96me\033[0m=pick from screen  "
            "\033[96md\033[0m=delete numbers  \033[96mc\033[0m=clear  \033[96mq\033[0m=back"
        )
        choice = input("User colors> ").strip().lower()
        if not choice:
            continue
        if choice == 'q':
            break
        if choice == 'e':
            prompt_screen_color(fig, add_to_saved=True)
            continue
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
                    hex_col = to_display_hex(col) or col
                    if hex_col not in colors and col not in colors:
                        colors.append(hex_col)
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
    'ensure_colormap',
    'format_color_listing',
    'get_colormap',
    'manage_user_colors',
    'palette_preview',
    'print_user_colors',
    'prompt_screen_color',
    'blank_means_back',
    'clear_blank_color_input_guard',
    'last_screen_pick_count',
    'remove_user_color',
    'run_color_token_input_loop',
    'to_display_hex',
    'resolve_color_token',
    'get_user_color_list',
]
