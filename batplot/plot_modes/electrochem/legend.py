"""Legend helpers for EC interactive mode."""

from __future__ import annotations

from typing import Optional

from ..common.fonts import sync_legend_title_fontsize


def _visible_legend_entries(ax):
    """Return handles/labels for visible, user-facing lines only."""
    handles = []
    labels = []
    for ln in ax.lines:
        if ln.get_visible():
            lab = ln.get_label() or ""
            if lab.startswith("_"):
                continue
            handles.append(ln)
            labels.append(lab)
    return handles, labels


def _legend_handles_labels_ncol(ax):
    """Return (handles, labels, ncol). For multi-file, order by legend_file_order (vertical, ncol=1)."""
    fig = ax.figure
    file_data = getattr(fig, "_ec_file_data", None)
    is_multi_file = getattr(fig, "_ec_is_multi_file", False)
    if not is_multi_file or not file_data:
        h, l = _visible_legend_entries(ax)
        return h, l, 1
    # Use legend_file_order for display order; filter to visible only
    order = getattr(fig, "_ec_legend_file_order", None)
    if order is None or not isinstance(order, (list, tuple)):
        order = list(range(len(file_data)))
    handles = []
    labels = []
    for idx in order:
        if idx < 0 or idx >= len(file_data):
            continue
        f = file_data[idx]
        if not f.get("visible", True):
            continue
        cl = f.get("cycle_lines") or {}
        for cyc in sorted(cl.keys(), key=lambda x: (x if isinstance(x, (int, float)) else 0)):
            parts = cl[cyc]
            if isinstance(parts, dict):
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is not None and ln.get_visible():
                        lab = ln.get_label() or ""
                        if not lab.startswith("_"):
                            handles.append(ln)
                            labels.append(lab)
            else:
                if parts.get_visible():
                    lab = parts.get_label() or ""
                    if not lab.startswith("_"):
                        handles.append(parts)
                        labels.append(lab)
    # Vertical layout: ncol=1 for multi-file
    ncol = 1
    return handles, labels, ncol


def _get_legend_user_pref(fig):
    try:
        return bool(getattr(fig, '_ec_legend_user_visible'))
    except Exception:
        return True


def _set_legend_user_pref(fig, visible: bool):
    try:
        fig._ec_legend_user_visible = bool(visible)
    except Exception:
        pass


def _store_legend_title(fig, ax, fallback: str = "Cycle"):
    """Persist the current legend title on the figure for later rebuilds."""
    try:
        leg = ax.get_legend()
        text = ""
        if leg is not None:
            title_artist = leg.get_title()
            if title_artist is not None:
                text = title_artist.get_text() or ""
        if text:
            fig._ec_legend_title = text
        elif not getattr(fig, '_ec_legend_title', None):
            fig._ec_legend_title = fallback
    except Exception:
        if not getattr(fig, '_ec_legend_title', None):
            fig._ec_legend_title = fallback


def _get_legend_title(fig, default: str = "Cycle") -> str:
    try:
        title = getattr(fig, '_ec_legend_title')
        if isinstance(title, str) and title:
            return title
    except Exception:
        pass
    return default


def _apply_file_display_names_to_legend(file_data: list) -> None:
    """Update all curve labels from each file's display_name (for undo/import)."""
    for f in file_data:
        name = f.get("display_name", f.get("filename", ""))
        if not name:
            continue
        cl = f.get("cycle_lines") or {}
        for cyc in sorted(cl.keys(), key=lambda x: (x if isinstance(x, (int, float)) else 0)):
            parts = cl[cyc]
            if isinstance(parts, dict):
                chg, dch = parts.get("charge"), parts.get("discharge")
                if chg is not None:
                    chg.set_label(f"{name}: {cyc}")
                if dch is not None:
                    dch.set_label("_nolegend_" if chg is not None else f"{name}: {cyc}")
            elif hasattr(parts, "set_label"):
                parts.set_label(f"{name}: {cyc}")


