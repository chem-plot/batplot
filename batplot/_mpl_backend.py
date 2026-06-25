"""Ensure a headless Matplotlib backend unless the user chose a GUI backend.

Imported early from :mod:`batplot.cli` so pytest/CI on Windows never fall back
to Tk when ``MPLBACKEND=Agg`` is set.
"""

from __future__ import annotations

import os

if "MPLBACKEND" not in os.environ:
    os.environ["MPLBACKEND"] = "Agg"

import matplotlib as _mpl

_mpl.use(os.environ["MPLBACKEND"], force=True)
