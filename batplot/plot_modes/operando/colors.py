"""Operando colormap helpers and menu runner."""

from __future__ import annotations

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.colors import LinearSegmentedColormap  # type: ignore[import-untyped]

from ...color_utils import get_colormap, palette_preview
from ..common.palettes import palette_items

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


def apply_operando_colormap(im, choice: str):
    """Apply an operando colormap name to an image and return the colormap object."""
    choice = resolve_operando_colormap_choice(choice)
    reversed_choice = choice.lower().endswith("_r")
    base_choice = choice[:-2] if reversed_choice else choice
    palette_obj = None
    if _ensure_operando_colormap(base_choice):
        available = set(name.lower() for name in plt.colormaps())
    else:
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
    while True:
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
            print("\nOther available: " + ", ".join(optional))
        print(colorize_inline_commands("Append _r to reverse (e.g., viridis_r or 1_r). q=back."))
        choice = safe_input(f"Palette name or number (1-{len(rec_palettes)}): ").strip()
        if not choice or choice.lower() == "q":
            break
        try:
            snapshot("operando-colormap")
            resolved_choice = resolve_operando_colormap_choice(choice, rec_palettes)
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


__all__ = [
    "_CUSTOM_CMAPS",
    "_ensure_operando_colormap",
    "apply_operando_colormap",
    "recommended_operando_colormaps",
    "resolve_operando_colormap_choice",
    "run_operando_colormap_menu",
]
