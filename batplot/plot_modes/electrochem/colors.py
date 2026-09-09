"""Colors/cycles menu (``c``) for EC interactive mode."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import re

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from matplotlib import colors as mcolors  # type: ignore[import-untyped]

from ...color_utils import (
    color_bar,
    color_block,
    ensure_colormap,
    format_color_listing,
    get_colormap,
    get_user_color_list,
    manage_user_colors,
    palette_preview,
    prompt_screen_color,
    blank_means_back,
    resolve_color_token,
)
from ...plotting import apply_curve_color
from ..common.palettes import DEFAULT_PALETTE_ALIASES, TAB10_HEX, palette_items, resolve_palette_token, sample_colormap


def _coerce_cycle_id(cyc) -> Optional[int]:
    try:
        return int(cyc)
    except Exception:
        return None


def normalize_cycle_lines_keys(cycle_lines: Optional[dict]) -> dict:
    """Force int cycle keys so old str-key pickles match live menu parsing."""
    if not isinstance(cycle_lines, dict) or not cycle_lines:
        return cycle_lines if isinstance(cycle_lines, dict) else {}
    out: Dict[Any, Any] = {}
    for k, v in cycle_lines.items():
        ik = _coerce_cycle_id(k)
        out[ik if ik is not None else k] = v
    return out


def _normalize_cycle_lines_inplace(cycle_lines: dict) -> None:
    if not isinstance(cycle_lines, dict) or not cycle_lines:
        return
    items = list(cycle_lines.items())
    if all(_coerce_cycle_id(k) == k for k, _ in items):
        return
    cycle_lines.clear()
    cycle_lines.update(normalize_cycle_lines_keys(dict(items)))


def _cycle_in(cycle_lines: dict, cyc) -> bool:
    if cyc in cycle_lines:
        return True
    ik = _coerce_cycle_id(cyc)
    if ik is not None and ik in cycle_lines:
        return True
    return str(cyc) in cycle_lines


def _get_cycle_parts(cycle_lines: dict, cyc):
    if cyc in cycle_lines:
        return cycle_lines[cyc]
    ik = _coerce_cycle_id(cyc)
    if ik is not None and ik in cycle_lines:
        return cycle_lines[ik]
    return cycle_lines.get(str(cyc))


def _iter_cycle_lines(cycle_lines: Dict[int, Dict[str, Optional[Any]]]):
    """Iterate over all Line2D objects in cycle_lines, handling both GC and CV modes.
    
    Yields: (cyc, role_or_None, Line2D) tuples
    - For GC mode: yields (cyc, 'charge', ln) and (cyc, 'discharge', ln) for each cycle
    - For CV mode: yields (cyc, None, ln) for each cycle
    """
    for cyc, parts in cycle_lines.items():
        if not isinstance(parts, dict):
            # CV mode: parts is a Line2D directly
            yield (cyc, None, parts)
        else:
            # GC mode: parts is a dict with 'charge' and 'discharge' keys
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is not None:
                    yield (cyc, role, ln)



def _cycle_sort_key(key):
    try:
        return int(key)
    except Exception:
        return key


def _cycle_is_visible(cycle_lines: dict, cyc) -> bool:
    """True if at least one charge/discharge/CV line for this cycle is visible."""
    parts = _get_cycle_parts(cycle_lines, cyc)
    if parts is None:
        return False
    if isinstance(parts, dict):
        for role in ("charge", "discharge"):
            ln = parts.get(role)
            if ln is None:
                continue
            try:
                if ln.get_visible():
                    return True
            except Exception:
                continue
        return False
    try:
        return bool(parts.get_visible())
    except Exception:
        return False


def _visible_cycle_keys(cycle_lines: dict, keys=None):
    """Sorted cycle keys that currently have a visible line."""
    if keys is None:
        keys = cycle_lines.keys()
    return [c for c in sorted(keys, key=_cycle_sort_key) if _cycle_is_visible(cycle_lines, c)]


def _visible_cycle_numbers(cycle_lines: dict) -> List[int]:
    """Sorted cycle *numbers* (ints) that currently have a visible line.

    Stored in sessions/styles so reload cannot renumber a selection (e.g. 1+31
    must never come back as 1+2).
    """
    out: List[int] = []
    for cyc in _visible_cycle_keys(cycle_lines):
        try:
            out.append(int(cyc))
        except Exception:
            continue
    return out


def _selected_cycle_numbers_for_file(f_entry: dict) -> List[int]:
    """Cycle ids to persist for one file entry (survives file hide).

    When a file is hidden every line is forced invisible, so the live
    ``visible`` flags are empty. Prefer the stashed ``selected_cycles`` list
    written by the hide path; otherwise fall back to currently visible lines.
    """
    if not isinstance(f_entry, dict):
        return []
    cl = f_entry.get("cycle_lines") or {}
    if not f_entry.get("visible", True):
        stashed = f_entry.get("selected_cycles")
        if stashed is not None:
            try:
                return sorted({int(c) for c in stashed})
            except Exception:
                pass
    return _visible_cycle_numbers(cl)


def _apply_visible_cycle_numbers(cycle_lines: dict, visible_cycles) -> None:
    """Apply an explicit visible-cycle id list (no renumbering)."""
    if visible_cycles is None:
        return
    try:
        show = {int(c) for c in visible_cycles}
    except Exception:
        return
    _set_visible_cycles(cycle_lines, show)


def _cycle_color_listing(cycle_lines: dict, cyc) -> str:
    if cyc not in cycle_lines:
        return format_color_listing(None)
    parts = cycle_lines[cyc]
    ln = None
    if isinstance(parts, dict):
        # Prefer a currently visible role so listing matches what is on screen
        for role in ("charge", "discharge"):
            cand = parts.get(role)
            if cand is None:
                continue
            try:
                if cand.get_visible():
                    ln = cand
                    break
            except Exception:
                continue
        if ln is None:
            ln = parts.get("charge") or parts.get("discharge")
    else:
        ln = parts
    try:
        return format_color_listing(ln.get_color() if ln is not None else None)
    except Exception:
        return format_color_listing(None)


# In multi-file mode, expand per-cycle listing only up to this many visible cycles
# per file; beyond that, one row per file (avoids dumping 100+ identical file names).
_MULTI_FILE_EXPAND_MAX = 20


def _print_ec_current_curves(
    *,
    target_cycle_lines_list,
    is_multi_file: bool,
    file_data: list[dict],
) -> None:
    print("Current curves (visible only):")
    any_printed = False
    if is_multi_file:
        for fi, f in enumerate(file_data, 1):
            if not f.get("visible", True):
                continue
            cl = f.get("cycle_lines") or {}
            fname = f.get("display_name") or f.get("filename") or f"file {fi}"
            vis = _visible_cycle_keys(cl)
            if not vis:
                continue
            any_printed = True
            # Always lead with a per-file summary row: swatch + name + count.
            n_vis = len(vis)
            print(f"  f{fi}: {_cycle_color_listing(cl, vis[0])}  {fname}  ({n_vis} visible cycle{'s' if n_vis != 1 else ''})")
            if n_vis <= _MULTI_FILE_EXPAND_MAX:
                for cyc in vis:
                    print(f"      {cyc}: {_cycle_color_listing(cl, cyc)}")
    else:
        cl, acyc = target_cycle_lines_list[0]
        for cyc in _visible_cycle_keys(cl, acyc):
            any_printed = True
            print(f"  {cyc}: {_cycle_color_listing(cl, cyc)}")
    if not any_printed:
        print("  (none visible)")


def _apply_curve_linewidth(fig, cycle_lines: Dict[int, Dict[str, Optional[Any]]]):
    """Apply stored curve linewidth to all curves.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    lw = getattr(fig, '_ec_curve_linewidth', None)
    if lw is not None:
        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
            try:
                ln.set_linewidth(lw)
            except Exception:
                pass


