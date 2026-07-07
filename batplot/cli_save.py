"""Non-interactive session save (--save) for batplot CLI routes.

Prompts for a save directory (same options as interactive ``s``) and a
``.pkl`` filename.  Single-file and ``--all`` batch runs default to the data
file stem; combined plots (``allfiles``, operando, multi-file GC/CPC) require
an explicit name.
"""

from __future__ import annotations

import copy
import os
import sys
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Optional, Sequence

from .utils import _confirm_overwrite, choose_save_path, ensure_exact_case_filename, natural_sort_key

STYLE_EXTS = {".bps", ".bpsg", ".bpcfg"}


def wants_cli_session_save(args) -> bool:
    """True when ``--save`` is set without ``--i``."""
    return bool(getattr(args, "save", False)) and not getattr(args, "interactive", False)


def should_show_plot(args) -> bool:
    """Return False when the figure should not be displayed after plotting."""
    if getattr(args, "savefig", False) or getattr(args, "out", None):
        return False
    if wants_cli_session_save(args):
        return False
    return True


def filter_data_paths(paths: Iterable[str]) -> list[str]:
    """Keep existing non-style input paths for save-location prompts."""
    out: list[str] = []
    for raw in paths or []:
        if not raw:
            continue
        try:
            abs_path = os.path.abspath(str(raw))
        except Exception:
            continue
        ext = os.path.splitext(abs_path)[1].lower()
        if ext in STYLE_EXTS:
            continue
        if os.path.isfile(abs_path) or os.path.isdir(abs_path):
            out.append(abs_path)
    return out


def clone_args_for_file(args, fpath: str):
    """Shallow-copy ``args`` for per-file batch ``--save`` runs."""
    sub = copy.copy(args)
    sub.files = [fpath]
    sub.all = None
    if getattr(sub, "delta", None) is None:
        sub.delta = 0.1 if getattr(sub, "stack", False) else 0.0
    return sub


def get_or_prompt_save_folder(args, source_paths: Sequence[str], purpose: str) -> Optional[str]:
    cached = getattr(args, "_cli_save_folder", None)
    if cached:
        return cached
    folder = choose_save_path(list(source_paths), purpose=purpose)
    if folder:
        args._cli_save_folder = folder
    return folder


def _normalize_pkl_name(name: str) -> str:
    root, ext = os.path.splitext(name)
    if ext.lower() != ".pkl":
        return root + ".pkl"
    return name


def prompt_session_target(
    folder: str,
    *,
    default_stem: Optional[str] = None,
    require_name: bool = False,
    batch_auto: bool = False,
) -> Optional[str]:
    """Prompt for a session filename inside ``folder``; return full path or None."""
    if batch_auto and default_stem:
        target = ensure_exact_case_filename(os.path.join(folder, _normalize_pkl_name(default_stem)))
        return _confirm_overwrite(target)

    if require_name:
        try:
            choice = input("Enter session filename (required, q=cancel): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCanceled.")
            return None
        if not choice or choice.lower() == "q":
            print("Save canceled.")
            return None
        name = _normalize_pkl_name(choice)
        target = name if os.path.isabs(name) else os.path.join(folder, name)
        target = ensure_exact_case_filename(target)
        if os.path.exists(target):
            yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
            if yn != "y":
                print("Save canceled.")
                return None
        return target

    hint = f" [{default_stem}.pkl]" if default_stem else ""
    try:
        choice = input(f"Enter session filename{hint} (Enter=default, q=cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCanceled.")
        return None
    if choice.lower() == "q":
        print("Save canceled.")
        return None
    if not choice:
        if not default_stem:
            print("Save canceled.")
            return None
        name = _normalize_pkl_name(default_stem)
    else:
        name = _normalize_pkl_name(choice)
    target = name if os.path.isabs(name) else os.path.join(folder, name)
    target = ensure_exact_case_filename(target)
    if os.path.exists(target):
        yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
        if yn != "y":
            print("Save canceled.")
            return None
    return target


def run_cli_session_save_flow(
    args,
    source_paths: Sequence[str],
    *,
    purpose: str,
    default_stem: Optional[str] = None,
    combined_plot: bool = False,
    batch_auto: bool = False,
) -> Optional[str]:
    """Choose folder + filename; return absolute ``.pkl`` path or None."""
    paths = filter_data_paths(source_paths)
    if not paths and source_paths:
        paths = [os.path.abspath(str(p)) for p in source_paths if p]
    folder = get_or_prompt_save_folder(args, paths, purpose)
    if not folder:
        print("Save canceled.")
        return None
    print(f"\nChosen path: {folder}")
    require_name = combined_plot or (default_stem is None and not batch_auto)
    return prompt_session_target(
        folder,
        default_stem=default_stem,
        require_name=require_name,
        batch_auto=batch_auto,
    )


def save_xy_session(
    target: str,
    *,
    fig,
    ax,
    x_data_list,
    y_data_list,
    orig_y,
    x_full_list,
    raw_y_full_list,
    offsets_list,
    labels,
    delta,
    args,
    cif_tick_series=None,
    cif_hkl_map=None,
    cif_hkl_label_map=None,
    show_cif_hkl=False,
    show_cif_titles=True,
) -> None:
    from .plot_modes.common.spines import default_flat_tick_state
    from .session import dump_session

    tick_state = default_flat_tick_state()
    dump_session(
        target,
        fig=fig,
        ax=ax,
        x_data_list=x_data_list,
        y_data_list=y_data_list,
        orig_y=orig_y,
        x_full_list=x_full_list,
        raw_y_full_list=raw_y_full_list,
        offsets_list=offsets_list,
        labels=labels,
        delta=delta,
        args=args,
        tick_state=tick_state,
        cif_tick_series=cif_tick_series,
        cif_hkl_map=cif_hkl_map,
        cif_hkl_label_map=cif_hkl_label_map,
        show_cif_hkl=show_cif_hkl,
        show_cif_titles=show_cif_titles,
        skip_confirm=True,
    )
    fig._last_session_save_path = os.path.abspath(target)


