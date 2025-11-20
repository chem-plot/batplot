"""Interactive menu for normal XY plots (moved from monolithic batplot.py).

This module provides interactive_menu(fig, ax, ...). It mirrors the previous
implementation but lives outside batplot.py to match the pattern used by other
interactive modes (EC, Operando).
"""

from __future__ import annotations

import os
import json
import random
import sys
from typing import List, Optional, Tuple, Dict, Any

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, NullFormatter

from .plotting import update_labels
from .utils import _confirm_overwrite, normalize_label_text
from .session import dump_session as _bp_dump_session
from .ui import (
    apply_font_changes as _ui_apply_font_changes,
    sync_fonts as _ui_sync_fonts,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    update_tick_visibility as _ui_update_tick_visibility,
    ensure_text_visibility as _ui_ensure_text_visibility,
    resize_plot_frame as _ui_resize_plot_frame,
    resize_canvas as _ui_resize_canvas,
)
from .style import (
    print_style_info as _bp_print_style_info,
    export_style_config as _bp_export_style_config,
    apply_style_config as _bp_apply_style_config,
)


def interactive_menu(fig, ax, y_data_list, x_data_list, labels, orig_y,
                     label_text_objects, delta, x_label, args,
                     x_full_list, raw_y_full_list, offsets_list,
                     use_Q, use_r, use_E, use_k, use_rft,
                     cif_globals: Optional[Dict[str, Any]] = None):
    """Interactive menu for XY plots.
    
    Args:
        fig: matplotlib Figure
        ax: matplotlib Axes
        y_data_list: List of y-data arrays (with offsets applied)
        x_data_list: List of x-data arrays (cropped to current view)
        labels: List of curve labels
        orig_y: List of baseline y-data (normalized, no offset)
        label_text_objects: List of matplotlib Text objects for curve labels
        delta: Current offset spacing value
        x_label: X-axis label string
        args: Argument namespace from CLI
        x_full_list: List of full x-data arrays (uncropped)
        raw_y_full_list: List of full raw y-data arrays
        offsets_list: List of current offset values per curve
        use_Q, use_r, use_E, use_k, use_rft: Boolean flags for axis mode
        cif_globals: Optional dict containing CIF-related state:
            - 'cif_tick_series': list of CIF tick data
            - 'cif_hkl_map': dict mapping filenames to hkl reflections
            - 'cif_hkl_label_map': dict mapping Q to hkl label strings
            - 'show_cif_hkl': bool flag for hkl label visibility
            - 'cif_extend_suspended': bool flag to prevent re-entrant extension
            - 'keep_canvas_fixed': bool flag for canvas resize behavior
    """
    # Use the provided fig/ax as-is; do not close or switch figures to avoid spawning new windows
    
    # Handle CIF globals - prefer explicit parameter, fallback to __main__ for backward compatibility
    if cif_globals is None:
        # Legacy path: try to access __main__ module for CIF state
        _bp = sys.modules.get('__main__')
        if _bp is not None and hasattr(_bp, 'cif_tick_series'):
            cif_globals = {
                'cif_tick_series': getattr(_bp, 'cif_tick_series', None),
                'cif_hkl_map': getattr(_bp, 'cif_hkl_map', None),
                'cif_hkl_label_map': getattr(_bp, 'cif_hkl_label_map', None),
                'show_cif_hkl': getattr(_bp, 'show_cif_hkl', False),
                'show_cif_titles': getattr(_bp, 'show_cif_titles', True),
                'cif_extend_suspended': getattr(_bp, 'cif_extend_suspended', False),
                'keep_canvas_fixed': getattr(_bp, 'keep_canvas_fixed', False),
            }
        else:
            cif_globals = {}
    
    # Provide a consistent interface for accessing CIF state
    _bp = type('CIFState', (), cif_globals)() if cif_globals else None

    # Initialize rotation state (0, 90, 180, or 270 degrees)
    if not hasattr(ax, '_rotation_angle'):
        ax._rotation_angle = 0

    # Initialize stack label position state (True = bottom, False = top/max)
    if not hasattr(fig, '_stack_label_at_bottom'):
        fig._stack_label_at_bottom = False

    # ANSI color codes for menu highlighting
    def colorize_menu(text):
        """Colorize menu items: command in cyan, colon in white, description in default."""
        if ':' not in text:
            return text
        parts = text.split(':', 1)
        cmd = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ''
        return f"\033[96m{cmd}\033[0m: {desc}"  # Cyan for command, default for description
    
    def colorize_prompt(text):
        """Colorize commands within input prompts. Handles formats like (s=size, f=family, q=return) or (y/n) or (q=cancel)."""
        import re
        # Pattern to match parenthesized command lists like (s=size, f=family, q=return) or (y/n) or (m/p/s/t/q) or (q=cancel)
        pattern = r'\(([a-z]+=[^,)]+(?:,\s*[a-z]+=[^,)]+)*|[a-z]+(?:/[a-z]+)+)\)'
        
        def colorize_match(match):
            content = match.group(1)
            # Check if it's slash-separated (like y/n or m/p/s/t/q)
            if '/' in content:
                parts = content.split('/')
                colored_parts = [f"\033[96m{p.strip()}\033[0m" for p in parts]
                return f"({'/'.join(colored_parts)})"
            # Otherwise it's equals-separated (like s=size, f=family or q=cancel)
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
    
    def colorize_inline_commands(text):
        """Colorize inline command examples in help text. Colors quoted examples and specific known commands."""
        import re
        # Color quoted command examples (like 's2 w5 a4', 'w2 w5', or 'all magma_r')
        text = re.sub(r"'([a-z0-9\s_-]+)'", lambda m: f"'\033[96m{m.group(1)}\033[0m'", text)
        # Color specific known single-letter commands: q, i, l, when they appear as standalone commands
        # Pattern: word boundary + (q|i|l|list|help|all) + space/equals/comma/end
        text = re.sub(r'\b(q|i|l|list|help|all)\b(?=\s*[=,]|\s*$)', lambda m: f"\033[96m{m.group(1)}\033[0m", text)
        return text
    
    # REPLACED print_main_menu with column layout (now hides 'd' and 'y' in --stack)
    is_diffraction = use_Q or (not use_r and not use_E and not use_k and not use_rft)  # 2θ or Q
    def print_main_menu():
        has_cif = False
        try:
            has_cif = any(f.lower().endswith('.cif') for f in args.files)
        except Exception:
            pass
        col1 = ["c: colors", "f: font", "l: line", "ro: rotate", "t: toggle axes", "g: size", "h: legend"]
        if has_cif:
            col1.append("z: hkl")
            col1.append("j: CIF titles")
        col2 = ["a: rearrange", "d: offset", "r: rename", "x: change X", "y: change Y"]
        col3 = ["v: find peaks", "n: crosshair", "p: print(export) style/geom", "i: import style/geom", "e: export figure", "s: save project", "b: undo", "q: quit"]
        
        # Hide rotation and offset/y-range in stack mode
        if args.stack:
            col1 = [item for item in col1 if not item.startswith("ro:")]
            col2 = [item for item in col2 if not item.startswith("d:") and not item.startswith("y:")]
        
        if not is_diffraction:
            col3 = [item for item in col3 if not item.startswith("n:")]
        # Dynamic widths for cleaner alignment across terminals (account for ANSI codes)
        # Use plain text length for width calculations
        w1 = max(len("(Styles)"), *(len(s) for s in col1), 16)
        w2 = max(len("(Geometries)"), *(len(s) for s in col2), 16)
        w3 = max(len("(Options)"), *(len(s) for s in col3), 16)
        rows = max(len(col1), len(col2), len(col3))
        print("\n\033[1mInteractive menu:\033[0m")  # Bold title
        print(f"  \033[93m{'(Styles)':<{w1}}\033[0m \033[93m{'(Geometries)':<{w2}}\033[0m \033[93m{'(Options)':<{w3}}\033[0m")  # Yellow headers
        for i in range(rows):
            p1 = colorize_menu(col1[i]) if i < len(col1) else ""
            p2 = colorize_menu(col2[i]) if i < len(col2) else ""
            p3 = colorize_menu(col3[i]) if i < len(col3) else ""
            # Add padding to account for ANSI escape codes (9 chars per colorized item)
            pad1 = w1 + (9 if i < len(col1) else 0)
            pad2 = w2 + (9 if i < len(col2) else 0)
            pad3 = w3 + (9 if i < len(col3) else 0)
            print(f"  {p1:<{pad1}} {p2:<{pad2}} {p3:<{pad3}}")

    # --- Helper for spine visibility ---
    def set_spine_visible(which, visible):
        if which in ax.spines:
            ax.spines[which].set_visible(visible)
            fig.canvas.draw_idle()

    def get_spine_visible(which):
        if which in ax.spines:
            return ax.spines[which].get_visible()
        return False
    # Initial menu display REMOVED to avoid double print
    ax.set_aspect('auto', adjustable='datalim')

    def on_xlim_change(event_ax):
        stack_label_bottom = getattr(fig, '_stack_label_at_bottom', False)
        update_labels(event_ax, y_data_list, label_text_objects, args.stack, stack_label_bottom)
        # Extend CIF ticks if needed when user pans/zooms horizontally
        try:
            if (
                _bp is not None
                and (not getattr(_bp, 'cif_extend_suspended', False))
                and hasattr(ax, '_cif_extend_func') and hasattr(ax, '_cif_draw_func') and callable(ax._cif_extend_func)
            ):
                current_xlim = ax.get_xlim()
                xmax = current_xlim[1]
                ax._cif_extend_func(xmax)
        except Exception:
            pass
        fig.canvas.draw()
    ax.callbacks.connect('xlim_changed', on_xlim_change)

    # --------- UPDATED unified font update helper ----------
    def apply_font_changes(new_size=None, new_family=None):
        return _ui_apply_font_changes(ax, fig, label_text_objects, normalize_label_text, new_size, new_family)

    # Generic font sync (even when size/family unchanged) so newly created labels/twin axes inherit the rcParams size
    def sync_fonts():
        return _ui_sync_fonts(ax, fig, label_text_objects)

    # Adjust vertical position of duplicate top X label depending on top tick visibility
    def position_top_xlabel():
        return _ui_position_top_xlabel(ax, fig, tick_state)

    def position_right_ylabel():
        return _ui_position_right_ylabel(ax, fig, tick_state)
    
    def position_bottom_xlabel():
        return _ui_position_bottom_xlabel(ax, fig, tick_state)
    
    def position_left_ylabel():
        return _ui_position_left_ylabel(ax, fig, tick_state)
    
    def play_jump_game():
        """
        Simple terminal 'jumping bird' (Flappy-style) game.
        Controls: j = jump, Enter = let bird fall, q = quit game.
        Avoid hitting '#' pillars. Score increases when you pass a pillar.
        Difficulty lowered: bigger gaps, stronger jump, sparser pillars.
        """
        # Board/config
        WIDTH = 32
        HEIGHT = 12
        BIRD_X = 5
        GRAVITY = 1
        JUMP_VEL = -3   # stronger jump for easier play
        GAP_SIZE = 4    # larger gap
        MIN_OBS_SPACING = 8  # fewer pillars

        class Obstacle:
            __slots__ = ("x", "gap_start", "scored")
            def __init__(self, x):
                self.x = x
                self.gap_start = random.randint(1, max(1, HEIGHT - GAP_SIZE - 1))
                self.scored = False

        bird_y = HEIGHT // 2
        vel = 0
        tick = 0
        score = 0
        obstacles = [Obstacle(WIDTH - 1)]

        def need_new():
            if not obstacles:
                return True
            rightmost = max(o.x for o in obstacles)
            return rightmost < WIDTH - MIN_OBS_SPACING

        def new_obstacle():
            obstacles.append(Obstacle(WIDTH - 1))
            # Out of bounds
            if bird_y < 0 or bird_y >= HEIGHT:
                return True
            # Pillar collisions at or just before bird column unless within gap
            for o in obstacles:
                if o.x in (BIRD_X, BIRD_X - 1):
                    if not (o.gap_start <= bird_y < o.gap_start + GAP_SIZE):
                        return True
            return False

        def move_obstacles():
            for o in obstacles:
                o.x -= 1

        def purge_obstacles():
            while obstacles and obstacles[0].x < -1:
                obstacles.pop(0)

        def render():
            border = "+" + ("-" * WIDTH) + "+"
            print("\n" + border)
            for y in range(HEIGHT):
                row = []
                for x in range(WIDTH):
                    ch = " "
                    if x == BIRD_X and y == bird_y:
                        ch = "@"
                    else:
                        for o in obstacles:
                            if x == o.x and not (o.gap_start <= y < o.gap_start + GAP_SIZE):
                                ch = "#"
                                break
                    row.append(ch)
                print("|" + "".join(row) + "|")
            print(border)
            print(f"Score: {score}   (j=jump, Enter=fall, q=quit)")

        # One-time instructions
        print("\nJumping Bird: pass through the gaps!")
        print("Controls: j = jump, Enter = fall, q = quit\n")

        while True:
            render()
            cmd = input("> ").strip().lower()
            if cmd == 'q':
                print("Exited game. Returning to interactive menu.\n")
                break
            if cmd == 'j':
                vel = JUMP_VEL
            else:
                vel += GRAVITY

            bird_y += vel

            move_obstacles()
            if need_new():
                new_obstacle()
            purge_obstacles()

            # Scoring: mark a pillar once it moves left of bird
            for o in obstacles:
                if not o.scored and o.x < BIRD_X:
                    o.scored = True
                    score += 1

            tick += 1
            if collision():
                render()
                print(f"Game Over! Final score: {score}\n")
                break

    # -------------------------------------------------------

    # --------- NEW: Resize only the plotting frame (axes), keep canvas (figure) size fixed ----------
    def resize_plot_frame():
        return _ui_resize_plot_frame(fig, ax, y_data_list, label_text_objects, args, update_labels)

    def resize_canvas():
        return _ui_resize_canvas(fig, ax)
    # -------------------------------------------------

    # ---- Tick / label visibility state ----
    # New model: separate tick marks vs tick labels per side
    # Keys:
    #   b_ticks, b_labels, t_ticks, t_labels, l_ticks, l_labels, r_ticks, r_labels
    # Minor ticks remain: mbx, mtx, mly, mry
    # Back-compat: also maintain synthetic bx/tx/ly/ry (mapped to *_ticks) for helpers.
    saved_ts = getattr(ax, '_saved_tick_state', None)
    def _make_default_tick_state():
        return {
            # Major ticks vs labels (defaults: bottom/left on, top/right off)
            'b_ticks': True,  'b_labels': True,
            't_ticks': False, 't_labels': False,
            'l_ticks': True,  'l_labels': True,
            'r_ticks': False, 'r_labels': False,
            # Minor ticks
            'mbx': False, 'mtx': False, 'mly': False, 'mry': False,
            # Legacy mirrors (filled by _sync_legacy_tick_keys)
            'bx': True, 'tx': False, 'ly': True, 'ry': False,
        }

    def _from_legacy(legacy: dict):
        ts = _make_default_tick_state()
        bx = bool(legacy.get('bx', ts['bx']))
        tx = bool(legacy.get('tx', ts['tx']))
        ly = bool(legacy.get('ly', ts['ly']))
        ry = bool(legacy.get('ry', ts['ry']))
        ts.update({
            'b_ticks': bx, 'b_labels': bx,
            't_ticks': tx, 't_labels': tx,
            'l_ticks': ly, 'l_labels': ly,
            'r_ticks': ry, 'r_labels': ry,
            'mbx': bool(legacy.get('mbx', False)),
            'mtx': bool(legacy.get('mtx', False)),
            'mly': bool(legacy.get('mly', False)),
            'mry': bool(legacy.get('mry', False)),
        })
        return ts

    def _sync_legacy_tick_keys():
        # Mirror current *_ticks into legacy bx/tx/ly/ry keys for code that reads them
        tick_state['bx'] = bool(tick_state.get('b_ticks', True))
        tick_state['tx'] = bool(tick_state.get('t_ticks', False))
        tick_state['ly'] = bool(tick_state.get('l_ticks', True))
        tick_state['ry'] = bool(tick_state.get('r_ticks', False))

    if isinstance(saved_ts, dict):
        if any(k in saved_ts for k in ('b_ticks','t_ticks','l_ticks','r_ticks')):
            # Already new-format; start from defaults then overlay
            tick_state = _make_default_tick_state()
            for k,v in saved_ts.items():
                if k in tick_state:
                    tick_state[k] = v
        else:
            tick_state = _from_legacy(saved_ts)
    else:
        tick_state = _make_default_tick_state()
    _sync_legacy_tick_keys()

    if hasattr(ax, '_saved_tick_state'):
        try:
            delattr(ax, '_saved_tick_state')
        except Exception:
            pass

    # NEW: dynamic margin adjustment for top/right ticks
    # Flag to preserve a manual/initial interactive top margin override
    if not hasattr(fig, '_interactive_top_locked'):
        fig._interactive_top_locked = False

    def adjust_margins():
        """Lightweight margin tweak based on tick visibility.

        Unlike the old version this DOES NOT try to aggressively reallocate
        space or change apparent plot size; it only adds a small padding on
        sides that show ticks so labels have breathing room. Intended to be
        idempotent and minimally invasive. Called during initial setup & some
        style operations, but not on every tick toggle anymore.
        """
        sp = fig.subplotpars
        # Start from current to avoid jumping
        left, right, bottom, top = sp.left, sp.right, sp.bottom, sp.top
        pad = 0.01  # modest expansion per active side
        max_pad = 0.10
        # Expand outward (shrinks axes) only if room
        if tick_state['ly'] and left < 0.25:
            left = min(left + pad, 0.40)
        if tick_state['ry'] and (1 - right) < 0.25:
            right = max(right - pad, 0.60)
        if tick_state['bx'] and bottom < 0.25:
            bottom = min(bottom + pad, 0.40)
        if tick_state['tx'] and (1 - top) < 0.25:
            top = max(top - pad, 0.60)

        # Keep minimum plot span
        if right - left < 0.25:
            # Undo horizontal change proportionally
            mid = (left + right) / 2
            left = mid - 0.125
            right = mid + 0.125
        if top - bottom < 0.25:
            mid = (bottom + top) / 2
            bottom = mid - 0.125
            top = mid + 0.125

        fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)

    def ensure_text_visibility(max_iterations=4, check_only=False):
        return _ui_ensure_text_visibility(fig, ax, label_text_objects, max_iterations, check_only)

    def update_tick_visibility():
        # Apply major ticks and labels independently per side
        ax.tick_params(axis='x',
                       bottom=bool(tick_state['b_ticks']), labelbottom=bool(tick_state['b_labels']),
                       top=bool(tick_state['t_ticks']),    labeltop=bool(tick_state['t_labels']))
        ax.tick_params(axis='y',
                       left=bool(tick_state['l_ticks']),  labelleft=bool(tick_state['l_labels']),
                       right=bool(tick_state['r_ticks']), labelright=bool(tick_state['r_labels']))

        if tick_state['mbx'] or tick_state['mtx']:
            ax.xaxis.set_minor_locator(AutoMinorLocator())
            ax.xaxis.set_minor_formatter(NullFormatter())
            ax.tick_params(axis='x', which='minor',
                           bottom=tick_state['mbx'],
                           top=tick_state['mtx'],
                           labelbottom=False, labeltop=False)
        else:
            ax.tick_params(axis='x', which='minor',
                           bottom=False, top=False,
                           labelbottom=False, labeltop=False)

        if tick_state['mly'] or tick_state['mry']:
            ax.yaxis.set_minor_locator(AutoMinorLocator())
            ax.yaxis.set_minor_formatter(NullFormatter())
            ax.tick_params(axis='y', which='minor',
                           left=tick_state['mly'],
                           right=tick_state['mry'],
                           labelleft=False, labelright=False)
        else:
            ax.tick_params(axis='y', which='minor',
                           left=False, right=False,
                           labelleft=False, labelright=False)

    # NOTE: We keep margins stable (no auto-adjust on every toggle)
    ensure_text_visibility()
    fig.canvas.draw_idle()

    # NEW helper (was referenced in 'h' menu but not defined previously)
    def print_tick_state():
        def onoff(v):
            return 'ON ' if bool(v) else 'off'
        summary = []
        sides = (
            ('bottom',
             get_spine_visible('bottom'),
             tick_state.get('b_ticks', True),
             tick_state.get('mbx', False),
             tick_state.get('b_labels', True),
             bool(ax.get_xlabel())),
            ('top',
             get_spine_visible('top'),
             tick_state.get('t_ticks', False),
             tick_state.get('mtx', False),
             tick_state.get('t_labels', False),
             bool(getattr(ax, '_top_xlabel_on', False))),
            ('left',
             get_spine_visible('left'),
             tick_state.get('l_ticks', True),
             tick_state.get('mly', False),
             tick_state.get('l_labels', True),
             bool(ax.get_ylabel())),
            ('right',
             get_spine_visible('right'),
             tick_state.get('r_ticks', False),
             tick_state.get('mry', False),
             tick_state.get('r_labels', False),
             bool(getattr(ax, '_right_ylabel_on', False))),
        )
        print("State (per side: spine, major, minor, labels, title):")
        for name, spine, mj, mn, lbl, title in sides:
            print(f"  {name:<6}: spine={onoff(spine)} major={onoff(mj)} minor={onoff(mn)} labels={onoff(lbl)} title={onoff(title)}")

    # NEW: style / diagnostics printer (clean version)
    def print_style_info():
        cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
        show_hkl = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else None
        return _bp_print_style_info(
            fig, ax,
            y_data_list, labels,
            offsets_list,
            x_full_list, raw_y_full_list,
            args, delta,
            label_text_objects,
            tick_state,
            cts,
            show_hkl,
        )

    # NEW: export current style to .bpcfg
    def export_style_config(filename):
        cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
        return _bp_export_style_config(filename, fig, ax, y_data_list, labels, delta, args, tick_state, offsets_list, cts, label_text_objects)

    # NEW: apply imported style config (restricted application)
    def apply_style_config(filename):
        cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
        hkl_map = getattr(_bp, 'cif_hkl_label_map', None) if _bp is not None else None
        res = _bp_apply_style_config(
            filename,
            fig,
            ax,
            x_data_list,
            y_data_list,
            orig_y,
            offsets_list,
            label_text_objects,
            args,
            tick_state,
            labels,
            update_labels,
            cts,
            hkl_map,
            adjust_margins,
        )
        # Sync top/right tick label2 fonts with current rcParams after style import
        try:
            fam_chain = plt.rcParams.get('font.sans-serif')
            fam0 = fam_chain[0] if isinstance(fam_chain, list) and fam_chain else None
            size0 = plt.rcParams.get('font.size', None)
            if fam0 or size0 is not None:
                for t in ax.xaxis.get_major_ticks():
                    if hasattr(t, 'label2'):
                        if size0 is not None: t.label2.set_size(size0)
                        if fam0: t.label2.set_family(fam0)
                for t in ax.yaxis.get_major_ticks():
                    if hasattr(t, 'label2'):
                        if size0 is not None: t.label2.set_size(size0)
                        if fam0: t.label2.set_family(fam0)
        except Exception:
            pass
        return res

    # Initialize with current defaults
    update_tick_visibility()

    # --- Crosshair state & toggle function (UPDATED) ---
    crosshair = {
        'active': False,
        'hline': None,
        'vline': None,
        'text': None,
        'cid_motion': None,
        'wavelength': None  # only used when axis is 2theta
    }

    def toggle_crosshair():
        if not crosshair['active']:
            # Only ask for wavelength if it's diffraction data and not using Q
            if is_diffraction and not use_Q:
                try:
                    wl_in = input("Enter wavelength in Å for Q,d display (blank=skip, q=cancel): ").strip()
                    if wl_in.lower() == 'q':
                        print("Canceled.")
                        return
                    if wl_in:
                        crosshair['wavelength'] = float(wl_in)
                    else:
                        crosshair['wavelength'] = None
                except ValueError:
                    print("Invalid wavelength. Skipping Q,d calculation.")
                    crosshair['wavelength'] = None
            vline = ax.axvline(x=ax.get_xlim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            hline = ax.axhline(y=ax.get_ylim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            txt = ax.text(1.0, 1.0, "",
                          ha='right', va='bottom',
                          transform=ax.transAxes,
                          fontsize=max(9, int(0.6 * plt.rcParams.get('font.size', 12))),
                          color='0.15',
                          bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))

            def on_move(event):
                if event.inaxes != ax or event.xdata is None or event.ydata is None:
                    return
                x = float(event.xdata)
                y = float(event.ydata)
                vline.set_xdata([x, x])
                hline.set_ydata([y, y])

                # For diffraction data, show Q/d calculations
                if is_diffraction:
                    if use_Q:
                        Q = x
                        if Q != 0:
                            d = 2 * np.pi / Q
                            txt.set_text(f"Q={Q:.6g}\nd={d:.6g} Å\ny={y:.6g}")
                        else:
                            txt.set_text(f"Q={Q:.6g}\nd=∞\ny={y:.6g}")
                    elif use_r:
                        txt.set_text(f"r={x:.6g} Å\ny={y:.6g}")
                    else:
                        # 2θ mode
                        if crosshair['wavelength'] is not None:
                            lam = crosshair['wavelength']
                            theta_rad = np.radians(x / 2.0)
                            Q = 4 * np.pi * np.sin(theta_rad) / lam
                            if Q != 0:
                                d = 2 * np.pi / Q
                                txt.set_text(f"2θ={x:.6g}°\nQ={Q:.6g}\nd={d:.6g} Å\ny={y:.6g}")
                            else:
                                txt.set_text(f"2θ={x:.6g}°\nQ=0\nd=∞\ny={y:.6g}")
                        else:
                            txt.set_text(f"2θ={x:.6g}°\ny={y:.6g}")
                else:
                    # For non-diffraction data, just show x and y values
                    txt.set_text(f"x={x:.6g}\ny={y:.6g}")

                fig.canvas.draw_idle()

            cid = fig.canvas.mpl_connect('motion_notify_event', on_move)
            crosshair.update({'active': True, 'hline': hline, 'vline': vline,
                              'text': txt, 'cid_motion': cid})
            print("Crosshair ON. Move mouse over axes. Press 'n' again to turn off.")
        else:
            if crosshair['cid_motion'] is not None:
                fig.canvas.mpl_disconnect(crosshair['cid_motion'])
            for k in ('hline', 'vline', 'text'):
                art = crosshair[k]
                if art is not None:
                    try:
                        art.remove()
                    except Exception:
                        pass
            crosshair.update({'active': False, 'hline': None, 'vline': None,
                              'text': None, 'cid_motion': None})
            fig.canvas.draw_idle()
            print("Crosshair OFF.")
    # --- End crosshair additions (UPDATED) ---

    # -------- Session helper now provided by batplot.session (dump only here) --------

    
    # history management:
    state_history = []

    def push_state(note=""):
        """Snapshot current editable state (before a modifying action)."""
        try:
            # Helper to capture a representative tick line width
            def _tick_width(axis, which):
                try:
                    ticks = axis.get_major_ticks() if which=='major' else axis.get_minor_ticks()
                    for t in ticks:
                        ln = t.tick1line
                        if ln.get_visible():
                            return ln.get_linewidth()
                except Exception:
                    return None
                return None
            snap = {
                "note": note,
                "xlim": ax.get_xlim(),
                "ylim": ax.get_ylim(),
                "tick_state": tick_state.copy(),
                "font_size": plt.rcParams.get('font.size'),
                "font_chain": list(plt.rcParams.get('font.sans-serif', [])),
                "labels": list(labels),
                "delta": delta,
                "lines": [],
                "fig_size": list(fig.get_size_inches()),
                "fig_dpi": fig.dpi,
                "axes_bbox": [float(v) for v in ax.get_position().bounds],  # x0,y0,w,h
                "axis_labels": {"xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel()},
                "axis_titles": {"top_x": bool(getattr(ax, '_top_xlabel_on', False)),
                                 "right_y": bool(getattr(ax, '_right_ylabel_on', False))},
                "spines": {name: {"lw": sp.get_linewidth(), "color": sp.get_edgecolor(), "visible": sp.get_visible()} for name, sp in ax.spines.items()},
                "tick_widths": {
                    "x_major": _tick_width(ax.xaxis, 'major'),
                    "x_minor": _tick_width(ax.xaxis, 'minor'),
                    "y_major": _tick_width(ax.yaxis, 'major'),
                    "y_minor": _tick_width(ax.yaxis, 'minor')
                },
                "tick_lengths": dict(getattr(fig, '_tick_lengths', {'major': None, 'minor': None})),
                "tick_direction": getattr(fig, '_tick_direction', 'out'),
                "cif_tick_series": (list(getattr(_bp, 'cif_tick_series')) if (_bp is not None and hasattr(_bp, 'cif_tick_series')) else None),
                "show_cif_hkl": (bool(getattr(_bp, 'show_cif_hkl')) if _bp is not None and hasattr(_bp, 'show_cif_hkl') else False),
                "show_cif_titles": (bool(getattr(_bp, 'show_cif_titles')) if _bp is not None and hasattr(_bp, 'show_cif_titles') else True),
                "rotation_angle": getattr(ax, '_rotation_angle', 0),
                "stack_label_at_bottom": getattr(fig, '_stack_label_at_bottom', False),
                "grid": ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False
            }
            # Line + data arrays
            for i, ln in enumerate(ax.lines):
                snap["lines"].append({
                    "index": i,
                    "x": np.array(ln.get_xdata(), copy=True),
                    "y": np.array(ln.get_ydata(), copy=True),
                    "color": ln.get_color(),
                    "lw": ln.get_linewidth(),
                    "ls": ln.get_linestyle(),
                    "marker": ln.get_marker(),
                    "markersize": getattr(ln, 'get_markersize', lambda: None)(),
                    "mfc": getattr(ln, 'get_markerfacecolor', lambda: None)(),
                    "mec": getattr(ln, 'get_markeredgecolor', lambda: None)(),
                    "alpha": ln.get_alpha()
                })
            # Data lists
            snap["x_data_list"] = [np.array(a, copy=True) for a in x_data_list]
            snap["y_data_list"] = [np.array(a, copy=True) for a in y_data_list]
            snap["orig_y"]      = [np.array(a, copy=True) for a in orig_y]
            snap["offsets"]     = list(offsets_list)
            # Label text content
            snap["label_texts"] = [t.get_text() for t in label_text_objects]
            state_history.append(snap)
            if len(state_history) > 40:
                state_history.pop(0)
        except Exception as e:
            print(f"Warning: could not snapshot state: {e}")

    def restore_state():
        nonlocal delta
        if not state_history:
            print("No undo history.")
            return
        snap = state_history.pop()
        try:
            # Basic numeric state
            ax.set_xlim(*snap["xlim"]) 
            ax.set_ylim(*snap["ylim"]) 
            # Tick state
            snap_ts = snap.get("tick_state", {})
            for k, v in snap_ts.items():
                if k in tick_state:
                    tick_state[k] = v
            # If snapshot was legacy-only, map bx/tx/ly/ry into new keys
            if not any(k in snap_ts for k in ('b_ticks','t_ticks','l_ticks','r_ticks')):
                if 'bx' in snap_ts:
                    tick_state['b_ticks'] = bool(snap_ts.get('bx', tick_state['bx']))
                    tick_state['b_labels'] = bool(snap_ts.get('bx', tick_state['bx']))
                if 'tx' in snap_ts:
                    tick_state['t_ticks'] = bool(snap_ts.get('tx', tick_state['tx']))
                    tick_state['t_labels'] = bool(snap_ts.get('tx', tick_state['tx']))
                if 'ly' in snap_ts:
                    tick_state['l_ticks'] = bool(snap_ts.get('ly', tick_state['ly']))
                    tick_state['l_labels'] = bool(snap_ts.get('ly', tick_state['ly']))
                if 'ry' in snap_ts:
                    tick_state['r_ticks'] = bool(snap_ts.get('ry', tick_state['ry']))
                    tick_state['r_labels'] = bool(snap_ts.get('ry', tick_state['ry']))
            _sync_legacy_tick_keys()
            update_tick_visibility()

            # Fonts
            if snap["font_chain"]:
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['font.sans-serif'] = snap["font_chain"]
            if snap["font_size"]:
                try:
                    plt.rcParams['font.size'] = snap["font_size"]
                except Exception:
                    pass

            # Figure size & dpi
            if snap.get("fig_size") and isinstance(snap["fig_size"], (list, tuple)) and len(snap["fig_size"])==2:
                if not (getattr(_bp, 'keep_canvas_fixed', True) if _bp is not None else True):
                    try:
                        fig.set_size_inches(snap["fig_size"][0], snap["fig_size"][1], forward=True)
                    except Exception:
                        pass
                else:
                    print("(Canvas fixed) Ignoring undo figure size restore.")
            # Don't restore DPI from undo - use system default to avoid display-dependent issues
            
            # Restore axes (plot frame) via stored bbox if present
            if snap.get("axes_bbox") and isinstance(snap["axes_bbox"], (list, tuple)) and len(snap["axes_bbox"])==4:
                try:
                    x0,y0,w,h = snap["axes_bbox"]
                    left = x0; bottom = y0; right = x0 + w; top = y0 + h
                    if 0 < left < right <=1 and 0 < bottom < top <=1:
                        fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
                except Exception:
                    pass

            # Axis labels (use low-level API to avoid layout recalculation)
            axis_labels = snap.get("axis_labels", {})
            if axis_labels.get("xlabel") is not None:
                ax.xaxis.label.set_text(axis_labels["xlabel"])
            if axis_labels.get("ylabel") is not None:
                ax.yaxis.label.set_text(axis_labels["ylabel"])

            # Axis title duplicates (top X / right Y)
            at = snap.get("axis_titles", {})
            # Top X
            try:
                ax._top_xlabel_on = bool(at.get('top_x', False))
                position_top_xlabel()
            except Exception:
                pass
            # Right Y
            try:
                ax._right_ylabel_on = bool(at.get('right_y', False))
                position_right_ylabel()
            except Exception:
                pass
            # Also reposition bottom/left titles to consume pending pads and match tick label visibility
            try:
                position_bottom_xlabel()
            except Exception:
                pass
            try:
                position_left_ylabel()
            except Exception:
                pass

            # Spines (linewidth, color, visibility)
            for name, spec in snap.get("spines", {}).items():
                sp_obj = ax.spines.get(name)
                if sp_obj is None: continue
                try:
                    if "lw" in spec:
                        sp_obj.set_linewidth(spec["lw"])
                    if "color" in spec and spec["color"] is not None:
                        sp_obj.set_edgecolor(spec["color"]) 
                    if "visible" in spec:
                        try:
                            sp_obj.set_visible(bool(spec["visible"]))
                        except Exception:
                            pass
                except Exception:
                    pass

            # Tick widths
            tw = snap.get("tick_widths", {})
            try:
                if tw.get("x_major") is not None:
                    ax.tick_params(axis='x', which='major', width=tw["x_major"])
                if tw.get("x_minor") is not None:
                    ax.tick_params(axis='x', which='minor', width=tw["x_minor"]) 
                if tw.get("y_major") is not None:
                    ax.tick_params(axis='y', which='major', width=tw["y_major"]) 
                if tw.get("y_minor") is not None:
                    ax.tick_params(axis='y', which='minor', width=tw["y_minor"]) 
            except Exception:
                pass

            # Tick lengths
            tl = snap.get("tick_lengths", {})
            try:
                if tl.get("major") is not None:
                    ax.tick_params(axis='both', which='major', length=tl["major"])
                if tl.get("minor") is not None:
                    ax.tick_params(axis='both', which='minor', length=tl["minor"])
                if tl:
                    fig._tick_lengths = dict(tl)
            except Exception:
                pass

            # Tick direction
            try:
                tick_dir = snap.get("tick_direction", 'out')
                ax.tick_params(axis='both', which='both', direction=tick_dir)
                fig._tick_direction = tick_dir
            except Exception:
                pass

            # Labels list
            labels[:] = snap["labels"]

            # Data & lines
            if len(snap["lines"]) == len(ax.lines):
                for item in snap["lines"]:
                    i = item["index"]
                    ln = ax.lines[i]
                    ln.set_data(item["x"], item["y"])
                    ln.set_color(item["color"]) 
                    ln.set_linewidth(item["lw"]) 
                    ln.set_linestyle(item["ls"]) 
                    if item["marker"] is not None:
                        ln.set_marker(item["marker"]) 
                    if item.get("markersize") is not None:
                        try: ln.set_markersize(item["markersize"]) 
                        except Exception: pass
                    if item.get("mfc") is not None:
                        try: ln.set_markerfacecolor(item["mfc"]) 
                        except Exception: pass
                    if item.get("mec") is not None:
                        try: ln.set_markeredgecolor(item["mec"]) 
                        except Exception: pass
                    if item["alpha"] is not None:
                        ln.set_alpha(item["alpha"]) 

            # Replace lists
            x_data_list[:] = [np.array(a, copy=True) for a in snap["x_data_list"]]
            y_data_list[:] = [np.array(a, copy=True) for a in snap["y_data_list"]]
            orig_y[:]      = [np.array(a, copy=True) for a in snap["orig_y"]]
            offsets_list[:] = list(snap["offsets"]) 
            delta = snap.get("delta", delta)

            # Restore rotation angle
            if 'rotation_angle' in snap:
                ax._rotation_angle = snap['rotation_angle']

            # Restore legend position (stack_label_at_bottom)
            if 'stack_label_at_bottom' in snap:
                fig._stack_label_at_bottom = bool(snap['stack_label_at_bottom'])

            # Restore grid state
            if 'grid' in snap:
                try:
                    if snap['grid']:
                        ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                    else:
                        ax.grid(False)
                except Exception:
                    pass

            # CIF tick sets & label visibility (write back to batplot module globals)
            if _bp is not None and snap.get("cif_tick_series") is not None and hasattr(_bp, 'cif_tick_series'):
                try:
                    _bp.cif_tick_series[:] = [tuple(t) for t in snap["cif_tick_series"]]
                except Exception:
                    pass
            if _bp is not None and 'show_cif_hkl' in snap:
                try:
                    setattr(_bp, 'show_cif_hkl', bool(snap['show_cif_hkl']))
                except Exception:
                    pass
            if _bp is not None and 'show_cif_titles' in snap:
                try:
                    setattr(_bp, 'show_cif_titles', bool(snap['show_cif_titles']))
                except Exception:
                    pass
            # Redraw CIF ticks after restoration if available
            if hasattr(ax, '_cif_draw_func'):
                try:
                    ax._cif_draw_func()
                except Exception:
                    pass

            # Restore label texts (keep numbering style)
            for i, txt in enumerate(label_text_objects):
                base = labels[i] if i < len(labels) else ""
                txt.set_text(f"{i+1}: {base}")

            update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
            try:
                globals()['tick_state'] = tick_state
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                try: fig.canvas.draw_idle()
                except Exception: pass
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Error restoring state: {e}")


    while True:
        print_main_menu()
        key = input("Press a key: ")


        # NEW: disable 'y' and 'd' in stack mode
        if args.stack and key in ('y', 'd'):
            print("Option disabled in --stack mode.")
            continue

        if key == 'q':
            confirm = input(colorize_prompt("Quit interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            if confirm == 'y':
                break
            else:
                continue
        elif key == 'z':  # toggle hkl labels on CIF ticks (non-blocking)
            try:
                # Flip visibility flag in batplot module
                cur = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else False
                if _bp is not None:
                    setattr(_bp, 'show_cif_hkl', not cur)
                # Avoid re-entrant extension while redrawing
                prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                if _bp is not None:
                    setattr(_bp, 'cif_extend_suspended', True)
                if hasattr(ax, '_cif_draw_func'):
                    ax._cif_draw_func()
                if _bp is not None:
                    setattr(_bp, 'cif_extend_suspended', prev_ext)
                # Count visible labels
                n_labels = 0
                if bool(getattr(_bp, 'show_cif_hkl', False)) and hasattr(ax, '_cif_tick_art'):
                    for art in getattr(ax, '_cif_tick_art'):
                        try:
                            if hasattr(art, 'get_text') and '(' in art.get_text():
                                n_labels += 1
                        except Exception:
                            pass
                print(f"CIF hkl labels {'ON' if bool(getattr(_bp,'show_cif_hkl', False)) else 'OFF'} (visible labels: {n_labels}).")
            except Exception as e:
                print(f"Error toggling hkl labels: {e}")
            continue
        elif key == 'h':  # legend submenu
            try:
                while True:
                    print("\n\033[1mLegend submenu:\033[0m")
                    print(f"  {colorize_menu('v: show/hide curve names')}")
                    current_pos = "bottom-right" if getattr(fig, '_stack_label_at_bottom', False) else "top-right"
                    print(f"  {colorize_menu(f's: legend position (current: {current_pos})')}")
                    print(f"  {colorize_menu('q: back to main menu')}")
                    sub_key = input("Choose: ").strip().lower()
                    
                    if sub_key == 'q':
                        break
                    elif sub_key == 'v':
                        # Toggle curve name labels visibility
                        first_visible = label_text_objects[0].get_visible() if label_text_objects else True
                        new_state = not first_visible
                        for lbl in label_text_objects:
                            lbl.set_visible(new_state)
                        fig._curve_names_visible = new_state
                        stack_label_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, stack_label_bottom)
                        fig.canvas.draw_idle()
                        print(f"Curve name labels {'ON' if new_state else 'OFF'}.")
                    elif sub_key == 's':
                        # Toggle label position between top-right and bottom-right
                        current_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        fig._stack_label_at_bottom = not current_bottom
                        new_pos = "bottom-right" if fig._stack_label_at_bottom else "top-right"
                        update_labels(ax, y_data_list, label_text_objects, args.stack, fig._stack_label_at_bottom)
                        fig.canvas.draw_idle()
                        print(f"Legend position changed to {new_pos}.")
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in legend submenu: {e}")
            continue
        elif key == 'j':  # toggle CIF title labels (filename labels)
            try:
                # Flip visibility flag for CIF titles
                cur = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
                if _bp is not None:
                    setattr(_bp, 'show_cif_titles', not cur)
                # Avoid re-entrant extension while redrawing
                prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                if _bp is not None:
                    setattr(_bp, 'cif_extend_suspended', True)
                if hasattr(ax, '_cif_draw_func'):
                    ax._cif_draw_func()
                if _bp is not None:
                    setattr(_bp, 'cif_extend_suspended', prev_ext)
                print(f"CIF title labels {'ON' if bool(getattr(_bp,'show_cif_titles', True)) else 'OFF'}.")
            except Exception as e:
                print(f"Error toggling CIF titles: {e}")
            continue
        elif key == 'b':  # <-- UNDO
            restore_state()
            continue
        elif key == 'n':
            try:
                toggle_crosshair()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            continue
        elif key == 's':
            # Save current interactive session with numbered overwrite picker
            try:
                folder = os.getcwd()
                files = []
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
                    print("Canceled.")
                    continue
                target_path = None
                # Overwrite by number
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            print("Canceled.")
                            continue
                        target_path = os.path.join(folder, name)
                        skip_confirm = True  # Already confirmed above
                    else:
                        print("Invalid number.")
                        continue
                else:
                    # New name, allow relative or absolute
                    name = choice
                    root, ext = os.path.splitext(name)
                    if ext == '':
                        name = name + '.pkl'
                    target_path = name if os.path.isabs(name) else os.path.join(folder, name)
                    skip_confirm = False  # Let dump_session ask
                    if os.path.exists(target_path):
                        yn = input(f"'{os.path.basename(target_path)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            print("Canceled.")
                            continue
                        skip_confirm = True  # Already confirmed
                # Delegate to session dumper
                _bp_dump_session(
                    target_path,
                    fig=fig,
                    ax=ax,
                    x_data_list=x_data_list,
                    y_data_list=y_data_list,
                    orig_y=orig_y,
                    offsets_list=offsets_list,
                    labels=labels,
                    delta=delta,
                    args=args,
                    tick_state=tick_state,
                    cif_tick_series=(getattr(_bp, 'cif_tick_series', None) if _bp is not None else None),
                    cif_hkl_map=(getattr(_bp, 'cif_hkl_map', None) if _bp is not None else None),
                    cif_hkl_label_map=(getattr(_bp, 'cif_hkl_label_map', None) if _bp is not None else None),
                    show_cif_hkl=(bool(getattr(_bp,'show_cif_hkl', False)) if _bp is not None else False),
                    show_cif_titles=(bool(getattr(_bp,'show_cif_titles', True)) if _bp is not None else True),
                    skip_confirm=skip_confirm,
                )
                print(f"Saved session to {target_path}")
            except Exception as e:
                print(f"Error saving session: {e}")
            continue
        elif key == 'w':  # hidden game remains on 'i'
            play_jump_game(); continue
        elif key == 'c':
            try:
                has_cif = False
                try:
                    has_cif = any(f.lower().endswith('.cif') for f in args.files)
                except Exception:
                    pass
                while True:
                    print("\033[1mColor menu:\033[0m")
                    print(f"  {colorize_menu('m : manual color mapping  (e.g., 1:red 2:#00B006)')}")
                    print(f"  {colorize_menu('p : apply colormap palette to a range (e.g., 1-3 viridis)')}")
                    print(f"  {colorize_menu('s : spine colors (e.g., w:red a:#4561F7 for top & left)')}")
                    if has_cif and (_bp is not None and getattr(_bp, 'cif_tick_series', None)):
                        print(f"  {colorize_menu('t : change CIF tick set color (e.g., 1:red 2:#888888)')}")
                    print(f"  {colorize_menu('q : return to main menu')}")
                    sub = input(colorize_prompt("Choose (m/p/s/t/q): ")).strip().lower()
                    if sub == 'q':
                        break
                    if sub == '':
                        continue
                    if sub == 'm':
                        print("Current curves (q to cancel):")
                        for idx, label in enumerate(labels):
                            print(f"{idx+1}: {label}")
                        color_input = input("Enter colors (e.g., 1:red 2:#00B006) or q: ").strip()
                        if not color_input or color_input.lower() == 'q':
                            print("Canceled.")
                        else:
                            push_state("color-manual")
                            entries = color_input.split()
                            for entry in entries:
                                if ":" not in entry:
                                    print(f"Skip malformed token: {entry}")
                                    continue
                                idx_str, color = entry.split(":", 1)
                                try:
                                    i = int(idx_str) - 1
                                    if 0 <= i < len(ax.lines):
                                        ax.lines[i].set_color(color)
                                    else:
                                        print(f"Index out of range: {idx_str}")
                                except ValueError:
                                    print(f"Bad index: {idx_str}")
                            # Update label colors to match new curve colors
                            update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                    elif sub == 's':
                        # Spine colors (w=top, a=left, s=bottom, d=right)
                        print("Set spine colors (with matching tick and label colors):")
                        print(colorize_inline_commands("  w : top spine    | a : left spine"))
                        print(colorize_inline_commands("  s : bottom spine | d : right spine"))
                        print(colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
                        line = input("Enter mappings (e.g., w:red a:#4561F7) or q: ").strip()
                        if not line or line.lower() == 'q':
                            print("Canceled.")
                        else:
                            push_state("color-spine")
                            # Map wasd to spine names
                            key_to_spine = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}
                            tokens = line.split()
                            for token in tokens:
                                if ':' not in token:
                                    print(f"Skip malformed token: {token}")
                                    continue
                                key_part, color = token.split(':', 1)
                                key_part = key_part.lower()
                                if key_part not in key_to_spine:
                                    print(f"Unknown key: {key_part} (use w/a/s/d)")
                                    continue
                                spine_name = key_to_spine[key_part]
                                if spine_name not in ax.spines:
                                    print(f"Spine '{spine_name}' not found.")
                                    continue
                                try:
                                    # Set spine color
                                    ax.spines[spine_name].set_edgecolor(color)
                                    # Set tick colors and axis label color for this axis
                                    if spine_name in ('top', 'bottom'):
                                        ax.tick_params(axis='x', which='both', colors=color)
                                        ax.xaxis.label.set_color(color)
                                    else:  # left or right
                                        ax.tick_params(axis='y', which='both', colors=color)
                                        ax.yaxis.label.set_color(color)
                                    print(f"Set {spine_name} spine to {color}")
                                except Exception as e:
                                    print(f"Error setting {spine_name} color: {e}")
                            fig.canvas.draw()
                    elif sub == 't' and has_cif and (_bp is not None and getattr(_bp, 'cif_tick_series', None)):
                        cts = getattr(_bp, 'cif_tick_series', [])
                        print("Current CIF tick sets:")
                        for i,(lab, fname, *_rest) in enumerate(cts):
                            print(f"  {i+1}: {lab} ({os.path.basename(fname)})")
                        line = input("Enter mappings (e.g., 1:red 2:#555555) or q: ").strip()
                        if not line or line.lower()=='q':
                            print("Canceled.")
                        else:
                            mappings = line.split()
                            for token in mappings:
                                if ':' not in token:
                                    print(f"Skip malformed token: {token}")
                                    continue
                                idx_s, col = token.split(':',1)
                                try:
                                    idx_i = int(idx_s)-1
                                    if 0 <= idx_i < len(cts):
                                        lab,fname,peaksQ,wl,qmax_sim,_c = cts[idx_i]
                                        cts[idx_i] = (lab,fname,peaksQ,wl,qmax_sim,col)
                                    else:
                                        print(f"Index out of range: {idx_s}")
                                except ValueError:
                                    print(f"Bad index: {idx_s}")
                            setattr(_bp, 'cif_tick_series', cts)
                            if hasattr(ax,'_cif_draw_func'):
                                ax._cif_draw_func()
                        fig.canvas.draw()
                    elif sub == 'p':
                        base_palettes = ['viridis', 'plasma', 'inferno', 'magma', 'batlow']
                        extras = []
                        if 'turbo' in plt.colormaps():
                            extras.append('turbo')
                        if 'batlowK' in plt.colormaps():
                            extras.append('batlowK')
                        print("Common perceptually uniform palettes:")
                        print("  " + ", ".join(base_palettes + extras[:2]))
                        print(colorize_inline_commands("Example: 1-4 viridis   or: all magma_r   or: 1-3,5 plasma, _r for reverse"))
                        line = input("Enter range(s) and palette (e.g., '1-3 viridis') or q: ").strip()
                        if not line or line.lower() == 'q':
                            print("Canceled.")
                        else:
                            parts = line.split()
                            if len(parts) < 2:
                                print("Need range(s) and palette.")
                            else:
                                palette_name = parts[-1]
                                range_part = " ".join(parts[:-1]).replace(" ", "")
                                def parse_ranges(spec, total):
                                    spec = spec.lower()
                                    if spec == 'all':
                                        return list(range(total))
                                    result = set()
                                    tokens = spec.split(',')
                                    for tok in tokens:
                                        if not tok:
                                            continue
                                        if '-' in tok:
                                            try:
                                                a, b = tok.split('-', 1)
                                                start = int(a) - 1
                                                end = int(b) - 1
                                                if start > end:
                                                    start, end = end, start
                                                for i in range(start, end + 1):
                                                    if 0 <= i < total:
                                                        result.add(i)
                                            except ValueError:
                                                print(f"Bad range token: {tok}")
                                        else:
                                            try:
                                                i = int(tok) - 1
                                                if 0 <= i < total:
                                                    result.add(i)
                                                else:
                                                    print(f"Index out of range: {tok}")
                                            except ValueError:
                                                print(f"Bad index token: {tok}")
                                    return sorted(result)
                                indices = parse_ranges(range_part, len(ax.lines))
                                if not indices:
                                    print("No valid indices parsed.")
                                else:
                                    try:
                                        cmap = plt.get_cmap(palette_name)
                                    except ValueError:
                                        cmap = None
                                    if cmap is None and palette_name.lower().startswith("batlow"):
                                        try:
                                            import importlib
                                            cmc = importlib.import_module('cmcrameri.cm')
                                            attr = palette_name.lower()
                                            if hasattr(cmc, attr):
                                                cmap = getattr(cmc, attr)
                                            elif hasattr(cmc, 'batlow'):
                                                cmap = getattr(cmc, 'batlow')
                                        except Exception:
                                            pass
                                    if cmap is None:
                                        print(f"Unknown colormap '{palette_name}'.")
                                    else:
                                        push_state("color-palette")
                                        nsel = len(indices)
                                        low_clip = 0.08
                                        high_clip = 0.85
                                        if nsel == 1:
                                            colors = [cmap(0.55)]
                                        elif nsel == 2:
                                            colors = [cmap(low_clip), cmap(high_clip)]
                                        else:
                                            positions = np.linspace(low_clip, high_clip, nsel)
                                            colors = [cmap(p) for p in positions]
                                        for c_idx, line_idx in enumerate(indices):
                                            ax.lines[line_idx].set_color(colors[c_idx])
                                        # Update label colors to match new curve colors
                                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                                        fig.canvas.draw()
                                        print(f"Applied '{palette_name}' to curves: " +
                                              ", ".join(str(i+1) for i in indices))
                    else:
                        print("Unknown color submenu option.")
            except Exception as e:
                print(f"Error in color menu: {e}")
        elif key == 'r':
            try:
                has_cif = False
                try:
                    has_cif = any(f.lower().endswith('.cif') for f in args.files)
                except Exception:
                    pass
                while True:
                    rename_opts = "c=curve"
                    if has_cif:
                        rename_opts += ", t=cif tick label"
                    rename_opts += ", x=x-axis, y=y-axis, q=return"
                    mode = input(f"Rename ({rename_opts}): ").strip().lower()
                    if mode == 'q':
                        break
                    if mode == '':
                        continue
                    if mode == 'c':
                        print("Tip: Use LaTeX/mathtext for special characters:")
                        print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
                        print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
                        idx_in = input("Curve number to rename (q=cancel): ").strip()
                        if not idx_in or idx_in.lower() == 'q':
                            print("Canceled.")
                            continue
                        try:
                            idx = int(idx_in) - 1
                        except ValueError:
                            print("Invalid index.")
                            continue
                        if not (0 <= idx < len(labels)):
                            print("Invalid index.")
                            continue
                        new_label = input("New curve label (q=cancel): ")
                        if not new_label or new_label.lower() == 'q':
                            print("Canceled.")
                            continue
                        push_state("rename-curve")
                        labels[idx] = new_label
                        label_text_objects[idx].set_text(f"{idx+1}: {new_label}")
                        fig.canvas.draw()
                    elif mode == 't':
                        cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                        if not cts:
                            print("No CIF tick sets to rename.")
                            continue
                        for i,(lab, fname, *_rest) in enumerate(cts):
                            print(f"  {i+1}: {lab} ({os.path.basename(fname)})")
                        s = input("CIF tick number to rename (q=cancel): ").strip()
                        if not s or s.lower()=='q':
                            print("Canceled."); continue
                        try:
                            idx = int(s)-1
                            if not (0 <= idx < len(cts)):
                                print("Index out of range."); continue
                        except ValueError:
                            print("Bad index."); continue
                        print("Tip: Use LaTeX/mathtext for special characters:")
                        print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
                        print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
                        new_name = input("New CIF tick label (q=cancel): ")
                        if not new_name or new_name.lower()=='q':
                            print("Canceled."); continue
                        lab,fname,peaksQ,wl,qmax_sim,color = cts[idx]
                        # Suspend extension while updating label
                        if _bp is not None:
                            setattr(_bp, 'cif_extend_suspended', True)
                        if hasattr(ax, '_cif_tick_art'):
                            try:
                                for art in list(getattr(ax, '_cif_tick_art', [])):
                                    try:
                                        art.remove()
                                    except Exception:
                                        pass
                                ax._cif_tick_art = []
                            except Exception:
                                pass
                        cts[idx] = (new_name, fname, peaksQ, wl, qmax_sim, color)
                        setattr(_bp, 'cif_tick_series', cts)
                        if hasattr(ax,'_cif_draw_func'): ax._cif_draw_func()
                        fig.canvas.draw()
                        if _bp is not None:
                            setattr(_bp, 'cif_extend_suspended', False)
                    elif mode in ('x','y'):
                        print("Enter new axis label (q=cancel).")
                        print("Tip: Use LaTeX/mathtext for special characters:")
                        print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
                        print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
                        new_axis = input("New axis label: ")
                        if not new_axis or new_axis.lower() == 'q':
                            print("Canceled.")
                            continue
                        new_axis = normalize_label_text(new_axis)
                        push_state("rename-axis")
                        # Freeze layout and preserve current pad via one-shot pending to avoid drift
                        try:
                            fig.set_layout_engine('none')
                        except Exception:
                            try:
                                fig.set_tight_layout(False)
                            except Exception:
                                pass
                        try:
                            fig.set_constrained_layout(False)
                        except Exception:
                            pass
                        if mode == 'x':
                            # Preserve current pad exactly once after rename
                            try:
                                ax._pending_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
                            except Exception:
                                pass
                            ax.xaxis.label.set_text(new_axis)
                            position_top_xlabel()
                            position_bottom_xlabel()
                        else:
                            try:
                                ax._pending_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
                            except Exception:
                                pass
                            ax.yaxis.label.set_text(new_axis)
                            position_right_ylabel()
                            position_left_ylabel()
                        sync_fonts()
                        fig.canvas.draw()
                    else:
                        print("Invalid choice.")
                    # loop continues until q
            except Exception as e:
                print(f"Error: {e}")
        elif key == 'a':
            try:
                if not args.stack:
                    print('Be careful, changing the arrangement may lead to a mess! If you want to rearrange the curves, use "--stack".')
                print("Current curve order:")
                for idx, label in enumerate(labels):
                    print(f"{idx+1}: {label}")
                new_order_str = input("Enter new order (space-separated indices, q=cancel): ").strip()
                if not new_order_str or new_order_str.lower() == 'q':
                    print("Canceled.")
                    continue
                new_order = [int(i)-1 for i in new_order_str.strip().split()]
                if len(new_order) != len(labels):
                    print("Error: Number of indices does not match number of curves.")
                    continue
                if any(i < 0 or i >= len(labels) for i in new_order):
                    print("Error: Invalid index in order list.")
                    continue

                push_state("rearrange")

                original_styles = []
                for ln in ax.lines:
                    original_styles.append({
                        "color": ln.get_color(),
                        "linewidth": ln.get_linewidth(),
                        "linestyle": ln.get_linestyle(),
                        "alpha": ln.get_alpha(),
                        "marker": ln.get_marker(),
                        "markersize": ln.get_markersize(),
                        "markerfacecolor": ln.get_markerfacecolor(),
                        "markeredgecolor": ln.get_markeredgecolor()
                    })
                reordered_styles = [original_styles[i] for i in new_order]
                xlim_current = ax.get_xlim()

                x_data_list[:]      = [x_data_list[i] for i in new_order]
                orig_y[:]           = [orig_y[i] for i in new_order]
                y_data_list[:]      = [y_data_list[i] for i in new_order]
                labels[:]           = [labels[i] for i in new_order]
                label_text_objects[:] = [label_text_objects[i] for i in new_order]
                x_full_list[:]      = [x_full_list[i] for i in new_order]
                raw_y_full_list[:]  = [raw_y_full_list[i] for i in new_order]
                offsets_list[:]     = [offsets_list[i] for i in new_order]

                if args.stack:
                    offset_local = 0.0
                    for i, (x_plot, y_norm, style) in enumerate(zip(x_data_list, orig_y, reordered_styles)):
                        y_plot_offset = y_norm + offset_local
                        y_data_list[i] = y_plot_offset
                        offsets_list[i] = offset_local
                        ln = ax.lines[i]
                        ln.set_data(x_plot, y_plot_offset)
                        ln.set_color(style["color"]) 
                        ln.set_linewidth(style["linewidth"]) 
                        ln.set_linestyle(style["linestyle"]) 
                        ln.set_alpha(style["alpha"]) 
                        ln.set_marker(style["marker"]) 
                        ln.set_markersize(style["markersize"]) 
                        ln.set_markerfacecolor(style["markerfacecolor"]) 
                        ln.set_markeredgecolor(style["markeredgecolor"]) 
                        y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                        gap = y_range + (delta * (y_range if args.autoscale else 1.0))
                        offset_local -= gap
                else:
                    offset_local = 0.0
                    for i, (x_plot, y_norm, style) in enumerate(zip(x_data_list, orig_y, reordered_styles)):
                        y_plot_offset = y_norm + offset_local
                        y_data_list[i] = y_plot_offset
                        offsets_list[i] = offset_local
                        ln = ax.lines[i]
                        ln.set_data(x_plot, y_plot_offset)
                        ln.set_color(style["color"]) 
                        ln.set_linewidth(style["linewidth"]) 
                        ln.set_linestyle(style["linestyle"]) 
                        ln.set_alpha(style["alpha"]) 
                        ln.set_marker(style["marker"]) 
                        ln.set_markersize(style["markersize"]) 
                        ln.set_markerfacecolor(style["markerfacecolor"]) 
                        ln.set_markeredgecolor(style["markeredgecolor"]) 
                        increment = (y_norm.max() - y_norm.min()) * delta if (args.autoscale and y_norm.size) else delta
                        offset_local += increment

                for i, (txt, lab) in enumerate(zip(label_text_objects, labels)):
                    txt.set_text(f"{i+1}: {lab}")
                # Preserve current axis titles (respect 't' menu toggles like bt/lt)
                ax.set_xlim(xlim_current)
                # Do not reset xlabel/ylabel here; rearrange should not change title visibility
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                fig.canvas.draw()
            except Exception as e:
                print(f"Error rearranging curves: {e}")
        elif key == 'x':
            while True:
                try:
                    current_xlim = ax.get_xlim()
                    print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                    rng = input("Enter new X range (min max) or 'full' (q=back): ").strip()
                    if not rng or rng.lower() == 'q':
                        break
                    push_state("xrange")
                    if rng.lower() == 'full':
                        new_min = min(xf.min() for xf in x_full_list if xf.size)
                        new_max = max(xf.max() for xf in x_full_list if xf.size)
                    else:
                        new_min, new_max = map(float, rng.split())
                    ax.set_xlim(new_min, new_max)
                    for i in range(len(labels)):
                        xf = x_full_list[i]; yf_raw = raw_y_full_list[i]
                        mask = (xf>=new_min) & (xf<=new_max)
                        x_sub = xf[mask]; y_sub_raw = yf_raw[mask]
                        if x_sub.size == 0:
                            ax.lines[i].set_data([], [])
                            y_data_list[i] = np.array([]); orig_y[i] = np.array([]); continue
                        # Auto-normalize for --stack mode, or explicit --norm flag
                        should_normalize = args.stack or getattr(args, 'norm', False)
                        if should_normalize:
                            if y_sub_raw.size:
                                y_min = float(y_sub_raw.min())
                                y_max = float(y_sub_raw.max())
                                span = y_max - y_min
                                if span > 0:
                                    y_sub_norm = (y_sub_raw - y_min) / span
                                else:
                                    y_sub_norm = np.zeros_like(y_sub_raw)
                            else:
                                y_sub_norm = y_sub_raw
                        else:
                            y_sub_norm = y_sub_raw
                        offset_val = offsets_list[i]
                        y_with_offset = y_sub_norm + offset_val
                        ax.lines[i].set_data(x_sub, y_with_offset)
                        x_data_list[i] = x_sub
                        y_data_list[i] = y_with_offset
                        orig_y[i] = y_sub_norm
                    ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                    update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                    # Extend CIF ticks after x-range change
                    try:
                        if hasattr(ax, '_cif_extend_func'):
                            ax._cif_extend_func(ax.get_xlim()[1])
                    except Exception:
                        pass
                    try:
                        if hasattr(ax, '_cif_draw_func'):
                            ax._cif_draw_func()
                    except Exception:
                        pass
                    fig.canvas.draw()
                except Exception as e:
                    print(f"Error setting X-axis range: {e}")
        elif key == 'y':  # <-- Y-RANGE HANDLER (now only reachable if not args.stack)
            while True:
                try:
                    current_ylim = ax.get_ylim()
                    print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                    rng = input("Enter new Y range (min max), 'auto', or 'full' (q=back): ").strip().lower()
                    if not rng or rng == 'q':
                        break
                    push_state("yrange")
                    if rng == 'auto':
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                    else:
                        if rng == 'full':
                            all_min = None
                            all_max = None
                            for arr in y_data_list:
                                if arr.size:
                                    mn = float(arr.min())
                                    mx = float(arr.max())
                                    all_min = mn if all_min is None else min(all_min, mn)
                                    all_max = mx if all_max is None else max(all_max, mx)
                            if all_min is None or all_max is None:
                                print("No data to compute full Y range.")
                                continue
                            y_min, y_max = all_min, all_max
                        else:
                            parts = rng.split()
                            if len(parts) != 2:
                                print("Need exactly two numbers for Y range.")
                                continue
                            y_min, y_max = map(float, parts)
                            if y_min == y_max:
                                print("Warning: min == max; expanding slightly.")
                                eps = abs(y_min)*1e-6 if y_min != 0 else 1e-6
                                y_min -= eps
                                y_max += eps
                        ax.set_ylim(y_min, y_max)
                    update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                    fig.canvas.draw_idle()
                    print(f"Y range set to {ax.get_ylim()}")
                except Exception as e:
                    print(f"Error setting Y-axis range: {e}")
        elif key == 'd':  # <-- DELTA / OFFSET HANDLER (now only reachable if not args.stack)
            print("\n\033[1mOffset adjustment menu:\033[0m")
            print(f"  {colorize_menu('1-{}: adjust individual curve offset'.format(len(labels)))}")
            print(f"  {colorize_menu('a: adjust total offset (baseline shift)')}")
            print(f"  {colorize_menu('r: reset all offsets to 0')}")
            print(f"  {colorize_menu('d: change delta spacing (original behavior)')}")
            print(f"  {colorize_menu('q: back to main menu')}")
            
            while True:
                offset_cmd = input("Offset> ").strip().lower()
                
                if offset_cmd == 'q' or offset_cmd == '':
                    break
                    
                elif offset_cmd == 'r':
                    # Reset all offsets to 0
                    try:
                        push_state("reset-offsets")
                        for i in range(len(labels)):
                            # Reset to normalized data without any offset
                            y_norm = orig_y[i]
                            y_data_list[i] = y_norm.copy()
                            offsets_list[i] = 0.0
                            ax.lines[i].set_data(x_data_list[i], y_norm)
                        
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        print("All offsets reset to 0")
                    except Exception as e:
                        print(f"Error resetting offsets: {e}")
                    
                elif offset_cmd == 'a':
                    # Adjust total offset (baseline shift for all curves)
                    try:
                        # Calculate current average offset
                        current_avg = sum(offsets_list) / len(offsets_list) if offsets_list else 0.0
                        total_offset_input = input("Enter total offset value (current avg: {:.4g}): ".format(current_avg)).strip()
                        if not total_offset_input:
                            print("Canceled.")
                            continue
                        
                        total_offset = float(total_offset_input)
                        push_state("total-offset")
                        
                        # Add total offset to all curves
                        for i in range(len(labels)):
                            y_norm = orig_y[i]
                            current_individual = offsets_list[i]
                            new_offset = current_individual + total_offset
                            offsets_list[i] = new_offset
                            y_with_offset = y_norm + new_offset
                            y_data_list[i] = y_with_offset
                            ax.lines[i].set_data(x_data_list[i], y_with_offset)
                        
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        print("Total offset of {:.4g} applied to all curves".format(total_offset))
                        
                    except ValueError:
                        print("Invalid offset value")
                    except Exception as e:
                        print(f"Error applying total offset: {e}")
                        
                elif offset_cmd == 'd':
                    # Original delta spacing behavior
                    if len(labels) <= 1:
                        print("Warning: Only one curve loaded; applying an offset is not recommended.")
                    try:
                        new_delta_str = input(f"Enter new offset spacing (current={delta}): ").strip()
                        if not new_delta_str:
                            print("Canceled.")
                            continue
                        new_delta = float(new_delta_str)
                        push_state("delta-spacing")
                        delta = new_delta
                        offsets_list[:] = []
                        if args.stack:
                            current_offset = 0.0
                            for i, y_norm in enumerate(orig_y):
                                y_with_offset = y_norm + current_offset
                                y_data_list[i] = y_with_offset
                                offsets_list.append(current_offset)
                                ax.lines[i].set_data(x_data_list[i], y_with_offset)
                                y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                                gap = y_range + (delta * (y_range if args.autoscale else 1.0))
                                current_offset -= gap
                        else:
                            current_offset = 0.0
                            for i, y_norm in enumerate(orig_y):
                                y_with_offset = y_norm + current_offset
                                y_data_list[i] = y_with_offset
                                offsets_list.append(current_offset)
                                ax.lines[i].set_data(x_data_list[i], y_with_offset)
                                increment = (y_norm.max() - y_norm.min()) * delta if (args.autoscale and y_norm.size) else delta
                                current_offset += increment
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                        fig.canvas.draw()
                        print(f"Offsets updated with delta={delta}")
                    except ValueError:
                        print("Invalid delta value")
                    except Exception as e:
                        print(f"Error updating offsets: {e}")
                        
                elif offset_cmd.isdigit():
                    # Adjust individual curve offset
                    try:
                        curve_num = int(offset_cmd)
                        if curve_num < 1 or curve_num > len(labels):
                            print("Invalid curve number (1-{})".format(len(labels)))
                            continue
                        
                        idx = curve_num - 1
                        current_offset = offsets_list[idx]
                        
                        individual_offset_input = input("Enter offset for curve {} (current: {:.4g}): ".format(
                            curve_num, current_offset)).strip()
                        if not individual_offset_input:
                            print("Canceled.")
                            continue
                        
                        individual_offset = float(individual_offset_input)
                        push_state("curve-{}-offset".format(curve_num))
                        
                        # Apply individual offset to this curve
                        y_norm = orig_y[idx]
                        offsets_list[idx] = individual_offset
                        y_with_offset = y_norm + individual_offset
                        y_data_list[idx] = y_with_offset
                        ax.lines[idx].set_data(x_data_list[idx], y_with_offset)
                        
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        print("Curve {} offset set to: {:.4g}".format(curve_num, individual_offset))
                        
                    except ValueError:
                        print("Invalid offset value")
                    except Exception as e:
                        print(f"Error setting curve offset: {e}")
                else:
                    print("Unknown command. Use 1-{}, a, r, d, or q".format(len(labels)))
        elif key == 'ro':
            # Rotate plot 90 degrees clockwise or counter-clockwise
            # Only allowed in normal XY mode (not stack mode)
            if args.stack:
                print("Rotation is disabled in --stack mode.")
                continue
            
            while True:
                print("\nRotate plot:")
                print("  c: clockwise (90°)")
                print("  a: anti-clockwise (-90°)")
                print("  q: back")
                
                rot_cmd = input("Rotate> ").strip().lower()
                
                if rot_cmd == 'q' or rot_cmd == '':
                    break
                
                if rot_cmd == 'c' or rot_cmd == 'a':
                    try:
                        push_state("rotate")
                        
                        # Determine rotation direction
                        angle_delta = 90 if rot_cmd == 'c' else -90
                        ax._rotation_angle = (ax._rotation_angle + angle_delta) % 360
                        
                        # Swap X and Y data for all curves - MUST COPY to avoid mutation
                        for i in range(len(labels)):
                            xdata = x_data_list[i].copy()  # COPY to avoid mutation
                            ydata = y_data_list[i].copy()  # COPY to avoid mutation
                            
                            if rot_cmd == 'c':
                                # Clockwise: X->Y, -Y->X
                                new_x = -ydata
                                new_y = xdata
                            else:
                                # Counter-clockwise: Y->X, -X->Y  
                                new_x = ydata
                                new_y = -xdata
                            
                            x_data_list[i] = new_x
                            y_data_list[i] = new_y
                            ax.lines[i].set_data(new_x, new_y)
                            
                            # Also update orig_y (normalized data without offset)
                            if i < len(orig_y):
                                orig_y_data = orig_y[i].copy()  # COPY original
                                if rot_cmd == 'c':
                                    # For clockwise, orig_y should come from old x_data 
                                    # But we need the normalized version, so recalculate from offset
                                    offset_val = offsets_list[i] if i < len(offsets_list) else 0.0
                                    orig_y[i] = xdata - offset_val
                                else:
                                    # For counter-clockwise
                                    offset_val = offsets_list[i] if i < len(offsets_list) else 0.0
                                    orig_y[i] = -(xdata - offset_val)
                        
                        # Also rotate full data - MUST COPY
                        for i in range(len(x_full_list)):
                            xf = x_full_list[i].copy()  # COPY to avoid mutation
                            yf = raw_y_full_list[i].copy()  # COPY to avoid mutation
                            
                            if rot_cmd == 'c':
                                x_full_list[i] = -yf
                                raw_y_full_list[i] = xf
                            else:
                                x_full_list[i] = yf
                                raw_y_full_list[i] = -xf
                        
                        # Swap axis limits
                        xlim = ax.get_xlim()
                        ylim = ax.get_ylim()
                        if rot_cmd == 'c':
                            ax.set_xlim(-ylim[1], -ylim[0])
                            ax.set_ylim(xlim)
                        else:
                            ax.set_xlim(ylim)
                            ax.set_ylim(-xlim[1], -xlim[0])
                        
                        # Swap axis labels
                        xlabel = ax.get_xlabel()
                        ylabel = ax.get_ylabel()
                        ax.set_xlabel(ylabel)
                        ax.set_ylabel(xlabel)
                        
                        # Relimit and redraw
                        ax.relim()
                        ax.autoscale_view()
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        
                        direction = "clockwise" if rot_cmd == 'c' else "anti-clockwise"
                        print(f"Plot rotated 90° {direction}. Current rotation: {ax._rotation_angle}°")
                        print("WARNING: Rotation is experimental. Offsets may need adjustment.")
                        
                    except Exception as e:
                        print(f"Error rotating plot: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("Invalid choice")
        elif key == 'l':
            try:
                while True:
                    print("\033[1mLine submenu:\033[0m")
                    print(f"  {colorize_menu('c  : change curve line widths')}")
                    print(f"  {colorize_menu('f  : change frame (axes spines) and tick widths')}")
                    print(f"  {colorize_menu('g  : toggle grid lines')}")
                    print(f"  {colorize_menu('l  : show only lines (no markers) for all curves')}")
                    print(f"  {colorize_menu('ld : show line and dots (markers) for all curves')}")
                    print(f"  {colorize_menu('d  : show only dots (no connecting line) for all curves')}")
                    print(f"  {colorize_menu('q  : return')}")
                    sub = input(colorize_prompt("Choose (c/f/g/l/ld/d/q): ")).strip().lower()
                    if sub == 'q':
                        break
                    if sub == '':
                        continue
                    if sub == 'c':
                        spec = input("Curve widths (single value OR mappings like '1:1.2 3:2', q=cancel): ").strip()
                        if not spec or spec.lower() == 'q':
                            print("Canceled.")
                        else:
                            push_state("linewidth")
                            if ":" in spec:
                                parts = spec.split()
                                for p in parts:
                                    if ":" not in p:
                                        print(f"Skip malformed token: {p}")
                                        continue
                                    idx_str, lw_str = p.split(":", 1)
                                    try:
                                        idx = int(idx_str) - 1
                                        lw = float(lw_str)
                                        if 0 <= idx < len(ax.lines):
                                            ax.lines[idx].set_linewidth(lw)
                                        else:
                                            print(f"Index out of range: {idx+1}")
                                    except ValueError:
                                        print(f"Bad token: {p}")
                            else:
                                try:
                                    lw = float(spec)
                                    for ln in ax.lines:
                                        ln.set_linewidth(lw)
                                except ValueError:
                                    print("Invalid width value.")
                            fig.canvas.draw()
                    elif sub == 'f':
                        fw_in = input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q: ").strip()
                        if not fw_in or fw_in.lower() == 'q':
                            print("Canceled.")
                        else:
                            push_state("framewidth")
                            parts = fw_in.split()
                            try:
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
                        for ln in ax.lines:
                            # Check if already in line-only mode (has line style and no marker)
                            current_ls = ln.get_linestyle()
                            current_marker = ln.get_marker()
                            # If already line-only (has line, no marker), skip
                            if current_ls not in ['None', '', ' ', 'none'] and current_marker in ['None', '', ' ', 'none', None]:
                                continue
                            # Otherwise, set to line-only
                            ln.set_linestyle('-')
                            ln.set_marker('None')
                        fig.canvas.draw()
                        print("Applied line-only style to all curves.")
                    elif sub == 'ld':
                        push_state("line+dots")
                        try:
                            msize_in = input("Marker size (blank=auto ~3*lw): ").strip()
                            custom_msize = float(msize_in) if msize_in else None
                        except ValueError:
                            custom_msize = None
                        for ln in ax.lines:
                            lw = ln.get_linewidth() or 1.0
                            ln.set_linestyle('-')
                            ln.set_marker('o')
                            msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
                            ln.set_markersize(msize)
                            col = ln.get_color()
                            try:
                                ln.set_markerfacecolor(col)
                                ln.set_markeredgecolor(col)
                            except Exception:
                                pass
                        fig.canvas.draw()
                        print("Applied line+dots style to all curves.")
                    elif sub == 'd':
                        push_state("dots-only")
                        try:
                            msize_in = input("Marker size (blank=auto ~3*lw): ").strip()
                            custom_msize = float(msize_in) if msize_in else None
                        except ValueError:
                            custom_msize = None
                        for ln in ax.lines:
                            lw = ln.get_linewidth() or 1.0
                            ln.set_linestyle('None')
                            ln.set_marker('o')
                            msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
                            ln.set_markersize(msize)
                            col = ln.get_color()
                            try:
                                ln.set_markerfacecolor(col)
                                ln.set_markeredgecolor(col)
                            except Exception:
                                pass
                        fig.canvas.draw()
                        print("Applied dots-only style to all curves.")
                    else:
                        print("Unknown submenu option.")
            except Exception as e:
                print(f"Error setting widths: {e}")
        elif key == 'f':
            while True:
                subkey = input(colorize_prompt("Font submenu (s=size, f=family, q=return): ")).strip().lower()
                if subkey == 'q':
                    break
                if subkey == '':
                    continue
                if subkey == 's':
                    try:
                        fs = input("Enter new font size (q=cancel): ").strip()
                        if not fs or fs.lower() == 'q':
                            print("Canceled.")
                        else:
                            push_state("font-change")
                            fs_val = float(fs)
                            apply_font_changes(new_size=fs_val)
                            # Reposition top/right labels to match new tick label sizes
                            position_top_xlabel()
                            position_right_ylabel()
                            fig.canvas.draw()
                    except Exception as e:
                        print(f"Error changing font size: {e}")
                elif subkey == 'f':
                    try:
                        print("Common publication fonts:")
                        print("  1) Arial")
                        print("  2) Helvetica")
                        print("  3) Times New Roman")
                        print("  4) STIXGeneral")
                        print("  5) DejaVu Sans")
                        ft_raw = input("Enter font number or family name (q=cancel): ").strip()
                        if not ft_raw or ft_raw.lower() == 'q':
                            print("Canceled.")
                        else:
                            font_map = {
                                '1': 'Arial',
                                '2': 'Helvetica',
                                '3': 'Times New Roman',
                                '4': 'STIXGeneral',
                                '5': 'DejaVu Sans'
                            }
                            ft = font_map.get(ft_raw, ft_raw)
                            push_state("font-change")
                            print(f"Setting font family to: {ft}")
                            apply_font_changes(new_family=ft)
                            # Reposition top/right labels to match new tick label sizes
                            position_top_xlabel()
                            position_right_ylabel()
                            fig.canvas.draw()
                    except Exception as e:
                        print(f"Error changing font family: {e}")
                else:
                    print("Invalid font submenu option.")
        elif key == 'g':
            try:
                while True:
                    choice = input(colorize_prompt("Resize submenu: (p=plot frame, c=canvas, q=cancel): ")).strip().lower()
                    if not choice:
                        continue
                    if choice == 'q':
                        break
                    if choice == 'p':
                        push_state("resize-frame")
                        resize_plot_frame()
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                    elif choice == 'c':
                        push_state("resize-canvas")
                        resize_canvas()
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in resize submenu: {e}")
        elif key == 'h':
            # Legend submenu
            try:
                while True:
                    print("\nLegend submenu:")
                    print("  v: show/hide curve names")
                    current_pos = "bottom-right" if getattr(fig, '_stack_label_at_bottom', False) else "top-right"
                    print(f"  s: legend position (current: {current_pos})")
                    print("  q: back to main menu")
                    sub_key = input("Choose: ").strip().lower()
                    
                    if sub_key == 'q':
                        break
                    elif sub_key == 'v':
                        push_state("curve-names")
                        # Check current visibility from first label
                        current_visible = True
                        if label_text_objects and len(label_text_objects) > 0:
                            try:
                                current_visible = label_text_objects[0].get_visible()
                            except Exception:
                                current_visible = True
                        
                        # Toggle all labels
                        new_visible = not current_visible
                        for txt in label_text_objects:
                            try:
                                txt.set_visible(new_visible)
                            except Exception:
                                pass
                        
                        # Store state on figure for persistence
                        fig._curve_names_visible = new_visible
                        
                        status = "shown" if new_visible else "hidden"
                        print(f"Curve names {status}")
                        stack_label_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, stack_label_bottom)
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                    elif sub_key == 's':
                        push_state("label-position")
                        # Toggle label position between top-right and bottom-right
                        current_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        fig._stack_label_at_bottom = not current_bottom
                        new_pos = "bottom-right" if fig._stack_label_at_bottom else "top-right"
                        update_labels(ax, y_data_list, label_text_objects, args.stack, fig._stack_label_at_bottom)
                        print(f"Legend position changed to {new_pos}.")
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in legend submenu: {e}")
        elif key == 't':
            try:
                while True:
                    print("\033[1mToggle help:\033[0m")
                    print(colorize_inline_commands("  wasd choose side: w=top, a=left, s=bottom, d=right"))
                    print(colorize_inline_commands("  1..5 choose what: 1=spine line, 2=major ticks, 3=minor ticks, 4=labels, 5=axis title"))
                    print(colorize_inline_commands("  Combine letter+number to toggle, e.g. 's2 w5 a4' (case-insensitive)"))
                    print(colorize_inline_commands("  i = invert tick direction, l = change tick length, list = show state, q = return"))
                    cmd = input("Enter code(s): ").strip().lower()
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
                    parts = cmd.split()
                    if parts == ['list']:
                        print_tick_state()
                        continue
                    push_state("tick-toggle")
                    # Track which sides need re-positioning of axis titles
                    need_pos = {
                        'bottom': False,  # bottom X title spacing
                        'top': False,     # top X duplicate title
                        'left': False,    # left Y title spacing
                        'right': False,   # right Y duplicate title
                    }
                    # New key aliases -> legacy/internal codes
                    alias_map = {
                        # Spines
                        's1':'bl', 'w1':'tl', 'a1':'ll', 'd1':'rl',
                        # Major tick marks
                        's2':'btcs', 'w2':'ttcs', 'a2':'ltcs', 'd2':'rtcs',
                        # Minor ticks
                        's3':'mbx', 'w3':'mtx', 'a3':'mly', 'd3':'mry',
                        # Labels
                        's4':'blb', 'w4':'tlb', 'a4':'llb', 'd4':'rlb',
                        # Axis titles
                        's5':'bt', 'w5':'tt', 'a5':'lt', 'd5':'rt',
                        # Small typo tolerance
                        'tics':'ttcs',
                    }
                    for p in parts:
                        if p in alias_map:
                            p = alias_map[p]
                        # Axis title toggles
                        if p in ('bt','tt','lt','rt'):
                            if p == 'bt':
                                # Use visibility toggle to avoid layout recalculation
                                label_obj = ax.xaxis.label
                                if label_obj.get_visible():
                                    # Store text before hiding
                                    if not hasattr(ax, '_stored_xlabel'):
                                        ax._stored_xlabel = label_obj.get_text()
                                    # Store current labelpad to restore later
                                    try:
                                        ax._stored_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
                                    except Exception:
                                        pass
                                    label_obj.set_visible(False)
                                    print("Hid bottom X axis title")
                                else:
                                    # Restore text if needed before showing
                                    if hasattr(ax, '_stored_xlabel') and ax._stored_xlabel:
                                        label_obj.set_text(ax._stored_xlabel)
                                    label_obj.set_visible(True)
                                    # Freeze any automatic layout to prevent margin reflow on toggle
                                    try:
                                        fig.set_layout_engine('none')
                                    except Exception:
                                        try:
                                            fig.set_tight_layout(False)
                                        except Exception:
                                            pass
                                    try:
                                        # On some MPL versions this exists; harmless otherwise
                                        fig.set_constrained_layout(False)
                                    except Exception:
                                        pass
                                    # Reapply a deterministic pad based on current bottom label visibility
                                    try:
                                        # Prefer exact stored pad if available; else compute from tick visibility
                                        if hasattr(ax, '_stored_xlabelpad') and ax._stored_xlabelpad is not None:
                                            desired_pad = ax._stored_xlabelpad
                                            # Set a one-shot pending pad for ui.position_bottom_xlabel to consume
                                            ax._pending_xlabelpad = desired_pad
                                        else:
                                            desired_pad = 14 if bool(tick_state.get('b_labels', tick_state.get('bx', False))) else 6
                                        ax.xaxis.labelpad = desired_pad
                                    except Exception:
                                        pass
                                    print("Shown bottom X axis title")
                                need_pos['bottom'] = True
                            elif p == 'tt':
                                vis = getattr(ax, '_top_xlabel_on', False)
                                if not vis:
                                    # Just set the flag and let position_top_xlabel() create/update the artist
                                    ax._top_xlabel_on = True
                                    need_pos['top'] = True
                                    print("Shown duplicate top X axis title")
                                else:
                                    if hasattr(ax,'_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                                        ax._top_xlabel_artist.set_visible(False)
                                    ax._top_xlabel_on = False
                                    need_pos['top'] = True
                                    print("Hid top X axis title duplicate")
                            elif p == 'lt':
                                # Use visibility toggle to avoid layout recalculation
                                label_obj = ax.yaxis.label
                                if label_obj.get_visible():
                                    # Store text before hiding
                                    if not hasattr(ax, '_stored_ylabel'):
                                        ax._stored_ylabel = label_obj.get_text()
                                    # Store current labelpad to restore later
                                    try:
                                        ax._stored_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
                                    except Exception:
                                        pass
                                    label_obj.set_visible(False)
                                    print("Hid left Y axis title")
                                else:
                                    # Restore text if needed before showing
                                    if hasattr(ax, '_stored_ylabel') and ax._stored_ylabel:
                                        label_obj.set_text(ax._stored_ylabel)
                                    label_obj.set_visible(True)
                                    # Freeze auto layout and restore exact pad if available
                                    try:
                                        fig.set_layout_engine('none')
                                    except Exception:
                                        try:
                                            fig.set_tight_layout(False)
                                        except Exception:
                                            pass
                                    try:
                                        fig.set_constrained_layout(False)
                                    except Exception:
                                        pass
                                    try:
                                        if hasattr(ax, '_stored_ylabelpad') and ax._stored_ylabelpad is not None:
                                            ax.yaxis.labelpad = ax._stored_ylabelpad
                                            # Set a one-shot pending pad for ui.position_left_ylabel to consume
                                            ax._pending_ylabelpad = ax._stored_ylabelpad
                                        else:
                                            desired_pad = 14 if bool(tick_state.get('l_labels', tick_state.get('ly', False))) else 6
                                            ax.yaxis.labelpad = desired_pad
                                    except Exception:
                                        pass
                                    print("Shown left Y axis title")
                                need_pos['left'] = True
                            elif p == 'rt':
                                vis = getattr(ax, '_right_ylabel_on', False)
                                if not vis:
                                    # Just set the flag and let position_right_ylabel() create/update the artist
                                    ax._right_ylabel_on = True
                                    need_pos['right'] = True
                                    print("Shown duplicate right Y axis title")
                                else:
                                    if hasattr(ax,'_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                                        try:
                                            ax._right_ylabel_artist.set_visible(False)
                                        except Exception:
                                            pass
                                    ax._right_ylabel_on = False
                                    need_pos['right'] = True
                                    print("Hid right Y axis title")
                            continue
                        # Plot frame (spine) toggles
                        if p in ('bl','tl','ll','rl'):
                            spine_map = {'bl':'bottom','tl':'top','ll':'left','rl':'right'}
                            spine = spine_map[p]
                            vis = get_spine_visible(spine)
                            set_spine_visible(spine, not vis)
                            print(f"Toggled {spine} spine -> {'ON' if not vis else 'off'}")
                            continue
                        # New granular tick/label toggles
                        if p in ('btcs','blb','ttcs','tlb','ltcs','llb','rtcs','rlb'):
                            if p == 'btcs':
                                tick_state['b_ticks'] = not tick_state['b_ticks']
                                print(f"Toggled bottom ticks -> {'ON' if tick_state['b_ticks'] else 'off'}")
                            elif p == 'blb':
                                tick_state['b_labels'] = not tick_state['b_labels']
                                print(f"Toggled bottom labels -> {'ON' if tick_state['b_labels'] else 'off'}")
                                need_pos['bottom'] = True
                            elif p == 'ttcs':
                                tick_state['t_ticks'] = not tick_state['t_ticks']
                                print(f"Toggled top ticks -> {'ON' if tick_state['t_ticks'] else 'off'}")
                            elif p == 'tlb':
                                tick_state['t_labels'] = not tick_state['t_labels']
                                print(f"Toggled top labels -> {'ON' if tick_state['t_labels'] else 'off'}")
                                need_pos['top'] = True
                            elif p == 'ltcs':
                                tick_state['l_ticks'] = not tick_state['l_ticks']
                                print(f"Toggled left ticks -> {'ON' if tick_state['l_ticks'] else 'off'}")
                            elif p == 'llb':
                                tick_state['l_labels'] = not tick_state['l_labels']
                                print(f"Toggled left labels -> {'ON' if tick_state['l_labels'] else 'off'}")
                                need_pos['left'] = True
                            elif p == 'rtcs':
                                tick_state['r_ticks'] = not tick_state['r_ticks']
                                print(f"Toggled right ticks -> {'ON' if tick_state['r_ticks'] else 'off'}")
                            elif p == 'rlb':
                                tick_state['r_labels'] = not tick_state['r_labels']
                                print(f"Toggled right labels -> {'ON' if tick_state['r_labels'] else 'off'}")
                                need_pos['right'] = True
                            _sync_legacy_tick_keys()
                            continue
                        # Minor tick toggles
                        if p in ('mbx','mtx','mly','mry'):
                            tick_state[p] = not tick_state[p]
                            print(f"Toggled {p} -> {'ON' if tick_state[p] else 'off'}")
                            continue
                        # Legacy combined toggles
                        if p in ('bx','tx','ly','ry'):
                            if p == 'bx':
                                newv = not (tick_state['b_ticks'] or tick_state['b_labels'])
                                tick_state['b_ticks'] = newv; tick_state['b_labels'] = newv
                                print(f"Toggled bottom (ticks+labels) -> {'ON' if newv else 'off'}")
                                need_pos['bottom'] = True
                            elif p == 'tx':
                                newv = not (tick_state['t_ticks'] or tick_state['t_labels'])
                                tick_state['t_ticks'] = newv; tick_state['t_labels'] = newv
                                print(f"Toggled top (ticks+labels) -> {'ON' if newv else 'off'}")
                                need_pos['top'] = True
                            elif p == 'ly':
                                newv = not (tick_state['l_ticks'] or tick_state['l_labels'])
                                tick_state['l_ticks'] = newv; tick_state['l_labels'] = newv
                                print(f"Toggled left (ticks+labels) -> {'ON' if newv else 'off'}")
                                need_pos['left'] = True
                            elif p == 'ry':
                                newv = not (tick_state['r_ticks'] or tick_state['r_labels'])
                                tick_state['r_ticks'] = newv; tick_state['r_labels'] = newv
                                print(f"Toggled right (ticks+labels) -> {'ON' if newv else 'off'}")
                                need_pos['right'] = True
                            _sync_legacy_tick_keys()
                            continue
                        # Unknown code
                        print(f"Unknown code: {p}")
                    # After tick toggles, update visibility and reposition ALL axis labels for independence
                    update_tick_visibility()
                    update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                    sync_fonts()
                    # Only reposition sides that were actually affected by the toggles
                    if need_pos['bottom']:
                        position_bottom_xlabel()
                    if need_pos['left']:
                        position_left_ylabel()
                    if need_pos['top']:
                        position_top_xlabel()
                    if need_pos['right']:
                        position_right_ylabel()
                    # Single draw at the end after all positioning is complete
                    fig.canvas.draw_idle()
            except Exception as e:
                print(f"Error in tick visibility menu: {e}")
        elif key == 'p':
            try:
                from .utils import list_files_in_subdirectory
                style_menu_active = True
                while style_menu_active:
                    print_style_info()
                    # List available style files (.bps, .bpsg, .bpcfg) in Styles/ subdirectory
                    style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
                    _bpcfg_files = [f[0] for f in style_file_list]
                    if _bpcfg_files:
                        print("Existing style files in Styles/ (.bps/.bpsg):")
                        for _i, _f in enumerate(_bpcfg_files, 1):
                            print(f"  {_i}: {_f}")
                    sub = input(colorize_prompt("Style submenu: (e=export, q=return, r=refresh): ")).strip().lower()
                    if sub == 'q':
                        break
                    if sub == 'r' or sub == '':
                        continue
                    if sub == 'e':
                        # Call export_style_config which handles the entire export dialog
                        export_style_config(None)  # The filename parameter is ignored by the function
                        style_menu_active = False  # Exit style submenu and return to main menu
                        break
                    else:
                        print("Unknown choice.")
            except Exception as e:
                print(f"Error in style submenu: {e}")
        elif key == 'i':
            try:
                from .utils import list_files_in_subdirectory
                style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
                _style_files = [f[0] for f in style_file_list]
                if _style_files:
                    print("Available style files in Styles/:")
                    for _i, _f in enumerate(_style_files, 1):
                        print(f"  {_i}: {_f}")
                inp = input("Enter number or filename (.bps/.bpsg; q=cancel): ").strip()
                if not inp or inp.lower() == 'q':
                    print("Canceled.")
                    continue
                if inp.isdigit() and _style_files:
                    _idx = int(inp)
                    if 1 <= _idx <= len(_style_files):
                        fname = style_file_list[_idx-1][1]  # Full path from list
                    else:
                        print("Invalid number.")
                        continue
                else:
                    fname = inp
                    # If it's not an absolute path, check in Styles/ subdirectory
                    if not os.path.isabs(fname) and not os.path.isfile(fname):
                        # Try in Styles/ subdirectory with different extensions
                        found = False
                        styles_dir = os.path.join(os.getcwd(), 'Styles')
                        for ext in ['.bps', '.bpsg', '.bpcfg']:
                            alt = fname if fname.lower().endswith(ext) else fname + ext
                            styles_path = os.path.join(styles_dir, alt)
                            if os.path.isfile(styles_path):
                                fname = styles_path
                                found = True
                                break
                        if not found:
                            # Try current directory as fallback
                            for ext in ['.bps', '.bpsg', '.bpcfg']:
                                alt = fname if fname.lower().endswith(ext) else fname + ext
                                if os.path.isfile(alt):
                                    fname = alt
                                    found = True
                                    break
                            if not found:
                                print("File not found in Styles/ or current directory.")
                                continue
                    elif not os.path.isfile(fname):
                        print("File not found.")
                        continue
                push_state("style-import")
                apply_style_config(fname)
            except Exception as e:
                print(f"Error importing style: {e}")
        elif key == 'e':
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
                
                filename = input("Enter filename (default SVG if no extension) or number to overwrite (q=cancel): ").strip()
                if not filename or filename.lower() == 'q':
                    print("Canceled.")
                    continue
                
                # Check if user selected a number
                already_confirmed = False
                if filename.isdigit() and files:
                    idx = int(filename)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            print("Canceled.")
                            continue
                        export_target = file_list[idx-1][1]  # Full path from list
                        already_confirmed = True
                    else:
                        print("Invalid number.")
                        continue
                else:
                    if not os.path.splitext(filename)[1]:
                        filename += ".svg"
                    # Use organized path unless it's an absolute path
                    if os.path.isabs(filename):
                        export_target = filename
                    else:
                        export_target = get_organized_path(filename, 'figure')
                
                # Confirm overwrite if file exists (and not already confirmed by number selection)
                if not already_confirmed:
                    if os.path.exists(export_target):
                        export_target = _confirm_overwrite(export_target)
                
                if not export_target:
                    print("Export canceled.")
                else:
                        # Temporarily remove numbering for export
                        for i, txt in enumerate(label_text_objects):
                            txt.set_text(labels[i])
                        # Transparent background for SVG exports
                        _, _ext = os.path.splitext(export_target)
                        if _ext.lower() == '.svg':
                            try:
                                _fig_fc = fig.get_facecolor()
                            except Exception:
                                _fig_fc = None
                            try:
                                _ax_fc = ax.get_facecolor()
                            except Exception:
                                _ax_fc = None
                            try:
                                if getattr(fig, 'patch', None) is not None:
                                    fig.patch.set_alpha(0.0); fig.patch.set_facecolor('none')
                                if getattr(ax, 'patch', None) is not None:
                                    ax.patch.set_alpha(0.0); ax.patch.set_facecolor('none')
                            except Exception:
                                pass
                            try:
                                fig.savefig(export_target, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                            finally:
                                try:
                                    if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                                        fig.patch.set_alpha(1.0); fig.patch.set_facecolor(_fig_fc)
                                except Exception:
                                    pass
                                try:
                                    if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                                        ax.patch.set_alpha(1.0); ax.patch.set_facecolor(_ax_fc)
                                except Exception:
                                    pass
                        else:
                            fig.savefig(export_target, dpi=300)
                        print(f"Figure saved to {export_target}")
                        for i, txt in enumerate(label_text_objects):
                            txt.set_text(f"{i+1}: {labels[i]}")
                        fig.canvas.draw()
            except Exception as e:
                print(f"Error saving figure: {e}")
        elif key == 'v':
            while True:
                try:
                    rng_in = input("Peak X range (min max, 'current' for axes limits, q=back): ").strip().lower()
                    if not rng_in or rng_in == 'q':
                        break
                    if rng_in == 'current':
                        x_min, x_max = ax.get_xlim()
                    else:
                        parts = rng_in.split()
                        if len(parts) != 2:
                            print("Need exactly two numbers or 'current'.")
                            continue
                        x_min, x_max = map(float, parts)
                        if x_min > x_max:
                            x_min, x_max = x_max, x_min

                    frac_in = input("Min relative peak height (0–1, default 0.1): ").strip()
                    min_frac = float(frac_in) if frac_in else 0.1
                    if min_frac < 0: min_frac = 0.0
                    if min_frac > 1: min_frac = 1.0

                    swin = input("Smoothing window (odd int >=3, blank=none): ").strip()
                    if swin:
                        try:
                            win = int(swin)
                            if win < 3 or win % 2 == 0:
                                print("Invalid window; disabling smoothing.")
                                win = 0
                            else:
                                print(f"Using moving-average smoothing (window={win}).")
                        except ValueError:
                            print("Bad window value; no smoothing.")
                            win = 0
                    else:
                        win = 0

                    print("\n--- Peak Report ---")
                    print(f"X range used: {x_min} .. {x_max}  (relative height threshold={min_frac})")
                    for i, (x_arr, y_off) in enumerate(zip(x_data_list, y_data_list)):
                        # Recover original curve (remove vertical offset)
                        if i < len(offsets_list):
                            y_arr = y_off - offsets_list[i]
                        else:
                            y_arr = y_off.copy()

                        # Restrict to selected window
                        mask = (x_arr >= x_min) & (x_arr <= x_max)
                        x_sel = x_arr[mask]
                        y_sel = y_arr[mask]

                        label = labels[i] if i < len(labels) else f"Curve {i+1}"
                        print(f"\nCurve {i+1}: {label}")
                        if x_sel.size < 3:
                            print("  (Insufficient points)")
                            continue

                        # Optional smoothing
                        if win >= 3 and x_sel.size >= win:
                            kernel = np.ones(win, dtype=float) / win
                            y_sm = np.convolve(y_sel, kernel, mode='same')
                        else:
                            y_sm = y_sel

                        # Determine threshold
                        ymax = float(np.max(y_sm))
                        if ymax <= 0:
                            print("  (Non-positive data)")
                            continue
                        min_height = ymax * min_frac

                        # Simple local maxima detection
                        y_prev = y_sm[:-2]
                        y_mid  = y_sm[1:-1]
                        y_next = y_sm[2:]
                        core_mask = (y_mid > y_prev) & (y_mid >= y_next) & (y_mid >= min_height)
                        if not np.any(core_mask):
                            print("  (No peaks)")
                            continue
                        peak_indices = np.where(core_mask)[0] + 1  # shift because we looked at 1..n-2

                        # Optional refine: keep only distinct peaks (skip adjacent equal plateau)
                        peaks = []
                        last_idx = -10
                        for pi in peak_indices:
                            if pi - last_idx == 1 and y_sm[pi] == y_sm[last_idx]:
                                # same plateau, keep first
                                continue
                            peaks.append(pi)
                            last_idx = pi

                        print("  Peaks (x, y):")
                        for pi in peaks:
                            print(f"    x={x_sel[pi]:.6g}, y={y_sel[pi]:.6g}")
                    print("\n--- End Peak Report ---\n")
                except Exception as e:
                    print(f"Error finding peaks: {e}")

__all__ = ["interactive_menu"]
