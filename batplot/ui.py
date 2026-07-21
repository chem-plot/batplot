"""UI utilities for batplot: font/tick helpers and resize operations.

This module provides functions for managing fonts, tick labels, and axis labels
in batplot plots. It handles:
- Font family and size changes across all text elements
- Positioning of duplicate axis labels (top x-axis, right y-axis)
- Font synchronization to ensure consistency

HOW FONT MANAGEMENT WORKS:
--------------------------
When you change fonts in the interactive menu, we need to update fonts for:
- Curve labels (text objects identifying each curve)
- Axis labels (x-axis and y-axis titles)
- Duplicate axis labels (top x-axis, right y-axis)
- Tick labels (numbers on axes)
- All of these must stay synchronized

This module provides functions to apply font changes consistently across
all these elements.
"""

from __future__ import annotations

import os
from typing import List, Dict, Any, Optional
import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib import colors as mcolors  # type: ignore[import]
from matplotlib.ticker import (  # type: ignore[import]
    AutoLocator,
    AutoMinorLocator,
    MultipleLocator,
    NullFormatter,
    NullLocator,
)
from .plot_modes.common.terminal import safe_input
import matplotlib.transforms as mtransforms  # type: ignore[import]

_DEBUG_SPINE_COLOR = os.environ.get("BATPLOT_DEBUG_SPINE_COLOR", "").strip().lower() in ("1", "true", "yes")


def _debug_spine(msg: str) -> None:
    """Print spine color debug message when BATPLOT_DEBUG_SPINE_COLOR is set."""
    if _DEBUG_SPINE_COLOR:
        print(msg)


def _hex_color(color) -> str:
    try:
        return mcolors.to_hex(mcolors.to_rgb(color))
    except (ValueError, TypeError):
        return str(color)


def format_spine_side_tick_report(
    ax,
    side: str,
    *,
    expected_color=None,
    wasd_state: dict | None = None,
) -> str:
    """Human-readable spine/tick/label visibility and color check for one side."""
    side = str(side).lower()
    lines = [f"Spine/tick check ({side}):"]
    sp = ax.spines.get(side)
    if sp is None:
        lines.append("  spine: MISSING")
    else:
        lines.append(
            f"  spine: visible={sp.get_visible()} edge={_hex_color(sp.get_edgecolor())}"
        )

    if wasd_state and side in wasd_state:
        st = wasd_state.get(side) or {}
        lines.append(
            "  wasd: "
            f"spine={st.get('spine', '?')} ticks={st.get('ticks', '?')} "
            f"labels={st.get('labels', '?')} title={st.get('title', '?')}"
        )

    axis = ax.xaxis if side in ("top", "bottom") else ax.yaxis
    axis_name = "x" if side in ("top", "bottom") else "y"
    use_tick1 = side in ("bottom", "left")
    line_attr = "tick1line" if use_tick1 else "tick2line"
    label_attr = "label1" if use_tick1 else "label2"

    try:
        major_kw = getattr(axis, "_major_tick_kw", {}) or {}
        lines.append(
            f"  mpl tick_params ({axis_name} major): "
            f"left={major_kw.get('left', '?')} labelleft={major_kw.get('labelleft', '?')} "
            f"right={major_kw.get('right', '?')} labelright={major_kw.get('labelright', '?')} "
            f"bottom={major_kw.get('bottom', '?')} labelbottom={major_kw.get('labelbottom', '?')} "
            f"top={major_kw.get('top', '?')} labeltop={major_kw.get('labeltop', '?')} "
            f"color={major_kw.get('color', '?')} labelcolor={major_kw.get('labelcolor', '?')}"
        )
    except Exception:
        pass

    exp_hex = _hex_color(expected_color) if expected_color is not None else None
    major_n = minor_n = 0
    label_colors: list[str] = []
    line_colors: list[str] = []
    for which in ("major", "minor"):
        try:
            ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
        except Exception:
            ticks = []
        for t in ticks:
            ln = getattr(t, line_attr, None)
            lab = getattr(t, label_attr, None)
            if ln is not None and ln.get_visible():
                if which == "major":
                    major_n += 1
                else:
                    minor_n += 1
                line_colors.append(_hex_color(ln.get_color()))
            if lab is not None and lab.get_visible():
                label_colors.append(_hex_color(lab.get_color()))

    lines.append(f"  tick artists ({line_attr}/{label_attr}): major={major_n} minor={minor_n}")
    if label_colors:
        sample = label_colors[:4]
        extra = f" (+{len(label_colors) - 4} more)" if len(label_colors) > 4 else ""
        lines.append(f"  label colors: {sample}{extra}")
    else:
        lines.append("  label colors: (none visible)")
    if line_colors:
        lines.append(f"  visible tick line colors: {line_colors[:4]}")
    else:
        lines.append("  visible tick lines: (none on this side)")

    if exp_hex in ("#ffffff", "#fff", "white"):
        lines.append(
            "  note: white on a white figure background looks invisible "
            "(spine, ticks, labels, title are still set to white)"
        )

    if side == "bottom":
        try:
            lines.append(f"  axis title (x): {_hex_color(ax.xaxis.label.get_color())}")
        except Exception:
            pass
    elif side == "left":
        try:
            lines.append(f"  axis title (y): {_hex_color(ax.yaxis.label.get_color())}")
        except Exception:
            pass

    if exp_hex:
        mismatches = []
        if sp is not None and _hex_color(sp.get_edgecolor()) != exp_hex:
            mismatches.append(f"spine={_hex_color(sp.get_edgecolor())}")
        bad_labels = [c for c in label_colors if c != exp_hex]
        if bad_labels:
            mismatches.append(f"labels={bad_labels[:3]}")
        bad_lines = [c for c in line_colors if c != exp_hex]
        if bad_lines:
            mismatches.append(f"tick_lines={bad_lines[:3]}")
        if mismatches:
            lines.append(f"  MISMATCH (expected {exp_hex}): {', '.join(mismatches)}")
        elif label_colors or line_colors:
            lines.append(f"  OK: matches expected {exp_hex}")
        else:
            lines.append(
                f"  WARNING: expected {exp_hex} but no visible tick labels/lines on this side "
                "(check wasd ticks/labels or run with ticks visible)"
            )
    return "\n".join(lines)


def _poke_axis_tick_color_kw(axis, color) -> None:
    """Deprecated: axis-wide tick kw overwrites the opposite side on shared x/y axes."""
    _debug_spine("[DEBUG spine] _poke_axis_tick_color_kw skipped (per-side coloring only)")


def _axis_for_spine_side(ax, side: str):
    return ax.xaxis if side in ("top", "bottom") else ax.yaxis


def _visible_tick_sides_on_axis(ax, axis) -> dict[str, bool]:
    major = getattr(axis, "_major_tick_kw", {}) or {}
    if axis is ax.xaxis:
        return {
            "bottom": bool(major.get("bottom", major.get("tick1On", True))),
            "top": bool(major.get("top", major.get("tick2On", False))),
        }
    return {
        "left": bool(major.get("left", major.get("tick1On", True))),
        "right": bool(major.get("right", major.get("tick2On", False))),
    }


def _resolve_tick_state(ax, tick_state=None) -> dict:
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


def _side_ticks_on(ts: dict, side: str) -> bool:
    key_map = {
        "left": ("l_ticks", "ly"),
        "right": ("r_ticks", "ry"),
        "bottom": ("b_ticks", "bx"),
        "top": ("t_ticks", "tx"),
    }
    for key in key_map.get(side, ()):
        if key in ts:
            return bool(ts[key])
    return side in ("bottom", "left")


def _sync_mpl_tick_params_for_side(ax, side: str, color, tick_state=None) -> None:
    """Set axis tick kw via tick_params so mpl rebuilds tick lines with this color on draw."""
    ts = _resolve_tick_state(ax, tick_state)
    hex_color = _hex_color(color)
    opposite = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
    if not _side_ticks_on(ts, side):
        return
    if _side_ticks_on(ts, opposite[side]):
        return
    try:
        if side in ("left", "right"):
            ax.tick_params(axis="y", which="both", colors=hex_color, labelcolor=hex_color)
        else:
            ax.tick_params(axis="x", which="both", colors=hex_color, labelcolor=hex_color)
    except Exception:
        pass


