"""Tests for unified CLI/batch style routing."""

from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.common.style_routing import apply_ec_style_dict, apply_xy_style_dict
from batplot.plot_modes.xy.style import apply_style_config, export_style_config


def test_apply_xy_style_dict_matches_interactive_path():
    fig, ax = plt.subplots()
    x = np.linspace(0, 10, 50)
    y = np.sin(x)
    ax.plot(x, y, color="C0", lw=1.5)
    ax.set_xlabel("X")
    ax.set_ylabel("Y")

    tick_state = {
        "tx": False,
        "bx": True,
        "ly": True,
        "ry": False,
        "t_ticks": False,
        "b_ticks": True,
        "l_ticks": True,
        "r_ticks": False,
        "t_labels": False,
        "b_labels": True,
        "l_labels": True,
        "r_labels": False,
        "mtx": False,
        "mbx": False,
        "mly": False,
        "mry": False,
    }

    with tempfile.NamedTemporaryFile("w", suffix=".bpsg", delete=False) as fh:
        path = fh.name
    try:
        export_style_config(
            path,
            fig,
            ax,
            [y],
            ["curve"],
            0.0,
            SimpleNamespace(stack=False),
            tick_state,
            [0.0],
            overwrite_path=path,
            force_kind="psg",
        )
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)

        fig_batch, ax_batch = plt.subplots()
        ax_batch.plot(x, y, color="C0", lw=1.5)
        apply_xy_style_dict(cfg, fig_batch, ax_batch)

        fig_inter, ax_inter = plt.subplots()
        ax_inter.plot(x, y, color="C0", lw=1.5)
        apply_style_config(
            path,
            fig_inter,
            ax_inter,
            None,
            [y],
            None,
            [0.0],
            [],
            SimpleNamespace(stack=False),
            tick_state,
            ["curve"],
            lambda *_a, **_k: None,
        )

        assert ax_batch.get_xlim() == ax_inter.get_xlim()
        assert ax_batch.get_ylim() == ax_inter.get_ylim()
        assert ax_batch.xaxis.label.get_text() == ax_inter.xaxis.label.get_text()
        assert ax_batch.yaxis.label.get_text() == ax_inter.yaxis.label.get_text()
    finally:
        plt.close(fig)
        plt.close("all")
        try:
            os.unlink(path)
        except OSError:
            pass


def test_apply_ec_style_dict_uses_canonical_applier():
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 1], color="C0", lw=2.0)

    cfg = {
        "kind": "ec_style_geom",
        "geometry": {"xlabel": "Cycles", "ylabel": "Cap"},
    }

    assert apply_ec_style_dict(cfg, fig, ax, cycle_lines={}) is True
    assert ax.get_xlabel() == "Cycles"
    assert ax.get_ylabel() == "Cap"
    plt.close(fig)


def test_apply_ec_style_dict_rejects_wrong_kind():
    fig, ax = plt.subplots()
    assert apply_ec_style_dict({"kind": "xy_style"}, fig, ax) is False
    plt.close(fig)
