"""EC-specific helpers for batch session editing (Tier A/B style sync).

Mirrors the operando batch pattern: nested EC submenus run against the
reference panel only (with undo/print callbacks disabled), then the
resulting style snapshot is captured from the reference and applied to every
other panel via the existing ``_capture_panel``/``_apply_cfg`` round trip
already used for undo and style import/export in ``menu_ec.py``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Sequence

from matplotlib.ticker import MaxNLocator  # type: ignore[import-untyped]

from ...ui import (
    finalize_spine_colors,
    position_bottom_xlabel,
    position_left_ylabel,
    position_right_ylabel,
    position_top_xlabel,
)
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_wasd_spines,
    apply_wasd_tick_params,
    build_wasd_state,
    run_spine_tick_menu,
    sync_tick_state_from_wasd,
)
from ..common.terminal import colorize_inline_commands, colorize_prompt, safe_input
from ..electrochem.colors import _iter_cycle_lines
from ..electrochem.interactive import _apply_spine_color, _apply_stored_axis_colors
from ..electrochem.legend import _rebuild_legend
from ..electrochem.style_apply import _apply_display_mode as _sa_apply_display_mode
from .load import EcPanel
from .operando_batch_helpers import edit_ref_then_sync, noop_snapshot, sync_style_from_ref

__all__ = [
    "default_ec_tick_state",
    "ec_all_cycles",
    "ec_apply_display_mode",
    "ec_apply_nice_ticks",
    "ec_apply_spine_color",
    "ec_normalize_file_data",
    "ec_set_file_visibility",
    "ensure_ec_fig_state",
    "ec_print_file_list_factory",
    "ec_rebuild_legend",
    "ec_run_file_visibility_menu",
    "ec_tick_state_from_fig",
    "edit_ref_then_sync",
    "noop_snapshot",
    "print_batch_ec_cycles_status",
    "run_ec_batch_spine_menu",
]

# Re-exported for convenience so callers only need this one module for
# EC batch style menus (matches the rename/spine-color/line-style helpers).
ec_apply_spine_color = _apply_spine_color
ec_rebuild_legend = _rebuild_legend


def default_ec_tick_state() -> dict:
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


def ec_tick_state_from_fig(fig: Any) -> dict:
    """Rebuild the flat EC tick_state dict from the stored WASD state."""
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
    return default_ec_tick_state()


def ec_normalize_file_data(panel: EcPanel) -> tuple[list[dict], dict, bool]:
    """Return (file_data, cycle_lines, is_multi_file) for menu reuse.

    When ``panel.file_data`` is present, entries are filled in-place (same
    dict objects, same list) so any mutation performed by reused normal-mode
    menus (rename, visibility, colors, ...) persists to the panel and is
    picked up by session save/export. Single-file panels (no ``file_data``)
    get an ephemeral, non-persisted one-entry placeholder list instead —
    matching the fallback normalization ``electrochem_interactive_menu`` uses.
    """
    raw = panel.file_data
    if raw:
        for i, entry in enumerate(raw):
            entry.setdefault("visible", True)
            if not entry.get("filename"):
                fp = entry.get("filepath")
                entry["filename"] = os.path.basename(fp) if fp else f"File {i + 1}"
            entry.setdefault("display_name", entry.get("filename", str(i + 1)))
        file_data = raw
    else:
        cl = panel.cycle_lines or {}
        file_data = [{
            "filename": "Data",
            "display_name": "Data",
            "cycle_lines": cl,
            "visible": True,
        }]
    is_multi_file = len(file_data) > 1
    cycle_lines = file_data[0]["cycle_lines"]
    return file_data, cycle_lines, is_multi_file


def ensure_ec_fig_state(panel: EcPanel, file_data: list[dict], is_multi_file: bool) -> None:
    """Mirror the fig-level attrs ``electrochem_interactive_menu`` sets on startup.

    ``_rebuild_legend``/``_apply_legend_position`` read these directly off the
    figure, and batch panels are loaded via ``session.load_ec_session`` (no
    interactive setup pass), so they need to be seeded once before reusing
    those normal-mode helpers in batch menus.
    """
    fig = panel.fig
    try:
        fig._ec_file_data = file_data
        fig._ec_is_multi_file = is_multi_file
        if is_multi_file and not hasattr(fig, "_ec_legend_file_order"):
            fig._ec_legend_file_order = list(range(len(file_data)))
    except Exception:
        pass


def ec_print_file_list_factory(is_multi_file: bool) -> Callable[..., None]:
    def _print_file_list(_file_data, _current_idx: int = 0) -> None:
        if not is_multi_file or not _file_data:
            return
        for i, f in enumerate(_file_data):
            vis = "visible" if f.get("visible", True) else "hidden"
            name = f.get("filename", "?")
            mark = ">" if i == _current_idx else " "
            print(f"  {mark} {i + 1}: {name} [{vis}]")

    return _print_file_list


def ec_set_file_visibility(f_entry: dict, visible: bool) -> None:
    """Show/hide all cycle lines belonging to one multi-file EC entry."""
    f_entry["visible"] = bool(visible)
    cl = f_entry.get("cycle_lines") or {}
    for _cyc, parts in cl.items():
        if isinstance(parts, dict):
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is not None:
                    try:
                        ln.set_visible(visible)
                    except Exception:
                        pass
        else:
            try:
                parts.set_visible(visible)
            except Exception:
                pass


def ec_run_file_visibility_menu(
    *,
    file_data: list,
    is_multi_file: bool,
    print_file_list: Callable[..., None],
    rebuild_legend: Callable[[Any], Any],
    fig: Any,
    ax: Any,
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Multi-file show/hide submenu (EC ``v``), matching normal interactive."""
    if not is_multi_file or not file_data:
        print("File visibility (v) is only available with multiple files.")
        return
    while True:
        print_file_list(file_data)
        choice = safe_input(
            colorize_prompt(f"Toggle visibility (1-{len(file_data)}, a=all, q=back): ")
        ).strip()
        if not choice or choice.lower() == "q":
            break
        if choice.lower() in ("a", "all"):
            push_state("visibility")
            any_visible = any(f.get("visible", True) for f in file_data)
            new_state = not any_visible
            for f in file_data:
                ec_set_file_visibility(f, new_state)
        else:
            try:
                idx = int(choice) - 1
            except ValueError:
                print("Invalid input.")
                continue
            if not (0 <= idx < len(file_data)):
                print("Invalid file number.")
                continue
            push_state("visibility")
            f = file_data[idx]
            ec_set_file_visibility(f, not f.get("visible", True))
        try:
            rebuild_legend(ax)
            fig.canvas.draw_idle()
        except Exception:
            pass


