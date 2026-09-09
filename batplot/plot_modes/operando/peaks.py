"""Peak-search helpers for operando contour plots.

Peak X positions are always taken from the **current** imshow extent/domain
(after Options ``u`` remesh), so ``pk`` stays consistent with 2θ ↔ Q ↔ d.
When λ is known, exports also include the full Bragg triplet.
"""

from __future__ import annotations

import os
import traceback
from typing import Any, Optional

import numpy as np  # type: ignore[import-untyped]

from ...utils import choose_save_path
from ..xy.axis_units import convert_x_array

try:
    from scipy.signal import find_peaks
except ImportError:  # pragma: no cover - defensive if env is incomplete
    find_peaks = None

_XRD_MODES = ("2theta", "Q", "d")

_AXIS_LABEL = {
    "2theta": "2θ (°)",
    "Q": "Q (Å⁻¹)",
    "d": "d (Å)",
}


def extract_operando_peak_data(im) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return contour data and x-axis values for peak searching.

    Column ``i`` maps to ``linspace(extent_x0, extent_x1, n)`` so the mapping
    matches Options ``u`` remesh (which always writes ascending extent).
    """
    data_array = np.asarray(im.get_array(), dtype=float)
    if data_array.ndim != 2 or data_array.size == 0:
        raise ValueError("No operando data available.")
    extent = im.get_extent()
    x0, x1, _y0, _y1 = (float(v) for v in extent)
    n_scans, n_x_points = data_array.shape
    # Preserve extent orientation (left→right of the image array).
    x_axis = np.linspace(x0, x1, n_x_points)
    x_min = float(min(x0, x1))
    x_max = float(max(x0, x1))
    return data_array, x_axis, x_min, x_max


def resolve_peak_axis_context(
    fig: Any | None = None,
    ax: Any | None = None,
) -> tuple[str, Optional[float]]:
    """Return ``(axis_mode, wavelength)`` for peak labeling / Bragg export."""
    mode = "unknown"
    wl: Optional[float] = None
    if fig is not None:
        try:
            from .axis_units import get_operando_axis_mode, resolve_operando_wavelength

            mode = str(get_operando_axis_mode(fig, ax) or "unknown")
            wl = resolve_operando_wavelength(fig=fig)
        except Exception:
            stored = getattr(fig, "_operando_axis_mode", None)
            if stored:
                mode = str(stored)
            raw_wl = getattr(fig, "_operando_wl", None)
            if raw_wl is not None:
                try:
                    cand = float(raw_wl)
                    if np.isfinite(cand) and cand > 0:
                        wl = cand
                except (TypeError, ValueError):
                    pass
    if mode.lower() == "q":
        mode = "Q"
    return mode, wl


def peak_bragg_triplet(
    x: float,
    *,
    axis_mode: str,
    wavelength: Optional[float] = None,
) -> dict[str, Optional[float]]:
    """Convert a peak x in the current domain to ``2theta`` / ``Q`` / ``d``.

    Missing conversions (no λ for 2θ) leave that key as ``None``.
    """
    mode = str(axis_mode or "").strip()
    if mode.lower() == "q":
        mode = "Q"
    out: dict[str, Optional[float]] = {"2theta": None, "Q": None, "d": None}
    try:
        xv = float(x)
    except (TypeError, ValueError):
        return out
    if mode not in _XRD_MODES:
        return out

    wl: Optional[float] = None
    if wavelength is not None:
        try:
            cand = float(wavelength)
            if np.isfinite(cand) and cand > 0:
                wl = cand
        except (TypeError, ValueError):
            wl = None

    try:
        if mode == "Q":
            q = xv
        elif mode == "d":
            q = float(convert_x_array(np.asarray([xv]), frm="d", to="Q", wl=None)[0])
        else:  # 2theta
            out["2theta"] = xv
            if wl is None:
                return out
            q = float(convert_x_array(np.asarray([xv]), frm="2theta", to="Q", wl=wl)[0])
        if np.isfinite(q):
            out["Q"] = q
            if abs(q) > 1e-30:
                out["d"] = float(2.0 * np.pi / q)
        if wl is not None and out["Q"] is not None:
            tth = float(
                convert_x_array(
                    np.asarray([out["Q"]]), frm="Q", to="2theta", wl=wl, clip_bragg=True,
                )[0]
            )
            if np.isfinite(tth):
                out["2theta"] = tth
        elif mode == "2theta":
            out["2theta"] = xv
    except Exception:
        # Keep whatever we could fill; primary domain value as fallback.
        if mode == "2theta":
            out["2theta"] = xv
        elif mode == "Q":
            out["Q"] = xv
        elif mode == "d":
            out["d"] = xv
    return out


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
    """Find refined peak positions for each operando scan.

    ``x_axis`` / ``x_range_*`` are in the **current** operando X domain
    (same units as Options ``u`` left the plot in).
    """
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


def write_peak_results(
    target: str,
    results: list[tuple[Any, ...]],
    *,
    include_intensity: bool = False,
    axis_mode: str | None = None,
    wavelength: Optional[float] = None,
) -> None:
    """Write peak table; with XRD + λ include 2θ / Q / d columns."""
    mode = str(axis_mode or "").strip()
    if mode.lower() == "q":
        mode = "Q"
    use_bragg = mode in _XRD_MODES and wavelength is not None
    try:
        wl_ok = float(wavelength) if wavelength is not None else None
        if wl_ok is not None and (not np.isfinite(wl_ok) or wl_ok <= 0):
            use_bragg = False
            wl_ok = None
    except (TypeError, ValueError):
        use_bragg = False
        wl_ok = None

    primary = _AXIS_LABEL.get(mode, "Peak position")

    with open(target, "w", encoding="utf-8") as handle:
        if use_bragg:
            handle.write(
                "# axis_mode={0}\twavelength_A={1:.8g}\n".format(mode, float(wl_ok))
            )
            cols = [
                "File number",
                "Peak position ({0})".format(primary),
                "2theta_deg",
                "Q_A^-1",
                "d_A",
            ]
            if include_intensity:
                cols.append("Peak intensity")
            handle.write("# " + "\t".join(cols) + "\n")
            for row in results:
                if include_intensity and len(row) >= 3:
                    scan_idx, peak_x, peak_intensity = row[0], row[1], row[2]
                else:
                    scan_idx, peak_x = row[0], row[1]
                    peak_intensity = None
                trip = peak_bragg_triplet(float(peak_x), axis_mode=mode, wavelength=wl_ok)
                tth = trip["2theta"]
                q = trip["Q"]
                d = trip["d"]
                parts = [
                    str(scan_idx),
                    f"{float(peak_x):.6f}",
                    f"{tth:.6f}" if tth is not None and np.isfinite(tth) else "nan",
                    f"{q:.6f}" if q is not None and np.isfinite(q) else "nan",
                    f"{d:.6f}" if d is not None and np.isfinite(d) else "nan",
                ]
                if include_intensity:
                    parts.append(
                        f"{float(peak_intensity):.6f}" if peak_intensity is not None else "nan"
                    )
                handle.write("\t".join(parts) + "\n")
            return

        # Backward-compatible single-position export (no λ / non-XRD)
        if include_intensity:
            handle.write(f"# File number\t{primary}\tPeak intensity\n")
            for scan_idx, peak_x, peak_intensity in results:
                handle.write(f"{scan_idx}\t{peak_x:.6f}\t{peak_intensity:.6f}\n")
        else:
            handle.write(f"# File number\t{primary}\n")
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
    fig: Any | None = None,
    ax: Any | None = None,
) -> None:
    """Run the `pk` peak-search submenu (X domain = current Options ``u`` units)."""
    try:
        if find_peaks is None:
            print("Error: scipy is required for peak finding. Install with: pip install scipy")
            return

        axis_mode, wavelength = resolve_peak_axis_context(fig, ax)
        unit_name = _AXIS_LABEL.get(axis_mode, "X")

        while True:
            # Re-read im each loop so a prior Options ``u`` remesh is always used.
            try:
                data_array, x_axis, x_min, x_max = extract_operando_peak_data(im)
            except ValueError as exc:
                print(f"Error: {exc}")
                return
            axis_mode, wavelength = resolve_peak_axis_context(fig, ax)
            unit_name = _AXIS_LABEL.get(axis_mode, "X")

            print("\nPeak Search:")
            if axis_mode in _XRD_MODES:
                wl_txt = f", λ={wavelength:g} Å" if wavelength is not None else ", λ unknown"
                print(f"  Current XRD axis: {unit_name}{wl_txt}")
                if wavelength is not None:
                    print("  Export will include 2θ, Q, and d (compatible with Options u).")
            print("  " + colorize_menu("1: find peaks in X range"))
            print("  " + colorize_menu("e: explanation"))
            print("  " + colorize_menu("q: back"))
            sub = safe_input(colorize_prompt("Peak (1/e/q): ")).strip().lower()
            if not sub or sub == "q":
                break
            if sub == "e":
                print_peak_search_explanation()
                continue
            if sub not in ("1",):
                print("Invalid option.")
                continue

            print(f"\nCurrent {unit_name} range: {x_min:.6g} to {x_max:.6g}")
            print("  " + colorize_menu("min max: set both limits (current axis units)"))
            print("  " + colorize_menu("Enter: use full range"))
            print("  " + colorize_menu("q: back"))
            x_range_input = safe_input(colorize_prompt("Peak X (min max/enter/q): ")).strip()
            if x_range_input.lower() == "q":
                continue
            if not x_range_input:
                x_range_min = x_min
                x_range_max = x_max
            else:
                try:
                    parts = x_range_input.split()
                    if len(parts) < 2:
                        print("Invalid format. Use: min max")
                        continue
                    x_range_min = float(parts[0])
                    x_range_max = float(parts[1])
                except ValueError:
                    print("Invalid number format.")
                    continue

            x_range_min = max(x_min, min(x_max, x_range_min))
            x_range_max = max(x_min, min(x_max, x_range_max))
            if x_range_min >= x_range_max:
                print("Invalid range: min must be < max")
                continue

            print("\nPeak finding parameters (q=back from any prompt returns to peak menu):")
            while True:
                prominence_input = safe_input("Prominence (relative to max, default 0.1, q=back): ").strip()
                if prominence_input.lower() == "q":
                    break
                try:
                    prominence = float(prominence_input) if prominence_input else 0.1
                except ValueError:
                    print("Invalid prominence.")
                    continue
                if not (prominence > 0) or prominence != prominence:  # NaN reject
                    print("Prominence must be a positive number.")
                    continue
                distance_input = safe_input("Minimum distance between peaks (data points, default 5, q=back): ").strip()
                if distance_input.lower() == "q":
                    break
                try:
                    distance = int(distance_input) if distance_input else 5
                except ValueError:
                    print("Invalid distance (integer data points).")
                    continue
                if distance < 1:
                    print("Distance must be >= 1.")
                    continue
                width_input = safe_input("Minimum peak width (data points, default 1, 0=disabled, q=back): ").strip()
                if width_input.lower() == "q":
                    break
                try:
                    width = int(width_input) if width_input else 1
                except ValueError:
                    print("Invalid width (integer data points).")
                    continue
                if width < 0:
                    print("Width must be >= 0.")
                    continue
                include_raw = safe_input("Include peak intensity in output? (y/n, default n, q=back): ").strip().lower()
                if include_raw == "q":
                    break
                include_intensity = include_raw == "y"

                print(
                    f"\nFinding peaks in {unit_name} range "
                    f"[{x_range_min:.6g}, {x_range_max:.6g}]..."
                )
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
                    continue

                folder = choose_save_path(file_paths, purpose="peak search export")
                if not folder:
                    continue
                print(f"\nChosen path: {folder}")
                fname = safe_input("Export filename (default: peaks.txt, q=back): ").strip()
                if fname.lower() == "q":
                    continue
                if not fname:
                    fname = "peaks.txt"
                if not fname.endswith(".txt"):
                    fname += ".txt"
                target = fname if os.path.isabs(fname) else os.path.join(folder, fname)
                if os.path.exists(target):
                    yn = safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                    if yn != "y":
                        continue

                try:
                    write_peak_results(
                        target,
                        results,
                        include_intensity=include_intensity,
                        axis_mode=axis_mode,
                        wavelength=wavelength,
                    )
                    print(f"Peak positions exported to {target}")
                    print(f"Found {len(results)} peaks across {len(set(r[0] for r in results))} scans")
                    if axis_mode in _XRD_MODES and wavelength is not None:
                        print("  Columns: peak in current axis + 2θ + Q + d (Options u compatible).")
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
    print("AXIS UNITS (Options u):")
    print("- Peaks are found in the **current** X-axis units (2θ / Q / d).")
    print("- After converting with Options u, re-run pk; ranges and positions")
    print("  use the new domain (imshow is remeshed by u).")
    print("- When wavelength is known (--wl / session), the export also includes")
    print("  2θ, Q, and d for every peak so results stay usable after unit changes.\n")
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
    print("  Column 2: Peak position in the current axis units")
    print("  With λ (XRD): also 2theta_deg, Q_A^-1, d_A")
    print("  Optional: Peak intensity\n")
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
    "peak_bragg_triplet",
    "print_peak_search_explanation",
    "resolve_peak_axis_context",
    "run_peak_search_menu",
    "write_peak_results",
]
