"""Interactive add-file support for CPC/EPC sessions."""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Sequence

import matplotlib.colors as mcolors  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ...color_utils import get_colormap
from ...utils import parse_mass_mg_from_cli, _ask_files_dialog
from ..common.palettes import TAB10_HEX
from .legend import _rebuild_legend
from .load import cpc_file_needs_mass, cpc_supported_extension, load_cpc_file_arrays

_DATA_FILETYPES = (".csv", ".CSV", ".xlsx", ".XLSX", ".xls", ".XLS", ".mpt", ".MPT")


def detect_cpc_is_epc(fig, ax=None) -> bool:
    flag = getattr(fig, "_cpc_is_epc", None)
    if flag is not None:
        return bool(flag)
    try:
        ylab = str((ax.get_ylabel() if ax is not None else "") or "").lower()
    except Exception:
        ylab = ""
    return ("energy" in ylab) or ("mwh" in ylab)


def next_cpc_file_colors(n_existing: int) -> tuple[str, str]:
    """Capacity (tab10) + efficiency (viridis) colors for the next file index."""
    cap = TAB10_HEX[n_existing % len(TAB10_HEX)]
    cmap = get_colormap("viridis")
    if n_existing <= 0:
        pos = 0.55
    else:
        pos = float(np.linspace(0.08, 0.88, n_existing + 1)[-1])
    if cmap is None:
        eff = "#440154"
    else:
        eff = mcolors.rgb2hex(cmap(pos)[:3])
    return cap, eff


def _series_labels(filename: str, *, multi: bool, is_epc: bool) -> tuple[str, str, str]:
    if not multi:
        if is_epc:
            return (
                "Charge energy density",
                "Discharge energy density",
                "Coulombic efficiency",
            )
        return "Charge capacity", "Discharge capacity", "Coulombic efficiency"
    return f"{filename} (Chg)", f"{filename} (Dch)", f"{filename} (Eff)"


def relabel_cpc_files_for_count(file_data: List[dict], *, is_epc: bool) -> None:
    """Keep single-file role labels vs multi-file ``name (Chg)`` labels in sync."""
    multi = len(file_data) > 1
    for info in file_data:
        base = (
            info.get("display_name")
            or info.get("filename")
            or os.path.basename(str(info.get("filepath") or "Data"))
        )
        # Strip extension for cleaner multi labels when still a raw filename.
        if multi and isinstance(base, str) and "." in base and base.lower().endswith(
            (".csv", ".xlsx", ".xls", ".mpt")
        ):
            label_base = os.path.splitext(base)[0]
        else:
            label_base = str(base)
        chg, dch, eff = _series_labels(
            label_base if multi else str(base), multi=multi, is_epc=is_epc
        )
        for key, lab in (
            ("sc_charge", chg),
            ("sc_discharge", dch),
            ("sc_eff", eff),
        ):
            sc = info.get(key)
            if sc is not None:
                try:
                    sc.set_label(lab)
                except Exception:
                    pass
        if multi:
            info["display_name"] = label_base
        elif "display_name" not in info or not info.get("display_name"):
            info["display_name"] = str(base)


def create_cpc_scatter_artists(
    ax,
    ax2,
    *,
    cyc_nums,
    cap_charge,
    cap_discharge,
    eff,
    color: str,
    eff_color: str,
    label_chg: str,
    label_dch: str,
    label_eff: str,
    display_mode: str = "both",
    file_visible: bool = True,
    eff_visible: bool = True,
    sizes: Optional[tuple[float, float, float]] = None,
):
    """Create the three CPC scatter artists for one file."""
    sz_c, sz_d, sz_e = sizes if sizes is not None else (32.0, 32.0, 40.0)
    sc_charge = ax.scatter(
        cyc_nums,
        cap_charge,
        label=label_chg,
        s=sz_c,
        zorder=3,
        alpha=0.8,
        marker="s",
        color=color,
    )
    sc_discharge = ax.scatter(
        cyc_nums,
        cap_discharge,
        label=label_dch,
        s=sz_d,
        zorder=3,
        alpha=0.8,
        marker="s",
        facecolor="none",
        edgecolor=color,
    )
    sc_eff = ax2.scatter(
        cyc_nums,
        eff,
        color=eff_color,
        marker="^",
        label=label_eff,
        s=sz_e,
        alpha=0.7,
        zorder=3,
    )
    dm = display_mode if display_mode in ("charge", "discharge", "both") else "both"
    try:
        sc_charge.set_visible(bool(file_visible) and dm in ("charge", "both"))
        sc_discharge.set_visible(bool(file_visible) and dm in ("discharge", "both"))
        sc_eff.set_visible(bool(file_visible) and bool(eff_visible))
    except Exception:
        pass
    return sc_charge, sc_discharge, sc_eff


