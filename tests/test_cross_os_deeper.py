"""Deeper cross-OS consistency regressions (Win / macOS / Linux)."""

from __future__ import annotations

import io
import os
import subprocess
import sys

import pytest


def test_operando_startup_cif_token_uses_extended_windows_path():
    from batplot.plot_modes.operando.plot import _parse_operando_cif_path_token

    path, wl = _parse_operando_cif_path_token(r"\\?\C:\data\phase.cif:1.54")
    assert path == r"\\?\C:\data\phase.cif"
    assert wl == pytest.approx(1.54)


def test_windows_popen_kwargs_has_create_no_window(monkeypatch):
    import batplot.screen_color as sc

    monkeypatch.setattr(sc.sys, "platform", "win32")
    kw = sc._windows_popen_kwargs()
    assert "creationflags" in kw
    expected = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    assert kw["creationflags"] == expected

    monkeypatch.setattr(sc.sys, "platform", "linux")
    assert sc._windows_popen_kwargs() == {}


def test_linux_without_display_skips_gui_backends(monkeypatch):
    import batplot._mpl_backend as mb

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(mb, "_should_respect_env_agg", lambda: False)
    monkeypatch.setattr(mb, "_USER_SET_MPLBACKEND", False)
    monkeypatch.setattr(mb, "is_interactive_backend", lambda: False)
    monkeypatch.setattr(mb, "wants_interactive_window", lambda _a: True)
    tried = []

    def _use(name, force=True):
        tried.append(name)

    monkeypatch.setattr(mb._mpl, "use", _use)
    assert mb.ensure_gui_backend(object()) is False
    assert tried == [], "linux without DISPLAY must not try Tk/Qt"


def test_darwin_without_display_still_tries_gui(monkeypatch):
    """macOS GUI does not require DISPLAY — must not short-circuit like Linux."""
    import batplot._mpl_backend as mb

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(mb, "_should_respect_env_agg", lambda: False)
    monkeypatch.setattr(mb, "_USER_SET_MPLBACKEND", False)
    monkeypatch.setattr(mb, "is_interactive_backend", lambda: False)
    monkeypatch.setattr(mb, "wants_interactive_window", lambda _a: True)
    tried = []

    def _use(name, force=True):
        tried.append(name)
        raise RuntimeError("no gui in test")

    monkeypatch.setattr(mb._mpl, "use", _use)
    monkeypatch.setattr(mb, "_backend_can_be_tried", lambda _n: True)
    assert mb.ensure_gui_backend(object()) is False
    assert tried, "darwin should attempt GUI backends even without DISPLAY"


def test_safe_console_print_survives_cp1252(monkeypatch):
    from batplot.plot_modes.common import terminal as T

    class _Cp1252:
        encoding = "cp1252"

        def __init__(self):
            self.buf = io.StringIO()

        def write(self, s):
            # Simulate Windows console: reject characters outside cp1252.
            s.encode("cp1252")
            self.buf.write(s)

        def flush(self):
            pass

    fake = _Cp1252()
    monkeypatch.setattr(T.sys, "stdout", fake)
    # Arrow / box chars must not raise
    T.safe_console_print("Current \u2192 Latest \u256d\u2500\u256e")
    assert "Current" in fake.buf.getvalue()


def test_version_banner_uses_ascii_and_windows_disable(monkeypatch, capsys):
    import batplot.version_check as VC

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(VC, "_get_terminal_width", lambda: 80)
    VC._print_update_message("1.0.0", "1.0.1", versions_behind=1)
    out = capsys.readouterr().out
    assert "\u256d" not in out and "\u2192" not in out
    assert "->" in out or "Latest" in out
    assert "BATPLOT_NO_VERSION_CHECK" in out
    assert "set " in out or "PowerShell" in out


def test_version_banner_unix_disable_hint(monkeypatch, capsys):
    import batplot.version_check as VC

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(VC, "_get_terminal_width", lambda: 80)
    VC._print_update_message("1.0.0", "1.0.1", versions_behind=0)
    out = capsys.readouterr().out
    assert "export BATPLOT_NO_VERSION_CHECK=1" in out


def test_console_safe_text_transliterates_menu_glyphs():
    from batplot.plot_modes.common.terminal import console_safe_text

    s = console_safe_text("✓ 2θ → Q  g⁻¹  ≥1")
    assert "✓" not in s and "θ" not in s and "→" not in s
    assert "≥" not in s
    assert "[OK]" in s
    assert "theta" in s
    assert "->" in s
    assert ">=" in s


def test_safe_input_sanitizes_prompt_on_cp1252(monkeypatch):
    from batplot.plot_modes.common import terminal as T

    class _Out:
        encoding = "cp1252"

        def flush(self):
            pass

    seen = {}

    def _input(prompt=""):
        seen["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(T.sys, "stdout", _Out())
    monkeypatch.setattr("builtins.input", _input)
    assert T.safe_input("Enter λ for 2θ: ") == "ok"
    assert "θ" not in seen["prompt"]
    assert "λ" not in seen["prompt"] or "lambda" in seen["prompt"]


def test_install_safe_builtins_routes_print(monkeypatch):
    import builtins
    from batplot.plot_modes.common import terminal as T

    # Reset install flag for this test
    monkeypatch.setattr(T, "_safe_builtins_installed", False)
    orig = builtins.print
    try:
        T.install_safe_builtins()
        assert builtins.print is T.safe_console_print
        T.install_safe_builtins()  # idempotent
        assert builtins.print is T.safe_console_print
    finally:
        builtins.print = orig
        T._safe_builtins_installed = False


def test_wayland_grim_skipped_without_wayland_cursor_source(monkeypatch):
    import batplot.screen_color as sc

    monkeypatch.setattr(sc, "_is_wayland_session", lambda: True)
    monkeypatch.setattr(sc, "_last_cursor_source", "tk")
    monkeypatch.setattr(sc.shutil, "which", lambda name: "/usr/bin/grim" if name == "grim" else None)
    # Force empty attempts after grim gate → None
    monkeypatch.setattr(sc, "_read_image_file", lambda _p: None)
    assert sc._grab_region_linux(0, 0, 10, 10) is None


def test_session_helpers_pip_uses_create_no_window_on_windows(monkeypatch):
    import batplot.plot_modes.common.session_helpers as SH

    seen = {}

    class _Res:
        returncode = 1
        stdout = ""

    def _run(cmd, **kwargs):
        seen["kwargs"] = kwargs
        seen["cmd"] = cmd
        return _Res()

    monkeypatch.setattr(SH.sys, "platform", "win32")
    monkeypatch.setattr(SH.subprocess, "run", _run)

    class _NP:
        @property
        def __version__(self):
            raise RuntimeError("force pip path")

    monkeypatch.setattr(SH, "np", _NP())
    out = SH._get_current_numpy_version()
    assert out == "unknown"
    assert "pip" in " ".join(seen.get("cmd") or [])
    assert "creationflags" in seen.get("kwargs", {})


def test_version_check_cache_uses_utf8(tmp_path, monkeypatch):
    import batplot.version_check as VC
    import json

    cache = tmp_path / "version_check.json"
    monkeypatch.setattr(VC, "get_cache_file", lambda: cache)
    monkeypatch.setattr(VC, "get_latest_version", lambda: None)
    monkeypatch.setattr(VC, "parse_version", lambda s: (1, 0, 0))
    VC.check_for_updates("1.0.0", force=True)
    assert cache.is_file()
    # Must be valid UTF-8 JSON
    json.loads(cache.read_text(encoding="utf-8"))