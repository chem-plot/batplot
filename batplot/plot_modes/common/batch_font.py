"""Shared batch-session font menu (family/size/weight/highlight for all panels)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import matplotlib.pyplot as plt  # type: ignore[import]

from .font_extras import (
    apply_fig_font_weight,
    apply_fig_text_highlight,
    get_fig_font_weight,
    get_fig_text_highlight,
    get_fig_text_highlight_style,
    set_fig_font_weight,
)
from .fonts import apply_font_family_to_artists, apply_font_size_to_artists, set_font_family_defaults, set_font_size_default
from .menus import run_font_menu


def run_batch_font_menu(
    *,
    panels: list[Any],
    undo: Any,
    capture_panel: Callable[[Any], dict],
    draw_panels: Callable[[], None],
    collect_artists: Callable[[Any], list],
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Run full font submenu and apply changes to every panel in a batch session."""
    if not panels:
        return
    ref = panels[0]
    ref_fig = ref.fig

    def _push_all() -> None:
        undo.push_all([capture_panel(p) for p in panels])

    def _all_artists() -> list:
        artists: list = []
        for panel in panels:
            artists.extend(collect_artists(panel))
        return artists

    def _apply_family(family: str) -> None:
        _push_all()
        set_font_family_defaults(family, sans_serif_stack=True, update_mathtext=True)
        apply_font_family_to_artists(_all_artists(), family)
        draw_panels()

    def _apply_size(size: float) -> None:
        _push_all()
        set_font_size_default(size)
        apply_font_size_to_artists(_all_artists(), size)
        draw_panels()

    def _apply_weight(weight: str) -> None:
        _push_all()
        for panel in panels:
            apply_fig_font_weight(panel.fig, collect_artists(panel), weight)
        draw_panels()

    def _toggle_highlight() -> None:
        _push_all()
        new_val = not get_fig_text_highlight(ref_fig)
        for panel in panels:
            apply_fig_text_highlight(panel.fig, collect_artists(panel), new_val)
        draw_panels()

    def _set_hl_fc(fc: str) -> None:
        _push_all()
        for panel in panels:
            apply_fig_text_highlight(
                panel.fig,
                collect_artists(panel),
                get_fig_text_highlight(panel.fig),
                fc=fc,
            )
        draw_panels()

    def _set_hl_alpha(alpha: float) -> None:
        _push_all()
        for panel in panels:
            apply_fig_text_highlight(
                panel.fig,
                collect_artists(panel),
                get_fig_text_highlight(panel.fig),
                alpha=alpha,
            )
        draw_panels()

    def _set_hl_pad(pad: float) -> None:
        _push_all()
        for panel in panels:
            apply_fig_text_highlight(
                panel.fig,
                collect_artists(panel),
                get_fig_text_highlight(panel.fig),
                pad=pad,
            )
        draw_panels()

    if not hasattr(ref_fig, "_bp_font_weight"):
        set_fig_font_weight(ref_fig, plt.rcParams.get("font.weight", "normal"))

    run_font_menu(
        safe_input=safe_input,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        get_current_family=lambda: plt.rcParams.get("font.sans-serif", [""])[0],
        get_current_size=lambda: plt.rcParams.get("font.size"),
        apply_family=_apply_family,
        apply_size=_apply_size,
        get_current_weight=lambda: get_fig_font_weight(ref_fig),
        apply_weight=_apply_weight,
        get_current_highlight=lambda: get_fig_text_highlight(ref_fig),
        get_highlight_style=lambda: get_fig_text_highlight_style(ref_fig),
        apply_highlight_toggle=_toggle_highlight,
        apply_highlight_facecolor=_set_hl_fc,
        apply_highlight_alpha=_set_hl_alpha,
        apply_highlight_pad=_set_hl_pad,
    )


def batch_panel_label_artists(panel: Any) -> list:
    """Default text artists for batch font apply (axis labels, title, ticks)."""
    ax = panel.ax
    artists = [ax.xaxis.label, ax.yaxis.label, ax.title]
    artists.extend(ax.get_xticklabels())
    artists.extend(ax.get_yticklabels())
    return artists


__all__ = ["batch_panel_label_artists", "run_batch_font_menu"]
