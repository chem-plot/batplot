"""Inline panel submenus for the CPC interactive menu.

Extracted verbatim from interactive.py: the former inline dispatch blocks for
``v`` (file visibility), ``k`` (spine colors), ``d`` (display mode), ``ry``
(efficiency axis), ``l`` (line widths/grid), ``m`` (marker sizes), and ``ie``
(invert efficiency). The dispatcher keeps thin calls so prompts, messages, and
undo semantics are unchanged.
"""
from __future__ import annotations

import numpy as np

from ...color_utils import blank_means_back, prompt_screen_color, resolve_color_token
from ..common.spines import (
    apply_frame_and_tick_widths,
    current_tick_width,
    parse_frame_tick_widths,
    sync_tick_state_from_wasd,
)
from .legend import _color_of, _normalize_spine_color, _rebuild_legend


def _cpc_efficiency_globally_on(fig, file_data) -> bool:
    """Current global efficiency-on intent (``ry`` / wasd), not per-file hide."""
    wasd = getattr(fig, "_cpc_wasd_state", None)
    if isinstance(wasd, dict) and isinstance(wasd.get("right"), dict):
        if "title" in wasd["right"]:
            return bool(wasd["right"]["title"])
        if "ticks" in wasd["right"]:
            return bool(wasd["right"]["ticks"])
    # Fallback: any efficiency artist currently drawn on a visible file.
    for f in file_data or []:
        if not f.get("visible", True):
            continue
        sc = f.get("sc_eff")
        try:
            if sc is not None and sc.get_visible():
                return True
        except Exception:
            pass
    return False


def apply_cpc_file_artist_visibility(fig, file_data, *, eff_on: bool | None = None) -> None:
    """Apply ``visible`` × ``display_mode`` × efficiency-on to CPC scatter artists.

    Shared by interactive ``d``/``v``, batch sync, and style restore so hidden
    files are not resurrected by display-mode changes.
    """
    mode = getattr(fig, "_cpc_display_mode", "both") or "both"
    if eff_on is None:
        eff_on = _cpc_efficiency_globally_on(fig, file_data)
    for f in file_data or []:
        file_vis = bool(f.get("visible", True))
        sc_c = f.get("sc_charge")
        sc_d = f.get("sc_discharge")
        sc_e = f.get("sc_eff")
        try:
            if sc_c is not None:
                sc_c.set_visible(file_vis and mode in ("charge", "both"))
        except Exception:
            pass
        try:
            if sc_d is not None:
                sc_d.set_visible(file_vis and mode in ("discharge", "both"))
        except Exception:
            pass
        try:
            if sc_e is not None:
                sc_e.set_visible(file_vis and bool(eff_on))
        except Exception:
            pass


def run_cpc_visibility_menu(
    *,
    fig,
    ax,
    ax2,
    file_data,
    current_file_idx,
    is_multi_file,
    push_state,
    print_menu,
    print_file_list,
    safe_input,
    colorize_menu,
    colorize_prompt,
):
    """File visibility toggles (v). Former inline v block."""
    try:
        if is_multi_file:
            while True:
                print_file_list(file_data, current_file_idx)
                print("  " + colorize_menu("1, 1 2 3, 1-4: toggle file(s)"))
                print("  " + colorize_menu("a: toggle all"))
                print("  " + colorize_menu("q: back"))
                choice = safe_input(
                    colorize_prompt(f"Select file numbers (1-{len(file_data)}), a=all, q=back: ")
                ).strip()
                if not choice or choice.lower() == 'q':
                    break

                indices_to_toggle = []
                if choice.lower() in ('a', 'all'):
                    indices_to_toggle = list(range(len(file_data)))
                else:
                    parts = choice.replace(',', ' ').split()
                    for p in parts:
                        p = p.strip()
                        if not p:
                            continue
                        if '-' in p and p.count('-') == 1:
                            try:
                                lo, hi = p.split('-')
                                lo_i = int(lo.strip()) - 1
                                hi_i = int(hi.strip()) - 1
                                for i in range(lo_i, hi_i + 1):
                                    if 0 <= i < len(file_data):
                                        indices_to_toggle.append(i)
                            except ValueError:
                                pass
                        else:
                            try:
                                idx = int(p) - 1
                                if 0 <= idx < len(file_data):
                                    indices_to_toggle.append(idx)
                            except ValueError:
                                pass
                    indices_to_toggle = sorted(set(indices_to_toggle))

                if indices_to_toggle:
                    push_state("visibility")
                    for idx in indices_to_toggle:
                        f = file_data[idx]
                        f['visible'] = not f.get('visible', True)
                    # Honor display_mode + ry — do not force charge/discharge/eff all on.
                    apply_cpc_file_artist_visibility(fig, file_data)
                    _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                    fig.canvas.draw_idle()
                    names = [file_data[i].get('filename', f'File {i+1}') for i in indices_to_toggle]
                    print(f"Toggled: {', '.join(names)}")
                else:
                    print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
        else:
            print("File visibility (v) is only available in multi-file CPC mode.")
    except ValueError:
        print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
    except Exception as e:
        print(f"Visibility toggle failed: {e}")
    print_menu(fig)
    if is_multi_file:
        print_file_list(file_data, current_file_idx)


