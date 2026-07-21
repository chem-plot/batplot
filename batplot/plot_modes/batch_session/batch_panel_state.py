"""Central batch panel state contract for ``p`` / ``i`` / ``s`` / ``b``.

Batch interactive menus mutate figures through mode-specific helpers.  Undo (``b``),
style export (``p``), style import (``i``), and session save (``s``) must all
round-trip the *same* snapshot shape.  Register each supported ``kind`` here so
new batch keys have a single place to hook capture/restore and CI can enforce the
contract without manual reminders.

When adding a batch menu command that changes visible style or geometry:

1. Push undo via the registered ``capture`` function (or ``SyncUndoStacks`` using it).
2. Confirm the edit is included in ``capture`` output (fields the user expects in
   ``p``/``i``/``ops``/``opsg``).
3. Add/extend ``tests/test_batch_pisb_contract.py`` for the mode.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..histo.interactive import _export_style as export_histo_style
from ..histo.session import (
    apply_histo_snapshot,
    apply_histo_style_snapshot,
    capture_histo_snapshot,
)
from ..operando.style import build_operando_ec_style_config_v2
from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.style import export_style_config
from . import menu_cpc, menu_ec, menu_operando, menu_xy
from .menu_histo import _save_histo_panel
from .xy_batch_helpers import dump_xy_panel

CaptureFn = Callable[[Any], dict]
RestoreFn = Callable[[Any, dict], None]
ApplyImportFn = Callable[[Any, Any], bool | None]
SaveFn = Callable[[Any, str], None]
ExportStyleFn = Callable[[Any, str, str], None]
LoadImportFn = Callable[[str], Any | None]


@dataclass(frozen=True)
class BatchPanelStateHandler:
    """Per-mode hooks shared by undo, style I/O, and session save."""

    kind: str
    capture: CaptureFn
    restore: RestoreFn
    apply_import: ApplyImportFn
    save: SaveFn
    export_style: ExportStyleFn
    load_import: LoadImportFn
    style_ext_ps: str = ".bps"
    style_ext_psg: str = ".bpsg"


def _capture_xy(panel) -> dict:
    return menu_xy._capture_panel(panel)


def _restore_xy(panel, cfg: dict) -> None:
    menu_xy._restore_panel(panel, cfg)


def _apply_xy_import(panel, style_path: str) -> bool | None:
    return menu_xy._apply_style_path(panel, style_path)


def _export_xy_style(panel, path: str, sub: str) -> None:
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    tick_state = menu_xy._tick_state_for(panel)
    cif_globals = kw.get("cif_globals") or {}
    export_style_config(
        path,
        panel.fig,
        panel.ax,
        kw.get("y_data_list") or [],
        kw.get("labels") or [],
        kw.get("delta", 0.0),
        kw.get("args"),
        tick_state,
        kw.get("offsets_list") or [],
        cif_tick_series=cif_globals.get("cif_tick_series"),
        label_text_objects=kw.get("label_text_objects") or [],
        overwrite_path=path,
        force_kind=sub,
    )


def _load_xy_import(path: str):
    return path if os.path.isfile(path) else None


def _capture_ec(panel) -> dict:
    return menu_ec._capture_panel(panel)


def _restore_ec(panel, cfg: dict) -> None:
    menu_ec._restore_panel(panel, cfg)


def _apply_ec_import(panel, cfg: dict) -> bool | None:
    return menu_ec._apply_cfg(panel, cfg)


def _export_ec_style(panel, path: str, sub: str) -> None:
    cfg = _capture_ec(panel)
    cfg["kind"] = "ec_style_geom" if sub == "psg" else "ec_style"
    if sub == "ps":
        cfg.pop("geometry", None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def _load_json_style(path: str) -> dict | None:
    from ...batch import _load_style_file

    return _load_style_file(path) or None


def _capture_cpc(panel) -> dict:
    return menu_cpc._capture_panel(panel)


def _restore_cpc(panel, cfg: dict) -> None:
    menu_cpc._restore_panel(panel, cfg)


def _apply_cpc_import(panel, cfg: dict) -> bool | None:
    return menu_cpc._apply_cpc_style(panel, cfg)


def _export_cpc_style(panel, path: str, sub: str) -> None:
    cfg = _capture_cpc(panel)
    cfg["kind"] = "cpc_style_geom" if sub == "psg" else "cpc_style"
    if sub == "ps":
        cfg.pop("geometry", None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def _capture_operando(panel) -> dict:
    return menu_operando._capture_panel(panel)


def _restore_operando(panel, cfg: dict) -> None:
    menu_operando._restore_panel(panel, cfg)


def _apply_operando_import(panel, cfg: dict) -> bool | None:
    return menu_operando._apply_operando_cfg(panel, cfg)


def _export_operando_style(panel, path: str, sub: str) -> None:
    cfg, _ext = build_operando_ec_style_config_v2(
        panel.fig, panel.ax, panel.im, panel.cbar, panel.ec_ax, sub
    )
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


def _capture_histo(panel) -> dict:
    return capture_histo_snapshot(panel.state, panel.fig, panel.ax)


def _restore_histo(panel, cfg: dict) -> None:
    apply_histo_snapshot(panel.fig, panel.ax, panel.state, cfg)


def _apply_histo_import(panel, cfg: dict) -> bool | None:
    apply_histo_style_snapshot(panel.fig, panel.ax, panel.state, cfg)
    return True


def _export_histo_style(panel, path: str, sub: str) -> None:
    export_histo_style(
        panel.fig,
        panel.ax,
        panel.state,
        path,
        include_geometry=(sub == "psg"),
    )


def _load_histo_style(path: str) -> dict | None:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    kind = payload.get("kind", "")
    if kind and kind != "histo_style":
        return None
    return payload


_BATCH_HANDLERS: dict[str, BatchPanelStateHandler] = {
    "xy": BatchPanelStateHandler(
        kind="xy",
        capture=_capture_xy,
        restore=_restore_xy,
        apply_import=_apply_xy_import,
        save=dump_xy_panel,
        export_style=_export_xy_style,
        load_import=_load_xy_import,
        style_ext_ps=".bps",
        style_ext_psg=".bpsg",
    ),
    "ec_gc": BatchPanelStateHandler(
        kind="ec_gc",
        capture=_capture_ec,
        restore=_restore_ec,
        apply_import=_apply_ec_import,
        save=menu_ec._save_ec_panel,
        export_style=_export_ec_style,
        load_import=_load_json_style,
    ),
    "cpc": BatchPanelStateHandler(
        kind="cpc",
        capture=_capture_cpc,
        restore=_restore_cpc,
        apply_import=_apply_cpc_import,
        save=menu_cpc._save_cpc_panel,
        export_style=_export_cpc_style,
        load_import=_load_json_style,
    ),
    "operando_ec": BatchPanelStateHandler(
        kind="operando_ec",
        capture=_capture_operando,
        restore=_restore_operando,
        apply_import=_apply_operando_import,
        save=menu_operando._save_operando_panel,
        export_style=_export_operando_style,
        load_import=_load_json_style,
    ),
    "histo": BatchPanelStateHandler(
        kind="histo",
        capture=_capture_histo,
        restore=_restore_histo,
        apply_import=_apply_histo_import,
        save=_save_histo_panel,
        export_style=_export_histo_style,
        load_import=_load_histo_style,
        style_ext_ps=".bpsh",
        style_ext_psg=".bpsh",
    ),
}


def batch_state_handlers() -> Mapping[str, BatchPanelStateHandler]:
    """Return registered batch kind → handler map (copy)."""
    return dict(_BATCH_HANDLERS)


def get_batch_state_handler(kind: str) -> BatchPanelStateHandler:
    try:
        return _BATCH_HANDLERS[kind]
    except KeyError as exc:
        supported = ", ".join(sorted(_BATCH_HANDLERS))
        raise KeyError(f"Unsupported batch kind {kind!r}; supported: {supported}") from exc


def verify_panel_pisb_roundtrip(panel: Any, kind: str, *, sub: str = "ps") -> None:
    """Raise when capture/restore or export/import round-trip fails for one panel."""
    handler = get_batch_state_handler(kind)
    snap = handler.capture(panel)
    if not isinstance(snap, dict):
        raise TypeError(f"{kind} capture must return dict, got {type(snap).__name__}")

    handler.restore(panel, snap)

    fd, style_path = _temp_path(handler.style_ext_ps if sub == "ps" else handler.style_ext_psg)
    os.close(fd)
    try:
        handler.export_style(panel, style_path, sub)
        payload = handler.load_import(style_path)
        if payload is None:
            raise RuntimeError(f"{kind} load_import returned None for exported {sub}")
        before = handler.capture(panel)
        result = handler.apply_import(panel, payload)
        if result is False:
            raise RuntimeError(f"{kind} apply_import rejected exported {sub}")
        handler.restore(panel, before)
    finally:
        try:
            os.unlink(style_path)
        except OSError:
            pass


def _temp_path(suffix: str) -> tuple[int, str]:
    import tempfile

    return tempfile.mkstemp(suffix=suffix)


__all__ = [
    "BatchPanelStateHandler",
    "batch_state_handlers",
    "get_batch_state_handler",
    "verify_panel_pisb_roundtrip",
]
