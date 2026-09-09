"""CPC interactive add-file (a) and p/i/s/b persistence."""

from __future__ import annotations

import os
import pickle
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.cpc import session as CS
from batplot.plot_modes.cpc.add_file import (
    append_cpc_file,
    run_cpc_add_files_menu,
    trim_cpc_files_to_count,
)
from batplot.plot_modes.cpc.load import cpc_file_needs_mass, load_cpc_file_arrays
from batplot.plot_modes.cpc.menu import build_cpc_menu_columns, print_cpc_menu
from batplot.plot_modes.cpc.snapshots import push_cpc_state, restore_cpc_state
from batplot.plot_modes.cpc.style import _apply_style, _style_snapshot
from batplot.plot_modes.cpc.legend import _build_compact_cpc_legend


def _write_cpc_csv(path: Path, *, scale: float = 1.0) -> Path:
    lines = [
        "Cycle Index,Chg. Spec. Cap.(mAh/g),DChg. Spec. Cap.(mAh/g),Efficiency(%)",
        f"1,{100*scale},{98*scale},98",
        f"2,{99*scale},{97*scale},98",
        f"3,{98*scale},{96*scale},98",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _build_single_cpc(tmp_path: Path):
    p = _write_cpc_csv(tmp_path / "cell_a.csv")
    cyc, qchg, qdch, eff = load_cpc_file_arrays(str(p), is_epc=False)
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._cpc_is_epc = False  # type: ignore[attr-defined]
    sc_c = ax.scatter(cyc, qchg, c="C0", marker="s", s=50, label="Charge capacity")
    sc_d = ax.scatter(
        cyc, qdch, facecolors="none", edgecolors="C0", marker="s", s=50, label="Discharge capacity"
    )
    sc_e = ax2.scatter(cyc, eff, c="C1", marker="^", s=60, label="Coulombic efficiency")
    file_data = [{
        "filename": p.name,
        "display_name": p.name,
        "filepath": str(p.resolve()),
        "cyc_nums": cyc,
        "cap_charge": qchg,
        "cap_discharge": qdch,
        "eff": eff,
        "color": "C0",
        "eff_color": "C1",
        "visible": True,
        "sc_charge": sc_c,
        "sc_discharge": sc_d,
        "sc_eff": sc_e,
    }]
    fig._cpc_is_multi_file = False  # type: ignore[attr-defined]
    return fig, ax, ax2, file_data, p


def test_load_cpc_csv_arrays(tmp_path):
    p = _write_cpc_csv(tmp_path / "c.csv")
    cyc, qchg, qdch, eff = load_cpc_file_arrays(str(p))
    assert list(cyc) == [1.0, 2.0, 3.0]
    assert qchg[0] == pytest.approx(100.0)
    assert qdch[0] == pytest.approx(98.0)
    assert not cpc_file_needs_mass(str(p))


def test_mpt_needs_mass_and_errors_without(tmp_path):
    p = tmp_path / "cell.mpt"
    p.write_text("EC-Lab ASCII FILE\nNb header lines : 3\n\nmode\ttime/s\n", encoding="utf-8")
    assert cpc_file_needs_mass(str(p))
    with pytest.raises(ValueError, match="mass"):
        load_cpc_file_arrays(str(p), mass_mg=None, is_epc=False)


def test_append_inherits_marker_size_and_eff_visibility(tmp_path):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    file_data[0]["sc_eff"].set_visible(False)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=0.9)
    entry = append_cpc_file(fig, ax, ax2, file_data, str(p1))
    assert entry["sc_eff"].get_visible() is False
    assert float(entry["sc_charge"].get_sizes()[0]) == pytest.approx(50.0)
    assert float(entry["sc_eff"].get_sizes()[0]) == pytest.approx(60.0)
    plt.close(fig)


def test_append_preserves_hidden_legend(tmp_path):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    leg = ax.legend()
    leg.set_visible(False)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=0.9)
    append_cpc_file(fig, ax, ax2, file_data, str(p1))
    leg2 = ax.get_legend() or ax2.get_legend()
    assert leg2 is not None
    assert leg2.get_visible() is False
    plt.close(fig)


def test_compact_legend_uses_display_name(tmp_path):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=0.9)
    append_cpc_file(fig, ax, ax2, file_data, str(p1))
    _build_compact_cpc_legend(ax, ax2, file_data)
    leg = ax.get_legend() or ax2.get_legend()
    texts = [t.get_text() for t in leg.get_texts()] if leg else []
    joined = " ".join(texts)
    assert "cell_a" in joined or "cell_b" in joined
    assert ".csv" not in joined
    plt.close(fig)


def test_append_cpc_file_single_to_multi_and_session(tmp_path):
    fig, ax, ax2, file_data, p0 = _build_single_cpc(tmp_path)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=0.9)
    entry = append_cpc_file(fig, ax, ax2, file_data, str(p1))
    assert len(file_data) == 2
    assert entry["filepath"] == str(p1.resolve())
    assert fig._cpc_is_multi_file is True
    assert "(Chg)" in (file_data[0]["sc_charge"].get_label() or "")
    assert "(Chg)" in (file_data[1]["sc_charge"].get_label() or "")

    pkl = tmp_path / "cpc_add.pkl"
    CS.dump_cpc_session(
        str(pkl),
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=file_data[0]["sc_charge"],
        sc_discharge=file_data[0]["sc_discharge"],
        sc_eff=file_data[0]["sc_eff"],
        file_data=file_data,
        skip_confirm=True,
    )
    with open(pkl, "rb") as f:
        sess = pickle.load(f)
    assert len(sess.get("multi_files") or []) == 2
    assert sess["multi_files"][1].get("filepath")
    assert sess.get("is_epc") is False

    loaded = CS.load_cpc_session(str(pkl))
    assert loaded is not None
    fig2, ax_l, ax2_l, sc_c, sc_d, sc_e, fd = loaded
    assert fd is not None and len(fd) == 2
    assert bool(getattr(fig2, "_cpc_is_multi_file", False))
    plt.close(fig)
    plt.close(fig2)


