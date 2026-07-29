"""1D XY plot round-trip tests: dump->load and export->import.

Guards against regressions such as:
* full (untrimmed) ``.raw``/``.brml`` data being lost after save/load,
* custom tick spacing / minor-tick locators not being restored on load.
"""

import sys
import pickle
import json
from types import SimpleNamespace

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, AutoMinorLocator

from batplot import session as S
from batplot import style as ST
from conftest import assert_allclose, loaded


def _build_xy_figure(display_lo=20.0, display_hi=40.0):
    """A figure whose displayed window is a *subset* of the full data."""
    x_full = np.linspace(0.0, 100.0, 1001)
    y_full = np.sin(x_full)
    mask = (x_full >= display_lo) & (x_full <= display_hi)
    x_disp, y_disp = x_full[mask], y_full[mask]
    fig, ax = plt.subplots()
    ax.plot(x_disp, y_disp, label="c1")
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    ax.set_xlim(display_lo, display_hi)
    return fig, ax, x_full, y_full, x_disp, y_disp


def _dump_xy(path, fig, ax, x_disp, y_disp, x_full, y_full, args):
    S.dump_session(
        path, fig=fig, ax=ax,
        x_data_list=[x_disp], y_data_list=[y_disp], orig_y=[y_disp],
        x_full_list=[x_full], raw_y_full_list=[y_full],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=args,
        tick_state={}, skip_confirm=True,
    )


