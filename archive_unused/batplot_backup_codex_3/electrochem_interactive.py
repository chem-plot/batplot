"""Interactive menu for electrochemistry (.mpt GC) plots.

Provides a minimal interactive loop when running:
  batplot file.mpt --gc --mass <mg> --interactive

"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple
import json
import os

import matplotlib.pyplot as plt
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
from matplotlib.ticker import MaxNLocator, AutoMinorLocator, NullFormatter
from .plotting import update_labels as _update_labels
from .utils import _confirm_overwrite
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


def _rebuild_legend(ax):
    """Rebuild legend using only visible lines, anchoring to absolute inches from canvas center if available."""
    handles = []
    labels = []
    for ln in ax.lines:
        if ln.get_visible():
            lab = ln.get_label() or ""
            # Skip private labels like _nolegend_
            if lab.startswith("_"):
                continue
            handles.append(ln)
            labels.append(lab)
    if handles:
        fig = ax.figure
        xy_in = getattr(fig, '_ec_legend_xy_in', None)
        if xy_in is not None:
            try:
                fw, fh = fig.get_size_inches()
                fx = 0.5 + float(xy_in[0]) / float(fw)
                fy = 0.5 + float(xy_in[1]) / float(fh)
                ax.legend(handles, labels, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
            except Exception:
                ax.legend(handles, labels, loc='best', borderaxespad=1.0)
        else:
            ax.legend(handles, labels, loc='best', borderaxespad=1.0)
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
            plt.get_cmap(alias)
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
            plt.get_cmap(alias)
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
        plt.get_cmap(last)
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
    
    # Detect dQdV mode: check stored flag first, then fall back to y-label detection
    # This handles cases where the user renamed the y-axis and saved/reloaded the session
    is_dqdv = getattr(ax, '_is_dqdv_mode', None)
    if is_dqdv is None:
        # Initial detection: check if y-label contains "dQ"
        is_dqdv = 'dQ' in base_ylabel
        # Store the mode on the axes for persistence
        ax._is_dqdv_mode = is_dqdv

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
                current_px = _px_value('_top_xlabel_manual_offset_pts')
                print(f"Top title offset: {current_px:+.2f} px (positive = up)")
                sub = input("top (w=up, s=down, 0=reset, q=back): ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_top_xlabel_manual_offset_pts', 0.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_pts', +1.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_pts', -1.0)
                else:
                    print("Unknown choice (use w/s/0/q).")
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
                current_px = _px_value('_right_ylabel_manual_offset_pts')
                print(f"Right title offset: {current_px:+.2f} px (positive = right)")
                sub = input("right (d=right, a=left, 0=reset, q=back): ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_right_ylabel_manual_offset_pts', 0.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_pts', +1.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_pts', -1.0)
                else:
                    print("Unknown choice (use d/a/0/q).")
                    continue
                _ui_position_right_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        while True:
            print("Duplicate title offsets:")
            print("  w : adjust top title (w=up, s=down)")
            print("  d : adjust right title (d=right, a=left)")
            print("  r : reset both offsets")
            print("  q : return")
            choice = input("p> ").strip().lower()
            if not choice:
                continue
            if choice == 'q':
                break
            if choice == 'w':
                _top_menu()
                continue
            if choice == 'd':
                _right_menu()
                continue
            if choice == 'r':
                _ensure_snapshot()
                _set_attr('_top_xlabel_manual_offset_pts', 0.0)
                _set_attr('_right_ylabel_manual_offset_pts', 0.0)
                _ui_position_top_xlabel(ax, fig, tick_state)
                _ui_position_right_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
                print("Reset manual offsets for duplicate titles.")
                continue
            print("Unknown option. Use w/d/r/q.")

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
    all_cycles = sorted(cycle_lines.keys())
    # ---------------- Undo stack ----------------
    state_history: List[dict] = []

    def _tick_width(axis, which: str):
        try:
            ticks = axis.get_major_ticks() if which == 'major' else axis.get_minor_ticks()
            for t in ticks:
                ln = t.tick1line
                if ln.get_visible():
                    return ln.get_linewidth()
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
                    'visible': (ax.spines.get(name).get_visible() if ax.spines.get(name) else None)
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
                    'top': float(getattr(ax, '_top_xlabel_manual_offset_pts', 0.0) or 0.0),
                    'right': float(getattr(ax, '_right_ylabel_manual_offset_pts', 0.0) or 0.0),
                },
                'lines': []
            }
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
            # Title duplicates
            try:
                offsets = snap.get('title_offsets', {})
                try:
                    ax._top_xlabel_manual_offset_pts = float(offsets.get('top', 0.0) or 0.0)
                except Exception:
                    ax._top_xlabel_manual_offset_pts = 0.0
                try:
                    ax._right_ylabel_manual_offset_pts = float(offsets.get('right', 0.0) or 0.0)
                except Exception:
                    ax._right_ylabel_manual_offset_pts = 0.0
                ax._top_xlabel_on = bool(snap.get('titles',{}).get('top_x', False))
                ax._right_ylabel_on = bool(snap.get('titles',{}).get('right_y', False))
                _ui_position_top_xlabel(ax, fig, tick_state)
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
            _rebuild_legend(ax)
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
                from .utils import list_files_in_subdirectory, get_organized_path
                # List existing figure files in Figures/ subdirectory
                fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
                file_list = list_files_in_subdirectory(fig_extensions, 'figure')
                files = [f[0] for f in file_list]
                if files:
                    print("Existing figure files in Figures/:")
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
                        target = get_organized_path(fname, 'figure')
                
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
                            xy_in = getattr(fig, '_ec_legend_xy_in', None)
                            leg = ax.get_legend()
                            if xy_in is None or leg is None or not leg.get_visible():
                                return
                            fw, fh = fig.get_size_inches()
                            fx = 0.5 + float(xy_in[0]) / float(fw)
                            fy = 0.5 + float(xy_in[1]) / float(fh)
                            handles, labels = ax.get_legend_handles_labels()
                            if handles:
                                ax.legend(handles, labels, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
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
                                fig._ec_legend_xy_in = ((fx - 0.5) * fw, (fy - 0.5) * fh)
                            except Exception:
                                pass
                except Exception:
                    pass
                # Current status
                leg = ax.get_legend()
                vis = bool(leg.get_visible()) if leg is not None else False
                xy_in = getattr(fig, '_ec_legend_xy_in', (0.0, 0.0))
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
                            else:
                                # Rebuild legend; if a custom position exists, honor it
                                handles, labels = ax.get_legend_handles_labels()
                                if handles:
                                    xy_in = getattr(fig, '_ec_legend_xy_in', None)
                                    if xy_in is not None:
                                        fw, fh = fig.get_size_inches()
                                        fx = 0.5 + float(xy_in[0]) / float(fw)
                                        fy = 0.5 + float(xy_in[1]) / float(fh)
                                        ax.legend(handles, labels, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
                                    else:
                                        ax.legend(handles, labels, loc='best', borderaxespad=1.0)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    elif sub == 'm':
                        xy_in = getattr(fig, '_ec_legend_xy_in', (0.0, 0.0))
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
                            fig._ec_legend_xy_in = (x_in, y_in)
                            # If legend visible, reposition now
                            leg = ax.get_legend()
                            if leg is not None and leg.get_visible():
                                fw, fh = fig.get_size_inches()
                                fx = 0.5 + float(x_in) / float(fw)
                                fy = 0.5 + float(y_in) / float(fh)
                                handles, labels = ax.get_legend_handles_labels()
                                if handles:
                                    ax.legend(handles, labels, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
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
                print("Print & Export: ps=style only (.bps), psg=style+geometry (.bpsg), q=cancel")
                choice = input("p> ").strip().lower()
                if not choice or choice == 'q':
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                
                if choice == 'ps':
                    # Style only
                    cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state)
                    cfg['kind'] = 'ec_style'
                    _print_style_snapshot(cfg)
                    _export_style_dialog(cfg, default_ext='.bps')
                elif choice == 'psg':
                    # Style + Geometry
                    cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state)
                    geom = _get_geometry_snapshot(fig, ax)
                    cfg['kind'] = 'ec_style_geom'
                    cfg['geometry'] = geom
                    _print_style_snapshot(cfg)
                    print("\n--- Geometry ---")
                    print(f"X-axis label: {geom['xlabel']}")
                    print(f"Y-axis label: {geom['ylabel']}")
                    print(f"X limits: {geom['xlim'][0]:.4g} to {geom['xlim'][1]:.4g}")
                    print(f"Y limits: {geom['ylim'][0]:.4g} to {geom['ylim'][1]:.4g}")
                    _export_style_dialog(cfg, default_ext='.bpsg')
                else:
                    print(f"Unknown option: {choice}")
            except Exception as e:
                print(f"Error in print/export menu: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'i':
            # Import style from .bps/.bpsg/.bpcfg (with numbered list from Styles/)
            try:
                from .utils import list_files_in_subdirectory
                style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
                _style_files = [f[0] for f in style_file_list]
                if _style_files:
                    print("Available style files in Styles/:")
                    for _i, _f in enumerate(_style_files, 1):
                        print(f"  {_i}: {_f}")
                inp = input("Enter number or filename (.bps/.bpsg, q=cancel): ").strip()
                if not inp or inp.lower() == 'q':
                    _print_menu(len(all_cycles), is_dqdv); continue
                push_state("import-style")
                if inp.isdigit() and _style_files:
                    _idx = int(inp)
                    if 1 <= _idx <= len(_style_files):
                        path = style_file_list[_idx-1][1]  # Full path from list
                    else:
                        print("Invalid number."); _print_menu(len(all_cycles), is_dqdv); continue
                else:
                    path = inp
                    # If it's not an absolute path, check in Styles/ subdirectory
                    if not os.path.isabs(path) and not os.path.isfile(path):
                        found = False
                        styles_dir = os.path.join(os.getcwd(), 'Styles')
                        for ext in ['.bps', '.bpsg', '.bpcfg']:
                            alt = path if path.lower().endswith(ext) else path + ext
                            styles_path = os.path.join(styles_dir, alt)
                            if os.path.isfile(styles_path):
                                path = styles_path
                                found = True
                                break
                        if not found:
                            # Try current directory as fallback
                            for ext in ['.bps', '.bpsg', '.bpcfg']:
                                alt = path if path.lower().endswith(ext) else path + ext
                                if os.path.isfile(alt):
                                    path = alt
                                    found = True
                                    break
                            if not found:
                                print("File not found in Styles/ or current directory."); _print_menu(len(all_cycles), is_dqdv); continue
                    elif not os.path.isfile(path):
                        print("File not found."); _print_menu(len(all_cycles), is_dqdv); continue
                
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                
                # Check file type
                kind = cfg.get('kind', '')
                if kind not in ('ec_style', 'ec_style_geom'):
                    print("Not an EC style file.")
                    _print_menu(len(all_cycles), is_dqdv)
                    continue
                
                has_geometry = (kind == 'ec_style_geom' and 'geometry' in cfg)
                
                # --- Apply comprehensive style (no curve data) ---
                # Figure and font
                try:
                    fig_cfg = cfg.get('figure', {})
                    canvas_size = fig_cfg.get('canvas_size')
                    if canvas_size and isinstance(canvas_size, list) and len(canvas_size) == 2:
                        fig.set_size_inches(canvas_size[0], canvas_size[1], forward=True)
                    
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
                        
                        # Apply minor ticks
                        if top_s.get('minor') or bot_s.get('minor'):
                            ax.xaxis.set_minor_locator(AutoMinorLocator())
                            ax.xaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='x', which='minor', 
                                      top=bool(top_s.get('minor', False)), 
                                      bottom=bool(bot_s.get('minor', False)), 
                                      labeltop=False, labelbottom=False)
                        
                        if left_s.get('minor') or right_s.get('minor'):
                            ax.yaxis.set_minor_locator(AutoMinorLocator())
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
                        
                        # Reposition titles
                        _ui_position_top_xlabel(ax, fig, tick_state)
                        _ui_position_bottom_xlabel(ax, fig, tick_state)
                        _ui_position_left_ylabel(ax, fig, tick_state)
                        _ui_position_right_ylabel(ax, fig, tick_state)
                        
                except Exception as e:
                    print(f"Warning: Could not apply tick visibility: {e}")

                # Spines and Ticks (widths)
                try:
                    spines_cfg = cfg.get('spines', {})
                    for name, props in spines_cfg.items():
                        if name in ax.spines:
                            if props.get('linewidth') is not None:
                                ax.spines[name].set_linewidth(props['linewidth'])
                    
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
                
                # Final redraw
                _rebuild_legend(ax)
                
                # Apply geometry if present
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
                
                fig.canvas.draw_idle()
                print(f"Applied style from {path}")

            except Exception as e:
                print(f"Error importing style: {e}")
            _print_menu(len(all_cycles), is_dqdv)
            continue
        elif key == 'l':
            # Line widths submenu: curves vs frame/ticks
            try:
                def _tick_width(axis, which: str):
                    try:
                        ticks = axis.get_major_ticks() if which == 'major' else axis.get_minor_ticks()
                        for t in ticks:
                            ln = t.tick1line
                            if ln.get_visible():
                                return ln.get_linewidth()
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
                            # Set spine color
                            resolved = resolve_color_token(color, fig)
                            ax.spines[spine_name].set_edgecolor(resolved)
                            # Set tick colors and axis label color for this axis
                            if spine_name in ('top', 'bottom'):
                                ax.tick_params(axis='x', which='both', colors=resolved)
                                ax.xaxis.label.set_color(resolved)
                            else:  # left or right
                                ax.tick_params(axis='y', which='both', colors=resolved)
                                ax.yaxis.label.set_color(resolved)
                            print(f"Set {spine_name} spine to {color_block(resolved)} {resolved}")
                            if spine_name == 'top':
                                _ui_position_top_xlabel(ax, fig, tick_state)
                            elif spine_name == 'right':
                                _ui_position_right_ylabel(ax, fig, tick_state)
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
                        'bottom': {'spine': _get_spine_visible('bottom'), 'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', False))), 'minor': bool(tick_state['mbx']), 'labels': bool(tick_state.get('b_labels', tick_state.get('bx', False))), 'title': bool(ax.get_xlabel())},
                        'left':   {'spine': _get_spine_visible('left'),   'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', False))), 'minor': bool(tick_state['mly']), 'labels': bool(tick_state.get('l_labels', tick_state.get('ly', False))), 'title': bool(ax.get_ylabel())},
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
                    # Minor X
                    if wasd['top']['minor'] or wasd['bottom']['minor']:
                        ax.xaxis.set_minor_locator(AutoMinorLocator()); ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor', top=bool(wasd['top']['minor']), bottom=bool(wasd['bottom']['minor']), labeltop=False, labelbottom=False)
                    # Minor Y
                    if wasd['left']['minor'] or wasd['right']['minor']:
                        ax.yaxis.set_minor_locator(AutoMinorLocator()); ax.yaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='y', which='minor', left=bool(wasd['left']['minor']), right=bool(wasd['right']['minor']), labelleft=False, labelright=False)
                    # Titles
                    if bool(wasd['bottom']['title']):
                        if hasattr(ax,'_stored_xlabel') and isinstance(ax._stored_xlabel,str) and ax._stored_xlabel:
                            ax.set_xlabel(ax._stored_xlabel)
                    else:
                        if not hasattr(ax,'_stored_xlabel'):
                            try: ax._stored_xlabel = ax.get_xlabel()
                            except Exception: ax._stored_xlabel = ''
                        ax.set_xlabel("")
                    ax._top_xlabel_on = bool(wasd['top']['title'])
                    if bool(wasd['left']['title']):
                        if hasattr(ax,'_stored_ylabel') and isinstance(ax._stored_ylabel,str) and ax._stored_ylabel:
                            ax.set_ylabel(ax._stored_ylabel)
                    else:
                        if not hasattr(ax,'_stored_ylabel'):
                            try: ax._stored_ylabel = ax.get_ylabel()
                            except Exception: ax._stored_ylabel = ''
                        ax.set_ylabel("")
                    ax._right_ylabel_on = bool(wasd['right']['title'])
                    
                    # Only reposition sides that were actually changed
                    # This prevents unnecessary title movement when toggling unrelated elements
                    if 'bottom' in changed_sides:
                        _ui_position_bottom_xlabel(ax, fig, tick_state)
                    if 'top' in changed_sides:
                        _ui_position_top_xlabel(ax, fig, tick_state)
                    if 'left' in changed_sides:
                        _ui_position_left_ylabel(ax, fig, tick_state)
                    if 'right' in changed_sides:
                        _ui_position_right_ylabel(ax, fig, tick_state)
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
                    print("WASD toggles: direction (w/a/s/d) x action (1..5)")
                    print("  1=spine   2=ticks   3=minor ticks   4=tick labels   5=axis title")
                    print("Type 'i' to invert tick direction, 'l' to change tick length, 'list' for state, 'q' to return.")
                    print("  p = adjust duplicate top/right title offsets (w/d)")
                    cmd = input("t> ").strip().lower()
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
                        print("Spine/ticks state:")
                        def b(v): return 'ON' if bool(v) else 'off'
                        print(f"top    w1:{b(wasd['top']['spine'])} w2:{b(wasd['top']['ticks'])} w3:{b(wasd['top']['minor'])} w4:{b(wasd['top']['labels'])} w5:{b(wasd['top']['title'])}")
                        print(f"bottom s1:{b(wasd['bottom']['spine'])} s2:{b(wasd['bottom']['ticks'])} s3:{b(wasd['bottom']['minor'])} s4:{b(wasd['bottom']['labels'])} s5:{b(wasd['bottom']['title'])}")
                        print(f"left   a1:{b(wasd['left']['spine'])} a2:{b(wasd['left']['ticks'])} a3:{b(wasd['left']['minor'])} a4:{b(wasd['left']['labels'])} a5:{b(wasd['left']['title'])}")
                        print(f"right  d1:{b(wasd['right']['spine'])} d2:{b(wasd['right']['ticks'])} d3:{b(wasd['right']['minor'])} d4:{b(wasd['right']['labels'])} d5:{b(wasd['right']['title'])}")
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
                folder = os.getcwd()
                try:
                    files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')])
                except Exception:
                    files = []
                if files:
                    print("Existing .pkl files:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                choice = input("Enter new filename or number to overwrite (q=cancel): ").strip()
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
                    cmap = plt.get_cmap(palette) if palette else None
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
                    print("Input the theoretical capacity per 1 active ion (mAh g⁻¹), e.g., 125")
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
                    ax.set_xlabel(f"Number of ions (C / {c_th:g} mAh g⁻¹)")
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
                    ax.set_xlabel("Specific Capacity (mAh g⁻¹)")
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
    def _tick_width(axis, which: str):
        try:
            ticks = axis.get_major_ticks() if which == 'major' else axis.get_minor_ticks()
            for t in ticks:
                if t.tick1line.get_visible():
                    return t.tick1line.get_linewidth()
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

    return {
        'kind': 'ec_style',
        'version': 2,
        'figure': {
            'canvas_size': [fig_w, fig_h],
            'frame_size': [frame_w_in, frame_h_in],
        },
        'font': {'family': font_fam0, 'size': font_size},
        'spines': spines,
        'ticks': {'widths': tick_widths, 'direction': tick_direction},
        'wasd_state': wasd_state,
        'curve_linewidth': curve_linewidth,
        'curve_markers': curve_marker_props,
        'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),
    }


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

    # Spines
    spines = cfg.get('spines', {})
    if spines:
        print("Spines:")
        for name in ('bottom', 'top', 'left', 'right'):
            props = spines.get(name, {})
            lw = props.get('linewidth', '?')
            vis = props.get('visible', False)
            print(f"  {name:<6} lw={lw} visible={vis}")

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

    print("--- End diagnostics ---\n")


def _export_style_dialog(cfg: Dict, default_ext: str = '.bpcfg'):
    """Handles the dialog for exporting a style configuration to a file.
    
    Args:
        cfg: Configuration dictionary to export
        default_ext: Default file extension ('.bps' for style-only, '.bpsg' for style+geometry)
    """
    try:
        from .utils import list_files_in_subdirectory, get_organized_path
        # List files with matching extension in Styles/ subdirectory
        file_list = list_files_in_subdirectory((default_ext, '.bpcfg'), 'style')
        bpcfg_files = [f[0] for f in file_list]
        if bpcfg_files:
            print(f"Existing {default_ext} files in Styles/:")
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
                target_path = get_organized_path(filename_with_ext, 'style')
            
            if not _confirm_overwrite(target_path):
                return
        
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Style exported to {target_path}")

    except Exception as e:
        print(f"Export failed: {e}")
