"""Peak-finder submenu for the XY interactive menu.

Self-contained read-only analysis: it detects local maxima on the (offset-
removed) curves over a chosen X window and can export the result to a text
file. It owns no undo/plot mutation state, so the dispatcher only injects the
data lists and terminal callbacks.
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Sequence

import numpy as np  # type: ignore[import]

from ...utils import choose_save_path


def run_peak_finder_menu(
    *,
    ax: Any,
    x_data_list: Sequence[Any],
    y_data_list: Sequence[Any],
    offsets_list: Sequence[float],
    labels: Sequence[str],
    source_file_paths: Sequence[str],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Interactive local-maxima finder with optional text export."""
    while True:
        try:
            print("  " + colorize_menu("min max: set both limits"))
            print("  " + colorize_menu("current: use axes limits"))
            print("  " + colorize_menu("q: back"))
            rng_in = safe_input(colorize_prompt("Peak X (min max/current/q): ")).strip().lower()
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

            frac_in = safe_input("Min relative peak height (0–1, default 0.1): ").strip()
            min_frac = float(frac_in) if frac_in else 0.1
            if min_frac < 0: min_frac = 0.0
            if min_frac > 1: min_frac = 1.0

            swin = safe_input("Smoothing window (odd int >=3, blank=none): ").strip()
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
            all_peak_results = []  # list of (curve_index, label, [(x, y), ...])
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
                peak_xy_list = []
                for pi in peaks:
                    px, py = float(x_sel[pi]), float(y_sel[pi])
                    peak_xy_list.append((px, py))
                    print(f"    x={x_sel[pi]:.6g}, y={y_sel[pi]:.6g}")
                if peak_xy_list:
                    all_peak_results.append((i + 1, label, peak_xy_list))
            print("\n--- End Peak Report ---\n")

            # Export peaks to file
            if all_peak_results:
                export_yn = safe_input("Export peaks to file? (y/n): ").strip().lower()
                if export_yn == 'y':
                    folder = choose_save_path(list(source_file_paths), purpose="peak export")
                    if folder:
                        print(f"\nChosen path: {folder}")
                        fname = safe_input("Export filename (default: peaks.txt): ").strip()
                        if not fname:
                            fname = "peaks.txt"
                        if not fname.endswith('.txt'):
                            fname += '.txt'
                        target = fname if os.path.isabs(fname) else os.path.join(folder, fname)
                        do_write = not os.path.exists(target)
                        if os.path.exists(target):
                            ow = safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                            if ow == 'y':
                                do_write = True
                            else:
                                print("Export canceled.")
                        if do_write:
                            try:
                                with open(target, 'w') as f:
                                    f.write("# Curve\tLabel\tPeak x\tPeak y\n")
                                    for curve_idx, label, peak_xy_list in all_peak_results:
                                        for px, py in peak_xy_list:
                                            f.write(f"{curve_idx}\t{label}\t{px:.6g}\t{py:.6g}\n")
                                total_peaks = sum(len(pairs) for _, _, pairs in all_peak_results)
                                print(f"Peak positions exported to {target}")
                                print(f"Found {total_peaks} peaks across {len(all_peak_results)} curves.")
                            except Exception as e:
                                print(f"Error saving file: {e}")
                    else:
                        print("Export canceled.")
        except Exception as e:
            print(f"Error finding peaks: {e}")


__all__ = ["run_peak_finder_menu"]
