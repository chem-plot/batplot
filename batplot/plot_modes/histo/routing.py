"""Top-level routing for histogram mode."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ..._mpl_backend import (
    ensure_gui_backend,
    hold_figure_open,
    prime_interactive_figure,
    require_interactive_display,
    show_figure_if_possible,
)
from ...batch import HISTO_BATCH_EXTENSIONS, batch_process_histo
from ...utils import natural_sort_key
from .interactive import histo_interactive_menu
from .load import (
    TableData,
    auto_range,
    build_bin_edges,
    column_stats,
    load_table,
    resolve_column_index,
    suggest_bin_width,
)
from .plot import build_histo_state, create_histo_figure
from .wizard import HistoSetup, run_histo_wizard

HISTO_ALLFILES_EXTENSIONS = frozenset(HISTO_BATCH_EXTENSIONS)


def _resolve_data_files(files) -> list[str]:
    data_files = []
    for f in files or []:
        if os.path.isdir(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in (".bps", ".bpsg", ".bpcfg", ".bpsh", ".pkl"):
            continue
        data_files.append(f)
    return data_files


def _list_histo_files(directory: str) -> list[str]:
    files = []
    for name in sorted(os.listdir(directory), key=natural_sort_key):
        full = os.path.join(directory, name)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(name)[1].lower() in HISTO_ALLFILES_EXTENSIONS:
            files.append(full)
    return files


def _maybe_expand_histo_allfiles(args) -> None:
    """Expand ``allfiles`` / ``allcsvfiles`` tokens for histogram mode."""
    if not args.files:
        return
    token_info = []
    non_token_entries = []
    for original in args.files:
        lower = original.lower()
        if lower.startswith("all") and lower.endswith("files"):
            token_info.append((original, lower[3:-5]))
        else:
            non_token_entries.append(original)
    if not token_info:
        return
    if len(token_info) > 1:
        print("Specify only one all*files token (e.g., allfiles or allcsvfiles) at a time.")
        raise SystemExit(1)
    _, middle = token_info[0]
    if len(non_token_entries) > 1:
        print("When using all*files tokens, provide zero or one directory argument.")
        raise SystemExit(1)
    if middle:
        ext = f".{middle}"
        if ext not in HISTO_ALLFILES_EXTENSIONS:
            allowed = ", ".join(sorted(e.strip(".") for e in HISTO_ALLFILES_EXTENSIONS))
            print(f"Unknown all-files token 'all{middle}files'. Allowed extensions: {allowed}")
            raise SystemExit(1)
        allowed_exts = {ext}
    else:
        allowed_exts = HISTO_ALLFILES_EXTENSIONS
    if len(non_token_entries) == 1:
        dir_arg = non_token_entries[0]
        if not os.path.isdir(dir_arg):
            print(f"Directory not found: {dir_arg}")
            raise SystemExit(1)
        target_dir = os.path.abspath(dir_arg)
        use_relative = False
    else:
        target_dir = os.getcwd()
        use_relative = True
    collected = []
    for name in sorted(os.listdir(target_dir), key=natural_sort_key):
        full = os.path.join(target_dir, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in allowed_exts:
            continue
        collected.append(name if use_relative else full)
    if not collected:
        ext_list = ", ".join(sorted(allowed_exts))
        print(f"No {ext_list} files found in directory: {target_dir}")
        raise SystemExit(1)
    print(f"Found {len(collected)} histogram file(s) to process")
    args.files = collected


def _setup_from_args(
    args,
    table: TableData,
    *,
    interactive: bool | None = None,
) -> HistoSetup | None:
    col = getattr(args, "histocol", None)
    if col is None and getattr(args, "readcol", None):
        # Legacy convenience: --readcol N y uses column N for histogram.
        col = args.readcol[0]
    use_interactive = getattr(args, "interactive", False) if interactive is None else interactive
    if use_interactive:
        fixed = None
        if col is not None:
            try:
                fixed = resolve_column_index(table, col)
            except ValueError as exc:
                print(exc)
                return None
        return run_histo_wizard(table, fixed_col=fixed)
    if col is None:
        print("Histogram mode: specify which column to plot, e.g. --histocol Length")
        print("  or use --i for the column/range/bin wizard.")
        return None
    col_index = resolve_column_index(table, col)
    values = table.column_values(col_index)
    headers = table.padded_headers()
    col_name = headers[col_index - 1].strip() or f"column {col_index}"

    xrange = getattr(args, "xrange", None)
    if xrange and len(xrange) == 2:
        xmin, xmax = float(xrange[0]), float(xrange[1])
    else:
        xmin, xmax = auto_range(values)

    bin_width = getattr(args, "binwidth", None)
    n_bins = getattr(args, "bins", None)
    if bin_width is None and n_bins is None:
        bin_width = suggest_bin_width(xmin, xmax, column_stats(values)["n"])
    edges = build_bin_edges(xmin, xmax, bin_width=bin_width, n_bins=n_bins)
    return HistoSetup(
        column_index=col_index,
        column_name=col_name,
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )


def _setup_from_template(template: HistoSetup, table: TableData, path: str) -> HistoSetup | None:
    try:
        col_index = template.column_index
        if col_index > table.ncols:
            print(f"Skipping {os.path.basename(path)}: column {col_index} not in file")
            return None
        values = table.column_values(col_index)
    except ValueError as exc:
        print(f"Skipping {os.path.basename(path)}: {exc}")
        return None
    headers = table.padded_headers()
    col_name = headers[col_index - 1].strip() or f"column {col_index}"
    return HistoSetup(
        column_index=col_index,
        column_name=col_name,
        values=values,
        xmin=template.xmin,
        xmax=template.xmax,
        bin_edges=template.bin_edges.copy(),
    )


def _resolve_histo_batch_directory(args) -> str | None:
    if getattr(args, "all", None) is not None:
        return os.getcwd()
    if len(args.files) == 1:
        sole = args.files[0]
        if sole.lower() == "all":
            return os.getcwd()
        if os.path.isdir(sole):
            return os.path.abspath(sole)
    return None


def _handle_histo_batch_interactive(args, data_files: list[str]) -> int:
    from ...plot_modes.batch_session.load import HistoPanel
    from ...plot_modes.batch_session.menu_histo import run_histo_batch_menu

    if not require_interactive_display(args, context="histogram batch interactive menu"):
        return 1

    wizard_template: HistoSetup | None = None
    panels: list[HistoPanel] = []
    for fpath in data_files:
        path = os.path.abspath(fpath)
        try:
            table = load_table(path)
        except Exception as exc:
            print(f"Skipping {os.path.basename(path)}: {exc}")
            continue

        if getattr(args, "histocol", None) is not None or getattr(args, "readcol", None):
            setup = _setup_from_args(args, table, interactive=False)
        elif wizard_template is not None:
            setup = _setup_from_template(wizard_template, table, path)
        else:
            setup = run_histo_wizard(table)
            if setup is None:
                return 1
            wizard_template = setup

        if setup is None:
            continue
        state = build_histo_state(setup, source_path=path)
        try:
            fig, ax, _meta = create_histo_figure(state)
        except Exception as exc:
            print(f"Skipping {os.path.basename(path)}: {exc}")
            continue
        panels.append(HistoPanel(path=path, fig=fig, ax=ax, state=state))

    if len(panels) < 2:
        print("Histogram batch interactive mode requires at least two data files.")
        return 1

    for panel in panels:
        prime_interactive_figure(panel.fig)
    try:
        run_histo_batch_menu(panels)
    except Exception as exc:
        print(f"Histogram batch interactive menu failed: {exc}")
        return 1
    finally:
        hold_figure_open()
        for panel in panels:
            try:
                plt.close(panel.fig)
            except Exception:
                pass
    return 0


def _handle_single_histo(args, path: str) -> int:
    try:
        table = load_table(path)
    except Exception as exc:
        print(f"Could not load table: {exc}")
        return 1

    setup = _setup_from_args(args, table)
    if setup is None:
        return 1

    state = build_histo_state(setup, source_path=path)
    try:
        fig, ax, _meta = create_histo_figure(state)
    except Exception as exc:
        print(f"Histogram plot failed: {exc}")
        return 1

    outname = getattr(args, "savefig", None) or getattr(args, "out", None)
    if outname:
        if not os.path.splitext(outname)[1]:
            outname += ".png"
        try:
            fig.savefig(outname, dpi=300, bbox_inches="tight")
            print(f"Histogram saved to {outname}")
        except Exception as exc:
            print(f"Save failed: {exc}")
            return 1

    from ...cli_save import run_cli_save_if_requested, should_show_plot
    from .interactive import _save_session

    def _do_histo_cli_save(target: str) -> None:
        _save_session(fig, ax, state, target)

    if run_cli_save_if_requested(
        args,
        [os.path.abspath(path)],
        purpose="histogram session save",
        default_stem=os.path.splitext(os.path.basename(path))[0],
        combined_plot=False,
        save_fn=_do_histo_cli_save,
    ):
        try:
            plt.close(fig)
        except Exception:
            pass
        return 0

    if getattr(args, "interactive", False):
        if require_interactive_display(args, context="histogram interactive menu"):
            prime_interactive_figure(fig)
            try:
                histo_interactive_menu(fig, ax, state, table_loader=lambda: table)
            except Exception as exc:
                print(f"Interactive menu failed: {exc}")
            hold_figure_open()
    else:
        if should_show_plot(args) and not outname:
            show_figure_if_possible(args)
    try:
        plt.close(fig)
    except Exception:
        pass
    return 0


def handle_histo_mode(args) -> int:
    """Handle histogram mode including batch export and batch interactive editing."""
    ensure_gui_backend(args)

    batch_dir = _resolve_histo_batch_directory(args)
    if batch_dir is not None:
        batch_process_histo(batch_dir, args)
        return 0

    _maybe_expand_histo_allfiles(args)

    data_files = _resolve_data_files(args.files)
    if not data_files:
        print("Histogram mode: provide a .csv or .txt file, a folder, or use --all / allfiles.")
        print("Examples:")
        print("  batplot data.csv --histo --i")
        print("  batplot --all --histo --histocol Length")
        print("  batplot allfiles --histo --i")
        return 1

    if len(data_files) >= 2:
        if getattr(args, "interactive", False):
            return _handle_histo_batch_interactive(args, data_files)
        first_dir = os.path.dirname(os.path.abspath(data_files[0]))
        batch_process_histo(first_dir, args, only_files=data_files)
        return 0

    return _handle_single_histo(args, os.path.abspath(data_files[0]))


__all__ = ["handle_histo_mode"]
