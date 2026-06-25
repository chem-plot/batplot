"""End-to-end CLI smoke tests for the top-level mode routes.

These tests run each plotting route via ``batplot.cli.main`` on small
synthetic data files and assert that the route completes successfully
(``exit`` code 0 / ``None``) without raising. For routes that write a
figure non-interactively they also assert the output file is produced.

They guard the routing/dispatch boundary in ``batplot.batplot`` -- in
particular they catch regressions (e.g. a missing import / ``NameError``)
introduced when mode handlers are moved into ``batplot.plot_modes``.

The tests are headless (Agg backend via conftest) so they run unchanged on
Windows, macOS and Linux.
"""

import os

import pytest

from batplot.cli import main


def _run(argv):
    """Invoke the CLI in-process; return the integer exit code.

    Routes use ``exit()`` (SystemExit) on success, so translate that to a
    code. A non-SystemExit exception is allowed to propagate and fail the
    test (that is the regression we want to catch).
    """
    try:
        rc = main(list(argv))
    except SystemExit as exc:
        rc = exc.code
    return 0 if rc is None else rc


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _xrd_xy(path, shift=0.0, scale=1.0):
    lines = []
    for j in range(60):
        x = 10.0 + j * 0.5
        y = 100.0 + scale * 1000.0 * pow(2.718281828, -((x - 30.0 - shift) ** 2) / 4.0)
        lines.append(f"{x:.4f} {y:.4f}")
    _write(path, "\n".join(lines) + "\n")


_GC_CSV = (
    "Voltage(V),Current(mA),Step Type,Spec. Cap.(mAh/g)\n"
    "3.0,0.5,CC Chg,0\n"
    "3.2,0.5,CC Chg,50\n"
    "3.4,0.5,CC Chg,100\n"
    "3.2,-0.5,CC DChg,100\n"
    "3.0,-0.5,CC DChg,50\n"
    "2.8,-0.5,CC DChg,0\n"
)

_DQDV_CSV = (
    "Voltage(V),Current(mA),Step Type,dQm/dV(mAh/V.g)\n"
    "3.0,0.5,CC Chg,10\n"
    "3.2,0.5,CC Chg,80\n"
    "3.4,0.5,CC Chg,20\n"
    "3.2,-0.5,CC DChg,-30\n"
    "3.0,-0.5,CC DChg,-90\n"
    "2.8,-0.5,CC DChg,-15\n"
)

_CPC_CSV = (
    "Cycle Index,Chg. Spec. Cap.(mAh/g),DChg. Spec. Cap.(mAh/g),Efficiency(%)\n"
    "1,100,98,98\n"
    "2,99,97,98\n"
    "3,98,96,98\n"
)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_xy_route_saves_figure(workdir):
    _xrd_xy(workdir / "scan.xy")
    rc = _run(["scan.xy", "--xaxis", "2theta", "--out", "xy.png"])
    assert rc in (0, None)
    assert (workdir / "xy.png").is_file()


def test_xy_stack_multi_file(workdir):
    _xrd_xy(workdir / "a.xy", shift=0.0)
    _xrd_xy(workdir / "b.xy", shift=1.0, scale=0.8)
    rc = _run(["a.xy", "b.xy", "--xaxis", "Q", "--stack", "--out", "stack.png"])
    assert rc in (0, None)
    assert (workdir / "stack.png").is_file()


def test_gc_route_saves_figure(workdir):
    _write(workdir / "gc.csv", _GC_CSV)
    rc = _run(["gc.csv", "--gc", "--mass", "5.0", "--out", "gc.png"])
    assert rc in (0, None)
    assert (workdir / "gc.png").is_file()


def test_gc_multi_file_route_saves_combined_figure(workdir, monkeypatch):
    _write(workdir / "gc_a.csv", _GC_CSV)
    _write(workdir / "gc_b.csv", _GC_CSV)

    from batplot.plot_modes.electrochem import routing as ec_routing

    monkeypatch.setattr(ec_routing.plt, "show", lambda *args, **kwargs: None)

    rc = _run(["gc_a.csv", "gc_b.csv", "--gc", "--out", "gc_multi.png"])
    assert rc in (0, None)
    assert (workdir / "gc_multi.png").is_file()


def test_dqdv_route_saves_figure(workdir):
    _write(workdir / "dqdv.csv", _DQDV_CSV)
    rc = _run(["dqdv.csv", "--dqdv", "--out", "dqdv.png"])
    assert rc in (0, None)
    assert (workdir / "dqdv.png").is_file()


def test_cpc_route_runs_clean(workdir):
    _write(workdir / "cpc.csv", _CPC_CSV)
    rc = _run(["cpc.csv", "--cpc", "--out", "cpc.png"])
    assert rc in (0, None)


def test_cpc_multi_file_route_builds_compact_file_data(workdir, monkeypatch):
    _write(workdir / "cpc_a.csv", _CPC_CSV)
    _write(workdir / "cpc_b.csv", _CPC_CSV)
    captured = {}

    from batplot.plot_modes.cpc import routing as cpc_routing

    def _fake_compact_legend(_ax, _ax2, file_data):
        captured["filenames"] = [entry["filename"] for entry in file_data]
        captured["visible"] = [entry.get("visible") for entry in file_data]

    monkeypatch.setattr(cpc_routing, "_build_compact_cpc_legend", _fake_compact_legend)

    rc = _run(["cpc_a.csv", "cpc_b.csv", "--cpc", "--out", "cpc_multi.png"])

    assert rc in (0, None)
    assert captured == {
        "filenames": ["cpc_a.csv", "cpc_b.csv"],
        "visible": [True, True],
    }


def _write_cv_mpt(path):
    import math

    lines = ["EC-Lab ASCII FILE", "Nb header lines : 4", "",
             "mode\ttime/s\tEwe/V\t<I>/mA\tcycle number"]
    t = 0.0
    for cyc in (1, 2):
        for k in range(40):
            v = 2.5 + 1.5 * (k / 39.0)
            i = math.sin(k / 39.0 * math.pi) * (1.0 if cyc == 1 else 0.8)
            lines.append(f"1\t{t:.2f}\t{v:.4f}\t{i:.4f}\t{cyc}")
            t += 1
    _write(path, "\n".join(lines) + "\n")


def test_cv_route_runs_clean(workdir):
    _write_cv_mpt(workdir / "cv.mpt")
    rc = _run(["cv.mpt", "--cv", "--out", "cv.png"])
    assert rc in (0, None)


def test_operando_route_saves_figure(workdir):
    folder = workdir / "scans"
    folder.mkdir()
    for i in range(1, 6):
        _xrd_xy(folder / f"scan_{i}.xy", shift=i * 0.3, scale=1.0 + i * 0.05)
    rc = _run(["scans", "--operando", "--xaxis", "2theta", "--out", "op.png"])
    assert rc in (0, None)
    assert (workdir / "op.png").is_file()
