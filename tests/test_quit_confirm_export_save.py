"""Quit confirm must accept e/s and route to export/save in every menu family."""

from __future__ import annotations

import pytest

from batplot.plot_modes.common.terminal import confirm_quit_interactive
from batplot.plot_modes.batch_session.batch_commands import batch_quit_confirm
from batplot.plot_modes.batch_session.batch_menu_io import batch_quit_or_save_all


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("y", "y"),
        ("Y", "y"),
        ("e", "e"),
        ("s", "s"),
        ("n", None),
        ("", None),
        ("nope", None),
    ],
)
def test_confirm_quit_interactive_accepts_export_save(monkeypatch, typed, expected):
    monkeypatch.setattr(
        "batplot.plot_modes.common.terminal.safe_input",
        lambda *_a, **_k: typed,
    )
    assert confirm_quit_interactive() == expected


def test_confirm_quit_interactive_prompt_lists_e_s_and_y_n_e_s(monkeypatch):
    seen = {}

    def _fake_input(prompt: str = "", **_k):
        seen["prompt"] = prompt
        return "n"

    assert confirm_quit_interactive(
        safe_input_fn=_fake_input,
        colorize_fn=lambda t: t,
    ) is None
    prompt = seen["prompt"]
    assert "e=export" in prompt
    assert "s=save" in prompt
    assert "(y/n/e/s)" in prompt


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("y", "y"),
        ("e", "e"),
        ("s", "s"),
        ("n", None),
    ],
)
def test_batch_quit_confirm_accepts_export_save(monkeypatch, typed, expected):
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *_a, **_k: typed,
    )
    assert batch_quit_confirm(allow_export=True) == expected


def test_batch_quit_or_save_all_returns_pending_keys(monkeypatch):
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_menu_io.batch_quit_confirm",
        lambda **_k: "e",
    )
    assert batch_quit_or_save_all([], lambda *_a: None) == "e"

    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_menu_io.batch_quit_confirm",
        lambda **_k: "s",
    )
    assert batch_quit_or_save_all([], lambda *_a: None) == "s"

    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_menu_io.batch_quit_confirm",
        lambda **_k: "y",
    )
    assert batch_quit_or_save_all([], lambda *_a: None) is True

    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_menu_io.batch_quit_confirm",
        lambda **_k: None,
    )
    assert batch_quit_or_save_all([], lambda *_a: None) is False


def test_batch_quit_confirm_save_all_alias_stays(monkeypatch):
    """Legacy 's all' is not a quit shortcut; stay in menu (use pending s instead)."""
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *_a, **_k: "s all",
    )
    assert batch_quit_confirm(allow_export=True) is None
