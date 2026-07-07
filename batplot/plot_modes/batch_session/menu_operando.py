"""Batch interactive menu for operando+EC sessions."""

from __future__ import annotations

import json
import os
from typing import List

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...batch import _load_style_file
from ...session import dump_operando_session
from ..common.files import confirm_previous_path
from ..common.menu_rendering import print_menu_columns
from ..common.terminal import colorize_prompt, prompt_float, safe_input
from ..operando.style import build_operando_ec_style_config_v2
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
from .load import OperandoPanel


def _colorize_menu(text: str) -> str:
    if ":" not in text:
        return text
    cmd, desc = text.split(":", 1)
    return f"\033[96m{cmd.strip()}\033[0m: {desc.strip()}"


def _print_operando_batch_menu(panels: List[OperandoPanel]) -> None:
    col1 = ["f: font", "g: canvas size", "oc: colormap"]
    col2 = ["or: rename operando labels"]
    col3 = ["p: export style", "i: import style", "s: save sessions", "s all: save all", "b: undo", "q: quit"]
    append_batch_io_shortcuts(col3, panels)
    print_menu_columns(
        title=f"Batch Operando Menu ({len(panels)} plots)",
        columns=[("(Styles)", col1), ("(Geometries)", col2), ("(I/O)", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _capture_panel(panel: OperandoPanel) -> dict:
    cfg, _ext = build_operando_ec_style_config_v2(
        panel.fig, panel.ax, panel.im, panel.cbar, panel.ec_ax, "psg"
    )
    return cfg


def _apply_operando_cfg(panel: OperandoPanel, cfg: dict) -> None:
    kind = cfg.get("kind", "")
    if kind and kind not in ("operando_ec_style", "operando_ec_style_geom"):
        print(f"Skipping incompatible style kind: {kind}")
        return
    font = cfg.get("font") or {}
    if font.get("size") is not None:
        plt.rcParams["font.size"] = font["size"]
    if font.get("family"):
        fam = font["family"]
        plt.rcParams["font.sans-serif"] = [fam] if isinstance(fam, str) else list(fam)
    fig_cfg = cfg.get("figure") or {}
    size = fig_cfg.get("size") or fig_cfg.get("canvas_size")
    if size and len(size) >= 2:
        panel.fig.set_size_inches(float(size[0]), float(size[1]), forward=True)
    op = cfg.get("operando") or {}
    cmap = op.get("colormap")
    if cmap:
        try:
            panel.im.set_cmap(str(cmap))
            panel.im._operando_cmap_name = str(cmap)  # type: ignore[attr-defined]
        except Exception:
            pass
    geom = cfg.get("axes_geometry") or {}
    if geom.get("xlabel") is not None:
        panel.ax.set_xlabel(str(geom.get("xlabel", "")))
    if geom.get("ylabel") is not None:
        panel.ax.set_ylabel(str(geom.get("ylabel", "")))
    if geom.get("xlim") and len(geom["xlim"]) == 2:
        panel.ax.set_xlim(geom["xlim"])
    if geom.get("ylim") and len(geom["ylim"]) == 2:
        panel.ax.set_ylim(geom["ylim"])


def _restore_panel(panel: OperandoPanel, cfg: dict) -> None:
    _apply_operando_cfg(panel, cfg)
    try:
        panel.fig.canvas.draw_idle()
    except Exception:
        pass


def _save_operando_panel(panel: OperandoPanel, path: str) -> None:
    dump_operando_session(
        path,
        fig=panel.fig,
        ax=panel.ax,
        im=panel.im,
        cbar=panel.cbar,
        ec_ax=panel.ec_ax,
        skip_confirm=True,
    )


def run_operando_batch_menu(panels: List[OperandoPanel]) -> None:
    print_batch_header("operando_ec", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_operando_batch_menu(panels)
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
            w = prompt_float(safe_input, "Canvas width (inches): ", on_error="Invalid width.")
            h = prompt_float(safe_input, "Canvas height (inches): ", on_error="Invalid height.")
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
                for ax in (p.ax, p.ec_ax, p.cbar.ax if p.cbar is not None else None):
                    if ax is None:
                        continue
                    for lbl in (getattr(ax, "xaxis", None), getattr(ax, "yaxis", None)):
                        if lbl is None:
                            continue
                        try:
                            lbl.label.set_fontsize(fs)
                        except Exception:
                            pass
            draw_panels(panels)
            continue

        if cmd == "oc":
            cmap = safe_input("Colormap name (q=cancel): ", cancel_on_interrupt=True).strip()
            if not cmap or cmap.lower() == "q":
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                try:
                    p.im.set_cmap(cmap)
                    p.im._operando_cmap_name = cmap  # type: ignore[attr-defined]
                except Exception as exc:
                    print(f"Colormap failed: {exc}")
            draw_panels(panels)
            continue

        if cmd == "or":
            xl = safe_input("Operando X label (blank=keep, q=cancel): ", cancel_on_interrupt=True).strip()
            if xl.lower() == "q":
                continue
            yl = safe_input("Operando Y label (blank=keep, q=cancel): ", cancel_on_interrupt=True).strip()
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
                path_prompt="Import operando style path (.bps/.bpsg, q=cancel): ",
                load_style=lambda path: _load_style_file(path) or None,
                apply_style=lambda panel, cfg: _apply_operando_cfg(panel, cfg),
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

            def _export_operando_panel(panel: OperandoPanel, out: str) -> None:
                cfg, _ = build_operando_ec_style_config_v2(
                    panel.fig, panel.ax, panel.im, panel.cbar, panel.ec_ax, sub
                )
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(cfg, fh, indent=2)
                panel.fig._last_style_export_path = os.path.abspath(out)  # type: ignore[attr-defined]

            run_batch_export_style(
                panels,
                _export_operando_panel,
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
                try:
                    cfg, _kind = build_operando_ec_style_config_v2(
                        source.fig, source.ax, source.im, source.cbar, source.ec_ax,
                        "psg" if cmd == "opsg" else "ps",
                    )
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(cfg, fh, indent=2)
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s all":
            run_batch_save_all(panels, lambda p: _save_operando_panel(p, p.path))
            continue

        if cmd == "s":
            run_batch_save_sessions(panels, lambda p: _save_operando_panel(p, p.path))
            continue

        if cmd == "os":
            run_batch_overwrite_sessions(panels, _save_operando_panel)
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_operando_batch_menu"]
