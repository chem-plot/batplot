"""Tests for macOS IMK stderr noise filtering helpers."""

from __future__ import annotations

import io

from batplot.plot_modes.common.terminal import FilterIMKWarning, is_imk_noise


def test_is_imk_noise_detects_known_messages():
    assert is_imk_noise("error messaging the mach port for IMKCFRunLoopWakeUpReliable")
    assert is_imk_noise(b"python[123:456] error messaging the mach port for IMKCFRunLoopWakeUpReliable\n")
    assert not is_imk_noise("Canvas set to 5.00 x 3.00 in on all 3 plots.")


def test_filter_imk_warning_drops_noise_only():
    out = io.StringIO()
    filt = FilterIMKWarning(out)
    filt.write("real error: bad value\n")
    filt.write("error messaging the mach port for IMKCFRunLoopWakeUpReliable\n")
    filt.write("still visible\n")
    assert out.getvalue() == "real error: bad value\nstill visible\n"
