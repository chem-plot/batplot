"""Intensity (color scale) submenu for the operando interactive menu.

Extracted verbatim from interactive.py (the former inline ``oz`` dispatch
block, including the RangeSlider drag bar). The dispatcher keeps a thin call
so prompts, messages, and undo semantics are unchanged.
"""
from __future__ import annotations

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

try:
    from matplotlib.widgets import RangeSlider, Button  # type: ignore[import-untyped]
except ImportError:
    RangeSlider = None  # type: ignore[misc, assignment]
    Button = None  # type: ignore[misc, assignment]

from ..common.terminal import imk_stderr_guard as _imk_stderr_guard
from .layout import _safe_set_clim, _update_custom_colorbar


def run_intensity_menu(
    *,
    fig,
    ax,
    im,
    cbar,
    snapshot,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
    pop_undo=None,
    restore=None,
):
    """Color-scale intensity submenu (limits/w/s/b/a/q). Former inline oz block."""
    while True:
        try:
            cur = im.get_clim()
            print(f"Current color scale range: {cur[0]:.4g} to {cur[1]:.4g}")
        except Exception:
            print("Could not retrieve current color scale range")

        # Initialize variables for auto-fit
        auto_available = False
        auto_lo = 0.0
        auto_hi = 1.0

        # Calculate actual intensity range in the visible (current X/Y) area
        try:
            arr = np.asarray(im.get_array(), dtype=float)
            if arr.ndim == 2 and arr.size > 0:
                H, W = arr.shape
                x0, x1, y0, y1 = im.get_extent()
                xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
                ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)
                xl = ax.get_xlim(); yl = ax.get_ylim()
                xlo, xhi = (min(xl), max(xl))
                ylo, yhi = (min(yl), max(yl))

                # Map to pixel indices
                if xmax > xmin:
                    c0 = int(np.floor((xlo - xmin) / (xmax - xmin) * (W - 1)))
                    c1 = int(np.ceil((xhi - xmin) / (xmax - xmin) * (W - 1)))
                else:
                    c0, c1 = 0, W - 1
                if ymax > ymin:
                    r0 = int(np.floor((ylo - ymin) / (ymax - ymin) * (H - 1)))
                    r1 = int(np.ceil((yhi - ymin) / (ymax - ymin) * (H - 1)))
                else:
                    r0, r1 = 0, H - 1

                c0 = max(0, min(W - 1, c0)); c1 = max(0, min(W - 1, c1))
                r0 = max(0, min(H - 1, r0)); r1 = max(0, min(H - 1, r1))
                if c1 < c0: c0, c1 = c1, c0
                if r1 < r0: r0, r1 = r1, r0
                view = arr[r0:r1+1, c0:c1+1]
                finite = view[np.isfinite(view)]
                if finite.size:
                    auto_lo = float(np.min(finite))
                    auto_hi = float(np.max(finite))
                    print(f"Actual intensity range in visible area: {auto_lo:.4g} to {auto_hi:.4g}")
                    auto_available = True
                else:
                    print("No finite intensity data in visible area")
                    auto_available = False
            else:
                print("No intensity data available")
                auto_available = False
        except Exception as e:
            print(f"Could not compute intensity range in visible area: {e}")
            auto_available = False

        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("b: bar (drag to adjust range)"))
        if auto_available:
            print("  " + colorize_menu("a: auto-fit to visible"))
        print("  " + colorize_menu("q: back"))
        if auto_available:
            line = safe_input(colorize_prompt("Intensity (w/s/b/a/q): ")).strip()
        else:
            line = safe_input(colorize_prompt("Intensity (w/s/b/q): ")).strip()

        if not line or line.lower() == 'q':
            break

        if line.lower() == 'b':
            # Interactive bar: drag to adjust intensity range
            if RangeSlider is None or Button is None:
                print("Intensity bar requires matplotlib 3.4+ (RangeSlider). Use limit1 limit2 or w/s instead.")
                continue
            with _imk_stderr_guard():
                pushed = False
                try:
                    cur = im.get_clim()
                    vmin_cur, vmax_cur = float(cur[0]), float(cur[1])
                    # Get full data range for slider bounds
                    arr = np.asarray(im.get_array(), dtype=float)
                    if arr.ndim == 2 and arr.size > 0:
                        finite = arr[np.isfinite(arr)]
                        vmin_data = float(np.min(finite)) if finite.size else vmin_cur
                        vmax_data = float(np.max(finite)) if finite.size else vmax_cur
                    else:
                        vmin_data = vmin_cur
                        vmax_data = vmax_cur
                    # Ensure slider range spans current values
                    vmin_slider = min(vmin_data, vmin_cur)
                    vmax_slider = max(vmax_data, vmax_cur)
                    if vmax_slider <= vmin_slider:
                        vmax_slider = vmin_slider + 1.0
                    # Snapshot before live mutate so cancel/unchanged can pop.
                    snapshot("operando-intensity-range")
                    pushed = True
                    # Create slider figure
                    fig_slider = plt.figure(figsize=(8, 1.8), facecolor='0.95')
                    try:
                        fig_slider.canvas.manager.set_window_title("Intensity range")
                    except Exception:
                        pass
                    ax_slider = fig_slider.add_axes((0.15, 0.35, 0.7, 0.25))
                    slider = RangeSlider(ax_slider, "Intensity", vmin_slider, vmax_slider, valinit=(vmin_cur, vmax_cur))
                    ax_btn = fig_slider.add_axes((0.8, 0.05, 0.15, 0.2))
                    btn_done = Button(ax_btn, "Done", color="0.85", hovercolor="0.95")

                    def _on_slider_change(val):
                        lo, hi = val
                        _safe_set_clim(im, lo, hi)
                        try:
                            if cbar is not None:
                                _update_custom_colorbar(cbar.ax, im)
                        except Exception:
                            pass
                        fig.canvas.draw_idle()

                    def _on_done_clicked(event):
                        fig_slider.canvas.stop_event_loop()

                    def _on_slider_closed(event):
                        try:
                            fig_slider.canvas.stop_event_loop()
                        except Exception:
                            pass

                    slider.on_changed(_on_slider_change)
                    btn_done.on_clicked(_on_done_clicked)
                    fig_slider.canvas.mpl_connect("close_event", _on_slider_closed)
                    fig_slider.canvas.draw_idle()
                    plt.show(block=False)
                    try:
                        fig_slider.canvas.start_event_loop(timeout=-1)
                    except Exception:
                        pass
                    # Capture final values from slider before closing (callback already updated im)
                    try:
                        final_lo, final_hi = slider.val
                    except Exception:
                        final_lo, final_hi = im.get_clim()
                    plt.close(fig_slider)
                    unchanged = (
                        abs(float(final_lo) - vmin_cur) < 1e-12
                        and abs(float(final_hi) - vmax_cur) < 1e-12
                    )
                    if unchanged and pushed and pop_undo is not None:
                        try:
                            pop_undo()
                        except Exception:
                            pass
                        pushed = False
                    try:
                        _safe_set_clim(im, final_lo, final_hi)
                        if cbar is not None:
                            _update_custom_colorbar(cbar.ax, im)
                        fig.canvas.draw_idle()
                        print(f"Intensity range: {final_lo:.4g} to {final_hi:.4g}")
                    except Exception:
                        pass
                except Exception as e:
                    # Live clim may already have changed — full restore, not discard.
                    if pushed:
                        try:
                            if restore is not None:
                                restore()
                            elif pop_undo is not None:
                                pop_undo()
                        except Exception:
                            pass
                    print(f"Slider failed: {e}")
            continue

        if line.lower() == 'w':
            # Upper only: change upper limit, fix lower - stay in loop
            while True:
                try:
                    cur = im.get_clim()
                    print(f"Current color scale range: {cur[0]:.4g} to {cur[1]:.4g}")
                except Exception:
                    print("Could not retrieve current color scale range")
                    break
                val = safe_input(colorize_inline_commands(f"Enter new upper intensity limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_upper = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("operando-intensity-range")
                _safe_set_clim(im, cur[0], new_upper)
                try:
                    if cbar is not None:
                        _update_custom_colorbar(cbar.ax, im)
                except Exception:
                    pass
                fig.canvas.draw_idle()
                print(f"Intensity range updated: {im.get_clim()[0]:.4g} to {im.get_clim()[1]:.4g}")
            continue
        if line.lower() == 's':
            # Lower only: change lower limit, fix upper - stay in loop
            while True:
                try:
                    cur = im.get_clim()
                    print(f"Current color scale range: {cur[0]:.4g} to {cur[1]:.4g}")
                except Exception:
                    print("Could not retrieve current color scale range")
                    break
                val = safe_input(colorize_inline_commands(f"Enter new lower intensity limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                try:
                    new_lower = float(val)
                except (ValueError, KeyboardInterrupt):
                    print("Invalid value, ignored.")
                    continue
                snapshot("operando-intensity-range")
                _safe_set_clim(im, new_lower, cur[1])
                try:
                    if cbar is not None:
                        _update_custom_colorbar(cbar.ax, im)
                except Exception:
                    pass
                fig.canvas.draw_idle()
                print(f"Intensity range updated: {im.get_clim()[0]:.4g} to {im.get_clim()[1]:.4g}")
            continue

        try:
            if line.lower() == 'a':
                # Apply auto-normalization to visible data
                if not auto_available:
                    print("Auto-fit unavailable: no finite data in visible area")
                    continue
                snapshot("operando-intensity-range")
                _safe_set_clim(im, auto_lo, auto_hi)
                try:
                    if cbar is not None:
                        _update_custom_colorbar(cbar.ax, im)
                except Exception:
                    pass
                fig.canvas.draw_idle()
                print(f"Applied auto-fit range: {auto_lo:.4g} to {auto_hi:.4g}")
            else:
                lo, hi = map(float, line.split())
                snapshot("operando-intensity-range")
                _safe_set_clim(im, lo, hi)
                try:
                    if cbar is not None:
                        _update_custom_colorbar(cbar.ax, im)
                except Exception:
                    pass
                fig.canvas.draw_idle()
                print(f"Applied intensity range: {lo:.4g} to {hi:.4g}")
        except Exception as e:
            print(f"Invalid range: {e}")
    print_menu()