def run_cpc_spine_color_menu(
    *,
    fig,
    file_data,
    current_file_idx,
    is_multi_file,
    sc_charge,
    sc_eff,
    push_state,
    set_spine_color,
    print_menu,
    print_file_list,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
):
    """Spine colors w/a/s/d mappings with auto mode (k). Former inline k block."""
    try:
        while True:
            print("\nSet spine colors (with matching tick and label colors):")
            print(colorize_inline_commands("  w : top spine    | a : left spine"))
            print(colorize_inline_commands("  s : bottom spine | d : right spine"))
            print(colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
            # Add auto function when only one file is loaded
            if not is_multi_file:
                auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                auto_status = "ON" if auto_enabled else "OFF"
                print(colorize_inline_commands(f"  auto : auto-apply capacity color to left y-axis, efficiency to right y-axis [{auto_status}]"))
            print("  " + colorize_menu("e: pick color from screen"))
            print("  " + colorize_menu("q: back to main menu"))
            line = safe_input(colorize_prompt("Enter mappings (e.g., w:red a:#4561F7, q=back): ")).strip()
            if line.lower() == 'q' or blank_means_back(line):
                break
            if line.lower() == 'e':
                prompt_screen_color(fig)
                continue
            # Handle auto toggle when only one file is loaded
            # Bare ``a`` is left-spine (a:color); only ``auto`` toggles auto mode.
            if not is_multi_file and line.lower() == 'auto':
                auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                # Always push before mutate so ``b`` can restore prior auto state.
                push_state("color-spine-auto")
                fig._cpc_spine_auto = not auto_enabled
                new_status = "ON" if fig._cpc_spine_auto else "OFF"
                print(f"Auto mode: {new_status}")
                if fig._cpc_spine_auto:
                    try:
                        # Draw first so tick objects exist (even when right axis was hidden)
                        fig.canvas.draw_idle()
                        # Get capacity curve color (charge color)
                        charge_col = _normalize_spine_color(_color_of(sc_charge))
                        # Get efficiency curve color
                        eff_col = _normalize_spine_color(_color_of(sc_eff))
                        if charge_col and eff_col:
                            set_spine_color('left', charge_col)
                            set_spine_color('right', eff_col)
                            print(f"Applied: left y-axis = {charge_col}, right y-axis = {eff_col}")
                        else:
                            print("Could not get charge/efficiency colors from artists.")
                        fig.canvas.draw()
                    except Exception as e:
                        print(f"Error applying auto colors: {e}")
                continue
            # Map wasd to spine names
            key_to_spine = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}
            tokens = line.split()
            planned = []
            for token in tokens:
                if ':' not in token:
                    # Skip auto keyword silently (handled above)
                    if token.lower() != 'auto':
                        print(f"Skip malformed token: {token}")
                    continue
                key_part, color = token.split(':', 1)
                key_part = key_part.lower()
                if key_part not in key_to_spine:
                    print(f"Unknown key: {key_part} (use w/a/s/d)")
                    continue
                try:
                    resolved = resolve_color_token(color, fig)
                except Exception as exc:
                    print(f"Skip {key_part}: {exc}")
                    continue
                planned.append((key_to_spine[key_part], resolved))
            if not planned:
                continue
            push_state("color-spine")
            # Draw first so tick objects exist (even when right axis was hidden)
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            manual_change_made = False
            for spine_name, resolved in planned:
                set_spine_color(spine_name, resolved)
                print(f"Set {spine_name} spine to {resolved}")
                manual_change_made = True
            # Disable auto mode if manual changes were made
            if manual_change_made and not is_multi_file and getattr(fig, '_cpc_spine_auto', False):
                fig._cpc_spine_auto = False
                print("Auto mode disabled (manual spine color set)")
            fig.canvas.draw()
    except Exception as e:
        print(f"Error in spine color menu: {e}")
    print_menu(fig)
    if is_multi_file:
        print_file_list(file_data, current_file_idx)


