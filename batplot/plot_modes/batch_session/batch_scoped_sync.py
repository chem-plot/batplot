"""Shared peer-merge helpers for batch style sync (avoid full-style over-sync).

Pattern (same as EC ``apply_ec_scoped_sync``):
1. Start from the *peer* panel's current style snapshot.
2. Overlay only the keys the active menu owns from the reference cfg.
3. Apply as style-only (never hitchhike canvas/geometry resize).

``p`` / ``i`` / ``s`` / ``b`` keep using each mode's full apply path.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, FrozenSet, Mapping, MutableMapping, Optional, Sequence


def deep_merge_keys(
    peer_cfg: Mapping[str, Any],
    ref_cfg: Mapping[str, Any],
    *,
    top_keys: FrozenSet[str] = frozenset(),
    nested_keys: Optional[Mapping[str, FrozenSet[str]]] = None,
    force_kind: Optional[str] = None,
    drop_geometry: bool = True,
) -> dict:
    """Return peer_cfg ⊕ selected keys from ref_cfg."""
    merged: dict = copy.deepcopy(dict(peer_cfg))
    if force_kind is not None:
        merged["kind"] = force_kind
    if drop_geometry:
        merged.pop("geometry", None)
        merged.pop("axes_geometry", None)
        fig = merged.get("figure")
        if isinstance(fig, dict):
            fig = dict(fig)
            fig.pop("canvas_size", None)
            fig.pop("frame_size", None)
            fig.pop("axes_fraction", None)
            merged["figure"] = fig

    for key in top_keys:
        if key in ref_cfg:
            merged[key] = copy.deepcopy(ref_cfg[key])

    if nested_keys:
        for section, keys in nested_keys.items():
            ref_sec = ref_cfg.get(section)
            if not isinstance(ref_sec, dict) or not keys:
                continue
            peer_sec = merged.get(section)
            out_sec = copy.deepcopy(peer_sec) if isinstance(peer_sec, dict) else {}
            for sub in keys:
                if sub in ref_sec:
                    out_sec[sub] = copy.deepcopy(ref_sec[sub])
            merged[section] = out_sec
    return merged


def merge_spines_props(
    peer: Any,
    ref: Any,
    *,
    mode: str,
) -> dict:
    """mode: ``linewidth`` | ``color`` | ``visible`` | ``all``."""
    out = copy.deepcopy(peer) if isinstance(peer, dict) else {}
    if not isinstance(ref, dict):
        return out
    for name, props in ref.items():
        if not isinstance(props, dict):
            continue
        dest = dict(out.get(name) or {})
        if mode in ("linewidth", "all"):
            if "linewidth" in props:
                dest["linewidth"] = props["linewidth"]
        # Visibility is owned by WASD (``t``).
        if mode in ("visible", "all") and "visible" in props:
            dest["visible"] = props["visible"]
        if mode in ("color", "all"):
            if "color" in props:
                dest["color"] = props["color"]
        out[name] = dest
    return out


def merge_list_of_dicts_fields(
    peer_list: Any,
    ref_list: Any,
    fields: Sequence[str],
) -> Any:
    """Overlay selected fields onto equal-length list-of-dicts (keep peer otherwise)."""
    if not isinstance(peer_list, list) or not isinstance(ref_list, list):
        return peer_list
    if len(peer_list) != len(ref_list):
        return peer_list
    out = copy.deepcopy(peer_list)
    for i, ref_entry in enumerate(ref_list):
        if not isinstance(ref_entry, dict) or not isinstance(out[i], dict):
            continue
        for field in fields:
            if field in ref_entry:
                out[i][field] = copy.deepcopy(ref_entry[field])
    return out


def make_scoped_apply(
    *,
    capture_peer: Callable[[Any], dict],
    apply_merged: Callable[[Any, dict], bool],
    build_merged: Callable[[dict, dict], dict],
) -> Callable[..., bool]:
    """Build ``apply_cfg(panel, ref_cfg)`` for ``edit_ref_then_sync``."""

    def _apply(panel: Any, ref_cfg: dict, *, silent: bool = True) -> bool:
        try:
            peer = capture_peer(panel)
            merged = build_merged(peer, ref_cfg if isinstance(ref_cfg, dict) else {})
            return bool(apply_merged(panel, merged))
        except Exception as exc:
            if not silent:
                print(f"Scoped sync failed for {getattr(panel, 'path', '?')}: {exc}")
            return False

    return _apply


__all__ = [
    "deep_merge_keys",
    "make_scoped_apply",
    "merge_list_of_dicts_fields",
    "merge_spines_props",
]
