"""Load multiple session files for batch editing."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...session import load_cpc_session, load_ec_session, load_operando_session, load_xy_session
from ..common.session_helpers import restore_last_figure_export_path
from ..electrochem.dqdv_2d import restore_dqdv_2d_companion_figure
from ..histo.session import load_histo_session
from ..xy.interactive import normalize_xy_menu_kwargs
from .kinds import load_session_dict, validate_batch_profiles


@dataclass
class XyPanel:
    path: str
    fig: Any
    ax: Any
    menu_kwargs: dict


@dataclass
class EcPanel:
    path: str
    fig: Any
    ax: Any
    cycle_lines: Any = None
    file_data: Any = None


@dataclass
class CpcPanel:
    path: str
    fig: Any
    ax: Any
    ax2: Any
    sc_charge: Any
    sc_discharge: Any
    sc_eff: Any
    file_data: Any = None
    tick_state: dict = field(default_factory=dict)


@dataclass
class OperandoPanel:
    path: str
    fig: Any
    ax: Any
    im: Any
    cbar: Any
    ec_ax: Any


@dataclass
class HistoPanel:
    path: str
    fig: Any
    ax: Any
    state: Any


@dataclass
class BatchLoadResult:
    kind: str
    panels: list


def _seed_session_path(fig, path: str) -> None:
    try:
        fig._last_session_save_path = os.path.abspath(path)
    except Exception:
        pass


def validate_same_kind(paths: List[str]) -> tuple[str | None, Dict[str, str], int | None]:
    """Return (kind, path->kind, error_code).

    Backward-compatible wrapper around :func:`validate_batch_profiles`.
    Mixed top-level kinds and mismatched subtypes both abort (``error_code=1``);
    subtype mismatches print a Warning instead of an Error.
    """
    kind, profiles, err = validate_batch_profiles(paths)
    kinds = {path: profile.kind for path, profile in profiles.items()}
    return kind, kinds, err


def load_batch_panels(paths: List[str]) -> BatchLoadResult | int:
    kind, _profiles, err = validate_batch_profiles(paths)
    if err is not None:
        return err
    assert kind is not None
    panels: list = []
    for path in paths:
        abspath = os.path.abspath(path)
        loaded = _load_one_panel(kind, abspath)
        if loaded is None:
            print(f"Failed to load: {abspath}")
            return 1
        panels.append(loaded)
    return BatchLoadResult(kind=kind, panels=panels)


def _load_one_panel(kind: str, path: str):
    if kind == "xy":
        res = load_xy_session(path)
        if not res:
            return None
        fig, ax, menu_kwargs = res
        _seed_session_path(fig, path)
        return XyPanel(path=path, fig=fig, ax=ax, menu_kwargs=normalize_xy_menu_kwargs(menu_kwargs))
    if kind == "ec_gc":
        res = load_ec_session(path)
        if not res:
            return None
        if len(res) == 4 and res[2] is None:
            fig, ax, _, file_data = res
            panel = EcPanel(path=path, fig=fig, ax=ax, file_data=file_data)
        else:
            fig, ax, cycle_lines = res[0], res[1], res[2]
            panel = EcPanel(path=path, fig=fig, ax=ax, cycle_lines=cycle_lines)
        _seed_session_path(panel.fig, path)
        return panel
    if kind == "cpc":
        res = load_cpc_session(path)
        if not res:
            return None
        fig, ax, ax2, sc_c, sc_d, sc_e, file_data = res
        _seed_session_path(fig, path)
        tick_state = {
            "bx": True,
            "tx": False,
            "ly": True,
            "ry": True,
            "b_ticks": True,
            "t_ticks": False,
            "l_ticks": True,
            "r_ticks": True,
            "b_labels": True,
            "t_labels": False,
            "l_labels": True,
            "r_labels": True,
            "mbx": False,
            "mtx": False,
            "mly": False,
            "mry": False,
        }
        # Prefer axis attr even when {} (empty dict is authoritative, not "missing").
        saved_ax = getattr(ax, "_saved_tick_state", None)
        saved_fig = getattr(fig, "_saved_tick_state", None)
        if isinstance(saved_ax, dict):
            tick_state = dict(saved_ax)
        elif isinstance(saved_fig, dict):
            tick_state = dict(saved_fig)
        return CpcPanel(
            path=path,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_c,
            sc_discharge=sc_d,
            sc_eff=sc_e,
            file_data=file_data,
            tick_state=tick_state,
        )
    if kind == "operando_ec":
        res = load_operando_session(path)
        if not res:
            return None
        fig, ax, im, cbar, ec_ax = res
        _seed_session_path(fig, path)
        return OperandoPanel(path=path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax)
    if kind == "dqdv_2d_contour":
        sess = load_session_dict(path)
        if not sess:
            return None
        res = restore_dqdv_2d_companion_figure(sess)
        if not res:
            return None
        fig, ax, im, cbar = res
        _seed_session_path(fig, path)
        try:
            restore_last_figure_export_path(fig, sess, session_filename=path)
        except Exception:
            pass
        return OperandoPanel(path=path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None)
    if kind == "histo":
        res = load_histo_session(path)
        if not res:
            return None
        fig, ax, state = res
        _seed_session_path(fig, path)
        return HistoPanel(path=path, fig=fig, ax=ax, state=state)
    return None


__all__ = [
    "BatchLoadResult",
    "CpcPanel",
    "EcPanel",
    "HistoPanel",
    "OperandoPanel",
    "XyPanel",
    "load_batch_panels",
    "validate_same_kind",
    "validate_batch_profiles",
]
