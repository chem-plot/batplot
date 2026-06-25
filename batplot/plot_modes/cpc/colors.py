"""CPC color and palette menu helpers."""

from __future__ import annotations

from matplotlib.colors import hsv_to_rgb, rgb_to_hsv, to_rgb  # type: ignore[import]

from ...color_utils import (
    color_block,
    ensure_colormap,
    get_colormap,
    get_user_color_list,
    manage_user_colors,
    palette_preview,
    resolve_color_token,
)
from ..common.palettes import build_palette_options, sample_palette_colors
from .legend import _color_of


def _generate_similar_color(base_color):
    """Generate a similar but distinguishable discharge color."""
    try:
        rgb = to_rgb(base_color)
        h, s, v = rgb_to_hsv(rgb)
        rgb_new = hsv_to_rgb([(h + 0.04) % 1.0, max(0.3, s * 0.85), max(0.4, v * 0.9)])
        return rgb_new
    except Exception:
        try:
            rgb = to_rgb(base_color)
            return tuple(max(0, c * 0.7) for c in rgb)
        except Exception:
            return base_color


def cpc_palette_options() -> list[str]:
    return build_palette_options(ensure_colormap)


def cpc_palette_color(name: str, idx: int = 0, total: int = 1):
    colors = sample_palette_colors(
        name,
        max(total, 1),
        ensure_colormap=ensure_colormap,
        get_cmap=get_colormap,
        prefer_listed_colors=True,
        pair=(0.15, 0.85),
        span=(0.08, 0.88),
    )
    return colors[idx % len(colors)]


def parse_file_range_palette(tokens: list[str], n_files: int, palette_opts: list[str]):
    """Parse `1-5 viridis` or `1 3 5 viridis` into 0-based indices and palette."""
    if not tokens or len(tokens) < 2 or n_files < 1:
        return None
    last = tokens[-1]
    if ":" in last:
        return None
    try:
        if not ensure_colormap(last):
            raise ValueError(last)
        if get_colormap(last) is None:
            raise ValueError(last)
        palette = last
    except Exception:
        if last.isdigit() and 1 <= int(last) <= len(palette_opts):
            palette = palette_opts[int(last) - 1]
        else:
            return None
    indices = []
    for token in tokens[:-1]:
        if ":" in token:
            return None
        if "-" in token and token.count("-") == 1:
            lo, hi = token.split("-", 1)
            try:
                start, stop = int(lo.strip()), int(hi.strip())
                for idx in range(start, stop + 1):
                    if 1 <= idx <= n_files:
                        indices.append(idx - 1)
            except ValueError:
                return None
        else:
            try:
                idx = int(token)
                if 1 <= idx <= n_files:
                    indices.append(idx - 1)
            except ValueError:
                return None
    indices = sorted(set(indices))
    return (indices, palette) if indices else None


def resolve_cpc_color(spec: str, fig, palette_opts: list[str], idx: int = 0, total: int = 1, default_cmap: str = "tab10"):
    spec = spec.strip()
    if not spec:
        return None
    if spec.lower() == "r":
        return cpc_palette_color(default_cmap, idx, total)
    user_color = None
    if spec.lower().startswith("u") and len(spec) > 1 and spec[1:].isdigit():
        user_color = resolve_color_token(spec, fig)
    elif spec.isdigit():
        number = int(spec)
        if 1 <= number <= len(palette_opts):
            return cpc_palette_color(palette_opts[number - 1], idx, total)
    if user_color:
        return user_color
    spec_lower = spec.lower()
    base_lower = spec.rstrip("_r").rstrip("_R").lower()
    for palette in palette_opts:
        if spec_lower == palette.lower() or base_lower == palette.lower() or spec_lower == (palette + "_r").lower():
            return cpc_palette_color(palette if not spec.endswith("_r") and not spec.endswith("_R") else spec, idx, total)
    return resolve_color_token(spec, fig)


def _print_color_targets(*, fig, file_data, series_key: str, colorize_menu) -> None:
    title = "capacity curves" if series_key == "capacity" else "efficiency curves"
    artist_key = "sc_charge" if series_key == "capacity" else "sc_eff"
    print(f"\nCurrent {title}:")
    for idx, file_info in enumerate(file_data, 1):
        current = _color_of(file_info[artist_key])
        preview_color = current if isinstance(current, str) else None
        visible_mark = "●" if file_info.get("visible", True) else "○"
        print("  " + colorize_menu(f"{idx}: {visible_mark} {file_info['filename']}  {color_block(preview_color)} {current}"))
    saved_colors = get_user_color_list(fig)
    if saved_colors:
        print("\nSaved colors (refer as number or u#):")
        for idx, color in enumerate(saved_colors, 1):
            print("  " + colorize_menu(f"{idx}: {color_block(color)} {color}"))


