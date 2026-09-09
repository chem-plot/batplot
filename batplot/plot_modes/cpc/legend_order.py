"""Legend ordering helpers for multi-file CPC/EPC plots."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence


def _legend_host_fig(fig: Any, ax: Any = None) -> Any:
    """Prefer ``ax.figure`` — that is what legend rebuild reads."""
    if ax is not None:
        try:
            host = ax.figure
            if host is not None:
                return host
        except Exception:
            pass
    return fig


def ensure_cpc_legend_file_order(
    fig: Any,
    file_data: Optional[Sequence[dict]],
    *,
    ax: Any = None,
) -> List[int]:
    """Return a valid 0-based permutation for ``file_data``; store on the host figure."""
    host = _legend_host_fig(fig, ax)
    n = len(file_data) if file_data is not None else 0
    if n <= 0:
        for target in (host, fig):
            if target is None:
                continue
            try:
                target._cpc_legend_file_order = []
            except Exception:
                pass
        return []

    raw = getattr(host, "_cpc_legend_file_order", None)
    if raw is None and fig is not None and fig is not host:
        raw = getattr(fig, "_cpc_legend_file_order", None)

    order: List[int] = []
    if isinstance(raw, (list, tuple)):
        seen = set()
        for item in raw:
            try:
                idx = int(item)
            except Exception:
                continue
            if 0 <= idx < n and idx not in seen:
                order.append(idx)
                seen.add(idx)
        for idx in range(n):
            if idx not in seen:
                order.append(idx)
    else:
        order = list(range(n))

    for target in (host, fig):
        if target is None:
            continue
        try:
            target._cpc_legend_file_order = list(order)
        except Exception:
            pass
    return order


def set_cpc_legend_file_order(
    fig: Any,
    file_data: Sequence[dict],
    order: Sequence[int],
    *,
    ax: Any = None,
) -> List[int]:
    """Validate and store a legend display permutation on the host figure."""
    host = _legend_host_fig(fig, ax)
    n = len(file_data)
    new_order = [int(i) for i in order]
    if len(new_order) != n or sorted(new_order) != list(range(n)):
        raise ValueError(f"Need a permutation of 0..{n - 1}")
    for target in (host, fig):
        if target is None:
            continue
        try:
            target._cpc_legend_file_order = list(new_order)
        except Exception:
            pass
    return list(new_order)


def _file_label(file_entry: dict, fallback: str) -> str:
    return str(
        file_entry.get("display_name")
        or file_entry.get("filename")
        or fallback
    )


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
        # Some macOS/Qt backends need a hard draw to show legend text changes.
        fig.canvas.draw()
    except Exception:
        pass


def run_cpc_legend_order_menu(
    *,
    fig: Any,
    ax: Any,
    ax2: Any,
    file_data: list[dict],
    is_multi_file: bool,
    print_file_list: Callable[..., Any],
    rebuild_legend: Callable[..., Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
) -> None:
    """Run the multi-file CPC legend-order submenu (display order only)."""
    try:
        if not is_multi_file or not file_data or len(file_data) < 2:
            print("Legend rearrange (ra) is only available with multiple files.")
            return
        host = _legend_host_fig(fig, ax)
        while True:
            order = ensure_cpc_legend_file_order(host, file_data, ax=ax)
            # One list only: files in current legend order, tagged with stable #.
            print("\nLegend top→bottom (number = file id):")
            for idx in order:
                if 0 <= idx < len(file_data):
                    f = file_data[idx]
                    vis = "" if f.get("visible", True) else " [hidden]"
                    print(f"  {idx + 1}: {_file_label(f, str(idx + 1))}{vis}")
            print(f"Current order: {' '.join(str(i + 1) for i in order)}")

            new_order_str = safe_input(
                f"New order (file ids, e.g. 1 2 3 4), q=back: "
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
            set_cpc_legend_file_order(host, file_data, new_order, ax=ax)
            try:
                rebuild_legend(ax, ax2, file_data, preserve_position=True)
            except TypeError:
                rebuild_legend(ax, ax2, file_data)
            except Exception as exc:
                print(f"Legend rebuild failed: {exc}")
                continue
            set_cpc_legend_file_order(host, file_data, new_order, ax=ax)
            _force_draw(host)

            # Confirm from the live legend artists (not just the stored list).
            try:
                leg = ax.get_legend() or (ax2.get_legend() if ax2 is not None else None)
                if leg is not None:
                    names = [t.get_text() for t in leg.get_texts() if (t.get_text() or "").strip()]
                    # Skip Charge/Discharge/Efficiency header rows.
                    skip = {"charge", "discharge", "efficiency"}
                    file_names = [n for n in names if n.strip().lower() not in skip]
                    if file_names:
                        print("Plot legend files: " + " → ".join(file_names))
            except Exception:
                pass
            print("Legend order updated: " + " ".join(str(i + 1) for i in new_order))
    except Exception as exc:
        print(f"Error rearranging legend: {exc}")


__all__ = [
    "ensure_cpc_legend_file_order",
    "run_cpc_legend_order_menu",
    "set_cpc_legend_file_order",
]
