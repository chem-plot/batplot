"""Font submenu (``f``) for the histogram interactive menu."""

from __future__ import annotations

from typing import Callable

import matplotlib.pyplot as plt  # type: ignore[import]

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


def sync_histo_font_rcparams(state: HistoState) -> None:
    """Reapply stored font settings to matplotlib rcParams (import/undo/load)."""
    if state.style.font_family:
        apply_histo_font_family(state, state.style.font_family)
    if state.style.label_fontsize > 0:
        plt.rcParams["font.size"] = state.style.label_fontsize


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

    run_font_menu(
        safe_input=safe_input,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        get_current_family=lambda: state.style.font_family or plt.rcParams.get("font.sans-serif", [""])[0],
        get_current_size=lambda: state.style.label_fontsize,
        apply_family=_apply_family,
        apply_size=_apply_size,
        fonts=["Arial", "Helvetica", "Times New Roman", "STIXGeneral", "DejaVu Sans"],
        blank_exits=True,
    )


__all__ = [
    "apply_histo_font_family",
    "apply_histo_font_size",
    "run_histo_font_menu",
    "sync_histo_font_rcparams",
]
