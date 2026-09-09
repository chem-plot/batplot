"""Label shortcut conversion, recent-name reflection, and rename math help."""

from __future__ import annotations

import batplot.config as CFG
from batplot.utils import (
    convert_label_shortcuts,
    finalize_axis_label_text,
    print_label_math_help,
    print_recent_axis_names,
    remember_axis_name,
    resolve_recent_axis_name,
)


def test_convert_sub_super_italic_and_greek():
    assert convert_label_shortcuts("g{super(-1)}") == r"g$^{\mathrm{-1}}$"
    assert convert_label_shortcuts("Li{sub(2)}O") == r"Li$_{\mathrm{2}}$O"
    assert convert_label_shortcuts("{italic(Fe)}") == r"$\mathit{Fe}$"
    assert convert_label_shortcuts("{alpha}-{beta}") == r"$\alpha$-$\beta$"
    assert convert_label_shortcuts("2{theta} ({deg})") == r"2$\theta$ ($^{\circ}$)"
    assert convert_label_shortcuts("{AA}") == r"$\mathrm{\AA}$"
    # Already-converted mathtext is idempotent.
    assert finalize_axis_label_text(r"Li$_{\mathrm{2}}$O") == r"Li$_{\mathrm{2}}$O"


def test_remember_axis_name_stores_converted_shortcuts():
    remember_axis_name("Capacity (mAh g{super(-1)})", mode="xy")
    names = CFG.get_recent_axis_names(mode="xy")
    assert names[0] == r"Capacity (mAh g$^{\mathrm{-1}}$)"


def test_print_recent_shows_shortcut_arrow_for_legacy_raw(capsys):
    # Simulate an old config entry that still stores raw shortcuts.
    CFG.save_config(
        {
            "recent_axis_names_by_mode": {
                "ec": ["Li{sub(2)}O"],
            }
        }
    )
    print_recent_axis_names(mode="ec")
    out = capsys.readouterr().out
    assert "Li{sub(2)}O" in out
    assert r"Li$_{\mathrm{2}}$O" in out


def test_resolve_recent_finalizes_legacy_raw():
    CFG.save_config({"recent_axis_names_by_mode": {"cpc": ["g{super(-1)}"]}})
    picked = resolve_recent_axis_name("1", mode="cpc")
    assert picked == r"g$^{\mathrm{-1}}$"


def test_print_label_math_help_lists_sub_super(capsys):
    print_label_math_help()
    out = capsys.readouterr().out
    assert "{sub(" in out
    assert "{super(" in out
    assert "{alpha}" in out
    assert "{italic(" in out


def test_cpc_style_apply_finalizes_legacy_shortcut_labels():
    import matplotlib.pyplot as plt
    from batplot.plot_modes.cpc.style import _apply_style

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_d = ax.scatter([1], [2])
    sc_e = ax2.scatter([1], [90])
    cfg = {
        "kind": "cpc_style",
        "axis_labels": {
            "xlabel": "Cycle",
            "ylabel_left": "Cap (mAh g{super(-1)})",
            "ylabel_right": "CE (%)",
        },
        "grid": False,
        "display_mode": "both",
        "series": {
            "charge": {"color": "#111111", "alpha": 1.0, "hollow": False, "markersize": 36},
            "discharge": {"color": "#222222", "alpha": 1.0, "hollow": False, "markersize": 36},
            "efficiency": {"color": "#333333", "alpha": 1.0, "hollow": False, "markersize": 36},
        },
    }
    try:
        _apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)
        assert ax.get_ylabel() == r"Cap (mAh g$^{\mathrm{-1}}$)"
    finally:
        plt.close(fig)


def test_xy_rename_menu_has_math_help_subkey(capsys):
    import matplotlib.pyplot as plt
    from batplot.plot_modes.xy.labels import run_xy_rename_menu

    fig, ax = plt.subplots()
    answers = iter(["m", "q"])
    run_xy_rename_menu(
        ax=ax,
        fig=fig,
        labels=["a"],
        label_text_objects=[ax.text(0, 0, "1: a")],
        args_files=[],
        get_cif_series=lambda: [],
        print_cif_phase_list=lambda cts: None,
        apply_cif_phase_label_rename=lambda i, s: None,
        position_top_xlabel=lambda: None,
        position_bottom_xlabel=lambda: None,
        position_right_ylabel=lambda: None,
        position_left_ylabel=lambda: None,
        sync_fonts=lambda: None,
        push_state=lambda note="": None,
        safe_input=lambda *a, **k: next(answers),
    )
    out = capsys.readouterr().out
    assert "{sub(" in out
    assert "{super(" in out
    plt.close(fig)
