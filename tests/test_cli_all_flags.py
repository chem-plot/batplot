"""Parse and route smoke coverage for every CLI flag registered in args.py."""

from __future__ import annotations

import pytest

from batplot.args import parse_args
from batplot.cli import main


def _run(argv):
    try:
        rc = main(list(argv))
    except SystemExit as exc:
        rc = exc.code
    return 0 if rc is None else rc


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["f.xy"], {}),
        (
            [
                "f.xy",
                "--xaxis",
                "2theta",
                "--wl",
                "1.54",
                "--delta",
                "0.2",
                "--autoscale",
                "--xrange",
                "1",
                "90",
                "--errors",
                "--norm",
                "--1d",
                "--2d",
            ],
            {
                "xaxis": "2theta",
                "wl": 1.54,
                "delta": 0.2,
                "autoscale": True,
                "xrange": [1.0, 90.0],
                "errors": True,
                "norm": True,
                "derivative_1d": True,
                "derivative_2d": True,
            },
        ),
        (
            ["f.xy", "--stack", "--txaxis", "--ro", "--debug", "--format", "png"],
            {"stack": True, "txaxis": True, "ro": True, "debug": True, "format": "png"},
        ),
        (
            ["gc.csv", "--gc", "--mass", "5", "--mass", "0.01g", "--anode", "--cathode"],
            {"gc": True, "mass": [5.0, 10.0], "anode": True, "cathode": True},
        ),
        (
            ["cv.mpt", "--cv", "--pw", "2.5", "4.2", "--cd", "0.1", "--b", "0.05", "0.05"],
            {"cv": True, "pw": [2.5, 4.2], "cd": 0.1, "b": [0.05, 0.05]},
        ),
        (["d.csv", "--dqdv"], {"dqdv": True}),
        (["c.csv", "--cpc"], {"cpc": True}),
        (["e.csv", "--epc", "--mass", "7"], {"epc": True, "mass": [7.0]}),
        (
            ["folder", "--operando", "--contour", "--average", "3", "--sum", "5"],
            {"operando": True, "average": 3, "scan_sum": 5},
        ),
        (
            ["h.csv", "--histo", "--histocol", "7", "--binwidth", "1", "--bins", "20"],
            {"histo": True, "histocol": 7, "binwidth": 1.0, "bins": 20},
        ),
        (["a.pkl", "b.pkl", "--canvas"], {"canvas": True}),
        (["--all"], {"all": "all"}),
        (["--all", "xy"], {"all": "xy"}),
        (["f.xy", "--convert", "1.54", "q"], {"convert": ["1.54", "q"]}),
        (["f.xy", "--extract-brml-scans"], {"extract_brml_scans": ""}),
        (["f.xy", "--extract-brml-scans", "outdir"], {"extract_brml_scans": "outdir"}),
        (["f.xy", "--fullprof", "1", "2", "3"], {"fullprof": [1.0, 2.0, 3.0]}),
        (
            ["f.xy", "--save", "--savefig", "out.png", "--out", "plot.png", "--i"],
            {"save": True, "savefig": "out.png", "out": "plot.png", "interactive": True},
        ),
        (
            ["left.xy", "--ry", "data.afes", "-i", "-r", "1", "2", "-o", "out.svg", "--readcolafes", "3", "4"],
            {
                "files": ["left.xy", "data.afes"],
                "interactive": True,
                "xrange": [1.0, 2.0],
                "out": "out.svg",
            },
        ),
    ],
)
def test_parse_args_all_registered_flags(argv, expected):
    args = parse_args(argv)
    for key, value in expected.items():
        assert getattr(args, key) == value
    if "readcolafes" in " ".join(argv):
        assert args.readcol_by_ext[".afes"] == [3, 4]
    if "--ry" in argv:
        assert args.right_y_indices == frozenset({0})


def test_version_flag_exits_cleanly(capsys):
    rc = main(["--version"])
    assert rc == 0
    assert "batplot v" in capsys.readouterr().out


def test_xy_route_flags_with_xaxis(workdir):
    from tests.test_cli_smoke import _xrd_xy, _run as cli_run

    _xrd_xy(workdir / "a.xy")
    _xrd_xy(workdir / "b.xy")
    assert cli_run(["a.xy", "b.xy", "--xaxis", "2theta", "--ry", "--out", "ry.png"]) in (0, None)
    assert (workdir / "ry.png").is_file()
    assert cli_run(["a.xy", "--xaxis", "2theta", "--ro", "--out", "ro.png"]) in (0, None)
    assert (workdir / "ro.png").is_file()
    assert cli_run(["a.xy", "--xaxis", "2theta", "--norm", "--out", "norm.png"]) in (0, None)
    assert (workdir / "norm.png").is_file()


def test_operando_average_and_sum_flags(workdir):
    from tests.test_cli_smoke import _xrd_xy, _run as cli_run

    folder = workdir / "scans"
    folder.mkdir()
    for i in range(1, 6):
        _xrd_xy(folder / f"s{i}.xy", shift=i * 0.3)
    assert cli_run(["scans", "--contour", "--average", "2", "--out", "avg.png"]) in (0, None)
    assert (workdir / "avg.png").is_file()
    assert cli_run(["scans", "--operando", "--sum", "2", "--out", "sum.png"]) in (0, None)
    assert (workdir / "sum.png").is_file()


def test_convert_flag_exports_qye(workdir):
    from tests.test_cli_smoke import _xrd_xy, _run as cli_run

    _xrd_xy(workdir / "a.xy")
    _xrd_xy(workdir / "b.xy")
    assert cli_run(["a.xy", "b.xy", "--convert", "1.54", "q"]) in (0, None)
    converted = workdir / "converted"
    assert converted.is_dir()
    assert list(converted.glob("*.qye"))


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path
