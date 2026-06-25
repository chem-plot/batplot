"""CPC label and rename menu helpers."""

from __future__ import annotations

import re

from ...utils import (
    convert_label_shortcuts,
    normalize_label_text,
    print_label_latex_tips,
    print_recent_axis_names,
    remember_axis_name,
)


def extract_cpc_file_base_name(file_info) -> str:
    """Extract the display filename from CPC legend labels."""
    base_name = file_info.get("filename", "Data")
    labels = _current_file_labels(file_info)
    for label in labels:
        if not label:
            continue
        bracket_match = re.search(r"^(.+?)\s*\([^)]+\)\s*$", label)
        if bracket_match:
            potential_base = bracket_match.group(1).strip()
            if potential_base:
                return potential_base
            continue
        for suffix in (" charge", " discharge", " efficiency"):
            if label.endswith(suffix):
                potential_base = label[: -len(suffix)].strip()
                if potential_base:
                    return potential_base
    return base_name


def build_cpc_file_labels(file_info, new_name: str) -> tuple[str, str, str]:
    """Build charge/discharge/efficiency labels while preserving role brackets."""
    charge_label, discharge_label, efficiency_label = _current_file_labels(file_info)
    charge_bracket = _extract_role_bracket(charge_label, "Chg")
    discharge_bracket = _extract_role_bracket(discharge_label, "DChg")
    efficiency_bracket = _extract_role_bracket(efficiency_label, "Eff")
    return (
        f"{new_name} ({charge_bracket})",
        f"{new_name} ({discharge_bracket})",
        f"{new_name} ({efficiency_bracket})",
    )


def apply_cpc_file_name(file_info, new_name: str) -> tuple[str, str, str]:
    """Apply a new CPC file display name and return updated legend labels."""
    sc_charge = file_info["sc_charge"]
    sc_discharge = file_info["sc_discharge"]
    sc_eff = file_info["sc_eff"]
    charge_label, discharge_label, efficiency_label = build_cpc_file_labels(file_info, new_name)
    sc_charge.set_label(charge_label)
    sc_discharge.set_label(discharge_label)
    sc_eff.set_label(efficiency_label)
    file_info["filename"] = new_name
    return charge_label, discharge_label, efficiency_label


def run_cpc_rename_menu(
    *,
    fig,
    ax,
    ax2,
    file_data,
    current_file_idx: int,
    is_multi_file: bool,
    push_state,
    rebuild_legend,
    print_file_list,
    safe_input,
    colorize_menu,
    colorize_prompt,
) -> None:
    """Run the CPC rename submenu."""
    print_label_latex_tips()
    while True:
        print("Rename:")
        print("  " + colorize_menu("x: x-axis"))
        print("  " + colorize_menu("ly: left y-axis"))
        print("  " + colorize_menu("ry: right y-axis"))
        print("  " + colorize_menu("f: file names (legend)"))
        print("  " + colorize_menu("s: show recent axis names"))
        print("  " + colorize_menu("q: back"))
        sub = safe_input(colorize_prompt("Rename (x/ly/ry/f/s/q): ")).strip().lower()
        if not sub:
            continue
        if sub == "q":
            break
        if sub == "s":
            print_recent_axis_names()
            continue
        if sub in ("l", "f"):
            _run_file_rename(
                fig=fig,
                ax=ax,
                ax2=ax2,
                file_data=file_data,
                current_file_idx=current_file_idx,
                is_multi_file=is_multi_file,
                push_state=push_state,
                rebuild_legend=rebuild_legend,
                print_file_list=print_file_list,
                safe_input=safe_input,
            )
            continue
        if sub == "x":
            _rename_x_axis(fig=fig, ax=ax, push_state=push_state, safe_input=safe_input)
            continue
        if sub == "ly":
            _rename_left_y_axis(fig=fig, ax=ax, push_state=push_state, safe_input=safe_input)
            continue
        if sub == "ry":
            _rename_right_y_axis(fig=fig, ax2=ax2, push_state=push_state, safe_input=safe_input)
            continue
        print("Unknown option.")


