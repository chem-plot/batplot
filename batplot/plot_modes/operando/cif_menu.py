"""CIF tick-label submenu for the operando interactive menu.

Extracted verbatim from interactive.py (the former nested ``_handle_op_c``);
the dispatcher keeps a thin wrapper so prompts, messages, undo semantics, and
the fig/ax-backed CIF state stay unchanged.
"""
from __future__ import annotations

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...utils import finalize_axis_label_text, print_label_math_help
from .colors import run_operando_cif_color_menu
from .plot import _draw_operando_cif_ticks, append_operando_cif_file


def run_operando_cif_menu(
    *,
    fig,
    ax,
    state_history,
    snapshot,
    pop_undo,
    restore,
    print_menu,
    safe_input,
    colorize_menu,
    colorize_prompt,
    colorize_inline_commands,
):
    """CIF tick labels submenu (a/z/t/h/p/v/c/f/r/n/x/b/q)."""
    def _refresh_cif_locals():
        series = list(getattr(ax, '_operando_cif_tick_series', None) or [])
        hkl_map = dict(getattr(ax, '_operando_cif_hkl_label_map', None) or {})
        show_h = bool(getattr(fig, '_operando_cif_show_hkl', False))
        show_t = bool(getattr(fig, '_operando_cif_show_titles', True))
        place = str(getattr(fig, '_operando_cif_placement', 'below') or 'below')
        y_pos = list(getattr(fig, '_operando_cif_y_positions', None) or [])
        ax_pos = ax.get_position()
        y_base = ax_pos.ymin - 0.02 if place == 'below' else ax_pos.ymax + 0.02
        dy = -0.025 if place == 'below' else 0.025
        while len(y_pos) < len(series):
            y_pos.append(y_base + len(y_pos) * dy)
        fig._operando_cif_y_positions = y_pos
        return series, hkl_map, show_h, show_t, place, y_pos

    def _add_cif_files_interactive():
        """Sub-key a: one multi-select native picker, then return to the CIF menu.

        OS dialog opens immediately (macOS AppleScript, Windows/Linux tkinter,
        Linux zenity/kdialog). After a successful pick the dialog does not reopen.
        If the dialog is cancelled or unavailable, one typed-path fallback is offered.
        """
        nonlocal cif_series, cif_hkl_map, show_hkl, show_titles, placement, y_positions
        from ...utils import _ask_files_dialog, _parse_typed_path_list

        try:
            from .axis_units import ensure_operando_axis_mode
            axis_mode_local = ensure_operando_axis_mode(fig, ax)
        except Exception:
            axis_mode_local = getattr(fig, '_operando_axis_mode', None)
        if axis_mode_local not in ("2theta", "Q", "d"):
            print("CIF overlay needs a known XRD axis (2θ / Q / d).")
            return
        print("Select CIF file(s)… (cancel to return)")
        try:
            picked = _ask_files_dialog(
                filetypes=(".cif", ".CIF"),
                title="Select CIF file(s)",
                multiple=True,
            )
        except Exception:
            picked = []
        if not picked:
            line = safe_input(colorize_prompt(
                "No file selected. Type CIF path(s) (quote if spaces), q=back: "
            )).strip()
            if not line or line.lower() == "q":
                return
            picked = _parse_typed_path_list(line)
            if not picked:
                print("No file selected.")
                return
        wl_suffix = ""
        # Optional wavelength only when the operando axis is 2θ (once for all picks).
        if axis_mode_local == '2theta':
            wl_hint = safe_input(colorize_prompt(
                "Wavelength Å for 2θ (Enter=session default, q=cancel add): "
            )).strip()
            if wl_hint.lower() == 'q':
                return
            if wl_hint:
                try:
                    wl_val = float(wl_hint)
                except ValueError:
                    print("Invalid wavelength; using session default.")
                else:
                    if wl_val > 0 and wl_val == wl_val:
                        wl_suffix = f":{wl_hint}"
                    else:
                        print("Wavelength must be > 0; using session default.")
        for path in picked:
            token = f"{path}{wl_suffix}"
            # snapshot swallows errors — detect a real push by stack growth.
            n_before = len(state_history)
            snapshot("cif-add")
            pushed = len(state_history) > n_before
            try:
                lab, resolved = append_operando_cif_file(fig, ax, token, redraw=True)
                (
                    cif_series,
                    cif_hkl_map,
                    show_hkl,
                    show_titles,
                    placement,
                    y_positions,
                ) = _refresh_cif_locals()
                print(f"Added CIF set {len(cif_series)}: {lab}")
                print(f"  ({resolved})")
            except Exception as exc:
                # Full restore of the pre-add snap (not discard-only): append may
                # have partially mutated artists before raising.
                if pushed:
                    try:
                        restore()
                    except Exception:
                        try:
                            pop_undo()
                        except Exception:
                            pass
                print(f"Could not add CIF: {exc}")

    def _live_axis_mode_wl():
        try:
            from .axis_units import ensure_operando_axis_mode
            mode = ensure_operando_axis_mode(fig, ax)
        except Exception:
            mode = getattr(fig, '_operando_axis_mode', None)
        # Never invent Q — unknown mode → titles-only CIF redraw
        if mode is None:
            mode = ""
        return mode, getattr(fig, '_operando_wl', None)

    def _print_cif_set_list(*, y_positions=None, title_visible=None, set_visible=None):
        """List CIF sets with hex+cube colors so add/rename/hide stay in sync."""
        from ...color_utils import format_color_listing

        for i, entry in enumerate(cif_series):
            try:
                lab, _fname, _p, _w, _q, col = entry
            except Exception:
                lab, col = (entry[0] if entry else f"set {i+1}"), None
            bits = [f"{i+1}:", format_color_listing(col), str(lab)]
            if y_positions is not None and i < len(y_positions):
                bits.append(f"y={y_positions[i]:.2f}")
            if title_visible is not None:
                vis = "show" if (i < len(title_visible) and title_visible[i]) else "hide"
                bits.append(f"({vis})")
            if set_visible is not None:
                vis = "show" if (i < len(set_visible) and set_visible[i]) else "hide"
                bits.append(f"({vis})")
            print("  " + " ".join(bits))

    while True:
        # Always re-sync from fig/ax so newly added CIF sets appear in
        # every sub-key (v/c/r/n/x/…) and undo restores consistently.
        (
            cif_series,
            cif_hkl_map,
            show_hkl,
            show_titles,
            placement,
            y_positions,
        ) = _refresh_cif_locals()
        axis_mode, wl = _live_axis_mode_wl()
        print(colorize_inline_commands("CIF tick labels:"))
        if not cif_series:
            print("  (no CIF sets yet — use a to add)")
        print("  " + colorize_menu("a: add CIF file(s)"))
        if cif_series:
            print("  " + colorize_menu(f"z: toggle hkl labels (currently {'on' if show_hkl else 'off'})"))
            print("  " + colorize_menu(f"t: toggle CIF titles (currently {'on' if show_titles else 'off'})"))
            show_highlight = getattr(fig, '_operando_cif_highlight', False)
            print("  " + colorize_menu(f"h: highlight for overlay (currently {'on' if show_highlight else 'off'})"))
            print("  " + colorize_menu(f"p: placement (currently {placement})"))
            print("  " + colorize_menu("v: vertical position (per CIF set)"))
            print("  " + colorize_menu("c: CIF color (per set / colormap)"))
            cif_font = getattr(fig, '_operando_cif_title_font', None) or {}
            rc_fam = plt.rcParams.get('font.family', ['sans-serif'])
            if isinstance(rc_fam, list):
                rc_fam = rc_fam[0] if rc_fam else 'sans-serif'
            rc_sz = max(8, int(0.55 * plt.rcParams.get('font.size', 12)))
            fam_disp = cif_font.get('family') or rc_fam
            sz_disp = cif_font.get('size') if cif_font.get('size') is not None else rc_sz
            font_desc = f"family={fam_disp}, size={sz_disp}"
            print("  " + colorize_inline_commands(f"f: font (currently {font_desc})"))
            print("  " + colorize_inline_commands("r: rename (per set)  n: hide/show name (per set)"))
            print("  " + colorize_menu("x: show/hide CIF set (per set)"))
        print("  " + colorize_menu("b: undo"))
        print("  " + colorize_menu("q: back"))
        sub = safe_input(colorize_prompt(
            "CIF tick labels (key letter from list above, q=back): "
        )).strip().lower()
        if not sub or sub == 'q':
            break
        if sub == 'a':
            _add_cif_files_interactive()
            continue
        if not cif_series:
            print("No CIF sets yet. Use a to add a CIF file.")
            continue
        if sub == 'z':
            snapshot("cif-hkl")
            fig._operando_cif_show_hkl = not show_hkl
            show_hkl = fig._operando_cif_show_hkl
            _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
            fig.canvas.draw_idle()
            print(f"CIF hkl labels: {'on' if show_hkl else 'off'}")
        elif sub == 't':
            snapshot("cif-titles")
            fig._operando_cif_show_titles = not show_titles
            show_titles = fig._operando_cif_show_titles
            _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
            fig.canvas.draw_idle()
            print(f"CIF titles: {'on' if show_titles else 'off'}")
        elif sub == 'h':
            snapshot("cif-highlight")
            fig._operando_cif_highlight = not getattr(fig, '_operando_cif_highlight', False)
            _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
            fig.canvas.draw_idle()
            print(f"CIF highlight: {'on' if fig._operando_cif_highlight else 'off'} (visible when overlaid on contour)")
        elif sub == 'p':
            snapshot("cif-placement")
            placement = 'above' if placement == 'below' else 'below'
            fig._operando_cif_placement = placement
            ax_pos = ax.get_position()
            y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
            dy = -0.025 if placement == 'below' else 0.025
            y_positions = [y_base + i * dy for i in range(len(cif_series))]
            fig._operando_cif_y_positions = y_positions
            _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
            fig.canvas.draw_idle()
            print(f"CIF placement: {placement}")
        elif sub == 'v':
            print(f"CIF sets: {list(range(1, len(cif_series) + 1))}")
            _print_cif_set_list(y_positions=y_positions)
            idx_s = safe_input(colorize_inline_commands("Set index to adjust (q=back): ")).strip().lower()
            if idx_s == 'q':
                continue
            try:
                idx = int(idx_s) - 1
                if 0 <= idx < len(cif_series):
                    while True:
                        cur_y = y_positions[idx] if idx < len(y_positions) else 0
                        val_s = safe_input(colorize_inline_commands(f"New y for set {idx+1} (current {cur_y:.3f}, w=up s=down, q=back): ")).strip().lower()
                        if not val_s or val_s == 'q':
                            break
                        delta = None
                        target_y = None
                        if val_s == 'w':
                            delta = 0.02
                        elif val_s == 's':
                            delta = -0.02
                        elif val_s:
                            try:
                                target_y = float(val_s)
                            except ValueError:
                                print("Invalid value.")
                                continue
                        if delta is None and target_y is None:
                            continue
                        snapshot("cif-y-position")
                        y_positions = list(getattr(fig, '_operando_cif_y_positions', []))
                        ax_pos = ax.get_position()
                        y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
                        dy = -0.025 if placement == 'below' else 0.025
                        while len(y_positions) < len(cif_series):
                            y_positions.append(y_base + len(y_positions) * dy)
                        if delta is not None:
                            y_positions[idx] = (y_positions[idx] if idx < len(y_positions) else 0) + delta
                        else:
                            y_positions[idx] = target_y
                        fig._operando_cif_y_positions = y_positions
                        _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                        fig.canvas.draw_idle()
                        print(f"Set {idx+1} y = {y_positions[idx]:.2f}")
                else:
                    print("Invalid index.")
            except ValueError:
                print("Invalid index.")
        elif sub in ('c', 'o', 'm'):
            # Unified XY-style CIF color menu (o/m kept as aliases)
            def _redraw_cif_colors(series):
                nonlocal cif_series
                cif_series = list(series)
                ax._operando_cif_tick_series = cif_series
                _draw_operando_cif_ticks(
                    ax, fig, cif_series, cif_hkl_map,
                    axis_mode=axis_mode, wl=wl, show_hkl=show_hkl,
                    show_titles=show_titles, placement=placement,
                    y_positions=y_positions,
                )
                fig.canvas.draw_idle()

            cif_series = run_operando_cif_color_menu(
                fig=fig,
                ax=ax,
                cif_series=cif_series,
                safe_input=safe_input,
                push_state=snapshot,
                redraw=_redraw_cif_colors,
                colorize_prompt=colorize_prompt,
            )
        elif sub == 'f':
            # Validate-then-push: do not leave a junk undo level on open→q.
            cur = getattr(fig, '_operando_cif_title_font', None) or {}
            rc_family = plt.rcParams.get('font.family', ['sans-serif'])
            if isinstance(rc_family, list):
                rc_family = rc_family[0] if rc_family else 'sans-serif'
            rc_size = max(8, int(0.55 * plt.rcParams.get('font.size', 12)))
            fam_display = cur.get('family') or rc_family
            sz_display = cur.get('size') if cur.get('size') is not None else rc_size
            font_pushed = False
            while True:
                print(f"\nCIF title font (current: family={fam_display}, size={sz_display})")
                print("  " + colorize_menu("f: family"))
                print("  " + colorize_menu("s: size"))
                print("  " + colorize_menu("q: back"))
                font_sub = safe_input(colorize_prompt("CIF font (f/s/q): ")).strip().lower()
                if not font_sub or font_sub == 'q':
                    break
                if font_sub == 'f':
                    print(colorize_inline_commands("Common: Arial, DejaVu Sans, Times New Roman, Courier New"))
                    while True:
                        new_fam = safe_input(colorize_prompt(f"Font family (current: {fam_display}, q=back): ")).strip()
                        if not new_fam or new_fam.lower() == 'q':
                            break
                        if not font_pushed:
                            snapshot("cif-font")
                            font_pushed = True
                        font_dict = dict(cur)
                        font_dict['family'] = new_fam
                        fig._operando_cif_title_font = font_dict
                        cur = font_dict
                        fam_display = new_fam
                        _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                        fig.canvas.draw_idle()
                        print(f"CIF title font family: {fam_display}")
                elif font_sub == 's':
                    while True:
                        new_sz = safe_input(colorize_prompt(f"Font size (current: {sz_display}, q=back): ")).strip()
                        if not new_sz or new_sz.lower() == 'q':
                            break
                        try:
                            val = max(6, int(float(new_sz)))
                        except (ValueError, TypeError):
                            print("Invalid font size.")
                            continue
                        if not font_pushed:
                            snapshot("cif-font")
                            font_pushed = True
                        font_dict = dict(cur)
                        font_dict['size'] = val
                        fig._operando_cif_title_font = font_dict
                        cur = font_dict
                        sz_display = val
                        _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                        fig.canvas.draw_idle()
                        print(f"CIF title font size: {sz_display}")
        elif sub == 'r':
            while True:
                (
                    cif_series,
                    cif_hkl_map,
                    show_hkl,
                    show_titles,
                    placement,
                    y_positions,
                ) = _refresh_cif_locals()
                print(colorize_inline_commands("CIF sets (q=back; m=math help)"))
                _print_cif_set_list()
                idx_s = safe_input(colorize_inline_commands("Set index to rename (m=math help, q=back): ")).strip().lower()
                if not idx_s or idx_s == 'q':
                    break
                if idx_s == 'm':
                    print_label_math_help(colorize=colorize_inline_commands)
                    continue
                try:
                    idx = int(idx_s) - 1
                    if 0 <= idx < len(cif_series):
                        lab, fname, peaksQ, wl_e, qmax, col = cif_series[idx]
                        while True:
                            new_lab = safe_input(f"New label for set {idx+1} (current: {lab}, m=math help, q=back): ").strip()
                            if not new_lab or new_lab.lower() == 'q':
                                break
                            if new_lab.lower() == 'm':
                                print_label_math_help(colorize=colorize_inline_commands)
                                continue
                            new_lab = finalize_axis_label_text(new_lab)
                            snapshot("cif-rename")
                            cif_series = list(cif_series)
                            cif_series[idx] = (new_lab, fname, peaksQ, wl_e, qmax, col)
                            ax._operando_cif_tick_series = cif_series
                            _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                            fig.canvas.draw_idle()
                            print(f"Set {idx+1} renamed to: {new_lab}")
                    else:
                        print("Invalid index.")
                except ValueError:
                    print("Invalid index.")
        elif sub == 'n':
            while True:
                (
                    cif_series,
                    cif_hkl_map,
                    show_hkl,
                    show_titles,
                    placement,
                    y_positions,
                ) = _refresh_cif_locals()
                title_visible = list(
                    getattr(fig, '_operando_cif_title_visible', None)
                    or [True] * len(cif_series)
                )
                while len(title_visible) < len(cif_series):
                    title_visible.append(True)
                print("CIF sets - hide/show name (per set):")
                _print_cif_set_list(title_visible=title_visible)
                idx_s = safe_input(colorize_inline_commands("Set index to toggle (q=back): ")).strip().lower()
                if not idx_s or idx_s == 'q':
                    break
                try:
                    idx = int(idx_s) - 1
                    if 0 <= idx < len(cif_series):
                        snapshot("cif-hide-name")
                        if idx < len(title_visible):
                            title_visible[idx] = not title_visible[idx]
                        else:
                            title_visible.extend([True] * (idx - len(title_visible) + 1))
                            title_visible[idx] = False
                        fig._operando_cif_title_visible = title_visible
                        _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                        fig.canvas.draw_idle()
                        v = "shown" if title_visible[idx] else "hidden"
                        print(f"Set {idx+1} name: {v}")
                    else:
                        print("Invalid index.")
                except ValueError:
                    print("Invalid index.")
        elif sub == 'x':
            while True:
                (
                    cif_series,
                    cif_hkl_map,
                    show_hkl,
                    show_titles,
                    placement,
                    y_positions,
                ) = _refresh_cif_locals()
                set_visible = list(
                    getattr(fig, '_operando_cif_set_visible', None)
                    or [True] * len(cif_series)
                )
                while len(set_visible) < len(cif_series):
                    set_visible.append(True)
                print("CIF sets - show/hide entire set (ticks + labels):")
                _print_cif_set_list(set_visible=set_visible)
                idx_s = safe_input(colorize_inline_commands("Set index to toggle (q=back): ")).strip().lower()
                if not idx_s or idx_s == 'q':
                    break
                try:
                    idx = int(idx_s) - 1
                    if 0 <= idx < len(cif_series):
                        snapshot("cif-set-visibility")
                        if idx < len(set_visible):
                            set_visible[idx] = not set_visible[idx]
                        else:
                            set_visible.extend([True] * (idx - len(set_visible) + 1))
                            set_visible[idx] = False
                        fig._operando_cif_set_visible = set_visible
                        _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                        fig.canvas.draw_idle()
                        v = "shown" if set_visible[idx] else "hidden"
                        print(f"Set {idx+1}: {v}")
                    else:
                        print("Invalid index.")
                except ValueError:
                    print("Invalid index.")
        elif sub == 'b':
            restore()
            (
                cif_series,
                cif_hkl_map,
                show_hkl,
                show_titles,
                placement,
                y_positions,
            ) = _refresh_cif_locals()
            axis_mode, wl = _live_axis_mode_wl()
            _draw_operando_cif_ticks(
                ax, fig, cif_series, cif_hkl_map,
                axis_mode=axis_mode, wl=wl, show_hkl=show_hkl,
                show_titles=show_titles, placement=placement,
                y_positions=y_positions,
            )
            fig.canvas.draw_idle()
        else:
            print("Unknown choice.")
    print_menu()
