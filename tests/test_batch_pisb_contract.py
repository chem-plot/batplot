"""Contract tests: batch ``p`` / ``i`` / ``s`` / ``b`` share one capture path per mode."""

from __future__ import annotations

import os
import pickle

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot import session as S
from batplot.plot_modes.batch_session.batch_panel_state import (
    batch_state_handlers,
    get_batch_state_handler,
    verify_panel_pisb_roundtrip,
)
from batplot.plot_modes.batch_session.kinds import detect_session_kind
from batplot.plot_modes.batch_session.load import load_batch_panels
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
from batplot.plot_modes.histo.session import save_histo_session
from batplot.plot_modes.histo.wizard import HistoSetup


def test_all_batch_kinds_registered():
    handlers = batch_state_handlers()
    assert set(handlers) == {"xy", "ec_gc", "cpc", "operando_ec", "histo"}
    for kind, handler in handlers.items():
        assert handler.kind == kind
        assert callable(handler.capture)
        assert callable(handler.restore)
        assert callable(handler.apply_import)
        assert callable(handler.save)
        assert callable(handler.export_style)
        assert callable(handler.load_import)


def test_xy_pisb_roundtrip(tmp_path):
    from tests.test_batch_session import _make_xy_pkl

    pkl = tmp_path / "xy.pkl"
    _make_xy_pkl(str(pkl))
    result = load_batch_panels([str(pkl)])
    assert not isinstance(result, int)
    panel = result.panels[0]
    try:
        verify_panel_pisb_roundtrip(panel, "xy", sub="ps")
        verify_panel_pisb_roundtrip(panel, "xy", sub="psg")
        out = tmp_path / "saved.pkl"
        get_batch_state_handler("xy").save(panel, str(out))
        reloaded = load_batch_panels([str(out)])
        assert not isinstance(reloaded, int)
        verify_panel_pisb_roundtrip(reloaded.panels[0], "xy")
        plt.close(reloaded.panels[0].fig)
    finally:
        plt.close(panel.fig)


def test_histo_pisb_roundtrip(tmp_path):
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
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("Length\n1\n2\n2.5\n3\n8\n", encoding="utf-8")
    state = build_histo_state(setup, source_path=str(csv_path))
    fig, ax, _meta = create_histo_figure(state)
    pkl = tmp_path / "histo.pkl"
    save_histo_session(fig, ax, state, str(pkl))
    plt.close(fig)

    result = load_batch_panels([str(pkl)])
    assert not isinstance(result, int)
    panel = result.panels[0]
    try:
        verify_panel_pisb_roundtrip(panel, "histo", sub="ps")
        out = tmp_path / "saved.pkl"
        get_batch_state_handler("histo").save(panel, str(out))
        reloaded = load_batch_panels([str(out)])
        assert not isinstance(reloaded, int)
        verify_panel_pisb_roundtrip(reloaded.panels[0], "histo")
        plt.close(reloaded.panels[0].fig)
    finally:
        plt.close(panel.fig)


def test_operando_pisb_roundtrip():
    from tests.test_operando_batch_menu import _build_panel

    panel = _build_panel()
    try:
        verify_panel_pisb_roundtrip(panel, "operando_ec", sub="ps")
        verify_panel_pisb_roundtrip(panel, "operando_ec", sub="psg")
    finally:
        plt.close(panel.fig)


def _collect_pkl_paths(*roots: str) -> list[str]:
    paths: list[str] = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower().endswith(".pkl"):
                    paths.append(os.path.join(dirpath, name))
    return sorted(set(paths))


@pytest.fixture(scope="module")
def user_figures_pkls():
    roots = [
        os.environ.get(
            "BATPLOT_FIGURES_PKL_DIR",
            "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/Li2FeSeO_processing/Figures",
        ),
        os.environ.get(
            "BATPLOT_FIGURES_PKL_DIR2",
            "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/NFSO data/Figures",
        ),
    ]
    paths = _collect_pkl_paths(*roots)
    if not paths:
        pytest.skip("No user Figures .pkl directories found on this machine")
    return paths


def test_user_figures_pkls_batch_pisb(user_figures_pkls):
    """Optional integration: every user .pkl loads and passes batch p/i/s/b round-trip."""
    failures: list[tuple[str, str]] = []
    for path in user_figures_pkls:
        kind = detect_session_kind(path)
        if kind is None or kind == "dqdv_2d_contour":
            continue
        if kind not in batch_state_handlers():
            continue
        try:
            result = load_batch_panels([path])
            if isinstance(result, int):
                failures.append((os.path.basename(path), f"load_batch_panels returned {result}"))
                continue
            panel = result.panels[0]
            try:
                verify_panel_pisb_roundtrip(panel, kind, sub="ps")
                handler = get_batch_state_handler(kind)
                fd, tmp_pkl = _temp_pkl()
                os.close(fd)
                try:
                    handler.save(panel, tmp_pkl)
                    reloaded = load_batch_panels([tmp_pkl])
                    if isinstance(reloaded, int):
                        failures.append((os.path.basename(path), "save reload failed"))
                    else:
                        plt.close(reloaded.panels[0].fig)
                finally:
                    try:
                        os.unlink(tmp_pkl)
                    except OSError:
                        pass
            finally:
                plt.close(panel.fig)
        except Exception as exc:
            failures.append((os.path.basename(path), f"{type(exc).__name__}: {exc}"))
    if failures:
        msg = "\n".join(f"  {name}: {err}" for name, err in failures[:40])
        extra = f"\n  ... and {len(failures) - 40} more" if len(failures) > 40 else ""
        pytest.fail(f"{len(failures)} batch p/i/s/b failure(s):\n{msg}{extra}")


def _temp_pkl():
    import tempfile

    return tempfile.mkstemp(suffix=".pkl")
