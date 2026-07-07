"""Batch interactive menu for EC sessions."""

from __future__ import annotations

import json
import os
from typing import List

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...batch import _apply_ec_style, _load_style_file
from ..common.files import confirm_previous_path
from ..common.menu_rendering import print_menu_columns
from ..common.terminal import colorize_prompt, prompt_float, safe_input
from ..electrochem.session import dump_ec_session
from ..electrochem.style import _get_geometry_snapshot, _get_style_snapshot
from .batch_commands import (
    append_batch_io_shortcuts,
    batch_quit_confirm,
    prompt_style_source_index,
    run_batch_overwrite_sessions,
    run_batch_save_all,
)
from .batch_io import (
    run_batch_export_style,
    run_batch_import_style,
    run_batch_save_sessions,
)
from .common import SyncUndoStacks, draw_panels, print_batch_header
from .load import EcPanel


def _colorize_menu(text: str) -> str:
    if ":" not in text:
        return text
    cmd, desc = text.split(":", 1)
    return f"\033[96m{cmd.strip()}\033[0m: {desc.strip()}"


def _default_tick_state() -> dict:
    return {
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
        "mbx": False,
        "mtx": False,
        "mly": False,
        "mry": False,
    }


def _tick_state_from_fig(fig) -> dict:
    wasd = getattr(fig, "_ec_wasd_state", None)
    if isinstance(wasd, dict):
        top = wasd.get("top", {})
        bot = wasd.get("bottom", {})
        left = wasd.get("left", {})
        right = wasd.get("right", {})
        return {
            "bx": bool(bot.get("ticks", True)),
            "tx": bool(top.get("ticks", False)),
            "ly": bool(left.get("ticks", True)),
            "ry": bool(right.get("ticks", False)),
            "mbx": bool(bot.get("minor", False)),
            "mtx": bool(top.get("minor", False)),
            "mly": bool(left.get("minor", False)),
            "mry": bool(right.get("minor", False)),
            "b_ticks": bool(bot.get("ticks", True)),
            "t_ticks": bool(top.get("ticks", False)),
            "l_ticks": bool(left.get("ticks", True)),
            "r_ticks": bool(right.get("ticks", False)),
            "b_labels": bool(bot.get("labels", True)),
            "t_labels": bool(top.get("labels", False)),
            "l_labels": bool(left.get("labels", True)),
            "r_labels": bool(right.get("labels", False)),
        }
    return _default_tick_state()