def _rebuild_legend(ax):
    """Rebuild legend using only visible lines, anchoring to absolute inches from canvas center if available.
    For multi-file, uses ncol = n visible files so each file gets its own column."""
    fig = ax.figure
    # Capture existing title before any rebuild so it isn't lost
    _store_legend_title(fig, ax)
    # If no stored position yet, try to capture the current legend location once
    # so rebuilds (e.g., after renaming) don't jump to a new "best" spot.
    try:
        if getattr(fig, '_ec_legend_xy_in', None) is None:
            leg0 = ax.get_legend()
            if leg0 is not None and leg0.get_visible():
                try:
                    renderer = fig.canvas.get_renderer()
                except Exception:
                    fig.canvas.draw()
                    renderer = fig.canvas.get_renderer()
                bb = leg0.get_window_extent(renderer=renderer)
                cx = 0.5 * (bb.x0 + bb.x1)
                cy = 0.5 * (bb.y0 + bb.y1)
                fx, fy = fig.transFigure.inverted().transform((cx, cy))
                fw, fh = fig.get_size_inches()
                offset = ((fx - 0.5) * fw, (fy - 0.5) * fh)
                offset = _sanitize_legend_offset(fig, offset)
                if offset is not None:
                    fig._ec_legend_xy_in = offset
    except Exception:
        pass
    if not _get_legend_user_pref(fig):
        leg = ax.get_legend()
        if leg is not None:
            try:
                leg.remove()
            except Exception:
                pass
        return

    handles, labels, ncol = _legend_handles_labels_ncol(ax)
    if handles:
        xy_in = _sanitize_legend_offset(fig, getattr(fig, '_ec_legend_xy_in', None))
        legend_title = _get_legend_title(fig)
        if xy_in is not None:
            try:
                fw, fh = fig.get_size_inches()
                fx = 0.5 + float(xy_in[0]) / float(fw)
                fy = 0.5 + float(xy_in[1]) / float(fh)
                _legend_no_frame(
                    ax,
                    handles,
                    labels,
                    loc='center',
                    bbox_to_anchor=(fx, fy),
                    bbox_transform=fig.transFigure,
                    borderaxespad=1.0,
                    title=legend_title,
                    ncol=ncol,
                )
            except Exception:
                _legend_no_frame(ax, handles, labels, loc='best', borderaxespad=1.0, title=legend_title, ncol=ncol)
        else:
            _legend_no_frame(ax, handles, labels, loc='best', borderaxespad=1.0, title=legend_title, ncol=ncol)
        _store_legend_title(fig, ax, legend_title)
    else:
        leg = ax.get_legend()
        if leg is not None:
            try:
                leg.remove()
            except Exception:
                pass




def _legend_no_frame(ax, *args, title: Optional[str] = None, ncol: int = 1, **kwargs):
    kwargs.setdefault("ncol", ncol)
    leg = ax.legend(*args, **kwargs)
    if leg is not None:
        try:
            leg.set_frame_on(False)
            for t in leg.get_texts():
                t.set_verticalalignment('center')
            # Nudge text up so it aligns with the line handle (Line2D sits higher than text baseline)
            try:
                sizes = [t.get_fontsize() for t in leg.get_texts() if t.get_text().strip()]
                fs = float(sum(sizes) / len(sizes)) if sizes else 10.0
                shift_pts = fs * 0.5  # Points to move text up (was 0.15, increased for proper alignment)
                for t in leg.get_texts():
                    t.set_position((0, shift_pts))
            except Exception:
                pass
        except Exception:
            pass
        if title:
            try:
                leg.set_title(title)
            except Exception:
                pass
        sync_legend_title_fontsize(leg)
    return leg


def _apply_legend_position(fig, ax):
    xy_in = _sanitize_legend_offset(fig, getattr(fig, '_ec_legend_xy_in', None))
    if xy_in is None:
        return False
    # Preserve current title before rebuilding the legend
    _store_legend_title(fig, ax)
    handles, labels, ncol = _legend_handles_labels_ncol(ax)
    if not handles:
        return False
    fw, fh = fig.get_size_inches()
    if fw <= 0 or fh <= 0:
        return False
    fx = 0.5 + float(xy_in[0]) / float(fw)
    fy = 0.5 + float(xy_in[1]) / float(fh)
    _legend_no_frame(
        ax,
        handles,
        labels,
        loc='center',
        bbox_to_anchor=(fx, fy),
        bbox_transform=fig.transFigure,
        borderaxespad=1.0,
        title=_get_legend_title(fig),
        ncol=ncol,
    )
    return True


def _sanitize_legend_offset(fig, xy):
    if xy is None or not isinstance(xy, (tuple, list)) or len(xy) != 2:
        return None
    try:
        x_val = float(xy[0])
        y_val = float(xy[1])
    except Exception:
        return None
    fw, fh = fig.get_size_inches()
    if fw <= 0 or fh <= 0:
        return None
    max_x = fw * 0.45
    max_y = fh * 0.45
    if abs(x_val) > max_x or abs(y_val) > max_y:
        return None
    return (x_val, y_val)

