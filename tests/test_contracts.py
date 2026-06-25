"""Signature / API contract tests.

These are cheap guards against the class of bug where an internal helper is
called with the wrong arguments or where a serialized dict key diverges from
what the importer reads (e.g. the CPC ``ops``/``opsg`` overwrite once called
``_style_snapshot`` with a stale signature and wrote geometry under the wrong
key).
"""

import inspect
import importlib
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot import session as S


def test_session_dump_load_functions_exist():
    for name in ("dump_session", "load_xy_session",
                 "dump_ec_session", "load_ec_session",
                 "dump_cpc_session", "load_cpc_session",
                 "dump_operando_session", "load_operando_session"):
        assert callable(getattr(S, name, None)), f"session.{name} missing"


def test_session_facade_delegates_to_per_mode_modules(monkeypatch):
    checks = {
        "batplot.plot_modes.xy.session": ("dump_session", "load_xy_session"),
        "batplot.plot_modes.electrochem.session": ("dump_ec_session", "load_ec_session"),
        "batplot.plot_modes.cpc.session": ("dump_cpc_session", "load_cpc_session"),
        "batplot.plot_modes.operando.session": ("dump_operando_session", "load_operando_session"),
    }

    for module_name, names in checks.items():
        module = importlib.import_module(module_name)
        for name in names:
            assert callable(getattr(module, name))
            calls = []

            def _fake(*args, **kwargs):
                calls.append((args, kwargs))
                return f"{module_name}:{name}"

            monkeypatch.setattr(module, name, _fake)
            assert getattr(S, name)("sentinel", flag=True) == f"{module_name}:{name}"
            assert calls == [(("sentinel",), {"flag": True})]


def test_session_facade_preserves_public_signatures():
    pairs = (
        ("dump_session", "_dump_session_impl"),
        ("load_xy_session", "_load_xy_session_impl"),
        ("dump_ec_session", "_dump_ec_session_impl"),
        ("load_ec_session", "_load_ec_session_impl"),
        ("dump_cpc_session", "_dump_cpc_session_impl"),
        ("load_cpc_session", "_load_cpc_session_impl"),
        ("dump_operando_session", "_dump_operando_session_impl"),
        ("load_operando_session", "_load_operando_session_impl"),
    )

    for public_name, impl_name in pairs:
        assert inspect.signature(getattr(S, public_name)) == inspect.signature(getattr(S, impl_name))


def test_legacy_mode_import_paths_still_work():
    """Old public-ish mode module paths should remain importable after reorg."""
    checks = {
        "batplot.interactive": "interactive_menu",
        "batplot.electrochem_interactive": "electrochem_interactive_menu",
        "batplot.cpc_interactive": "cpc_interactive_menu",
        "batplot.operando_ec_interactive": "operando_ec_interactive_menu",
        "batplot.cpc_menu": "print_cpc_menu",
        "batplot.operando_menu": "print_operando_ec_menu",
        "batplot.operando_layout": "_draw_custom_colorbar",
        "batplot.operando_style": "build_operando_ec_style_config_v2",
        "batplot.interactive_state": "build_saved_tick_state",
    }

    for module_name, symbol in checks.items():
        module = importlib.import_module(module_name)
        assert callable(getattr(module, symbol, None)), f"{module_name}.{symbol} missing"


def test_root_style_module_is_xy_compatibility_shim():
    root_style = importlib.import_module("batplot.style")
    xy_style = importlib.import_module("batplot.plot_modes.xy.style")

    for name in ("print_style_info", "export_style_config", "apply_style_config"):
        assert getattr(root_style, name) is getattr(xy_style, name)

    assert getattr(root_style, "_color_to_hex") is getattr(xy_style, "_color_to_hex")


def test_stale_modes_module_is_compatibility_only():
    module = importlib.import_module("batplot.modes")

    assert callable(module.handle_cv_mode)
    assert callable(module.handle_gc_mode)
    module_file = module.__file__
    assert module_file is not None
    source = Path(module_file).read_text(encoding="utf-8")
    assert "compatibility wrapper" in source
    assert "read_mpt_file" not in source
    with pytest.raises(RuntimeError):
        module.handle_gc_mode(object())


