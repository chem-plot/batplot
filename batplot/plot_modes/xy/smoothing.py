"""Smoothing and data-reduction submenu (``sm``) for the XY interactive menu.

Owns the row-reduction (delete/skip, delete-missing, merge) and smoothing
(adjacent-average, Savitzky-Golay, FFT) workflows. The dispatcher injects the
mutable data lists and the data-lifecycle callbacks (ensure-original, reset,
apply, full-processed) so undo and X-range filtering keep working exactly as
before. The numeric kernels live in ``data_ops`` and ``common.smoothing`` so a
fix there benefits every caller.
"""

from __future__ import annotations

from typing import Any, Callable, List, Sequence

import numpy as np  # type: ignore[import]

from ..common.smoothing import savgol_smooth as _savgol_smooth
from .data_ops import _adjacent_average_smooth, _fft_smooth


def run_smoothing_menu(
    *,
    fig: Any,
    x_data_list: List[Any],
    y_data_list: List[Any],
    offsets_list: Sequence[float],
    ensure_original_data: Callable[[], Any],
    reset_to_original: Callable[[], Any],
    apply_data_changes: Callable[[], Any],
    update_full_processed_data: Callable[[], Any],
    get_last_reduce_rows_settings: Callable[[str], dict],
    save_last_reduce_rows_settings: Callable[[str, dict], Any],
    get_last_smooth_settings_from_config: Callable[[], dict],
    save_last_smooth_settings_to_config: Callable[[dict], Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Run the smoothing / data-reduction submenu."""
    # Bind injected callbacks to the original local names so the body below is
    # an exact copy of the dispatcher logic (no behavioral change).
    _ensure_original_data = ensure_original_data
    _reset_to_original = reset_to_original
    _apply_data_changes = apply_data_changes
    _update_full_processed_data = update_full_processed_data
    _get_last_reduce_rows_settings = get_last_reduce_rows_settings
    _save_last_reduce_rows_settings = save_last_reduce_rows_settings
    _get_last_smooth_settings_from_config = get_last_smooth_settings_from_config
    _save_last_smooth_settings_to_config = save_last_smooth_settings_to_config
    _safe_input = safe_input

    # Smoothing and data reduction menu
    _ensure_original_data()
    while True:
        print("\n\033[1mSmoothing and Data Reduction\033[0m")
        print("Commands:")
        print("  " + colorize_menu("r: reduce rows (delete/merge rows based on pattern)"))
        print("  " + colorize_menu("s: smooth data (various smoothing methods)"))
        print("  " + colorize_menu("reset: reset all curves to original data"))
        print("  " + colorize_menu("q: back to main menu"))
        sub = _safe_input(colorize_prompt("sm> ")).strip().lower()
        if not sub:
            continue
        if sub == 'q':
            break
        if sub == 'reset':
            push_state("smooth-reset")
            success, reset_count, total_points = _reset_to_original()
            if success:
                print(f"Reset {reset_count} curve(s) to original data ({total_points} total points restored).")
                _apply_data_changes()
            else:
                print("No processed data to reset.")
            continue
        if sub == 'r':
            # Reduce rows submenu
            while True:
                print("\n\033[1mReduce Rows\033[0m")
                print("Methods:")
                print("  " + colorize_menu("1: Delete N rows, then skip M rows"))
                print("  " + colorize_menu("2: Delete rows with missing values"))
                print("  " + colorize_menu("3: Reduce N rows with merged values (average/sum/min/max)"))
                print("  " + colorize_menu("q: back to smooth menu"))
                method = _safe_input(colorize_prompt("sm>r> ")).strip().lower()
                if not method or method == 'q':
                    break
                if method == '1':
                    # Delete N rows, then skip M rows
                    try:
                        # Check for last settings
                        last_settings = _get_last_reduce_rows_settings('delete_skip')
                        last_n = last_settings.get('n')
                        last_m = last_settings.get('m')
                        last_start_row = last_settings.get('start_row')
                                
                        if last_n is not None and last_m is not None and last_start_row is not None:
                            use_last = _safe_input(f"Use last settings? (N={last_n}, M={last_m}, start_row={last_start_row+1}, y/n or enter N): ").strip().lower()
                            # Check if user entered a number directly (skip "use last settings")
                            if use_last and use_last.replace('-', '').replace('.', '').isdigit():
                                n = int(float(use_last))
                                if n < 1:
                                    print("N must be >= 1.")
                                    continue
                                m_in = _safe_input(f"Enter M (rows to skip, default {last_m}): ").strip()
                                m = int(m_in) if m_in else last_m
                                if m < 0:
                                    print("M must be >= 0.")
                                    continue
                                start_in = _safe_input(f"Starting row (1-based, default {last_start_row+1}): ").strip()
                                start_row = int(start_in) - 1 if start_in else last_start_row
                            elif use_last != 'n':
                                n = last_n
                                m = last_m
                                start_row = last_start_row  # Already 0-based in config
                            else:
                                n_in = _safe_input(f"Enter N (rows to delete, default {last_n}): ").strip()
                                n = int(n_in) if n_in else last_n
                                if n < 1:
                                    print("N must be >= 1.")
                                    continue
                                m_in = _safe_input(f"Enter M (rows to skip, default {last_m}): ").strip()
                                m = int(m_in) if m_in else last_m
                                if m < 0:
                                    print("M must be >= 0.")
                                    continue
                                start_in = _safe_input(f"Starting row (1-based, default {last_start_row+1}): ").strip()
                                start_row = int(start_in) - 1 if start_in else last_start_row
                        else:
                            n_in = _safe_input("Enter N (rows to delete, default 1): ").strip()
                            n = int(n_in) if n_in else 1
                            if n < 1:
                                print("N must be >= 1.")
                                continue
                            m_in = _safe_input("Enter M (rows to skip, default 0): ").strip()
                            m = int(m_in) if m_in else 0
                            if m < 0:
                                print("M must be >= 0.")
                                continue
                            start_in = _safe_input("Starting row (1-based, default 1): ").strip()
                            start_row = int(start_in) - 1 if start_in else 0
                                
                        if start_row < 0:
                            start_row = 0
                        push_state("reduce-rows-delete-skip")
                        _ensure_original_data()
                        processed = 0
                        total_before = 0
                        total_after = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed), not original
                                orig_x = x_data_list[i].copy()
                                orig_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    orig_y = orig_y - offsets_list[i]
                                if start_row >= len(orig_x):
                                    continue
                                before = len(orig_x)
                                # Create mask: delete n rows, then skip m rows, repeat
                                mask = np.ones(len(orig_x), dtype=bool)
                                idx = start_row
                                while idx < len(orig_x):
                                    # Delete n rows
                                    end_del = min(idx + n, len(orig_x))
                                    mask[idx:end_del] = False
                                    idx = end_del
                                    # Skip m rows
                                    idx = min(idx + m, len(orig_x))
                                new_x = orig_x[mask]
                                new_y = orig_y[mask]
                                after = len(new_x)
                                if len(new_x) > 0:
                                    # Restore offset
                                    if i < len(offsets_list):
                                        new_y = new_y + offsets_list[i]
                                    x_data_list[i] = new_x
                                    y_data_list[i] = new_y
                                    processed += 1
                                    total_before += before
                                    total_after += after
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            print(f"Processed {processed} curve(s); removed {removed} of {total_before} points ({pct:.1f}%).")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                            _apply_data_changes()
                            # Save settings for next time
                            _save_last_reduce_rows_settings('delete_skip', {
                                'n': n,
                                'm': m,
                                'start_row': start_row  # Save as 0-based
                            })
                        else:
                            print("No curves were processed.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                if method == '2':
                    # Delete rows with missing values
                    try:
                        # Check for last settings
                        last_settings = _get_last_reduce_rows_settings('delete_missing')
                        last_delete_entire_row = last_settings.get('delete_entire_row')
                                
                        if last_delete_entire_row is not None:
                            default_str = "y" if last_delete_entire_row else "n"
                            use_last = _safe_input(f"Use last settings? (delete_entire_row={'y' if last_delete_entire_row else 'n'}, y/n or enter y/n): ").strip().lower()
                            # Check if user entered y/n directly (skip "use last settings")
                            if use_last in ('y', 'n', 'yes', 'no'):
                                delete_entire_row = use_last in ('y', 'yes')
                            elif use_last != 'n':
                                delete_entire_row = last_delete_entire_row
                            else:
                                delete_entire_row_in = _safe_input(f"Delete entire row? (y/n, default {default_str}): ").strip().lower()
                                delete_entire_row = delete_entire_row_in != 'n'
                        else:
                            delete_entire_row_in = _safe_input("Delete entire row? (y/n, default y): ").strip().lower()
                            delete_entire_row = delete_entire_row_in != 'n'
                        push_state("reduce-rows-delete-missing")
                        _ensure_original_data()
                        processed = 0
                        total_before = 0
                        total_after = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed), not original
                                orig_x = x_data_list[i].copy()
                                orig_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    orig_y = orig_y - offsets_list[i]
                                before = len(orig_x)
                                # Check for missing values (NaN or inf)
                                if delete_entire_row:
                                    mask = np.isfinite(orig_x) & np.isfinite(orig_y)
                                else:
                                    # Only delete missing in current column
                                    mask = np.isfinite(orig_y)
                                new_x = orig_x[mask]
                                new_y = orig_y[mask]
                                after = len(new_x)
                                if len(new_x) > 0:
                                    # Restore offset
                                    if i < len(offsets_list):
                                        new_y = new_y + offsets_list[i]
                                    x_data_list[i] = new_x
                                    y_data_list[i] = new_y
                                    processed += 1
                                    total_before += before
                                    total_after += after
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            print(f"Processed {processed} curve(s); removed {removed} of {total_before} points ({pct:.1f}%).")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                            _apply_data_changes()
                            # Save settings for next time
                            _save_last_reduce_rows_settings('delete_missing', {
                                'delete_entire_row': delete_entire_row
                            })
                        else:
                            print("No curves were processed.")
                    except Exception:
                        print("Error processing data.")
                    continue
                if method == '3':
                    # Reduce N rows with merged values
                    try:
                        # Check for last settings
                        last_settings = _get_last_reduce_rows_settings('merge')
                        last_n = last_settings.get('n')
                        last_merge_by = last_settings.get('merge_by')
                        last_start_row = last_settings.get('start_row')
                                
                        if last_n is not None and last_merge_by is not None and last_start_row is not None:
                            merge_names = {
                                '1': 'First point',
                                '2': 'Last point',
                                '3': 'Average',
                                '4': 'Min',
                                '5': 'Max',
                                '6': 'Sum'
                            }
                            merge_name = merge_names.get(last_merge_by, 'Average')
                            use_last = _safe_input(f"Use last settings? (N={last_n}, merge_by={merge_name}, start_row={last_start_row+1}, y/n or enter N): ").strip().lower()
                            # Check if user entered a number directly (skip "use last settings")
                            if use_last and use_last.replace('-', '').replace('.', '').isdigit():
                                n = int(float(use_last))
                                if n < 2:
                                    print("N must be >= 2.")
                                    continue
                                print("Merge by:")
                                print("  " + colorize_menu("1: First point"))
                                print("  " + colorize_menu("2: Last point"))
                                print("  " + colorize_menu("3: Average"))
                                print("  " + colorize_menu("4: Min"))
                                print("  " + colorize_menu("5: Max"))
                                print("  " + colorize_menu("6: Sum"))
                                merge_by_in = _safe_input(f"Choose (1-6, default {last_merge_by}): ").strip()
                                merge_by = merge_by_in if merge_by_in else last_merge_by
                                start_in = _safe_input(f"Starting row (1-based, default {last_start_row+1}): ").strip()
                                start_row = int(start_in) - 1 if start_in else last_start_row
                            elif use_last != 'n':
                                n = last_n
                                merge_by = last_merge_by
                                start_row = last_start_row  # Already 0-based in config
                            else:
                                n_in = _safe_input(f"Enter N (rows to merge, default {last_n}): ").strip()
                                n = int(n_in) if n_in else last_n
                                if n < 2:
                                    print("N must be >= 2.")
                                    continue
                                print("Merge by:")
                                print("  " + colorize_menu("1: First point"))
                                print("  " + colorize_menu("2: Last point"))
                                print("  " + colorize_menu("3: Average"))
                                print("  " + colorize_menu("4: Min"))
                                print("  " + colorize_menu("5: Max"))
                                print("  " + colorize_menu("6: Sum"))
                                merge_by_in = _safe_input(f"Choose (1-6, default {last_merge_by}): ").strip()
                                merge_by = merge_by_in if merge_by_in else last_merge_by
                                start_in = _safe_input(f"Starting row (1-based, default {last_start_row+1}): ").strip()
                                start_row = int(start_in) - 1 if start_in else last_start_row
                        else:
                            n_in = _safe_input("Enter N (rows to merge, default 2): ").strip()
                            n = int(n_in) if n_in else 2
                            if n < 2:
                                print("N must be >= 2.")
                                continue
                            print("Merge by:")
                            print("  " + colorize_menu("1: First point"))
                            print("  " + colorize_menu("2: Last point"))
                            print("  " + colorize_menu("3: Average"))
                            print("  " + colorize_menu("4: Min"))
                            print("  " + colorize_menu("5: Max"))
                            print("  " + colorize_menu("6: Sum"))
                            merge_by_in = _safe_input("Choose (1-6, default 3): ").strip()
                            merge_by = merge_by_in if merge_by_in else '3'
                            start_in = _safe_input("Starting row (1-based, default 1): ").strip()
                            start_row = int(start_in) - 1 if start_in else 0
                                
                        if start_row < 0:
                            start_row = 0
                                
                        merge_funcs = {
                            '1': lambda arr: arr[0] if len(arr) > 0 else np.nan,
                            '2': lambda arr: arr[-1] if len(arr) > 0 else np.nan,
                            '3': np.nanmean,
                            '4': np.nanmin,
                            '5': np.nanmax,
                            '6': np.nansum,
                        }
                        merge_func = merge_funcs.get(merge_by, np.nanmean)
                        push_state("reduce-rows-merge")
                        _ensure_original_data()
                        processed = 0
                        total_before = 0
                        total_after = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed), not original
                                orig_x = x_data_list[i].copy()
                                orig_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    orig_y = orig_y - offsets_list[i]
                                if start_row >= len(orig_x):
                                    continue
                                before = len(orig_x)
                                # Group into chunks of N
                                new_x_list = []
                                new_y_list = []
                                idx = 0
                                while idx < start_row:
                                    new_x_list.append(orig_x[idx])
                                    new_y_list.append(orig_y[idx])
                                    idx += 1
                                while idx < len(orig_x):
                                    end_idx = min(idx + n, len(orig_x))
                                    chunk_x = orig_x[idx:end_idx]
                                    chunk_y = orig_y[idx:end_idx]
                                    # Merge: use first x, merge y based on method
                                    new_x = chunk_x[0] if len(chunk_x) > 0 else np.nan
                                    new_y = merge_func(chunk_y) if len(chunk_y) > 0 else np.nan
                                    if np.isfinite(new_x) and np.isfinite(new_y):
                                        new_x_list.append(new_x)
                                        new_y_list.append(new_y)
                                    idx = end_idx
                                if len(new_x_list) > 0:
                                    new_x = np.array(new_x_list)
                                    new_y = np.array(new_y_list)
                                    after = len(new_x)
                                    # Restore offset
                                    if i < len(offsets_list):
                                        new_y = new_y + offsets_list[i]
                                    x_data_list[i] = new_x
                                    y_data_list[i] = new_y
                                    processed += 1
                                    total_before += before
                                    total_after += after
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            print(f"Processed {processed} curve(s); reduced {total_before} to {total_after} points (removed {removed}, {pct:.1f}%).")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                            _apply_data_changes()
                            # Save settings for next time
                            _save_last_reduce_rows_settings('merge', {
                                'n': n,
                                'merge_by': merge_by,
                                'start_row': start_row  # Save as 0-based
                            })
                        else:
                            print("No curves were processed.")
                    except (ValueError, KeyError):
                        print("Invalid input.")
                    continue
        if sub == 's':
            # Smooth submenu
            while True:
                print("\n\033[1mSmooth Data\033[0m")
                print("Methods:")
                print("  " + colorize_menu("1: Adjacent-Averaging (moving average)"))
                print("  " + colorize_menu("2: Savitzky-Golay (polynomial smoothing)"))
                print("  " + colorize_menu("3: FFT Filter (low-pass frequency filter)"))
                print("  " + colorize_menu("q: back to smooth menu"))
                method = _safe_input(colorize_prompt("sm>s> ")).strip().lower()
                if not method or method == 'q':
                    break
                if method == '1':
                    # Adjacent-Averaging
                    try:
                        # Check for last settings (from config file for persistence)
                        config_settings = _get_last_smooth_settings_from_config()
                        session_settings = getattr(fig, '_last_smooth_settings', {})
                        # Prefer config settings (persistent) over session settings
                        last_settings = config_settings if config_settings.get('method') == 'adjacent_average' else session_settings
                        last_method = last_settings.get('method')
                        last_points = last_settings.get('points')
                                
                        if last_method == 'adjacent_average' and last_points is not None:
                            use_last = _safe_input(f"Use last settings? (points={last_points}, y/n or enter points): ").strip().lower()
                            # Check if user entered a number directly (skip "use last settings")
                            if use_last and use_last.replace('-', '').replace('.', '').isdigit():
                                points = int(float(use_last))
                            elif use_last != 'n':
                                points = last_points
                            else:
                                points_in = _safe_input(f"Number of points (default {last_points}): ").strip()
                                points = int(points_in) if points_in else last_points
                        else:
                            points_in = _safe_input("Number of points (default 5): ").strip()
                            points = int(points_in) if points_in else 5
                                
                        if points < 2:
                            print("Points must be >= 2.")
                            continue
                        push_state("smooth-adjacent-average")
                        _ensure_original_data()
                        processed = 0
                        total_points = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed), not original
                                orig_x = x_data_list[i].copy()
                                orig_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    orig_y = orig_y - offsets_list[i]
                                n_points = len(orig_y)
                                # Apply smoothing
                                smoothed_y = _adjacent_average_smooth(orig_y, points)
                                if len(smoothed_y) > 0:
                                    # Restore offset
                                    if i < len(offsets_list):
                                        smoothed_y = smoothed_y + offsets_list[i]
                                    # Keep original x, update y
                                    x_data_list[i] = orig_x.copy()
                                    y_data_list[i] = smoothed_y
                                    processed += 1
                                    total_points += n_points
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            print(f"Smoothed {processed} curve(s) with {total_points} total points using Adjacent-Averaging (window={points}).")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                            _apply_data_changes()
                            # Store settings (both current and last)
                            if not hasattr(fig, '_smooth_settings'):
                                fig._smooth_settings = {}
                            fig._smooth_settings['method'] = 'adjacent_average'
                            fig._smooth_settings['points'] = points
                            # Store as last settings for next time (both in-memory and config file)
                            if not hasattr(fig, '_last_smooth_settings'):
                                fig._last_smooth_settings = {}
                            fig._last_smooth_settings['method'] = 'adjacent_average'
                            fig._last_smooth_settings['points'] = points
                            # Save to config file for persistence across sessions
                            _save_last_smooth_settings_to_config({
                                'method': 'adjacent_average',
                                'points': points
                            })
                        else:
                            print("No curves were smoothed.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                if method == '2':
                    # Savitzky-Golay
                    try:
                        # Check for last settings (from config file for persistence)
                        config_settings = _get_last_smooth_settings_from_config()
                        session_settings = getattr(fig, '_last_smooth_settings', {})
                        # Prefer config settings (persistent) over session settings
                        last_settings = config_settings if config_settings.get('method') == 'savgol' else session_settings
                        last_method = last_settings.get('method')
                        last_window = last_settings.get('window')
                        last_poly = last_settings.get('poly')
                                
                        if last_method == 'savgol' and last_window is not None and last_poly is not None:
                            use_last = _safe_input(f"Use last settings? (window={last_window}, poly={last_poly}, y/n or enter window): ").strip().lower()
                            # Check if user entered a number directly (skip "use last settings")
                            if use_last and use_last.replace('-', '').replace('.', '').isdigit():
                                window = int(float(use_last))
                                if window < 3:
                                    window = 3
                                if window % 2 == 0:
                                    window += 1
                                poly_in = _safe_input(f"Polynomial order (default {last_poly}): ").strip()
                                poly = int(poly_in) if poly_in else last_poly
                            elif use_last != 'n':
                                window = last_window
                                poly = last_poly
                            else:
                                window_in = _safe_input(f"Window size (odd >= 3, default {last_window}): ").strip()
                                window = int(window_in) if window_in else last_window
                                if window < 3:
                                    window = 3
                                if window % 2 == 0:
                                    window += 1
                                poly_in = _safe_input(f"Polynomial order (default {last_poly}): ").strip()
                                poly = int(poly_in) if poly_in else last_poly
                        else:
                            window_in = _safe_input("Window size (odd >= 3, default 9): ").strip()
                            window = int(window_in) if window_in else 9
                            if window < 3:
                                window = 3
                            if window % 2 == 0:
                                window += 1
                            poly_in = _safe_input("Polynomial order (default 3): ").strip()
                            poly = int(poly_in) if poly_in else 3
                                
                        if poly < 1:
                            poly = 1
                        if poly >= window:
                            poly = window - 1
                        push_state("smooth-savgol")
                        _ensure_original_data()
                        processed = 0
                        total_points = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed), not original
                                orig_x = x_data_list[i].copy()
                                orig_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    orig_y = orig_y - offsets_list[i]
                                n_points = len(orig_y)
                                # Apply smoothing
                                smoothed_y = _savgol_smooth(orig_y, window, poly)
                                if len(smoothed_y) > 0:
                                    # Restore offset
                                    if i < len(offsets_list):
                                        smoothed_y = smoothed_y + offsets_list[i]
                                    # Keep original x, update y
                                    x_data_list[i] = orig_x.copy()
                                    y_data_list[i] = smoothed_y
                                    processed += 1
                                    total_points += n_points
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            print(f"Smoothed {processed} curve(s) with {total_points} total points using Savitzky-Golay (window={window}, poly={poly}).")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                            _apply_data_changes()
                            # Store settings (both current and last)
                            if not hasattr(fig, '_smooth_settings'):
                                fig._smooth_settings = {}
                            fig._smooth_settings['method'] = 'savgol'
                            fig._smooth_settings['window'] = window
                            fig._smooth_settings['poly'] = poly
                            # Store as last settings for next time (both in-memory and config file)
                            if not hasattr(fig, '_last_smooth_settings'):
                                fig._last_smooth_settings = {}
                            fig._last_smooth_settings['method'] = 'savgol'
                            fig._last_smooth_settings['window'] = window
                            fig._last_smooth_settings['poly'] = poly
                            # Save to config file for persistence across sessions
                            _save_last_smooth_settings_to_config({
                                'method': 'savgol',
                                'window': window,
                                'poly': poly
                            })
                        else:
                            print("No curves were smoothed.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                if method == '3':
                    # FFT Filter
                    try:
                        # Check for last settings (from config file for persistence)
                        config_settings = _get_last_smooth_settings_from_config()
                        session_settings = getattr(fig, '_last_smooth_settings', {})
                        # Prefer config settings (persistent) over session settings
                        last_settings = config_settings if config_settings.get('method') == 'fft' else session_settings
                        last_method = last_settings.get('method')
                        last_points = last_settings.get('points')
                        last_cutoff = last_settings.get('cutoff')
                                
                        if last_method == 'fft' and last_points is not None and last_cutoff is not None:
                            use_last = _safe_input(f"Use last settings? (points={last_points}, cutoff={last_cutoff:.3f}, y/n or enter points): ").strip().lower()
                            # Check if user entered a number directly (skip "use last settings")
                            if use_last and use_last.replace('-', '').replace('.', '').isdigit():
                                points = int(float(use_last))
                                if points < 2:
                                    points = 2
                                cutoff_in = _safe_input(f"Cutoff frequency (0-1, default {last_cutoff:.3f}): ").strip()
                                cutoff = float(cutoff_in) if cutoff_in else last_cutoff
                            elif use_last != 'n':
                                points = last_points
                                cutoff = last_cutoff
                            else:
                                points_in = _safe_input(f"Points for FFT (default {last_points}): ").strip()
                                points = int(points_in) if points_in else last_points
                                if points < 2:
                                    points = 2
                                cutoff_in = _safe_input(f"Cutoff frequency (0-1, default {last_cutoff:.3f}): ").strip()
                                cutoff = float(cutoff_in) if cutoff_in else last_cutoff
                        else:
                            points_in = _safe_input("Points for FFT (default 5): ").strip()
                            points = int(points_in) if points_in else 5
                            if points < 2:
                                points = 2
                            cutoff_in = _safe_input("Cutoff frequency (0-1, default 0.1): ").strip()
                            cutoff = float(cutoff_in) if cutoff_in else 0.1
                                
                        if cutoff < 0:
                            cutoff = 0
                        if cutoff > 1:
                            cutoff = 1
                        push_state("smooth-fft")
                        _ensure_original_data()
                        processed = 0
                        total_points = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed), not original
                                orig_x = x_data_list[i].copy()
                                orig_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    orig_y = orig_y - offsets_list[i]
                                n_points = len(orig_y)
                                # Apply smoothing
                                smoothed_y = _fft_smooth(orig_y, points, cutoff)
                                if len(smoothed_y) > 0:
                                    # Restore offset
                                    if i < len(offsets_list):
                                        smoothed_y = smoothed_y + offsets_list[i]
                                    # Keep original x, update y
                                    x_data_list[i] = orig_x.copy()
                                    y_data_list[i] = smoothed_y
                                    processed += 1
                                    total_points += n_points
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            print(f"Smoothed {processed} curve(s) with {total_points} total points using FFT Filter (cutoff={cutoff:.3f}).")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                            _apply_data_changes()
                            # Store settings (both current and last)
                            if not hasattr(fig, '_smooth_settings'):
                                fig._smooth_settings = {}
                            fig._smooth_settings['method'] = 'fft'
                            fig._smooth_settings['points'] = points
                            fig._smooth_settings['cutoff'] = cutoff
                            # Store as last settings for next time (both in-memory and config file)
                            if not hasattr(fig, '_last_smooth_settings'):
                                fig._last_smooth_settings = {}
                            fig._last_smooth_settings['method'] = 'fft'
                            fig._last_smooth_settings['points'] = points
                            fig._last_smooth_settings['cutoff'] = cutoff
                            # Save to config file for persistence across sessions
                            _save_last_smooth_settings_to_config({
                                'method': 'fft',
                                'points': points,
                                'cutoff': cutoff
                            })
                        else:
                            print("No curves were smoothed.")
                    except ValueError:
                        print("Invalid number.")
                    continue


__all__ = ["run_smoothing_menu"]