def _legend_currently_visible(ax, ax2) -> bool:
    for host in (ax, ax2):
        try:
            leg = host.get_legend()
            if leg is not None and bool(leg.get_visible()):
                return True
        except Exception:
            pass
    return False


def _peer_efficiency_visible(file_data: Sequence[dict]) -> bool:
    """Match existing files: if every visible peer has Eff hidden, hide new Eff too."""
    peers = [
        f
        for f in file_data
        if f.get("visible", True) and f.get("sc_eff") is not None
    ]
    if not peers:
        return True
    for f in peers:
        sc = f.get("sc_eff")
        try:
            if bool(sc.get_visible()):
                return True
        except Exception:
            return True
    return False


def _peer_marker_sizes(file_data: Sequence[dict]) -> Optional[tuple[float, float, float]]:
    if not file_data:
        return None
    ref = file_data[0]
    try:
        sc_c = ref.get("sc_charge")
        sc_d = ref.get("sc_discharge")
        sc_e = ref.get("sc_eff")
        sz_c = float(sc_c.get_sizes()[0]) if sc_c is not None else 32.0
        sz_d = float(sc_d.get_sizes()[0]) if sc_d is not None else 32.0
        sz_e = float(sc_e.get_sizes()[0]) if sc_e is not None else 40.0
        return (sz_c, sz_d, sz_e)
    except Exception:
        return None


def _rebuild_legend_preserving_visibility(ax, ax2, file_data) -> None:
    was_visible = _legend_currently_visible(ax, ax2)
    _rebuild_legend(ax, ax2, file_data, preserve_position=True)
    if not was_visible:
        for host in (ax, ax2):
            try:
                leg = host.get_legend()
                if leg is not None:
                    leg.set_visible(False)
            except Exception:
                pass


