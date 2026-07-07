"""Route multiple same-mode .pkl sessions to batch interactive editing."""

from __future__ import annotations

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ..._mpl_backend import (
    ensure_gui_backend,
    hold_figure_open,
    is_interactive_backend,
    prime_interactive_figure,
    running_headless,
    warn_if_noninteractive,
)
from .load import BatchLoadResult, load_batch_panels
from .menu_cpc import run_cpc_batch_menu
from .menu_ec import run_ec_batch_menu
from .menu_histo import run_histo_batch_menu
from .menu_operando import run_operando_batch_menu
from .menu_xy import run_xy_batch_menu


def _prime_all_panels(result: BatchLoadResult) -> None:
    for panel in result.panels:
        prime_interactive_figure(panel.fig)


def _run_batch_menu(result: BatchLoadResult) -> None:
    kind = result.kind
    panels = result.panels
    if kind == "xy":
        run_xy_batch_menu(panels)
    elif kind == "ec_gc":
        run_ec_batch_menu(panels)
    elif kind == "cpc":
        run_cpc_batch_menu(panels)
    elif kind == "operando_ec":
        run_operando_batch_menu(panels)
    elif kind == "histo":
        run_histo_batch_menu(panels)
    else:
        print(f"Batch session mode not implemented for: {kind}")


def handle_batch_session_reload(args) -> int:
    """Load multiple .pkl files of the same mode and run batch interactive menu."""
    ensure_gui_backend(args)
    if not is_interactive_backend() and not running_headless():
        warn_if_noninteractive("batch session reload")
        return 1

    paths = list(args.files or [])
    if len(paths) < 2:
        print("Batch session mode requires at least two .pkl files.")
        return 1

    loaded = load_batch_panels(paths)
    if isinstance(loaded, int):
        return loaded

    _prime_all_panels(loaded)
    try:
        _run_batch_menu(loaded)
    except Exception as exc:
        print(f"Batch interactive menu failed: {exc}")
        return 1
    finally:
        hold_figure_open()
        for panel in loaded.panels:
            try:
                plt.close(panel.fig)
            except Exception:
                pass
    return 0


__all__ = ["handle_batch_session_reload"]
