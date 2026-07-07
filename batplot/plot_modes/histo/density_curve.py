"""KDE density curve overlay for histogram mode."""

from __future__ import annotations

from typing import Callable, Tuple

import numpy as np  # type: ignore[import]

from .plot import HistoState


def _finite_values_in_range(state: HistoState) -> np.ndarray:
    vals = state.setup.values
    mask = np.isfinite(vals)
    vals = vals[mask]
    if state.setup.xmin is not None:
        vals = vals[(vals >= state.setup.xmin) & (vals <= state.setup.xmax)]
    return np.asarray(vals, dtype=float)


def _silverman_bandwidth(data: np.ndarray) -> float:
    n = data.size
    if n < 2:
        return 1.0
    std = float(np.std(data, ddof=1))
    if std <= 0:
        span = float(np.max(data) - np.min(data))
        std = span / 4.0 if span > 0 else 1.0
    return max(1.06 * std * (n ** (-1.0 / 5.0)), 1e-9)


def gaussian_kde_pdf(x_grid: np.ndarray, data: np.ndarray, bandwidth: float | None = None) -> np.ndarray:
    """Gaussian KDE probability density on ``x_grid`` (numpy-only, no scipy)."""
    data = np.asarray(data, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    if data.size == 0:
        return np.zeros_like(x_grid)
    bw = bandwidth if bandwidth is not None and bandwidth > 0 else _silverman_bandwidth(data)
    diff = (x_grid[:, None] - data[None, :]) / bw
    kernel = np.exp(-0.5 * diff * diff) / np.sqrt(2.0 * np.pi)
    return kernel.sum(axis=1) / (data.size * bw)


def density_curve_xy(
    state: HistoState,
    edges: np.ndarray,
    *,
    n_points: int = 200,
) -> Tuple[np.ndarray, np.ndarray] | None:
    """Return (x, y) arrays for a KDE overlay scaled to the current y-axis mode."""
    data = _finite_values_in_range(state)
    if data.size < 2:
        return None
    x0, x1 = float(edges[0]), float(edges[-1])
    if x1 <= x0:
        return None
    x_grid = np.linspace(x0, x1, max(int(n_points), 2))
    pdf = gaussian_kde_pdf(x_grid, data)
    if state.style.density:
        y = pdf
    else:
        widths = np.diff(edges)
        avg_width = float(np.mean(widths)) if widths.size else 1.0
        y = pdf * data.size * avg_width
    return x_grid, y


def run_histo_density_curve_menu(
    *,
    state: HistoState,
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Interactive submenu for the KDE density curve overlay."""

    def _flag(on: bool) -> str:
        return "ON" if on else "off"

    linestyle_labels = {"-": "solid", "--": "dashed", ":": "dotted"}
    linestyle_keys = {"s": "-", "d": "--", "t": ":"}

    while True:
        st = state.style
        ls_name = linestyle_labels.get(st.density_curve_ls, st.density_curve_ls)
        print("\n\033[1mDensity curve>\033[0m  (KDE overlay on histogram)")
        print(f"  show:      {_flag(st.show_density_curve)}")
        print(f"  color:     {st.density_curve_color}")
        print(f"  width:     {st.density_curve_lw:g}")
        print(f"  linestyle: {ls_name}")
        print("  " + colorize_menu("t: toggle on/off"))
        print("  " + colorize_menu("c: color"))
        print("  " + colorize_menu("w: line width"))
        print("  " + colorize_menu("l: linestyle (s/d/t)"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(colorize_prompt("Density (t/c/w/l/q): "), cancel_on_interrupt=True).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "t":
            push_state()
            st.show_density_curve = not st.show_density_curve
            refresh()
            print(f"Density curve {_flag(st.show_density_curve)}.")
            continue
        if choice == "c":
            spec = safe_input(colorize_prompt("Curve color (name/#hex, q=cancel): "), cancel_on_interrupt=True).strip()
            if not spec or spec.lower() == "q":
                continue
            push_state()
            st.density_curve_color = spec
            refresh()
            print(f"Density curve color set to {spec}.")
            continue
        if choice == "w":
            raw = safe_input(colorize_prompt("Line width (blank=keep): "), cancel_on_interrupt=True).strip()
            if not raw:
                continue
            try:
                lw = float(raw)
            except ValueError:
                print("Invalid line width.")
                continue
            if lw <= 0:
                print("Line width must be positive.")
                continue
            push_state()
            st.density_curve_lw = lw
            refresh()
            print(f"Density curve width set to {lw:g}.")
            continue
        if choice == "l":
            sub = safe_input(colorize_prompt("Linestyle s=solid, d=dashed, t=dotted (q=cancel): "), cancel_on_interrupt=True).strip().lower()
            if not sub or sub == "q":
                continue
            if sub not in linestyle_keys:
                print("Unknown linestyle.")
                continue
            push_state()
            st.density_curve_ls = linestyle_keys[sub]
            refresh()
            print(f"Density curve linestyle set to {linestyle_labels[st.density_curve_ls]}.")
            continue
        print("Unknown option.")


__all__ = [
    "density_curve_xy",
    "gaussian_kde_pdf",
    "run_histo_density_curve_menu",
]
