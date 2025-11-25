"""Shared helpers for color previews and user-defined color management."""

from __future__ import annotations

from typing import List, Optional, Sequence

import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.colors import LinearSegmentedColormap

from .config import get_user_colors as _cfg_get_user_colors
from .config import save_user_colors as _cfg_save_user_colors

_CUSTOM_CMAPS = {
    'batlow': ['#02121d', '#053061', '#2b7a8b', '#7cbf7b', '#c7e6a2', '#f9f0c3'],
    'batlowk': ['#150b2d', '#3d2e63', '#5f4f85', '#81718f', '#a6938e', '#cbb58f', '#efd78d'],
    'batloww': ['#0a1427', '#17385d', '#295f8d', '#4f8fa3', '#7db7a1', '#b2d39a', '#e3e6a8'],
}


def ensure_colormap(name: Optional[str]) -> bool:
    """Ensure that a named colormap exists (register custom/cmcrameri fallback if needed)."""
    if not name:
        return False
    base = name[:-2] if name.lower().endswith('_r') else name
    base_lower = base.lower()
    if base_lower in plt.colormaps():
        return True
    try:
        import cmcrameri.cm as cmc
        if hasattr(cmc, base_lower):
            cmap_obj = getattr(cmc, base_lower)
            try:
                plt.register_cmap(name=base_lower, cmap=cmap_obj)
            except ValueError:
                pass
            return True
    except Exception:
        pass
    custom = _CUSTOM_CMAPS.get(base_lower)
    if custom:
        try:
            cmap_obj = LinearSegmentedColormap.from_list(base_lower, custom, N=256)
            try:
                plt.register_cmap(name=base_lower, cmap=cmap_obj)
            except ValueError:
                pass
            return True
        except Exception:
            return False
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
    """Return a color bar preview for a matplotlib colormap."""
    ensure_colormap(name)
    try:
        cmap = plt.get_cmap(name)
    except Exception:
        cmap = None
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
    if steps < 1:
        steps = 1
    samples = [
        mcolors.to_hex(cmap(i / max(steps - 1, 1)))
        for i in range(steps)
    ]
    return color_bar(samples)


def _set_cached_colors(fig, colors: List[str]):
    if fig is not None:
        setattr(fig, '_user_colors_cache', list(colors))


def get_user_color_list(fig=None) -> List[str]:
    """Return cached user colors (persisted to ~/.batplot)."""
    if fig is not None and hasattr(fig, '_user_colors_cache'):
        return list(getattr(fig, '_user_colors_cache'))
    colors = list(_cfg_get_user_colors())
    _set_cached_colors(fig, colors)
    return colors


def _save_user_colors(colors: List[str], fig=None) -> List[str]:
    cleaned: List[str] = []
    for col in colors:
        if not col:
            continue
        if col not in cleaned:
            cleaned.append(col)
    _cfg_save_user_colors(cleaned)
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
    """Translate references like '2' or 'u3' into stored colors."""
    if not token:
        return token
    stripped = token.strip()
    idx = None
    if stripped.lower().startswith('u') and stripped[1:].isdigit():
        idx = int(stripped[1:]) - 1
    elif stripped.isdigit():
        idx = int(stripped) - 1
    if idx is not None:
        colors = get_user_color_list(fig)
        if 0 <= idx < len(colors):
            return colors[idx]
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
                for idx in sorted(indices, reverse=True):
                    colors.pop(idx)
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
