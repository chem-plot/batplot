"""Colors submenu (``c``) for the histogram interactive menu."""

from __future__ import annotations

from typing import Callable

import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib import colors as mcolors  # type: ignore[import]

from ...color_utils import (
    ensure_colormap,
    format_color_listing,
    get_colormap,
    get_user_color_list,
    manage_user_colors,
    prompt_screen_color,
    blank_means_back,
    palette_preview,
    resolve_color_token,
)
from ..common.palettes import (
    PALETTE_DESCRIPTIONS,
    build_palette_options,
    resolve_palette_token,
    sample_palette_colors,
)
from ...ui import format_spine_side_tick_report
from .spines import (
    set_histo_spine_color,
    get_histo_spine_colors,
    capture_histo_spine_colors_from_ax,
    format_histo_spine_extra_report,
)

_SPINE_KEYS = {"w": "top", "a": "left", "s": "bottom", "d": "right"}


def histo_palette_options() -> list[str]:
    return build_palette_options(ensure_colormap)


def resolve_histo_color(
    spec: str,
    fig,
    palette_index: dict[str, str],
) -> str | None:
    """Resolve a palette name/number, saved color ref, or matplotlib color token."""
    spec = (spec or "").strip()
    if not spec:
        return None
    pal = resolve_palette_token(spec, palette_index)
    if pal in plt.colormaps() or ensure_colormap(pal):
        colors = sample_palette_colors(
            pal,
            1,
            ensure_colormap=ensure_colormap,
            get_cmap=get_colormap,
        )
        if colors:
            return colors[0]
    try:
        resolved = resolve_color_token(spec, fig)
        mcolors.to_rgb(resolved)
        return resolved
    except (ValueError, TypeError):
        return None


