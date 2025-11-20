"""UI utilities for batplot: font/tick helpers and resize operations."""

from __future__ import annotations

from typing import List, Dict, Any
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, NullFormatter
import matplotlib.transforms as mtransforms


def apply_font_changes(ax, fig, label_text_objects: List, normalize_label_text, new_size=None, new_family=None):
    if new_family:
        fallback_chain = ['DejaVu Sans', 'Arial Unicode MS', 'Liberation Sans']
        existing = plt.rcParams.get('font.sans-serif', [])
        new_list = [new_family] + [f for f in fallback_chain if f != new_family] + \
                   [f for f in existing if f not in fallback_chain and f != new_family]
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = new_list
        lf = new_family.lower()
        if any(k in lf for k in ('stix', 'times', 'roman')):
            plt.rcParams['mathtext.fontset'] = 'stix'
        else:
            plt.rcParams['mathtext.fontset'] = 'dejavusans'
    if new_size is not None:
        plt.rcParams['font.size'] = new_size
    for txt in label_text_objects:
        if new_size is not None:
            txt.set_fontsize(new_size)
        if new_family:
            txt.set_fontfamily(new_family)
    for axis_label in (ax.xaxis.label, ax.yaxis.label):
        cur = axis_label.get_text()
        norm = normalize_label_text(cur)
        if norm != cur:
            axis_label.set_text(norm)
        if new_size is not None:
            axis_label.set_fontsize(new_size)
        if new_family:
            axis_label.set_fontfamily(new_family)
    if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
        if new_size is not None:
            ax._top_xlabel_artist.set_fontsize(new_size)
        if new_family:
            ax._top_xlabel_artist.set_fontfamily(new_family)
    if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
        if new_size is not None:
            ax._right_ylabel_artist.set_fontsize(new_size)
        if new_family:
            ax._right_ylabel_artist.set_fontfamily(new_family)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        if new_size is not None:
            lbl.set_fontsize(new_size)
        if new_family:
            lbl.set_fontfamily(new_family)
    # Also update top/right tick labels (label2)
    try:
        for t in ax.xaxis.get_major_ticks():
            if hasattr(t, 'label2'):
                if new_size is not None: t.label2.set_size(new_size)
                if new_family: t.label2.set_family(new_family)
        for t in ax.yaxis.get_major_ticks():
            if hasattr(t, 'label2'):
                if new_size is not None: t.label2.set_size(new_size)
                if new_family: t.label2.set_family(new_family)
    except Exception:
        pass
    fig.canvas.draw_idle()


def sync_fonts(ax, fig, label_text_objects: List):
    try:
        base_size = plt.rcParams.get('font.size')
        if base_size is None:
            return
        for txt in label_text_objects:
            txt.set_fontsize(base_size)
        if ax.xaxis.label: ax.xaxis.label.set_fontsize(base_size)
        if ax.yaxis.label: ax.yaxis.label.set_fontsize(base_size)
        if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
            ax._top_xlabel_artist.set_fontsize(base_size)
        if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
            ax._right_ylabel_artist.set_fontsize(base_size)
        for tl in ax.get_xticklabels() + ax.get_yticklabels():
            tl.set_fontsize(base_size)
        fig.canvas.draw_idle()
    except Exception:
        pass


