"""Rename/file-label menu helpers for EC interactive mode."""

from __future__ import annotations

from typing import Any, Callable

from ...utils import (
    finalize_axis_label_text,
    print_label_math_help,
    print_recent_axis_names,
    remember_axis_name,
    resolve_recent_axis_name,
)

_RECENT_MODE = "ec"


def run_ec_rename_menu(
    *,
    fig: Any,
    ax: Any,
    file_data: list[dict] | None,
    tick_state: dict,
    push_state: Callable[[str], Any],
    rebuild_legend: Callable[[Any], Any],
    print_file_list: Callable[..., Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    ui_position_top_xlabel: Callable[..., Any],
    ui_position_bottom_xlabel: Callable[..., Any],
    ui_position_left_ylabel: Callable[..., Any],
    ui_position_right_ylabel: Callable[..., Any],
) -> str | None:
    """Run the EC rename submenu and return a new base y-label when changed."""
    updated_base_ylabel = None
    try:
        is_dual_xaxis = getattr(fig, "_xaxis_mode", "capacity") == "dual"
        secax = getattr(fig, "_xaxis_secondary", None) if is_dual_xaxis else None
        while True:
            print("Rename:")
            print("  " + colorize_menu("x: x-axis (bottom)"))
            if is_dual_xaxis and secax is not None:
                print("  " + colorize_menu("tx: x-axis (top)"))
            print("  " + colorize_menu("y: y-axis"))
            if file_data:
                print("  " + colorize_menu("f: file names (legend)"))
            print("  " + colorize_menu("s: show recent axis names (type a number at a label prompt to reuse one)"))
            print("  " + colorize_menu("m: math / science typing help ({sub()}, {super()}, Greek, …)"))
            print("  " + colorize_menu("q: back"))
            opts = "x/y" + ("/tx" if (is_dual_xaxis and secax) else "") + ("/f" if file_data else "") + "/s/m/q"
            sub = safe_input(colorize_prompt(f"Rename ({opts}): ")).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "s":
                print_recent_axis_names(mode=_RECENT_MODE)
                continue
            if sub == "m":
                print_label_math_help(colorize=colorize_menu)
                continue
            if sub == "f" and file_data:
                _run_file_rename(
                    fig=fig,
                    ax=ax,
                    file_data=file_data,
                    push_state=push_state,
                    rebuild_legend=rebuild_legend,
                    print_file_list=print_file_list,
                    safe_input=safe_input,
                )
                continue
            if sub == "x":
                _rename_bottom_x(
                    fig=fig,
                    ax=ax,
                    tick_state=tick_state,
                    push_state=push_state,
                    safe_input=safe_input,
                    ui_position_top_xlabel=ui_position_top_xlabel,
                    ui_position_bottom_xlabel=ui_position_bottom_xlabel,
                )
            if sub == "tx":
                _rename_top_x(fig=fig, secax=secax, is_dual_xaxis=is_dual_xaxis, push_state=push_state, safe_input=safe_input)
            if sub == "y":
                updated_base_ylabel = _rename_y(
                    fig=fig,
                    ax=ax,
                    tick_state=tick_state,
                    push_state=push_state,
                    safe_input=safe_input,
                    ui_position_left_ylabel=ui_position_left_ylabel,
                    ui_position_right_ylabel=ui_position_right_ylabel,
                ) or updated_base_ylabel
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
    except Exception as exc:
        print(f"Error renaming axes: {exc}")
    return updated_base_ylabel


def apply_file_display_name(file_entry: dict, new_name: str) -> None:
    """Apply one display name to all legend labels for a file."""
    file_entry["display_name"] = new_name
    cycle_lines = file_entry.get("cycle_lines") or {}
    for cycle in sorted(cycle_lines.keys(), key=lambda x: (x if isinstance(x, (int, float)) else 0)):
        parts = cycle_lines[cycle]
        if isinstance(parts, dict):
            charge = parts.get("charge")
            discharge = parts.get("discharge")
            if charge is not None:
                charge.set_label(f"{new_name}: {cycle}")
            if discharge is not None:
                discharge.set_label("_nolegend_" if charge is not None else f"{new_name}: {cycle}")
        elif hasattr(parts, "set_label"):
            parts.set_label(f"{new_name}: {cycle}")


def _run_file_rename(*, fig, ax, file_data, push_state, rebuild_legend, print_file_list, safe_input) -> None:
    while True:
        print_file_list(file_data)
        choice = safe_input(f"File to rename (1-{len(file_data)}), q=back: ").strip()
        if choice.lower() == "q":
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(file_data):
                file_entry = file_data[idx]
                current = file_entry.get("display_name", file_entry.get("filename", str(idx + 1)))
                while True:
                    new_name = safe_input(
                        f"New name for this file (current: {current!r}, m=math help, q=back): "
                    ).strip()
                    if not new_name or new_name.lower() == "q":
                        break
                    if new_name.lower() == "m":
                        print_label_math_help()
                        continue
                    new_name = finalize_axis_label_text(new_name)
                    push_state("rename-file")
                    apply_file_display_name(file_entry, new_name)
                    rebuild_legend(ax)
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                    print(f"File {idx + 1} display name set to {new_name!r}.")
                    current = new_name
            else:
                print("Invalid file number.")
        except ValueError:
            print("Invalid input.")


def _rename_bottom_x(*, fig, ax, tick_state, push_state, safe_input, ui_position_top_xlabel, ui_position_bottom_xlabel) -> None:
    from ..common.axis_state import primary_axis_label_text

    while True:
        current = primary_axis_label_text(ax, "x")
        text = safe_input(f"New X-axis label [{current}] (number=recent, s=list, m=math help, q=back): ")
        if not text or text.lower() == "q":
            break
        if text.strip().lower() == "s":
            print_recent_axis_names(mode=_RECENT_MODE)
            continue
        if text.strip().lower() == "m":
            print_label_math_help()
            continue
        text = resolve_recent_axis_name(text, mode=_RECENT_MODE)
        text = finalize_axis_label_text(text)
        remember_axis_name(text, mode=_RECENT_MODE)
        push_state("rename-x")
        try:
            _freeze_layout(fig)
            try:
                ax._pending_xlabelpad = getattr(ax.xaxis, "labelpad", None)
            except Exception:
                pass
            ax.set_xlabel(text)
            ax._stored_xlabel = text
            ax._stored_xlabel_color = ax.xaxis.label.get_color()
            # Dual: top title is SecondaryAxis — never create capacity duplicate
            if getattr(fig, "_xaxis_mode", "capacity") == "dual":
                try:
                    from .style import reseal_ec_chrome

                    reseal_ec_chrome(fig, ax, tick_state=tick_state)
                except Exception:
                    pass
            else:
                ui_position_top_xlabel(ax, fig, tick_state)
            ui_position_bottom_xlabel(ax, fig, tick_state)
            print(f"X-axis label updated to: '{text}'")
        except Exception:
            pass


def _rename_top_x(*, fig, secax, is_dual_xaxis: bool, push_state, safe_input) -> None:
    if not (is_dual_xaxis and secax is not None):
        print("Top x-axis is only available in dual mode. Use 'a' menu → 'd' to enable.")
        return
    while True:
        current = secax.get_xlabel()
        text = safe_input(f"New top X-axis label [{current}] (number=recent, s=list, m=math help, q=back): ")
        if not text or text.lower() == "q":
            break
        if text.strip().lower() == "s":
            print_recent_axis_names(mode=_RECENT_MODE)
            continue
        if text.strip().lower() == "m":
            print_label_math_help()
            continue
        text = resolve_recent_axis_name(text, mode=_RECENT_MODE)
        text = finalize_axis_label_text(text)
        remember_axis_name(text, mode=_RECENT_MODE)
        push_state("rename-tx")
        try:
            # Preserve spine/title color across rename (set_xlabel can reset it).
            keep_c = (
                getattr(secax, "_stored_top_xlabel_color", None)
                or (getattr(secax, "_bp_spine_side_colors", None) or {}).get("top")
                or getattr(getattr(secax, "_parent", None), "_stored_top_xlabel_color", None)
                or (getattr(fig, "_bp_spine_side_colors", None) or {}).get("top")
                or secax.xaxis.label.get_color()
            )
            secax.set_xlabel(text)
            secax._stored_xlabel = text
            try:
                secax._bp_top_title_color = keep_c if keep_c is not None else getattr(
                    secax, "_bp_top_title_color", None
                )
            except Exception:
                pass
            if keep_c is not None:
                try:
                    secax.xaxis.label.set_color(keep_c)
                    secax._stored_top_xlabel_color = keep_c
                except Exception:
                    pass
            try:
                parent = getattr(secax, "_parent", None) or getattr(fig, "axes", [None])[0]
                from .style import reseal_ec_chrome

                if parent is not None:
                    reseal_ec_chrome(fig, parent)
            except Exception:
                pass
            print(f"Top X-axis label updated to: '{text}'")
        except Exception as exc:
            print(f"Error setting top x-axis label: {exc}")


def _rename_y(*, fig, ax, tick_state, push_state, safe_input, ui_position_left_ylabel, ui_position_right_ylabel) -> str | None:
    from ..common.axis_state import primary_axis_label_text

    updated = None
    while True:
        current = primary_axis_label_text(ax, "y")
        text = safe_input(f"New Y-axis label [{current}] (number=recent, s=list, m=math help, q=back): ")
        if not text or text.lower() == "q":
            break
        if text.strip().lower() == "s":
            print_recent_axis_names(mode=_RECENT_MODE)
            continue
        if text.strip().lower() == "m":
            print_label_math_help()
            continue
        text = resolve_recent_axis_name(text, mode=_RECENT_MODE)
        text = finalize_axis_label_text(text)
        remember_axis_name(text, mode=_RECENT_MODE)
        push_state("rename-y")
        try:
            _freeze_layout(fig)
            try:
                ax._pending_ylabelpad = getattr(ax.yaxis, "labelpad", None)
            except Exception:
                pass
            ax.set_ylabel(text)
            ax._stored_ylabel = text
            ax._stored_ylabel_color = ax.yaxis.label.get_color()
            ui_position_right_ylabel(ax, fig, tick_state)
            ui_position_left_ylabel(ax, fig, tick_state)
            print(f"Y-axis label updated to: '{text}'")
            updated = text
        except Exception:
            pass
    return updated


def _freeze_layout(fig) -> None:
    layout_engine_handled = False
    try:
        fig.set_layout_engine("none")
        layout_engine_handled = True
    except Exception:
        try:
            fig.set_tight_layout(False)
        except Exception:
            pass
    if not layout_engine_handled:
        try:
            fig.set_constrained_layout(False)
        except Exception:
            pass


__all__ = ["apply_file_display_name", "run_ec_rename_menu"]