def print_batch_ec_cycles_status(panels: Sequence) -> None:
    """Print visible-cycle counts and curve colors for every batch EC panel."""
    from ..electrochem.colors import _cycle_color_listing, _visible_cycle_keys

    print("Visible cycles:")
    rows: list[tuple[int, dict, list, str]] = []
    for i, panel in enumerate(panels, 1):
        _fd, cycle_lines, _multi = ec_normalize_file_data(panel)
        all_cyc = ec_all_cycles(cycle_lines, _fd if _fd else None)
        n_vis = len(_visible_cycle_keys(cycle_lines, all_cyc))
        name = os.path.basename(getattr(panel, "path", "") or "") or f"plot {i}"
        if not all_cyc or n_vis == len(all_cyc):
            print(f"  [{i}] {n_vis}  ({name})")
        else:
            print(f"  [{i}] {n_vis} (of {len(all_cyc)} total)  ({name})")
        rows.append((i, cycle_lines, all_cyc, name))

    print("Current curves (visible only):")
    any_printed = False
    for i, cycle_lines, all_cyc, name in rows:
        vis = _visible_cycle_keys(cycle_lines, all_cyc)
        if not vis:
            continue
        any_printed = True
        print(f"  [{i}] {name}")
        for cyc in vis:
            print(f"    {cyc}: {_cycle_color_listing(cycle_lines, cyc)}")
    if not any_printed:
        print("  (none visible)")


def ec_all_cycles(cycle_lines: dict, file_data: Optional[list]) -> list:
    if file_data:
        return sorted(set(cyc for f in file_data for cyc in (f.get("cycle_lines") or {}).keys()))
    return sorted((cycle_lines or {}).keys())


def ec_apply_nice_ticks(ax: Any) -> None:
    try:
        if getattr(ax, "get_xscale", None) and ax.get_xscale() == "linear":
            ax.xaxis.set_major_locator(MaxNLocator(nbins="auto", steps=[1, 2, 5], min_n_ticks=4))
        if getattr(ax, "get_yscale", None) and ax.get_yscale() == "linear":
            ax.yaxis.set_major_locator(MaxNLocator(nbins="auto", steps=[1, 2, 5], min_n_ticks=4))
    except Exception:
        pass


def ec_apply_display_mode(mode: str, *, cycle_lines: dict, file_data: Optional[list], is_multi_file: bool) -> None:
    _sa_apply_display_mode(
        mode,
        cycle_lines=cycle_lines,
        file_data=file_data,
        is_multi_file=is_multi_file,
        iter_cycle_lines=_iter_cycle_lines,
    )