def test_manual_entrypoint_removed_and_flag_opens_pdf(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    manifest = (root / "MANIFEST.in").read_text(encoding="utf-8")
    assert "batplot-manual" not in pyproject
    assert "include-package-data = false" in pyproject
    assert "recursive-include batplot/data *.md" not in manifest
    assert "exclude batplot/data/USER_MANUAL.md" in manifest

    opened = {}

    def _fake_open(url):
        opened["url"] = url
        return True

    monkeypatch.setattr("webbrowser.open", _fake_open)
    from batplot.args import parse_args

    with pytest.raises(SystemExit) as exc:
        parse_args(["--manual"])

    assert exc.value.code == 0
    assert opened["url"].endswith("batplot_user_manual.pdf")


def test_legacy_operando_ec_exports_layout_helpers():
    module = importlib.import_module("batplot.operando_ec_interactive")

    assert callable(getattr(module, "_draw_custom_colorbar", None))
    assert callable(getattr(module, "_ensure_fixed_params", None))
    assert callable(getattr(module, "build_operando_ec_style_config_v2", None))


def test_title_offset_handler_is_only_wired_when_defined():
    """Prevent runtime NameError in shared `t` menus from missing callbacks."""
    root = Path(__file__).resolve().parents[1]
    for relpath in (
        "batplot/plot_modes/xy/interactive.py",
        "batplot/plot_modes/electrochem/interactive.py",
        "batplot/plot_modes/cpc/interactive.py",
        "batplot/plot_modes/operando/interactive.py",
    ):
        source = (root / relpath).read_text(encoding="utf-8")
        if "title_offset_handler=_title_offset_menu" in source:
            assert "def _title_offset_menu" in source, relpath


def test_cpc_style_snapshot_signature():
    """CPC `_style_snapshot` must keep its (fig, ax, ax2, sc_*, file_data) shape."""
    from batplot.plot_modes.cpc import interactive as C

    params = list(inspect.signature(C._style_snapshot).parameters)
    assert params[:6] == [
        "fig", "ax", "ax2", "sc_charge", "sc_discharge", "sc_eff",
    ], f"unexpected _style_snapshot signature: {params}"


def test_cpc_geometry_snapshot_signature():
    from batplot.plot_modes.cpc import interactive as C

    params = list(inspect.signature(C._get_geometry_snapshot).parameters)
    assert params[:2] == ["ax", "ax2"], (
        f"CPC _get_geometry_snapshot must take (ax, ax2); got {params}"
    )


def test_ec_snapshot_helpers_exist():
    from batplot.plot_modes.electrochem import interactive as E

    assert callable(getattr(E, "_get_style_snapshot", None))
    assert callable(getattr(E, "_get_geometry_snapshot", None))
    params = list(inspect.signature(E._get_geometry_snapshot).parameters)
    assert params[:2] == ["fig", "ax"], (
        f"EC _get_geometry_snapshot must take (fig, ax); got {params}"
    )


def test_ec_style_geom_snapshot_uses_importer_geometry_key():
    """EC style+geometry configs must use `geometry`, not `axes_geometry`."""
    from batplot.plot_modes.electrochem import interactive as E

    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 100.0, 20)
    volt = np.linspace(3.0, 4.2, 20)
    charge, = ax.plot(cap, volt, label="charge")
    discharge, = ax.plot(cap[::-1], volt, label="discharge")
    ax.set_xlabel("Capacity")
    ax.set_ylabel("Voltage")
    ax.set_xlim(0.0, 100.0)
    ax.set_ylim(3.0, 4.2)

    cfg = E._get_style_snapshot(
        fig, ax, {1: {"charge": charge, "discharge": discharge}}, tick_state={}
    )
    cfg["kind"] = "ec_style_geom"
    cfg["geometry"] = E._get_geometry_snapshot(fig, ax)

    assert "geometry" in cfg, "EC .bpsg importer reads cfg['geometry']"
    assert "axes_geometry" not in cfg, "stale key would be ignored by EC importer"
    assert cfg["geometry"]["xlabel"] == "Capacity"
    assert cfg["geometry"]["ylabel"] == "Voltage"


