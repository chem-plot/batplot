"""CPC interactive undo and geometry snapshot helpers."""

from __future__ import annotations

from typing import Dict


def _geom_label_text(obj, stored_attr: str, live_getter) -> str:
    """Prefer ``_stored_*`` (including empty) so cleared/hidden titles round-trip."""
    if obj is not None and hasattr(obj, stored_attr):
        val = getattr(obj, stored_attr)
        return "" if val is None else str(val)
    try:
        return live_getter() or ""
    except Exception:
        return ""


def _get_geometry_snapshot(ax, ax2) -> Dict:
    """Collect a CPC geometry snapshot."""
    geom = {
        "xlim": list(ax.get_xlim()),
        "ylim_left": list(ax.get_ylim()),
        "xlabel": _geom_label_text(ax, "_stored_xlabel", ax.get_xlabel),
        "ylabel_left": _geom_label_text(ax, "_stored_ylabel", ax.get_ylabel),
    }
    if ax2 is not None:
        geom["ylim_right"] = list(ax2.get_ylim())
        geom["ylabel_right"] = _geom_label_text(ax2, "_stored_ylabel", ax2.get_ylabel)
    return geom


def _apply_cpc_geometry_snapshot(ax, ax2, geom) -> None:
    """Restore CPC axis labels and limits from a geometry snapshot."""
    if not isinstance(geom, dict) or not geom:
        return
    try:
        if "xlabel" in geom:
            text = geom.get("xlabel") or ""
            ax.set_xlabel(text)
            ax._stored_xlabel = str(text)
        if "ylabel_left" in geom:
            text = geom.get("ylabel_left") or ""
            ax.set_ylabel(text)
            ax._stored_ylabel = str(text)
        if ax2 is not None and "ylabel_right" in geom:
            text = geom.get("ylabel_right") or ""
            ax2.set_ylabel(text)
            ax2._stored_ylabel = str(text)
    except Exception:
        pass
    try:
        xlim = geom.get("xlim")
        if isinstance(xlim, (list, tuple)) and len(xlim) == 2:
            ax.set_xlim(xlim[0], xlim[1])
        ylim_left = geom.get("ylim_left")
        if isinstance(ylim_left, (list, tuple)) and len(ylim_left) == 2:
            ax.set_ylim(ylim_left[0], ylim_left[1])
        ylim_right = geom.get("ylim_right")
        if ax2 is not None and isinstance(ylim_right, (list, tuple)) and len(ylim_right) == 2:
            ax2.set_ylim(ylim_right[0], ylim_right[1])
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
) -> bool:
    """Capture CPC undo state (style + geometry, same schema as batch undo)."""
    try:
        from .style import _apply_style, _style_snapshot
        from .legend import _reapply_cpc_legend_text_colors
        from ..common.state_capture import as_style_geom_export

        snap = as_style_geom_export(
            _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data),
            kind="cpc_style_geom",
            geometry=_get_geometry_snapshot(ax, ax2),
        )
        snap["__note__"] = note
        # File-count checkpoint so undo can drop series added after this snap.
        try:
            snap["__cpc_n_files__"] = int(len(file_data) if file_data else 0)
        except Exception:
            snap["__cpc_n_files__"] = 0
        snap.setdefault("ticks", {}).setdefault("visibility", dict(tick_state))
        state_history.append(snap)
        if len(state_history) > 40:
            state_history.pop(0)
        return True
    except Exception as e:
        print(f"Warning: could not snapshot state for undo: {e}")
        return False


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
        from .style import _apply_style
        from .legend import _reapply_cpc_legend_text_colors
        from .add_file import trim_cpc_files_to_count

        # Drop files added after this checkpoint (style snaps have no xy arrays).
        n_keep = cfg.get("__cpc_n_files__")
        if isinstance(n_keep, int) and file_data is not None and len(file_data) > n_keep:
            trim_cpc_files_to_count(fig, ax, ax2, file_data, n_keep)

        # Primary artists may have shifted after a trim — refresh from file_data[0].
        sc_c, sc_d, sc_e = sc_charge, sc_discharge, sc_eff
        if file_data:
            sc_c = file_data[0].get("sc_charge", sc_c)
            sc_d = file_data[0].get("sc_discharge", sc_d)
            sc_e = file_data[0].get("sc_eff", sc_e)

        _apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, file_data)
        _apply_cpc_geometry_snapshot(ax, ax2, cfg.get("geometry"))
        vis = (cfg.get("ticks") or {}).get("visibility") or {}
        for key, value in vis.items():
            if key in tick_state:
                tick_state[key] = bool(value)
        update_ticks_func()
        _reapply_cpc_legend_text_colors(ax)
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
        print("Undo: restored previous state.")
        return True
    except Exception as exc:
        # Put the snap back so a failed ``b`` does not burn an undo level.
        state_history.append(cfg)
        print(f"Undo failed: {exc}")
        return False


__all__ = [
    "_apply_cpc_geometry_snapshot",
    "_get_geometry_snapshot",
    "push_cpc_state",
    "restore_cpc_state",
]