def get_fig_spine_colors(fig) -> dict[str, str]:
    """Merged per-side spine colors from all mode-specific figure stores."""
    merged: dict[str, str] = {}
    for attr in (
        "_cpc_spine_colors",
        "_xy_spine_colors",
        "_histo_spine_colors",
        "_bp_spine_side_colors",
    ):
        stored = getattr(fig, attr, None)
        if not isinstance(stored, dict):
            continue
        for key, value in stored.items():
            if value is not None:
                merged[str(key)] = _hex_color(value)
    return merged


def finalize_spine_colors(
    fig,
    ax,
    tick_state=None,
    colors=None,
    *,
    sides=None,
    draw: bool = False,
) -> None:
    """Re-apply stored spine/tick colors after tick_params or canvas draw (all modes)."""
    if colors is None:
        ax_store = getattr(ax, "_bp_spine_side_colors", None)
        if isinstance(ax_store, dict) and ax_store:
            colors = {
                str(k): _hex_color(v)
                for k, v in ax_store.items()
                if v is not None and str(k) in ("top", "bottom", "left", "right")
            }
        else:
            colors = get_fig_spine_colors(fig)
    if not colors:
        return
    ts = _resolve_tick_state(ax, tick_state)
    for side, hex_c in colors.items():
        if side not in ("top", "bottom", "left", "right"):
            continue
        if sides is not None and side not in sides:
            continue
        if ax.spines.get(side) is None:
            continue
        _sync_mpl_tick_params_for_side(ax, side, hex_c, ts)
        _apply_side_color_once(ax, side, hex_c)
        _store_and_sync_tick_kw(ax, side, hex_c)
    ensure_spine_color_draw_hook(fig, ax)
    if draw:
        _refresh_canvas_after_spine_color(fig)
        for side, hex_c in colors.items():
            if side not in ("top", "bottom", "left", "right"):
                continue
            if sides is not None and side not in sides:
                continue
            if ax.spines.get(side) is None:
                continue
            _apply_side_color_once(ax, side, hex_c)
            _sync_mpl_tick_params_for_side(ax, side, hex_c, ts)


def finalize_spine_colors_cpc(
    fig,
    ax,
    ax2,
    tick_state=None,
    colors=None,
    *,
    draw: bool = False,
) -> None:
    """Re-apply CPC spine colors on ax (left/bottom/top) and ax2 (right/bottom/top)."""
    colors = colors or get_fig_spine_colors(fig)
    if not colors:
        return
    try:
        fig._bp_spine_secondary_ax = ax2  # type: ignore[attr-defined]
    except Exception:
        pass
    axes_map = {
        "top": [ax, ax2],
        "bottom": [ax, ax2],
        "left": [ax],
        "right": [ax2] if ax2 is not None else [],
    }
    for side, hex_c in colors.items():
        if side not in ("top", "bottom", "left", "right"):
            continue
        for curr_ax in axes_map.get(side, [ax]):
            if curr_ax is None or curr_ax.spines.get(side) is None:
                continue
            ts = _resolve_tick_state(curr_ax, tick_state)
            _sync_mpl_tick_params_for_side(curr_ax, side, hex_c, ts)
            _apply_side_color_once(curr_ax, side, hex_c)
            _store_and_sync_tick_kw(curr_ax, side, hex_c)
    ensure_spine_color_draw_hook(fig, ax)
    if draw:
        _refresh_canvas_after_spine_color(fig)
        for side, hex_c in colors.items():
            if side not in ("top", "bottom", "left", "right"):
                continue
            for curr_ax in axes_map.get(side, [ax]):
                if curr_ax is None or curr_ax.spines.get(side) is None:
                    continue
                ts = _resolve_tick_state(curr_ax, tick_state)
                _apply_side_color_once(curr_ax, side, hex_c)
                _sync_mpl_tick_params_for_side(curr_ax, side, hex_c, ts)


def finalize_spine_colors_for_axes(
    fig,
    axis_entries,
    *,
    draw: bool = False,
) -> None:
    """Re-apply spine colors on multiple axes (e.g. operando + EC panel)."""
    for entry in axis_entries:
        if not entry:
            continue
        if isinstance(entry, tuple):
            curr_ax, ts = entry[0], entry[1] if len(entry) > 1 else None
        else:
            curr_ax, ts = entry, None
        if curr_ax is None:
            continue
        finalize_spine_colors(fig, curr_ax, tick_state=ts, draw=False)
    if draw:
        _refresh_canvas_after_spine_color(fig)
        for entry in axis_entries:
            if not entry:
                continue
            if isinstance(entry, tuple):
                curr_ax, ts = entry[0], entry[1] if len(entry) > 1 else None
            else:
                curr_ax, ts = entry, None
            if curr_ax is None:
                continue
            finalize_spine_colors(fig, curr_ax, tick_state=ts, draw=False)


def _collect_visible_tick_line_colors(ax, side: str) -> list[str]:
    axis = _axis_for_spine_side(ax, side)
    use_tick1 = side in ("bottom", "left")
    line_attr = "tick1line" if use_tick1 else "tick2line"
    colors: list[str] = []
    for which in ("major", "minor"):
        try:
            ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
        except Exception:
            ticks = []
        for t in ticks:
            ln = getattr(t, line_attr, None)
            if ln is not None and ln.get_visible():
                colors.append(_hex_color(ln.get_color()))
    try:
        ticklines = axis.get_ticklines(which="both")
        if ticklines:
            half = len(ticklines) // 2
            active = ticklines[:half] if use_tick1 else ticklines[half:]
            for line in active:
                if line is not None and line.get_visible():
                    colors.append(_hex_color(line.get_color()))
    except Exception:
        pass
    return colors


def _store_and_sync_tick_kw(ax, side: str, color) -> None:
    """Persist per-side tick color and sync axis tick kw when one side owns the axis."""
    axis = _axis_for_spine_side(ax, side)
    hex_color = _hex_color(color)
    store = getattr(axis, "_bp_side_tick_colors", None)
    if not isinstance(store, dict):
        store = {}
    store[side] = hex_color
    axis._bp_side_tick_colors = store  # type: ignore[attr-defined]

    visible = _visible_tick_sides_on_axis(ax, axis)
    active_sides = [name for name, on in visible.items() if on]
    if len(active_sides) == 1 and active_sides[0] == side:
        for kw_name in ("_major_tick_kw", "_minor_tick_kw"):
            kw = getattr(axis, kw_name, None)
            if isinstance(kw, dict):
                kw["color"] = color
                kw["labelcolor"] = color
        _debug_spine(
            f"[DEBUG spine]   synced {side} -> axis tick kw color={hex_color} "
            f"(sole active side on axis)"
        )


def _get_fig_spine_color_store(fig) -> dict[str, str]:
    return get_fig_spine_colors(fig)


def _reapply_all_stored_spine_colors(fig, ax) -> None:
    ax2 = getattr(fig, "_bp_spine_secondary_ax", None)
    if isinstance(getattr(fig, "_cpc_spine_colors", None), dict) and ax2 is not None:
        finalize_spine_colors_cpc(fig, ax, ax2)
    else:
        finalize_spine_colors(fig, ax)


def ensure_spine_color_draw_hook(fig, ax) -> None:
    """After each canvas draw, re-apply stored spine/tick colors if mpl reset them."""
    if getattr(fig, "_bp_spine_draw_cid", None) is not None:
        return

    def _after_draw(event) -> None:
        if event.canvas.figure is not fig:
            return
        if getattr(fig, "_bp_spine_reapply_busy", False):
            return
        colors = _get_fig_spine_color_store(fig)
        if not colors:
            return
        mismatched = []
        for side, hex_c in colors.items():
            lines = _collect_visible_tick_line_colors(ax, side)
            if lines and any(c != _hex_color(hex_c) for c in lines):
                mismatched.append(side)
        if not mismatched:
            return
        fig._bp_spine_reapply_busy = True  # type: ignore[attr-defined]
        try:
            _reapply_all_stored_spine_colors(fig, ax)
        finally:
            fig._bp_spine_reapply_busy = False  # type: ignore[attr-defined]
        try:
            event.canvas.draw_idle()
        except Exception:
            pass

    fig._bp_spine_draw_cid = fig.canvas.mpl_connect("draw_event", _after_draw)  # type: ignore[attr-defined]


