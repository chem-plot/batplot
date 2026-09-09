"""Old EC sessions must use the same three color modes as new plots.

After load (including pickles without ``visible_cycles`` / with str cycle keys),
typing ``1 2`` assigns palette 2 (Set2) to cycle 1 — same as a fresh figure.
"""

from __future__ import annotations

import pickle

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from batplot import session as S
from batplot.color_utils import clear_blank_color_input_guard
from batplot.plot_modes.electrochem import colors as ECY
from batplot.plot_modes.electrochem.style import _get_style_snapshot
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config
from conftest import loaded


def _menu_kwargs(fig, ax, cycle_lines, feeds, *, file_data=None, is_multi_file=False):
    return dict(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=file_data or [],
        current_file_idx=0,
        all_cycles=sorted(cycle_lines.keys()),
        is_multi_file=is_multi_file,
        is_dqdv=False,
        menu_title="EC",
        canvas_mode=False,
        print_file_list=lambda *_a, **_k: None,
        print_menu=lambda *_a, **_k: None,
        colorize_menu=lambda s: s,
        colorize_inline_commands=lambda s: s,
        colorize_prompt=lambda s: s,
        safe_input=lambda *_a, **_k: next(feeds),
        push_state=lambda *_a, **_k: None,
        parse_fall_cycles_tokens=ECY._parse_fall_cycles_tokens,
        parse_per_file_cycle_tokens=ECY._parse_per_file_cycle_tokens,
        parse_file_palette_tokens=ECY._parse_file_palette_tokens,
        parse_cycle_tokens=ECY._parse_cycle_tokens,
        set_visible_cycles=ECY._set_visible_cycles,
        apply_colors=ECY._apply_colors,
        apply_curve_linewidth=ECY._apply_curve_linewidth,
        apply_stored_smooth_settings=lambda *_a, **_k: None,
        apply_display_mode=lambda *_a, **_k: None,
        rebuild_legend=lambda *_a, **_k: None,
        apply_nice_ticks=lambda: None,
    )


def _dump_legacy_single(session_path, *, cycles=(1, 2, 31)):
    fig, ax = plt.subplots()
    cl = {}
    for cyc in cycles:
        ch, = ax.plot(np.linspace(0, 1, 5), np.linspace(0, float(cyc), 5), color="#000000")
        di, = ax.plot(np.linspace(0, 1, 5), np.linspace(float(cyc), 0, 5), color="#000000")
        cl[int(cyc)] = {"charge": ch, "discharge": di}
    ECY._set_visible_cycles(cl, list(cycles))
    p = session_path("gc_legacy_str_keys.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cl, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    # Simulate oldest pickles: no visible_cycles key, string cycle keys
    sess.pop("visible_cycles", None)
    sess["lines"] = {str(k): v for k, v in sess["lines"].items()}
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)
    plt.close(fig)
    return p


def test_old_session_mode1_one_two_is_cycle1_palette2(session_path):
    p = _dump_legacy_single(session_path)
    fig, ax, cl = loaded(S.load_ec_session(p))[:3]
    assert set(cl.keys()) == {1, 2, 31}
    assert all(isinstance(k, int) for k in cl.keys())

    clear_blank_color_input_guard()
    feeds = iter(["1 2", "q"])
    ECY.run_ec_cycles_menu(**_menu_kwargs(fig, ax, cl, feeds))

    assert cl[1]["charge"].get_visible() is True
    assert cl[2]["charge"].get_visible() is False
    assert cl[31]["charge"].get_visible() is False
    c1 = mcolors.to_hex(cl[1]["charge"].get_color()).lower()
    assert c1 != "#000000"
    # Set2 first sample is not black; palette mode applied
    mode, cycles, _m, palette, use_all = ECY._parse_cycle_tokens(["1", "2"])
    assert mode == "palette" and cycles == [1] and palette == "Set2" and use_all is False
    plt.close(fig)


