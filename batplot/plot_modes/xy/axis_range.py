"""Axis-range submenus (``x`` and ``y``) for the XY interactive menu.

These set/restore the displayed X and Y windows, with the X handler being
processed-data aware (re-expands from full/processed arrays). All data lists are
mutated in place; the dispatcher injects them plus the terminal callbacks.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, List

import numpy as np  # type: ignore[import]

from ...plotting import update_labels


def run_x_range_menu(
    *,
    args: Any,
    ax: Any,
    fig: Any,
    labels: List[str],
    label_text_objects: List[Any],
    x_data_list: List[Any],
    y_data_list: List[Any],
    orig_y: List[Any],
    offsets_list: List[float],
    x_full_list: List[Any],
    raw_y_full_list: List[Any],
    push_state: Callable[[str], Any],
    _safe_input: Callable[[str], str],
    _line: Callable[[int], Any],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
        while True:
            try:
                current_xlim = ax.get_xlim()
                print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + colorize_menu("w: upper only"))
                print("  " + colorize_menu("s: lower only"))
                print("  " + colorize_menu("a: auto (restore original)"))
                print("  " + colorize_menu("q: back"))
                rng = _safe_input(colorize_prompt("X (w/s/a/q): ")).strip()
                if not rng or rng.lower() == 'q':
                    break
                if rng.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        current_xlim = ax.get_xlim()
                        print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter upper limit (current lower: {current_xlim[0]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("xrange")
                        new_min = current_xlim[0]
                        new_max = new_upper
                        ax.set_xlim(new_min, new_max)
                        # Re-filter data from original processed data if available
                        data_is_processed = (hasattr(fig, '_original_x_data_list') or 
                                           hasattr(fig, '_smooth_settings') or 
                                           hasattr(fig, '_derivative_order') or
                                           hasattr(fig, '_pre_derivative_x_data_list'))
                        if data_is_processed and hasattr(fig, '_original_x_data_list'):
                            for i in range(len(labels)):
                                if i < len(fig._original_x_data_list):
                                    x_current = fig._original_x_data_list[i]
                                    y_current = fig._original_y_data_list[i]
                                    if i < len(offsets_list):
                                        y_current_no_offset = y_current - offsets_list[i]
                                    else:
                                        y_current_no_offset = y_current.copy()
                                    mask = (x_current >= new_min) & (x_current <= new_max)
                                    x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                                    y_sub = np.asarray(y_current_no_offset[mask], dtype=float).flatten()
                                    if x_sub.size == 0:
                                        _line(i).set_data([], [])
                                        x_data_list[i] = np.array([], dtype=float)
                                        y_data_list[i] = np.array([], dtype=float)
                                        if i < len(orig_y):
                                            orig_y[i] = np.array([], dtype=float)
                                        continue
                                    if i < len(offsets_list):
                                        y_sub = y_sub + offsets_list[i]
                                    _line(i).set_data(x_sub, y_sub)
                                    x_data_list[i] = np.asarray(x_sub, dtype=float).flatten()
                                    y_data_list[i] = np.asarray(y_sub, dtype=float).flatten()
                                    # Update orig_y with robust method
                                    while len(orig_y) <= i:
                                        orig_y.append(np.array([], dtype=float))
                                    try:
                                        y_no_offset = y_sub - offsets_list[i] if i < len(offsets_list) else y_sub
                                        y_no_offset_1d = np.array(y_no_offset, dtype=float).ravel()
                                        if i < len(orig_y):
                                            del orig_y[i]
                                        orig_y.insert(i, y_no_offset_1d)
                                    except Exception:
                                        pass
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
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
                        print(f"X range updated: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    continue
                if rng.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        current_xlim = ax.get_xlim()
                        print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter lower limit (current upper: {current_xlim[1]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("xrange")
                        new_min = new_lower
                        new_max = current_xlim[1]
                        ax.set_xlim(new_min, new_max)
                        # Re-filter data from original processed data if available
                        data_is_processed = (hasattr(fig, '_original_x_data_list') or 
                                           hasattr(fig, '_smooth_settings') or 
                                           hasattr(fig, '_derivative_order') or
                                           hasattr(fig, '_pre_derivative_x_data_list'))
                        if data_is_processed and hasattr(fig, '_original_x_data_list'):
                            for i in range(len(labels)):
                                if i < len(fig._original_x_data_list):
                                    x_current = fig._original_x_data_list[i]
                                    y_current = fig._original_y_data_list[i]
                                    if i < len(offsets_list):
                                        y_current_no_offset = y_current - offsets_list[i]
                                    else:
                                        y_current_no_offset = y_current.copy()
                                    mask = (x_current >= new_min) & (x_current <= new_max)
                                    x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                                    y_sub = np.asarray(y_current_no_offset[mask], dtype=float).flatten()
                                    if x_sub.size == 0:
                                        _line(i).set_data([], [])
                                        x_data_list[i] = np.array([], dtype=float)
                                        y_data_list[i] = np.array([], dtype=float)
                                        if i < len(orig_y):
                                            orig_y[i] = np.array([], dtype=float)
                                        continue
                                    if i < len(offsets_list):
                                        y_sub = y_sub + offsets_list[i]
                                    _line(i).set_data(x_sub, y_sub)
                                    x_data_list[i] = np.asarray(x_sub, dtype=float).flatten()
                                    y_data_list[i] = np.asarray(y_sub, dtype=float).flatten()
                                    # Update orig_y with robust method
                                    while len(orig_y) <= i:
                                        orig_y.append(np.array([], dtype=float))
                                    try:
                                        y_no_offset = y_sub - offsets_list[i] if i < len(offsets_list) else y_sub
                                        y_no_offset_1d = np.array(y_no_offset, dtype=float).ravel()
                                        if i < len(orig_y):
                                            del orig_y[i]
                                        orig_y.insert(i, y_no_offset_1d)
                                    except Exception:
                                        pass
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
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
                        print(f"X range updated: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    continue
                if rng.lower() == 'a':
                    # Auto: restore original range from CURRENT PROCESSED data (not original unprocessed)
                    push_state("xrange-auto")
                    try:
                        # Check if data has been processed
                        data_is_processed = (hasattr(fig, '_original_x_data_list') or 
                                           hasattr(fig, '_smooth_settings') or 
                                           hasattr(fig, '_derivative_order') or
                                           hasattr(fig, '_pre_derivative_x_data_list'))
                        if data_is_processed and x_data_list and all(xd.size > 0 for xd in x_data_list):
                            # Use CURRENT processed data to determine full range (preserves all processing)
                            print(f"DEBUG: Using current processed data for auto restore (has {len(x_data_list)} curves)")
                            new_min = min(xd.min() for xd in x_data_list if xd.size)
                            new_max = max(xd.max() for xd in x_data_list if xd.size)
                            print(f"DEBUG: Processed data range: {new_min:.6g} to {new_max:.6g}")
                        elif x_full_list:
                            print(f"DEBUG: Using original full data (no processing detected)")
                            new_min = min(xf.min() for xf in x_full_list if xf.size)
                            new_max = max(xf.max() for xf in x_full_list if xf.size)
                        else:
                            print("No original data available.")
                            continue
                        # Restore all data - use CURRENT PROCESSED data (preserves all processing steps)
                        for i in range(len(labels)):
                            if data_is_processed and hasattr(fig, '_full_processed_x_data_list') and i < len(fig._full_processed_x_data_list):
                                # Use FULL processed data (preserves all processing: reduce + smooth + derivative)
                                print(f"DEBUG: Auto restore curve {i+1}: Using full processed data ({len(fig._full_processed_x_data_list[i])} points)")
                                xf = np.asarray(fig._full_processed_x_data_list[i], dtype=float).flatten()
                                yf = np.asarray(fig._full_processed_y_data_list[i], dtype=float).flatten()
                                yf_raw = yf - (offsets_list[i] if i < len(offsets_list) else 0.0)
                            elif data_is_processed and i < len(x_data_list) and x_data_list[i].size > 0:
                                # Fallback: use current processed data
                                print(f"DEBUG: Auto restore curve {i+1}: Using current processed data ({len(x_data_list[i])} points)")
                                xf = np.asarray(x_data_list[i], dtype=float).flatten()
                                yf = np.asarray(y_data_list[i], dtype=float).flatten()
                                yf_raw = yf - (offsets_list[i] if i < len(offsets_list) else 0.0)
                            else:
                                # Use full original data (no processing)
                                print(f"DEBUG: Auto restore curve {i+1}: Using original full data")
                                xf = x_full_list[i] if i < len(x_full_list) else x_data_list[i]
                                yf_raw = raw_y_full_list[i] if i < len(raw_y_full_list) else (orig_y[i] if i < len(orig_y) else y_data_list[i])
                                xf = np.asarray(xf, dtype=float).flatten()
                                yf_raw = np.asarray(yf_raw, dtype=float).flatten()
                            mask = (xf >= new_min) & (xf <= new_max)
                            x_sub = np.asarray(xf[mask], dtype=float).flatten()
                            y_sub_raw = np.asarray(yf_raw[mask], dtype=float).flatten()
                            if x_sub.size == 0:
                                _line(i).set_data([], [])
                                x_data_list[i] = np.array([], dtype=float)
                                y_data_list[i] = np.array([], dtype=float)
                                if i < len(orig_y):
                                    orig_y[i] = np.array([], dtype=float)
                                continue
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
                            offset_val = offsets_list[i] if i < len(offsets_list) else 0.0
                            y_with_offset = y_sub_norm + offset_val
                            _line(i).set_data(x_sub, y_with_offset)
                            x_data_list[i] = np.asarray(x_sub, dtype=float).flatten()
                            y_data_list[i] = np.asarray(y_with_offset, dtype=float).flatten()
                            # Ensure orig_y list has enough elements
                            while len(orig_y) <= i:
                                orig_y.append(np.array([], dtype=float))
                            # Create a new 1D array - ensure it's a proper numpy array
                            # Handle all edge cases: scalar, 0-d array, multi-d array
                            try:
                                if isinstance(y_sub_norm, np.ndarray):
                                    if y_sub_norm.ndim == 0:
                                        y_sub_norm_1d = np.array([float(y_sub_norm)], dtype=float)
                                    else:
                                        y_sub_norm_1d = np.array(y_sub_norm.flatten(), dtype=float, copy=True)
                                else:
                                    # It's a scalar or list
                                    y_sub_norm_1d = np.array(y_sub_norm, dtype=float).flatten()
                                # Ensure it's 1D
                                if y_sub_norm_1d.ndim != 1:
                                    y_sub_norm_1d = y_sub_norm_1d.reshape(-1)
                                # Replace list element - delete old one first if needed
                                if i < len(orig_y):
                                    del orig_y[i]
                                orig_y.insert(i, y_sub_norm_1d)
                            except Exception as e:
                                # Fallback: just create a simple array
                                try:
                                    y_sub_norm_1d = np.array(y_sub_norm, dtype=float).ravel()
                                    if i < len(orig_y):
                                        orig_y[i] = y_sub_norm_1d
                                    else:
                                        orig_y.append(y_sub_norm_1d)
                                except Exception:
                                    # Last resort: skip orig_y update
                                    pass
                        ax.set_xlim(new_min, new_max)
                        ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
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
                        print(f"X range restored to original: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    except Exception as e:
                        print(f"Error during auto restore: {e}")
                        traceback.print_exc()
                    continue
                push_state("xrange")
                if rng.lower() == 'full':
                    # Use full data if available, otherwise use current processed data
                    if x_full_list and all(xf.size > 0 for xf in x_full_list):
                        new_min = min(xf.min() for xf in x_full_list if xf.size)
                        new_max = max(xf.max() for xf in x_full_list if xf.size)
                    else:
                        new_min = min(xd.min() for xd in x_data_list if xd.size)
                        new_max = max(xd.max() for xd in x_data_list if xd.size)
                else:
                    new_min, new_max = map(float, rng.split())
                ax.set_xlim(new_min, new_max)
                # Check if data has been processed (smooth/derivative/reduce)
                data_is_processed = (hasattr(fig, '_original_x_data_list') or 
                                   hasattr(fig, '_smooth_settings') or 
                                   hasattr(fig, '_derivative_order') or
                                   hasattr(fig, '_pre_derivative_x_data_list'))
    
                for i in range(len(labels)):
                    if data_is_processed and i < len(x_data_list) and x_data_list[i].size > 0:
                        # Use full processed data if available (allows expansion), otherwise use current filtered data
                        curr_x = np.asarray(x_data_list[i], dtype=float)
                        curr_min = curr_x.min() if curr_x.size > 0 else float('inf')
                        curr_max = curr_x.max() if curr_x.size > 0 else float('-inf')
    
                        # Check if we need full processed data (for expansion beyond current filter)
                        need_full = (new_min < curr_min or new_max > curr_max)
    
                        if need_full and hasattr(fig, '_full_processed_x_data_list') and i < len(fig._full_processed_x_data_list):
                            # Use full processed data to allow expansion
                            full_x = np.asarray(fig._full_processed_x_data_list[i], dtype=float)
                            if full_x.size > 0:
                                full_min = full_x.min()
                                full_max = full_x.max()
                                print(f"DEBUG: Curve {i+1}: Expanding range ({curr_min:.6g}-{curr_max:.6g} -> {new_min:.6g}-{new_max:.6g}), using full processed data (range {full_min:.6g} to {full_max:.6g})")
                                x_current = full_x
                                y_current = np.asarray(fig._full_processed_y_data_list[i], dtype=float)
                            else:
                                print(f"DEBUG: Curve {i+1}: Full processed data empty, using current data")
                                x_current = curr_x
                                y_current = np.asarray(y_data_list[i], dtype=float)
                        else:
                            print(f"DEBUG: Curve {i+1}: Using current processed data (range {curr_min:.6g} to {curr_max:.6g}, requested {new_min:.6g} to {new_max:.6g})")
                            x_current = curr_x
                            y_current = np.asarray(y_data_list[i], dtype=float)
                        # Remove offset for filtering
                        if i < len(offsets_list):
                            y_current_no_offset = y_current - offsets_list[i]
                        else:
                            y_current_no_offset = y_current.copy()
                        mask = (x_current >= new_min) & (x_current <= new_max)
                        x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                        y_sub = np.asarray(y_current_no_offset[mask], dtype=float).flatten()
                        if x_sub.size == 0:
                            _line(i).set_data([], [])
                            x_data_list[i] = np.array([], dtype=float)
                            y_data_list[i] = np.array([], dtype=float)
                            if i < len(orig_y):
                                orig_y[i] = np.array([], dtype=float)
                            continue
                        # Restore offset
                        if i < len(offsets_list):
                            y_sub = y_sub + offsets_list[i]
                        _line(i).set_data(x_sub, y_sub)
                        x_data_list[i] = np.asarray(x_sub, dtype=float).flatten()
                        y_data_list[i] = np.asarray(y_sub, dtype=float).flatten()
                        # Update orig_y
                        # Update orig_y with robust method
                        while len(orig_y) <= i:
                            orig_y.append(np.array([], dtype=float))
                        try:
                            y_no_offset = y_sub - offsets_list[i] if i < len(offsets_list) else y_sub
                            y_no_offset_1d = np.array(y_no_offset, dtype=float).ravel()
                            if i < len(orig_y):
                                del orig_y[i]
                            orig_y.insert(i, y_no_offset_1d)
                        except Exception:
                            pass
                    elif data_is_processed and i < len(x_data_list) and x_data_list[i].size > 0:
                        # Fallback: use current data if _original_x_data_list not available
                        x_current = np.asarray(x_data_list[i], dtype=float)
                        y_current = np.asarray(y_data_list[i], dtype=float)
                        mask = (x_current >= new_min) & (x_current <= new_max)
                        x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                        y_sub = np.asarray(y_current[mask], dtype=float).flatten()
                        if x_sub.size == 0:
                            _line(i).set_data([], [])
                            x_data_list[i] = np.array([], dtype=float)
                            y_data_list[i] = np.array([], dtype=float)
                            if i < len(orig_y):
                                orig_y[i] = np.array([], dtype=float)
                            continue
                        _line(i).set_data(x_sub, y_sub)
                        x_data_list[i] = np.asarray(x_sub, dtype=float).flatten()
                        y_data_list[i] = np.asarray(y_sub, dtype=float).flatten()
                        # Update orig_y - use same robust method as in 'a' branch
                        while len(orig_y) <= i:
                            orig_y.append(np.array([], dtype=float))
                        try:
                            y_no_offset = y_sub - offsets_list[i] if i < len(offsets_list) else y_sub
                            if isinstance(y_no_offset, np.ndarray):
                                if y_no_offset.ndim == 0:
                                    y_no_offset_1d = np.array([float(y_no_offset)], dtype=float)
                                else:
                                    y_no_offset_1d = np.array(y_no_offset.flatten(), dtype=float, copy=True)
                            else:
                                y_no_offset_1d = np.array(y_no_offset, dtype=float).flatten()
                            if y_no_offset_1d.ndim != 1:
                                y_no_offset_1d = y_no_offset_1d.reshape(-1)
                            if i < len(orig_y):
                                del orig_y[i]
                            orig_y.insert(i, y_no_offset_1d)
                        except Exception:
                            try:
                                y_no_offset = y_sub - offsets_list[i] if i < len(offsets_list) else y_sub
                                y_no_offset_1d = np.array(y_no_offset, dtype=float).ravel()
                                if i < len(orig_y):
                                    orig_y[i] = y_no_offset_1d
                                else:
                                    orig_y.append(y_no_offset_1d)
                            except Exception:
                                pass
                    else:
                        # Use original full data as source
                        xf = x_full_list[i] if i < len(x_full_list) else x_data_list[i]
                        yf_raw = raw_y_full_list[i] if i < len(raw_y_full_list) else (orig_y[i] if i < len(orig_y) else y_data_list[i])
                        mask = (xf >= new_min) & (xf <= new_max)
                        x_sub = np.array(xf[mask], copy=True)
                        y_sub_raw = np.array(yf_raw[mask], copy=True)
                        if x_sub.size == 0:
                            _line(i).set_data([], [])
                            x_data_list[i] = np.array([])
                            y_data_list[i] = np.array([])
                            if i < len(orig_y):
                                orig_y[i] = np.array([])
                            continue
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
                        offset_val = offsets_list[i] if i < len(offsets_list) else 0.0
                        y_with_offset = y_sub_norm + offset_val
                        _line(i).set_data(x_sub, y_with_offset)
                        x_data_list[i] = x_sub
                        y_data_list[i] = y_with_offset
                        if i < len(orig_y):
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


def run_y_range_menu(
    *,
    args: Any,
    ax: Any,
    fig: Any,
    label_text_objects: List[Any],
    y_data_list: List[Any],
    push_state: Callable[[str], Any],
    _safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
        while True:
            try:
                current_ylim = ax.get_ylim()
                print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + colorize_menu("w: upper only"))
                print("  " + colorize_menu("s: lower only"))
                print("  " + colorize_menu("a: auto (restore original)"))
                print("  " + colorize_menu("q: back"))
                rng = _safe_input(colorize_prompt("Y (w/s/a/q): ")).strip().lower()
                if not rng or rng == 'q':
                    break
                if rng == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        current_ylim = ax.get_ylim()
                        print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter upper limit (current lower: {current_ylim[0]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("yrange")
                        ax.set_ylim(current_ylim[0], new_upper)
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw_idle()
                        print(f"Y range updated: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                if rng == 'w':
                    continue
                if rng == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        current_ylim = ax.get_ylim()
                        print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter lower limit (current upper: {current_ylim[1]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("yrange")
                        ax.set_ylim(new_lower, current_ylim[1])
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw_idle()
                        print(f"Y range updated: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                if rng == 's':
                    continue
                if rng == 'a':
                    # Auto: restore original range from y_data_list
                    push_state("yrange-auto")
                    if y_data_list:
                        all_min = None
                        all_max = None
                        for arr in y_data_list:
                            if arr.size:
                                mn = float(arr.min())
                                mx = float(arr.max())
                                all_min = mn if all_min is None else min(all_min, mn)
                                all_max = mx if all_max is None else max(all_max, mx)
                        if all_min is None or all_max is None:
                            print("No original data available.")
                            continue
                        ax.set_ylim(all_min, all_max)
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw_idle()
                        print(f"Y range restored to original: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                    else:
                        print("No original data available.")
                    continue
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
                ymin, ymax = ax.get_ylim()
                print(f"Y range set to ({float(ymin)}, {float(ymax)})")
            except Exception as e:
                print(f"Error setting Y-axis range: {e}")


__all__ = ["run_x_range_menu", "run_y_range_menu"]