def _print_palette_help(palette_opts: list[str], colorize_menu) -> None:
    print("\nPalettes:")
    for idx, name in enumerate(palette_opts, 1):
        preview = palette_preview(name)
        print("  " + colorize_menu(f"{idx}: {name}"))
        if preview:
            print(f"      {preview}")
    c, r = "\033[96m", "\033[0m"
    print()
    print(f"Apply palette to ALL files:  {c}all 1{r}  or  {c}all viridis{r}  (or just  {c}1{r}  or  {c}viridis{r})")
    print(f"Apply palette to file range:  {c}1-5 viridis{r}  or  {c}1 3 5 4{r}")
    print(f"Apply per file (file:color):  {c}1:2{r}  {c}2:red{r}  {c}3:#455353{r}")
    print(f"  {c}q{r}: cancel")


def apply_capacity_color_tokens(tokens: list[str], *, fig, file_data, palette_opts: list[str]) -> None:
    spec = None
    file_range_result = parse_file_range_palette(tokens, len(file_data), palette_opts)
    if len(tokens) == 1 and ":" not in tokens[0]:
        spec = tokens[0]
    elif len(tokens) >= 2 and tokens[0].lower() in ("all", "a"):
        spec = tokens[1]

    if spec is not None and file_range_result is None:
        for idx, file_info in enumerate(file_data):
            charge_col = resolve_cpc_color(spec, fig, palette_opts, idx, len(file_data), default_cmap="tab10")
            if not charge_col:
                continue
            _apply_capacity_color_to_file(file_info, charge_col)
        try:
            palette_name = palette_opts[int(spec) - 1] if spec.isdigit() and 1 <= int(spec) <= len(palette_opts) else spec
        except (ValueError, IndexError):
            palette_name = spec
        print(f"Palette applied to all capacity curves ({palette_name}).")
        return

    if file_range_result is not None:
        indices, palette_spec = file_range_result
        for idx, file_idx in enumerate(indices):
            charge_col = resolve_cpc_color(palette_spec, fig, palette_opts, idx, len(indices), default_cmap="tab10")
            if charge_col:
                _apply_capacity_color_to_file(file_data[file_idx], charge_col)
        print(f"Palette '{palette_spec}' applied to files {[idx + 1 for idx in indices]}.")
        return

    if any(token and ":" not in token for token in tokens):
        print("Use file:color pairs (e.g. 1:2 2:red 3:#455353) or all 1 / all viridis for palette.")
        return

    for token in tokens:
        if ":" not in token:
            continue
        idx_str, color_spec = token.split(":", 1)
        try:
            file_idx = int(idx_str) - 1
        except ValueError:
            print(f"Bad index: {idx_str}")
            continue
        if not (0 <= file_idx < len(file_data)):
            print(f"Index out of range: {idx_str}")
            continue
        resolved = resolve_color_token(color_spec, fig)
        charge_col = resolved if resolved else color_spec
        if charge_col:
            _apply_capacity_color_to_file(file_data[file_idx], charge_col)
    print("Colors applied to selected files.")


def apply_efficiency_color_tokens(tokens: list[str], *, fig, file_data, palette_opts: list[str]) -> None:
    spec = None
    file_range_result = parse_file_range_palette(tokens, len(file_data), palette_opts)
    if len(tokens) == 1 and ":" not in tokens[0]:
        spec = tokens[0]
    elif len(tokens) >= 2 and tokens[0].lower() in ("all", "a"):
        spec = tokens[1]

    if spec is not None and file_range_result is None:
        for idx, file_info in enumerate(file_data):
            color = resolve_cpc_color(spec, fig, palette_opts, idx, len(file_data), default_cmap="viridis")
            if color:
                _apply_efficiency_color_to_file(file_info, color)
        try:
            palette_name = palette_opts[int(spec) - 1] if spec.isdigit() and 1 <= int(spec) <= len(palette_opts) else spec
        except (ValueError, IndexError):
            palette_name = spec
        print(f"Palette applied to all efficiency curves ({palette_name}).")
        return

    if file_range_result is not None:
        indices, palette_spec = file_range_result
        for idx, file_idx in enumerate(indices):
            color = resolve_cpc_color(palette_spec, fig, palette_opts, idx, len(indices), default_cmap="viridis")
            if color:
                _apply_efficiency_color_to_file(file_data[file_idx], color)
        print(f"Palette '{palette_spec}' applied to files {[idx + 1 for idx in indices]}.")
        return

    if any(token and ":" not in token for token in tokens):
        print("Use file:color pairs (e.g. 1:2 2:red 3:#455353) or all 1 / all viridis for palette.")
        return

    for token in tokens:
        if ":" not in token:
            continue
        idx_str, color_spec = token.split(":", 1)
        try:
            file_idx = int(idx_str) - 1
        except ValueError:
            print(f"Bad index: {idx_str}")
            continue
        if not (0 <= file_idx < len(file_data)):
            print(f"Index out of range: {idx_str}")
            continue
        resolved = resolve_color_token(color_spec, fig)
        color = resolved if resolved else color_spec
        if color:
            _apply_efficiency_color_to_file(file_data[file_idx], color)
    print("Colors applied to selected files.")


