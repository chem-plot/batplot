"""Per-mode recent axis names: storage, migration, numeric pick, quote escape.

Covers the config layer (``recent_axis_names_by_mode`` + lazy migration from
the legacy shared list), the utils helpers (``print_recent_axis_names``,
``remember_axis_name``, ``resolve_recent_axis_name``), and the wiring inside
the per-mode rename menus (XY interactive + batch XY as representatives; all
modes share the same helpers).
"""

from __future__ import annotations

import json

import pytest

import batplot.config as CFG
from batplot.utils import (
    print_recent_axis_names,
    remember_axis_name,
    resolve_recent_axis_name,
)


def _write_config(payload: dict) -> None:
    CFG.save_config(payload)


def _read_config() -> dict:
    with open(CFG.get_config_file(), "r") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# config layer
# ---------------------------------------------------------------------------

def test_record_and_get_per_mode_are_isolated():
    CFG.record_recent_axis_name("Potential (V)", mode="ec")
    CFG.record_recent_axis_name("2theta (deg)", mode="xy")

    assert CFG.get_recent_axis_names(mode="ec") == ["Potential (V)"]
    assert CFG.get_recent_axis_names(mode="xy") == ["2theta (deg)"]
    # Other modes stay empty (no leak across modes).
    assert CFG.get_recent_axis_names(mode="cpc") == []


def test_newest_first_dedupe_and_cap():
    for i in range(25):
        CFG.record_recent_axis_name(f"label {i}", mode="xy")
    CFG.record_recent_axis_name("label 3", mode="xy")  # re-use bumps to front

    names = CFG.get_recent_axis_names(mode="xy")
    assert names[0] == "label 3"
    assert len(names) == CFG.RECENT_AXIS_NAMES_MAX
    assert len(set(names)) == len(names)


def test_lazy_migration_seeds_mode_from_legacy_list():
    _write_config({"recent_axis_names": ["Old shared name", "Another"]})

    # First per-mode read seeds from the legacy list and persists the seed.
    assert CFG.get_recent_axis_names(mode="ec") == ["Old shared name", "Another"]
    stored = _read_config()
    assert stored["recent_axis_names_by_mode"]["ec"] == ["Old shared name", "Another"]
    # Legacy list itself is untouched (old batplot versions keep working).
    assert stored["recent_axis_names"] == ["Old shared name", "Another"]


def test_migration_on_first_write_then_isolated():
    _write_config({"recent_axis_names": ["Seeded"]})

    CFG.record_recent_axis_name("New EC name", mode="ec")
    assert CFG.get_recent_axis_names(mode="ec") == ["New EC name", "Seeded"]

    # After migration, EC records do not touch other modes or the legacy list.
    CFG.record_recent_axis_name("Second EC name", mode="ec")
    stored = _read_config()
    assert stored["recent_axis_names"] == ["Seeded"]
    assert "xy" not in stored.get("recent_axis_names_by_mode", {})


def test_legacy_no_mode_calls_unchanged():
    CFG.record_recent_axis_name("Shared A")
    CFG.record_recent_axis_name("Shared B")
    assert CFG.get_recent_axis_names() == ["Shared B", "Shared A"]


def test_corrupt_by_mode_value_degrades_gracefully():
    _write_config({"recent_axis_names_by_mode": {"xy": "not-a-list"}})
    assert CFG.get_recent_axis_names(mode="xy") == []


# ---------------------------------------------------------------------------
# utils helpers
# ---------------------------------------------------------------------------

def test_resolve_numeric_pick_and_out_of_range():
    remember_axis_name("Voltage (V)", mode="ec")
    remember_axis_name("Capacity (mAh/g)", mode="ec")

    # 1 = newest
    assert resolve_recent_axis_name("1", mode="ec") == "Capacity (mAh/g)"
    assert resolve_recent_axis_name("2", mode="ec") == "Voltage (V)"
    # Out of range -> literal text.
    assert resolve_recent_axis_name("9", mode="ec") == "9"
    # Non-numeric passes through untouched.
    assert resolve_recent_axis_name("Potential", mode="ec") == "Potential"


def test_resolve_quote_escape_gives_literal_number():
    remember_axis_name("Voltage (V)", mode="ec")
    assert resolve_recent_axis_name('"1"', mode="ec") == "1"
    assert resolve_recent_axis_name('"quoted text"', mode="ec") == "quoted text"


def test_resolve_respects_mode_separation():
    remember_axis_name("XY only", mode="xy")
    # No recent names in histo -> "1" stays literal.
    assert resolve_recent_axis_name("1", mode="histo") == "1"
    assert resolve_recent_axis_name("1", mode="xy") == "XY only"


