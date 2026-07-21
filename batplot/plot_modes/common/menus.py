"""Shared interactive submenu runners for plot modes.

These helpers own only the terminal prompt/dispatch loops. Each plot mode still
passes callbacks for the actual state changes so mode-specific behavior stays
local.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Optional


DEFAULT_FONT_FAMILIES = [
    "Arial",
    "DejaVu Sans",
    "Helvetica",
    "Liberation Sans",
    "Times New Roman",
    "Courier New",
    "Verdana",
    "Tahoma",
]


def run_repeat_input_loop(
    *,
    prompt: str | Callable[[], str],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
    process: Callable[[str], bool | None],
    cancel_on_blank: bool = True,
) -> None:
    """Repeatedly prompt until the user enters blank/q.

    ``process(raw)`` should apply one edit and return ``True`` to continue looping,
    ``False`` to stay on the same prompt after a validation error, or ``None``/implicit
    success to continue. Blank/q always exits.
    """
    while True:
        text = prompt() if callable(prompt) else prompt
        try:
            try:
                raw = safe_input(colorize_prompt(text), cancel_on_interrupt=True).strip()
            except TypeError:
                raw = safe_input(colorize_prompt(text)).strip()
        except (KeyboardInterrupt, EOFError):
            print("Canceled.")
            break
        if raw.lower() == "q" or (cancel_on_blank and not raw):
            break
        try:
            result = process(raw)
        except Exception as exc:
            print(f"Error: {exc}")
            continue
        if result is False:
            continue


def run_font_menu(
    *,
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    get_current_family: Callable[[], object],
    get_current_size: Callable[[], object],
    apply_family: Callable[[str], None],
    apply_size: Callable[[float], None],
    fonts: Optional[list[str]] = None,
    blank_exits: bool = True,
    get_current_weight: Callable[[], object] | None = None,
    apply_weight: Callable[[str], None] | None = None,
    get_current_highlight: Callable[[], bool] | None = None,
    get_highlight_style: Callable[[], dict] | None = None,
    apply_highlight_toggle: Callable[[], None] | None = None,
    apply_highlight_facecolor: Callable[[str], None] | None = None,
    apply_highlight_alpha: Callable[[float], None] | None = None,
    apply_highlight_pad: Callable[[float], None] | None = None,
) -> None:
    """Run the shared ``f`` font submenu.

    Font application itself is delegated to callbacks because each mode has
    different artists to update (legends, duplicate titles, secondary axes).
    """
    fonts = fonts or DEFAULT_FONT_FAMILIES
    has_weight = apply_weight is not None and get_current_weight is not None
    has_highlight = (
        apply_highlight_toggle is not None
        and get_current_highlight is not None
        and get_highlight_style is not None
    )
    while True:
        status = f"family='{get_current_family()}', size={get_current_size()}"
        if has_weight:
            status += f", weight={get_current_weight()}"
        if has_highlight:
            on = "on" if get_current_highlight() else "off"
            status += f", highlight={on}"
        print(f"\nFont (current: {status})")
        print("  " + colorize_menu("f: family"))
        print("  " + colorize_menu("s: size"))
        if has_weight:
            print("  " + colorize_menu("b: bold / weight"))
        if has_highlight:
            print("  " + colorize_menu("h: text highlight (bbox behind labels)"))
        print("  " + colorize_menu("q: back"))
        keys = "f/s"
        if has_weight:
            keys += "/b"
        if has_highlight:
            keys += "/h"
        keys += "/q"
        sub = safe_input(colorize_prompt(f"Font ({keys}): ")).strip().lower()
        if not sub:
            if blank_exits:
                break
            continue
        if sub == "q":
            break
        if sub == "f":
            print("\nCommon font families:")
            for idx, font in enumerate(fonts, 1):
                print("  " + colorize_menu(f"{idx}: {font}"))
            print("  " + colorize_menu("Or enter custom font name directly"))

            def _apply_family_choice(choice: str) -> bool:
                if choice.isdigit():
                    index = int(choice)
                    if not (1 <= index <= len(fonts)):
                        print("Invalid number.")
                        return False
                    family = fonts[index - 1]
                else:
                    family = choice
                try:
                    apply_family(family)
                    print(f"Applied font family: {family}")
                except Exception as exc:
                    print(f"Error changing font family: {exc}")
                return True

            run_repeat_input_loop(
                prompt=lambda: (
                    f"Font family (current: '{get_current_family()}', number or name, q=back): "
                ),
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                process=_apply_family_choice,
            )
            continue
        if sub == "s":

            def _apply_size_choice(choice: str) -> bool:
                try:
                    size = float(choice)
                except ValueError:
                    print("Invalid size.")
                    return False
                if size <= 0:
                    print("Size must be positive.")
                    return False
                try:
                    apply_size(size)
                    print(f"Applied font size: {size}")
                except Exception as exc:
                    print(f"Error changing font size: {exc}")
                return True

            run_repeat_input_loop(
                prompt=lambda: f"Font size (current: {get_current_size()}, q=back): ",
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                process=_apply_size_choice,
            )
            continue
        if sub == "b" and has_weight:

            def _apply_weight_choice(choice: str) -> bool:
                raw = choice.strip().lower()
                if not raw:
                    new_w = "normal" if str(get_current_weight()).lower() == "bold" else "bold"
                elif raw in ("bold", "b"):
                    new_w = "bold"
                elif raw in ("normal", "n", "regular", "r"):
                    new_w = "normal"
                else:
                    print("Use bold, normal, or blank to toggle.")
                    return False
                try:
                    apply_weight(new_w)
                    print(f"Applied font weight: {new_w}")
                except Exception as exc:
                    print(f"Error changing font weight: {exc}")
                return True

            run_repeat_input_loop(
                prompt=lambda: f"Font weight (current: {get_current_weight()}, bold/normal/blank=toggle, q=back): ",
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                process=_apply_weight_choice,
                cancel_on_blank=False,
            )
            continue
        if sub == "h" and has_highlight:
            while True:
                st = get_highlight_style()
                on = "on" if get_current_highlight() else "off"
                print(f"\nText highlight (current: {on}, face={st.get('fc', 'white')}, alpha={st.get('alpha', 0.85):g}, pad={st.get('pad', 0.2):g})")
                print("  " + colorize_menu("t: toggle on/off"))
                print("  " + colorize_menu("c: face color (e.g. white, #f8f8f8)"))
                print("  " + colorize_menu("a: alpha (0-1)"))
                print("  " + colorize_menu("p: pad (bbox padding)"))
                print("  " + colorize_menu("q: back"))
                hsub = safe_input(colorize_prompt("Highlight (t/c/a/p/q): ")).strip().lower()
                if not hsub or hsub == "q":
                    break
                if hsub == "t":
                    try:
                        apply_highlight_toggle()
                        print(f"Text highlight {'on' if get_current_highlight() else 'off'}.")
                    except Exception as exc:
                        print(f"Error toggling highlight: {exc}")
                    continue
                if hsub == "c" and apply_highlight_facecolor is not None:

                    def _apply_hl_color(spec: str) -> bool:
                        try:
                            apply_highlight_facecolor(spec)
                            print(f"Highlight face color set to {spec}.")
                        except Exception as exc:
                            print(f"Error: {exc}")
                        return True

                    run_repeat_input_loop(
                        prompt=lambda: f"Highlight face color (current: {get_highlight_style().get('fc', 'white')}, q=back): ",
                        safe_input=safe_input,
                        colorize_prompt=colorize_prompt,
                        process=_apply_hl_color,
                    )
                    continue
                if hsub == "a" and apply_highlight_alpha is not None:

                    def _apply_hl_alpha(raw: str) -> bool:
                        try:
                            val = float(raw)
                        except ValueError:
                            print("Invalid alpha.")
                            return False
                        if not (0.0 <= val <= 1.0):
                            print("Alpha must be between 0 and 1.")
                            return False
                        try:
                            apply_highlight_alpha(val)
                            print(f"Highlight alpha set to {val:g}.")
                        except Exception as exc:
                            print(f"Error: {exc}")
                        return True

                    run_repeat_input_loop(
                        prompt=lambda: f"Highlight alpha (current: {get_highlight_style().get('alpha', 0.85):g}, q=back): ",
                        safe_input=safe_input,
                        colorize_prompt=colorize_prompt,
                        process=_apply_hl_alpha,
                    )
                    continue
                if hsub == "p" and apply_highlight_pad is not None:

                    def _apply_hl_pad(raw: str) -> bool:
                        try:
                            val = float(raw)
                        except ValueError:
                            print("Invalid pad.")
                            return False
                        if val < 0:
                            print("Pad must be non-negative.")
                            return False
                        try:
                            apply_highlight_pad(val)
                            print(f"Highlight pad set to {val:g}.")
                        except Exception as exc:
                            print(f"Error: {exc}")
                        return True

                    run_repeat_input_loop(
                        prompt=lambda: f"Highlight pad (current: {get_highlight_style().get('pad', 0.2):g}, q=back): ",
                        safe_input=safe_input,
                        colorize_prompt=colorize_prompt,
                        process=_apply_hl_pad,
                    )
                    continue
                print("Unknown highlight option.")
            continue
        print("Invalid font submenu option.")


def run_option_menu(
    *,
    title: str | None = None,
    prompt: str,
    options: Mapping[str, tuple[str, Callable[[], None]]],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    blank_exits: bool = True,
) -> None:
    """Run a simple key-to-callback submenu while preserving local callbacks."""
    while True:
        if title:
            print(title)
        for key, (description, _handler) in options.items():
            print("  " + colorize_menu(f"{key}: {description}"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(colorize_prompt(prompt)).strip().lower()
        if not choice:
            if blank_exits:
                break
            continue
        if choice == "q":
            break
        option = options.get(choice)
        if option is None:
            print("Unknown option.")
            continue
        option[1]()


def run_dispatch_menu(
    *,
    title: str | None = None,
    prompt: str,
    options: Mapping[str, str],
    handle_choice: Callable[[str], None],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    blank_exits: bool = True,
) -> None:
    """Run a submenu loop where the caller owns mode-specific dispatch."""
    while True:
        if title:
            print(title)
        for key, description in options.items():
            print("  " + colorize_menu(f"{key}: {description}"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(colorize_prompt(prompt)).strip().lower()
        if not choice:
            if blank_exits:
                break
            continue
        if choice == "q":
            break
        handle_choice(choice)


def run_axis_limit_menu(
    *,
    axis_name: str,
    prompt_name: str,
    get_limits: Callable[[], tuple[float, float]],
    set_limits: Callable[[float, float], None],
    auto_limits: Callable[[], Any],  # return value is ignored; callers may return a tuple
    push_state: Callable[[str], None],
    state_label: str,
    draw: Callable[[], None],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    normalize_pair: bool = False,
    invalid_message: str = "Invalid limits, ignored.",
) -> None:
    """Run a shared axis range menu for ``x``/``y`` style commands."""
    while True:
        low, high = get_limits()
        print(f"Current {axis_name} range: {low:.6g} to {high:.6g}")
        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("a: auto (restore original)"))
        print("  " + colorize_menu("q: back"))
        raw = safe_input(colorize_prompt(f"{prompt_name} (w/s/a/q): ")).strip()
        if not raw or raw.lower() == "q":
            break
        key = raw.lower()
        if key == "a":
            push_state(f"{state_label}-auto")
            auto_limits()
            draw()
            continue
        if key in ("w", "s"):
            is_upper = key == "w"
            while True:
                low, high = get_limits()
                fixed_label = "lower" if is_upper else "upper"
                fixed_value = low if is_upper else high
                target_label = "upper" if is_upper else "lower"
                print(f"Current {axis_name} range: {low:.6g} to {high:.6g}")
                value = safe_input(
                    colorize_prompt(f"Enter {target_label} limit (current {fixed_label}: {fixed_value:.6g}, q=back): ")
                ).strip()
                if not value or value.lower() == "q":
                    break
                try:
                    number = float(value)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                push_state(state_label)
                if is_upper:
                    set_limits(low, number)
                else:
                    set_limits(number, high)
                draw()
                new_low, new_high = get_limits()
                print(f"{axis_name} range updated: {new_low:.6g} to {new_high:.6g}")
            continue
        try:
            parts = raw.split()
            if len(parts) != 2:
                raise ValueError()
            low, high = float(parts[0]), float(parts[1])
            if normalize_pair:
                low, high = min(low, high), max(low, high)
            push_state(state_label)
            set_limits(low, high)
            draw()
        except Exception:
            print(invalid_message)


def derive_legend_offset_from_current(
    *,
    fig: Any,
    legend: Any,
    sanitize_offset: Callable[[object], tuple[float, float] | None],
) -> tuple[float, float] | None:
    """Return legend offset in inches from figure center for an existing legend."""
    if legend is None:
        return None
    try:
        try:
            renderer = fig.canvas.get_renderer()
        except Exception:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
        bbox = legend.get_window_extent(renderer=renderer)
        cx = 0.5 * (bbox.x0 + bbox.x1)
        cy = 0.5 * (bbox.y0 + bbox.y1)
        fx, fy = fig.transFigure.inverted().transform((cx, cy))
        fw, fh = fig.get_size_inches()
        return sanitize_offset(((fx - 0.5) * fw, (fy - 0.5) * fh))
    except Exception:
        return None


def _legend_position_submenu(
    *,
    get_position: Callable[[], tuple[float, float]],
    set_position: Callable[[tuple[float, float]], None],
    sanitize_offset: Callable[[object], tuple[float, float] | None],
    apply_position: Callable[[], None],
    push_state: Callable[[str], None],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    step: float,
) -> None:
    def _set_and_apply(pos: tuple[float, float], message: str | None = None) -> None:
        new_pos = sanitize_offset(pos)
        if new_pos is None:
            print(f"Invalid position: x={pos[0]:.2f}, y={pos[1]:.2f} is out of bounds.")
            return
        set_position(new_pos)
        apply_position()
        if message is None:
            message = f"Legend position updated: x={new_pos[0]:.2f}, y={new_pos[1]:.2f}"
        print(message)

    def _axis_submenu(axis: str) -> None:
        while True:
            x_in, y_in = get_position()
            print(f"Current position: x={x_in:.2f}, y={y_in:.2f}")
            print(axis + ":")
            if axis == "x":
                print("  " + colorize_menu("a: left"))
                print("  " + colorize_menu("d: right"))
                prompt = "x (a/d/number/q): "
            else:
                print("  " + colorize_menu("w: up"))
                print("  " + colorize_menu("s: down"))
                prompt = "y (w/s/number/q): "
            print("  " + colorize_menu("number: direct"))
            print("  " + colorize_menu("q: back"))
            value = safe_input(colorize_prompt(prompt)).strip().lower()
            if not value or value == "q":
                break
            if axis == "x" and value in ("a", "d"):
                push_state("legend-position")
                delta = -step if value == "a" else step
                _set_and_apply((x_in + delta, y_in))
                continue
            if axis == "y" and value in ("w", "s"):
                push_state("legend-position")
                delta = step if value == "w" else -step
                _set_and_apply((x_in, y_in + delta))
                continue
            try:
                direct = float(value)
            except (ValueError, KeyboardInterrupt):
                print(f"Invalid input (use {'a, d' if axis == 'x' else 'w, s'}, number, or q).")
                continue
            push_state("legend-position")
            _set_and_apply((direct, y_in) if axis == "x" else (x_in, direct))

    while True:
        xy_in = get_position()
        print(f"Current position: x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
        print("Position:")
        print("  " + colorize_menu("w: up"))
        print("  " + colorize_menu("s: down"))
        print("  " + colorize_menu("a: left"))
        print("  " + colorize_menu("d: right"))
        print("  " + colorize_menu("0: reset"))
        print("  " + colorize_menu("x: x only"))
        print("  " + colorize_menu("y: y only"))
        print("  " + colorize_menu("(x y): direct"))
        print("  " + colorize_menu("q: back"))
        cmd = safe_input(colorize_prompt("Position (w/s/a/d/0/x/y/(x y)/q): ")).strip().lower()
        if not cmd or cmd == "q":
            break
        x_in, y_in = get_position()
        if cmd == "0":
            push_state("legend-position")
            _set_and_apply((0.0, 0.0), "Legend position reset to center.")
            continue
        if cmd in ("w", "s", "a", "d"):
            push_state("legend-position")
            dx = (-step if cmd == "a" else step if cmd == "d" else 0.0)
            dy = (step if cmd == "w" else -step if cmd == "s" else 0.0)
            _set_and_apply((x_in + dx, y_in + dy))
            continue
        if cmd == "x":
            _axis_submenu("x")
            continue
        if cmd == "y":
            _axis_submenu("y")
            continue
        parts = cmd.replace(",", " ").split()
        if len(parts) != 2:
            print("Need two numbers (e.g. 2.5 3.1) or use w/s/a/d/0/x/y/q.")
            continue
        try:
            direct_x = float(parts[0])
            direct_y = float(parts[1])
        except Exception:
            print("Invalid numbers.")
            continue
        push_state("legend-position")
        _set_and_apply((direct_x, direct_y))


def run_legend_position_menu(
    *,
    fig: Any,
    get_legend: Callable[[], Any],
    get_position: Callable[[], object],
    set_position: Callable[[tuple[float, float]], None],
    sanitize_offset: Callable[[object], tuple[float, float] | None],
    toggle_legend: Callable[[], None],
    apply_position: Callable[[], None],
    push_state: Callable[[str], None],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    step: float = 0.1,
) -> None:
    """Run shared EC/CPC legend visibility and position submenu."""
    if sanitize_offset(get_position()) is None:
        offset = derive_legend_offset_from_current(
            fig=fig,
            legend=get_legend(),
            sanitize_offset=sanitize_offset,
        )
        if offset is not None:
            set_position(offset)

    def _current_position() -> tuple[float, float]:
        return sanitize_offset(get_position()) or (0.0, 0.0)

    legend = get_legend()
    visible = bool(legend.get_visible()) if legend is not None else False
    xy_in = _current_position()
    print(f"Legend is {'ON' if visible else 'off'}; position (inches from center): x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")

    while True:
        print("Legend:")
        print("  " + colorize_menu("t: toggle"))
        print("  " + colorize_menu("p: set position"))
        print("  " + colorize_menu("q: back"))
        sub = safe_input(colorize_prompt("Legend (t/p/q): ")).strip().lower()
        if not sub:
            continue
        if sub == "q":
            break
        if sub == "t":
            push_state("legend-toggle")
            toggle_legend()
            continue
        if sub == "p":
            _legend_position_submenu(
                get_position=_current_position,
                set_position=set_position,
                sanitize_offset=sanitize_offset,
                apply_position=apply_position,
                push_state=push_state,
                safe_input=safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
                step=step,
            )
            continue
        print("Unknown option.")


__all__ = [
    "DEFAULT_FONT_FAMILIES",
    "derive_legend_offset_from_current",
    "run_axis_limit_menu",
    "run_dispatch_menu",
    "run_font_menu",
    "run_legend_position_menu",
    "run_option_menu",
    "run_repeat_input_loop",
]