def append_cpc_file(
    fig,
    ax,
    ax2,
    file_data: List[dict],
    path: str,
    *,
    mass_mg: Optional[float] = None,
    is_epc: Optional[bool] = None,
) -> dict:
    """Load ``path`` and append a new entry (+ artists) to ``file_data``.

    Returns the new ``file_data`` entry. Raises on duplicate path / load errors.
    """
    resolved = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"File not found: {resolved}")
    if not cpc_supported_extension(resolved):
        raise ValueError("Unsupported format (use .csv, .xlsx, .xls, or .mpt)")

    for existing in file_data:
        prev = existing.get("filepath")
        if prev and os.path.abspath(str(prev)) == resolved:
            raise ValueError(f"Already loaded: {os.path.basename(resolved)}")

    epc = detect_cpc_is_epc(fig, ax) if is_epc is None else bool(is_epc)
    cyc, qchg, qdch, eta = load_cpc_file_arrays(
        resolved, mass_mg=mass_mg, is_epc=epc
    )
    if len(np.asarray(cyc)) == 0:
        raise ValueError("No cycle data found in file")

    # Adding onto an existing list → multi-file labels after append.
    multi_after = len(file_data) >= 1
    color, eff_color = next_cpc_file_colors(len(file_data))
    basename = os.path.basename(resolved)
    stem = os.path.splitext(basename)[0]
    label_base = stem if multi_after else basename
    chg, dch, eff_lab = _series_labels(label_base, multi=multi_after, is_epc=epc)
    display_mode = getattr(fig, "_cpc_display_mode", "both") or "both"
    eff_visible = _peer_efficiency_visible(file_data)
    sizes = _peer_marker_sizes(file_data)

    sc_c, sc_d, sc_e = create_cpc_scatter_artists(
        ax,
        ax2,
        cyc_nums=cyc,
        cap_charge=qchg,
        cap_discharge=qdch,
        eff=eta,
        color=color,
        eff_color=eff_color,
        label_chg=chg,
        label_dch=dch,
        label_eff=eff_lab,
        display_mode=str(display_mode),
        file_visible=True,
        eff_visible=eff_visible,
        sizes=sizes,
    )

    entry = {
        "filename": basename,
        "display_name": stem if multi_after else basename,
        "filepath": resolved,
        "mass_mg": float(mass_mg) if mass_mg is not None else None,
        "cyc_nums": np.asarray(cyc, dtype=float),
        "cap_charge": np.asarray(qchg, dtype=float),
        "cap_discharge": np.asarray(qdch, dtype=float),
        "eff": np.asarray(eta, dtype=float),
        "color": color,
        "eff_color": eff_color,
        "visible": True,
        "eff_inverted": False,
        "sc_charge": sc_c,
        "sc_discharge": sc_d,
        "sc_eff": sc_e,
    }
    file_data.append(entry)

    # First→multi: rewrite existing file labels to compact form.
    if len(file_data) > 1:
        relabel_cpc_files_for_count(file_data, is_epc=epc)
        try:
            fig._cpc_is_multi_file = True
        except Exception:
            pass
        # Spine auto is single-file only.
        try:
            if getattr(fig, "_cpc_spine_auto", False):
                fig._cpc_spine_auto = False
                print("Spine color auto mode turned OFF (multi-file).")
        except Exception:
            pass

    try:
        fig._cpc_is_epc = bool(epc)
    except Exception:
        pass

    # Keep legend display order in sync (new file at end unless already tracked).
    try:
        from .legend_order import ensure_cpc_legend_file_order

        ensure_cpc_legend_file_order(fig, file_data, ax=ax)
    except Exception:
        pass

    _rebuild_legend_preserving_visibility(ax, ax2, file_data)
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass
    return entry


def trim_cpc_files_to_count(
    fig,
    ax,
    ax2,
    file_data: List[dict],
    n_keep: int,
    *,
    is_epc: Optional[bool] = None,
) -> None:
    """Remove trailing files (artists + entries) so ``len(file_data) == n_keep``.

    Used by undo when restoring a pre-add checkpoint.
    """
    if n_keep < 0:
        n_keep = 0
    while len(file_data) > n_keep:
        info = file_data.pop()
        for key in ("sc_charge", "sc_discharge", "sc_eff"):
            sc = info.get(key)
            if sc is None:
                continue
            try:
                sc.remove()
            except Exception:
                try:
                    sc.set_visible(False)
                except Exception:
                    pass
    epc = detect_cpc_is_epc(fig, ax) if is_epc is None else bool(is_epc)
    if file_data:
        relabel_cpc_files_for_count(file_data, is_epc=epc)
    try:
        fig._cpc_is_multi_file = len(file_data) > 1
    except Exception:
        pass
    try:
        from .legend_order import ensure_cpc_legend_file_order

        ensure_cpc_legend_file_order(fig, file_data, ax=ax)
    except Exception:
        pass
    if file_data:
        _rebuild_legend_preserving_visibility(ax, ax2, file_data)
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def _prompt_mass_mg(safe_input, colorize_prompt, *, required: bool, basename: str) -> Optional[float]:
    mode = "required" if required else "optional (Enter to skip)"
    while True:
        raw = safe_input(
            colorize_prompt(
                f"Active mass for {basename} [{mode}; e.g. 5.2 or 5.2mg or 0.0052g, q=cancel]: "
            )
        ).strip()
        if raw.lower() == "q":
            return None
        if not raw:
            if required:
                print("Mass is required for this file.")
                continue
            return None
        try:
            return float(parse_mass_mg_from_cli(raw))
        except Exception as exc:
            print(f"Invalid mass: {exc}")


