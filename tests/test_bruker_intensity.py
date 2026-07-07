"""Tests for Bruker XRD intensity sentinel handling."""

from __future__ import annotations

import numpy as np

from batplot.readers import sanitize_xrd_intensity


def test_sanitize_xrd_intensity_replaces_bruker_sentinels():
    y = np.array([0.0, 100.0, -9999.0, 200.0, -999.0, 50.0])
    out = sanitize_xrd_intensity(y)
    assert out[0] == 0.0
    assert out[1] == 100.0
    assert np.isnan(out[2])
    assert out[3] == 200.0
    assert np.isnan(out[4])
    assert out[5] == 50.0


def test_sanitize_xrd_intensity_all_missing_becomes_all_nan():
    y = np.full(10, -9999.0)
    out = sanitize_xrd_intensity(y)
    assert out.shape == (10,)
    assert np.all(np.isnan(out))
