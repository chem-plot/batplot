"""Backward-compatibility smoke tests for saved .pkl session reload."""

from __future__ import annotations

import os

import matplotlib
import pytest

matplotlib.use("Agg")

from batplot.plot_modes.common.session_key_smoke import smoke_session_path


FIGURES_DIR = os.environ.get(
    "BATPLOT_FIGURES_PKL_DIR",
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/Li2FeSeO_processing/Figures",
)
FIGURES_DIR2 = os.environ.get(
    "BATPLOT_FIGURES_PKL_DIR2",
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/NFSO data/Figures",
)

FIGURES_RECURSIVE = os.environ.get("BATPLOT_FIGURES_PKL_RECURSIVE", "").lower() in ("1", "true", "yes")


def _collect_pkl_paths(root: str, *, recursive: bool) -> list[str]:
    paths: list[str] = []
    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if name.lower().endswith(".pkl"):
                    paths.append(os.path.join(dirpath, name))
    else:
        paths = [
            os.path.join(root, name)
            for name in os.listdir(root)
            if name.lower().endswith(".pkl") and os.path.isfile(os.path.join(root, name))
        ]
    paths.sort()
    return paths


@pytest.fixture(scope="module")
def figures_pkls():
    roots = [FIGURES_DIR, FIGURES_DIR2]
    if not any(os.path.isdir(r) for r in roots):
        pytest.skip(f"Figures pkl dirs not present: {roots}")
    paths: list[str] = []
    for root in roots:
        if os.path.isdir(root):
            paths.extend(_collect_pkl_paths(root, recursive=FIGURES_RECURSIVE))
    paths = sorted(set(paths))
    if not paths:
        pytest.skip("No .pkl files in configured Figures dirs")
    return paths


@pytest.mark.parametrize("pkl_path", [])
def test_figures_pkl_loads(pkl_path: str):
    smoke_session_path(pkl_path)


def test_figures_pkls_all_load(pytestconfig, figures_pkls):
    """Load every .pkl in the user's Figures folder and exercise key submenus."""
    failures = []
    for path in figures_pkls:
        try:
            smoke_session_path(path)
        except Exception as exc:
            failures.append((os.path.basename(path), str(exc)))
    if failures:
        msg = "\n".join(f"  {name}: {err}" for name, err in failures)
        pytest.fail(f"{len(failures)} pkl key-smoke failure(s):\n{msg}")


def test_bm_xrd_pkl_color_menu_if_present():
    path = os.path.join(FIGURES_DIR, "BM_XRD.pkl")
    if not os.path.isfile(path):
        pytest.skip("BM_XRD.pkl not on this machine")
    smoke_session_path(path)
