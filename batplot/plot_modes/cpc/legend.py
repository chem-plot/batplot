"""Legend and color helpers for CPC interactive mode."""

from __future__ import annotations

from typing import Any, Optional, cast

import numpy as np
import matplotlib.patches as mpatches  # type: ignore[import]
from matplotlib.colors import to_hex  # type: ignore[import]
from matplotlib.legend_handler import HandlerPatch  # type: ignore[import]

from ..common.fonts import sync_legend_title_fontsize


class _HandlerSquarePatch(HandlerPatch):
    """Legend handler that forces Patch objects to render as squares."""

    def create_artists(self, legend, orig_handle, xdescent, ydescent, width, height, fontsize, trans):
        size = min(width, height)
        x = (width - size) / 2
        y = (height - size) / 2
        patch = mpatches.Rectangle((x, y), size, size)
        self.update_prop(patch, orig_handle, legend)
        patch.set_transform(trans)
        return [patch]


def _legend_no_frame(ax, *args, **kwargs):
    """Build a compact no-frame legend and clear stale twin-axis legends."""
    kwargs.setdefault("frameon", False)
    handle_len = kwargs.get("handlelength") or kwargs.get("handleheight") or 0.7
    kwargs["handlelength"] = kwargs["handleheight"] = handle_len
    kwargs.setdefault("handletextpad", 0.35)
    kwargs.setdefault("labelspacing", 0.25)
    kwargs.setdefault("borderaxespad", 0.5)
    kwargs.setdefault("borderpad", 0.3)
    kwargs.setdefault("columnspacing", 0.6)

    legend_host_ax = kwargs.pop("legend_host_ax", None)
    target_ax = legend_host_ax if legend_host_ax is not None else ax
    try:
        axes_to_clear = [ax]
        if target_ax is not ax:
            axes_to_clear.append(target_ax)
        for host in axes_to_clear:
            old_leg = host.get_legend()
            if old_leg is not None:
                try:
                    old_leg.remove()
                except Exception:
                    try:
                        old_leg.set_visible(False)
                    except Exception:
                        pass
                try:
                    host.legend_ = None
                except Exception:
                    pass
    except Exception:
        pass

    leg = target_ax.legend(*args, **kwargs)
    if leg is not None:
        try:
            try:
                ax.legend_ = leg
            except Exception:
                pass
            try:
                target_ax.legend_ = leg
            except Exception:
                pass
            leg.set_frame_on(False)
            leg.set_zorder(1_000_000)
            leg.set_clip_on(False)
            for text in leg.get_texts():
                text.set_verticalalignment("center")
            sync_legend_title_fontsize(leg)
        except Exception:
            pass
    return leg


def _visible_handles_labels(ax, ax2):
    """Return legend handles and labels for visible artists only."""
    try:
        h1, l1 = ax.get_legend_handles_labels()
    except Exception:
        h1, l1 = [], []
    try:
        h2, l2 = ax2.get_legend_handles_labels()
    except Exception:
        h2, l2 = [], []
    handles, labels = [], []
    for handle, label in list(zip(h1, l1)) + list(zip(h2, l2)):
        try:
            if hasattr(handle, "get_visible") and not handle.get_visible():
                continue
        except Exception:
            pass
        handles.append(handle)
        labels.append(label)
    return handles, labels


def _color_of(artist):
    """Return a representative color for a Line2D/PathCollection."""
    try:
        if artist is None:
            return None
        if hasattr(artist, "get_color"):
            color = artist.get_color()
            if isinstance(color, str):
                return color
            if isinstance(color, (list, tuple)) and color and not isinstance(color, str):
                try:
                    return to_hex(color[0])
                except Exception:
                    return color[0]
            if color is not None:
                try:
                    return to_hex(cast(Any, color))
                except Exception:
                    return color
        if hasattr(artist, "get_facecolors"):
            face_arr = artist.get_facecolors()
            edge_arr = artist.get_edgecolors() if hasattr(artist, "get_edgecolors") else None
            if face_arr is not None and len(face_arr):
                face = face_arr[0]
                try:
                    if len(face) >= 4 and face[3] > 0.01:
                        return to_hex(face)
                except Exception:
                    return to_hex(face)
            if edge_arr is not None and len(edge_arr):
                return to_hex(edge_arr[0])
    except Exception:
        pass
    return None


def _normalize_spine_color(color):
    """Convert color to a spine/tick/label-friendly color value."""
    if color is None:
        return None
    try:
        if isinstance(color, str) and (
            color.startswith("#")
            or color in ("black", "white", "red", "blue", "green", "gray", "grey")
        ):
            return color
        return to_hex(color)
    except Exception:
        return None


def _coerce_legend_color(color):
    """Normalize legend handle colors before assigning them to text."""
    if isinstance(color, (list, tuple)) and len(color) and not isinstance(color, str):
        color = color[0]
    try:
        if hasattr(color, "__len__") and not isinstance(color, str):
            color = tuple(np.array(color).ravel().tolist())
    except Exception:
        pass
    return color


