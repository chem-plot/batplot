"""CPC interactive undo and geometry snapshot helpers."""

from __future__ import annotations

from typing import Dict


def _get_geometry_snapshot(ax, ax2) -> Dict:
    """Collect a CPC geometry snapshot."""
    geom = {
        "xlim": list(ax.get_xlim()),
        "ylim_left": list(ax.get_ylim()),
        "xlabel": ax.get_xlabel() or "",
        "ylabel_left": ax.get_ylabel() or "",
    }
    if ax2 is not None:
        geom["ylim_right"] = list(ax2.get_ylim())
        geom["ylabel_right"] = ax2.get_ylabel() or ""
    return geom


def _apply_cpc_geometry_snapshot(ax, ax2, geom) -> None:
    """Restore CPC axis labels and limits from a geometry snapshot."""
    if not isinstance(geom, dict) or not geom:
        return
    try:
        if "xlabel" in geom:
            ax.set_xlabel(geom.get("xlabel") or "")
        if "ylabel_left" in geom:
            ax.set_ylabel(geom.get("ylabel_left") or "")
        if ax2 is not None and "ylabel_right" in geom:
            ax2.set_ylabel(geom.get("ylabel_right") or "")
    except Exception:
        pass
    try:
        if geom.get("xlim") and len(geom["xlim"]) == 2:
            ax.set_xlim(*geom["xlim"])
        if geom.get("ylim_left") and len(geom["ylim_left"]) == 2:
            ax.set_ylim(*geom["ylim_left"])
        if ax2 is not None and geom.get("ylim_right") and len(geom["ylim_right"]) == 2:
            ax2.set_ylim(*geom["ylim_right"])
    except Exception:
        pass


def push_cpc_state(
    state_history,
    *,
    fig,
    ax,
    ax2,
    sc_charge,
    sc_discharge,
    sc_eff,
    file_data,
    tick_state,
    note: str = "",
) -> None:
    """Capture CPC undo state (style + geometry, same schema as batch undo)."""
    try:
        from . import interactive as _interactive
        from ..common.state_capture import as_style_geom_export

        snap = as_style_geom_export(
            _interactive._style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data),
            kind="cpc_style_geom",
            geometry=_get_geometry_snapshot(ax, ax2),
        )
        snap["__note__"] = note
        snap.setdefault("ticks", {}).setdefault("visibility", dict(tick_state))
        state_history.append(snap)
        if len(state_history) > 40:
            state_history.pop(0)
    except Exception:
        pass


def restore_cpc_state(
    state_history,
    *,
    fig,
    ax,
    ax2,
    sc_charge,
    sc_discharge,
    sc_eff,
    file_data,
    tick_state,
    update_ticks_func,
) -> bool:
    """Restore CPC undo state."""
    if not state_history:
        print("No undo history.")
        return False
    cfg = state_history.pop()
    try:
        from . import interactive as _interactive

        _interactive._apply_style(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cfg, file_data)
        _apply_cpc_geometry_snapshot(ax, ax2, cfg.get("geometry"))
        vis = (cfg.get("ticks") or {}).get("visibility") or {}
        for key, value in vis.items():
            if key in tick_state:
                tick_state[key] = bool(value)
        update_ticks_func()
        _interactive._reapply_cpc_legend_text_colors(ax)
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
        print("Undo: restored previous state.")
        return True
    except Exception as exc:
        print(f"Undo failed: {exc}")
        return False


__all__ = [
    "_apply_cpc_geometry_snapshot",
    "_get_geometry_snapshot",
    "push_cpc_state",
    "restore_cpc_state",
]
