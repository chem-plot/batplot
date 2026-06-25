"""Legend ordering menu helpers for multi-file EC plots."""

from __future__ import annotations

from typing import Any, Callable


def run_ec_legend_order_menu(
    *,
    fig: Any,
    ax: Any,
    file_data: list[dict],
    is_multi_file: bool,
    print_file_list: Callable[..., Any],
    rebuild_legend: Callable[[Any], Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
) -> None:
    """Run the multi-file legend-order submenu."""
    try:
        if not is_multi_file or not file_data:
            print("Legend rearrange (ra) is only available with multiple files.")
            return
        while True:
            print_file_list(file_data)
            print("Current legend order (top to bottom):")
            order = getattr(fig, "_ec_legend_file_order", None) or list(range(len(file_data)))
            for pos, idx in enumerate(order):
                if 0 <= idx < len(file_data):
                    file_entry = file_data[idx]
                    name = file_entry.get("display_name", file_entry.get("filename", str(idx + 1)))
                    visible = "visible" if file_entry.get("visible", True) else "hidden"
                    print(f"  {pos + 1}: [{visible}] {name}")
            new_order_str = safe_input("Enter new order (space-separated indices 1-N, q=back): ").strip()
            if not new_order_str or new_order_str.lower() == "q":
                break
            try:
                new_order = [int(item) - 1 for item in new_order_str.split()]
                if len(new_order) != len(file_data):
                    print(f"Error: Need exactly {len(file_data)} indices.")
                    continue
                if sorted(new_order) != list(range(len(file_data))):
                    print("Error: Indices must be a permutation of 1 to N.")
                    continue
                push_state("rearrange-legend")
                fig._ec_legend_file_order = new_order
                rebuild_legend(ax)
                fig.canvas.draw_idle()
                print("Legend order updated.")
            except ValueError:
                print("Invalid input. Use space-separated numbers (e.g., 3 1 2 4 5).")
    except Exception as exc:
        print(f"Error rearranging legend: {exc}")


__all__ = ["run_ec_legend_order_menu"]
