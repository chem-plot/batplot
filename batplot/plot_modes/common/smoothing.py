"""Numerical smoothing helpers shared by interactive plot modes."""

from __future__ import annotations

import numpy as np


def savgol_kernel(window: int, poly: int) -> np.ndarray:
    """Return a Savitzky-Golay smoothing kernel for the given window/poly."""
    half = window // 2
    x = np.arange(-half, half + 1, dtype=float)
    A = np.vander(x, poly + 1, increasing=True)
    ATA = A.T @ A
    ATA_inv = np.linalg.pinv(ATA)
    target = np.zeros(poly + 1, dtype=float)
    target[0] = 1.0
    return target @ ATA_inv @ A.T


def savgol_smooth(y: np.ndarray, window: int = 9, poly: int = 3) -> np.ndarray:
    """Apply the existing DiffCapAnalyzer-style Savitzky-Golay smoothing."""
    n = y.size
    if n < 3:
        return y
    if window > n:
        window = n if n % 2 == 1 else n - 1
    if window < 3:
        return y
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return y
    if poly >= window:
        poly = window - 1
    coeffs = savgol_kernel(window, poly)
    half = window // 2
    padded = np.pad(y, (half, half), mode="edge")
    return np.convolve(padded, coeffs[::-1], mode="valid")