def run_cpc_color_menu(
    *,
    fig,
    ax,
    ax2,
    file_data,
    is_multi_file: bool,
    sc_charge,
    sc_eff,
    push_state,
    set_spine_color,
    rebuild_legend,
    safe_input,
    colorize_menu,
    colorize_prompt,
) -> None:
    palette_opts = cpc_palette_options()
    while True:
        print()
        print("Colors (CPC):")
        print("  " + colorize_menu("ly: capacity curve colors (left Y-axis)"))
        print("  " + colorize_menu("ry: efficiency marker colors (right Y-axis)"))
        print("  " + colorize_menu("u: manage user colors (save/reuse palettes)"))
        print("  " + colorize_menu("s: spine colors (top/bottom/left/right, with optional auto mode)"))
        print("  " + colorize_menu("q: back to main menu"))
        sub = safe_input(colorize_prompt("Colors (ly/ry/u/s/q): ")).strip().lower()
        if not sub:
            continue
        if sub == "q":
            break
        if sub == "u":
            manage_user_colors(fig)
            continue
        if sub == "ly":
            push_state("colors-ly")
            _print_color_targets(fig=fig, file_data=file_data, series_key="capacity", colorize_menu=colorize_menu)
            _print_palette_help(palette_opts, colorize_menu)
            color_input = safe_input(colorize_prompt("Colors (ly) (file:color or palette, q=back): ")).strip()
            if not color_input or color_input.lower() == "q":
                continue
            apply_capacity_color_tokens(color_input.split(), fig=fig, file_data=file_data, palette_opts=palette_opts)
            if not is_multi_file and getattr(fig, "_cpc_spine_auto", False):
                try:
                    current = _color_of(sc_charge)
                    if current:
                        set_spine_color("left", current)
                except Exception:
                    pass
            try:
                rebuild_legend(ax, ax2, file_data)
                fig.canvas.draw()
            except Exception:
                pass
            continue
        if sub == "ry":
            push_state("colors-ry")
            _print_color_targets(fig=fig, file_data=file_data, series_key="efficiency", colorize_menu=colorize_menu)
            _print_palette_help(palette_opts, colorize_menu)
            color_input = safe_input(colorize_prompt("Colors (ry) (file:color or palette, q=back): ")).strip()
            if not color_input or color_input.lower() == "q":
                continue
            apply_efficiency_color_tokens(color_input.split(), fig=fig, file_data=file_data, palette_opts=palette_opts)
            if not is_multi_file and getattr(fig, "_cpc_spine_auto", False):
                try:
                    current = _color_of(sc_eff)
                    if current:
                        set_spine_color("right", current)
                except Exception:
                    pass
            try:
                rebuild_legend(ax, ax2, file_data)
                fig.canvas.draw()
            except Exception:
                pass
            continue
        print("Unknown option.")


def _apply_capacity_color_to_file(file_info, charge_col) -> None:
    discharge_col = _generate_similar_color(charge_col)
    try:
        file_info["color"] = charge_col
        file_info["sc_charge"].set_facecolor(charge_col)
        file_info["sc_charge"].set_edgecolor(charge_col)
        if hasattr(file_info["sc_discharge"], "set_facecolors"):
            file_info["sc_discharge"].set_facecolors("none")
            file_info["sc_discharge"].set_edgecolors(discharge_col)
        else:
            file_info["sc_discharge"].set_color(discharge_col)
    except Exception as exc:
        print(f"Error setting color: {exc}")


def _apply_efficiency_color_to_file(file_info, color) -> None:
    try:
        file_info["sc_eff"].set_facecolor(color)
        file_info["sc_eff"].set_edgecolor(color)
        file_info["eff_color"] = color
    except Exception:
        pass


__all__ = [
    "_generate_similar_color",
    "apply_capacity_color_tokens",
    "apply_efficiency_color_tokens",
    "cpc_palette_color",
    "cpc_palette_options",
    "parse_file_range_palette",
    "resolve_cpc_color",
    "run_cpc_color_menu",
]
