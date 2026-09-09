"""Smoke-test operando interactive submenu helpers (quit immediately).

Regression guard for NameError / bad kwargs that crash the interactive menu
before any plot mutation (e.g. ``oc`` using an undefined ``colorize_prompt``).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.common.menus import run_axis_limit_menu, run_font_menu
from batplot.plot_modes.common.menu_rendering import colorize_menu
from batplot.plot_modes.common.terminal import colorize_prompt
from batplot.plot_modes.operando.colors import (
    run_operando_cif_color_menu,
    run_operando_colormap_menu,
)
from batplot.plot_modes.operando.grid import run_ec_grid_menu
from batplot.plot_modes.operando.labels import (
    run_operando_ec_rename_menu,
    run_operando_rename_menu,
)
from batplot.plot_modes.operando.line_style import run_ec_line_style_menu
from batplot.plot_modes.operando.peaks import run_peak_search_menu
from batplot.plot_modes.operando.visibility import run_visibility_menu


def _feed(*vals):
    it = iter(vals)

    def _in(_prompt=""):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _in


@pytest.fixture
def op_fig():
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(
        np.random.rand(8, 12), origin="lower", aspect="auto", extent=(1, 5, 0, 7)
    )
    cbar = fig.colorbar(im)
    ec_ax = fig.add_axes([0.78, 0.15, 0.12, 0.7])
    (line,) = ec_ax.plot([0, 1], [0, 1], color="C0")
    ec_ax._ec_line = line  # type: ignore[attr-defined]
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    fig._operando_wl = 0.709  # type: ignore[attr-defined]
    im._operando_cmap_name = "viridis"  # type: ignore[attr-defined]
    ax._operando_cif_tick_series = [  # type: ignore[attr-defined]
        ("phase1", "/tmp/a.cif", [1.0, 2.0], 0.709, 5.0, "#1f77b4"),
    ]
    ax._operando_cif_hkl_label_map = {}  # type: ignore[attr-defined]
    fig._operando_cif_y_positions = [0.1]  # type: ignore[attr-defined]
    yield fig, ax, im, cbar, ec_ax
    plt.close(fig)


def test_oc_colormap_menu_quit_and_apply(op_fig):
    fig, _ax, im, cbar, _ec = op_fig
    run_operando_colormap_menu(
        fig=fig,
        im=im,
        cbar=cbar,
        snapshot=lambda _n: None,
        update_custom_colorbar=lambda *_a, **_k: None,
        safe_input=_feed("q"),
        colorize_inline_commands=lambda s: s,
    )
    run_operando_colormap_menu(
        fig=fig,
        im=im,
        cbar=cbar,
        snapshot=lambda _n: None,
        update_custom_colorbar=lambda *_a, **_k: None,
        safe_input=_feed("plasma", "q"),
        colorize_inline_commands=lambda s: s,
    )
    assert getattr(im, "_operando_cmap_name", None) == "plasma"


def test_operando_submenu_helpers_accept_quit(op_fig):
    fig, ax, im, cbar, ec_ax = op_fig
    identity = lambda s: s

    run_operando_cif_color_menu(
        fig=fig,
        ax=ax,
        cif_series=list(ax._operando_cif_tick_series),
        safe_input=_feed("q"),
        push_state=lambda _n: None,
        redraw=lambda _s: None,
        colorize_prompt=colorize_prompt,
    )
    run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        snapshot=lambda _n: None,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=identity,
    )
    run_ec_line_style_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=lambda _n: None,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_ec_grid_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=lambda _n: None,
        safe_input=_feed("q"),
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=identity,
    )
    run_operando_rename_menu(
        fig=fig,
        ax=ax,
        snapshot=lambda _n: None,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_operando_ec_rename_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=lambda _n: None,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_peak_search_menu(
        im=im,
        file_paths=["/tmp/fake.npy"],
        print_menu=lambda: None,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_font_menu(
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        get_current_family=lambda: "Arial",
        get_current_size=lambda: 12,
        apply_family=lambda _f: None,
        apply_size=lambda _s: None,
    )
    run_axis_limit_menu(
        axis_name="X",
        prompt_name="X",
        get_limits=lambda: (0.0, 1.0),
        set_limits=lambda _a, _b: None,
        auto_limits=lambda: None,
        push_state=lambda _n: None,
        state_label="x",
        draw=lambda: None,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )


def test_ast_no_import_alias_bare_name_bugs():
    """Fail if a function imports ``X as _X`` but still references bare ``X``."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "batplot" / "plot_modes"
    issues: list[str] = []
    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in list(node.args.args) + list(node.args.kwonlyargs)}
            if node.args.vararg:
                params.add(node.args.vararg.arg)
            if node.args.kwarg:
                params.add(node.args.kwarg.arg)
            alias_map: dict[str, str] = {}
            imported_bound: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    for al in child.names:
                        bound = al.asname or al.name
                        imported_bound.add(bound)
                        if al.asname and al.asname != al.name:
                            alias_map[al.name] = al.asname
            used = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            }
            for original, alias in alias_map.items():
                if (
                    original in used
                    and original not in params
                    and original not in imported_bound
                ):
                    # Allow known safe fallback patterns in except branches
                    if path.name == "plot.py" and original == "_draw_custom_colorbar":
                        continue
                    issues.append(
                        f"{path.relative_to(root.parent.parent)}:{node.lineno} "
                        f"{node.name}: uses {original!r} but imported as {alias!r}"
                    )
    assert issues == [], "Import-alias NameError risks:\n" + "\n".join(issues)
