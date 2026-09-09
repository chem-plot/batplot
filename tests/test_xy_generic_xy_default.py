"""XY quick plot: no --xaxis/--wl → cols 1–2 with labels X / Y."""

from __future__ import annotations

import os
import tempfile

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from batplot import session as S
from batplot.args import parse_args
from batplot.plot_modes.xy.axis_units import get_xy_axis_mode
from batplot.plot_modes.xy.pipeline import run_xy_pipeline
from conftest import loaded


def _prep(argv):
    args = parse_args(argv)
    # Mirror batplot_main defaulting (pipeline assumes delta is a float).
    if args.delta is None:
        args.delta = 0.1 if args.stack else 0.0
    return args


def _stub_display(monkeypatch):
    import batplot._mpl_backend as MB

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    for name in (
        "show_figure_if_possible",
        "hold_figure_open",
        "require_interactive_display",
        "prime_interactive_figure",
    ):
        monkeypatch.setattr(MB, name, lambda *a, **k: None)


def _xy_file(td: str, name: str = "file.xy", *, n: int = 40, ncol: int = 3) -> str:
    path = os.path.join(td, name)
    x = np.linspace(0.0, 10.0, n)
    cols = [x, np.sin(x)]
    if ncol >= 3:
        cols.append(np.cos(x))
    np.savetxt(path, np.column_stack(cols))
    return path


def test_xy_default_no_xaxis_no_wl_uses_X_Y_labels(monkeypatch):
    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td)
        run_xy_pipeline(_prep([path]))
        fig = plt.gcf()
        ax = fig.axes[0]
        assert ax.get_xlabel() == "X"
        assert ax.get_ylabel() == "Y"
        assert get_xy_axis_mode(fig, ax=ax) == "unknown"
        assert len(ax.lines) == 1
        plt.close("all")


def test_xy_default_readcol_and_stack_still_work(monkeypatch):
    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td, ncol=3)
        x = np.loadtxt(path)[:, 0]
        z = np.loadtxt(path)[:, 2]

        run_xy_pipeline(_prep([path, "--readcol", "1", "3"]))
        ax = plt.gcf().axes[0]
        assert ax.get_xlabel() == "X"
        assert ax.get_ylabel() == "Y"
        assert abs(float(ax.lines[0].get_ydata()[0]) - float(z[0])) < 1e-6
        plt.close("all")

        path2 = _xy_file(td, "file2.xy", ncol=2)
        run_xy_pipeline(_prep([path, path2, "--stack"]))
        ax = plt.gcf().axes[0]
        assert ax.get_xlabel() == "X"
        assert "Normalized" in ax.get_ylabel()
        assert len(ax.lines) == 2
        plt.close("all")


def test_xy_explicit_xaxis_and_wl_unchanged(monkeypatch):
    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td)
        run_xy_pipeline(_prep([path, "--xaxis", "2theta"]))
        ax = plt.gcf().axes[0]
        assert "2" in ax.get_xlabel()
        assert ax.get_ylabel() == "Intensity"
        plt.close("all")

        run_xy_pipeline(_prep([path, "--wl", "1.5406"]))
        fig = plt.gcf()
        ax = fig.axes[0]
        # --wl without --xaxis → Q mode
        assert get_xy_axis_mode(fig, ax=ax) == "Q"
        assert "Q" in ax.get_xlabel() or "q" in ax.get_xlabel().lower()
        plt.close("all")


def test_xy_generic_session_roundtrip_preserves_XY(monkeypatch, session_path):
    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td)
        args = _prep([path])
        run_xy_pipeline(args)
        fig = plt.gcf()
        ax = fig.axes[0]
        xs = [ln.get_xdata().copy() for ln in ax.lines]
        ys = [ln.get_ydata().copy() for ln in ax.lines]
        p = session_path("xy_generic_xy.pkl")
        S.dump_session(
            p,
            fig=fig,
            ax=ax,
            x_data_list=xs,
            y_data_list=ys,
            orig_y=ys,
            x_full_list=xs,
            raw_y_full_list=ys,
            offsets_list=[0.0],
            labels=["c1"],
            delta=0.0,
            args=args,
            tick_state={},
            skip_confirm=True,
        )
        plt.close("all")
        fig2, ax2, _mk = loaded(S.load_xy_session(p))
        assert ax2.get_xlabel() == "X"
        assert ax2.get_ylabel() == "Y"
        assert get_xy_axis_mode(fig2, ax=ax2) in ("unknown", "other")
        plt.close(fig2)


