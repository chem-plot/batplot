"""Legend ordering menu helpers for multi-file EC plots."""

from __future__ import annotations

from typing import Any, Callable, List, Sequence


def _legend_host_fig(fig: Any, ax: Any = None) -> Any:
    if ax is not None:
        try:
            host = ax.figure
            if host is not None:
                return host
        except Exception:
            pass
    return fig


def _file_label(file_entry: dict, fallback: str) -> str:
    return str(
        file_entry.get("display_name")
        or file_entry.get("filename")
        or fallback
    )


def set_ec_legend_file_order(
    fig: Any,
    file_data: Sequence[dict],
    order: Sequence[int],
    *,
    ax: Any = None,
) -> List[int]:
    host = _legend_host_fig(fig, ax)
    n = len(file_data)
    new_order = [int(i) for i in order]
    if len(new_order) != n or sorted(new_order) != list(range(n)):
        raise ValueError(f"Need a permutation of 0..{n - 1}")
    for target in (host, fig):
        if target is None:
            continue
        try:
            target._ec_legend_file_order = list(new_order)
        except Exception:
            pass
    return list(new_order)


def _force_draw(fig: Any) -> None:
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass
    try:
        fig.canvas.flush_events()
    except Exception:
        pass
    try:
        fig.canvas.draw()
    except Exception:
        pass


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
    restore_state: Callable[[], Any] | None = None,
) -> None:
    """Run the multi-file legend-order submenu."""
    try:
        if not is_multi_file or not file_data or len(file_data) < 2:
            print("Legend rearrange (ra) is only available with multiple files.")
            return
        host = _legend_host_fig(fig, ax)
        while True:
            order = getattr(host, "_ec_legend_file_order", None)
            if not isinstance(order, (list, tuple)) or len(order) != len(file_data):
                order = list(range(len(file_data)))
            order = [int(i) for i in order]
            # Keep host + fig in sync for legend build / style dump.
            set_ec_legend_file_order(host, file_data, order, ax=ax)
            try:
                host._ec_file_data = file_data
            except Exception:
                pass

            print("\nLegend top→bottom (number = file id):")
            for idx in order:
                if 0 <= idx < len(file_data):
                    f = file_data[idx]
                    vis = "" if f.get("visible", True) else " [hidden]"
                    print(f"  {idx + 1}: {_file_label(f, str(idx + 1))}{vis}")
            print(f"Current order: {' '.join(str(i + 1) for i in order)}")

            new_order_str = safe_input(
                "New order (file ids, e.g. 1 2 3 4), q=back: "
            ).strip()
            if not new_order_str or new_order_str.lower() == "q":
                break
            try:
                new_order = [int(item) - 1 for item in new_order_str.split()]
            except ValueError:
                print("Invalid input. Use space-separated file ids (e.g. 1 2 3 4).")
                continue
            if len(new_order) != len(file_data):
                print(f"Need exactly {len(file_data)} ids.")
                continue
            if sorted(new_order) != list(range(len(file_data))):
                print(f"Use each file id 1-{len(file_data)} exactly once.")
                continue
            if new_order == list(order):
                print("Order unchanged.")
                continue

            push_state("rearrange-legend")
            set_ec_legend_file_order(host, file_data, new_order, ax=ax)
            try:
                host._ec_file_data = file_data
            except Exception:
                pass
            try:
                rebuild_legend(ax)
            except Exception as exc:
                print(f"Legend rebuild failed: {exc}")
                if restore_state is not None:
                    try:
                        restore_state()
                    except Exception:
                        pass
                continue
            set_ec_legend_file_order(host, file_data, new_order, ax=ax)
            _force_draw(host)
            print("Legend order updated: " + " ".join(str(i + 1) for i in new_order))
    except Exception as exc:
        print(f"Error rearranging legend: {exc}")


__all__ = ["run_ec_legend_order_menu", "set_ec_legend_file_order"]
