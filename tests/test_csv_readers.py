"""CSV reader tests for mixed label/value exports."""

from __future__ import annotations

import numpy as np

from batplot.readers import read_csv_numeric_grid, robust_loadtxt_skipheader


def test_read_csv_numeric_grid_parses_mixed_refinement_rows(tmp_path):
    csv_path = tmp_path / "refinement.csv"
    csv_path.write_text(
        "Scan Number,Rwp2,phase,extra,Bi2Se3\n"
        "0,4.85,;,percent_bi2se3;,100,;,a_bi2se3,;,4.15\n"
        "15,4.86,;,percent_bi2se3;,99,;,a_bi2se3,;,4.16\n",
        encoding="utf-8",
    )

    grid = read_csv_numeric_grid(str(csv_path))
    assert grid.shape[0] == 2
    assert grid.shape[1] >= 5
    np.testing.assert_allclose(grid[:, 0], [0.0, 15.0])
    np.testing.assert_allclose(grid[:, 1], [4.85, 4.86])
    np.testing.assert_allclose(grid[:, 4], [100.0, 99.0])


def test_robust_loadtxt_skipheader_uses_csv_grid_for_csv(tmp_path):
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text(
        "Scan Number,Rwp2,Bi2Se3\n"
        "0,1.1,100\n"
        "10,1.2,99\n",
        encoding="utf-8",
    )

    data = robust_loadtxt_skipheader(str(csv_path))
    np.testing.assert_allclose(data[:, 0], [0.0, 10.0])
    np.testing.assert_allclose(data[:, 2], [100.0, 99.0])
