"""Capacity / number-of-ions / dual X-axis submenu for the electrochem menu.

Extracted verbatim from interactive.py (the former nested ``_handle_key_a``);
the dispatcher keeps a thin wrapper so prompts, messages, and undo semantics
are unchanged.
"""
from __future__ import annotations

import matplotlib as mpl  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from .style import (
    capture_dual_top_axis,
    reapply_ec_dual_secondary_chrome,
    suppress_ec_dual_duplicate_top_title,
)


def _set_bottom_xlabel(ax, label_text: str) -> None:
    """Set bottom xlabel and keep ``_stored_xlabel`` in sync for hide/dump/undo."""
    ax.set_xlabel(label_text)
    try:
        ax._stored_xlabel = str(label_text)
    except Exception:
        pass


def _ensure_dual_wasd_top_defaults(fig, *, first_enable: bool = False) -> None:
    """Dual needs top spine+title on by default; pre-dual WASD often has them off."""
    wasd = getattr(fig, "_ec_wasd_state", None)
    if not isinstance(wasd, dict):
        wasd = {}
        fig._ec_wasd_state = wasd
    top = wasd.setdefault("top", {})
    if not isinstance(top, dict):
        top = {}
        wasd["top"] = top
    if first_enable:
        top["spine"] = True
        top["title"] = True
        # ticks/labels stay user preference (often off for dual ions)
        top.setdefault("ticks", False)
        top.setdefault("labels", False)
        top.setdefault("minor", False)
    else:
        # Recreate (swap/C_th): keep toggles; only fill missing keys
        top.setdefault("spine", True)
        top.setdefault("title", True)
        top.setdefault("ticks", False)
        top.setdefault("labels", False)
        top.setdefault("minor", False)


def _clear_dual_wasd_top_on_leave(fig, ax) -> None:
    """Leaving dual must not leave top.title=True (would create capacity duplicate)."""
    wasd = getattr(fig, "_ec_wasd_state", None)
    if isinstance(wasd, dict):
        top = wasd.setdefault("top", {})
        if isinstance(top, dict):
            top["title"] = False
            top["ticks"] = False
            top["labels"] = False
            top["minor"] = False
            # spine can stay; primary top spine is normal frame
    try:
        ax._top_xlabel_on = False
    except Exception:
        pass
    try:
        suppress_ec_dual_duplicate_top_title(ax, fig)
    except Exception:
        pass


def _leave_dual_axis_chrome(fig, ax) -> None:
    """Exit dual via ``c``/``n``: clear sticky swap and reseal primary WASD/colors.

    Without this, ``t``/``k`` after leave see stale ``_xaxis_swapped`` and/or
    dual-era top tick/label flags that never get reapplied to the primary axis.
    """
    from ...ui import finalize_spine_colors
    from .style import reseal_ec_chrome

    try:
        fig._xaxis_swapped = False
    except Exception:
        pass
    _clear_dual_wasd_top_on_leave(fig, ax)
    try:
        reseal_ec_chrome(
            fig, ax, wasd=getattr(fig, "_ec_wasd_state", None),
            tick_state=getattr(ax, "_saved_tick_state", None),
            apply_titles=True,
        )
    except Exception:
        try:
            finalize_spine_colors(
                fig, ax, tick_state=getattr(ax, "_saved_tick_state", None),
            )
        except Exception:
            pass


def _is_default_gc_xlabel(text) -> bool:
    t = str(text or "")
    return ("Specific Capacity" in t) or ("Number of ions" in t)


