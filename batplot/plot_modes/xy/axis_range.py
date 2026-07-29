"""Axis-range submenus (``x`` and ``y``) for the XY interactive menu.

These set/restore the displayed X and Y windows, with the X handler being
processed-data aware (re-expands from full/processed arrays). All data lists are
mutated in place; the dispatcher injects them plus the terminal callbacks.
"""

from __future__ import annotations

from typing import Any, Callable, List

import numpy as np  # type: ignore[import]

from ...plotting import update_labels


def _xy_truly_processed(fig: Any) -> bool:
    """True only when smooth/derivative (or full-processed buffers) exist.

    Presence of ``_original_x_data_list`` alone does NOT count: session load
    always restores that attribute as a full-data backup even for unprocessed
    plots. Treating it as "processed" made the X-range menu expand from the
    cropped displayed window and drop recoverable ``x_full_data``.
    """
    if bool(getattr(fig, "_smooth_settings", None)):
        return True
    if int(getattr(fig, "_derivative_order", 0) or 0) > 0:
        return True
    if hasattr(fig, "_pre_derivative_x_data_list"):
        return True
    if hasattr(fig, "_full_processed_x_data_list"):
        return True
    return False


def _set_orig_y_at(orig_y: List[Any], i: int, arr: Any) -> None:
    while len(orig_y) <= i:
        orig_y.append(np.array([], dtype=float))
    try:
        y1 = np.asarray(arr, dtype=float).ravel()
        if i < len(orig_y):
            del orig_y[i]
        orig_y.insert(i, y1)
    except Exception:
        try:
            orig_y[i] = np.asarray(arr, dtype=float).ravel()
        except Exception:
            pass


def _refilter_curves_from_full(
    *,
    args: Any,
    labels: List[str],
    x_data_list: List[Any],
    y_data_list: List[Any],
    orig_y: List[Any],
    offsets_list: List[float],
    x_full_list: List[Any],
    raw_y_full_list: List[Any],
    new_min: float,
    new_max: float,
    _line: Callable[[int], Any],
) -> None:
    """Slice curves from untrimmed ``x_full_list`` / ``raw_y_full_list`` into [new_min, new_max]."""
    for i in range(len(labels)):
        xf = x_full_list[i] if i < len(x_full_list) else x_data_list[i]
        yf_raw = (
            raw_y_full_list[i]
            if i < len(raw_y_full_list)
            else (orig_y[i] if i < len(orig_y) else y_data_list[i])
        )
        xf = np.asarray(xf, dtype=float).flatten()
        yf_raw = np.asarray(yf_raw, dtype=float).flatten()
        if xf.size != yf_raw.size:
            m = min(xf.size, yf_raw.size)
            xf, yf_raw = xf[:m], yf_raw[:m]
        mask = (xf >= new_min) & (xf <= new_max)
        x_sub = np.asarray(xf[mask], dtype=float).flatten()
        y_sub_raw = np.asarray(yf_raw[mask], dtype=float).flatten()
        if x_sub.size == 0:
            _line(i).set_data([], [])
            x_data_list[i] = np.array([], dtype=float)
            y_data_list[i] = np.array([], dtype=float)
            if i < len(orig_y):
                orig_y[i] = np.array([], dtype=float)
            continue
        should_normalize = args.stack or getattr(args, "norm", False)
        if should_normalize and y_sub_raw.size:
            y_min = float(y_sub_raw.min())
            y_max = float(y_sub_raw.max())
            span = y_max - y_min
            y_sub_norm = (y_sub_raw - y_min) / span if span > 0 else np.zeros_like(y_sub_raw)
        else:
            y_sub_norm = y_sub_raw
        offset_val = offsets_list[i] if i < len(offsets_list) else 0.0
        y_with_offset = y_sub_norm + offset_val
        _line(i).set_data(x_sub, y_with_offset)
        x_data_list[i] = np.asarray(x_sub, dtype=float).flatten()
        y_data_list[i] = np.asarray(y_with_offset, dtype=float).flatten()
        _set_orig_y_at(orig_y, i, y_sub_norm)


