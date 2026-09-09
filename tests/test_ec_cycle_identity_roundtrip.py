"""Cycle numbers must never be renumbered 1..N across select / save / load / style.

Guards the class of bug where selecting cycles 1 and 31 comes back as 1 and 2.
Trailing palette digits ``1``..``6`` are the last token for color mode 1; lists
whose last token is not a palette digit (e.g. ``1 31``) stay visibility-only.
Sessions persist an explicit ``visible_cycles`` id list.
"""

import pickle

import numpy as np
import matplotlib.pyplot as plt

from batplot import session as S
from batplot.plot_modes.electrochem import colors as ECY
from conftest import loaded


def test_parse_plain_cycle_list_not_eaten_by_palette_aliases():
    """Non-palette last token keeps cycle ids; trailing 1-6 is palette (mode 1)."""
    mode, cycles, _m, palette, use_all = ECY._parse_cycle_tokens(["1", "31"])
    assert mode == "numbers" and cycles == [1, 31] and palette is None and use_all is False

    # Last digit 1-6 = palette (color mode 1)
    mode, cycles, _m, palette, use_all = ECY._parse_cycle_tokens(["1", "2"])
    assert mode == "palette" and cycles == [1] and palette == "Set2"

    mode, cycles, _m, palette, use_all = ECY._parse_cycle_tokens(["1", "2", "3"])
    assert mode == "palette" and cycles == [1, 2] and palette == "Dark2"

    # Visibility of 1 and 2 without recolor: use a range alone
    mode, cycles, _m, palette, use_all = ECY._parse_cycle_tokens(["1-2"])
    assert mode == "numbers" and cycles == [1, 2] and palette is None


def test_parse_range_still_allows_trailing_numeric_palette():
    """Documented form ``2-30 1`` keeps working (range + palette 1/tab10)."""
    mode, cycles, _m, palette, use_all = ECY._parse_cycle_tokens(["2-30", "1"])
    assert mode == "palette"
    assert cycles[0] == 2 and cycles[-1] == 30
    assert palette == "tab10"
    assert use_all is False


def test_parse_trailing_named_or_digit_palette_after_plain_list():
    """Use digit ``2`` or name ``Set2`` — legacy ``p2`` is rejected."""
    mode, cycles, _m, palette, _u = ECY._parse_cycle_tokens(["1", "31", "2"])
    assert mode == "palette" and cycles == [1, 31] and palette == "Set2"
    mode, cycles, _m, palette, _u = ECY._parse_cycle_tokens(["1", "31", "Set2"])
    assert mode == "palette" and cycles == [1, 31] and palette == "Set2"
    mode, cycles, _m, palette, _u = ECY._parse_cycle_tokens(["1", "31", "p2"])
    assert mode == "numbers" and cycles == [1, 31] and palette is None


def test_set_visible_cycles_keeps_real_cycle_ids():
    fig, ax = plt.subplots()
    cl = {}
    for cyc in (1, 2, 31):
        (ln,) = ax.plot([0, 1], [0, float(cyc)], label=str(cyc))
        cl[cyc] = {"charge": ln, "discharge": None}
    ECY._set_visible_cycles(cl, [1, 31])
    assert cl[1]["charge"].get_visible() is True
    assert cl[2]["charge"].get_visible() is False
    assert cl[31]["charge"].get_visible() is True
    plt.close(fig)


def _build_multifile_gc(cycles=(1, 2, 30, 31)):
    fig, ax = plt.subplots()
    file_data = []
    for name in ("A", "B"):
        cl = {}
        for cyc in cycles:
            x = np.linspace(0.0, 50.0 + cyc, 40)
            y = np.linspace(3.0, 4.0, 40)
            ch, = ax.plot(x, y, label=f"{name}: {cyc}")
            dch, = ax.plot(x[::-1], y, label="_nolegend_")
            cl[int(cyc)] = {"charge": ch, "discharge": dch}
        file_data.append({
            "filename": f"{name}.csv",
            "display_name": name,
            "filepath": f"{name}.csv",
            "visible": True,
            "cycle_lines": cl,
        })
    return fig, ax, file_data