def position_top_xlabel(ax, fig, tick_state: Dict[str, bool]):
    try:
        on = bool(getattr(ax, '_top_xlabel_on', False))
        if on:
            # Try multiple sources for label text: bottom xlabel, stored, or existing artist
            base = ax.get_xlabel()
            if not base and hasattr(ax, '_stored_xlabel'):
                try:
                    base = ax._stored_xlabel
                except Exception:
                    pass
            if not base:
                prev = getattr(ax, '_top_xlabel_artist', None)
                if prev is not None and hasattr(prev, 'get_text'):
                    base = prev.get_text() or ''
                else:
                    base = ''
            
            # Get renderer without forcing draws (let main loop handle drawing)
            try:
                renderer = fig.canvas.get_renderer()
            except Exception:
                renderer = None

            # Measure tick label height - ONLY use top labels for top title (independence)
            dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
            max_h_px = 0.0

            # Measure TOP tick labels only (for independence from bottom side)
            top_labels_on = bool(tick_state.get('t_labels', tick_state.get('tx', False)))
            if top_labels_on and renderer is not None:
                try:
                    for t in ax.xaxis.get_major_ticks():
                        lab = getattr(t, 'label2', None)
                        if lab is not None and lab.get_visible():
                            bb = lab.get_window_extent(renderer=renderer)
                            if bb is not None:
                                max_h_px = max(max_h_px, float(bb.height))
                except Exception:
                    pass

            # Convert to points and add gap (match matplotlib's labelpad = 14pt)
            if max_h_px > 0:
                tick_height_pts = max_h_px * 72.0 / dpi
                dy_pts = tick_height_pts + 14.0  # 14pt gap to match bottom labelpad
            else:
                dy_pts = 6.0  # Minimal spacing when no tick labels (match small labelpad)
            
            base_trans = ax.transAxes
            off_trans = mtransforms.offset_copy(base_trans, fig=fig, x=0.0, y=dy_pts, units='points')
            art = getattr(ax, '_top_xlabel_artist', None)
            if art is None:
                ax._top_xlabel_artist = ax.text(0.5, 1.0, base, ha='center', va='bottom', transform=off_trans, clip_on=False, zorder=10)
            else:
                ax._top_xlabel_artist.set_transform(off_trans)
                ax._top_xlabel_artist.set_text(base)
                ax._top_xlabel_artist.set_visible(True)
        else:
            if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                try:
                    ax._top_xlabel_artist.set_visible(False)
                except Exception:
                    pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def position_right_ylabel(ax, fig, tick_state: Dict[str, bool]):
    try:
        on = bool(getattr(ax, '_right_ylabel_on', False))
        if on:
            # Try multiple sources for label text: left ylabel, stored, or existing artist
            base = ax.get_ylabel()
            if not base and hasattr(ax, '_stored_ylabel'):
                try:
                    base = ax._stored_ylabel
                except Exception:
                    pass
            if not base:
                prev = getattr(ax, '_right_ylabel_artist', None)
                if prev is not None and hasattr(prev, 'get_text'):
                    base = prev.get_text() or ''
                else:
                    base = ''
            
            # Get renderer without forcing draws (let main loop handle drawing)
            try:
                renderer = fig.canvas.get_renderer()
            except Exception:
                renderer = None

            # Measure tick label width - ONLY use right labels for right title (independence)
            dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
            max_w_px = 0.0

            # Measure RIGHT tick labels only (for independence from left side)
            right_labels_on = bool(tick_state.get('r_labels', tick_state.get('ry', False)))
            if right_labels_on and renderer is not None:
                try:
                    for t in ax.yaxis.get_major_ticks():
                        lab = getattr(t, 'label2', None)
                        if lab is not None and lab.get_visible():
                            bb = lab.get_window_extent(renderer=renderer)
                            if bb is not None:
                                max_w_px = max(max_w_px, float(bb.width))
                except Exception:
                    pass

            # Convert to points and add gap (6pt gap to visually match left labelpad=8pt)
            if max_w_px > 0:
                tick_width_pts = max_w_px * 72.0 / dpi
                dx_pts = tick_width_pts + 6.0  # 6pt gap to visually match left labelpad
            else:
                dx_pts = 6.0  # Minimal spacing when no tick labels (match small labelpad)
            
            # Place at (1.0, 0.5) in axes with a points-based offset to the right
            base_trans = ax.transAxes
            off_trans = mtransforms.offset_copy(base_trans, fig=fig, x=dx_pts, y=0.0, units='points')
            art = getattr(ax, '_right_ylabel_artist', None)
            if art is None:
                ax._right_ylabel_artist = ax.text(
                    1.0, 0.5, base,
                    rotation=90, va='center', ha='left', transform=off_trans,
                    clip_on=False, zorder=10
                )
            else:
                ax._right_ylabel_artist.set_transform(off_trans)
                ax._right_ylabel_artist.set_text(base)
                ax._right_ylabel_artist.set_visible(True)
        else:
            if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                try:
                    ax._right_ylabel_artist.set_visible(False)
                except Exception:
                    pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def position_bottom_xlabel(ax, fig, tick_state: Dict[str, bool]):
    """Adjust bottom X label spacing based on bottom tick label visibility.

    Uses labelpad (in points). Larger pad when bottom tick labels are visible,
    smaller when hidden.
    """
    try:
        lbl = ax.get_xlabel()
        if not lbl:
            return
        # If a one-shot pad restore is pending (after hide->show), honor it once to avoid drift
        if hasattr(ax, '_pending_xlabelpad') and ax._pending_xlabelpad is not None:
            try:
                ax.xaxis.labelpad = ax._pending_xlabelpad
            finally:
                try:
                    delattr(ax, '_pending_xlabelpad')
                except Exception:
                    pass
            return
        # Otherwise choose pad based on current tick label visibility
        pad = 8 if bool(tick_state.get('b_labels', tick_state.get('bx', False))) else 6
        try:
            ax.xaxis.labelpad = pad
        except Exception:
            pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def position_left_ylabel(ax, fig, tick_state: Dict[str, bool]):
    """Adjust left Y label spacing based on left tick label visibility.

    Uses labelpad (in points). Larger pad when left tick labels are visible,
    smaller when hidden.
    """
    try:
        lbl = ax.get_ylabel()
        if not lbl:
            return
        # If a one-shot pad restore is pending (after hide->show), honor it once to avoid drift
        if hasattr(ax, '_pending_ylabelpad') and ax._pending_ylabelpad is not None:
            try:
                ax.yaxis.labelpad = ax._pending_ylabelpad
            finally:
                try:
                    delattr(ax, '_pending_ylabelpad')
                except Exception:
                    pass
            return
        pad = 8 if bool(tick_state.get('l_labels', tick_state.get('ly', False))) else 6
        try:
            ax.yaxis.labelpad = pad
        except Exception:
            pass
        # Do NOT call draw_idle() here - let the main loop handle drawing
    except Exception:
        pass