def _get_legend_title(fig, default: Optional[str] = None) -> Optional[str]:
    """Fetch stored legend title, falling back to current legend text or None."""
    try:
        title = getattr(fig, "_cpc_legend_title", None)
        if isinstance(title, str) and title:
            return title
    except Exception:
        pass
    try:
        for ax in getattr(fig, "axes", []):
            leg = ax.get_legend()
            if leg is not None:
                title = leg.get_title().get_text()
                if title:
                    return title
    except Exception:
        pass
    return default


def _sanitize_legend_offset(xy: Optional[tuple]) -> Optional[tuple]:
    if xy is None or not isinstance(xy, tuple) or len(xy) != 2:
        return None
    try:
        x_val = float(xy[0])
        y_val = float(xy[1])
    except (TypeError, ValueError):
        return None
    if not (-50.0 <= x_val <= 50.0 and -50.0 <= y_val <= 50.0):
        return None
    return (x_val, y_val)


def _rebuild_legend(ax, ax2, file_data, preserve_position=True):
    """Rebuild CPC legend from visible files while preserving stored position."""
    try:
        fig = ax.figure
        is_multi = file_data is not None and len(file_data) > 1
        visible_count = sum(1 for f in (file_data or []) if f.get("visible", True)) if is_multi else 0

        xy_in = None
        if preserve_position:
            try:
                xy_in = getattr(fig, "_cpc_legend_xy_in", None)
            except Exception:
                xy_in = None
            if xy_in is None:
                try:
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
                        offset = _sanitize_legend_offset(((fx - 0.5) * fw, (fy - 0.5) * fh))
                        if offset is not None:
                            fig._cpc_legend_xy_in = offset
                            xy_in = offset
                except Exception:
                    pass

        leg_title = _get_legend_title(fig, default=None)
        use_single_style = False
        visible_file = None
        if is_multi and visible_count == 1:
            visible_file = next((f for f in (file_data or []) if f.get("visible", True)), None)
            if visible_file:
                sc_c = visible_file.get("sc_charge")
                sc_d = visible_file.get("sc_discharge")
                sc_e = visible_file.get("sc_eff")
                if sc_c and sc_d and sc_e:
                    use_single_style = True
                    try:
                        setattr(fig, "_cpc_legend_single_file_effective", True)
                    except Exception:
                        pass

        if is_multi and not use_single_style:
            try:
                setattr(fig, "_cpc_legend_single_file_effective", False)
            except Exception:
                pass
            _build_compact_cpc_legend(ax, ax2, file_data, xy_in=xy_in, leg_title=leg_title)
        elif use_single_style and visible_file is not None:
            sc_c = visible_file["sc_charge"]
            sc_d = visible_file["sc_discharge"]
            sc_e = visible_file["sc_eff"]
            handles = [sc_c, sc_d]
            labels = [
                sc_c.get_label() or visible_file.get("filename", "Charge"),
                sc_d.get_label() or visible_file.get("filename", "Discharge"),
            ]
            if sc_e is not None and hasattr(sc_e, "get_visible") and sc_e.get_visible():
                handles.append(sc_e)
                labels.append(sc_e.get_label() or visible_file.get("filename", "Efficiency"))
            if handles:
                if xy_in is not None and preserve_position:
                    try:
                        fw, fh = fig.get_size_inches()
                        fx = 0.5 + float(xy_in[0]) / float(fw)
                        fy = 0.5 + float(xy_in[1]) / float(fh)
                        _legend_no_frame(
                            ax,
                            handles,
                            labels,
                            loc="center",
                            bbox_to_anchor=(fx, fy),
                            bbox_transform=fig.transFigure,
                            borderaxespad=1.0,
                            title=leg_title,
                            legend_host_ax=ax2,
                        )
                    except Exception:
                        _legend_no_frame(ax, handles, labels, loc="best", borderaxespad=1.0, title=leg_title, legend_host_ax=ax2)
                else:
                    _legend_no_frame(ax, handles, labels, loc="best", borderaxespad=1.0, title=leg_title, legend_host_ax=ax2)
        else:
            try:
                setattr(fig, "_cpc_legend_single_file_effective", True)
            except Exception:
                pass
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            handles, labels = [], []
            for handle, label in zip(h1 + h2, l1 + l2):
                if handle.get_visible():
                    handles.append(handle)
                    labels.append(label)

            if handles:
                if xy_in is not None and preserve_position:
                    try:
                        fw, fh = fig.get_size_inches()
                        fx = 0.5 + float(xy_in[0]) / float(fw)
                        fy = 0.5 + float(xy_in[1]) / float(fh)
                        _legend_no_frame(
                            ax,
                            handles,
                            labels,
                            loc="center",
                            bbox_to_anchor=(fx, fy),
                            bbox_transform=fig.transFigure,
                            borderaxespad=1.0,
                            title=leg_title,
                            legend_host_ax=ax2,
                        )
                    except Exception:
                        _legend_no_frame(ax, handles, labels, loc="best", borderaxespad=1.0, title=leg_title, legend_host_ax=ax2)
                else:
                    _legend_no_frame(ax, handles, labels, loc="best", borderaxespad=1.0, title=leg_title, legend_host_ax=ax2)
            else:
                leg = ax.get_legend()
                if leg:
                    leg.set_visible(False)
    except Exception:
        pass


