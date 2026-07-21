"""Shared batch helpers: I/O menu labels, value summaries for prompts, apply-to-all geometry."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from ..common.terminal import colorize_prompt, prompt_float, safe_input


def summarize_values(values: Sequence, *, fmt: str = "{:.2g}") -> str:
    """Format one value or ``a / b / c`` when panels differ (for prompts/submenus only)."""
    text = [fmt.format(v) for v in values]
    unique: list[str] = []
    seen: set[str] = set()
    for item in text:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[0] if len(unique) == 1 else " / ".join(unique)


def summarize_limit_pairs(
    pairs: Sequence[tuple[float, float]],
    *,
    fmt: str = "{:.4g}",
) -> str:
    """Format one ``lo hi`` pair or ``a b / c d / …`` when panels differ."""
    labels = [f"{fmt.format(a)} {fmt.format(b)}" for a, b in pairs]
    unique: list[str] = []
    seen: set[str] = set()
    for item in labels:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[0] if len(unique) == 1 else " / ".join(unique)


def print_batch_pair_status(
    panels: Sequence,
    *,
    label: str,
    get_pair: Callable[[Any], tuple[float, float]],
    fmt: str = "{:.4g}",
) -> None:
    """Print current lo/hi for all batch panels (numbered list when values differ)."""
    if not panels:
        return
    pairs = [get_pair(p) for p in panels]
    if len({(round(a, 8), round(b, 8)) for a, b in pairs}) == 1:
        a, b = pairs[0]
        print(f"Current {label} (all plots): {fmt.format(a)} {fmt.format(b)}")
        return
    print(f"Current {label}:")
    for i, (a, b) in enumerate(pairs, 1):
        print(f"  [{i}] {fmt.format(a)} {fmt.format(b)}")


def print_batch_scalar_status(
    panels: Sequence,
    *,
    label: str,
    get_value: Callable[[Any], float],
    fmt: str = "{:.4g}",
    unit: str = "",
) -> None:
    """Print one scalar per panel when values differ."""
    if not panels:
        return
    values = [float(get_value(p)) for p in panels]
    suffix = f" {unit}".rstrip()
    if len({round(v, 8) for v in values}) == 1:
        print(f"Current {label} (all plots): {fmt.format(values[0])}{suffix}")
        return
    print(f"Current {label}:")
    for i, val in enumerate(values, 1):
        print(f"  [{i}] {fmt.format(val)}{suffix}")


def batch_io_menu_options() -> list[str]:
    """Standard I/O column entries for batch interactive menus."""
    return [
        "e: export figures",
        "p: export style",
        "i: import style",
        "s: save sessions",
        "b: undo",
        "q: quit",
    ]


def batch_options_menu_column(panels: Sequence) -> list[str]:
    """Options column: crosshair + I/O (+ overwrite shortcuts when available)."""
    from .batch_commands import append_batch_io_shortcuts

    col = ["n: crosshair"]
    col.extend(batch_io_menu_options())
    append_batch_io_shortcuts(col, panels)
    return col


def _print_figsize_status(panels: Sequence, *, item_name: str) -> None:
    figs = [getattr(p, "fig", p) for p in panels]
    sizes = [fig.get_size_inches() for fig in figs]
    same = len({(round(w, 3), round(h, 3)) for w, h in sizes}) == 1
    if same and panels:
        w, h = sizes[0]
        print(f"Current {item_name} (all plots): {w:.2f} x {h:.2f} in")
        return
    print(f"Current {item_name} sizes (new values apply to ALL plots):")
    for i, (w, h) in enumerate(sizes, 1):
        print(f"  [{i}] {w:.2f} x {h:.2f} in")


def prompt_and_apply_figsize_all(
    panels: Sequence,
    *,
    push_undo: Callable[[], None],
    draw_all: Callable[[], None],
    item_name: str = "figure",
    width_prompt: str | None = None,
    height_prompt: str | None = None,
) -> None:
    """Prompt repeatedly and set the same canvas/figure size on every panel."""
    if not panels:
        return
    w_prompt = width_prompt or f"{item_name.title()} width for ALL plots (inches, q=back): "
    h_prompt = height_prompt or f"{item_name.title()} height for ALL plots (inches, q=back): "
    while True:
        _print_figsize_status(panels, item_name=item_name)
        w = prompt_float(safe_input, w_prompt, on_error="Invalid width.")
        if w is None:
            return
        if w <= 0:
            print("Width must be positive.")
            continue
        h = prompt_float(safe_input, h_prompt, on_error="Invalid height.")
        if h is None:
            return
        if h <= 0:
            print("Height must be positive.")
            continue
        push_undo()
        for panel in panels:
            getattr(panel, "fig", panel).set_size_inches(w, h, forward=True)
        draw_all()
        print(f"{item_name.title()} size set to {w:.2f} x {h:.2f} in on all {len(panels)} plots.")


def prompt_axis_limits(
    *,
    label: str,
    get_current: Callable[[], tuple[float, float]] | None = None,
    panels: Sequence | None = None,
    get_panel_limits: Callable[[Any], tuple[float, float]] | None = None,
) -> tuple[float, float] | None:
    """Shared w/s/a/q axis limit prompt. Returns (lo, hi) or None if cancelled."""
    if panels is not None and get_panel_limits is not None:
        return _prompt_batch_axis_limits(panels, label=label, get_panel_limits=get_panel_limits)
    if get_current is None:
        raise ValueError("prompt_axis_limits requires get_current or panels+get_panel_limits")
    return _prompt_axis_limits_single(label=label, get_current=get_current)


def _prompt_axis_limits_single(
    *,
    label: str,
    get_current: Callable[[], tuple[float, float]],
) -> tuple[float, float] | None:
    while True:
        cur = get_current()
        print(f"Current {label}: {cur[0]:.4g} {cur[1]:.4g}")
        print("  " + "limit1 limit2 | w=upper | s=lower | a=auto | q=back")
        line = safe_input(
            colorize_prompt(f"{label} (w/s/a/q): "),
            cancel_on_interrupt=True,
        ).strip()
        if not line or line.lower() == "q":
            return None
        low = line.lower()
        if low == "a":
            print("Auto range is per-plot; set explicit limits to sync all panels.")
            continue
        if low == "w":
            while True:
                cur = get_current()
                val = safe_input(
                    colorize_prompt(f"New upper (current lower {cur[0]:.4g}, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if not val or val.lower() == "q":
                    break
                try:
                    hi = float(val)
                    lo = float(cur[0])
                    return (lo, hi) if lo <= hi else (hi, lo)
                except ValueError:
                    print("Invalid number.")
            continue
        if low == "s":
            while True:
                cur = get_current()
                val = safe_input(
                    colorize_prompt(f"New lower (current upper {cur[1]:.4g}, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if not val or val.lower() == "q":
                    break
                try:
                    lo = float(val)
                    hi = float(cur[1])
                    return (lo, hi) if lo <= hi else (hi, lo)
                except ValueError:
                    print("Invalid number.")
            continue
        parts = line.replace(",", " ").split()
        if len(parts) == 2:
            try:
                a, b = float(parts[0]), float(parts[1])
                return (a, b) if a <= b else (b, a)
            except ValueError:
                print("Invalid range.")
                continue
        print("Enter two limits, or w/s/a/q.")


def _prompt_batch_axis_limits(
    panels: Sequence,
    *,
    label: str,
    get_panel_limits: Callable[[Any], tuple[float, float]],
) -> tuple[float, float] | None:
    """Batch axis limit prompt: show every panel's current range when they differ."""
    ref = panels[0]

    def _ref_limits() -> tuple[float, float]:
        return get_panel_limits(ref)

    while True:
        print_batch_pair_status(panels, label=label, get_pair=get_panel_limits)
        print("  " + "limit1 limit2 | w=upper | s=lower | a=auto | q=back")
        line = safe_input(
            colorize_prompt(f"{label} (w/s/a/q): "),
            cancel_on_interrupt=True,
        ).strip()
        if not line or line.lower() == "q":
            return None
        low = line.lower()
        if low == "a":
            print("Auto range is per-plot; set explicit limits to sync all panels.")
            continue
        if low == "w":
            lowers = summarize_values([get_panel_limits(p)[0] for p in panels], fmt="{:.4g}")
            while True:
                val = safe_input(
                    colorize_prompt(f"New upper (current lower(s) {lowers}, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if not val or val.lower() == "q":
                    break
                try:
                    hi = float(val)
                    lo = float(_ref_limits()[0])
                    return (lo, hi) if lo <= hi else (hi, lo)
                except ValueError:
                    print("Invalid number.")
            continue
        if low == "s":
            uppers = summarize_values([get_panel_limits(p)[1] for p in panels], fmt="{:.4g}")
            while True:
                val = safe_input(
                    colorize_prompt(f"New lower (current upper(s) {uppers}, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if not val or val.lower() == "q":
                    break
                try:
                    lo = float(val)
                    hi = float(_ref_limits()[1])
                    return (lo, hi) if lo <= hi else (hi, lo)
                except ValueError:
                    print("Invalid number.")
            continue
        parts = line.replace(",", " ").split()
        if len(parts) == 2:
            try:
                a, b = float(parts[0]), float(parts[1])
                return (a, b) if a <= b else (b, a)
            except ValueError:
                print("Invalid range.")
                continue
        print("Enter two limits, or w/s/a/q.")


def prompt_batch_clim(
    panels: Sequence,
    *,
    label: str = "intensity",
    get_clim: Callable[[Any], tuple[float, float]] | None = None,
) -> tuple[float, float] | None:
    """Prompt vmin/vmax applied to all panels; show each panel's clim when they differ."""
    if not panels:
        return None
    getter = get_clim or (lambda p: p.im.get_clim())
    while True:
        print_batch_pair_status(panels, label=label, get_pair=getter)
        line = safe_input(
            colorize_prompt(f"{label.title()} vmin vmax for ALL (q=back): "),
            cancel_on_interrupt=True,
        ).strip()
        if not line or line.lower() == "q":
            return None
        parts = line.replace(",", " ").split()
        if len(parts) != 2:
            print("Enter two numbers.")
            continue
        try:
            vmin, vmax = float(parts[0]), float(parts[1])
        except ValueError:
            print("Invalid numbers.")
            continue
        if vmin == vmax:
            print("Limits must differ.")
            continue
        if vmin > vmax:
            vmin, vmax = vmax, vmin
        return vmin, vmax


__all__ = [
    "batch_io_menu_options",
    "batch_options_menu_column",
    "print_batch_pair_status",
    "print_batch_scalar_status",
    "prompt_and_apply_figsize_all",
    "prompt_axis_limits",
    "prompt_batch_clim",
    "summarize_limit_pairs",
    "summarize_values",
]
