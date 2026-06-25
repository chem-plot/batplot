"""Colors/cycles menu (``c``) for EC interactive mode."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import re

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from matplotlib import colors as mcolors  # type: ignore[import-untyped]

from ...color_utils import (
    color_bar,
    color_block,
    ensure_colormap,
    get_user_color_list,
    manage_user_colors,
    palette_preview,
    resolve_color_token,
)
from ...plotting import apply_curve_color
from ..common.palettes import DEFAULT_PALETTE_ALIASES, TAB10_HEX, palette_items, resolve_palette_token, sample_colormap


def _iter_cycle_lines(cycle_lines: Dict[int, Dict[str, Optional[Any]]]):
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



def _apply_curve_linewidth(fig, cycle_lines: Dict[int, Dict[str, Optional[Any]]]):
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


def _apply_colors(cycle_lines: Dict[int, Dict[str, Optional[Any]]], mapping: Dict[int, object]):
    """Apply color mapping to charge/discharge lines for the given cycles.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    for cyc, col in mapping.items():
        if cyc not in cycle_lines:
            continue
        for _, _, ln in _iter_cycle_lines({cyc: cycle_lines[cyc]}):
            try:
                apply_curve_color(ln, col)
            except Exception:
                pass


def _set_visible_cycles(cycle_lines: Dict[int, Dict[str, Optional[Any]]], show: Iterable[int]):
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
    return resolve_palette_token(token, palette_map)


def _parse_file_palette_tokens(tokens: List[str], n_files: int, fig=None) -> Optional[Tuple[List[int], str]]:
    """Parse file-palette syntax: f1-5 viridis, f1 f3 f5 viridis, fall viridis.
    Returns (file_indices_0based, palette_name) or None if not matched."""
    if not tokens or n_files < 1:
        return None
    last = tokens[-1]
    alias = _resolve_palette_alias(last, DEFAULT_PALETTE_ALIASES) if last else last
    try:
        if not ensure_colormap(alias):
            raise ValueError(alias)
        plt.get_cmap(alias)
        palette = alias
    except Exception:
        return None
    num_tokens = tokens[:-1]
    if not num_tokens:
        return None
    file_indices = []
    for t in num_tokens:
        t = t.strip().lower()
        if t == 'fall' or t == 'f':
            file_indices = list(range(n_files))
            break
        if t.startswith('f'):
            t = t[1:]
        if '-' in t and t.count('-') == 1:
            lo, hi = t.split('-', 1)
            try:
                a, b = int(lo.strip()), int(hi.strip())
                for i in range(a, b + 1):
                    if 1 <= i <= n_files:
                        file_indices.append(i - 1)
            except ValueError:
                pass
        else:
            try:
                idx = int(t)
                if 1 <= idx <= n_files:
                    file_indices.append(idx - 1)
            except ValueError:
                pass
    file_indices = sorted(set(file_indices))
    if not file_indices:
        return None
    return (file_indices, palette)


def _parse_per_file_cycle_tokens(
    tokens: List[str], n_files: int, fig=None
) -> Optional[Tuple[Dict[int, List[int]], Optional[str]]]:
    """Parse per-file cycle selection: f1:1,5,10 f2:2,4,6 viridis.
    Returns (file_to_cycles, palette) or None if not matched.
    file_to_cycles: 1-based file index -> list of cycles to show (empty = all)."""
    if not tokens or n_files < 1:
        return None
    # Must have at least one fN:... pattern (f required to avoid 1:red cycle-color confusion)
    file_cycle_pattern = re.compile(r'^f(\d+):(.+)$', re.IGNORECASE)
    file_specs: Dict[int, List[int]] = {}
    remaining = []
    for t in tokens:
        m = file_cycle_pattern.match(t.strip())
        if m:
            try:
                fidx = int(m.group(1))
                if 1 <= fidx <= n_files:
                    val = m.group(2).strip().lower()
                    if val == 'all':
                        file_specs[fidx] = []  # empty = all cycles
                    else:
                        cycles = []
                        for part in val.replace(',', ' ').split():
                            if '-' in part and part.count('-') == 1:
                                lo, hi = part.split('-', 1)
                                try:
                                    a, b = int(lo.strip()), int(hi.strip())
                                    cycles.extend(range(a, b + 1))
                                except ValueError:
                                    pass
                            else:
                                try:
                                    cycles.append(int(part))
                                except ValueError:
                                    pass
                        # Only add if we got valid cycles (skip f1:red which is per-curve color)
                        if cycles:
                            file_specs[fidx] = sorted(set(cycles))
            except (ValueError, IndexError):
                remaining.append(t)
        else:
            remaining.append(t)
    if not file_specs:
        return None
    # Last remaining token may be palette
    palette = None
    if remaining:
        last = remaining[-1]
        alias = _resolve_palette_alias(last, DEFAULT_PALETTE_ALIASES) if last else last
        try:
            if not ensure_colormap(alias):
                raise ValueError(alias)
            plt.get_cmap(alias)
            palette = alias
            remaining = remaining[:-1]
        except Exception:
            pass
    return (file_specs, palette)