def _print_ec_batch_menu(panels: List[EcPanel]) -> None:
    col1 = ["f: font", "l: line width", "t: toggle spines", "g: figure size"]
    col2 = ["r: rename axis labels"]
    col3 = ["p: export style", "i: import style", "s: save sessions", "s all: save all", "b: undo", "q: quit"]
    append_batch_io_shortcuts(col3, panels)
    print_menu_columns(
        title=f"Batch EC Menu ({len(panels)} plots)",
        columns=[("(Styles)", col1), ("(Geometries)", col2), ("(I/O)", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _capture_panel(panel: EcPanel) -> dict:
    tick_state = _tick_state_from_fig(panel.fig)
    snap = _get_style_snapshot(
        panel.fig,
        panel.ax,
        panel.cycle_lines or {},
        tick_state,
        panel.file_data,
    )
    snap["kind"] = "ec_style_geom"
    snap["geometry"] = _get_geometry_snapshot(panel.fig, panel.ax)
    return snap


def _apply_cfg(panel: EcPanel, cfg: dict) -> None:
    _apply_ec_style(panel.fig, panel.ax, cfg)


def _restore_panel(panel: EcPanel, cfg: dict) -> None:
    _apply_cfg(panel, cfg)
    try:
        panel.fig.canvas.draw_idle()
    except Exception:
        pass


def _save_ec_panel(panel: EcPanel, path: str) -> None:
    dump_ec_session(
        path,
        fig=panel.fig,
        ax=panel.ax,
        cycle_lines=panel.cycle_lines or {},
        file_data=panel.file_data,
        skip_confirm=True,
    )


def run_ec_batch_menu(panels: List[EcPanel]) -> None:
    print_batch_header("ec_gc", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_ec_batch_menu(panels)
        try:
            if pending:
                cmd = pending
                pending = None
            else:
                cmd = safe_input(colorize_prompt("Press a key: "), cancel_on_interrupt=True).strip().lower()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue

        if cmd == "q":
            action = batch_quit_confirm(allow_export=True)
            if action == "y":
                break
            if action == "s":
                pending = "s"
            elif action == "s all":
                pending = "s all"
            continue

        if cmd == "b":
            undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
            draw_panels(panels)
            continue

        if cmd == "g":
            w = prompt_float(safe_input, "Figure width (inches): ", on_error="Invalid width.")
            h = prompt_float(safe_input, "Figure height (inches): ", on_error="Invalid height.")
            if w is None or h is None or w <= 0 or h <= 0:
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                p.fig.set_size_inches(w, h, forward=True)
            draw_panels(panels)
            continue

        if cmd == "f":
            fs = prompt_float(safe_input, "Font size: ", on_error="Invalid font size.")
            if fs is None or fs <= 0:
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            plt.rcParams["font.size"] = fs
            for p in panels:
                for lbl in (p.ax.xaxis.label, p.ax.yaxis.label, p.ax.title):
                    try:
                        lbl.set_fontsize(fs)
                    except Exception:
                        pass
            draw_panels(panels)
            continue

        if cmd == "l":
            lw = prompt_float(safe_input, "Line width for all curves: ", on_error="Invalid line width.")
            if lw is None or lw <= 0:
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                for ln in p.ax.lines:
                    try:
                        ln.set_linewidth(lw)
                    except Exception:
                        pass
            draw_panels(panels)
            continue

        if cmd == "t":
            sub = safe_input(colorize_prompt("Spine b/t/l/r (q=cancel): "), cancel_on_interrupt=True).strip().lower()
            if sub not in ("b", "t", "l", "r"):
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            side = {"b": "bottom", "t": "top", "l": "left", "r": "right"}[sub]
            for p in panels:
                sp = p.ax.spines.get(side)
                if sp is not None:
                    sp.set_visible(not sp.get_visible())
            draw_panels(panels)
            continue

        if cmd == "r":
            xl = safe_input("X label (blank=keep, q=cancel): ", cancel_on_interrupt=True).strip()
            if xl.lower() == "q":
                continue
            yl = safe_input("Y label (blank=keep, q=cancel): ", cancel_on_interrupt=True).strip()
            if yl.lower() == "q":
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                if xl:
                    p.ax.set_xlabel(xl)
                if yl:
                    p.ax.set_ylabel(yl)
            draw_panels(panels)
            continue

        if cmd == "i":
            run_batch_import_style(
                panels,
                path_prompt="Import style path (.bps/.bpsg, q=cancel): ",
                load_style=lambda path: _load_style_file(path) or None,
                apply_style=lambda panel, cfg: _apply_cfg(panel, cfg),
                prepare=lambda indices: undo.push_indices(
                    indices, [_capture_panel(panels[i]) for i in indices]
                ),
                on_applied=lambda indices, _path: (
                    draw_panels(panels),
                    print(
                        f"Applied style to plot(s) {', '.join(str(i + 1) for i in indices)}."
                    ),
                ),
            )
            continue

        if cmd == "p":
            sub = safe_input("Export ps=style, psg=style+geometry, q=cancel: ", cancel_on_interrupt=True).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            ext = ".bpsg" if sub == "psg" else ".bps"

            def _export_ec_panel(panel: EcPanel, out: str) -> None:
                cfg = _capture_panel(panel)
                cfg["kind"] = "ec_style_geom" if sub == "psg" else "ec_style"
                if sub == "ps":
                    cfg.pop("geometry", None)
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(cfg, fh, indent=2)
                panel.fig._last_style_export_path = os.path.abspath(out)  # type: ignore[attr-defined]

            run_batch_export_style(
                panels,
                _export_ec_panel,
                default_ext=ext,
                path_prompt_single="Export path (q=cancel): ",
                purpose=f"batch {sub} export",
            )
            continue

        if cmd in ("ops", "opsg"):
            src = prompt_style_source_index(panels)
            if src is None:
                continue
            source = panels[src]
            path = confirm_previous_path(
                source.fig,
                "_last_style_export_path",
                safe_input=safe_input,
                missing_message="No previous style export found.",
                missing_file_message="Previous export file not found: {path}",
                confirm_prompt="Overwrite '{basename}'? (y/n): ",
            )
            if path:
                cfg = _capture_panel(source)
                cfg["kind"] = "ec_style_geom" if cmd == "opsg" else "ec_style"
                if cmd == "ops":
                    cfg.pop("geometry", None)
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(cfg, fh, indent=2)
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s all":
            run_batch_save_all(panels, lambda p: _save_ec_panel(p, p.path))
            continue

        if cmd == "s":
            run_batch_save_sessions(panels, lambda p: _save_ec_panel(p, p.path))
            continue

        if cmd == "os":
            run_batch_overwrite_sessions(panels, _save_ec_panel)
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_ec_batch_menu"]
