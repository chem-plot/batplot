"""Shared spine/tick state helpers for interactive ``t`` commands.

The interactive modes keep their own menus and title behavior. This module only
owns the common WASD side-state shape and the low-level matplotlib spine/tick
application that is identical across modes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence, cast

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    AutoLocator,
    AutoMinorLocator,
    MultipleLocator,
    NullFormatter,
    NullLocator,
    ScalarFormatter,
)

from .interactive_state import SIDES, x_tickparam_keys

WASD_PROPS = ("spine", "ticks", "minor", "labels", "title")

_PREFIX_BY_SIDE = {
    "top": "t",
    "bottom": "b",
    "left": "l",
    "right": "r",
}


def side_minor_key(side: str) -> str:
    """Return the flat tick-state key for a side's minor ticks."""
    prefix = _PREFIX_BY_SIDE[str(side)]
    return f"m{prefix}x" if side in ("top", "bottom") else f"m{prefix}y"


def wasd_to_tick_state(
    wasd: Mapping[str, Mapping[str, object]] | None,
    *,
    tick_defaults: Mapping[str, bool] | None = None,
    label_defaults: Mapping[str, bool] | None = None,
    include_legacy: bool = True,
) -> Dict[str, bool]:
    """Convert a WASD side-state dict into the flat ``tick_state`` format."""
    wasd = wasd or {}
    out: Dict[str, bool] = {}
    for side in SIDES:
        prefix = _PREFIX_BY_SIDE[side]
        state = wasd.get(side, {}) or {}
        ticks = bool(state.get("ticks", (tick_defaults or {}).get(side, False)))
        labels = bool(state.get("labels", (label_defaults or {}).get(side, False)))
        out[f"{prefix}_ticks"] = ticks
        out[f"{prefix}_labels"] = labels
        out[side_minor_key(side)] = bool(state.get("minor", False))
        if include_legacy:
            legacy_key = {"top": "tx", "bottom": "bx", "left": "ly", "right": "ry"}[side]
            out[legacy_key] = bool(ticks and labels)
    return out


def sync_tick_state_from_wasd(
    tick_state: MutableMapping[str, Any],
    wasd: Mapping[str, Mapping[str, object]] | None,
    *,
    tick_defaults: Mapping[str, bool] | None = None,
    label_defaults: Mapping[str, bool] | None = None,
) -> MutableMapping[str, Any]:
    """Update an existing flat tick-state mapping from a WASD side-state dict."""
    tick_state.update(
        wasd_to_tick_state(
            wasd,
            tick_defaults=tick_defaults,
            label_defaults=label_defaults,
            include_legacy=True,
        )
    )
    return tick_state


def build_wasd_state(
    *,
    get_spine_visible: Callable[[str], bool],
    tick_state: Mapping[str, object],
    title_visible: Mapping[str, bool] | None = None,
    tick_defaults: Mapping[str, bool] | None = None,
    label_defaults: Mapping[str, bool] | None = None,
) -> Dict[str, Dict[str, bool]]:
    """Build the standard side-state shape used by all interactive ``t`` menus."""
    title_visible = title_visible or {}
    tick_defaults = tick_defaults or {}
    label_defaults = label_defaults or {}
    out: Dict[str, Dict[str, bool]] = {}
    for side in SIDES:
        prefix = _PREFIX_BY_SIDE[side]
        legacy_key = {"top": "tx", "bottom": "bx", "left": "ly", "right": "ry"}[side]
        out[side] = {
            "spine": bool(get_spine_visible(side)),
            "ticks": bool(tick_state.get(f"{prefix}_ticks", tick_state.get(legacy_key, tick_defaults.get(side, False)))),
            "minor": bool(tick_state.get(side_minor_key(side), False)),
            "labels": bool(tick_state.get(f"{prefix}_labels", tick_state.get(legacy_key, label_defaults.get(side, False)))),
            "title": bool(title_visible.get(side, label_defaults.get(side, False))),
        }
    return out


