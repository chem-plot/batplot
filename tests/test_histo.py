"""Tests for histogram mode."""

from __future__ import annotations

import json

import numpy as np
import pytest

from batplot.plot_modes.histo.load import (
    TableData,
    auto_range,
    build_bin_edges,
    column_stats,
    load_table,
    resolve_column_index,
    suggest_bin_width,
)
from batplot.plot_modes.histo.colors import resolve_histo_color, histo_palette_options
from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.histo.interactive import (
    _restore_snapshot,
    _snapshot_for_json,
)


def test_load_table_csv(tmp_path):
    p = tmp_path / "sizes.csv"
    p.write_text(
        " ,Area,Mean,Min,Max,Angle,Length\n"
        "1,0.753,180.930,148.000,242.064,-41.186,11.289\n"
        "2,0.952,178.378,161.353,196.542,-38.577,14.263\n",
        encoding="utf-8",
    )
    table = load_table(str(p))
    assert table.ncols >= 7
    col = resolve_column_index(table, "Length")
    vals = table.column_values(col)
    assert vals.shape == (2,)
    assert vals[0] == pytest.approx(11.289)


def test_build_bin_edges_width():
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    assert edges[0] == 0.0
    assert edges[-1] >= 10.0
    assert np.all(np.diff(edges) == pytest.approx(2.0))


def test_suggest_bin_width_positive():
    w = suggest_bin_width(0.5, 16.0, 170)
    assert w > 0


def test_histo_setup_counts(tmp_path):
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, meta = create_histo_figure(state)
    assert int(np.sum(meta["counts"])) == len(values)
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_auto_range_expands():
    vals = np.array([1.0, 2.0, 3.0])
    xmin, xmax = auto_range(vals)
    assert xmin < 1.0
    assert xmax > 3.0


def test_column_stats():
    stats = column_stats(np.array([1.0, 2.0, 3.0]))
    assert stats["n"] == 3
    assert stats["mean"] == pytest.approx(2.0)