def run_cpc_display_menu(
    *,
    fig,
    ax,
    ax2,
    file_data,
    current_file_idx,
    is_multi_file,
    push_state,
    print_menu,
    print_file_list,
    safe_input,
    colorize_menu,
    colorize_prompt,
):
    """Charge/discharge/both display mode (d). Former inline d block."""
    # Display mode: charge-only / discharge-only / both
    try:
        while True:
            print("\nDisplay mode for CPC:")
            print("  " + colorize_menu("c: show only charge capacity (hide discharge)"))
            print("  " + colorize_menu("d: show only discharge capacity (hide charge)"))
            print("  " + colorize_menu("b: show both charge and discharge"))
            print("  " + colorize_menu("q: back"))
            sub = safe_input(colorize_prompt("Display (c/d/b/q): ")).strip().lower()
            if not sub or sub == 'q':
                break
            if sub == 'c':
                push_state("display-charge")
                try:
                    fig._cpc_display_mode = "charge"
                except Exception:
                    pass
                apply_cpc_file_artist_visibility(fig, file_data)
            elif sub == 'd':
                push_state("display-discharge")
                try:
                    fig._cpc_display_mode = "discharge"
                except Exception:
                    pass
                apply_cpc_file_artist_visibility(fig, file_data)
            elif sub == 'b':
                push_state("display-both")
                try:
                    fig._cpc_display_mode = "both"
                except Exception:
                    pass
                apply_cpc_file_artist_visibility(fig, file_data)
            else:
                print("Unknown choice (use c, d, b, or q).")
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
            fig.canvas.draw_idle()
    except Exception as e:
        print(f"Display mode change failed: {e}")
    print_menu(fig)
    if is_multi_file:
        print_file_list(file_data, current_file_idx)


def run_cpc_efficiency_axis_menu(
    *,
    fig,
    ax,
    ax2,
    sc_eff,
    file_data,
    is_multi_file,
    tick_state,
    push_state,
    sanitize_legend_offset,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
):
    """Efficiency (right Y) axis visibility toggle (ry). Former inline ry block."""
    while True:
        print("  " + colorize_menu("t: toggle efficiency axis visibility"))
        print("  " + colorize_menu("q: back"))
        sub = safe_input(colorize_prompt("Efficiency axis (t/q): ")).strip().lower()
        if not sub or sub == 'q':
            break
        if sub != 't':
            print("Unknown option.")
            continue
        try:
            push_state("toggle-eff")

            # Capture current legend position BEFORE toggling visibility
            try:
                if not hasattr(fig, '_cpc_legend_xy_in') or getattr(fig, '_cpc_legend_xy_in') is None:
                    leg0 = ax.get_legend()
                    if leg0 is not None and leg0.get_visible():
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
                            offset = ((fx - 0.5) * fw, (fy - 0.5) * fh)
                            offset = sanitize_legend_offset(offset)
                            if offset is not None:
                                fig._cpc_legend_xy_in = offset
                        except Exception:
                            pass
            except Exception:
                pass

            # Global ry intent (wasd), not per-file artist visibility — all files
            # hidden via ``v`` would otherwise force toggle stuck on "show".
            new_vis = not _cpc_efficiency_globally_on(fig, file_data)

            # Series + chrome only — never ax2.set_visible (would hide right spine).
            try:
                ax2.yaxis.label.set_visible(new_vis)
            except Exception:
                pass

            try:
                ax2.tick_params(axis='y', right=new_vis, labelright=new_vis)
            except Exception:
                pass

            try:
                wasd = getattr(fig, '_cpc_wasd_state', None)
                if not isinstance(wasd, dict):
                    wasd = {
                        'top': {'spine': bool(ax.spines.get('top').get_visible()) if ax.spines.get('top') else False,
                                'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
                                'minor': bool(tick_state.get('mtx', False)),
                                'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
                                'title': bool(getattr(ax, '_top_xlabel_on', False))},
                        'bottom': {'spine': bool(ax.spines.get('bottom').get_visible()) if ax.spines.get('bottom') else True,
                                   'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
                                   'minor': bool(tick_state.get('mbx', False)),
                                   'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
                                   'title': bool(ax.xaxis.label.get_visible())},
                        'left': {'spine': bool(ax.spines.get('left').get_visible()) if ax.spines.get('left') else True,
                                 'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
                                 'minor': bool(tick_state.get('mly', False)),
                                 'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
                                 'title': bool(ax.yaxis.label.get_visible())},
                        'right': {'spine': bool(ax2.spines.get('right').get_visible()) if ax2.spines.get('right') else True,
                                  'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', True))),
                                  'minor': bool(tick_state.get('mry', False)),
                                  'labels': bool(tick_state.get('r_labels', tick_state.get('ry', True))),
                                  'title': bool(ax2.yaxis.label.get_visible())},
                    }
                wasd.setdefault('right', {})
                wasd['right']['ticks'] = bool(new_vis)
                wasd['right']['labels'] = bool(new_vis)
                wasd['right']['title'] = bool(new_vis)
                setattr(fig, '_cpc_wasd_state', wasd)
                # Keep split + legacy keys coherent (do not leave ry alone stale).
                sync_tick_state_from_wasd(
                    tick_state,
                    wasd,
                    tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                    label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                )
                try:
                    ax._saved_tick_state = dict(tick_state)
                except Exception:
                    pass
            except Exception:
                pass

            # Apply series visibility: file_vis × display_mode × ry(new_vis).
            apply_cpc_file_artist_visibility(fig, file_data, eff_on=bool(new_vis))
            if not is_multi_file and sc_eff is not None:
                try:
                    sc_eff.set_visible(bool(new_vis))
                except Exception:
                    pass

            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
            fig.canvas.draw_idle()
        except Exception:
            pass
    print_menu(fig)


