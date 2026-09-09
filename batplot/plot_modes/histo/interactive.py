"""Interactive menu for histogram mode."""

from __future__ import annotations

import json
import os
import pickle
from typing import List

import numpy as np  # type: ignore[import]

from ..common.crosshair_export import savefig_without_crosshair
from ..common.files import format_file_timestamp
from ..common.menu_rendering import append_last_action_shortcuts, print_menu_columns, prompt_menu_key
from ..common.menus import run_option_menu
from ..common.terminal import colorize_prompt, safe_input
from ...ui import resize_canvas, resize_plot_frame
from ...utils import finalize_axis_label_text
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
from .line_style import run_histo_line_style_menu
from .fonts import run_histo_font_menu, sync_histo_font_rcparams
from .plot import HistoState, HistoStyle, apply_histo_geometry, normalize_histo_title, refresh_histo_figure, sync_histo_geometry
from .spines import apply_histo_spine_snapshot, capture_histo_spine_snapshot
from .toggles import run_histo_toggle_menu
from .wizard import HistoSetup, run_histo_wizard
from .y_range import run_histo_y_range_menu


def _colorize_menu(text: str) -> str:
    from ..common.menu_rendering import colorize_menu

    return colorize_menu(text)


def _apply_style_file(fig, ax, state: HistoState, path: str) -> bool:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    kind = payload.get("kind", "") if isinstance(payload, dict) else ""
    if kind and kind != "histo_style":
        print(f"Not a histogram style file (kind={kind!r}).")
        return False
    from .session import apply_histo_style_snapshot

    apply_histo_style_snapshot(fig, ax, state, payload)
    return True


def _histo_action_context(
    fig,
    ax,
    state: HistoState,
    *,
    push_state,
    pop_undo,
    restore_state=None,
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
        restore_state=restore_state,
        save_session=lambda path: _save_session(fig, ax, state, path),
        export_style=lambda path, include_geometry=True: _export_style(fig, ax, state, path, include_geometry=include_geometry),
        export_figure=lambda path: _export_figure(fig, ax, path),
        apply_style_file=lambda path: _apply_style_file(fig, ax, state, path),
    )


def _y_range_menu_label(state: HistoState) -> str:
    if state.style.ylim is not None:
        lo, hi = state.style.ylim
        return f"y: y range ({lo:g}–{hi:g})"
    return "y: y range (auto)"