def format_spine_draw_stability_report(
    fig,
    ax,
    side: str,
    *,
    expected_color=None,
) -> str:
    """Show whether canvas.draw() wipes tick line colors (common GUI bug)."""
    import matplotlib as mpl

    exp_hex = _hex_color(expected_color) if expected_color is not None else None
    lines = [f"Draw stability check ({side}):"]
    try:
        import batplot.ui as ui_mod

        lines.append(f"  ui module: {ui_mod.__file__}")
    except Exception:
        pass
    lines.append(f"  matplotlib: {mpl.__version__}")
    lines.append(f"  canvas: {type(fig.canvas).__name__}")

    axis = _axis_for_spine_side(ax, side)
    major_kw = getattr(axis, "_major_tick_kw", {}) or {}
    lines.append(
        f"  axis tick kw (major): color={major_kw.get('color', '?')} "
        f"labelcolor={major_kw.get('labelcolor', '?')}"
    )
    visible = _visible_tick_sides_on_axis(ax, axis)
    lines.append(f"  active tick sides on axis: {visible}")

    try:
        grid_on = bool(getattr(ax.yaxis if side in ("left", "right") else ax.xaxis, "_gridOnMajor", False))
        lines.append(f"  grid on this axis: {grid_on}")
    except Exception:
        pass

    before = _collect_visible_tick_line_colors(ax, side)
    lines.append(f"  tick lines BEFORE draw: {before[:6] or '(none visible)'}")

    try:
        fig.canvas.draw()
    except Exception as exc:
        lines.append(f"  draw failed: {exc}")
        return "\n".join(lines)

    after = _collect_visible_tick_line_colors(ax, side)
    lines.append(f"  tick lines AFTER draw: {after[:6] or '(none visible)'}")

    if exp_hex:
        bad_after = [c for c in after if c != exp_hex]
        if bad_after and before and all(c == exp_hex for c in before):
            lines.append(
                f"  *** DRAW RESET TICKS: were {exp_hex}, now {bad_after[:3]} "
                f"(mpl rebuilt tick lines from axis kw; re-applying now)"
            )
        elif bad_after:
            lines.append(f"  tick line mismatch after draw: expected {exp_hex}, got {bad_after[:3]}")
        elif after:
            lines.append(f"  tick lines survived draw: {exp_hex}")

    _apply_side_color_once(ax, side, expected_color)
    if expected_color is not None:
        _store_and_sync_tick_kw(ax, side, expected_color)
    fixed = _collect_visible_tick_line_colors(ax, side)
    lines.append(f"  tick lines AFTER re-apply: {fixed[:6] or '(none visible)'}")
    if exp_hex and fixed:
        if all(c == exp_hex for c in fixed):
            lines.append(f"  re-apply OK: visible tick lines are {exp_hex}")
        else:
            lines.append(
                f"  *** RE-APPLY FAILED: still {fixed[:3]} (expected {exp_hex}) — "
                "restart batplot to load latest code; check ui module path above"
            )
    return "\n".join(lines)


def _color_side_tick_getters(ax, side: str, color) -> None:
    """Color tick labels/lines for one side only (no visibility, no axis-wide kw)."""
    try:
        if side == "left":
            axis = ax.yaxis
            attrs = ("tick1line", "label1")
            ticklines = axis.get_ticklines(which="both")
            use_tick1_lines = True
        elif side == "right":
            axis = ax.yaxis
            attrs = ("tick2line", "label2")
            ticklines = axis.get_ticklines(which="both")
            use_tick1_lines = False
        elif side == "bottom":
            axis = ax.xaxis
            attrs = ("tick1line", "label1")
            ticklines = axis.get_ticklines(which="both")
            use_tick1_lines = True
        elif side == "top":
            axis = ax.xaxis
            attrs = ("tick2line", "label2")
            ticklines = axis.get_ticklines(which="both")
            use_tick1_lines = False
        else:
            return
        for tick in axis.get_major_ticks() + axis.get_minor_ticks():
            for attr in attrs:
                obj = getattr(tick, attr, None)
                if obj is not None:
                    obj.set_color(color)
        # get_ticklines returns [tick1..., tick2...]; take the active side half
        if ticklines:
            half = len(ticklines) // 2
            active = ticklines[:half] if use_tick1_lines else ticklines[half:]
            for line in active:
                if line is not None and line.get_visible():
                    line.set_color(color)
    except Exception as e:
        _debug_spine(f"[DEBUG spine]   getter tick color: {e}")


def _apply_side_color_once(ax, side: str, color) -> None:
    """Apply spine/tick/label/title colors for one side (no canvas draw).

    Does NOT use tick_params (which would affect both sides of the axis). Instead sets
    the spine and the per-tick artists (tick1line/tick2line, label1/label2) for the
    requested side only.
    """
    _debug_spine(f"[DEBUG spine] set_spine_side_color(ax, side={side!r}, color={color!r})")
    sp = ax.spines.get(side)
    if sp is not None:
        try:
            sp.set_edgecolor(color)
            _debug_spine(f"[DEBUG spine]   spine {side}: set_edgecolor OK")
        except Exception as e:
            _debug_spine(f"[DEBUG spine]   spine {side}: set_edgecolor failed: {e}")

    def _set_tick_side_color(axis, use_tick1: bool):
        """Set color on tick lines and labels for one side. use_tick1=True -> tick1line/label1, else tick2line/label2."""
        line_attr = "tick1line" if use_tick1 else "tick2line"
        label_attr = "label1" if use_tick1 else "label2"
        counts = {"major": 0, "minor": 0}
        for which in ("major", "minor"):
            try:
                ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
            except Exception:
                ticks = []
            for t in ticks:
                try:
                    ln = getattr(t, line_attr, None)
                    if ln is not None:
                        ln.set_color(color)
                        counts[which] += 1
                except Exception as e:
                    _debug_spine(f"[DEBUG spine]   {which} {line_attr} set_color: {e}")
                try:
                    lab = getattr(t, label_attr, None)
                    if lab is not None:
                        lab.set_color(color)
                except Exception as e:
                    _debug_spine(f"[DEBUG spine]   {which} {label_attr} set_color: {e}")
        _debug_spine(f"[DEBUG spine]   axis ticks: major={counts['major']} minor={counts['minor']} ({line_attr}/{label_attr})")

    if side == "top":
        _set_tick_side_color(ax.xaxis, use_tick1=False)
        try:
            ax._stored_top_xlabel_color = color
        except Exception:
            pass
        art = getattr(ax, "_top_xlabel_artist", None)
        if art is not None:
            try:
                art.set_color(color)
                _debug_spine("[DEBUG spine]   top title (_top_xlabel_artist): set_color OK")
            except Exception as e:
                _debug_spine(f"[DEBUG spine]   top title: {e}")
    elif side == "bottom":
        _set_tick_side_color(ax.xaxis, use_tick1=True)
        try:
            ax.xaxis.label.set_color(color)
            ax._stored_xlabel_color = color
            _debug_spine("[DEBUG spine]   bottom title (xaxis.label): set_color OK")
        except Exception as e:
            _debug_spine(f"[DEBUG spine]   bottom title: {e}")
    elif side == "left":
        _set_tick_side_color(ax.yaxis, use_tick1=True)
        try:
            ax.yaxis.label.set_color(color)
            ax._stored_ylabel_color = color
            _debug_spine("[DEBUG spine]   left title (yaxis.label): set_color OK")
        except Exception as e:
            _debug_spine(f"[DEBUG spine]   left title: {e}")
    elif side == "right":
        _set_tick_side_color(ax.yaxis, use_tick1=False)
        try:
            ax._stored_right_ylabel_color = color
        except Exception:
            pass
        art = getattr(ax, "_right_ylabel_artist", None)
        if art is not None:
            try:
                art.set_color(color)
                _debug_spine("[DEBUG spine]   right title (_right_ylabel_artist): set_color OK")
            except Exception as e:
                _debug_spine(f"[DEBUG spine]   right title: {e}")
        # For twin axes (e.g. CPC), y-axis label is ax.yaxis.label when positioned on right
        try:
            if ax.yaxis.get_label_position() == "right":
                ax.yaxis.label.set_color(color)
                _debug_spine("[DEBUG spine]   right title (yaxis.label): set_color OK")
        except Exception:
            pass

    _color_side_tick_getters(ax, side, color)
    _store_and_sync_tick_kw(ax, side, color)