def run_cpc_line_width_menu(
    *,
    fig,
    ax,
    ax2,
    push_state,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
):
    """Frame/tick widths and grid toggle (l). Former inline l block."""
    # Line widths submenu: frame/ticks vs grid
    try:
        while True:
            # Show current widths summary
            try:
                cur_sp_lw = {name: (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None)
                              for name in ('bottom','top','left','right')}
            except Exception:
                cur_sp_lw = {}
            x_maj = current_tick_width(ax.xaxis, 'major')
            x_min = current_tick_width(ax.xaxis, 'minor')
            ly_maj = current_tick_width(ax.yaxis, 'major')
            ly_min = current_tick_width(ax.yaxis, 'minor')
            ry_maj = current_tick_width(ax2.yaxis, 'major')
            ry_min = current_tick_width(ax2.yaxis, 'minor')
            print("Line widths:")
            if cur_sp_lw:
                print("  Frame spines lw:", 
                      " ".join(f"{k}={v:.3g}" if isinstance(v,(int,float)) else f"{k}=?" for k,v in cur_sp_lw.items()))
            print(f"  Tick widths: xM={x_maj if x_maj is not None else '?'} xm={x_min if x_min is not None else '?'} lyM={ly_maj if ly_maj is not None else '?'} lym={ly_min if ly_min is not None else '?'} ryM={ry_maj if ry_maj is not None else '?'} rym={ry_min if ry_min is not None else '?'}")
            print("\033[1mLine submenu:\033[0m")
            print(f"  {colorize_menu('f  : change frame (axes spines) and tick widths')}")
            print(f"  {colorize_menu('g  : toggle grid lines')}")
            print(f"  {colorize_menu('q  : return')}")
            sub = safe_input(colorize_prompt("Choose (f/g/q): ")).strip().lower()
            if not sub:
                continue
            if sub == 'q':
                break
            if sub == 'f':
                while True:
                    fw_in = safe_input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q=back: ").strip()
                    if not fw_in or fw_in.lower() == 'q':
                        break
                    try:
                        frame_w, tick_major, tick_minor = parse_frame_tick_widths(fw_in)
                    except ValueError:
                        print("Invalid numeric value(s).")
                        continue
                    push_state("framewidth")
                    apply_frame_and_tick_widths(
                        [ax, ax2],
                        frame_width=frame_w,
                        major_width=tick_major,
                        minor_width=tick_minor,
                    )
                    fig.canvas.draw()
                    print(f"Set frame width={frame_w}, major tick width={tick_major}, minor tick width={tick_minor}")
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
                    # Disable grid
                    ax.grid(False)
                fig.canvas.draw()
                print(f"Grid {'enabled' if new_grid_state else 'disabled'}.")
            else:
                print("Unknown option.")
    except Exception as e:
        print(f"Error in line submenu: {e}")
    print_menu(fig)