def run_ec_batch_spine_menu(
    ref: EcPanel,
    panels: List[EcPanel],
    *,
    undo,
    capture_panel: Callable[[EcPanel], dict],
    apply_cfg: Callable[[EcPanel, dict], bool],
    draw_all: Callable[[], None],
) -> None:
    """Full WASD spine/tick editor on the reference panel, synced to all panels."""
    ax = ref.ax
    fig = ref.fig
    tick_state = ec_tick_state_from_fig(fig)

    def _get_spine_visible(side: str) -> bool:
        sp = ax.spines.get(side)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False

    wasd = getattr(fig, "_ec_wasd_state", None)
    if not isinstance(wasd, dict):
        wasd = build_wasd_state(
            get_spine_visible=_get_spine_visible,
            tick_state=tick_state,
            title_visible={
                "top": bool(getattr(ax, "_top_xlabel_on", False)),
                "bottom": bool(ax.xaxis.label.get_visible()),
                "left": bool(ax.yaxis.label.get_visible()),
                "right": bool(getattr(ax, "_right_ylabel_on", False)),
            },
            tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
            label_defaults={"top": False, "bottom": True, "left": True, "right": False},
        )
        fig._ec_wasd_state = wasd

    def _apply_wasd(changed_sides=None) -> None:
        if changed_sides is None:
            changed_sides = {"bottom", "top", "left", "right"}
        is_dual_xaxis = getattr(fig, "_xaxis_mode", "capacity") == "dual"
        secax = getattr(fig, "_xaxis_secondary", None) if is_dual_xaxis else None

        apply_wasd_spines(ax, wasd, axes_by_side={"top": secax} if is_dual_xaxis and secax is not None else None)
        if is_dual_xaxis and secax is not None:
            try:
                apply_wasd_tick_params(ax, wasd, x_sides=("bottom",), y_sides=("left", "right"))
                apply_wasd_tick_params(secax, wasd, x_sides=("top",), y_sides=())
            except Exception:
                apply_wasd_tick_params(ax, wasd)
        else:
            apply_wasd_tick_params(ax, wasd)

        if bool(wasd["bottom"]["title"]):
            if hasattr(ax, "_stored_xlabel") and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                ax.set_xlabel(ax._stored_xlabel)
                ax.xaxis.label.set_visible(True)
                _apply_stored_axis_colors(ax)
        else:
            if not hasattr(ax, "_stored_xlabel"):
                try:
                    ax._stored_xlabel = ax.get_xlabel()
                except Exception:
                    ax._stored_xlabel = ""
            ax.set_xlabel("")
            ax.xaxis.label.set_visible(False)

        ax._top_xlabel_on = bool(wasd["top"]["title"])
        if is_dual_xaxis and secax is not None:
            try:
                secax.xaxis.label.set_visible(bool(wasd["top"]["title"]))
            except Exception:
                pass

        if bool(wasd["left"]["title"]):
            if hasattr(ax, "_stored_ylabel") and isinstance(ax._stored_ylabel, str) and ax._stored_ylabel:
                ax.set_ylabel(ax._stored_ylabel)
                ax.yaxis.label.set_visible(True)
                _apply_stored_axis_colors(ax)
        else:
            if not hasattr(ax, "_stored_ylabel"):
                try:
                    ax._stored_ylabel = ax.get_ylabel()
                except Exception:
                    ax._stored_ylabel = ""
            ax.set_ylabel("")
            ax.yaxis.label.set_visible(False)
        ax._right_ylabel_on = bool(wasd["right"]["title"])

        def _position_top() -> None:
            position_top_xlabel(ax, fig, tick_state)
            _apply_stored_axis_colors(ax)

        def _position_right() -> None:
            position_right_ylabel(ax, fig, tick_state)
            _apply_stored_axis_colors(ax)

        apply_changed_side_title_positions(
            changed_sides,
            bottom=lambda: position_bottom_xlabel(ax, fig, tick_state),
            top=_position_top,
            left=lambda: position_left_ylabel(ax, fig, tick_state),
            right=_position_right,
        )
        try:
            finalize_spine_colors(fig, ax, tick_state=tick_state)
        except Exception:
            pass

    def _sync_tick_state() -> None:
        sync_tick_state_from_wasd(
            tick_state,
            wasd,
            tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
            label_defaults={"top": False, "bottom": True, "left": True, "right": False},
        )

    def _draw_spine_menu() -> None:
        try:
            finalize_spine_colors(fig, ax, tick_state=tick_state)
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
        sync_style_from_ref(
            ref,
            panels,
            capture_panel=capture_panel,
            apply_cfg=apply_cfg,
            include_geometry=False,
        )
        draw_all()

    def _edit() -> None:
        run_spine_tick_menu(
            fig=fig,
            wasd=wasd,
            safe_input=safe_input,
            colorize_prompt=colorize_prompt,
            colorize_inline_commands=colorize_inline_commands,
            push_state=noop_snapshot,
            sync_tick_state=_sync_tick_state,
            apply_wasd=_apply_wasd,
            draw=_draw_spine_menu,
            mode_label="batch EC",
            back_label="batch menu",
            axis_map={"x": ax.xaxis, "y": ax.yaxis},
            direction_axes=[ax],
            length_axes=[ax],
        )

    edit_ref_then_sync(
        ref,
        panels,
        undo=undo,
        capture_panel=capture_panel,
        apply_cfg=apply_cfg,
        draw_all=draw_all,
        edit_fn=_edit,
        include_geometry=False,
    )
