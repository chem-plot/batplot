"""dQ/dV smoothing/filtering submenu for the electrochem interactive menu.

Extracted verbatim from interactive.py (the former nested ``_handle_key_sm``);
the dispatcher keeps a thin wrapper so prompts, messages, and undo semantics
are unchanged.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

import numpy as np  # type: ignore[import-untyped]

from ..common.smoothing import savgol_smooth as _savgol_smooth

__all__ = [
    "format_dqdv_smooth_status",
    "run_dqdv_smoothing_menu",
]


def _diffcap_clean_series(x: np.ndarray, y: np.ndarray, min_step: float = 1e-3) -> Tuple[np.ndarray, np.ndarray, int]:
    """Remove points where ΔPotential < min_step (default 1 mV) while preserving order."""
    if x.size <= 1:
        return x, y, 0
    keep_indices = [0]
    last_x = x[0]
    removed = 0
    for idx in range(1, x.size):
        if abs(x[idx] - last_x) >= min_step:
            keep_indices.append(idx)
            last_x = x[idx]
        else:
            removed += 1
    if removed == 0:
        return x, y, 0
    keep = np.array(keep_indices, dtype=int)
    return x[keep], y[keep], removed


def _iter_smooth_lines(
    cycle_lines: Any = None,
    file_data: Optional[Sequence[dict]] = None,
):
    """Yield line artists from multi-file entries or a single cycle_lines map."""
    if file_data:
        for f in file_data:
            cl = f.get("cycle_lines") or {}
            for parts in cl.values():
                if isinstance(parts, dict):
                    for ln in parts.values():
                        if ln is not None:
                            yield ln
                elif parts is not None:
                    yield parts
        return
    if not cycle_lines:
        return
    for parts in cycle_lines.values():
        if isinstance(parts, dict):
            for ln in parts.values():
                if ln is not None:
                    yield ln
        elif parts is not None:
            yield parts


def _any_curve_filtered(
    cycle_lines: Any = None,
    file_data: Optional[Sequence[dict]] = None,
) -> bool:
    for ln in _iter_smooth_lines(cycle_lines, file_data):
        if bool(getattr(ln, "_smooth_applied", False)):
            return True
        if hasattr(ln, "_original_xdata") and hasattr(ln, "_original_ydata"):
            return True
    return False


def format_dqdv_smooth_status(
    fig,
    *,
    cycle_lines: Any = None,
    file_data: Optional[Sequence[dict]] = None,
) -> str:
    """Human-readable current dQ/dV filter state for the ``sm`` menu header.

    Prefers ``fig._dqdv_smooth_settings`` (saved in pkl / style). Old sessions
    that only restore filtered curve data still report that filtering is on.
    """
    settings = getattr(fig, "_dqdv_smooth_settings", None)
    if isinstance(settings, dict) and settings:
        method = settings.get("method")
        if method == "voltage_step":
            try:
                thr_mv = float(settings.get("threshold_v", 0.0)) * 1000.0
            except Exception:
                thr_mv = settings.get("threshold_v", "?")
            return f"Current: potential step filter (min ΔV = {thr_mv:g} mV)"
        if method == "diffcap":
            try:
                min_step_mv = float(settings.get("min_step", 0.001)) * 1000.0
            except Exception:
                min_step_mv = settings.get("min_step", "?")
            window = settings.get("window", 9)
            poly = settings.get("poly", settings.get("polyorder", 3))
            return (
                f"Current: DiffCap (ΔV ≥ {min_step_mv:g} mV + "
                f"Savitzky–Golay window={window}, order={poly})"
            )
        if method == "outlier":
            om = str(settings.get("outlier_method", "1"))
            name = "Z-score" if om == "1" else "MAD"
            thr = settings.get("threshold", "?")
            return f"Current: outlier removal ({name}, threshold={thr})"
        # Legacy / incomplete dicts (e.g. only window/poly) from older code paths
        parts = []
        if "threshold_v" in settings:
            try:
                parts.append(f"min ΔV = {float(settings['threshold_v']) * 1000.0:g} mV")
            except Exception:
                parts.append(f"threshold_v={settings['threshold_v']}")
        if "min_step" in settings:
            try:
                parts.append(f"ΔV ≥ {float(settings['min_step']) * 1000.0:g} mV")
            except Exception:
                parts.append(f"min_step={settings['min_step']}")
        if "window" in settings or "poly" in settings or "polyorder" in settings:
            w = settings.get("window", "?")
            p = settings.get("poly", settings.get("polyorder", "?"))
            parts.append(f"Savitzky–Golay window={w}, order={p}")
        if "threshold" in settings:
            parts.append(f"outlier threshold={settings['threshold']}")
        if parts:
            return "Current: " + "; ".join(parts)
        if method:
            return f"Current: {method}"
    if _any_curve_filtered(cycle_lines, file_data):
        return (
            "Current: filtering applied "
            "(parameters not stored in this session — use r to reset)"
        )
    return "Current: none (raw data)"


def run_dqdv_smoothing_menu(
    *,
    fig,
    cycle_lines,
    file_data,
    current_file_idx,
    all_cycles,
    is_dqdv,
    is_multi_file,
    menu_title,
    canvas_mode,
    print_menu,
    print_file_list,
    push_state,
    safe_input,
    colorize_menu,
    colorize_prompt,
):
    """dQ/dV data-filtering submenu (a/d/o/r/q)."""
    if not is_dqdv:
        print("Smoothing is only available in dQ/dV mode.")
        print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
        return
    # Multi-file: choose target file(s) for smoothing
    smooth_target_list = [cycle_lines]
    if is_multi_file:
        print_file_list(file_data, current_file_idx)
        choice = safe_input(f"Select file numbers (1-{len(file_data)}), all (a), or q=cancel: ").strip().lower()
        if choice == 'q':
            print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            print_file_list(file_data, current_file_idx)
            return
        if choice in ('a', 'all'):
            smooth_target_list = [f['cycle_lines'] for f in file_data if f.get('visible', True)]
        else:
            try:
                idx = int(choice)
                if 1 <= idx <= len(file_data):
                    smooth_target_list = [file_data[idx - 1]['cycle_lines']]
                else:
                    print("Invalid file number.")
                    return
            except ValueError:
                print("Invalid input.")
                return
    while True:
        print("\n\033[1mdQ/dV Data Filtering (Neware method)\033[0m")
        print(
            format_dqdv_smooth_status(
                fig, cycle_lines=cycle_lines, file_data=file_data if is_multi_file else None
            )
        )
        print("Commands:")
        print("  " + colorize_menu("a: apply potential step filter (removes small ΔV points)"))
        print("  " + colorize_menu("d: DiffCap smooth (≥1 mV ΔV + Savitzky–Golay, order 3, window 9)"))
        print("  " + colorize_menu("o: remove outliers (removes abrupt dQ/dV spikes)"))
        print("  " + colorize_menu("r: reset to original data"))
        print("  " + colorize_menu("q: back to main menu"))
        sub = safe_input(colorize_prompt(
            "dQ/dV filter command (a/d/o/r per list above, q=back to main menu): "
        )).strip().lower()
        if not sub:
            continue
        if sub == 'q':
            break
        if sub == 'r':
            has_filtered = False
            try:
                for _tcl in smooth_target_list:
                    for _cyc, parts in _tcl.items():
                        for role in ("charge", "discharge"):
                            ln = parts.get(role) if isinstance(parts, dict) else parts
                            if ln is not None and hasattr(ln, '_original_xdata'):
                                has_filtered = True
                                break
                        if has_filtered:
                            break
                    if has_filtered:
                        break
            except Exception:
                has_filtered = False
            if not has_filtered:
                print("No filtered data to reset.")
                continue
            push_state("smooth-reset")
            restored_count = 0
            try:
                for _tcl in smooth_target_list:
                    for cyc, parts in _tcl.items():
                        for role in ("charge", "discharge"):
                            ln = parts.get(role) if isinstance(parts, dict) else parts
                            if ln is None:
                                continue
                            if hasattr(ln, '_original_xdata'):
                                ln.set_xdata(ln._original_xdata)
                                ln.set_ydata(ln._original_ydata)
                                if hasattr(ln, '_smooth_applied'):
                                    delattr(ln, '_smooth_applied')
                                restored_count += 1
                if restored_count:
                    print(f"Reset {restored_count} curve(s) to original data.")
                    # Clear stored smooth settings
                    if hasattr(fig, '_dqdv_smooth_settings'):
                        fig._dqdv_smooth_settings = {}
                    fig.canvas.draw_idle()
                else:
                    print("No filtered data to reset.")
            except Exception as e:
                print(f"Error resetting filter: {e}")
            continue
        if sub == 'a':
            try:
                while True:
                    threshold_input = safe_input("Enter minimum potential step in mV (default 0.5 mV, 'q'=quit, 'e'=explain): ").strip()
                    if threshold_input.lower() == 'q':
                        break
                    if threshold_input.lower() == 'e':
                        print("\n--- Potential Step Filter Explanation ---")
                        print("This filter removes data points where the potential change (ΔV) between")
                        print("consecutive points is smaller than the threshold.")
                        print("\nExample: If threshold = 0.5 mV, any point where |V[i+1] - V[i]| < 0.5 mV")
                        print("will be removed. This helps eliminate noisy or redundant measurements.")
                        print("\nTypical values: 0.1-1.0 mV (smaller = more aggressive filtering)")
                        print("Higher values remove more points but may oversmooth the data.")
                        print("----------------------------------------\n")
                        continue
                    threshold_mv = 0.5 if not threshold_input else float(threshold_input)
                    break
                if threshold_input.lower() == 'q':  # User quit
                    continue
                threshold_v = threshold_mv / 1000.0
                if threshold_v <= 0:
                    print("Threshold must be positive.")
                    continue
                push_state("smooth-apply")
                # Store smooth settings for future cycle changes
                if not hasattr(fig, '_dqdv_smooth_settings'):
                    fig._dqdv_smooth_settings = {}
                fig._dqdv_smooth_settings.update({
                    'method': 'voltage_step',
                    'threshold_v': threshold_v
                })
                filtered = 0
                total_before = 0
                total_after = 0
                for _tcl in smooth_target_list:
                    for cyc, parts in _tcl.items():
                        for role in ("charge", "discharge"):
                            ln = parts.get(role) if isinstance(parts, dict) else parts
                            if ln is None or not ln.get_visible():
                                continue
                            xdata = np.asarray(ln.get_xdata(), float)
                            ydata = np.asarray(ln.get_ydata(), float)
                            if xdata.size != ydata.size:
                                n = int(min(xdata.size, ydata.size))
                                if n < 3:
                                    continue
                                xdata = xdata[:n]
                                ydata = ydata[:n]
                            if xdata.size < 3:
                                continue
                            if not hasattr(ln, '_original_xdata'):
                                ln._original_xdata = np.array(xdata, copy=True)
                                ln._original_ydata = np.array(ydata, copy=True)
                            dv = np.abs(np.diff(xdata))
                            mask = np.ones_like(xdata, dtype=bool)
                            mask[1:] &= dv >= threshold_v
                            mask[:-1] &= dv >= threshold_v
                            filtered_x = xdata[mask]
                            filtered_y = ydata[mask]
                            before = len(xdata)
                            after = len(filtered_x)
                            if after < before:
                                ln.set_xdata(filtered_x)
                                ln.set_ydata(filtered_y)
                                ln._smooth_applied = True
                                filtered += 1
                                total_before += before
                                total_after += after
                if filtered:
                    removed = total_before - total_after
                    pct = 100 * removed / total_before if total_before else 0
                    print(f"Filtered {filtered} curve(s); removed {removed} of {total_before} points ({pct:.1f}%).")
                    print("Tip: Increase threshold to aggressively filter points (always applied to raw data).")
                    fig.canvas.draw_idle()
                else:
                    print("No curves affected by current threshold.")
            except ValueError:
                print("Invalid number.")
            continue
        if sub == 'd':
            try:
                print("DiffCap smoothing per Thompson et al. (2020): clean ΔV < threshold and apply Savitzky–Golay (order 3).")
                while True:
                    delta_input = safe_input("Minimum ΔV between points (mV, default 1.0, 'q'=quit, 'e'=explain): ").strip()
                    if delta_input.lower() == 'q':
                        break
                    if delta_input.lower() == 'e':
                        print("\n--- Minimum ΔV Explanation ---")
                        print("First step: Remove points where potential change is too small.")
                        print("This threshold (in mV) determines the minimum potential difference")
                        print("required between consecutive points. Points with smaller ΔV are")
                        print("removed as noise before smoothing.")
                        print("\nTypical values: 0.5-2.0 mV")
                        print("Smaller values = keep more points (less aggressive cleaning)")
                        print("Larger values = remove more points (more aggressive cleaning)")
                        print("--------------------------------\n")
                        continue
                    min_step = 0.001 if not delta_input else max(float(delta_input), 0.0) / 1000.0
                    if min_step <= 0:
                        print("ΔV threshold must be positive.")
                        continue
                    break
                # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                if delta_input and delta_input.lower() == 'q':  # User quit at previous step
                    continue
                while True:
                    window_input = safe_input("Savitzky–Golay window (odd, default 9, 'q'=quit, 'e'=explain): ").strip()
                    if window_input.lower() == 'q':
                        break
                    if window_input.lower() == 'e':
                        print("\n--- Savitzky–Golay Window Explanation ---")
                        print("The window size determines how many neighboring points are used")
                        print("to smooth each data point. Must be an odd number (3, 5, 7, 9, 11, ...).")
                        print("\nLarger window = smoother result but may lose fine details")
                        print("Smaller window = preserves more detail but less smoothing")
                        print("\nTypical values: 5-15 (9 is a good default)")
                        print("Window must be larger than polynomial order.")
                        print("------------------------------------------\n")
                        continue
                    window = 9 if not window_input else int(window_input)
                    break
                # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                if window_input and window_input.lower() == 'q':  # User quit at previous step
                    continue
                while True:
                    poly_input = safe_input("Polynomial order (default 3, 'q'=quit, 'e'=explain): ").strip()
                    if poly_input.lower() == 'q':
                        break
                    if poly_input.lower() == 'e':
                        print("\n--- Polynomial Order Explanation ---")
                        print("The polynomial order determines the complexity of the smoothing")
                        print("function. Higher order = more flexible curve fitting.")
                        print("\nOrder 1 = linear (straight line) - very smooth, may oversimplify")
                        print("Order 3 = cubic (default) - good balance of smoothness and detail")
                        print("Order 5+ = higher complexity - preserves more features, less smooth")
                        print("\nTypical values: 1-5 (3 is recommended)")
                        print("Order must be less than window size.")
                        print("--------------------------------------\n")
                        continue
                    poly = 3 if not poly_input else int(poly_input)
                    break
                # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                if poly_input and poly_input.lower() == 'q':  # User quit at previous step
                    continue
            except ValueError:
                print("Invalid number.")
                continue
            if window < 3:
                window = 3
            if window % 2 == 0:
                window += 1
            if poly < 1:
                poly = 1
            push_state("smooth-diffcap")
            # Store smooth settings for future cycle changes
            if not hasattr(fig, '_dqdv_smooth_settings'):
                fig._dqdv_smooth_settings = {}
            fig._dqdv_smooth_settings.update({
                'method': 'diffcap',
                'min_step': min_step,
                'window': window,
                'poly': poly
            })
            cleaned_curves = 0
            total_removed = 0
            for _tcl in smooth_target_list:
                for cyc, parts in _tcl.items():
                    iter_parts = [(None, parts)] if not isinstance(parts, dict) else [(k, v) for k, v in parts.items()]
                    for role, ln in iter_parts:
                        if ln is None or not ln.get_visible():
                            continue
                        xdata = np.asarray(ln.get_xdata(), float)
                        ydata = np.asarray(ln.get_ydata(), float)
                        if xdata.size != ydata.size:
                            n = int(min(xdata.size, ydata.size))
                            if n < 3:
                                continue
                            xdata = xdata[:n]
                            ydata = ydata[:n]
                        if xdata.size < 3:
                            continue
                        if not hasattr(ln, '_original_xdata'):
                            ln._original_xdata = np.array(xdata, copy=True)
                            ln._original_ydata = np.array(ydata, copy=True)
                        x_clean, y_clean, removed = _diffcap_clean_series(xdata, ydata, min_step)
                        if x_clean.size < poly + 2:
                            continue
                        y_smooth = _savgol_smooth(y_clean, window, poly)
                        ln.set_xdata(x_clean)
                        ln.set_ydata(y_smooth)
                        ln._smooth_applied = True
                        cleaned_curves += 1
                        total_removed += removed
            if cleaned_curves:
                print(f"DiffCap smoothing applied to {cleaned_curves} curve(s); removed {total_removed} noisy points.")
                fig.canvas.draw_idle()
            else:
                print("No curves were smoothed (not enough data after cleaning).")
            continue
        if sub == 'o':
            print("Outlier removal methods:")
            print("  " + colorize_menu("1: Z-score (enter standard deviation threshold, default 5.0)"))
            print("  " + colorize_menu("2: MAD (median absolute deviation, default factor 6.0)"))
            while True:
                method = safe_input("Method (1/2, blank=cancel, 'q'=quit, 'e'=explain): ").strip()
                if not method or method.lower() == 'q':
                    break
                if method.lower() == 'e':
                    print("\n--- Outlier Removal Methods Explanation ---")
                    print("Method 1 - Z-score:")
                    print("  Removes points where |(value - mean) / std| > threshold")
                    print("  Works well for normally distributed data")
                    print("  Default threshold: 5.0 (removes points >5 standard deviations)")
                    print("\nMethod 2 - MAD (Median Absolute Deviation):")
                    print("  Removes points where |(value - median) / MAD| > threshold")
                    print("  More robust to outliers (uses median instead of mean)")
                    print("  Default threshold: 6.0 (removes points >6 MAD units)")
                    print("\nHigher threshold = removes fewer points (less aggressive)")
                    print("Lower threshold = removes more points (more aggressive)")
                    print("Typical thresholds: 3.0-10.0")
                    print("--------------------------------------------\n")
                    continue
                if method not in ('1', '2'):
                    print("Unknown method.")
                    continue
                break
            if not method:  # User canceled/quitted
                continue
            try:
                while True:
                    thresh_input = safe_input("Enter threshold (blank=default, 'q'=quit, 'e'=explain): ").strip()
                    if thresh_input.lower() == 'q':
                        break
                    if thresh_input.lower() == 'e':
                        if method == '1':
                            print("\n--- Z-score Threshold Explanation ---")
                            print("Threshold determines how many standard deviations a point can")
                            print("deviate from the mean before being considered an outlier.")
                            print("\nDefault: 5.0 (removes points where |z-score| > 5)")
                            print("Higher values (6-10) = remove only extreme outliers")
                            print("Lower values (2-4) = remove more points, including moderate spikes")
                            print("\nExample: threshold=5.0 means points >5σ from mean are removed")
                            print("--------------------------------------\n")
                        else:
                            print("\n--- MAD Threshold Explanation ---")
                            print("Threshold determines how many MAD units a point can deviate")
                            print("from the median before being considered an outlier.")
                            print("\nDefault: 6.0 (removes points where |MAD-score| > 6)")
                            print("Higher values (7-10) = remove only extreme outliers")
                            print("Lower values (3-5) = remove more points, including moderate spikes")
                            print("\nMAD is more robust than standard deviation for noisy data.")
                            print("----------------------------------\n")
                        continue
                    if method == '1':
                        z_threshold = 5.0 if not thresh_input else float(thresh_input)
                        if z_threshold <= 0:
                            print("Threshold must be positive.")
                            continue
                    else:
                        mad_threshold = 6.0 if not thresh_input else float(thresh_input)
                        if mad_threshold <= 0:
                            print("Threshold must be positive.")
                            continue
                    break
                # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                if thresh_input and thresh_input.lower() == 'q':  # User quit
                    continue
                push_state("smooth-outlier")
                # Store smooth settings for future cycle changes
                if not hasattr(fig, '_dqdv_smooth_settings'):
                    fig._dqdv_smooth_settings = {}
                thresh_val = z_threshold if method == '1' else mad_threshold
                fig._dqdv_smooth_settings.update({
                    'method': 'outlier',
                    'outlier_method': method,
                    'threshold': thresh_val
                })
                filtered = 0
                total_before = 0
                total_after = 0
                for _tcl in smooth_target_list:
                    for cyc, parts in _tcl.items():
                        for role in ("charge", "discharge"):
                            ln = parts.get(role) if isinstance(parts, dict) else parts
                            if ln is None or not ln.get_visible():
                                continue
                            xdata = np.asarray(ln.get_xdata(), float)
                            ydata = np.asarray(ln.get_ydata(), float)
                            if xdata.size != ydata.size:
                                n = int(min(xdata.size, ydata.size))
                                if n < 5:
                                    continue
                                xdata = xdata[:n]
                                ydata = ydata[:n]
                            if xdata.size < 5:
                                continue
                            if not hasattr(ln, '_original_xdata'):
                                ln._original_xdata = np.array(xdata, copy=True)
                                ln._original_ydata = np.array(ydata, copy=True)
                            if method == '1':
                                mean_y = np.nanmean(ydata)
                                std_y = np.nanstd(ydata)
                                if not np.isfinite(std_y) or std_y == 0:
                                    continue
                                zscores = np.abs((ydata - mean_y) / std_y)
                                mask = zscores <= z_threshold
                            else:
                                median_y = np.nanmedian(ydata)
                                mad = np.nanmedian(np.abs(ydata - median_y))
                                if not np.isfinite(mad) or mad == 0:
                                    continue
                                deviations = np.abs(ydata - median_y) / mad
                                mask = deviations <= mad_threshold
                            filtered_x = xdata[mask]
                            filtered_y = ydata[mask]
                            before = len(xdata)
                            after = len(filtered_x)
                            if after < before:
                                ln.set_xdata(filtered_x)
                                ln.set_ydata(filtered_y)
                                ln._smooth_applied = True
                                filtered += 1
                                total_before += before
                                total_after += after
                if filtered:
                    removed = total_before - total_after
                    pct = 100 * removed / total_before if total_before else 0
                    method_name = "Z-score" if method == '1' else "MAD"
                    print(f"Removed outliers from {filtered} curve(s) using {method_name} (threshold={thresh_val}).")
                    print(f"Removed {removed} of {total_before} points ({pct:.1f}%).")
                    print("Tip: Adjust threshold to control sensitivity (always applied to raw data).")
                    fig.canvas.draw_idle()
                else:
                    print("No outliers found with current threshold.")
            except ValueError:
                print("Invalid number.")
            continue
        print("Unknown command. Use a/o/r/q.")
    print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
    return