def _refresh_canvas_after_spine_color(fig) -> None:
    """Full draw so GUI tick line colors survive matplotlib's post-draw rebuild."""
    try:
        fig.canvas.draw()
        try:
            fig.canvas.flush_events()
        except Exception:
            pass
    except Exception:
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass


def set_spine_side_color(ax, side: str, color, fig=None, tick_state=None) -> None:
    """Set color for one side: spine, ticks, labels, and axis title."""
    ts = _resolve_tick_state(ax, tick_state)
    _apply_side_color_once(ax, side, color)
    _sync_mpl_tick_params_for_side(ax, side, color, ts)
    hex_c = _hex_color(color)
    # Per-axis store so dual-panel figures (operando+EC) do not overwrite each other.
    ax_store = getattr(ax, "_bp_spine_side_colors", None)
    if not isinstance(ax_store, dict):
        ax_store = {}
    ax_store[side] = hex_c
    ax._bp_spine_side_colors = ax_store  # type: ignore[attr-defined]
    if fig is not None:
        store = getattr(fig, "_bp_spine_side_colors", None)
        if not isinstance(store, dict):
            store = {}
        store[side] = hex_c
        fig._bp_spine_side_colors = store  # type: ignore[attr-defined]
        ensure_spine_color_draw_hook(fig, ax)
        _refresh_canvas_after_spine_color(fig)
        _apply_side_color_once(ax, side, color)
        _sync_mpl_tick_params_for_side(ax, side, color, ts)
        _store_and_sync_tick_kw(ax, side, color)


def apply_font_changes(ax, fig, label_text_objects: List, normalize_label_text, new_size=None, new_family=None, new_weight=None):
    """
    Apply font size and/or family changes to all text elements in the plot.
    
    HOW IT WORKS:
    ------------
    This function updates fonts for all text elements in the plot:
    1. Curve labels (text objects next to curves)
    2. Axis labels (x-axis and y-axis titles)
    3. Duplicate axis labels (top x-axis, right y-axis)
    4. Tick labels (numbers on axes, including top/right ticks)
    
    FONT FAMILY HANDLING:
    --------------------
    When changing font family, we:
    1. Build a fallback chain (primary font + common fallbacks)
    2. Update matplotlib's rcParams (affects new text)
    3. Update all existing text objects
    
    FONT SIZE HANDLING:
    -------------------
    When changing font size, we:
    1. Update matplotlib's rcParams (affects new text)
    2. Update all existing text objects directly
    
    MATH TEXT FONT SET:
    ------------------
    If font family contains "stix", "times", or "roman", we use STIX math font
    (better for mathematical notation). Otherwise, use DejaVu Sans math font.
    
    Args:
        ax: Matplotlib axes object
        fig: Matplotlib figure object
        label_text_objects: List of Text objects for curve labels
        normalize_label_text: Function to normalize label text (handles LaTeX)
        new_size: New font size (None = don't change)
        new_family: New font family name (None = don't change)
    """
    if new_family:
        fallback_chain = ['DejaVu Sans', 'Arial Unicode MS', 'Liberation Sans']
        existing = plt.rcParams.get('font.sans-serif', [])
        new_list = [new_family] + [f for f in fallback_chain if f != new_family] + \
                   [f for f in existing if f not in fallback_chain and f != new_family]
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = new_list
        lf = new_family.lower()
        if any(k in lf for k in ('stix', 'times', 'roman')):
            plt.rcParams['mathtext.fontset'] = 'stix'
        else:
            plt.rcParams['mathtext.fontset'] = 'dejavusans'
    if new_size is not None:
        plt.rcParams['font.size'] = new_size
    if new_weight is not None:
        from batplot.plot_modes.common.font_extras import normalize_font_weight, set_fig_font_weight
        w = set_fig_font_weight(fig, new_weight)
        new_weight = w
    for txt in label_text_objects:
        if new_size is not None:
            txt.set_fontsize(new_size)
        if new_family:
            txt.set_fontfamily(new_family)
        if new_weight is not None:
            try:
                txt.set_fontweight(new_weight)
            except Exception:
                pass
    for axis_label in (ax.xaxis.label, ax.yaxis.label):
        cur = axis_label.get_text()
        norm = normalize_label_text(cur)
        if norm != cur:
            axis_label.set_text(norm)
        if new_size is not None:
            axis_label.set_fontsize(new_size)
        if new_family:
            axis_label.set_fontfamily(new_family)
        if new_weight is not None:
            try:
                axis_label.set_fontweight(new_weight)
            except Exception:
                pass
    if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
        if new_size is not None:
            ax._top_xlabel_artist.set_fontsize(new_size)
        if new_family:
            ax._top_xlabel_artist.set_fontfamily(new_family)
        if new_weight is not None:
            try:
                ax._top_xlabel_artist.set_fontweight(new_weight)
            except Exception:
                pass
    if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
        if new_size is not None:
            ax._right_ylabel_artist.set_fontsize(new_size)
        if new_family:
            ax._right_ylabel_artist.set_fontfamily(new_family)
        if new_weight is not None:
            try:
                ax._right_ylabel_artist.set_fontweight(new_weight)
            except Exception:
                pass
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        if new_size is not None:
            lbl.set_fontsize(new_size)
        if new_family:
            lbl.set_fontfamily(new_family)
        if new_weight is not None:
            try:
                lbl.set_fontweight(new_weight)
            except Exception:
                pass
    # Also update top/right tick labels (label2)
    try:
        for t in ax.xaxis.get_major_ticks():
            if hasattr(t, 'label2'):
                if new_size is not None: t.label2.set_size(new_size)
                if new_family: t.label2.set_family(new_family)
        for t in ax.yaxis.get_major_ticks():
            if hasattr(t, 'label2'):
                if new_size is not None: t.label2.set_size(new_size)
                if new_family: t.label2.set_family(new_family)
    except Exception:
        pass
    try:
        from batplot.plot_modes.common.font_extras import refresh_font_extras_on_artists
        from batplot.plot_modes.common.fonts import collect_fig_font_artists

        ax2 = getattr(fig, "_xy_ax2", None)
        refresh_font_extras_on_artists(
            fig,
            collect_fig_font_artists(
                ax,
                fig,
                include_title=True,
                extra_axes=[ax2] if ax2 is not None else None,
                extra_artists=list(label_text_objects or []),
            ),
        )
    except Exception:
        pass
    fig.canvas.draw_idle()