def _build_compact_cpc_legend(ax, ax2, file_data, xy_in=None, leg_title=None):
    """Build the compact multi-file CPC legend."""
    fig = ax.figure
    if leg_title is None:
        leg_title = _get_legend_title(fig, default=None)

    file_rows = []
    any_eff_visible = False
    for file_info in file_data:
        sc_c = file_info.get("sc_charge")
        sc_d = file_info.get("sc_discharge")
        sc_e = file_info.get("sc_eff")
        if sc_c is None:
            continue
        try:
            if not sc_c.get_visible() and (sc_d is None or not sc_d.get_visible()):
                continue
        except Exception:
            pass

        color = "#555555"
        try:
            facecolors = sc_c.get_facecolors()
            if facecolors is not None and len(facecolors):
                color = to_hex(facecolors[0])
        except Exception:
            try:
                color = _color_of(sc_c) or "#555555"
            except Exception:
                pass

        raw_label = file_info.get("filename", "") or file_info.get("label", "")
        if not raw_label:
            try:
                raw_label = sc_c.get_label() or ""
            except Exception:
                raw_label = ""
        for suffix in (" (Chg)", " (Dch)", " (Eff)", " (chg)", " (dch)", " (eff)"):
            raw_label = raw_label.replace(suffix, "")
        file_rows.append((color, raw_label.strip()))

        if sc_e is not None:
            try:
                if sc_e.get_visible():
                    any_eff_visible = True
            except Exception:
                pass

    if not any_eff_visible:
        try:
            for artist in ax2.collections:
                if hasattr(artist, "get_visible") and artist.get_visible():
                    label = artist.get_label()
                    if label and ("(Eff)" in label or "(eff)" in label or "fficiency" in label):
                        any_eff_visible = True
                        break
        except Exception:
            pass

    marker_area = 28.0
    chg_handle = ax.scatter([], [], marker="s", s=marker_area, facecolors="#444444", edgecolors="#444444", linewidths=1.0, label="Charge")
    dch_handle = ax.scatter([], [], marker="s", s=marker_area, facecolors="none", edgecolors="#444444", linewidths=1.2, label="Discharge")
    handles = [chg_handle, dch_handle]
    labels = ["Charge", "Discharge"]

    if any_eff_visible:
        eff_color = "#888888"
        try:
            for file_info in file_data:
                sc_e = file_info.get("sc_eff")
                if sc_e is not None and sc_e.get_visible():
                    eff_color = _color_of(sc_e) or eff_color
                    break
        except Exception:
            eff_color = "#888888"
        eff_handle = ax.scatter([], [], marker="^", s=marker_area, facecolors=eff_color, edgecolors=eff_color, linewidths=1.0, label="Efficiency")
        handles.append(eff_handle)
        labels.append("Efficiency")

    sep = ax.scatter([], [], s=0.0, alpha=0.0, label="")
    handles.append(sep)
    labels.append("")

    for color, filename in file_rows:
        file_handle = ax.scatter([], [], marker="s", s=marker_area, facecolors=color, edgecolors=color, linewidths=1.0, label=filename)
        handles.append(file_handle)
        labels.append(filename)

    if not file_rows:
        return

    legend_kw = dict(
        handlelength=0.35,
        handleheight=0.35,
        borderaxespad=1.0,
        title=leg_title,
        scatterpoints=1,
        scatteryoffsets=[0.5],
    )
    if xy_in is not None:
        try:
            fw, fh = fig.get_size_inches()
            fx = 0.5 + float(xy_in[0]) / float(fw)
            fy = 0.5 + float(xy_in[1]) / float(fh)
            _legend_no_frame(
                ax,
                handles,
                labels,
                loc="center",
                bbox_to_anchor=(fx, fy),
                bbox_transform=fig.transFigure,
                legend_host_ax=ax2,
                **legend_kw,
            )
        except Exception:
            _legend_no_frame(ax, handles, labels, loc="best", legend_host_ax=ax2, **legend_kw)
    else:
        _legend_no_frame(ax, handles, labels, loc="best", legend_host_ax=ax2, **legend_kw)


def _reapply_cpc_legend_text_colors(ax) -> None:
    """Re-apply CPC legend text colors from legend handles."""
    try:
        leg = ax.get_legend()
        if leg is None:
            return
        handles = list(getattr(leg, "legendHandles", []))
        for handle, text in zip(handles, leg.get_texts()):
            color = _color_of(handle)
            if color is None and hasattr(handle, "get_edgecolor"):
                color = handle.get_edgecolor()
            color = _coerce_legend_color(color)
            if color is not None:
                text.set_color(color)
    except Exception:
        pass


__all__ = [
    "_HandlerSquarePatch",
    "_build_compact_cpc_legend",
    "_coerce_legend_color",
    "_color_of",
    "_get_legend_title",
    "_legend_no_frame",
    "_normalize_spine_color",
    "_reapply_cpc_legend_text_colors",
    "_rebuild_legend",
    "_sanitize_legend_offset",
    "_visible_handles_labels",
]
