"""Shared font application helpers for interactive plot modes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import matplotlib as mpl


def set_font_family_defaults(
    family: str,
    *,
    sans_serif_stack: bool = False,
    update_mathtext: bool = False,
) -> None:
    """Update matplotlib defaults for new text created after a font change."""
    if sans_serif_stack:
        mpl.rcParams["font.family"] = "sans-serif"
        mpl.rcParams["font.sans-serif"] = [family, "DejaVu Sans", "Arial", "Helvetica"]
    else:
        mpl.rcParams["font.family"] = family

    if update_mathtext:
        lower_family = family.lower()
        mpl.rcParams["mathtext.fontset"] = "stix" if any(k in lower_family for k in ("stix", "times", "roman")) else "dejavusans"
        mpl.rcParams["mathtext.default"] = "regular"


def set_font_size_default(size: float) -> None:
    """Update matplotlib default font size for new text."""
    mpl.rcParams["font.size"] = size


def apply_font_family_to_artists(artists: Iterable[Any], family: str) -> None:
    for artist in artists:
        if artist is None:
            continue
        try:
            if hasattr(artist, "set_fontfamily"):
                artist.set_fontfamily(family)
            else:
                artist.set_family(family)
        except Exception:
            pass


def apply_font_size_to_artists(artists: Iterable[Any], size: float) -> None:
    for artist in artists:
        if artist is None:
            continue
        try:
            if hasattr(artist, "set_fontsize"):
                artist.set_fontsize(size)
            else:
                artist.set_size(size)
        except Exception:
            pass


def axis_text_artists(ax: Any, *, include_title: bool = False, include_axes_texts: bool = False) -> list[Any]:
    """Collect common axis labels, tick labels, and optional title/text artists."""
    artists: list[Any] = []
    try:
        artists.extend([ax.xaxis.label, ax.yaxis.label])
    except Exception:
        pass
    if include_title:
        try:
            artists.append(ax.title)
        except Exception:
            pass
    try:
        artists.extend(list(ax.get_xticklabels()) + list(ax.get_yticklabels()))
    except Exception:
        pass
    try:
        for tick in ax.xaxis.get_major_ticks():
            if hasattr(tick, "label2"):
                artists.append(tick.label2)
        for tick in ax.yaxis.get_major_ticks():
            if hasattr(tick, "label2"):
                artists.append(tick.label2)
    except Exception:
        pass
    if include_axes_texts:
        try:
            artists.extend(list(getattr(ax, "texts", [])))
        except Exception:
            pass
    return artists


def legend_text_artists(legend: Any) -> list[Any]:
    if legend is None:
        return []
    try:
        return list(legend.get_texts())
    except Exception:
        return []


def secondary_xaxis_text_artists(secax: Any) -> list[Any]:
    if secax is None:
        return []
    artists: list[Any] = []
    try:
        artists.append(secax.xaxis.label)
    except Exception:
        pass
    try:
        artists.extend(list(secax.get_xticklabels()))
    except Exception:
        pass
    try:
        for tick in secax.xaxis.get_major_ticks():
            if hasattr(tick, "label1"):
                artists.append(tick.label1)
    except Exception:
        pass
    return artists


__all__ = [
    "apply_font_family_to_artists",
    "apply_font_size_to_artists",
    "axis_text_artists",
    "legend_text_artists",
    "secondary_xaxis_text_artists",
    "set_font_family_defaults",
    "set_font_size_default",
]