def test_print_recent_axis_names_mode_output(capsys):
    remember_axis_name("Voltage (V)", mode="cpc")
    print_recent_axis_names(mode="cpc")
    out = capsys.readouterr().out
    assert "1: Voltage (V)" in out
    assert "this mode only" in out

    print_recent_axis_names(mode="operando")
    out = capsys.readouterr().out
    assert "No recent axis names stored yet." in out


# ---------------------------------------------------------------------------
# menu wiring (XY interactive rename + batch XY as representatives)
# ---------------------------------------------------------------------------

def _feed(monkeypatch_inputs):
    it = iter(monkeypatch_inputs)

    def _fake(prompt="", **_k):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _fake


def test_xy_rename_menu_records_and_picks_by_number():
    import matplotlib.pyplot as plt
    from batplot.plot_modes.xy.labels import run_xy_rename_menu

    fig, ax = plt.subplots()
    kwargs = dict(
        ax=ax,
        fig=fig,
        labels=["curve"],
        label_text_objects=[ax.text(0, 0, "1: curve")],
        args_files=["a.xy"],
        get_cif_series=lambda: [],
        print_cif_phase_list=lambda cts: None,
        apply_cif_phase_label_rename=lambda i, s: None,
        position_top_xlabel=lambda: None,
        position_bottom_xlabel=lambda: None,
        position_right_ylabel=lambda: None,
        position_left_ylabel=lambda: None,
        sync_fonts=lambda: None,
        push_state=lambda note="": None,
    )

    # Type a fresh label -> recorded for xy mode.
    run_xy_rename_menu(safe_input=_feed(["x", "My X Label", "q", "q"]), **kwargs)
    assert ax.xaxis.label.get_text() == "My X Label"
    assert CFG.get_recent_axis_names(mode="xy") == ["My X Label"]

    # Pick it by number on the y-axis.
    run_xy_rename_menu(safe_input=_feed(["y", "1", "q", "q"]), **kwargs)
    assert ax.yaxis.label.get_text() == "My X Label"

    # Quoted number stays literal.
    run_xy_rename_menu(safe_input=_feed(["y", '"1"', "q", "q"]), **kwargs)
    assert ax.yaxis.label.get_text() == "1"


def test_xy_label_prompt_s_lists_names_without_renaming(capsys):
    import matplotlib.pyplot as plt
    from batplot.plot_modes.xy.labels import run_xy_rename_menu

    remember_axis_name("Stored XY", mode="xy")
    fig, ax = plt.subplots()
    ax.set_xlabel("before")
    run_xy_rename_menu(
        ax=ax,
        fig=fig,
        labels=["curve"],
        label_text_objects=[ax.text(0, 0, "1: curve")],
        args_files=["a.xy"],
        get_cif_series=lambda: [],
        print_cif_phase_list=lambda cts: None,
        apply_cif_phase_label_rename=lambda i, s: None,
        position_top_xlabel=lambda: None,
        position_bottom_xlabel=lambda: None,
        position_right_ylabel=lambda: None,
        position_left_ylabel=lambda: None,
        sync_fonts=lambda: None,
        push_state=lambda note="": None,
        safe_input=_feed(["x", "s", "q", "q"]),
    )
    out = capsys.readouterr().out
    # `s` at the label prompt lists names instead of renaming the axis to "s".
    assert "1: Stored XY" in out
    assert ax.xaxis.label.get_text() == "before"


def test_ec_rename_menu_uses_ec_mode_key():
    import matplotlib.pyplot as plt
    from batplot.plot_modes.electrochem.labels import run_ec_rename_menu

    fig, ax = plt.subplots()
    run_ec_rename_menu(
        fig=fig,
        ax=ax,
        file_data=None,
        tick_state={},
        push_state=lambda note="": None,
        rebuild_legend=lambda a: None,
        print_file_list=lambda *a, **k: None,
        safe_input=_feed(["x", "Potential vs Li (V)", "q", "q"]),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        ui_position_top_xlabel=lambda *a, **k: None,
        ui_position_bottom_xlabel=lambda *a, **k: None,
        ui_position_left_ylabel=lambda *a, **k: None,
        ui_position_right_ylabel=lambda *a, **k: None,
    )
    assert ax.get_xlabel() == "Potential vs Li (V)"
    assert CFG.get_recent_axis_names(mode="ec") == ["Potential vs Li (V)"]
    # Not visible from xy.
    assert CFG.get_recent_axis_names(mode="xy") == []


def test_recent_names_survive_pkl_session_reload(tmp_path):
    """Names typed in a session-reloaded menu use the same config store."""
    remember_axis_name("From session", mode="xy")
    # Simulate a fresh process reading config again.
    assert CFG.get_recent_axis_names(mode="xy") == ["From session"]
