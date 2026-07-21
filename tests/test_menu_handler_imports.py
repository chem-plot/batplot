"""AST regression: interactive/batch menu loops must not call undefined handlers.

Catches NameError bugs like missing ``run_histo_y_range_menu`` imports before runtime.
"""

from __future__ import annotations

import ast
import builtins
import importlib
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

# (path relative to repo root, main menu function, handler name prefixes)
MENU_MODULES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "batplot/plot_modes/histo/interactive.py",
        "histo_interactive_menu",
        ("run_histo_", "handle_", "_run_histo_"),
    ),
    (
        "batplot/plot_modes/batch_session/menu_histo.py",
        "run_histo_batch_menu",
        ("run_histo_", "run_batch_", "handle_"),
    ),
    (
        "batplot/plot_modes/batch_session/menu_xy.py",
        "run_xy_batch_menu",
        ("run_xy_", "run_x_", "run_y_", "run_batch_", "handle_"),
    ),
    (
        "batplot/plot_modes/batch_session/menu_ec.py",
        "run_ec_batch_menu",
        ("run_batch_", "handle_"),
    ),
    (
        "batplot/plot_modes/batch_session/menu_cpc.py",
        "run_cpc_batch_menu",
        ("run_batch_", "handle_"),
    ),
    (
        "batplot/plot_modes/batch_session/menu_operando.py",
        "run_operando_batch_menu",
        ("run_batch_", "handle_"),
    ),
    (
        "batplot/plot_modes/xy/interactive.py",
        "interactive_menu",
        ("run_", "handle_"),
    ),
    (
        "batplot/plot_modes/electrochem/interactive.py",
        "electrochem_interactive_menu",
        ("run_", "handle_", "_handle_"),
    ),
    (
        "batplot/plot_modes/cpc/interactive.py",
        "cpc_interactive_menu",
        ("run_", "handle_", "_handle_", "_run_"),
    ),
    (
        "batplot/plot_modes/operando/interactive.py",
        "operando_ec_interactive_menu",
        ("run_", "handle_", "_handle_", "_run_"),
    ),
]

HELPER_MODULES: list[tuple[str, tuple[str, ...]]] = [
    ("batplot/plot_modes/batch_session/histo_batch_helpers.py", ("run_batch_",)),
    ("batplot/plot_modes/batch_session/xy_batch_helpers.py", ("run_xy_", "run_batch_")),
    ("batplot/plot_modes/batch_session/batch_io.py", ("run_batch_",)),
    ("batplot/plot_modes/histo/y_range.py", ("run_histo_",)),
]

IMPORT_SMOKE_MODULES = [
    "batplot.plot_modes.histo.interactive",
    "batplot.plot_modes.batch_session.menu_histo",
    "batplot.plot_modes.batch_session.menu_xy",
    "batplot.plot_modes.batch_session.menu_ec",
    "batplot.plot_modes.batch_session.menu_cpc",
    "batplot.plot_modes.batch_session.menu_operando",
    "batplot.plot_modes.batch_session.histo_batch_helpers",
    "batplot.plot_modes.batch_session.xy_batch_helpers",
    "batplot.plot_modes.batch_session.batch_io",
    "batplot.plot_modes.batch_session.batch_menu_io",
    "batplot.plot_modes.histo.y_range",
    "batplot.plot_modes.xy.interactive",
    "batplot.plot_modes.electrochem.interactive",
    "batplot.plot_modes.cpc.interactive",
    "batplot.plot_modes.operando.interactive",
]


def _module_scope_names(tree: ast.Module) -> set[str]:
    names: set[str] = set(dir(builtins))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _names_defined_in_subtree(root: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(root):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def _handler_calls_in_function(
    menu_fn: ast.FunctionDef,
    prefixes: Iterable[str],
) -> set[str]:
    local_names = _names_defined_in_subtree(menu_fn)
    called: set[str] = set()
    for node in ast.walk(menu_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Name):
            continue
        if not any(func.id.startswith(prefix) for prefix in prefixes):
            continue
        if func.id in local_names:
            continue
        called.add(func.id)
    return called


def _undefined_handlers(source_path: Path, menu_fn_name: str, prefixes: tuple[str, ...]) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    module_names = _module_scope_names(tree)
    menu_fn = _find_function(tree, menu_fn_name)
    called = _handler_calls_in_function(menu_fn, prefixes)
    return sorted(called - module_names)


def _undefined_handlers_in_module(source_path: Path, prefixes: tuple[str, ...]) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    module_names = _module_scope_names(tree)
    called: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            called |= _handler_calls_in_function(node, prefixes)
    return sorted(called - module_names)


def test_all_interactive_and_batch_menu_handlers_are_imported():
    failures: list[str] = []
    for rel_path, menu_fn, prefixes in MENU_MODULES:
        path = REPO_ROOT / rel_path
        missing = _undefined_handlers(path, menu_fn, prefixes)
        if missing:
            failures.append(f"{rel_path}::{menu_fn} undefined handlers: {missing}")
    assert not failures, "\n".join(failures)


def test_batch_helper_modules_handlers_are_imported():
    failures: list[str] = []
    for rel_path, prefixes in HELPER_MODULES:
        path = REPO_ROOT / rel_path
        missing = _undefined_handlers_in_module(path, prefixes)
        if missing:
            failures.append(f"{rel_path} undefined handlers: {missing}")
    assert not failures, "\n".join(failures)


def test_menu_modules_import_cleanly():
    for module_name in IMPORT_SMOKE_MODULES:
        importlib.import_module(module_name)


def test_histo_y_range_handler_exported_in_single_and_batch():
    from batplot.plot_modes.histo.interactive import run_histo_y_range_menu as single_fn
    from batplot.plot_modes.batch_session import menu_histo

    assert callable(single_fn)
    assert callable(menu_histo.run_histo_y_range_menu)
    assert single_fn is menu_histo.run_histo_y_range_menu
