"""Unified ``g: size`` submenu for operando (+ optional EC) interactive and batch modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from ..common.size_spec import parse_positive_float, parse_size_spec
from ..common.terminal import colorize_prompt, safe_input
from .layout import (
    _apply_group_layout_inches,
    _ensure_fixed_params,
    _get_fig_size,
    _redraw_operando_cif_if_present,
)

MIN_PANEL_IN = 0.25
MIN_CANVAS_IN = 1.0


@dataclass
class OperandoLayoutInches:
    """Fixed inch geometry for colorbar + operando + optional EC panel."""

    cb_w_in: float
    cb_gap_in: float
    ec_gap_in: float
    ec_w_in: float
    op_w_in: float
    op_h_in: float

    @classmethod
    def read(cls, fig, ax, cbar_ax, ec_ax) -> OperandoLayoutInches:
        cb_w, cb_gap, ec_gap, ec_w, op_w, op_h = _ensure_fixed_params(fig, ax, cbar_ax, ec_ax)
        return cls(cb_w, cb_gap, ec_gap, ec_w, op_w, op_h)

    def apply(self, fig, ax, cbar_ax, ec_ax) -> None:
        _apply_group_layout_inches(
            fig,
            ax,
            cbar_ax,
            ec_ax,
            self.op_w_in,
            self.op_h_in,
            self.cb_w_in,
            self.cb_gap_in,
            self.ec_gap_in,
            self.ec_w_in,
        )


def apply_canvas_preserving_panels(
    fig,
    ax,
    cbar_ax,
    ec_ax,
    canvas_w: float,
    canvas_h: float,
) -> OperandoLayoutInches:
    """Resize figure canvas while keeping panel inch dimensions unchanged."""
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    fig.set_size_inches(max(MIN_CANVAS_IN, canvas_w), max(MIN_CANVAS_IN, canvas_h), forward=True)
    layout.apply(fig, ax, cbar_ax, ec_ax)
    return layout


def apply_operando_width(
    fig, ax, cbar_ax, ec_ax, width_in: float,
) -> OperandoLayoutInches:
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    layout.op_w_in = max(MIN_PANEL_IN, width_in)
    layout.apply(fig, ax, cbar_ax, ec_ax)
    return layout


def apply_ec_width(
    fig, ax, cbar_ax, ec_ax, width_in: float,
) -> OperandoLayoutInches:
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    layout.ec_w_in = max(MIN_PANEL_IN, width_in)
    layout.apply(fig, ax, cbar_ax, ec_ax)
    return layout


def apply_shared_panel_height(
    fig, ax, cbar_ax, ec_ax, height_in: float,
) -> OperandoLayoutInches:
    """Set shared height for operando contour, colorbar, and EC side panel."""
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    layout.op_h_in = max(MIN_PANEL_IN, height_in)
    layout.apply(fig, ax, cbar_ax, ec_ax)
    return layout


def apply_layout_scale(
    fig, ax, cbar_ax, ec_ax, factor: float,
) -> OperandoLayoutInches:
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    f = max(0.05, float(factor))
    layout.cb_w_in *= f
    layout.cb_gap_in *= f
    layout.ec_gap_in *= f
    layout.ec_w_in *= f
    layout.op_w_in *= f
    layout.op_h_in *= f
    layout.apply(fig, ax, cbar_ax, ec_ax)
    cur_w, cur_h = _get_fig_size(fig)
    apply_canvas_preserving_panels(fig, ax, cbar_ax, ec_ax, cur_w * f, cur_h * f)
    return OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)


def panel_heights_inches(fig, ax, cbar_ax, ec_ax) -> tuple[float, float, float]:
    """Return operando, colorbar, EC vertical sizes in inches."""
    fw, fh = _get_fig_size(fig)
    op_h = ax.get_position().height * fh
    cb_h = cbar_ax.get_position().height * fh
    ec_h = ec_ax.get_position().height * fh if ec_ax is not None else op_h
    return float(op_h), float(cb_h), float(ec_h)


def print_operando_layout_status(
    fig,
    ax,
    cbar_ax,
    ec_ax,
    *,
    title: str = "Current sizes",
) -> None:
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    cw, ch = _get_fig_size(fig)
    print(f"\n── {title} ──")
    print(f"  Canvas (figure):     {cw:.2f} x {ch:.2f} in")
    print(
        f"  Operando (contour):  {layout.op_w_in:.2f} x {layout.op_h_in:.2f} in  (width x height)"
    )
    print(f"  Colorbar:            {layout.cb_w_in:.2f} in wide")
    if ec_ax is not None:
        print(
            f"  EC side panel:       {layout.ec_w_in:.2f} x {layout.op_h_in:.2f} in  (width x height)"
        )
    print("  (Height is shared: contour, colorbar, and EC use the same panel height.)")


def _print_batch_layout_status(panels: Sequence, *, title: str) -> None:
    from ..batch_session.batch_menu_helpers import summarize_values

    if not panels:
        return
    ref = panels[0]
    fig, ax, cbar_ax, ec_ax = ref.fig, ref.ax, ref.cbar.ax, ref.ec_ax
    layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
    canvases = [p.fig.get_size_inches() for p in panels]
    cw_text = summarize_values([f"{w:.2f}x{h:.2f}" for w, h in canvases], fmt="{}")
    op_w = summarize_values(
        [OperandoLayoutInches.read(p.fig, p.ax, p.cbar.ax, p.ec_ax).op_w_in for p in panels]
    )
    op_h = summarize_values(
        [OperandoLayoutInches.read(p.fig, p.ax, p.cbar.ax, p.ec_ax).op_h_in for p in panels]
    )
    print(f"\n── {title} ──")
    print(f"  Canvas (figure):     {cw_text} in")
    print(f"  Operando (contour):  {op_w} x {op_h} in  (width x height)")
    print(f"  Colorbar:            {layout.cb_w_in:.2f} in wide")
    if ec_ax is not None:
        ec_w = summarize_values(
            [OperandoLayoutInches.read(p.fig, p.ax, p.cbar.ax, p.ec_ax).ec_w_in for p in panels]
        )
        print(f"  EC side panel:       {ec_w} x {op_h} in  (width x height)")
    print("  (New values apply to ALL plots; height syncs contour, colorbar, and EC.)")


def _size_submenu_options(ec_ax, *, colorize_menu: Callable[[str], str]) -> None:
    print("  " + colorize_menu("c: canvas size (W x H)"))
    print("  " + colorize_menu("o: operando / contour width"))
    if ec_ax is not None:
        print("  " + colorize_menu("e: EC side panel width"))
    print("  " + colorize_menu("h: panel height (contour + colorbar + EC)"))
    print("  " + colorize_menu("s: scale all layout (e.g. scale=1.2)"))
    print("  " + colorize_menu("q: back"))


def normalize_size_focus(focus: str | None) -> str | None:
    """Map legacy top-level keys (``ow``/``ew``/``h``) to submenu letters."""
    if not focus:
        return None
    key = focus.strip().lower()
    legacy = {"ow": "o", "ew": "e", "op": "o", "contour": "o"}
    return legacy.get(key, key)


def _parse_scale_factor(spec: str) -> float | None:
    raw = (spec or "").strip().lower()
    if not raw or raw == "q":
        return None
    if "scale=" in raw:
        try:
            factor = float(raw.split("scale=", 1)[1].strip())
        except ValueError:
            print("Invalid scale factor.")
            return None
    else:
        try:
            factor = float(raw)
        except ValueError:
            print("Invalid scale factor.")
            return None
    if factor <= 0:
        print("Scale factor must be positive.")
        return None
    return factor


def _apply_size_all_panels(panels: Sequence, action: str, value) -> None:
    for panel in panels:
        cbar_ax = panel.cbar.ax
        fig, ax, ec_ax = panel.fig, panel.ax, panel.ec_ax
        if action == "canvas":
            w, h = value
            apply_canvas_preserving_panels(fig, ax, cbar_ax, ec_ax, w, h)
        elif action == "op_w":
            apply_operando_width(fig, ax, cbar_ax, ec_ax, value)
        elif action == "ec_w":
            apply_ec_width(fig, ax, cbar_ax, ec_ax, value)
        elif action == "height":
            apply_shared_panel_height(fig, ax, cbar_ax, ec_ax, value)
        elif action == "scale":
            apply_layout_scale(fig, ax, cbar_ax, ec_ax, value)
        _redraw_operando_cif_if_present(fig, ax)


def run_operando_size_menu(
    fig,
    ax,
    cbar,
    ec_ax,
    *,
    on_before_change: Callable[[], None],
    on_after_change: Callable[[], None],
    safe_input_fn: Callable = safe_input,
    colorize_menu_fn: Callable[[str], str],
    colorize_prompt_fn: Callable[[str], str] = colorize_prompt,
    initial_focus: str | None = None,
) -> OperandoLayoutInches:
    """Interactive ``g: size`` submenu for a single operando figure."""
    cbar_ax = cbar.ax
    focus = normalize_size_focus(initial_focus)

    def _change(action: str) -> bool:
        layout = OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)
        if action == "c":
            cur_w, cur_h = _get_fig_size(fig)
            spec = safe_input_fn(
                colorize_prompt_fn(
                    "Canvas size (e.g. '11 6', '6x4', 'w=11 h=6', q=back): "
                ),
                cancel_on_interrupt=True,
            ).strip()
            if not spec or spec.lower() == "q":
                return False
            parsed = parse_size_spec(spec, cur_w, cur_h)
            if parsed is None:
                return True
            new_w, new_h = max(MIN_CANVAS_IN, parsed[0]), max(MIN_CANVAS_IN, parsed[1])
            on_before_change()
            apply_canvas_preserving_panels(fig, ax, cbar_ax, ec_ax, new_w, new_h)
            on_after_change()
            print(f"Canvas set to {new_w:.2f} x {new_h:.2f} in (panel inches preserved).")
            return True
        if action == "o":
            print(f"Current operando width: {layout.op_w_in:.2f} in")
            val = parse_positive_float(
                safe_input_fn(colorize_prompt_fn("Operando width inches (q=back): ")).strip(),
                label="width",
            )
            if val is None:
                return False
            on_before_change()
            apply_operando_width(fig, ax, cbar_ax, ec_ax, val)
            on_after_change()
            print(f"Operando width set to {val:.2f} in.")
            return True
        if action == "e":
            if ec_ax is None:
                print("EC side panel not available.")
                return True
            print(f"Current EC width: {layout.ec_w_in:.2f} in")
            val = parse_positive_float(
                safe_input_fn(colorize_prompt_fn("EC width inches (q=back): ")).strip(),
                label="width",
            )
            if val is None:
                return False
            on_before_change()
            apply_ec_width(fig, ax, cbar_ax, ec_ax, val)
            on_after_change()
            print(f"EC width set to {val:.2f} in.")
            return True
        if action == "h":
            print(f"Current panel height: {layout.op_h_in:.2f} in")
            val = parse_positive_float(
                safe_input_fn(
                    colorize_prompt_fn(
                        "Panel height inches (contour + colorbar + EC, q=back): "
                    )
                ).strip(),
                label="height",
            )
            if val is None:
                return False
            on_before_change()
            apply_shared_panel_height(fig, ax, cbar_ax, ec_ax, val)
            on_after_change()
            op_h, cb_h, ec_h = panel_heights_inches(fig, ax, cbar_ax, ec_ax)
            print(
                f"Panel height set to {val:.2f} in "
                f"(contour {op_h:.2f}, colorbar {cb_h:.2f}, EC {ec_h:.2f} in)."
            )
            return True
        if action == "s":
            factor = _parse_scale_factor(
                safe_input_fn(
                    colorize_prompt_fn("Scale factor (e.g. 1.2 or scale=0.8, q=back): ")
                ).strip()
            )
            if factor is None:
                return False
            on_before_change()
            apply_layout_scale(fig, ax, cbar_ax, ec_ax, factor)
            on_after_change()
            print(f"Layout scaled by {factor:.3g}.")
            return True
        return True

    if focus in ("c", "o", "e", "h", "s"):
        _change(focus)
        _redraw_operando_cif_if_present(fig, ax)
        return OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)

    while True:
        print_operando_layout_status(fig, ax, cbar_ax, ec_ax)
        _size_submenu_options(ec_ax, colorize_menu=colorize_menu_fn)
        choice = safe_input_fn(colorize_prompt_fn("Size (c/o/e/h/s/q): ")).strip().lower()
        if not choice or choice == "q":
            break
        if choice not in ("c", "o", "e", "h", "s"):
            print("Unknown option.")
            continue
        _change(choice)

    _redraw_operando_cif_if_present(fig, ax)
    return OperandoLayoutInches.read(fig, ax, cbar_ax, ec_ax)


def run_operando_batch_size_menu(
    panels: Sequence,
    *,
    push_undo: Callable[[], None],
    draw_all: Callable[[], None],
    safe_input_fn: Callable = safe_input,
    colorize_menu_fn: Callable[[str], str],
    colorize_prompt_fn: Callable[[str], str] = colorize_prompt,
    initial_focus: str | None = None,
) -> None:
    """Batch ``g: size`` submenu — applies the same inch values to every panel."""
    if not panels:
        return
    ref = panels[0]
    ec_ax = ref.ec_ax
    focus = normalize_size_focus(initial_focus)

    def _mutate(action: str, value) -> None:
        push_undo()
        _apply_size_all_panels(panels, action, value)
        draw_all()

    def _change(action: str) -> bool:
        from ..batch_session.batch_menu_helpers import print_batch_scalar_status
        from ..batch_session.operando_batch_helpers import panel_layout_inches

        if action == "c":
            cur_w, cur_h = _get_fig_size(ref.fig)
            spec = safe_input_fn(
                colorize_prompt_fn(
                    "Canvas size for ALL plots (e.g. '11 6', '6x4', q=back): "
                ),
                cancel_on_interrupt=True,
            ).strip()
            if not spec or spec.lower() == "q":
                return False
            parsed = parse_size_spec(spec, cur_w, cur_h)
            if parsed is None:
                return True
            w, h = max(MIN_CANVAS_IN, parsed[0]), max(MIN_CANVAS_IN, parsed[1])
            _mutate("canvas", (w, h))
            print(f"Canvas set to {w:.2f} x {h:.2f} in on all {len(panels)} plots.")
            return True
        if action == "o":
            print_batch_scalar_status(
                panels,
                label="operando width",
                get_value=lambda p: panel_layout_inches(p)[4],
                fmt="{:.2f}",
                unit="in",
            )
            val = parse_positive_float(
                safe_input_fn(colorize_prompt_fn("Operando width for ALL (q=back): ")).strip(),
                label="width",
            )
            if val is None:
                return False
            _mutate("op_w", val)
            print(f"Operando width set to {val:.2f} in on all plots.")
            return True
        if action == "e":
            if ec_ax is None:
                print("EC side panel not available.")
                return True
            print_batch_scalar_status(
                panels,
                label="EC width",
                get_value=lambda p: panel_layout_inches(p)[3],
                fmt="{:.2f}",
                unit="in",
            )
            val = parse_positive_float(
                safe_input_fn(colorize_prompt_fn("EC width for ALL (q=back): ")).strip(),
                label="width",
            )
            if val is None:
                return False
            _mutate("ec_w", val)
            print(f"EC width set to {val:.2f} in on all plots.")
            return True
        if action == "h":
            print_batch_scalar_status(
                panels,
                label="panel height",
                get_value=lambda p: panel_layout_inches(p)[5],
                fmt="{:.2f}",
                unit="in",
            )
            val = parse_positive_float(
                safe_input_fn(
                    colorize_prompt_fn(
                        "Panel height for ALL (contour + colorbar + EC, q=back): "
                    )
                ).strip(),
                label="height",
            )
            if val is None:
                return False
            _mutate("height", val)
            print(f"Panel height set to {val:.2f} in on all plots.")
            return True
        if action == "s":
            factor = _parse_scale_factor(
                safe_input_fn(colorize_prompt_fn("Scale for ALL (e.g. 1.2, q=back): ")).strip()
            )
            if factor is None:
                return False
            _mutate("scale", factor)
            print(f"Layout scaled by {factor:.3g} on all plots.")
            return True
        return True

    if focus in ("c", "o", "e", "h", "s"):
        _change(focus)
        return

    while True:
        _print_batch_layout_status(panels, title="Size (all plots)")
        _size_submenu_options(ec_ax, colorize_menu=colorize_menu_fn)
        choice = safe_input_fn(colorize_prompt_fn("Size (c/o/e/h/s/q): ")).strip().lower()
        if not choice or choice == "q":
            break
        if choice not in ("c", "o", "e", "h", "s"):
            print("Unknown option.")
            continue
        _change(choice)


__all__ = [
    "OperandoLayoutInches",
    "apply_canvas_preserving_panels",
    "apply_ec_width",
    "apply_layout_scale",
    "apply_operando_width",
    "apply_shared_panel_height",
    "normalize_size_focus",
    "panel_heights_inches",
    "print_operando_layout_status",
    "run_operando_batch_size_menu",
    "run_operando_size_menu",
]