def _rehonor_bottom_xlabel_after_dual(
    fig, ax, *, keep_bottom_xlabel: bool = True,
) -> None:
    """After dual recreate set defaults — restore custom bottom / honor s5 hide.

    Always respects WASD ``bottom.title`` (including after ``s`` swap). Never
    force-show the bottom title when the user hid it.
    """
    wasd = getattr(fig, "_ec_wasd_state", None)
    bot = (wasd or {}).get("bottom", {}) if isinstance(wasd, dict) else {}
    if not isinstance(bot, dict):
        bot = {}
    title_on = bool(bot.get("title", True)) if "title" in bot else True
    if not title_on:
        try:
            cur = ax.get_xlabel()
            if cur:
                ax._stored_xlabel = cur
        except Exception:
            pass
        try:
            ax.set_xlabel("")
            ax.xaxis.label.set_visible(False)
        except Exception:
            pass
        return
    if not keep_bottom_xlabel:
        # New default label already on ax (swap/u) — bookkeep, keep visible
        try:
            ax._stored_xlabel = ax.get_xlabel()
            ax.xaxis.label.set_visible(True)
        except Exception:
            pass
        return
    stored = getattr(ax, "_stored_xlabel", None)
    if isinstance(stored, str) and stored.strip() and not _is_default_gc_xlabel(stored):
        try:
            ax.set_xlabel(stored)
            ax.xaxis.label.set_visible(True)
        except Exception:
            pass
    else:
        try:
            ax._stored_xlabel = ax.get_xlabel()
            ax.xaxis.label.set_visible(True)
        except Exception:
            pass


def _chrome_after_dual_recreate(
    fig,
    ax,
    *,
    keep_top_xlabel: bool = True,
    keep_bottom_xlabel: bool = True,
    first_enable: bool = False,
) -> None:
    """Restore WASD chrome after SecondaryAxis recreate.

    Must apply **all** sides (not only SecondaryAxis top): after ``s`` swap,
    bottom spine/ticks/labels/title visibility lives in swapped WASD and was
    previously left stale on the primary axis.
    """
    from .style import reseal_ec_chrome

    _ensure_dual_wasd_top_defaults(fig, first_enable=first_enable)
    prev = getattr(fig, "_bp_pending_dual_top_axis", None)
    try:
        delattr(fig, "_bp_pending_dual_top_axis")
    except Exception:
        pass
    cfg = dict(prev) if isinstance(prev, dict) else None
    if isinstance(cfg, dict) and not keep_top_xlabel:
        cfg.pop("xlabel", None)
    try:
        reapply_ec_dual_secondary_chrome(
            fig, ax, wasd_state=getattr(fig, "_ec_wasd_state", None), top_axis_cfg=cfg,
        )
    except Exception:
        pass
    _rehonor_bottom_xlabel_after_dual(fig, ax, keep_bottom_xlabel=keep_bottom_xlabel)
    # Full w/a/s/d + locator sync + colors (swap must move bottom spine visibility)
    try:
        reseal_ec_chrome(
            fig, ax, wasd=getattr(fig, "_ec_wasd_state", None), apply_titles=True,
        )
    except Exception:
        pass


def _stash_dual_top_before_remove(fig, ax) -> None:
    try:
        fig._bp_pending_dual_top_axis = capture_dual_top_axis(fig, ax)
    except Exception:
        fig._bp_pending_dual_top_axis = None


def _capture_primary_bottom_x(ax) -> dict:
    """Capture bottom x spine/tick/title chrome (capacity or ions when swapped)."""
    from matplotlib import colors as mcolors  # type: ignore[import-untyped]

    out: dict = {}
    try:
        out["xlabel"] = ax.get_xlabel()
        out["xlabel_visible"] = bool(ax.xaxis.label.get_visible())
        out["label_color"] = mcolors.to_hex(ax.xaxis.label.get_color())
    except Exception:
        pass
    try:
        sp = ax.spines.get("bottom")
        if sp is not None:
            out["spine_visible"] = bool(sp.get_visible())
            out["spine_color"] = mcolors.to_hex(sp.get_edgecolor())
    except Exception:
        pass
    try:
        out["major_tick_color"] = (ax.xaxis.get_tick_params() or {}).get("color")
    except Exception:
        pass
    # Prefer stored bookkeeping if artist color is unreliable
    try:
        stored = getattr(ax, "_stored_xlabel_color", None)
        if stored:
            out["label_color"] = stored
        ax_store = getattr(ax, "_bp_spine_side_colors", None)
        if isinstance(ax_store, dict) and ax_store.get("bottom"):
            out["spine_color"] = ax_store["bottom"]
    except Exception:
        pass
    return out


