"""Rename submenu (``r``) for the XY interactive menu.

Covers curve labels, CIF phase labels, and x/y axis labels. Mutations are
guarded by the injected ``push_state`` so undo is unchanged; CIF-specific
callbacks and axis-title positioners are injected by the dispatcher because
they close over module/global plot state.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

from ...utils import (
    finalize_axis_label_text,
    print_label_math_help,
    print_recent_axis_names,
    remember_axis_name,
    resolve_recent_axis_name,
)
from ..common.sources import cif_present

_RECENT_MODE = "xy"


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
            rename_opts += ", x=x-axis, y=y-axis, s=show recent, m=math help, q=return"
            mode = safe_input(f"Rename ({rename_opts}): ").strip().lower()
            if mode == 'q':
                break
            if mode == '':
                continue
            if mode == 's':
                print_recent_axis_names(mode=_RECENT_MODE)
                continue
            if mode == 'm':
                print_label_math_help()
                continue
            if mode == 'c':
                while True:
                    idx_in = safe_input("Curve number to rename (q=back): ").strip()
                    if not idx_in or idx_in.lower() == 'q':
                        break
                    try:
                        idx = int(idx_in) - 1
                    except ValueError:
                        print("Invalid index.")
                        continue
                    if not (0 <= idx < len(labels)):
                        print("Invalid index.")
                        continue
                    if idx >= len(label_text_objects):
                        print("Invalid index (label artist missing).")
                        continue
                    new_label = safe_input(f"New curve label [{labels[idx]}] (m=math help, q=back): ")
                    if not new_label or new_label.lower() == 'q':
                        continue
                    if new_label.strip().lower() == 'm':
                        print_label_math_help()
                        continue
                    new_label = finalize_axis_label_text(new_label)
                    push_state("rename-curve")
                    labels[idx] = new_label
                    label_text_objects[idx].set_text(f"{idx+1}: {new_label}")
                    fig.canvas.draw()
                    print(f"Curve {idx + 1} label updated.")
            elif mode == 't':
                cts = get_cif_series()
                if not cts:
                    print("No CIF phases to rename.")
                    continue
                print("CIF phases (then pick one; same list as cif→r)")
                print_cif_phase_list(cts)
                while True:
                    s = safe_input("Phase number to rename (q=back): ").strip()
                    if not s or s.lower() == 'q':
                        break
                    try:
                        idx = int(s) - 1
                        if not (0 <= idx < len(cts)):
                            print("Index out of range.")
                            continue
                    except ValueError:
                        print("Bad index.")
                        continue
                    while True:
                        new_name = safe_input("New CIF phase label (m=math help, q=back): ").strip()
                        if not new_name or new_name.lower() == 'q':
                            break
                        if new_name.lower() == 'm':
                            print_label_math_help()
                            continue
                        new_name = finalize_axis_label_text(new_name)
                        apply_cif_phase_label_rename(idx, new_name)
                        print(f"Phase {idx + 1} label updated.")
            elif mode in ('x','y'):
                print("Enter new axis label (q=back; number = recent name, s=list, m=math help; use \"quotes\" for a literal number).")
                while True:
                    from ..common.axis_state import primary_axis_label_text

                    current = primary_axis_label_text(ax, mode)
                    new_axis = safe_input(f"New axis label [{current}] (number=recent, s=list, m=math help, q=back): ")
                    if not new_axis or new_axis.lower() == 'q':
                        break
                    if new_axis.strip().lower() == 's':
                        print_recent_axis_names(mode=_RECENT_MODE)
                        continue
                    if new_axis.strip().lower() == 'm':
                        print_label_math_help()
                        continue
                    new_axis = resolve_recent_axis_name(new_axis, mode=_RECENT_MODE)
                    new_axis = finalize_axis_label_text(new_axis)
                    remember_axis_name(new_axis, mode=_RECENT_MODE)
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
                        try:
                            ax._stored_xlabel = new_axis
                        except Exception:
                            pass
                        # Clear sticky top override so duplicate top title follows rename
                        try:
                            if hasattr(ax, '_top_xlabel_text_override'):
                                delattr(ax, '_top_xlabel_text_override')
                        except Exception:
                            pass
                        position_top_xlabel()
                        position_bottom_xlabel()
                    else:
                        try:
                            ax._pending_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
                        except Exception:
                            pass
                        ax.yaxis.label.set_text(new_axis)
                        try:
                            ax._stored_ylabel = new_axis
                        except Exception:
                            pass
                        # Clear sticky right override (mirror x/top clear above).
                        try:
                            if hasattr(ax, "_right_ylabel_text_override"):
                                delattr(ax, "_right_ylabel_text_override")
                        except Exception:
                            pass
                        # Dual-Y twin must get the same rename.
                        ax2 = getattr(fig, "_xy_ax2", None)
                        if ax2 is not None:
                            try:
                                ax2.set_ylabel(new_axis)
                                ax2._stored_ylabel = new_axis
                            except Exception:
                                pass
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
