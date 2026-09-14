"""EC side-panel line styling menu for operando mode."""

from __future__ import annotations

from ...color_utils import format_color_listing, manage_user_colors, prompt_screen_color, blank_means_back, last_screen_pick_count, resolve_color_token
from ..common.curve_look_help import CURVE_LOOK_CHOICES, print_curve_look_legend
from ..common.line_dash import clear_dash_pattern, prompt_dash_pattern, set_dash_pattern
from ..common.menu_rendering import print_menu_key_rows
from ..common.session_helpers import _artist_linewidth


def run_ec_line_style_menu(
    *,
    fig,
    ec_ax,
    snapshot,
    safe_input,
    colorize_menu,
    colorize_prompt,
) -> None:
    """Run the EC line color/width submenu."""
    if ec_ax is None:
        print("EC panel not available (no .mpt file in folder).")
        return
    try:
        line = getattr(ec_ax, "_ec_line", None)
        if line is None and ec_ax.lines:
            line = ec_ax.lines[0]
        if line is None:
            print("No EC line found to style.")
            return

        print_menu_key_rows(
            [
                "c: color",
                "l: linewidth",
                "s: line style (line / dots / dashed / dash-dot)",
                "q: back",
            ],
            colorize=colorize_menu,
        )
        while True:
            sub = safe_input(colorize_prompt("EC line style (c/l/s/q): ")).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "c":
                _set_ec_line_color(
                    fig=fig,
                    line=line,
                    snapshot=snapshot,
                    safe_input=safe_input,
                    colorize_menu=colorize_menu,
                    colorize_prompt=colorize_prompt,
                )
            elif sub == "l":
                _set_ec_line_width(line=line, snapshot=snapshot, safe_input=safe_input, colorize_prompt=colorize_prompt)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            elif sub == "s":
                _set_ec_line_dash_style(
                    fig=fig,
                    line=line,
                    snapshot=snapshot,
                    safe_input=safe_input,
                    colorize_menu=colorize_menu,
                    colorize_prompt=colorize_prompt,
                )
            else:
                print("Unknown option.")
    except Exception as exc:
        print(f"EC line styling failed: {exc}")


def _set_ec_line_color(*, fig, line, snapshot, safe_input, colorize_menu, colorize_prompt) -> None:
    from ..common.color_menu_help import (
        join_cyan_samples_spaced,
        print_color_action_keys,
        print_how_to_set_color_methods,
        print_saved_colors_block,
    )

    while True:
        current = line.get_color()
        print(f"Current EC line color: {format_color_listing(current)}")
        print_how_to_set_color_methods(
            [
                (
                    "Line color (name / #hex / saved index)",
                    join_cyan_samples_spaced("red", "#00FF00", "u3"),
                ),
            ]
        )
        print_saved_colors_block(fig, colorize_menu=colorize_menu)
        print_color_action_keys(colorize_menu=colorize_menu, include_v=False)
        val = safe_input(colorize_prompt("Selection: ")).strip()
        if val.lower() == "q" or blank_means_back(val):
            break
        if val.lower() == "u":
            manage_user_colors(fig)
            continue
        if val.lower() == "e":
            picked = prompt_screen_color(fig)
            if not picked:
                continue
            if last_screen_pick_count() > 1:
                continue
            snapshot("ec-line-color")
            try:
                line.set_color(picked)
                fig.canvas.draw_idle()
                print(f"EC line color set to: {format_color_listing(picked)}")
            except Exception as exc:
                print(f"Invalid color: {exc}")
            continue
        try:
            resolved = resolve_color_token(val, fig)
        except Exception as exc:
            print(f"Invalid color: {exc}")
            continue
        snapshot("ec-line-color")
        try:
            line.set_color(resolved)
            fig.canvas.draw_idle()
            print(f"EC line color set to: {format_color_listing(resolved)}")
        except Exception as exc:
            print(f"Invalid color: {exc}")


def _set_ec_line_dash_style(*, fig, line, snapshot, safe_input, colorize_menu, colorize_prompt) -> None:
    """Apply line/dots/dashed presets to the EC voltage curve (same keys as XY/EC)."""
    print_curve_look_legend(scope="EC curve")
    print_menu_key_rows(["q: back"], colorize=colorize_menu)
    sub = safe_input(colorize_prompt(f"Choose ({CURVE_LOOK_CHOICES}/q): ")).strip().lower()
    if not sub or sub == "q":
        return
    if sub == "l":
        snapshot("ec-line-style")
        line.set_linestyle("-")
        clear_dash_pattern(line)
        line.set_marker("None")
        print("Applied line-only style to EC curve.")
    elif sub in ("ld", "d"):
        while True:
            raw = safe_input("Marker size (blank=auto ~3*lw, q=back): ").strip().lower()
            if raw == "q":
                return
            custom_msize = None
            if raw:
                try:
                    custom_msize = float(raw)
                except ValueError:
                    print("Invalid marker size.")
                    continue
            snapshot("ec-line-style")
            lw = _artist_linewidth(line)
            line.set_linestyle("-" if sub == "ld" else "None")
            clear_dash_pattern(line)
            line.set_marker("o")
            msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
            line.set_markersize(msize)
            try:
                color = line.get_color()
                line.set_markerfacecolor(color)
                line.set_markeredgecolor(color)
            except Exception:
                pass
            print(f"Applied {'line+dots' if sub == 'ld' else 'dots-only'} style to EC curve.")
            break
    elif sub in ("da", "dd"):
        dash_vals = prompt_dash_pattern(safe_input, kind="dashdot" if sub == "dd" else "dash")
        if dash_vals is None:
            return
        snapshot("ec-line-style")
        line.set_marker("None")
        set_dash_pattern(line, dash_vals)
        print(f"Applied {'dash-dot' if sub == 'dd' else 'dashed'} line to EC curve.")
    else:
        print("Unknown option.")
        return
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def _set_ec_line_width(*, line, snapshot, safe_input, colorize_prompt) -> None:
    while True:
        current = line.get_linewidth()
        val = safe_input(colorize_prompt(f"Line width (current={current}, q=back): ")).strip()
        if not val or val.lower() == "q":
            break
        try:
            linewidth = float(val)
            if linewidth <= 0:
                print("Width must be > 0.")
                continue
        except Exception as exc:
            print(f"Invalid width: {exc}")
            continue
        snapshot("ec-line-width")
        line.set_linewidth(linewidth)
        print(f"EC line width set to {linewidth:g}.")


__all__ = ["run_ec_line_style_menu"]