def _swap_ec_dual_wasd_top_bottom(fig) -> None:
    """Swap WASD top↔bottom so chrome follows ions/capacity across ``s``."""
    wasd = getattr(fig, "_ec_wasd_state", None)
    if not isinstance(wasd, dict):
        return
    top = wasd.get("top") if isinstance(wasd.get("top"), dict) else {}
    bot = wasd.get("bottom") if isinstance(wasd.get("bottom"), dict) else {}
    wasd["top"] = dict(bot)
    wasd["bottom"] = dict(top)


def _swap_ec_dual_spine_color_stores(fig, ax) -> None:
    """Swap stored top↔bottom spine colors on fig/ax (semantic follow on swap)."""
    for owner in (fig, ax):
        try:
            store = getattr(owner, "_bp_spine_side_colors", None)
            if not isinstance(store, dict):
                continue
            top_c = store.get("top")
            bot_c = store.get("bottom")
            if top_c is not None or bot_c is not None:
                store["top"], store["bottom"] = bot_c, top_c
                owner._bp_spine_side_colors = store
        except Exception:
            pass
    # Title color bookkeeping
    try:
        top_title = getattr(ax, "_stored_top_xlabel_color", None)
        bot_title = getattr(ax, "_stored_xlabel_color", None)
        if top_title is not None or bot_title is not None:
            ax._stored_top_xlabel_color = bot_title
            ax._stored_xlabel_color = top_title
    except Exception:
        pass


def _pending_top_from_bottom_cfg(bottom_cfg: dict, wasd_top) -> dict:
    """Build SecondaryAxis top_axis cfg from former bottom (after color/WASD swap)."""
    wasd_top = wasd_top if isinstance(wasd_top, dict) else {}
    spine_c = bottom_cfg.get("spine_color") or bottom_cfg.get("major_tick_color")
    label_c = bottom_cfg.get("label_color") or spine_c
    return {
        "xlabel": None,  # swap resets to capacity/ions defaults
        "xlabel_visible": bool(wasd_top.get("title", True)),
        "label_color": label_c,
        "spine_visible": bool(wasd_top.get("spine", True)),
        "spine_color": spine_c,
        "major_tick_color": bottom_cfg.get("major_tick_color") or spine_c,
    }