def _parse_fall_cycles_tokens(
    tokens: List[str], n_files: int, fig=None
) -> Optional[Tuple[List[int], Optional[str]]]:
    """Parse fall:1 2 3 5 4 — show cycles 1,2,3,5 for ALL files, one color per file from palette 4.
    Returns (cycles_list, palette) or None if not matched."""
    if not tokens or n_files < 1:
        return None
    first = tokens[0].strip()
    if not first.lower().startswith("fall:"):
        return None
    suffix = first[5:].strip()  # after "fall:"
    cycle_tokens = [suffix] + list(tokens[1:])
    palette = None
    if cycle_tokens:
        last = cycle_tokens[-1]
        alias = _resolve_palette_alias(last, DEFAULT_PALETTE_ALIASES) if last else last
        try:
            if not ensure_colormap(alias):
                raise ValueError(alias)
            plt.get_cmap(alias)
            palette = alias
            cycle_tokens = cycle_tokens[:-1]
        except Exception:
            pass
    cycles = []
    for t in cycle_tokens:
        for part in str(t).replace(',', ' ').split():
            if '-' in part and part.count('-') == 1:
                lo, hi = part.split('-', 1)
                try:
                    a, b = int(lo.strip()), int(hi.strip())
                    cycles.extend(range(a, b + 1))
                except ValueError:
                    pass
            else:
                try:
                    cycles.append(int(part))
                except ValueError:
                    pass
    cycles = sorted(set(cycles))
    if not cycles:
        return None
    return (cycles, palette)


def _expand_cycle_number_tokens(parts: List[str]) -> List[int]:
    """Turn tokens like ``5``, ``2-30``, or ``1,3-5`` into sorted unique cycle numbers.

    Hyphen ranges use inclusive endpoints; ``10-2`` is treated as ``2``..``10``.
    Non-numeric pieces are skipped.
    """
    out: List[int] = []
    for t in parts:
        for piece in str(t).replace(",", " ").split():
            piece = piece.strip()
            if not piece:
                continue
            if "-" in piece and piece.count("-") == 1:
                lo, hi = piece.split("-", 1)
                try:
                    a, b = int(lo.strip()), int(hi.strip())
                except ValueError:
                    continue
                if a <= b:
                    out.extend(range(a, b + 1))
                else:
                    out.extend(range(b, a + 1))
            else:
                try:
                    out.append(int(piece))
                except ValueError:
                    pass
    return sorted(set(out))


def _format_cycles_compact(cycles: List[int]) -> str:
    """Format cycle ids for messages, e.g. ``[2,3,4,30]`` → ``2-4, 30``."""
    if not cycles:
        return ""
    c = sorted(set(int(x) for x in cycles))
    parts: List[str] = []
    i = 0
    while i < len(c):
        j = i
        while j + 1 < len(c) and c[j + 1] == c[j] + 1:
            j += 1
        if j == i:
            parts.append(str(c[i]))
        else:
            parts.append(f"{c[i]}-{c[j]}")
        i = j + 1
    return ", ".join(parts)


