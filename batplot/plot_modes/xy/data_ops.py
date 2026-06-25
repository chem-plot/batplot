"""Pure data-processing helpers for the XY interactive menu.

These functions are intentionally free of any plot/figure/undo state: they take
arrays in and return arrays out. Keeping them here lets the smoothing and
derivative submenus stay thin and makes the math reusable/testable.
"""

from __future__ import annotations

from typing import Optional

import numpy as np  # type: ignore[import]


def _fft_smooth(y: np.ndarray, points: int = 5, cutoff: float = 0.1) -> np.ndarray:
    """Apply FFT filter smoothing to data."""
    n = y.size
    if n < 3:
        return y
    # FFT
    fft_vals = np.fft.rfft(y)
    freq = np.fft.rfftfreq(n)
    # Low-pass filter: zero out frequencies above cutoff
    mask = freq <= cutoff
    fft_vals[~mask] = 0
    # Inverse FFT
    smoothed = np.fft.irfft(fft_vals, n)
    return smoothed


def _adjacent_average_smooth(y: np.ndarray, points: int = 5) -> np.ndarray:
    """Apply Adjacent-Averaging smoothing to data."""
    n = y.size
    if n < points:
        return y
    if points < 2:
        return y
    # Use convolution for moving average
    kernel = np.ones(points) / points
    # Pad edges
    padded = np.pad(y, (points//2, points//2), mode='edge')
    smoothed = np.convolve(padded, kernel, mode='valid')
    return smoothed


def _calculate_derivative(x: np.ndarray, y: np.ndarray, order: int = 1) -> np.ndarray:
    """Calculate 1st or 2nd derivative using numpy gradient.

    Args:
        x: X values
        y: Y values
        order: 1 for first derivative (dy/dx), 2 for second derivative (d²y/dx²)

    Returns:
        Derivative array (same length as input)
    """
    if len(y) < 2:
        return y.copy()
    # Calculate dy/dx
    dy_dx = np.gradient(y, x)
    if order == 1:
        return dy_dx
    elif order == 2:
        # Calculate d²y/dx² = d(dy/dx)/dx
        if len(dy_dx) < 2:
            return np.zeros_like(y)
        d2y_dx2 = np.gradient(dy_dx, x)
        return d2y_dx2
    else:
        return y.copy()


def _calculate_reversed_derivative(x, y, order):
    """Calculate reversed 1st or 2nd derivative (dx/dy or d²x/dy²).

    Args:
        x: X values
        y: Y values
        order: 1 for first reversed derivative (dx/dy), 2 for second reversed derivative (d²x/dy²)

    Returns:
        Reversed derivative array (same length as input)
    """
    if len(y) < 2:
        return y.copy()
    # First calculate dy/dx
    dy_dx = np.gradient(y, x)
    # Avoid division by zero - replace zeros with small epsilon
    epsilon = 1e-10
    dy_dx_safe = np.where(np.abs(dy_dx) < epsilon, np.sign(dy_dx) * epsilon, dy_dx)
    # Calculate dx/dy = 1 / (dy/dx)
    dx_dy = 1.0 / dy_dx_safe
    if order == 1:
        return dx_dy
    elif order == 2:
        # Calculate d²x/dy² = d(dx/dy)/dy
        # d(dx/dy)/dy = d(1/(dy/dx))/dy = -1/(dy/dx)² * d²y/dx²
        if len(dx_dy) < 2:
            return np.zeros_like(y)
        # Calculate d²y/dx² first
        d2y_dx2 = np.gradient(dy_dx, x)
        # d²x/dy² = -d²y/dx² / (dy/dx)³
        d2x_dy2 = -d2y_dx2 / (dy_dx_safe ** 3)
        return d2x_dy2
    else:
        return y.copy()


__all__ = [
    "_fft_smooth",
    "_adjacent_average_smooth",
    "_calculate_derivative",
    "_calculate_reversed_derivative",
]