def update_tick_visibility(ax, tick_state: Dict[str, bool]):
    # Support new separate tick/label keys; fallback to legacy when absent
    if 'b_ticks' in tick_state or 'b_labels' in tick_state:
        ax.tick_params(axis='x',
                       bottom=bool(tick_state.get('b_ticks', True)), labelbottom=bool(tick_state.get('b_labels', True)),
                       top=bool(tick_state.get('t_ticks', False)),   labeltop=bool(tick_state.get('t_labels', False)))
        ax.tick_params(axis='y',
                       left=bool(tick_state.get('l_ticks', True)),  labelleft=bool(tick_state.get('l_labels', True)),
                       right=bool(tick_state.get('r_ticks', False)), labelright=bool(tick_state.get('r_labels', False)))
    else:
        ax.tick_params(axis='x',
                       bottom=tick_state['bx'], labelbottom=tick_state['bx'],
                       top=tick_state['tx'],    labeltop=tick_state['tx'])
        ax.tick_params(axis='y',
                       left=tick_state['ly'],  labelleft=tick_state['ly'],
                       right=tick_state['ry'], labelright=tick_state['ry'])
    if tick_state['mbx'] or tick_state['mtx']:
        ax.xaxis.set_minor_locator(AutoMinorLocator())
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis='x', which='minor',
                       bottom=tick_state['mbx'],
                       top=tick_state['mtx'],
                       labelbottom=False, labeltop=False)
    else:
        ax.tick_params(axis='x', which='minor', bottom=False, top=False,
                       labelbottom=False, labeltop=False)
    if tick_state['mly'] or tick_state['mry']:
        ax.yaxis.set_minor_locator(AutoMinorLocator())
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.tick_params(axis='y', which='minor',
                       left=tick_state['mly'],
                       right=tick_state['mry'],
                       labelleft=False, labelright=False)
    else:
        ax.tick_params(axis='y', which='minor', left=False, right=False,
                       labelleft=False, labelright=False)
    # After visibility changes, sync tick label fonts (label1 and label2) to rcParams
    try:
        fam_chain = plt.rcParams.get('font.sans-serif')
        fam0 = fam_chain[0] if isinstance(fam_chain, list) and fam_chain else None
        size0 = plt.rcParams.get('font.size', None)
        # Standard tick labels (bottom/left)
        for lbl in ax.get_xticklabels() + ax.get_yticklabels():
            if size0 is not None:
                try: lbl.set_fontsize(size0)
                except Exception: pass
            if fam0:
                try: lbl.set_fontfamily(fam0)
                except Exception: pass
        # Top/right labels (label2)
        for t in ax.xaxis.get_major_ticks():
            lab2 = getattr(t, 'label2', None)
            if lab2 is not None:
                if size0 is not None:
                    try: lab2.set_fontsize(size0)
                    except Exception: pass
                if fam0:
                    try: lab2.set_fontfamily(fam0)
                    except Exception: pass
        for t in ax.yaxis.get_major_ticks():
            lab2 = getattr(t, 'label2', None)
            if lab2 is not None:
                if size0 is not None:
                    try: lab2.set_fontsize(size0)
                    except Exception: pass
                if fam0:
                    try: lab2.set_fontfamily(fam0)
                    except Exception: pass
    except Exception:
        pass