def _parse_cycle_tokens(tokens: List[str], fig=None) -> Tuple[str, List[int], dict, Optional[str], bool]:
    """Classify and parse tokens for the cycle command.

    Returns a tuple: (mode, cycles, mapping, palette)
      - mode: 'map' for explicit mappings like 1:red, 'palette' for numbers + cmap,
              'numbers' for numbers only.
      - cycles: list of cycle indices (integers); supports hyphen ranges (e.g. ``2-30``) and commas.
      - mapping: dict for 'map' mode only, empty otherwise
      - palette: colormap name for 'palette' mode else None
    """
    if not tokens:
        return ("numbers", [], {}, None, False)

    # Support 'all' and 'all <palette>'
    if len(tokens) == 1 and tokens[0].lower() == 'all':
        return ("numbers", [], {}, None, True)
    if len(tokens) == 2 and tokens[0].lower() == 'all':
        alias = _resolve_palette_alias(tokens[1], DEFAULT_PALETTE_ALIASES)
        try:
            if not ensure_colormap(alias):
                raise ValueError(alias)
            plt.get_cmap(alias)
            return ("palette", [], {}, alias, True)
        except Exception:
            # Unknown palette -> still select all, no recolor
            return ("numbers", [], {}, None, True)

    # Check explicit mapping mode first
    if any(":" in t for t in tokens):
        cycles: List[int] = []
        mapping: Dict[int, object] = {}
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

    # Check if last token is a known numeric palette shortcut
    if last in DEFAULT_PALETTE_ALIASES:
        palette = DEFAULT_PALETTE_ALIASES[last]
        num_tokens = tokens[:-1]
        cycles = _expand_cycle_number_tokens(num_tokens)
        return ("palette", cycles, {}, palette, False)
    alias = _resolve_palette_alias(last, DEFAULT_PALETTE_ALIASES)
    if alias != last:
        try:
            if not ensure_colormap(alias):
                raise ValueError(alias)
            plt.get_cmap(alias)
            palette = alias
            num_tokens = tokens[:-1]
            cycles = _expand_cycle_number_tokens(num_tokens)
            return ("palette", cycles, {}, palette, False)
        except Exception:
            pass

    # Check if last token is a valid colormap name
    try:
        if not ensure_colormap(last):
            raise ValueError(last)
        plt.get_cmap(last)
        palette = last
        num_tokens = tokens[:-1]
        cycles = _expand_cycle_number_tokens(num_tokens)
        return ("palette", cycles, {}, palette, False)
    except Exception:
        pass

    # Numbers only (supports ranges, e.g. 2-30)
    cycles = _expand_cycle_number_tokens(tokens)
    return ("numbers", cycles, {}, None, False)



