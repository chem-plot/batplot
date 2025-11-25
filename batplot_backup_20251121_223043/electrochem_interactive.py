"""Interactive menu for electrochemistry (.mpt GC) plots.

Provides a minimal interactive loop when running:
  batplot file.mpt --gc --mass <mg> --interactive

"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple
import json
import os

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
from matplotlib import colors as mcolors
from .ui import (
    resize_plot_frame, resize_canvas,
    update_tick_visibility as _ui_update_tick_visibility,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
)
from matplotlib.ticker import MaxNLocator, AutoMinorLocator, NullFormatter, NullLocator
from .plotting import update_labels as _update_labels
from .utils import (
    _confirm_overwrite,
    choose_save_path,
    choose_style_file,
    list_files_in_subdirectory,
    get_organized_path,
)
from .color_utils import (
    color_block,
    color_bar,
    palette_preview,
    manage_user_colors,
    get_user_color_list,
    resolve_color_token,
)


def _colorize_menu(text):
    """Colorize menu items: command in cyan, colon in white, description in default."""
    if ':' not in text:
        return text
    parts = text.split(':', 1)
    cmd = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ''
    return f"\033[96m{cmd}\033[0m: {desc}"  # Cyan for command, default for description


def _colorize_prompt(text):
    """Colorize commands within input prompts. Handles formats like (s=size, f=family, q=return) or (y/n)."""
    import re
    pattern = r'\(([a-z]+=[^,)]+(?:,\s*[a-z]+=[^,)]+)*|[a-z]+(?:/[a-z]+)+)\)'
    
    def colorize_match(match):
        content = match.group(1)
        if '/' in content:
            parts = content.split('/')
            colored_parts = [f"\033[96m{p.strip()}\033[0m" for p in parts]
            return f"({'/'.join(colored_parts)})"
        else:
            parts = content.split(',')
            colored_parts = []
            for part in parts:
                part = part.strip()
                if '=' in part:
                    cmd, desc = part.split('=', 1)
                    colored_parts.append(f"\033[96m{cmd.strip()}\033[0m={desc.strip()}")
                else:
                    colored_parts.append(part)
            return f"({', '.join(colored_parts)})"
    
    return re.sub(pattern, colorize_match, text)


def _colorize_inline_commands(text):
    """Colorize inline command examples in help text. Colors quoted examples and specific known commands."""
    import re
    # Color quoted command examples (like 's2 w5 a4', 'w2 w5')
    text = re.sub(r"'([a-z0-9\s_-]+)'", lambda m: f"'\033[96m{m.group(1)}\033[0m'", text)
    # Color specific known commands: q, i, l, list, help, all
    text = re.sub(r'\b(q|i|l|list|help|all)\b(?=\s*[=,]|\s*$)', lambda m: f"\033[96m{m.group(1)}\033[0m", text)
    return text


def _apply_stored_axis_colors(ax):
    try:
        color = getattr(ax, '_stored_xlabel_color', None)
        if color:
            ax.xaxis.label.set_color(color)
    except Exception:
        pass
    try:
        color = getattr(ax, '_stored_ylabel_color', None)
        if color:
            ax.yaxis.label.set_color(color)
    except Exception:
        pass
    try:
        top_artist = getattr(ax, '_top_xlabel_artist', None)
        color = getattr(ax, '_stored_top_xlabel_color', None)
        if top_artist is not None and color:
            top_artist.set_color(color)
    except Exception:
        pass
    try:
        right_artist = getattr(ax, '_right_ylabel_artist', None)
        color = getattr(ax, '_stored_right_ylabel_color', None)
        if right_artist is not None and color:
            right_artist.set_color(color)
    except Exception:
        pass


def _apply_spine_color(ax, fig, tick_state, spine_name: str, color) -> None:
    if color is None:
        return
    sp = ax.spines.get(spine_name)
    if sp is not None:
        try:
            sp.set_edgecolor(color)
        except Exception:
            pass
    try:
        if spine_name in ('top', 'bottom'):
            ax.tick_params(axis='x', which='both', colors=color)
            ax.xaxis.label.set_color(color)
            ax._stored_xlabel_color = color
            if spine_name == 'top':
                ax._stored_top_xlabel_color = color
                artist = getattr(ax, '_top_xlabel_artist', None)
                if artist is not None:
                    artist.set_color(color)
                _ui_position_top_xlabel(ax, fig, tick_state)
            else:
                _ui_position_bottom_xlabel(ax, fig, tick_state)
        else:
            ax.tick_params(axis='y', which='both', colors=color)
            ax.yaxis.label.set_color(color)
            ax._stored_ylabel_color = color
            if spine_name == 'right':
                ax._stored_right_ylabel_color = color
                artist = getattr(ax, '_right_ylabel_artist', None)
                if artist is not None:
                    artist.set_color(color)
                _ui_position_right_ylabel(ax, fig, tick_state)
            else:
                _ui_position_left_ylabel(ax, fig, tick_state)
    except Exception:
        pass
    _apply_stored_axis_colors(ax)


def _diffcap_clean_series(x: np.ndarray, y: np.ndarray, min_step: float = 1e-3) -> Tuple[np.ndarray, np.ndarray, int]:
    """Remove points where ΔVoltage < min_step (default 1 mV) while preserving order."""
    if x.size <= 1:
        return x, y, 0
    keep_indices = [0]
    last_x = x[0]
    removed = 0
    for idx in range(1, x.size):
        if abs(x[idx] - last_x) >= min_step:
            keep_indices.append(idx)
            last_x = x[idx]
        else:
            removed += 1
    if removed == 0:
        return x, y, 0
    keep = np.array(keep_indices, dtype=int)
    return x[keep], y[keep], removed


def _savgol_kernel(window: int, poly: int) -> np.ndarray:
    """Return Savitzky–Golay smoothing kernel of given window/poly."""
    half = window // 2
    x = np.arange(-half, half + 1, dtype=float)
    A = np.vander(x, poly + 1, increasing=True)
    ATA = A.T @ A
    ATA_inv = np.linalg.pinv(ATA)
    target = np.zeros(poly + 1, dtype=float)
    target[0] = 1.0  # evaluate polynomial at x=0
    coeffs = target @ ATA_inv @ A.T
    return coeffs


def _savgol_smooth(y: np.ndarray, window: int = 9, poly: int = 3) -> np.ndarray:
    """Apply Savitzky–Golay smoothing (defaults from DiffCapAnalyzer) to data."""
    n = y.size
    if n < 3:
        return y
    if window > n:
        window = n if n % 2 == 1 else n - 1
    if window < 3:
        return y
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return y
    if poly >= window:
        poly = window - 1
    coeffs = _savgol_kernel(window, poly)
    half = window // 2
    padded = np.pad(y, (half, half), mode='edge')
    smoothed = np.convolve(padded, coeffs[::-1], mode='valid')
    return smoothed


def _print_menu(n_cycles: int, is_dqdv: bool = False):
    # Three-column menu similar to operando: Styles | Geometries | Options
    # Use dynamic column widths for clean alignment.
    col1 = [
        "f: font",
        "l: line",
        "k: spine colors",
        "t: toggle axes",
        "h: legend",
        "g: size",
        "ro: rotation",
    ]
    if is_dqdv:
        col1.insert(2, "sm: smooth")
    col2 = [
        "c: cycles/colors",
        "r: rename axes",
        "x: x-scale",
        "y: y-scale",
    ]
    # Only show capacity/ion option when NOT in dQdV mode
    if not is_dqdv:
        col2.insert(1, "a: capacity/ion")
    
    col3 = [
        "p: print(export) style/geom",
        "i: import style/geom",
        "e: export figure",
        "s: save project",
        "b: undo",
        "q: quit",
    ]
    # Compute widths (min width prevents overly narrow columns)
    w1 = max(len("(Styles)"), *(len(s) for s in col1), 18)
    w2 = max(len("(Geometries)"), *(len(s) for s in col2), 12)
    w3 = max(len("(Options)"), *(len(s) for s in col3), 12)
    rows = max(len(col1), len(col2), len(col3))
    print("\n\033[1mInteractive menu:\033[0m")  # Bold title
    print(f"  \033[93m{'(Styles)':<{w1}}\033[0m \033[93m{'(Geometries)':<{w2}}\033[0m \033[93m{'(Options)':<{w3}}\033[0m")  # Yellow headers
    for i in range(rows):
        p1 = _colorize_menu(col1[i]) if i < len(col1) else ""
        p2 = _colorize_menu(col2[i]) if i < len(col2) else ""
        p3 = _colorize_menu(col3[i]) if i < len(col3) else ""
        # Add padding to account for ANSI escape codes
        pad1 = w1 + (9 if i < len(col1) else 0)
        pad2 = w2 + (9 if i < len(col2) else 0)
        pad3 = w3 + (9 if i < len(col3) else 0)
        print(f"  {p1:<{pad1}} {p2:<{pad2}} {p3:<{pad3}}")


def _iter_cycle_lines(cycle_lines: Dict[int, Dict[str, Optional[object]]]):
    """Iterate over all Line2D objects in cycle_lines, handling both GC and CV modes.
    
    Yields: (cyc, role_or_None, Line2D) tuples
    - For GC mode: yields (cyc, 'charge', ln) and (cyc, 'discharge', ln) for each cycle
    - For CV mode: yields (cyc, None, ln) for each cycle
    """
    for cyc, parts in cycle_lines.items():
        if not isinstance(parts, dict):
            # CV mode: parts is a Line2D directly
            yield (cyc, None, parts)
        else:
            # GC mode: parts is a dict with 'charge' and 'discharge' keys
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is not None:
                    yield (cyc, role, ln)


def _visible_legend_entries(ax):
    """Return handles/labels for visible, user-facing lines only."""
    handles = []
    labels = []
    for ln in ax.lines:
        if ln.get_visible():
            lab = ln.get_label() or ""
            if lab.startswith("_"):
                continue
            handles.append(ln)
            labels.append(lab)
    return handles, labels


def _get_legend_user_pref(fig):
    try:
        return bool(getattr(fig, '_ec_legend_user_visible'))
    except Exception:
        return True


def _set_legend_user_pref(fig, visible: bool):
    try:
        fig._ec_legend_user_visible = bool(visible)
    except Exception:
        pass


def _store_legend_title(fig, ax, fallback: str = "Cycle"):
    """Persist the current legend title on the figure for later rebuilds."""
    try:
        leg = ax.get_legend()
        text = ""
        if leg is not None:
            title_artist = leg.get_title()
            if title_artist is not None:
                text = title_artist.get_text() or ""
        if text:
            fig._ec_legend_title = text
        elif not getattr(fig, '_ec_legend_title', None):
            fig._ec_legend_title = fallback
    except Exception:
        if not getattr(fig, '_ec_legend_title', None):
            fig._ec_legend_title = fallback


def _get_legend_title(fig, default: str = "Cycle") -> str:
    try:
        title = getattr(fig, '_ec_legend_title')
        if isinstance(title, str) and title:
            return title
    except Exception:
        pass
    return default


def _rebuild_legend(ax):
    """Rebuild legend using only visible lines, anchoring to absolute inches from canvas center if available."""
    fig = ax.figure
    if not _get_legend_user_pref(fig):
        leg = ax.get_legend()
        if leg is not None:
            try:
                leg.remove()
            except Exception:
                pass
        return

    handles, labels = _visible_legend_entries(ax)
    if handles:
        xy_in = _sanitize_legend_offset(fig, getattr(fig, '_ec_legend_xy_in', None))
        legend_title = _get_legend_title(fig)
        if xy_in is not None:
            try:
                fw, fh = fig.get_size_inches()
                fx = 0.5 + float(xy_in[0]) / float(fw)
                fy = 0.5 + float(xy_in[1]) / float(fh)
                _legend_no_frame(
                    ax,
                    handles,
                    labels,
                    loc='center',
                    bbox_to_anchor=(fx, fy),
                    bbox_transform=fig.transFigure,
                    borderaxespad=1.0,
                    title=legend_title,
                )
            except Exception:
                _legend_no_frame(ax, handles, labels, loc='best', borderaxespad=1.0, title=legend_title)
        else:
            _legend_no_frame(ax, handles, labels, loc='best', borderaxespad=1.0, title=legend_title)
        _store_legend_title(fig, ax, legend_title)
    else:
        leg = ax.get_legend()
        if leg is not None:
            try:
                leg.remove()
            except Exception:
                pass


def _apply_curve_linewidth(fig, cycle_lines: Dict[int, Dict[str, Optional[object]]]):
    """Apply stored curve linewidth to all curves.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    lw = getattr(fig, '_ec_curve_linewidth', None)
    if lw is not None:
        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
            try:
                ln.set_linewidth(lw)
            except Exception:
                pass


def _apply_colors(cycle_lines: Dict[int, Dict[str, Optional[object]]], mapping: Dict[int, object]):
    """Apply color mapping to charge/discharge lines for the given cycles.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    for cyc, col in mapping.items():
        if cyc not in cycle_lines:
            continue
        for _, _, ln in _iter_cycle_lines({cyc: cycle_lines[cyc]}):
            try:
                ln.set_color(col)
            except Exception:
                pass


def _set_visible_cycles(cycle_lines: Dict[int, Dict[str, Optional[object]]], show: Iterable[int]):
    """Set visibility for specified cycles.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    show_set = set(show)
    for cyc, role, ln in _iter_cycle_lines(cycle_lines):
        vis = cyc in show_set
        try:
            ln.set_visible(vis)
        except Exception:
            pass


def _resolve_palette_alias(token: str, palette_map: dict) -> str:
    """Resolve numeric aliases (e.g., '2' or '2_r') to palette names."""
    suffix = ''
    base = token
    if token.lower().endswith('_r'):
        suffix = '_r'
        base = token[:-2]
    if base in palette_map:
        return palette_map[base] + suffix
    return token


def _parse_cycle_tokens(tokens: List[str], fig=None) -> Tuple[str, List[int], dict, Optional[str], bool]:
    """Classify and parse tokens for the cycle command.

    Returns a tuple: (mode, cycles, mapping, palette)
      - mode: 'map' for explicit mappings like 1:red, 'palette' for numbers + cmap,
              'numbers' for numbers only.
      - cycles: list of cycle indices (integers)
      - mapping: dict for 'map' mode only, empty otherwise
      - palette: colormap name for 'palette' mode else None
    """
    if not tokens:
        return ("numbers", [], {}, None, False)

    palette_map = {
        '1': 'tab10',
        '2': 'Set2',
        '3': 'Dark2',
        '4': 'viridis',
        '5': 'plasma'
    }

    # Support 'all' and 'all <palette>'
    if len(tokens) == 1 and tokens[0].lower() == 'all':
        return ("numbers", [], {}, None, True)
    if len(tokens) == 2 and tokens[0].lower() == 'all':
        alias = _resolve_palette_alias(tokens[1], palette_map)
        try:
            cm.get_cmap(alias)
            return ("palette", [], {}, alias, True)
        except Exception:
            # Unknown palette -> still select all, no recolor
            return ("numbers", [], {}, None, True)

    # Check explicit mapping mode first
    if any(":" in t for t in tokens):
        cycles: List[int] = []
        mapping = {}
        for t in tokens:
            if ":" not in t:
                continue
            idx_s, col = t.split(":", 1)
            try:
                cyc = int(idx_s)
            except ValueError:
                continue
            mapping[cyc] = resolve_color_token(col, fig)
            if cyc not in cycles:
                cycles.append(cyc)
        return ("map", cycles, mapping, None, False)

    # If last token is a valid colormap or number (1-5) -> palette mode
    last = tokens[-1]

    # Check if last token is a number from 1-5
    if last in palette_map:
        palette = palette_map[last]
        num_tokens = tokens[:-1]
        cycles = []
        for t in num_tokens:
            try:
                cycles.append(int(t))
            except ValueError:
                pass
        return ("palette", cycles, {}, palette, False)
    alias = _resolve_palette_alias(last, palette_map)
    if alias != last:
        try:
            cm.get_cmap(alias)
            palette = alias
            num_tokens = tokens[:-1]
            cycles = []
            for t in num_tokens:
                try:
                    cycles.append(int(t))
                except ValueError:
                    pass
            return ("palette", cycles, {}, palette, False)
        except Exception:
            pass

    # Check if last token is a valid colormap name
    try:
        cm.get_cmap(last)
        palette = last
        num_tokens = tokens[:-1]
        cycles = []
        for t in num_tokens:
            try:
                cycles.append(int(t))
            except ValueError:
                pass
        return ("palette", cycles, {}, palette, False)
    except Exception:
        pass

    # Numbers only
    cycles: List[int] = []
    for t in tokens:
        try:
            cycles.append(int(t))
        except ValueError:
            pass
    return ("numbers", cycles, {}, None, False)


