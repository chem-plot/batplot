"""Axis/limit submenus for the operando interactive menu.

Extracted verbatim from interactive.py: the former nested handlers
``_handle_op_et`` / ``_handle_op_ex`` / ``_handle_op_ox`` and the inline
``oy`` (operando Y) and ``ey`` (EC ions/time) dispatch blocks. The dispatcher
keeps thin wrappers/calls so prompts, messages, and undo semantics are
unchanged.
"""
from __future__ import annotations

import numpy as np  # type: ignore[import-untyped]

from .ions_axis import (
    charge_segment_bounds,
    clear_ec_ion_overlays,
    install_ec_ions_y_display,
    place_ec_ion_segment_labels,
    restore_ec_time_y_display,
)
from .layout import _redraw_operando_cif_if_present


def run_ec_time_range_menu(
    *,
    fig,
    ec_ax,
    snapshot,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
):
    """EC time (Y) range submenu (limits/w/s/a/q). Former _handle_op_et."""
    if ec_ax is None:
        print("EC panel not available (no .mpt file in folder).")
        print_menu()
        return
    while True:
        cur = ec_ax.get_ylim(); print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("a: auto (restore original)"))
        print("  " + colorize_menu("q: back"))
        line = safe_input(colorize_prompt("EC time (w/s/a/q): ")).strip()
        if not line or line.lower() == 'q':
            break
        if line.lower() == 'w':
            # Upper only: change upper limit, fix lower - stay in loop
            while True:
                cur = ec_ax.get_ylim()
                print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new upper time limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_upper = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("ec-time-range")
                ec_ax.set_ylim(cur[0], new_upper)
                ec_ax._saved_time_ylim = (cur[0], new_upper)
                fig.canvas.draw_idle()
                print(f"EC time range updated: {ec_ax.get_ylim()[0]:.4g} {ec_ax.get_ylim()[1]:.4g}")
            continue
        if line.lower() == 's':
            # Lower only: change lower limit, fix upper - stay in loop
            while True:
                cur = ec_ax.get_ylim()
                print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new lower time limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_lower = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("ec-time-range")
                ec_ax.set_ylim(new_lower, cur[1])
                ec_ax._saved_time_ylim = (new_lower, cur[1])
                fig.canvas.draw_idle()
                print(f"EC time range updated: {ec_ax.get_ylim()[0]:.4g} {ec_ax.get_ylim()[1]:.4g}")
            continue
        if line.lower() == 'a':
            # Auto: restore original range from EC lines
            try:
                all_y = []
                for ln in ec_ax.lines:
                    try:
                        yd = np.asarray(ln.get_ydata(), dtype=float)
                        if yd.size > 0:
                            all_y.extend([yd.min(), yd.max()])
                    except Exception:
                        pass
                if all_y:
                    orig_min = min(all_y)
                    orig_max = max(all_y)
                    snapshot("ec-time-range-auto")
                    ec_ax.set_ylim(orig_min, orig_max)
                    ec_ax._saved_time_ylim = (orig_min, orig_max)
                    fig.canvas.draw_idle()
                    print(f"EC time range restored to original: {ec_ax.get_ylim()[0]:.4g} {ec_ax.get_ylim()[1]:.4g}")
                else:
                    print("No original data available.")
            except Exception as e:
                print(f"Error restoring original time range: {e}")
            continue
        try:
            lo, hi = map(float, line.split())
        except Exception as e:
            print(f"Invalid range: {e}")
            continue
        snapshot("ec-time-range")
        try:
            ec_ax.set_ylim(lo, hi)
            # Persist chosen time-mode limits so ey toggles won't override
            try:
                ec_ax._saved_time_ylim = (lo, hi)
            except Exception:
                pass
            # Ions mode keeps the time spine; only refresh status-bar mapping.
            if getattr(ec_ax, '_ec_y_mode', 'time') == 'ions':
                try:
                    t = np.asarray(getattr(ec_ax, '_ec_time_h'))
                    ions_abs = getattr(ec_ax, '_ions_abs', None)
                    if ions_abs is not None:
                        install_ec_ions_y_display(ec_ax, t, ions_abs, save_prev=False)
                except Exception:
                    pass
            fig.canvas.draw_idle()
        except Exception as e:
            print(f"Invalid range: {e}")
    print_menu()