def test_ec_session_roundtrips_visible_cycles_1_and_31(session_path):
    fig, ax, file_data = _build_multifile_gc()
    for f in file_data:
        ECY._set_visible_cycles(f["cycle_lines"], [1, 31])

    p = session_path("gc_cycles_1_31.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines={}, file_data=file_data, skip_confirm=True)

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["multi_file"] is True
    for f in sess["file_data"]:
        assert f["visible_cycles"] == [1, 31]
        # Per-line flags must agree with the authoritative list
        assert f["lines"][1]["charge"]["style"]["visible"] is True
        assert f["lines"][31]["charge"]["style"]["visible"] is True
        assert f["lines"][2]["charge"]["style"]["visible"] is False

    _fig2, _ax2, _cl, fd2 = loaded(S.load_ec_session(p))
    for f in fd2:
        vis = sorted(
            cyc for cyc, parts in f["cycle_lines"].items()
            if parts["charge"] is not None and parts["charge"].get_visible()
        )
        assert vis == [1, 31], f"expected cycles 1 and 31 visible, got {vis}"
        assert f["cycle_lines"][31]["charge"].get_label().endswith(": 31")
        assert f["cycle_lines"][2]["charge"].get_visible() is False
    plt.close(fig)


def test_ec_old_session_without_visible_cycles_key_still_loads(session_path):
    """Backward compatible: old pickles rely on per-line style['visible']."""
    fig, ax, file_data = _build_multifile_gc()
    for f in file_data:
        ECY._set_visible_cycles(f["cycle_lines"], [1, 31])
    p = session_path("gc_old_no_visible_cycles.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines={}, file_data=file_data, skip_confirm=True)

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    for f in sess["file_data"]:
        f.pop("visible_cycles", None)
    sess.pop("visible_cycles", None)
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)

    _fig2, _ax2, _cl, fd2 = loaded(S.load_ec_session(p))
    for f in fd2:
        vis = sorted(
            cyc for cyc, parts in f["cycle_lines"].items()
            if parts["charge"] is not None and parts["charge"].get_visible()
        )
        assert vis == [1, 31]
    plt.close(fig)


def test_ec_session_visible_cycles_overrides_stale_line_flags(session_path):
    """If line flags drift, the stored visible_cycles list wins on load."""
    fig, ax, file_data = _build_multifile_gc()
    for f in file_data:
        ECY._set_visible_cycles(f["cycle_lines"], [1, 31])
    p = session_path("gc_stale_flags.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines={}, file_data=file_data, skip_confirm=True)

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    # Corrupt per-line flags: claim cycle 2 visible and 31 hidden
    for f in sess["file_data"]:
        f["lines"][2]["charge"]["style"]["visible"] = True
        f["lines"][2]["discharge"]["style"]["visible"] = True
        f["lines"][31]["charge"]["style"]["visible"] = False
        f["lines"][31]["discharge"]["style"]["visible"] = False
        # but keep authoritative list correct
        assert f["visible_cycles"] == [1, 31]
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)

    _fig2, _ax2, _cl, fd2 = loaded(S.load_ec_session(p))
    for f in fd2:
        vis = sorted(
            cyc for cyc, parts in f["cycle_lines"].items()
            if parts["charge"] is not None and parts["charge"].get_visible()
        )
        assert vis == [1, 31]
    plt.close(fig)


def test_fall_plain_list_keeps_cycle_2():
    """``fall:`` trailing digit 1-6 is palette; use ``fall:1-2`` for cycles 1–2."""
    cycles, palette = ECY._parse_fall_cycles_tokens(["fall:1", "2"], n_files=2)
    assert cycles == [1] and palette == "Set2"

    cycles, palette = ECY._parse_fall_cycles_tokens(["fall:1-2"], n_files=2)
    assert cycles == [1, 2] and palette is None

    cycles, palette = ECY._parse_fall_cycles_tokens(["fall:1", "31", "2"], n_files=2)
    assert cycles == [1, 31] and palette == "Set2"

    cycles, palette = ECY._parse_fall_cycles_tokens(["fall:1", "31", "p2"], n_files=2)
    assert cycles == [1, 31] and palette is None

    cycles, palette = ECY._parse_fall_cycles_tokens(["fall:2-30", "1"], n_files=2)
    assert cycles[0] == 2 and cycles[-1] == 30 and palette == "tab10"


def test_ec_style_roundtrips_visible_cycles_1_and_31():
    from batplot.plot_modes.electrochem.style import _get_style_snapshot
    from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config

    fig, ax, file_data = _build_multifile_gc()
    for f in file_data:
        ECY._set_visible_cycles(f["cycle_lines"], [1, 31])
    tick_state = {"bx": True, "tx": False, "ly": True, "ry": False}
    cfg = _get_style_snapshot(fig, ax, {}, tick_state, file_data=file_data)
    assert cfg["visible_cycles_per_file"] == [[1, 31], [1, 31]]

    # Corrupt live visibility, then re-apply style — ids must win.
    for f in file_data:
        ECY._set_visible_cycles(f["cycle_lines"], [1, 2])
    ok = apply_ec_style_config(
        cfg,
        fig=fig,
        ax=ax,
        cycle_lines={},
        file_data=file_data,
        is_multi_file=True,
        tick_state=tick_state,
        silent=True,
    )
    assert ok is True
    for f in file_data:
        vis = sorted(
            cyc for cyc, parts in f["cycle_lines"].items()
            if parts["charge"] is not None and parts["charge"].get_visible()
        )
        assert vis == [1, 31]
    plt.close(fig)