def test_append_undo_trims_added_file(tmp_path):
    fig, ax, ax2, file_data, _p0 = _build_single_cpc(tmp_path)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=0.8)
    hist = []
    tick_state = {"bx": True, "ly": True, "ry": True, "tx": False}
    push_cpc_state(
        hist,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=file_data[0]["sc_charge"],
        sc_discharge=file_data[0]["sc_discharge"],
        sc_eff=file_data[0]["sc_eff"],
        file_data=file_data,
        tick_state=tick_state,
        note="pre-add",
    )
    assert hist[-1]["__cpc_n_files__"] == 1
    append_cpc_file(fig, ax, ax2, file_data, str(p1))
    assert len(file_data) == 2
    ok = restore_cpc_state(
        hist,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=file_data[0]["sc_charge"],
        sc_discharge=file_data[0]["sc_discharge"],
        sc_eff=file_data[0]["sc_eff"],
        file_data=file_data,
        tick_state=tick_state,
        update_ticks_func=lambda: None,
    )
    assert ok
    assert len(file_data) == 1
    assert fig._cpc_is_multi_file is False
    plt.close(fig)


def test_style_export_grows_with_added_file(tmp_path):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=1.1)
    append_cpc_file(fig, ax, ax2, file_data, str(p1))
    snap = _style_snapshot(
        fig, ax, ax2,
        file_data[0]["sc_charge"],
        file_data[0]["sc_discharge"],
        file_data[0]["sc_eff"],
        file_data,
    )
    assert len(snap.get("multi_files") or []) == 2
    assert snap["multi_files"][1].get("display_name")
    file_data[1]["visible"] = False
    _apply_style(
        fig, ax, ax2,
        file_data[0]["sc_charge"],
        file_data[0]["sc_discharge"],
        file_data[0]["sc_eff"],
        snap,
        file_data,
    )
    assert file_data[1]["visible"] is True
    plt.close(fig)


def test_add_menu_opens_picker_immediately(tmp_path, monkeypatch, capsys):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv")
    import batplot.plot_modes.cpc.add_file as AF

    monkeypatch.setattr(AF, "_ask_files_dialog", lambda **k: [str(p1)])

    run_cpc_add_files_menu(
        fig=fig,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        push_state=lambda _n: None,
        pop_undo=lambda: None,
        safe_input=lambda _p: "q",
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        print_menu=lambda *_a, **_k: None,
    )
    assert len(file_data) == 2
    out = capsys.readouterr().out
    assert "Added file" in out
    assert "Select CPC data file" in out
    plt.close(fig)


def test_add_menu_multi_select(tmp_path, monkeypatch):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    p1 = _write_cpc_csv(tmp_path / "cell_b.csv", scale=0.9)
    p2 = _write_cpc_csv(tmp_path / "cell_c.csv", scale=0.8)
    import batplot.plot_modes.cpc.add_file as AF

    monkeypatch.setattr(AF, "_ask_files_dialog", lambda **k: [str(p1), str(p2)])

    run_cpc_add_files_menu(
        fig=fig,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        push_state=lambda _n: None,
        pop_undo=lambda: None,
        safe_input=lambda _p: "q",
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        print_menu=lambda *_a, **_k: None,
    )
    assert len(file_data) == 3
    plt.close(fig)


def test_add_menu_mpt_requires_mass(tmp_path, monkeypatch):
    fig, ax, ax2, file_data, _ = _build_single_cpc(tmp_path)
    mpt = tmp_path / "cell.mpt"
    mpt.write_text("EC-Lab ASCII FILE\nNb header lines : 3\n\nx\n", encoding="utf-8")
    import batplot.plot_modes.cpc.add_file as AF

    monkeypatch.setattr(AF, "_ask_files_dialog", lambda **k: [str(mpt)])
    feeds = iter(["q"])  # cancel mass

    def _feed(_prompt=""):
        try:
            return next(feeds)
        except StopIteration:
            return "q"

    run_cpc_add_files_menu(
        fig=fig,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        push_state=lambda _n: None,
        pop_undo=lambda: None,
        safe_input=_feed,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        print_menu=lambda *_a, **_k: None,
    )
    assert len(file_data) == 1
    plt.close(fig)


def test_cpc_menu_prints_add_in_options(capsys):
    fig, ax = plt.subplots()
    print_cpc_menu(fig)
    out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "a: add file" in out
    cols = build_cpc_menu_columns(fig)
    # Options is column 3
    assert any(item.startswith("a:") for item in cols[2])
    assert not any(item.startswith("a:") for item in cols[1])
    plt.close(fig)


def test_trim_helper():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    a = ax.scatter([1], [1])
    b = ax.scatter([2], [2])
    c = ax2.scatter([1], [90])
    d = ax.scatter([3], [3])
    e = ax.scatter([4], [4])
    f = ax2.scatter([2], [91])
    fd = [
        {"sc_charge": a, "sc_discharge": b, "sc_eff": c, "filename": "a.csv", "display_name": "a"},
        {"sc_charge": d, "sc_discharge": e, "sc_eff": f, "filename": "b.csv", "display_name": "b"},
    ]
    trim_cpc_files_to_count(fig, ax, ax2, fd, 1, is_epc=False)
    assert len(fd) == 1
    plt.close(fig)