def _apply_font_family(ax, family: str):
    try:
        import matplotlib as mpl
        # Update defaults for any new text
        mpl.rcParams['font.family'] = family
        # Configure mathtext to use the same font family
        lf = family.lower()
        if any(k in lf for k in ('stix', 'times', 'roman')):
            mpl.rcParams['mathtext.fontset'] = 'stix'
        else:
            # Use dejavusans for Arial, Helvetica, etc. to match sans-serif fonts
            mpl.rcParams['mathtext.fontset'] = 'dejavusans'
        mpl.rcParams['mathtext.default'] = 'regular'
        # Apply to existing labels
        try:
            ax.xaxis.label.set_family(family)
        except Exception:
            pass
        try:
            ax.yaxis.label.set_family(family)
        except Exception:
            pass
        # Title (safe if exists)
        try:
            ax.title.set_family(family)
        except Exception:
            pass
        # Duplicate titles
        try:
            art = getattr(ax, '_top_xlabel_artist', None)
            if art is not None:
                art.set_family(family)
        except Exception:
            pass
        try:
            art = getattr(ax, '_right_ylabel_artist', None)
            if art is not None:
                art.set_family(family)
        except Exception:
            pass
        # Ticks
        for lab in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            try:
                lab.set_family(family)
            except Exception:
                pass
        # Top/right tick labels (label2)
        try:
            for t in ax.xaxis.get_major_ticks():
                if hasattr(t, 'label2'):
                    t.label2.set_family(family)
            for t in ax.yaxis.get_major_ticks():
                if hasattr(t, 'label2'):
                    t.label2.set_family(family)
        except Exception:
            pass
        # Legend
        leg = ax.get_legend()
        if leg is not None:
            for t in leg.get_texts():
                try:
                    t.set_family(family)
                except Exception:
                    pass
        # Any additional text in axes
        for t in getattr(ax, 'texts', []):
            try:
                t.set_family(family)
            except Exception:
                pass
    except Exception:
        pass


def _apply_font_size(ax, size: float):
    """Apply font size to all text elements on the axes."""
    try:
        import matplotlib as mpl
        # Update defaults for any new text
        mpl.rcParams['font.size'] = size
        # Labels
        try:
            ax.xaxis.label.set_size(size)
        except Exception:
            pass
        try:
            ax.yaxis.label.set_size(size)
        except Exception:
            pass
        # Title (safe if exists)
        try:
            ax.title.set_size(size)
        except Exception:
            pass
        # Duplicate titles
        try:
            art = getattr(ax, '_top_xlabel_artist', None)
            if art is not None:
                art.set_size(size)
        except Exception:
            pass
        try:
            art = getattr(ax, '_right_ylabel_artist', None)
            if art is not None:
                art.set_size(size)
        except Exception:
            pass
        # Ticks
        for lab in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            try:
                lab.set_size(size)
            except Exception:
                pass
        # Also update top/right tick labels (label2)
        try:
            for t in ax.xaxis.get_major_ticks():
                if hasattr(t, 'label2'):
                    t.label2.set_size(size)
            for t in ax.yaxis.get_major_ticks():
                if hasattr(t, 'label2'):
                    t.label2.set_size(size)
        except Exception:
            pass
    except Exception:
        pass


