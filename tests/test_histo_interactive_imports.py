"""Regression: histogram interactive menu must import every handler it calls."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path


def _interactive_module_path() -> Path:
    return Path(__file__).resolve().parents[1] / "batplot" / "plot_modes" / "histo" / "interactive.py"


def _module_scope_names(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    names: set[str] = set(dir(builtins))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def _menu_handler_calls(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    menu_fn = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "histo_interactive_menu"
    )
    prefixes = ("run_histo_", "handle_", "_run_histo_")
    called: set[str] = set()
    for node in ast.walk(menu_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id.startswith(prefixes):
            called.add(func.id)
    return called


def test_histo_interactive_menu_handlers_are_imported():
    path = _interactive_module_path()
    available = _module_scope_names(path)
    called = _menu_handler_calls(path)
    missing = sorted(called - available)
    assert not missing, f"histo_interactive_menu calls undefined handlers: {missing}"


def test_histo_interactive_y_range_import():
    from batplot.plot_modes.histo.interactive import run_histo_y_range_menu

    assert callable(run_histo_y_range_menu)


def test_histo_batch_menu_y_range_import():
    from batplot.plot_modes.batch_session.menu_histo import run_histo_batch_menu
    from batplot.plot_modes.histo.y_range import run_histo_y_range_menu

    assert callable(run_histo_batch_menu)
    assert callable(run_histo_y_range_menu)
