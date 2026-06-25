"""XY session API.

The implementation still lives in :mod:`batplot.session` during the first
compatibility-preserving split. Keep this mode-owned module as the stable seam
for future extraction.
"""

from __future__ import annotations

from ... import session as _session

dump_session = _session._dump_session_impl
load_xy_session = _session._load_xy_session_impl

__all__ = ["dump_session", "load_xy_session"]
