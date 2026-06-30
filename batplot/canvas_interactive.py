"""Canvas mode: combine multiple .pkl sessions in one figure.

Usage: batplot xrd.pkl operando.pkl gc.pkl dqdv.pkl --canvas

Supported session types (all modes):
- XY/1D: XRD, diffraction, EXAFS, etc. (dump_session)
- EC: GC, CV, dQ/dV (dump_ec_session, kind=ec_gc)
- CPC, EPC: capacity/energy per cycle (dump_cpc_session, kind=cpc)
- Operando: contour + EC panel (dump_operando_session, kind=operando_ec)

- All plots in ONE canvas
- Panels: click • drag • corner resize • 1-9 / Enter edit • p image • t text • Backspace delete ann • e / s / q q
"""

from __future__ import annotations

import io
import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.text import Text

from .session import load_ec_session, load_operando_session, load_cpc_session, load_xy_session
from ._mpl_backend import ensure_gui_backend
from .plot_modes.electrochem.interactive import electrochem_interactive_menu
from .plot_modes.xy.interactive import interactive_menu, normalize_xy_menu_kwargs
from .utils import _confirm_overwrite

try:
    from .plot_modes.operando.interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None

try:
    from .plot_modes.cpc.interactive import cpc_interactive_menu
except ImportError:
    cpc_interactive_menu = None


# Resize handle size in figure coordinates (0-1)
HANDLE_SIZE = 0.02
MIN_PANEL_SIZE = 0.05
MIN_ANN_SIZE = 0.02
SELECTION_EDGE_COLOR = '#2196F3'
ANN_SELECTION_COLOR = '#FF9800'
SELECTION_EDGE_WIDTH = 2.0


def _detect_session_kind(path: str) -> Optional[str]:
    try:
        with open(path, 'rb') as f:
            sess = pickle.load(f)
        if not isinstance(sess, dict):
            return None
        kind = sess.get('kind')
        if kind == 'ec_gc':
            return 'ec_gc'  # GC, CV, dQ/dV
        if kind == 'operando_ec':
            return 'operando_ec'
        if kind == 'cpc':
            return 'cpc'  # CPC, EPC
        if 'version' in sess and 'x_data' in sess:
            return 'xy'  # XY/1D (XRD, diffraction, EXAFS, etc.)
        return None
    except Exception as e:
        print(f"  Could not read {path}: {e}")
        return None


def _load_panel_session(path: str) -> Optional[Tuple[str, Any, Dict[str, Any]]]:
    kind = _detect_session_kind(path)
    if kind is None:
        return None
    try:
        if kind == 'ec_gc':
            res = load_ec_session(path)
            if not res:
                return None
            if len(res) == 4 and res[2] is None:
                fig, ax, _, file_data = res[0], res[1], res[2], res[3]
                return ('ec_gc', (fig, ax, None, file_data), {'file_data': file_data})
            fig, ax, cycle_lines = res[0], res[1], res[2]
            return ('ec_gc', (fig, ax, cycle_lines, None), {'cycle_lines': cycle_lines, 'file_path': path})
        if kind == 'operando_ec':
            res = load_operando_session(path)
            if not res:
                return None
            return ('operando_ec', res, {'file_paths': [path]})
        if kind == 'cpc':
            res = load_cpc_session(path)
            if not res:
                return None
            return ('cpc', res, {})
        if kind == 'xy':
            res = load_xy_session(path)
            if not res:
                return None
            fig, ax, menu_kwargs = res
            return ('xy', (fig, ax, menu_kwargs), {'menu_kwargs': menu_kwargs})
    except Exception as e:
        print(f"  Error loading {path}: {e}")
        return None
    print(f"  {path}: unknown session format (supported: XY/1D, EC/GC/CV/dQdV, CPC/EPC, operando)")
    return None


def _figure_to_rgba(fig, dpi: int = 150) -> Optional[np.ndarray]:
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                    pad_inches=0.05, facecolor='white')
        buf.seek(0)
        from matplotlib.image import imread
        arr = imread(buf)
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr, np.ones_like(arr)], axis=-1)
        elif arr.ndim == 3 and arr.shape[2] == 3:
            alpha = np.ones((*arr.shape[:2], 1), dtype=arr.dtype)
            arr = np.concatenate([arr, alpha], axis=2)
        return arr
    except Exception:
        return None


def _default_positions_from_sizes(
    original_sizes: List[Tuple[float, float]],
    canvas_w: float,
    canvas_h: float,
) -> List[Tuple[float, float, float, float]]:
    """Default positions using each panel's original size. No scaling - plots at native size.
    Returns (left, bottom, width, height) in figure coords 0–1.
    """
    positions = []
    gap = 0.02
    x, row_top = gap, 1.0 - gap
    for pw, ph in original_sizes:
        w_frac = pw / canvas_w
        h_frac = ph / canvas_h
        if x + w_frac > 1.0 - gap:
            x = gap
            if positions:
                row_top = positions[-1][1] - gap
            else:
                row_top = 1.0 - gap
        bottom = row_top - h_frac
        if bottom < gap:
            bottom = gap
        positions.append((x, bottom, w_frac, h_frac))
        x += w_frac + gap
    return positions


def _print_canvas_menu(panels: List[Tuple[str, str]]):
    """Print canvas menu with panel numbers and filenames."""
    print("\n\033[1mCanvas Interactive Menu:\033[0m")
    for i, (_, path) in enumerate(panels):
        name = os.path.basename(path)
        print(f"  \033[93m{i+1}\033[0m: {name}")
    print("  ---")
    print("  Click panel to select • Double-click or Enter to edit • Drag to move • Drag corner to resize")
    print("  1-9: edit panel • p: insert image • t: add text • Backspace: delete selected annotation")
    print("  e: export • s: save (includes images/text) • q q: quit")
    print("  (Click canvas first for keys; orange box = picture or text overlay)")


