"""Flexible parsing and cyan-highlighted prompts for canvas/frame size menus."""

from __future__ import annotations

from .menu_rendering import ansi_menu_enabled


def _hl(text: str) -> str:
    """Cyan-highlight a keyword or number when ANSI menus are enabled."""
    if not ansi_menu_enabled():
        return str(text)
    return f"\033[96m{text}\033[0m"


def fmt_inches_pair(w: float, h: float, *, decimals: int = 2) -> str:
    """``W x H in`` with cyan numbers."""
    fmt = f"{{:.{decimals}f}}"
    return f"{_hl(fmt.format(w))} x {_hl(fmt.format(h))} in"


def is_size_quit_token(spec: str) -> bool:
    """True for blank / ``q`` / ``qq`` (common typo) — cancel size entry."""
    raw = (spec or "").strip().lower()
    if not raw or raw == "q":
        return True
    return len(raw) <= 3 and set(raw) == {"q"}


def fmt_inch(value: float, *, decimals: int = 2) -> str:
    """Single inch magnitude with cyan number."""
    fmt = f"{{:.{decimals}f}}"
    return f"{_hl(fmt.format(value))} in"


def current_canvas_status(
    w: float,
    h: float,
    *,
    frame: tuple[float, float] | None = None,
    all_plots: bool = False,
) -> str:
    """Status line for current canvas (optional nested frame)."""
    scope = " (all plots)" if all_plots else ""
    base = f"Current {_hl('canvas')}{scope}: {fmt_inches_pair(w, h)}"
    if frame is None:
        return base
    fw, fh = frame
    return f"{base} ({_hl('frame')} {fmt_inches_pair(fw, fh)})"


def current_plot_frame_status(w: float, h: float, *, all_plots: bool = False) -> str:
    """Status line for current plot frame."""
    scope = " (all plots)" if all_plots else ""
    return (
        f"Current {_hl('plot frame')}{scope}: "
        f"{fmt_inches_pair(w, h)} ({_hl('W x H')})"
    )


def panel_size_list_line(
    index: int,
    *,
    canvas: tuple[float, float],
    frame: tuple[float, float],
    label: str = "",
) -> str:
    """One row when panels differ in size."""
    cw, ch = canvas
    fw, fh = frame
    suffix = f"  ({label})" if label else ""
    return (
        f"  [{index}] {_hl('canvas')} {fmt_inches_pair(cw, ch)}, "
        f"{_hl('frame')} {fmt_inches_pair(fw, fh)}{suffix}"
    )


def plot_frame_size_prompt(*, all_plots: bool = False) -> str:
    """Prompt text with cyan example forms."""
    scope = " for ALL plots" if all_plots else ""
    examples = (
        f"{_hl('6 4')}  |  {_hl('6x4')}  |  {_hl('w=6')} {_hl('h=4')}  |  "
        f"{_hl('scale=1.2')}  |  single width  |  {_hl('q')}=back"
    )
    return f"Enter new {_hl('plot frame')} size{scope} (e.g. {examples}): "


def canvas_size_prompt(*, all_plots: bool = False) -> str:
    """Prompt text with cyan example forms."""
    scope = " for ALL plots" if all_plots else ""
    examples = (
        f"{_hl('8 6')}  |  {_hl('6x4')}  |  {_hl('w=6')} {_hl('h=5')}  |  "
        f"{_hl('scale=1.2')}  |  {_hl('q')}=back"
    )
    return f"Enter new {_hl('canvas')} size{scope} (e.g. {examples}): "


def plot_frame_applied_msg(
    w: float,
    h: float,
    *,
    canvas: tuple[float, float] | None = None,
    n_plots: int | None = None,
) -> str:
    if n_plots is not None:
        return f"{_hl('Plot frame')} set to {fmt_inches_pair(w, h)} on all {n_plots} plots."
    if canvas is not None:
        return (
            f"{_hl('Plot frame')} set to {fmt_inches_pair(w, h)} "
            f"inside {_hl('canvas')} {fmt_inches_pair(canvas[0], canvas[1])}."
        )
    return f"{_hl('Plot frame')} set to {fmt_inches_pair(w, h)}."


def canvas_applied_msg(
    w: float,
    h: float,
    *,
    frame: tuple[float, float] | None = None,
    frame_before: tuple[float, float] | None = None,
    note: str = "",
    n_plots: int | None = None,
) -> str:
    if n_plots is not None:
        return f"{_hl('Canvas')} set to {fmt_inches_pair(w, h)} on all {n_plots} plots."
    if frame is not None and frame_before is not None:
        return (
            f"{_hl('Canvas')} resized to {fmt_inches_pair(w, h)}; "
            f"{_hl('frame')} preserved at {fmt_inches_pair(frame[0], frame[1])}{note} "
            f"(was {fmt_inches_pair(frame_before[0], frame_before[1])})."
        )
    return f"{_hl('Canvas')} set to {fmt_inches_pair(w, h)}."


def parse_size_spec(
    spec: str,
    cur_w: float,
    cur_h: float,
) -> tuple[float, float] | None:
    """Parse a resize spec (same rules as ``ui.resize_plot_frame``).

    Accepts ``6 4``, ``6x4``, ``w=6 h=4``, ``scale=1.2``, or a single width
    (height scaled to preserve aspect). Returns ``None`` on quit/invalid.
    """
    raw = (spec or "").strip().lower()
    if is_size_quit_token(raw):
        return None
    new_w, new_h = cur_w, cur_h
    if "scale=" in raw:
        try:
            factor = float(raw.split("scale=", 1)[1].strip())
            new_w = cur_w * factor
            new_h = cur_h * factor
        except Exception:
            print("Invalid scale factor.")
            return None
    else:
        parts = raw.replace("x", " ").split()
        kv: dict[str, str] = {}
        numbers: list[str] = []
        for part in parts:
            if "=" in part:
                key, val = part.split("=", 1)
                kv[key.strip()] = val.strip()
            else:
                numbers.append(part)
        try:
            if kv:
                if "w" in kv:
                    new_w = float(kv["w"])
                if "h" in kv:
                    new_h = float(kv["h"])
            elif len(numbers) == 2:
                new_w, new_h = float(numbers[0]), float(numbers[1])
            elif len(numbers) == 1:
                new_w = float(numbers[0])
                aspect = cur_h / cur_w if cur_w else 1.0
                new_h = new_w * aspect
            else:
                print("Could not parse specification.")
                return None
        except ValueError:
            print("Invalid size numbers.")
            return None
    min_in = 0.01
    return max(min_in, new_w), max(min_in, new_h)


def parse_positive_float(spec: str, *, label: str = "value") -> float | None:
    """Parse one positive inch value; return None on cancel/invalid."""
    raw = (spec or "").strip().lower()
    if is_size_quit_token(raw):
        return None
    try:
        val = float(raw)
    except ValueError:
        print(f"Invalid {label}.")
        return None
    if val <= 0:
        print(f"{label.title()} must be positive.")
        return None
    return val


__all__ = [
    "canvas_applied_msg",
    "canvas_size_prompt",
    "current_canvas_status",
    "current_plot_frame_status",
    "fmt_inch",
    "fmt_inches_pair",
    "is_size_quit_token",
    "panel_size_list_line",
    "parse_positive_float",
    "parse_size_spec",
    "plot_frame_applied_msg",
    "plot_frame_size_prompt",
]
