"""Interactive menu for histogram mode."""

from __future__ import annotations

import json
import os
import pickle
from typing import List

import numpy as np  # type: ignore[import]

from ..common.files import format_file_timestamp
from ..common.menu_rendering import append_last_action_shortcuts, print_menu_columns
from ..common.menus import run_option_menu
from ..common.terminal import colorize_prompt, safe_input
from ...ui import resize_canvas, resize_plot_frame
from .actions import (
    HistoActionContext,
    handle_figure_export,
    handle_quick_overwrite_figure,
    handle_quick_overwrite_session,
    handle_quick_overwrite_style,
    handle_save_session,
    handle_style_export,
    handle_style_import,
)
from .colors import run_histo_color_menu
from .labels import run_histo_rename_menu
from .density_curve import run_histo_density_curve_menu
from .fonts import run_histo_font_menu, sync_histo_font_rcparams
from .plot import HistoState, HistoStyle, apply_histo_geometry, refresh_histo_figure, sync_histo_geometry
from .spines import apply_histo_spine_snapshot, capture_histo_spine_snapshot
from .toggles import run_histo_toggle_menu
from .wizard import HistoSetup, run_histo_wizard


def _colorize_menu(text: str) -> str:
    if ":" not in text:
        return text
    cmd, desc = text.split(":", 1)
    return f"\033[96m{cmd.strip()}\033[0m: {desc.strip()}"