def run_ec_x_range_menu(
    *,
    fig,
    ec_ax,
    snapshot,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
):
    """EC X range submenu (limits/w/s/a/q). Former _handle_op_ex."""
    if ec_ax is None:
        print("EC panel not available (no .mpt file in folder).")
        print_menu()
        return
    while True:
        cur = ec_ax.get_xlim()
        print(f"Current EC X range: {cur[0]:.4g} {cur[1]:.4g}")
        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("a: auto (restore original)"))
        print("  " + colorize_menu("q: back"))
        line = safe_input(colorize_prompt("EC X (w/s/a/q): ")).strip()
        if not line or line.lower() == 'q':
            break
        if line.lower() == 'w':
            # Upper only: change upper limit, fix lower - stay in loop
            while True:
                cur = ec_ax.get_xlim()
                print(f"Current EC X range: {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new upper EC X limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_upper = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("ec-x-range")
                ec_ax.set_xlim(cur[0], new_upper)
                ec_ax._prev_ec_xlim = (cur[0], new_upper)
                ec_ax._ions_xlim_expanded = False
                fig.canvas.draw_idle()
                print(f"EC X range updated: {ec_ax.get_xlim()[0]:.4g} {ec_ax.get_xlim()[1]:.4g}")
            continue
        if line.lower() == 's':
            # Lower only: change lower limit, fix upper - stay in loop
            while True:
                cur = ec_ax.get_xlim()
                print(f"Current EC X range: {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new lower EC X limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_lower = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("ec-x-range")
                ec_ax.set_xlim(new_lower, cur[1])
                ec_ax._prev_ec_xlim = (new_lower, cur[1])
                ec_ax._ions_xlim_expanded = False
                fig.canvas.draw_idle()
                print(f"EC X range updated: {ec_ax.get_xlim()[0]:.4g} {ec_ax.get_xlim()[1]:.4g}")
            continue
        if line.lower() == 'a':
            # Auto: restore original range from EC lines
            try:
                all_x = []
                for ln in ec_ax.lines:
                    try:
                        xd = np.asarray(ln.get_xdata(), dtype=float)
                        if xd.size > 0:
                            all_x.extend([xd.min(), xd.max()])
                    except Exception:
                        pass
                if all_x:
                    orig_min = min(all_x)
                    orig_max = max(all_x)
                    snapshot("ec-x-range-auto")
                    ec_ax.set_xlim(orig_min, orig_max)
                    ec_ax._prev_ec_xlim = (orig_min, orig_max)
                    ec_ax._ions_xlim_expanded = False
                    fig.canvas.draw_idle()
                    print(f"EC X range restored to original: {ec_ax.get_xlim()[0]:.4g} {ec_ax.get_xlim()[1]:.4g}")
                else:
                    print("No original data available.")
            except Exception as e:
                print(f"Error restoring original EC X range: {e}")
            continue
        try:
            lo, hi = map(float, line.split())
            if lo == hi:
                raise ValueError("limits must differ")
        except Exception as e:
            print(f"Invalid range: {e}")
            continue
        snapshot("ec-x-range")
        try:
            ec_ax.set_xlim(lo, hi)
            try:
                ec_ax._prev_ec_xlim = (lo, hi)
                ec_ax._ions_xlim_expanded = False
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
        except Exception as e:
            print(f"Invalid range: {e}")
    print_menu()


def run_operando_x_range_menu(
    *,
    fig,
    ax,
    im,
    cbar,
    snapshot,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
    dqdv_2d_potential_window_menu,
    pop_undo=None,
):
    """Operando X range submenu (limits/w/s/a/q). Former _handle_op_ox."""
    if getattr(fig, '_is_dqdv_2d_contour', False):
        try:
            dqdv_2d_potential_window_menu(
                fig, ax, im, cbar, snapshot, pop_undo=pop_undo
            )
        except Exception as e:
            print(f"Potential window change failed: {e}")
        print_menu()
        return
    while True:
        cur = ax.get_xlim(); print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("a: auto (restore original)"))
        print("  " + colorize_menu("q: back"))
        line = safe_input(colorize_prompt("Operando X (w/s/a/q): ")).strip()
        if not line or line.lower() == 'q':
            break
        if line.lower() == 'w':
            # Upper only: change upper limit, fix lower - stay in loop
            while True:
                cur = ax.get_xlim()
                print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new upper X limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_upper = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("operando-xrange")
                ax.set_xlim(cur[0], new_upper)
                _redraw_operando_cif_if_present(fig, ax)
                fig.canvas.draw_idle()
                print(f"Operando X range updated: {ax.get_xlim()[0]:.4g} {ax.get_xlim()[1]:.4g}")
        if line.lower() == 'w':
            continue
        if line.lower() == 's':
            # Lower only: change lower limit, fix upper - stay in loop
            while True:
                cur = ax.get_xlim()
                print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new lower X limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_lower = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("operando-xrange")
                ax.set_xlim(new_lower, cur[1])
                _redraw_operando_cif_if_present(fig, ax)
                fig.canvas.draw_idle()
                print(f"Operando X range updated: {ax.get_xlim()[0]:.4g} {ax.get_xlim()[1]:.4g}")
        if line.lower() == 's':
            continue
        if line.lower() == 'a':
            # Auto: restore original range from image data
            try:
                data_array = np.asarray(im.get_array(), dtype=float)
                if data_array.size > 0:
                    # Get original extent from image
                    extent = im.get_extent()
                    if extent and len(extent) == 4:
                        orig_min = min(extent[0], extent[1])
                        orig_max = max(extent[0], extent[1])
                        snapshot("operando-xrange-auto")
                        ax.set_xlim(orig_min, orig_max)
                        _redraw_operando_cif_if_present(fig, ax)
                        fig.canvas.draw_idle()
                        print(f"Operando X range restored to original: {ax.get_xlim()[0]:.4g} {ax.get_xlim()[1]:.4g}")
                    else:
                        print("No original data available.")
                else:
                    print("No original data available.")
            except Exception as e:
                print(f"Error restoring original X range: {e}")
            continue
        try:
            lo, hi = map(float, line.split())
        except Exception as e:
            print(f"Invalid range: {e}")
            continue
        snapshot("operando-xrange")
        try:
            ax.set_xlim(lo, hi)
            _redraw_operando_cif_if_present(fig, ax)
            fig.canvas.draw_idle()
        except Exception as e:
            print(f"Invalid range: {e}")
    print_menu()


def run_operando_y_range_menu(
    *,
    fig,
    ax,
    im,
    snapshot,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
):
    """Operando Y range submenu (limits/w/s/a/q). Former inline oy block."""
    while True:
        cur = ax.get_ylim(); print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("a: auto (restore original)"))
        print("  " + colorize_menu("q: back"))
        line = safe_input(colorize_prompt("Operando Y (w/s/a/q): ")).strip()
        if not line or line.lower() == 'q':
            break
        if line.lower() == 'w':
            # Upper only: change upper limit, fix lower - stay in loop
            while True:
                cur = ax.get_ylim()
                print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new upper Y limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_upper = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("operando-yrange")
                ax.set_ylim(cur[0], new_upper)
                fig.canvas.draw_idle()
                print(f"Operando Y range updated: {ax.get_ylim()[0]:.4g} {ax.get_ylim()[1]:.4g}")
        if line.lower() == 'w':
            continue
        if line.lower() == 's':
            # Lower only: change lower limit, fix upper - stay in loop
            while True:
                cur = ax.get_ylim()
                print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
                val = safe_input(colorize_inline_commands(f"Enter new lower Y limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_lower = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("operando-yrange")
                ax.set_ylim(new_lower, cur[1])
                fig.canvas.draw_idle()
                print(f"Operando Y range updated: {ax.get_ylim()[0]:.4g} {ax.get_ylim()[1]:.4g}")
        if line.lower() == 's':
            continue
        if line.lower() == 'a':
            # Auto: restore original range from image data
            try:
                data_array = np.asarray(im.get_array(), dtype=float)
                if data_array.size > 0:
                    # Get original extent from image
                    extent = im.get_extent()
                    if extent and len(extent) == 4:
                        orig_min = min(extent[2], extent[3])
                        orig_max = max(extent[2], extent[3])
                        snapshot("operando-yrange-auto")
                        ax.set_ylim(orig_min, orig_max)
                        fig.canvas.draw_idle()
                        print(f"Operando Y range restored to original: {ax.get_ylim()[0]:.4g} {ax.get_ylim()[1]:.4g}")
                    else:
                        print("No original data available.")
                else:
                    print("No original data available.")
            except Exception as e:
                print(f"Error restoring original Y range: {e}")
            continue
        try:
            lo, hi = map(float, line.split())
        except Exception as e:
            print(f"Invalid range: {e}")
            continue
        snapshot("operando-yrange")
        try:
            ax.set_ylim(lo, hi)
            fig.canvas.draw_idle()
        except Exception as e:
            print(f"Invalid range: {e}")
    print_menu()


def run_ec_ions_time_menu(
    *,
    fig,
    ec_ax,
    snapshot,
    print_menu,
    safe_input,
    colorize_inline_commands,
):
    """EC Y-axis ions/time submenu (n/t/q). Former inline ey block."""
    # Submenu: n = show number of ions, t = back to time
    if ec_ax is None:
        print("EC panel not available (no .mpt file in folder).")
        print_menu()
        return
    try:
        time_h = getattr(ec_ax, '_ec_time_h', None)
        voltage_v = getattr(ec_ax, '_ec_voltage_v', None)
        current_mA = getattr(ec_ax, '_ec_current_mA', None)
        ln = getattr(ec_ax, '_ec_line', None)
        if time_h is None or ln is None:
            print("EC data not available for ion calculation.")
            print_menu(); return
        if current_mA is None:
            print("Error: Current data is required for ion counting but is not available in the .mpt file.")
            print("The .mpt file must contain the '<I>/mA' column to use this feature.")
            print_menu(); return
        while True:
            sub = safe_input(colorize_inline_commands("ey submenu: n=ions, t=time, q=back: ")).strip().lower()
            if not sub:
                continue
            if sub == 'q':
                break
            if sub == 'n':
                params = getattr(ec_ax, '_ion_params', {"mass_mg": None, "cap_per_ion_mAh_g": None, "start_ions": None, "material": "cathode"})
                while True:
                    mass_mg = params.get('mass_mg')
                    cap_per_ion = params.get('cap_per_ion_mAh_g')
                    start_ions = params.get('start_ions')
                    material = params.get('material', 'cathode')
                    need_input = (mass_mg is None or cap_per_ion is None or start_ions is None)
                    if need_input:
                        prompt = colorize_inline_commands("Enter mass(mg), capacity-per-ion(mAh g^-1), start-ions (e.g. 4.5 26.8 0), q=back: ")
                    else:
                        prompt = colorize_inline_commands(f"Enter mass,cap-per-ion,start-ions (blank=reuse {mass_mg} {cap_per_ion} {start_ions}; q=back): ")
                    s = safe_input(prompt).strip()
                    if s.lower() == 'q':
                        break
                    if not s:
                        if need_input:
                            continue
                    else:
                        try:
                            vals = list(map(float, s.split()))
                            if len(vals) != 3:
                                raise ValueError()
                            mass_mg, cap_per_ion, start_ions = vals
                        except Exception:
                            print("Bad input. Expect three numbers: mass, capacity-per-ion, start-ions.")
                            continue
                        if material is None:
                            material = 'cathode'
                    if mass_mg is None or cap_per_ion is None or start_ions is None:
                        print("Bad input. Expect three numbers: mass, capacity-per-ion, start-ions.")
                        continue
                    # Snapshot before mutating ion params / overlays so ``b`` is clean.
                    snapshot("ey->ions")
                    ec_ax._ion_params = {
                        "mass_mg": mass_mg,
                        "cap_per_ion_mAh_g": cap_per_ion,
                        "start_ions": start_ions,
                        "material": material,
                    }
                    t = np.asarray(time_h, float)
                    i_mA = np.asarray(current_mA, float)
                    v = np.asarray(voltage_v, float)
                    # Cumulative trapezoidal integration for capacity (mAh)
                    dt = np.diff(t)
                    cap_increments = np.empty_like(t)
                    cap_increments[0] = 0.0
                    if t.size > 1:
                        cap_increments[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                    cap_mAh = np.cumsum(cap_increments)
                    mass_g = float(mass_mg) / 1000.0
                    with np.errstate(divide='ignore', invalid='ignore'):
                        cap_mAh_g = np.where(mass_g>0, cap_mAh / mass_g, np.nan)
                        ions_delta = np.where(cap_per_ion>0, cap_mAh_g / float(cap_per_ion), np.nan)
                    ions_abs = float(start_ions) + ions_delta
                    seg_bounds = charge_segment_bounds(i_mA)
                    # For cathode materials, ions should decrease during charge (voltage rising)
                    try:
                        if material and str(material).lower().startswith('cat') and len(seg_bounds) > 1:
                            a0 = seg_bounds[0]
                            b0 = seg_bounds[1]
                            if b0 > a0:
                                dv = float(v[b0]) - float(v[a0])
                                dt_seg = float(t[b0]) - float(t[a0])
                                if dt_seg > 0 and np.isfinite(dv):
                                    slope = dv / dt_seg  # dV/dt
                                    # Expected ions change sign for cathode: -sign(dV/dt)
                                    expected = -np.sign(slope) if slope != 0 else 0.0
                                    actual = np.sign(float(ions_abs[b0]) - float(ions_abs[a0]))
                                    if expected != 0 and actual != 0 and actual != expected:
                                        # Flip ions direction globally
                                        ions_abs = float(start_ions) - ions_delta
                                        setattr(ec_ax, '_ion_inverted', True)
                                        # Quietly invert without verbose console output
                                    else:
                                        setattr(ec_ax, '_ion_inverted', False)
                    except Exception:
                        pass
                    # Keep Y spine/ticks/title as time — only add ion count tags.
                    try:
                        setattr(ec_ax, '_ions_abs', np.asarray(ions_abs, float))
                    except Exception:
                        pass
                    try:
                        if getattr(ec_ax, '_ec_y_mode', 'time') != 'ions' and not hasattr(ec_ax, '_saved_time_ylim'):
                            ec_ax._saved_time_ylim = ec_ax.get_ylim()
                    except Exception:
                        pass
                    install_ec_ions_y_display(ec_ax, t, ions_abs)
                    place_ec_ion_segment_labels(
                        ec_ax, t, ions_abs, voltage=v, seg_bounds=seg_bounds,
                    )
                    ec_ax._ec_y_mode = 'ions'
            elif sub == 't':
                snapshot("ey->time")
                # Remove ion overlays; leave spine/ticks/limits untouched
                clear_ec_ion_overlays(ec_ax)
                try:
                    setattr(ec_ax, '_ions_abs', None)
                except Exception:
                    pass
                restore_ec_time_y_display(ec_ax)
                # Legacy sessions may have expanded xlim / renamed ylabel for ions
                prev_xlim = getattr(ec_ax, '_prev_ec_xlim', None)
                if prev_xlim and isinstance(prev_xlim, tuple) and len(prev_xlim) == 2:
                    try:
                        ec_ax.set_xlim(*prev_xlim)
                    except Exception:
                        pass
                try:
                    setattr(ec_ax, '_prev_ec_xlim', None)
                    setattr(ec_ax, '_ions_xlim_expanded', False)
                except Exception:
                    pass
                try:
                    ylab = (ec_ax.get_ylabel() or "").strip().lower()
                    if ylab in ("number of ions", "ions"):
                        label = 'Time (h)'
                        _cl = getattr(ec_ax, '_custom_labels', None) or {}
                        if 'y_time' in _cl and _cl['y_time'] is not None:
                            label = str(_cl['y_time'])
                        ec_ax.set_ylabel(label)
                except Exception:
                    pass
                ec_ax._ec_y_mode = 'time'
            # Draw after any submenu action
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
    except Exception as e:
        print(f"Error in ey submenu: {e}")
    print_menu()