def _apply_colors(cycle_lines: Dict[int, Dict[str, Optional[Any]]], mapping: Dict[int, object]):
    """Apply color mapping to charge/discharge lines for the given cycles.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    _normalize_cycle_lines_inplace(cycle_lines)
    for cyc, col in mapping.items():
        parts = _get_cycle_parts(cycle_lines, cyc)
        if parts is None:
            continue
        for _, _, ln in _iter_cycle_lines({_coerce_cycle_id(cyc) or cyc: parts}):
            try:
                apply_curve_color(ln, col)
            except Exception:
                pass


def _set_visible_cycles(cycle_lines: Dict[int, Dict[str, Optional[Any]]], show: Iterable[int]):
    """Set visibility for specified cycles.
    
    Handles both GC mode (dict with 'charge'/'discharge' keys) and CV mode (direct Line2D).
    """
    _normalize_cycle_lines_inplace(cycle_lines)
    show_set = set()
    for c in show:
        ik = _coerce_cycle_id(c)
        show_set.add(ik if ik is not None else c)
    for cyc, role, ln in _iter_cycle_lines(cycle_lines):
        ik = _coerce_cycle_id(cyc)
        vis = (ik if ik is not None else cyc) in show_set
        try:
            ln.set_visible(vis)
        except Exception:
            pass


def _filter_ec_entry_by_display_mode(f_entry: dict, display_mode: str | None) -> None:
    """Apply charge/discharge/both to a visible file's selected cycles.

    Used after ``v`` re-show so ``d`` is not ignored (CPC already couples
    visibility with display_mode).
    """
    mode = (display_mode or "both").strip().lower()
    if mode not in ("charge", "discharge", "both"):
        mode = "both"
    if mode == "both":
        return
    cl = f_entry.get("cycle_lines") or {}
    for _cyc, parts in cl.items():
        if not isinstance(parts, dict):
            continue
        chg = parts.get("charge")
        dch = parts.get("discharge")
        cycle_on = (
            (chg is not None and bool(chg.get_visible()))
            or (dch is not None and bool(dch.get_visible()))
        )
        if not cycle_on:
            continue
        if chg is not None:
            try:
                chg.set_visible(mode in ("both", "charge"))
            except Exception:
                pass
        if dch is not None:
            try:
                dch.set_visible(mode in ("both", "discharge"))
            except Exception:
                pass


def set_ec_file_visibility(
    f_entry: dict,
    visible: bool,
    *,
    display_mode: str | None = None,
) -> None:
    """Show/hide one multi-file EC entry without destroying cycle selection.

    Shared by interactive and batch ``v`` menus. On hide, stashes currently
    visible cycle ids in ``selected_cycles`` then forces all lines off. On
    show, restores that selection (or shows all if nothing was stashed —
    backward compatible with old sessions), then reapplies ``display_mode``
    so ``d`` (Chg/Dch) is preserved.

    Re-hiding an already-hidden file does **not** rewrite ``selected_cycles``
    (``v`` → ``a`` / hide-all would otherwise see all lines off and stash
    ``[]``, wiping a prior 1+31 selection).
    """
    if not isinstance(f_entry, dict):
        return
    cl = f_entry.get("cycle_lines") or {}
    if not visible:
        # Only snapshot selection while the file is still considered visible.
        # Already-hidden entries keep their stashed ``selected_cycles``.
        if bool(f_entry.get("visible", True)):
            try:
                f_entry["selected_cycles"] = _visible_cycle_numbers(cl)
            except Exception:
                f_entry["selected_cycles"] = []
        f_entry["visible"] = False
        for _cyc, parts in cl.items():
            if isinstance(parts, dict):
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is not None:
                        try:
                            ln.set_visible(False)
                        except Exception:
                            pass
            elif parts is not None:
                try:
                    parts.set_visible(False)
                except Exception:
                    pass
        return
    f_entry["visible"] = True
    sel = f_entry.get("selected_cycles")
    if sel is not None:
        try:
            _set_visible_cycles(cl, sel)
            _filter_ec_entry_by_display_mode(f_entry, display_mode)
            return
        except Exception:
            pass
    for _cyc, parts in cl.items():
        if isinstance(parts, dict):
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is not None:
                    try:
                        ln.set_visible(True)
                    except Exception:
                        pass
        elif parts is not None:
            try:
                parts.set_visible(True)
            except Exception:
                pass
    _filter_ec_entry_by_display_mode(f_entry, display_mode)


def _resolve_palette_alias(token: str, palette_map: dict) -> str:
    """Resolve numeric aliases (e.g., '2' or '2_r') to palette names."""
    return resolve_palette_token(token, palette_map)


def _parse_file_palette_tokens(tokens: List[str], n_files: int, fig=None) -> Optional[Tuple[List[int], str]]:
    """Parse file-palette syntax: f1-5 viridis, f1 f3 f5 viridis, fall viridis.
    Returns (file_indices_0based, palette_name) or None if not matched."""
    if not tokens or n_files < 1:
        return None
    last = tokens[-1]
    alias = _resolve_palette_alias(last, DEFAULT_PALETTE_ALIASES) if last else last
    try:
        if not ensure_colormap(alias):
            raise ValueError(alias)
        if get_colormap(alias) is None:
            raise ValueError(alias)
        palette = alias
    except Exception:
        return None
    num_tokens = tokens[:-1]
    if not num_tokens:
        return None
    file_indices = []
    for t in num_tokens:
        t = t.strip().lower()
        if t == 'fall' or t == 'f':
            file_indices = list(range(n_files))
            break
        if t.startswith('f'):
            t = t[1:]
        if '-' in t and t.count('-') == 1:
            lo, hi = t.split('-', 1)
            try:
                a, b = int(lo.strip()), int(hi.strip())
                for i in range(a, b + 1):
                    if 1 <= i <= n_files:
                        file_indices.append(i - 1)
            except ValueError:
                pass
        else:
            try:
                idx = int(t)
                if 1 <= idx <= n_files:
                    file_indices.append(idx - 1)
            except ValueError:
                pass
    file_indices = sorted(set(file_indices))
    if not file_indices:
        return None
    return (file_indices, palette)


def _parse_per_file_cycle_tokens(
    tokens: List[str], n_files: int, fig=None
) -> Optional[Tuple[Dict[int, List[int]], Optional[str]]]:
    """Parse per-file cycle selection: f1:1,5,10 f2:2,4,6 viridis.
    Returns (file_to_cycles, palette) or None if not matched.
    file_to_cycles: 1-based file index -> list of cycles to show (empty = all)."""
    if not tokens or n_files < 1:
        return None
    # Must have at least one fN:... pattern (f required to avoid 1:red cycle-color confusion)
    file_cycle_pattern = re.compile(r'^f(\d+):(.+)$', re.IGNORECASE)
    file_specs: Dict[int, List[int]] = {}
    remaining = []
    for t in tokens:
        m = file_cycle_pattern.match(t.strip())
        if m:
            try:
                fidx = int(m.group(1))
                if 1 <= fidx <= n_files:
                    val = m.group(2).strip().lower()
                    if val == 'all':
                        file_specs[fidx] = []  # empty = all cycles
                    else:
                        cycles = []
                        for part in val.replace(',', ' ').split():
                            if '-' in part and part.count('-') == 1:
                                lo, hi = part.split('-', 1)
                                try:
                                    a, b = int(lo.strip()), int(hi.strip())
                                    cycles.extend(range(a, b + 1))
                                except ValueError:
                                    pass
                            else:
                                try:
                                    cycles.append(int(part))
                                except ValueError:
                                    pass
                        # Only add if we got valid cycles (skip f1:red which is per-curve color)
                        if cycles:
                            file_specs[fidx] = sorted(set(cycles))
            except (ValueError, IndexError):
                remaining.append(t)
        else:
            remaining.append(t)
    if not file_specs:
        return None
    # Last remaining token may be palette (same rules as cycle lists)
    remaining, palette = _split_trailing_palette(remaining)
    return (file_specs, palette)


def _parse_fall_cycles_tokens(
    tokens: List[str], n_files: int, fig=None
) -> Optional[Tuple[List[int], Optional[str]]]:
    """Parse ``fall:1 31`` / ``fall:2-30 1`` — cycles for ALL files.

    Trailing bare ``1``..``6`` or colormap names are palette (same rules as
    ``_split_trailing_palette``). Returns (cycles_list, palette) or None.
    """
    if not tokens or n_files < 1:
        return None
    first = tokens[0].strip()
    if not first.lower().startswith("fall:"):
        return None
    suffix = first[5:].strip()  # after "fall:"
    cycle_tokens = ([suffix] if suffix else []) + list(tokens[1:])
    cycle_tokens, palette = _split_trailing_palette(cycle_tokens)
    cycles = []
    for t in cycle_tokens:
        for part in str(t).replace(',', ' ').split():
            if '-' in part and part.count('-') == 1:
                lo, hi = part.split('-', 1)
                try:
                    a, b = int(lo.strip()), int(hi.strip())
                    cycles.extend(range(a, b + 1))
                except ValueError:
                    pass
            else:
                try:
                    cycles.append(int(part))
                except ValueError:
                    pass
    cycles = sorted(set(cycles))
    if not cycles:
        return None
    return (cycles, palette)


def _expand_cycle_number_tokens(parts: List[str]) -> List[int]:
    """Turn tokens like ``5``, ``2-30``, or ``1,3-5`` into sorted unique cycle numbers.

    Hyphen ranges use inclusive endpoints; ``10-2`` is treated as ``2``..``10``.
    Non-numeric pieces are skipped.
    """
    out: List[int] = []
    for t in parts:
        for piece in str(t).replace(",", " ").split():
            piece = piece.strip()
            if not piece:
                continue
            if "-" in piece and piece.count("-") == 1:
                lo, hi = piece.split("-", 1)
                try:
                    a, b = int(lo.strip()), int(hi.strip())
                except ValueError:
                    continue
                if a <= b:
                    out.extend(range(a, b + 1))
                else:
                    out.extend(range(b, a + 1))
            else:
                try:
                    out.append(int(piece))
                except ValueError:
                    pass
    return sorted(set(out))


def _format_cycles_compact(cycles: List[int]) -> str:
    """Format cycle ids for messages, e.g. ``[2,3,4,30]`` → ``2-4, 30``."""
    if not cycles:
        return ""
    c = sorted(set(int(x) for x in cycles))
    parts: List[str] = []
    i = 0
    while i < len(c):
        j = i
        while j + 1 < len(c) and c[j + 1] == c[j] + 1:
            j += 1
        if j == i:
            parts.append(str(c[i]))
        else:
            parts.append(f"{c[i]}-{c[j]}")
        i = j + 1
    return ", ".join(parts)


def _explicit_palette_token(token: str) -> Optional[str]:
    """Resolve a palette name or ``N_r`` form (not bare ``1``..``6``).

    Bare digits ``1``..``6`` are handled by callers (``_split_trailing_palette``,
    ``all N``). Legacy ``p1``..``p6`` is no longer accepted — use ``1``..``6``
    or the colormap name (``Set2``, ``viridis``, …).
    """
    t = (token or "").strip()
    if not t:
        return None
    # Named / reversed aliases via shared resolver (e.g. tab10, 2_r, viridis)
    alias = _resolve_palette_alias(t, DEFAULT_PALETTE_ALIASES)
    try:
        if not ensure_colormap(alias):
            return None
        if get_colormap(alias) is None:
            return None
        return alias
    except Exception:
        return None


def _tokens_have_cycle_range(tokens: List[str]) -> bool:
    """True if any token is a hyphen cycle range (e.g. ``2-30``).

    Kept for callers/tests; trailing palette digits no longer require a range.
    """
    for t in tokens:
        for piece in str(t).replace(",", " ").split():
            if "-" in piece and piece.count("-") == 1:
                lo, hi = piece.split("-", 1)
                try:
                    int(lo.strip())
                    int(hi.strip())
                    return True
                except ValueError:
                    continue
    return False


def _split_trailing_palette(tokens: List[str]) -> Tuple[List[str], Optional[str]]:
    """Split ``tokens`` into (cycle_tokens, palette).

    The **last** token is the palette when it is a bare digit ``1``..``6``,
    ``N_r``, or a colormap name — and at least one preceding cycle token exists
    (``2-30 1``, ``1 5 10 3``, ``1-3 viridis``).

    Plain cycle selection without recoloring uses no trailing palette digit
    (``1 31``, ``1-2``, ``5 10 20``). Prefer a range alone (``1-2``) when you
    need cycles whose ids collide with palette digits.
    """
    if not tokens:
        return [], None
    last = tokens[-1]
    head = tokens[:-1]
    # Last digit 1-6 = palette whenever cycles precede it (user-facing rule).
    allow_bare_numeric_palette = bool(head)
    low = last.lower()
    bare_digit_alias = last in DEFAULT_PALETTE_ALIASES
    digit_r_alias = low.endswith("_r") and low[:-2] in DEFAULT_PALETTE_ALIASES

    palette = None
    if bare_digit_alias and allow_bare_numeric_palette:
        palette = DEFAULT_PALETTE_ALIASES[last]
    elif digit_r_alias:
        palette = _explicit_palette_token(last)
    elif not last.isdigit() and not bare_digit_alias:
        palette = _explicit_palette_token(last)

    if palette:
        return head, palette
    return list(tokens), None


def _parse_cycle_tokens(tokens: List[str], fig=None) -> Tuple[str, List[int], dict, Optional[str], bool]:
    """Classify and parse tokens for the cycle command.

    Color-setting forms:
      1. ``palette`` — cycle list + last token = palette (digit ``1``..``6`` or
         colormap name), e.g. ``2-30 1``, ``1 5 10 3``, ``1-3 viridis``.
      2. ``map`` — per-cycle ``N:color`` (name, ``#hex``, or plain saved index);
         multiple entries allowed, e.g. ``1:red 2:4 5:#00B006``.
      3. ``palette`` + ``use_all`` — ``all <palette>`` (``all 3``, ``all viridis``).

    Non-color: ``numbers`` (cycle ids alone, or bare ``all``) only changes
    visibility / keeps current colors — kept for BC, not advertised as a color mode.

    Returns ``(mode, cycles, mapping, palette, use_all)``.
    """
    if not tokens:
        return ("numbers", [], {}, None, False)

    # Support 'all' and 'all <palette>'
    if len(tokens) == 1 and tokens[0].lower() == 'all':
        return ("numbers", [], {}, None, True)
    if len(tokens) == 2 and tokens[0].lower() == 'all':
        # all <palette>: bare 1-6 and names
        last = tokens[1]
        palette = None
        if last in DEFAULT_PALETTE_ALIASES:
            palette = DEFAULT_PALETTE_ALIASES[last]
        else:
            palette = _explicit_palette_token(last)
        if palette:
            return ("palette", [], {}, palette, True)
        # Unknown palette -> still select all, no recolor
        return ("numbers", [], {}, None, True)

    # Check explicit mapping mode first
    if any(":" in t for t in tokens):
        cycles: List[int] = []
        mapping: Dict[int, object] = {}
        for t in tokens:
            if ":" not in t:
                continue
            idx_s, col = t.split(":", 1)
            try:
                cyc = int(idx_s)
            except ValueError:
                continue
            mapping[cyc] = resolve_color_token(col, fig)
            if cyc not in cycles:
                cycles.append(cyc)
        return ("map", cycles, mapping, None, False)

    head, palette = _split_trailing_palette(tokens)
    if palette:
        cycles = _expand_cycle_number_tokens(head)
        return ("palette", cycles, {}, palette, False)

    # Numbers only (supports ranges, e.g. 2-30) — includes lists like 1 31
    cycles = _expand_cycle_number_tokens(tokens)
    return ("numbers", cycles, {}, None, False)



def _print_ec_palette_choices(colorize_menu: Callable[[str], str]) -> None:
    """Print the recommended-palette list with previews (shared by prompts/help)."""
    print("Recommended palettes for scientific publications:")
    rec_palettes = palette_items(DEFAULT_PALETTE_ALIASES.values())
    for idx, (name, desc) in enumerate(rec_palettes, 1):
        bar = palette_preview(name)
        print("  " + colorize_menu(f"{idx}: {name} - {desc}"))
        if bar:
            print(f"      {bar}")


def run_ec_cycles_menu(
    *,
    fig: Any,
    ax: Any,
    cycle_lines: dict,
    file_data: list[dict],
    current_file_idx: int,
    all_cycles: list,
    is_multi_file: bool,
    is_dqdv: bool,
    menu_title: str,
    canvas_mode: bool,
    print_file_list: Callable[..., Any],
    print_menu: Callable[..., Any],
    colorize_menu: Callable[[str], str],
    colorize_inline_commands: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    safe_input: Callable[[str], str],
    push_state: Callable[[str], Any],
    parse_fall_cycles_tokens: Callable[..., Any],
    parse_per_file_cycle_tokens: Callable[..., Any],
    parse_file_palette_tokens: Callable[..., Any],
    parse_cycle_tokens: Callable[..., Any],
    set_visible_cycles: Callable[..., Any],
    apply_colors: Callable[..., Any],
    apply_curve_linewidth: Callable[..., Any],
    apply_stored_smooth_settings: Callable[..., Any],
    apply_display_mode: Callable[[str], Any],
    rebuild_legend: Callable[[Any], Any],
    apply_nice_ticks: Callable[[], Any],
    curves_status_fn: Callable[[], None] | None = None,
) -> None:
    from ..common.menu_rendering import menu_block_begin

    # Simple model: single-file shows the color menu directly; multi-file first
    # asks which file to edit (by number), then shows the exact same
    # single-file menu for that file. q returns to the file picker.

    def _edit_one_file(cl: dict, acyc: list, header: Optional[str] = None) -> None:
        """Single-file color menu for one file's cycles (GC, CV, dQ/dV)."""
        _normalize_cycle_lines_inplace(cl)
        while True:
            menu_block_begin(force_new=True)
            if header:
                print(header)
            n_visible_cycles = len(_visible_cycle_keys(cl, acyc))
            if n_visible_cycles == len(acyc):
                print(f"Visible cycles: {n_visible_cycles}")
            else:
                print(f"Visible cycles: {n_visible_cycles} (of {len(acyc)} total)")
            print()
            print("How to set color:")
            # Highlight only the typed examples (cyan when ANSI menus enabled).
            from ..common.menu_rendering import ansi_menu_enabled

            def _ex(sample: str) -> str:
                if ansi_menu_enabled():
                    return f"\033[96m{sample}\033[0m"
                return sample

            print("  1) Cycles + palette number as LAST token (digit 1-6 or name):")
            print(
                "       e.g. "
                f"{_ex('2-30 1')}   |   {_ex('1 5 10 3')}   |   {_ex('1-3 viridis')}"
            )
            print("  2) Colon per cycle (multiple entries allowed):")
            print(
                "       name / #hex / saved index:  e.g. "
                f"{_ex('1:red')} {_ex('5:#00B006')} {_ex('2:4')}"
            )
            print("  3) all + palette:")
            print(
                "       e.g. "
                f"{_ex('all 1')}   |   {_ex('all 3')}   |   {_ex('all viridis')}"
            )
            print()
            _print_ec_palette_choices(colorize_menu)
            print("  " + colorize_menu("Palette digits: 1=tab10  2=Set2  3=Dark2  4=viridis  5=plasma  6=rainbow"))
            user_colors = get_user_color_list(fig)
            if user_colors:
                print("\nSaved colors (use with colon form as number):")
                for idx, color in enumerate(user_colors, 1):
                    print("  " + colorize_menu(f"{idx}: {format_color_listing(color)}"))
                print("  " + colorize_menu("u: edit saved colors"))
            print("  " + colorize_menu("v: show current colors"))
            print("  " + colorize_menu("e: pick color from screen"))
            print("  " + colorize_menu("q: back"))
            line = safe_input(colorize_prompt("Selection: ")).strip()
            if line.lower() == 'q' or blank_means_back(line):
                break
            if line.lower() == 'v':
                _print_ec_current_curves(
                    target_cycle_lines_list=[(cl, acyc)],
                    is_multi_file=False,
                    file_data=file_data,
                )
                continue
            if line.lower() == 'u':
                manage_user_colors(fig)
                continue
            if line.lower() == 'e':
                prompt_screen_color(fig)
                continue
            tokens = line.replace(',', ' ').split()
            mode, cycles, mapping, palette, use_all = parse_cycle_tokens(tokens, fig)
            if use_all:
                existing = list(_visible_cycle_keys(cl, acyc))
                ignored: List[int] = []
            else:
                existing = [c for c in cycles if _cycle_in(cl, c)]
                ignored = [c for c in cycles if not _cycle_in(cl, c)]
            if not existing:
                print("No matching cycles; nothing changed.")
                if ignored:
                    print("Ignored cycles:", ", ".join(str(c) for c in sorted(set(ignored))))
                continue
            # Palette: validate colormap before push (reject must not dirty undo / visibility).
            cols = None
            if mode == 'palette':
                if palette and palette.lower() in ('tab10', '1'):
                    cols = [mcolors.to_rgba(TAB10_HEX[i % len(TAB10_HEX)])
                            for i in range(len(existing))]
                else:
                    try:
                        cmap = get_colormap(palette) if palette else None
                    except Exception:
                        cmap = None
                    if cmap is None:
                        print(f"Unknown colormap '{palette}'.")
                        continue
                    cols = sample_colormap(cmap, len(existing), pair=(0.15, 0.85), span=(0.08, 0.88))
            push_state("cycles/colors")
            # Update visibility only when explicitly selecting cycles —
            # "all" recolors currently visible cycles without un-hiding.
            if not use_all:
                set_visible_cycles(cl, existing)
                # Keep multi-file stash in sync so old sessions re-save like new ones.
                try:
                    for f_entry in (file_data or []):
                        if f_entry.get("cycle_lines") is cl:
                            f_entry["selected_cycles"] = [
                                int(c) for c in existing if _coerce_cycle_id(c) is not None
                            ]
                            break
                except Exception:
                    pass
            if mode == 'map' and mapping:
                mapping2 = {c: mapping[c] for c in existing if c in mapping}
                apply_colors(cl, mapping2)
                if mapping2:
                    print("Applied manual colors:")
                    for cyc, col in mapping2.items():
                        print(f"  Cycle {cyc}: {format_color_listing(col)}")
            elif mode == 'palette' and cols:
                apply_colors(cl, {c: col for c, col in zip(existing, cols)})
                try:
                    preview = color_bar([mcolors.to_hex(col) for col in cols])
                except Exception:
                    preview = ""
                if preview:
                    palette_display = 'tab10 (default)' if palette and palette.lower() in ('tab10', '1') else palette
                    cc = _format_cycles_compact(cycles) if (not use_all and cycles) else ""
                    cyc_suff = f" — cycles {cc}" if cc else ""
                    print(f"Palette '{palette_display}' applied{cyc_suff}: {preview}")
            # mode == 'numbers': visibility-only selection; no recoloring.
            apply_curve_linewidth(fig, cl)
            if is_dqdv and hasattr(fig, '_dqdv_smooth_settings'):
                apply_stored_smooth_settings(cl, fig)
            # Re-apply display mode so re-shown cycles keep charge/discharge visibility
            dm = getattr(fig, '_ec_display_mode', 'both')
            apply_display_mode(dm)
            rebuild_legend(ax)
            apply_nice_ticks()
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            if ignored:
                print("Ignored cycles:", ", ".join(str(c) for c in sorted(set(ignored))))

    if not is_multi_file:
        _edit_one_file(cycle_lines, all_cycles)
        return

    # Multi-file: file picker → the same single-file menu per chosen file.
    while True:
        menu_block_begin(force_new=True)
        visible_entries = [f for f in file_data if f.get('visible', True)]
        if not visible_entries:
            print("No visible files.")
            print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            break
        if curves_status_fn is not None:
            # Counts only by default (colors behind ``v``).
            curves_status_fn()
        else:
            print_file_list(file_data, current_file_idx)
        print("  " + colorize_menu(f"1-{len(file_data)}: edit colors of that file"))
        print("  " + colorize_menu("v: show current colors"))
        print("  " + colorize_menu("q: back"))
        sel = safe_input(colorize_prompt("File number: ")).strip()
        if sel.lower() == 'q' or blank_means_back(sel):
            break
        if sel.lower() == 'v':
            shown = False
            if curves_status_fn is not None:
                try:
                    curves_status_fn(colors=True)  # type: ignore[call-arg]
                    shown = True
                except TypeError:
                    shown = False
            if not shown:
                _print_ec_current_curves(
                    target_cycle_lines_list=[
                        (f['cycle_lines'], sorted((f.get('cycle_lines') or {}).keys()))
                        for f in visible_entries
                    ],
                    is_multi_file=True,
                    file_data=file_data,
                )
            continue
        try:
            fidx = int(sel.lstrip('fF'))
        except ValueError:
            print(f"Enter a file number (1-{len(file_data)}), v, or q.")
            continue
        if not (1 <= fidx <= len(file_data)):
            print(f"File must be 1-{len(file_data)}.")
            continue
        f_entry = file_data[fidx - 1]
        cl = f_entry.get('cycle_lines') or {}
        if not cl:
            print("That file has no cycles to color.")
            continue
        if not f_entry.get('visible', True):
            print("Note: this file is currently hidden; color edits show once it is visible.")
        fname = f_entry.get('display_name') or f_entry.get('filename') or f"file {fidx}"
        _edit_one_file(
            cl,
            sorted(cl.keys(), key=_cycle_sort_key),
            header=f"Editing colors — file {fidx}: {fname}",
        )

__all__ = ["run_ec_cycles_menu"]