@contextmanager
def catch_system_exit():
    """Treat ``exit()`` in mode handlers as normal return (batch ``--save``)."""
    try:
        yield
    except SystemExit:
        pass


def invoke_ec_mode_with_exit(args) -> None:
    from .plot_modes.electrochem.routing import (
        handle_cv_mode,
        handle_dqdv_mode,
        handle_gc_mode,
    )

    with catch_system_exit():
        if getattr(args, "gc", False):
            handle_gc_mode(args)
        elif getattr(args, "cv", False):
            handle_cv_mode(args)
        elif getattr(args, "dqdv", False):
            handle_dqdv_mode(args)
        elif getattr(args, "cpc", False) or getattr(args, "epc", False):
            from .plot_modes.cpc.routing import handle_cpc_mode

            handle_cpc_mode(args)


def batch_save_xy_directory(directory: str, args, files: Sequence[str]) -> None:
    """``--all --save`` for XY: one session per file using the full XY pipeline."""
    from .plot_modes.xy.pipeline import run_xy_pipeline

    folder = get_or_prompt_save_folder(args, [directory], purpose="project save")
    if not folder:
        print("Save canceled.")
        return
    args._cli_save_folder = folder
    print(f"\nChosen path: {folder}")
    print(f"Saving sessions for {len(files)} file(s)...")
    saved = 0
    for fname in files:
        fpath = os.path.join(directory, fname)
        sub = clone_args_for_file(args, fpath)
        sub._cli_save_folder = folder
        sub._cli_save_batch = True
        try:
            rc = run_xy_pipeline(sub)
            if rc == 0:
                saved += 1
        except SystemExit:
            saved += 1
        except Exception as exc:
            print(f"  Skipped {fname}: {exc}")
    print(f"Batch session save complete ({saved}/{len(files)} files).")


def batch_save_ec_directory(directory: str, args) -> None:
    """``--all --save`` for EC modes: one session per file via mode routing."""
    mode = None
    supported_ext: set[str] = set()
    if getattr(args, "gc", False):
        mode = "gc"
        supported_ext = {".mpt", ".npt", ".csv"}
    elif getattr(args, "cv", False):
        mode = "cv"
        supported_ext = {".mpt", ".npt", ".txt"}
    elif getattr(args, "dqdv", False):
        mode = "dqdv"
        supported_ext = {".mpt", ".npt", ".csv"}
    elif getattr(args, "cpc", False) or getattr(args, "epc", False):
        mode = "cpc"
        supported_ext = {".mpt", ".npt", ".csv", ".xlsx", ".xls"}
    else:
        print("EC batch --save requires one of: --gc, --cv, --dqdv, --cpc")
        return

    files = [
        f
        for f in sorted(os.listdir(directory), key=natural_sort_key)
        if os.path.isfile(os.path.join(directory, f))
        and os.path.splitext(f)[1].lower() in supported_ext
    ]
    if not files:
        print(f"No {mode.upper()} files found.")
        return

    folder = get_or_prompt_save_folder(args, [directory], purpose=f"{mode.upper()} session save")
    if not folder:
        print("Save canceled.")
        return
    args._cli_save_folder = folder
    print(f"\nChosen path: {folder}")
    print(f"Saving sessions for {len(files)} file(s)...")
    saved = 0
    for fname in files:
        fpath = os.path.join(directory, fname)
        sub = clone_args_for_file(args, fpath)
        sub._cli_save_folder = folder
        sub._cli_save_batch = True
        try:
            invoke_ec_mode_with_exit(sub)
            saved += 1
        except Exception as exc:
            print(f"  Skipped {fname}: {exc}")
    print(f"Batch session save complete ({saved}/{len(files)} files).")


def batch_save_histo_directory(directory: str, args, files: Sequence[str]) -> None:
    """``--all --histo --save``: one histogram session per CSV/TXT file."""
    from .plot_modes.histo.routing import _handle_single_histo

    folder = get_or_prompt_save_folder(args, [directory], purpose="histogram session save")
    if not folder:
        print("Save canceled.")
        return
    args._cli_save_folder = folder
    print(f"\nChosen path: {folder}")
    print(f"Saving sessions for {len(files)} file(s)...")
    saved = 0
    for fname in files:
        fpath = os.path.join(directory, fname)
        sub = clone_args_for_file(args, fpath)
        sub._cli_save_folder = folder
        sub._cli_save_batch = True
        try:
            rc = _handle_single_histo(sub, fpath)
            if rc == 0:
                saved += 1
        except Exception as exc:
            print(f"  Skipped {fname}: {exc}")
    print(f"Batch session save complete ({saved}/{len(files)} files).")


def run_cli_save_if_requested(
    args,
    source_paths: Sequence[str],
    *,
    purpose: str,
    default_stem: Optional[str],
    combined_plot: bool,
    save_fn: Callable[[str], None],
) -> bool:
    """Run the ``--save`` flow when active. Returns True if save was attempted."""
    if not wants_cli_session_save(args):
        return False
    batch_auto = bool(getattr(args, "_cli_save_batch", False))
    target = run_cli_session_save_flow(
        args,
        source_paths,
        purpose=purpose,
        default_stem=default_stem,
        combined_plot=combined_plot,
        batch_auto=batch_auto,
    )
    if not target:
        return True
    try:
        save_fn(target)
        print(f"Session saved to {target}")
    except Exception as exc:
        print(f"Session save failed: {exc}")
    return True
