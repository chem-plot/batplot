"""Spine/tick color helpers for XY mode (mirrors EC ``_apply_spine_color``)."""

from __future__ import annotations

from typing import Any, Mapping

from matplotlib import colors as mcolors  # type: ignore[import]

from ...ui import (
    finalize_spine_colors,
    position_bottom_xlabel,
    position_left_ylabel,
    position_right_ylabel,
    position_top_xlabel,
    set_spine_side_color,
)

_SPINE_SIDES = ("top", "bottom", "left", "right")


def _normalize_spine_color(color) -> str:
    try:
        return mcolors.to_hex(mcolors.to_rgb(color))
    except (ValueError, TypeError):
        return str(color)


def _apply_stored_xy_axis_colors(ax) -> None:
    """Re-apply stored duplicate axis title colors (same as EC)."""
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


def _sync_xy_grid_color(ax, side: str, color) -> None:
    """Recolor visible grid lines at tick positions (only when grid is on)."""
    try:
        if side in ("left", "right"):
            lines = ax.get_ygridlines()
        elif side in ("top", "bottom"):
            lines = ax.get_xgridlines()
        else:
            return
        if not any(gl.get_visible() for gl in lines):
            return
        for gl in lines:
            if gl.get_visible():
                gl.set_color(color)
    except Exception:
        pass


def ensure_xy_tick_state(ax, tick_state: Mapping[str, bool] | None = None) -> dict[str, bool]:
    if isinstance(tick_state, dict) and tick_state:
        return dict(tick_state)
    saved = getattr(ax, "_saved_tick_state", None)
    if isinstance(saved, dict) and saved:
        return dict(saved)
    return {
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": False,
        "r_labels": False,
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
    }


def get_xy_spine_colors(fig) -> dict[str, str]:
    stored = getattr(fig, "_xy_spine_colors", None)
    if isinstance(stored, dict):
        return {str(k): str(v) for k, v in stored.items()}
    return {}


def _sync_xy_mpl_tick_kw(ax, side: str, color, tick_state: Mapping[str, bool]) -> None:
    """Set axis tick kw via tick_params so mpl rebuilds tick *lines* with this color on draw."""
    ts = ensure_xy_tick_state(ax, tick_state)
    hex_color = _normalize_spine_color(color)
    try:
        if side == "left":
            if not bool(ts.get("l_ticks", ts.get("ly", True))):
                return
            if bool(ts.get("r_ticks", ts.get("ry", False))):
                return
            ax.tick_params(axis="y", which="both", colors=hex_color, labelcolor=hex_color)
        elif side == "right":
            if not bool(ts.get("r_ticks", ts.get("ry", False))):
                return
            if bool(ts.get("l_ticks", ts.get("ly", True))):
                return
            ax.tick_params(axis="y", which="both", colors=hex_color, labelcolor=hex_color)
        elif side == "bottom":
            if not bool(ts.get("b_ticks", ts.get("bx", True))):
                return
            if bool(ts.get("t_ticks", ts.get("tx", False))):
                return
            ax.tick_params(axis="x", which="both", colors=hex_color, labelcolor=hex_color)
        elif side == "top":
            if not bool(ts.get("t_ticks", ts.get("tx", False))):
                return
            if bool(ts.get("b_ticks", ts.get("bx", True))):
                return
            ax.tick_params(axis="x", which="both", colors=hex_color, labelcolor=hex_color)
    except Exception:
        pass


def apply_xy_spine_color(
    fig,
    ax,
    tick_state: Mapping[str, bool],
    side: str,
    color,
) -> None:
    """Apply one spine color like EC ``_apply_spine_color``."""
    if color is None or side not in _SPINE_SIDES:
        return
    hex_color = _normalize_spine_color(color)
    ts = ensure_xy_tick_state(ax, tick_state)
    if not hasattr(fig, "_xy_spine_colors") or not isinstance(
        getattr(fig, "_xy_spine_colors", None), dict
    ):
        fig._xy_spine_colors = {}  # type: ignore[attr-defined]
    fig._xy_spine_colors[side] = hex_color  # type: ignore[attr-defined]
    try:
        set_spine_side_color(ax, side, hex_color, fig=fig)
        if side == "top":
            ax._stored_top_xlabel_color = hex_color  # type: ignore[attr-defined]
            position_top_xlabel(ax, fig, ts)
        elif side == "bottom":
            ax._stored_xlabel_color = hex_color  # type: ignore[attr-defined]
            position_bottom_xlabel(ax, fig, ts)
        elif side == "left":
            ax._stored_ylabel_color = hex_color  # type: ignore[attr-defined]
            position_left_ylabel(ax, fig, ts)
            _sync_xy_grid_color(ax, side, hex_color)
        elif side == "right":
            ax._stored_right_ylabel_color = hex_color  # type: ignore[attr-defined]
            position_right_ylabel(ax, fig, ts)
            _sync_xy_grid_color(ax, side, hex_color)
    except Exception:
        pass
    _sync_xy_mpl_tick_kw(ax, side, hex_color, ts)
    _apply_stored_xy_axis_colors(ax)
    # Per-tick artists again after tick_params (labels/lines must match)
    try:
        set_spine_side_color(ax, side, hex_color, fig=None)
    except Exception:
        pass


def apply_xy_spine_colors(
    fig,
    ax,
    tick_state: Mapping[str, bool],
    colors: Mapping[str, Any] | None,
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
        if color is None:
            continue
        apply_xy_spine_color(fig, ax, tick_state, side, color)
    try:
        finalize_spine_colors(
            fig,
            ax,
            tick_state=tick_state,
            colors=colors,
            sides=only_sides,
        )
    except Exception:
        pass


def apply_xy_spine_specs(
    fig,
    ax,
    tick_state: Mapping[str, bool],
    spines_cfg: Mapping[str, Any] | None,
) -> None:
    """Apply linewidth/visibility/color from a spines config dict."""
    if not spines_cfg:
        return
    colors: dict[str, Any] = {}
    for name, spec in spines_cfg.items():
        if name not in _SPINE_SIDES:
            continue
        sp = ax.spines.get(name)
        if sp is None:
            continue
        if not isinstance(spec, dict):
            if spec is not None:
                colors[name] = spec
            continue
        if spec.get("linewidth") is not None:
            try:
                sp.set_linewidth(spec["linewidth"])
            except Exception:
                pass
        if spec.get("visible") is not None:
            try:
                sp.set_visible(bool(spec["visible"]))
            except Exception:
                pass
        if spec.get("color") is not None:
            colors[name] = spec["color"]
        elif spec.get("lw") is not None:
            try:
                sp.set_linewidth(spec["lw"])
            except Exception:
                pass
    apply_xy_spine_colors(fig, ax, tick_state, colors)


__all__ = [
    "apply_xy_spine_color",
    "apply_xy_spine_colors",
    "apply_xy_spine_specs",
    "ensure_xy_tick_state",
    "get_xy_spine_colors",
]
