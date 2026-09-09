"""Tests for CLI --convert (2θ / Q / d) file export."""

from __future__ import annotations

import os
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

from batplot.converters import (
    convert_xrd_data,
    normalize_extension,
    resolve_conversion,
)
from batplot.plot_modes.xy.axis_units import convert_x_array


def test_normalize_extension():
    assert normalize_extension("xy") == ".xy"
    assert normalize_extension(".QYE") == ".qye"
    assert normalize_extension("*.dat") == ".dat"
    assert normalize_extension(None) is None
    assert normalize_extension("") is None


def test_resolve_conversion_legacy_and_units():
    assert resolve_conversion("1.54", "q") == ("2theta", "Q", 1.54, None)
    assert resolve_conversion("q", "1.54") == ("Q", "2theta", None, 1.54)
    assert resolve_conversion("q", "d") == ("Q", "d", None, None)
    assert resolve_conversion("d", "q") == ("d", "Q", None, None)
    assert resolve_conversion("0.26", "1.54") == ("2theta", "2theta", 0.26, 1.54)
    assert resolve_conversion("2theta", "q", wl_fallback=0.26) == ("2theta", "Q", 0.26, None)
    assert resolve_conversion("q", "2theta", wl_fallback=1.54) == ("Q", "2theta", None, 1.54)
    assert resolve_conversion("d", "2th", wl_fallback=1.5406) == ("d", "2theta", None, 1.5406)


def test_resolve_conversion_errors():
    with pytest.raises(ValueError, match="wavelength"):
        resolve_conversion("2theta", "q")
    with pytest.raises(ValueError, match="No conversion"):
        resolve_conversion("q", "Q")
    with pytest.raises(ValueError, match="Invalid"):
        resolve_conversion("foo", "q")


def test_convert_folder_xy_to_q(tmp_path: Path):
    folder = tmp_path / "patterns"
    folder.mkdir()
    # 2θ (Cu) sample points
    tth = np.array([10.0, 20.0, 30.0])
    y = np.array([1.0, 2.0, 3.0])
    for name in ("a.xy", "b.xy", "skip.txt"):
        if name.endswith(".xy"):
            np.savetxt(folder / name, np.column_stack([tth, y]))
        else:
            (folder / name).write_text("not used\n", encoding="utf-8")

    from batplot.batplot import _run_convert_route

    args = Namespace(
        convert=["1.5406", "q"],
        files=[str(folder)],
        ext=".xy",
        convert_ext=None,
        wl=None,
        readcol=None,
        readcol_by_file=None,
        readcol_by_ext=None,
    )
    rc = _run_convert_route(args)
    assert rc == 0
    out_dir = folder / "converted"
    assert out_dir.is_dir()
    assert (out_dir / "a.qye").is_file()
    assert (out_dir / "b.qye").is_file()
    assert not (out_dir / "skip.qye").exists()

    loaded = np.loadtxt(out_dir / "a.qye")
    q_expected = convert_x_array(tth, frm="2theta", to="Q", wl=1.5406)
    np.testing.assert_allclose(loaded[:, 0], q_expected, rtol=1e-5)
    np.testing.assert_allclose(loaded[:, 1], y)


def test_convert_ext_and_named_units(tmp_path: Path):
    f = tmp_path / "pat.xy"
    tth = np.array([15.0, 25.0])
    y = np.array([10.0, 20.0])
    np.savetxt(f, np.column_stack([tth, y]))

    args = Namespace(
        wl=0.25,
        readcol=None,
        readcol_by_file={},
        readcol_by_ext={},
    )
    convert_xrd_data(
        [str(f)],
        "2theta",
        "q",
        args=args,
        out_ext="dat",
    )
    out = tmp_path / "converted" / "pat.dat"
    assert out.is_file()
    loaded = np.loadtxt(out)
    q_expected = convert_x_array(tth, frm="2theta", to="Q", wl=0.25)
    np.testing.assert_allclose(loaded[:, 0], q_expected, rtol=1e-5)


def test_convert_q_to_d_roundtrip(tmp_path: Path):
    f = tmp_path / "data.qye"
    q = np.array([1.0, 2.0, 3.0])
    y = np.array([4.0, 5.0, 6.0])
    e = np.array([0.1, 0.2, 0.3])
    np.savetxt(f, np.column_stack([q, y, e]))

    convert_xrd_data([str(f)], "q", "d")
    out_d = tmp_path / "converted" / "data.xy"
    assert out_d.is_file()
    d_loaded = np.loadtxt(out_d)
    d_expected = convert_x_array(q, frm="Q", to="d", wl=None)
    np.testing.assert_allclose(d_loaded[:, 0], d_expected, rtol=1e-5)
    np.testing.assert_allclose(d_loaded[:, 2], e)

    convert_xrd_data([str(out_d)], "d", "q", out_ext=".qye")
    # out_d is already under converted/, so the next write nests another converted/
    nested = out_d.parent / "converted" / "data.qye"
    assert nested.is_file()
    q_back = np.loadtxt(nested)
    np.testing.assert_allclose(q_back[:, 0], q, rtol=1e-5)


def test_cli_parse_ext_flags():
    from batplot.args import parse_args

    args = parse_args(
        ["folder", "--ext", "xy", "--convert", "0.26", "q", "--convert-ext", "qye"]
    )
    assert args.ext == "xy"
    assert args.convert == ["0.26", "q"]
    assert args.convert_ext == "qye"
