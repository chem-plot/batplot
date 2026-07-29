"""Shared palette / colormap helpers for interactive menus.

These primitives were duplicated (identically or near-identically) across the
``xy``, ``cpc`` and ``electrochem`` colour submenus. Centralising them keeps the
behaviour byte-for-byte identical while removing the copies. Behavioural knobs
(clip positions, out-of-range warnings) are exposed as parameters so each mode
keeps its own established defaults.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple, cast

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from ...color_utils import get_colormap


TAB10_HEX: Tuple[str, ...] = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
)

DEFAULT_PALETTE_ALIASES: Dict[str, str] = {
    "1": "tab10",
    "2": "Set2",
    "3": "Dark2",
    "4": "viridis",
    "5": "plasma",
    "6": "rainbow",
}

PALETTE_DESCRIPTIONS: Dict[str, str] = {
    "tab10": "Distinct, colorblind-friendly (default matplotlib)",
    "Set2": "Soft, pastel colors for presentations",
    "Dark2": "Bold, saturated colors for print",
    "viridis": "Perceptually uniform (blue→yellow)",
    "plasma": "Perceptually uniform (purple→yellow)",
    "inferno": "Perceptually uniform (black→yellow), good for dark backgrounds",
    "cividis": "Perceptually uniform, optimized for color vision deficiency",
    "magma": "Perceptually uniform (black→white), excellent for grayscale",
    "rainbow": "Full-spectrum rainbow gradient",
    "batlow": "Colorblind-friendly sequential (cmcrameri)",
}


def parse_index_ranges(spec: str, total: int, *, warn_out_of_range: bool = True) -> List[int]:
    """Parse a 1-based index spec into sorted, de-duplicated 0-based indices.

    Accepts ``"all"`` (returns every index) and comma-separated tokens where each
    token is either a single index (``"3"``) or an inclusive, reversible range
    (``"1-4"``). Out-of-range single indices print a notice when
    ``warn_out_of_range`` is True (the XY palette behaviour); otherwise they are
    silently skipped (the XY CIF behaviour).
    """
    spec = (spec or "").lower().strip()
    if spec == "all":
        return list(range(total))
    result: set[int] = set()
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if "-" in tok:
            try:
                a, b = tok.split("-", 1)
                s, e = int(a) - 1, int(b) - 1
                if s > e:
                    s, e = e, s
                result.update(i for i in range(s, e + 1) if 0 <= i < total)
            except ValueError:
                print(f"Bad range: {tok}")
        else:
            try:
                i = int(tok) - 1
                if 0 <= i < total:
                    result.add(i)
                elif warn_out_of_range:
                    print(f"Index out of range: {tok}")
            except ValueError:
                print(f"Bad index: {tok}")
    return sorted(result)


def resolve_palette_token(token: str, palette_map: Dict[str, str]) -> str:
    """Map a numeric/alias ``token`` to a colormap name, preserving ``_r`` suffix.

    Unknown bases pass through unchanged (so explicit colormap names still work).
    """
    suffix = "_r" if token.lower().endswith("_r") else ""
    base = token[:-2] if suffix else token
    return palette_map.get(base, base) + suffix


def palette_items(names: Iterable[str]) -> List[Tuple[str, str]]:
    """Return ``(palette, description)`` pairs for displayed palette menus."""
    return [(name, PALETTE_DESCRIPTIONS.get(name, "")) for name in names]


def build_palette_options(
    ensure_colormap: Callable[[str], Any],
    *,
    base: Sequence[str] | None = None,
    optional: Sequence[str] = ("batlow", "batlowk", "batloww"),
) -> List[str]:
    """Build a palette option list while preserving caller-provided ordering."""
    palettes = list(base or DEFAULT_PALETTE_ALIASES.values())
    for extra in optional:
        try:
            if ensure_colormap(extra) and extra not in palettes:
                palettes.append(extra)
        except Exception:
            pass
    return palettes


_XY_BASE_PALETTES = ["viridis", "cividis", "plasma", "inferno", "magma", "batlow", "rainbow"]


def build_xy_palette_options(ensure_colormap: Callable[[str], Any]) -> List[str]:
    """Build the XY/CIF palette option list (viridis family + available extras)."""
    extras: List[str] = []
    if "turbo" in plt.colormaps():
        extras.append("turbo")
    for extra in ("batlowK", "batlowW"):
        try:
            if extra in plt.colormaps() or ensure_colormap(extra):
                extras.append(extra)
        except Exception:
            pass
    return list(_XY_BASE_PALETTES) + extras[:3]


def sample_colormap(
    cmap: Any,
    n: int,
    *,
    single: float = 0.55,
    pair: Tuple[float, float] = (0.08, 0.85),
    span: Tuple[float, float] = (0.08, 0.85),
) -> List[Any]:
    """Sample ``n`` colours from ``cmap`` using the shared clip convention.

    - ``n == 1`` -> ``[cmap(single)]``
    - ``n == 2`` -> ``[cmap(pair[0]), cmap(pair[1])]``
    - ``n  > 2`` -> ``cmap`` sampled at ``linspace(span[0], span[1], n)``

    Each mode supplies its own ``pair``/``span`` so output colours are unchanged.
    """
    if n <= 0:
        return []
    if n == 1:
        return [cmap(single)]
    if n == 2:
        return [cmap(pair[0]), cmap(pair[1])]
    lo, hi = span
    return [cmap(p) for p in np.linspace(lo, hi, n)]


def sample_palette_colors(
    name: str,
    n: int,
    *,
    ensure_colormap: Callable[[str], Any],
    get_cmap: Callable[[str], Any] | None = None,
    tab10_exact: bool = True,
    prefer_listed_colors: bool = False,
    single: float = 0.55,
    pair: Tuple[float, float] = (0.08, 0.85),
    span: Tuple[float, float] = (0.08, 0.85),
) -> List[str]:
    """Sample a named palette and return hex colours.

    ``tab10_exact`` preserves the legacy hardcoded Matplotlib tab10 sequence used
    by CPC/EC menus instead of relying on backend-dependent colormap objects.
    """
    if n <= 0:
        return []
    if tab10_exact and name.lower() == "tab10":
        return [TAB10_HEX[i % len(TAB10_HEX)] for i in range(n)]
    if not ensure_colormap(name):
        name = "viridis"
        ensure_colormap(name)
    cmap_getter = get_cmap or get_colormap
    try:
        cmap = cmap_getter(name)
    except Exception:
        ensure_colormap("viridis")
        cmap = cmap_getter("viridis")
    if (
        prefer_listed_colors
        and cmap is not None
        and hasattr(cmap, "colors")
        and getattr(cmap, "colors", None) is not None
    ):
        colors = cmap.colors
        out = []
        for i in range(n):
            rgb = colors[i % len(colors)]
            if isinstance(rgb, tuple) and len(rgb) >= 3:
                out.append(mcolors.rgb2hex(rgb[:3]))
            else:
                out.append(mcolors.to_hex(cast(Any, rgb)))
        return out
    sampled = sample_colormap(cmap, n, single=single, pair=pair, span=span)
    return [mcolors.rgb2hex(color[:3]) for color in sampled]


__all__ = [
    "parse_index_ranges",
    "resolve_palette_token",
    "DEFAULT_PALETTE_ALIASES",
    "PALETTE_DESCRIPTIONS",
    "TAB10_HEX",
    "palette_items",
    "build_palette_options",
    "build_xy_palette_options",
    "sample_colormap",
    "sample_palette_colors",
]
