"""Compatibility wrappers for legacy ``batplot.modes`` imports.

The active CLI dispatcher lives in :mod:`batplot.batplot`.  This module keeps
older direct imports working without carrying a second copy of mode logic.
"""

from __future__ import annotations

import warnings


def _warn_legacy_modes() -> None:
    warnings.warn(
        "batplot.modes is a compatibility wrapper; use batplot.batplot for the active dispatcher.",
        DeprecationWarning,
        stacklevel=2,
    )


def handle_cv_mode(args) -> int:
    """Run the active CV mode handler for legacy callers."""
    _warn_legacy_modes()
    from .batplot import _handle_cv_mode

    return _handle_cv_mode(args)


def handle_gc_mode(args) -> int:
    """Legacy placeholder for the removed duplicate GC implementation."""
    _warn_legacy_modes()
    raise RuntimeError(
        "batplot.modes.handle_gc_mode no longer carries duplicate GC logic. "
        "Use the batplot CLI entry point instead."
    )


__all__ = ["handle_cv_mode", "handle_gc_mode"]
