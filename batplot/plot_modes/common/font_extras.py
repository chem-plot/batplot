"""Bold weight and text highlight helpers shared across interactive modes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import matplotlib as mpl

DEFAULT_FONT_WEIGHT = "normal"
DEFAULT_HIGHLIGHT_FC = "white"
DEFAULT_HIGHLIGHT_ALPHA = 0.85
DEFAULT_HIGHLIGHT_PAD = 0.2


def normalize_font_weight(value: object) -> str:
    raw = str(value or DEFAULT_FONT_WEIGHT).strip().lower()
    if raw in ("bold", "b", "700", "800", "900"):
        return "bold"
    return "normal"


def is_bold_weight(value: object) -> bool:
    return normalize_font_weight(value) == "bold"


def toggle_font_weight(value: object) -> str:
    return "normal" if is_bold_weight(value) else "bold"


def get_fig_font_weight(fig: Any) -> str:
    stored = getattr(fig, "_bp_font_weight", None)
    if stored is not None:
        return normalize_font_weight(stored)
    return normalize_font_weight(mpl.rcParams.get("font.weight", DEFAULT_FONT_WEIGHT))


def set_fig_font_weight(fig: Any, weight: object) -> str:
    w = normalize_font_weight(weight)
    fig._bp_font_weight = w
    mpl.rcParams["font.weight"] = w
    return w


def get_fig_text_highlight(fig: Any) -> bool:
    return bool(getattr(fig, "_bp_text_highlight", False))


def get_fig_text_highlight_style(fig: Any) -> dict[str, float | str]:
    return {
        "fc": str(getattr(fig, "_bp_text_highlight_fc", DEFAULT_HIGHLIGHT_FC)),
        "alpha": float(getattr(fig, "_bp_text_highlight_alpha", DEFAULT_HIGHLIGHT_ALPHA)),
        "pad": float(getattr(fig, "_bp_text_highlight_pad", DEFAULT_HIGHLIGHT_PAD)),
    }


def set_fig_text_highlight(fig: Any, enabled: bool, *, fc: str | None = None, alpha: float | None = None, pad: float | None = None) -> None:
    fig._bp_text_highlight = bool(enabled)
    if fc is not None:
        fig._bp_text_highlight_fc = str(fc)
    if alpha is not None:
        fig._bp_text_highlight_alpha = max(0.0, min(1.0, float(alpha)))
    if pad is not None:
        fig._bp_text_highlight_pad = max(0.0, float(pad))


def highlight_bbox(style: dict[str, float | str] | None = None) -> dict[str, object]:
    st = style or {}
    return {
        "boxstyle": f"round,pad={float(st.get('pad', DEFAULT_HIGHLIGHT_PAD)):g}",
        "facecolor": str(st.get("fc", DEFAULT_HIGHLIGHT_FC)),
        "edgecolor": "0.7",
        "alpha": float(st.get("alpha", DEFAULT_HIGHLIGHT_ALPHA)),
    }


def highlight_path_effects() -> list[Any]:
    try:
        from matplotlib import patheffects as pe

        return [pe.withStroke(linewidth=2.5, foreground="white")]
    except Exception:
        return []


def apply_font_weight_to_artists(artists: Iterable[Any], weight: object) -> None:
    w = normalize_font_weight(weight)
    for artist in artists:
        if artist is None:
            continue
        try:
            if hasattr(artist, "set_fontweight"):
                artist.set_fontweight(w)
            elif hasattr(artist, "set_weight"):
                artist.set_weight(w)
        except Exception:
            pass


def apply_text_highlight_to_artists(artists: Iterable[Any], enabled: bool, style: dict[str, float | str] | None = None) -> None:
    bbox = highlight_bbox(style) if enabled else None
    pe = highlight_path_effects() if enabled else None
    for artist in artists:
        if artist is None:
            continue
        try:
            artist.set_bbox(bbox)
        except Exception:
            pass
        try:
            artist.set_path_effects(pe)
        except Exception:
            pass


def font_extras_export_dict(fig: Any) -> dict[str, object]:
    st = get_fig_text_highlight_style(fig)
    return {
        "weight": get_fig_font_weight(fig),
        "highlight": get_fig_text_highlight(fig),
        "highlight_fc": st["fc"],
        "highlight_alpha": st["alpha"],
        "highlight_pad": st["pad"],
    }


def apply_font_extras_from_cfg(fig: Any, artists: Iterable[Any], cfg: dict[str, object] | None) -> None:
    if not cfg:
        return
    if cfg.get("weight") is not None:
        w = set_fig_font_weight(fig, cfg["weight"])
        apply_font_weight_to_artists(artists, w)
    highlight = cfg.get("highlight")
    if highlight is not None:
        try:
            alpha_raw = cfg.get("highlight_alpha", DEFAULT_HIGHLIGHT_ALPHA)
            alpha = float(alpha_raw) if isinstance(alpha_raw, (int, float, str)) else DEFAULT_HIGHLIGHT_ALPHA
        except (TypeError, ValueError):
            alpha = DEFAULT_HIGHLIGHT_ALPHA
        try:
            pad_raw = cfg.get("highlight_pad", DEFAULT_HIGHLIGHT_PAD)
            pad = float(pad_raw) if isinstance(pad_raw, (int, float, str)) else DEFAULT_HIGHLIGHT_PAD
        except (TypeError, ValueError):
            pad = DEFAULT_HIGHLIGHT_PAD
        fc = cfg.get("highlight_fc", DEFAULT_HIGHLIGHT_FC)
        style = {
            "fc": str(fc if fc is not None else DEFAULT_HIGHLIGHT_FC),
            "alpha": alpha,
            "pad": pad,
        }
        set_fig_text_highlight(fig, bool(highlight), fc=str(style["fc"]), alpha=float(style["alpha"]), pad=float(style["pad"]))
        apply_text_highlight_to_artists(artists, bool(highlight), style)


def merge_session_font_dump(fig: Any, *, include_mathtext: bool = True) -> dict[str, object]:
    """Build the ``font`` block for session ``.pkl`` save (family/size + weight/highlight)."""
    out: dict[str, object] = {
        "size": mpl.rcParams.get("font.size"),
        "chain": list(mpl.rcParams.get("font.sans-serif", [])),
    }
    if include_mathtext:
        out["mathtext_fontset"] = mpl.rcParams.get("mathtext.fontset")
    out.update(font_extras_export_dict(fig))
    return out


def _resolve_font_family_from_cfg(font_cfg: dict[str, object]) -> str | None:
    fam = font_cfg.get("family")
    if isinstance(fam, str) and fam.strip():
        return fam.strip()
    for key in ("family_chain", "chain"):
        chain = font_cfg.get(key)
        if chain and isinstance(chain, (list, tuple)) and chain:
            head = chain[0]
            if head is not None and str(head).strip():
                return str(head).strip()
    return None


def sync_font_rcparams_from_cfg(font_cfg: dict[str, object] | None) -> None:
    """Update matplotlib rcParams from a saved ``font`` block (no artist mutation)."""
    if not font_cfg:
        return
    from .fonts import set_font_family_defaults, set_font_size_default

    fam = _resolve_font_family_from_cfg(font_cfg)
    fam_chain = font_cfg.get("family_chain")
    chain = font_cfg.get("chain")
    if fam_chain and isinstance(fam_chain, (list, tuple)) and fam_chain:
        mpl.rcParams["font.family"] = "sans-serif"
        mpl.rcParams["font.sans-serif"] = list(fam_chain)
    elif chain and isinstance(chain, (list, tuple)) and chain:
        mpl.rcParams["font.family"] = "sans-serif"
        mpl.rcParams["font.sans-serif"] = list(chain)
    elif fam:
        set_font_family_defaults(fam, sans_serif_stack=True, update_mathtext=True)
    if font_cfg.get("size") is not None:
        size_raw = font_cfg["size"]
        if isinstance(size_raw, (int, float, str)):
            set_font_size_default(float(size_raw))
    if font_cfg.get("mathtext_fontset"):
        mpl.rcParams["mathtext.fontset"] = font_cfg["mathtext_fontset"]


def apply_session_font_cfg(
    fig: Any,
    font_cfg: dict[str, object] | None,
    *axes: Any,
    cbar_ax: Any = None,
    extra_artists: Iterable[Any] | None = None,
    artists: Iterable[Any] | None = None,
) -> None:
    """Restore saved font family/size/weight/highlight onto existing figure text.

    Call at the **end** of session load or style apply, after labels/legend/ticks
    are rebuilt, so axis labels adopt the saved size instead of matplotlib defaults.
    """
    if not font_cfg:
        return
    from .fonts import (
        apply_font_family_to_artists,
        apply_font_size_to_artists,
        collect_fig_font_artists,
        sync_legend_title_fontsize,
    )

    sync_font_rcparams_from_cfg(font_cfg)

    collected: list[Any] = []
    if artists is not None:
        collected.extend(a for a in artists if a is not None)
    else:
        for ax in axes:
            if ax is None:
                continue
            collected.extend(
                collect_fig_font_artists(ax, fig, include_title=True, include_axes_texts=True)
            )
        if cbar_ax is not None:
            try:
                collected.extend(collect_fig_font_artists(cbar_ax, fig, include_axes_texts=True))
            except Exception:
                pass
        if extra_artists:
            collected.extend(a for a in extra_artists if a is not None)

    fam = _resolve_font_family_from_cfg(font_cfg)
    if fam:
        apply_font_family_to_artists(collected, fam)
    if font_cfg.get("size") is not None:
        size_raw = font_cfg["size"]
        if isinstance(size_raw, (int, float, str)):
            sz = float(size_raw)
            apply_font_size_to_artists(collected, sz)
            for ax in axes:
                if ax is not None:
                    sync_legend_title_fontsize(ax.get_legend(), sz)
    apply_font_extras_from_cfg(fig, collected, font_cfg)


def apply_session_font_extras(
    fig: Any,
    font_cfg: dict[str, object] | None,
    *axes: Any,
    cbar_ax: Any = None,
    extra_artists: Iterable[Any] | None = None,
) -> None:
    """Restore font weight/highlight only (legacy helper).

    Prefer :func:`apply_session_font_cfg` for full family/size/weight/highlight restore.
    """
    if not font_cfg:
        return
    from .fonts import collect_fig_font_artists

    artists: list[Any] = []
    for ax in axes:
        if ax is None:
            continue
        artists.extend(collect_fig_font_artists(ax, fig, include_title=True, include_axes_texts=True))
    if cbar_ax is not None:
        try:
            artists.extend(collect_fig_font_artists(cbar_ax, fig))
        except Exception:
            pass
    if extra_artists:
        artists.extend(a for a in extra_artists if a is not None)
    apply_font_extras_from_cfg(fig, artists, font_cfg)


def refresh_font_extras_on_artists(fig: Any, artists: Iterable[Any]) -> None:
    """Re-apply stored fig weight/highlight to text artists (after color/spine changes)."""
    apply_font_weight_to_artists(artists, get_fig_font_weight(fig))
    apply_text_highlight_to_artists(
        artists,
        get_fig_text_highlight(fig),
        get_fig_text_highlight_style(fig),
    )


def apply_fig_font_weight(fig: Any, artists: Iterable[Any], weight: object) -> str:
    w = set_fig_font_weight(fig, weight)
    apply_font_weight_to_artists(artists, w)
    return w


def apply_fig_text_highlight(
    fig: Any,
    artists: Iterable[Any],
    enabled: bool,
    *,
    fc: str | None = None,
    alpha: float | None = None,
    pad: float | None = None,
) -> None:
    set_fig_text_highlight(fig, enabled, fc=fc, alpha=alpha, pad=pad)
    apply_text_highlight_to_artists(artists, enabled, get_fig_text_highlight_style(fig))


def histo_style_to_highlight_style(style: Any) -> dict[str, float | str]:
    return {
        "fc": str(getattr(style, "text_highlight_fc", DEFAULT_HIGHLIGHT_FC)),
        "alpha": float(getattr(style, "text_highlight_alpha", DEFAULT_HIGHLIGHT_ALPHA)),
        "pad": float(getattr(style, "text_highlight_pad", DEFAULT_HIGHLIGHT_PAD)),
    }


def apply_font_extras_to_histo_style(style: Any, fig: Any | None = None) -> None:
    """Copy fig font extras onto histo style (batch sync helper)."""
    if fig is None:
        return
    style.font_weight = get_fig_font_weight(fig)
    style.text_highlight = get_fig_text_highlight(fig)
    st = get_fig_text_highlight_style(fig)
    style.text_highlight_fc = str(st["fc"])
    style.text_highlight_alpha = float(st["alpha"])
    style.text_highlight_pad = float(st["pad"])


def sync_histo_style_font_extras_to_fig(style: Any, fig: Any) -> None:
    set_fig_font_weight(fig, getattr(style, "font_weight", DEFAULT_FONT_WEIGHT))
    set_fig_text_highlight(
        fig,
        bool(getattr(style, "text_highlight", False)),
        fc=str(getattr(style, "text_highlight_fc", DEFAULT_HIGHLIGHT_FC)),
        alpha=float(getattr(style, "text_highlight_alpha", DEFAULT_HIGHLIGHT_ALPHA)),
        pad=float(getattr(style, "text_highlight_pad", DEFAULT_HIGHLIGHT_PAD)),
    )


__all__ = [
    "DEFAULT_FONT_WEIGHT",
    "DEFAULT_HIGHLIGHT_ALPHA",
    "DEFAULT_HIGHLIGHT_FC",
    "DEFAULT_HIGHLIGHT_PAD",
    "apply_font_extras_from_cfg",
    "apply_fig_font_weight",
    "apply_fig_text_highlight",
    "apply_font_extras_to_histo_style",
    "apply_font_weight_to_artists",
    "apply_session_font_cfg",
    "apply_session_font_extras",
    "apply_text_highlight_to_artists",
    "font_extras_export_dict",
    "get_fig_font_weight",
    "get_fig_text_highlight",
    "get_fig_text_highlight_style",
    "merge_session_font_dump",
    "sync_font_rcparams_from_cfg",
    "highlight_bbox",
    "highlight_path_effects",
    "histo_style_to_highlight_style",
    "is_bold_weight",
    "normalize_font_weight",
    "refresh_font_extras_on_artists",
    "set_fig_font_weight",
    "set_fig_text_highlight",
    "sync_histo_style_font_extras_to_fig",
    "toggle_font_weight",
]
