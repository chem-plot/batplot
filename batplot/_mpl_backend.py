"""Matplotlib backend selection for batplot CLI and interactive sessions.

Imported early from :mod:`batplot.cli` so pytest/CI on Windows never fall back
to Tk when ``MPLBACKEND=Agg`` is set explicitly in the environment.

When the user has not set ``MPLBACKEND``, we start on Agg for safe imports but
may switch to a GUI backend before opening interactive windows (``.pkl`` reload,
``--gc --i``, ``--canvas``, etc.).
"""

from __future__ import annotations

import importlib.util
import os
import sys

_USER_SET_MPLBACKEND = "MPLBACKEND" in os.environ
_DEFAULT_BACKEND = os.environ.get("MPLBACKEND", "Agg")

import matplotlib as _mpl

_mpl.use(_DEFAULT_BACKEND, force=True)

_INTERACTIVE_BACKENDS = frozenset(
    {
        "macosx",
        "tkagg",
        "qt5agg",
        "qt4agg",
        "qtagg",
        "wxagg",
        "gtk3agg",
        "gtk4agg",
        "wx",
        "qt",
        "gtk",
        "gtk3",
        "gtk4",
    }
)


def _is_noninteractive_backend(name: str | None) -> bool:
    if not isinstance(name, str):
        return False
    low = name.lower()
    if low in _INTERACTIVE_BACKENDS:
        return False
    return ("agg" in low) or ("inline" in low) or (low in {"pdf", "ps", "svg", "template"})


def is_interactive_backend() -> bool:
    """Return True when the active Matplotlib backend can open a GUI window."""
    try:
        return not _is_noninteractive_backend(_mpl.get_backend())
    except Exception:
        return False


def _headless_context() -> bool:
    """True when batplot must stay on a non-interactive backend (CI/pytest)."""
    if os.environ.get("BATPLOT_HEADLESS", "").lower() in ("1", "true", "yes"):
        return True
    if os.environ.get("CI", "").lower() in ("1", "true", "yes"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    if "pytest" in sys.modules:
        return True
    return False


def running_headless() -> bool:
    """True under pytest, CI, or when ``BATPLOT_HEADLESS`` is set."""
    return _headless_context()


def wants_interactive_window(args) -> bool:
    """Return True when this CLI invocation should open an interactive figure."""
    if getattr(args, "all", None) is not None:
        return False
    files = getattr(args, "files", None) or []
    if any(str(f).lower().endswith(".pkl") for f in files):
        return True
    if getattr(args, "canvas", False):
        return True
    if getattr(args, "interactive", False):
        return True
    # Headless export: mode flags with --out/--savefig do not need a GUI window.
    if getattr(args, "savefig", False) or getattr(args, "out", None):
        return False
    for attr in ("operando", "contour", "gc", "cv", "dqdv", "cpc", "epc"):
        if getattr(args, attr, False):
            return True
    return False


def _should_respect_env_agg() -> bool:
    """Keep Agg when the environment requested it and we are in headless context."""
    if not _USER_SET_MPLBACKEND:
        return False
    env_be = os.environ.get("MPLBACKEND")
    if not env_be or not _is_noninteractive_backend(env_be):
        return False
    return _headless_context()


def _has_qt_bindings() -> bool:
    for mod in ("PyQt6", "PyQt5", "PySide6", "PySide2"):
        if importlib.util.find_spec(mod) is not None:
            return True
    return False


def _gui_backend_order() -> list[str]:
    if sys.platform == "darwin":
        return ["MacOSX", "TkAgg", "QtAgg"]
    if sys.platform.startswith("win"):
        return ["TkAgg", "QtAgg"]
    return ["TkAgg", "QtAgg", "Gtk4Agg", "Gtk3Agg"]


def _backend_can_be_tried(name: str) -> bool:
    if name == "TkAgg":
        return importlib.util.find_spec("tkinter") is not None
    if name == "QtAgg":
        return _has_qt_bindings()
    return True


def ensure_gui_backend(args=None) -> bool:
    """Switch from Agg to a GUI backend when an interactive window is expected.

    Returns True when the active backend is interactive (or was switched to one).
    Honors ``MPLBACKEND=Agg`` only under pytest/CI; interactive CLI use (``--i``,
    ``.pkl`` reload) overrides an inherited Agg default from conda/shell profiles.
    """
    if args is not None and not wants_interactive_window(args):
        return is_interactive_backend()

    if _should_respect_env_agg():
        return False

    if _USER_SET_MPLBACKEND:
        env_be = os.environ.get("MPLBACKEND")
        if env_be and not _is_noninteractive_backend(env_be):
            return True

    if is_interactive_backend():
        return True

    for cand in _gui_backend_order():
        if not _backend_can_be_tried(cand):
            continue
        try:
            _mpl.use(cand, force=True)
            if is_interactive_backend():
                return True
        except Exception:
            continue
    return False


def _one_line_backend_workaround() -> str:
    """Return a copy-paste command prefix for the current platform."""
    if sys.platform == "darwin":
        return "MPLBACKEND=MacOSX batplot ..."
    if sys.platform.startswith("win"):
        return 'set MPLBACKEND=TkAgg  (cmd)  or  $env:MPLBACKEND="TkAgg"  (PowerShell), then batplot ...'
    return "MPLBACKEND=TkAgg batplot ..."


def _print_interactive_backend_help(context: str = "interactive menu") -> None:
    """User-facing recovery steps when no GUI window can be opened."""
    try:
        backend = _mpl.get_backend()
    except Exception:
        backend = "unknown"
    try:
        from . import __version__ as _bp_version
    except Exception:
        _bp_version = "latest"

    print()
    print("Interactive plotting needs a display window, but batplot could not open one.")
    print(f"(Matplotlib backend: {backend})")
    if context:
        print(f"This affects: {context}.")
    print()
    print("Try these steps, in order:")
    print("  1. Upgrade batplot (fixes most cases):")
    print("       pip install --upgrade batplot")
    print(f"     You need v1.8.45 or newer (installed: {_bp_version}).")
    print("  2. If you cannot upgrade yet, force a GUI backend for this session:")
    print(f"       {_one_line_backend_workaround()}")
    print("  3. To save a figure without the interactive menu:")
    print("       batplot ... --out figure.png   (omit --i)")
    print()
    print("Advanced: if MPLBACKEND=Agg is set in your shell or conda env, unset it or override")
    print("as in step 2. On headless servers (SSH with no display), use --out instead of --i.")
    print()


def warn_if_noninteractive(context: str = "interactive menu") -> bool:
    """Print a helpful message when the backend cannot show a window."""
    if is_interactive_backend():
        return True
    _print_interactive_backend_help(context)
    return False


def require_interactive_display(
    args=None,
    *,
    context: str = "interactive menu",
    export_hint: str | None = None,
) -> bool:
    """Ensure a GUI backend, warn if unavailable, return True when display is possible."""
    ensure_gui_backend(args)
    if is_interactive_backend():
        return True
    warn_if_noninteractive(context)
    return False


def show_figure_if_possible(args=None, *, block: bool = False) -> bool:
    """Show the current figure when the backend supports windows."""
    ensure_gui_backend(args)
    if not is_interactive_backend():
        if args is not None and not (getattr(args, "savefig", False) or getattr(args, "out", None)):
            print("No display window available. Save the figure with: batplot ... --out figure.png")
        return False
    import matplotlib.pyplot as plt

    plt.show(block=block)
    return True
