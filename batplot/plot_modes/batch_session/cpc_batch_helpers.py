"""CPC-specific helpers for batch session editing (Tier A/B style sync).

Nested CPC submenus run against the reference panel only, then a *scoped*
peer-merge apply copies only the fields that menu owns (colors stay local
under ``t``/``h``/…; labels-only under ``r``). Full ``_apply_style`` remains
for ``p``/``i``/``s``/``b``.
"""

from __future__ import annotations

import copy
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
    set_primary_axis_title,
    sync_tick_state_from_wasd,
)
from ..common.terminal import colorize_inline_commands, colorize_prompt, safe_input
from ..cpc.legend import _normalize_spine_color, _rebuild_legend
from ..cpc.style import _apply_style, _style_snapshot
from .batch_scoped_sync import (
    deep_merge_keys,
    merge_list_of_dicts_fields,
    merge_spines_props,
)
from .load import CpcPanel
from .operando_batch_helpers import (
    edit_ref_then_sync,
    make_batch_live_sync,
    noop_snapshot,
    sync_style_from_ref,
)

__all__ = [
    "apply_cpc_colors_only",
    "apply_cpc_file_visibility_only",
    "apply_cpc_labels_only",
    "apply_cpc_legend_only",
    "apply_cpc_wasd_chrome_only",
    "cpc_normalize_file_data",
    "cpc_print_file_list_factory",
    "cpc_run_file_visibility_menu",
    "cpc_set_spine_color",
    "edit_ref_then_sync",
    "make_batch_live_sync",
    "noop_snapshot",
    "run_cpc_batch_spine_menu",
]


_CPC_COLOR_MULTI_FIELDS = (
    "charge_color",
    "discharge_color",
    "efficiency_color",
    "charge_hollow",
    "discharge_hollow",
    "efficiency_hollow",
)

# Series color sync fields (batch ``c``) — include alpha for p/i/s/b parity.
_CPC_SERIES_COLOR_FIELDS = ("color", "hollow", "alpha")


def _peer_cpc_style(panel: CpcPanel) -> dict:
    return _style_snapshot(
        panel.fig,
        panel.ax,
        panel.ax2,
        panel.sc_charge,
        panel.sc_discharge,
        panel.sc_eff,
        panel.file_data,
    )


def _apply_cpc_merged(panel: CpcPanel, cfg: dict, *, silent: bool = True) -> bool:
    kind = cfg.get("kind", "")
    if kind and kind not in ("cpc_style", "cpc_style_geom"):
        if not silent:
            print(f"Not a CPC style file (kind={kind!r}).")
        return False
    file_ro = bool(cfg.get("ro_active", False))
    current_ro = bool(getattr(panel.fig, "_ro_active", False))
    if file_ro != current_ro:
        if not silent:
            print("Not applying CPC style (ro mismatch).")
        return False
    cfg = dict(cfg)
    cfg["kind"] = "cpc_style"
    cfg.pop("geometry", None)
    cfg.pop("axes_geometry", None)
    _apply_style(
        panel.fig,
        panel.ax,
        panel.ax2,
        panel.sc_charge,
        panel.sc_discharge,
        panel.sc_eff,
        cfg,
        panel.file_data,
    )
    return True


def apply_cpc_scoped_sync(
    panel: CpcPanel,
    ref_cfg: dict,
    *,
    top_keys: frozenset[str] = frozenset(),
    spine_mode: str | None = None,
    multi_file_fields: tuple[str, ...] = (),
    series_color_fields: tuple[str, ...] = (),
    silent: bool = True,
) -> bool:
    peer = _peer_cpc_style(panel)
    merged = deep_merge_keys(
        peer,
        ref_cfg,
        top_keys=top_keys,
        force_kind="cpc_style",
        drop_geometry=True,
    )
    if spine_mode and "spines" in top_keys:
        merged["spines"] = merge_spines_props(
            peer.get("spines"), ref_cfg.get("spines"), mode=spine_mode
        )
    if multi_file_fields:
        merged["multi_files"] = merge_list_of_dicts_fields(
            peer.get("multi_files"),
            ref_cfg.get("multi_files"),
            multi_file_fields,
        )
    if series_color_fields:
        peer_series = peer.get("series") if isinstance(peer.get("series"), dict) else {}
        ref_series = ref_cfg.get("series") if isinstance(ref_cfg.get("series"), dict) else {}
        out_series = copy.deepcopy(peer_series) if peer_series else {}
        for role in ("charge", "discharge", "efficiency"):
            pe = dict(out_series.get(role) or {})
            re = ref_series.get(role) if isinstance(ref_series.get(role), dict) else {}
            for field in series_color_fields:
                if field in re:
                    pe[field] = copy.deepcopy(re[field])
            out_series[role] = pe
        merged["series"] = out_series
    # legend_file_order only when file counts match
    if "legend_file_order" in top_keys:
        order = ref_cfg.get("legend_file_order")
        fd = panel.file_data
        if not (isinstance(order, (list, tuple)) and fd and len(order) == len(fd)):
            merged["legend_file_order"] = peer.get("legend_file_order")
    return _apply_cpc_merged(panel, merged, silent=silent)