def sync_fonts(ax, fig, label_text_objects: List):
    """Sync font size AND family from rcParams to all text objects."""
    try:
        base_size = plt.rcParams.get('font.size')
        base_family_list = plt.rcParams.get('font.sans-serif', [])
        base_family = base_family_list[0] if base_family_list else None
        
        # Set mathtext.fontset based on font family (same logic as apply_font_changes)
        if base_family:
            lf = base_family.lower()
            if any(k in lf for k in ('stix', 'times', 'roman')):
                plt.rcParams['mathtext.fontset'] = 'stix'
            else:
                plt.rcParams['mathtext.fontset'] = 'dejavusans'
        
        if base_size is None:
            return
        
        # Update label text objects
        for txt in label_text_objects:
            txt.set_fontsize(base_size)
            if base_family:
                txt.set_fontfamily(base_family)
        
        base_weight = None
        try:
            from batplot.plot_modes.common.font_extras import get_fig_font_weight, refresh_font_extras_on_artists

            base_weight = get_fig_font_weight(fig)
        except Exception:
            pass
        
        # Update axis labels
        if ax.xaxis.label:
            ax.xaxis.label.set_fontsize(base_size)
            if base_family:
                ax.xaxis.label.set_fontfamily(base_family)
            if base_weight is not None:
                try:
                    ax.xaxis.label.set_fontweight(base_weight)
                except Exception:
                    pass
        if ax.yaxis.label:
            ax.yaxis.label.set_fontsize(base_size)
            if base_family:
                ax.yaxis.label.set_fontfamily(base_family)
            if base_weight is not None:
                try:
                    ax.yaxis.label.set_fontweight(base_weight)
                except Exception:
                    pass
        
        # Update duplicate axis labels (top/right)
        if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
            ax._top_xlabel_artist.set_fontsize(base_size)
            if base_family:
                ax._top_xlabel_artist.set_fontfamily(base_family)
        if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
            ax._right_ylabel_artist.set_fontsize(base_size)
            if base_family:
                ax._right_ylabel_artist.set_fontfamily(base_family)
        
        # Update tick labels
        for tl in ax.get_xticklabels() + ax.get_yticklabels():
            tl.set_fontsize(base_size)
            if base_family:
                tl.set_fontfamily(base_family)
            if base_weight is not None:
                try:
                    tl.set_fontweight(base_weight)
                except Exception:
                    pass

        # Update top/right tick labels (label2)
        try:
            for t in ax.xaxis.get_major_ticks():
                if hasattr(t, 'label2'):
                    t.label2.set_size(base_size)
                    if base_family:
                        t.label2.set_family(base_family)
                    if base_weight is not None:
                        try:
                            t.label2.set_weight(base_weight)
                        except Exception:
                            pass
            for t in ax.yaxis.get_major_ticks():
                if hasattr(t, 'label2'):
                    t.label2.set_size(base_size)
                    if base_family:
                        t.label2.set_family(base_family)
                    if base_weight is not None:
                        try:
                            t.label2.set_weight(base_weight)
                        except Exception:
                            pass
        except Exception:
            pass
        
        try:
            from batplot.plot_modes.common.font_extras import refresh_font_extras_on_artists
            from batplot.plot_modes.common.fonts import collect_fig_font_artists

            ax2 = getattr(fig, "_xy_ax2", None)
            refresh_font_extras_on_artists(
                fig,
                collect_fig_font_artists(
                    ax,
                    fig,
                    include_title=True,
                    extra_axes=[ax2] if ax2 is not None else None,
                    extra_artists=list(label_text_objects or []),
                ),
            )
        except Exception:
            pass
        
        fig.canvas.draw_idle()
    except Exception:
        pass


