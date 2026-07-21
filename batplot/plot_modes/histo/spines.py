"""Spine/tick state for histogram mode (XY-style ``t`` menu)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set

from ..common.spines import (
    apply_changed_side_title_positions,
    apply_wasd_spines,
    apply_wasd_tick_params,
    build_wasd_state,
    default_flat_tick_state,
    legacy_tick_state_to_flat,
    sync_legacy_tick_keys,
    sync_tick_state_from_wasd,
)
from ...ui import (
    capture_axes_tick_locators,
    finalize_spine_colors,
    position_bottom_xlabel,
    position_left_ylabel,
    position_top_xlabel,
    restore_axes_tick_locators,
    set_spine_side_color,
)
from .plot import HistoState
from .line_style import apply_histo_line_style_to_ax, capture_histo_line_style_from_ax

_SPINE_SIDES = ("top", "bottom", "left", "right")

_TICK_DEFAULTS = {"top": False, "bottom": True, "left": True, "right": False}
_LABEL_DEFAULTS = {"top": False, "bottom": True, "left": True, "right": False}


def ensure_histo_tick_state(ax) -> Dict[str, bool]:
    tick_state = getattr(ax, "_saved_tick_state", None)
    if not isinstance(tick_state, dict) or not tick_state:
        tick_state = default_flat_tick_state(
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        ax._saved_tick_state = tick_state
    else:
        tick_state = legacy_tick_state_to_flat(
            tick_state,
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        ax._saved_tick_state = tick_state
    sync_legacy_tick_keys(tick_state)
    return tick_state


def ensure_histo_wasd(fig, ax, tick_state: Dict[str, bool]) -> Dict[str, Dict[str, bool]]:
    wasd = getattr(fig, "_histo_wasd_state", None)
    if not isinstance(wasd, dict) or not wasd:
        wasd = build_wasd_state(
            get_spine_visible=lambda side: bool(ax.spines.get(side).get_visible()) if ax.spines.get(side) else False,
            tick_state=tick_state,
            title_visible={
                "top": False,
                "bottom": bool(ax.xaxis.label.get_visible()),
                "left": bool(ax.yaxis.label.get_visible()),
                "right": False,
            },
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        fig._histo_wasd_state = wasd
    return wasd


def _capture_histo_title_offsets(ax) -> dict:
    return {
        "bottom_y": float(getattr(ax, "_bottom_xlabel_manual_offset_y_pts", 0.0) or 0.0),
        "left_x": float(getattr(ax, "_left_ylabel_manual_offset_x_pts", 0.0) or 0.0),
    }


def _restore_histo_title_offsets(ax, offsets: dict | None) -> None:
    if not offsets:
        return
    if "bottom_y" in offsets:
        ax._bottom_xlabel_manual_offset_y_pts = float(offsets.get("bottom_y", 0.0) or 0.0)
    if "left_x" in offsets:
        ax._left_ylabel_manual_offset_x_pts = float(offsets.get("left_x", 0.0) or 0.0)


def _restore_histo_tick_locators(ax, fig) -> None:
    spacing = getattr(fig, "_histo_tick_spacing", None)
    if spacing:
        restore_axes_tick_locators(ax, spacing, ("x", "y"))


def _normalize_spine_color(color) -> str:
    from matplotlib import colors as mcolors

    try:
        return mcolors.to_hex(mcolors.to_rgb(color))
    except (ValueError, TypeError):
        return str(color)


def get_histo_spine_colors(fig) -> dict[str, str]:
    stored = getattr(fig, "_histo_spine_colors", None)
    if isinstance(stored, dict):
        return {str(k): str(v) for k, v in stored.items()}
    return {}


def capture_histo_spine_colors_from_ax(ax) -> dict[str, str]:
    out: dict[str, str] = {}
    for side in _SPINE_SIDES:
        sp = ax.spines.get(side)
        if sp is None:
            continue
        try:
            out[side] = _normalize_spine_color(sp.get_edgecolor())
        except Exception:
            pass
    return out


def _apply_stored_histo_axis_colors(ax) -> None:
    """Re-apply stored duplicate axis title colors (same as EC ``_apply_stored_axis_colors``)."""
    try:
        color = getattr(ax, "_stored_xlabel_color", None)
        if color:
            ax.xaxis.label.set_color(color)
    except Exception:
        pass
    try:
        color = getattr(ax, "_stored_ylabel_color", None)
        if color:
            ax.yaxis.label.set_color(color)
    except Exception:
        pass
    try:
        top_artist = getattr(ax, "_top_xlabel_artist", None)
        color = getattr(ax, "_stored_top_xlabel_color", None)
        if top_artist is not None and color:
            top_artist.set_color(color)
    except Exception:
        pass
    try:
        right_artist = getattr(ax, "_right_ylabel_artist", None)
        color = getattr(ax, "_stored_right_ylabel_color", None)
        if right_artist is not None and color:
            right_artist.set_color(color)
    except Exception:
        pass


def _histo_grid_enabled(fig) -> bool:
    state = getattr(fig, "_bp_histo_state", None)
    if state is not None:
        return bool(getattr(state.style, "show_grid", False))
    return False


def _sync_histo_ygrid_color(ax, color, *, fig=None) -> None:
    """Histogram y-grid lines sit at tick heights and look like tick marks."""
    if fig is not None and not _histo_grid_enabled(fig):
        return
    try:
        for gl in ax.get_ygridlines():
            if gl.get_visible():
                gl.set_color(color)
    except Exception:
        pass


def _apply_histo_spine_color(fig, ax, side: str, color) -> None:
    """Apply one spine color the same way EC ``_apply_spine_color`` does."""
    if color is None:
        return
    hex_color = _normalize_spine_color(color)
    tick_state = ensure_histo_tick_state(ax)
    try:
        set_spine_side_color(ax, side, hex_color, fig=fig)
        if side == "top":
            ax._stored_top_xlabel_color = hex_color  # type: ignore[attr-defined]
            position_top_xlabel(ax, fig, tick_state)
        elif side == "bottom":
            ax._stored_xlabel_color = hex_color  # type: ignore[attr-defined]
            position_bottom_xlabel(ax, fig, tick_state)
        elif side == "left":
            ax._stored_ylabel_color = hex_color  # type: ignore[attr-defined]
            position_left_ylabel(ax, fig, tick_state)
            _sync_histo_ygrid_color(ax, hex_color, fig=fig)
        elif side == "right":
            ax._stored_right_ylabel_color = hex_color  # type: ignore[attr-defined]
            _sync_histo_ygrid_color(ax, hex_color, fig=fig)
    except Exception:
        pass
    _apply_stored_histo_axis_colors(ax)


def apply_histo_spine_colors(
    fig,
    ax,
    colors: dict[str, str] | None,
    *,
    only_sides: set[str] | None = None,
) -> None:
    if not colors:
        return
    for side, color in colors.items():
        if side not in _SPINE_SIDES:
            continue
        if only_sides is not None and side not in only_sides:
            continue
        try:
            _apply_histo_spine_color(fig, ax, side, color)
        except Exception:
            pass
    try:
        tick_state = ensure_histo_tick_state(ax)
        finalize_spine_colors(
            fig,
            ax,
            tick_state=tick_state,
            colors=colors,
            sides=only_sides,
        )
    except Exception:
        pass


def set_histo_spine_color(fig, ax, side: str, color) -> None:
    """Persist and apply one spine side color (survives redraw and p/i/s/b)."""
    if side not in _SPINE_SIDES:
        return
    hex_color = _normalize_spine_color(color)
    if not hasattr(fig, "_histo_spine_colors") or not isinstance(
        getattr(fig, "_histo_spine_colors", None), dict
    ):
        fig._histo_spine_colors = {}
    fig._histo_spine_colors[side] = hex_color  # type: ignore[attr-defined]
    _apply_histo_spine_color(fig, ax, side, hex_color)


def sync_histo_spine_colors_from_reference(
    ref_fig,
    ref_ax,
    targets: list[tuple[Any, Any]],
) -> None:
    colors = get_histo_spine_colors(ref_fig) or capture_histo_spine_colors_from_ax(ref_ax)
    for fig, ax in targets:
        fig._histo_spine_colors = dict(colors)  # type: ignore[attr-defined]
        apply_histo_spine_colors(fig, ax, colors)


def _collect_y_gridline_colors(ax) -> list[str]:
    try:
        from matplotlib import colors as mcolors

        out: list[str] = []
        for gl in ax.get_ygridlines():
            if gl.get_visible():
                out.append(mcolors.to_hex(mcolors.to_rgb(gl.get_color())))
        return out
    except Exception:
        return []


def format_histo_spine_extra_report(ax, side: str, *, expected_color=None) -> str:
    """Extra histo checks: y-grid lines often look like tick marks."""
    from matplotlib import colors as mcolors

    lines = [f"Histo extra check ({side}):"]
    exp_hex = None
    if expected_color is not None:
        try:
            exp_hex = mcolors.to_hex(mcolors.to_rgb(expected_color))
        except (ValueError, TypeError):
            exp_hex = str(expected_color)

    if side in ("left", "right"):
        grid_colors = _collect_y_gridline_colors(ax)
        n = len(grid_colors)
        lines.append(f"  y-grid lines visible: {n}")
        if grid_colors:
            lines.append(f"  y-grid line colors: {grid_colors[:6]}")
            if exp_hex and any(c != exp_hex for c in grid_colors):
                lines.append(
                    f"  *** Y-GRID MISMATCH: grid still {grid_colors[:3]} "
                    f"(expected {exp_hex}) — these look like tick marks on histograms"
                )
            elif exp_hex and grid_colors:
                lines.append(f"  y-grid matches spine color: {exp_hex}")
        elif exp_hex:
            lines.append("  y-grid: none visible (marks you see should be tick lines)")

    try:
        state = getattr(ax.figure, "_bp_histo_state", None)
        if state is not None:
            lines.append(f"  style.show_grid: {getattr(state.style, 'show_grid', '?')}")
    except Exception:
        pass
    return "\n".join(lines)


def capture_histo_spine_snapshot(fig, ax) -> dict:
    tick_state = ensure_histo_tick_state(ax)
    wasd = ensure_histo_wasd(fig, ax, tick_state)
    tick_spacing = capture_axes_tick_locators(ax, ("x", "y"))
    fig._histo_tick_spacing = dict(tick_spacing)
    spine_colors = get_histo_spine_colors(fig) or capture_histo_spine_colors_from_ax(ax)
    if spine_colors:
        fig._histo_spine_colors = dict(spine_colors)  # type: ignore[attr-defined]
    line_style = capture_histo_line_style_from_ax(ax)
    return {
        "tick_state": dict(tick_state),
        "wasd_state": {side: dict(state) for side, state in wasd.items()},
        "tick_direction": getattr(fig, "_tick_direction", "out"),
        "tick_lengths": dict(getattr(fig, "_tick_lengths", {}) or {}),
        "tick_spacing": tick_spacing,
        "title_offsets": _capture_histo_title_offsets(ax),
        "spine_colors": dict(spine_colors),
        "spine_linewidths": line_style.get("spine_linewidths", {}),
        "tick_widths": line_style.get("tick_widths", {}),
    }


def apply_histo_spine_snapshot(fig, ax, snap: dict) -> None:
    if isinstance(snap.get("tick_state"), dict):
        tick_state = legacy_tick_state_to_flat(
            snap["tick_state"],
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        sync_legacy_tick_keys(tick_state)
        ax._saved_tick_state = tick_state
    if isinstance(snap.get("wasd_state"), dict):
        fig._histo_wasd_state = {side: dict(state) for side, state in snap["wasd_state"].items()}
    if snap.get("tick_direction"):
        fig._tick_direction = str(snap["tick_direction"])
    if isinstance(snap.get("tick_lengths"), dict):
        fig._tick_lengths = dict(snap["tick_lengths"])
    if isinstance(snap.get("tick_spacing"), dict):
        fig._histo_tick_spacing = dict(snap["tick_spacing"])
        _restore_histo_tick_locators(ax, fig)
    if isinstance(snap.get("title_offsets"), dict):
        _restore_histo_title_offsets(ax, snap["title_offsets"])
    if isinstance(snap.get("spine_colors"), dict):
        fig._histo_spine_colors = {  # type: ignore[attr-defined]
            str(k): str(v) for k, v in snap["spine_colors"].items()
        }
    elif isinstance(getattr(fig, "_histo_spine_colors", None), dict):
        pass
    else:
        fig._histo_spine_colors = {}  # type: ignore[attr-defined]
    apply_histo_line_style_to_ax(
        ax,
        {
            "spine_linewidths": snap.get("spine_linewidths"),
            "tick_widths": snap.get("tick_widths"),
        },
    )
    apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig))


def apply_histo_wasd(
    fig,
    ax,
    wasd: Dict[str, Dict[str, bool]],
    tick_state: Dict[str, bool],
    state: HistoState,
    *,
    changed_sides: Optional[Set[str]] = None,
) -> None:
    if changed_sides is None:
        changed_sides = {"bottom", "top", "left", "right"}
    apply_wasd_spines(ax, wasd)
    apply_wasd_tick_params(ax, wasd)
    direction = getattr(fig, "_tick_direction", "out")
    ax.tick_params(axis="both", which="both", direction=direction)
    tick_lengths = getattr(fig, "_tick_lengths", {}) or {}
    major = tick_lengths.get("major")
    if major is not None:
        minor = tick_lengths.get("minor", float(major) * 0.7)
        ax.tick_params(axis="both", which="major", length=major)
        ax.tick_params(axis="both", which="minor", length=minor)

    bottom = wasd.get("bottom", {})
    if bool(bottom.get("title", True)):
        ax.set_xlabel(state.style.xlabel, fontsize=state.style.label_fontsize)
        ax.xaxis.label.set_visible(True)
    else:
        if not hasattr(ax, "_stored_xlabel"):
            ax._stored_xlabel = state.style.xlabel
        ax.xaxis.label.set_visible(False)

    top = wasd.get("top", {})
    ax._top_xlabel_on = bool(top.get("title", False))  # type: ignore[attr-defined]
    if state.style.top_xlabel:
        ax._top_xlabel_text_override = state.style.top_xlabel  # type: ignore[attr-defined]

    left = wasd.get("left", {})
    ylab = state.style.ylabel or state.y_label_default()
    if bool(left.get("title", True)):
        ax.set_ylabel(ylab, fontsize=state.style.label_fontsize)
        ax.yaxis.label.set_visible(True)
    else:
        if not hasattr(ax, "_stored_ylabel"):
            ax._stored_ylabel = ylab
        ax.yaxis.label.set_visible(False)

    apply_changed_side_title_positions(
        changed_sides,
        bottom=lambda: position_bottom_xlabel(ax, fig, tick_state),
        top=lambda: position_top_xlabel(ax, fig, tick_state),
        left=lambda: position_left_ylabel(ax, fig, tick_state),
        right=lambda: None,
    )
    _restore_histo_tick_locators(ax, fig)
    apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig), only_sides=changed_sides)
    from .plot import apply_histo_grid

    apply_histo_grid(ax, state)


def reapply_histo_spine_layout(
    fig,
    ax,
    state: HistoState,
    *,
    changed_sides: Optional[Set[str]] = None,
) -> None:
    tick_state = ensure_histo_tick_state(ax)
    wasd = ensure_histo_wasd(fig, ax, tick_state)
    apply_histo_wasd(fig, ax, wasd, tick_state, state, changed_sides=changed_sides)
    # Locators after WASD, then full spine/tick color reapply (must be last).
    _restore_histo_tick_locators(ax, fig)
    apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig))
    from .plot import apply_histo_grid

    apply_histo_grid(ax, state)


def sync_histo_spine_from_reference(ref_fig, ref_ax, targets: list[tuple[Any, Any]]) -> None:
    snap = capture_histo_spine_snapshot(ref_fig, ref_ax)
    for fig, ax in targets:
        apply_histo_spine_snapshot(fig, ax, snap)
        apply_histo_spine_colors(fig, ax, snap.get("spine_colors"))


def persist_histo_spine_before_redraw(
    fig,
    ax,
    *,
    sync_targets: list[tuple[Any, Any]] | None = None,
) -> dict:
    """Capture spine/tick state from the live axis before histogram redraw clears locators."""
    snap = capture_histo_spine_snapshot(fig, ax)
    if sync_targets:
        for tfig, tax in sync_targets:
            apply_histo_spine_snapshot(tfig, tax, snap)
    return snap


def histo_title_offset_menu(
    *,
    fig,
    ax,
    tick_state: Dict[str, bool],
    push_state: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Nudge bottom/left axis title positions (histogram has no duplicate top/right titles)."""

    def _dpi() -> float:
        try:
            return float(fig.dpi)
        except Exception:
            return 72.0

    def _px_value(attr: str) -> float:
        try:
            pts = float(getattr(ax, attr, 0.0) or 0.0)
        except Exception:
            pts = 0.0
        return pts * _dpi() / 72.0

    def _set_attr(attr: str, pts: float) -> None:
        try:
            setattr(ax, attr, float(pts))
        except Exception:
            pass

    def _nudge(attr: str, delta_px: float) -> None:
        try:
            current_pts = float(getattr(ax, attr, 0.0) or 0.0)
        except Exception:
            current_pts = 0.0
        delta_pts = float(delta_px) * 72.0 / _dpi()
        _set_attr(attr, current_pts + delta_pts)

    snapshot_taken = False

    def _ensure_snapshot() -> None:
        nonlocal snapshot_taken
        if not snapshot_taken:
            push_state()
            snapshot_taken = True

    while True:
        print("Title offsets (bottom X / left Y):")
        print("  s: bottom X label   a: left Y label   q: back")
        choice = safe_input(colorize_prompt("Title offset (s/a/q): ")).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "s":
            while True:
                y_px = _px_value("_bottom_xlabel_manual_offset_y_pts")
                print(f"Bottom title offset: Y={y_px:+.2f} px")
                sub = safe_input(colorize_prompt("bottom (w=up, s=down, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == "q":
                    break
                if sub == "0":
                    _ensure_snapshot()
                    _set_attr("_bottom_xlabel_manual_offset_y_pts", 0.0)
                elif sub == "w":
                    _ensure_snapshot()
                    _nudge("_bottom_xlabel_manual_offset_y_pts", +1.0)
                elif sub == "s":
                    _ensure_snapshot()
                    _nudge("_bottom_xlabel_manual_offset_y_pts", -1.0)
                else:
                    print("Unknown choice.")
                    continue
                position_bottom_xlabel(ax, fig, tick_state)
                fig.canvas.draw_idle()
            continue
        if choice == "a":
            while True:
                x_px = _px_value("_left_ylabel_manual_offset_x_pts")
                print(f"Left title offset: X={x_px:+.2f} px")
                sub = safe_input(colorize_prompt("left (a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == "q":
                    break
                if sub == "0":
                    _ensure_snapshot()
                    _set_attr("_left_ylabel_manual_offset_x_pts", 0.0)
                elif sub == "a":
                    _ensure_snapshot()
                    _nudge("_left_ylabel_manual_offset_x_pts", -1.0)
                elif sub == "d":
                    _ensure_snapshot()
                    _nudge("_left_ylabel_manual_offset_x_pts", +1.0)
                else:
                    print("Unknown choice.")
                    continue
                position_left_ylabel(ax, fig, tick_state)
                fig.canvas.draw_idle()
            continue
        print("Unknown choice.")


__all__ = [
    "apply_histo_spine_colors",
    "apply_histo_spine_snapshot",
    "apply_histo_wasd",
    "capture_histo_spine_snapshot",
    "ensure_histo_tick_state",
    "ensure_histo_wasd",
    "format_histo_spine_extra_report",
    "get_histo_spine_colors",
    "histo_title_offset_menu",
    "persist_histo_spine_before_redraw",
    "reapply_histo_spine_layout",
    "set_histo_spine_color",
    "sync_histo_spine_colors_from_reference",
    "sync_histo_spine_from_reference",
]