def test_histo_legacy_auto_title_stripped_on_restore():
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    snap = _snapshot_for_json(build_histo_state(setup, source_path="Length.csv"))
    snap["style"]["title"] = "Histogram Length"
    restored = _restore_snapshot(snap)
    assert restored.style.title == ""

    fig, ax, _meta = create_histo_figure(restored)
    assert ax.get_title() == ""
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_custom_title_preserved_on_restore():
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    snap = _snapshot_for_json(build_histo_state(setup, source_path="Length.csv"))
    snap["style"]["title"] = "Particle sizes"
    restored = _restore_snapshot(snap)
    assert restored.style.title == "Particle sizes"

    fig, ax, _meta = create_histo_figure(restored)
    assert ax.get_title() == "Particle sizes"
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_default_title_empty():
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    assert state.style.title == ""

    fig, ax, _meta = create_histo_figure(state)
    assert ax.get_title() == ""
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_style_snapshot_json_roundtrip(tmp_path):
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.bar_color = "#ff0000"
    state.style.edge_color = "#00aa00"
    state.style.font_family = "Arial"
    state.style.label_fontsize = 12.0
    snap = _snapshot_for_json(state)
    import json

    path = tmp_path / "style.bpsh"
    path.write_text(json.dumps(snap), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    restored = _restore_snapshot(loaded)
    assert restored.style.bar_color == "#ff0000"
    assert restored.style.edge_color == "#00aa00"
    assert restored.style.font_family == "Arial"
    assert restored.style.label_fontsize == pytest.approx(12.0)
    assert np.array_equal(restored.setup.values, values)


def test_histo_session_geometry_roundtrip(tmp_path):
    """Saved .pkl must restore the same plot-frame inches as the live session."""
    from batplot.plot_modes.histo.interactive import _save_session
    from batplot.plot_modes.histo.plot import sync_histo_geometry
    from batplot.plot_modes.histo.session import load_histo_session

    values = np.array([2.939, 7.46, 8.679, 19.79, 7.55, 8.365, 14.816, 19.018])
    edges = build_bin_edges(0.0, 20.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=7,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="Pirstine_size.csv")
    fig, ax, _meta = create_histo_figure(state)
    sync_histo_geometry(fig, ax, state)
    fw, fh = fig.get_size_inches()
    bbox = ax.get_position()
    frame_w_in = bbox.width * fw
    frame_h_in = bbox.height * fh

    pkl_path = tmp_path / "histo_geom.pkl"
    _save_session(fig, ax, state, str(pkl_path))

    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    bbox2 = ax2.get_position()
    fw2, fh2 = fig2.get_size_inches()
    assert fw2 == pytest.approx(fw)
    assert fh2 == pytest.approx(fh)
    assert bbox2.width * fw2 == pytest.approx(frame_w_in, abs=1e-3)
    assert bbox2.height * fh2 == pytest.approx(frame_h_in, abs=1e-3)
    assert state2.style.axes_fraction is not None
    assert state2.style.axes_fraction[2] == pytest.approx(bbox.width, abs=1e-6)

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def test_histo_geometry_snapshot_roundtrip(tmp_path):
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    fig.set_size_inches(9.0, 6.0, forward=True)
    ax.set_position([0.15, 0.12, 0.75, 0.78])
    from batplot.plot_modes.histo.plot import sync_histo_geometry

    sync_histo_geometry(fig, ax, state)
    snap = _snapshot_for_json(state)
    restored = _restore_snapshot(snap)
    assert restored.style.figsize == pytest.approx((9.0, 6.0))
    assert restored.style.axes_fraction is not None
    assert restored.style.axes_fraction[2] == pytest.approx(0.75)
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_resolve_histo_color_hex_and_palette():
    palette_opts = histo_palette_options()
    palette_index = {str(i): name for i, name in enumerate(palette_opts, 1)}
    assert resolve_histo_color("#ff0000", None, palette_index) == "#ff0000"
    assert resolve_histo_color("red", None, palette_index) == "red"
    pal_color = resolve_histo_color("viridis", None, palette_index)
    assert pal_color is not None
    assert pal_color.startswith("#")


def test_gaussian_kde_pdf_normalizes():
    from batplot.plot_modes.histo.density_curve import gaussian_kde_pdf

    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    x = np.linspace(0.0, 6.0, 100)
    pdf = gaussian_kde_pdf(x, data)
    dx = x[1] - x[0]
    integral = np.trapezoid(pdf, x) if hasattr(np, "trapezoid") else np.trapz(pdf, x)
    assert integral == pytest.approx(1.0, rel=0.15)


def test_density_curve_count_and_density_scaling():
    from batplot.plot_modes.histo.density_curve import density_curve_xy
    from batplot.plot_modes.histo.plot import HistoState, HistoStyle

    values = np.array([1.0, 2.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = HistoState(setup=setup, style=HistoStyle())
    count_curve = density_curve_xy(state, edges)
    assert count_curve is not None
    state.style.density = True
    density_curve = density_curve_xy(state, edges)
    assert density_curve is not None
    _, y_count = count_curve
    _, y_density = density_curve
    avg_width = float(np.mean(np.diff(edges)))
    assert np.max(y_count) == pytest.approx(np.max(y_density) * values.size * avg_width, rel=0.15)


def test_histo_density_curve_drawn():
    values = np.array([1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.show_density_curve = True
    fig, ax, meta = create_histo_figure(state)
    assert "density_curve" in meta
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_density_curve_snapshot_roundtrip():
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.show_density_curve = True
    state.style.density_curve_color = "#112233"
    state.style.density_curve_lw = 2.5
    snap = _snapshot_for_json(state)
    restored = _restore_snapshot(snap)
    assert restored.style.show_density_curve is True
    assert restored.style.density_curve_color == "#112233"
    assert restored.style.density_curve_lw == pytest.approx(2.5)


def test_histo_density_curve_style_export_import(tmp_path):
    from batplot.plot_modes.histo.interactive import _apply_style_file, _export_style
    from batplot.plot_modes.histo.plot import refresh_histo_figure

    values = np.array([1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.show_density_curve = True
    state.style.density_curve_color = "#aabbcc"
    fig, ax, meta = create_histo_figure(state)
    assert "density_curve" in meta

    style_path = tmp_path / "curve.bpsh"
    _export_style(fig, ax, state, str(style_path))
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "histo_style"
    assert payload["style"]["show_density_curve"] is True
    assert payload["style"]["density_curve_color"] == "#aabbcc"

    state.style.show_density_curve = False
    _apply_style_file(fig, ax, state, str(style_path))
    assert state.style.show_density_curve is True
    meta2 = refresh_histo_figure(fig, ax, state)
    assert "density_curve" in meta2

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_density_curve_session_roundtrip(tmp_path):
    from batplot.plot_modes.histo.interactive import _save_session
    from batplot.plot_modes.histo.session import load_histo_session

    values = np.array([1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.show_density_curve = True
    state.style.density_curve_ls = "--"
    fig, ax, _meta = create_histo_figure(state)
    pkl_path = tmp_path / "histo.pkl"
    _save_session(fig, ax, state, str(pkl_path))

    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    assert state2.style.show_density_curve is True
    assert state2.style.density_curve_ls == "--"
    from batplot.plot_modes.histo.plot import refresh_histo_figure

    meta = refresh_histo_figure(fig2, ax2, state2)
    assert "density_curve" in meta

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def test_histo_density_curve_undo_snapshot():
    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.session import apply_histo_snapshot, capture_histo_snapshot

    values = np.array([1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    snap_off = capture_histo_snapshot(state, fig, ax)
    state.style.show_density_curve = True
    snap_on = capture_histo_snapshot(state, fig, ax)

    apply_histo_snapshot(fig, ax, state, snap_off)
    assert state.style.show_density_curve is False
    meta_off = refresh_histo_figure(fig, ax, state)
    assert "density_curve" not in meta_off

    apply_histo_snapshot(fig, ax, state, snap_on)
    assert state.style.show_density_curve is True
    meta_on = refresh_histo_figure(fig, ax, state)
    assert "density_curve" in meta_on

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_bar_width_frac_snapshot_roundtrip():
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.bar_width_frac = 0.6
    snap = _snapshot_for_json(state)
    restored = _restore_snapshot(snap)
    assert restored.style.bar_width_frac == pytest.approx(0.6)

    fig, ax, meta = create_histo_figure(restored)
    bar = meta["bars"][0]
    bin_w = float(edges[1] - edges[0])
    assert bar.get_width() == pytest.approx(bin_w * 0.6)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_ylim_snapshot_roundtrip():
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.ylim = (0.0, 42.0)
    snap = _snapshot_for_json(state)
    restored = _restore_snapshot(snap)
    assert restored.style.ylim == pytest.approx((0.0, 42.0))

    fig, ax, _meta = create_histo_figure(restored)
    assert ax.get_ylim()[0] == pytest.approx(0.0)
    assert ax.get_ylim()[1] == pytest.approx(42.0)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_ylim_style_export_import(tmp_path):
    from batplot.plot_modes.histo.interactive import _apply_style_file, _export_style
    from batplot.plot_modes.histo.plot import refresh_histo_figure

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.ylim = (0.0, 25.0)
    fig, ax, _meta = create_histo_figure(state)
    style_path = tmp_path / "style.bpsh"
    _export_style(fig, ax, state, str(style_path))

    state.style.ylim = None
    refresh_histo_figure(fig, ax, state)
    assert ax.get_ylim()[1] != pytest.approx(25.0)

    _apply_style_file(fig, ax, state, str(style_path))
    assert state.style.ylim == pytest.approx((0.0, 25.0))
    assert ax.get_ylim()[1] == pytest.approx(25.0)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_ylim_undo_snapshot():
    from batplot.plot_modes.histo.session import apply_histo_snapshot, capture_histo_snapshot

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    snap_auto = capture_histo_snapshot(state, fig, ax)
    state.style.ylim = (0.0, 50.0)
    snap_fixed = capture_histo_snapshot(state, fig, ax)

    apply_histo_snapshot(fig, ax, state, snap_auto)
    assert state.style.ylim is None

    apply_histo_snapshot(fig, ax, state, snap_fixed)
    assert state.style.ylim == pytest.approx((0.0, 50.0))
    assert ax.get_ylim()[1] == pytest.approx(50.0)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_label_snapshot_roundtrip():
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.xlabel = "Size (µm)"
    state.style.ylabel = "Count"
    state.style.title = "Particle sizes"
    state.style.top_xlabel = "Length (µm)"
    snap = _snapshot_for_json(state)
    restored = _restore_snapshot(snap)
    assert restored.style.xlabel == "Size (µm)"
    assert restored.style.ylabel == "Count"
    assert restored.style.title == "Particle sizes"
    assert restored.style.top_xlabel == "Length (µm)"


def test_histo_session_header_accepted_by_session_routing(tmp_path):
    """``batplot histo.pkl`` must not reject histogram sessions for missing ``version``."""
    from batplot.plot_modes.session_routing import (
        _is_valid_session_header,
        _load_session_dict_with_diagnostics,
    )
    from batplot.plot_modes.histo.interactive import _save_session

    values = np.array([1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    pkl_path = tmp_path / "histo_p.pkl"
    _save_session(fig, ax, state, str(pkl_path))

    header, err = _load_session_dict_with_diagnostics(str(pkl_path))
    assert err is None
    assert header is not None
    assert header.get("kind") == "histo"
    assert header.get("version") == 1
    assert _is_valid_session_header(header) is True

    # Legacy histo files saved before version field must still reload.
    legacy = {"kind": "histo", "state": header["state"]}
    assert _is_valid_session_header(legacy) is True

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_tick_spacing_survives_refresh():
    from matplotlib.ticker import MultipleLocator

    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.spines import capture_histo_spine_snapshot

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    ax.yaxis.set_major_locator(MultipleLocator(20))
    snap = capture_histo_spine_snapshot(fig, ax)
    assert snap["tick_spacing"]["y_major_step"] == pytest.approx(20.0)

    refresh_histo_figure(fig, ax, state)
    loc = ax.yaxis.get_major_locator()
    assert isinstance(loc, MultipleLocator)
    assert float(loc._edge.step) == pytest.approx(20.0)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_tick_spacing_batch_sync():
    from matplotlib.ticker import MultipleLocator

    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.spines import persist_histo_spine_before_redraw

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state1 = build_histo_state(setup, source_path="test.csv")
    state2 = build_histo_state(setup, source_path="test.csv")
    fig1, ax1, _meta1 = create_histo_figure(state1)
    fig2, ax2, _meta2 = create_histo_figure(state2)
    ax1.yaxis.set_major_locator(MultipleLocator(20))
    persist_histo_spine_before_redraw(fig1, ax1, sync_targets=[(fig2, ax2)])
    refresh_histo_figure(fig1, ax1, state1)
    refresh_histo_figure(fig2, ax2, state2)

    for ax in (ax1, ax2):
        loc = ax.yaxis.get_major_locator()
        assert isinstance(loc, MultipleLocator)
        assert float(loc._edge.step) == pytest.approx(20.0)

    import matplotlib.pyplot as plt

    plt.close(fig1)
    plt.close(fig2)


def test_histo_tick_spacing_style_export_import(tmp_path):
    from matplotlib.ticker import MultipleLocator

    from batplot.plot_modes.histo.interactive import _apply_style_file, _export_style
    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.spines import capture_histo_spine_snapshot

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    capture_histo_spine_snapshot(fig, ax)
    style_path = tmp_path / "style.bpsh"
    _export_style(fig, ax, state, str(style_path))

    ax.xaxis.set_major_locator(MultipleLocator(5))
    capture_histo_spine_snapshot(fig, ax)
    refresh_histo_figure(fig, ax, state)
    assert float(ax.xaxis.get_major_locator()._edge.step) == pytest.approx(5.0)

    _apply_style_file(fig, ax, state, str(style_path))
    refresh_histo_figure(fig, ax, state)
    assert float(ax.xaxis.get_major_locator()._edge.step) == pytest.approx(2.0)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_spine_snapshot_roundtrip():
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    from batplot.plot_modes.histo.spines import capture_histo_spine_snapshot, apply_histo_spine_snapshot

    fig._histo_wasd_state = {  # type: ignore[attr-defined]
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "top": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
        "right": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    ax._saved_tick_state = {  # type: ignore[attr-defined]
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": False,
        "r_labels": False,
        "mbx": False,
        "mtx": False,
        "mly": False,
        "mry": False,
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
    }
    snap = capture_histo_spine_snapshot(fig, ax)
    payload = _snapshot_for_json(state, fig, ax)
    assert "wasd_state" in payload
    assert payload["wasd_state"]["bottom"]["spine"] is True
    restored = _restore_snapshot(payload)
    fig2, ax2, _ = create_histo_figure(restored)
    apply_histo_spine_snapshot(fig2, ax2, payload)
    snap2 = capture_histo_spine_snapshot(fig2, ax2)
    assert snap2["wasd_state"]["bottom"]["ticks"] == snap["wasd_state"]["bottom"]["ticks"]
    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def test_histo_spine_color_persists_through_refresh_and_pisb():
    from matplotlib import colors as mcolors

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.session import apply_histo_style_snapshot
    from batplot.plot_modes.histo.spines import (
        capture_histo_spine_snapshot,
        get_histo_spine_colors,
        set_histo_spine_color,
    )

    def _assert_left_white(target_ax) -> None:
        assert mcolors.to_hex(mcolors.to_rgb(target_ax.spines["left"].get_edgecolor())) == "#ffffff"
        assert mcolors.to_hex(mcolors.to_rgb(target_ax.yaxis.label.get_color())) == "#ffffff"
        for tick in target_ax.yaxis.get_major_ticks():
            lab = getattr(tick, "label1", None)
            if lab is not None and lab.get_visible():
                assert mcolors.to_hex(mcolors.to_rgb(lab.get_color())) == "#ffffff"
                break
            ln = getattr(tick, "tick1line", None)
            if ln is not None and ln.get_visible():
                assert mcolors.to_hex(mcolors.to_rgb(ln.get_color())) == "#ffffff"

    set_histo_spine_color(fig, ax, "left", "white")
    _assert_left_white(ax)
    fig.canvas.draw()
    from batplot.plot_modes.histo.spines import apply_histo_spine_colors

    apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig), only_sides={"left"})
    _assert_left_white(ax)
    refresh_histo_figure(fig, ax, state)
    assert get_histo_spine_colors(fig).get("left") == "#ffffff"
    _assert_left_white(ax)

    snap = capture_histo_spine_snapshot(fig, ax)
    assert snap.get("spine_colors", {}).get("left") == "#ffffff"

    state.style.bar_color = "#123456"
    style_payload = _snapshot_for_json(state, fig, ax)
    state2 = build_histo_state(setup, source_path="test.csv")
    fig2, ax2, _meta = create_histo_figure(state2)
    apply_histo_style_snapshot(fig2, ax2, state2, style_payload)
    assert get_histo_spine_colors(fig2).get("left") == "#ffffff"
    _assert_left_white(ax2)

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def _histo_y_grid_visible(ax) -> bool:
    return any(gl.get_visible() for gl in ax.get_ygridlines())


def test_histo_default_grid_off():
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup)
    assert state.style.show_grid is False
    fig, ax, _meta = create_histo_figure(state)
    assert _histo_y_grid_visible(ax) is False

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_grid_off_survives_refresh_spine_colors_and_batch_load(tmp_path):
    from batplot.plot_modes.histo.interactive import _save_session
    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.session import load_histo_session
    from batplot.plot_modes.histo.spines import apply_histo_spine_colors, get_histo_spine_colors, set_histo_spine_color

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.show_grid = False
    fig, ax, _meta = create_histo_figure(state)
    assert _histo_y_grid_visible(ax) is False

    set_histo_spine_color(fig, ax, "left", "red")
    apply_histo_spine_colors(fig, ax, get_histo_spine_colors(fig))
    fig.canvas.draw()
    assert _histo_y_grid_visible(ax) is False

    refresh_histo_figure(fig, ax, state)
    assert _histo_y_grid_visible(ax) is False

    pkl_path = tmp_path / "histo_no_grid.pkl"
    _save_session(fig, ax, state, str(pkl_path))
    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    assert state2.style.show_grid is False
    assert _histo_y_grid_visible(ax2) is False

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def test_histo_grid_pisb_roundtrip(tmp_path):
    from batplot.plot_modes.histo.interactive import _export_style, _save_session
    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.session import (
        apply_histo_snapshot,
        apply_histo_style_snapshot,
        capture_histo_snapshot,
        load_histo_session,
    )

    values = np.array([1.0, 2.0, 3.0, 4.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.show_grid = True
    fig, ax, _meta = create_histo_figure(state)
    assert _histo_y_grid_visible(ax) is True

    snap_on = capture_histo_snapshot(state, fig, ax)
    state.style.show_grid = False
    refresh_histo_figure(fig, ax, state)
    snap_off = capture_histo_snapshot(state, fig, ax)
    assert _histo_y_grid_visible(ax) is False

    apply_histo_snapshot(fig, ax, state, snap_on)
    assert state.style.show_grid is True
    assert _histo_y_grid_visible(ax) is True

    apply_histo_snapshot(fig, ax, state, snap_off)
    assert state.style.show_grid is False
    assert _histo_y_grid_visible(ax) is False

    style_path = tmp_path / "style.bpsh"
    _export_style(fig, ax, state, str(style_path))
    state2 = build_histo_state(setup, source_path="test.csv")
    state2.style.show_grid = True
    fig2, ax2, _meta = create_histo_figure(state2)
    apply_histo_style_snapshot(fig2, ax2, state2, json.loads(style_path.read_text(encoding="utf-8")))
    assert state2.style.show_grid is False
    assert _histo_y_grid_visible(ax2) is False

    pkl_path = tmp_path / "histo_grid.pkl"
    _save_session(fig, ax, state, str(pkl_path))
    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    _fig3, ax3, state3 = loaded
    assert state3.style.show_grid is False
    assert _histo_y_grid_visible(ax3) is False

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)
    plt.close(_fig3)


def test_histo_line_menu_grid_and_widths_pisb(tmp_path):
    from batplot.plot_modes.histo.interactive import _export_style, _save_session
    from batplot.plot_modes.histo.line_style import run_histo_line_style_menu
    from batplot.plot_modes.histo.plot import refresh_histo_figure
    from batplot.plot_modes.histo.session import (
        apply_histo_snapshot,
        apply_histo_style_snapshot,
        capture_histo_snapshot,
        load_histo_session,
    )

    values = np.array([1.0, 2.0, 3.0, 4.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    history: list = []

    def _push() -> None:
        history.append(capture_histo_snapshot(state, fig, ax))

    def _refresh() -> None:
        refresh_histo_figure(fig, ax, state)

    _push()
    state.style.show_grid = True
    state.style.grid_linewidth = 1.2
    _refresh()
    assert _histo_y_grid_visible(ax) is True

    snap_on = capture_histo_snapshot(state, fig, ax)
    assert snap_on["style"]["show_grid"] is True
    assert snap_on["style"]["grid_linewidth"] == pytest.approx(1.2)
    assert snap_on.get("tick_widths", {}).get("y_major") is not None

    state.style.show_grid = False
    _refresh()
    snap_off = capture_histo_snapshot(state, fig, ax)

    apply_histo_snapshot(fig, ax, state, snap_on)
    assert state.style.show_grid is True
    assert _histo_y_grid_visible(ax) is True

    apply_histo_snapshot(fig, ax, state, snap_off)
    assert state.style.show_grid is False
    assert _histo_y_grid_visible(ax) is False

    style_path = tmp_path / "style.bpsh"
    _export_style(fig, ax, state, str(style_path))
    state2 = build_histo_state(setup, source_path="test.csv")
    state2.style.show_grid = True
    fig2, ax2, _meta2 = create_histo_figure(state2)
    apply_histo_style_snapshot(fig2, ax2, state2, json.loads(style_path.read_text(encoding="utf-8")))
    assert state2.style.show_grid is False
    assert state2.style.grid_linewidth == pytest.approx(1.2)

    pkl_path = tmp_path / "histo_line.pkl"
    _save_session(fig, ax, state, str(pkl_path))
    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    _fig3, ax3, state3 = loaded
    assert state3.style.show_grid is False
    assert state3.style.grid_linewidth == pytest.approx(1.2)

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)
    plt.close(_fig3)


def _write_size_csv(path, length_values):
    rows = [" ,Area,Mean,Min,Max,Angle,Length"]
    for i, length in enumerate(length_values, start=1):
        rows.append(f"{i},0.75,180.0,148.0,242.0,-41.0,{length}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_histo_batch_export(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from batplot.batch import batch_process_histo

    monkeypatch.chdir(tmp_path)
    _write_size_csv(tmp_path / "a.csv", [11.0, 12.0, 13.0])
    _write_size_csv(tmp_path / "b.csv", [8.0, 9.5, 10.0])
    args = SimpleNamespace(
        histocol=7,
        readcol=None,
        xrange=None,
        binwidth=1.0,
        bins=None,
        all="all",
        format="svg",
    )
    batch_process_histo(str(tmp_path), args)
    out_dir = tmp_path / "Figures"
    assert out_dir.is_dir()
    exports = sorted(out_dir.glob("*_histo.svg"))
    assert len(exports) == 2


def test_histo_allfiles_routing_batch_export(tmp_path, monkeypatch):
    from batplot.cli import main

    monkeypatch.chdir(tmp_path)
    _write_size_csv(tmp_path / "sample1.csv", [11.0, 12.0])
    _write_size_csv(tmp_path / "sample2.csv", [8.0, 9.5])
    try:
        rc = main(["allfiles", "--histo", "--histocol", "7", "--binwidth", "1"])
    except SystemExit as exc:
        rc = exc.code
    assert rc in (0, None)
    exports = list((tmp_path / "Figures").glob("*_histo.svg"))
    assert len(exports) == 2


def test_histo_style_import_preserves_histogram_data(tmp_path):
    """Style import (i) must not replace each panel's values/setup."""
    from batplot.plot_modes.histo.interactive import _export_style
    from batplot.plot_modes.histo.session import apply_histo_style_snapshot

    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    values_a = np.array([1.0, 2.0, 3.0])
    values_b = np.array([8.0, 9.0, 9.5])
    setup_a = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values_a,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    setup_b = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values_b,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state_a = build_histo_state(setup_a, source_path="a.csv")
    state_b = build_histo_state(setup_b, source_path="b.csv")
    state_a.style.bar_color = "#ff0000"
    fig_a, ax_a, _meta_a = create_histo_figure(state_a)
    fig_b, ax_b, _meta_b = create_histo_figure(state_b)

    style_path = tmp_path / "style.bpsh"
    _export_style(fig_a, ax_a, state_a, str(style_path))

    apply_histo_style_snapshot(fig_b, ax_b, state_b, json.loads(style_path.read_text(encoding="utf-8")))
    assert state_b.style.bar_color == "#ff0000"
    assert np.array_equal(state_b.setup.values, values_b)
    assert state_b.source_path == "b.csv"

    import matplotlib.pyplot as plt

    plt.close(fig_a)
    plt.close(fig_b)


def test_histo_ylim_session_roundtrip(tmp_path):
    from batplot.plot_modes.histo.interactive import _save_session
    from batplot.plot_modes.histo.session import load_histo_session

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.ylim = (0.0, 33.0)
    fig, ax, _meta = create_histo_figure(state)
    pkl_path = tmp_path / "histo.pkl"
    _save_session(fig, ax, state, str(pkl_path))

    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    assert state2.style.ylim == pytest.approx((0.0, 33.0))
    assert ax2.get_ylim()[1] == pytest.approx(33.0)

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def test_histo_tick_spacing_session_roundtrip(tmp_path):
    from matplotlib.ticker import MultipleLocator

    from batplot.plot_modes.histo.interactive import _save_session
    from batplot.plot_modes.histo.session import load_histo_session
    from batplot.plot_modes.histo.spines import capture_histo_spine_snapshot

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    ax.yaxis.set_major_locator(MultipleLocator(20))
    capture_histo_spine_snapshot(fig, ax)
    pkl_path = tmp_path / "histo.pkl"
    _save_session(fig, ax, state, str(pkl_path))

    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    fig2, ax2, _state2 = loaded
    loc = ax2.yaxis.get_major_locator()
    assert isinstance(loc, MultipleLocator)
    assert float(loc._edge.step) == pytest.approx(20.0)

    import matplotlib.pyplot as plt

    plt.close(fig)
    plt.close(fig2)


def test_histo_tick_spacing_undo_snapshot():
    from matplotlib.ticker import MultipleLocator

    from batplot.plot_modes.histo.session import apply_histo_snapshot, capture_histo_snapshot

    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    fig, ax, _meta = create_histo_figure(state)
    snap_before = capture_histo_snapshot(state, fig, ax)
    step_before = snap_before["tick_spacing"].get("y_major_step")

    ax.yaxis.set_major_locator(MultipleLocator(20))
    snap_after = capture_histo_snapshot(state, fig, ax)
    assert snap_after["tick_spacing"]["y_major_step"] == pytest.approx(20.0)

    apply_histo_snapshot(fig, ax, state, snap_before)
    loc = ax.yaxis.get_major_locator()
    if step_before is not None:
        assert isinstance(loc, MultipleLocator)
        assert float(loc._edge.step) == pytest.approx(step_before)
    else:
        assert not isinstance(loc, MultipleLocator)

    apply_histo_snapshot(fig, ax, state, snap_after)
    loc2 = ax.yaxis.get_major_locator()
    assert isinstance(loc2, MultipleLocator)
    assert float(loc2._edge.step) == pytest.approx(20.0)

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_legacy_title_stripped_with_empty_column_name():
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="Length.csv")
    state.style.title = "Histogram Length"
    fig, ax, _meta = create_histo_figure(state)
    assert state.style.title == ""
    assert ax.get_title() == ""

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_legacy_title_stripped_on_pkl_batch_load(tmp_path):
    import pickle

    from batplot.plot_modes.histo.session import load_histo_session

    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="Length.csv")
    state.style.title = "Histogram Length"
    fig, ax, _meta = create_histo_figure(state)
    snap = _snapshot_for_json(state, fig, ax)
    snap["style"]["title"] = "Histogram Length"
    pkl_path = tmp_path / "Length_histo.pkl"
    with open(pkl_path, "wb") as fh:
        pickle.dump({"kind": "histo", "version": 1, "state": snap}, fh)
    import matplotlib.pyplot as plt

    plt.close(fig)

    loaded = load_histo_session(str(pkl_path))
    assert loaded is not None
    fig2, ax2, state2 = loaded
    assert state2.style.title == ""
    assert ax2.get_title() == ""
    plt.close(fig2)


def test_new_pkl_save_never_stores_legacy_title(tmp_path):
    import pickle

    from batplot.plot_modes.histo.interactive import _save_session

    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="Length.csv")
    state.style.title = "Histogram Length"
    fig, ax, _meta = create_histo_figure(state)
    pkl_path = tmp_path / "new_histo.pkl"
    _save_session(fig, ax, state, str(pkl_path))

    with open(pkl_path, "rb") as fh:
        payload = pickle.load(fh)
    assert payload["state"]["style"]["title"] == ""
    assert state.style.title == ""
    assert ax.get_title() == ""

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_old_pkl_resave_cleans_title_in_file(tmp_path):
    import pickle

    from batplot.plot_modes.histo.interactive import _save_session
    from batplot.plot_modes.histo.session import load_histo_session

    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    legacy_snap = _snapshot_for_json(build_histo_state(setup, source_path="Length.csv"))
    legacy_snap["style"]["title"] = "Histogram Length"
    old_path = tmp_path / "old.pkl"
    with open(old_path, "wb") as fh:
        pickle.dump({"kind": "histo", "version": 1, "state": legacy_snap}, fh)

    loaded = load_histo_session(str(old_path))
    assert loaded is not None
    fig, ax, state = loaded
    assert ax.get_title() == ""
    assert state.style.title == ""

    clean_path = tmp_path / "clean.pkl"
    _save_session(fig, ax, state, str(clean_path))
    with open(clean_path, "rb") as fh:
        payload = pickle.load(fh)
    assert payload["state"]["style"]["title"] == ""

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_legacy_title_stripped_on_style_export(tmp_path):
    from batplot.plot_modes.histo.interactive import _export_style, _snapshot_state

    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="Length.csv")
    state.style.title = "Histogram Length"
    fig, ax, _meta = create_histo_figure(state)
    style_path = tmp_path / "style.bpsh"
    _export_style(fig, ax, state, str(style_path))
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["style"]["title"] == ""

    snap = _snapshot_state(state, fig, ax)
    assert snap["style"]["title"] == ""

    import matplotlib.pyplot as plt

    plt.close(fig)


def test_histo_bold_and_highlight_apply_to_bar_labels_and_legend():
    """f→b/h must survive redraw for bar numbers and mean/median legend (p/i/s/b artists)."""
    import matplotlib.pyplot as plt

    from batplot.plot_modes.histo.plot import draw_histogram

    values = np.array([1.0, 2.0, 2.0, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.font_weight = "bold"
    state.style.text_highlight = True
    state.style.show_bar_labels = True
    state.style.show_mean_line = True
    fig, ax = plt.subplots()
    draw_histogram(fig, ax, state)

    assert ax.xaxis.label.get_fontweight() == "bold"
    assert ax.xaxis.label.get_bbox_patch() is not None
    bar_texts = [t for t in ax.texts if t.get_text()]
    assert bar_texts
    assert all(t.get_fontweight() == "bold" for t in bar_texts)
    leg = ax.get_legend()
    assert leg is not None
    assert all(t.get_fontweight() == "bold" for t in leg.get_texts())
    plt.close(fig)


def test_histo_style_p_i_roundtrip_font_weight_highlight(tmp_path):
    """Old sessions without weight keys stay safe; export/import round-trips bold+highlight."""
    import matplotlib.pyplot as plt

    from batplot.plot_modes.histo.interactive import _export_style
    from batplot.plot_modes.histo.session import apply_histo_style_snapshot
    from batplot.plot_modes.histo.plot import refresh_histo_figure

    values = np.array([1.0, 2.0, 3.0, 4.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path="test.csv")
    state.style.font_weight = "bold"
    state.style.text_highlight = True
    state.style.text_highlight_fc = "yellow"
    fig, ax, _meta = create_histo_figure(state)
    style_path = tmp_path / "font.bpsh"
    _export_style(fig, ax, state, str(style_path))
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["style"]["font_weight"] == "bold"
    assert payload["style"]["text_highlight"] is True

    # Old-style payload without weight/highlight keys must not crash
    from batplot.plot_modes.histo.interactive import _snapshot_state

    state2 = build_histo_state(setup, source_path="test.csv")
    fig2, ax2, _ = create_histo_figure(state2)
    old = _snapshot_state(state2, fig2, ax2)
    old["style"].pop("font_weight", None)
    old["style"].pop("text_highlight", None)
    old["style"].pop("text_highlight_fc", None)
    old["style"].pop("text_highlight_alpha", None)
    old["style"].pop("text_highlight_pad", None)
    apply_histo_style_snapshot(fig2, ax2, state2, old)
    refresh_histo_figure(fig2, ax2, state2)
    assert state2.style.font_weight == "normal"
    assert state2.style.text_highlight is False

    # Import exported bold style
    apply_histo_style_snapshot(fig2, ax2, state2, payload)
    refresh_histo_figure(fig2, ax2, state2)
    assert state2.style.font_weight == "bold"
    assert state2.style.text_highlight is True
    assert ax2.xaxis.label.get_fontweight() == "bold"
    plt.close(fig)
    plt.close(fig2)