def test_old_session_mode2_colon_and_mode3_all_palette(session_path):
    p = _dump_legacy_single(session_path)
    fig, ax, cl = loaded(S.load_ec_session(p))[:3]
    clear_blank_color_input_guard()

    feeds = iter(["1:#00ff00 31:#ff00ff", "q"])
    ECY.run_ec_cycles_menu(**_menu_kwargs(fig, ax, cl, feeds))
    assert mcolors.to_hex(cl[1]["charge"].get_color()).lower() == "#00ff00"
    assert mcolors.to_hex(cl[31]["charge"].get_color()).lower() == "#ff00ff"
    assert cl[1]["charge"].get_visible() is True
    assert cl[31]["charge"].get_visible() is True
    assert cl[2]["charge"].get_visible() is False

    # Show all again then mode 3
    ECY._set_visible_cycles(cl, [1, 2, 31])
    for cyc in (1, 2, 31):
        ECY._apply_colors(cl, {cyc: "#000000"})
    feeds = iter(["all 3", "q"])
    ECY.run_ec_cycles_menu(**_menu_kwargs(fig, ax, cl, feeds))
    assert mcolors.to_hex(cl[1]["charge"].get_color()).lower() != "#000000"
    assert cl[1]["charge"].get_visible() is True
    assert cl[2]["charge"].get_visible() is True
    assert cl[31]["charge"].get_visible() is True
    plt.close(fig)


def test_old_session_style_pisb_after_mode1(session_path):
    """After ``1 2`` on a legacy load, p/i/s/b cycle_styles round-trip the color."""
    p = _dump_legacy_single(session_path)
    fig, ax, cl = loaded(S.load_ec_session(p))[:3]
    clear_blank_color_input_guard()
    feeds = iter(["1 2", "q"])
    ECY.run_ec_cycles_menu(**_menu_kwargs(fig, ax, cl, feeds))
    c_before = mcolors.to_hex(cl[1]["charge"].get_color()).lower()

    tick_state = {"bx": True, "tx": False, "ly": True, "ry": False}
    cfg = _get_style_snapshot(fig, ax, cl, tick_state)
    assert "1" in cfg["cycle_styles"]
    ECY._apply_colors(cl, {1: "#111111"})
    ok = apply_ec_style_config(
        cfg, fig=fig, ax=ax, cycle_lines=cl, file_data=None, tick_state=tick_state, silent=True
    )
    assert ok is True
    assert mcolors.to_hex(cl[1]["charge"].get_color()).lower() == c_before
    plt.close(fig)


def test_old_multifile_session_stamps_selected_cycles(session_path):
    fig, ax = plt.subplots()
    file_data = []
    for name in ("A", "B"):
        cl = {}
        for cyc in (1, 2, 31):
            ch, = ax.plot([0, 1], [0, 1], color="#000000")
            di, = ax.plot([0, 1], [1, 0], color="#000000")
            cl[cyc] = {"charge": ch, "discharge": di}
        ECY._set_visible_cycles(cl, [1, 31])
        file_data.append({
            "filename": f"{name}.csv",
            "display_name": name,
            "filepath": f"{name}.csv",
            "visible": True,
            "cycle_lines": cl,
        })
    p = session_path("gc_legacy_mf.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines={}, file_data=file_data, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    for f in sess["file_data"]:
        f.pop("visible_cycles", None)
        f["lines"] = {str(k): v for k, v in f["lines"].items()}
    sess.pop("visible_cycles", None)
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)
    plt.close(fig)

    _fig2, _ax2, _cl, fd2 = loaded(S.load_ec_session(p))
    for f in fd2:
        assert f.get("selected_cycles") == [1, 31]
        assert all(isinstance(k, int) for k in f["cycle_lines"].keys())

    # Same as after multi-file picker: single-file menu on that file's lines
    f0 = fd2[0]
    clear_blank_color_input_guard()
    feeds = iter(["1 2", "q"])
    ECY.run_ec_cycles_menu(
        **_menu_kwargs(
            _fig2, _ax2, f0["cycle_lines"], feeds, file_data=fd2, is_multi_file=False
        )
    )
    assert f0["cycle_lines"][1]["charge"].get_visible() is True
    assert f0["cycle_lines"][2]["charge"].get_visible() is False
    assert f0["selected_cycles"] == [1]
    assert mcolors.to_hex(f0["cycle_lines"][1]["charge"].get_color()).lower() != "#000000"
    plt.close(_fig2)