def test_cpc_style_geom_snapshot_uses_current_helper_contract():
    """CPC style+geometry snapshot must be buildable with current helper APIs."""
    from batplot.plot_modes.cpc import interactive as C

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    cycles = np.arange(1, 6, dtype=float)
    sc_charge = ax.scatter(cycles, np.linspace(150.0, 140.0, cycles.size), c="red")
    sc_discharge = ax.scatter(cycles, np.linspace(148.0, 138.0, cycles.size), c="blue")
    sc_eff = ax2.scatter(cycles, np.linspace(95.0, 99.0, cycles.size), c="green")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity")
    ax2.set_ylabel("Efficiency")
    ax.set_xlim(0.0, 6.0)

    cfg = C._style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff)
    cfg["kind"] = "cpc_style_geom"
    cfg["geometry"] = C._get_geometry_snapshot(ax, ax2)

    assert "geometry" in cfg, "CPC .bpsg importer reads cfg['geometry']"
    assert "axes_geometry" not in cfg, "stale key would be ignored by CPC importer"
    assert cfg["geometry"]["xlabel"] == "Cycle"
    assert cfg["geometry"]["ylabel_left"] == "Capacity"
    assert cfg["geometry"]["ylabel_right"] == "Efficiency"


def test_cpc_menu_redraws_keep_figure_context():
    root = Path(__file__).resolve().parents[1]
    for relpath in (
        "batplot/plot_modes/cpc/actions.py",
        "batplot/plot_modes/cpc/interactive.py",
    ):
        source = (root / relpath).read_text(encoding="utf-8")
        assert "_print_menu()" not in source, relpath


def test_quick_overwrite_commands_are_action_handlers():
    """Keep oe/os/ops/opsg out of mode menu loops so they share action code."""
    root = Path(__file__).resolve().parents[1]
    checks = {
        "electrochem": ("key", "ec_actions", "_command"),
        "cpc": ("key", "action_ctx", ""),
        "operando": ("cmd", "_make_action_context()", ""),
    }

    for mode, (command_var, ctx_expr, suffix) in checks.items():
        interactive = root / "batplot" / "plot_modes" / mode / "interactive.py"
        actions = root / "batplot" / "plot_modes" / mode / "actions.py"
        interactive_source = interactive.read_text(encoding="utf-8")
        actions_source = actions.read_text(encoding="utf-8")

        assert f"handle_quick_overwrite_figure{suffix}" in actions_source, mode
        assert f"handle_quick_overwrite_session{suffix}" in actions_source, mode
        assert f"handle_quick_overwrite_style{suffix}" in actions_source, mode
        assert f"elif {command_var} == 'oe':" in interactive_source, mode
        assert f"handle_quick_overwrite_figure{suffix}({ctx_expr}" in interactive_source, mode
        assert f"elif {command_var} == 'os':" in interactive_source, mode
        assert f"handle_quick_overwrite_session{suffix}({ctx_expr}" in interactive_source, mode
        assert f"elif {command_var} in ('ops', 'opsg'):" in interactive_source, mode
        assert f"handle_quick_overwrite_style{suffix}({ctx_expr}" in interactive_source, mode


def test_quick_overwrite_style_uses_canonical_builders():
    root = Path(__file__).resolve().parents[1]
    expected = {
        "electrochem": "_build_ec_style_export_config(ctx, exp_choice)",
        "cpc": "_build_cpc_style_export_config(ctx, exp_choice)",
        "operando": "_build_operando_ec_style_config_v2(ctx.fig, ctx.ax, ctx.im, ctx.cbar, ctx.ec_ax, exp_choice)",
    }

    for mode, builder_call in expected.items():
        source = (root / "batplot" / "plot_modes" / mode / "actions.py").read_text(encoding="utf-8")
        assert builder_call in source, mode


