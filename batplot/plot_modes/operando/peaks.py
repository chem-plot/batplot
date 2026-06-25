"""Peak-search helpers for operando contour plots."""

from __future__ import annotations

import os
import traceback
from typing import Any

import numpy as np  # type: ignore[import-untyped]

from ...utils import choose_save_path

try:
    from scipy.signal import find_peaks
except ImportError:  # pragma: no cover - optional dependency
    find_peaks = None


def extract_operando_peak_data(im) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return contour data and x-axis values for peak searching."""
    data_array = np.asarray(im.get_array(), dtype=float)
    if data_array.ndim != 2 or data_array.size == 0:
        raise ValueError("No operando data available.")
    extent = im.get_extent()
    x0, x1, _y0, _y1 = extent
    x_min, x_max = (x0, x1) if x0 <= x1 else (x1, x0)
    n_scans, n_x_points = data_array.shape
    x_axis = np.linspace(x_min, x_max, n_x_points)
    return data_array, x_axis, float(x_min), float(x_max)


def find_operando_peaks(
    data_array: np.ndarray,
    x_axis: np.ndarray,
    *,
    x_range_min: float,
    x_range_max: float,
    prominence: float = 0.1,
    distance: int = 5,
    width: int = 1,
    include_intensity: bool = False,
    find_peaks_func: Any | None = None,
) -> list[tuple[Any, ...]]:
    """Find refined peak positions for each operando scan."""
    peak_func = find_peaks_func or find_peaks
    if peak_func is None:
        raise RuntimeError("scipy is required for peak finding. Install with: pip install scipy")
    n_scans, n_x_points = data_array.shape
    x_min = float(np.nanmin(x_axis))
    x_max = float(np.nanmax(x_axis))
    x_range_min = max(x_min, min(x_max, x_range_min))
    x_range_max = max(x_min, min(x_max, x_range_max))
    if x_range_min >= x_range_max:
        raise ValueError("Invalid range: min must be < max")

    col_min = int(np.argmin(np.abs(x_axis - x_range_min)))
    col_max = int(np.argmin(np.abs(x_axis - x_range_max)))
    if col_min > col_max:
        col_min, col_max = col_max, col_min
    col_max = min(col_max + 1, n_x_points)

    results: list[tuple[Any, ...]] = []
    for scan_idx in range(n_scans):
        intensity_profile = data_array[scan_idx, col_min:col_max]
        x_profile = x_axis[col_min:col_max]
        if len(intensity_profile) < 3:
            continue
        try:
            max_intensity = np.max(intensity_profile)
            min_intensity = np.min(intensity_profile)
            prominence_abs = (max_intensity - min_intensity) * prominence
            peak_kwargs = {
                "prominence": prominence_abs if prominence_abs > 0 else None,
                "distance": max(1, distance),
            }
            if width > 0:
                peak_kwargs["width"] = width
            peak_kwargs = {key: val for key, val in peak_kwargs.items() if val is not None}

            peak_indices, _peak_properties = peak_func(intensity_profile, **peak_kwargs)
            for peak_idx in peak_indices:
                if peak_idx == 0 or peak_idx == len(intensity_profile) - 1:
                    peak_x = x_profile[peak_idx]
                    peak_intensity = intensity_profile[peak_idx]
                else:
                    peak_x, peak_intensity = _quadratic_peak_position(x_profile, intensity_profile, int(peak_idx))
                if include_intensity:
                    results.append((scan_idx, peak_x, peak_intensity))
                else:
                    results.append((scan_idx, peak_x))
        except Exception:
            continue
    return results


def write_peak_results(target: str, results: list[tuple[Any, ...]], *, include_intensity: bool = False) -> None:
    with open(target, "w", encoding="utf-8") as handle:
        if include_intensity:
            handle.write("# File number\tPeak position\tPeak intensity\n")
            for scan_idx, peak_x, peak_intensity in results:
                handle.write(f"{scan_idx}\t{peak_x:.6f}\t{peak_intensity:.6f}\n")
        else:
            handle.write("# File number\tPeak position\n")
            for result in results:
                if len(result) == 2:
                    scan_idx, peak_x = result
                else:
                    scan_idx, peak_x, _peak_intensity = result
                handle.write(f"{scan_idx}\t{peak_x:.6f}\n")


def run_peak_search_menu(
    *,
    im,
    file_paths,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
) -> None:
    """Run the `pk` peak-search submenu."""
    try:
        if find_peaks is None:
            print("Error: scipy is required for peak finding. Install with: pip install scipy")
            print_menu()
            return

        try:
            data_array, x_axis, x_min, x_max = extract_operando_peak_data(im)
        except ValueError as exc:
            print(f"Error: {exc}")
            print_menu()
            return

        print("\nPeak Search:")
        print("  " + colorize_menu("1: find peaks in X range"))
        print("  " + colorize_menu("e: explanation"))
        print("  " + colorize_menu("q: back"))
        sub = safe_input(colorize_prompt("Peak (1/e/q): ")).strip().lower()

        if sub == "e":
            print_peak_search_explanation()
            print_menu()
            return
        if sub == "q":
            print_menu()
            return
        if sub not in ("1", ""):
            print("Invalid option.")
            print_menu()
            return

        print(f"\nCurrent X range: {x_min:.6g} to {x_max:.6g}")
        print("  " + colorize_menu("min max: set both limits"))
        print("  " + colorize_menu("Enter: use full range"))
        print("  " + colorize_menu("q: back"))
        x_range_input = safe_input(colorize_prompt("Peak X (min max/enter/q): ")).strip()
        if x_range_input.lower() == "q":
            print_menu()
            return
        if x_range_input:
            try:
                parts = x_range_input.split()
                if len(parts) < 2:
                    print("Invalid format. Use: min max")
                    print_menu()
                    return
                x_range_min = float(parts[0])
                x_range_max = float(parts[1])
            except ValueError:
                print("Invalid number format.")
                print_menu()
                return
        else:
            x_range_min = x_min
            x_range_max = x_max

        x_range_min = max(x_min, min(x_max, x_range_min))
        x_range_max = max(x_min, min(x_max, x_range_max))
        if x_range_min >= x_range_max:
            print("Invalid range: min must be < max")
            print_menu()
            return

        print("\nPeak finding parameters:")
        prominence_input = safe_input("Prominence (relative to max, default 0.1): ").strip()
        prominence = float(prominence_input) if prominence_input else 0.1
        distance_input = safe_input("Minimum distance between peaks (data points, default 5): ").strip()
        distance = int(distance_input) if distance_input else 5
        width_input = safe_input("Minimum peak width (data points, default 1, 0=disabled): ").strip()
        width = int(width_input) if width_input else 1
        include_intensity = safe_input("Include peak intensity in output? (y/n, default n): ").strip().lower() == "y"

        print(f"\nFinding peaks in X range [{x_range_min:.6g}, {x_range_max:.6g}]...")
        results = find_operando_peaks(
            data_array,
            x_axis,
            x_range_min=x_range_min,
            x_range_max=x_range_max,
            prominence=prominence,
            distance=distance,
            width=width,
            include_intensity=include_intensity,
        )
        if not results:
            print("No peaks found in the selected X range.")
            print_menu()
            return

        folder = choose_save_path(file_paths, purpose="peak search export")
        if not folder:
            print_menu()
            return
        print(f"\nChosen path: {folder}")
        fname = safe_input("Export filename (default: peaks.txt): ").strip()
        if not fname:
            fname = "peaks.txt"
        if not fname.endswith(".txt"):
            fname += ".txt"
        target = fname if os.path.isabs(fname) else os.path.join(folder, fname)
        if os.path.exists(target):
            yn = safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
            if yn != "y":
                print_menu()
                return

        try:
            write_peak_results(target, results, include_intensity=include_intensity)
            print(f"Peak positions exported to {target}")
            print(f"Found {len(results)} peaks across {len(set(r[0] for r in results))} scans")
        except Exception as exc:
            print(f"Error saving file: {exc}")
    except Exception as exc:
        print(f"Error in peak search: {exc}")
        traceback.print_exc()
    print_menu()


def print_peak_search_explanation() -> None:
    print("\n" + "=" * 70)
    print("PEAK SEARCHING EXPLANATION")
    print("=" * 70)
    print("\nPeak searching identifies local maxima in diffraction patterns.")
    print("This is useful for tracking how peak positions change over time")
    print("(or scan number) in operando experiments.\n")
    print("HOW IT WORKS:")
    print("1. Select X range: Choose the region where you want to find peaks")
    print("2. For each scan (file):")
    print("   - Extract intensity profile in the selected X range")
    print("   - Find local maxima (peaks) using scipy.signal.find_peaks")
    print("   - Refine peak positions using quadratic interpolation")
    print("3. Export results: Peak positions vs file number saved to .txt file\n")
    print("PARAMETERS:")
    print("- Prominence: Minimum height of peak relative to surrounding baseline")
    print("  (Higher = fewer, stronger peaks)")
    print("- Distance: Minimum separation between peaks (in data points)")
    print("  (Larger = peaks must be further apart)")
    print("- Width: Minimum width of peak at half maximum")
    print("  (Larger = broader peaks only)\n")
    print("OUTPUT FORMAT:")
    print("The exported .txt file contains:")
    print("  Column 1: File number (scan index, 0-based)")
    print("  Column 2: Peak position (X-axis value)")
    print("  Column 3: Peak intensity (optional, if enabled)\n")
    print("=" * 70 + "\n")


def _quadratic_peak_position(x_profile: np.ndarray, intensity_profile: np.ndarray, peak_idx: int) -> tuple[float, float]:
    y1 = intensity_profile[peak_idx - 1]
    y2 = intensity_profile[peak_idx]
    y3 = intensity_profile[peak_idx + 1]
    x1 = x_profile[peak_idx - 1]
    x2 = x_profile[peak_idx]
    x3 = x_profile[peak_idx + 1]
    denom = y1 - 2 * y2 + y3
    if abs(denom) > 1e-12:
        dx = 0.5 * (y1 - y3) / denom
        if -0.6 < dx < 0.6:
            return float(x2 + dx * (x3 - x1) / 2.0), float(y2 + 0.5 * dx * (y3 - y1))
    return float(x2), float(y2)


__all__ = [
    "extract_operando_peak_data",
    "find_operando_peaks",
    "print_peak_search_explanation",
    "run_peak_search_menu",
    "write_peak_results",
]
