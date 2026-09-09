"""Smoke tests for screen color picker helpers (no GUI)."""

from __future__ import annotations

from batplot.screen_color import _normalize_hex, _sample_around_cursor
from batplot.color_utils import (
    prompt_screen_color,
    blank_means_back,
    arm_ignore_next_blank_color_input,
)


def test_normalize_hex():
    assert _normalize_hex("#AbCdEf") == "#abcdef"
    assert _normalize_hex("ff0000") == "#ff0000"
    assert _normalize_hex("bad") is None
    assert _normalize_hex("") is None


def test_sample_around_cursor_center_pixel():
    import numpy as np

    rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    rgb[50, 40] = (10, 20, 30)
    patch, hex_c = _sample_around_cursor(rgb, 40, 50, 100, 100)
    assert patch is not None
    assert hex_c == "#0a141e"
    assert tuple(int(v) for v in patch[patch.shape[0] // 2, patch.shape[1] // 2]) == (10, 20, 30)


def test_prompt_screen_color_cancelled(monkeypatch):
    import batplot.screen_color as sc

    monkeypatch.setattr(sc, "pick_screen_colors", lambda **kwargs: [])
    assert prompt_screen_color(None, add_to_saved=False) is None


def test_prompt_screen_color_saves(monkeypatch):
    import batplot.screen_color as sc
    import batplot.color_utils as cu

    monkeypatch.setattr(sc, "pick_screen_colors", lambda **kwargs: ["#112233", "#445566"])
    saved = []

    def _fake_add(color, fig=None):
        saved.append(color)
        return list(saved)

    monkeypatch.setattr(cu, "add_user_color", _fake_add)
    out = prompt_screen_color(None, add_to_saved=True)
    assert out == "#445566"  # last pick returned for apply-on-pick paths
    assert saved == ["#112233", "#445566"]
    assert cu.last_screen_pick_count() == 2


def test_blank_means_back_ignores_one_after_picker():
    arm_ignore_next_blank_color_input()
    assert blank_means_back("") is False  # ignored once
    assert blank_means_back("") is True  # next blank exits
    arm_ignore_next_blank_color_input()
    assert blank_means_back("red") is False  # real input clears guard
    assert blank_means_back("") is True  # blank now exits (guard cleared)


def test_run_color_token_input_loop_e_and_resolve(monkeypatch):
    from batplot.color_utils import run_color_token_input_loop
    import batplot.color_utils as cu

    inputs = iter(["e", "red", "q"])
    applied = []

    def _fake_prompt(fig=None, **k):
        cu._last_screen_pick_count = 1
        return "#abcdef"

    monkeypatch.setattr(cu, "prompt_screen_color", _fake_prompt)
    monkeypatch.setattr(cu, "resolve_color_token", lambda tok, fig=None: tok.lower() if tok else tok)

    run_color_token_input_loop(
        prompt="Color> ",
        safe_input=lambda *_a, **_k: next(inputs),
        colorize_prompt=lambda s: s,
        process=lambda c: applied.append(c) or True,
        fig=None,
    )
    assert applied == ["#abcdef", "red"]


def test_run_color_token_input_loop_multipick_skips_auto_apply(monkeypatch):
    from batplot.color_utils import run_color_token_input_loop
    import batplot.color_utils as cu

    inputs = iter(["e", "red", "q"])
    applied = []

    def _fake_prompt(fig=None, **k):
        cu._last_screen_pick_count = 3  # palette grab
        arm_ignore_next_blank_color_input()
        return "#abcdef"

    monkeypatch.setattr(cu, "prompt_screen_color", _fake_prompt)
    monkeypatch.setattr(cu, "resolve_color_token", lambda tok, fig=None: tok.lower() if tok else tok)

    run_color_token_input_loop(
        prompt="Color> ",
        safe_input=lambda *_a, **_k: next(inputs),
        colorize_prompt=lambda s: s,
        process=lambda c: applied.append(c) or True,
        fig=None,
    )
    # Multi-pick must NOT auto-apply last; only explicit token applies
    assert applied == ["red"]


def test_run_color_token_input_loop_ignores_blank_after_e(monkeypatch):
    from batplot.color_utils import run_color_token_input_loop
    import batplot.color_utils as cu

    # e → pick → leftover blank must not exit; then red applies; q exits
    inputs = iter(["e", "", "red", "q"])
    applied = []

    def _fake_prompt(fig=None, **k):
        cu._last_screen_pick_count = 1
        arm_ignore_next_blank_color_input()
        return "#abcdef"

    monkeypatch.setattr(cu, "prompt_screen_color", _fake_prompt)
    monkeypatch.setattr(cu, "resolve_color_token", lambda tok, fig=None: tok.lower() if tok else tok)

    run_color_token_input_loop(
        prompt="Color> ",
        safe_input=lambda *_a, **_k: next(inputs),
        colorize_prompt=lambda s: s,
        process=lambda c: applied.append(c) or True,
        fig=None,
    )
    assert applied == ["#abcdef", "red"]


def test_platform_helpers():
    from batplot.screen_color import _is_macos, _is_windows, _is_linux
    import sys

    assert _is_macos() == (sys.platform == "darwin")
    assert _is_windows() == sys.platform.startswith("win")
    assert _is_linux() == sys.platform.startswith("linux")
    # Exactly one primary desktop OS family for normal hosts
    assert sum([_is_macos(), _is_windows(), _is_linux()]) <= 1 or sys.platform.startswith("linux")


def test_grab_region_dispatches_native_first(monkeypatch):
    import batplot.screen_color as sc
    import numpy as np

    calls = []

    fake = np.zeros((15, 15, 3), dtype=np.uint8)
    fake[7, 7] = (1, 2, 3)

    monkeypatch.setattr(sc, "_grab_region_macos", lambda *a, **k: calls.append("mac") or fake)
    monkeypatch.setattr(sc, "_grab_region_windows", lambda *a, **k: calls.append("win") or fake)
    monkeypatch.setattr(sc, "_grab_region_linux", lambda *a, **k: calls.append("linux") or fake)
    monkeypatch.setattr(sc, "_grab_region_pillow", lambda *a, **k: calls.append("pillow") or None)

    monkeypatch.setattr(sc, "_is_macos", lambda: True)
    monkeypatch.setattr(sc, "_is_windows", lambda: False)
    monkeypatch.setattr(sc, "_is_linux", lambda: False)
    out = sc._grab_region(0, 0, 15, 15)
    assert calls == ["mac"]
    assert out is fake

    calls.clear()
    monkeypatch.setattr(sc, "_is_macos", lambda: False)
    monkeypatch.setattr(sc, "_is_windows", lambda: True)
    out = sc._grab_region(0, 0, 15, 15)
    assert calls == ["win"]

    calls.clear()
    monkeypatch.setattr(sc, "_is_windows", lambda: False)
    monkeypatch.setattr(sc, "_is_linux", lambda: True)
    # Force linux helper to fail so pillow is tried
    monkeypatch.setattr(sc, "_grab_region_linux", lambda *a, **k: calls.append("linux") or None)
    monkeypatch.setattr(sc, "_grab_region_pillow", lambda *a, **k: calls.append("pillow") or fake)
    out = sc._grab_region(0, 0, 15, 15)
    assert calls == ["linux", "pillow"]
    assert out is fake


def test_live_hex_file_roundtrip(tmp_path):
    from batplot.screen_color import _write_live_hex, _read_live_hex

    path = str(tmp_path / "live.hex")
    _write_live_hex(path, "#a1b2c3")
    assert _read_live_hex(path) == "#a1b2c3"