def position_top_xlabel(ax, fig, tick_state: Dict[str, bool]):
    """
    Position the duplicate x-axis label at the top of the plot.
    
    HOW IT WORKS:
    ------------
    This function creates or updates a text label at the top of the plot that
    duplicates the bottom x-axis label. This is useful when you want the same
    label visible at both top and bottom.
    
    POSITIONING LOGIC:
    -----------------
    1. Measure height of top tick labels (if visible)
    2. Add spacing gap (14 points) to avoid overlap
    3. Apply any manual offsets (if user nudged the label)
    4. Position label above the plot area
    
    COORDINATE SYSTEMS:
    ------------------
    - transAxes: Coordinates relative to axes (0,0 = bottom-left, 1,1 = top-right)
    - points: Physical units (72 points = 1 inch)
    - We use offset_copy() to shift from axes coordinates by a fixed point distance
    
    Args:
        ax: Matplotlib axes object
        fig: Matplotlib figure object
        tick_state: Dictionary tracking which ticks/labels are visible
    """
    try:
        # Check if top xlabel should be visible
        on = bool(getattr(ax, '_top_xlabel_on', False))
        if on:
            # Try multiple sources for label text (in order of priority):
            # 1. Override text (if explicitly set)
            # 2. Current bottom xlabel (most common case)
            # 3. Stored xlabel (backup if bottom label was cleared)
            # 4. Existing artist text (preserve if already exists)
            base = getattr(ax, '_top_xlabel_text_override', None)
            if not base:
                base = ax.get_xlabel()  # Get current bottom x-axis label
            if not base and hasattr(ax, '_stored_xlabel'):
                try:
                    base = ax._stored_xlabel  # Fallback to stored label
                except Exception:
                    pass
            if not base:
                # Last resort: get text from existing artist (if it exists)
                prev = getattr(ax, '_top_xlabel_artist', None)
                if prev is not None and hasattr(prev, 'get_text'):
                    base = prev.get_text() or ''
                else:
                    base = ''  # No text available
            
            # Get renderer to measure text dimensions
            # Renderer converts text to pixels so we can measure its size
            # We wrap in try/except because renderer might not be available in all contexts
            try:
                renderer = fig.canvas.get_renderer()
            except Exception:
                renderer = None

            # Measure tick label height - ONLY use top labels for top title (independence)
            # DPI = dots per inch (resolution of the figure)
            # We need this to convert pixels to points (72 points = 1 inch)
            dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
            max_h_px = 0.0  # Maximum height in pixels (will find tallest tick label)

            # Measure TOP tick labels only (for independence from bottom side)
            # tick_state dictionary tracks which ticks/labels are visible
            # 't_labels' or 'tx' means top x-axis labels are visible
            top_labels_on = bool(tick_state.get('t_labels', tick_state.get('tx', False)))
            if top_labels_on and renderer is not None:
                try:
                    # Loop through all major ticks on x-axis
                    for t in ax.xaxis.get_major_ticks():
                        # label2 is the top tick label (label1 is bottom)
                        lab = getattr(t, 'label2', None)
                        if lab is not None and lab.get_visible():
                            # Get bounding box (size) of this label in pixels
                            bb = lab.get_window_extent(renderer=renderer)
                            if bb is not None:
                                # Track the tallest label (we need space for the tallest one)
                                max_h_px = max(max_h_px, float(bb.height))
                except Exception:
                    pass

            # Convert pixels to points and add gap
            # 72 points = 1 inch, so: points = pixels * 72 / dpi
            # We add 14 points of gap to match matplotlib's default labelpad
            if max_h_px > 0:
                tick_height_pts = max_h_px * 72.0 / dpi  # Convert pixels → points
                dy_pts = tick_height_pts + 14.0  # 14pt gap to match bottom labelpad
            else:
                # No tick labels visible - use minimal spacing
                dy_pts = 6.0  # Minimal spacing when no tick labels (match small labelpad)
            # Apply manual offsets (stored in points) if user nudged the duplicate title
            # Users can manually adjust label position in interactive menu (WASD keys)
            # These offsets are stored as figure attributes and applied here
            try:
                manual_y_pts = float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0)
            except Exception:
                manual_y_pts = 0.0
            try:
                manual_x_pts = float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0)
            except Exception:
                manual_x_pts = 0.0
            dy_pts += manual_y_pts  # Add user's manual vertical offset
            
            # Create coordinate transformation
            # transAxes: coordinates relative to axes (0,0 = bottom-left, 1,1 = top-right)
            # offset_copy: creates a new transform that's offset by fixed point distances
            # This lets us position text at (0.5, 1.0) in axes coords, then shift by points
            base_trans = ax.transAxes  # Base coordinate system (axes-relative)
            off_trans = mtransforms.offset_copy(base_trans, fig=fig, x=manual_x_pts, y=dy_pts, units='points')
            art = getattr(ax, '_top_xlabel_artist', None)
            try:
                dup_color = getattr(ax, '_stored_top_xlabel_color', None) or ax.xaxis.label.get_color()
            except Exception:
                dup_color = getattr(ax, '_stored_top_xlabel_color', None)
            if art is None:
                ax._top_xlabel_artist = ax.text(
                    0.5, 1.0, base, ha='center', va='bottom',
                    transform=off_trans, clip_on=False, zorder=10,
                    color=dup_color
                )
            else:
                ax._top_xlabel_artist.set_transform(off_trans)
                ax._top_xlabel_artist.set_text(base)
                ax._top_xlabel_artist.set_visible(True)
                if dup_color is not None:
                    try:
                        ax._top_xlabel_artist.set_color(dup_color)
                    except Exception:
                        pass
        else:
            if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                try:
                    ax._top_xlabel_artist.set_visible(False)
                except Exception:
                    pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def position_right_ylabel(ax, fig, tick_state: Dict[str, bool]):
    try:
        on = bool(getattr(ax, '_right_ylabel_on', False))
        if on:
            # Try multiple sources for label text: override, left ylabel, stored, or existing artist
            base = getattr(ax, '_right_ylabel_text_override', None)
            if not base:
                base = ax.get_ylabel()
            if not base and hasattr(ax, '_stored_ylabel'):
                try:
                    base = ax._stored_ylabel
                except Exception:
                    pass
            if not base:
                prev = getattr(ax, '_right_ylabel_artist', None)
                if prev is not None and hasattr(prev, 'get_text'):
                    base = prev.get_text() or ''
                else:
                    base = ''
            
            # Get renderer without forcing draws (let main loop handle drawing)
            try:
                renderer = fig.canvas.get_renderer()
            except Exception:
                renderer = None

            # Measure tick label width - ONLY use right labels for right title (independence)
            dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
            max_w_px = 0.0

            # Measure RIGHT tick labels only (for independence from left side)
            right_labels_on = bool(tick_state.get('r_labels', tick_state.get('ry', False)))
            if right_labels_on and renderer is not None:
                try:
                    for t in ax.yaxis.get_major_ticks():
                        lab = getattr(t, 'label2', None)
                        if lab is not None and lab.get_visible():
                            bb = lab.get_window_extent(renderer=renderer)
                            if bb is not None:
                                max_w_px = max(max_w_px, float(bb.width))
                except Exception:
                    pass

            # Convert to points and add gap (6pt gap to visually match left labelpad=8pt)
            if max_w_px > 0:
                tick_width_pts = max_w_px * 72.0 / dpi
                dx_pts = tick_width_pts + 6.0  # 6pt gap to visually match left labelpad
            else:
                dx_pts = 6.0  # Minimal spacing when no tick labels (match small labelpad)
            # Apply manual offsets (stored in points) if user nudged the duplicate title
            try:
                manual_x_pts = float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0)
            except Exception:
                manual_x_pts = 0.0
            try:
                manual_y_pts = float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0)
            except Exception:
                manual_y_pts = 0.0
            dx_pts += manual_x_pts
            
            # Place at (1.0, 0.5) in axes with a points-based offset to the right
            base_trans = ax.transAxes
            off_trans = mtransforms.offset_copy(base_trans, fig=fig, x=dx_pts, y=manual_y_pts, units='points')
            art = getattr(ax, '_right_ylabel_artist', None)
            try:
                dup_color = getattr(ax, '_stored_right_ylabel_color', None) or ax.yaxis.label.get_color()
            except Exception:
                dup_color = getattr(ax, '_stored_right_ylabel_color', None)
            if art is None:
                ax._right_ylabel_artist = ax.text(
                    1.0, 0.5, base,
                    rotation=90, va='center', ha='left', transform=off_trans,
                    clip_on=False, zorder=10,
                    color=dup_color
                )
            else:
                ax._right_ylabel_artist.set_transform(off_trans)
                ax._right_ylabel_artist.set_text(base)
                ax._right_ylabel_artist.set_visible(True)
                if dup_color is not None:
                    try:
                        ax._right_ylabel_artist.set_color(dup_color)
                    except Exception:
                        pass
        else:
            if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                try:
                    ax._right_ylabel_artist.set_visible(False)
                except Exception:
                    pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def position_bottom_xlabel(ax, fig, tick_state: Dict[str, bool]):
    """Adjust bottom X label spacing based on bottom tick label visibility.

    Uses labelpad (in points). Larger pad when bottom tick labels are visible,
    smaller when hidden. Also applies manual offsets if set.
    """
    try:
        lbl = ax.get_xlabel()
        if not lbl:
            return
        # If a one-shot pad restore is pending (after hide->show), honor it once to avoid drift
        if hasattr(ax, '_pending_xlabelpad') and ax._pending_xlabelpad is not None:
            try:
                ax.xaxis.labelpad = ax._pending_xlabelpad
            finally:
                try:
                    delattr(ax, '_pending_xlabelpad')
                except Exception:
                    pass
            return
        # Otherwise choose pad based on current tick label visibility
        pad = 8 if bool(tick_state.get('b_labels', tick_state.get('bx', False))) else 6
        # Apply manual y-offset (affects labelpad - positive = down, negative = up)
        try:
            manual_y_pts = float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0)
        except Exception:
            manual_y_pts = 0.0
        pad += manual_y_pts
        try:
            ax.xaxis.labelpad = pad
        except Exception:
            pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def position_left_ylabel(ax, fig, tick_state: Dict[str, bool]):
    """Adjust left Y label spacing based on left tick label visibility.

    Uses labelpad (in points). Larger pad when left tick labels are visible,
    smaller when hidden.
    """
    try:
        lbl = ax.get_ylabel()
        if not lbl:
            return
        # If a one-shot pad restore is pending (after hide->show), honor it once to avoid drift
        if hasattr(ax, '_pending_ylabelpad') and ax._pending_ylabelpad is not None:
            try:
                ax.yaxis.labelpad = ax._pending_ylabelpad
            finally:
                try:
                    delattr(ax, '_pending_ylabelpad')
                except Exception:
                    pass
            return
        pad = 8 if bool(tick_state.get('l_labels', tick_state.get('ly', False))) else 6
        # Apply manual x-offset (affects labelpad - positive = left, negative = right)
        try:
            manual_x_pts = float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0)
        except Exception:
            manual_x_pts = 0.0
        pad += manual_x_pts
        try:
            ax.yaxis.labelpad = pad
        except Exception:
            pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def update_tick_visibility(ax, tick_state: Dict[str, bool]):
    # Support new separate tick/label keys; fallback to legacy when absent
    if 'b_ticks' in tick_state or 'b_labels' in tick_state:
        ax.tick_params(axis='x',
                       bottom=bool(tick_state.get('b_ticks', True)), labelbottom=bool(tick_state.get('b_labels', True)),
                       top=bool(tick_state.get('t_ticks', False)),   labeltop=bool(tick_state.get('t_labels', False)))
        ax.tick_params(axis='y',
                       left=bool(tick_state.get('l_ticks', True)),  labelleft=bool(tick_state.get('l_labels', True)),
                       right=bool(tick_state.get('r_ticks', False)), labelright=bool(tick_state.get('r_labels', False)))
    else:
        ax.tick_params(axis='x',
                       bottom=tick_state['bx'], labelbottom=tick_state['bx'],
                       top=tick_state['tx'],    labeltop=tick_state['tx'])
        ax.tick_params(axis='y',
                       left=tick_state['ly'],  labelleft=tick_state['ly'],
                       right=tick_state['ry'], labelright=tick_state['ry'])
    if tick_state['mbx'] or tick_state['mtx']:
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis='x', which='minor',
                       bottom=tick_state['mbx'],
                       top=tick_state['mtx'],
                       labelbottom=False, labeltop=False)
    else:
        ax.tick_params(axis='x', which='minor', bottom=False, top=False,
                       labelbottom=False, labeltop=False)
    if tick_state['mly'] or tick_state['mry']:
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis='y', which='minor',
                       left=tick_state['mly'],
                       right=tick_state['mry'],
                       labelleft=False, labelright=False)
    else:
        ax.tick_params(axis='y', which='minor', left=False, right=False,
                       labelleft=False, labelright=False)
    # After visibility changes, sync tick label fonts (label1 and label2) to rcParams
    try:
        fam_chain = plt.rcParams.get('font.sans-serif')
        fam0 = fam_chain[0] if isinstance(fam_chain, list) and fam_chain else None
        size0 = plt.rcParams.get('font.size', None)
        # Standard tick labels (bottom/left)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            if size0 is not None:
                try: lbl.set_fontsize(size0)
                except Exception: pass
            if fam0:
                try: lbl.set_fontfamily(fam0)
                except Exception: pass
        # Top/right labels (label2)
        for t in ax.xaxis.get_major_ticks():
            lab2 = getattr(t, 'label2', None)
            if lab2 is not None:
                if size0 is not None:
                    try: lab2.set_fontsize(size0)
                    except Exception: pass
                if fam0:
                    try: lab2.set_fontfamily(fam0)
                    except Exception: pass
        for t in ax.yaxis.get_major_ticks():
            lab2 = getattr(t, 'label2', None)
            if lab2 is not None:
                if size0 is not None:
                    try: lab2.set_fontsize(size0)
                    except Exception: pass
                if fam0:
                    try: lab2.set_fontfamily(fam0)
                    except Exception: pass
    except Exception:
        pass


