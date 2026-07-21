"""Smoke-test interactive submenu entry points after session reload (q-only)."""

from __future__ import annotations

import os
import pickle
from typing import Any, Callable

import matplotlib.pyplot as plt

from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.colors import run_xy_color_menu
from ..xy.labels import run_xy_rename_menu
from ..xy.line_style import run_line_style_menu
from ..xy.derivative import run_derivative_menu
from ..xy.axis_range import run_x_range_menu, run_y_range_menu
from ..common.menus import run_font_menu
from ..common.font_extras import (
    apply_fig_font_weight,
    apply_fig_text_highlight,
    get_fig_font_weight,
    get_fig_text_highlight,
    get_fig_text_highlight_style,
)


def _q_input(_prompt: str = "", **_kw) -> str:
    return "q"


def _noop(*_a, **_k) -> None:
    pass


def _colorize(t: str) -> str:
    return t


def _font_menu(fig: Any, artists: list) -> None:
    def _apply_family(_family: str) -> None:
        pass

    def _apply_size(_size: float) -> None:
        pass

    run_font_menu(
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
        get_current_family=lambda: plt.rcParams.get("font.sans-serif", [""])[0],
        get_current_size=lambda: plt.rcParams.get("font.size"),
        apply_family=_apply_family,
        apply_size=_apply_size,
        get_current_weight=lambda: get_fig_font_weight(fig),
        apply_weight=lambda w: apply_fig_font_weight(fig, artists, w),
        get_current_highlight=lambda: get_fig_text_highlight(fig),
        get_highlight_style=lambda: get_fig_text_highlight_style(fig),
        apply_highlight_toggle=lambda: apply_fig_text_highlight(
            fig, artists, not get_fig_text_highlight(fig)
        ),
        apply_highlight_facecolor=lambda fc: apply_fig_text_highlight(
            fig, artists, get_fig_text_highlight(fig), fc=fc
        ),
        apply_highlight_alpha=lambda a: apply_fig_text_highlight(
            fig, artists, get_fig_text_highlight(fig), alpha=a
        ),
        apply_highlight_pad=lambda p: apply_fig_text_highlight(
            fig, artists, get_fig_text_highlight(fig), pad=p
        ),
    )


