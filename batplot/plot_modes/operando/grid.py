"""EC side-panel grid menu helpers for operando mode."""

from __future__ import annotations

from ...color_utils import color_block, resolve_color_token


def get_ec_grid_state(ec_ax) -> dict:
    """Return normalized EC grid state stored on the side-panel axes."""
    grid = getattr(ec_ax, "_ec_grid", None) or {}
    return {
        "visible": grid.get("visible", False),
        "alpha": float(grid.get("alpha", 0.3)),
        "linestyle": str(grid.get("linestyle", "--")),
        "color": str(grid.get("color", "0.6")),
        "which": str(grid.get("which", "major")),
    }


def apply_ec_grid_state(ec_ax, state: dict) -> None:
    """Apply and store EC grid state without changing persistence keys."""
    ec_ax._ec_grid = dict(state)
    ec_ax.grid(
        state["visible"],
        which=state["which"],
        axis="both",
        alpha=state["alpha"],
        color=state["color"],
        linestyle=state["linestyle"],
    )


def run_ec_grid_menu(
    *,
    fig,
    ec_ax,
    snapshot,
    safe_input,
    colorize_prompt,
    colorize_inline_commands,
) -> None:
    """Run the EC grid submenu."""
    if ec_ax is None:
        print("EC panel not available (no .mpt file in folder).")
        return
    try:
        grid_state = get_ec_grid_state(ec_ax)
        print(colorize_inline_commands("EC grid: t=toggle, a=alpha, s=linestyle, c=color, w=which (major/both), q=back"))
        while True:
            print(
                f"  Grid: {'on' if grid_state['visible'] else 'off'}, "
                f"alpha={grid_state['alpha']}, ls={grid_state['linestyle']}, which={grid_state['which']}"
            )
            sub = safe_input(colorize_prompt("EC grid options (t/a/s/c/w/q per line above): ")).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "t":
                snapshot("ec-grid")
                grid_state["visible"] = not grid_state["visible"]
                apply_ec_grid_state(ec_ax, grid_state)
                print(f"Grid: {'on' if grid_state['visible'] else 'off'}")
            elif sub == "a":
                val = safe_input(f"Alpha (0-1, current={grid_state['alpha']}): ").strip()
                if val:
                    try:
                        alpha = max(0.0, min(1.0, float(val)))
                        snapshot("ec-grid")
                        grid_state["alpha"] = alpha
                        apply_ec_grid_state(ec_ax, grid_state)
                        print(f"Alpha: {alpha}")
                    except ValueError:
                        print("Invalid value.")
            elif sub == "s":
                styles = [("-", "solid"), ("--", "dashed"), (":", "dotted"), ("-.", "dashdot")]
                print(colorize_inline_commands("Linestyle: 1=solid, 2=dashed, 3=dotted, 4=dashdot"))
                val = safe_input(f"Choice (current={grid_state['linestyle']}): ").strip()
                if val:
                    if val.isdigit() and 1 <= int(val) <= 4:
                        linestyle = styles[int(val) - 1][0]
                        snapshot("ec-grid")
                        grid_state["linestyle"] = linestyle
                        apply_ec_grid_state(ec_ax, grid_state)
                        print(f"Linestyle: {linestyle}")
                    elif val in ("-", "--", ":", "-."):
                        snapshot("ec-grid")
                        grid_state["linestyle"] = val
                        apply_ec_grid_state(ec_ax, grid_state)
                        print(f"Linestyle: {val}")
                    else:
                        print("Invalid choice.")
            elif sub == "c":
                current = grid_state["color"]
                print(f"Current color: {color_block(current)} {current}")
                val = safe_input("Color (blank=cancel): ").strip()
                if val:
                    resolved = resolve_color_token(val, fig)
                    if resolved:
                        snapshot("ec-grid")
                        grid_state["color"] = resolved
                        apply_ec_grid_state(ec_ax, grid_state)
                        print(f"Color: {resolved}")
                    else:
                        print("Could not resolve color.")
            elif sub == "w":
                val = safe_input(f"Which: major | both (current={grid_state['which']}): ").strip().lower()
                if val in ("major", "both"):
                    snapshot("ec-grid")
                    grid_state["which"] = val
                    apply_ec_grid_state(ec_ax, grid_state)
                    print(f"Which: {val}")
                elif val:
                    print("Use 'major' or 'both'.")
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
    except Exception as exc:
        print(f"Grid failed: {exc}")


__all__ = [
    "apply_ec_grid_state",
    "get_ec_grid_state",
    "run_ec_grid_menu",
]
