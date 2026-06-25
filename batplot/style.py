"""Compatibility shim for XY style helpers.

The implementation lives in :mod:`batplot.plot_modes.xy.style`. Keep this
module so existing imports such as ``from batplot import style`` continue to
work.
"""

from __future__ import annotations

from .plot_modes.xy import style as _xy_style
from .plot_modes.xy.style import *  # noqa: F401,F403

for _name in dir(_xy_style):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_xy_style, _name))

# Dynamic mirror of the real module's __all__; static analyzers cannot
# evaluate it, which is fine for a compatibility shim.
__all__ = list(getattr(_xy_style, "__all__", []))  # pyright: ignore[reportUnsupportedDunderAll]