def _full_processed_covers(fig: Any, new_min: float, new_max: float) -> bool:
    """True if ``_full_processed_x_data_list`` spans the requested X window."""
    arrs = getattr(fig, "_full_processed_x_data_list", None)
    if not arrs:
        return False
    try:
        lo = min(float(np.asarray(a).min()) for a in arrs if np.asarray(a).size)
        hi = max(float(np.asarray(a).max()) for a in arrs if np.asarray(a).size)
    except ValueError:
        return False
    return lo <= new_min + 1e-12 and hi >= new_max - 1e-12


def run_x_range_menu(
    *,
    args: Any,
    ax: Any,
    fig: Any,
    labels: List[str],
    label_text_objects: List[Any],
    x_data_list: List[Any],
    y_data_list: List[Any],
    orig_y: List[Any],
    offsets_list: List[float],
    x_full_list: List[Any],
    raw_y_full_list: List[Any],
    push_state: Callable[[str], Any],
    _safe_input: Callable[[str], str],
    _line: Callable[[int], Any],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
        while True:
            try:
                current_xlim = ax.get_xlim()
                print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + colorize_menu("w: upper only"))
                print("  " + colorize_menu("s: lower only"))
                print("  " + colorize_menu("a: auto (restore original)"))
                print("  " + colorize_menu("q: back"))
                rng = _safe_input(colorize_prompt("X (w/s/a/q): ")).strip()
                if not rng or rng.lower() == 'q':
                    break
                if rng.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        current_xlim = ax.get_xlim()
                        print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter upper limit (current lower: {current_xlim[0]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("xrange")
                        new_min = current_xlim[0]
                        new_max = new_upper
                        ax.set_xlim(new_min, new_max)
                        # Re-filter data from original processed data if available
                        data_is_processed = _xy_truly_processed(fig)
                        if data_is_processed and _full_processed_covers(fig, new_min, new_max):
                            for i in range(len(labels)):
                                if i >= len(fig._full_processed_x_data_list):
                                    continue
                                x_current = np.asarray(fig._full_processed_x_data_list[i], dtype=float).flatten()
                                y_current = np.asarray(fig._full_processed_y_data_list[i], dtype=float).flatten()
                                off = offsets_list[i] if i < len(offsets_list) else 0.0
                                y_current_no_offset = y_current - off
                                mask = (x_current >= new_min) & (x_current <= new_max)
                                x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                                y_sub = np.asarray(y_current_no_offset[mask], dtype=float).flatten()
                                if x_sub.size == 0:
                                    _line(i).set_data([], [])
                                    x_data_list[i] = np.array([], dtype=float)
                                    y_data_list[i] = np.array([], dtype=float)
                                    if i < len(orig_y):
                                        orig_y[i] = np.array([], dtype=float)
                                    continue
                                y_sub = y_sub + off
                                _line(i).set_data(x_sub, y_sub)
                                x_data_list[i] = x_sub
                                y_data_list[i] = y_sub
                                _set_orig_y_at(orig_y, i, y_sub - off)
                        else:
                            # Unprocessed, or processed crop that does not span the new window
                            _refilter_curves_from_full(
                                args=args, labels=labels,
                                x_data_list=x_data_list, y_data_list=y_data_list, orig_y=orig_y,
                                offsets_list=offsets_list, x_full_list=x_full_list,
                                raw_y_full_list=raw_y_full_list, new_min=new_min, new_max=new_max,
                                _line=_line,
                            )
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        try:
                            if hasattr(ax, '_cif_extend_func'):
                                ax._cif_extend_func(ax.get_xlim()[1])
                        except Exception:
                            pass
                        try:
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                        except Exception:
                            pass
                        fig.canvas.draw()
                        print(f"X range updated: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    continue
                if rng.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        current_xlim = ax.get_xlim()
                        print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter lower limit (current upper: {current_xlim[1]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("xrange")
                        new_min = new_lower
                        new_max = current_xlim[1]
                        ax.set_xlim(new_min, new_max)
                        data_is_processed = _xy_truly_processed(fig)
                        if data_is_processed and _full_processed_covers(fig, new_min, new_max):
                            for i in range(len(labels)):
                                if i >= len(fig._full_processed_x_data_list):
                                    continue
                                x_current = np.asarray(fig._full_processed_x_data_list[i], dtype=float).flatten()
                                y_current = np.asarray(fig._full_processed_y_data_list[i], dtype=float).flatten()
                                off = offsets_list[i] if i < len(offsets_list) else 0.0
                                y_current_no_offset = y_current - off
                                mask = (x_current >= new_min) & (x_current <= new_max)
                                x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                                y_sub = np.asarray(y_current_no_offset[mask], dtype=float).flatten()
                                if x_sub.size == 0:
                                    _line(i).set_data([], [])
                                    x_data_list[i] = np.array([], dtype=float)
                                    y_data_list[i] = np.array([], dtype=float)
                                    if i < len(orig_y):
                                        orig_y[i] = np.array([], dtype=float)
                                    continue
                                y_sub = y_sub + off
                                _line(i).set_data(x_sub, y_sub)
                                x_data_list[i] = x_sub
                                y_data_list[i] = y_sub
                                _set_orig_y_at(orig_y, i, y_sub - off)
                        else:
                            _refilter_curves_from_full(
                                args=args, labels=labels,
                                x_data_list=x_data_list, y_data_list=y_data_list, orig_y=orig_y,
                                offsets_list=offsets_list, x_full_list=x_full_list,
                                raw_y_full_list=raw_y_full_list, new_min=new_min, new_max=new_max,
                                _line=_line,
                            )
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        try:
                            if hasattr(ax, '_cif_extend_func'):
                                ax._cif_extend_func(ax.get_xlim()[1])
                        except Exception:
                            pass
                        try:
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                        except Exception:
                            pass
                        fig.canvas.draw()
                        print(f"X range updated: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    continue
                if rng.lower() == 'a':
                    # Auto: restore full X span from full/processed buffers
                    push_state("xrange-auto")
                    try:
                        data_is_processed = _xy_truly_processed(fig)
                        if (
                            data_is_processed
                            and hasattr(fig, '_full_processed_x_data_list')
                            and fig._full_processed_x_data_list
                            and all(np.asarray(xd).size > 0 for xd in fig._full_processed_x_data_list)
                        ):
                            new_min = min(float(np.asarray(xd).min()) for xd in fig._full_processed_x_data_list)
                            new_max = max(float(np.asarray(xd).max()) for xd in fig._full_processed_x_data_list)
                            # If processed buffers are a crop of the saved full arrays, prefer full span
                            if x_full_list and any(np.asarray(xf).size > 0 for xf in x_full_list):
                                full_min = min(float(np.asarray(xf).min()) for xf in x_full_list if np.asarray(xf).size)
                                full_max = max(float(np.asarray(xf).max()) for xf in x_full_list if np.asarray(xf).size)
                                if full_min < new_min - 1e-12 or full_max > new_max + 1e-12:
                                    new_min, new_max = full_min, full_max
                                    data_is_processed = False
                        elif x_full_list and any(np.asarray(xf).size > 0 for xf in x_full_list):
                            new_min = min(float(np.asarray(xf).min()) for xf in x_full_list if np.asarray(xf).size)
                            new_max = max(float(np.asarray(xf).max()) for xf in x_full_list if np.asarray(xf).size)
                        else:
                            print("No original data available.")
                            continue
                        if data_is_processed and _full_processed_covers(fig, new_min, new_max):
                            for i in range(len(labels)):
                                if i >= len(fig._full_processed_x_data_list):
                                    continue
                                xf = np.asarray(fig._full_processed_x_data_list[i], dtype=float).flatten()
                                yf = np.asarray(fig._full_processed_y_data_list[i], dtype=float).flatten()
                                off = offsets_list[i] if i < len(offsets_list) else 0.0
                                yf_raw = yf - off
                                mask = (xf >= new_min) & (xf <= new_max)
                                x_sub = np.asarray(xf[mask], dtype=float).flatten()
                                y_sub_raw = np.asarray(yf_raw[mask], dtype=float).flatten()
                                if x_sub.size == 0:
                                    _line(i).set_data([], [])
                                    x_data_list[i] = np.array([], dtype=float)
                                    y_data_list[i] = np.array([], dtype=float)
                                    if i < len(orig_y):
                                        orig_y[i] = np.array([], dtype=float)
                                    continue
                                y_with_offset = y_sub_raw + off
                                _line(i).set_data(x_sub, y_with_offset)
                                x_data_list[i] = x_sub
                                y_data_list[i] = y_with_offset
                                _set_orig_y_at(orig_y, i, y_sub_raw)
                        else:
                            _refilter_curves_from_full(
                                args=args, labels=labels,
                                x_data_list=x_data_list, y_data_list=y_data_list, orig_y=orig_y,
                                offsets_list=offsets_list, x_full_list=x_full_list,
                                raw_y_full_list=raw_y_full_list, new_min=new_min, new_max=new_max,
                                _line=_line,
                            )
                        ax.set_xlim(new_min, new_max)
                        ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        try:
                            if hasattr(ax, '_cif_extend_func'):
                                ax._cif_extend_func(ax.get_xlim()[1])
                        except Exception:
                            pass
                        try:
                            if hasattr(ax, '_cif_draw_func'):
                                ax._cif_draw_func()
                        except Exception:
                            pass
                        fig.canvas.draw()
                        print(f"X range restored to original: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    except Exception as e:
                        print(f"Error during auto restore: {e}")
                    continue
                push_state("xrange")
                if rng.lower() == 'full':
                    # Use full data if available, otherwise use current processed data
                    if x_full_list and all(xf.size > 0 for xf in x_full_list):
                        new_min = min(xf.min() for xf in x_full_list if xf.size)
                        new_max = max(xf.max() for xf in x_full_list if xf.size)
                    else:
                        new_min = min(xd.min() for xd in x_data_list if xd.size)
                        new_max = max(xd.max() for xd in x_data_list if xd.size)
                else:
                    parts = rng.split()
                    if len(parts) != 2:
                        print("Need exactly two numbers for X range (or w/s/a/full/q).")
                        continue
                    new_min, new_max = map(float, parts)
                    if new_min > new_max:
                        new_min, new_max = new_max, new_min
                ax.set_xlim(new_min, new_max)
                data_is_processed = _xy_truly_processed(fig)

                if data_is_processed and _full_processed_covers(fig, new_min, new_max):
                    for i in range(len(labels)):
                        if i >= len(fig._full_processed_x_data_list):
                            continue
                        curr_x = np.asarray(x_data_list[i], dtype=float) if i < len(x_data_list) else np.array([])
                        curr_min = float(curr_x.min()) if curr_x.size else float('inf')
                        curr_max = float(curr_x.max()) if curr_x.size else float('-inf')
                        need_full = (new_min < curr_min or new_max > curr_max)
                        if need_full:
                            full_x = np.asarray(fig._full_processed_x_data_list[i], dtype=float).flatten()
                            if full_x.size > 0:
                                x_current = full_x
                                y_current = np.asarray(fig._full_processed_y_data_list[i], dtype=float).flatten()
                            else:
                                x_current = curr_x
                                y_current = np.asarray(y_data_list[i], dtype=float).flatten()
                        else:
                            x_current = curr_x
                            y_current = np.asarray(y_data_list[i], dtype=float).flatten()
                        off = offsets_list[i] if i < len(offsets_list) else 0.0
                        y_current_no_offset = y_current - off
                        mask = (x_current >= new_min) & (x_current <= new_max)
                        x_sub = np.asarray(x_current[mask], dtype=float).flatten()
                        y_sub = np.asarray(y_current_no_offset[mask], dtype=float).flatten()
                        if x_sub.size == 0:
                            _line(i).set_data([], [])
                            x_data_list[i] = np.array([], dtype=float)
                            y_data_list[i] = np.array([], dtype=float)
                            if i < len(orig_y):
                                orig_y[i] = np.array([], dtype=float)
                            continue
                        y_sub = y_sub + off
                        _line(i).set_data(x_sub, y_sub)
                        x_data_list[i] = x_sub
                        y_data_list[i] = y_sub
                        _set_orig_y_at(orig_y, i, y_sub - off)
                else:
                    # Unprocessed / session reload / processed crop too narrow
                    _refilter_curves_from_full(
                        args=args, labels=labels,
                        x_data_list=x_data_list, y_data_list=y_data_list, orig_y=orig_y,
                        offsets_list=offsets_list, x_full_list=x_full_list,
                        raw_y_full_list=raw_y_full_list, new_min=new_min, new_max=new_max,
                        _line=_line,
                    )
                ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                # Extend CIF ticks after x-range change
                try:
                    if hasattr(ax, '_cif_extend_func'):
                        ax._cif_extend_func(ax.get_xlim()[1])
                except Exception:
                    pass
                try:
                    if hasattr(ax, '_cif_draw_func'):
                        ax._cif_draw_func()
                except Exception:
                    pass
                fig.canvas.draw()
            except Exception as e:
                print(f"Error setting X-axis range: {e}")


def run_y_range_menu(
    *,
    args: Any,
    ax: Any,
    fig: Any,
    label_text_objects: List[Any],
    y_data_list: List[Any],
    push_state: Callable[[str], Any],
    _safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
        while True:
            try:
                current_ylim = ax.get_ylim()
                print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + colorize_menu("w: upper only"))
                print("  " + colorize_menu("s: lower only"))
                print("  " + colorize_menu("a: auto (restore original)"))
                print("  " + colorize_menu("q: back"))
                rng = _safe_input(colorize_prompt("Y (w/s/a/q): ")).strip().lower()
                if not rng or rng == 'q':
                    break
                if rng == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        current_ylim = ax.get_ylim()
                        print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter upper limit (current lower: {current_ylim[0]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("yrange")
                        ax.set_ylim(current_ylim[0], new_upper)
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw_idle()
                        print(f"Y range updated: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                if rng == 'w':
                    continue
                if rng == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        current_ylim = ax.get_ylim()
                        print(f"Current Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                        val = _safe_input(colorize_prompt(f"Enter lower limit (current upper: {current_ylim[1]:.6g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("yrange")
                        ax.set_ylim(new_lower, current_ylim[1])
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw_idle()
                        print(f"Y range updated: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                if rng == 's':
                    continue
                if rng == 'a':
                    # Auto: restore original range from y_data_list
                    push_state("yrange-auto")
                    if y_data_list:
                        all_min = None
                        all_max = None
                        for arr in y_data_list:
                            if arr.size:
                                mn = float(arr.min())
                                mx = float(arr.max())
                                all_min = mn if all_min is None else min(all_min, mn)
                                all_max = mx if all_max is None else max(all_max, mx)
                        if all_min is None or all_max is None:
                            print("No original data available.")
                            continue
                        ax.set_ylim(all_min, all_max)
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw_idle()
                        print(f"Y range restored to original: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                    else:
                        print("No original data available.")
                    continue
                push_state("yrange")
                if rng == 'auto':
                    ax.relim()
                    ax.autoscale_view(scalex=False, scaley=True)
                else:
                    if rng == 'full':
                        all_min = None
                        all_max = None
                        for arr in y_data_list:
                            if arr.size:
                                mn = float(arr.min())
                                mx = float(arr.max())
                                all_min = mn if all_min is None else min(all_min, mn)
                                all_max = mx if all_max is None else max(all_max, mx)
                        if all_min is None or all_max is None:
                            print("No data to compute full Y range.")
                            continue
                        y_min, y_max = all_min, all_max
                    else:
                        parts = rng.split()
                        if len(parts) != 2:
                            print("Need exactly two numbers for Y range.")
                            continue
                        y_min, y_max = map(float, parts)
                        if y_min == y_max:
                            print("Warning: min == max; expanding slightly.")
                            eps = abs(y_min)*1e-6 if y_min != 0 else 1e-6
                            y_min -= eps
                            y_max += eps
                ax.set_ylim(y_min, y_max)
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                fig.canvas.draw_idle()
                ymin, ymax = ax.get_ylim()
                print(f"Y range set to ({float(ymin)}, {float(ymax)})")
            except Exception as e:
                print(f"Error setting Y-axis range: {e}")


__all__ = ["run_x_range_menu", "run_y_range_menu"]