def run_cpc_marker_size_menu(
    *,
    fig,
    sc_charge,
    sc_discharge,
    sc_eff,
    file_data,
    is_multi_file,
    push_state,
    print_menu,
    safe_input,
):
    """Marker sizes for all series (m). Former inline m block."""
    try:
        while True:
            print("Current marker sizes:")
            try:
                c_ms = getattr(sc_charge, 'get_sizes', lambda: [32])()[0]
            except Exception:
                c_ms = 32
            try:
                d_ms = getattr(sc_discharge, 'get_sizes', lambda: [32])()[0]
            except Exception:
                d_ms = 32
            try:
                e_ms = getattr(sc_eff, 'get_sizes', lambda: [40])()[0]
            except Exception:
                e_ms = 40
            print(f"  charge ms={c_ms}, discharge ms={d_ms}, efficiency ms={e_ms}")
            spec = safe_input("Set new marker size for all series (q=back): ").strip().lower()
            if not spec or spec == 'q':
                break
            try:
                num = float(spec)
                push_state("marker-size")
                # Apply to current file's artists
                if hasattr(sc_charge, 'set_sizes'):
                    sc_charge.set_sizes([num])
                if hasattr(sc_discharge, 'set_sizes'):
                    sc_discharge.set_sizes([num])
                if hasattr(sc_eff, 'set_sizes'):
                    sc_eff.set_sizes([num])
                # In multi-file mode, also apply to all files' capacity/efficiency
                if is_multi_file and file_data:
                    for f in file_data:
                        ch = f.get('sc_charge')
                        dh = f.get('sc_discharge')
                        ef = f.get('sc_eff')
                        try:
                            if ch is not None and hasattr(ch, 'set_sizes'):
                                ch.set_sizes([num])
                        except Exception:
                            pass
                        try:
                            if dh is not None and hasattr(dh, 'set_sizes'):
                                dh.set_sizes([num])
                        except Exception:
                            pass
                        try:
                            if ef is not None and hasattr(ef, 'set_sizes'):
                                ef.set_sizes([num])
                        except Exception:
                            pass
                fig.canvas.draw_idle()
            except Exception:
                print("Invalid value.")
    except Exception as e:
        print(f"Error: {e}")
    print_menu(fig)


def run_cpc_invert_efficiency_menu(
    *,
    fig,
    sc_eff,
    file_data,
    current_file_idx,
    is_multi_file,
    push_state,
    print_menu,
    print_file_list,
    safe_input,
):
    """Invert coulombic efficiency around 100% (ie). Former inline ie block."""
    # Invert coulombic efficiency values around 100% for the current file(s)
    try:
        if sc_eff is None or not hasattr(sc_eff, 'get_offsets'):
            print("No efficiency data to invert.")
            print_menu(fig); return
        if is_multi_file:
            print_file_list(file_data, current_file_idx)
            choice = safe_input(
                f"Select file numbers (1-{len(file_data)}) to invert efficiency, a for all, or q=cancel: "
            ).strip().lower()
            if not choice or choice == 'q':
                print_menu(fig); return
            targets = []
            if choice in ('a', 'all'):
                targets = list(range(len(file_data)))
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(file_data):
                        targets = [idx]
                    else:
                        print("Invalid file number.")
                        print_menu(fig); return
                except ValueError:
                    print("Invalid choice.")
                    print_menu(fig); return
            # Validate at least one invertible target before burning an undo tip.
            can_invert = False
            for idx in targets:
                f = file_data[idx]
                eff_sc = f.get('sc_eff')
                if eff_sc is None or not hasattr(eff_sc, 'get_offsets'):
                    continue
                if np.asarray(eff_sc.get_offsets()).size:
                    can_invert = True
                    break
            if not can_invert:
                print("No efficiency data to invert.")
                print_menu(fig); return
            push_state("invert-efficiency")
            for idx in targets:
                f = file_data[idx]
                eff_sc = f.get('sc_eff')
                if eff_sc is None or not hasattr(eff_sc, 'get_offsets'):
                    continue
                offsets = eff_sc.get_offsets()
                if offsets.size == 0:
                    continue
                xs = offsets[:, 0]
                ys = offsets[:, 1]
                # Invert around 100% (y -> 100 - y + 100 = 200 - y)
                new_ys = 200.0 - ys
                eff_sc.set_offsets(list(zip(xs, new_ys)))
                f['eff_inverted'] = not bool(f.get('eff_inverted', False))
            fig.canvas.draw_idle()
            print("Inverted efficiency for selected file(s).")
        else:
            offsets = sc_eff.get_offsets()
            if offsets.size == 0:
                print("No efficiency data to invert.")
                print_menu(fig); return
            xs = offsets[:, 0]
            ys = offsets[:, 1]
            push_state("invert-efficiency")
            new_ys = 200.0 - ys
            sc_eff.set_offsets(list(zip(xs, new_ys)))
            if file_data:
                file_data[0]['eff_inverted'] = not bool(
                    file_data[0].get('eff_inverted', False)
                )
            fig.canvas.draw_idle()
            print("Inverted efficiency for current dataset.")
    except Exception as e:
        print(f"Error in efficiency inversion: {e}")
    print_menu(fig)