def _run_file_rename(
    *,
    fig,
    ax,
    ax2,
    file_data,
    current_file_idx: int,
    is_multi_file: bool,
    push_state,
    rebuild_legend,
    print_file_list,
    safe_input,
) -> None:
    if not is_multi_file:
        _rename_one_file(fig=fig, ax=ax, ax2=ax2, file_data=file_data, file_info=file_data[0], push_state=push_state, rebuild_legend=rebuild_legend, safe_input=safe_input)
        return
    while True:
        print("\nAvailable files:")
        print_file_list(file_data, current_file_idx)
        file_choice = safe_input(f"Select file number (1-{len(file_data)}) to rename (q=back): ").strip()
        if not file_choice or file_choice.lower() == "q":
            break
        try:
            file_idx = int(file_choice) - 1
        except (ValueError, KeyboardInterrupt):
            print("Invalid input.")
            continue
        if not (0 <= file_idx < len(file_data)):
            print("Invalid file number.")
            continue
        _rename_one_file(fig=fig, ax=ax, ax2=ax2, file_data=file_data, file_info=file_data[file_idx], push_state=push_state, rebuild_legend=rebuild_legend, safe_input=safe_input)


def _rename_one_file(*, fig, ax, ax2, file_data, file_info, push_state, rebuild_legend, safe_input) -> None:
    base_name = extract_cpc_file_base_name(file_info)
    print(f"Current file name in legend: '{base_name}'")
    new_name = safe_input("Enter new file name (q=cancel): ").strip()
    if not new_name or new_name.lower() == "q":
        return
    new_name = convert_label_shortcuts(new_name)
    try:
        push_state("rename-legend")
        labels = apply_cpc_file_name(file_info, new_name)
        rebuild_legend(ax, ax2, file_data, preserve_position=True)
        fig.canvas.draw_idle()
        print(f"Legend labels updated: '{labels[0]}', '{labels[1]}', '{labels[2]}'")
    except Exception as exc:
        print(f"Error: {exc}")


def _rename_x_axis(*, fig, ax, push_state, safe_input) -> None:
    current = ax.get_xlabel()
    print(f"Current x-axis title: '{current}'")
    new_title = safe_input("Enter new x-axis title (q=cancel): ")
    if not new_title or new_title.lower() == "q":
        return
    new_title = normalize_label_text(convert_label_shortcuts(new_title))
    remember_axis_name(new_title)
    try:
        push_state("rename-x")
        ax.set_xlabel(new_title)
        ax._stored_xlabel = new_title
        ax._stored_top_xlabel = new_title
        if hasattr(ax, "_top_xlabel_text") and ax._top_xlabel_text is not None and ax._top_xlabel_text.get_visible():
            ax._top_xlabel_text.set_text(new_title)
        fig.canvas.draw_idle()
        print(f"X-axis title updated to: '{new_title}'")
    except Exception as exc:
        print(f"Error: {exc}")


def _rename_left_y_axis(*, fig, ax, push_state, safe_input) -> None:
    current = ax.get_ylabel()
    print(f"Current left y-axis title: '{current}'")
    new_title = safe_input("Enter new left y-axis title (q=cancel): ")
    if not new_title or new_title.lower() == "q":
        return
    new_title = normalize_label_text(convert_label_shortcuts(new_title))
    remember_axis_name(new_title)
    try:
        push_state("rename-ly")
        ax.set_ylabel(new_title)
        ax._stored_ylabel = new_title
        fig.canvas.draw_idle()
        print(f"Left y-axis title updated to: '{new_title}'")
    except Exception as exc:
        print(f"Error: {exc}")


def _rename_right_y_axis(*, fig, ax2, push_state, safe_input) -> None:
    current = ax2.get_ylabel()
    print(f"Current right y-axis title: '{current}'")
    new_title = safe_input("Enter new right y-axis title (q=cancel): ")
    if not new_title or new_title.lower() == "q":
        return
    new_title = normalize_label_text(convert_label_shortcuts(new_title))
    remember_axis_name(new_title)
    try:
        push_state("rename-ry")
        ax2.set_ylabel(new_title)
        if not hasattr(ax2, "_stored_ylabel"):
            ax2._stored_ylabel = ""
        ax2._stored_ylabel = new_title
        fig.canvas.draw_idle()
        print(f"Right y-axis title updated to: '{new_title}'")
    except Exception as exc:
        print(f"Error: {exc}")


def _current_file_labels(file_info) -> tuple[str, str, str]:
    sc_charge = file_info["sc_charge"]
    sc_discharge = file_info["sc_discharge"]
    sc_eff = file_info["sc_eff"]
    return (
        sc_charge.get_label() or "",
        sc_discharge.get_label() or "",
        sc_eff.get_label() or "",
    )


def _extract_role_bracket(label: str, default: str) -> str:
    match = re.search(r"\(([^)]+)\)", label or "")
    if not match:
        return default
    bracket = match.group(1)
    if bracket.lower() == "dchg":
        return "DChg"
    return bracket or default


__all__ = [
    "apply_cpc_file_name",
    "build_cpc_file_labels",
    "extract_cpc_file_base_name",
    "run_cpc_rename_menu",
]