def _event_to_figure_coords(fig, event) -> Optional[Tuple[float, float]]:
    """Convert event (display pixels) to figure coordinates (0-1). Cross-platform."""
    if event is None:
        return None
    try:
        inv = fig.transFigure.inverted()
        xy = inv.transform((event.x, event.y))
        return (float(xy[0]), float(xy[1]))
    except Exception:
        return None


def _hit_test_panel(fig_x: float, fig_y: float, panel_positions: List[Tuple[float, float, float, float]]) -> int:
    """Return panel index if (fig_x, fig_y) is inside a panel, else -1. Top-most panel wins."""
    for i in range(len(panel_positions) - 1, -1, -1):
        left, bottom, w, h = panel_positions[i]
        right, top = left + w, bottom + h
        if left <= fig_x <= right and bottom <= fig_y <= top:
            return i
    return -1


def _hit_test_handle(
    fig_x: float, fig_y: float,
    left: float, bottom: float, w: float, h: float,
) -> int:
    """Return handle index 0-3 (bl, br, tr, tl) if inside a handle, else -1."""
    right, top = left + w, bottom + h
    hs = HANDLE_SIZE
    handles = [
        (left, bottom),           # 0: bl
        (right - hs, bottom),     # 1: br
        (right - hs, top - hs),   # 2: tr
        (left, top - hs),         # 3: tl
    ]
    for idx, (hx, hy) in enumerate(handles):
        if hx <= fig_x <= hx + hs and hy <= fig_y <= hy + hs:
            return idx
    return -1


def _expand_canvas_paths(pkl_paths: List[str]) -> Tuple[
    List[str],
    Optional[List[Tuple[float, float, float, float]]],
    List[Dict[str, Any]],
    Optional[str],
]:
    """Return (paths, positions or None, raw annotation dicts, manifest_base_dir or None)."""
    if len(pkl_paths) != 1:
        return pkl_paths, None, [], None
    path = pkl_paths[0]
    if not os.path.isfile(path) or not path.lower().endswith('.pkl'):
        return pkl_paths, None, [], None
    try:
        with open(path, 'rb') as f:
            manifest = pickle.load(f)
        if isinstance(manifest, dict) and manifest.get('kind') == 'canvas':
            panel_paths = manifest.get('panel_paths', [])
            positions = manifest.get('panel_positions', [])
            base_dir = os.path.dirname(os.path.abspath(path))
            raw_ann = manifest.get('canvas_annotations', [])
            if not isinstance(raw_ann, list):
                raw_ann = []
            expanded = []
            pos_list = []
            for i, p in enumerate(panel_paths):
                abs_p = os.path.abspath(p) if not os.path.isabs(p) else p
                rel_p = os.path.join(base_dir, os.path.basename(p))
                pos = (positions[i] if i < len(positions) else (0.1, 0.1, 0.4, 0.4))
                if os.path.isfile(abs_p):
                    expanded.append(abs_p)
                    pos_list.append(pos)
                elif os.path.isfile(rel_p):
                    expanded.append(rel_p)
                    pos_list.append(pos)
                elif os.path.isfile(os.path.join(base_dir, p)):
                    expanded.append(os.path.join(base_dir, p))
                    pos_list.append(pos)
                elif os.path.isfile(p):
                    expanded.append(os.path.abspath(p))
                    pos_list.append(pos)
            if expanded:
                return expanded, pos_list, list(raw_ann), base_dir
            print("Canvas file references could not be resolved.")
    except Exception:
        pass
    return pkl_paths, None, [], None


