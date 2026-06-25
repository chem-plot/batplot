"""Operando session API.

The implementation still lives in :mod:`batplot.session` during the first
compatibility-preserving split. Keep this mode-owned module as the stable seam
for future extraction.
"""

from __future__ import annotations

from ... import session as _session

dump_operando_session = _session._dump_operando_session_impl
load_operando_session = _session._load_operando_session_impl

__all__ = ["dump_operando_session", "load_operando_session"]