def apply_wasd_spines(
    ax: Any,
    wasd: Mapping[str, Mapping[str, object]] | None,
    *,
    sides: Iterable[str] = SIDES,
    axes_by_side: Optional[Mapping[str, Any]] = None,
) -> None:
    """Apply WASD spine visibility to one or more axes."""
    wasd = wasd or {}
    axes_by_side = axes_by_side or {}
    for side in sides:
        state = wasd.get(side, {}) or {}
        if "spine" not in state:
            continue
        target_ax = axes_by_side.get(side, ax)
        if target_ax is None:
            continue
        spine = target_ax.spines.get(side)
        if spine is not None:
            spine.set_visible(bool(state["spine"]))


def apply_wasd_tick_params(
    ax: Any,
    wasd: Mapping[str, Mapping[str, object]] | None,
    *,
    x_sides: Iterable[str] = ("top", "bottom"),
    y_sides: Iterable[str] = ("left", "right"),
    y_mode: str = "both",
) -> None:
    """Apply WASD major/minor tick and label visibility to an axis.

    ``y_mode`` lets modes keep their unique ownership:
    ``both`` controls left and right y sides, ``left`` only controls left, and
    ``right`` only controls right.
    """
    wasd = wasd or {}
    x_sides = tuple(x_sides)
    y_sides = tuple(y_sides)
    for side in x_sides:
        state = wasd.get(side, {}) or {}
        tick_key, label_key = x_tickparam_keys(side)
        if "ticks" in state:
            ax.tick_params(axis="x", which="major", **{tick_key: bool(state["ticks"])})
        if "minor" in state:
            ax.tick_params(axis="x", which="minor", **{tick_key: bool(state["minor"])})
        if "labels" in state:
            ax.tick_params(axis="x", which="major", **{label_key: bool(state["labels"])})

    active_y_sides = {
        side for side in y_sides
        if not ((y_mode == "left" and side != "left") or (y_mode == "right" and side != "right"))
    }
    y_major_kwargs: Dict[str, bool] = {}
    y_minor_kwargs: Dict[str, bool] = {}
    for side in ("left", "right"):
        if side not in active_y_sides:
            continue
        state = wasd.get(side, {}) or {}
        if "ticks" in state:
            y_major_kwargs[side] = bool(state["ticks"])
        if "labels" in state:
            y_major_kwargs[f"label{side}"] = bool(state["labels"])
        if "minor" in state:
            y_minor_kwargs[side] = bool(state["minor"])
    if y_major_kwargs:
        ax.tick_params(axis="y", which="major", **y_major_kwargs)
    if y_minor_kwargs:
        ax.tick_params(axis="y", which="minor", labelleft=False, labelright=False, **y_minor_kwargs)

    top_minor = bool((wasd.get("top", {}) or {}).get("minor", False))
    bottom_minor = bool((wasd.get("bottom", {}) or {}).get("minor", False))
    if any(side in x_sides for side in ("top", "bottom")):
        if top_minor or bottom_minor:
            ax.xaxis.set_minor_locator(AutoMinorLocator())
            ax.xaxis.set_minor_formatter(NullFormatter())
        else:
            ax.xaxis.set_minor_locator(NullLocator())
            ax.xaxis.set_minor_formatter(NullFormatter())

    left_minor = bool((wasd.get("left", {}) or {}).get("minor", False))
    right_minor = bool((wasd.get("right", {}) or {}).get("minor", False))
    if active_y_sides:
        side_minor_enabled = (
            ("left" in active_y_sides and left_minor)
            or ("right" in active_y_sides and right_minor)
        )
        if side_minor_enabled:
            ax.yaxis.set_minor_locator(AutoMinorLocator())
            ax.yaxis.set_minor_formatter(NullFormatter())
        else:
            ax.yaxis.set_minor_locator(NullLocator())
            ax.yaxis.set_minor_formatter(NullFormatter())


def normalize_changed_sides(changed_sides: Optional[Iterable[str]]) -> set[str]:
    """Return title-position sides, preserving empty sets as "reposition none"."""
    if changed_sides is None:
        return set(SIDES)
    return set(changed_sides)


def apply_changed_side_title_positions(
    changed_sides: Optional[Iterable[str]],
    *,
    bottom: Optional[Callable[[], None]] = None,
    top: Optional[Callable[[], None]] = None,
    left: Optional[Callable[[], None]] = None,
    right: Optional[Callable[[], None]] = None,
) -> set[str]:
    """Run only the title-position callbacks requested by ``changed_sides``.

    ``None`` means a deliberate full refresh. An empty set means no title
    movement, which is critical for spine/tick/minor-only commands.
    """
    sides = normalize_changed_sides(changed_sides)
    callbacks = {
        "bottom": bottom,
        "top": top,
        "left": left,
        "right": right,
    }
    for side in ("bottom", "top", "left", "right"):
        callback = callbacks[side]
        if side in sides and callback is not None:
            callback()
    return sides


