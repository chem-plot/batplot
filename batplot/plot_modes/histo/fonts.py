"""Font submenu (``f``) for the histogram interactive menu."""

from __future__ import annotations

from typing import Callable

import matplotlib.pyplot as plt  # type: ignore[import]

from ..common.font_extras import (
    apply_fig_font_weight,
    apply_fig_text_highlight,
    histo_style_to_highlight_style,
    normalize_font_weight,
)
from ..common.menus import run_font_menu
from .plot import HistoState, title_fontsize_from_label


def apply_histo_font_family(state: HistoState, family: str) -> None:
    state.style.font_family = family
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [family, "DejaVu Sans", "Arial", "Helvetica"]
    low = family.lower()
    if any(token in low for token in ("stix", "times", "roman")):
        plt.rcParams["mathtext.fontset"] = "stix"
    else:
        plt.rcParams["mathtext.fontset"] = "dejavusans"


def apply_histo_font_size(state: HistoState, size: float) -> None:
    state.style.label_fontsize = float(size)
    state.style.title_fontsize = title_fontsize_from_label(size)
    plt.rcParams["font.size"] = size


def apply_histo_font_weight(state: HistoState, weight: str) -> None:
    state.style.font_weight = normalize_font_weight(weight)
    plt.rcParams["font.weight"] = state.style.font_weight


def apply_histo_text_highlight(
    state: HistoState,
    enabled: bool,
    *,
    fc: str | None = None,
    alpha: float | None = None,
    pad: float | None = None,
) -> None:
    state.style.text_highlight = bool(enabled)
    if fc is not None:
        state.style.text_highlight_fc = str(fc)
    if alpha is not None:
        state.style.text_highlight_alpha = float(alpha)
    if pad is not None:
        state.style.text_highlight_pad = float(pad)


def sync_histo_font_rcparams(state: HistoState) -> None:
    """Reapply stored font settings to matplotlib rcParams (import/undo/load)."""
    if state.style.font_family:
        apply_histo_font_family(state, state.style.font_family)
    if state.style.label_fontsize > 0:
        plt.rcParams["font.size"] = state.style.label_fontsize
    plt.rcParams["font.weight"] = normalize_font_weight(state.style.font_weight)


def run_histo_font_menu(
    *,
    state: HistoState,
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Run the shared ``f`` font submenu for histogram mode."""

    def _apply_family(family: str) -> None:
        push_state()
        apply_histo_font_family(state, family)
        refresh()

    def _apply_size(size: float) -> None:
        push_state()
        apply_histo_font_size(state, size)
        refresh()

    def _apply_weight(weight: str) -> None:
        push_state()
        apply_histo_font_weight(state, weight)
        refresh()

    def _toggle_highlight() -> None:
        push_state()
        apply_histo_text_highlight(state, not state.style.text_highlight)
        refresh()

    def _set_hl_fc(fc: str) -> None:
        push_state()
        apply_histo_text_highlight(state, state.style.text_highlight, fc=fc)
        refresh()

    def _set_hl_alpha(alpha: float) -> None:
        push_state()
        apply_histo_text_highlight(state, state.style.text_highlight, alpha=alpha)
        refresh()

    def _set_hl_pad(pad: float) -> None:
        push_state()
        apply_histo_text_highlight(state, state.style.text_highlight, pad=pad)
        refresh()

    run_font_menu(
        safe_input=safe_input,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        get_current_family=lambda: state.style.font_family or plt.rcParams.get("font.sans-serif", [""])[0],
        get_current_size=lambda: state.style.label_fontsize,
        apply_family=_apply_family,
        apply_size=_apply_size,
        get_current_weight=lambda: state.style.font_weight,
        apply_weight=_apply_weight,
        get_current_highlight=lambda: bool(state.style.text_highlight),
        get_highlight_style=lambda: histo_style_to_highlight_style(state.style),
        apply_highlight_toggle=_toggle_highlight,
        apply_highlight_facecolor=_set_hl_fc,
        apply_highlight_alpha=_set_hl_alpha,
        apply_highlight_pad=_set_hl_pad,
        fonts=["Arial", "Helvetica", "Times New Roman", "STIXGeneral", "DejaVu Sans"],
        blank_exits=True,
    )


__all__ = [
    "apply_histo_font_family",
    "apply_histo_font_size",
    "apply_histo_font_weight",
    "apply_histo_text_highlight",
    "run_histo_font_menu",
    "sync_histo_font_rcparams",
]
