"""Histogram figure construction."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.figure import Figure  # type: ignore[import-untyped]
from matplotlib.axes import Axes  # type: ignore[import-untyped]

from .wizard import HistoSetup


def title_fontsize_from_label(label_size: float) -> float:
    return round(float(label_size) * 15.0 / 14.0, 2)


@dataclass
class HistoStyle:
    bar_color: str = "#4C72B0"
    edge_color: str = "#1f1f1f"
    alpha: float = 0.85
    bar_width_frac: float = 0.95
    show_grid: bool = False
    grid_linewidth: float = 0.6
    density: bool = False
    show_bar_labels: bool = False
    show_mean_line: bool = False
    show_median_line: bool = False
    show_density_curve: bool = False
    density_curve_color: str = "#c0392b"
    density_curve_lw: float = 1.8
    density_curve_ls: str = "-"
    density_curve_alpha: float = 1.0
    xlabel: str = ""
    ylabel: str = ""
    title: str = ""
    top_xlabel: str = ""
    figsize: Tuple[float, float] = (8.0, 5.5)
    axes_fraction: Tuple[float, float, float, float] | None = None
    font_family: str = ""
    label_fontsize: float = 14.0
    title_fontsize: float = 15.0
    font_weight: str = "normal"
    text_highlight: bool = False
    text_highlight_fc: str = "white"
    text_highlight_alpha: float = 0.85
    text_highlight_pad: float = 0.2
    ylim: Tuple[float, float] | None = None


@dataclass
class HistoState:
    setup: HistoSetup
    style: HistoStyle = field(default_factory=HistoStyle)
    source_path: str = ""

    def counts_and_edges(self) -> Tuple[np.ndarray, np.ndarray]:
        vals = self.setup.values
        mask = np.isfinite(vals)
        vals = vals[mask]
        if self.setup.xmin is not None:
            vals = vals[(vals >= self.setup.xmin) & (vals <= self.setup.xmax)]
        counts, edges = np.histogram(vals, bins=self.setup.bin_edges)
        return counts.astype(float), edges

    def y_label_default(self) -> str:
        return "Density" if self.style.density else "Count"


def legacy_auto_histo_titles(state: HistoState) -> set[str]:
    """Plot titles that older histo builds auto-generated from column/file names."""
    out: set[str] = set()
    col = (state.setup.column_name or "").strip()
    if col:
        col_title = col.title()
        for name in (col, col_title):
            out.update(
                {
                    name,
                    f"Histogram {name}",
                    f"histogram {name}",
                    f"{name} histogram",
                    f"{name} Histogram",
                }
            )
    src = (state.source_path or "").strip()
    if src:
        fname = os.path.basename(src)
        base = os.path.splitext(fname)[0]
        if fname:
            out.add(fname)
        if base:
            out.add(base)
            if base.lower().endswith("_histo"):
                out.add(base[: -len("_histo")])
    return {item.strip() for item in out if item and item.strip()}


def normalize_histo_title(state: HistoState) -> None:
    """Drop legacy auto titles; keep explicit user-set titles."""
    title = (state.style.title or "").strip()
    if not title:
        state.style.title = ""
        return
    legacy = {item.lower() for item in legacy_auto_histo_titles(state)}
    low = title.lower()
    col = (state.setup.column_name or "").strip().lower()
    if low in legacy:
        state.style.title = ""
        return
    # Older sessions stored "Histogram Length" even when column_name was missing/wrong.
    if low.startswith("histogram "):
        suffix = low[len("histogram ") :].strip()
        if suffix in (col, "length", "size", "sizes", "width", "diameter", "area"):
            state.style.title = ""
            return
        if col and suffix.replace("_", " ") == col.replace("_", " "):
            state.style.title = ""
            return
    if low in ("length", "size", "sizes") and col == low:
        state.style.title = ""


def histo_bar_heights(state: HistoState) -> Tuple[np.ndarray, np.ndarray]:
    """Return bar heights and bin edges for the current histogram setup."""
    counts, edges = state.counts_and_edges()
    heights = counts.astype(float)
    if state.style.density and counts.sum() > 0:
        widths = np.diff(edges)
        if np.sum(widths) > 0:
            heights = counts / (counts.sum() * widths)
    return heights, edges


def histo_auto_ylim(state: HistoState) -> Tuple[float, float]:
    """Default y-axis limits from bar heights (and KDE overlay when shown)."""
    heights, edges = histo_bar_heights(state)
    ymax = 1.0
    if heights.size and np.any(np.isfinite(heights)):
        ymax = max(ymax, float(np.nanmax(heights)))
    if state.style.show_density_curve:
        from .density_curve import density_curve_xy

        curve = density_curve_xy(state, edges)
        if curve is not None:
            _, y_curve = curve
            if y_curve.size:
                ymax = max(ymax, float(np.nanmax(y_curve)))
    if ymax <= 0:
        ymax = 1.0
    pad = ymax * 0.05
    return (0.0, ymax + pad)


def histo_current_ylim(state: HistoState) -> Tuple[float, float]:
    if state.style.ylim is not None:
        return state.style.ylim
    return histo_auto_ylim(state)


def _apply_histo_ylim(ax: Axes, state: HistoState) -> None:
    ymin, ymax = histo_current_ylim(state)
    if ymin == ymax:
        eps = abs(ymin) * 1e-6 if ymin != 0 else 1e-6
        ymin -= eps
        ymax += eps
    ax.set_ylim(ymin, ymax)


def _axis_label_for_column(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "Value"
    low = text.lower()
    if "length" in low and "µm" not in low and "um" not in low:
        return f"{text} (µm)" if text else "Length (µm)"
    return text


def _apply_histo_text_fonts(ax: Axes, state: HistoState) -> None:
    """Apply family/weight/highlight to all histo text (call AFTER bar labels/legend/spines)."""
    from ..common.font_extras import (
        apply_font_weight_to_artists,
        apply_text_highlight_to_artists,
        histo_style_to_highlight_style,
        normalize_font_weight,
    )
    from ..common.fonts import legend_text_artists

    tick_sz = max(8.0, state.style.label_fontsize * 12.0 / 14.0)
    ax.tick_params(axis="both", labelsize=tick_sz)
    fam = state.style.font_family
    weight = normalize_font_weight(state.style.font_weight)
    labels = list(ax.get_xticklabels()) + list(ax.get_yticklabels())
    for label in (ax.xaxis.label, ax.yaxis.label, ax.title):
        labels.append(label)
    for attr in ("_top_xlabel_artist", "_right_ylabel_artist"):
        art = getattr(ax, attr, None)
        if art is not None:
            labels.append(art)
    try:
        labels.extend(list(getattr(ax, "texts", []) or []))
    except Exception:
        pass
    try:
        labels.extend(legend_text_artists(ax.get_legend()))
    except Exception:
        pass
    if fam:
        for label in labels:
            try:
                if hasattr(label, "set_fontfamily"):
                    label.set_fontfamily(fam)
                else:
                    label.set_family(fam)
            except Exception:
                pass
    apply_font_weight_to_artists(labels, weight)
    apply_text_highlight_to_artists(
        labels,
        bool(state.style.text_highlight),
        histo_style_to_highlight_style(state.style),
    )


def _disable_histo_auto_layout(fig: Figure) -> None:
    """Prevent matplotlib from moving axes after manual geometry is set."""
    try:
        fig.set_layout_engine("none")
    except AttributeError:
        try:
            fig.set_tight_layout(False)
        except Exception:
            pass
    try:
        fig.set_constrained_layout(False)
    except Exception:
        pass


def histo_y_grid_visible(ax) -> bool:
    """Return True if any y-axis major gridline is visible."""
    try:
        return any(gl.get_visible() for gl in ax.get_ygridlines())
    except Exception:
        return False


def apply_histo_grid(ax, state: HistoState) -> None:
    """Apply y-grid visibility from ``state.style.show_grid`` (call after spine/tick ops)."""
    try:
        lw = float(getattr(state.style, "grid_linewidth", 0.6) or 0.6)
        if state.style.show_grid:
            ax.grid(True, axis="y", alpha=0.35, linestyle="--", linewidth=lw)
        else:
            ax.grid(False, axis="y")
    except Exception:
        pass


def build_histo_state(
    setup: HistoSetup,
    *,
    source_path: str = "",
    style: HistoStyle | None = None,
) -> HistoState:
    st = HistoStyle() if style is None else style
    if not st.xlabel:
        st.xlabel = _axis_label_for_column(setup.column_name)
    if not st.ylabel:
        st.ylabel = st.ylabel or "Count"
    state = HistoState(setup=setup, style=st, source_path=source_path)
    normalize_histo_title(state)
    return state


def draw_histogram(fig: Figure, ax: Axes, state: HistoState) -> Dict[str, Any]:
    normalize_histo_title(state)
    ax.cla()
    counts, edges = state.counts_and_edges()
    widths = np.diff(edges)
    centers = edges[:-1] + widths / 2.0
    weights = None
    heights = counts
    if state.style.density and counts.sum() > 0:
        total_width = np.sum(widths)
        if total_width > 0:
            heights = counts / (counts.sum() * widths)
    bars = ax.bar(
        centers,
        heights,
        width=widths * max(0.01, min(float(state.style.bar_width_frac), 1.0)),
        align="center",
        color=state.style.bar_color,
        edgecolor=state.style.edge_color,
        linewidth=0.6,
        alpha=state.style.alpha,
    )
    ax.set_xlim(edges[0], edges[-1])
    ax.set_xlabel(state.style.xlabel, fontsize=state.style.label_fontsize)
    ax.set_ylabel(state.style.ylabel or state.y_label_default(), fontsize=state.style.label_fontsize)
    if state.style.title:
        ax.set_title(state.style.title, fontsize=state.style.title_fontsize)
    else:
        ax.set_title("")
    if state.style.top_xlabel:
        ax._top_xlabel_text_override = state.style.top_xlabel  # type: ignore[attr-defined]
    lw = float(getattr(state.style, "grid_linewidth", 0.6) or 0.6)
    if state.style.show_grid:
        ax.grid(True, axis="y", alpha=0.35, linestyle="--", linewidth=lw)
    else:
        ax.grid(False, axis="y")
    extras: Dict[str, Any] = {"bars": bars, "counts": counts, "edges": edges}
    finite = state.setup.values[np.isfinite(state.setup.values)]
    if state.style.show_mean_line and finite.size:
        mean = float(np.mean(finite))
        extras["mean_line"] = ax.axvline(mean, color="crimson", ls="--", lw=1.2, label=f"mean={mean:.3g}")
    if state.style.show_median_line and finite.size:
        med = float(np.median(finite))
        extras["median_line"] = ax.axvline(med, color="darkorange", ls=":", lw=1.2, label=f"median={med:.3g}")
    if state.style.show_density_curve and finite.size >= 2:
        from .density_curve import density_curve_xy

        curve = density_curve_xy(state, edges)
        if curve is not None:
            x_curve, y_curve = curve
            extras["density_curve"] = ax.plot(
                x_curve,
                y_curve,
                color=state.style.density_curve_color,
                linewidth=state.style.density_curve_lw,
                linestyle=state.style.density_curve_ls,
                alpha=state.style.density_curve_alpha,
                label="density",
            )[0]
    if state.style.show_bar_labels:
        bar_label_sz = max(8.0, state.style.label_fontsize * 9.0 / 14.0)
        for rect, h in zip(bars, heights):
            if h <= 0:
                continue
            ax.text(
                rect.get_x() + rect.get_width() / 2.0,
                rect.get_height(),
                f"{h:.0g}" if h >= 1 else f"{h:.2f}",
                ha="center",
                va="bottom",
                fontsize=bar_label_sz,
            )
    if extras.get("mean_line") or extras.get("median_line") or extras.get("density_curve"):
        legend_sz = max(8.0, state.style.label_fontsize * 10.0 / 14.0)
        ax.legend(loc="best", fontsize=legend_sz)
    _apply_histo_ylim(ax, state)
    if state.style.axes_fraction is not None:
        _disable_histo_auto_layout(fig)
        ax.set_position(state.style.axes_fraction)
    else:
        fig.tight_layout()
    from .spines import apply_histo_spine_colors, get_histo_spine_colors

    apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig))
    # Weight/highlight after bar labels, legend, and spine duplicate titles exist.
    _apply_histo_text_fonts(ax, state)
    return extras


def sync_histo_geometry(fig: Figure, ax: Axes, state: HistoState) -> None:
    """Copy current canvas and axes layout into ``state.style``."""
    fw, fh = fig.get_size_inches()
    state.style.figsize = (float(fw), float(fh))
    bbox = ax.get_position()
    state.style.axes_fraction = (float(bbox.x0), float(bbox.y0), float(bbox.width), float(bbox.height))
    _disable_histo_auto_layout(fig)


def apply_histo_geometry(fig: Figure, ax: Axes, state: HistoState) -> None:
    """Apply stored canvas and axes layout from ``state.style``."""
    fig.set_size_inches(*state.style.figsize, forward=True)
    if state.style.axes_fraction is not None:
        _disable_histo_auto_layout(fig)
        ax.set_position(state.style.axes_fraction)


def create_histo_figure(state: HistoState) -> Tuple[Figure, Axes, Dict[str, Any]]:
    fig, ax = plt.subplots(figsize=state.style.figsize)
    if state.style.axes_fraction is not None:
        _disable_histo_auto_layout(fig)
    meta = draw_histogram(fig, ax, state)
    fig._bp_histo_state = state  # type: ignore[attr-defined]
    return fig, ax, meta


def refresh_histo_figure(fig: Figure, ax: Axes, state: HistoState) -> Dict[str, Any]:
    state.style.ylabel = state.style.ylabel or state.y_label_default()
    meta = draw_histogram(fig, ax, state)
    from .spines import reapply_histo_spine_layout

    reapply_histo_spine_layout(fig, ax, state)
    apply_histo_grid(ax, state)
    fig._bp_histo_state = state  # type: ignore[attr-defined]
    return meta