def run_ec_cycles_menu(
    *,
    fig: Any,
    ax: Any,
    cycle_lines: dict,
    file_data: list[dict],
    current_file_idx: int,
    all_cycles: list,
    is_multi_file: bool,
    is_dqdv: bool,
    menu_title: str,
    canvas_mode: bool,
    print_file_list: Callable[..., Any],
    print_menu: Callable[..., Any],
    colorize_menu: Callable[[str], str],
    colorize_inline_commands: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    safe_input: Callable[[str], str],
    push_state: Callable[[str], Any],
    parse_fall_cycles_tokens: Callable[..., Any],
    parse_per_file_cycle_tokens: Callable[..., Any],
    parse_file_palette_tokens: Callable[..., Any],
    parse_cycle_tokens: Callable[..., Any],
    set_visible_cycles: Callable[..., Any],
    apply_colors: Callable[..., Any],
    apply_curve_linewidth: Callable[..., Any],
    apply_stored_smooth_settings: Callable[..., Any],
    apply_display_mode: Callable[[str], Any],
    rebuild_legend: Callable[[Any], Any],
    apply_nice_ticks: Callable[[], Any],
) -> None:
    # Cycles/colors: multi-file defaults to all visible files; type fall viridis etc. directly
    while True:
        if is_multi_file:
            target_cycle_lines_list = [(f['cycle_lines'], sorted((f.get('cycle_lines') or {}).keys())) for f in file_data if f.get('visible', True)]
            if not target_cycle_lines_list:
                print("No visible files.")
                print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                break
        else:
            target_cycle_lines_list = [(cycle_lines, all_cycles)]
        if is_multi_file:
            print_file_list(file_data, current_file_idx)
        print(f"Total cycles: {len(all_cycles)}")
        _C, _R = "\033[96m", "\033[0m"
        if is_multi_file:
            print(f"  {_C}fall viridis{_R}  = palette to all files (one color per file)")
            print(f"  {_C}fall:1 2 3 5 4{_R}  = cycles 1,2,3,5 for ALL files, one color per file (palette 4)")
            print(f"  {_C}f1-5 viridis{_R}  = files 1–5  |  {_C}f1 f3 f5 4{_R}  = files 1,3,5 (4=viridis)")
            print(f"  {_C}f1:1,5,10 f2:2,4,6 viridis{_R}  = per-file cycles (file 1: 1,5,10; file 2: 2,4,6)")
        print("Enter one of:")
        print(colorize_inline_commands("  - per-curve: e.g. 1:red 5:#00B006"))
        print(colorize_inline_commands("  - cycle numbers + palette: e.g. 2-30 1 (cycles 2–30, palette 1/tab10)  OR  1 5 10 viridis"))
        print(colorize_inline_commands("  - all cycles + palette: e.g. all viridis  OR  all 3"))
        print("\nRecommended palettes for scientific publications:")
        rec_palettes = palette_items(DEFAULT_PALETTE_ALIASES.values())
        for idx, (name, desc) in enumerate(rec_palettes, 1):
            bar = palette_preview(name)
            print("  " + colorize_menu(f"{idx}: {name} - {desc}"))
            if bar:
                print(f"      {bar}")
        print("  " + colorize_menu("Enter palette name OR number"))
        user_colors = get_user_color_list(fig)
        if user_colors:
            print("\nSaved colors (use number or u# in mappings):")
            for idx, color in enumerate(user_colors, 1):
                print("  " + colorize_menu(f"{idx}: {color_block(color)} {color}"))
            print("  " + colorize_menu("u: edit saved colors before assigning"))
        print("  " + colorize_menu("q: back"))
        line = safe_input(colorize_prompt("Selection: ")).strip()
        if not line or line.lower() == 'q':
            break
        if line.lower() == 'u':
            manage_user_colors(fig)
            continue
        tokens_raw = line.split()
        tokens = line.replace(',', ' ').split()
        all_ignored = []
        # Check fall:1 2 3 5 4 — cycles for ALL files, one color per file (multi-file only)
        fall_cycles_result = None
        if is_multi_file and len(tokens) >= 1:
            fall_cycles_result = parse_fall_cycles_tokens(tokens, len(file_data), fig)
        if fall_cycles_result is not None:
            sel_cycles, fc_palette = fall_cycles_result
            push_state("cycles/colors")
            n_visible = len(target_cycle_lines_list)
            if fc_palette and fc_palette.lower() in ('tab10', '1'):
                file_colors = [mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                              for i in range(n_visible)]
            else:
                try:
                    cmap = plt.get_cmap(fc_palette) if fc_palette else None
                except Exception:
                    cmap = None
                if cmap is not None:
                    file_colors = [cmap(t) for t in np.linspace(0.08, 0.88, n_visible)] if n_visible > 1 else [cmap(0.55)]
                else:
                    file_colors = [mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                                  for i in range(n_visible)]
            for idx, (cl, acyc) in enumerate(target_cycle_lines_list):
                show = [c for c in sel_cycles if c in cl]
                set_visible_cycles(cl, show)
                if show and idx < len(file_colors):
                    col = file_colors[idx]
                    apply_colors(cl, {c: col for c in show})
                apply_curve_linewidth(fig, cl)
                if is_dqdv and hasattr(fig, '_dqdv_smooth_settings'):
                    apply_stored_smooth_settings(cl, fig)
            dm = getattr(fig, '_ec_display_mode', 'both')
            apply_display_mode(dm)
            rebuild_legend(ax)
            apply_nice_ticks()
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            fc_display = fc_palette or 'tab10'
            if fc_palette and fc_palette.lower() in ('tab10', '1'):
                fc_display = 'tab10'
            print(f"fall: cycles {sel_cycles} for all files (palette: {fc_display}, one color per file)")
        else:
            # Check per-file cycle selection (multi-file only): f1:1,5,10 f2:2,4,6 viridis
            per_file_result = None
            if is_multi_file and len(tokens_raw) >= 1:
                per_file_result = parse_per_file_cycle_tokens(tokens_raw, len(file_data), fig)
            if per_file_result is not None:
                file_to_cycles, pf_palette = per_file_result
                push_state("cycles/colors")
                # Collect valid file selections first so palette colors can be assigned
                # consistently across files (f1..fN), not per-cycle within each file.
                selected_file_items = []
                for fidx_1based, sel_cycles in sorted(file_to_cycles.items()):
                    if 1 <= fidx_1based <= len(file_data):
                        f_entry = file_data[fidx_1based - 1]
                        if not f_entry.get('visible', True):
                            continue
                        cl = f_entry.get('cycle_lines') or {}
                        acyc = sorted(cl.keys())
                        if not acyc:
                            continue
                        show = list(acyc) if not sel_cycles else [c for c in sel_cycles if c in cl]
                        set_visible_cycles(cl, show)
                        if not show:
                            continue
                        selected_file_items.append((fidx_1based, cl, show))

                n_selected_files = len(selected_file_items)
                file_palette_cols = []
                if n_selected_files > 0:
                    if pf_palette and pf_palette.lower() in ('tab10', '1'):
                        file_palette_cols = [
                            mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                            for i in range(n_selected_files)
                        ]
                    elif pf_palette:
                        try:
                                    cmap = plt.get_cmap(pf_palette)
                        except Exception:
                            cmap = None
                        if cmap is not None:
                            file_palette_cols = (
                                [cmap(0.55)] if n_selected_files == 1 else
                                [cmap(t) for t in np.linspace(0.08, 0.88, n_selected_files)]
                            )
                        else:
                            file_palette_cols = [
                                mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                                for i in range(n_selected_files)
                            ]

                for idx, (fidx_1based, cl, show) in enumerate(selected_file_items):
                    if file_palette_cols:
                        # Palette in per-file syntax means one color per file.
                        col = file_palette_cols[idx]
                        apply_colors(cl, {c: col for c in show})
                    else:
                        # No palette: keep per-cycle tab10 fallback inside each file.
                        cols = [mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                                for i in range(len(show))]
                        apply_colors(cl, {c: col for c, col in zip(show, cols)})
                        apply_curve_linewidth(fig, cl)
                        if is_dqdv and hasattr(fig, '_dqdv_smooth_settings'):
                            apply_stored_smooth_settings(cl, fig)
                dm = getattr(fig, '_ec_display_mode', 'both')
                apply_display_mode(dm)
                rebuild_legend(ax)
                apply_nice_ticks()
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
                pf_display = pf_palette or 'tab10'
                if pf_palette and pf_palette.lower() in ('tab10', '1'):
                    pf_display = 'tab10'
                print(f"Per-file cycles applied (palette: {pf_display}): "
                      + ", ".join(f"f{i}:{','.join(map(str, c)) if c else 'all'}" for i, c in sorted(file_to_cycles.items())))
            else:
                # Check file-palette mode (multi-file only): f1-5 viridis, fall viridis
                file_palette_result = None
                if is_multi_file and len(tokens) >= 2:
                    file_palette_result = parse_file_palette_tokens(tokens, len(file_data), fig)
                if file_palette_result is not None:
                    file_indices, fp_palette = file_palette_result
                    target_cycle_lines_list = [(file_data[i]['cycle_lines'], sorted((file_data[i].get('cycle_lines') or {}).keys())) for i in file_indices]
                    push_state("cycles/colors")
                    n_files = len(target_cycle_lines_list)
                    if fp_palette and fp_palette.lower() in ('tab10', '1'):
                        cols = [mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)]) for i in range(n_files)]
                    else:
                        try:
                                    cmap = plt.get_cmap(fp_palette) if fp_palette else None
                        except Exception:
                            cmap = None
                        if cmap is None:
                            print(f"Unknown colormap '{fp_palette}'.")
                            continue
                        else:
                            cols = [cmap(t) for t in np.linspace(0.08, 0.88, n_files)] if n_files > 1 else [cmap(0.55)]
                    for idx, (cl, acyc) in enumerate(target_cycle_lines_list):
                        if idx < len(cols):
                            col = cols[idx]
                            mapping = {c: col for c in acyc}
                            apply_colors(cl, mapping)
                            set_visible_cycles(cl, list(acyc))
                        apply_curve_linewidth(fig, cl)
                    if is_dqdv and hasattr(fig, '_dqdv_smooth_settings'):
                        for cl, _ in target_cycle_lines_list:
                            apply_stored_smooth_settings(cl, fig)
                    dm = getattr(fig, '_ec_display_mode', 'both')
                    apply_display_mode(dm)
                    rebuild_legend(ax)
                    apply_nice_ticks()
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                    try:
                        preview = color_bar([mcolors.to_hex(col) for col in cols])
                        print(f"Palette '{fp_palette}' applied to files {[i+1 for i in file_indices]}: {preview}")
                    except Exception:
                        print(f"Palette '{fp_palette}' applied to files {[i+1 for i in file_indices]}.")
                else:
                    mode, cycles, mapping, palette, use_all = parse_cycle_tokens(tokens, fig)
                    push_state("cycles/colors")
                    all_ignored = []
                    # Apply to each target file
                    for cl, acyc in target_cycle_lines_list:
                        # Filter to existing cycles in this target
                        if use_all:
                            existing = list(acyc)
                            ignored = []
                        else:
                            existing = [c for c in cycles if c in cl]
                            ignored = [c for c in cycles if c not in cl]
                            all_ignored.extend(ignored)
                        if not existing and mode != 'numbers':
                            continue
                        if not existing:
                            print("No valid cycles provided; keeping current visibility.")
                        # Update visibility
                        if existing:
                            set_visible_cycles(cl, existing)
                        # Apply coloring by mode
                        if mode == 'map' and mapping:
                            mapping2 = {c: mapping[c] for c in existing if c in mapping}
                            apply_colors(cl, mapping2)
                            if mapping2 and cl is target_cycle_lines_list[0][0]:
                                print("Applied manual colors:")
                                for cyc, col in mapping2.items():
                                    print(f"  Cycle {cyc}: {color_block(col)} {col}")
                        elif mode == 'palette' and existing:
                            # ====================================================================
                            # APPLY COLOR PALETTE TO ELECTROCHEMISTRY CYCLES
                            # ====================================================================
                            #
                            # This applies a colormap to selected cycles in EC mode (GC, CV, dQ/dV).
                            #
                            # HOW IT WORKS:
                            # Similar to XY mode, but works with cycles instead of individual files.
                            # Each cycle gets a different color sampled from the colormap.
                            #
                            # Example with 10 cycles and 'viridis':
                            #   Cycle 1 → dark purple
                            #   Cycle 2 → purple-blue
                            #   Cycle 3 → blue
                            #   ...
                            #   Cycle 10 → bright yellow
                            #
                            # This creates a visual progression showing how the battery changes
                            # over multiple cycles (degradation, capacity fade, etc.)
                            # ====================================================================
                            #
                            # Special handling for Tab10 (default palette) to match hardcoded colors exactly
                            if palette and palette.lower() in ('tab10', '1'):
                                # Use the exact hardcoded Tab10 colors to match default behavior
                                n = len(existing)
                                cols = [mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                                        for i in range(n)]
                            else:
                                try:
                                            cmap = plt.get_cmap(palette) if palette else None
                                except Exception:
                                    cmap = None
                                if cmap is None:
                                    print(f"Unknown colormap '{palette}'.")
                                    cols = []
                                else:
                                    n = len(existing)
                                    cols = sample_colormap(cmap, n, pair=(0.15, 0.85), span=(0.08, 0.88))
                            if cols:
                                apply_colors(cl, {c: col for c, col in zip(existing, cols)})
                                try:
                                    preview = color_bar([mcolors.to_hex(col) for col in cols])
                                except Exception:
                                    preview = ""
                                if preview and cl is target_cycle_lines_list[0][0]:
                                    palette_display = 'tab10 (default)' if palette and palette.lower() in ('tab10', '1') else palette
                                    cc = _format_cycles_compact(cycles) if (not use_all and cycles) else ""
                                    cyc_suff = f" — cycles {cc}" if cc else ""
                                    print(f"Palette '{palette_display}' applied{cyc_suff}: {preview}")
                        elif mode == 'numbers' and existing:
                            pass
                        # Reapply curve linewidth and smooth for this target
                        apply_curve_linewidth(fig, cl)
                        if is_dqdv and hasattr(fig, '_dqdv_smooth_settings'):
                            apply_stored_smooth_settings(cl, fig)

                    # Re-apply display mode so newly added cycles get correct charge/discharge visibility
                    dm = getattr(fig, '_ec_display_mode', 'both')
                    apply_display_mode(dm)

                    # Rebuild legend and redraw (once after all targets)
                    rebuild_legend(ax)
                    apply_nice_ticks()
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()

                    if all_ignored:
                        print("Ignored cycles:", ", ".join(str(c) for c in sorted(set(all_ignored))))


__all__ = ["run_ec_cycles_menu"]
