"""Visibility and colorbar-position menu for operando mode."""

from __future__ import annotations

from .layout import _apply_group_layout_inches, _ensure_fixed_params, _update_custom_colorbar


def run_visibility_menu(
    *,
    fig,
    ax,
    im,
    cbar,
    ec_ax,
    snapshot,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
) -> None:
    """Run the `v` visibility/colorbar submenu."""
    snapshot("toggle-visibility")
    try:
        if ec_ax is not None:
            _run_dual_panel_visibility_menu(
                fig=fig,
                ax=ax,
                im=im,
                cbar=cbar,
                ec_ax=ec_ax,
                snapshot=snapshot,
                safe_input=safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
            )
        else:
            _run_operando_only_visibility_menu(
                fig=fig,
                ax=ax,
                im=im,
                cbar=cbar,
                ec_ax=ec_ax,
                snapshot=snapshot,
                safe_input=safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
                colorize_inline_commands=colorize_inline_commands,
            )
        fig.canvas.draw_idle()
    except Exception as exc:
        print(f"Error toggling visibility: {exc}")


def _run_dual_panel_visibility_menu(*, fig, ax, im, cbar, ec_ax, snapshot, safe_input, colorize_menu, colorize_prompt) -> None:
    cb_h_offset = getattr(cbar.ax, "_cb_h_offset_in", 0.0)
    ec_h_offset = getattr(ec_ax, "_ec_h_offset_in", 0.0)
    print(f"  Colorbar offset: {cb_h_offset:.3f}\", EC offset: {ec_h_offset:.3f}\"")
    print("  " + colorize_menu("1: toggle colorbar"))
    print("  " + colorize_menu("2: toggle EC panel"))
    print("  " + colorize_menu("3: toggle both"))
    print("  " + colorize_menu("4: colorbar label mode"))
    print("  " + colorize_menu("5: colorbar label text"))
    print("  " + colorize_menu("m: move horizontal position"))
    print("  " + colorize_menu("q: back"))
    choice = safe_input(colorize_prompt("Visibility & colorbar (1-5, m=move offsets, q=back to main menu): ")).strip().lower()
    if choice == "1":
        cb_vis = cbar.ax.get_visible()
        cbar.ax.set_visible(not cb_vis)
        print(f"Colorbar: {'hidden' if cb_vis else 'shown'}")
    elif choice == "2":
        ec_vis = ec_ax.get_visible()
        ec_ax.set_visible(not ec_vis)
        print(f"EC panel: {'hidden' if ec_vis else 'shown'}")
    elif choice == "3":
        cb_vis = cbar.ax.get_visible()
        ec_vis = ec_ax.get_visible()
        new_vis = not (cb_vis and ec_vis)
        cbar.ax.set_visible(new_vis)
        ec_ax.set_visible(new_vis)
        print(f"Colorbar & EC panel: {'shown' if new_vis else 'hidden'}")
    elif choice == "4":
        _toggle_colorbar_label_mode(fig=fig, im=im, cbar=cbar)
    elif choice == "5":
        _set_colorbar_label_text(im=im, cbar=cbar, safe_input=safe_input)
    elif choice == "m":
        snapshot("move-horizontal-position")
        _run_horizontal_position_menu(
            fig=fig,
            ax=ax,
            cbar=cbar,
            ec_ax=ec_ax,
            safe_input=safe_input,
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
            allow_ec=True,
        )
    elif choice != "q":
        print("Invalid choice")


def _run_operando_only_visibility_menu(
    *,
    fig,
    ax,
    im,
    cbar,
    ec_ax,
    snapshot,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
) -> None:
    cb_h_offset = getattr(cbar.ax, "_cb_h_offset_in", 0.0)
    print(colorize_inline_commands(f"Toggle: 1=colorbar visibility, 2=colorbar label mode, 3=colorbar label text, m=move horizontal position (cb:{cb_h_offset:.3f}\"), q=cancel"))
    choice = safe_input(colorize_prompt("Visibility & colorbar (1-3/m per list above, q=cancel): ")).strip().lower()
    if choice == "1":
        cb_vis = cbar.ax.get_visible()
        cbar.ax.set_visible(not cb_vis)
        print(f"Colorbar: {'hidden' if cb_vis else 'shown'}")
    elif choice == "2":
        _toggle_colorbar_label_mode(fig=fig, im=im, cbar=cbar)
    elif choice == "3":
        _set_colorbar_label_text(im=im, cbar=cbar, safe_input=safe_input)
    elif choice == "m":
        snapshot("move-horizontal-position")
        _run_horizontal_position_menu(
            fig=fig,
            ax=ax,
            cbar=cbar,
            ec_ax=ec_ax,
            safe_input=safe_input,
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
            allow_ec=False,
        )
    elif choice != "q":
        print("Invalid choice")


