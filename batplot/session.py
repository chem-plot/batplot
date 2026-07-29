"""Session helpers for batplot interactive mode.

Public save/load APIs live here for backward compatibility. Mode-specific
implementations are owned by:

- ``batplot.plot_modes.xy.session``
- ``batplot.plot_modes.electrochem.session``
- ``batplot.plot_modes.cpc.session``
- ``batplot.plot_modes.operando.session``

Shared version/tick/bbox helpers live in
``batplot.plot_modes.common.session_helpers`` and are re-exported below.
"""

from __future__ import annotations

# Shared helpers (re-exported for batplot.py / session_routing / tests).
from .plot_modes.common.session_helpers import (  # noqa: F401
    _try_extract_version_from_pickle,
    _package_versions_stamp,
    _get_current_numpy_version,
    _current_tick_width,
    _current_tick_length,
    _apply_session_tick_lengths,
    _apply_axes_bbox,
    _capture_session_tick_locator,
    _restore_session_tick_locator,
)


# Public facade: stable batplot.session API → mode-owned implementations.

def dump_session(*args, **kwargs):
    from .plot_modes.xy.session import dump_session as _dump
    return _dump(*args, **kwargs)


def load_xy_session(*args, **kwargs):
    from .plot_modes.xy.session import load_xy_session as _load
    return _load(*args, **kwargs)


def dump_ec_session(*args, **kwargs):
    from .plot_modes.electrochem.session import dump_ec_session as _dump
    return _dump(*args, **kwargs)


def load_ec_session(*args, **kwargs):
    from .plot_modes.electrochem.session import load_ec_session as _load
    return _load(*args, **kwargs)


def dump_cpc_session(*args, **kwargs):
    from .plot_modes.cpc.session import dump_cpc_session as _dump
    return _dump(*args, **kwargs)


def load_cpc_session(*args, **kwargs):
    from .plot_modes.cpc.session import load_cpc_session as _load
    return _load(*args, **kwargs)


def dump_operando_session(*args, **kwargs):
    from .plot_modes.operando.session import dump_operando_session as _dump
    return _dump(*args, **kwargs)


def load_operando_session(*args, **kwargs):
    from .plot_modes.operando.session import load_operando_session as _load
    return _load(*args, **kwargs)


def __getattr__(name: str):
    """Lazy private impl aliases for mode-owned sessions (avoid import cycles)."""
    if name == "_dump_session_impl":
        from .plot_modes.xy.session import dump_session as _dump

        return _dump
    if name == "_load_xy_session_impl":
        from .plot_modes.xy.session import load_xy_session as _load

        return _load
    if name == "_dump_ec_session_impl":
        from .plot_modes.electrochem.session import dump_ec_session as _dump

        return _dump
    if name == "_load_ec_session_impl":
        from .plot_modes.electrochem.session import load_ec_session as _load

        return _load
    if name == "_dump_cpc_session_impl":
        from .plot_modes.cpc.session import dump_cpc_session as _dump

        return _dump
    if name == "_load_cpc_session_impl":
        from .plot_modes.cpc.session import load_cpc_session as _load

        return _load
    if name == "_dump_operando_session_impl":
        from .plot_modes.operando.session import dump_operando_session as _dump

        return _dump
    if name == "_load_operando_session_impl":
        from .plot_modes.operando.session import load_operando_session as _load

        return _load
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
