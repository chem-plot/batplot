"""Status line for dQ/dV ``sm`` menu (current smooth settings)."""

from __future__ import annotations

import matplotlib.pyplot as plt

from batplot.plot_modes.electrochem.smoothing_menu import format_dqdv_smooth_status


def test_format_none_when_raw():
    fig, ax = plt.subplots()
    try:
        (ln,) = ax.plot([0.0, 1.0], [0.0, 1.0])
        assert format_dqdv_smooth_status(
            fig, cycle_lines={1: {"charge": ln, "discharge": None}}
        ) == "Current: none (raw data)"
    finally:
        plt.close(fig)


def test_format_diffcap_and_updates():
    fig, _ax = plt.subplots()
    try:
        fig._dqdv_smooth_settings = {
            "method": "diffcap",
            "min_step": 0.001,
            "window": 9,
            "poly": 3,
        }
        text = format_dqdv_smooth_status(fig)
        assert "DiffCap" in text
        assert "1" in text  # 1 mV
        assert "window=9" in text
        assert "order=3" in text

        fig._dqdv_smooth_settings = {
            "method": "voltage_step",
            "threshold_v": 0.0005,
        }
        text = format_dqdv_smooth_status(fig)
        assert "potential step" in text
        assert "0.5" in text

        fig._dqdv_smooth_settings = {}
        assert format_dqdv_smooth_status(fig) == "Current: none (raw data)"
    finally:
        plt.close(fig)


def test_format_outlier_methods():
    fig, _ax = plt.subplots()
    try:
        fig._dqdv_smooth_settings = {
            "method": "outlier",
            "outlier_method": "1",
            "threshold": 5.0,
        }
        assert "Z-score" in format_dqdv_smooth_status(fig)
        fig._dqdv_smooth_settings = {
            "method": "outlier",
            "outlier_method": "2",
            "threshold": 6.0,
        }
        assert "MAD" in format_dqdv_smooth_status(fig)
    finally:
        plt.close(fig)


def test_format_old_session_filtered_without_settings():
    """Old pkl may restore filtered lines without dqdv_smooth_settings."""
    fig, ax = plt.subplots()
    try:
        (ln,) = ax.plot([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
        ln._original_xdata = [0.0, 1.0, 2.0]
        ln._original_ydata = [0.0, 1.0, 0.5]
        ln._smooth_applied = True
        text = format_dqdv_smooth_status(
            fig, cycle_lines={1: {"charge": ln, "discharge": None}}
        )
        assert "filtering applied" in text
        assert "not stored" in text
    finally:
        plt.close(fig)


def test_format_legacy_settings_without_method():
    fig, _ax = plt.subplots()
    try:
        fig._dqdv_smooth_settings = {"window": 11, "polyorder": 3}
        text = format_dqdv_smooth_status(fig)
        assert "window=11" in text
        assert "order=3" in text
    finally:
        plt.close(fig)