def _apply_style_file(fig, ax, state: HistoState, path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    restored = _restore_snapshot(payload)
    _apply_state(fig, ax, state, restored, snap=payload)


def _histo_action_context(
    fig,
    ax,
    state: HistoState,
    *,
    push_state,
    pop_undo,
) -> HistoActionContext:
    paths = [state.source_path] if state.source_path else []
    return HistoActionContext(
        fig=fig,
        ax=ax,
        state=state,
        source_file_paths=paths,
        safe_input=safe_input,
        colorize_prompt=colorize_prompt,
        format_file_timestamp=format_file_timestamp,
        push_state=push_state,
        pop_undo=pop_undo,
        save_session=lambda path: _save_session(fig, ax, state, path),
        export_style=lambda path: _export_style(fig, ax, state, path),
        export_figure=lambda path: _export_figure(fig, ax, path),
        apply_style_file=lambda path: _apply_style_file(fig, ax, state, path),
    )


def _print_histo_menu(fig, state: HistoState) -> None:
    bw = max(0.01, min(float(state.style.bar_width_frac), 1.0))
    col1 = ["c: colors", "f: font", "a: density curve", "t: toggle spines", "g: size"]
    col2 = [f"w: bar width ({bw:g})", "r: rename labels", "x: range/bins"]
    col3 = ["e: export figure", "p: export style", "i: import style", "s: save session", "b: undo", "q: quit"]
    append_last_action_shortcuts(col3, fig)
    print_menu_columns(
        title="Histogram Interactive Menu",
        columns=[("(Styles)", col1), ("(Geometries)", col2), ("(Options)", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _snapshot_state(state: HistoState, fig=None, ax=None) -> dict:
    snap = {
        "setup": {
            "column_index": state.setup.column_index,
            "column_name": state.setup.column_name,
            "values": np.asarray(state.setup.values, dtype=float),
            "xmin": state.setup.xmin,
            "xmax": state.setup.xmax,
            "bin_edges": np.asarray(state.setup.bin_edges, dtype=float),
        },
        "style": {
            "bar_color": state.style.bar_color,
            "edge_color": state.style.edge_color,
            "alpha": state.style.alpha,
            "bar_width_frac": state.style.bar_width_frac,
            "show_grid": state.style.show_grid,
            "density": state.style.density,
            "show_bar_labels": state.style.show_bar_labels,
            "show_mean_line": state.style.show_mean_line,
            "show_median_line": state.style.show_median_line,
            "show_density_curve": state.style.show_density_curve,
            "density_curve_color": state.style.density_curve_color,
            "density_curve_lw": state.style.density_curve_lw,
            "density_curve_ls": state.style.density_curve_ls,
            "density_curve_alpha": state.style.density_curve_alpha,
            "xlabel": state.style.xlabel,
            "ylabel": state.style.ylabel,
            "title": state.style.title,
            "top_xlabel": state.style.top_xlabel,
            "figsize": list(state.style.figsize),
            "axes_fraction": (
                list(state.style.axes_fraction) if state.style.axes_fraction is not None else None
            ),
            "font_family": state.style.font_family,
            "label_fontsize": state.style.label_fontsize,
            "title_fontsize": state.style.title_fontsize,
        },
        "source_path": state.source_path,
    }
    if fig is not None and ax is not None:
        snap.update(capture_histo_spine_snapshot(fig, ax))
    return snap


def _snapshot_for_json(state: HistoState, fig=None, ax=None) -> dict:
    snap = _snapshot_state(state, fig, ax)
    snap["setup"]["values"] = np.asarray(snap["setup"]["values"]).tolist()
    snap["setup"]["bin_edges"] = np.asarray(snap["setup"]["bin_edges"]).tolist()
    return snap


def _restore_snapshot(snap: dict) -> HistoState:
    s = snap["setup"]
    st = snap["style"]
    setup = HistoSetup(
        column_index=int(s["column_index"]),
        column_name=str(s["column_name"]),
        values=np.asarray(s["values"], dtype=float),
        xmin=float(s["xmin"]),
        xmax=float(s["xmax"]),
        bin_edges=np.asarray(s["bin_edges"], dtype=float),
    )
    style = HistoStyle(
        bar_color=st.get("bar_color", "#4C72B0"),
        edge_color=st.get("edge_color", "#1f1f1f"),
        alpha=float(st.get("alpha", 0.85)),
        bar_width_frac=float(st.get("bar_width_frac", 0.95)),
        show_grid=bool(st.get("show_grid", True)),
        density=bool(st.get("density", False)),
        show_bar_labels=bool(st.get("show_bar_labels", False)),
        show_mean_line=bool(st.get("show_mean_line", False)),
        show_median_line=bool(st.get("show_median_line", False)),
        show_density_curve=bool(st.get("show_density_curve", False)),
        density_curve_color=str(st.get("density_curve_color", "#c0392b")),
        density_curve_lw=float(st.get("density_curve_lw", 1.8)),
        density_curve_ls=str(st.get("density_curve_ls", "-")),
        density_curve_alpha=float(st.get("density_curve_alpha", 1.0)),
        xlabel=str(st.get("xlabel", "")),
        ylabel=str(st.get("ylabel", "")),
        title=str(st.get("title", "")),
        top_xlabel=str(st.get("top_xlabel", "")),
        figsize=tuple(st.get("figsize", [8.0, 5.5])),
        axes_fraction=(
            tuple(st["axes_fraction"])
            if isinstance(st.get("axes_fraction"), (list, tuple)) and len(st["axes_fraction"]) == 4
            else None
        ),
        label_fontsize=float(st.get("label_fontsize", 14.0)),
        title_fontsize=float(st.get("title_fontsize", 15.0)),
        font_family=str(st.get("font_family", "")),
    )
    return HistoState(setup=setup, style=style, source_path=str(snap.get("source_path", "")))


def _apply_state(fig, ax, state: HistoState, restored: HistoState, snap: dict | None = None) -> None:
    state.setup = restored.setup
    state.style = restored.style
    state.source_path = restored.source_path
    sync_histo_font_rcparams(state)
    if snap is not None:
        apply_histo_spine_snapshot(fig, ax, snap)
    apply_histo_geometry(fig, ax, state)
    refresh_histo_figure(fig, ax, state)
    fig.canvas.draw_idle()


def _noop_update_labels(*_args, **_kwargs) -> None:
    return None


def _run_histo_size_menu(fig, ax, state: HistoState, *, push_state) -> None:
    """Canvas vs plot-frame resize submenu (same pattern as XY/CPC)."""

    def _resize_frame() -> None:
        try:
            push_state()
            resize_plot_frame(fig, ax, [], [], type("Args", (), {"stack": False})(), _noop_update_labels)
            sync_histo_geometry(fig, ax, state)
            fig.canvas.draw_idle()
        except Exception as exc:
            print(f"Resize failed: {exc}")

    def _resize_canvas_cmd() -> None:
        try:
            push_state()
            resize_canvas(fig, ax)
            sync_histo_geometry(fig, ax, state)
            fig.canvas.draw_idle()
        except Exception as exc:
            print(f"Resize failed: {exc}")

    run_option_menu(
        prompt="Geom (p/c/q): ",
        options={
            "p": ("plot frame", _resize_frame),
            "c": ("canvas", _resize_canvas_cmd),
        },
        safe_input=safe_input,
        colorize_menu=_colorize_menu,
        colorize_prompt=colorize_prompt,
    )


def _save_session(fig, ax, state: HistoState, path: str) -> None:
    sync_histo_geometry(fig, ax, state)
    payload = {"kind": "histo", "version": 1, "state": _snapshot_state(state, fig, ax)}
    with open(path, "wb") as fh:
        pickle.dump(payload, fh)
    fig._last_session_save_path = os.path.abspath(path)  # type: ignore[attr-defined]


def _export_style(fig, ax, state: HistoState, path: str) -> None:
    sync_histo_geometry(fig, ax, state)
    payload = _snapshot_for_json(state, fig, ax)
    payload["kind"] = "histo_style"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    fig._last_style_export_path = os.path.abspath(path)  # type: ignore[attr-defined]


def _export_figure(fig, ax, path: str) -> None:
    _, ext = os.path.splitext(path)
    if ext.lower() == ".svg":
        fig_fc = fig.get_facecolor() if getattr(fig, "patch", None) is not None else None
        ax_fc = ax.get_facecolor() if getattr(ax, "patch", None) is not None else None
        try:
            if getattr(fig, "patch", None) is not None:
                fig.patch.set_alpha(0.0)
                fig.patch.set_facecolor("none")
            if getattr(ax, "patch", None) is not None:
                ax.patch.set_alpha(0.0)
                ax.patch.set_facecolor("none")
            fig.savefig(path, dpi=300, bbox_inches="tight", transparent=True, facecolor="none", edgecolor="none")
        finally:
            try:
                if fig_fc is not None and getattr(fig, "patch", None) is not None:
                    fig.patch.set_alpha(1.0)
                    fig.patch.set_facecolor(fig_fc)
            except Exception:
                pass
            try:
                if ax_fc is not None and getattr(ax, "patch", None) is not None:
                    ax.patch.set_alpha(1.0)
                    ax.patch.set_facecolor(ax_fc)
            except Exception:
                pass
    else:
        fig.savefig(path, dpi=300, bbox_inches="tight")
    fig._last_figure_export_path = os.path.abspath(path)  # type: ignore[attr-defined]


def histo_interactive_menu(fig, ax, state: HistoState, *, table_loader=None) -> None:
    """Run the histogram interactive command loop."""
    history: List[dict] = []
    pending_key: str | None = None

    def push_state() -> None:
        history.append(_snapshot_state(state, fig, ax))
        if len(history) > 40:
            history.pop(0)

    def pop_undo() -> None:
        if history:
            history.pop()

    push_state()

    sync_histo_geometry(fig, ax, state)
    history[-1] = _snapshot_state(state, fig, ax)

    while True:
        _print_histo_menu(fig, state)
        try:
            if pending_key is not None:
                cmd = pending_key
                pending_key = None
            else:
                cmd = safe_input(colorize_prompt("Press a key: "), cancel_on_interrupt=True).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        if not cmd:
            continue

        if cmd == "q":
            try:
                confirm = safe_input(
                    colorize_prompt(
                        "Quit interactive? Remember to save (e=export, s=save). Quit now? (y/n): "
                    ),
                    cancel_on_interrupt=True,
                ).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting interactive menu...")
                break
            if confirm == "y":
                break
            if confirm in ("e", "s"):
                pending_key = confirm
                continue
            continue

        if cmd == "b":
            if len(history) <= 1:
                print("No undo history.")
                continue
            history.pop()
            _apply_state(fig, ax, state, _restore_snapshot(history[-1]), snap=history[-1])
            continue

        if cmd == "c":
            run_histo_color_menu(
                fig=fig,
                ax=ax,
                get_bar_color=lambda: state.style.bar_color,
                set_bar_color=lambda c: setattr(state.style, "bar_color", c),
                get_edge_color=lambda: state.style.edge_color,
                set_edge_color=lambda c: setattr(state.style, "edge_color", c),
                push_state=push_state,
                refresh=lambda: refresh_histo_figure(fig, ax, state),
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "f":
            run_histo_font_menu(
                state=state,
                push_state=push_state,
                refresh=lambda: refresh_histo_figure(fig, ax, state),
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            fig.canvas.draw_idle()
            continue

        if cmd == "a":
            run_histo_density_curve_menu(
                state=state,
                push_state=push_state,
                refresh=lambda: refresh_histo_figure(fig, ax, state),
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            fig.canvas.draw_idle()
            continue

        if cmd == "g":
            _run_histo_size_menu(fig, ax, state, push_state=push_state)
            continue

        if cmd == "r":
            run_histo_rename_menu(
                fig=fig,
                ax=ax,
                state=state,
                push_state=push_state,
                refresh=lambda: refresh_histo_figure(fig, ax, state),
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "w":
            cur = max(0.01, min(float(state.style.bar_width_frac), 1.0))
            raw = safe_input(
                colorize_prompt(
                    f"Bar width fraction [{cur:g}] (0–1, fraction of bin width, blank=keep, q=cancel): "
                ),
                cancel_on_interrupt=True,
            ).strip()
            if raw.lower() == "q":
                continue
            if not raw:
                continue
            try:
                val = float(raw)
            except ValueError:
                print("Invalid bar width.")
                continue
            if val <= 0 or val > 1:
                print("Bar width must be between 0 and 1.")
                continue
            push_state()
            state.style.bar_width_frac = float(val)
            refresh_histo_figure(fig, ax, state)
            fig.canvas.draw_idle()
            print(f"Bar width set to {val:g}.")
            continue

        if cmd == "x":
            if table_loader is None:
                print("Range/bin editor needs the source table (internal error).")
                continue
            table = table_loader()
            new_setup = run_histo_wizard(
                table,
                fixed_col=state.setup.column_index,
            )
            if new_setup is None:
                print("Canceled.")
                continue
            push_state()
            state.setup = new_setup
            refresh_histo_figure(fig, ax, state)
            fig.canvas.draw_idle()
            continue

        if cmd == "t":
            def _histo_toggle_display(key: str) -> None:
                if key == "g":
                    state.style.show_grid = not state.style.show_grid
                elif key == "d":
                    state.style.density = not state.style.density
                    state.style.ylabel = state.y_label_default()
                elif key == "n":
                    state.style.show_bar_labels = not state.style.show_bar_labels
                elif key == "m":
                    state.style.show_mean_line = not state.style.show_mean_line
                    state.style.show_median_line = not state.style.show_median_line

            try:
                run_histo_toggle_menu(
                    fig=fig,
                    ax=ax,
                    state=state,
                    push_state=push_state,
                    refresh=lambda: refresh_histo_figure(fig, ax, state),
                    safe_input=safe_input,
                    colorize_prompt=colorize_prompt,
                    colorize_menu=_colorize_menu,
                    toggle_display=_histo_toggle_display,
                )
            except Exception as exc:
                print(f"Error in toggle menu: {exc}")
            fig.canvas.draw_idle()
            continue

        if cmd == "e":
            handle_figure_export(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        if cmd == "p":
            handle_style_export(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        if cmd == "i":
            handle_style_import(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        if cmd == "s":
            handle_save_session(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        if cmd == "oe":
            handle_quick_overwrite_figure(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        if cmd == "os":
            handle_quick_overwrite_session(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        if cmd in ("ops", "opsg"):
            handle_quick_overwrite_style(_histo_action_context(fig, ax, state, push_state=push_state, pop_undo=pop_undo))
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["histo_interactive_menu"]
