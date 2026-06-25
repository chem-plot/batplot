"""Shared pytest configuration and fixtures for the batplot round-trip suite.

These tests exercise the persistence boundaries that have historically drifted
out of sync between code paths:

* ``dump_* -> load_*``      (session save / restore, the ``.pkl`` files)
* ``export -> import``      (style files, ``.bps`` / ``.bpsg``)

They are intentionally headless (Matplotlib ``Agg`` backend) so they run
unchanged on Windows, macOS and Linux and inside CI with no display.
"""

import os

# Force a non-interactive backend BEFORE pyplot is imported anywhere.
os.environ["MPLBACKEND"] = "Agg"

import matplotlib

matplotlib.use("Agg", force=True)

import types
from typing import Optional, TypeVar

import numpy as np
import pytest
import matplotlib.pyplot as plt

T = TypeVar("T")


@pytest.fixture(autouse=True)
def close_figures_after_test():
    """Avoid cross-test figure leakage and Matplotlib max-open warnings."""
    yield
    plt.close("all")


@pytest.fixture
def session_path(tmp_path):
    """Return a helper that builds absolute paths inside a per-test tmp dir."""

    def _make(name):
        return str(tmp_path / name)

    return _make


@pytest.fixture
def fake_args():
    """Minimal stand-in for the parsed CLI ``args`` namespace.

    Only attributes actually read by the persistence code paths are provided;
    everything else resolves via ``getattr(..., default)`` in the source.
    """

    return types.SimpleNamespace(stack=False, norm=False, ro=False, xrange=None)


def assert_allclose(a, b, msg=""):
    """Array comparison that tolerates float round-tripping through JSON/pickle."""
    np.testing.assert_allclose(np.asarray(a, float), np.asarray(b, float),
                               rtol=1e-6, atol=1e-9, err_msg=msg)


def loaded(result: Optional[T], name: str = "session loader") -> T:
    """Assert that a ``load_*_session`` call succeeded and return its result.

    The ``load_*_session`` helpers return ``None`` on a failed/aborted load, so
    their return type is ``Optional[...]``. Tests that expect a successful load
    route the result through this helper: it fails loudly with a clear message
    if ``None`` slips through, and narrows the type away from ``None`` so that
    static type checkers stop flagging the subsequent tuple unpacking.
    """
    assert result is not None, f"{name} returned None"
    return result