def ensure_text_visibility(fig, ax, label_text_objects: List, max_iterations=4, check_only=False):
    try:
        renderer = fig.canvas.get_renderer()
    except Exception:
        fig.canvas.draw()
        try:
            renderer = fig.canvas.get_renderer()
        except Exception:
            return
    if renderer is None:
        return

    def collect(renderer_obj):
        items = []
        # CRITICAL: Check visibility to avoid measuring hidden labels
        if ax.xaxis.label.get_text() and ax.xaxis.label.get_visible():
            try: items.append(ax.xaxis.label.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        if ax.yaxis.label.get_text() and ax.yaxis.label.get_visible():
            try: items.append(ax.yaxis.label.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        # Include duplicate top/right title artists if present
        if getattr(ax, '_top_xlabel_on', False) and hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
            try: items.append(ax._top_xlabel_artist.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        if getattr(ax, '_right_ylabel_on', False) and hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
            try: items.append(ax._right_ylabel_artist.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        for t in label_text_objects:
            try: items.append(t.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        return items

    fig_w, fig_h = fig.get_size_inches(); dpi = fig.dpi
    W, H = fig_w * dpi, fig_h * dpi
    pad = 2

    def is_out(bb):
        return (bb.x0 < -pad or bb.y0 < -pad or bb.x1 > W + pad or bb.y1 > H + pad)

    initial = collect(renderer)
    overflow = any(is_out(bb) for bb in initial)
    if check_only:
        return overflow
    if not overflow:
        return False

    for _ in range(max_iterations):
        sp = fig.subplotpars
        left, right, bottom, top = sp.left, sp.right, sp.bottom, sp.top
        changed = False
        for bb in collect(renderer):
            if not is_out(bb):
                continue
            if bb.x0 < 0 and left < 0.40:
                left = min(left + 0.01, 0.40); changed = True
            if bb.x1 > W and right > left + 0.25:
                right = max(right - 0.01, left + 0.25); changed = True
            if bb.y0 < 0 and bottom < 0.40:
                bottom = min(bottom + 0.01, 0.40); changed = True
            if bb.y1 > H and top > bottom + 0.25:
                top = max(top - 0.01, bottom + 0.25); changed = True
        if not changed:
            break
        fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
        fig.canvas.draw()
        try:
            renderer = fig.canvas.get_renderer()
        except Exception:
            break
        if not any(is_out(bb) for bb in collect(renderer)):
            break
    return True


def resize_plot_frame(fig, ax, y_data_list: List, label_text_objects: List, args, update_labels_func):
    while True:
            try:
                fig_w_in, fig_h_in = fig.get_size_inches()
                ax_bbox = ax.get_position()
                cur_ax_w_in = ax_bbox.width * fig_w_in
                cur_ax_h_in = ax_bbox.height * fig_h_in
                print(f"Current canvas: {fig_w_in:.2f} x {fig_h_in:.2f} in")
                print(f"Current plot frame:     {cur_ax_w_in:.2f} x {cur_ax_h_in:.2f} in (W x H)")
                spec = safe_input(
                    "Enter new plot frame size (e.g. '6 4', '6x4', 'w=6 h=4', 'scale=1.2', single width, q=back): ",
                    cancel_on_interrupt=True,
                ).strip().lower()
                if not spec or spec == 'q':
                    return
                new_w_in, new_h_in = cur_ax_w_in, cur_ax_h_in
                if 'scale=' in spec:
                    try:
                        factor = float(spec.split('scale=')[1].strip())
                        new_w_in = cur_ax_w_in * factor
                        new_h_in = cur_ax_h_in * factor
                    except Exception:
                        print("Invalid scale factor.")
                        continue
                else:
                    parts = spec.replace('x', ' ').split()
                    kv = {}; numbers = []
                    for p in parts:
                        if '=' in p:
                            k, v = p.split('=', 1)
                            kv[k.strip()] = v.strip()
                        else:
                            numbers.append(p)
                    if kv:
                        if 'w' in kv: new_w_in = float(kv['w'])
                        if 'h' in kv: new_h_in = float(kv['h'])
                    elif len(numbers) == 2:
                        new_w_in, new_h_in = float(numbers[0]), float(numbers[1])
                    elif len(numbers) == 1:
                        new_w_in = float(numbers[0])
                        aspect = cur_ax_h_in / cur_ax_w_in if cur_ax_w_in else 1.0
                        new_h_in = new_w_in * aspect
                    else:
                        print("Could not parse specification.")
                        continue
                req_w_in, req_h_in = new_w_in, new_h_in
                # Apply exact requested size without any clamping
                # Only enforce minimum size to prevent division by zero
                min_ax_in = 0.01
                new_w_in = max(min_ax_in, new_w_in)
                new_h_in = max(min_ax_in, new_h_in)
                tol = 1e-3
                requesting_full_canvas = (abs(req_w_in - fig_w_in) < tol and abs(req_h_in - fig_h_in) < tol)
                w_frac = new_w_in / fig_w_in
                h_frac = new_h_in / fig_h_in
                same_axes = False
                if hasattr(fig, '_last_user_axes_inches'):
                    pw, ph = fig._last_user_axes_inches
                    if abs(pw - new_w_in) < tol and abs(ph - new_h_in) < tol:
                        same_axes = True
                if same_axes and hasattr(fig, '_last_user_margins'):
                    left, bottom, w, h = fig._last_user_margins
                    ax.set_position([left, bottom, w, h])
                    update_labels_func(ax, y_data_list, label_text_objects, args.stack)
                    fig.canvas.draw_idle()
                    print(f"Plot frame unchanged ({new_w_in:.2f} x {new_h_in:.2f} in); layout preserved.")
                    continue
                left = (1 - w_frac) / 2
                bottom = (1 - h_frac) / 2
                # Use ax.set_position so it works for both standalone subplots and embedded add_axes
                ax.set_position([left, bottom, w_frac, h_frac])
                update_labels_func(ax, y_data_list, label_text_objects, args.stack)
                fig._last_user_axes_inches = (new_w_in, new_h_in)
                fig._last_user_margins = (left, bottom, w_frac, h_frac)
                # Show the requested size (which is what was applied)
                print(f"Plot frame set to {req_w_in:.2f} x {req_h_in:.2f} in inside canvas {fig_w_in:.2f} x {fig_h_in:.2f} in.")
            except KeyboardInterrupt:
                print("Canceled.")
                return
            except Exception as e:
                print(f"Error resizing plot frame: {e}")


def resize_canvas(fig, ax):
    while True:
            try:
                cur_w, cur_h = fig.get_size_inches()
                bbox_before = ax.get_position()
                frame_w_in_before = bbox_before.width * cur_w
                frame_h_in_before = bbox_before.height * cur_h
                print(f"Current canvas size: {cur_w:.2f} x {cur_h:.2f} in (frame {frame_w_in_before:.2f} x {frame_h_in_before:.2f} in)")
                spec = safe_input(
                    "Enter new canvas size (e.g. '8 6', '6x4', 'w=6 h=5', 'scale=1.2', q=back): ",
                    cancel_on_interrupt=True,
                ).strip().lower()
                if not spec or spec == 'q':
                    return
                new_w, new_h = cur_w, cur_h
                if 'scale=' in spec:
                    try:
                        fct = float(spec.split('scale=')[1])
                        new_w, new_h = cur_w * fct, cur_h * fct
                    except Exception:
                        print("Invalid scale factor.")
                        continue
                else:
                    parts = spec.replace('x',' ').split()
                    kv = {}; nums = []
                    for p in parts:
                        if '=' in p:
                            k,v = p.split('=',1); kv[k.strip()] = v.strip()
                        else:
                            nums.append(p)
                    if kv:
                        if 'w' in kv: new_w = float(kv['w'])
                        if 'h' in kv: new_h = float(kv['h'])
                    elif len(nums)==2:
                        new_w, new_h = float(nums[0]), float(nums[1])
                    elif len(nums)==1:
                        new_w = float(nums[0]); aspect = cur_h/cur_w if cur_w else 1.0; new_h = new_w * aspect
                    else:
                        print("Could not parse specification.")
                        continue
                min_size = 1.0
                new_w = max(min_size, new_w)
                new_h = max(min_size, new_h)
                tol = 1e-3
                same = hasattr(fig,'_last_canvas_size') and all(abs(a-b)<tol for a,b in zip(fig._last_canvas_size,(new_w,new_h)))
                fig.set_size_inches(new_w, new_h, forward=True)
                bbox_after = ax.get_position()
                desired_w_frac = frame_w_in_before / new_w
                desired_h_frac = frame_h_in_before / new_h
                min_margin = 0.05
                max_w_frac = 1 - 2*min_margin
                max_h_frac = 1 - 2*min_margin
                if desired_w_frac > max_w_frac:
                    desired_w_frac = max_w_frac
                if desired_h_frac > max_h_frac:
                    desired_h_frac = max_h_frac
                left = (1 - desired_w_frac) / 2
                bottom = (1 - desired_h_frac) / 2
                if desired_w_frac > 0.05 and desired_h_frac > 0.05:
                    ax.set_position([left, bottom, desired_w_frac, desired_h_frac])
                fig._last_canvas_size = (new_w, new_h)
                bbox_final = ax.get_position()
                final_frame_w_in = bbox_final.width * new_w
                final_frame_h_in = bbox_final.height * new_h
                if same:
                    print(f"Canvas unchanged ({new_w:.2f} x {new_h:.2f} in). Frame {final_frame_w_in:.2f} x {final_frame_h_in:.2f} in.")
                else:
                    note = ""
                    if abs(final_frame_w_in - frame_w_in_before) > 1e-3 or abs(final_frame_h_in - frame_h_in_before) > 1e-3:
                        note = " (clamped to fit)" if final_frame_w_in < frame_w_in_before or final_frame_h_in < frame_h_in_before else ""
                    print(f"Canvas resized to {new_w:.2f} x {new_h:.2f} in; frame preserved at {final_frame_w_in:.2f} x {final_frame_h_in:.2f} in{note} (was {frame_w_in_before:.2f} x {frame_h_in_before:.2f}).")
                fig.canvas.draw_idle()
            except KeyboardInterrupt:
                print("Canceled.")
                return
            except Exception as e:
                print(f"Error resizing canvas: {e}")


def _locator_step_value(locator) -> Optional[float]:
    try:
        if isinstance(locator, MultipleLocator):
            return float(locator._edge.step)
    except Exception:
        pass
    return None


def _locator_minor_ndivs(locator) -> Optional[int]:
    try:
        if isinstance(locator, AutoMinorLocator):
            return int(locator._ndivs)
    except Exception:
        pass
    return None


def capture_axis_tick_locators(mpl_axis, prefix: str) -> Dict[str, Any]:
    """Capture major/minor tick locators for one axis (undo snapshots).

    Keys use *prefix* (e.g. ``x``, ``y``, ``ry``): ``{prefix}_major_step``,
    ``{prefix}_minor_step``, ``{prefix}_minor_ndivs``, ``{prefix}_minor_off``.
    """
    loc_min = mpl_axis.get_minor_locator()
    return {
        f'{prefix}_major_step': _locator_step_value(mpl_axis.get_major_locator()),
        f'{prefix}_minor_step': _locator_step_value(loc_min),
        f'{prefix}_minor_ndivs': _locator_minor_ndivs(loc_min),
        f'{prefix}_minor_off': isinstance(loc_min, NullLocator),
    }


def restore_axis_tick_locators(mpl_axis, spacing: Optional[dict], prefix: str) -> None:
    """Restore tick locators saved by :func:`capture_axis_tick_locators`.

    When minors were disabled (``NullLocator``), both minor step and ndivs are
    absent in older snapshots; restore uses ``NullLocator`` instead of turning
    minors back on with ``AutoMinorLocator()``.
    """
    if not spacing:
        return
    p = prefix
    maj_step = spacing.get(f'{p}_major_step')
    min_step = spacing.get(f'{p}_minor_step')
    ndivs = spacing.get(f'{p}_minor_ndivs')
    minor_off = spacing.get(f'{p}_minor_off')
    if minor_off is None and min_step is None and ndivs is None:
        minor_off = True
    try:
        if maj_step is not None:
            mpl_axis.set_major_locator(MultipleLocator(float(maj_step)))
        else:
            mpl_axis.set_major_locator(AutoLocator())
    except Exception:
        pass
    try:
        if minor_off:
            mpl_axis.set_minor_locator(NullLocator())
            mpl_axis.set_minor_formatter(NullFormatter())
        elif min_step is not None:
            mpl_axis.set_minor_locator(MultipleLocator(float(min_step)))
            mpl_axis.set_minor_formatter(NullFormatter())
        elif ndivs is not None:
            mpl_axis.set_minor_locator(AutoMinorLocator(int(ndivs)))
            mpl_axis.set_minor_formatter(NullFormatter())
        else:
            mpl_axis.set_minor_locator(NullLocator())
            mpl_axis.set_minor_formatter(NullFormatter())
    except Exception:
        pass


def capture_axes_tick_locators(ax, prefixes: tuple = ('x', 'y')) -> Dict[str, Any]:
    """Merge :func:`capture_axis_tick_locators` for each prefix on one Axes."""
    out: Dict[str, Any] = {}
    axis_map = {'x': ax.xaxis, 'y': ax.yaxis}
    for prefix in prefixes:
        mpl_axis = axis_map.get(prefix)
        if mpl_axis is not None:
            out.update(capture_axis_tick_locators(mpl_axis, prefix))
    return out


def restore_axes_tick_locators(ax, spacing: Optional[dict], prefixes: tuple = ('x', 'y')) -> None:
    """Restore locators for each prefix on one Axes."""
    if not spacing:
        return
    axis_map = {'x': ax.xaxis, 'y': ax.yaxis}
    for prefix in prefixes:
        mpl_axis = axis_map.get(prefix)
        if mpl_axis is not None:
            restore_axis_tick_locators(mpl_axis, spacing, prefix)


def apply_wasd_minor_ticks(ax, wasd: Optional[dict], *, y_minor_mode: str = 'both') -> None:
    """Apply WASD minor tick locators and visibility from a wasd_state dict.

    *y_minor_mode* controls which y sides receive minor tick_params:
    ``both`` (default), ``left`` (operando heatmap in dual-pane), or ``right`` (EC panel).
    """
    if not wasd or not isinstance(wasd, dict):
        return
    top_m = bool(wasd.get('top', {}).get('minor', False))
    bot_m = bool(wasd.get('bottom', {}).get('minor', False))
    if top_m or bot_m:
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
    else:
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
    ax.tick_params(
        axis='x', which='minor',
        top=top_m, bottom=bot_m,
        labeltop=False, labelbottom=False,
    )

    left_m = bool(wasd.get('left', {}).get('minor', False))
    right_m = bool(wasd.get('right', {}).get('minor', False))
    if left_m or right_m:
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())
    else:
        ax.yaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())

    if y_minor_mode == 'right':
        ax.tick_params(axis='y', which='minor', left=False, right=right_m, labelleft=False, labelright=False)
    elif y_minor_mode == 'left':
        ax.tick_params(axis='y', which='minor', left=left_m, right=False, labelleft=False, labelright=False)
    else:
        ax.tick_params(
            axis='y', which='minor',
            left=left_m, right=right_m,
            labelleft=False, labelright=False,
        )


__all__ = [
    'apply_font_changes',
    'sync_fonts',
    'position_top_xlabel',
    'position_right_ylabel',
    'position_bottom_xlabel',
    'position_left_ylabel',
    'update_tick_visibility',
    'ensure_text_visibility',
    'resize_plot_frame',
    'resize_canvas',
    'capture_axis_tick_locators',
    'capture_axes_tick_locators',
    'restore_axis_tick_locators',
    'restore_axes_tick_locators',
    'apply_wasd_minor_ticks',
    'format_spine_side_tick_report',
    'format_spine_draw_stability_report',
    'ensure_spine_color_draw_hook',
    'finalize_spine_colors',
    'finalize_spine_colors_cpc',
    'finalize_spine_colors_for_axes',
    'get_fig_spine_colors',
    'set_spine_side_color',
]