def run_histo_color_menu(
    *,
    fig,
    ax,
    get_bar_color: Callable[[], str],
    set_bar_color: Callable[[str], None],
    get_edge_color: Callable[[], str],
    set_edge_color: Callable[[str], None],
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
    apply_spine_color: Callable[[str, str], None] | None = None,
    finish_spine_change: Callable[[list[tuple[str, str]]], None] | None = None,
    get_bar_alpha: Callable[[], float] | None = None,
    set_bar_alpha: Callable[[float], None] | None = None,
) -> None:
    """Run the histogram colors submenu (bar, edge, spines, palettes, saved colors)."""
    palette_opts = histo_palette_options()
    palette_index = {str(i): name for i, name in enumerate(palette_opts, 1)}

    def _apply_spine(spine_name: str, resolved: str) -> None:
        if apply_spine_color is not None:
            apply_spine_color(spine_name, resolved)
        else:
            set_histo_spine_color(fig, ax, spine_name, resolved)

    def _finish_spine_change(changed: list[tuple[str, str]]) -> None:
        if finish_spine_change is not None:
            finish_spine_change(changed)
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
        wasd = getattr(fig, "_histo_wasd_state", None)
        if not isinstance(wasd, dict):
            wasd = None
        for side, resolved in changed:
            print(
                format_spine_side_tick_report(
                    ax,
                    side,
                    expected_color=resolved,
                    wasd_state=wasd,
                )
            )
            print(
                format_histo_spine_extra_report(
                    ax,
                    side,
                    expected_color=resolved,
                )
            )

    from ..common.menu_rendering import menu_block_begin

    while True:
        menu_block_begin(force_new=True)
        print("\033[1mColors>\033[0m")
        user_colors = get_user_color_list(fig)
        if user_colors:
            print("Saved colors (refer as number or u#):")
            for idx, col in enumerate(user_colors, 1):
                print(f"  {idx}: {format_color_listing(col)}")

        print("Palettes:")
        for idx, name in enumerate(palette_opts, 1):
            preview = palette_preview(name)
            desc = PALETTE_DESCRIPTIONS.get(name, "")
            print(f"  {idx}. {name}" + (f" - {desc}" if desc else ""))
            if preview:
                print(f"      {preview}")

        c, r = "\033[96m", "\033[0m"
        print()
        print("How to set color:")
        print(f"  bar/edge:  {c}bar:red{r}  {c}edge:#333{r}  {c}bar:2 edge:u3{r}")
        if get_bar_alpha is not None and set_bar_alpha is not None:
            print(f"  alpha:     {c}alpha:0.5{r}")
        print(f"  palette:   {c}viridis{r}  or  {c}3{r}  (palette number/name)")
        print(f"  spine:     {c}w:red{r}  {c}a:#4561F7{r}  ({c}w{r}=top {c}a{r}=left {c}s{r}=bottom {c}d{r}=right)")
        print(
            f"Other           : {c}v{r}: show current colors   "
            f"{c}u{r}: edit saved colors   {c}e{r}: pick color from screen   {c}q{r}: back"
        )

        try:
            line = safe_input(colorize_prompt("Colors> "), cancel_on_interrupt=True).strip()
        except (KeyboardInterrupt, EOFError):
            break
        if line.lower() == "q" or blank_means_back(line):
            break

        low = line.lower()
        if low == "v":
            bar_cur = get_bar_color()
            edge_cur = get_edge_color()
            print("Current:")
            print(f"  bar:  {format_color_listing(bar_cur)}")
            print(f"  edge: {format_color_listing(edge_cur)}")
            if get_bar_alpha is not None:
                print(f"  alpha: {float(get_bar_alpha()):g}")
            spine_cols = get_histo_spine_colors(fig) or capture_histo_spine_colors_from_ax(ax)
            if spine_cols:
                key_map = {"top": "w", "left": "a", "bottom": "s", "right": "d"}
                parts = [
                    f"{key_map[side]}:{spine_cols[side]}"
                    for side in ("top", "left", "bottom", "right")
                    if side in spine_cols
                ]
                if parts:
                    print(f"  spines: {' '.join(parts)}")
            continue
        if low == "u":
            manage_user_colors(fig)
            continue
        if low == "e":
            prompt_screen_color(fig)
            continue

        tokens = line.split()
        is_spine = all(":" in t and t.split(":", 1)[0].lower() in _SPINE_KEYS for t in tokens if t)
        if is_spine and tokens:
            planned: list[tuple[str, str]] = []
            for tok in tokens:
                key_part, color_spec = tok.split(":", 1)
                spine_name = _SPINE_KEYS[key_part.lower()]
                resolved = resolve_histo_color(color_spec, fig, palette_index)
                if resolved is None:
                    print(f"Invalid color for {spine_name}: {color_spec}")
                    continue
                planned.append((spine_name, resolved))
            if not planned:
                continue
            push_state()
            changed: list[tuple[str, str]] = []
            for spine_name, resolved in planned:
                try:
                    _apply_spine(spine_name, resolved)
                    changed.append((spine_name, resolved))
                    print(f"Set {spine_name} spine to {format_color_listing(resolved)}")
                except Exception as exc:
                    print(f"Error setting {spine_name} color: {exc}")
            if changed:
                _finish_spine_change(changed)
            continue

        has_colon = any(":" in t for t in tokens)
        if not has_colon and tokens:
            resolved = resolve_histo_color(tokens[0], fig, palette_index)
            if not resolved:
                print(f"Unknown palette or color '{tokens[0]}'. Use bar:color or edge:color.")
                continue
            push_state()
            set_bar_color(resolved)
            refresh()
            pal = resolve_palette_token(tokens[0], palette_index)
            if pal in plt.colormaps() or ensure_colormap(pal):
                preview = palette_preview(pal)
                print(f"Bar color from palette '{pal}': {format_color_listing(resolved)}")
                if preview:
                    print(f"  {preview}")
            else:
                print(f"Bar color: {format_color_listing(resolved)}")
            fig.canvas.draw_idle()
            continue

        if has_colon:
            bar_val: str | None = None
            edge_val: str | None = None
            alpha_val: float | None = None
            spines: list[tuple[str, str]] = []
            for tok in tokens:
                if ":" not in tok:
                    print(f"Skip: {tok}")
                    continue
                key, color_spec = tok.split(":", 1)
                key = key.lower()
                if key == "alpha":
                    if set_bar_alpha is None:
                        print("Bar alpha is not available here.")
                        continue
                    try:
                        alpha_val = float(color_spec)
                    except ValueError:
                        print(f"Invalid alpha: {color_spec}")
                        continue
                    if alpha_val < 0.0 or alpha_val > 1.0:
                        print("Alpha must be between 0 and 1.")
                        alpha_val = None
                        continue
                    continue
                resolved = resolve_histo_color(color_spec, fig, palette_index)
                if resolved is None:
                    print(f"Invalid color for {key}: {color_spec}")
                    continue
                if key == "bar":
                    bar_val = resolved
                elif key == "edge":
                    edge_val = resolved
                elif key in _SPINE_KEYS:
                    spines.append((_SPINE_KEYS[key], resolved))
                else:
                    print(f"Unknown key '{key}'. Use bar, edge, alpha, or w/a/s/d.")
            if bar_val is None and edge_val is None and alpha_val is None and not spines:
                continue
            push_state()
            if bar_val is not None:
                set_bar_color(bar_val)
                print(f"Bar: {format_color_listing(bar_val)}")
            if edge_val is not None:
                set_edge_color(edge_val)
                print(f"Edge: {format_color_listing(edge_val)}")
            if alpha_val is not None and set_bar_alpha is not None:
                set_bar_alpha(alpha_val)
                print(f"Bar alpha: {alpha_val:g}")
            changed_spines: list[tuple[str, str]] = []
            for spine_name, resolved in spines:
                try:
                    _apply_spine(spine_name, resolved)
                    changed_spines.append((spine_name, resolved))
                    print(f"{spine_name} spine: {format_color_listing(resolved)}")
                except Exception as exc:
                    print(f"Error setting {spine_name} color: {exc}")
            # Bar/edge/alpha live in style and need a redraw — do not skip when
            # the same line also sets spine colors (old elif left patches stale).
            if bar_val is not None or edge_val is not None or alpha_val is not None:
                refresh()
            if changed_spines:
                _finish_spine_change(changed_spines)
            elif bar_val is not None or edge_val is not None or alpha_val is not None:
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
            continue

        print("Unknown input. Use bar:color, edge:color, alpha:0.5, palette name, or spine keys.")


__all__ = ["histo_palette_options", "resolve_histo_color", "run_histo_color_menu"]
