"""Operando and EC side-panel rename menu helpers."""

from __future__ import annotations

from ...ui import position_right_ylabel as _ui_position_right_ylabel
from ...ui import position_top_xlabel as _ui_position_top_xlabel
from ...utils import (
    convert_label_shortcuts,
    normalize_label_text,
    print_label_latex_tips,
    print_recent_axis_names,
    remember_axis_name,
)
from ..common.spines import keep_yaxis_label_on_side


def run_operando_rename_menu(
    *,
    fig,
    ax,
    snapshot,
    safe_input,
    colorize_menu,
    colorize_prompt,
) -> None:
    """Run the operando-axis rename submenu."""
    try:
        if not hasattr(ax, "_custom_labels"):
            ax._custom_labels = {"x": None, "y": None}
        print("Rename Operando Axes:")
        print("  " + colorize_menu("x: x-axis"))
        print("  " + colorize_menu("y: y-axis"))
        print("  " + colorize_menu("s: show recent axis names"))
        print("  " + colorize_menu("q: back"))
        print_label_latex_tips()
        while True:
            sub = safe_input(colorize_prompt("Rename operando axes (x/y/s/q): ")).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "s":
                print_recent_axis_names()
                continue
            if sub == "x":
                _rename_operando_x(fig=fig, ax=ax, snapshot=snapshot, safe_input=safe_input)
            elif sub == "y":
                _rename_operando_y(fig=fig, ax=ax, snapshot=snapshot, safe_input=safe_input)
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
    except Exception as exc:
        print(f"Rename failed: {exc}")


def run_operando_ec_rename_menu(
    *,
    fig,
    ec_ax,
    snapshot,
    safe_input,
    colorize_menu,
    colorize_prompt,
) -> None:
    """Run the EC side-panel rename submenu."""
    if ec_ax is None:
        print("EC panel not available (no .mpt file in folder).")
        return
    try:
        if not hasattr(ec_ax, "_custom_labels"):
            ec_ax._custom_labels = {"x": None, "y_time": None, "y_ions": None}
        print("Rename EC Axes:")
        print("  " + colorize_menu("x: x-axis"))
        print("  " + colorize_menu("y: y-axis (mode-aware)"))
        print("  " + colorize_menu("s: show recent axis names"))
        print("  " + colorize_menu("q: back"))
        print_label_latex_tips()
        while True:
            sub = safe_input(colorize_prompt("Rename EC axes (x/y/s/q): ")).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "s":
                print_recent_axis_names()
                continue
            if sub == "x":
                _rename_ec_x(fig=fig, ec_ax=ec_ax, snapshot=snapshot, safe_input=safe_input)
            elif sub == "y":
                _rename_ec_y(fig=fig, ec_ax=ec_ax, snapshot=snapshot, safe_input=safe_input)
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
    except Exception as exc:
        print(f"Rename failed: {exc}")


def _rename_operando_x(*, fig, ax, snapshot, safe_input) -> None:
    current = ax.get_xlabel() or ""
    label = safe_input(f"New operando X label (blank=cancel, current='{current}'): ")
    if not label:
        return
    label = normalize_label_text(convert_label_shortcuts(label))
    remember_axis_name(label)
    snapshot("rename-op-x")
    try:
        ax.set_xlabel(label)
        ax._custom_labels["x"] = label
        _ui_position_top_xlabel(ax, fig, getattr(ax, "_saved_tick_state", {}))
    except Exception:
        pass


def _rename_operando_y(*, fig, ax, snapshot, safe_input) -> None:
    current = ax.get_ylabel() or ""
    label = safe_input(f"New operando Y label (blank=cancel, current='{current}'): ")
    if not label:
        return
    label = normalize_label_text(convert_label_shortcuts(label))
    remember_axis_name(label)
    snapshot("rename-op-y")
    try:
        ax.set_ylabel(label)
        ax._custom_labels["y"] = label
        _ui_position_left_ylabel(ax, fig, getattr(ax, "_saved_tick_state", {}))
    except Exception:
        pass


def _rename_ec_x(*, fig, ec_ax, snapshot, safe_input) -> None:
    current = ec_ax.get_xlabel() or ""
    label = safe_input(f"New EC X label (blank=cancel, current='{current}'): ")
    if not label:
        return
    label = normalize_label_text(convert_label_shortcuts(label))
    remember_axis_name(label)
    snapshot("rename-ec-x")
    try:
        ec_ax.set_xlabel(label)
        ec_ax._custom_labels["x"] = label
        _ui_position_top_xlabel(ec_ax, fig, getattr(ec_ax, "_saved_tick_state", {}))
    except Exception:
        pass


def _rename_ec_y(*, fig, ec_ax, snapshot, safe_input) -> None:
    current = ec_ax.get_ylabel() or ""
    label = safe_input(f"New EC Y label (blank=cancel, current='{current}'): ")
    if not label:
        return
    label = normalize_label_text(convert_label_shortcuts(label))
    remember_axis_name(label)
    snapshot("rename-ec-y")
    try:
        ec_ax.set_ylabel(label)
        mode = getattr(ec_ax, "_ec_y_mode", "time")
        if mode == "ions":
            ec_ax._custom_labels["y_ions"] = label
        else:
            ec_ax._custom_labels["y_time"] = label
        keep_yaxis_label_on_side(ec_ax, "right", visible=True)
        if hasattr(ec_ax, "_right_ylabel_artist") and ec_ax._right_ylabel_artist is not None:
            ec_ax._right_ylabel_artist.set_visible(False)
    except Exception:
        pass


__all__ = [
    "run_operando_ec_rename_menu",
    "run_operando_rename_menu",
]