def keep_yaxis_label_on_side(ax: Any, side: str = "right", *, visible: Optional[bool] = None) -> None:
    """Move a y-axis label without changing tick or tick-label visibility."""
    ax.yaxis.set_label_position(side)
    if visible is not None:
        ax.yaxis.label.set_visible(bool(visible))


def default_flat_tick_state(
    *,
    tick_defaults: Mapping[str, bool] | None = None,
    label_defaults: Mapping[str, bool] | None = None,
) -> Dict[str, bool]:
    """Return the flat tick-state format used by XY and legacy save paths."""
    return wasd_to_tick_state(
        {},
        tick_defaults=tick_defaults or {"top": False, "bottom": True, "left": True, "right": False},
        label_defaults=label_defaults or {"top": False, "bottom": True, "left": True, "right": False},
        include_legacy=True,
    )


def legacy_tick_state_to_flat(
    legacy: Mapping[str, object],
    *,
    tick_defaults: Mapping[str, bool] | None = None,
    label_defaults: Mapping[str, bool] | None = None,
) -> Dict[str, bool]:
    """Convert legacy ``bx/tx/ly/ry`` tick-state keys into explicit flat keys."""
    out = default_flat_tick_state(tick_defaults=tick_defaults, label_defaults=label_defaults)
    for side, legacy_key in {"top": "tx", "bottom": "bx", "left": "ly", "right": "ry"}.items():
        prefix = _PREFIX_BY_SIDE[side]
        value = bool(legacy.get(legacy_key, out[legacy_key]))
        out[f"{prefix}_ticks"] = value
        out[f"{prefix}_labels"] = value
        out[legacy_key] = value
        out[side_minor_key(side)] = bool(legacy.get(side_minor_key(side), False))
    return out


