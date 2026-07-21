"""CIF ticks submenu (``cif``/``z``/``j``) for the XY (diffraction) menu.

Manages CIF phase tick overlays: hkl/title visibility, reordering, per-row
vertical shift, colors, visibility, and phase renaming. CIF state lives on the
batplot module and figure attributes, so the dispatcher injects ``_bp`` plus the
CIF bridge callbacks; mutations go through ``push_state`` for undo parity.
"""

from __future__ import annotations

import sys
import sys as _sys_vis
from typing import Any, Callable

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib import colors as mcolors  # type: ignore[import]

from ...utils import (
    convert_label_shortcuts,
    normalize_xy_cif_stack_y_offsets,
    print_label_latex_tips,
)
from ...color_utils import (
    color_block,
    format_color_listing,
    ensure_colormap,
    get_colormap,
    resolve_color_token,
    _CUSTOM_CMAPS,
)
from ..common.palettes import (
    build_xy_palette_options,
    parse_index_ranges,
    resolve_palette_token,
    sample_colormap,
)


def run_cif_ticks_menu(
    *,
    ax: Any,
    fig: Any,
    _bp: Any,
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    _safe_input: Callable[[str], str],
    push_state: Callable[[str], Any],
    _print_cif_phase_list: Callable[[Any], Any],
    _apply_cif_phase_label_rename: Callable[[int, str], Any],
    _sync_fig_cif_tick_series: Callable[[], Any],
) -> None:
        # Unified CIF ticks submenu (mirrors operando 'c' → CIF menu).
        # Always expose the command; if no CIF data is present, show guidance.
        cif_series = None
        try:
            if _bp is not None and hasattr(_bp, 'cif_tick_series'):
                cif_series = getattr(_bp, 'cif_tick_series')
        except Exception:
            cif_series = None
        has_cif = bool(cif_series)
        if not has_cif:
            print("\nNo CIF tick labels are available.")
            print("To enable CIF ticks, include one or more CIF files when launching batplot, e.g.:")
            print("  batplot data.xy phase.cif:1.5406 --interactive # plot in 2theta space")
            print("  batplot data.xy:0.709 phase.cif --interactive # plot in Q space")
            return

        # Local state mirrors operando CIF submenu: hkl and title visibility flags.
        show_hkl = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else False
        show_titles = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
        while True:
            print("\n\033[1mCIF tick labels:\033[0m")
            hkl_desc = f"z: toggle hkl labels (currently {'on' if show_hkl else 'off'})"
            titles_desc = f"t: toggle CIF titles (currently {'on' if show_titles else 'off'})"
            order_desc = "v: change CIF vertical order (sequence of rows)"
            print("  " + colorize_menu(hkl_desc))
            # Accept both 'j' (legacy) and 't' (to match operando) for title toggle
            print("  " + colorize_menu(titles_desc))
            print("  " + colorize_menu(order_desc))
            print("  " + colorize_menu("p: shift all CIF ticks (w/s or type a value)"))
            print("  " + colorize_menu("c: CIF color (per set)"))
            print("  " + colorize_menu("x: show/hide CIF set"))
            print("  " + colorize_menu("r: rename CIF phase label (same as main menu r→t)"))
            print("  " + colorize_menu("q: back to main menu"))
            sub = _safe_input(colorize_prompt("CIF (z/t/v/p/c/x/r/q): ")).strip().lower()
            if not sub or sub == 'q':
                break
            if sub == 'z':
                try:
                    push_state("toggle-cif-hkl")
                except Exception:
                    pass
                try:
                    cur = bool(getattr(_bp, 'show_cif_hkl', False)) if _bp is not None else False
                    new_state = not cur
                    if _bp is not None:
                        setattr(_bp, 'show_cif_hkl', new_state)
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None:
                            setattr(_bp_module, 'show_cif_hkl', new_state)
                    except Exception:
                        pass
                    prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', True)
                    if hasattr(ax, '_cif_draw_func'):
                        ax._cif_draw_func()
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', prev_ext)
                    n_labels = 0
                    if bool(getattr(_bp, 'show_cif_hkl', False)) and hasattr(ax, '_cif_tick_art'):
                        for art in getattr(ax, '_cif_tick_art'):
                            try:
                                if hasattr(art, 'get_text') and '(' in art.get_text():
                                    n_labels += 1
                            except Exception:
                                pass
                    show_hkl = bool(getattr(_bp, 'show_cif_hkl', False))
                    print(f"CIF hkl labels {'ON' if show_hkl else 'OFF'} (visible labels: {n_labels}).")
                except Exception as e:
                    print(f"Error toggling hkl labels: {e}")
            elif sub == 't':
                try:
                    push_state("toggle-cif-titles")
                except Exception:
                    pass
                try:
                    prev_xlim = ax.get_xlim()
                    prev_ylim = ax.get_ylim()
                    cur = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
                    new_state = not cur
                    if _bp is not None:
                        setattr(_bp, 'show_cif_titles', new_state)
                    fig._bp_show_cif_titles = new_state
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None:
                            setattr(_bp_module, 'show_cif_titles', new_state)
                    except Exception:
                        pass
                    prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', True)
                    if hasattr(ax, '_cif_draw_func'):
                        ax._cif_draw_func()
                    if _bp is not None:
                        setattr(_bp, 'cif_extend_suspended', prev_ext)
                    # Restore limits to prevent drift if draw function adjusted them unexpectedly
                    try:
                        ax.set_xlim(prev_xlim)
                        ax.set_ylim(prev_ylim)
                    except Exception:
                        pass
                    show_titles = new_state
                    print(f"CIF title labels {'ON' if new_state else 'OFF'}.")
                except Exception as e:
                    print(f"Error toggling CIF titles: {e}")
            elif sub == 'v':
                # Reorder CIF series vertically by changing sequence in cif_tick_series.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets to reorder.")
                    else:
                        print("Current CIF order (top to bottom):")
                        for i, (lab, fname, *_rest) in enumerate(cts):
                            print(f"  {i+1}: {lab}")
                        seq = _safe_input("New order (comma-separated indices, e.g. 2,1,3; q=cancel): ").strip().lower()
                        if not seq or seq == 'q':
                            continue
                        try:
                            parts = [int(s.strip()) for s in seq.split(',') if s.strip()]
                        except ValueError:
                            print("Invalid sequence. Use numbers separated by commas, e.g. 2,1,3.")
                            continue
                        n = len(cts)
                        if len(parts) != n or sorted(parts) != list(range(1, n + 1)):
                            print(f"Sequence must be a permutation of 1..{n}.")
                            continue
                        try:
                            push_state("cif-reorder")
                        except Exception:
                            pass
                        new_cts = [cts[i - 1] for i in parts]
                        if _bp is not None:
                            setattr(_bp, 'cif_tick_series', new_cts)
                        _sync_fig_cif_tick_series()
                        prev_offs = getattr(fig, '_bp_cif_stack_y_offsets', None)
                        if prev_offs is not None and len(prev_offs) == len(cts):
                            fig._bp_cif_stack_y_offsets = [prev_offs[i - 1] for i in parts]
                        if hasattr(ax, '_cif_draw_func'):
                            ax._cif_draw_func()
                        print("Updated CIF vertical order.")
                except Exception as e:
                    print(f"Error reordering CIF sets: {e}")
            elif sub == 'p':
                # Same offset list length as CIF sets: apply one shared data-Y shift to every row,
                # or w/s nudge all stacks by fixed typographic points on screen (2 pt).
                _CIF_NUDGE_PT = 2.0
    
                def _dy_data_for_display_pts(ax_, dy_pts):
                    try:
                        x_ref = float(np.mean(ax_.get_xlim()))
                        y_ref = float(np.mean(ax_.get_ylim()))
                        p0 = np.asarray(ax_.transData.transform((x_ref, y_ref)), dtype=float)
                        fig_ = ax_.figure
                        d_pix = float(dy_pts) * (float(fig_.dpi) / 72.0)
                        p1 = p0 + np.array([0.0, d_pix], dtype=float)
                        y1 = float(ax_.transData.inverted().transform(tuple(p1))[1])
                        return y1 - y_ref
                    except Exception:
                        return 0.0
    
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets.")
                    else:
                        n = len(cts)
                        _Hi = '\033[1m'
                        _Cc = '\033[96m'
                        _Rn = '\033[0m'
                        while True:
                            normalize_xy_cif_stack_y_offsets(fig, n)
                            offs = list(fig._bp_cif_stack_y_offsets)
                            print(
                                f"\n{_Hi}All CIF ticks:{_Rn} {_Hi}{_Cc}w{_Rn}/{_Hi}{_Cc}s{_Rn} nudge all "
                                f"(±{_CIF_NUDGE_PT:g} pt), or a {_Hi}{_Cc}number{_Rn} for all; "
                                f"{_Hi}{_Cc}0{_Rn} clear; {_Hi}{_Cc}q{_Rn} leave."
                            )
                            line = _safe_input(colorize_prompt("(w/s/value/0/q): ")).strip().lower()
                            if not line or line == 'q':
                                break
                            dd = _dy_data_for_display_pts(ax, _CIF_NUDGE_PT)
                            if line == 'w':
                                try:
                                    push_state("cif-stack-y-offset")
                                except Exception:
                                    pass
                                fig._bp_cif_stack_y_offsets = [float(o) + dd for o in offs]
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                                continue
                            if line == 's':
                                try:
                                    push_state("cif-stack-y-offset")
                                except Exception:
                                    pass
                                fig._bp_cif_stack_y_offsets = [float(o) - dd for o in offs]
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                                continue
                            if line in ('reset', '0', 'zero'):
                                try:
                                    push_state("cif-stack-y-offset")
                                except Exception:
                                    pass
                                fig._bp_cif_stack_y_offsets = [0.0] * n
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                                continue
                            try:
                                val = float(line)
                            except ValueError:
                                print("w, s, a number, or q.")
                                continue
                            try:
                                push_state("cif-stack-y-offset")
                            except Exception:
                                pass
                            fig._bp_cif_stack_y_offsets = [float(val)] * n
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                except Exception as e:
                    print(f"Error setting CIF offsets: {e}")
            elif sub == 'c':
                # CIF colors: support per-set mappings and palette-like tokens, mirroring main color menu behavior.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets to recolor.")
                    else:
                        # Show current CIF sets and colors
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
                            line = _safe_input("Enter mappings or range+palette (q=back): ").strip()
                            if not line or line.lower() == 'q':
                                break
                            tokens = line.split()
                            # Decide mode: if any token contains ':', treat as manual index:color pairs.
                            if any(':' in t for t in tokens):
                                # Manual CIF index:color pairs, e.g. 1:red 2:u3
                                try:
                                    push_state("cif-color")
                                except Exception:
                                    pass
                                pairs = []
                                for tok in tokens:
                                    if ':' not in tok:
                                        print(f"Skip malformed token: {tok}")
                                        continue
                                    idx_str, color_spec = tok.split(":", 1)
                                    pairs.append((idx_str, color_spec))
                                for idx_str, color_spec in pairs:
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
                                if _bp is not None:
                                    setattr(_bp, 'cif_tick_series', cts)
                                _sync_fig_cif_tick_series()
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                            else:
                                # Palette mode: treat input as "<range> <palette>" similar to main color menu.
                                parts = tokens
                                if len(parts) < 2:
                                    print("Need range(s) and palette (e.g., '1-3 viridis' or 'all magma_r').")
                                    continue
                                range_part = " ".join(parts[:-1]).replace(" ", "")
                                palette_token = parts[-1]
                                # Resolve palette token: number or name, with optional _r suffix.
                                available = list(_CUSTOM_CMAPS.keys()) + list(plt.colormaps())
                                # If numeric, map to a small predefined list as in main menu
                                palette_options = build_xy_palette_options(ensure_colormap)
                                palette_index = {str(i): name for i, name in enumerate(palette_options, 1)}
                                palette_name = resolve_palette_token(palette_token, palette_index)
                                # Check palette availability
                                if palette_name not in available and not ensure_colormap(palette_name):
                                    print(f"Unknown palette '{palette_name}'.")
                                    continue
                                indices = parse_index_ranges(range_part, len(cts), warn_out_of_range=True)
                                if not indices:
                                    print("No valid indices parsed.")
                                    continue
                                try:
                                    cmap = get_colormap(palette_name)
                                except Exception:
                                    cmap = None
                                if cmap is None:
                                    print(f"Could not load palette '{palette_name}'.")
                                    continue
                                try:
                                    push_state("cif-color-palette")
                                except Exception:
                                    pass
                                nsel = len(indices)
                                colors = sample_colormap(cmap, nsel)
                                for c_idx, idx in enumerate(indices):
                                    lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
                                    col = colors[c_idx]
                                    # Convert RGBA to hex or keep as RGBA tuple
                                    try:
                                        col_val = mcolors.to_hex(col)
                                    except Exception:
                                        col_val = col
                                    cts[idx] = (lab, fname, peaksQ, wl_e, qmax, col_val)
                                if _bp is not None:
                                    setattr(_bp, 'cif_tick_series', cts)
                                _sync_fig_cif_tick_series()
                                if hasattr(ax, '_cif_draw_func'):
                                    ax._cif_draw_func()
                except Exception as e:
                    print(f"Error changing CIF colors: {e}")
            elif sub == 'x':
                # Per-set CIF visibility: maintain a boolean list in __main__.cif_set_visible.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF tick sets to show/hide.")
                    else:
                        _bp_module = _sys_vis.modules.get('__main__')
                        vis = []
                        if _bp_module is not None and hasattr(_bp_module, 'cif_set_visible'):
                            try:
                                vis = list(getattr(_bp_module, 'cif_set_visible') or [])
                            except Exception:
                                vis = []
                        if len(vis) < len(cts):
                            vis = vis + [True] * (len(cts) - len(vis))
                        while True:
                            print("CIF set visibility (q=back):")
                            for i, (lab, fname, *_rest) in enumerate(cts):
                                state = "show" if vis[i] else "hide"
                                print(f"  {i+1}: {lab} ({state})")
                            idx_s = _safe_input("Set index to toggle (q=back): ").strip().lower()
                            if not idx_s or idx_s == 'q':
                                break
                            try:
                                idx = int(idx_s) - 1
                                if 0 <= idx < len(cts):
                                    try:
                                        push_state("cif-visibility")
                                    except Exception:
                                        pass
                                    vis[idx] = not vis[idx]
                                    if _bp_module is not None:
                                        setattr(_bp_module, 'cif_set_visible', list(vis))
                                    if hasattr(ax, '_cif_draw_func'):
                                        ax._cif_draw_func()
                                else:
                                    print("Invalid index.")
                            except ValueError:
                                print("Invalid index.")
                except Exception as e:
                    print(f"Error toggling CIF visibility: {e}")
            elif sub == 'r':
                # Rename CIF phase labels — same behavior as main menu r→t.
                try:
                    cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
                    if not cts:
                        print("No CIF phases to rename.")
                    else:
                        while True:
                            print("CIF phases (q=back to CIF menu)")
                            _print_cif_phase_list(cts)
                            idx_s = _safe_input(
                                "Phase number to rename (q=back): "
                            ).strip().lower()
                            if not idx_s or idx_s == 'q':
                                break
                            try:
                                idx = int(idx_s) - 1
                                if not (0 <= idx < len(cts)):
                                    print("Invalid index.")
                                    continue
                            except ValueError:
                                print("Invalid index.")
                                continue
                            print_label_latex_tips()
                            while True:
                                new_lab = _safe_input(
                                    f"New CIF phase label (q=back): "
                                ).strip()
                                if not new_lab or new_lab.lower() == 'q':
                                    break
                                new_lab = convert_label_shortcuts(new_lab)
                                _apply_cif_phase_label_rename(idx, new_lab)
                                print(f"Phase {idx + 1} label updated.")
                except Exception as e:
                    print(f"Error renaming CIF phase labels: {e}")
            else:
                print("Unknown option.")
        return


__all__ = ["run_cif_ticks_menu"]