def electrochem_interactive_menu(fig, ax, cycle_lines: Dict[int, Dict[str, Optional[object]]], file_path=None):
    # --- Tick/label state and helpers (similar to normal XY menu) ---
    tick_state = getattr(ax, '_saved_tick_state', {
        'bx': True,
        'tx': False,
        'ly': True,
        'ry': False,
        'mbx': False,
        'mtx': False,
        'mly': False,
        'mry': False,
    })

    base_ylabel = ax.get_ylabel() or ''
    if not hasattr(ax, '_stored_xlabel'):
        ax._stored_xlabel = ax.get_xlabel() or ''
    if not hasattr(ax, '_stored_ylabel'):
        ax._stored_ylabel = base_ylabel
    if not hasattr(ax, '_stored_xlabel_color'):
        try:
            ax._stored_xlabel_color = ax.xaxis.label.get_color()
        except Exception:
            ax._stored_xlabel_color = None
    if not hasattr(ax, '_stored_ylabel_color'):
        try:
            ax._stored_ylabel_color = ax.yaxis.label.get_color()
        except Exception:
            ax._stored_ylabel_color = None
    if not hasattr(ax, '_stored_top_xlabel_color'):
        ax._stored_top_xlabel_color = ax.xaxis.label.get_color()
    if not hasattr(ax, '_stored_right_ylabel_color'):
        ax._stored_right_ylabel_color = ax.yaxis.label.get_color()
    
    # Detect dQdV mode: check stored flag first, then fall back to y-label detection
    # This handles cases where the user renamed the y-axis and saved/reloaded the session
    is_dqdv = getattr(ax, '_is_dqdv_mode', None)
    if is_dqdv is None:
        # Initial detection: check if y-label contains "dQ"
        is_dqdv = 'dQ' in base_ylabel
        # Store the mode on the axes for persistence
        ax._is_dqdv_mode = is_dqdv

    source_paths = []
    _source_seen = set()

    def _add_source_path(path_val):
        if not path_val:
            return
        try:
            abs_path = os.path.abspath(path_val)
        except Exception:
            return
        if not os.path.exists(abs_path):
            return
        if abs_path in _source_seen:
            return
        _source_seen.add(abs_path)
        source_paths.append(abs_path)

    if file_path:
        _add_source_path(file_path)
    fig_source_attr = getattr(fig, '_bp_source_paths', None)
    if fig_source_attr:
        for _p in fig_source_attr:
            _add_source_path(_p)
    if not source_paths and hasattr(ax, 'figure'):
        attr = getattr(ax.figure, '_bp_source_paths', None)
        if attr:
            for _p in attr:
                _add_source_path(_p)
    try:
        fig._bp_source_paths = list(source_paths)
    except Exception:
        pass

    def _set_spine_visible(which: str, visible: bool):
        sp = ax.spines.get(which)
        if sp is not None:
            try:
                sp.set_visible(bool(visible))
            except Exception:
                pass

    def _get_spine_visible(which: str) -> bool:
        sp = ax.spines.get(which)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False

    def _update_tick_visibility():
        # Use shared UI helper for consistent behavior
        try:
            _ui_update_tick_visibility(ax, tick_state)
        except Exception:
            pass
        # Persist on axes
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass
        # Keep label spacing consistent with XY behavior
        try:
            _ui_position_bottom_xlabel(ax, ax.figure, tick_state)
            _ui_position_left_ylabel(ax, ax.figure, tick_state)
        except Exception:
            pass

    def _title_offset_menu():
        """Allow nudging duplicate top/right titles by single-pixel increments."""
        def _dpi():
            try:
                return float(fig.dpi)
            except Exception:
                return 72.0

        def _px_value(attr):
            try:
                pts = float(getattr(ax, attr, 0.0) or 0.0)
            except Exception:
                pts = 0.0
            return pts * _dpi() / 72.0

        def _set_attr(attr, pts):
            try:
                setattr(ax, attr, float(pts))
            except Exception:
                pass

        def _nudge(attr, delta_px):
            try:
                current_pts = float(getattr(ax, attr, 0.0) or 0.0)
            except Exception:
                current_pts = 0.0
            delta_pts = float(delta_px) * 72.0 / _dpi()
            _set_attr(attr, current_pts + delta_pts)

        snapshot_taken = False

        def _ensure_snapshot():
            nonlocal snapshot_taken
            if not snapshot_taken:
                push_state("title-offset")
                snapshot_taken = True

        def _top_menu():
            if not getattr(ax, '_top_xlabel_on', False):
                print("Top duplicate title is currently hidden (enable with w5).")
                return
            while True:
                current_y_px = _px_value('_top_xlabel_manual_offset_y_pts')
                current_x_px = _px_value('_top_xlabel_manual_offset_x_pts')
                print(f"Top title offset: Y={current_y_px:+.2f} px (positive=up), X={current_x_px:+.2f} px (positive=right)")
                sub = input(_colorize_prompt("top (w=up, s=down, a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_top_xlabel_manual_offset_y_pts', 0.0)
                    _set_attr('_top_xlabel_manual_offset_x_pts', 0.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_y_pts', +1.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_y_pts', -1.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_x_pts', -1.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_x_pts', +1.0)
                else:
                    print("Unknown choice (use w/s/a/d/0/q).")
                    continue
                _ui_position_top_xlabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _right_menu():
            if not getattr(ax, '_right_ylabel_on', False):
                print("Right duplicate title is currently hidden (enable with d5).")
                return
            while True:
                current_x_px = _px_value('_right_ylabel_manual_offset_x_pts')
                current_y_px = _px_value('_right_ylabel_manual_offset_y_pts')
                print(f"Right title offset: X={current_x_px:+.2f} px (positive=right), Y={current_y_px:+.2f} px (positive=up)")
                sub = input(_colorize_prompt("right (d=right, a=left, w=up, s=down, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_right_ylabel_manual_offset_x_pts', 0.0)
                    _set_attr('_right_ylabel_manual_offset_y_pts', 0.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_x_pts', +1.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_x_pts', -1.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_y_pts', +1.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_y_pts', -1.0)
                else:
                    print("Unknown choice (use d/a/w/s/0/q).")
                    continue
                _ui_position_right_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _bottom_menu():
            if not ax.get_xlabel():
                print("Bottom title is currently hidden.")
                return
            while True:
                current_y_px = _px_value('_bottom_xlabel_manual_offset_y_pts')
                print(f"Bottom title offset: Y={current_y_px:+.2f} px (positive=down)")
                sub = input(_colorize_prompt("bottom (s=down, w=up, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_bottom_xlabel_manual_offset_y_pts', 0.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_bottom_xlabel_manual_offset_y_pts', +1.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_bottom_xlabel_manual_offset_y_pts', -1.0)
                else:
                    print("Unknown choice (use s/w/0/q).")
                    continue
                _ui_position_bottom_xlabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _left_menu():
            if not ax.get_ylabel():
                print("Left title is currently hidden.")
                return
            while True:
                current_x_px = _px_value('_left_ylabel_manual_offset_x_pts')
                print(f"Left title offset: X={current_x_px:+.2f} px (positive=left)")
                sub = input(_colorize_prompt("left (a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_left_ylabel_manual_offset_x_pts', 0.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_left_ylabel_manual_offset_x_pts', +1.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_left_ylabel_manual_offset_x_pts', -1.0)
                else:
                    print("Unknown choice (use a/d/0/q).")
                    continue
                _ui_position_left_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        while True:
            print(_colorize_inline_commands("Title offsets:"))
            print("  " + _colorize_menu('w : adjust top title (w=up, s=down, a=left, d=right)'))
            print("  " + _colorize_menu('s : adjust bottom title (s=down, w=up)'))
            print("  " + _colorize_menu('a : adjust left title (a=left, d=right)'))
            print("  " + _colorize_menu('d : adjust right title (d=right, a=left, w=up, s=down)'))
            print("  " + _colorize_menu('r : reset all offsets'))
            print("  " + _colorize_menu('q : return'))
            choice = input(_colorize_prompt("p> ")).strip().lower()
            if not choice:
                continue
            if choice == 'q':
                break
            if choice == 'w':
                _top_menu()
                continue
            if choice == 's':
                _bottom_menu()
                continue
            if choice == 'a':
                _left_menu()
                continue
            if choice == 'd':
                _right_menu()
                continue
            if choice == 'r':
                _ensure_snapshot()
                _set_attr('_top_xlabel_manual_offset_y_pts', 0.0)
                _set_attr('_top_xlabel_manual_offset_x_pts', 0.0)
                _set_attr('_bottom_xlabel_manual_offset_y_pts', 0.0)
                _set_attr('_left_ylabel_manual_offset_x_pts', 0.0)
                _set_attr('_right_ylabel_manual_offset_x_pts', 0.0)
                _set_attr('_right_ylabel_manual_offset_y_pts', 0.0)
                _ui_position_top_xlabel(ax, fig, tick_state)
                _ui_position_bottom_xlabel(ax, fig, tick_state)
                _ui_position_left_ylabel(ax, fig, tick_state)
                _ui_position_right_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
                print("Reset manual offsets for all titles.")
                continue
            print("Unknown option. Use w/s/a/d/r/q.")

    def _apply_nice_ticks():
            try:
                # Only enforce MaxNLocator for linear scales; let Matplotlib defaults handle log/symlog
                if (getattr(ax, 'get_xscale', None) and ax.get_xscale() == 'linear'):
                    ax.xaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
                if (getattr(ax, 'get_yscale', None) and ax.get_yscale() == 'linear'):
                    ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
            except Exception:
                pass
    # Ensure nice ticks on entry and apply initial visibility
    _apply_nice_ticks()
    _update_tick_visibility()
    _ui_position_top_xlabel(ax, fig, tick_state)
    _ui_position_right_ylabel(ax, fig, tick_state)
    _store_legend_title(fig, ax)
    all_cycles = sorted(cycle_lines.keys())

    # Initialize legend visibility preference
    if not hasattr(fig, '_ec_legend_user_visible'):
        try:
            leg0 = ax.get_legend()
            visible = True
            if leg0 is not None:
                visible = bool(leg0.get_visible())
            _set_legend_user_pref(fig, visible)
        except Exception:
            _set_legend_user_pref(fig, True)
    else:
        if not _get_legend_user_pref(fig):
            leg0 = ax.get_legend()
            if leg0 is not None:
                try:
                    leg0.set_visible(False)
                except Exception:
                    pass
    # ---------------- Undo stack ----------------
    state_history: List[dict] = []

    def _tick_width(axis_obj, which: str):
        try:
            tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
            width = tick_kw.get('width')
            if width is None:
                axis_name = getattr(axis_obj, 'axis_name', 'x')
                rc_key = f"{axis_name}tick.{which}.width"
                width = plt.rcParams.get(rc_key)
            if width is not None:
                return float(width)
        except Exception:
            return None
        return None

    def push_state(note: str = ""):
        try:
            snap = {
                'note': note,
                'xlim': ax.get_xlim(),
                'ylim': ax.get_ylim(),
                'xscale': ax.get_xscale(),
                'yscale': ax.get_yscale(),
                'xlabel': ax.get_xlabel(),
                'ylabel': ax.get_ylabel(),
                'tick_state': dict(tick_state),
                'wasd_state': dict(getattr(fig, '_ec_wasd_state', {})) if hasattr(fig, '_ec_wasd_state') else {},
                'fig_size': list(fig.get_size_inches()),
                'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),
                'labelpads': {
                    'x': getattr(ax.xaxis, 'labelpad', None),
                    'y': getattr(ax.yaxis, 'labelpad', None),
                },
                'spines': {name: {
                    'lw': (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None),
                    'visible': (ax.spines.get(name).get_visible() if ax.spines.get(name) else None),
                    'color': (ax.spines.get(name).get_edgecolor() if ax.spines.get(name) else None)
                } for name in ('bottom','top','left','right')},
                'tick_widths': {
                    'x_major': _tick_width(ax.xaxis, 'major'),
                    'x_minor': _tick_width(ax.xaxis, 'minor'),
                    'y_major': _tick_width(ax.yaxis, 'major'),
                    'y_minor': _tick_width(ax.yaxis, 'minor')
                },
                'tick_lengths': dict(getattr(fig, '_tick_lengths', {'major': None, 'minor': None})),
                'tick_direction': getattr(fig, '_tick_direction', 'out'),
                'titles': {
                    'top_x': bool(getattr(ax, '_top_xlabel_on', False)),
                    'right_y': bool(getattr(ax, '_right_ylabel_on', False))
                },
                'title_offsets': {
                    'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
                    'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
                    'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
                    'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
                    'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
                    'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
                },
                'legend': {
                    'visible': False,
                    'position_inches': None,
                },
                'lines': []
            }
            try:
                leg_obj = ax.get_legend()
                snap['legend']['visible'] = bool(leg_obj.get_visible()) if leg_obj is not None else False
            except Exception:
                pass
            try:
                legend_xy = getattr(fig, '_ec_legend_xy_in', None)
                if legend_xy is not None:
                    snap['legend']['position_inches'] = (float(legend_xy[0]), float(legend_xy[1]))
            except Exception:
                snap['legend']['position_inches'] = None
            for i, ln in enumerate(ax.lines):
                try:
                    snap['lines'].append({
                        'index': i,
                        'x': np.array(ln.get_xdata(), copy=True),
                        'y': np.array(ln.get_ydata(), copy=True),
                        'color': ln.get_color(),
                        'lw': ln.get_linewidth(),
                        'ls': ln.get_linestyle(),
                        'alpha': ln.get_alpha(),
                        'visible': ln.get_visible()
                    })
                except Exception:
                    snap['lines'].append({'index': i})
            state_history.append(snap)
            if len(state_history) > 40:
                state_history.pop(0)
        except Exception:
            pass

    def restore_state():
        if not state_history:
            print("No undo history.")
            return
        snap = state_history.pop()
        try:
            # Scales, limits, labels
            try:
                ax.set_xscale(snap.get('xscale','linear'))
                ax.set_yscale(snap.get('yscale','linear'))
            except Exception:
                pass
            try:
                ax.set_xlim(*snap.get('xlim', ax.get_xlim()))
                ax.set_ylim(*snap.get('ylim', ax.get_ylim()))
            except Exception:
                pass
            try:
                ax.set_xlabel(snap.get('xlabel') or '')
                ax.set_ylabel(snap.get('ylabel') or '')
            except Exception:
                pass
            # Tick state
            st = snap.get('tick_state', {})
            for k,v in st.items():
                if k in tick_state:
                    tick_state[k] = bool(v)
            # WASD state
            wasd_snap = snap.get('wasd_state', {})
            if wasd_snap:
                setattr(fig, '_ec_wasd_state', wasd_snap)
                _sync_tick_state()
                _apply_wasd()
            _update_tick_visibility()
            # Rotation angle
            try:
                rot_angle = snap.get('rotation_angle', 0)
                setattr(fig, '_ec_rotation_angle', rot_angle)
            except Exception:
                pass
            # Spines
            for name, spec in snap.get('spines', {}).items():
                sp = ax.spines.get(name)
                if not sp: continue
                if spec.get('lw') is not None:
                    try: sp.set_linewidth(spec['lw'])
                    except Exception: pass
                if spec.get('visible') is not None:
                    try: sp.set_visible(bool(spec['visible']))
                    except Exception: pass
                if spec.get('color') is not None:
                    try:
                        sp.set_edgecolor(spec['color'])
                        if name in ('top', 'bottom'):
                            ax.tick_params(axis='x', which='both', colors=spec['color'])
                            ax.xaxis.label.set_color(spec['color'])
                        else:
                            ax.tick_params(axis='y', which='both', colors=spec['color'])
                            ax.yaxis.label.set_color(spec['color'])
                    except Exception:
                        pass
            # Tick widths
            tw = snap.get('tick_widths', {})
            try:
                if tw.get('x_major') is not None:
                    ax.tick_params(axis='x', which='major', width=tw['x_major'])
                if tw.get('x_minor') is not None:
                    ax.tick_params(axis='x', which='minor', width=tw['x_minor'])
                if tw.get('y_major') is not None:
                    ax.tick_params(axis='y', which='major', width=tw['y_major'])
                if tw.get('y_minor') is not None:
                    ax.tick_params(axis='y', which='minor', width=tw['y_minor'])
            except Exception:
                pass
            # Tick lengths
            tl = snap.get('tick_lengths', {})
            try:
                if tl.get('major') is not None:
                    ax.tick_params(axis='both', which='major', length=tl['major'])
                if tl.get('minor') is not None:
                    ax.tick_params(axis='both', which='minor', length=tl['minor'])
                if tl:
                    fig._tick_lengths = dict(tl)
            except Exception:
                pass
            # Tick direction
            try:
                tick_dir = snap.get('tick_direction', 'out')
                if tick_dir:
                    setattr(fig, '_tick_direction', tick_dir)
                    ax.tick_params(axis='both', which='both', direction=tick_dir)
            except Exception:
                pass
            # Title offsets - all four titles
            try:
                offsets = snap.get('title_offsets', {})
                # Support both old format (top/right) and new format (top_y/top_x/bottom_y/left_x/right_x/right_y)
                try:
                    if 'top_y' in offsets:
                        ax._top_xlabel_manual_offset_y_pts = float(offsets.get('top_y', 0.0) or 0.0)
                    else:
                        # Backward compatibility: old format used 'top' for y-offset
                        ax._top_xlabel_manual_offset_y_pts = float(offsets.get('top', 0.0) or 0.0)
                except Exception:
                    ax._top_xlabel_manual_offset_y_pts = 0.0
                try:
                    ax._top_xlabel_manual_offset_x_pts = float(offsets.get('top_x', 0.0) or 0.0)
                except Exception:
                    ax._top_xlabel_manual_offset_x_pts = 0.0
                try:
                    ax._bottom_xlabel_manual_offset_y_pts = float(offsets.get('bottom_y', 0.0) or 0.0)
                except Exception:
                    ax._bottom_xlabel_manual_offset_y_pts = 0.0
                try:
                    ax._left_ylabel_manual_offset_x_pts = float(offsets.get('left_x', 0.0) or 0.0)
                except Exception:
                    ax._left_ylabel_manual_offset_x_pts = 0.0
                try:
                    if 'right_x' in offsets:
                        ax._right_ylabel_manual_offset_x_pts = float(offsets.get('right_x', 0.0) or 0.0)
                    else:
                        # Backward compatibility: old format used 'right' for x-offset
                        ax._right_ylabel_manual_offset_x_pts = float(offsets.get('right', 0.0) or 0.0)
                except Exception:
                    ax._right_ylabel_manual_offset_x_pts = 0.0
                try:
                    ax._right_ylabel_manual_offset_y_pts = float(offsets.get('right_y', 0.0) or 0.0)
                except Exception:
                    ax._right_ylabel_manual_offset_y_pts = 0.0
                ax._top_xlabel_on = bool(snap.get('titles',{}).get('top_x', False))
                ax._right_ylabel_on = bool(snap.get('titles',{}).get('right_y', False))
                _ui_position_top_xlabel(ax, fig, tick_state)
                _ui_position_bottom_xlabel(ax, fig, tick_state)
                _ui_position_left_ylabel(ax, fig, tick_state)
                _ui_position_right_ylabel(ax, fig, tick_state)
            except Exception:
                pass
            # Restore labelpads (for title positioning)
            try:
                pads = snap.get('labelpads', {})
                if pads:
                    if pads.get('x') is not None:
                        ax.xaxis.labelpad = pads['x']
                    if pads.get('y') is not None:
                        ax.yaxis.labelpad = pads['y']
            except Exception:
                pass
            # Lines (by index)
            try:
                if len(ax.lines) == len(snap.get('lines', [])):
                    for item in snap['lines']:
                        idx = item.get('index')
                        if idx is None or idx >= len(ax.lines):
                            continue
                        ln = ax.lines[idx]
                        if 'x' in item and 'y' in item:
                            ln.set_data(item['x'], item['y'])
                        if item.get('color') is not None:
                            ln.set_color(item['color'])
                        if item.get('lw') is not None:
                            ln.set_linewidth(item['lw'])
                        if item.get('ls') is not None:
                            ln.set_linestyle(item['ls'])
                        if item.get('alpha') is not None:
                            ln.set_alpha(item['alpha'])
                        if item.get('visible') is not None:
                            ln.set_visible(bool(item['visible']))
            except Exception:
                pass
            legend_snap = snap.get('legend', {})
            if legend_snap:
                try:
                    xy = legend_snap.get('position_inches')
                    fig._ec_legend_xy_in = _sanitize_legend_offset(fig, xy) if xy is not None else None
                except Exception:
                    pass
            _rebuild_legend(ax)
            if legend_snap:
                try:
                    if legend_snap.get('visible'):
                        _apply_legend_position(fig, ax)
                    leg_obj = ax.get_legend()
                    if leg_obj is not None:
                        leg_obj.set_visible(bool(legend_snap.get('visible', False)))
                except Exception:
                    pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Undo failed: {e}")
    _print_menu(len(all_cycles), is_dqdv)
    while True:
        key = input("Press a key: ").strip().lower()
        if not key:
            continue
        if key == 'q':
            try:
                confirm = input(_colorize_prompt("Quit EC interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            except Exception:
                confirm = 'y'
            if confirm == 'y':
                break
            else:
                _print_menu(len(all_cycles), is_dqdv)
                continue
        elif key == 'b':
            restore_state()
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'e':
            # Export current figure to a file; default extension .svg if missing
            try:
                base_path = choose_save_path(source_paths, purpose="figure export")
                if not base_path:
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                # List existing figure files in Figures/ subdirectory
                fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
                file_list = list_files_in_subdirectory(fig_extensions, 'figure', base_path=base_path)
                files = [f[0] for f in file_list]
                if files:
                    figures_dir = os.path.join(base_path, 'Figures')
                    print(f"Existing figure files in {figures_dir}:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                
                fname = input("Export filename (default .svg if no extension) or number to overwrite (q=cancel): ").strip()
                if not fname or fname.lower() == 'q':
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                
                # Check if user selected a number
                already_confirmed = False
                if fname.isdigit() and files:
                    idx = int(fname)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(len(all_cycles), is_dqdv)
                            continue
                        target = file_list[idx-1][1]  # Full path from list
                        already_confirmed = True
                    else:
                        print("Invalid number.")
                        _print_menu(len(all_cycles), is_dqdv)
                        continue
                else:
                    root, ext = os.path.splitext(fname)
                    if ext == '':
                        fname = fname + '.svg'
                    # Use organized path unless it's an absolute path
                    if os.path.isabs(fname):
                        target = fname
                    else:
                        target = get_organized_path(fname, 'figure', base_path=base_path)
                
                try:
                    if not already_confirmed and os.path.exists(target):
                        target = _confirm_overwrite(target)
                    if target:
                        # If exporting SVG, make background transparent for PowerPoint
                        _, ext2 = os.path.splitext(target)
                        ext2 = ext2.lower()
                        if ext2 == '.svg':
                            # Save original patch states
                            try:
                                fig_fc = fig.get_facecolor()
                            except Exception:
                                fig_fc = None
                            try:
                                ax_fc = ax.get_facecolor()
                            except Exception:
                                ax_fc = None
                            try:
                                # Set transparent patches
                                if getattr(fig, 'patch', None) is not None:
                                    fig.patch.set_alpha(0.0)
                                    fig.patch.set_facecolor('none')
                                if getattr(ax, 'patch', None) is not None:
                                    ax.patch.set_alpha(0.0)
                                    ax.patch.set_facecolor('none')
                            except Exception:
                                pass
                            try:
                                fig.savefig(target, bbox_inches='tight', transparent=True, facecolor='none', edgecolor='none')
                            finally:
                                # Restore original patches if available
                                try:
                                    if fig_fc is not None and getattr(fig, 'patch', None) is not None:
                                        fig.patch.set_alpha(1.0)
                                        fig.patch.set_facecolor(fig_fc)
                                except Exception:
                                    pass
                                try:
                                    if ax_fc is not None and getattr(ax, 'patch', None) is not None:
                                        ax.patch.set_alpha(1.0)
                                        ax.patch.set_facecolor(ax_fc)
                                except Exception:
                                    pass
                        else:
                            fig.savefig(target, bbox_inches='tight')
                        print(f"Exported figure to {target}")
                except Exception as e:
                    print(f"Export failed: {e}")
            except Exception as e:
                print(f"Error exporting figure: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'h':
            # Legend submenu: toggle visibility and move legend in inches relative to canvas center
            try:
                fig = ax.figure
                # Ensure resize hook to reapply custom position
                if not hasattr(fig, '_ec_legpos_cid') or getattr(fig, '_ec_legpos_cid') is None:
                    def _on_resize_ec(event):
                        try:
                            leg = ax.get_legend()
                            if leg is None or not leg.get_visible():
                                return
                            if _apply_legend_position(fig, ax):
                                fig.canvas.draw_idle()
                        except Exception:
                            pass
                    fig._ec_legpos_cid = fig.canvas.mpl_connect('resize_event', _on_resize_ec)
                # If we don't yet have a stored inches position, derive it from current legend
                try:
                    if not hasattr(fig, '_ec_legend_xy_in') or getattr(fig, '_ec_legend_xy_in') is None:
                        leg0 = ax.get_legend()
                        if leg0 is not None:
                            try:
                                try:
                                    renderer = fig.canvas.get_renderer()
                                except Exception:
                                    fig.canvas.draw()
                                    renderer = fig.canvas.get_renderer()
                                bb = leg0.get_window_extent(renderer=renderer)
                                cx = 0.5 * (bb.x0 + bb.x1)
                                cy = 0.5 * (bb.y0 + bb.y1)
                                fx, fy = fig.transFigure.inverted().transform((cx, cy))
                                fw, fh = fig.get_size_inches()
                                offset = _sanitize_legend_offset(fig, ((fx - 0.5) * fw, (fy - 0.5) * fh))
                                if offset is not None:
                                    fig._ec_legend_xy_in = offset
                            except Exception:
                                pass
                except Exception:
                    pass
                # Current status
                leg = ax.get_legend()
                vis = bool(leg.get_visible()) if leg is not None else False
                xy_in = _sanitize_legend_offset(fig, getattr(fig, '_ec_legend_xy_in', (0.0, 0.0))) or (0.0, 0.0)
                print(f"Legend is {'ON' if vis else 'off'}; position (inches from center): x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                while True:
                    sub = input(_colorize_prompt("Legend: (t=toggle, m=set position, q=back): ")).strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 't':
                        try:
                            leg = ax.get_legend()
                            if leg is not None and leg.get_visible():
                                leg.set_visible(False)
                                _set_legend_user_pref(fig, False)
                                _rebuild_legend(ax)
                            else:
                                _set_legend_user_pref(fig, True)
                                _rebuild_legend(ax)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    elif sub == 'm':
                        xy_in = _sanitize_legend_offset(fig, getattr(fig, '_ec_legend_xy_in', (0.0, 0.0))) or (0.0, 0.0)
                        print(f"Current position: x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                        vals = input("Enter legend position x y (inches from center; e.g., 0.0 0.0): ").strip()
                        parts = vals.replace(',', ' ').split()
                        if len(parts) != 2:
                            print("Need two numbers."); continue
                        try:
                            x_in = float(parts[0]); y_in = float(parts[1])
                        except Exception:
                            print("Invalid numbers."); continue
                        try:
                            fig._ec_legend_xy_in = _sanitize_legend_offset(fig, (x_in, y_in))
                            # If legend visible, reposition now
                            leg = ax.get_legend()
                            if leg is not None and leg.get_visible():
                                if not _apply_legend_position(fig, ax):
                                    handles, labels = _visible_legend_entries(ax)
                                    if handles:
                                        _legend_no_frame(ax, handles, labels, loc='best', borderaxespad=1.0)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    else:
                        print("Unknown option.")
            except Exception:
                pass
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'p':
            # Print/export style or style+geometry
            try:
                style_menu_active = True
                while style_menu_active:
                    # Print style info first
                    cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state)
                    cfg['kind'] = 'ec_style'  # Default, will be updated if psg is chosen
                    _print_style_snapshot(cfg)
                    
                    # List available style files (.bps, .bpsg, .bpcfg) in Styles/ subdirectory
                    style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
                    _bpcfg_files = [f[0] for f in style_file_list]
                    if _bpcfg_files:
                        print("Existing style files in Styles/ (.bps/.bpsg):")
                        for _i, _f in enumerate(_bpcfg_files, 1):
                            print(f"  {_i}: {_f}")
                    
                    sub = input(_colorize_prompt("Style submenu: (e=export, q=return, r=refresh): ")).strip().lower()
                    if sub == 'q':
                        break
                    if sub == 'r' or sub == '':
                        continue
                    if sub == 'e':
                        # Ask for ps or psg
                        print("Export options:")
                        print("  ps  = style only (.bps)")
                        print("  psg = style + geometry (.bpsg)")
                        exp_choice = input(_colorize_prompt("Export choice (ps/psg, q=cancel): ")).strip().lower()
                        if not exp_choice or exp_choice == 'q':
                            print("Style export canceled.")
                            continue
                        
                        if exp_choice == 'ps':
                            # Style only
                            cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state)
                            cfg['kind'] = 'ec_style'
                            default_ext = '.bps'
                        elif exp_choice == 'psg':
                            # Style + Geometry
                            cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state)
                            geom = _get_geometry_snapshot(fig, ax)
                            cfg['kind'] = 'ec_style_geom'
                            cfg['geometry'] = geom
                            default_ext = '.bpsg'
                            print("\n--- Geometry ---")
                            print(f"X-axis label: {geom['xlabel']}")
                            print(f"Y-axis label: {geom['ylabel']}")
                            print(f"X limits: {geom['xlim'][0]:.4g} to {geom['xlim'][1]:.4g}")
                            print(f"Y limits: {geom['ylim'][0]:.4g} to {geom['ylim'][1]:.4g}")
                        else:
                            print(f"Unknown option: {exp_choice}")
                            continue
                        
                        save_base = choose_save_path(source_paths, purpose="style export")
                        if not save_base:
                            print("Style export canceled.")
                            continue
                        _export_style_dialog(cfg, default_ext=default_ext, base_path=save_base)
                        style_menu_active = False  # Exit style submenu and return to main menu
                        break
                    else:
                        print("Unknown choice.")
            except Exception as e:
                print(f"Error in style submenu: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'i':
            # Import style from .bps/.bpsg/.bpcfg
            try:
                path = choose_style_file(source_paths, purpose="style import")
                if not path:
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                push_state("import-style")
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                
                # Check file type
                kind = cfg.get('kind', '')
                if kind not in ('ec_style', 'ec_style_geom'):
                    print("Not an EC style file.")
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                
                has_geometry = (kind == 'ec_style_geom' and 'geometry' in cfg)
                
                # Save current labelpad values and axes position BEFORE any style changes
                saved_xlabelpad = None
                saved_ylabelpad = None
                saved_axes_position = None
                try:
                    saved_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
                except Exception:
                    pass
                try:
                    saved_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
                except Exception:
                    pass
                try:
                    # Save current axes position to detect if it actually changes
                    saved_axes_position = ax.get_position()
                except Exception:
                    pass
                
                # --- Apply comprehensive style (no curve data) ---
                # Figure and font
                try:
                    fig_cfg = cfg.get('figure', {})
                    # Get axes_fraction BEFORE changing canvas size (to preserve exact position)
                    axes_frac = fig_cfg.get('axes_fraction')
                    frame_size = fig_cfg.get('frame_size')
                    
                    canvas_size = fig_cfg.get('canvas_size')
                    if canvas_size and isinstance(canvas_size, list) and len(canvas_size) == 2:
                        # Use forward=False to prevent automatic subplot adjustment that can shift the plot
                        # We'll restore axes_fraction immediately after to set exact position
                        fig.set_size_inches(canvas_size[0], canvas_size[1], forward=False)
                    
                    # Frame position: prefer axes_fraction (exact position), fall back to centering based on frame_size
                    axes_position_changed = False
                    if axes_frac and isinstance(axes_frac, (list, tuple)) and len(axes_frac) == 4:
                        # Restore exact position from axes_fraction (this overrides any automatic adjustments)
                        x0, y0, w, h = axes_frac
                        left = float(x0)
                        bottom = float(y0)
                        right = left + float(w)
                        top = bottom + float(h)
                        if 0 < left < right <= 1 and 0 < bottom < top <= 1:
                            # Check if axes position actually changed
                            if saved_axes_position is not None:
                                tol = 1e-6
                                if (abs(saved_axes_position.x0 - left) > tol or
                                    abs(saved_axes_position.y0 - bottom) > tol or
                                    abs(saved_axes_position.width - w) > tol or
                                    abs(saved_axes_position.height - h) > tol):
                                    axes_position_changed = True
                                    # Only call subplots_adjust if position actually changed
                                    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
                            else:
                                axes_position_changed = True
                                fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
                    elif frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                        # Fall back to centering based on frame_size (for backward compatibility)
                        fw_in, fh_in = frame_size
                        canvas_w, canvas_h = fig.get_size_inches()
                        if canvas_w > 0 and canvas_h > 0:
                            min_margin = 0.05
                            w_frac = min(fw_in / canvas_w, 1 - 2 * min_margin)
                            h_frac = min(fh_in / canvas_h, 1 - 2 * min_margin)
                            left = (1 - w_frac) / 2
                            bottom = (1 - h_frac) / 2
                            # Check if axes position actually changed
                            if saved_axes_position is not None:
                                tol = 1e-6
                                new_pos = (left, bottom, w_frac, h_frac)
                                if (abs(saved_axes_position.x0 - new_pos[0]) > tol or
                                    abs(saved_axes_position.y0 - new_pos[1]) > tol or
                                    abs(saved_axes_position.width - new_pos[2]) > tol or
                                    abs(saved_axes_position.height - new_pos[3]) > tol):
                                    axes_position_changed = True
                                    # Only call subplots_adjust if position actually changed
                                    fig.subplots_adjust(left=left, right=left + w_frac, bottom=bottom, top=bottom + h_frac)
                            else:
                                axes_position_changed = True
                                fig.subplots_adjust(left=left, right=left + w_frac, bottom=bottom, top=bottom + h_frac)
                    
                    font_cfg = cfg.get('font', {})
                    if font_cfg.get('family'):
                        _apply_font_family(ax, font_cfg['family'])
                    if font_cfg.get('size') is not None:
                        _apply_font_size(ax, float(font_cfg['size']))
                except Exception as e:
                    print(f"Warning: Could not apply figure/font settings: {e}")

                # WASD state and dependent components
                try:
                    wasd_state = cfg.get('wasd_state')
                    if wasd_state and isinstance(wasd_state, dict):
                        # Apply spines
                        for name in ('top','bottom','left','right'):
                            side = wasd_state.get(name, {})
                            if name in ax.spines and 'spine' in side:
                                ax.spines[name].set_visible(bool(side['spine']))
                        
                        # Apply major ticks & labels
                        top_s = wasd_state.get('top', {})
                        bot_s = wasd_state.get('bottom', {})
                        left_s = wasd_state.get('left', {})
                        right_s = wasd_state.get('right', {})
                        
                        ax.tick_params(axis='x', 
                                      top=bool(top_s.get('ticks', False)), 
                                      bottom=bool(bot_s.get('ticks', True)),
                                      labeltop=bool(top_s.get('labels', False)), 
                                      labelbottom=bool(bot_s.get('labels', True)))
                        ax.tick_params(axis='y', 
                                      left=bool(left_s.get('ticks', True)), 
                                      right=bool(right_s.get('ticks', False)),
                                      labelleft=bool(left_s.get('labels', True)), 
                                      labelright=bool(right_s.get('labels', False)))
                        
                        # Apply minor ticks - only set locator if minor ticks are enabled, otherwise clear it
                        if top_s.get('minor') or bot_s.get('minor'):
                            ax.xaxis.set_minor_locator(AutoMinorLocator())
                            ax.xaxis.set_minor_formatter(NullFormatter())
                        else:
                            # Clear minor locator if no minor ticks are enabled
                            ax.xaxis.set_minor_locator(NullLocator())
                            ax.xaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='x', which='minor', 
                                      top=bool(top_s.get('minor', False)), 
                                      bottom=bool(bot_s.get('minor', False)), 
                                      labeltop=False, labelbottom=False)
                        
                        if left_s.get('minor') or right_s.get('minor'):
                            ax.yaxis.set_minor_locator(AutoMinorLocator())
                            ax.yaxis.set_minor_formatter(NullFormatter())
                        else:
                            # Clear minor locator if no minor ticks are enabled
                            ax.yaxis.set_minor_locator(NullLocator())
                            ax.yaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='y', which='minor', 
                                      left=bool(left_s.get('minor', False)), 
                                      right=bool(right_s.get('minor', False)), 
                                      labelleft=False, labelright=False)
                        
                        # Apply axis titles
                        ax._top_xlabel_on = bool(top_s.get('title', False))
                        ax._right_ylabel_on = bool(right_s.get('title', False))
                        
                        # Update tick_state for consistency
                        tick_state['t_ticks'] = bool(top_s.get('ticks', False))
                        tick_state['t_labels'] = bool(top_s.get('labels', False))
                        tick_state['b_ticks'] = bool(bot_s.get('ticks', True))
                        tick_state['b_labels'] = bool(bot_s.get('labels', True))
                        tick_state['l_ticks'] = bool(left_s.get('ticks', True))
                        tick_state['l_labels'] = bool(left_s.get('labels', True))
                        tick_state['r_ticks'] = bool(right_s.get('ticks', False))
                        tick_state['r_labels'] = bool(right_s.get('labels', False))
                        tick_state['mtx'] = bool(top_s.get('minor', False))
                        tick_state['mbx'] = bool(bot_s.get('minor', False))
                        tick_state['mly'] = bool(left_s.get('minor', False))
                        tick_state['mry'] = bool(right_s.get('minor', False))
                        
                        # Don't reposition labels here - do it at the end after all style changes
                        # This prevents font changes and other operations from triggering unnecessary recalculations
                        
                except Exception as e:
                    print(f"Warning: Could not apply tick visibility: {e}")

                # Spines and Ticks (widths)
                try:
                    spines_cfg = cfg.get('spines', {})
                    for name, props in spines_cfg.items():
                        if name in ax.spines:
                            if props.get('linewidth') is not None:
                                ax.spines[name].set_linewidth(props['linewidth'])
                            if props.get('color') is not None:
                                _apply_spine_color(ax, fig, tick_state, name, props['color'])
                    
                    tick_widths = cfg.get('ticks', {}).get('widths', {})
                    if tick_widths.get('x_major') is not None: ax.tick_params(axis='x', which='major', width=tick_widths['x_major'])
                    if tick_widths.get('x_minor') is not None: ax.tick_params(axis='x', which='minor', width=tick_widths['x_minor'])
                    if tick_widths.get('y_major') is not None: ax.tick_params(axis='y', which='major', width=tick_widths['y_major'])
                    if tick_widths.get('y_minor') is not None: ax.tick_params(axis='y', which='minor', width=tick_widths['y_minor'])
                    
                    # Apply tick direction
                    tick_direction = cfg.get('ticks', {}).get('direction', 'out')
                    if tick_direction:
                        setattr(fig, '_tick_direction', tick_direction)
                        ax.tick_params(axis='both', which='both', direction=tick_direction)
                except Exception: pass
                
                # Grid state
                try:
                    grid_enabled = cfg.get('grid', False)
                    if grid_enabled:
                        ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                    else:
                        ax.grid(False)
                except Exception: pass
                
                # Rotation angle
                try:
                    rotation_angle = cfg.get('rotation_angle', 0)
                    setattr(fig, '_ec_rotation_angle', rotation_angle)
                except Exception: pass
                
                # Curve linewidth (single value for all curves)
                try:
                    curve_linewidth = cfg.get('curve_linewidth')
                    if curve_linewidth is not None:
                        # Store globally on fig so it persists
                        setattr(fig, '_ec_curve_linewidth', float(curve_linewidth))
                        # Apply to all curves
                        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                            try:
                                ln.set_linewidth(float(curve_linewidth))
                            except Exception:
                                pass
                except Exception: pass
                
                # Curve marker properties (linestyle, marker, markersize, colors)
                try:
                    curve_markers = cfg.get('curve_markers', {})
                    if curve_markers:
                        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                            try:
                                if 'linestyle' in curve_markers:
                                    ln.set_linestyle(curve_markers['linestyle'])
                                if 'marker' in curve_markers:
                                    ln.set_marker(curve_markers['marker'])
                                if 'markersize' in curve_markers:
                                    ln.set_markersize(curve_markers['markersize'])
                                if 'markerfacecolor' in curve_markers:
                                    ln.set_markerfacecolor(curve_markers['markerfacecolor'])
                                if 'markeredgecolor' in curve_markers:
                                    ln.set_markeredgecolor(curve_markers['markeredgecolor'])
                            except Exception:
                                pass
                except Exception: pass

                # Legend visibility/position
                legend_cfg = cfg.get('legend', {}) or {}
                legend_visible = None
                try:
                    if legend_cfg:
                        legend_visible = bool(legend_cfg.get('visible', True))
                        xy = legend_cfg.get('position_inches')
                        if xy is not None:
                            fig._ec_legend_xy_in = _sanitize_legend_offset(fig, xy)
                        else:
                            fig._ec_legend_xy_in = None
                        if 'title' in legend_cfg and legend_cfg['title']:
                            fig._ec_legend_title = legend_cfg['title']
                        fig._ec_legend_user_visible = bool(legend_visible)
                except Exception:
                    legend_visible = None
                
                cycle_styles_cfg = cfg.get('cycle_styles')
                if cycle_styles_cfg:
                    _apply_cycle_styles(cycle_lines, cycle_styles_cfg)
                
                # Apply geometry if present (before final repositioning)
                if has_geometry:
                    try:
                        geom = cfg.get('geometry', {})
                        if 'xlabel' in geom and geom['xlabel']:
                            ax.set_xlabel(geom['xlabel'])
                        if 'ylabel' in geom and geom['ylabel']:
                            ax.set_ylabel(geom['ylabel'])
                        if 'xlim' in geom and isinstance(geom['xlim'], list) and len(geom['xlim']) == 2:
                            ax.set_xlim(geom['xlim'][0], geom['xlim'][1])
                        if 'ylim' in geom and isinstance(geom['ylim'], list) and len(geom['ylim']) == 2:
                            ax.set_ylim(geom['ylim'][0], geom['ylim'][1])
                        print("Applied geometry (labels and limits)")
                    except Exception as e:
                        print(f"Warning: Could not apply geometry: {e}")
                
                # Final label positioning - do this AFTER all style changes to prevent drift
                # Set pending labelpad before repositioning to preserve original values
                try:
                    if saved_xlabelpad is not None:
                        ax._pending_xlabelpad = saved_xlabelpad
                    if saved_ylabelpad is not None:
                        ax._pending_ylabelpad = saved_ylabelpad
                    
                    # Only reposition if axes position actually changed OR if fonts changed
                    # This prevents unnecessary movement when nothing actually changed
                    font_cfg = cfg.get('font', {})
                    font_changed = (font_cfg.get('family') is not None or font_cfg.get('size') is not None)
                    
                    if axes_position_changed or font_changed:
                        # Reposition titles (will use _pending_xlabelpad if set, preserving original labelpad)
                        _ui_position_top_xlabel(ax, fig, tick_state)
                        _ui_position_bottom_xlabel(ax, fig, tick_state)
                        _ui_position_left_ylabel(ax, fig, tick_state)
                        _ui_position_right_ylabel(ax, fig, tick_state)
                    
                    # Always ensure labelpad is exactly as it was before style import
                    # This is a final safeguard against any drift
                    if saved_xlabelpad is not None:
                        ax.xaxis.labelpad = saved_xlabelpad
                    if saved_ylabelpad is not None:
                        ax.yaxis.labelpad = saved_ylabelpad
                except Exception:
                    pass
                
                # Rebuild and reposition legend after all changes (including figure size changes)
                _rebuild_legend(ax)
                if legend_cfg:
                    try:
                        if legend_visible:
                            _apply_legend_position(fig, ax)
                        leg = ax.get_legend()
                        if leg is not None:
                            leg.set_visible(bool(legend_visible))
                        _set_legend_user_pref(fig, bool(legend_visible))
                    except Exception:
                        pass
                
                fig.canvas.draw_idle()
                print(f"Applied style from {path}")

            except Exception as e:
                print(f"Error importing style: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'l':
            # Line widths submenu: curves vs frame/ticks
            try:
                def _tick_width(axis_obj, which: str):
                    try:
                        tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
                        width = tick_kw.get('width')
                        if width is None:
                            axis_name = getattr(axis_obj, 'axis_name', 'x')
                            rc_key = f"{axis_name}tick.{which}.width"
                            width = plt.rcParams.get(rc_key)
                        if width is not None:
                            return float(width)
                    except Exception:
                        return None
                    return None
                while True:
                    # Show current widths summary
                    try:
                        cur_sp_lw = {name: (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None)
                                      for name in ('bottom','top','left','right')}
                    except Exception:
                        cur_sp_lw = {}
                    x_maj = _tick_width(ax.xaxis, 'major')
                    x_min = _tick_width(ax.xaxis, 'minor')
                    y_maj = _tick_width(ax.yaxis, 'major')
                    y_min = _tick_width(ax.yaxis, 'minor')
                    # Curve linewidth: get single stored value or from first curve
                    cur_curve_lw = getattr(fig, '_ec_curve_linewidth', None)
                    if cur_curve_lw is None:
                        try:
                            for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                                try:
                                    cur_curve_lw = float(ln.get_linewidth() or 1.0)
                                    break
                                except Exception:
                                    pass
                                if cur_curve_lw is not None:
                                    break
                        except Exception:
                            pass
                    print("Line widths:")
                    if cur_sp_lw:
                        print("  Frame spines lw:", 
                              " ".join(f"{k}={v:.3g}" if isinstance(v,(int,float)) else f"{k}=?" for k,v in cur_sp_lw.items()))
                    print(f"  Tick widths: xM={x_maj if x_maj is not None else '?'} xm={x_min if x_min is not None else '?'} yM={y_maj if y_maj is not None else '?'} ym={y_min if y_min is not None else '?'}")
                    if cur_curve_lw is not None:
                        print(f"  Curves (all): {cur_curve_lw:.3g}")
                    print("\033[1mLine submenu:\033[0m")
                    print(f"  {_colorize_menu('c  : change curve line widths')}")
                    print(f"  {_colorize_menu('f  : change frame (axes spines) and tick widths')}")
                    print(f"  {_colorize_menu('g  : toggle grid lines')}")
                    print(f"  {_colorize_menu('l  : show only lines (no markers) for all curves')}")
                    print(f"  {_colorize_menu('ld : show line and dots (markers) for all curves')}")
                    print(f"  {_colorize_menu('d  : show only dots (no connecting line) for all curves')}")
                    print(f"  {_colorize_menu('q  : return')}")
                    sub = input(_colorize_prompt("Choose (c/f/g/l/ld/d/q): ")).strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'c':
                        spec = input("Curve linewidth (single value for all curves, q=cancel): ").strip()
                        if not spec or spec.lower() == 'q':
                            continue
                        # Apply single width to all curves
                        try:
                            push_state("curve-linewidth")
                            lw = float(spec)
                            # Store globally on fig so it persists
                            setattr(fig, '_ec_curve_linewidth', lw)
                            # Apply to all curves
                            for cyc, parts in cycle_lines.items():
                                for role in ("charge","discharge"):
                                    ln = parts.get(role)
                                    if ln is not None:
                                        try: ln.set_linewidth(lw)
                                        except Exception: pass
                            try:
                                _rebuild_legend(ax)
                                fig.canvas.draw()
                            except Exception:
                                try:
                                    _rebuild_legend(ax)
                                except Exception:
                                    pass
                                fig.canvas.draw_idle()
                            print(f"Set all curve linewidths to {lw}")
                        except ValueError:
                            print("Invalid width value.")
                    elif sub == 'f':
                        fw_in = input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q: ").strip()
                        if not fw_in or fw_in.lower() == 'q':
                            print("Canceled.")
                            continue
                        parts = fw_in.split()
                        try:
                            push_state("framewidth")
                            if len(parts) == 1:
                                frame_w = float(parts[0])
                                tick_major = frame_w
                                tick_minor = frame_w * 0.6
                            else:
                                frame_w = float(parts[0])
                                tick_major = float(parts[1])
                                tick_minor = float(tick_major) * 0.7
                            for sp in ax.spines.values():
                                sp.set_linewidth(frame_w)
                            ax.tick_params(which='major', width=tick_major)
                            ax.tick_params(which='minor', width=tick_minor)
                            fig.canvas.draw()
                            print(f"Set frame width={frame_w}, major tick width={tick_major}, minor tick width={tick_minor}")
                        except ValueError:
                            print("Invalid numeric value(s).")
                    elif sub == 'g':
                        push_state("grid")
                        # Toggle grid state - check if any gridlines are visible
                        current_grid = False
                        try:
                            # Check if grid is currently on by looking at gridline visibility
                            for line in ax.get_xgridlines() + ax.get_ygridlines():
                                if line.get_visible():
                                    current_grid = True
                                    break
                        except Exception:
                            current_grid = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False
                        
                        new_grid_state = not current_grid
                        if new_grid_state:
                            # Enable grid with light styling
                            ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                        else:
                            # Disable grid (no style parameters when disabling)
                            ax.grid(False)
                        fig.canvas.draw()
                        print(f"Grid {'enabled' if new_grid_state else 'disabled'}.")
                    elif sub == 'l':
                        # Line-only mode: set linestyle to solid and remove markers
                        push_state("line-only")
                        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                            try:
                                # Check if already in line-only mode (has line style and no marker)
                                current_ls = ln.get_linestyle()
                                current_marker = ln.get_marker()
                                # If already line-only (has line, no marker), skip
                                if current_ls not in ['None', '', ' ', 'none'] and current_marker in ['None', '', ' ', 'none', None]:
                                    continue
                                # Otherwise, set to line-only
                                ln.set_linestyle('-')
                                ln.set_marker('None')
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax)
                            fig.canvas.draw()
                        except Exception:
                            try:
                                _rebuild_legend(ax)
                            except Exception:
                                pass
                            fig.canvas.draw_idle()
                        print("Applied line-only style to all curves.")
                    elif sub == 'ld':
                        # Line + dots for all curves
                        push_state("line+dots")
                        try:
                            msize_in = input("Marker size (blank=auto ~3*lw): ").strip()
                            custom_msize = float(msize_in) if msize_in else None
                        except ValueError:
                            custom_msize = None
                        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                            try:
                                lw = ln.get_linewidth() or 1.0
                                ln.set_linestyle('-')
                                ln.set_marker('o')
                                msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
                                ln.set_markersize(msize)
                                col = ln.get_color()
                                ln.set_markerfacecolor(col)
                                ln.set_markeredgecolor(col)
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax)
                            fig.canvas.draw()
                        except Exception:
                            try:
                                _rebuild_legend(ax)
                            except Exception:
                                pass
                            fig.canvas.draw_idle()
                        print("Applied line+dots style to all curves.")
                    elif sub == 'd':
                        # Dots only for all curves
                        push_state("dots-only")
                        try:
                            msize_in = input("Marker size (blank=auto ~3*lw): ").strip()
                            custom_msize = float(msize_in) if msize_in else None
                        except ValueError:
                            custom_msize = None
                        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                            try:
                                lw = ln.get_linewidth() or 1.0
                                ln.set_linestyle('None')
                                ln.set_marker('o')
                                msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
                                ln.set_markersize(msize)
                                col = ln.get_color()
                                ln.set_markerfacecolor(col)
                                ln.set_markeredgecolor(col)
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax)
                            fig.canvas.draw()
                        except Exception:
                            try:
                                _rebuild_legend(ax)
                            except Exception:
                                pass
                            fig.canvas.draw_idle()
                        print("Applied dots-only style to all curves.")
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in line submenu: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'k':
            # Spine colors (w=top, a=left, s=bottom, d=right)
            try:
                print("Set spine colors (with matching tick and label colors):")
                print(_colorize_inline_commands("  w : top spine    | a : left spine"))
                print(_colorize_inline_commands("  s : bottom spine | d : right spine"))
                print(_colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
                user_colors = get_user_color_list(fig)
                if user_colors:
                    print("\nSaved colors (enter number or u# to reuse):")
                    for idx, color in enumerate(user_colors, 1):
                        print(f"  {idx}: {color_block(color)} {color}")
                    print("Type 'u' to edit saved colors.")
                line = input("Enter mappings (e.g., w:red a:#4561F7) or q: ").strip()
                if line.lower() == 'u':
                    manage_user_colors(fig)
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                if line and line.lower() != 'q':
                    push_state("color-spine")
                    key_to_spine = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}
                    tokens = line.split()
                    pairs = []
                    i = 0
                    while i < len(tokens):
                        tok = tokens[i]
                        if ':' in tok:
                            key_part, color = tok.split(':', 1)
                        else:
                            if i + 1 >= len(tokens):
                                print(f"Skip incomplete entry: {tok}")
                                break
                            key_part = tok
                            color = tokens[i + 1]
                            i += 1
                        pairs.append((key_part.lower(), color))
                        i += 1
                    for key_part, color in pairs:
                        if key_part not in key_to_spine:
                            print(f"Unknown key: {key_part} (use w/a/s/d)")
                            continue
                        spine_name = key_to_spine[key_part]
                        if spine_name not in ax.spines:
                            print(f"Spine '{spine_name}' not found.")
                            continue
                        try:
                            resolved = resolve_color_token(color, fig)
                            _apply_spine_color(ax, fig, tick_state, spine_name, resolved)
                            print(f"Set {spine_name} spine to {color_block(resolved)} {resolved}")
                        except Exception as e:
                            print(f"Error setting {spine_name} color: {e}")
                    fig.canvas.draw()
                else:
                    print("Canceled.")
            except Exception as e:
                print(f"Error in spine color menu: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'r':
            # Rename axis labels
            try:
                print("Tip: Use LaTeX/mathtext for special characters:")
                print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
                print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
                while True:
                    print("Rename axis: x, y, both, q=back")
                    sub = input("Rename> ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub in ('x','both'):
                        txt = input("New X-axis label (blank=cancel): ")
                        if txt:
                            push_state("rename-x")
                            try:
                                # Freeze layout and preserve existing pad for one-shot restore
                                try: fig.set_layout_engine('none')
                                except Exception:
                                    try: fig.set_tight_layout(False)
                                    except Exception: pass
                                try: fig.set_constrained_layout(False)
                                except Exception: pass
                                try:
                                    ax._pending_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
                                except Exception:
                                    pass
                                ax.set_xlabel(txt)
                                ax._stored_xlabel = txt
                                ax._stored_xlabel_color = ax.xaxis.label.get_color()
                                _ui_position_top_xlabel(ax, fig, tick_state)
                                _ui_position_bottom_xlabel(ax, fig, tick_state)
                            except Exception:
                                pass
                    if sub in ('y','both'):
                        txt = input("New Y-axis label (blank=cancel): ")
                        if txt:
                            push_state("rename-y")
                            base_ylabel = txt
                            try:
                                try: fig.set_layout_engine('none')
                                except Exception:
                                    try: fig.set_tight_layout(False)
                                    except Exception: pass
                                try: fig.set_constrained_layout(False)
                                except Exception: pass
                                try:
                                    ax._pending_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
                                except Exception:
                                    pass
                                ax.set_ylabel(txt)
                                ax._stored_ylabel = txt
                                ax._stored_ylabel_color = ax.yaxis.label.get_color()
                                _ui_position_right_ylabel(ax, fig, tick_state)
                                _ui_position_left_ylabel(ax, fig, tick_state)
                            except Exception:
                                pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
            except Exception as e:
                print(f"Error renaming axes: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 't':
            # Unified WASD: w/a/s/d x 1..5 => spine, ticks, minor, labels, title
            try:
                wasd = getattr(fig, '_ec_wasd_state', None)
                if not isinstance(wasd, dict):
                    wasd = {
                        'top':    {'spine': _get_spine_visible('top'),    'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))), 'minor': bool(tick_state['mtx']), 'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))), 'title': bool(getattr(ax, '_top_xlabel_on', False))},
                        'bottom': {'spine': _get_spine_visible('bottom'), 'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', False))), 'minor': bool(tick_state['mbx']), 'labels': bool(tick_state.get('b_labels', tick_state.get('bx', False))), 'title': bool(ax.xaxis.label.get_visible())},
                        'left':   {'spine': _get_spine_visible('left'),   'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', False))), 'minor': bool(tick_state['mly']), 'labels': bool(tick_state.get('l_labels', tick_state.get('ly', False))), 'title': bool(ax.yaxis.label.get_visible())},
                        'right':  {'spine': _get_spine_visible('right'),  'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', False))), 'minor': bool(tick_state['mry']), 'labels': bool(tick_state.get('r_labels', tick_state.get('ry', False))), 'title': bool(getattr(ax, '_right_ylabel_on', False))},
                    }
                    setattr(fig, '_ec_wasd_state', wasd)
                def _apply_wasd(changed_sides=None):
                    # If no changed_sides specified, reposition all sides (for load style, etc.)
                    if changed_sides is None:
                        changed_sides = {'bottom', 'top', 'left', 'right'}
                    
                    # Spines
                    for name in ('top','bottom','left','right'):
                        _set_spine_visible(name, bool(wasd[name]['spine']))
                    # Major ticks & labels
                    ax.tick_params(axis='x', top=bool(wasd['top']['ticks']), bottom=bool(wasd['bottom']['ticks']),
                                   labeltop=bool(wasd['top']['labels']), labelbottom=bool(wasd['bottom']['labels']))
                    ax.tick_params(axis='y', left=bool(wasd['left']['ticks']), right=bool(wasd['right']['ticks']),
                                   labelleft=bool(wasd['left']['labels']), labelright=bool(wasd['right']['labels']))
                    # Minor X - only set locator if minor ticks are enabled, otherwise clear it
                    if wasd['top']['minor'] or wasd['bottom']['minor']:
                        ax.xaxis.set_minor_locator(AutoMinorLocator())
                        ax.xaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ax.xaxis.set_minor_locator(NullLocator())
                        ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor', top=bool(wasd['top']['minor']), bottom=bool(wasd['bottom']['minor']), labeltop=False, labelbottom=False)
                    # Minor Y - only set locator if minor ticks are enabled, otherwise clear it
                    if wasd['left']['minor'] or wasd['right']['minor']:
                        ax.yaxis.set_minor_locator(AutoMinorLocator())
                        ax.yaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ax.yaxis.set_minor_locator(NullLocator())
                        ax.yaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='y', which='minor', left=bool(wasd['left']['minor']), right=bool(wasd['right']['minor']), labelleft=False, labelright=False)
                    # Titles
                    if bool(wasd['bottom']['title']):
                        if hasattr(ax,'_stored_xlabel') and isinstance(ax._stored_xlabel,str) and ax._stored_xlabel:
                            ax.set_xlabel(ax._stored_xlabel)
                            ax.xaxis.label.set_visible(True)
                            _apply_stored_axis_colors(ax)
                    else:
                        if not hasattr(ax,'_stored_xlabel'):
                            try: ax._stored_xlabel = ax.get_xlabel()
                            except Exception: ax._stored_xlabel = ''
                        ax.set_xlabel("")
                        ax.xaxis.label.set_visible(False)
                    ax._top_xlabel_on = bool(wasd['top']['title'])
                    if bool(wasd['left']['title']):
                        if hasattr(ax,'_stored_ylabel') and isinstance(ax._stored_ylabel,str) and ax._stored_ylabel:
                            ax.set_ylabel(ax._stored_ylabel)
                            ax.yaxis.label.set_visible(True)
                            _apply_stored_axis_colors(ax)
                    else:
                        if not hasattr(ax,'_stored_ylabel'):
                            try: ax._stored_ylabel = ax.get_ylabel()
                            except Exception: ax._stored_ylabel = ''
                        ax.set_ylabel("")
                        ax.yaxis.label.set_visible(False)
                    ax._right_ylabel_on = bool(wasd['right']['title'])
                    
                    # Only reposition sides that were actually changed
                    # This prevents unnecessary title movement when toggling unrelated elements
                    if 'bottom' in changed_sides:
                        _ui_position_bottom_xlabel(ax, fig, tick_state)
                    if 'top' in changed_sides:
                        _ui_position_top_xlabel(ax, fig, tick_state)
                        _apply_stored_axis_colors(ax)
                    if 'left' in changed_sides:
                        _ui_position_left_ylabel(ax, fig, tick_state)
                    if 'right' in changed_sides:
                        _ui_position_right_ylabel(ax, fig, tick_state)
                        _apply_stored_axis_colors(ax)
                def _sync_tick_state():
                    # Write new separate keys
                    tick_state['t_ticks'] = bool(wasd['top']['ticks'])
                    tick_state['t_labels'] = bool(wasd['top']['labels'])
                    tick_state['b_ticks'] = bool(wasd['bottom']['ticks'])
                    tick_state['b_labels'] = bool(wasd['bottom']['labels'])
                    tick_state['l_ticks'] = bool(wasd['left']['ticks'])
                    tick_state['l_labels'] = bool(wasd['left']['labels'])
                    tick_state['r_ticks'] = bool(wasd['right']['ticks'])
                    tick_state['r_labels'] = bool(wasd['right']['labels'])
                    # Legacy combined flags for backward compatibility
                    tick_state['tx'] = bool(wasd['top']['ticks'] and wasd['top']['labels'])
                    tick_state['bx'] = bool(wasd['bottom']['ticks'] and wasd['bottom']['labels'])
                    tick_state['ly'] = bool(wasd['left']['ticks'] and wasd['left']['labels'])
                    tick_state['ry'] = bool(wasd['right']['ticks'] and wasd['right']['labels'])
                    # Minor ticks
                    tick_state['mtx'] = bool(wasd['top']['minor'])
                    tick_state['mbx'] = bool(wasd['bottom']['minor'])
                    tick_state['mly'] = bool(wasd['left']['minor'])
                    tick_state['mry'] = bool(wasd['right']['minor'])
                while True:
                    print(_colorize_inline_commands("WASD toggles: direction (w/a/s/d) x action (1..5)"))
                    print(_colorize_inline_commands("  1=spine   2=ticks   3=minor ticks   4=tick labels   5=axis title"))
                    print(_colorize_inline_commands("Type 'i' to invert tick direction, 'l' to change tick length, 'list' for state, 'q' to return."))
                    print(_colorize_inline_commands("  p = adjust title offsets (w=top, s=bottom, a=left, d=right)"))
                    cmd = input(_colorize_prompt("t> ")).strip().lower()
                    if not cmd:
                        continue
                    if cmd == 'q':
                        break
                    if cmd == 'i':
                        # Invert tick direction (toggle between 'out' and 'in')
                        push_state("tick-direction")
                        current_dir = getattr(fig, '_tick_direction', 'out')
                        new_dir = 'in' if current_dir == 'out' else 'out'
                        setattr(fig, '_tick_direction', new_dir)
                        ax.tick_params(axis='both', which='both', direction=new_dir)
                        print(f"Tick direction: {new_dir}")
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                        continue
                    if cmd == 'p':
                        _title_offset_menu()
                        continue
                    if cmd == 'l':
                        # Change tick length (major and minor automatically set to 70%)
                        try:
                            # Get current major tick length from axes
                            current_major = ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() if ax.xaxis.get_major_ticks() else 4.0
                            print(f"Current major tick length: {current_major}")
                            new_length_str = input("Enter new major tick length (e.g., 6.0): ").strip()
                            if not new_length_str:
                                continue
                            new_major = float(new_length_str)
                            if new_major <= 0:
                                print("Length must be positive.")
                                continue
                            new_minor = new_major * 0.7  # Auto-set minor to 70%
                            push_state("tick-length")
                            # Apply to all four axes
                            ax.tick_params(axis='both', which='major', length=new_major)
                            ax.tick_params(axis='both', which='minor', length=new_minor)
                            # Store for persistence
                            if not hasattr(fig, '_tick_lengths'):
                                fig._tick_lengths = {}
                            fig._tick_lengths.update({'major': new_major, 'minor': new_minor})
                            print(f"Set major tick length: {new_major}, minor: {new_minor:.2f}")
                            try:
                                fig.canvas.draw()
                            except Exception:
                                fig.canvas.draw_idle()
                        except ValueError:
                            print("Invalid number.")
                        except Exception as e:
                            print(f"Error setting tick length: {e}")
                        continue
                    if cmd == 'list':
                        print(_colorize_inline_commands("Spine/ticks state:"))
                        def b(v): return 'ON' if bool(v) else 'off'
                        print(_colorize_inline_commands(f"top    w1:{b(wasd['top']['spine'])} w2:{b(wasd['top']['ticks'])} w3:{b(wasd['top']['minor'])} w4:{b(wasd['top']['labels'])} w5:{b(wasd['top']['title'])}"))
                        print(_colorize_inline_commands(f"bottom s1:{b(wasd['bottom']['spine'])} s2:{b(wasd['bottom']['ticks'])} s3:{b(wasd['bottom']['minor'])} s4:{b(wasd['bottom']['labels'])} s5:{b(wasd['bottom']['title'])}"))
                        print(_colorize_inline_commands(f"left   a1:{b(wasd['left']['spine'])} a2:{b(wasd['left']['ticks'])} a3:{b(wasd['left']['minor'])} a4:{b(wasd['left']['labels'])} a5:{b(wasd['left']['title'])}"))
                        print(_colorize_inline_commands(f"right  d1:{b(wasd['right']['spine'])} d2:{b(wasd['right']['ticks'])} d3:{b(wasd['right']['minor'])} d4:{b(wasd['right']['labels'])} d5:{b(wasd['right']['title'])}"))
                        continue
                    push_state("wasd-toggle")
                    changed = False
                    changed_sides = set()  # Track which sides were affected
                    for p in cmd.split():
                        if len(p) != 2:
                            print(f"Unknown code: {p}"); continue
                        side = {'w':'top','a':'left','s':'bottom','d':'right'}.get(p[0])
                        if side is None or p[1] not in '12345':
                            print(f"Unknown code: {p}"); continue
                        key = {'1':'spine','2':'ticks','3':'minor','4':'labels','5':'title'}[p[1]]
                        wasd[side][key] = not bool(wasd[side][key])
                        changed = True
                        # Track which side was changed to only reposition affected sides
                        # Labels and titles affect positioning, but spine/tick toggles don't necessarily
                        if key in ('labels', 'title'):
                            changed_sides.add(side)
                    if changed:
                        _sync_tick_state()
                        _apply_wasd(changed_sides if changed_sides else None)
                        _update_tick_visibility()
                        # Single draw at the end after all positioning is complete
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
            except Exception as e:
                print(f"Error in WASD tick visibility menu: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 's':
            try:
                from .session import dump_ec_session
                folder = choose_save_path(source_paths, purpose="EC session save")
                if not folder:
                    _print_menu(len(all_cycles), is_dqdv); continue
                try:
                    files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')])
                except Exception:
                    files = []
                if files:
                    print("Existing .pkl files:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                prompt = "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
                choice = input(prompt).strip()
                if not choice or choice.lower() == 'q':
                    _print_menu(len(all_cycles), is_dqdv); continue
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(len(all_cycles), is_dqdv); continue
                        target = os.path.join(folder, name)
                    else:
                        print("Invalid number.")
                        _print_menu(len(all_cycles), is_dqdv); continue
                else:
                    name = choice
                    root, ext = os.path.splitext(name)
                    if ext == '':
                        name = name + '.pkl'
                    target = name if os.path.isabs(name) else os.path.join(folder, name)
                    if os.path.exists(target):
                        yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(len(all_cycles), is_dqdv); continue
                dump_ec_session(target, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
            except Exception as e:
                print(f"Save failed: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'c':
            print(f"Total cycles: {len(all_cycles)}")
            print("Enter one of:")
            print(_colorize_inline_commands("  - numbers: e.g. 1 5 10"))
            print(_colorize_inline_commands("  - mappings: e.g. 1 red 5 u3  OR  1:red 5:#00B006"))
            print(_colorize_inline_commands("  - numbers + palette: e.g. 1 5 10 viridis  OR  1 5 10 3"))
            print(_colorize_inline_commands("  - all (optionally with palette): e.g. all  OR  all viridis  OR  all 3"))
            print("\nRecommended palettes for scientific publications:")
            rec_palettes = [
                ("tab10", "Distinct, colorblind-friendly (default matplotlib)"),
                ("Set2", "Soft, pastel colors for presentations"),
                ("Dark2", "Bold, saturated colors for print"),
                ("viridis", "Perceptually uniform (blue→yellow)"),
                ("plasma", "Perceptually uniform (purple→yellow)"),
            ]
            for idx, (name, desc) in enumerate(rec_palettes, 1):
                bar = palette_preview(name)
                print(f"  {idx}. {name} - {desc}")
                if bar:
                    print(f"      {bar}")
            print("  (Enter palette name OR number)")
            user_colors = get_user_color_list(fig)
            if user_colors:
                print("\nSaved colors (use number or u# in mappings):")
                for idx, color in enumerate(user_colors, 1):
                    print(f"  {idx}: {color_block(color)} {color}")
                print("Type 'u' to edit saved colors before assigning.")
            line = input("Selection: ").strip()
            if not line:
                continue
            if line.lower() == 'u':
                manage_user_colors(fig)
                _print_menu(len(all_cycles), is_dqdv)
                continue
            tokens = line.replace(',', ' ').split()
            mode, cycles, mapping, palette, use_all = _parse_cycle_tokens(tokens, fig)
            push_state("cycles/colors")

            # Filter to existing cycles and report ignored
            if use_all:
                existing = list(all_cycles)
                ignored = []
            else:
                existing = []
                ignored = []
                for c in cycles:
                    if c in cycle_lines:
                        existing.append(c)
                    else:
                        ignored.append(c)
            if not existing and mode != 'numbers':  # numbers mode can be empty too; handle below
                print("No valid cycles found.")
            # Update visibility
            if existing:
                _set_visible_cycles(cycle_lines, existing)
            else:
                # If nothing valid provided, keep current visibility
                print("No valid cycles provided; keeping current visibility.")

            # Apply coloring by mode
            if mode == 'map' and mapping:
                # Keep only existing cycles in mapping
                mapping2 = {c: mapping[c] for c in existing if c in mapping}
                _apply_colors(cycle_lines, mapping2)
                if mapping2:
                    print("Applied manual colors:")
                    for cyc, col in mapping2.items():
                        print(f"  Cycle {cyc}: {color_block(col)} {col}")
            elif mode == 'palette' and existing:
                try:
                    cmap = cm.get_cmap(palette) if palette else None
                except Exception:
                    cmap = None
                if cmap is None:
                    print(f"Unknown colormap '{palette}'.")
                else:
                    n = len(existing)
                    if n == 1:
                        cols = [cmap(0.55)]
                    elif n == 2:
                        cols = [cmap(0.15), cmap(0.85)]
                    else:
                        cols = [cmap(t) for t in np.linspace(0.08, 0.88, n)]
                    _apply_colors(cycle_lines, {c: col for c, col in zip(existing, cols)})
                    try:
                        preview = color_bar([mcolors.to_hex(col) for col in cols])
                    except Exception:
                        preview = ""
                    if preview:
                        print(f"Palette '{palette}' applied: {preview}")
            elif mode == 'numbers' and existing:
                # Do not change colors in numbers-only mode; only visibility changes.
                pass

            # Reapply curve linewidth (in case it was set)
            _apply_curve_linewidth(fig, cycle_lines)
            
            # Rebuild legend and redraw
            _rebuild_legend(ax)
            _apply_nice_ticks()
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()

            if ignored:
                print("Ignored cycles:", ", ".join(str(c) for c in ignored))
            # Show the menu again after completing the command
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'a':
            # X-axis submenu: number-of-ions vs capacity (not available in dQdV mode)
            if is_dqdv:
                print("Capacity/ion conversion is not available in dQ/dV mode.")
                _print_menu(len(all_cycles), is_dqdv)
                continue
            # X-axis submenu: number-of-ions vs capacity
            while True:
                print("X-axis menu: n=number of ions, c=capacity, q=back")
                sub = input("X> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'n':
                    print("Input the theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                    val = input("C_theoretical_per_ion: ").strip()
                    try:
                        c_th = float(val)
                        if c_th <= 0:
                            print("Theoretical capacity must be positive.")
                            continue
                    except Exception:
                        print("Invalid number.")
                        continue
                    # Store original x-data once, then set new x = orig_x / c_th
                    push_state("x=n(ions)")
                    for ln in ax.lines:
                        try:
                            if not hasattr(ln, "_orig_xdata_gc"):
                                x0 = np.asarray(ln.get_xdata(), dtype=float)
                                setattr(ln, "_orig_xdata_gc", x0.copy())
                            x_orig = getattr(ln, "_orig_xdata_gc")
                            ln.set_xdata(x_orig / c_th)
                        except Exception:
                            continue
                    # Construct label with proper mathtext for superscript
                    # Configure mathtext fontset BEFORE setting the label to ensure consistency
                    try:
                        import matplotlib.pyplot as plt
                        import matplotlib as mpl
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        
                        # Configure mathtext to use the same font family
                        if font_fam_str:
                            # Configure mathtext fontset to match the regular font
                            # For Arial-like fonts, use dejavusans; for Times/STIX, use stix
                            lf = font_fam_str.lower()
                            if any(k in lf for k in ('stix', 'times', 'roman')):
                                mpl.rcParams['mathtext.fontset'] = 'stix'
                            else:
                                # Use dejavusans for Arial, Helvetica, etc. (closest match to Arial)
                                mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                            mpl.rcParams['mathtext.default'] = 'regular'
                    except Exception:
                        pass
                    
                    label_text = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                    ax.set_xlabel(label_text)
                    
                    # Apply current font settings to the label to ensure consistency
                    try:
                        import matplotlib.pyplot as plt
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        font_size = plt.rcParams.get('font.size', None)
                        if font_fam_str:
                            ax.xaxis.label.set_family(font_fam_str)
                        if font_size is not None:
                            ax.xaxis.label.set_size(font_size)
                        # Force label to re-render with updated mathtext fontset by updating the text
                        ax.set_xlabel(label_text)
                    except Exception:
                        pass
                    _apply_nice_ticks()
                    try:
                        ax.relim(); ax.autoscale_view()
                    except Exception:
                        pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                elif sub == 'c':
                    # Restore original capacity on x if available
                    push_state("x=capacity")
                    any_restored = False
                    for ln in ax.lines:
                        try:
                            if hasattr(ln, "_orig_xdata_gc"):
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                ln.set_xdata(x_orig)
                                any_restored = True
                        except Exception:
                            continue
                    # Construct label with proper mathtext for superscript
                    # Configure mathtext fontset BEFORE setting the label to ensure consistency
                    try:
                        import matplotlib.pyplot as plt
                        import matplotlib as mpl
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        
                        # Configure mathtext to use the same font family
                        if font_fam_str:
                            # Configure mathtext fontset to match the regular font
                            # For Arial-like fonts, use dejavusans; for Times/STIX, use stix
                            lf = font_fam_str.lower()
                            if any(k in lf for k in ('stix', 'times', 'roman')):
                                mpl.rcParams['mathtext.fontset'] = 'stix'
                            else:
                                # Use dejavusans for Arial, Helvetica, etc. (closest match to Arial)
                                mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                            mpl.rcParams['mathtext.default'] = 'regular'
                    except Exception:
                        pass
                    
                    label_text = "Specific Capacity (mAh g$^{{-1}}$)"
                    ax.set_xlabel(label_text)
                    
                    # Apply current font settings to the label to ensure consistency
                    try:
                        import matplotlib.pyplot as plt
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        font_size = plt.rcParams.get('font.size', None)
                        if font_fam_str:
                            ax.xaxis.label.set_family(font_fam_str)
                        if font_size is not None:
                            ax.xaxis.label.set_size(font_size)
                        # Force label to re-render with updated mathtext fontset by updating the text
                        ax.set_xlabel(label_text)
                    except Exception:
                        pass
                    if any_restored:
                        _apply_nice_ticks()
                        try:
                            ax.relim(); ax.autoscale_view()
                        except Exception:
                            pass
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'f':
            # Font submenu with numbered options
            while True:
                print("\nFont menu: f=font family, s=size, q=back")
                sub = input("Font> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'f':
                    # Common font families with numbered options
                    fonts = ['Arial', 'DejaVu Sans', 'Helvetica', 'Liberation Sans', 
                             'Times New Roman', 'Courier New', 'Verdana', 'Tahoma']
                    print("\nCommon font families:")
                    for i, font in enumerate(fonts, 1):
                        print(f"  {i}: {font}")
                    print("Or enter custom font name directly.")
                    choice = input("Font family (number or name): ").strip()
                    if not choice:
                        continue
                    # Check if it's a number
                    if choice.isdigit():
                        idx = int(choice)
                        if 1 <= idx <= len(fonts):
                            fam = fonts[idx-1]
                            push_state("font-family")
                            _apply_font_family(ax, fam)
                            _rebuild_legend(ax)
                            print(f"Applied font family: {fam}")
                            try:
                                fig.canvas.draw()
                            except Exception:
                                fig.canvas.draw_idle()
                        else:
                            print("Invalid number.")
                    else:
                        # Use as custom font name
                        push_state("font-family")
                        _apply_font_family(ax, choice)
                        _rebuild_legend(ax)
                        print(f"Applied font family: {choice}")
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                elif sub == 's':
                    # Show current size and accept direct input
                    import matplotlib as mpl
                    cur_size = mpl.rcParams.get('font.size', None)
                    choice = input(f"Font size (current: {cur_size}): ").strip()
                    if not choice:
                        continue
                    try:
                        sz = float(choice)
                        if sz > 0:
                            push_state("font-size")
                            _apply_font_size(ax, sz)
                            _rebuild_legend(ax)
                            print(f"Applied font size: {sz}")
                            try:
                                fig.canvas.draw()
                            except Exception:
                                fig.canvas.draw_idle()
                        else:
                            print("Size must be positive.")
                    except Exception:
                        print("Invalid size.")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'x':
            # X-axis: set limits only
            while True:
                lim = input("Set X limits (min max, q=back): ").strip()
                if not lim or lim.lower() == 'q':
                    break
                try:
                    lo, hi = map(float, lim.split())
                    ax.set_xlim(lo, hi)
                    push_state("x-limits")
                    _apply_nice_ticks()
                    fig.canvas.draw()
                except Exception:
                    print("Invalid limits, ignored.")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'y':
            # Y-axis: set limits only
            while True:
                lim = input("Set Y limits (min max, q=back): ").strip()
                if not lim or lim.lower() == 'q':
                    break
                try:
                    lo, hi = map(float, lim.split())
                    ax.set_ylim(lo, hi)
                    push_state("y-limits")
                    _apply_nice_ticks()
                    fig.canvas.draw()
                except Exception:
                    print("Invalid limits, ignored.")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'g':
            # Geometry submenu: plot frame vs canvas (scales moved to separate keys)
            while True:
                print("Geometry menu: p=plot frame size, c=canvas size, q=back")
                sub = input("Geom> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'p':
                    # We don’t have y_data_list/labels here; pass minimal placeholders to keep API
                    push_state("resize-frame")
                    try:
                        resize_plot_frame(fig, ax, [], [], type('Args', (), {'stack': False})(), _update_labels)
                    except Exception as e:
                        print(f"Error changing plot frame: {e}")
                elif sub == 'c':
                    push_state("resize-canvas")
                    try:
                        resize_canvas(fig, ax)
                    except Exception as e:
                        print(f"Error changing canvas: {e}")
                try:
                    _apply_nice_ticks()
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'ro':
            # Rotation feature: rotate plot by 90 degrees
            while True:
                print("Rotation menu: c=clockwise 90°, a=anticlockwise 90°, q=back")
                sub = input("ro> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub in ('c', 'a'):
                    push_state("rotation")
                    current_angle = getattr(fig, '_ec_rotation_angle', 0)
                    # Increment or decrement rotation angle
                    if sub == 'c':
                        new_angle = (current_angle + 90) % 360
                    else:  # 'a'
                        new_angle = (current_angle - 90) % 360
                    
                    try:
                        print(f"WARNING: Rotation is experimental.")
                        import traceback
                        # Rotate all lines on the axes
                        for ln in ax.lines:
                            x_data = np.array(ln.get_xdata(), copy=True)
                            y_data = np.array(ln.get_ydata(), copy=True)
                            
                            if sub == 'c':
                                # Clockwise: (x, y) → (y, -x)
                                ln.set_data(y_data.copy(), -x_data.copy())
                            else:  # 'a'
                                # Anticlockwise: (x, y) → (-y, x)
                                ln.set_data(-y_data.copy(), x_data.copy())
                        
                        # Swap and update labels
                        xlabel = ax.get_xlabel()
                        ylabel = ax.get_ylabel()
                        if sub == 'c':
                            ax.set_xlabel(ylabel)
                            ax.set_ylabel(xlabel)
                        else:
                            ax.set_xlabel(ylabel)
                            ax.set_ylabel(xlabel)
                        
                        # Swap xlim and ylim
                        xlim = ax.get_xlim()
                        ylim = ax.get_ylim()
                        if sub == 'c':
                            ax.set_xlim(ylim)
                            ax.set_ylim(-xlim[1], -xlim[0])
                        else:
                            ax.set_xlim(-ylim[1], -ylim[0])
                            ax.set_ylim(xlim)
                        
                        # Store new rotation angle
                        setattr(fig, '_ec_rotation_angle', new_angle)
                        
                        # Rebuild legend to ensure it's positioned correctly
                        _rebuild_legend(ax)
                        
                        print(f"Rotated {'clockwise' if sub == 'c' else 'anticlockwise'} 90°. Total rotation: {new_angle}°")
                        
                    except Exception as e:
                        print(f"Rotation failed: {e}")
                        traceback.print_exc()
                    
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'sm':
            # dQ/dV smoothing utilities (only available in dQdV mode)
            if not is_dqdv:
                print("Smoothing is only available in dQ/dV mode.")
                _print_menu(len(all_cycles), is_dqdv)
                continue
            while True:
                print("\n\033[1mdQ/dV Data Filtering (Neware method)\033[0m")
                print("Commands:")
                print("  a: apply voltage step filter (removes small ΔV points)")
                print("  d: DiffCap smooth (≥1 mV ΔV + Savitzky–Golay, order 3, window 9)")
                print("  o: remove outliers (removes abrupt dQ/dV spikes)")
                print("  r: reset to original data")
                print("  q: back to main menu")
                sub = input("sm> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'r':
                    push_state("smooth-reset")
                    restored_count = 0
                    try:
                        for cyc, parts in cycle_lines.items():
                            for role in ("charge", "discharge"):
                                ln = parts.get(role) if isinstance(parts, dict) else parts
                                if ln is None:
                                    continue
                                if hasattr(ln, '_original_xdata'):
                                    ln.set_xdata(ln._original_xdata)
                                    ln.set_ydata(ln._original_ydata)
                                    restored_count += 1
                        if restored_count:
                            print(f"Reset {restored_count} curve(s) to original data.")
                            fig.canvas.draw_idle()
                        else:
                            print("No filtered data to reset.")
                    except Exception as e:
                        print(f"Error resetting filter: {e}")
                    continue
                if sub == 'a':
                    try:
                        threshold_input = input("Enter minimum voltage step in mV (default 0.5 mV): ").strip()
                        threshold_mv = 0.5 if not threshold_input else float(threshold_input)
                        threshold_v = threshold_mv / 1000.0
                        if threshold_v <= 0:
                            print("Threshold must be positive.")
                            continue
                        push_state("smooth-apply")
                        filtered = 0
                        total_before = 0
                        total_after = 0
                        for cyc, parts in cycle_lines.items():
                            for role in ("charge", "discharge"):
                                ln = parts.get(role) if isinstance(parts, dict) else parts
                                if ln is None or not ln.get_visible():
                                    continue
                                xdata = np.asarray(ln.get_xdata(), float)
                                ydata = np.asarray(ln.get_ydata(), float)
                                if xdata.size < 3:
                                    continue
                                if not hasattr(ln, '_original_xdata'):
                                    ln._original_xdata = np.array(xdata, copy=True)
                                    ln._original_ydata = np.array(ydata, copy=True)
                                dv = np.abs(np.diff(xdata))
                                mask = np.ones_like(xdata, dtype=bool)
                                mask[1:] &= dv >= threshold_v
                                mask[:-1] &= dv >= threshold_v
                                filtered_x = xdata[mask]
                                filtered_y = ydata[mask]
                                before = len(xdata)
                                after = len(filtered_x)
                                if after < before:
                                    ln.set_xdata(filtered_x)
                                    ln.set_ydata(filtered_y)
                                    filtered += 1
                                    total_before += before
                                    total_after += after
                        if filtered:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            print(f"Filtered {filtered} curve(s); removed {removed} of {total_before} points ({pct:.1f}%).")
                            print("Tip: Increase threshold to aggressively filter points (always applied to raw data).")
                            fig.canvas.draw_idle()
                        else:
                            print("No curves affected by current threshold.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                if sub == 'd':
                    try:
                        print("DiffCap smoothing per Thompson et al. (2020): clean ΔV < threshold and apply Savitzky–Golay (order 3).")
                        delta_input = input("Minimum ΔV between points (mV, default 1.0): ").strip()
                        min_step = 0.001 if not delta_input else max(float(delta_input), 0.0) / 1000.0
                        if min_step <= 0:
                            print("ΔV threshold must be positive.")
                            continue
                        window_input = input("Savitzky–Golay window (odd, default 9): ").strip()
                        poly_input = input("Polynomial order (default 3): ").strip()
                        window = 9 if not window_input else int(window_input)
                        poly = 3 if not poly_input else int(poly_input)
                    except ValueError:
                        print("Invalid number.")
                        continue
                    if window < 3:
                        window = 3
                    if window % 2 == 0:
                        window += 1
                    if poly < 1:
                        poly = 1
                    push_state("smooth-diffcap")
                    cleaned_curves = 0
                    total_removed = 0
                    for cyc, parts in cycle_lines.items():
                        iter_parts = [(None, parts)] if not isinstance(parts, dict) else parts.items()
                        for role, ln in iter_parts:
                            if ln is None or not ln.get_visible():
                                continue
                            xdata = np.asarray(ln.get_xdata(), float)
                            ydata = np.asarray(ln.get_ydata(), float)
                            if xdata.size < 3:
                                continue
                            if not hasattr(ln, '_original_xdata'):
                                ln._original_xdata = np.array(xdata, copy=True)
                                ln._original_ydata = np.array(ydata, copy=True)
                            x_clean, y_clean, removed = _diffcap_clean_series(xdata, ydata, min_step)
                            if x_clean.size < poly + 2:
                                continue
                            y_smooth = _savgol_smooth(y_clean, window, poly)
                            ln.set_xdata(x_clean)
                            ln.set_ydata(y_smooth)
                            cleaned_curves += 1
                            total_removed += removed
                    if cleaned_curves:
                        print(f"DiffCap smoothing applied to {cleaned_curves} curve(s); removed {total_removed} noisy points.")
                        fig.canvas.draw_idle()
                    else:
                        print("No curves were smoothed (not enough data after cleaning).")
                    continue
                if sub == 'o':
                    print("Outlier removal methods:")
                    print("  1: Z-score (enter standard deviation threshold, default 5.0)")
                    print("  2: MAD (median absolute deviation, default factor 6.0)")
                    method = input("Method (1/2, blank=cancel): ").strip()
                    if not method:
                        continue
                    if method not in ('1', '2'):
                        print("Unknown method.")
                        continue
                    try:
                        thresh_input = input("Enter threshold (blank=default): ").strip()
                        if method == '1':
                            z_threshold = 5.0 if not thresh_input else float(thresh_input)
                            if z_threshold <= 0:
                                print("Threshold must be positive.")
                                continue
                        else:
                            mad_threshold = 6.0 if not thresh_input else float(thresh_input)
                            if mad_threshold <= 0:
                                print("Threshold must be positive.")
                                continue
                        push_state("smooth-outlier")
                        filtered = 0
                        total_before = 0
                        total_after = 0
                        for cyc, parts in cycle_lines.items():
                            for role in ("charge", "discharge"):
                                ln = parts.get(role) if isinstance(parts, dict) else parts
                                if ln is None or not ln.get_visible():
                                    continue
                                xdata = np.asarray(ln.get_xdata(), float)
                                ydata = np.asarray(ln.get_ydata(), float)
                                if xdata.size < 5:
                                    continue
                                if not hasattr(ln, '_original_xdata'):
                                    ln._original_xdata = np.array(xdata, copy=True)
                                    ln._original_ydata = np.array(ydata, copy=True)
                                if method == '1':
                                    mean_y = np.nanmean(ydata)
                                    std_y = np.nanstd(ydata)
                                    if not np.isfinite(std_y) or std_y == 0:
                                        continue
                                    zscores = np.abs((ydata - mean_y) / std_y)
                                    mask = zscores <= z_threshold
                                else:
                                    median_y = np.nanmedian(ydata)
                                    mad = np.nanmedian(np.abs(ydata - median_y))
                                    if not np.isfinite(mad) or mad == 0:
                                        continue
                                    deviations = np.abs(ydata - median_y) / mad
                                    mask = deviations <= mad_threshold
                                filtered_x = xdata[mask]
                                filtered_y = ydata[mask]
                                before = len(xdata)
                                after = len(filtered_x)
                                if after < before:
                                    ln.set_xdata(filtered_x)
                                    ln.set_ydata(filtered_y)
                                    filtered += 1
                                    total_before += before
                                    total_after += after
                        if filtered:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            method_name = "Z-score" if method == '1' else "MAD"
                            thresh_val = z_threshold if method == '1' else mad_threshold
                            print(f"Removed outliers from {filtered} curve(s) using {method_name} (threshold={thresh_val}).")
                            print(f"Removed {removed} of {total_before} points ({pct:.1f}%).")
                            print("Tip: Adjust threshold to control sensitivity (always applied to raw data).")
                            fig.canvas.draw_idle()
                        else:
                            print("No outliers found with current threshold.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                print("Unknown command. Use a/o/r/q.")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        else:
            print("Unknown command.")
            _print_menu(len(all_cycles), is_dqdv)


def _get_geometry_snapshot(fig, ax) -> Dict:
    """Collects a snapshot of geometry settings (axes labels and limits)."""
    return {
        'xlim': list(ax.get_xlim()),
        'ylim': list(ax.get_ylim()),
        'xlabel': ax.get_xlabel() or '',
        'ylabel': ax.get_ylabel() or '',
    }


def _get_style_snapshot(fig, ax, cycle_lines: Dict, tick_state: Dict) -> Dict:
    """Collects a comprehensive snapshot of the current plot style (no curve data)."""
    # Figure and font properties
    fig_w, fig_h = fig.get_size_inches()
    ax_bbox = ax.get_position()
    frame_w_in = ax_bbox.width * fig_w
    frame_h_in = ax_bbox.height * fig_h
    
    font_fam = plt.rcParams.get('font.sans-serif', [''])
    font_fam0 = font_fam[0] if font_fam else ''
    font_size = plt.rcParams.get('font.size')

    # Spine properties
    spines = {}
    for name in ('bottom', 'top', 'left', 'right'):
        sp = ax.spines.get(name)
        if sp:
            spines[name] = {
                'linewidth': sp.get_linewidth(),
                'visible': sp.get_visible()
            }

    # Tick widths
    def _tick_width(axis_obj, which: str):
        try:
            tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
            width = tick_kw.get('width')
            if width is None:
                axis_name = getattr(axis_obj, 'axis_name', 'x')
                rc_key = f"{axis_name}tick.{which}.width"
                width = plt.rcParams.get(rc_key)
            if width is not None:
                return float(width)
        except Exception:
            return None
        return None

    tick_widths = {
        'x_major': _tick_width(ax.xaxis, 'major'),
        'x_minor': _tick_width(ax.xaxis, 'minor'),
        'y_major': _tick_width(ax.yaxis, 'major'),
        'y_minor': _tick_width(ax.yaxis, 'minor'),
    }

    # Tick direction
    tick_direction = getattr(fig, '_tick_direction', 'out')

    # Curve linewidth: get from stored value or first visible curve
    curve_linewidth = getattr(fig, '_ec_curve_linewidth', None)
    if curve_linewidth is None:
        try:
            for cyc, parts in cycle_lines.items():
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is not None:
                        try:
                            curve_linewidth = float(ln.get_linewidth() or 1.0)
                            break
                        except Exception:
                            pass
                if curve_linewidth is not None:
                    break
        except Exception:
            pass
    if curve_linewidth is None:
        curve_linewidth = 1.0  # default

    # Curve marker properties: get from first visible curve
    curve_marker_props = {}
    try:
        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
            try:
                curve_marker_props = {
                    'linestyle': ln.get_linestyle(),
                    'marker': ln.get_marker(),
                    'markersize': ln.get_markersize(),
                    'markerfacecolor': ln.get_markerfacecolor(),
                    'markeredgecolor': ln.get_markeredgecolor()
                }
                break
            except Exception:
                pass
            if curve_marker_props:
                break
    except Exception:
        pass

    def _line_color_hex(ln):
        try:
            return mcolors.to_hex(ln.get_color())
        except Exception:
            col = ln.get_color()
            if isinstance(col, str):
                return col
            try:
                return mcolors.to_hex(mcolors.to_rgba(col))
            except Exception:
                return None

    cycle_styles = {}
    for cyc, parts in cycle_lines.items():
        entry = {}
        if isinstance(parts, dict):
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is None:
                    continue
                style = {}
                color_hex = _line_color_hex(ln)
                if color_hex:
                    style['color'] = color_hex
                style['visible'] = bool(ln.get_visible())
                if style:
                    entry[role] = style
        else:
            ln = parts
            if ln is not None:
                style = {}
                color_hex = _line_color_hex(ln)
                if color_hex:
                    style['color'] = color_hex
                style['visible'] = bool(ln.get_visible())
                if style:
                    entry['line'] = style
        if entry:
            cycle_styles[str(cyc)] = entry

    # Build WASD state (20 parameters) from current axes state
    def _get_spine_visible(which: str) -> bool:
        sp = ax.spines.get(which)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False
    
    wasd_state = {
        'top':    {
            'spine': _get_spine_visible('top'),
            'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
            'minor': bool(tick_state.get('mtx', False)),
            'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
            'title': bool(getattr(ax, '_top_xlabel_on', False))
        },
        'bottom': {
            'spine': _get_spine_visible('bottom'),
            'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
            'minor': bool(tick_state.get('mbx', False)),
            'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
            'title': bool(ax.get_xlabel())
        },
        'left':   {
            'spine': _get_spine_visible('left'),
            'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
            'minor': bool(tick_state.get('mly', False)),
            'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
            'title': bool(ax.get_ylabel())
        },
        'right':  {
            'spine': _get_spine_visible('right'),
            'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', False))),
            'minor': bool(tick_state.get('mry', False)),
            'labels': bool(tick_state.get('r_labels', tick_state.get('ry', False))),
            'title': bool(getattr(ax, '_right_ylabel_on', False))
        },
    }

    # Legend visibility/location
    legend_visible = False
    legend_xy_in = None
    try:
        leg = ax.get_legend()
        if leg is not None:
            legend_visible = bool(leg.get_visible())
            legend_xy_in = getattr(fig, '_ec_legend_xy_in', None)
    except Exception:
        pass

    # Grid state
    grid_enabled = False
    try:
        # Check if grid is currently on by looking at gridline visibility
        for line in ax.get_xgridlines() + ax.get_ygridlines():
            if line.get_visible():
                grid_enabled = True
                break
    except Exception:
        grid_enabled = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False

    return {
        'kind': 'ec_style',
        'version': 2,
        'figure': {
            'canvas_size': [fig_w, fig_h],
            'frame_size': [frame_w_in, frame_h_in],
            'axes_fraction': [ax_bbox.x0, ax_bbox.y0, ax_bbox.width, ax_bbox.height],
        },
        'font': {'family': font_fam0, 'size': font_size},
        'legend': {
            'visible': legend_visible,
            'position_inches': legend_xy_in,
            'title': _get_legend_title(fig),
        },
        'spines': spines,
        'ticks': {'widths': tick_widths, 'direction': tick_direction},
        'grid': grid_enabled,
        'wasd_state': wasd_state,
        'curve_linewidth': curve_linewidth,
        'curve_markers': curve_marker_props,
        'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),
        'cycle_styles': cycle_styles,
    }


def _apply_cycle_styles(cycle_lines: Dict[int, Dict[str, Optional[object]]], style_cfg: Optional[Dict]) -> None:
    if not isinstance(style_cfg, dict):
        return
    for cyc_key, entry in style_cfg.items():
        try:
            cyc = int(cyc_key)
        except Exception:
            cyc = cyc_key
        if cyc not in cycle_lines:
            continue
        target = cycle_lines[cyc]
        if isinstance(target, dict):
            for role in ("charge", "discharge"):
                ln = target.get(role)
                style = entry.get(role) if isinstance(entry, dict) else None
                if ln is None or not isinstance(style, dict):
                    continue
                if 'color' in style:
                    try:
                        ln.set_color(style['color'])
                    except Exception:
                        pass
                if 'visible' in style:
                    try:
                        ln.set_visible(bool(style['visible']))
                    except Exception:
                        pass
        else:
            ln = target
            style = None
            if isinstance(entry, dict):
                style = entry.get('line', entry)
            elif isinstance(entry, (list, tuple)):
                continue
            else:
                style = entry
            if ln is None or not isinstance(style, dict):
                continue
            if 'color' in style:
                try:
                    ln.set_color(style['color'])
                except Exception:
                    pass
            if 'visible' in style:
                try:
                    ln.set_visible(bool(style['visible']))
                except Exception:
                    pass


def _print_style_snapshot(cfg: Dict):
    """Prints the style configuration in a user-friendly format matching XY plot."""
    print("\n--- Style / Diagnostics ---")
    
    # Geometry
    canvas_size = cfg.get('figure', {}).get('canvas_size', ['?', '?'])
    frame_size = cfg.get('figure', {}).get('frame_size', ['?', '?'])
    print(f"Figure size (inches): {canvas_size[0]:.3f} x {canvas_size[1]:.3f}")
    print(f"Plot frame size (inches):  {frame_size[0]:.3f} x {frame_size[1]:.3f}")

    # Font
    font = cfg.get('font', {})
    print(f"Effective font size (labels/ticks): {font.get('size', '?')}")
    print(f"Font family chain (rcParams['font.sans-serif']): ['{font.get('family', '?')}']")

    # Legend state
    leg_cfg = cfg.get('legend', {})
    if leg_cfg:
        leg_vis = bool(leg_cfg.get('visible', False))
        leg_pos = leg_cfg.get('position_inches')
        if isinstance(leg_pos, (list, tuple)) and len(leg_pos) == 2:
            try:
                lx = float(leg_pos[0])
                ly = float(leg_pos[1])
                print(f"Legend: {'ON' if leg_vis else 'off'} at x={lx:.3f} in, y={ly:.3f} in (relative to canvas center)")
            except Exception:
                print(f"Legend: {'ON' if leg_vis else 'off'}; position stored but unreadable")
        else:
            print(f"Legend: {'ON' if leg_vis else 'off'}; position=auto")
        legend_title = leg_cfg.get('title')
        if legend_title:
            print(f"Legend title: {legend_title}")

    # Rotation angle
    rotation_angle = cfg.get('rotation_angle', 0)
    if rotation_angle != 0:
        print(f"Rotation angle: {rotation_angle}°")

    # Per-side matrix summary (spine, major, minor, labels, title)
    def _onoff(v):
        return 'ON ' if bool(v) else 'off'
    
    wasd = cfg.get('wasd_state', {})
    if wasd:
        print("Per-side (w=top, a=left, s=bottom, d=right): spine, major, minor, labels, title")
        for side_key, side_label in [('top', 'w'), ('left', 'a'), ('bottom', 's'), ('right', 'd')]:
            s = wasd.get(side_key, {})
            spine_val = _onoff(s.get('spine', False))
            major_val = _onoff(s.get('ticks', False))
            minor_val = _onoff(s.get('minor', False))
            labels_val = _onoff(s.get('labels', False))
            title_val = _onoff(s.get('title', False))
            print(f"  {side_label}1:{spine_val} {side_label}2:{major_val} {side_label}3:{minor_val} {side_label}4:{labels_val} {side_label}5:{title_val}")

    # Tick widths
    tick_widths = cfg.get('ticks', {}).get('widths', {})
    x_maj = tick_widths.get('x_major')
    x_min = tick_widths.get('x_minor')
    y_maj = tick_widths.get('y_major')
    y_min = tick_widths.get('y_minor')
    print(f"Tick widths (major/minor): X=({x_maj}, {x_min})  Y=({y_maj}, {y_min})")
    
    # Tick direction
    tick_direction = cfg.get('ticks', {}).get('direction', 'out')
    print(f"Tick direction: {tick_direction}")

    # Grid
    grid_enabled = cfg.get('grid', False)
    print(f"Grid: {'enabled' if grid_enabled else 'disabled'}")

    # Spines
    spines = cfg.get('spines', {})
    if spines:
        print("Spines:")
        for name in ('bottom', 'top', 'left', 'right'):
            props = spines.get(name, {})
            lw = props.get('linewidth', '?')
            vis = props.get('visible', False)
            col = props.get('color')
            print(f"  {name:<6} lw={lw} visible={vis} color={col}")

    # Curve linewidth
    curve_linewidth = cfg.get('curve_linewidth')
    if curve_linewidth is not None:
        print(f"Curve linewidth (all curves): {curve_linewidth:.3g}")

    # Curve markers
    curve_markers = cfg.get('curve_markers', {})
    if curve_markers:
        ls = curve_markers.get('linestyle', '-')
        mk = curve_markers.get('marker', 'None')
        ms = curve_markers.get('markersize', 0)
        print(f"Curve style: linestyle={ls} marker={mk} markersize={ms}")

    cycle_styles = cfg.get('cycle_styles', {})
    if cycle_styles:
        print("Cycle colors:")
        def _cycle_sort_key(key):
            try:
                return int(key)
            except Exception:
                return key
        for cyc_key in sorted(cycle_styles.keys(), key=_cycle_sort_key):
            entry = cycle_styles[cyc_key] or {}
            segments = []
            for role_label, role_key in (('charge', 'charge'), ('discharge', 'discharge'), ('line', 'line')):
                style = entry.get(role_key)
                if not isinstance(style, dict):
                    continue
                color = style.get('color', 'unknown')
                vis = 'ON' if style.get('visible', True) else 'off'
                segments.append(f"{role_label}={color} ({vis})")
            if segments:
                print(f"  Cycle {cyc_key}: {', '.join(segments)}")

    print("--- End diagnostics ---\n")


def _export_style_dialog(cfg: Dict, default_ext: str = '.bpcfg', base_path: Optional[str] = None):
    """Handles the dialog for exporting a style configuration to a file.
    
    Args:
        cfg: Configuration dictionary to export
        default_ext: Default file extension ('.bps' for style-only, '.bpsg' for style+geometry)
    """
    try:
        # List files with matching extension in Styles/ subdirectory
        file_list = list_files_in_subdirectory((default_ext, '.bpcfg'), 'style', base_path=base_path)
        bpcfg_files = [f[0] for f in file_list]
        if bpcfg_files:
            styles_root = base_path if base_path else os.getcwd()
            styles_dir = os.path.join(styles_root, 'Styles')
            print(f"Existing {default_ext} files in {styles_dir}:")
            for i, f in enumerate(bpcfg_files, 1):
                print(f"  {i}: {f}")
        
        choice = input(f"Export to file? Enter filename or number to overwrite (q=cancel): ").strip()
        if not choice or choice.lower() == 'q':
            return

        target_path = ""
        if choice.isdigit() and bpcfg_files and 1 <= int(choice) <= len(bpcfg_files):
            target_path = file_list[int(choice) - 1][1]  # Full path from list
            if not _confirm_overwrite(target_path):
                return
        else:
            # Add default extension if no extension provided
            if not any(choice.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                filename_with_ext = f"{choice}{default_ext}"
            else:
                filename_with_ext = choice
            
            # Use organized path unless it's an absolute path
            if os.path.isabs(filename_with_ext):
                target_path = filename_with_ext
            else:
                target_path = get_organized_path(filename_with_ext, 'style', base_path=base_path)
            
            if not _confirm_overwrite(target_path):
                return
        
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Style exported to {target_path}")

    except Exception as e:
        print(f"Export failed: {e}")
def _legend_no_frame(ax, *args, title: Optional[str] = None, **kwargs):
    leg = ax.legend(*args, **kwargs)
    if leg is not None:
        try:
            leg.set_frame_on(False)
        except Exception:
            pass
        if title:
            try:
                leg.set_title(title)
            except Exception:
                pass
    return leg


def _apply_legend_position(fig, ax):
    xy_in = _sanitize_legend_offset(fig, getattr(fig, '_ec_legend_xy_in', None))
    if xy_in is None:
        return False
    handles, labels = _visible_legend_entries(ax)
    if not handles:
        return False
    fw, fh = fig.get_size_inches()
    if fw <= 0 or fh <= 0:
        return False
    fx = 0.5 + float(xy_in[0]) / float(fw)
    fy = 0.5 + float(xy_in[1]) / float(fh)
    _legend_no_frame(
        ax,
        handles,
        labels,
        loc='center',
        bbox_to_anchor=(fx, fy),
        bbox_transform=fig.transFigure,
        borderaxespad=1.0,
        title=_get_legend_title(fig),
    )
    return True


def _sanitize_legend_offset(fig, xy):
    if xy is None or not isinstance(xy, (tuple, list)) or len(xy) != 2:
        return None
    try:
        x_val = float(xy[0])
        y_val = float(xy[1])
    except Exception:
        return None
    fw, fh = fig.get_size_inches()
    if fw <= 0 or fh <= 0:
        return None
    max_x = fw * 0.45
    max_y = fh * 0.45
    if abs(x_val) > max_x or abs(y_val) > max_y:
        return None
    return (x_val, y_val)