def test_load_xy_session_menu_kwargs_match_interactive_menu(session_path, fake_args):
    """Regression: menu_kwargs keys must match interactive_menu (BM30.pkl class of bug)."""
    import inspect
    from batplot.plot_modes.xy.interactive import interactive_menu, normalize_xy_menu_kwargs

    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    p = session_path("xy_menu_kwargs.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    _, _, mk = loaded(S.load_xy_session(p))
    assert "labels_list" not in mk
    assert "labels" in mk

    params = inspect.signature(interactive_menu).parameters
    allowed = set(params.keys())
    normalized = normalize_xy_menu_kwargs(mk)
    assert set(normalized.keys()).issubset(allowed)

    called = {}

    def _probe(*args, **kwargs):
        called["labels"] = kwargs.get("labels")
        called["n_curves"] = len(kwargs.get("y_data_list", []))

    import batplot.plot_modes.xy.interactive as XI
    orig = XI.interactive_menu
    XI.interactive_menu = _probe
    try:
        fig2, ax2, mk2 = loaded(S.load_xy_session(p))
        XI.interactive_menu(fig2, ax2, **normalize_xy_menu_kwargs(mk2))
    finally:
        XI.interactive_menu = orig

    assert called["labels"] == ["c1"]
    assert called["n_curves"] == 1


def test_dump_load_preserves_full_untrimmed_data(session_path, fake_args):
    """Expanding the x-range after reload must recover ALL data, not the crop."""
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    p = session_path("xy_full.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    _, _, mk = loaded(S.load_xy_session(p))
    xfl = mk["x_full_list"]
    yfl = mk["raw_y_full_list"]

    assert xfl[0].size == x_full.size, "full x data was trimmed on reload"
    assert yfl[0].size == y_full.size, "full y data was trimmed on reload"
    assert_allclose(xfl[0].min(), 0.0)
    assert_allclose(xfl[0].max(), 100.0)


def test_x_range_expand_after_reload_uses_full_data_not_crop(session_path, fake_args):
    """Regression (XRD.pkl class): expanding X after .pkl reload must use x_full_data.

    Session load restores ``_original_x_data_list`` as a full-data backup. The X
    menu must NOT treat that alone as "processed" and re-slice from the cropped
    displayed window (which permanently drops points outside the saved viewport).
    """
    from batplot.plot_modes.xy.axis_range import run_x_range_menu

    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure(20.0, 40.0)
    # Mimic a prior save that persisted original_* alongside x_full_data
    fig._original_x_data_list = [np.array(x_full, copy=True)]
    fig._original_y_data_list = [np.array(y_full, copy=True)]
    p = session_path("xy_xrange_expand.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    fig2, ax2, mk = loaded(S.load_xy_session(p))
    assert hasattr(fig2, "_original_x_data_list")
    assert mk["x_data_list"][0].size == x_disp.size

    inputs = iter(["10 90", "q"])

    def _safe_input(_prompt=""):
        return next(inputs)

    run_x_range_menu(
        args=mk["args"],
        ax=ax2,
        fig=fig2,
        labels=mk["labels"],
        label_text_objects=mk.get("label_text_objects") or [],
        x_data_list=mk["x_data_list"],
        y_data_list=mk["y_data_list"],
        orig_y=mk["orig_y"],
        offsets_list=mk["offsets_list"],
        x_full_list=mk["x_full_list"],
        raw_y_full_list=mk["raw_y_full_list"],
        push_state=lambda *_a, **_k: None,
        _safe_input=_safe_input,
        _line=lambda i: ax2.lines[i],
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )

    expanded = mk["x_data_list"][0]
    assert expanded.size > x_disp.size, "X expand after reload stayed on cropped window"
    assert abs(float(expanded.min()) - 10.0) < 0.15
    assert abs(float(expanded.max()) - 90.0) < 0.15


def test_cli_pkl_shortcut_preserves_full_untrimmed_data(session_path, fake_args, monkeypatch):
    """The top-level `batplot session.pkl` path must use the full-data-aware loader."""
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    p = session_path("xy_cli_full.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    class _Args(SimpleNamespace):
        def __getattr__(self, _name):
            return None

    import batplot.batplot as BP
    import batplot.plot_modes.session_routing as SR

    captured = {}

    def _fake_menu(_fig, _ax, **kwargs):
        captured["x_full_list"] = kwargs["x_full_list"]
        captured["raw_y_full_list"] = kwargs["raw_y_full_list"]

    monkeypatch.setattr(BP, "_bp_parse_args", lambda: _Args(files=[p], interactive=True, stack=False, delta=None))
    # The `.pkl` session route now lives in batplot.plot_modes.session_routing;
    # patch the interactive menu where it is actually invoked.
    monkeypatch.setattr(SR, "interactive_menu", _fake_menu)
    monkeypatch.setattr(BP.plt, "ion", lambda *a, **k: None)
    monkeypatch.setattr(BP.plt, "show", lambda *a, **k: None)

    try:
        BP.batplot_main()
    except SystemExit as exc:
        assert exc.code in (None, 0)

    assert captured["x_full_list"][0].size == x_full.size
    assert captured["raw_y_full_list"][0].size == y_full.size


def test_dump_load_preserves_axis_limits_and_labels(session_path, fake_args):
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    p = session_path("xy_axes.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    fig2, ax2, _ = loaded(S.load_xy_session(p))
    assert_allclose(ax2.get_xlim(), (20.0, 40.0))
    assert ax2.get_xlabel() == "Two theta"
    assert ax2.get_ylabel() == "Intensity"


def test_xy_session_schema_kind_and_legacy_no_kind_load(session_path, fake_args):
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    p = session_path("xy_schema.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    with open(p, "rb") as fh:
        payload = pickle.load(fh)
    assert payload["kind"] == "xy"
    assert payload["version"] >= 3

    legacy = dict(payload)
    legacy.pop("kind", None)
    legacy_path = session_path("xy_legacy_no_kind.pkl")
    with open(legacy_path, "wb") as fh:
        pickle.dump(legacy, fh)

    assert S.load_xy_session(legacy_path) is not None


def test_dump_load_preserves_tick_spacing(session_path, fake_args):
    """Regression: custom MultipleLocator/minor locator must survive save+load."""
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    ax.xaxis.set_major_locator(MultipleLocator(0.5))
    ax.xaxis.set_minor_locator(AutoMinorLocator(4))
    p = session_path("xy_ticks.pkl")
    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)

    fig2, ax2, _ = loaded(S.load_xy_session(p))
    assert type(ax2.xaxis.get_major_locator()).__name__ == "MultipleLocator", (
        "custom tick spacing (t->n) was lost on reload"
    )


def test_dump_load_preserves_title_offsets(session_path, fake_args):
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    ax._top_xlabel_manual_offset_y_pts = 3.0
    ax._top_xlabel_manual_offset_x_pts = 1.0
    ax._bottom_xlabel_manual_offset_y_pts = -2.0
    ax._left_ylabel_manual_offset_x_pts = -4.0
    ax._right_ylabel_manual_offset_x_pts = 5.0
    ax._right_ylabel_manual_offset_y_pts = 1.5
    p = session_path("xy_title_offsets.pkl")

    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)
    fig2, ax2, _ = loaded(S.load_xy_session(p))

    assert ax2._top_xlabel_manual_offset_y_pts == 3.0
    assert ax2._top_xlabel_manual_offset_x_pts == 1.0
    assert ax2._bottom_xlabel_manual_offset_y_pts == -2.0
    assert ax2._left_ylabel_manual_offset_x_pts == -4.0
    assert ax2._right_ylabel_manual_offset_x_pts == 5.0
    assert ax2._right_ylabel_manual_offset_y_pts == 1.5


def test_dump_load_preserves_mathtext_fontset(session_path, fake_args):
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    plt.rcParams["mathtext.fontset"] = "stix"
    p = session_path("xy_mathtext.pkl")

    _dump_xy(p, fig, ax, x_disp, y_disp, x_full, y_full, fake_args)
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    S.load_xy_session(p)

    assert plt.rcParams["mathtext.fontset"] == "stix"


def test_export_import_preserves_style(session_path, fake_args):
    """A .bpsg style+geometry file applied to a fresh figure restores style."""
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    ax.set_xlabel("XLAB")
    ax.set_ylabel("YLAB")
    ax.set_xlim(1.0, 9.0)
    ax.grid(True)
    plt.rcParams["font.size"] = 17.0
    plt.rcParams["mathtext.fontset"] = "stix"
    main_mod = sys.modules["__main__"]
    setattr(main_mod, "show_cif_hkl", True)
    setattr(main_mod, "cif_set_visible", [True, False])
    cif_series = [
        ("phase a", "a.cif", [1.0], None, 5.0, "#ff0000"),
        ("phase b", "b.cif", [2.0], None, 5.0, "#0000ff"),
    ]

    style_file = session_path("style.bpsg")
    out = ST.export_style_config(
        style_file, fig, ax, [y_disp], ["renamed"], 0.0, fake_args, {}, [0.0],
        cif_tick_series=cif_series, show_cif_titles=False,
        overwrite_path=style_file, force_kind="psg",
    )
    assert out and out.endswith(".bpsg")
    with open(style_file, "r", encoding="utf-8") as fh:
        exported_cfg = json.load(fh)
    assert exported_cfg["kind"] == "xy_style_geom"
    assert exported_cfg["version"] >= 2

    # Fresh figure with default style; importing must pull the saved values in.
    plt.rcParams["font.size"] = 10.0
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    setattr(main_mod, "show_cif_hkl", False)
    setattr(main_mod, "cif_set_visible", [False, False])
    fig2, ax2 = plt.subplots()
    ax2.plot(x_disp, y_disp, label="c1")
    label_text = ax2.text(0.0, 0.0, "1: c1")
    imported_labels = ["c1"]
    imported_cif = [
        ("old a", "a.cif", [1.0], None, 5.0, "#111111"),
        ("old b", "b.cif", [2.0], None, 5.0, "#222222"),
    ]
    ST.apply_style_config(
        style_file, fig2, ax2, [x_disp], [y_disp], [y_disp], [0.0], [label_text], fake_args,
        {}, imported_labels, update_labels_func=lambda *a, **k: None,
        cif_tick_series=imported_cif,
    )
    assert plt.rcParams["font.size"] == 17.0, "font size not applied on import"
    assert plt.rcParams["mathtext.fontset"] == "stix"
    assert_allclose(ax2.get_xlim(), (1.0, 9.0), "geometry xlim not applied on import")
    assert any(line.get_visible() for line in ax2.get_xgridlines() + ax2.get_ygridlines())
    assert imported_labels == ["renamed"]
    assert label_text.get_text() == "1: renamed"
    assert imported_cif[0][0] == "phase a"
    assert imported_cif[1][-1] == "#0000ff"
    assert main_mod.show_cif_hkl is True
    assert main_mod.cif_set_visible == [True, False]