def test_allfiles_and_directory_without_xaxis_wl_use_XY(monkeypatch):
    """``batplot /path allfiles --i`` and ``batplot /path --i`` need no --xaxis/--wl."""
    from batplot.batplot import _maybe_expand_allfiles_argument, _prepare_allfiles_directory

    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        _xy_file(td, "a.xy", ncol=2)
        _xy_file(td, "b.xy", ncol=2)

        # path + allfiles (as in batplot /path allfiles --i)
        args = _prep([td, "allfiles", "--i"])
        _maybe_expand_allfiles_argument(args)
        args.interactive = False
        run_xy_pipeline(args)
        ax = plt.gcf().axes[0]
        assert ax.get_xlabel() == "X"
        assert ax.get_ylabel() == "Y"
        assert len(ax.lines) == 2
        plt.close("all")

        # directory alone with --i expansion (batplot_main isdir branch)
        args2 = _prep([td, "--i"])
        assert len(args2.files) == 1 and os.path.isdir(args2.files[0])
        _prepare_allfiles_directory(os.path.abspath(args2.files[0]), args2, use_relative_paths=False)
        args2.interactive = False
        run_xy_pipeline(args2)
        ax2 = plt.gcf().axes[0]
        assert ax2.get_xlabel() == "X"
        assert ax2.get_ylabel() == "Y"
        assert len(ax2.lines) == 2
        plt.close("all")


def test_batch_all_without_xaxis_wl_exports_XY_labels(monkeypatch):
    """``batplot --all`` must not require --xaxis / --wl; labels X/Y for plain files."""
    from batplot.batch import batch_process

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    with tempfile.TemporaryDirectory() as td:
        _xy_file(td, "a.xy", ncol=2)
        _xy_file(td, "b.xye", ncol=3)
        # Unknown extension: still columns 1–2
        x = np.linspace(0.0, 5.0, 20)
        np.savetxt(os.path.join(td, "c.afes"), np.column_stack([x, np.cos(x)]))
        # Non-Bruker .raw text (not Bruker binary)
        np.savetxt(os.path.join(td, "d.raw"), np.column_stack([x, np.sin(x)]))

        cwd = os.getcwd()
        try:
            os.chdir(td)
            args = parse_args(["--all", "--format", "svg"])
            assert args.xaxis is None and args.wl is None
            batch_process(td, args)
        finally:
            os.chdir(cwd)

        figs = os.path.join(td, "Figures")
        assert os.path.isdir(figs)
        for stem in ("a", "b", "c", "d"):
            assert os.path.isfile(os.path.join(figs, f"{stem}.svg")), stem


def test_batch_all_explicit_xaxis_still_exports(monkeypatch):
    """Typed ``--xaxis`` on ``--all`` must keep working (no regression)."""
    from batplot.batch import batch_process

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    with tempfile.TemporaryDirectory() as td:
        _xy_file(td, "a.xy", ncol=2)
        cwd = os.getcwd()
        try:
            os.chdir(td)
            args = parse_args(["--all", "--xaxis", "2theta", "--format", "svg"])
            batch_process(td, args)
        finally:
            os.chdir(cwd)
        assert os.path.isfile(os.path.join(td, "Figures", "a.svg"))


def test_xaxis_and_wl_behavior_unchanged_pipeline(monkeypatch):
    """With ``--xaxis`` / ``--wl``, modes and labels match pre-generic-X/Y behavior."""
    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td, ncol=2)
        x_mid = float(np.loadtxt(path)[10, 0])
        assert x_mid > 0.0

        # --xaxis 2theta
        run_xy_pipeline(_prep([path, "--xaxis", "2theta"]))
        fig = plt.gcf()
        ax = fig.axes[0]
        assert get_xy_axis_mode(fig, ax=ax) == "2theta"
        assert "2" in ax.get_xlabel()
        assert ax.get_ylabel() == "Intensity"
        assert abs(float(ax.lines[0].get_xdata()[10]) - x_mid) < 1e-9  # no Q conversion
        plt.close("all")

        # --xaxis Q (needs λ via --wl for conversion from 2θ-like x)
        run_xy_pipeline(_prep([path, "--xaxis", "Q", "--wl", "1.5406"]))
        fig = plt.gcf()
        ax = fig.axes[0]
        assert get_xy_axis_mode(fig, ax=ax) == "Q"
        assert "Q" in ax.get_xlabel() or "q" in ax.get_xlabel().lower()
        # x should be converted away from raw 2θ-like values when λ given
        assert abs(float(ax.lines[0].get_xdata()[10]) - x_mid) > 1e-6
        plt.close("all")

        # --wl alone → Q (historic for .xy)
        run_xy_pipeline(_prep([path, "--wl", "1.5406"]))
        fig = plt.gcf()
        ax = fig.axes[0]
        assert get_xy_axis_mode(fig, ax=ax) == "Q"
        assert ax.get_ylabel() == "Intensity"
        plt.close("all")

        # --xaxis d + --wl
        run_xy_pipeline(_prep([path, "--xaxis", "d", "--wl", "1.5406"]))
        fig = plt.gcf()
        ax = fig.axes[0]
        assert get_xy_axis_mode(fig, ax=ax) == "d"
        plt.close("all")