def _normalize_loaded_annotation(raw: Any, base_dir: Optional[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    kind = raw.get('kind')
    rect = raw.get('rect')
    if kind not in ('image', 'text') or not rect or len(rect) < 4:
        return None
    try:
        t = tuple(float(x) for x in rect[:4])
    except (TypeError, ValueError):
        return None
    if kind == 'image':
        p = str(raw.get('path', '')).strip()
        if not p:
            return None
        if not os.path.isfile(p) and base_dir:
            cand = os.path.join(base_dir, os.path.basename(p))
            if os.path.isfile(cand):
                p = cand
            elif os.path.isfile(os.path.join(base_dir, p)):
                p = os.path.join(base_dir, p)
        if not os.path.isfile(p):
            return None
        return {'kind': 'image', 'path': os.path.abspath(p), 'rect': t}
    txt = raw.get('text', '')
    if txt is None:
        txt = ''
    try:
        fs = float(raw.get('fontsize', 14))
    except (TypeError, ValueError):
        fs = 14.0
    return {'kind': 'text', 'text': str(txt), 'rect': t, 'fontsize': fs}


def run_canvas_mode(pkl_paths: List[str]) -> None:
    ensure_gui_backend(None)
    pkl_paths, loaded_positions, raw_annotations, manifest_base_dir = _expand_canvas_paths(pkl_paths)

    if not pkl_paths:
        print("No .pkl files provided.")
        return

    for p in pkl_paths:
        if not os.path.isfile(p):
            print(f"File not found: {p}")
            return

    prev_ion = plt.isinteractive()
    try:
        plt.ioff()
    except Exception:
        pass

    # Prevent window from staying on top / blocking minimize (plt.pause raises it repeatedly)
    try:
        import matplotlib as mpl
        mpl.rcParams['figure.raise_window'] = False
    except Exception:
        pass

    panels: List[Tuple[str, str]] = []
    thumbnail_cache: List[Optional[np.ndarray]] = []
    panel_original_sizes: List[Tuple[float, float]] = []
    canvas_w, canvas_h = 12.0, 8.0

    for path in pkl_paths:
        result = _load_panel_session(path)
        if result is None:
            print(f"Warning: Could not load {path}. Skipping.")
            continue
        kind, data, _ = result
        try:
            fig = data[0] if isinstance(data, (list, tuple)) else data
            w_in, h_in = fig.get_size_inches()
            panel_original_sizes.append((float(w_in), float(h_in)))
            arr = _figure_to_rgba(fig, dpi=150)
            plt.close(fig)
            thumbnail_cache.append(arr)
        except Exception:
            panel_original_sizes.append((8.0, 6.0))
            thumbnail_cache.append(None)
        panels.append((kind, path))

    if not panels:
        print("No valid sessions could be loaded.")
        return

    n_panels = len(panels)
    if loaded_positions and len(loaded_positions) == n_panels:
        panel_positions = list(loaded_positions)
    else:
        panel_positions = _default_positions_from_sizes(panel_original_sizes, canvas_w, canvas_h)

    fig_canvas = plt.figure(figsize=(12, 8), dpi=100, facecolor='white')
    fig_canvas.canvas.manager.set_window_title("Batplot Canvas")
    try:
        fig_canvas.set_layout_engine('none')
    except Exception:
        pass

    ann_items: List[Dict[str, Any]] = []
    for ra in raw_annotations:
        norm = _normalize_loaded_annotation(ra, manifest_base_dir)
        if norm:
            ann_items.append(norm)

    axes_list: List[Any] = []
    panel_edit_data: List[Optional[Dict[str, Any]]] = []
    # Per annotation: (image_axes_or_None, text_artist_or_None) — same length as ann_items
    ann_runtime: List[Tuple[Any, Optional[Text]]] = []

    # Selection state
    selected_panel: int = -1
    selected_ann: int = -1  # image/text overlay index; mutually exclusive with panel selection for handles
    selection_rect: Optional[Rectangle] = None
    handle_patches: List[Rectangle] = []
    drag_state: str = 'idle'  # 'idle' | 'dragging_panel' | 'dragging_handle' | 'dragging_ann' | 'dragging_ann_handle'
    drag_handle_idx: int = -1
    drag_start_fig: Tuple[float, float] = (0.0, 0.0)
    drag_start_positions: List[Tuple[float, float, float, float]] = []
    drag_start_ann_rect: Tuple[float, float, float, float] = (0.0, 0.0, 0.1, 0.1)
    drag_start_text_fontsize: float = 14.0
    running: bool = True
    quit_pending: bool = False  # First 'q' sets this; second 'q' within 2s quits (no terminal input)

    def _load_and_render(idx: int, target_size_inches: Optional[Tuple[float, float]] = None) -> Optional[np.ndarray]:
        if idx < 0 or idx >= len(panels):
            return None
        kind, path = panels[idx]
        result = _load_panel_session(path)
        if result is None:
            return None
        _, data, _ = result
        try:
            fig = data[0] if isinstance(data, (list, tuple)) else data
            if target_size_inches and len(target_size_inches) == 2:
                try:
                    fig.set_size_inches(float(target_size_inches[0]), float(target_size_inches[1]))
                except Exception:
                    pass
            arr = _figure_to_rgba(fig, dpi=150)
            plt.close(fig)
            return arr
        except Exception:
            return None

    def _sync_panel_positions_from_axes():
        """Sync panel_positions from current axes positions."""
        for i in range(min(len(axes_list), len(panel_positions))):
            try:
                bbox = axes_list[i].get_position()
                panel_positions[i] = (float(bbox.x0), float(bbox.y0), float(bbox.width), float(bbox.height))
            except Exception:
                pass

    def _remove_ann_artists():
        """Remove matplotlib artists for annotations (before rebuild)."""
        nonlocal ann_runtime
        for ax, txt in ann_runtime:
            if ax is not None:
                try:
                    fig_canvas.delaxes(ax)
                except Exception:
                    try:
                        ax.remove()
                    except Exception:
                        pass
            if txt is not None:
                try:
                    txt.remove()
                except Exception:
                    pass
        ann_runtime.clear()

    def _apply_ann_rect_to_artist(j: int):
        if j < 0 or j >= len(ann_items) or j >= len(ann_runtime):
            return
        l, b, w, h = ann_items[j]['rect']
        ax, txt = ann_runtime[j]
        if ax is not None:
            try:
                ax.set_position([l, b, w, h])
            except Exception:
                pass
        if txt is not None:
            try:
                txt.set_position((l + w / 2, b + h / 2))
                if ann_items[j]['kind'] == 'text':
                    txt.set_fontsize(float(ann_items[j].get('fontsize', 14)))
            except Exception:
                pass

    def _rebuild_ann_artists():
        """Recreate image axes and text artists from ann_items (after panel rebuild)."""
        nonlocal ann_runtime
        _remove_ann_artists()
        from matplotlib.image import imread as mpl_imread
        for item in ann_items:
            l, b, w, h = item['rect']
            kind = item['kind']
            if kind == 'image':
                pth = item.get('path', '')
                if not pth or not os.path.isfile(pth):
                    ann_runtime.append((None, None))
                    continue
                try:
                    arr = mpl_imread(pth)
                except Exception:
                    ann_runtime.append((None, None))
                    continue
                try:
                    ax_img = fig_canvas.add_axes((l, b, w, h), facecolor='none')
                    ax_img.set_zorder(15)
                    if arr.ndim == 2:
                        ax_img.imshow(arr, cmap='gray', aspect='auto', origin='upper')
                    elif arr.ndim == 3 and arr.shape[-1] >= 3:
                        ax_img.imshow(arr[..., :3], aspect='auto', origin='upper')
                    else:
                        ax_img.imshow(arr, aspect='auto', origin='upper')
                    ax_img.axis('off')
                    ann_runtime.append((ax_img, None))
                except Exception:
                    ann_runtime.append((None, None))
            else:
                fs = float(item.get('fontsize', 14))
                try:
                    tx = fig_canvas.text(
                        l + w / 2, b + h / 2, item.get('text', ''),
                        transform=fig_canvas.transFigure, ha='center', va='center',
                        fontsize=fs, clip_on=False, zorder=15,
                    )
                    ann_runtime.append((None, tx))
                except Exception:
                    ann_runtime.append((None, None))

    def _update_selection_visual():
        """Update selection border and resize handles for selected panel or annotation."""
        nonlocal selection_rect, handle_patches
        for p in handle_patches:
            try:
                p.remove()
            except Exception:
                pass
        handle_patches.clear()
        if selection_rect is not None:
            try:
                selection_rect.remove()
            except Exception:
                pass
            selection_rect = None

        left = bottom = w = h = 0.0
        edge_color = SELECTION_EDGE_COLOR
        if selected_ann >= 0 and selected_ann < len(ann_items):
            left, bottom, w, h = ann_items[selected_ann]['rect']
            edge_color = ANN_SELECTION_COLOR
        elif selected_panel >= 0 and selected_panel < len(panel_positions):
            left, bottom, w, h = panel_positions[selected_panel]
        else:
            fig_canvas.canvas.draw_idle()
            return

        selection_rect = Rectangle(
            (left, bottom), w, h,
            fill=False, edgecolor=edge_color, linewidth=SELECTION_EDGE_WIDTH,
            transform=fig_canvas.transFigure, zorder=200
        )
        fig_canvas.add_artist(selection_rect)

        hs = HANDLE_SIZE
        right, top = left + w, bottom + h
        corners = [(left, bottom), (right - hs, bottom), (right - hs, top - hs), (left, top - hs)]
        for cx, cy in corners:
            hp = Rectangle(
                (cx, cy), hs, hs,
                facecolor='white', edgecolor=edge_color, linewidth=1.5,
                transform=fig_canvas.transFigure, zorder=201
            )
            fig_canvas.add_artist(hp)
            handle_patches.append(hp)
        fig_canvas.canvas.draw_idle()

    def rebuild_canvas():
        """Redraw all panels at their current positions. ec_gc uses editable axes; others use raster."""
        try:
            cw, ch = fig_canvas.get_size_inches()
        except Exception:
            cw, ch = 12.0, 8.0
        for ax in axes_list:
            try:
                ax.remove()
            except Exception:
                pass
        axes_list.clear()
        panel_edit_data.clear()
        for i in range(n_panels):
            kind, path = panels[i]
            left, bottom, w, h = panel_positions[i]
            rect: Tuple[float, float, float, float] = (left, bottom, w, h)
            if kind == 'ec_gc':
                res = load_ec_session(path, parent_fig=fig_canvas, rect=rect)
                if res:
                    fig, ax, cycle_lines, file_data = res if len(res) == 4 else (*res[:3], None)
                    axes_list.append(ax)
                    panel_edit_data.append({
                        'cycle_lines': cycle_lines,
                        'file_data': file_data,
                        'path': path,
                    })
                    ax.set_title(f"{i+1}: {os.path.basename(path)[:25]}", fontsize=9)
                else:
                    ax = fig_canvas.add_axes(rect, facecolor='white')
                    ax.set_xticks([])
                    ax.set_yticks([])
                    ax.axis('off')
                    target_in = (cw * w, ch * h) if (cw > 0 and ch > 0) else None
                    arr = thumbnail_cache[i] if i < len(thumbnail_cache) else _load_and_render(i, target_in)
                    if arr is not None:
                        ax.imshow(arr, aspect='equal', interpolation='lanczos')
                        if i < len(thumbnail_cache):
                            thumbnail_cache[i] = arr
                    ax.set_title(f"{i+1}: {os.path.basename(path)[:25]}", fontsize=9)
                    axes_list.append(ax)
                    panel_edit_data.append(None)
            else:
                ax = fig_canvas.add_axes(rect, facecolor='white')
                ax.set_xticks([])
                ax.set_yticks([])
                ax.axis('off')
                target_in = (cw * w, ch * h) if (cw > 0 and ch > 0) else None
                arr = thumbnail_cache[i] if i < len(thumbnail_cache) else None
                if arr is None:
                    arr = _load_and_render(i, target_in)
                    if i < len(thumbnail_cache):
                        thumbnail_cache[i] = arr
                if arr is not None:
                    ax.imshow(arr, aspect='equal', interpolation='lanczos')
                ax.set_title(f"{i+1}: {os.path.basename(path)[:25]}", fontsize=9)
                axes_list.append(ax)
                panel_edit_data.append(None)
        for ax in axes_list:
            try:
                ax.set_zorder(5)
            except Exception:
                pass
        _rebuild_ann_artists()
        _update_selection_visual()
        fig_canvas.canvas.draw_idle()

    def run_panel_menu(idx: int) -> bool:
        """Run panel edit menu. Returns True if edited in-place (no rebuild needed), False otherwise."""
        if idx < 0 or idx >= len(panels):
            return True
        kind, path = panels[idx]
        ed = panel_edit_data[idx] if idx < len(panel_edit_data) else None
        if kind == 'ec_gc' and ed is not None:
            ax = axes_list[idx] if idx < len(axes_list) else None
            if ax is not None:
                try:
                    if ed.get('file_data') is not None:
                        electrochem_interactive_menu(fig_canvas, ax, file_data=ed['file_data'], canvas_mode=True)
                    else:
                        electrochem_interactive_menu(
                            fig_canvas, ax, cycle_lines=ed.get('cycle_lines'),
                            file_path=ed.get('path', path), canvas_mode=True
                        )
                except Exception as e:
                    print(f"Panel menu failed: {e}")
                try:
                    bbox = ax.get_position()
                    panel_positions[idx] = (float(bbox.x0), float(bbox.y0), float(bbox.width), float(bbox.height))
                except Exception:
                    pass
                return True
        result = _load_panel_session(path)
        if result is None:
            print(f"Could not reload panel {idx+1}")
            return False
        _, data, _ = result
        fig = data[0] if isinstance(data, (list, tuple)) else data
        try:
            fig.show()
        except Exception:
            pass
        try:
            if kind == 'ec_gc':
                fig, ax, cycle_lines, file_data = data
                if file_data is not None:
                    electrochem_interactive_menu(fig, ax, file_data=file_data)
                else:
                    electrochem_interactive_menu(fig, ax, cycle_lines, file_path=path)
            elif kind == 'operando_ec':
                fig, ax, im, cbar, ec_ax = data
                if operando_ec_interactive_menu:
                    operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, file_paths=[path], canvas_mode=True)
                else:
                    print("Operando menu not available.")
            elif kind == 'cpc':
                fig, ax, ax2, sc_c, sc_d, sc_e, file_data = data
                if cpc_interactive_menu:
                    cpc_interactive_menu(fig, ax, ax2, sc_c, sc_d, sc_e, file_data=file_data, canvas_mode=True)
                else:
                    print("CPC menu not available.")
            elif kind == 'xy':
                fig, ax, menu_kwargs = data
                interactive_menu(fig, ax, **normalize_xy_menu_kwargs({**menu_kwargs, 'canvas_mode': True}))
        except Exception as e:
            print(f"Panel menu failed: {e}")
        finally:
            try:
                fig = data[0] if isinstance(data, (list, tuple)) else data
                plt.close(fig)
            except Exception:
                pass
        thumbnail_cache[idx] = None
        return False

    def _do_export():
        _sync_panel_positions_from_axes()
        try:
            out = input("Export filename [canvas.svg]: ").strip() or "canvas.svg"
        except (EOFError, KeyboardInterrupt):
            return
        if not out:
            return
        if not os.path.splitext(out)[1]:
            out += '.svg'
        try:
            fig_exp = plt.figure(figsize=(12, 8), dpi=150, facecolor='white')
            fig_exp.set_layout_engine('none')
            for i in range(n_panels):
                kind, path = panels[i]
                l, b, w, h = panel_positions[i]
                rect: Tuple[float, float, float, float] = (l, b, w, h)
                if kind == 'ec_gc':
                    res = load_ec_session(path, parent_fig=fig_exp, rect=rect)
                    if res:
                        pass
                    else:
                        ax = fig_exp.add_axes(rect)
                        ax.set_xticks([])
                        ax.set_yticks([])
                        ax.axis('off')
                        arr = _load_and_render(i)
                        if arr is not None:
                            ax.imshow(arr, aspect='auto')
                        ax.set_title(os.path.basename(path)[:30], fontsize=10)
                else:
                    ax = fig_exp.add_axes(rect)
                    ax.set_xticks([])
                    ax.set_yticks([])
                    ax.axis('off')
                    arr = thumbnail_cache[i] if i < len(thumbnail_cache) else None
                    if arr is None:
                        arr = _load_and_render(i)
                        if i < len(thumbnail_cache):
                            thumbnail_cache[i] = arr
                    if arr is not None:
                        ax.imshow(arr, aspect='auto')
                    ax.set_title(os.path.basename(path)[:30], fontsize=10)
            try:
                from matplotlib.image import imread as mpl_imread
                for item in ann_items:
                    l, b, w, h = item['rect']
                    if item['kind'] == 'image':
                        ip = item.get('path', '')
                        if not ip or not os.path.isfile(ip):
                            continue
                        try:
                            arr_e = mpl_imread(ip)
                            ax_e = fig_exp.add_axes((l, b, w, h), facecolor='none')
                            ax_e.set_zorder(15)
                            if arr_e.ndim == 2:
                                ax_e.imshow(arr_e, cmap='gray', aspect='auto', origin='upper')
                            elif arr_e.ndim == 3 and arr_e.shape[-1] >= 3:
                                ax_e.imshow(arr_e[..., :3], aspect='auto', origin='upper')
                            else:
                                ax_e.imshow(arr_e, aspect='auto', origin='upper')
                            ax_e.axis('off')
                        except Exception:
                            pass
                    else:
                        fs = float(item.get('fontsize', 14))
                        fig_exp.text(
                            l + w / 2, b + h / 2, item.get('text', ''),
                            transform=fig_exp.transFigure, ha='center', va='center',
                            fontsize=fs, clip_on=False, zorder=15,
                        )
            except Exception:
                pass
            target = _confirm_overwrite(out)
            if target:
                fig_exp.savefig(target, dpi=150, bbox_inches='tight')
                print(f"Exported to {target}")
            plt.close(fig_exp)
        except Exception as e:
            print(f"Export failed: {e}")

    def _do_save():
        _sync_panel_positions_from_axes()
        try:
            out = input("Save canvas as [canvas.pkl]: ").strip() or "canvas.pkl"
        except (EOFError, KeyboardInterrupt):
            return
        if not out:
            return
        if not out.lower().endswith('.pkl'):
            out += '.pkl'
        try:
            target = _confirm_overwrite(out)
            if not target:
                return
            ann_serializable = []
            for item in ann_items:
                if item['kind'] == 'image':
                    ann_serializable.append({
                        'kind': 'image',
                        'path': os.path.abspath(item.get('path', '')),
                        'rect': list(item['rect']),
                    })
                else:
                    ann_serializable.append({
                        'kind': 'text',
                        'text': item.get('text', ''),
                        'rect': list(item['rect']),
                        'fontsize': float(item.get('fontsize', 14)),
                    })
            manifest = {
                'kind': 'canvas',
                'panel_paths': [os.path.abspath(p) for _, p in panels],
                'panel_kinds': [k for k, _ in panels],
                'panel_positions': list(panel_positions),
                'canvas_annotations': ann_serializable,
            }
            with open(target, 'wb') as f:
                pickle.dump(manifest, f)
            print(f"Canvas saved to {target}")
        except Exception as e:
            print(f"Save failed: {e}")

    def _add_image_from_file():
        nonlocal selected_ann, selected_panel
        try:
            from .utils import _ask_file_dialog as _pick_file
        except Exception:
            _pick_file = None  # type: ignore
        path = None
        if _pick_file:
            try:
                path = _pick_file(os.getcwd(), ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif'))
            except Exception:
                path = None
        if not path:
            try:
                path = input("Image path (empty=cancel): ").strip()
            except (EOFError, KeyboardInterrupt):
                return
        if not path or not os.path.isfile(path):
            print("No image added.")
            return
        ann_items.append({
            'kind': 'image',
            'path': os.path.abspath(path),
            'rect': (0.35, 0.35, 0.28, 0.22),
        })
        selected_ann = len(ann_items) - 1
        selected_panel = -1
        _rebuild_ann_artists()
        _update_selection_visual()
        print(f"Image added. Orange box: drag / corner resize. p=image t=text Backspace=delete. Save with s.")

    def _add_text_annotation():
        nonlocal selected_ann, selected_panel
        try:
            txt = input("Canvas text: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not txt:
            print("No text added.")
            return
        ann_items.append({
            'kind': 'text',
            'text': txt,
            'rect': (0.35, 0.52, 0.3, 0.08),
            'fontsize': 14.0,
        })
        selected_ann = len(ann_items) - 1
        selected_panel = -1
        _rebuild_ann_artists()
        _update_selection_visual()
        print("Text added. Orange box: drag / corners (scales font). Backspace deletes. Save with s.")

    def on_key(event):
        nonlocal running, selected_panel, selected_ann, quit_pending
        if event.key is None:
            return
        c = event.key.lower()
        if str(event.key).lower() == 'backspace' and selected_ann >= 0:
            del ann_items[selected_ann]
            selected_ann = -1
            _rebuild_ann_artists()
            _update_selection_visual()
            print("Annotation removed.")
            return
        if c == 'q':
            if quit_pending:
                running = False
                return
            quit_pending = True
            print("Press q again to quit.")
            return
        quit_pending = False  # Reset on any other key
        if c == 'e':
            _do_export()
            return
        if c == 's':
            _do_save()
            return
        if c == 'p':
            _add_image_from_file()
            return
        if c == 't':
            _add_text_annotation()
            return
        if c in ('enter', 'return') and selected_panel >= 0:
            selected_ann = -1
            idx = selected_panel
            in_place = run_panel_menu(idx)
            if not in_place:
                thumbnail_cache[idx] = None
                rebuild_canvas()
            else:
                _sync_panel_positions_from_axes()
                _update_selection_visual()
            try:
                fig_canvas.show()
            except Exception:
                pass
            return
        if len(c) == 1 and c.isdigit():
            idx = int(c) - 1
            if 0 <= idx < n_panels:
                selected_ann = -1
                in_place = run_panel_menu(idx)
                if not in_place:
                    thumbnail_cache[idx] = None
                    rebuild_canvas()
                else:
                    _sync_panel_positions_from_axes()
                    _update_selection_visual()
                try:
                    fig_canvas.show()
                except Exception:
                    pass
            return

    def on_press(event):
        nonlocal selected_panel, selected_ann, drag_state, drag_handle_idx, drag_start_fig, drag_start_positions
        nonlocal drag_start_ann_rect, drag_start_text_fontsize
        # Double-click: edit panel (do not start drag)
        if getattr(event, 'dblclick', False):
            panel_idx = -1
            if event.inaxes is not None:
                for i, ax in enumerate(axes_list):
                    if ax == event.inaxes:
                        panel_idx = i
                        break
            else:
                fig_xy = _event_to_figure_coords(fig_canvas, event)
                if fig_xy is not None:
                    panel_idx = _hit_test_panel(fig_xy[0], fig_xy[1], panel_positions)
            if panel_idx >= 0:
                selected_ann = -1
                selected_panel = panel_idx
                _update_selection_visual()
                in_place = run_panel_menu(panel_idx)
                if not in_place:
                    thumbnail_cache[panel_idx] = None
                    rebuild_canvas()
                else:
                    _sync_panel_positions_from_axes()
                    _update_selection_visual()
                try:
                    fig_canvas.show()
                except Exception:
                    pass
            return
        fig_xy = _event_to_figure_coords(fig_canvas, event)
        if fig_xy is None:
            return
        fig_x, fig_y = fig_xy

        # Annotation handles (orange) when an annotation is selected
        if selected_ann >= 0 and selected_ann < len(ann_items):
            l, b, w, h = ann_items[selected_ann]['rect']
            hi = _hit_test_handle(fig_x, fig_y, l, b, w, h)
            if hi >= 0:
                drag_state = 'dragging_ann_handle'
                drag_handle_idx = hi
                drag_start_fig = (fig_x, fig_y)
                drag_start_ann_rect = tuple(ann_items[selected_ann]['rect'])
                drag_start_text_fontsize = float(ann_items[selected_ann].get('fontsize', 14))
                return

        # Clicks inside annotation image axes
        if event.inaxes is not None:
            for j in range(len(ann_items) - 1, -1, -1):
                if j < len(ann_runtime):
                    ax_ann, _txt = ann_runtime[j]
                    if ax_ann is not None and event.inaxes == ax_ann:
                        selected_ann = j
                        selected_panel = -1
                        drag_state = 'dragging_ann'
                        drag_start_fig = (fig_x, fig_y)
                        drag_start_ann_rect = tuple(ann_items[j]['rect'])
                        drag_start_text_fontsize = float(ann_items[j].get('fontsize', 14))
                        _update_selection_visual()
                        return

        # Text annotations (figure coordinates; may overlap panel axes)
        for j in range(len(ann_items) - 1, -1, -1):
            if ann_items[j]['kind'] != 'text':
                continue
            l, b, w, h = ann_items[j]['rect']
            r, top = l + w, b + h
            if l <= fig_x <= r and b <= fig_y <= top:
                selected_ann = j
                selected_panel = -1
                drag_state = 'dragging_ann'
                drag_start_fig = (fig_x, fig_y)
                drag_start_ann_rect = tuple(ann_items[j]['rect'])
                drag_start_text_fontsize = float(ann_items[j].get('fontsize', 14))
                _update_selection_visual()
                return

        if event.inaxes is not None:
            for i, ax in enumerate(axes_list):
                if ax == event.inaxes:
                    fig_x, fig_y = fig_xy
                    left, bottom, w, h = panel_positions[i]
                    handle_idx = _hit_test_handle(fig_x, fig_y, left, bottom, w, h)
                    if handle_idx >= 0 and selected_panel == i:
                        selected_ann = -1
                        drag_state = 'dragging_handle'
                        drag_handle_idx = handle_idx
                        drag_start_fig = (fig_x, fig_y)
                        drag_start_positions = [p[:] for p in panel_positions]
                        return
                    selected_ann = -1
                    selected_panel = i
                    _update_selection_visual()
                    drag_state = 'dragging_panel'
                    drag_start_fig = (fig_x, fig_y)
                    drag_start_positions = [p[:] for p in panel_positions]
                    return
        else:
            panel_idx = _hit_test_panel(fig_x, fig_y, panel_positions)
            if panel_idx >= 0:
                left, bottom, w, h = panel_positions[panel_idx]
                handle_idx = _hit_test_handle(fig_x, fig_y, left, bottom, w, h)
                if handle_idx >= 0 and selected_panel == panel_idx:
                    selected_ann = -1
                    drag_state = 'dragging_handle'
                    drag_handle_idx = handle_idx
                    drag_start_fig = (fig_x, fig_y)
                    drag_start_positions = [p[:] for p in panel_positions]
                    return
                selected_ann = -1
                selected_panel = panel_idx
                _update_selection_visual()
                drag_state = 'dragging_panel'
                drag_start_fig = (fig_x, fig_y)
                drag_start_positions = [p[:] for p in panel_positions]
            else:
                selected_panel = -1
                selected_ann = -1
                _update_selection_visual()

    def on_motion(event):
        nonlocal panel_positions
        if drag_state == 'idle':
            return
        fig_xy = _event_to_figure_coords(fig_canvas, event)
        if fig_xy is None:
            return
        fig_x, fig_y = fig_xy
        dx = fig_x - drag_start_fig[0]
        dy = fig_y - drag_start_fig[1]

        if drag_state == 'dragging_ann' and selected_ann >= 0:
            l0, b0, w0, h0 = drag_start_ann_rect
            new_l = max(0.0, min(1.0 - w0, l0 + dx))
            new_b = max(0.0, min(1.0 - h0, b0 + dy))
            ann_items[selected_ann]['rect'] = (new_l, new_b, w0, h0)
            _apply_ann_rect_to_artist(selected_ann)
            _update_selection_visual()
            return

        if drag_state == 'dragging_ann_handle' and selected_ann >= 0:
            left, bottom, w, h = drag_start_ann_rect
            right, top = left + w, bottom + h
            idx = drag_handle_idx
            new_rect = None
            if idx == 0:
                new_left = max(0.0, min(right - MIN_ANN_SIZE, left + dx))
                new_bottom = max(0.0, min(top - MIN_ANN_SIZE, bottom + dy))
                new_w = right - new_left
                new_h = top - new_bottom
                if new_w >= MIN_ANN_SIZE and new_h >= MIN_ANN_SIZE:
                    new_rect = (new_left, new_bottom, new_w, new_h)
            elif idx == 1:
                new_right = max(left + MIN_ANN_SIZE, min(1.0, right + dx))
                new_bottom = max(0.0, min(top - MIN_ANN_SIZE, bottom + dy))
                new_w = new_right - left
                new_h = top - new_bottom
                if new_w >= MIN_ANN_SIZE and new_h >= MIN_ANN_SIZE:
                    new_rect = (left, new_bottom, new_w, new_h)
            elif idx == 2:
                new_right = max(left + MIN_ANN_SIZE, min(1.0, right + dx))
                new_top = max(bottom + MIN_ANN_SIZE, min(1.0, top + dy))
                new_w = new_right - left
                new_h = new_top - bottom
                if new_w >= MIN_ANN_SIZE and new_h >= MIN_ANN_SIZE:
                    new_rect = (left, bottom, new_w, new_h)
            elif idx == 3:
                new_left = max(0.0, min(right - MIN_ANN_SIZE, left + dx))
                new_top = max(bottom + MIN_ANN_SIZE, min(1.0, top + dy))
                new_w = right - new_left
                new_h = new_top - bottom
                if new_w >= MIN_ANN_SIZE and new_h >= MIN_ANN_SIZE:
                    new_rect = (new_left, bottom, new_w, new_h)
            if new_rect is not None:
                ann_items[selected_ann]['rect'] = new_rect
                if ann_items[selected_ann]['kind'] == 'text':
                    rh = drag_start_ann_rect[3]
                    if rh > 1e-9:
                        ann_items[selected_ann]['fontsize'] = max(
                            4.0, drag_start_text_fontsize * (new_rect[3] / rh)
                        )
                _apply_ann_rect_to_artist(selected_ann)
            _update_selection_visual()
            return

        if drag_state == 'dragging_panel' and selected_panel >= 0:
            left, bottom, w, h = drag_start_positions[selected_panel]
            new_left = max(0.0, min(1.0 - w, left + dx))
            new_bottom = max(0.0, min(1.0 - h, bottom + dy))
            panel_positions[selected_panel] = (new_left, new_bottom, w, h)
            if selected_panel < len(axes_list):
                axes_list[selected_panel].set_position([new_left, new_bottom, w, h])
            _update_selection_visual()
        elif drag_state == 'dragging_handle' and selected_panel >= 0:
            left, bottom, w, h = drag_start_positions[selected_panel]
            right, top = left + w, bottom + h
            idx = drag_handle_idx
            if idx == 0:  # bl
                new_left = max(0.0, min(right - MIN_PANEL_SIZE, left + dx))
                new_bottom = max(0.0, min(top - MIN_PANEL_SIZE, bottom + dy))
                new_w = right - new_left
                new_h = top - new_bottom
                if new_w >= MIN_PANEL_SIZE and new_h >= MIN_PANEL_SIZE:
                    panel_positions[selected_panel] = (new_left, new_bottom, new_w, new_h)
                    if selected_panel < len(axes_list):
                        axes_list[selected_panel].set_position([new_left, new_bottom, new_w, new_h])
            elif idx == 1:  # br
                new_right = max(left + MIN_PANEL_SIZE, min(1.0, right + dx))
                new_bottom = max(0.0, min(top - MIN_PANEL_SIZE, bottom + dy))
                new_w = new_right - left
                new_h = top - new_bottom
                if new_w >= MIN_PANEL_SIZE and new_h >= MIN_PANEL_SIZE:
                    panel_positions[selected_panel] = (left, new_bottom, new_w, new_h)
                    if selected_panel < len(axes_list):
                        axes_list[selected_panel].set_position([left, new_bottom, new_w, new_h])
            elif idx == 2:  # tr
                new_right = max(left + MIN_PANEL_SIZE, min(1.0, right + dx))
                new_top = max(bottom + MIN_PANEL_SIZE, min(1.0, top + dy))
                new_w = new_right - left
                new_h = new_top - bottom
                if new_w >= MIN_PANEL_SIZE and new_h >= MIN_PANEL_SIZE:
                    panel_positions[selected_panel] = (left, bottom, new_w, new_h)
                    if selected_panel < len(axes_list):
                        axes_list[selected_panel].set_position([left, bottom, new_w, new_h])
            elif idx == 3:  # tl
                new_left = max(0.0, min(right - MIN_PANEL_SIZE, left + dx))
                new_top = max(bottom + MIN_PANEL_SIZE, min(1.0, top + dy))
                new_w = right - new_left
                new_h = new_top - bottom
                if new_w >= MIN_PANEL_SIZE and new_h >= MIN_PANEL_SIZE:
                    panel_positions[selected_panel] = (new_left, bottom, new_w, new_h)
                    if selected_panel < len(axes_list):
                        axes_list[selected_panel].set_position([new_left, bottom, new_w, new_h])
            _update_selection_visual()

    def on_release(event):
        nonlocal drag_state, drag_handle_idx
        if drag_state == 'dragging_handle' and selected_panel >= 0:
            kind = panels[selected_panel][0]
            if kind != 'ec_gc':
                thumbnail_cache[selected_panel] = None
                rebuild_canvas()
        drag_state = 'idle'
        drag_handle_idx = -1

    rebuild_canvas()
    try:
        plt.ion()
    except Exception:
        pass
    plt.show(block=False)

    fig_canvas.canvas.mpl_connect('key_press_event', on_key)
    fig_canvas.canvas.mpl_connect('button_press_event', on_press)
    fig_canvas.canvas.mpl_connect('motion_notify_event', on_motion)
    fig_canvas.canvas.mpl_connect('button_release_event', on_release)

    _print_canvas_menu(panels)

    while running:
        try:
            if not plt.fignum_exists(fig_canvas.number):
                break
        except Exception:
            break
        plt.pause(0.05)

    plt.close(fig_canvas)
    try:
        if prev_ion:
            plt.ion()
        else:
            plt.ioff()
    except Exception:
        pass