def run_dual_axis_menu(
    *,
    fig,
    ax,
    all_cycles,
    is_dqdv,
    is_multi_file,
    menu_title,
    canvas_mode,
    print_menu,
    push_state,
    apply_nice_ticks,
    safe_input,
    colorize_menu,
    colorize_prompt,
    restore_state=None,
):
    """X-axis configuration submenu (c/n/d/s/u/q)."""
    if is_dqdv:
        print("Capacity/ion conversion is not available in dQ/dV mode.")
        print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
        return
    if fig is not None and hasattr(fig, "_ec_is_gc") and not bool(getattr(fig, "_ec_is_gc")):
        print("Capacity/ion conversion is only available in GC mode.")
        print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
        return
    # Initialize dual axis state if not present
    if not hasattr(fig, '_xaxis_mode'):
        fig._xaxis_mode = 'capacity'  # 'capacity', 'ions', or 'dual'
    if not hasattr(fig, '_xaxis_c_theoretical'):
        fig._xaxis_c_theoretical = None
    if not hasattr(fig, '_xaxis_secondary'):
        fig._xaxis_secondary = None  # Store secondary axis object
    if not hasattr(fig, '_xaxis_swapped'):
        fig._xaxis_swapped = False  # If True, ions on bottom, capacity on top

    # X-axis submenu: number-of-ions vs capacity with dual mode
    while True:
        # Show current state
        current_mode = getattr(fig, '_xaxis_mode', 'capacity')
        c_th = getattr(fig, '_xaxis_c_theoretical', None)
        swapped = getattr(fig, '_xaxis_swapped', False)

        print("\nX-axis configuration:")
        print(f"  Current mode: {current_mode}")
        if c_th:
            print(f"  Theoretical capacity: {c_th} mAh g⁻¹")
        if current_mode == 'dual':
            bottom_label = "Ions" if swapped else "Capacity"
            top_label = "Capacity" if swapped else "Ions"
            print(f"  Bottom: {bottom_label}, Top: {top_label}")
        print("\nOptions:")
        print("  " + colorize_menu("c : capacity only (bottom)"))
        print("  " + colorize_menu("n : number of ions only (bottom)"))
        print("  " + colorize_menu("d : dual mode (capacity bottom, ions top)"))
        if current_mode == 'dual':
            print("  " + colorize_menu("s : swap axes (switch top/bottom)"))
        if c_th:
            print("  " + colorize_menu("u : update theoretical capacity"))
        print("  " + colorize_menu("q : back to main menu"))

        sub = safe_input(colorize_prompt(
            "X-axis mode (c/n/d/s/u/q per menu above): "
        )).strip().lower()
        if not sub:
            continue
        if sub == 'q':
            break
        if sub == 'n':
            # Get theoretical capacity
            c_th_input = getattr(fig, '_xaxis_c_theoretical', None)
            c_th = c_th_input
            if not c_th_input:
                print("Input the theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                c_th = None
                while c_th is None:
                    val = safe_input("C_theoretical_per_ion (q=back): ").strip()
                    if not val or val.lower() == 'q':
                        break
                    try:
                        parsed = float(val)
                        if parsed <= 0:
                            print("Theoretical capacity must be positive.")
                            continue
                        c_th = parsed
                    except Exception:
                        print("Invalid number.")
                if c_th is None:
                    continue

            # Snapshot while SecondaryAxis still exists (undo must capture dual chrome).
            push_state("x=n(ions)")
            # Remove any existing secondary axis
            if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                try:
                    fig._xaxis_secondary.remove()
                except Exception:
                    pass
                fig._xaxis_secondary = None

            # Store original x-data once, then set new x = orig_x / c_th
            for ln in ax.lines:
                try:
                    if not hasattr(ln, "_orig_xdata_gc"):
                        x0 = np.asarray(ln.get_xdata(), dtype=float)
                        setattr(ln, "_orig_xdata_gc", x0.copy())
                    x_orig = getattr(ln, "_orig_xdata_gc")
                    ln.set_xdata(x_orig / c_th)
                except Exception:
                    continue

            # Store state
            fig._xaxis_mode = 'ions'
            fig._xaxis_c_theoretical = c_th
            _leave_dual_axis_chrome(fig, ax)
            # Construct label with proper mathtext for superscript
            # Configure mathtext fontset BEFORE setting the label to ensure consistency
            try:
                font_fam = plt.rcParams.get('font.sans-serif', [''])
                font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''

                # Configure mathtext to use the same font family
                if font_fam_str:
                    # Configure mathtext fontset to match the regular font
                    # For Arial-like fonts, use dejavusans; for Times/STIX, use stix
                    lf = font_fam_str.lower()
                    if any(k in lf for k in ('stix', 'times', 'roman')):
                        mpl.rcParams['mathtext.fontset'] = 'stix'
                    else:
                        # Use dejavusans for Arial, Helvetica, etc. (closest match to Arial)
                        mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                    mpl.rcParams['mathtext.default'] = 'regular'
            except Exception:
                pass

            label_text = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
            _set_bottom_xlabel(ax, label_text)

            # Apply current font settings to the label to ensure consistency
            try:
                font_fam = plt.rcParams.get('font.sans-serif', [''])
                font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                font_size = plt.rcParams.get('font.size', None)
                if font_fam_str:
                    ax.xaxis.label.set_family(font_fam_str)
                if font_size is not None:
                    ax.xaxis.label.set_size(font_size)
                # Force label to re-render with updated mathtext fontset by updating the text
                _set_bottom_xlabel(ax, label_text)
            except Exception:
                pass
            apply_nice_ticks()
            try:
                ax.relim(); ax.autoscale_view()
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print(f"✓ Ions mode enabled (bottom x-axis)")
        elif sub == 'c':
            # Snapshot while SecondaryAxis still exists (undo must capture dual chrome).
            push_state("x=capacity")
            # Remove any existing secondary axis
            if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                try:
                    fig._xaxis_secondary.remove()
                except Exception:
                    pass
                fig._xaxis_secondary = None

            # Restore original capacity on x if available
            any_restored = False
            for ln in ax.lines:
                try:
                    if hasattr(ln, "_orig_xdata_gc"):
                        x_orig = getattr(ln, "_orig_xdata_gc")
                        ln.set_xdata(x_orig)
                        any_restored = True
                except Exception:
                    continue

            # Store state
            fig._xaxis_mode = 'capacity'
            _leave_dual_axis_chrome(fig, ax)
            # Construct label with proper mathtext for superscript
            # Configure mathtext fontset BEFORE setting the label to ensure consistency
            try:
                font_fam = plt.rcParams.get('font.sans-serif', [''])
                font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''

                # Configure mathtext to use the same font family
                if font_fam_str:
                    # Configure mathtext fontset to match the regular font
                    # For Arial-like fonts, use dejavusans; for Times/STIX, use stix
                    lf = font_fam_str.lower()
                    if any(k in lf for k in ('stix', 'times', 'roman')):
                        mpl.rcParams['mathtext.fontset'] = 'stix'
                    else:
                        # Use dejavusans for Arial, Helvetica, etc. (closest match to Arial)
                        mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                    mpl.rcParams['mathtext.default'] = 'regular'
            except Exception:
                pass

            label_text = "Specific Capacity (mAh g$^{{-1}}$)"
            _set_bottom_xlabel(ax, label_text)

            # Apply current font settings to the label to ensure consistency
            try:
                font_fam = plt.rcParams.get('font.sans-serif', [''])
                font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                font_size = plt.rcParams.get('font.size', None)
                if font_fam_str:
                    ax.xaxis.label.set_family(font_fam_str)
                if font_size is not None:
                    ax.xaxis.label.set_size(font_size)
                # Force label to re-render with updated mathtext fontset by updating the text
                _set_bottom_xlabel(ax, label_text)
            except Exception:
                pass
            if any_restored:
                apply_nice_ticks()
                try:
                    ax.relim(); ax.autoscale_view()
                except Exception:
                    pass
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
            print(f"✓ Capacity mode enabled (bottom x-axis)")
        elif sub == 'd':
            # Dual mode: capacity on bottom, ions on top (or swapped)
            # Get theoretical capacity
            c_th_input = getattr(fig, '_xaxis_c_theoretical', None)
            c_th = c_th_input
            if not c_th_input:
                print("Input the theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                c_th = None
                while c_th is None:
                    val = safe_input("C_theoretical_per_ion (q=back): ").strip()
                    if not val or val.lower() == 'q':
                        break
                    try:
                        parsed = float(val)
                        if parsed <= 0:
                            print("Theoretical capacity must be positive.")
                            continue
                        c_th = parsed
                    except Exception:
                        print("Invalid number.")
                if c_th is None:
                    continue

            push_state("x=dual")
            prev_mode = getattr(fig, '_xaxis_mode', 'capacity')
            first_enable = prev_mode != 'dual'

            # Store original x-data and ensure primary axis shows capacity
            for ln in ax.lines:
                try:
                    if not hasattr(ln, "_orig_xdata_gc"):
                        x0 = np.asarray(ln.get_xdata(), dtype=float)
                        setattr(ln, "_orig_xdata_gc", x0.copy())
                    # Restore to capacity (primary data)
                    x_orig = getattr(ln, "_orig_xdata_gc")
                    ln.set_xdata(x_orig)
                except Exception:
                    continue

            # Remove existing secondary axis if any
            _stash_dual_top_before_remove(fig, ax)
            if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                try:
                    fig._xaxis_secondary.remove()
                except Exception:
                    pass

            # Define conversion functions
            def capacity_to_ions(capacity):
                return capacity / c_th

            def ions_to_capacity(ions):
                return ions * c_th

            # Create secondary x-axis on top
            try:
                secax = ax.secondary_xaxis('top', functions=(capacity_to_ions, ions_to_capacity))
                fig._xaxis_secondary = secax

                # Configure mathtext fontset
                try:
                    font_fam = plt.rcParams.get('font.sans-serif', [''])
                    font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                    if font_fam_str:
                        lf = font_fam_str.lower()
                        if any(k in lf for k in ('stix', 'times', 'roman')):
                            mpl.rcParams['mathtext.fontset'] = 'stix'
                        else:
                            mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                        mpl.rcParams['mathtext.default'] = 'regular'
                except Exception:
                    pass

                # Set labels
                capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                # Keep custom bottom rename across first dual enable (store only;
                # live shows the mode default until chrome restore reapplies it).
                custom_xl = None
                try:
                    cur_xl = ax.get_xlabel()
                    if cur_xl and not _is_default_gc_xlabel(cur_xl):
                        custom_xl = cur_xl
                except Exception:
                    pass

                _set_bottom_xlabel(ax, capacity_label)
                if custom_xl is not None:
                    ax._stored_xlabel = custom_xl
                secax.set_xlabel(ions_label)

                # Apply font settings to both labels
                try:
                    font_fam = plt.rcParams.get('font.sans-serif', [''])
                    font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                    font_size = plt.rcParams.get('font.size', None)
                    if font_fam_str:
                        ax.xaxis.label.set_family(font_fam_str)
                        secax.xaxis.label.set_family(font_fam_str)
                    if font_size is not None:
                        ax.xaxis.label.set_size(font_size)
                        secax.xaxis.label.set_size(font_size)
                except Exception:
                    pass

                # Store state — re-entering dual must not reset swap flag
                fig._xaxis_mode = 'dual'
                fig._xaxis_c_theoretical = c_th
                if first_enable:
                    fig._xaxis_swapped = False

                _chrome_after_dual_recreate(
                    fig, ax,
                    keep_top_xlabel=True,
                    keep_bottom_xlabel=True,
                    first_enable=first_enable,
                )
                apply_nice_ticks()
                try:
                    from ...ui import finalize_spine_colors

                    finalize_spine_colors(fig, ax, draw=False)
                except Exception:
                    pass
                try:
                    ax.relim(); ax.autoscale_view()
                except Exception:
                    pass
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()

                print(f"✓ Dual mode enabled")
                print(f"  Bottom: Capacity (mAh g⁻¹)")
                print(f"  Top: Number of ions (C / {c_th} mAh g⁻¹)")
            except Exception as e:
                print(f"Error creating dual axis: {e}")
                if restore_state is not None:
                    try:
                        restore_state()
                    except Exception:
                        fig._xaxis_mode = 'capacity'
                else:
                    fig._xaxis_mode = 'capacity'
        elif sub == 's':
            # Swap axes (only available in dual mode)
            if getattr(fig, '_xaxis_mode', 'capacity') != 'dual':
                print("Swap is only available in dual mode. Use 'd' first.")
                continue

            c_th = getattr(fig, '_xaxis_c_theoretical', None)
            if not c_th:
                print("Error: No theoretical capacity stored.")
                continue

            push_state("x=swap")

            swapped = getattr(fig, '_xaxis_swapped', False)
            new_swapped = not swapped

            # Capture chrome BEFORE remove. Colors/WASD must follow ions↔capacity
            # (not stick to physical top/bottom). Old path reapplied top stash to
            # the new top — ions color stayed on top after swap.
            from .style import capture_dual_top_axis as _cap_top

            old_top_cfg = _cap_top(fig, ax) or {}
            old_bot_cfg = _capture_primary_bottom_x(ax)
            _swap_ec_dual_wasd_top_bottom(fig)
            _swap_ec_dual_spine_color_stores(fig, ax)
            # New SecondaryAxis (physical top) gets former bottom colors
            wasd_after = getattr(fig, "_ec_wasd_state", {}) or {}
            fig._bp_pending_dual_top_axis = _pending_top_from_bottom_cfg(
                old_bot_cfg, wasd_after.get("top"),
            )

            if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                try:
                    fig._xaxis_secondary.remove()
                except Exception:
                    pass
                fig._xaxis_secondary = None

            # Update primary axis data and labels based on swap state
            for ln in ax.lines:
                try:
                    if hasattr(ln, "_orig_xdata_gc"):
                        x_orig = getattr(ln, "_orig_xdata_gc")
                        if new_swapped:
                            # Ions on bottom: divide by c_th
                            ln.set_xdata(x_orig / c_th)
                        else:
                            # Capacity on bottom: restore original
                            ln.set_xdata(x_orig)
                except Exception:
                    continue

            # Define conversion functions
            if new_swapped:
                # Bottom = ions, Top = capacity
                def _bottom_to_top_ions(ions):
                    return ions * c_th

                def _top_to_bottom_capacity(capacity):
                    return capacity / c_th

                bottom_to_top = _bottom_to_top_ions
                top_to_bottom = _top_to_bottom_capacity
            else:
                # Bottom = capacity, Top = ions
                def _bottom_to_top_capacity(capacity):
                    return capacity / c_th

                def _top_to_bottom_ions(ions):
                    return ions * c_th

                bottom_to_top = _bottom_to_top_capacity
                top_to_bottom = _top_to_bottom_ions

            # Create new secondary axis
            try:
                secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                fig._xaxis_secondary = secax

                # Configure mathtext fontset
                try:
                    font_fam = plt.rcParams.get('font.sans-serif', [''])
                    font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                    if font_fam_str:
                        lf = font_fam_str.lower()
                        if any(k in lf for k in ('stix', 'times', 'roman')):
                            mpl.rcParams['mathtext.fontset'] = 'stix'
                        else:
                            mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                        mpl.rcParams['mathtext.default'] = 'regular'
                except Exception:
                    pass

                # Set labels based on swap state
                capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"

                if new_swapped:
                    _set_bottom_xlabel(ax, ions_label)
                    secax.set_xlabel(capacity_label)
                else:
                    _set_bottom_xlabel(ax, capacity_label)
                    secax.set_xlabel(ions_label)

                # Apply font settings
                try:
                    font_fam = plt.rcParams.get('font.sans-serif', [''])
                    font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                    font_size = plt.rcParams.get('font.size', None)
                    if font_fam_str:
                        ax.xaxis.label.set_family(font_fam_str)
                        secax.xaxis.label.set_family(font_fam_str)
                    if font_size is not None:
                        ax.xaxis.label.set_size(font_size)
                        secax.xaxis.label.set_size(font_size)
                except Exception:
                    pass

                # Update state
                fig._xaxis_swapped = new_swapped

                # Labels: defaults for new meanings. Colors: pending top = old bottom;
                # then paint bottom with old top.
                _chrome_after_dual_recreate(
                    fig, ax, keep_top_xlabel=False, keep_bottom_xlabel=False, first_enable=False,
                )
                try:
                    from ...ui import finalize_spine_colors, set_spine_side_color

                    old_top_spine = old_top_cfg.get("spine_color") or old_top_cfg.get("major_tick_color")
                    old_top_label = old_top_cfg.get("label_color") or old_top_spine
                    if old_top_spine:
                        set_spine_side_color(
                            ax,
                            "bottom",
                            old_top_spine,
                            fig=fig,
                            title_color=old_top_label,
                            tick_state=getattr(ax, "_saved_tick_state", None),
                        )
                    if old_top_label:
                        ax.xaxis.label.set_color(old_top_label)
                        ax._stored_xlabel_color = old_top_label
                    finalize_spine_colors(
                        fig,
                        ax,
                        tick_state=getattr(ax, "_saved_tick_state", None),
                        draw=False,
                    )
                except Exception:
                    pass
                apply_nice_ticks()
                try:
                    from ...ui import finalize_spine_colors

                    finalize_spine_colors(fig, ax, draw=False)
                except Exception:
                    pass
                try:
                    ax.relim(); ax.autoscale_view()
                except Exception:
                    pass
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()

                bottom_label = "Ions" if new_swapped else "Capacity"
                top_label = "Capacity" if new_swapped else "Ions"
                print(f"✓ Axes swapped")
                print(f"  Bottom: {bottom_label}")
                print(f"  Top: {top_label}")
            except Exception as e:
                print(f"Error swapping axes: {e}")
                if restore_state is not None:
                    try:
                        restore_state()
                    except Exception:
                        pass
        elif sub == 'u':
            # Update theoretical capacity
            while True:
                current_c_th = getattr(fig, '_xaxis_c_theoretical', None)
                if current_c_th:
                    print(f"Current theoretical capacity: {current_c_th} mAh g⁻¹")
                print("Input new theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                val = safe_input("C_theoretical_per_ion (q=back): ").strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_c_th = float(val)
                    if new_c_th <= 0:
                        print("Theoretical capacity must be positive.")
                        continue
                except Exception:
                    print("Invalid number.")
                    continue

                # Snapshot BEFORE mutating C_th so undo can restore the old value.
                old_c_th = getattr(fig, '_xaxis_c_theoretical', None)
                current_mode = getattr(fig, '_xaxis_mode', 'capacity')
                if current_mode == 'ions':
                    push_state("update-c-theoretical")
                elif current_mode == 'dual':
                    push_state("update-c-theoretical-dual")
                else:
                    push_state("update-c-theoretical")
                fig._xaxis_c_theoretical = new_c_th
                print(f"Updated theoretical capacity: {old_c_th} → {new_c_th} mAh g⁻¹")

                # If in ions or dual mode, update the display
                if current_mode == 'ions':
                    for ln in ax.lines:
                        try:
                            if hasattr(ln, "_orig_xdata_gc"):
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                ln.set_xdata(x_orig / new_c_th)
                        except Exception:
                            continue
                    label_text = f"Number of ions (C / {new_c_th:g} mAh g$^{{-1}}$)"
                    _set_bottom_xlabel(ax, label_text)
                    apply_nice_ticks()
                    try:
                        ax.relim(); ax.autoscale_view()
                    except Exception:
                        pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                elif current_mode == 'dual':
                    swapped = getattr(fig, '_xaxis_swapped', False)
                    _stash_dual_top_before_remove(fig, ax)
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                    for ln in ax.lines:
                        try:
                            if hasattr(ln, "_orig_xdata_gc"):
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                if swapped:
                                    ln.set_xdata(x_orig / new_c_th)
                                else:
                                    ln.set_xdata(x_orig)
                        except Exception:
                            continue
                    if swapped:
                        def _bottom_to_top_ions_new(ions):
                            return ions * new_c_th
                        def _top_to_bottom_capacity_new(capacity):
                            return capacity / new_c_th
                        bottom_to_top = _bottom_to_top_ions_new
                        top_to_bottom = _top_to_bottom_capacity_new
                    else:
                        def _bottom_to_top_capacity_new(capacity):
                            return capacity / new_c_th
                        def _top_to_bottom_ions_new(ions):
                            return ions * new_c_th
                        bottom_to_top = _bottom_to_top_capacity_new
                        top_to_bottom = _top_to_bottom_ions_new
                    try:
                        secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                        fig._xaxis_secondary = secax
                        capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                        ions_label = f"Number of ions (C / {new_c_th:g} mAh g$^{{-1}}$)"
                        if swapped:
                            _set_bottom_xlabel(ax, ions_label)
                            secax.set_xlabel(capacity_label)
                        else:
                            _set_bottom_xlabel(ax, capacity_label)
                            secax.set_xlabel(ions_label)
                        try:
                            font_fam = plt.rcParams.get('font.sans-serif', [''])
                            font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                            font_size = plt.rcParams.get('font.size', None)
                            if font_fam_str:
                                secax.xaxis.label.set_family(font_fam_str)
                            if font_size is not None:
                                secax.xaxis.label.set_size(font_size)
                        except Exception:
                            pass
                        # Keep custom tx rename; refresh default ions/capacity strings for new C_th
                        prev = getattr(fig, "_bp_pending_dual_top_axis", None)
                        xl = str((prev or {}).get("xlabel") or "") if isinstance(prev, dict) else ""
                        keep_custom = bool(xl) and (
                            "Number of ions" not in xl and "Specific Capacity" not in xl
                        )
                        _chrome_after_dual_recreate(
                            fig,
                            ax,
                            keep_top_xlabel=keep_custom,
                            keep_bottom_xlabel=True,
                            first_enable=False,
                        )
                        apply_nice_ticks()
                        try:
                            from ...ui import finalize_spine_colors

                            finalize_spine_colors(fig, ax, draw=False)
                        except Exception:
                            pass
                        try:
                            ax.relim(); ax.autoscale_view()
                        except Exception:
                            pass
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                    except Exception as e:
                        print(f"Error updating dual axis: {e}")
                else:
                    print("Theoretical capacity updated (will be used if you switch to ions/dual mode)")
        else:
            print(f"Unknown option: {sub}")
    print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
    return
