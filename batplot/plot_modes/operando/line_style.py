"""EC side-panel line styling menu for operando mode."""

from __future__ import annotations

from ...color_utils import color_block, get_user_color_list, manage_user_colors, resolve_color_token


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

        print("  " + colorize_menu("c: color"))
        print("  " + colorize_menu("l: linewidth"))
        print("  " + colorize_menu("q: back"))
        while True:
            sub = safe_input(colorize_prompt("EC line style (c=color, l=linewidth, q=back): ")).strip().lower()
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
            else:
                print("Unknown option.")
    except Exception as exc:
        print(f"EC line styling failed: {exc}")


def _set_ec_line_color(*, fig, line, snapshot, safe_input, colorize_menu, colorize_prompt) -> None:
    current = line.get_color()
    print(f"EC line color: {color_block(current)} {current}")
    user_colors = get_user_color_list(fig)
    if user_colors:
        print("\nSaved colors (refer as number or u#):")
        for idx, color in enumerate(user_colors, 1):
            print("  " + colorize_menu(f"{idx}: {color_block(color)} {color}"))
    else:
        print("\nNo saved colors.")
        print("  " + colorize_menu("u: manage saved colors"))
    print("  (Enter color name/hex, saved color number, or 'u' to manage)")
    val = safe_input(colorize_prompt(f"Color (current={current}, blank=cancel): ")).strip()
    if not val:
        return
    if val.lower() == "u":
        manage_user_colors(fig)
        return
    snapshot("ec-line-color")
    try:
        resolved = resolve_color_token(val, fig)
        line.set_color(resolved)
        fig.canvas.draw_idle()
        print(f"EC line color set to: {resolved}")
    except Exception as exc:
        print(f"Invalid color: {exc}")


def _set_ec_line_width(*, line, snapshot, safe_input, colorize_prompt) -> None:
    current = line.get_linewidth()
    val = safe_input(colorize_prompt(f"Line width (current={current}, blank=cancel): ")).strip()
    if not val:
        return
    snapshot("ec-line-width")
    try:
        linewidth = float(val)
        if linewidth > 0:
            line.set_linewidth(linewidth)
        else:
            print("Width must be > 0.")
    except Exception as exc:
        print(f"Invalid width: {exc}")


__all__ = ["run_ec_line_style_menu"]