def ensure_text_visibility(fig, ax, label_text_objects: List, max_iterations=4, check_only=False):
    try:
        renderer = fig.canvas.get_renderer()
    except Exception:
        fig.canvas.draw()
        try:
            renderer = fig.canvas.get_renderer()
        except Exception:
            return
    if renderer is None:
        return

    def collect(renderer_obj):
        items = []
        # CRITICAL: Check visibility to avoid measuring hidden labels
        if ax.xaxis.label.get_text() and ax.xaxis.label.get_visible():
            try: items.append(ax.xaxis.label.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        if ax.yaxis.label.get_text() and ax.yaxis.label.get_visible():
            try: items.append(ax.yaxis.label.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        # Include duplicate top/right title artists if present
        if getattr(ax, '_top_xlabel_on', False) and hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
            try: items.append(ax._top_xlabel_artist.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        if getattr(ax, '_right_ylabel_on', False) and hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
            try: items.append(ax._right_ylabel_artist.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        for t in label_text_objects:
            try: items.append(t.get_window_extent(renderer=renderer_obj))
            except Exception: pass
        return items

    fig_w, fig_h = fig.get_size_inches(); dpi = fig.dpi
    W, H = fig_w * dpi, fig_h * dpi
    pad = 2

    def is_out(bb):
        return (bb.x0 < -pad or bb.y0 < -pad or bb.x1 > W + pad or bb.y1 > H + pad)

    initial = collect(renderer)
    overflow = any(is_out(bb) for bb in initial)
    if check_only:
        return overflow
    if not overflow:
        return False

    for _ in range(max_iterations):
        sp = fig.subplotpars
        left, right, bottom, top = sp.left, sp.right, sp.bottom, sp.top
        changed = False
        for bb in collect(renderer):
            if not is_out(bb):
                continue
            if bb.x0 < 0 and left < 0.40:
                left = min(left + 0.01, 0.40); changed = True
            if bb.x1 > W and right > left + 0.25:
                right = max(right - 0.01, left + 0.25); changed = True
            if bb.y0 < 0 and bottom < 0.40:
                bottom = min(bottom + 0.01, 0.40); changed = True
            if bb.y1 > H and top > bottom + 0.25:
                top = max(top - 0.01, bottom + 0.25); changed = True
        if not changed:
            break
        fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
        fig.canvas.draw()
        try:
            renderer = fig.canvas.get_renderer()
        except Exception:
            break
        if not any(is_out(bb) for bb in collect(renderer)):
            break
    return True


def resize_plot_frame(fig, ax, y_data_list: List, label_text_objects: List, args, update_labels_func):
    while True:
        try:
            fig_w_in, fig_h_in = fig.get_size_inches()
            ax_bbox = ax.get_position()
            cur_ax_w_in = ax_bbox.width * fig_w_in
            cur_ax_h_in = ax_bbox.height * fig_h_in
            print(f"Current canvas (fixed): {fig_w_in:.2f} x {fig_h_in:.2f} in")
            print(f"Current plot frame:     {cur_ax_w_in:.2f} x {cur_ax_h_in:.2f} in (W x H)")
            try:
                spec = input("Enter new plot frame size (e.g. '6 4', '6x4', 'w=6 h=4', 'scale=1.2', single width, q=back): ").strip().lower()
            except KeyboardInterrupt:
                print("Canceled.")
                return
            if not spec or spec == 'q':
                return
            new_w_in, new_h_in = cur_ax_w_in, cur_ax_h_in
            if 'scale=' in spec:
                try:
                    factor = float(spec.split('scale=')[1].strip())
                    new_w_in = cur_ax_w_in * factor
                    new_h_in = cur_ax_h_in * factor
                except Exception:
                    print("Invalid scale factor.")
                    continue
            else:
                parts = spec.replace('x', ' ').split()
                kv = {}; numbers = []
                for p in parts:
                    if '=' in p:
                        k, v = p.split('=', 1)
                        kv[k.strip()] = v.strip()
                    else:
                        numbers.append(p)
                if kv:
                    if 'w' in kv: new_w_in = float(kv['w'])
                    if 'h' in kv: new_h_in = float(kv['h'])
                elif len(numbers) == 2:
                    new_w_in, new_h_in = float(numbers[0]), float(numbers[1])
                elif len(numbers) == 1:
                    new_w_in = float(numbers[0])
                    aspect = cur_ax_h_in / cur_ax_w_in if cur_ax_w_in else 1.0
                    new_h_in = new_w_in * aspect
                else:
                    print("Could not parse specification.")
                    continue
            req_w_in, req_h_in = new_w_in, new_h_in
            min_margin_frac = 0.05
            max_w_in = fig_w_in * (1 - 2 * min_margin_frac)
            max_h_in = fig_h_in * (1 - 2 * min_margin_frac)
            if new_w_in > max_w_in:
                print(f"Requested width {new_w_in:.2f} exceeds max {max_w_in:.2f}; clamped.")
                new_w_in = max_w_in
            if new_h_in > max_h_in:
                print(f"Requested height {new_h_in:.2f} exceeds max {max_h_in:.2f}; clamped.")
                new_h_in = max_h_in
            min_ax_in = 0.25
            new_w_in = max(min_ax_in, new_w_in)
            new_h_in = max(min_ax_in, new_h_in)
            tol = 1e-3
            requesting_full_canvas = (abs(req_w_in - fig_w_in) < tol and abs(req_h_in - fig_h_in) < tol)
            w_frac = new_w_in / fig_w_in
            h_frac = new_h_in / fig_h_in
            same_axes = False
            if hasattr(fig, '_last_user_axes_inches'):
                pw, ph = fig._last_user_axes_inches
                if abs(pw - new_w_in) < tol and abs(ph - new_h_in) < tol:
                    same_axes = True
            if same_axes and hasattr(fig, '_last_user_margins'):
                lm, bm, rm, tm = fig._last_user_margins
                fig.subplots_adjust(left=lm, bottom=bm, right=rm, top=tm)
                update_labels_func(ax, y_data_list, label_text_objects, args.stack)
                if not ensure_text_visibility(fig, ax, label_text_objects, check_only=True):
                    fig.canvas.draw_idle()
                    print(f"Plot frame unchanged ({new_w_in:.2f} x {new_h_in:.2f} in); layout preserved.")
                    continue
            left = (1 - w_frac) / 2
            right = left + w_frac
            bottom = (1 - h_frac) / 2
            top = bottom + h_frac
            left = max(min_margin_frac, left)
            bottom = max(min_margin_frac, bottom)
            right = min(1 - min_margin_frac, right)
            top = min(1 - min_margin_frac, top)
            if right - left < 0.05 or top - bottom < 0.05:
                print("Requested frame too small after safety clamps; aborting.")
            else:
                fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
            update_labels_func(ax, y_data_list, label_text_objects, args.stack)
            ensure_text_visibility(fig, ax, label_text_objects)
            sp = fig.subplotpars
            fig._last_user_axes_inches = (((sp.right - sp.left) * fig_w_in), ((sp.top - sp.bottom) * fig_h_in))
            fig._last_user_margins = (sp.left, sp.bottom, sp.right, sp.top)
            final_w_in = (sp.right - sp.left) * fig_w_in
            final_h_in = (sp.top - sp.bottom) * fig_h_in
            if requesting_full_canvas:
                print(f"Requested full-canvas frame. Canvas remains {fig_w_in:.2f} x {fig_h_in:.2f} in; frame now {final_w_in:.2f} x {final_h_in:.2f} in (maximum with minimum margins {min_margin_frac*100:.0f}%).")
            else:
                print(f"Plot frame set to {final_w_in:.2f} x {final_h_in:.2f} in inside fixed canvas {fig_w_in:.2f} x {fig_h_in:.2f} in.")
        except KeyboardInterrupt:
            print("Canceled.")
            return
        except Exception as e:
            print(f"Error resizing plot frame: {e}")


def resize_canvas(fig, ax):
    while True:
        try:
            cur_w, cur_h = fig.get_size_inches()
            bbox_before = ax.get_position()
            frame_w_in_before = bbox_before.width * cur_w
            frame_h_in_before = bbox_before.height * cur_h
            print(f"Current canvas size: {cur_w:.2f} x {cur_h:.2f} in (frame {frame_w_in_before:.2f} x {frame_h_in_before:.2f} in)")
            try:
                spec = input("Enter new canvas size (e.g. '8 6', '6x4', 'w=6 h=5', 'scale=1.2', q=back): ").strip().lower()
            except KeyboardInterrupt:
                print("Canceled.")
                return
            if not spec or spec == 'q':
                return
            new_w, new_h = cur_w, cur_h
            if 'scale=' in spec:
                try:
                    fct = float(spec.split('scale=')[1])
                    new_w, new_h = cur_w * fct, cur_h * fct
                except Exception:
                    print("Invalid scale factor.")
                    continue
            else:
                parts = spec.replace('x',' ').split()
                kv = {}; nums = []
                for p in parts:
                    if '=' in p:
                        k,v = p.split('=',1); kv[k.strip()] = v.strip()
                    else:
                        nums.append(p)
                if kv:
                    if 'w' in kv: new_w = float(kv['w'])
                    if 'h' in kv: new_h = float(kv['h'])
                elif len(nums)==2:
                    new_w, new_h = float(nums[0]), float(nums[1])
                elif len(nums)==1:
                    new_w = float(nums[0]); aspect = cur_h/cur_w if cur_w else 1.0; new_h = new_w * aspect
                else:
                    print("Could not parse specification.")
                    continue
            min_size = 1.0
            new_w = max(min_size, new_w)
            new_h = max(min_size, new_h)
            tol = 1e-3
            same = hasattr(fig,'_last_canvas_size') and all(abs(a-b)<tol for a,b in zip(fig._last_canvas_size,(new_w,new_h)))
            fig.set_size_inches(new_w, new_h, forward=True)
            bbox_after = ax.get_position()
            desired_w_frac = frame_w_in_before / new_w
            desired_h_frac = frame_h_in_before / new_h
            min_margin = 0.05
            max_w_frac = 1 - 2*min_margin
            max_h_frac = 1 - 2*min_margin
            if desired_w_frac > max_w_frac:
                desired_w_frac = max_w_frac
            if desired_h_frac > max_h_frac:
                desired_h_frac = max_h_frac
            left = (1 - desired_w_frac) / 2
            bottom = (1 - desired_h_frac) / 2
            right = left + desired_w_frac
            top = bottom + desired_h_frac
            if right - left > 0.05 and top - bottom > 0.05:
                fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
            fig._last_canvas_size = (new_w, new_h)
            bbox_final = ax.get_position()
            final_frame_w_in = bbox_final.width * new_w
            final_frame_h_in = bbox_final.height * new_h
            if same:
                print(f"Canvas unchanged ({new_w:.2f} x {new_h:.2f} in). Frame {final_frame_w_in:.2f} x {final_frame_h_in:.2f} in.")
            else:
                note = ""
                if abs(final_frame_w_in - frame_w_in_before) > 1e-3 or abs(final_frame_h_in - frame_h_in_before) > 1e-3:
                    note = " (clamped to fit)" if final_frame_w_in < frame_w_in_before or final_frame_h_in < frame_h_in_before else ""
                print(f"Canvas resized to {new_w:.2f} x {new_h:.2f} in; frame preserved at {final_frame_w_in:.2f} x {final_frame_h_in:.2f} in{note} (was {frame_w_in_before:.2f} x {frame_h_in_before:.2f}).")
            fig.canvas.draw_idle()
        except KeyboardInterrupt:
            print("Canceled.")
            return
        except Exception as e:
            print(f"Error resizing canvas: {e}")


__all__ = [
    'apply_font_changes',
    'sync_fonts',
    'position_top_xlabel',
    'position_right_ylabel',
    'position_bottom_xlabel',
    'position_left_ylabel',
    'update_tick_visibility',
    'ensure_text_visibility',
    'resize_plot_frame',
    'resize_canvas',
]