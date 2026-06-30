"""Tests for Matplotlib backend selection (interactive vs headless)."""

from __future__ import annotations

import os
import types

import pytest

from batplot._mpl_backend import (
    ensure_gui_backend,
    is_interactive_backend,
    wants_interactive_window,
)


def _args(**kwargs):
    defaults = {
        "all": None,
        "interactive": False,
        "canvas": False,
        "savefig": False,
        "out": None,
        "files": [],
        "operando": False,
        "contour": False,
        "gc": False,
        "cv": False,
        "dqdv": False,
        "cpc": False,
        "epc": False,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_wants_interactive_for_pkl():
    assert wants_interactive_window(_args(files=["session.pkl"])) is True


def test_wants_interactive_for_gc_with_i():
    assert wants_interactive_window(_args(gc=True, interactive=True)) is True


def test_wants_not_interactive_for_gc_with_out():
    assert wants_interactive_window(_args(gc=True, out="plot.png")) is False


def test_wants_not_interactive_for_batch_all():
    assert wants_interactive_window(_args(gc=True, all=True, interactive=True)) is False


def test_wants_interactive_for_canvas():
    assert wants_interactive_window(_args(canvas=True, files=["a.pkl", "b.pkl"])) is True


@pytest.mark.parametrize(
    "flags",
    [
        {"operando": True},
        {"contour": True},
        {"cv": True},
        {"dqdv": True},
        {"cpc": True},
        {"epc": True},
    ],
)
def test_wants_interactive_for_mode_flags(flags):
    assert wants_interactive_window(_args(**flags)) is True


def test_ensure_gui_respects_agg_under_pytest():
    """When pytest loaded conftest (MPLBACKEND=Agg), stay headless."""
    assert os.environ.get("MPLBACKEND", "").lower() == "agg"
    assert wants_interactive_window(_args(gc=True, interactive=True)) is True
    ok = ensure_gui_backend(_args(gc=True, interactive=True))
    assert ok is False
    assert not is_interactive_backend()


def test_ensure_gui_overrides_env_agg_when_not_headless(monkeypatch):
    """Inherited MPLBACKEND=Agg must not block --i outside CI/pytest."""
    import batplot._mpl_backend as mb

    monkeypatch.setenv("MPLBACKEND", "Agg")
    monkeypatch.setattr(mb, "_headless_context", lambda: False)
    monkeypatch.setattr(mb, "_USER_SET_MPLBACKEND", True)
    mb._mpl.use("Agg", force=True)

    args = _args(gc=True, interactive=True)
    assert mb.wants_interactive_window(args) is True
    ok = mb.ensure_gui_backend(args)
    assert ok is True
    assert mb.is_interactive_backend()


def test_ensure_gui_does_not_switch_for_headless_export(monkeypatch):
    import batplot._mpl_backend as mb

    monkeypatch.setattr(mb, "_headless_context", lambda: False)
    mb._mpl.use("Agg", force=True)
    ok = mb.ensure_gui_backend(_args(gc=True, out="plot.png"))
    assert ok is False
    assert not is_interactive_backend()