def _print_histo_menu(fig, state: HistoState) -> None:
    bw = max(0.01, min(float(state.style.bar_width_frac), 1.0))
    col1 = ["c: colors", "f: font", "a: density curve", "l: lines/grid", "t: spines/ticks (+h display)", "g: size"]
    col2 = [f"w: bar width ({bw:g})", "r: rename labels", "x: range/bins", _y_range_menu_label(state)]
    col3 = ["e: export figure", "p: export style", "i: import style", "s: save session", "b: undo", "q: quit"]
    append_last_action_shortcuts(col3, fig)
    print_menu_columns(
        title="Histogram Interactive Menu",
        columns=[("Styles", col1), ("Geometries", col2), ("Options", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _ensure_histo_values_master(state: HistoState) -> np.ndarray:
    """Never-shrink full column backup on the live state object."""
    vals = np.asarray(state.setup.values, dtype=float)
    master = getattr(state, "_values_master", None)
    try:
        from ..common.session_data_guarantee import never_shrink_array

        master = never_shrink_array(master, vals)
    except Exception:
        master = np.array(vals, copy=True)
    try:
        state._values_master = master  # type: ignore[attr-defined]
    except Exception:
        pass
    return np.asarray(master, dtype=float)


def _snapshot_state(state: HistoState, fig=None, ax=None) -> dict:
    normalize_histo_title(state)
    # Live canvas/frame authority for s/b/p captures (mirrors export/save sync).
    if fig is not None and ax is not None:
        try:
            sync_histo_geometry(fig, ax, state)
        except Exception:
            pass
    values_master = _ensure_histo_values_master(state)
    snap = {
        "setup": {
            "column_index": state.setup.column_index,
            "column_name": state.setup.column_name,
            # Full column always — xmin/xmax only affect draw, never truncate values.
            "values": np.asarray(state.setup.values, dtype=float),
            "values_master": np.array(values_master, copy=True),
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
            "grid_linewidth": state.style.grid_linewidth,
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
            "font_weight": state.style.font_weight,
            "text_highlight": state.style.text_highlight,
            "text_highlight_fc": state.style.text_highlight_fc,
            "text_highlight_alpha": state.style.text_highlight_alpha,
            "text_highlight_pad": state.style.text_highlight_pad,
            "ylim": list(state.style.ylim) if state.style.ylim is not None else None,
        },
        "source_path": state.source_path,
    }
    if fig is not None and ax is not None:
        snap.update(capture_histo_spine_snapshot(fig, ax))
    return snap


def _snapshot_for_json(state: HistoState, fig=None, ax=None) -> dict:
    snap = _snapshot_state(state, fig, ax)
    snap["setup"]["values"] = np.asarray(snap["setup"]["values"]).tolist()
    if snap["setup"].get("values_master") is not None:
        snap["setup"]["values_master"] = np.asarray(snap["setup"]["values_master"]).tolist()
    snap["setup"]["bin_edges"] = np.asarray(snap["setup"]["bin_edges"]).tolist()
    return snap


def _restore_snapshot(snap: dict) -> HistoState:
    # Style-only ``p`` payloads omit setup — fabricate a placeholder; callers that
    # import style must keep the live setup (apply_histo_style_snapshot).
    s = snap.get("setup")
    if not isinstance(s, dict):
        s = {
            "column_index": 0,
            "column_name": "",
            "values": [],
            "xmin": 0.0,
            "xmax": 1.0,
            "bin_edges": [0.0, 1.0],
        }
    st = snap.get("style") or {}
    # Prefer never-truncated master column when present (BC: fall back to values).
    _vals = s.get("values_master")
    if _vals is None:
        _vals = s.get("values", [])
    _vals_arr = np.asarray(_vals, dtype=float)
    setup = HistoSetup(
        column_index=int(s["column_index"]),
        column_name=str(s["column_name"]),
        values=_vals_arr,
        xmin=float(s["xmin"]),
        xmax=float(s["xmax"]),
        bin_edges=np.asarray(s["bin_edges"], dtype=float),
    )
    style = HistoStyle(
        bar_color=st.get("bar_color", "#4C72B0"),
        edge_color=st.get("edge_color", "#1f1f1f"),
        alpha=float(st.get("alpha", 0.85)),
        bar_width_frac=float(st.get("bar_width_frac", 0.95)),
        show_grid=bool(st.get("show_grid", False)),
        grid_linewidth=float(st.get("grid_linewidth", 0.6)),
        density=bool(st.get("density", False)),
        show_bar_labels=bool(st.get("show_bar_labels", False)),
        show_mean_line=bool(st.get("show_mean_line", False)),
        show_median_line=bool(st.get("show_median_line", False)),
        show_density_curve=bool(st.get("show_density_curve", False)),
        density_curve_color=str(st.get("density_curve_color", "#c0392b")),
        density_curve_lw=float(st.get("density_curve_lw", 1.8)),
        density_curve_ls=str(st.get("density_curve_ls", "-")),
        density_curve_alpha=float(st.get("density_curve_alpha", 1.0)),
        xlabel=finalize_axis_label_text(str(st.get("xlabel", ""))),
        ylabel=finalize_axis_label_text(str(st.get("ylabel", ""))),
        title=finalize_axis_label_text(str(st.get("title", ""))),
        top_xlabel=finalize_axis_label_text(str(st.get("top_xlabel", ""))),
        figsize=tuple(st.get("figsize", [8.0, 5.5])),
        axes_fraction=(
            tuple(st["axes_fraction"])
            if isinstance(st.get("axes_fraction"), (list, tuple)) and len(st["axes_fraction"]) == 4
            else None
        ),
        label_fontsize=float(st.get("label_fontsize", 14.0)),
        title_fontsize=float(st.get("title_fontsize", 15.0)),
        font_family=str(st.get("font_family", "")),
        font_weight=str(st.get("font_weight", "normal")),
        text_highlight=bool(st.get("text_highlight", False)),
        text_highlight_fc=str(st.get("text_highlight_fc", "white")),
        text_highlight_alpha=float(st.get("text_highlight_alpha", 0.85)),
        text_highlight_pad=float(st.get("text_highlight_pad", 0.2)),
        ylim=(
            tuple(st["ylim"])
            if isinstance(st.get("ylim"), (list, tuple)) and len(st["ylim"]) == 2
            else None
        ),
    )
    state = HistoState(setup=setup, style=style, source_path=str(snap.get("source_path", "")))
    try:
        state._values_master = np.array(_vals_arr, copy=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    normalize_histo_title(state)
    return state


def sanitize_histo_session_snap(snap: dict) -> dict:
    """Strip legacy auto plot titles from a session snap (mutates and returns *snap*)."""
    if not isinstance(snap, dict):
        return snap
    # Style-only exports have no setup — only normalize title text.
    if not isinstance(snap.get("setup"), dict):
        style = snap.get("style")
        if isinstance(style, dict):
            title = str(style.get("title", "") or "").strip()
            low = title.lower()
            if not title or low.startswith("histogram ") or low in (
                "length",
                "histogram length",
                "histogram",
            ):
                style["title"] = ""
        return snap
    try:
        normalized = _restore_snapshot(snap)
        style = snap.get("style")
        if isinstance(style, dict):
            style["title"] = normalized.style.title
    except Exception:
        style = snap.get("style")
        if isinstance(style, dict):
            title = str(style.get("title", "") or "").strip()
            low = title.lower()
            if not title or low.startswith("histogram ") or low in (
                "length",
                "histogram length",
                "histogram",
            ):
                style["title"] = ""
    return snap


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
            resize_plot_frame(
                fig, ax, [], [], type("Args", (), {"stack": False})(), _noop_update_labels,
                on_before_change=push_state,
            )
            sync_histo_geometry(fig, ax, state)
            fig.canvas.draw_idle()
        except Exception as exc:
            print(f"Resize failed: {exc}")

    def _resize_canvas_cmd() -> None:
        try:
            resize_canvas(fig, ax, on_before_change=push_state)
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
    normalize_histo_title(state)
    sync_histo_geometry(fig, ax, state)
    snap = sanitize_histo_session_snap(_snapshot_state(state, fig, ax))
    payload = {"kind": "histo", "version": 1, "state": snap}
    try:
        from ..common.session_helpers import capture_last_figure_export_path

        # Last exported figure path so 'oe' works after reopening the session.
        payload["last_figure_export_path"] = capture_last_figure_export_path(fig)
    except Exception:
        pass
    try:
        from ...session import _package_versions_stamp

        payload["package_versions"] = _package_versions_stamp()
    except Exception:
        pass
    with open(path, "wb") as fh:
        pickle.dump(payload, fh)
    fig._last_session_save_path = os.path.abspath(path)  # type: ignore[attr-defined]


def _export_style(fig, ax, state: HistoState, path: str, *, include_geometry: bool = True) -> None:
    sync_histo_geometry(fig, ax, state)
    payload = _snapshot_for_json(state, fig, ax)
    payload["kind"] = "histo_style"
    # p/i contract: style-only — never ship column data / source path.
    payload.pop("setup", None)
    payload.pop("source_path", None)
    if not include_geometry:
        for key in ("figsize", "axes_fraction", "ylim"):
            payload.get("style", {}).pop(key, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    fig._last_style_export_path = os.path.abspath(path)  # type: ignore[attr-defined]
    fig._last_style_export_include_geometry = include_geometry  # type: ignore[attr-defined]


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
            savefig_without_crosshair(
                fig,
                path,
                dpi=300,
                bbox_inches="tight",
                transparent=True,
                facecolor="none",
                edgecolor="none",
            )
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
        savefig_without_crosshair(fig, path, dpi=300, bbox_inches="tight")
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

    def restore_state(*, quiet: bool = False) -> bool:
        """Pop tip and apply it (push-before-mutate contract)."""
        if len(history) <= 1:
            if not quiet:
                print("No undo history.")
            return False
        snap = history.pop()
        try:
            _apply_state(fig, ax, state, _restore_snapshot(snap), snap=snap)
            return True
        except Exception as exc:
            history.append(snap)
            if not quiet:
                print(f"Undo failed: {exc}")
            return False

    push_state()

    normalize_histo_title(state)
    sync_histo_geometry(fig, ax, state)
    refresh_histo_figure(fig, ax, state)
    history[-1] = _snapshot_state(state, fig, ax)

    def _refresh_figure() -> None:
        refresh_histo_figure(fig, ax, state)

    def _finish_spine_colors_only(_changed: list[tuple[str, str]]) -> None:
        from .spines import apply_histo_spine_colors, get_histo_spine_colors

        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
        # Re-apply after draw so tick lines keep spine colors (Agg/GUI).
        try:
            apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig))
        except Exception:
            pass

    def _ctx():
        return _histo_action_context(
            fig, ax, state,
            push_state=push_state,
            pop_undo=pop_undo,
            restore_state=lambda: restore_state(quiet=True),
        )

    while True:
        _print_histo_menu(fig, state)
        try:
            if pending_key is not None:
                cmd = pending_key
                pending_key = None
            else:
                cmd = prompt_menu_key()
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
            # Push-before-mutate: tip is the pre-edit state. Restore the popped
            # snap (XY/EC/CPC/operando/batch parity) — do not peek under it or
            # multi-step undo skips a level.
            restore_state(quiet=False)
            continue

        if cmd == "c":
            run_histo_color_menu(
                fig=fig,
                ax=ax,
                get_bar_color=lambda: state.style.bar_color,
                set_bar_color=lambda c: setattr(state.style, "bar_color", c),
                get_edge_color=lambda: state.style.edge_color,
                set_edge_color=lambda c: setattr(state.style, "edge_color", c),
                get_bar_alpha=lambda: float(state.style.alpha),
                set_bar_alpha=lambda a: setattr(state.style, "alpha", float(a)),
                push_state=push_state,
                refresh=_refresh_figure,
                finish_spine_change=_finish_spine_colors_only,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "f":
            run_histo_font_menu(
                state=state,
                push_state=push_state,
                refresh=_refresh_figure,
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
                refresh=_refresh_figure,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
                fig=fig,
            )
            fig.canvas.draw_idle()
            continue

        if cmd == "l":
            run_histo_line_style_menu(
                fig=fig,
                ax=ax,
                state=state,
                push_state=push_state,
                refresh=_refresh_figure,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
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
                refresh=_refresh_figure,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "w":
            while True:
                cur = max(0.01, min(float(state.style.bar_width_frac), 1.0))
                raw = safe_input(
                    colorize_prompt(
                        f"Bar width fraction [{cur:g}] (0–1, fraction of bin width, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if not raw or raw.lower() == "q":
                    break
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

        if cmd == "y":
            run_histo_y_range_menu(
                state=state,
                push_state=push_state,
                refresh=_refresh_figure,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "x":
            while True:
                if table_loader is None:
                    print("Range/bin editor needs the source table (internal error).")
                    break
                table = table_loader()
                new_setup = run_histo_wizard(
                    table,
                    fixed_col=state.setup.column_index,
                )
                if new_setup is None:
                    break
                push_state()
                state.setup = new_setup
                refresh_histo_figure(fig, ax, state)
                fig.canvas.draw_idle()
                print("Range/bin settings updated.")
            continue

        if cmd == "t":
            def _histo_toggle_display(key: str) -> None:
                if key == "d":
                    # Rewrite ylabel only when it still matches the prior mode
                    # default; keep cleared ("") and custom titles intact.
                    prev_default = state.y_label_default()
                    cur = state.style.ylabel
                    state.style.density = not state.style.density
                    if cur == prev_default:
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
                    refresh=_refresh_figure,
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
            handle_figure_export(_ctx())
            continue

        if cmd == "p":
            handle_style_export(_ctx())
            continue

        if cmd == "i":
            handle_style_import(_ctx())
            continue

        if cmd == "s":
            handle_save_session(_ctx())
            continue

        if cmd == "oe":
            handle_quick_overwrite_figure(_ctx())
            continue

        if cmd == "os":
            handle_quick_overwrite_session(_ctx())
            continue

        if cmd in ("ops", "opsg"):
            handle_quick_overwrite_style(_ctx(), include_geometry=(cmd == "opsg"))
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["histo_interactive_menu"]
