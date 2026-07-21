"""Colors submenu (``c``) for the XY interactive menu.

Handles per-curve colors, palette application (with optional ranges), saved
user colors, spine colors, and the CIF tick-color sub-submenu. Color resolution
and palette utilities are reused from ``color_utils`` so behavior matches the
other modes; plot/CIF mutations go through injected callbacks and ``push_state``
so undo and CIF redraw behavior are unchanged.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib import colors as mcolors  # type: ignore[import]

from ...plotting import apply_curve_color, update_labels
from .spines import apply_xy_spine_color
from ...color_utils import (
    color_block,
    color_bar,
    format_color_listing,
    palette_preview,
    manage_user_colors,
    get_user_color_list,
    resolve_color_token,
    ensure_colormap,
    get_colormap,
    _CUSTOM_CMAPS,
)
from ..common.palettes import (
    build_xy_palette_options,
    parse_index_ranges,
    resolve_palette_token,
    sample_colormap,
)
from ..common.sources import cif_present


def run_xy_color_menu(
    *,
    ax: Any,
    fig: Any,
    labels: Sequence[str],
    y_data_list: List[Any],
    label_text_objects: List[Any],
    stack: bool,
    args_files: Sequence[str],
    line_getter: Callable[[int], Any],
    bp: Any,
    get_cif_series: Callable[[], Any],
    sync_fig_cif_tick_series: Callable[[], Any],
    position_top_xlabel: Callable[[], Any],
    position_right_ylabel: Callable[[], Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    tick_state: dict | None = None,
) -> None:
    """Run the colors submenu."""
    _line = line_getter
    try:
        has_cif = cif_present(
            args_files,
            (lambda: getattr(bp, 'cif_tick_series', None)) if bp is not None else None,
        )

        # Build palette list once (shared XY/CIF palette helper)
        _palette_options = build_xy_palette_options(ensure_colormap)
        _palette_index = {str(i): name for i, name in enumerate(_palette_options, 1)}
        _desc_map = {
            'viridis': 'blue→yellow', 'cividis': 'blue→olive',
            'plasma': 'purple→yellow', 'inferno': 'dark→bright',
            'magma': 'dark→light purple', 'batlow': 'colorblind-friendly',
            'rainbow': 'full-spectrum rainbow', 'turbo': 'vibrant rainbow',
            'batlowK': 'dark-light batlow variant',
            'batlowW': 'warm batlow variant',
        }

        def _resolve_pal_token(token):
            return resolve_palette_token(token, _palette_index)

        def _apply_palette_to_lines(palette_name, indices):
            cmap = get_colormap(palette_name)
            if cmap is None:
                print(f"Unknown palette '{palette_name}'.")
                return
            push_state("color-palette")
            nsel = len(indices)
            low_clip, high_clip = 0.08, 0.85
            colors = sample_colormap(cmap, nsel)
            for c_idx, line_idx in enumerate(indices):
                apply_curve_color(_line(line_idx), colors[c_idx])
            update_labels(ax, y_data_list, label_text_objects, stack, getattr(fig, '_stack_label_at_bottom', False))
            fig.canvas.draw()
            try:
                applied_preview = color_bar([mcolors.to_hex(c) for c in colors])
            except Exception:
                applied_preview = ""
            print(f"Applied '{palette_name}' to curves: " + ", ".join(str(i+1) for i in indices))
            if applied_preview:
                print(f"  {applied_preview}")
            history = list(getattr(fig, '_curve_palette_history', []))
            history.append({'palette': palette_name, 'indices': [i+1 for i in indices], 'low_clip': low_clip, 'high_clip': high_clip})
            fig._curve_palette_history = history

        def _parse_ranges(spec, total):
            return parse_index_ranges(spec, total, warn_out_of_range=True)

        _spine_keys = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}

        while True:
            # Header: show current curves
            print("\n\033[1mColors>\033[0m  Current curves (visible only):")
            any_curve = False
            for idx, label in enumerate(labels):
                try:
                    ln = _line(idx)
                    if ln is not None and not ln.get_visible():
                        continue
                    cur = ln.get_color() if ln is not None else None
                except Exception:
                    cur = None
                any_curve = True
                print(f"  {idx+1}: {format_color_listing(cur)} {label}")
            if not any_curve:
                print("  (none visible)")
            # Saved user colors
            user_colors = get_user_color_list(fig)
            if user_colors:
                print("Saved colors (refer as number or u#):")
                for idx, col in enumerate(user_colors, 1):
                    print(f"  {idx}: {format_color_listing(col)}")
            # Palettes
            history = getattr(fig, '_curve_palette_history', [])
            cur_pal = history[-1]['palette'] if history else None
            if cur_pal:
                print(f"Current palette: {cur_pal}")
            print("Palettes:")
            for idx, name in enumerate(_palette_options, 1):
                bar = palette_preview(name)
                desc = _desc_map.get(name, '')
                print(f"  {idx}. {name}" + (f" - {desc}" if desc else ""))
                if bar:
                    print(f"      {bar}")
            _C = '\033[96m'; _R = '\033[0m'
            print(f"Spine/tick keys : {_C}w{_R}=top  {_C}a{_R}=left  {_C}s{_R}=bottom  {_C}d{_R}=right")
            print(f"Curve colors    : {_C}1:red{_R}  {_C}2:u3{_R}  {_C}3:#00FF00{_R}")
            print(f"Palette         : {_C}all viridis{_R}   {_C}1-3 magma_r{_R}   {_C}1-2,4 2{_R}")
            print(f"Spine colors    : {_C}w:red{_R}  {_C}a:#4561F7{_R}")
            if has_cif and (bp is not None and getattr(bp, 'cif_tick_series', None)):
                print(f"CIF tick colors : {_C}t{_R} (enter 't' to open CIF color submenu)")
            print(f"Other           : {_C}u{_R}=manage saved colors   {_C}q{_R}=back")
            line = safe_input(colorize_prompt("Colors> ")).strip()
            if not line or line.lower() == 'q':
                break
            low = line.lower()
            # Special single-key commands
            if low == 'u':
                manage_user_colors(fig)
                continue
            if low == 't':
                if has_cif and (bp is not None and getattr(bp, 'cif_tick_series', None)):
                    cts = getattr(bp, 'cif_tick_series', [])
                    while True:
                        _C = '\033[96m'; _R = '\033[0m'
                        print("CIF color (per set).")
                        for i, (lab, fname, peaksQ, wl_e, qmax, col) in enumerate(cts):
                            print(f"  {i+1}: {format_color_listing(col)}  {lab}")
                        print("Examples:")
                        print(f"  {_C}1:red 2:#00FF00{_R}       (set colors directly)")
                        print(f"  {_C}1:2 2:3{_R}               (use saved user colors 2 and 3)")
                        print(f"  {_C}all viridis{_R}           (apply palette to all CIF sets)")
                        print(f"  {_C}1-2,4 magma_r{_R}         (apply palette to a subset)")
                        cif_line = safe_input("Enter mappings or range+palette (q=back): ").strip()
                        if not cif_line or cif_line.lower() == 'q':
                            break
                        cif_tokens = cif_line.split()
                        if any(':' in t for t in cif_tokens):
                            try:
                                push_state("cif-color")
                            except Exception:
                                pass
                            for tok in cif_tokens:
                                if ':' not in tok:
                                    print(f"Skip malformed token: {tok}")
                                    continue
                                idx_str, color_spec = tok.split(":", 1)
                                try:
                                    idx = int(idx_str) - 1
                                except ValueError:
                                    print(f"Bad index: {idx_str}")
                                    continue
                                if not (0 <= idx < len(cts)):
                                    print(f"Index out of range: {idx_str}")
                                    continue
                                try:
                                    resolved = resolve_color_token(color_spec, fig)
                                except Exception:
                                    resolved = color_spec
                                lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
                                cts[idx] = (lab, fname, peaksQ, wl_e, qmax, resolved)
                            if bp is not None:
                                setattr(bp, 'cif_tick_series', cts)
                            sync_fig_cif_tick_series()
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                        else:
                            parts = cif_tokens
                            if len(parts) < 2:
                                print("Need range and palette (e.g., 'all viridis' or '1-2 magma_r').")
                                continue
                            range_part = "".join(parts[:-1])
                            palette_token = parts[-1]
                            pal_name = _resolve_pal_token(palette_token)
                            available = list(_CUSTOM_CMAPS.keys()) + list(plt.colormaps())
                            if pal_name not in available and not ensure_colormap(pal_name):
                                print(f"Unknown palette '{pal_name}'.")
                                continue
                            indices = parse_index_ranges(range_part, len(cts), warn_out_of_range=False)
                            if not indices:
                                print("No valid indices parsed.")
                                continue
                            try:
                                cmap = get_colormap(pal_name)
                            except Exception:
                                cmap = None
                            if cmap is None:
                                print(f"Could not load palette '{pal_name}'.")
                                continue
                            push_state("cif-color-palette")
                            nsel = len(indices)
                            cif_colors = sample_colormap(cmap, nsel)
                            for c_idx, idx in enumerate(indices):
                                lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
                                try:
                                    col_val = mcolors.to_hex(cif_colors[c_idx])
                                except Exception:
                                    col_val = cif_colors[c_idx]
                                cts[idx] = (lab, fname, peaksQ, wl_e, qmax, col_val)
                            if bp is not None:
                                setattr(bp, 'cif_tick_series', cts)
                            sync_fig_cif_tick_series()
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                else:
                    print("No CIF tick data present.")
                continue
            tokens = line.split()
            # Detect spine: all tokens are spine-key:color pairs (w/a/s/d prefix)
            _is_spine = all(':' in t and t.split(':', 1)[0].lower() in _spine_keys for t in tokens if t)
            if _is_spine and tokens:
                push_state("color-spine")
                changed_spines: list[tuple[str, str]] = []
                for tok in tokens:
                    key_part, color_spec = tok.split(':', 1)
                    spine_name = _spine_keys[key_part.lower()]
                    if spine_name not in ax.spines:
                        print(f"Spine '{spine_name}' not found.")
                        continue
                    try:
                        resolved = resolve_color_token(color_spec, fig)
                        apply_xy_spine_color(fig, ax, tick_state or {}, spine_name, resolved)
                        changed_spines.append((spine_name, resolved))
                        print(f"Set {spine_name} spine to {format_color_listing(resolved)}")
                    except Exception as e:
                        print(f"Error setting {spine_name} color: {e}")
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
                for spine_name, resolved in changed_spines:
                    apply_xy_spine_color(fig, ax, tick_state or {}, spine_name, resolved)
                continue
            # Detect palette: last token has no ':' and more than one token total OR single token is a palette name/number
            _has_colon = any(':' in t for t in tokens)
            if not _has_colon and tokens:
                # Single token: could be palette applied to all, or a named color applied to all (unlikely)
                n_curves = len(labels)
                if len(tokens) == 1:
                    pal = _resolve_pal_token(tokens[0])
                    if pal in plt.colormaps() or ensure_colormap(pal):
                        _apply_palette_to_lines(pal, list(range(n_curves)))
                    else:
                        print(f"Unknown palette or color '{tokens[0]}'. Use curve:color form for per-curve colors.")
                else:
                    # Multiple tokens without ':' → range + palette
                    pal = _resolve_pal_token(tokens[-1])
                    range_part = "".join(tokens[:-1])
                    indices = _parse_ranges(range_part, n_curves)
                    if indices:
                        _apply_palette_to_lines(pal, indices)
                    else:
                        print("No valid indices parsed.")
                continue
            # Mixed: some tokens have ':' — treat as curve index:color pairs
            if _has_colon:
                n_curves = len(labels)
                push_state("color-manual")
                for tok in tokens:
                    if ':' not in tok:
                        print(f"Skip: {tok}")
                        continue
                    idx_str, color_spec = tok.split(':', 1)
                    try:
                        line_idx = int(idx_str) - 1
                    except ValueError:
                        print(f"Bad index: {idx_str}")
                        continue
                    if not (0 <= line_idx < n_curves):
                        print(f"Index out of range: {idx_str}")
                        continue
                    resolved = resolve_color_token(color_spec, fig)
                    apply_curve_color(_line(line_idx), resolved)
                update_labels(ax, y_data_list, label_text_objects, stack, getattr(fig, '_stack_label_at_bottom', False))
                try:
                    fig._curve_palette_history = []
                except Exception:
                    pass
                fig.canvas.draw()
                continue
            print("Unknown input. Use curve:color pairs, range+palette, or spine keys.")
    except Exception as e:
        print(f"Error in color menu: {e}")


__all__ = ["run_xy_color_menu"]
