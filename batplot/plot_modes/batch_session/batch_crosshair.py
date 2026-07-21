"""Batch-session crosshair: toggle on all panels; export hides overlays via register_crosshair."""

from __future__ import annotations

from typing import Any, Callable, Sequence

import matplotlib.pyplot as plt  # type: ignore[import]

from ..common.crosshair_export import register_crosshair


def _state(fig) -> dict[str, Any] | None:
    st = getattr(fig, "_bp_crosshair", None)
    return st if isinstance(st, dict) else None


def panel_crosshair_active(fig) -> bool:
    st = _state(fig)
    return bool(st and st.get("active"))


def clear_panel_crosshair(fig) -> None:
    """Disconnect listeners and drop artist refs (safe if axes were cleared)."""
    st = _state(fig)
    if not st:
        register_crosshair(fig, None)
        return
    cid = st.get("cid_motion")
    if cid is not None:
        try:
            fig.canvas.mpl_disconnect(cid)
        except Exception:
            pass
    for key in ("hline", "vline", "text"):
        art = st.get(key)
        if art is None:
            continue
        try:
            art.remove()
        except Exception:
            pass
    st.update({"active": False, "hline": None, "vline": None, "text": None, "cid_motion": None})
    register_crosshair(fig, st)
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def enable_panel_crosshair(fig, ax) -> None:
    """Turn on a simple x/y readout crosshair on *ax* (batch-wide: no wavelength prompt)."""
    clear_panel_crosshair(fig)
    if ax is None:
        return
    try:
        x0 = float(ax.get_xlim()[0])
        y0 = float(ax.get_ylim()[0])
    except Exception:
        x0, y0 = 0.0, 0.0
    vline = ax.axvline(x=x0, color="0.35", ls="--", lw=0.8, alpha=0.85, zorder=9999)
    hline = ax.axhline(y=y0, color="0.35", ls="--", lw=0.8, alpha=0.85, zorder=9999)
    txt = ax.text(
        1.0,
        1.0,
        "",
        ha="right",
        va="bottom",
        transform=ax.transAxes,
        fontsize=max(9, int(0.6 * plt.rcParams.get("font.size", 16))),
        color="0.15",
        bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="0.7", alpha=0.8),
        zorder=10000,
    )
    state: dict[str, Any] = {
        "active": True,
        "hline": hline,
        "vline": vline,
        "text": txt,
        "cid_motion": None,
    }

    def on_move(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        x = float(event.xdata)
        y = float(event.ydata)
        vline.set_xdata([x, x])
        hline.set_ydata([y, y])
        txt.set_text(f"x={x:.6g}\ny={y:.6g}")
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass

    try:
        cid = fig.canvas.mpl_connect("motion_notify_event", on_move)
        state["cid_motion"] = cid
    except Exception:
        state["cid_motion"] = None
    register_crosshair(fig, state)
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def default_panel_ax(panel: Any):
    return getattr(panel, "ax", None)


def toggle_batch_crosshair(
    panels: Sequence[Any],
    *,
    get_ax: Callable[[Any], Any] | None = None,
) -> bool:
    """Toggle crosshair on every panel. Returns True if now ON."""
    if not panels:
        return False
    ax_fn = get_ax or default_panel_ax
    any_on = any(panel_crosshair_active(getattr(p, "fig", None)) for p in panels)
    if any_on:
        for panel in panels:
            fig = getattr(panel, "fig", None)
            if fig is not None:
                clear_panel_crosshair(fig)
        print("Crosshair OFF on all plots.")
        return False
    for panel in panels:
        fig = getattr(panel, "fig", None)
        ax = ax_fn(panel)
        if fig is not None and ax is not None:
            enable_panel_crosshair(fig, ax)
    print("Crosshair ON on all plots. Move mouse over each figure. Press 'n' again to turn off.")
    return True


def restore_batch_crosshair_if_was_on(
    panels: Sequence[Any],
    was_on: bool,
    *,
    get_ax: Callable[[Any], Any] | None = None,
) -> None:
    """After a full redraw (e.g. histo refresh), recreate crosshairs if they were on."""
    if not was_on:
        return
    ax_fn = get_ax or default_panel_ax
    for panel in panels:
        fig = getattr(panel, "fig", None)
        ax = ax_fn(panel)
        if fig is not None and ax is not None:
            enable_panel_crosshair(fig, ax)


def snapshot_batch_crosshair_on(panels: Sequence[Any]) -> bool:
    return any(panel_crosshair_active(getattr(p, "fig", None)) for p in panels)


__all__ = [
    "clear_panel_crosshair",
    "enable_panel_crosshair",
    "panel_crosshair_active",
    "restore_batch_crosshair_if_was_on",
    "snapshot_batch_crosshair_on",
    "toggle_batch_crosshair",
]
