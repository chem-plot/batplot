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
    """Legend entry labels plus the legend title (e.g. EC ``Cycle`` header)."""
    if legend is None:
        return []
    artists: list[Any] = []
    try:
        artists.extend(list(legend.get_texts()))
    except Exception:
        pass
    try:
        title = legend.get_title()
        if title is not None:
            artists.append(title)
    except Exception:
        pass
    return artists


def sync_legend_title_fontsize(legend: Any, size: float | None = None) -> None:
    """Match legend title size to rcParams or legend entry labels (after rebuild)."""
    if legend is None:
        return
    try:
        title = legend.get_title()
        if title is None:
            return
        if size is None:
            size = mpl.rcParams.get("font.size")
            if size is None:
                texts = [t.get_fontsize() for t in legend.get_texts() if t.get_text().strip()]
                if texts:
                    size = sum(texts) / len(texts)
        if size is not None:
            title.set_fontsize(float(size))
    except Exception:
        pass


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


def collect_fig_font_artists(
    ax: Any,
    fig: Any | None = None,
    *,
    include_title: bool = True,
    include_axes_texts: bool = False,
    include_legend: bool = True,
    legend: Any | None = None,
    extra_axes: list[Any] | None = None,
    extra_artists: list[Any] | None = None,
) -> list[Any]:
    """Collect axis labels, ticks, duplicate titles, legend, and optional extra text."""
    artists = axis_text_artists(ax, include_title=include_title, include_axes_texts=include_axes_texts)
    if fig is not None:
        artists.extend([
            getattr(ax, "_top_xlabel_artist", None),
            getattr(ax, "_right_ylabel_artist", None),
            getattr(ax, "_top_xlabel_text", None),
        ])
        try:
            if getattr(fig, "_xaxis_mode", "capacity") == "dual":
                artists.extend(secondary_xaxis_text_artists(getattr(fig, "_xaxis_secondary", None)))
        except Exception:
            pass
    if include_legend:
        try:
            leg = legend if legend is not None else ax.get_legend()
            artists.extend(legend_text_artists(leg))
        except Exception:
            pass
    for extra_ax in extra_axes or []:
        if extra_ax is None:
            continue
        artists.extend(axis_text_artists(extra_ax, include_title=include_title))
        artists.extend([
            getattr(extra_ax, "_top_xlabel_artist", None),
            getattr(extra_ax, "_right_ylabel_artist", None),
        ])
    if extra_artists:
        artists.extend(extra_artists)
    return [a for a in artists if a is not None]


def collect_operando_font_artists(
    fig: Any,
    ax: Any,
    ec_ax: Any | None = None,
    cbar: Any | None = None,
) -> list[Any]:
    """Axis + EC + colorbar text for operando / dQ/dV 2D contour font weight/highlight."""
    artists: list[Any] = []
    for a in (ax, ec_ax):
        if a is None:
            continue
        artists.extend(collect_fig_font_artists(a, fig, include_title=True, include_axes_texts=True))
    cbar_ax = getattr(cbar, "ax", None) if cbar is not None else None
    if cbar_ax is not None:
        try:
            artists.extend(collect_fig_font_artists(cbar_ax, fig, include_axes_texts=True))
        except Exception:
            pass
    for attr in ("_cbar_high_text", "_cbar_low_text"):
        art = getattr(fig, attr, None)
        if art is not None:
            artists.append(art)
    return [a for a in artists if a is not None]


__all__ = [
    "apply_font_family_to_artists",
    "apply_font_size_to_artists",
    "axis_text_artists",
    "collect_fig_font_artists",
    "collect_operando_font_artists",
    "legend_text_artists",
    "secondary_xaxis_text_artists",
    "sync_legend_title_fontsize",
    "set_font_family_defaults",
    "set_font_size_default",
]
