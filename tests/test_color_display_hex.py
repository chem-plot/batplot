"""All interactive color listings should show a cube + lowercase hex."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.color_utils import (
    format_color_listing,
    resolve_color_token,
    to_display_hex,
)


def test_to_display_hex_named_and_rgba():
    assert to_display_hex("red") == "#ff0000"
    assert to_display_hex("#00FF00") == "#00ff00"
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], color="C0")
    hx = to_display_hex(ax.lines[0].get_color())
    assert hx is not None and hx.startswith("#") and len(hx) == 7
    plt.close(fig)


def test_format_color_listing_always_hex_with_swatch():
    listing = format_color_listing("blue")
    assert "#0000ff" in listing
    # ANSI truecolor cube prefix
    assert "\033[48;2;" in listing
    listing_none = format_color_listing(None)
    assert "--" in listing_none


def test_resolve_color_token_returns_hex():
    assert resolve_color_token("red") == "#ff0000"
    assert resolve_color_token("#00FF00") == "#00ff00"
    hx = resolve_color_token("#0f0")
    assert hx == "#00ff00"


def test_operando_new_cif_default_color_is_hex():
    from batplot.plot_modes.operando.plot import load_operando_cif_entry
    from pathlib import Path

    cif = Path("/Users/tiandai/Downloads/ICSD_CollCode60433.cif")
    if not cif.is_file():
        return
    entry, _hkl = load_operando_cif_entry(
        str(cif),
        axis_mode="Q",
        default_wl=0.709,
        qmax_sim=5.0,
        color_index=0,
        wl_override=None,
    )
    col = entry[-1]
    assert isinstance(col, str) and col.startswith("#") and len(col) == 7
