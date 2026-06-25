"""Line, marker, frame, and grid submenu for EC interactive mode."""

from __future__ import annotations

from typing import Any, Callable

from ..common.spines import apply_frame_and_tick_widths, current_tick_width, parse_frame_tick_widths


def run_ec_line_style_menu(
    *,
    fig: Any,
    ax: Any,
    cycle_lines: dict,
    file_data: list[dict],
    current_file_idx: int,
    is_multi_file: bool,
    is_dqdv: bool,
    print_file_list: Callable[..., Any],
    iter_cycle_lines: Callable[..., Any],
    rebuild_legend: Callable[[Any], Any],
    apply_stored_smooth_settings: Callable[..., Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Run the EC line submenu previously owned by the main dispatcher."""
    try:
        line_target_list = [cycle_lines]
        if is_multi_file:
            print_file_list(file_data, current_file_idx)
            choice = safe_input(f"Select file numbers (1-{len(file_data)}), all (a), or q=cancel: ").strip().lower()
            if choice == "q":
                print_file_list(file_data, current_file_idx)
                return
            if choice in ("a", "all"):
                line_target_list = [f["cycle_lines"] for f in file_data if f.get("visible", True)]
            else:
                try:
                    idx = int(choice)
                    if 1 <= idx <= len(file_data):
                        line_target_list = [file_data[idx - 1]["cycle_lines"]]
                    else:
                        print("Invalid file number.")
                        return
                except ValueError:
                    print("Invalid input.")
                    return
        while True:
            _print_line_summary(fig, ax, line_target_list, iter_cycle_lines)
            print("\033[1mLine submenu:\033[0m")
            print(f"  {colorize_menu('c  : change curve line widths')}")
            print(f"  {colorize_menu('f  : change frame (axes spines) and tick widths')}")
            print(f"  {colorize_menu('g  : toggle grid lines')}")
            print(f"  {colorize_menu('l  : show only lines (no markers) for all curves')}")
            print(f"  {colorize_menu('ld : show line and dots (markers) for all curves')}")
            print(f"  {colorize_menu('d  : show only dots (no connecting line) for all curves')}")
            print(f"  {colorize_menu('q  : return')}")
            sub = safe_input(colorize_prompt("Choose (c/f/g/l/ld/d/q): ")).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "c":
                _set_curve_linewidth(
                    fig=fig,
                    ax=ax,
                    line_target_list=line_target_list,
                    iter_cycle_lines=iter_cycle_lines,
                    rebuild_legend=rebuild_legend,
                    push_state=push_state,
                    safe_input=safe_input,
                )
            elif sub == "f":
                _set_frame_tick_widths(fig=fig, ax=ax, push_state=push_state, safe_input=safe_input)
            elif sub == "g":
                _toggle_grid(fig=fig, ax=ax, push_state=push_state)
            elif sub in ("l", "ld", "d"):
                _apply_curve_style(
                    fig=fig,
                    ax=ax,
                    line_target_list=line_target_list,
                    style=sub,
                    iter_cycle_lines=iter_cycle_lines,
                    rebuild_legend=rebuild_legend,
                    push_state=push_state,
                    safe_input=safe_input,
                    is_dqdv=is_dqdv,
                    apply_stored_smooth_settings=apply_stored_smooth_settings,
                )
            else:
                print("Unknown option.")
    except Exception as exc:
        print(f"Error in line submenu: {exc}")


def _print_line_summary(fig: Any, ax: Any, line_target_list: list, iter_cycle_lines: Callable[..., Any]) -> None:
    try:
        cur_sp_lw = {
            name: (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None)
            for name in ("bottom", "top", "left", "right")
        }
    except Exception:
        cur_sp_lw = {}
    x_maj = current_tick_width(ax.xaxis, "major")
    x_min = current_tick_width(ax.xaxis, "minor")
    y_maj = current_tick_width(ax.yaxis, "major")
    y_min = current_tick_width(ax.yaxis, "minor")
    cur_curve_lw = getattr(fig, "_ec_curve_linewidth", None)
    if cur_curve_lw is None:
        try:
            for target_lines in line_target_list:
                for _cyc, _role, line in iter_cycle_lines(target_lines):
                    try:
                        cur_curve_lw = float(line.get_linewidth() or 1.0)
                        break
                    except Exception:
                        pass
                if cur_curve_lw is not None:
                    break
        except Exception:
            pass
    print("Line widths:")
    if cur_sp_lw:
        print(
            "  Frame spines lw:",
            " ".join(f"{k}={v:.3g}" if isinstance(v, (int, float)) else f"{k}=?" for k, v in cur_sp_lw.items()),
        )
    print(
        f"  Tick widths: xM={x_maj if x_maj is not None else '?'} "
        f"xm={x_min if x_min is not None else '?'} "
        f"yM={y_maj if y_maj is not None else '?'} ym={y_min if y_min is not None else '?'}"
    )
    if cur_curve_lw is not None:
        print(f"  Curves (all): {cur_curve_lw:.3g}")


def _set_curve_linewidth(*, fig: Any, ax: Any, line_target_list: list, iter_cycle_lines, rebuild_legend, push_state, safe_input) -> None:
    spec = safe_input("Curve linewidth (single value for all curves, q=cancel): ").strip()
    if not spec or spec.lower() == "q":
        return
    try:
        push_state("curve-linewidth")
        linewidth = float(spec)
        setattr(fig, "_ec_curve_linewidth", linewidth)
        for target_lines in line_target_list:
            for _cyc, _role, line in iter_cycle_lines(target_lines):
                try:
                    line.set_linewidth(linewidth)
                except Exception:
                    pass
        _redraw_with_legend(fig, ax, rebuild_legend)
        print(f"Set all curve linewidths to {linewidth}")
    except ValueError:
        print("Invalid width value.")


def _set_frame_tick_widths(*, fig: Any, ax: Any, push_state, safe_input) -> None:
    value = safe_input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q: ").strip()
    if not value or value.lower() == "q":
        print("Canceled.")
        return
    try:
        push_state("framewidth")
        frame_w, tick_major, tick_minor = parse_frame_tick_widths(value)
        apply_frame_and_tick_widths([ax], frame_width=frame_w, major_width=tick_major, minor_width=tick_minor)
        fig.canvas.draw()
        print(f"Set frame width={frame_w}, major tick width={tick_major}, minor tick width={tick_minor}")
    except ValueError:
        print("Invalid numeric value(s).")


def _toggle_grid(*, fig: Any, ax: Any, push_state) -> None:
    push_state("grid")
    current_grid = False
    try:
        for line in ax.get_xgridlines() + ax.get_ygridlines():
            if line.get_visible():
                current_grid = True
                break
    except Exception:
        current_grid = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, "_gridOnMajor") else False
    new_grid_state = not current_grid
    if new_grid_state:
        ax.grid(True, color="0.85", linestyle="-", linewidth=0.5, alpha=0.7)
    else:
        ax.grid(False)
    fig.canvas.draw()
    print(f"Grid {'enabled' if new_grid_state else 'disabled'}.")


def _apply_curve_style(
    *,
    fig: Any,
    ax: Any,
    line_target_list: list,
    style: str,
    iter_cycle_lines,
    rebuild_legend,
    push_state,
    safe_input,
    is_dqdv: bool,
    apply_stored_smooth_settings,
) -> None:
    if style == "l":
        push_state("line-only")
        _style_lines(line_target_list, iter_cycle_lines, linestyle="-", marker="None")
        _redraw_with_legend(fig, ax, rebuild_legend)
        print("Applied line-only style to all curves.")
        return

    state_name = "line+dots" if style == "ld" else "dots-only"
    message = "Applied line+dots style to all curves." if style == "ld" else "Applied dots-only style to all curves."
    push_state(state_name)
    try:
        marker_size_input = safe_input("Marker size (blank=auto ~3*lw): ").strip()
        custom_marker_size = float(marker_size_input) if marker_size_input else None
    except ValueError:
        custom_marker_size = None
    _style_lines(
        line_target_list,
        iter_cycle_lines,
        linestyle="-" if style == "ld" else "None",
        marker="o",
        custom_marker_size=custom_marker_size,
    )
    if is_dqdv and hasattr(fig, "_dqdv_smooth_settings"):
        for target_lines in line_target_list:
            apply_stored_smooth_settings(target_lines, fig)
    _redraw_with_legend(fig, ax, rebuild_legend)
    print(message)


def _style_lines(line_target_list: list, iter_cycle_lines, *, linestyle: str, marker: str, custom_marker_size: float | None = None) -> None:
    for target_lines in line_target_list:
        for _cyc, _role, line in iter_cycle_lines(target_lines):
            try:
                if linestyle == "-" and marker == "None":
                    current_ls = line.get_linestyle()
                    current_marker = line.get_marker()
                    if current_ls not in ["None", "", " ", "none"] and current_marker in ["None", "", " ", "none", None]:
                        continue
                linewidth = line.get_linewidth() or 1.0
                line.set_linestyle(linestyle)
                line.set_marker(marker)
                if marker != "None":
                    marker_size = custom_marker_size if custom_marker_size is not None else max(3.0, linewidth * 3.0)
                    line.set_markersize(marker_size)
                    color = line.get_color()
                    line.set_markerfacecolor(color)
                    line.set_markeredgecolor(color)
            except Exception:
                pass


def _redraw_with_legend(fig: Any, ax: Any, rebuild_legend) -> None:
    try:
        rebuild_legend(ax)
        fig.canvas.draw()
    except Exception:
        try:
            rebuild_legend(ax)
        except Exception:
            pass
        fig.canvas.draw_idle()


__all__ = ["run_ec_line_style_menu"]
