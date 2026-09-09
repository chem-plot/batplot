"""EC-specific helpers for batch session editing (Tier A/B style sync).

Mirrors the operando batch pattern: nested EC submenus run against the
reference panel only (with undo/print callbacks disabled), then a *scoped*
style merge is applied to peers so each menu key only syncs the fields it
owns (colors stay local under ``l``/``t``/``k``/…; smooth / dual C_th never
hitchhike). Full ``apply_ec_style_config`` remains for ``p``/``i``/``s``/``b``.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Callable, FrozenSet, List, Optional, Sequence

from matplotlib.ticker import MaxNLocator, MultipleLocator  # type: ignore[import-untyped]

from ...ui import (
    finalize_spine_colors,
    position_bottom_xlabel,
    position_left_ylabel,
    position_right_ylabel,
    position_top_xlabel,
)
from ..common.spines import (
    apply_changed_side_title_positions,
    build_wasd_state,
    run_spine_tick_menu,
    sync_legacy_tick_keys,
    sync_tick_state_from_wasd,
    wasd_to_tick_state,
)
from ..common.terminal import colorize_inline_commands, colorize_prompt, safe_input
from ..electrochem.colors import _iter_cycle_lines, set_ec_file_visibility
from ..electrochem.interactive import _apply_spine_color, _apply_stored_axis_colors
from ..electrochem.legend import _rebuild_legend
from ..electrochem.style import _get_style_snapshot
from ..electrochem.style_apply import (
    _apply_display_mode as _sa_apply_display_mode,
    apply_ec_style_config,
)
from .load import EcPanel
from .operando_batch_helpers import (
    edit_ref_then_sync,
    make_batch_live_sync,
    noop_snapshot,
    sync_style_from_ref,
)

__all__ = [
    "apply_ec_cycles_colors_only",
    "apply_ec_file_visibility_only",
    "apply_ec_labels_only",
    "apply_ec_legend_only",
    "apply_ec_line_chrome_only",
    "apply_ec_scoped_sync",
    "apply_ec_smooth_only",
    "apply_ec_spine_colors_only",
    "apply_ec_wasd_chrome_only",
    "default_ec_tick_state",
    "ec_all_cycles",
    "ec_apply_display_mode",
    "ec_apply_nice_ticks",
    "ec_apply_spine_color",
    "ec_normalize_file_data",
    "ec_panel_is_dqdv",
    "ec_set_file_visibility",
    "ensure_ec_fig_state",
    "ec_print_file_list_factory",
    "ec_rebuild_legend",
    "ec_run_file_visibility_menu",
    "ec_tick_state_from_fig",
    "edit_ref_then_sync",
    "make_batch_live_sync",
    "noop_snapshot",
    "print_batch_ec_cycles_status",
    "run_ec_batch_spine_menu",
]

# Re-exported for convenience so callers only need this one module for
# EC batch style menus (matches the rename/spine-color/line-style helpers).
ec_apply_spine_color = _apply_spine_color
ec_rebuild_legend = _rebuild_legend


def apply_ec_labels_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Apply only axis label text from a style cfg (batch ``r`` rename sync).

    Full ``apply_ec_style_config`` also copies cycle colors, dQ/dV smooth
    settings, WASD, visible cycles, and file display names — those must stay
    panel-local when the user only renames axis titles.
    """
    ax = panel.ax
    fig = panel.fig
    labels = cfg.get("axis_labels") or {}
    try:
        from ...utils import finalize_axis_label_text

        if labels.get("xlabel") is not None:
            text = finalize_axis_label_text(str(labels["xlabel"]))
            ax.set_xlabel(text)
            ax._stored_xlabel = text
        if labels.get("ylabel") is not None:
            text = finalize_axis_label_text(str(labels["ylabel"]))
            ax.set_ylabel(text)
            ax._stored_ylabel = text
    except Exception as exc:
        if not silent:
            print(f"Label sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False

    # Dual GC top xlabel text only — never mode/swap/scale from the ref.
    try:
        from ...utils import finalize_axis_label_text

        xd = cfg.get("xaxis_dual") or {}
        top = xd.get("top_axis") if isinstance(xd, dict) else None
        if isinstance(top, dict) and top.get("xlabel") is not None:
            from ..electrochem.style import ec_dual_secax

            sec = ec_dual_secax(fig)
            if sec is not None:
                sec.set_xlabel(finalize_axis_label_text(str(top["xlabel"])))
    except Exception:
        pass
    return True


def _peer_ec_style_snapshot(panel: EcPanel) -> dict:
    tick_state = ec_tick_state_from_fig(panel.fig, panel.ax)
    return _get_style_snapshot(
        panel.fig,
        panel.ax,
        panel.cycle_lines or {},
        tick_state,
        panel.file_data,
    )


def _merge_spines_dict(peer: Any, ref: Any, *, mode: str) -> dict:
    """Merge spine props. mode: ``linewidth`` | ``color`` | ``visible`` | ``all``."""
    out = copy.deepcopy(peer) if isinstance(peer, dict) else {}
    if not isinstance(ref, dict):
        return out
    for name, props in ref.items():
        if not isinstance(props, dict):
            continue
        dest = dict(out.get(name) or {})
        if mode in ("linewidth", "all"):
            if "linewidth" in props:
                dest["linewidth"] = props["linewidth"]
        # Visibility is owned by WASD (``t``).
        if mode in ("visible", "all") and "visible" in props:
            dest["visible"] = props["visible"]
        if mode in ("color", "all"):
            if "color" in props:
                dest["color"] = props["color"]
        out[name] = dest
    return out


def _merge_ticks_dict(peer: Any, ref: Any, *, mode: str) -> dict:
    """Merge tick props. mode: ``widths`` | ``spacing`` | ``all``."""
    if mode == "all" and isinstance(ref, dict):
        return copy.deepcopy(ref)
    out = copy.deepcopy(peer) if isinstance(peer, dict) else {}
    if not isinstance(ref, dict):
        return out
    if mode in ("widths", "all"):
        ref_w = ref.get("widths") or {}
        if ref_w:
            widths = dict(out.get("widths") or {})
            widths.update(ref_w)
            out["widths"] = widths
    if mode in ("spacing", "all"):
        for key in ("spacing", "lengths", "direction", "locator_state"):
            if key in ref:
                out[key] = copy.deepcopy(ref[key])
    return out


def _len_matches(seq: Any, n: int) -> bool:
    return isinstance(seq, (list, tuple)) and len(seq) == n


def _patch_cycle_styles_line_chrome(styles: Any, *, linewidth: Any, markers: Any) -> None:
    """Update lw/marker fields inside cycle_styles without touching colors."""
    if not isinstance(styles, dict):
        return
    # Do not copy marker face/edge colors — those track curve color on peers.
    marker_keys = ("linestyle", "marker", "markersize", "dash_pattern")
    for entry in styles.values():
        if not isinstance(entry, dict):
            continue
        for role_style in entry.values():
            if not isinstance(role_style, dict):
                continue
            if linewidth is not None:
                try:
                    role_style["linewidth"] = float(linewidth)
                except Exception:
                    pass
            if isinstance(markers, dict):
                for mk in marker_keys:
                    if mk in markers:
                        role_style[mk] = markers[mk]


# Color / visibility fields owned by batch ``c`` inside cycle_styles entries.
# Line chrome (lw / linestyle / markers / dash) is owned by ``l``.
_CYCLE_STYLE_COLOR_KEYS = frozenset({
    "color",
    "markerfacecolor",
    "markeredgecolor",
    "alpha",
    "visible",
})


def _overlay_cycle_styles_colors(peer: Any, ref: Any) -> Any:
    """Merge ref color fields onto peer cycle_styles; keep peer line chrome."""
    if not isinstance(ref, dict):
        return copy.deepcopy(peer) if isinstance(peer, dict) else ref
    out = copy.deepcopy(peer) if isinstance(peer, dict) else {}
    for cyc_key, entry in ref.items():
        if not isinstance(entry, dict):
            continue
        dest_entry = dict(out.get(cyc_key) or {})
        for role, role_style in entry.items():
            if not isinstance(role_style, dict):
                continue
            dest_role = dict(dest_entry.get(role) or {})
            for k in _CYCLE_STYLE_COLOR_KEYS:
                if k in role_style:
                    dest_role[k] = copy.deepcopy(role_style[k])
            dest_entry[role] = dest_role
        out[cyc_key] = dest_entry
    return out


def apply_ec_scoped_sync(
    panel: EcPanel,
    ref_cfg: dict,
    *,
    keys: FrozenSet[str],
    spine_mode: str | None = None,
    ticks_mode: str | None = None,
    silent: bool = True,
    patch_line_chrome_into_cycle_styles: bool = False,
    broadcast_cycle_styles: bool = False,
    cycle_styles_colors_only: bool = False,
) -> bool:
    """Merge selected keys from *ref_cfg* onto the peer's current style, then apply.

    Starts from the peer snapshot so panel-local fields (colors, smooth, dual
    C_th, limits, file names, …) stay put unless listed in *keys*. Always
    applies as ``ec_style`` (never resizes canvas from hitchhiking geometry).
    """
    merged = copy.deepcopy(_peer_ec_style_snapshot(panel))
    merged["kind"] = "ec_style"
    merged.pop("geometry", None)
    merged.pop("axes_geometry", None)

    n_files = len(panel.file_data) if panel.file_data else 0
    for key in keys:
        if key not in ref_cfg and key not in ("spines", "ticks"):
            continue
        if key == "spines" and spine_mode:
            merged["spines"] = _merge_spines_dict(
                merged.get("spines"), ref_cfg.get("spines"), mode=spine_mode
            )
            continue
        if key == "ticks" and ticks_mode:
            merged["ticks"] = _merge_ticks_dict(
                merged.get("ticks"), ref_cfg.get("ticks"), mode=ticks_mode
            )
            continue
        if key == "cycle_styles" and cycle_styles_colors_only:
            merged["cycle_styles"] = _overlay_cycle_styles_colors(
                merged.get("cycle_styles"), ref_cfg.get("cycle_styles")
            )
            continue
        if key == "cycle_styles_per_file" and cycle_styles_colors_only:
            val = ref_cfg.get(key)
            if n_files and _len_matches(val, n_files):
                peer_pf = merged.get(key)
                peer_list = (
                    list(peer_pf)
                    if _len_matches(peer_pf, n_files)
                    else [None] * n_files
                )
                merged[key] = [
                    _overlay_cycle_styles_colors(p_st, r_st)
                    for p_st, r_st in zip(peer_list, val)
                ]
            continue
        if key in ("file_visibility", "visible_cycles_per_file", "cycle_styles_per_file", "legend_file_order"):
            val = ref_cfg.get(key)
            if n_files and _len_matches(val, n_files):
                merged[key] = copy.deepcopy(val)
            continue
        if key == "xaxis_dual":
            # Dual mode / C_th / swap are owned by ``a``/``u``. WASD ``t`` may
            # only refresh top-axis chrome (labelpad / visibility / ticks) on
            # peers already dual. Top ``xlabel`` text is owned by ``r``.
            peer_xd = merged.get("xaxis_dual")
            ref_xd = ref_cfg.get("xaxis_dual")
            if (
                isinstance(peer_xd, dict)
                and peer_xd.get("mode") == "dual"
                and isinstance(ref_xd, dict)
            ):
                out_xd = copy.deepcopy(peer_xd)
                ref_top = ref_xd.get("top_axis")
                if isinstance(ref_top, dict):
                    peer_top = dict(out_xd.get("top_axis") or {})
                    for fld in (
                        "labelpad",
                        "x_labelpad",
                        "visible",
                        "spine_visible",
                        "ticks",
                        "labels",
                    ):
                        if fld in ref_top:
                            peer_top[fld] = copy.deepcopy(ref_top[fld])
                    out_xd["top_axis"] = peer_top
                merged["xaxis_dual"] = out_xd
            continue
        if key in ref_cfg:
            merged[key] = copy.deepcopy(ref_cfg[key])

    if broadcast_cycle_styles:
        # Force apply_ec_style_config's multi-file branch to use cycle_styles.
        merged.pop("cycle_styles_per_file", None)

    if patch_line_chrome_into_cycle_styles:
        lw = merged.get("curve_linewidth")
        markers = merged.get("curve_markers")
        _patch_cycle_styles_line_chrome(merged.get("cycle_styles"), linewidth=lw, markers=markers)
        per_file = merged.get("cycle_styles_per_file")
        if isinstance(per_file, list):
            for styles in per_file:
                _patch_cycle_styles_line_chrome(styles, linewidth=lw, markers=markers)

    tick_state = ec_tick_state_from_fig(panel.fig, panel.ax)
    is_multi = bool(panel.file_data and len(panel.file_data) > 1)
    return apply_ec_style_config(
        merged,
        fig=panel.fig,
        ax=panel.ax,
        cycle_lines=panel.cycle_lines or {},
        file_data=panel.file_data,
        tick_state=tick_state,
        is_multi_file=is_multi,
        silent=silent,
    )


def apply_ec_line_chrome_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``l``: linewidth / markers / grid / frame+tick widths (not colors)."""
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    # Strip curve color hitchhikers from shared marker props.
    markers = cfg.get("curve_markers")
    if isinstance(markers, dict):
        markers = {
            k: v
            for k, v in markers.items()
            if k in ("linestyle", "marker", "markersize", "dash_pattern")
        }
        cfg = {**cfg, "curve_markers": markers}
    return apply_ec_scoped_sync(
        panel,
        cfg,
        keys=frozenset({"curve_linewidth", "curve_markers", "grid", "spines", "ticks"}),
        spine_mode="linewidth",
        ticks_mode="widths",
        silent=silent,
        patch_line_chrome_into_cycle_styles=True,
    )


def apply_ec_wasd_chrome_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``t``: WASD / tick spacing / title offsets (not ``l`` widths or colors).

    Includes ``xaxis_dual`` so dual-top ``labelpad`` / visibility / tick chrome
    from the reference reaches peers already in dual mode. Top-axis ``xlabel``
    text stays on ``r``. Frame/tick linewidths stay on ``l``.
    """
    return apply_ec_scoped_sync(
        panel,
        cfg,
        keys=frozenset(
            {"wasd_state", "ticks", "spines", "title_offsets", "labelpads", "xaxis_dual"}
        ),
        spine_mode="visible",
        ticks_mode="spacing",
        silent=silent,
    )


def apply_ec_spine_colors_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``k``: spine + axis-label colors only."""
    return apply_ec_scoped_sync(
        panel,
        cfg,
        keys=frozenset({"spines", "axis_label_colors"}),
        spine_mode="color",
        silent=silent,
    )


def apply_ec_legend_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``h``: legend visibility/position (+ file order when counts match)."""
    return apply_ec_scoped_sync(
        panel,
        cfg,
        keys=frozenset({"legend", "legend_file_order"}),
        silent=silent,
    )


def apply_ec_file_visibility_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``v``: per-file show/hide via ``set_ec_file_visibility`` (supports re-show).

    Full style_apply only forces lines off when hiding; re-show needs the shared
    helper so stashed ``selected_cycles`` are restored on peers.
    """
    vis = cfg.get("file_visibility") if isinstance(cfg, dict) else None
    fd = panel.file_data
    if not isinstance(vis, (list, tuple)) or not fd:
        return False
    if len(vis) != len(fd):
        if not silent:
            print(
                f"Skipped file visibility sync for {getattr(panel, 'path', '?')}: "
                f"file count {len(fd)}≠{len(vis)}"
            )
        return False
    dm = getattr(panel.fig, "_ec_display_mode", "both")
    for f, visible in zip(fd, vis):
        set_ec_file_visibility(f, bool(visible), display_mode=dm)
    try:
        _rebuild_legend(panel.ax)
    except Exception:
        pass
    return True


def apply_ec_cycles_colors_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``c``: cycle colors / visibility (not ``d`` display, ``l`` chrome, WASD, smooth, dual)."""
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    n_files = len(panel.file_data) if panel.file_data else 0
    ref_pf = cfg.get("cycle_styles_per_file")
    # Single-file (or mismatched) ref → multi-file peer: drop peer per-file
    # styles so apply uses broadcast ``cycle_styles``.
    if n_files > 1 and not _len_matches(ref_pf, n_files):
        cfg = {**cfg}
        cfg.pop("cycle_styles_per_file", None)
        # Also drop length-gated keys that would no-op and leave peer stale.
        if not _len_matches(cfg.get("visible_cycles_per_file"), n_files):
            cfg.pop("visible_cycles_per_file", None)
    return apply_ec_scoped_sync(
        panel,
        cfg,
        keys=frozenset({
            "cycle_styles",
            "cycle_styles_per_file",
            "visible_cycles",
            "visible_cycles_per_file",
            # display_mode owned by ``d``; curve_linewidth / markers owned by ``l``.
        }),
        silent=silent,
        broadcast_cycle_styles=(n_files > 1 and not _len_matches(ref_pf, n_files)),
        cycle_styles_colors_only=True,
    )


def apply_ec_smooth_only(panel: EcPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``sm`` (dQdV): sync smooth settings and re-apply (not colors / WASD / limits)."""
    from ..electrochem.interactive import _apply_stored_smooth_settings

    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    smooth = cfg.get("_dqdv_smooth_settings")
    if not isinstance(smooth, dict):
        return False
    try:
        panel.fig._dqdv_smooth_settings = dict(smooth)
    except Exception:
        return False
    file_data, cycle_lines, is_multi = ec_normalize_file_data(panel)
    targets = (
        [f.get("cycle_lines") for f in file_data if f.get("cycle_lines")]
        if is_multi
        else [cycle_lines]
    )
    for cl in targets:
        if not isinstance(cl, dict):
            continue
        # Force re-apply: stored helper skips lines already marked smoothed.
        for parts in cl.values():
            iter_parts = (
                parts.items() if isinstance(parts, dict) else [(None, parts)]
            )
            for _role, ln in iter_parts:
                if ln is None:
                    continue
                try:
                    if hasattr(ln, "_smooth_applied"):
                        delattr(ln, "_smooth_applied")
                except Exception:
                    try:
                        ln._smooth_applied = False
                    except Exception:
                        pass
        if smooth:
            try:
                _apply_stored_smooth_settings(cl, panel.fig)
            except Exception as exc:
                if not silent:
                    print(
                        f"dQ/dV smooth sync failed for "
                        f"{getattr(panel, 'path', '?')}: {exc}"
                    )
                return False
    return True


def ec_panel_is_dqdv(panel: EcPanel) -> bool:
    """True when this EC panel is a dQ/dV (differential capacity) session."""
    ax = getattr(panel, "ax", None)
    if ax is None:
        return False
    flag = getattr(ax, "_is_dqdv_mode", None)
    if flag is not None:
        return bool(flag)
    for text in (
        getattr(ax, "_stored_ylabel", None),
        ax.get_ylabel() if hasattr(ax, "get_ylabel") else None,
    ):
        if text and "dq" in str(text).lower():
            return True
    return False


def default_ec_tick_state() -> dict:
    # Full flat schema matching wasd_to_tick_state / dump.
    return wasd_to_tick_state(
        {},
        tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
        label_defaults={"top": False, "bottom": True, "left": True, "right": False},
    )


def ec_tick_state_from_fig(fig: Any, ax: Any | None = None) -> dict:
    """Rebuild the flat EC tick_state dict from the stored WASD state.

    Falls back to ``ax._saved_tick_state`` when ``fig._ec_wasd_state`` is missing
    (older sessions / loaders that only seeded the axis attribute).
    """
    wasd = getattr(fig, "_ec_wasd_state", None)
    if not isinstance(wasd, dict) and ax is not None:
        saved = getattr(ax, "_saved_tick_state", None)
        # Non-empty saved only: empty {} must fall through to defaults so
        # batch style snapshots always have full side keys (BC).
        if isinstance(saved, dict) and saved:
            out = default_ec_tick_state()
            out.update(saved)
            # Older payloads often store legacy bx/tx/ly/ry + *_ticks but omit
            # *_labels. Infer missing labels from legacy before sync so
            # ticks∧labels does not wipe an explicit True legacy key.
            for leg, tk, lk in (
                ("bx", "b_ticks", "b_labels"),
                ("tx", "t_ticks", "t_labels"),
                ("ly", "l_ticks", "l_labels"),
                ("ry", "r_ticks", "r_labels"),
            ):
                if leg not in saved or lk in saved:
                    continue
                if tk in saved:
                    if saved.get(tk):
                        out[lk] = bool(saved[leg])
                else:
                    out[tk] = bool(saved[leg])
                    out[lk] = bool(saved[leg])
            sync_legacy_tick_keys(out)
            return out
    if isinstance(wasd, dict):
        # Same contract as dump/session: legacy = ticks AND labels.
        return wasd_to_tick_state(
            wasd,
            tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
            label_defaults={"top": False, "bottom": True, "left": True, "right": False},
        )
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


def ensure_ec_fig_state(
    panel: EcPanel,
    file_data: list[dict],
    is_multi_file: bool,
    *,
    is_dqdv: bool | None = None,
) -> None:
    """Mirror the fig-level attrs ``electrochem_interactive_menu`` sets on startup.

    ``_rebuild_legend``/``_apply_legend_position`` read these directly off the
    figure, and batch panels are loaded via ``session.load_ec_session`` (no
    interactive setup pass), so they need to be seeded once before reusing
    those normal-mode helpers in batch menus.
    """
    fig = panel.fig
    if is_dqdv is None:
        is_dqdv = ec_panel_is_dqdv(panel)
    try:
        fig._ec_file_data = file_data
        fig._ec_is_multi_file = is_multi_file
        # Overview is GC-only (interactive parity); never force it for dQ/dV.
        fig._ec_overview_enabled = not bool(is_dqdv)
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


def ec_set_file_visibility(
    f_entry: dict,
    visible: bool,
    *,
    display_mode: str | None = None,
    fig=None,
) -> None:
    """Show/hide one multi-file EC entry without destroying cycle selection.

    Thin wrapper around the shared interactive/batch helper so batch ``v`` and
    session dump keep the same ``selected_cycles`` / ``visible_cycles`` contract.
    """
    if display_mode is None and fig is not None:
        display_mode = getattr(fig, "_ec_display_mode", "both")
    set_ec_file_visibility(f_entry, visible, display_mode=display_mode)


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
                ec_set_file_visibility(f, new_state, fig=fig)
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
            ec_set_file_visibility(f, not f.get("visible", True), fig=fig)
        try:
            rebuild_legend(ax)
            fig.canvas.draw_idle()
        except Exception:
            pass


def print_batch_ec_cycles_status(panels: Sequence, *, colors: bool = False) -> None:
    """Print visible-cycle counts; optionally also list curve colors.

    ``colors=False`` (default) keeps the batch ``c`` menu compact. Pass
    ``colors=True`` (or press ``v`` in the color menu) to list swatches.
    """
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

    if not colors:
        return

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
    """Apply MaxNLocator on linear axes, preserving custom MultipleLocator (t>n)."""
    def _has_custom_major(axis_obj) -> bool:
        try:
            return isinstance(axis_obj.get_major_locator(), MultipleLocator)
        except Exception:
            return False

    try:
        if (
            getattr(ax, "get_xscale", None)
            and ax.get_xscale() == "linear"
            and not _has_custom_major(ax.xaxis)
        ):
            ax.xaxis.set_major_locator(MaxNLocator(nbins="auto", steps=[1, 2, 5], min_n_ticks=4))
        if (
            getattr(ax, "get_yscale", None)
            and ax.get_yscale() == "linear"
            and not _has_custom_major(ax.yaxis)
        ):
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
    tick_state = ec_tick_state_from_fig(fig, ax)

    def _get_spine_visible(side: str) -> bool:
        sp = ax.spines.get(side)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False

    wasd = getattr(fig, "_ec_wasd_state", None)
    if not isinstance(wasd, dict):
        from ..electrochem.style import dual_top_spine_visible, dual_top_title_visible

        _is_dual_init = getattr(fig, "_xaxis_mode", "capacity") == "dual"
        wasd = build_wasd_state(
            get_spine_visible=(
                (lambda side: dual_top_spine_visible(fig, ax) if side == "top"
                 else _get_spine_visible(side))
                if _is_dual_init else _get_spine_visible
            ),
            tick_state=tick_state,
            title_visible={
                "top": (
                    dual_top_title_visible(fig, ax)
                    if _is_dual_init
                    else bool(getattr(ax, "_top_xlabel_on", False))
                ),
                "bottom": bool(ax.xaxis.label.get_visible()),
                "left": bool(ax.yaxis.label.get_visible()),
                "right": bool(getattr(ax, "_right_ylabel_on", False)),
            },
            tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
            label_defaults={"top": False, "bottom": True, "left": True, "right": False},
        )
        fig._ec_wasd_state = wasd

    def _apply_wasd(changed_sides=None) -> None:
        from ..electrochem.style import apply_ec_wasd_chrome, ec_dual_secax

        if changed_sides is None:
            changed_sides = {"bottom", "top", "left", "right"}
        apply_ec_wasd_chrome(fig, ax, wasd, apply_titles=True)
        try:
            _apply_stored_axis_colors(ax, fig)
        except Exception:
            pass
        is_dual_xaxis = ec_dual_secax(fig) is not None

        def _position_top() -> None:
            if is_dual_xaxis:
                return
            position_top_xlabel(ax, fig, tick_state)
            _apply_stored_axis_colors(ax, fig)

        def _position_right() -> None:
            position_right_ylabel(ax, fig, tick_state)
            _apply_stored_axis_colors(ax, fig)

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
        # Persist immediately so panel capture/saves always see current toggles.
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass

    def _ec_live_dual_axes():
        from ..electrochem.style import ec_dual_secax
        out = [ax]
        sec = ec_dual_secax(fig)
        if sec is not None:
            out.append(sec)
        return out

    def _after_locator_edit() -> None:
        from ..electrochem.style import sync_ec_dual_secax_x_locators
        try:
            sync_ec_dual_secax_x_locators(fig, ax, wasd)
        except Exception:
            pass

    def _batch_title_offset() -> None:
        """Dual-aware title offset: top uses SecondaryAxis labelpad when dual."""
        from ..common.title_offsets import run_title_offset_nudge_menu
        from ..electrochem.style import ec_dual_secax

        sec = ec_dual_secax(fig)
        while True:
            print("\nTitle offsets (batch EC):")
            print("  w : top   | s : bottom | a : left | d : right")
            print("  q : back")
            side = safe_input(colorize_prompt("Side (w/a/s/d/q): ")).strip().lower()
            if not side or side == "q":
                break
            if side == "w" and sec is not None:
                try:
                    _pad = getattr(sec.xaxis, "labelpad", 4.0)
                    cur = float(4.0 if _pad is None else _pad)
                except Exception:
                    cur = 4.0
                print(f"Current top (ions) labelpad: {cur}")
                raw = safe_input(
                    colorize_prompt("New labelpad (pts) or +N/-N (q=back): ")
                ).strip()
                if not raw or raw.lower() == "q":
                    continue
                try:
                    if raw[0] in "+-" and raw[1:].replace(".", "", 1).isdigit():
                        sec.xaxis.labelpad = cur + float(raw)
                    else:
                        sec.xaxis.labelpad = float(raw)
                    print(f"Set top labelpad={sec.xaxis.labelpad}")
                    _draw_spine_menu()
                except Exception as exc:
                    print(f"Invalid: {exc}")
                continue
            if side not in ("w", "a", "s", "d"):
                print("Unknown side.")
                continue
            # Shared WASD nudge on primary axes (skips re-asking for side).
            run_title_offset_nudge_menu(
                fig=fig,
                ax=ax,
                push_state=lambda: None,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                draw=_draw_spine_menu,
                initial_side=side,
            )

    def _draw_spine_menu() -> None:
        try:
            from ..electrochem.style import reseal_ec_chrome

            reseal_ec_chrome(fig, ax, wasd=wasd, tick_state=tick_state, apply_titles=True)
        except Exception:
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
            direction_axes=_ec_live_dual_axes(),
            length_axes=_ec_live_dual_axes(),
            direction_axes_provider=_ec_live_dual_axes,
            length_axes_provider=_ec_live_dual_axes,
            after_locator_edit=_after_locator_edit,
            title_offset_handler=_batch_title_offset,
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