def _add_one_path(
    *,
    fig,
    ax,
    ax2,
    file_data,
    path: str,
    is_epc: bool,
    push_state,
    pop_undo,
    safe_input,
    colorize_prompt,
    pushed_ref: list,
) -> bool:
    """Load/append one path. ``pushed_ref`` is a 1-item list tracking undo push."""
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        return False
    if not cpc_supported_extension(path):
        print(f"Unsupported format: {os.path.basename(path)} (use .csv/.xlsx/.xls/.mpt)")
        return False

    mass_mg = None
    if cpc_file_needs_mass(path):
        mass_mg = _prompt_mass_mg(
            safe_input,
            colorize_prompt,
            required=True,
            basename=os.path.basename(path),
        )
        if mass_mg is None:
            print(f"Skipped {os.path.basename(path)} (no mass).")
            return False

    if not pushed_ref[0]:
        try:
            # push_cpc_state returns False when nothing was appended.
            pushed_ref[0] = bool(push_state("add-file"))
        except Exception:
            pushed_ref[0] = False

    try:
        entry = append_cpc_file(
            fig, ax, ax2, file_data, path, mass_mg=mass_mg, is_epc=is_epc
        )
        print(
            f"Added file {len(file_data)}: "
            f"{entry.get('display_name') or entry.get('filename')}"
        )
        print(f"  ({entry.get('filepath')})")
        return True
    except Exception as exc:
        if pushed_ref[0] and pop_undo is not None and len(file_data) == 0:
            # Only pop if nothing was successfully added yet — rare.
            pass
        print(f"Could not add {os.path.basename(path)}: {exc}")
        return False


def run_cpc_add_files_menu(
    *,
    fig: Any,
    ax: Any,
    ax2: Any,
    file_data: List[dict],
    push_state: Callable[[str], Any],
    pop_undo: Callable[[], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    print_menu: Callable[..., Any],
) -> None:
    """Top-level ``a``: open multi-file picker immediately, then append series."""
    is_epc = detect_cpc_is_epc(fig, ax)
    mode = "EPC" if is_epc else "CPC"
    print(f"\nSelect {mode} data file(s)… (.csv / .xlsx / .xls / .mpt)")
    try:
        paths = list(
            _ask_files_dialog(
                filetypes=_DATA_FILETYPES,
                title=f"Select {mode} data file(s)",
                multiple=True,
            )
            or []
        )
    except Exception:
        paths = []

    if not paths:
        # Fallback when dialog cancelled / unavailable (headless, CI, SSH).
        line = safe_input(
            colorize_prompt(
                "No file selected. Type a path (or several space-separated), q=back: "
            )
        ).strip()
        if not line or line.lower() == "q":
            try:
                print_menu(fig)
            except TypeError:
                print_menu()
            except Exception:
                pass
            return
        # Shared parser: Windows keeps backslashes; strips outer quotes for spaces.
        from ...utils import _parse_typed_path_list

        paths = _parse_typed_path_list(line)

    pushed_ref = [False]
    n_before = len(file_data)
    for path in paths:
        _add_one_path(
            fig=fig,
            ax=ax,
            ax2=ax2,
            file_data=file_data,
            path=path,
            is_epc=is_epc,
            push_state=push_state,
            pop_undo=pop_undo,
            safe_input=safe_input,
            colorize_prompt=colorize_prompt,
            pushed_ref=pushed_ref,
        )

    if len(file_data) == n_before and pushed_ref[0] and pop_undo is not None:
        # Pushed undo but every add failed — drop empty checkpoint.
        try:
            pop_undo()
        except Exception:
            pass

    try:
        print_menu(fig)
    except TypeError:
        print_menu()
    except Exception:
        pass


__all__ = [
    "append_cpc_file",
    "create_cpc_scatter_artists",
    "detect_cpc_is_epc",
    "next_cpc_file_colors",
    "relabel_cpc_files_for_count",
    "run_cpc_add_files_menu",
    "trim_cpc_files_to_count",
]
