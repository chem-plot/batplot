"""Histogram figure construction."""

from __future__ import annotations

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
    show_grid: bool = True
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


def _axis_label_for_column(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "Value"
    low = text.lower()
    if "length" in low and "µm" not in low and "um" not in low:
        return f"{text} (µm)" if text else "Length (µm)"
    return text


def _apply_histo_text_fonts(ax: Axes, state: HistoState) -> None:
    tick_sz = max(8.0, state.style.label_fontsize * 12.0 / 14.0)
    ax.tick_params(axis="both", labelsize=tick_sz)
    fam = state.style.font_family
    if not fam:
        return
    for label in (ax.xaxis.label, ax.yaxis.label, ax.title):
        try:
            label.set_fontfamily(fam)
        except Exception:
            pass
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        try:
            tick.set_fontfamily(fam)
        except Exception:
            pass


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
    return HistoState(setup=setup, style=st, source_path=source_path)


def draw_histogram(fig: Figure, ax: Axes, state: HistoState) -> Dict[str, Any]:
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
    if state.style.top_xlabel:
        ax._top_xlabel_text_override = state.style.top_xlabel  # type: ignore[attr-defined]
    _apply_histo_text_fonts(ax, state)
    ax.grid(state.style.show_grid, axis="y", alpha=0.35, linestyle="--", linewidth=0.6)
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
        leg = ax.legend(loc="best", fontsize=legend_sz)
        if leg and state.style.font_family:
            for text in leg.get_texts():
                try:
                    text.set_fontfamily(state.style.font_family)
                except Exception:
                    pass
    if state.style.axes_fraction is not None:
        _disable_histo_auto_layout(fig)
        ax.set_position(state.style.axes_fraction)
    else:
        fig.tight_layout()
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
    fig._bp_histo_state = state  # type: ignore[attr-defined]
    return meta