def sync_legacy_tick_keys(tick_state: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Mirror explicit ``*_ticks`` keys into legacy ``bx/tx/ly/ry`` keys."""
    tick_state["bx"] = bool(tick_state.get("b_ticks", True))
    tick_state["tx"] = bool(tick_state.get("t_ticks", False))
    tick_state["ly"] = bool(tick_state.get("l_ticks", True))
    tick_state["ry"] = bool(tick_state.get("r_ticks", False))
    return tick_state


def apply_flat_tick_params(ax: Any, tick_state: Mapping[str, object]) -> None:
    """Apply flat major/minor tick visibility state to a single matplotlib axis."""
    ax.tick_params(
        axis="x",
        bottom=bool(tick_state["b_ticks"]),
        labelbottom=bool(tick_state["b_labels"]),
        top=bool(tick_state["t_ticks"]),
        labeltop=bool(tick_state["t_labels"]),
    )
    ax.tick_params(
        axis="y",
        left=bool(tick_state["l_ticks"]),
        labelleft=bool(tick_state["l_labels"]),
        right=bool(tick_state["r_ticks"]),
        labelright=bool(tick_state["r_labels"]),
    )

    if tick_state["mbx"] or tick_state["mtx"]:
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(
            axis="x",
            which="minor",
            bottom=bool(tick_state["mbx"]),
            top=bool(tick_state["mtx"]),
            labelbottom=False,
            labeltop=False,
        )
    else:
        ax.xaxis.set_minor_locator(NullLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis="x", which="minor", bottom=False, top=False, labelbottom=False, labeltop=False)

    if tick_state["mly"] or tick_state["mry"]:
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(
            axis="y",
            which="minor",
            left=bool(tick_state["mly"]),
            right=bool(tick_state["mry"]),
            labelleft=False,
            labelright=False,
        )
    else:
        ax.yaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis="y", which="minor", left=False, right=False, labelleft=False, labelright=False)


def current_tick_width(axis_obj: Any, which: str) -> Optional[float]:
    """Return the current representative tick width for an x/y axis object."""
    try:
        tick_kw = axis_obj._major_tick_kw if which == "major" else axis_obj._minor_tick_kw
        width = tick_kw.get("width")
        if width is None:
            axis_name = getattr(axis_obj, "axis_name", "x")
            width = plt.rcParams.get(cast(Any, f"{axis_name}tick.{which}.width"))
        return float(width) if width is not None else None
    except Exception:
        return None


def parse_frame_tick_widths(raw: str, *, single_minor_scale: float = 0.6, paired_minor_scale: float = 0.7) -> tuple[float, float, float]:
    """Parse frame/tick-width submenu input into frame, major, and minor widths."""
    parts = str(raw).split()
    if len(parts) == 1:
        frame_width = float(parts[0])
        major_width = frame_width
        minor_width = frame_width * single_minor_scale
    elif len(parts) >= 2:
        frame_width = float(parts[0])
        major_width = float(parts[1])
        minor_width = major_width * paired_minor_scale
    else:
        raise ValueError("missing width")
    return frame_width, major_width, minor_width


def apply_frame_and_tick_widths(
    axes: Iterable[Any],
    *,
    frame_width: float,
    major_width: float,
    minor_width: Optional[float] = None,
) -> None:
    """Apply spine and tick widths to one or more matplotlib axes."""
    minor_width = major_width if minor_width is None else minor_width
    for axis in axes:
        if axis is None:
            continue
        for spine in getattr(axis, "spines", {}).values():
            spine.set_linewidth(frame_width)
        axis.tick_params(which="major", width=major_width)
        axis.tick_params(which="minor", width=minor_width)


def _draw_figure(fig: Any) -> None:
    try:
        fig.canvas.draw()
    except Exception:
        fig.canvas.draw_idle()


def _locator_spacing_text(locator: Any) -> str:
    try:
        if isinstance(locator, MultipleLocator):
            edge = getattr(locator, "_edge", None)
            step = getattr(edge, "step", None)
            return str(step) if step is not None else "auto"
        return "auto"
    except Exception:
        return "auto"


def _minor_locator_text(axis: Any) -> str:
    loc = axis.get_minor_locator()
    if isinstance(loc, AutoMinorLocator):
        try:
            ndivs = getattr(loc, "_ndivs", None)
            return f"{ndivs - 1}/interval" if ndivs is not None else "auto"
        except Exception:
            return "auto"
    if isinstance(loc, MultipleLocator):
        try:
            major = axis.get_major_locator()
            if isinstance(major, MultipleLocator):
                major_edge = getattr(major, "_edge", None)
                minor_edge = getattr(loc, "_edge", None)
                major_step = getattr(major_edge, "step", None)
                minor_step = getattr(minor_edge, "step", None)
                if major_step is not None and minor_step:
                    ratio = major_step / minor_step
                    return f"~{ratio:.4g}/interval"
        except Exception:
            pass
        edge = getattr(loc, "_edge", None)
        step = getattr(edge, "step", None)
        return f"step={step}" if step is not None else "auto"
    if isinstance(loc, NullLocator):
        return "off"
    return "auto"


def _format_axis_map(axis_map: Mapping[str, Any]) -> str:
    labels = {
        "x": "x",
        "y": "y",
        "r": "r",
        "all": "all",
    }
    return "  ".join(labels.get(key, key) for key in axis_map)


def print_wasd_state(
    wasd: Mapping[str, Mapping[str, object]],
    *,
    axis_map: Mapping[str, Any] | None = None,
    fig: Any = None,
) -> None:
    """Print the standard WASD state table used by all spine/tick menus."""
    cyan = "\033[96m"
    reset = "\033[0m"

    def onoff(value) -> str:
        return "ON " if bool(value) else "off"

    print("\033[1mToggle spines state:\033[0m")
    print(f"  {'Side':<8}  spine  major  minor  labels title")
    for side_key, side_code in [("top", "w"), ("bottom", "s"), ("left", "a"), ("right", "d")]:
        state = wasd.get(side_key, {})
        print(
            f"  {cyan}{side_code}={side_key:<6}{reset} "
            f"{onoff(state.get('spine'))}  {onoff(state.get('ticks'))}   "
            f"{onoff(state.get('minor'))}   {onoff(state.get('labels'))}  "
            f"{onoff(state.get('title'))}"
        )
    if fig is not None:
        tick_dir = getattr(fig, "_tick_direction", "out")
        print(f"  Tick direction  : {cyan}{tick_dir}{reset}")
        tick_lengths = getattr(fig, "_tick_lengths", {}) or {}
        major = tick_lengths.get("major")
        minor = tick_lengths.get("minor")
        if major is not None:
            minor_str = f"  minor={minor:.2g}" if minor is not None else ""
            print(f"  Tick length     : {cyan}major={major:.2g}{reset}{minor_str}")
        else:
            print("  Tick length     : default")
    if axis_map:
        spacing = []
        minors = []
        for key, axis in axis_map.items():
            spacing.append(f"{cyan}{key}{reset}={_locator_spacing_text(axis.get_major_locator())}")
            minors.append(f"{cyan}{key}{reset}={_minor_locator_text(axis)}")
        print("  Tick spacing    : " + "  ".join(spacing))
        print("  Minor count     : " + "  ".join(minors))


def run_spine_tick_menu(
    *,
    fig: Any,
    wasd: MutableMapping[str, Any],
    safe_input: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    colorize_inline_commands: Callable[[str], str],
    push_state: Callable[[str], None],
    sync_tick_state: Callable[[], None],
    apply_wasd: Callable[[Optional[set[str]]], None],
    draw: Optional[Callable[[], None]] = None,
    mode_label: str = "menu",
    back_label: str = "menu",
    axis_map: Optional[Mapping[str, Any]] = None,
    direction_axes: Optional[Sequence[Any]] = None,
    length_axes: Optional[Sequence[Any]] = None,
    side_aliases: Optional[Mapping[str, str]] = None,
    title_offset_handler: Optional[Callable[[], None]] = None,
    on_quit: Optional[Callable[[], None]] = None,
    print_state: Optional[Callable[[], None]] = None,
    extra_help_lines: Optional[Sequence[str]] = None,
    extra_command_handler: Optional[Callable[[str], bool]] = None,
) -> None:
    """Run the common interactive spine/tick command loop.

    Modes provide ``apply_wasd`` for their unique axis-title behavior and can
    choose which axes are affected by direction/length/spacing commands.
    """
    axis_map = dict(axis_map or {})
    direction_axes = list(direction_axes or [])
    length_axes = list(length_axes or direction_axes)
    side_aliases = dict(side_aliases or {})

    def _resolve_side(side: str) -> str:
        return side_aliases.get(side, side)

    def _draw() -> None:
        if draw is not None:
            draw()
        else:
            _draw_figure(fig)

    cyan = "\033[96m"
    reset = "\033[0m"
    axis_examples = _format_axis_map(axis_map) or "x  y  all"
    print("\033[1mToggle spines>\033[0m")
    print(f"  Side keys       : {cyan}w{reset}=top  {cyan}a{reset}=left  {cyan}s{reset}=bottom  {cyan}d{reset}=right")
    print(f"  What to toggle  : {cyan}1{reset}=spine line  {cyan}2{reset}=major ticks  {cyan}3{reset}=minor ticks  {cyan}4{reset}=labels  {cyan}5{reset}=axis title")
    print(f"  Toggle examples : {cyan}s2{reset}  {cyan}w5{reset}  {cyan}a4{reset}  {cyan}s2 w5 a4{reset}  (combine {cyan}w/a/s/d{reset}+{cyan}1-5{reset} only)")
    print(f"  Tick direction  : {cyan}i{reset}=invert (in/out)")
    print(f"  Tick length     : {cyan}l{reset}=set major length (minor auto-set to 70%)")
    print(f"  Tick spacing    : {cyan}n{reset}=set increment for {axis_examples}  (example: {cyan}x 0.5{reset}  {cyan}all 1{reset}  {cyan}x auto{reset})")
    print(f"  Minor count     : {cyan}m{reset}=minor ticks per interval  (example: {cyan}x 4{reset}  {cyan}all 0{reset}=off)")
    if title_offset_handler is not None:
        print(f"  Title offsets   : {cyan}p{reset}=adjust  ({cyan}w{reset}=top  {cyan}s{reset}=bottom  {cyan}a{reset}=left  {cyan}d{reset}=right)")
    if extra_help_lines:
        for line in extra_help_lines:
            print(line)
    print(f"  Other           : {cyan}list{reset}=show state   {cyan}q{reset}=back to {back_label}")
    print(colorize_inline_commands("Tip: q or blank backs out of submenus."))

    while True:
        cmd = safe_input(colorize_prompt("Enter spine/tick commands (w/a/s/d+1-5, i/l/n/m/p/list; q=back): ")).strip().lower()
        if not cmd or cmd == "q":
            if on_quit is not None:
                on_quit()
            break
        if extra_command_handler is not None and extra_command_handler(cmd):
            continue
        if cmd == "list":
            if print_state is not None:
                print_state()
            else:
                print_wasd_state(wasd, axis_map=axis_map, fig=fig)
            continue
        if cmd == "p":
            if title_offset_handler is not None:
                title_offset_handler()
            else:
                print("Title offset adjustment is not available in this mode.")
            continue
        if cmd == "i":
            push_state("tick-direction")
            current_dir = getattr(fig, "_tick_direction", "out")
            new_dir = "in" if current_dir == "out" else "out"
            setattr(fig, "_tick_direction", new_dir)
            for axis_owner in direction_axes:
                axis_owner.tick_params(axis="both", which="both", direction=new_dir)
            print(f"Tick direction: {new_dir}")
            _draw()
            continue
        if cmd == "l":
            while True:
                try:
                    sample_owner = length_axes[0] if length_axes else None
                    current_major = (
                        sample_owner.xaxis.get_major_ticks()[0].tick1line.get_markersize()
                        if sample_owner is not None and sample_owner.xaxis.get_major_ticks()
                        else 4.0
                    )
                    print(f"Current major tick length: {current_major}")
                    raw = safe_input("Enter new major tick length (e.g., 6.0, q=back): ").strip()
                    if not raw or raw.lower() == "q":
                        break
                    new_major = float(raw)
                    if new_major <= 0:
                        print("Length must be positive.")
                        continue
                    new_minor = new_major * 0.7
                    push_state("tick-length")
                    for axis_owner in length_axes:
                        axis_owner.tick_params(axis="both", which="major", length=new_major)
                        axis_owner.tick_params(axis="both", which="minor", length=new_minor)
                    if not hasattr(fig, "_tick_lengths"):
                        fig._tick_lengths = {}
                    fig._tick_lengths.update({"major": new_major, "minor": new_minor})
                    print(f"Set major tick length: {new_major}, minor: {new_minor:.2f}")
                    _draw()
                except ValueError:
                    print("Invalid number.")
                except Exception as exc:
                    print(f"Error setting tick length: {exc}")
            continue
        if cmd in ("n", "m"):
            is_minor = cmd == "m"
            if not axis_map:
                print("Tick spacing controls are not available in this mode.")
                continue
            print(f"{'Minor ticks' if is_minor else 'Set tick spacing'} for {mode_label}. Current:")
            for key, axis in axis_map.items():
                current = _minor_locator_text(axis) if is_minor else _locator_spacing_text(axis.get_major_locator())
                print(f"  {cyan}{key}{reset} : {current}")
            prompt = (
                "Minor ticks per interval (pairs like x 4, all 0, x auto; q=back): "
                if is_minor
                else "Major tick spacing (pairs like x 0.5, all 1, x auto; q=back): "
            )
            while True:
                raw = safe_input(colorize_prompt(prompt)).strip().lower()
                if not raw or raw == "q":
                    break
                parts = raw.split()
                if len(parts) < 2:
                    print("Need axis and value, e.g. 'x 0.5' or 'all 1'.")
                    continue
                if len(parts) % 2 != 0:
                    print("Unpaired token at end; use axis/value pairs.")
                    continue
                push_state("tick-minor-count" if is_minor else "tick-spacing")
                for index in range(0, len(parts), 2):
                    axis_key, value = parts[index], parts[index + 1]
                    axes = list(axis_map.values()) if axis_key == "all" else [axis_map.get(axis_key)]
                    axes = [axis for axis in axes if axis is not None]
                    if not axes:
                        print(f"Unknown axis '{axis_key}'. Use {', '.join(axis_map)} or all.")
                        break
                    for axis in axes:
                        if is_minor:
                            if value == "auto":
                                axis.set_minor_locator(AutoMinorLocator())
                                print(f"Set {axis.axis_name} minor ticks to auto.")
                            elif value == "0":
                                axis.set_minor_locator(NullLocator())
                                print(f"Disabled {axis.axis_name} minor ticks.")
                            else:
                                try:
                                    count = int(value)
                                    if count < 0:
                                        print("Count must be 0 or positive.")
                                        break
                                    axis.set_minor_locator(AutoMinorLocator(count + 1))
                                    print(f"Set {axis.axis_name} to {count} minor tick(s) per major interval.")
                                except ValueError:
                                    print(f"Invalid value '{value}'.")
                                    break
                        else:
                            if value == "auto":
                                axis.set_major_locator(AutoLocator())
                                axis.set_minor_locator(AutoMinorLocator())
                                print(f"Set {axis.axis_name} to auto spacing.")
                            else:
                                try:
                                    spacing = float(value)
                                    if spacing <= 0:
                                        print("Spacing must be positive.")
                                        break
                                    axis.set_major_locator(MultipleLocator(spacing))
                                    axis.set_minor_locator(MultipleLocator(spacing / 5))
                                    try:
                                        axis.set_major_formatter(ScalarFormatter())
                                    except Exception:
                                        pass
                                    print(f"Set {axis.axis_name} spacing: {spacing}")
                                except ValueError:
                                    print(f"Invalid value '{value}'.")
                                    break
                _draw()
            continue

        push_state("wasd-toggle")
        changed = False
        changed_sides = set()
        side_map = {"w": "top", "a": "left", "s": "bottom", "d": "right"}
        prop_map = {"1": "spine", "2": "ticks", "3": "minor", "4": "labels", "5": "title"}
        legacy_aliases = {
            "bl": ("bottom", "spine"),
            "tl": ("top", "spine"),
            "ll": ("left", "spine"),
            "rl": ("right", "spine"),
            "btcs": ("bottom", "ticks"),
            "ttcs": ("top", "ticks"),
            "tics": ("top", "ticks"),
            "ltcs": ("left", "ticks"),
            "rtcs": ("right", "ticks"),
            "mbx": ("bottom", "minor"),
            "mtx": ("top", "minor"),
            "mly": ("left", "minor"),
            "mry": ("right", "minor"),
            "blb": ("bottom", "labels"),
            "tlb": ("top", "labels"),
            "llb": ("left", "labels"),
            "rlb": ("right", "labels"),
            "bt": ("bottom", "title"),
            "tt": ("top", "title"),
            "lt": ("left", "title"),
            "rt": ("right", "title"),
        }
        combined_tick_label_aliases = {"bx": "bottom", "tx": "top", "ly": "left", "ry": "right"}
        for part in cmd.split():
            if part in combined_tick_label_aliases:
                side = _resolve_side(combined_tick_label_aliases[part])
                state = wasd.setdefault(side, {})
                new_value = not (bool(state.get("ticks", False)) or bool(state.get("labels", False)))
                state["ticks"] = new_value
                state["labels"] = new_value
                changed = True
                changed_sides.add(side)
                continue
            if part in legacy_aliases:
                side, prop = legacy_aliases[part]
                side = _resolve_side(side)
            elif len(part) == 2:
                raw_side = side_map.get(part[0])
                side = _resolve_side(raw_side) if raw_side is not None else None
                prop = prop_map.get(part[1])
            else:
                side = None
                prop = None
            if side is None or prop is None:
                print(f"Unknown code: {part}")
                continue
            wasd.setdefault(side, {})[prop] = not bool(wasd.get(side, {}).get(prop, False))
            changed = True
            if prop in ("labels", "title"):
                changed_sides.add(side)
        if changed:
            sync_tick_state()
            apply_wasd(changed_sides)
            _draw()


__all__ = [
    "WASD_PROPS",
    "apply_changed_side_title_positions",
    "apply_flat_tick_params",
    "apply_frame_and_tick_widths",
    "apply_wasd_spines",
    "apply_wasd_tick_params",
    "build_wasd_state",
    "current_tick_width",
    "default_flat_tick_state",
    "keep_yaxis_label_on_side",
    "legacy_tick_state_to_flat",
    "parse_frame_tick_widths",
    "side_minor_key",
    "sync_legacy_tick_keys",
    "sync_tick_state_from_wasd",
    "wasd_to_tick_state",
    "print_wasd_state",
    "run_spine_tick_menu",
]
