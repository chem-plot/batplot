"""WASD spines/ticks/labels/title toggle menu for the CPC interactive menu.

Extracted verbatim from interactive.py (the former nested ``_handle_key_t``
with its inner ``_apply_wasd``). The dispatcher keeps a thin wrapper so
prompts, messages, tick-state persistence, and undo semantics are unchanged.
"""
from __future__ import annotations

from matplotlib.ticker import AutoMinorLocator, MultipleLocator, NullLocator  # type: ignore[import]

from ...ui import (
    finalize_spine_colors_cpc,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_top_xlabel as _ui_position_top_xlabel,
)
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_wasd_spines,
    apply_wasd_tick_params,
    run_spine_tick_menu,
    set_primary_axis_title,
    sync_tick_state_from_wasd,
)


def run_cpc_wasd_menu(
    *,
    fig,
    ax,
    ax2,
    sc_eff,
    tick_state,
    push_state,
    print_menu,
    safe_input,
    colorize_prompt,
    colorize_inline_commands,
):
    """Unified WASD toggles for spines/ticks/minor/labels/title per side. Former _handle_key_t."""
    assert sc_eff is not None
    # Unified WASD toggles for spines/ticks/minor/labels/title per side
    # Import UI positioning functions locally to ensure they're accessible in nested functions

    try:
        # Local WASD state stored on figure to persist across openings
        wasd = getattr(fig, '_cpc_wasd_state', None)
        if not isinstance(wasd, dict):
            wasd = {
                'top':    {'spine': bool(ax.spines.get('top').get_visible()) if ax.spines.get('top') else False,
                           'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
                           'minor': bool(tick_state.get('mtx', False)),
                           'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
                           'title': bool(getattr(ax, '_top_xlabel_on', False))},
                'bottom': {'spine': bool(ax.spines.get('bottom').get_visible()) if ax.spines.get('bottom') else True,
                           'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
                           'minor': bool(tick_state.get('mbx', False)),
                           'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
                           'title': bool(ax.xaxis.label.get_visible())},
                'left':   {'spine': bool(ax.spines.get('left').get_visible()) if ax.spines.get('left') else True,
                           'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
                           'minor': bool(tick_state.get('mly', False)),
                           'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
                           'title': bool(ax.yaxis.label.get_visible())},
                'right':  {'spine': bool(ax2.spines.get('right').get_visible()) if ax2.spines.get('right') else True,
                           'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', True))),
                           'minor': bool(tick_state.get('mry', False)),
                           'labels': bool(tick_state.get('r_labels', tick_state.get('ry', True))),
                           # Do not AND current-file sc_eff — multi-file hide must
                           # not force right title off when global ry is on.
                           'title': bool(ax2.yaxis.label.get_visible())},
            }
            setattr(fig, '_cpc_wasd_state', wasd)

        def _apply_wasd(changed_sides=None):
            assert sc_eff is not None
            # If no changed_sides specified, reposition all sides (for load style, etc.)
            if changed_sides is None:
                changed_sides = {'bottom', 'top', 'left', 'right'}

            apply_wasd_spines(ax, wasd, sides=('top', 'bottom', 'left'))
            apply_wasd_spines(ax2, wasd, sides=('top', 'bottom', 'right'))
            apply_wasd_tick_params(ax, wasd, y_sides=('left',), y_mode='left')
            apply_wasd_tick_params(ax2, wasd, x_sides=(), y_sides=('right',), y_mode='right')

            # Titles
            try:
                # Bottom X title — visibility must match capture (get_visible).
                set_primary_axis_title(
                    ax, "x", on=bool(wasd["bottom"]["title"]), stored_attr="_stored_xlabel"
                )
            except Exception:
                pass
            try:
                # Top X title - create a text artist positioned at the top
                # First ensure we have the original xlabel text stored
                if not hasattr(ax, '_stored_top_xlabel') or not isinstance(ax._stored_top_xlabel, str):
                    # Try to get from current xlabel first
                    current_xlabel = ax.get_xlabel()
                    if current_xlabel:
                        ax._stored_top_xlabel = current_xlabel
                    # If still empty, try from stored bottom xlabel
                    elif hasattr(ax, '_stored_xlabel') and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                        ax._stored_top_xlabel = ax._stored_xlabel
                    else:
                        ax._stored_top_xlabel = ''

                ax._top_xlabel_on = bool(wasd['top']['title'])
                if bool(wasd['top']['title']) and isinstance(getattr(ax, '_stored_top_xlabel', None), str):
                    # Get or create the top xlabel artist
                    if not hasattr(ax, '_top_xlabel_text') or ax._top_xlabel_text is None:
                        # Create a new text artist at the top center
                        ax._top_xlabel_text = ax.text(0.5, 1.0, '', transform=ax.transAxes,
                                                      ha='center', va='bottom',
                                                      fontsize=ax.xaxis.label.get_fontsize(),
                                                      fontfamily=ax.xaxis.label.get_fontfamily())
                    # Update text and make visible
                    ax._top_xlabel_text.set_text(ax._stored_top_xlabel)
                    ax._top_xlabel_text.set_visible(True)
                    # Keep spine-color menu (`k`) title color across WASD recreate
                    top_c = (
                        (getattr(fig, "_cpc_spine_colors", None) or {}).get("top")
                        or getattr(ax, "_stored_top_xlabel_color", None)
                    )
                    if top_c is not None:
                        try:
                            ax._top_xlabel_text.set_color(top_c)
                            ax._stored_top_xlabel_color = top_c
                        except Exception:
                            pass

                    # Dynamic positioning based on top tick labels visibility
                    # Only reposition top if it's in changed_sides
                    if 'top' in changed_sides:
                        try:
                            # Get renderer for measurements
                            renderer = fig.canvas.get_renderer()

                            # Base padding
                            labelpad = ax.xaxis.labelpad if hasattr(ax.xaxis, 'labelpad') else 4.0
                            fig_h = fig.get_size_inches()[1]
                            ax_bbox = ax.get_position()
                            ax_h_inches = ax_bbox.height * fig_h
                            base_pad_axes = (labelpad / 72.0) / ax_h_inches if ax_h_inches > 0 else 0.02

                            # If top tick labels are visible, measure their height and add spacing
                            extra_offset = 0.0
                            if bool(wasd['top']['labels']) and renderer is not None:
                                try:
                                    max_h_px = 0.0
                                    for t in ax.xaxis.get_major_ticks():
                                        lab = getattr(t, 'label2', None)  # Top labels are label2
                                        if lab is not None and lab.get_visible():
                                            bb = lab.get_window_extent(renderer=renderer)
                                            if bb is not None:
                                                max_h_px = max(max_h_px, float(bb.height))
                                    # Convert pixels to axes coordinates
                                    if max_h_px > 0 and ax_h_inches > 0:
                                        dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
                                        max_h_inches = max_h_px / dpi
                                        extra_offset = max_h_inches / ax_h_inches
                                except Exception:
                                    # Fallback to fixed offset if labels are on
                                    extra_offset = 0.05

                            total_offset = 1.0 + base_pad_axes + extra_offset
                            ax._top_xlabel_text.set_position((0.5, total_offset))
                        except Exception:
                            # Fallback positioning
                            if bool(wasd['top']['labels']):
                                ax._top_xlabel_text.set_position((0.5, 1.07))
                            else:
                                ax._top_xlabel_text.set_position((0.5, 1.02))
                else:
                    # Hide top label
                    if hasattr(ax, '_top_xlabel_text') and ax._top_xlabel_text is not None:
                        ax._top_xlabel_text.set_visible(False)
            except Exception:
                pass
            try:
                # Left Y title — visibility must match capture (get_visible).
                set_primary_axis_title(
                    ax, "y", on=bool(wasd["left"]["title"]), stored_attr="_stored_ylabel"
                )
            except Exception:
                pass
            try:
                # Right Y title follows wasd/ry, not the current file's sc_eff.
                right_on = bool(wasd["right"]["title"])
                set_primary_axis_title(
                    ax2, "y", on=right_on, stored_attr="_stored_ylabel"
                )
            except Exception:
                pass

            # Only reposition sides that were actually changed
            # This prevents unnecessary title movement when toggling unrelated elements
            apply_changed_side_title_positions(
                changed_sides,
                bottom=lambda: _ui_position_bottom_xlabel(ax, fig, tick_state),
                left=lambda: _ui_position_left_ylabel(ax, fig, tick_state),
            )
            try:
                finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
            except Exception:
                pass

        def _print_wasd():
            _Cw = '\033[96m'; _Rw = '\033[0m'
            def b(v):
                return 'ON ' if bool(v) else 'off'
            print(f"\033[1mToggle spines state:\033[0m")
            print(f"  {'Side':<8}  spine  major  minor  labels title")
            for side_key, side_code in [('top','w'),('bottom','s'),('left','a'),('right','d')]:
                s = wasd[side_key]
                print(f"  {_Cw}{side_code}={side_key:<6}{_Rw} {b(s['spine'])}  {b(s['ticks'])}   {b(s['minor'])}   {b(s['labels'])}  {b(s['title'])}")
            # Tick direction
            tick_dir = getattr(fig, '_tick_direction', 'out')
            print(f"  Tick direction  : {_Cw}{tick_dir}{_Rw}")
            # Tick lengths
            tl = getattr(fig, '_tick_lengths', {}) or {}
            maj_l = tl.get('major')
            min_l = tl.get('minor')
            if maj_l is not None:
                min_str = f"  minor={min_l:.2g}" if min_l is not None else ""
                print(f"  Tick length     : {_Cw}major={maj_l:.2g}{_Rw}{min_str}")
            else:
                print(f"  Tick length     : default")
            # Tick spacing
            def _sp(loc):
                try:
                    if isinstance(loc, MultipleLocator):
                        return str(loc._edge.step)
                    return "auto"
                except Exception:
                    return "auto"
            def _mn(loc):
                try:
                    if isinstance(loc, AutoMinorLocator):
                        return f"{loc._ndivs-1}/interval"
                    if isinstance(loc, NullLocator):
                        return "off"
                    return "auto"
                except Exception:
                    return "auto"
            print(f"  Tick spacing    : {_Cw}x{_Rw}={_sp(ax.xaxis.get_major_locator())}  {_Cw}y{_Rw}={_sp(ax.yaxis.get_major_locator())}  {_Cw}r{_Rw}={_sp(ax2.yaxis.get_major_locator())}")
            print(f"  Minor count     : {_Cw}x{_Rw}={_mn(ax.xaxis.get_minor_locator())}  {_Cw}y{_Rw}={_mn(ax.yaxis.get_minor_locator())}  {_Cw}r{_Rw}={_mn(ax2.yaxis.get_minor_locator())}")

        def _sync_cpc_tick_state():
            sync_tick_state_from_wasd(
                tick_state,
                wasd,
                tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
            )
            try:
                ax._saved_tick_state = dict(tick_state)
            except Exception:
                pass
        def _draw_cpc_spine_menu():
            try:
                finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()

        def _title_offsets() -> None:
            from ..common.title_offsets import run_title_offset_nudge_menu

            def _draw_offsets() -> None:
                try:
                    _ui_position_top_xlabel(ax, fig, tick_state)
                except Exception:
                    pass
                try:
                    _ui_position_bottom_xlabel(ax, fig, tick_state)
                except Exception:
                    pass
                try:
                    _ui_position_left_ylabel(ax, fig, tick_state)
                except Exception:
                    pass
                try:
                    _ui_position_right_ylabel(ax2, fig, tick_state)
                except Exception:
                    pass
                _draw_cpc_spine_menu()

            # Right efficiency title lives on twin ``ax2``.
            run_title_offset_nudge_menu(
                fig=fig,
                ax=ax,
                push_state=lambda: push_state("title-offset"),
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                draw=_draw_offsets,
                axis_by_side={"d": ax2},
            )

        run_spine_tick_menu(
            fig=fig,
            wasd=wasd,
            safe_input=safe_input,
            colorize_prompt=colorize_prompt,
            colorize_inline_commands=colorize_inline_commands,
            push_state=push_state,
            sync_tick_state=_sync_cpc_tick_state,
            apply_wasd=_apply_wasd,
            draw=_draw_cpc_spine_menu,
            mode_label="CPC axes",
            back_label="CPC menu",
            axis_map={'x': ax.xaxis, 'y': ax.yaxis, 'r': ax2.yaxis},
            direction_axes=[ax, ax2],
            length_axes=[ax, ax2],
            title_offset_handler=_title_offsets,
            on_quit=lambda: setattr(ax, '_saved_tick_state', dict(tick_state)),
            print_state=_print_wasd,
        )
        print_menu(fig); return
    except Exception as e:
        print(f"Error in WASD tick menu: {e}")
    print_menu(fig); return