def smoke_xy_loaded(_path: str, fig: Any, ax: Any, menu_kwargs: dict) -> None:
    """Exercise XY submenu runners that previously broke on minimal Args after pkl reload."""
    kw = normalize_xy_menu_kwargs(menu_kwargs)
    args = kw["args"]
    labels = kw["labels"]
    y_data_list = kw["y_data_list"]
    label_text_objects = kw["label_text_objects"]
    x_data_list = kw["x_data_list"]
    orig_y = kw["orig_y"]
    offsets_list = kw.get("offsets_list") or [0.0] * len(labels)
    x_full_list = kw.get("x_full_list") or x_data_list
    raw_y_full_list = kw.get("raw_y_full_list") or orig_y
    cif_globals = kw.get("cif_globals") or {}
    bp = type("CIFState", (), cif_globals)() if cif_globals else None
    args_files = getattr(args, "files", [])

    def _line(i: int):
        return ax.lines[i] if i < len(ax.lines) else None

    def _lines_by_curve():
        return list(ax.lines)

    def _nlines() -> int:
        return len(ax.lines)

    tick_state = getattr(ax, "_saved_tick_state", {}) or {}

    run_xy_color_menu(
        ax=ax,
        fig=fig,
        labels=labels,
        y_data_list=y_data_list,
        label_text_objects=label_text_objects,
        stack=args.stack,
        args_files=args_files,
        line_getter=_line,
        bp=bp,
        get_cif_series=lambda: getattr(bp, "cif_tick_series", None) if bp else None,
        sync_fig_cif_tick_series=_noop,
        position_top_xlabel=_noop,
        position_right_ylabel=_noop,
        push_state=_noop,
        safe_input=_q_input,
        colorize_prompt=_colorize,
        tick_state=tick_state,
    )

    run_xy_rename_menu(
        ax=ax,
        fig=fig,
        labels=list(labels),
        label_text_objects=label_text_objects,
        args_files=args_files,
        get_cif_series=lambda: getattr(bp, "cif_tick_series", None) if bp else None,
        print_cif_phase_list=_noop,
        apply_cif_phase_label_rename=_noop,
        position_top_xlabel=_noop,
        position_bottom_xlabel=_noop,
        position_right_ylabel=_noop,
        position_left_ylabel=_noop,
        sync_fonts=_noop,
        push_state=_noop,
        safe_input=_q_input,
    )

    run_line_style_menu(
        ax=ax,
        fig=fig,
        lines_by_curve=_lines_by_curve(),
        line_getter=_line,
        line_count=_nlines,
        push_state=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    run_derivative_menu(
        args=args,
        ax=ax,
        fig=fig,
        label_text_objects=label_text_objects,
        x_data_list=x_data_list,
        y_data_list=y_data_list,
        offsets_list=list(offsets_list),
        push_state=_noop,
        _safe_input=_q_input,
        _apply_data_changes=_noop,
        _ensure_pre_derivative_data=_noop,
        _reset_from_derivative=_noop,
        _update_full_processed_data=_noop,
        _update_ylabel_for_derivative=_noop,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    run_x_range_menu(
        args=args,
        ax=ax,
        fig=fig,
        labels=labels,
        label_text_objects=label_text_objects,
        x_data_list=x_data_list,
        y_data_list=y_data_list,
        orig_y=orig_y,
        offsets_list=list(offsets_list),
        x_full_list=x_full_list,
        raw_y_full_list=raw_y_full_list,
        push_state=_noop,
        _safe_input=_q_input,
        _line=_line,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    if not args.stack:
        run_y_range_menu(
            args=args,
            ax=ax,
            fig=fig,
            label_text_objects=label_text_objects,
            y_data_list=y_data_list,
            push_state=_noop,
            _safe_input=_q_input,
            colorize_menu=_colorize,
            colorize_prompt=_colorize,
        )

    artists = (
        [ax.xaxis.label, ax.yaxis.label]
        + list(ax.get_xticklabels())
        + list(ax.get_yticklabels())
    )
    _font_menu(fig, artists)


def smoke_ec_loaded(fig: Any, ax: Any, res: tuple) -> None:
    from ..electrochem.line_style import run_ec_line_style_menu
    from ..electrochem.spine_colors import run_ec_spine_color_menu
    from ..electrochem.labels import run_ec_rename_menu
    from ..common.fonts import collect_fig_font_artists

    if len(res) == 4 and res[2] is None:
        _, _, _, file_data = res
        cycle_lines = file_data[0]["cycle_lines"] if file_data else {}
        is_multi = len(file_data) > 1
    else:
        cycle_lines = res[2] or {}
        file_data = [{"cycle_lines": cycle_lines, "visible": True, "filename": "Data"}]
        is_multi = False

    tick_state = getattr(ax, "_saved_tick_state", {}) or {}
    artists = collect_fig_font_artists(ax, fig, include_title=True, include_axes_texts=True)
    _font_menu(fig, artists)

    run_ec_line_style_menu(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=file_data,
        current_file_idx=0,
        is_multi_file=is_multi,
        is_dqdv=bool(getattr(fig, "_is_dqdv", False)),
        print_file_list=_noop,
        iter_cycle_lines=lambda cl, **_k: cl.items() if isinstance(cl, dict) else [],
        rebuild_legend=_noop,
        apply_stored_smooth_settings=_noop,
        push_state=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    run_ec_spine_color_menu(
        fig=fig,
        ax=ax,
        tick_state=tick_state,
        apply_spine_color=_noop,
        push_state=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    run_ec_rename_menu(
        fig=fig,
        ax=ax,
        file_data=file_data,
        tick_state=tick_state,
        push_state=_noop,
        rebuild_legend=_noop,
        print_file_list=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
        ui_position_top_xlabel=_noop,
        ui_position_bottom_xlabel=_noop,
        ui_position_left_ylabel=_noop,
        ui_position_right_ylabel=_noop,
    )


def smoke_cpc_loaded(fig: Any, ax: Any, ax2: Any, file_data: list, sc_charge: Any, sc_eff: Any) -> None:
    from ..cpc.colors import run_cpc_color_menu
    from ..common.fonts import collect_fig_font_artists

    is_multi = len(file_data) > 1
    artists = collect_fig_font_artists(ax, fig, include_title=True, extra_axes=[ax2])
    _font_menu(fig, artists)

    run_cpc_color_menu(
        fig=fig,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        is_multi_file=is_multi,
        sc_charge=sc_charge,
        sc_eff=sc_eff,
        push_state=_noop,
        set_spine_color=_noop,
        rebuild_legend=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )


def smoke_operando_loaded(fig: Any, ax: Any, im: Any, cbar: Any, ec_ax: Any) -> None:
    from ..operando.colors import run_operando_colormap_menu
    from ..operando.visibility import run_visibility_menu
    from ..common.fonts import collect_operando_font_artists

    artists = collect_operando_font_artists(fig, ax, ec_ax, cbar)

    _font_menu(fig, artists)

    run_operando_colormap_menu(
        fig=fig,
        im=im,
        cbar=cbar,
        snapshot=_noop,
        update_custom_colorbar=_noop,
        safe_input=_q_input,
        colorize_inline_commands=_colorize,
    )

    run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        snapshot=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
        colorize_inline_commands=_colorize,
    )


def smoke_histo_loaded(fig: Any, ax: Any, state: Any) -> None:
    from ..histo.colors import run_histo_color_menu
    from ..histo.fonts import run_histo_font_menu
    from ..histo.labels import run_histo_rename_menu
    from ..histo.line_style import run_histo_line_style_menu
    from ..histo.y_range import run_histo_y_range_menu

    run_histo_font_menu(
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    run_histo_color_menu(
        fig=fig,
        ax=ax,
        get_bar_color=lambda: state.style.bar_color,
        set_bar_color=_noop,
        get_edge_color=lambda: state.style.edge_color,
        set_edge_color=_noop,
        push_state=_noop,
        refresh=_noop,
        safe_input=_q_input,
        colorize_prompt=_colorize,
    )

    run_histo_line_style_menu(
        fig=fig,
        ax=ax,
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )

    run_histo_rename_menu(
        fig=fig,
        ax=ax,
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_q_input,
        colorize_prompt=_colorize,
    )

    run_histo_y_range_menu(
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_q_input,
        colorize_menu=_colorize,
        colorize_prompt=_colorize,
    )


def _classify(sess: dict) -> str:
    kind = sess.get("kind")
    if kind == "ec_gc":
        return "ec"
    if kind == "operando_ec":
        return "operando"
    if kind == "cpc":
        return "cpc"
    if kind == "histo":
        return "histo"
    if kind == "dqdv_2d_contour":
        return "dqdv_2d"
    if kind in (None, "xy") and "x_data" in sess:
        return "xy"
    return f"other:{kind}"


def smoke_session_path(path: str) -> None:
    """Load one session pkl and exercise key submenu entry points (q-only)."""
    from ...session import load_cpc_session, load_ec_session, load_operando_session, load_xy_session
    from ..histo.session import load_histo_session
    from ..electrochem.dqdv_2d import restore_dqdv_2d_companion_figure

    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    kind = _classify(sess)

    if kind == "xy":
        res = load_xy_session(path)
        if res is None:
            raise RuntimeError("load_xy_session returned None")
        fig, ax, menu_kwargs = res
        try:
            smoke_xy_loaded(path, fig, ax, menu_kwargs)
        finally:
            plt.close(fig)
    elif kind == "ec":
        res = load_ec_session(path)
        if res is None:
            raise RuntimeError("load_ec_session returned None")
        fig, ax = res[0], res[1]
        try:
            smoke_ec_loaded(fig, ax, res)
        finally:
            plt.close(fig)
    elif kind == "cpc":
        res = load_cpc_session(path)
        if res is None:
            raise RuntimeError("load_cpc_session returned None")
        fig, ax, ax2, sc_charge, _sc_discharge, sc_eff, file_data = res
        try:
            smoke_cpc_loaded(fig, ax, ax2, file_data, sc_charge, sc_eff)
        finally:
            plt.close(fig)
    elif kind == "operando":
        res = load_operando_session(path)
        if res is None:
            raise RuntimeError("load_operando_session returned None")
        fig, ax, im, cbar, ec_ax = res
        try:
            smoke_operando_loaded(fig, ax, im, cbar, ec_ax)
        finally:
            plt.close(fig)
    elif kind == "histo":
        res = load_histo_session(path)
        if res is None:
            raise RuntimeError("load_histo_session returned None")
        fig, ax, state = res
        try:
            smoke_histo_loaded(fig, ax, state)
        finally:
            plt.close(fig)
    elif kind == "dqdv_2d":
        res = restore_dqdv_2d_companion_figure(sess)
        if res is None:
            raise RuntimeError("restore_dqdv_2d_companion_figure returned None")
        fig = res[0]
        try:
            plt.close(fig)
        finally:
            pass
    else:
        raise RuntimeError(f"unsupported session kind: {kind}")


def audit_pkl_directory(root: str, *, recursive: bool = True) -> list[tuple[str, str]]:
    """Return list of (basename, error) for pkls that fail key smoke."""
    paths: list[str] = []
    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower().endswith(".pkl"):
                    paths.append(os.path.join(dirpath, name))
    else:
        paths = [
            os.path.join(root, name)
            for name in os.listdir(root)
            if name.lower().endswith(".pkl") and os.path.isfile(os.path.join(root, name))
        ]
    paths.sort()
    failures: list[tuple[str, str]] = []
    for path in paths:
        try:
            smoke_session_path(path)
        except Exception as exc:
            failures.append((os.path.basename(path), f"{type(exc).__name__}: {exc}"))
    return failures


__all__ = [
    "audit_pkl_directory",
    "smoke_cpc_loaded",
    "smoke_ec_loaded",
    "smoke_histo_loaded",
    "smoke_operando_loaded",
    "smoke_session_path",
    "smoke_xy_loaded",
]