def _toggle_colorbar_label_mode(*, fig, im, cbar) -> None:
    current_mode = getattr(fig, "_colorbar_label_mode", "highlow")
    new_mode = "normal" if current_mode == "highlow" else "highlow"
    fig._colorbar_label_mode = new_mode
    try:
        _update_custom_colorbar(cbar.ax, im, label_mode=new_mode)
    except Exception:
        pass
    print(f"Colorbar labels: {'High/Low mode' if new_mode == 'highlow' else 'Normal mode'}")


def _set_colorbar_label_text(*, im, cbar, safe_input) -> None:
    current_label = getattr(cbar.ax, "_colorbar_label", "Intensity")
    print(f"Current colorbar label: {current_label}")
    new_label = safe_input("New colorbar label (blank to keep): ").strip()
    if new_label:
        cbar.ax._colorbar_label = new_label
        try:
            _update_custom_colorbar(cbar.ax, im, label=new_label)
        except Exception:
            pass
        print(f"Colorbar label set to: {new_label}")
    else:
        print("Label unchanged")


def _fig_dpi(fig) -> float:
    try:
        return float(fig.dpi)
    except Exception:
        return 72.0


def _apply_h_offset_and_layout(*, fig, ax, cbar, ec_ax, target_ax, attr: str, offset_in: float) -> None:
    setattr(target_ax, attr, float(offset_in))
    cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
    fig.canvas.draw_idle()


def _run_single_h_offset_menu(
    *,
    fig,
    ax,
    cbar,
    ec_ax,
    safe_input,
    colorize_menu,
    colorize_prompt,
    panel_label: str,
    target_ax,
    attr: str,
) -> None:
    """Edit one horizontal offset with pixel nudges (a/d) or direct inches."""
    while True:
        current = float(getattr(target_ax, attr, 0.0) or 0.0)
        dpi = _fig_dpi(fig)
        px_equiv = current * dpi
        print(f"\n{panel_label} horizontal offset: {current:.4f}\" ({px_equiv:+.2f} px, + = right)")
        print("  " + colorize_menu("a: left 1 px"))
        print("  " + colorize_menu("d: right 1 px"))
        print("  " + colorize_menu("number: set offset in inches"))
        print("  " + colorize_menu("q: back"))
        raw = safe_input(colorize_prompt(f"{panel_label} (a/d/number/q): ")).strip().lower()
        if not raw or raw == "q":
            break
        px_step = 1.0 / dpi
        if raw == "a":
            new_offset = current - px_step
        elif raw == "d":
            new_offset = current + px_step
        else:
            try:
                new_offset = float(raw)
            except ValueError:
                print("Invalid input. Use a/d, a number (inches), or q.")
                continue
        try:
            _apply_h_offset_and_layout(
                fig=fig,
                ax=ax,
                cbar=cbar,
                ec_ax=ec_ax,
                target_ax=target_ax,
                attr=attr,
                offset_in=new_offset,
            )
            print(
                f"{panel_label} horizontal offset set to {new_offset:.4f}\" "
                f"({new_offset * dpi:+.2f} px)"
            )
        except Exception as exc:
            print(f"Error: {exc}")


def _run_horizontal_position_menu(*, fig, ax, cbar, ec_ax, safe_input, colorize_menu, colorize_prompt, allow_ec: bool) -> None:
    while True:
        cb_h_offset = getattr(cbar.ax, "_cb_h_offset_in", 0.0)
        ec_h_offset = getattr(ec_ax, "_ec_h_offset_in", 0.0) if ec_ax is not None else 0.0
        print("\nHorizontal position (relative to canvas center):")
        print(f"  Colorbar offset: {cb_h_offset:.3f}\" (positive=right, negative=left)")
        if allow_ec and ec_ax is not None:
            print(f"  EC panel offset: {ec_h_offset:.3f}\" (positive=right, negative=left)")
        print("  " + colorize_menu("c: colorbar"))
        if allow_ec:
            print("  " + colorize_menu("e: EC panel"))
        print("  " + colorize_menu("q: back"))
        sub = safe_input(colorize_prompt("Move (c/e/q): " if allow_ec else "Move (c/q): ")).strip().lower()
        if not sub or sub == "q":
            break
        if sub == "c":
            _run_single_h_offset_menu(
                fig=fig,
                ax=ax,
                cbar=cbar,
                ec_ax=ec_ax,
                safe_input=safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
                panel_label="Colorbar",
                target_ax=cbar.ax,
                attr="_cb_h_offset_in",
            )
            continue
        if sub == "e" and allow_ec:
            if ec_ax is None:
                print("EC panel not available.")
                continue
            _run_single_h_offset_menu(
                fig=fig,
                ax=ax,
                cbar=cbar,
                ec_ax=ec_ax,
                safe_input=safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
                panel_label="EC panel",
                target_ax=ec_ax,
                attr="_ec_h_offset_in",
            )
            continue
        print("Invalid choice.")


__all__ = ["run_visibility_menu"]