def _dispatch_keys_from_source(path: Path, variable: str) -> set[str]:
    source = path.read_text(encoding="utf-8")
    keys = set(re.findall(rf"(?:if|elif) {variable} == '([^']+)'", source))
    for match in re.findall(rf"(?:if|elif) {variable} in \(([^)]*)\)", source):
        keys.update(re.findall(r"'([^']+)'", match))
    return keys


def test_menu_command_specs_match_dispatch_keys():
    class FigureState:
        _last_session_save_path = "last.pkl"
        _last_style_export_path = "last.bps"
        _last_figure_export_path = "last.svg"
        _cpc_is_multi_file = True

    root = Path(__file__).resolve().parents[1]

    from batplot.plot_modes.electrochem.menu import electrochem_menu_command_keys
    from batplot.plot_modes.cpc.menu import cpc_menu_command_keys
    from batplot.plot_modes.operando.menu import operando_ec_menu_command_keys

    checks = [
        (
            electrochem_menu_command_keys(
                1, is_dqdv=True, fig=FigureState(), is_multi_file=True, canvas_mode=False
            ),
            _dispatch_keys_from_source(
                root / "batplot/plot_modes/electrochem/interactive.py", "key"
            ),
            "electrochem",
        ),
        (
            cpc_menu_command_keys(FigureState()),
            _dispatch_keys_from_source(root / "batplot/plot_modes/cpc/interactive.py", "key"),
            "cpc",
        ),
        (
            operando_ec_menu_command_keys(FigureState(), ec_ax=object()),
            _dispatch_keys_from_source(root / "batplot/plot_modes/operando/interactive.py", "cmd"),
            "operando",
        ),
    ]

    for printed_keys, dispatch_keys, mode in checks:
        missing = printed_keys - dispatch_keys
        assert not missing, f"{mode} menu prints unhandled commands: {sorted(missing)}"


def test_args_parser_keeps_core_flag_destinations():
    from batplot.args import build_parser

    args = build_parser().parse_args([
        "file.xy",
        "--gc",
        "--mass",
        "0.01g",
        "--format",
        "png",
        "--canvas",
    ])

    assert args.files == ["file.xy"]
    assert args.gc is True
    assert args.mass == [10.0]
    assert args.format == "png"
    assert args.canvas is True


def test_electrochem_modes_share_default_plot_and_canvas_size():
    from batplot import batplot as BP

    ec_w, ec_h = BP._default_ec_figsize()
    cpc_w, cpc_h = BP._default_cpc_figsize()

    assert (ec_w, ec_h) == pytest.approx((cpc_w, cpc_h))
    assert (ec_w, ec_h) == pytest.approx(BP._EC_DEFAULT_FIGSIZE)
    assert BP._CPC_DEFAULT_LAYOUT is BP._EC_DEFAULT_LAYOUT

    layout = BP._EC_DEFAULT_LAYOUT
    frame = (
        ec_w * (layout["right"] - layout["left"]),
        ec_h * (layout["top"] - layout["bottom"]),
    )
    assert frame == pytest.approx(BP._EC_DEFAULT_FRAME_SIZE)


def test_parse_args_keeps_short_aliases_and_dynamic_readcol():
    from batplot.args import parse_args

    args = parse_args([
        "left.xy",
        "--ry",
        "data.afes",
        "-i",
        "-r",
        "1",
        "2",
        "-o",
        "out.svg",
        "--readcolafes",
        "3",
        "4",
    ])

    assert args.files == ["left.xy", "data.afes"]
    assert args.interactive is True
    assert args.xrange == [1.0, 2.0]
    assert args.out == "out.svg"
    assert args.readcol_by_ext[".afes"] == [3, 4]
    assert args.right_y_indices == frozenset({0})
