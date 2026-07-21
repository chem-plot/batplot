"""Figure export helpers for EC interactive mode."""

from __future__ import annotations

from typing import Any, Dict, List

from ..common.crosshair_export import savefig_without_crosshair


def _ec_savefig_plot_window(fig, ax, target: str, *, transparent: bool = False) -> None:
    """Export EC/dQ/dV figure without clipping labels, legends, or duplicate labels."""
    try:
        fig.canvas.draw()
    except Exception:
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass
    extras: List[Any] = []
    try:
        for label in (ax.xaxis.label, ax.yaxis.label):
            if label is not None:
                extras.append(label)
    except Exception:
        pass
    for attr in ("_top_xlabel_artist", "_right_ylabel_artist"):
        try:
            artist = getattr(ax, attr, None)
            if artist is not None and bool(getattr(artist, "get_visible", lambda: True)()):
                extras.append(artist)
        except Exception:
            pass
    try:
        secondary = getattr(fig, "_xaxis_secondary", None)
        if secondary is not None:
            for label in (secondary.xaxis.label, secondary.yaxis.label):
                if label is not None:
                    extras.append(label)
    except Exception:
        pass
    try:
        legend = ax.get_legend()
        if legend is not None and legend.get_visible():
            extras.append(legend)
    except Exception:
        pass
    try:
        suptitle = getattr(fig, "_suptitle", None)
        if suptitle is not None and bool(getattr(suptitle, "get_visible", lambda: True)()):
            extras.append(suptitle)
    except Exception:
        pass
    kwargs: Dict[str, Any] = {
        "dpi": 300,
        "bbox_inches": "tight",
        "pad_inches": 0.28,
    }
    if extras:
        kwargs["bbox_extra_artists"] = extras
    if transparent:
        kwargs["transparent"] = True
        kwargs["facecolor"] = "none"
        kwargs["edgecolor"] = "none"
    savefig_without_crosshair(fig, target, **kwargs)


__all__ = ["_ec_savefig_plot_window"]
