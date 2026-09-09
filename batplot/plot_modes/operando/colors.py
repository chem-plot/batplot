"""Operando colormap helpers and menu runner."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib import colors as mcolors  # type: ignore[import-untyped]
from matplotlib.colors import LinearSegmentedColormap  # type: ignore[import-untyped]

from ...color_utils import (
    ensure_colormap,
    format_color_listing,
    get_colormap,
    get_user_color_list,
    manage_user_colors,
    palette_preview,
    prompt_screen_color,
    blank_means_back,
    resolve_color_token,
    _CUSTOM_CMAPS as _UTILS_CUSTOM_CMAPS,
)
from ..common.palettes import (
    build_xy_palette_options,
    palette_items,
    parse_index_ranges,
    resolve_palette_token,
    sample_colormap,
)

try:
    import cmcrameri.cm as cmc
except ImportError:  # pragma: no cover - optional dependency
    cmc = None


_CUSTOM_CMAPS = {
    "batlow": ["#02121d", "#053061", "#2b7a8b", "#7cbf7b", "#c7e6a2", "#f9f0c3"],
    "batlowk": ["#150b2d", "#3d2e63", "#5f4f85", "#81718f", "#a6938e", "#cbb58f", "#efd78d"],
    "batloww": ["#0a1427", "#17385d", "#295f8d", "#4f8fa3", "#7db7a1", "#b2d39a", "#e3e6a8"],
}


def _ensure_operando_colormap(name: str) -> bool:
    """Ensure the requested colormap is available, including optional cmcrameri maps."""
    if not name:
        return False
    base = name[:-2] if name.lower().endswith("_r") else name
    if base in plt.colormaps():
        return True
    try:
        cmap_obj = None
        if cmc is not None and hasattr(cmc, base):
            cmap_obj = getattr(cmc, base)
        elif cmc is not None and hasattr(cmc, base.lower()):
            cmap_obj = getattr(cmc, base.lower())
        if cmap_obj is not None:
            try:
                plt.register_cmap(name=base, cmap=cmap_obj)
            except ValueError:
                pass
            return True
    except Exception:
        pass
    custom = _CUSTOM_CMAPS.get(base.lower())
    if custom:
        try:
            cmap_obj = LinearSegmentedColormap.from_list(base.lower(), custom, N=256)
            try:
                plt.register_cmap(name=base, cmap=cmap_obj)
            except ValueError:
                pass
            return True
        except Exception:
            return False
    return False


def recommended_operando_colormaps() -> list[tuple[str, str]]:
    palettes = palette_items(["viridis", "plasma", "inferno", "cividis", "magma", "rainbow"])
    if _ensure_operando_colormap("batlow"):
        palettes.append(("batlow", "Colorblind-friendly sequential (cmcrameri)"))
    return palettes


def resolve_operando_colormap_choice(choice: str, rec_palettes: list[tuple[str, str]] | None = None) -> str:
    """Resolve numeric and `_r` palette choices to a concrete colormap name."""
    rec_palettes = rec_palettes or recommended_operando_colormaps()
    palette_map = {str(idx): name for idx, (name, _desc) in enumerate(rec_palettes, 1)}
    if choice.endswith("_r"):
        base_choice = choice[:-2]
        if base_choice in palette_map:
            return palette_map[base_choice] + "_r"
        return choice
    return palette_map.get(choice, choice)


def _resolve_operando_colormap_object(choice: str):
    """Resolve a colormap name to a Matplotlib colormap (no image mutation)."""
    choice = resolve_operando_colormap_choice(choice)
    reversed_choice = choice.lower().endswith("_r")
    base_choice = choice[:-2] if reversed_choice else choice
    palette_obj = None
    _ensure_operando_colormap(base_choice)
    available = set(name.lower() for name in plt.colormaps())
    if base_choice.lower() not in available:
        custom = _CUSTOM_CMAPS.get(base_choice.lower())
        if custom:
            palette_obj = LinearSegmentedColormap.from_list(base_choice.lower(), custom, N=256)
        else:
            raise ValueError(f"Unknown colormap '{choice}'")
    if palette_obj is None:
        palette_obj = get_colormap(base_choice)
        if palette_obj is None:
            raise ValueError(f"Unknown colormap '{choice}'")
    if reversed_choice:
        palette_obj = palette_obj.reversed()
    return choice, palette_obj


def _ensure_operando_colormap_ready(choice: str) -> str:
    """Validate colormap name; raise ValueError if unknown. Returns resolved name."""
    resolved, _palette = _resolve_operando_colormap_object(choice)
    return resolved


def apply_operando_colormap(im, choice: str):
    """Apply an operando colormap name to an image and return the colormap object."""
    choice, palette_obj = _resolve_operando_colormap_object(choice)
    im.set_cmap(palette_obj)
    setattr(im, "_operando_cmap_name", choice)
    return palette_obj


def run_operando_colormap_menu(
    *,
    fig,
    im,
    cbar,
    snapshot,
    update_custom_colorbar,
    safe_input,
    colorize_inline_commands,
) -> None:
    """Run the operando colormap submenu."""
    from ..common.menu_rendering import menu_block_begin
    from ..common.terminal import colorize_prompt

    while True:
        menu_block_begin(force_new=True)
        try:
            current_cmap = getattr(im, "_operando_cmap_name", None)
            if current_cmap is None:
                current_cmap = getattr(im.get_cmap(), "name", None)
            if current_cmap:
                print(f"Current operando colormap: {current_cmap}")
        except Exception:
            pass

        optional = []
        for extra in ("turbo", "batlow", "batlowK", "batlowW"):
            if extra == "turbo":
                if extra in plt.colormaps():
                    optional.append(extra)
            else:
                _ensure_operando_colormap(extra)
                optional.append(extra)

        print("Recommended colormaps for scientific publications:")
        rec_palettes = recommended_operando_colormaps()
        for idx, (name, desc) in enumerate(rec_palettes, 1):
            preview = palette_preview(name)
            print(f"  {idx}. {name} - {desc}")
            if preview:
                print(f"      {preview}")
        if optional:
            print("Other available: " + ", ".join(optional))
        print(colorize_inline_commands("Append _r to reverse (e.g., viridis_r or 1_r). q=back."))
        choice = safe_input(
            colorize_prompt(f"Palette name or number (1-{len(rec_palettes)}): ")
        ).strip()
        if not choice or choice.lower() == "q":
            break
        try:
            resolved_choice = resolve_operando_colormap_choice(choice, rec_palettes)
            # Validate colormap exists before undo push (raises on unknown names).
            _ensure_operando_colormap_ready(resolved_choice)
        except Exception as exc:
            print(f"Error applying colormap: {exc}")
            continue
        try:
            snapshot("operando-colormap")
            apply_operando_colormap(im, resolved_choice)
            try:
                if cbar is not None:
                    update_custom_colorbar(cbar.ax, im)
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print(f"Applied colormap: {resolved_choice}")
        except Exception as exc:
            print(f"Error applying colormap: {exc}")


def run_operando_cif_color_menu(
    *,
    fig: Any,
    ax: Any,
    cif_series: Sequence[Any],
    safe_input: Callable[..., str],
    push_state: Callable[[str], Any],
    redraw: Callable[[List[Any]], Any],
    colorize_prompt: Optional[Callable[[str], str]] = None,
) -> List[Any]:
    """XY-style CIF color editor for operando tick sets (``c`` under CIF menu).

    Supports:
    - ``1:red 2:#00FF00`` / ``1:2`` (saved user colors)
    - ``all viridis`` / ``1-2,4 magma_r`` (palette on all or a subset)
    - listed colormaps with preview bars
    - ``u`` edit saved colors

    Mutates ``ax._operando_cif_tick_series`` and ``fig._operando_cif_colormap``.
    Returns the updated series list (for the caller’s locals).
    """
    from ..common.menu_rendering import menu_block_begin, menu_block_end

    prompt = colorize_prompt or (lambda s: s)
    cts: List[Any] = list(cif_series or [])
    if not cts:
        print("No CIF sets to color.")
        return cts

    _ensure_operando_colormap("tab10")
    _ensure_operando_colormap("viridis")
    _ensure_operando_colormap("plasma")
    _palette_options = build_xy_palette_options(_ensure_operando_colormap)
    # Keep classic tab10 / Set2 / Dark2 aliases familiar from other menus
    for extra in ("tab10", "Set2", "Dark2"):
        if extra not in _palette_options:
            _palette_options.insert(0 if extra == "tab10" else len(_palette_options), extra)
    # de-dupe preserving order
    seen = set()
    _palette_options = [p for p in _palette_options if not (p in seen or seen.add(p))]
    _palette_index = {str(i): name for i, name in enumerate(_palette_options, 1)}

    def _resolve_pal(token: str) -> str:
        return resolve_palette_token(token, _palette_index)

    while True:
        cts = list(getattr(ax, "_operando_cif_tick_series", None) or cts)
        _C, _R = "\033[96m", "\033[0m"
        menu_block_begin(force_new=True)
        print("CIF color (per set).")
        user_colors = get_user_color_list(fig)
        if user_colors:
            print("Saved colors (refer as number or u#):")
            for idx, col in enumerate(user_colors, 1):
                print(f"  {idx}: {format_color_listing(col)}")
        cur_pal = getattr(fig, "_operando_cif_colormap", None)
        if cur_pal:
            print(f"Current palette: {cur_pal}")
        print("Colormaps:")
        for idx, name in enumerate(_palette_options, 1):
            bar = palette_preview(name) or ""
            print(f"  {idx}. {name}")
            if bar:
                print(f"      {bar}")
        print()
        print("How to set color:")
        print(f"  {_C}1:red 2:#00FF00{_R}       (set colors directly)")
        print(f"  {_C}1:2 2:3{_R}               (use saved user colors 2 and 3)")
        print(f"  {_C}all viridis{_R}           (apply palette to all CIF sets)")
        print(f"  {_C}1-2,4 magma_r{_R}         (apply palette to a subset)")
        print(
            f"Other: {_C}v{_R}: show current colors   "
            f"{_C}u{_R}: edit saved colors   {_C}e{_R}: pick color from screen   {_C}q{_R}: back"
        )
        menu_block_end()
        cif_line = safe_input(prompt("CIF colors> ")).strip()
        if cif_line.lower() == "q" or blank_means_back(cif_line):
            break
        low = cif_line.lower()
        if low == "v":
            cts = list(getattr(ax, "_operando_cif_tick_series", None) or cts)
            print("Current CIF colors:")
            for i, entry in enumerate(cts):
                try:
                    lab, _fname, _p, _w, _q, col = entry
                except Exception:
                    lab, col = f"set {i+1}", "k"
                print(f"  {i+1}: {format_color_listing(col)}  {lab}")
            if not cts:
                print("  (none)")
            continue
        if low == "u":
            manage_user_colors(fig)
            continue
        if low == "e":
            prompt_screen_color(fig)
            continue

        cif_tokens = cif_line.split()
        if any(":" in t for t in cif_tokens):
            planned = []
            for tok in cif_tokens:
                if ":" not in tok:
                    print(f"Skip malformed token: {tok}")
                    continue
                idx_str, color_spec = tok.split(":", 1)
                try:
                    idx = int(idx_str) - 1
                except ValueError:
                    print(f"Bad index: {idx_str}")
                    continue
                if not (0 <= idx < len(cts)):
                    print(f"Index out of range: {idx_str}")
                    continue
                try:
                    resolved = resolve_color_token(color_spec, fig)
                except Exception:
                    resolved = color_spec
                planned.append((idx, resolved))
            if not planned:
                continue
            push_state("cif-color")
            for idx, resolved in planned:
                lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
                cts[idx] = (lab, fname, peaksQ, wl_e, qmax, resolved)
            fig._operando_cif_colormap = None  # type: ignore[attr-defined]
            ax._operando_cif_tick_series = list(cts)
            redraw(cts)
            print("Applied per-set CIF colors.")
            continue

        parts = cif_tokens
        if len(parts) < 2:
            print("Need mappings (1:red) or range+palette (e.g. 'all viridis').")
            continue
        range_part = "".join(parts[:-1]).replace(" ", "")
        palette_token = parts[-1]
        pal_name = _resolve_pal(palette_token)
        available = list(_UTILS_CUSTOM_CMAPS.keys()) + list(plt.colormaps())
        if pal_name not in available and not ensure_colormap(pal_name) and not _ensure_operando_colormap(
            pal_name[:-2] if pal_name.lower().endswith("_r") else pal_name
        ):
            print(f"Unknown palette '{pal_name}'.")
            continue
        indices = parse_index_ranges(range_part, len(cts), warn_out_of_range=False)
        if not indices:
            print("No valid indices parsed.")
            continue
        try:
            cmap = get_colormap(pal_name)
        except Exception:
            cmap = None
        if cmap is None:
            print(f"Could not load palette '{pal_name}'.")
            continue
        push_state("cif-color-palette")
        nsel = len(indices)
        cif_colors = sample_colormap(cmap, nsel)
        for c_idx, idx in enumerate(indices):
            lab, fname, peaksQ, wl_e, qmax, _old = cts[idx]
            try:
                col_val = str(mcolors.to_hex(cif_colors[c_idx], keep_alpha=False)).lower()
            except Exception:
                col_val = cif_colors[c_idx]
            cts[idx] = (lab, fname, peaksQ, wl_e, qmax, col_val)
        fig._operando_cif_colormap = pal_name  # type: ignore[attr-defined]
        ax._operando_cif_tick_series = list(cts)
        redraw(cts)
        print(f"Applied '{pal_name}' to CIF set(s): " + ", ".join(str(i + 1) for i in indices))

    return list(getattr(ax, "_operando_cif_tick_series", None) or cts)


__all__ = [
    "_CUSTOM_CMAPS",
    "_ensure_operando_colormap",
    "apply_operando_colormap",
    "recommended_operando_colormaps",
    "resolve_operando_colormap_choice",
    "run_operando_colormap_menu",
    "run_operando_cif_color_menu",
]
