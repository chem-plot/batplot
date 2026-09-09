"""Integration: applied hex colors match what p/i/s/b dump/restore rely on."""

from __future__ import annotations

from matplotlib.colors import to_hex
import matplotlib.pyplot as plt

from batplot.plotting import apply_curve_color
from batplot.color_utils import add_user_color, get_user_color_list, resolve_color_token


def test_apply_curve_color_syncs_markers():
    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [0, 1], "o-", color="blue")
    apply_curve_color(ln, "#aa1122")
    assert to_hex(ln.get_color()).lower() == "#aa1122"
    assert to_hex(ln.get_markerfacecolor()).lower() == "#aa1122"
    assert to_hex(ln.get_markeredgecolor()).lower() == "#aa1122"
    plt.close(fig)


def test_session_style_dumps_get_color_hex():
    """Session/style writers persist ln.get_color() — eyedropper must land there."""
    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [1, 0], color="green")
    picked = "#c0ffee"
    apply_curve_color(ln, picked)
    dumped = to_hex(ln.get_color()).lower()
    assert dumped == picked
    # Simulate style restore used by i / session load
    apply_curve_color(ln, "#111111")
    apply_curve_color(ln, dumped)
    assert to_hex(ln.get_color()).lower() == picked
    plt.close(fig)


def test_user_colors_missing_key_is_empty(tmp_path, monkeypatch):
    """Old installs / empty config: no user_colors key → []."""
    monkeypatch.setattr(
        "batplot.config.get_config_dir",
        lambda: tmp_path / ".batplot",
    )
    (tmp_path / ".batplot").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".batplot" / "config.json").write_text("{}", encoding="utf-8")
    assert get_user_color_list(None) == []


def test_saved_user_color_index_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "batplot.config.get_config_dir",
        lambda: tmp_path / ".batplot",
    )
    (tmp_path / ".batplot").mkdir(parents=True, exist_ok=True)
    added = add_user_color("#abcdef", None)
    assert "#abcdef" in added
    idx = added.index("#abcdef") + 1
    assert resolve_color_token(str(idx), None).lower() == "#abcdef"
    assert resolve_color_token(f"u{idx}", None).lower() == "#abcdef"


def test_resolve_hex_without_palette():
    assert resolve_color_token("#00ff00", None).lower() == "#00ff00"
