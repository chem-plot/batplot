"""CPC-specific helpers for batch session editing (Tier A/B style sync).

Mirrors the EC/operando batch pattern: nested CPC submenus run against the
reference panel only (undo/print callbacks disabled), then the resulting
style snapshot is captured from the reference and applied to every other
panel via the existing ``_capture_panel``/``_apply_cpc_style`` round trip
already used for undo and style import/export in ``menu_cpc.py``.
"""

from __future__ import annotations

from typing import Any, Callable, List

from ...ui import (
    finalize_spine_colors_cpc,
    position_bottom_xlabel,
    position_left_ylabel,
    set_spine_side_color as _ui_set_spine_side_color,
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
from ..cpc.legend import _normalize_spine_color, _rebuild_legend
from .load import CpcPanel
from .operando_batch_helpers import edit_ref_then_sync, noop_snapshot, sync_style_from_ref

__all__ = [
    "cpc_normalize_file_data",
    "cpc_print_file_list_factory",
    "cpc_run_file_visibility_menu",
    "cpc_set_spine_color",
    "edit_ref_then_sync",
    "noop_snapshot",
    "run_cpc_batch_spine_menu",
]


def cpc_normalize_file_data(panel: CpcPanel) -> tuple[list[dict], bool]:
    """Return (file_data, is_multi_file) for menu reuse.

    When ``panel.file_data`` is present, entries are the same dict objects
    used by the panel (mutations from reused normal-mode menus persist and
    are picked up by session save/export). Single-file panels get an
    ephemeral, non-persisted one-entry placeholder list instead, matching
    the fallback normalization ``capacity_per_cycle_interactive_menu`` uses.
    """
    raw = panel.file_data
    if raw:
        for f in raw:
            f.setdefault("visible", True)
        return raw, len(raw) > 1
    file_data = [{
        "filename": "Data",
        "sc_charge": panel.sc_charge,
        "sc_discharge": panel.sc_discharge,
        "sc_eff": panel.sc_eff,
        "visible": True,
    }]
    return file_data, False


def cpc_print_file_list_factory(is_multi_file: bool) -> Callable[..., None]:
    def _print_file_list(_file_data, _current_idx: int = 0) -> None:
        if not is_multi_file or not _file_data:
            return
        for i, f in enumerate(_file_data):
            vis = "visible" if f.get("visible", True) else "hidden"
            name = f.get("filename", "?")
            mark = ">" if i == _current_idx else " "
            print(f"  {mark} {i + 1}: {name} [{vis}]")

    return _print_file_list


def cpc_run_file_visibility_menu(
    *,
    file_data: list,
    is_multi_file: bool,
    print_file_list: Callable[..., None],
    rebuild_legend: Callable[..., Any],
    fig: Any,
    ax: Any,
    ax2: Any,
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Multi-file show/hide submenu (CPC ``v``), matching normal interactive."""
    if not is_multi_file or not file_data:
        print("File visibility (v) is only available in multi-file CPC mode.")
        return
    while True:
        print_file_list(file_data)
        print("  " + colorize_menu("1, 1 2 3, 1-4: toggle file(s)"))
        print("  " + colorize_menu("a: toggle all"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(
            colorize_prompt(f"Select file numbers (1-{len(file_data)}), a=all, q=back: ")
        ).strip()
        if not choice or choice.lower() == "q":
            break

        indices_to_toggle: list[int] = []
        if choice.lower() in ("a", "all"):
            indices_to_toggle = list(range(len(file_data)))
        else:
            parts = choice.replace(",", " ").split()
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                if "-" in p and p.count("-") == 1:
                    try:
                        lo, hi = p.split("-")
                        lo_i = int(lo.strip()) - 1
                        hi_i = int(hi.strip()) - 1
                        for i in range(lo_i, hi_i + 1):
                            if 0 <= i < len(file_data):
                                indices_to_toggle.append(i)
                    except ValueError:
                        pass
                else:
                    try:
                        idx = int(p) - 1
                        if 0 <= idx < len(file_data):
                            indices_to_toggle.append(idx)
                    except ValueError:
                        pass
            indices_to_toggle = sorted(set(indices_to_toggle))

        if not indices_to_toggle:
            print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
            continue
        push_state("visibility")
        for idx in indices_to_toggle:
            f = file_data[idx]
            new_vis = not f.get("visible", True)
            f["visible"] = new_vis
            for key in ("sc_charge", "sc_discharge", "sc_eff"):
                sc = f.get(key)
                if sc is not None:
                    try:
                        sc.set_visible(new_vis)
                    except Exception:
                        pass
        try:
            rebuild_legend(ax, ax2, file_data, preserve_position=True)
            fig.canvas.draw_idle()
        except Exception:
            pass
        names = [file_data[i].get("filename", f"File {i + 1}") for i in indices_to_toggle]
        print(f"Toggled: {', '.join(names)}")


def cpc_set_spine_color(fig: Any, ax: Any, ax2: Any, spine_name: str, color) -> None:
    """Set one spine's color (with matching ticks/labels), mirroring the
    ``_set_spine_color`` closure ``_apply_style`` builds for normal mode."""
    if not hasattr(fig, "_cpc_spine_colors") or not isinstance(getattr(fig, "_cpc_spine_colors", None), dict):
        fig._cpc_spine_colors = {}
    color = _normalize_spine_color(color)
    if color is None:
        return
    fig._cpc_spine_colors[spine_name] = color
    axes_map = {
        "top": [ax, ax2],
        "bottom": [ax, ax2],
        "left": [ax],
        "right": [ax2],
    }
    for curr_ax in axes_map.get(spine_name, [ax, ax2]):
        if curr_ax is None or spine_name not in curr_ax.spines:
            continue
        try:
            _ui_set_spine_side_color(curr_ax, spine_name, color, fig=fig)
        except Exception:
            pass


def run_cpc_batch_spine_menu(
    ref: CpcPanel,
    panels: List[CpcPanel],
    *,
    undo,
    capture_panel: Callable[[CpcPanel], dict],
    apply_cfg: Callable[[CpcPanel, dict], bool],
    draw_all: Callable[[], None],
) -> None:
    """Full WASD spine/tick editor on the reference panel, synced to all panels."""
    fig, ax, ax2 = ref.fig, ref.ax, ref.ax2
    sc_eff = ref.sc_eff
    tick_state = ref.tick_state

    wasd = getattr(fig, "_cpc_wasd_state", None)
    if not isinstance(wasd, dict):
        def _spine_visible(side: str, _ax) -> bool:
            sp = _ax.spines.get(side)
            try:
                return bool(sp.get_visible()) if sp is not None else False
            except Exception:
                return False

        wasd = {
            "top": {
                "spine": _spine_visible("top", ax),
                "ticks": bool(tick_state.get("t_ticks", tick_state.get("tx", False))),
                "minor": bool(tick_state.get("mtx", False)),
                "labels": bool(tick_state.get("t_labels", tick_state.get("tx", False))),
                "title": bool(getattr(ax, "_top_xlabel_on", False)),
            },
            "bottom": {
                "spine": _spine_visible("bottom", ax),
                "ticks": bool(tick_state.get("b_ticks", tick_state.get("bx", True))),
                "minor": bool(tick_state.get("mbx", False)),
                "labels": bool(tick_state.get("b_labels", tick_state.get("bx", True))),
                "title": bool(ax.get_xlabel()),
            },
            "left": {
                "spine": _spine_visible("left", ax),
                "ticks": bool(tick_state.get("l_ticks", tick_state.get("ly", True))),
                "minor": bool(tick_state.get("mly", False)),
                "labels": bool(tick_state.get("l_labels", tick_state.get("ly", True))),
                "title": bool(ax.get_ylabel()),
            },
            "right": {
                "spine": _spine_visible("right", ax2),
                "ticks": bool(tick_state.get("r_ticks", tick_state.get("ry", True))),
                "minor": bool(tick_state.get("mry", False)),
                "labels": bool(tick_state.get("r_labels", tick_state.get("ry", True))),
                "title": bool(ax2.yaxis.get_label().get_text()) and bool(sc_eff.get_visible() if sc_eff is not None else False),
            },
        }
        fig._cpc_wasd_state = wasd

    def _apply_wasd(changed_sides=None) -> None:
        if changed_sides is None:
            changed_sides = {"bottom", "top", "left", "right"}

        apply_wasd_spines(ax, wasd, sides=("top", "bottom", "left"))
        apply_wasd_spines(ax2, wasd, sides=("top", "bottom", "right"))
        apply_wasd_tick_params(ax, wasd, y_sides=("left",), y_mode="left")
        apply_wasd_tick_params(ax2, wasd, x_sides=(), y_sides=("right",), y_mode="right")

        try:
            if bool(wasd["bottom"]["title"]):
                if hasattr(ax, "_stored_xlabel") and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                    ax.set_xlabel(ax._stored_xlabel)
            else:
                if not hasattr(ax, "_stored_xlabel"):
                    try:
                        ax._stored_xlabel = ax.get_xlabel()
                    except Exception:
                        ax._stored_xlabel = ""
                ax.set_xlabel("")
        except Exception:
            pass

        try:
            if not hasattr(ax, "_stored_top_xlabel") or not ax._stored_top_xlabel:
                current_xlabel = ax.get_xlabel()
                if current_xlabel:
                    ax._stored_top_xlabel = current_xlabel
                elif hasattr(ax, "_stored_xlabel") and ax._stored_xlabel:
                    ax._stored_top_xlabel = ax._stored_xlabel
                else:
                    ax._stored_top_xlabel = ""

            if bool(wasd["top"]["title"]) and ax._stored_top_xlabel:
                if not hasattr(ax, "_top_xlabel_text") or ax._top_xlabel_text is None:
                    ax._top_xlabel_text = ax.text(
                        0.5, 1.0, "", transform=ax.transAxes,
                        ha="center", va="bottom",
                        fontsize=ax.xaxis.label.get_fontsize(),
                        fontfamily=ax.xaxis.label.get_fontfamily(),
                    )
                ax._top_xlabel_text.set_text(ax._stored_top_xlabel)
                ax._top_xlabel_text.set_visible(True)
                if "top" in changed_sides:
                    try:
                        renderer = fig.canvas.get_renderer()
                        labelpad = ax.xaxis.labelpad if hasattr(ax.xaxis, "labelpad") else 4.0
                        fig_h = fig.get_size_inches()[1]
                        ax_bbox = ax.get_position()
                        ax_h_inches = ax_bbox.height * fig_h
                        base_pad_axes = (labelpad / 72.0) / ax_h_inches if ax_h_inches > 0 else 0.02
                        extra_offset = 0.0
                        if bool(wasd["top"]["labels"]) and renderer is not None:
                            try:
                                max_h_px = 0.0
                                for t in ax.xaxis.get_major_ticks():
                                    lab = getattr(t, "label2", None)
                                    if lab is not None and lab.get_visible():
                                        bb = lab.get_window_extent(renderer=renderer)
                                        if bb is not None:
                                            max_h_px = max(max_h_px, float(bb.height))
                                if max_h_px > 0 and ax_h_inches > 0:
                                    dpi = float(fig.dpi) if hasattr(fig, "dpi") else 100.0
                                    max_h_inches = max_h_px / dpi
                                    extra_offset = max_h_inches / ax_h_inches
                            except Exception:
                                extra_offset = 0.05
                        total_offset = 1.0 + base_pad_axes + extra_offset
                        ax._top_xlabel_text.set_position((0.5, total_offset))
                    except Exception:
                        if bool(wasd["top"]["labels"]):
                            ax._top_xlabel_text.set_position((0.5, 1.07))
                        else:
                            ax._top_xlabel_text.set_position((0.5, 1.02))
            else:
                if hasattr(ax, "_top_xlabel_text") and ax._top_xlabel_text is not None:
                    ax._top_xlabel_text.set_visible(False)
        except Exception:
            pass

        try:
            if bool(wasd["left"]["title"]):
                if hasattr(ax, "_stored_ylabel") and isinstance(ax._stored_ylabel, str) and ax._stored_ylabel:
                    ax.set_ylabel(ax._stored_ylabel)
            else:
                if not hasattr(ax, "_stored_ylabel"):
                    try:
                        ax._stored_ylabel = ax.get_ylabel()
                    except Exception:
                        ax._stored_ylabel = ""
                ax.set_ylabel("")
        except Exception:
            pass

        try:
            eff_visible = bool(sc_eff.get_visible()) if sc_eff is not None else False
            if bool(wasd["right"]["title"]) and eff_visible:
                if hasattr(ax2, "_stored_ylabel") and isinstance(ax2._stored_ylabel, str) and ax2._stored_ylabel:
                    ax2.set_ylabel(ax2._stored_ylabel)
            else:
                if not hasattr(ax2, "_stored_ylabel"):
                    try:
                        ax2._stored_ylabel = ax2.get_ylabel()
                    except Exception:
                        ax2._stored_ylabel = ""
                ax2.set_ylabel("")
        except Exception:
            pass

        apply_changed_side_title_positions(
            changed_sides,
            bottom=lambda: position_bottom_xlabel(ax, fig, tick_state),
            left=lambda: position_left_ylabel(ax, fig, tick_state),
        )
        try:
            finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
        except Exception:
            pass

    def _sync_tick_state() -> None:
        sync_tick_state_from_wasd(
            tick_state,
            wasd,
            tick_defaults={"top": False, "bottom": True, "left": True, "right": True},
            label_defaults={"top": False, "bottom": True, "left": True, "right": True},
        )
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass

    def _draw_spine_menu() -> None:
        try:
            finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
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
            mode_label="batch CPC",
            back_label="batch menu",
            axis_map={"x": ax.xaxis, "y": ax.yaxis, "r": ax2.yaxis},
            direction_axes=[ax, ax2],
            length_axes=[ax, ax2],
            on_quit=lambda: setattr(ax, "_saved_tick_state", dict(tick_state)),
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
