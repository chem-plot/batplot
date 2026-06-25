"""Rename submenu (``r``) for the XY interactive menu.

Covers curve labels, CIF phase labels, and x/y axis labels. Mutations are
guarded by the injected ``push_state`` so undo is unchanged; CIF-specific
callbacks and axis-title positioners are injected by the dispatcher because
they close over module/global plot state.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

from ...utils import (
    convert_label_shortcuts,
    normalize_label_text,
    print_label_latex_tips,
    print_recent_axis_names,
    remember_axis_name,
)
from ..common.sources import cif_present


def run_xy_rename_menu(
    *,
    ax: Any,
    fig: Any,
    labels: List[str],
    label_text_objects: Sequence[Any],
    args_files: Sequence[str],
    get_cif_series: Callable[[], Any],
    print_cif_phase_list: Callable[[Any], Any],
    apply_cif_phase_label_rename: Callable[[int, str], Any],
    position_top_xlabel: Callable[[], Any],
    position_bottom_xlabel: Callable[[], Any],
    position_right_ylabel: Callable[[], Any],
    position_left_ylabel: Callable[[], Any],
    sync_fonts: Callable[[], Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
) -> None:
    """Run the rename submenu (curve / CIF phase / axis labels)."""
    try:
        has_cif = cif_present(args_files, get_cif_series)
        while True:
            rename_opts = "c=curve"
            if has_cif:
                rename_opts += ", t=CIF phase label (same as cif→r)"
            rename_opts += ", x=x-axis, y=y-axis, s=show recent, q=return"
            mode = safe_input(f"Rename ({rename_opts}): ").strip().lower()
            if mode == 'q':
                break
            if mode == '':
                continue
            if mode == 's':
                print_recent_axis_names()
                continue
            if mode == 'c':
                print_label_latex_tips()
                idx_in = safe_input("Curve number to rename (q=cancel): ").strip()
                if not idx_in or idx_in.lower() == 'q':
                    print("Canceled.")
                    continue
                try:
                    idx = int(idx_in) - 1
                except ValueError:
                    print("Invalid index.")
                    continue
                if not (0 <= idx < len(labels)):
                    print("Invalid index.")
                    continue
                new_label = safe_input("New curve label (q=cancel): ")
                if not new_label or new_label.lower() == 'q':
                    print("Canceled.")
                    continue
                new_label = convert_label_shortcuts(new_label)
                push_state("rename-curve")
                labels[idx] = new_label
                label_text_objects[idx].set_text(f"{idx+1}: {new_label}")
                fig.canvas.draw()
            elif mode == 't':
                cts = get_cif_series()
                if not cts:
                    print("No CIF phases to rename.")
                    continue
                print("CIF phases (then pick one; same list as cif→r)")
                print_cif_phase_list(cts)
                s = safe_input(
                    "Phase number to rename (q=cancel): "
                ).strip()
                if not s or s.lower() == 'q':
                    print("Canceled.")
                    continue
                try:
                    idx = int(s) - 1
                    if not (0 <= idx < len(cts)):
                        print("Index out of range.")
                        continue
                except ValueError:
                    print("Bad index.")
                    continue
                print_label_latex_tips()
                new_name = safe_input(
                    "New CIF phase label (q=cancel): "
                ).strip()
                if not new_name or new_name.lower() == 'q':
                    print("Canceled.")
                    continue
                new_name = convert_label_shortcuts(new_name)
                apply_cif_phase_label_rename(idx, new_name)
                print(f"Phase {idx + 1} label updated.")
            elif mode in ('x','y'):
                print("Enter new axis label (q=cancel).")
                print_label_latex_tips()
                new_axis = safe_input("New axis label: ")
                if not new_axis or new_axis.lower() == 'q':
                    print("Canceled.")
                    continue
                new_axis = convert_label_shortcuts(new_axis)
                new_axis = normalize_label_text(new_axis)
                remember_axis_name(new_axis)
                push_state("rename-axis")
                # Freeze layout and preserve current pad via one-shot pending to avoid drift
                try:
                    fig.set_layout_engine('none')
                except Exception:
                    try:
                        fig.set_tight_layout(False)
                    except Exception:
                        pass
                try:
                    fig.set_constrained_layout(False)
                except Exception:
                    pass
                if mode == 'x':
                    # Preserve current pad exactly once after rename
                    try:
                        ax._pending_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
                    except Exception:
                        pass
                    ax.xaxis.label.set_text(new_axis)
                    position_top_xlabel()
                    position_bottom_xlabel()
                else:
                    try:
                        ax._pending_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
                    except Exception:
                        pass
                    ax.yaxis.label.set_text(new_axis)
                    position_right_ylabel()
                    position_left_ylabel()
                sync_fonts()
                fig.canvas.draw()
            else:
                print("Invalid choice.")
            # loop continues until q
    except Exception as e:
        print(f"Error: {e}")


__all__ = ["run_xy_rename_menu"]