def test_batch_all_xaxis_wl_labels_and_raw_wl_historic(monkeypatch):
    """``--all --xaxis`` / ``--wl`` labels unchanged; non-Bruker .raw + --wl stays 2θ."""
    from batplot.batch import batch_process
    import matplotlib.figure as mfig

    monkeypatch.setattr(plt, "show", lambda *a, **k: None)
    captured = []
    _orig = mfig.Figure.savefig

    def _spy(self, *a, **k):
        if self.axes:
            captured.append(
                (
                    self.axes[0].get_xlabel(),
                    self.axes[0].get_ylabel(),
                    float(self.axes[0].lines[0].get_xdata()[0]) if self.axes[0].lines else None,
                )
            )
        return _orig(self, *a, **k)

    monkeypatch.setattr(mfig.Figure, "savefig", _spy)

    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td, "a.xy", ncol=2)
        x_mid = float(np.loadtxt(path)[10, 0])
        assert x_mid > 0.0
        x = np.linspace(0.0, 5.0, 20)
        np.savetxt(os.path.join(td, "d.raw"), np.column_stack([x, np.sin(x)]))

        cwd = os.getcwd()
        try:
            os.chdir(td)
            # --xaxis 2theta
            captured.clear()
            batch_process(td, parse_args(["--all", "--xaxis", "2theta", "--format", "svg"]))
            assert captured
            for xlab, ylab, xfirst in captured:
                assert "2" in xlab or "θ" in xlab
                assert ylab == "Intensity"
                assert xfirst is not None

            # --wl alone on .xy → Q conversion; .raw historic stays 2θ (no convert)
            captured.clear()
            # only one .xy to isolate, then .raw alone
            os.remove(os.path.join(td, "d.raw"))
            batch_process(td, parse_args(["--all", "--wl", "1.5406", "--format", "svg"]))
            assert captured
            xlab, ylab, xfirst = captured[0]
            assert "Q" in xlab or "q" in xlab.lower()
            assert ylab == "Intensity"
            # mid-point (index 10) differs after 2θ→Q; spy still stores first point —
            # re-check via label only here, and conversion via separate mid capture
            assert "Q" in xlab or "q" in xlab.lower()

            # Capture mid-x for conversion proof
            captured_mid = []

            def _spy_mid(self, *a, **k):
                if self.axes and self.axes[0].lines:
                    xd = self.axes[0].lines[0].get_xdata()
                    captured_mid.append(float(xd[min(10, len(xd) - 1)]))
                return _orig(self, *a, **k)

            monkeypatch.setattr(mfig.Figure, "savefig", _spy_mid)
            captured_mid.clear()
            batch_process(td, parse_args(["--all", "--wl", "1.5406", "--format", "svg"]))
            assert captured_mid and abs(captured_mid[0] - x_mid) > 1e-6

            # non-Bruker .raw + --wl → still 2θ label, raw x (historic)
            monkeypatch.setattr(mfig.Figure, "savefig", _spy)
            captured.clear()
            np.savetxt(os.path.join(td, "d.raw"), np.column_stack([x, np.sin(x)]))
            os.remove(os.path.join(td, "a.xy"))
            batch_process(td, parse_args(["--all", "--wl", "1.5406", "--format", "svg"]))
            assert len(captured) == 1
            xlab, ylab, xfirst = captured[0]
            assert "2" in xlab or "θ" in xlab
            assert abs(xfirst - float(x[0])) < 1e-9
        finally:
            os.chdir(cwd)


def test_cif_2theta_still_requires_global_wl_when_xaxis_set(monkeypatch):
    """Historic gate: ``--xaxis 2theta`` + CIF still needs ``--wl`` (not only file:wl)."""
    import pytest

    _stub_display(monkeypatch)
    with tempfile.TemporaryDirectory() as td:
        path = _xy_file(td, "scan.xy", ncol=2)
        cif = os.path.join(td, "phase.cif")
        with open(cif, "w", encoding="utf-8") as f:
            f.write(
                "data_test\n"
                "_cell_length_a 4.0\n_cell_length_b 4.0\n_cell_length_c 4.0\n"
                "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
                "_symmetry_space_group_name_H-M 'P 1'\n"
                "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
                "Li 0 0 0\n"
            )
        with pytest.raises(ValueError, match="wavelength"):
            run_xy_pipeline(_prep([f"{path}:1.5406", cif, "--xaxis", "2theta"]))

        # With --wl: unchanged success path
        run_xy_pipeline(_prep([path, cif, "--xaxis", "2theta", "--wl", "1.5406"]))
        ax = plt.gcf().axes[0]
        assert "2" in ax.get_xlabel() or "θ" in ax.get_xlabel()
        plt.close("all")