def apply_cpc_labels_only(panel: CpcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Apply only axis label text from a style cfg (batch ``r`` rename sync).

    Full CPC style apply also copies series colors, markers, WASD, etc.
    Matches interactive ``r``→``x``: bottom + top title text stay in sync.
    """
    ax = panel.ax
    ax2 = panel.ax2
    labels = cfg.get("axis_labels") or {}
    try:
        from ...utils import finalize_axis_label_text

        if labels.get("xlabel") is not None:
            text = finalize_axis_label_text(str(labels["xlabel"]))
            ax.set_xlabel(text)
            ax._stored_xlabel = text
            # Top-axis title (t→w5) shares the same string as interactive rename.
            ax._stored_top_xlabel = text
            top_txt = getattr(ax, "_top_xlabel_text", None)
            if top_txt is not None:
                try:
                    if top_txt.get_visible():
                        top_txt.set_text(text)
                except Exception:
                    pass
        if labels.get("ylabel_left") is not None:
            text = finalize_axis_label_text(str(labels["ylabel_left"]))
            ax.set_ylabel(text)
            ax._stored_ylabel = text
        elif labels.get("ylabel") is not None:
            text = finalize_axis_label_text(str(labels["ylabel"]))
            ax.set_ylabel(text)
            ax._stored_ylabel = text
        if labels.get("ylabel_right") is not None and ax2 is not None:
            text = finalize_axis_label_text(str(labels["ylabel_right"]))
            ax2.set_ylabel(text)
            ax2._stored_ylabel = text
    except Exception as exc:
        if not silent:
            print(f"Label sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False
    return True


def apply_cpc_wasd_chrome_only(panel: CpcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``t``: WASD / ticks / title offsets (not ``l`` widths or series colors)."""
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    ticks = cfg.get("ticks")
    if isinstance(ticks, dict):
        ticks = dict(ticks)
        ticks.pop("widths", None)
        cfg["ticks"] = ticks
    return apply_cpc_scoped_sync(
        panel,
        cfg,
        top_keys=frozenset({"wasd_state", "ticks", "spines", "title_offsets", "labelpads"}),
        spine_mode="visible",
        silent=silent,
    )


def apply_cpc_colors_only(panel: CpcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``c``: series / multi-file / spine colors (not WASD / labels)."""
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    # Single-file ref → multi-file peer: broadcast series colors into multi_files.
    peer_mf = None
    try:
        peer_mf = _peer_cpc_style(panel).get("multi_files")
    except Exception:
        peer_mf = None
    ref_mf = cfg.get("multi_files")
    n_peer = len(peer_mf) if isinstance(peer_mf, list) else 0
    if (
        n_peer > 1
        and not (isinstance(ref_mf, list) and len(ref_mf) == n_peer)
        and isinstance(cfg.get("series"), dict)
    ):
        series = cfg["series"]
        broadcast = []
        for i in range(n_peer):
            base = dict(peer_mf[i]) if isinstance(peer_mf[i], dict) else {}
            for role, field in (
                ("charge", "charge_color"),
                ("discharge", "discharge_color"),
                ("efficiency", "efficiency_color"),
            ):
                role_cfg = series.get(role) if isinstance(series.get(role), dict) else {}
                if "color" in role_cfg:
                    base[field] = role_cfg["color"]
                hollow_key = field.replace("_color", "_hollow")
                if "hollow" in role_cfg:
                    base[hollow_key] = role_cfg["hollow"]
            broadcast.append(base)
        cfg = {**cfg, "multi_files": broadcast}
    return apply_cpc_scoped_sync(
        panel,
        cfg,
        top_keys=frozenset({"spine_colors", "spine_colors_auto", "spines"}),
        spine_mode="color",
        multi_file_fields=_CPC_COLOR_MULTI_FIELDS,
        series_color_fields=_CPC_SERIES_COLOR_FIELDS,
        silent=silent,
    )


def apply_cpc_legend_only(panel: CpcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``h``: legend visibility/position (+ file order when counts match)."""
    return apply_cpc_scoped_sync(
        panel,
        cfg,
        top_keys=frozenset({"legend", "legend_file_order"}),
        silent=silent,
    )


def apply_cpc_file_visibility_only(panel: CpcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``v``: per-file show/hide only (not efficiency/chg/dch or series)."""
    return apply_cpc_scoped_sync(
        panel,
        cfg,
        top_keys=frozenset(),
        multi_file_fields=("visible",),
        silent=silent,
    )


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
            f["visible"] = not f.get("visible", True)
        from ..cpc.panel_menus import apply_cpc_file_artist_visibility

        apply_cpc_file_artist_visibility(fig, file_data)
        try:
            rebuild_legend(ax, ax2, file_data, preserve_position=True)
            fig.canvas.draw_idle()
        except Exception:
            pass
        names = [file_data[i].get("filename", f"File {i + 1}") for i in indices_to_toggle]
        print(f"Toggled: {', '.join(names)}")


def cpc_set_spine_color(
    fig: Any,
    ax: Any,
    ax2: Any,
    spine_name: str,
    color,
    tick_state=None,
) -> None:
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
    ts = tick_state
    if ts is None:
        ts = getattr(ax, "_saved_tick_state", None)
    for curr_ax in axes_map.get(spine_name, [ax, ax2]):
        if curr_ax is None or spine_name not in curr_ax.spines:
            continue
        try:
            _ui_set_spine_side_color(
                curr_ax, spine_name, color, fig=fig, tick_state=ts
            )
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
                "title": bool(ax.xaxis.label.get_visible()),
            },
            "left": {
                "spine": _spine_visible("left", ax),
                "ticks": bool(tick_state.get("l_ticks", tick_state.get("ly", True))),
                "minor": bool(tick_state.get("mly", False)),
                "labels": bool(tick_state.get("l_labels", tick_state.get("ly", True))),
                "title": bool(ax.yaxis.label.get_visible()),
            },
            "right": {
                "spine": _spine_visible("right", ax2),
                "ticks": bool(tick_state.get("r_ticks", tick_state.get("ry", True))),
                "minor": bool(tick_state.get("mry", False)),
                "labels": bool(tick_state.get("r_labels", tick_state.get("ry", True))),
                "title": (
                    bool(ax2.yaxis.label.get_visible())
                    and bool(sc_eff.get_visible() if sc_eff is not None else False)
                ),
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
            set_primary_axis_title(
                ax, "x", on=bool(wasd["bottom"]["title"]), stored_attr="_stored_xlabel"
            )
        except Exception:
            pass

        try:
            if not hasattr(ax, "_stored_top_xlabel") or not isinstance(ax._stored_top_xlabel, str):
                current_xlabel = ax.get_xlabel()
                if current_xlabel:
                    ax._stored_top_xlabel = current_xlabel
                elif hasattr(ax, "_stored_xlabel") and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                    ax._stored_top_xlabel = ax._stored_xlabel
                else:
                    ax._stored_top_xlabel = ""

            ax._top_xlabel_on = bool(wasd["top"]["title"])
            if bool(wasd["top"]["title"]) and isinstance(getattr(ax, "_stored_top_xlabel", None), str):
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
            set_primary_axis_title(
                ax, "y", on=bool(wasd["left"]["title"]), stored_attr="_stored_ylabel"
            )
        except Exception:
            pass

        try:
            eff_visible = bool(sc_eff.get_visible()) if sc_eff is not None else False
            set_primary_axis_title(
                ax2,
                "y",
                on=bool(wasd["right"]["title"]) and eff_visible,
                stored_attr="_stored_ylabel",
            )
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

    def _title_offsets() -> None:
        from ..common.title_offsets import run_title_offset_nudge_menu

        # Right efficiency title lives on twin ``ax2``, not the left axes.
        run_title_offset_nudge_menu(
            fig=fig,
            ax=ax,
            push_state=lambda: None,
            safe_input=safe_input,
            colorize_prompt=colorize_prompt,
            draw=_draw_spine_menu,
            axis_by_side={"d": ax2},
        )

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
            title_offset_handler=_title_offsets,
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
