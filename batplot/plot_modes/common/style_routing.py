"""Unified style-import entry points for CLI, batch, and routing.

Interactive menus should continue calling each mode's full applier directly
when they have complete context (labels, tick state, file data, etc.).
CLI and batch paths route through these helpers so they share the same
canonical apply logic as interactive ``i`` import.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from .spines import default_flat_tick_state


def _noop_update_labels(*_args: Any, **_kwargs: Any) -> None:
    pass


def default_ec_tick_state(ax: Any = None) -> Dict[str, Any]:
    saved = getattr(ax, "_saved_tick_state", None) if ax is not None else None
    if isinstance(saved, dict):
        return dict(saved)
    return {
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
        "b_ticks": True,
        "t_ticks": False,
        "l_ticks": True,
        "r_ticks": False,
        "b_labels": True,
        "t_labels": False,
        "l_labels": True,
        "r_labels": False,
        "mbx": False,
        "mtx": False,
        "mly": False,
        "mry": False,
    }


def apply_xy_style_dict(
    cfg: dict,
    fig: Any,
    ax: Any,
    *,
    silent: bool = False,
    keep_canvas_fixed: bool = False,
    **kwargs: Any,
) -> bool:
    """Apply an XY style/geometry dict via ``plot_modes.xy.style``."""
    import json
    import os
    import tempfile

    from ..xy.style import apply_style_config

    params = {
        "x_data_list": None,
        "y_data_list": [],
        "orig_y": None,
        "offsets_list": [],
        "label_text_objects": [],
        "args": SimpleNamespace(stack=False),
        "tick_state": default_flat_tick_state(),
        "labels": [],
        "update_labels_func": _noop_update_labels,
        "cif_tick_series": None,
        "cif_hkl_label_map": None,
        "adjust_margins_cb": None,
        "keep_canvas_fixed": keep_canvas_fixed,
    }
    params.update(kwargs)
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix=".bpsg")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        apply_style_config(path, fig, ax, **params)
        return True
    except Exception as exc:
        if not silent:
            print(f"Warning: Error applying XY style: {exc}")
        return False
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def apply_ec_style_dict(
    cfg: dict,
    fig: Any,
    ax: Any,
    *,
    cycle_lines: Optional[dict] = None,
    file_data: Optional[List[dict]] = None,
    tick_state: Optional[dict] = None,
    is_multi_file: bool = False,
    silent: bool = False,
) -> bool:
    """Apply an EC style/geometry dict via ``plot_modes.electrochem.style_apply``."""
    from ..electrochem.style_apply import apply_ec_style_config

    ts = tick_state if tick_state is not None else default_ec_tick_state(ax)
    return apply_ec_style_config(
        cfg,
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines or {},
        file_data=file_data,
        tick_state=ts,
        is_multi_file=is_multi_file,
        silent=silent,
    )


__all__ = [
    "apply_ec_style_dict",
    "apply_xy_style_dict",
    "default_ec_tick_state",
]
