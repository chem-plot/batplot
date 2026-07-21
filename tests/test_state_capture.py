"""Tests for shared state capture helpers (phase 2)."""

from __future__ import annotations

import json
import os

import matplotlib.pyplot as plt

from batplot.plot_modes.common.state_capture import (
    as_style_geom_export,
    load_json_snapshot,
    remove_temp_snapshot,
    ro_states_compatible,
    ro_states_compatible_xy,
    write_temp_json_snapshot,
)


def test_ro_states_compatible_xy_blocks_mismatch():
    fig, _ax = plt.subplots()
    cfg = {"ro_active": True}
    assert ro_states_compatible_xy(cfg, fig) is False
    fig._ro_active = True  # type: ignore[attr-defined]
    assert ro_states_compatible_xy(cfg, fig) is True
    plt.close(fig)


def test_ro_states_compatible_generic():
    fig, _ax = plt.subplots()
    assert ro_states_compatible({"ro_active": False}, fig, mode_label="CPC style") is True
    plt.close(fig)


def test_temp_json_snapshot_roundtrip():
    cfg = {"kind": "ec_style", "font": {"size": 11}}
    path = write_temp_json_snapshot(cfg)
    try:
        loaded = load_json_snapshot(path)
        assert loaded == cfg
        with open(path, encoding="utf-8") as fh:
            assert json.load(fh) == cfg
    finally:
        remove_temp_snapshot(path)
        assert not os.path.exists(path)


def test_as_style_geom_export():
    base = {"font": {"size": 12}, "kind": "ec_style"}
    geom = {"xlim": [0, 1], "ylim": [2, 3]}
    out = as_style_geom_export(base, kind="ec_style_geom", geometry=geom)
    assert out["kind"] == "ec_style_geom"
    assert out["geometry"] == geom
    assert out["font"] == {"size": 12}
    assert base["kind"] == "ec_style"
