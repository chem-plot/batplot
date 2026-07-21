"""Shared electrochemistry routing helpers.

This module holds small helpers that are used by several electrochemistry
plotting routes (GC, CV, dQ/dV, CPC) as well as the session-reload path.
They were extracted verbatim from ``batplot.batplot`` so that the
mode-specific routing modules under ``batplot.plot_modes`` can import them
without creating a circular dependency back to the top-level dispatcher.
"""

from __future__ import annotations

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

# Optional operando interactive menu (used by the saved dQ/dV 2D companion).
try:
    from .plot_modes.operando.interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None


_EC_DEFAULT_FIGSIZE = (10.0, 6.0)
_EC_DEFAULT_LAYOUT = {'left': 0.12, 'right': 0.95, 'top': 0.88, 'bottom': 0.15}
# CPC shares the same canvas and plot-frame defaults as GC/CV/dQ/dV.
_CPC_DEFAULT_LAYOUT = _EC_DEFAULT_LAYOUT
_EC_DEFAULT_FRAME_SIZE = (
    _EC_DEFAULT_FIGSIZE[0] * (_EC_DEFAULT_LAYOUT['right'] - _EC_DEFAULT_LAYOUT['left']),
    _EC_DEFAULT_FIGSIZE[1] * (_EC_DEFAULT_LAYOUT['top'] - _EC_DEFAULT_LAYOUT['bottom']),
)


def _figsize_for_frame(layout: dict[str, float]) -> tuple[float, float]:
    """Return canvas size needed for the shared default electrochem frame."""
    width_frac = layout['right'] - layout['left']
    height_frac = layout['top'] - layout['bottom']
    return (_EC_DEFAULT_FRAME_SIZE[0] / width_frac, _EC_DEFAULT_FRAME_SIZE[1] / height_frac)


def _default_ec_figsize() -> tuple[float, float]:
    return _figsize_for_frame(_EC_DEFAULT_LAYOUT)


def _default_cpc_figsize() -> tuple[float, float]:
    """Alias for :func:`_default_ec_figsize` (GC/CV/dQ/dV/CPC share one default)."""
    return _default_ec_figsize()


def _apply_default_ec_layout(fig, *, cpc: bool = False) -> None:
    """Apply the default electrochem layout (same for GC, CV, dQ/dV, and CPC)."""
    del cpc  # kept for backward compatibility; CPC uses the same layout as other EC modes
    fig.subplots_adjust(**_EC_DEFAULT_LAYOUT)


def _resolve_mass(mass_arg, file_idx: int = 0):
    """Return mass (mg) for the file at *file_idx* from the --mass argument.

    Supports both the legacy single-value form (--mass 3.52) and the new
    per-file form (--mass 3.52 4.1 5.0).  When a single value is supplied it
    is applied to every file.  When multiple values are given they map 1-to-1
    with the input files; if there are fewer values than files the last value
    is reused for any extra files.

    Returns a float or None.
    """
    if mass_arg is None:
        return None
    if isinstance(mass_arg, (int, float)):
        return float(mass_arg)
    if isinstance(mass_arg, list):
        if len(mass_arg) == 1:
            return float(mass_arg[0])
        if file_idx < len(mass_arg):
            return float(mass_arg[file_idx])
        return float(mass_arg[-1])
    return None


def _run_saved_dqdv_2d_companion(fig, sess_path: str) -> None:
    """If load_ec_session attached a saved dQ/dV 2D bundle, run its operando menu after the EC menu."""
    b = getattr(fig, "_dqdv_2d_companion_bundle", None)
    if not b or len(b) < 4:
        return
    cfig, cax, im, cbar = b[0], b[1], b[2], b[3]
    if operando_ec_interactive_menu is None:
        print("Operando interactive not available; skipping saved dQ/dV 2D map.")
        return
    paths = list(getattr(fig, "_bp_source_paths", []) or [])
    if not paths:
        paths = [sess_path]
    print("\nSession includes a saved dQ/dV 2D map — opening contour interactive menu (q exits to finish).")
    try:
        plt.show(block=False)
    except Exception:
        pass
    try:
        operando_ec_interactive_menu(cfig, cax, im, cbar, None, file_paths=paths, canvas_mode=False)
    except Exception as e:
        print(f"Saved dQ/dV 2D map menu failed: {e}")
    finally:
        # Persist companion edits back into the parent EC session pickle.
        try:
            if cfig is not None and plt.fignum_exists(getattr(cfig, "number", -1)):
                from .plot_modes.electrochem.dqdv_2d import build_dqdv_2d_snapshot

                v_lo = float(getattr(cfig, "_dqdv_2d_v_lo", 0.0))
                v_hi = float(getattr(cfig, "_dqdv_2d_v_hi", 1.0))
                row_labels = [str(s) for s in (getattr(cfig, "_dqdv_2d_row_labels", None) or [])]
                zlab = str(getattr(cfig, "_dqdv_2d_zlabel", "dQ/dV"))
                snap = build_dqdv_2d_snapshot(cfig, cax, im, v_lo, v_hi, row_labels, zlab, cbar)
                if snap is not None:
                    try:
                        fig._dqdv_2d_snapshot = snap
                    except Exception:
                        pass
                    if _merge_dqdv_2d_into_ec_session(sess_path, snap):
                        print(f"Updated dQ/dV 2D map in session: {sess_path}")
                    else:
                        print("Warning: dQ/dV 2D map edits were not written back to the EC session file.")
                else:
                    print("Warning: could not build dQ/dV 2D snapshot after companion menu.")
        except Exception as e:
            print(f"Warning: could not save dQ/dV 2D map back into session: {e}")
        try:
            plt.close(cfig)
        except Exception:
            pass
        try:
            delattr(fig, "_dqdv_2d_companion_bundle")
        except Exception:
            pass


def _merge_dqdv_2d_into_ec_session(sess_path: str, snap: dict) -> bool:
    """Write ``snap`` into an existing ``ec_gc`` pickle as ``dqdv_2d``. Returns True on success."""
    import os
    import pickle

    if not sess_path or not isinstance(snap, dict) or snap.get("Z") is None:
        return False
    if not os.path.isfile(sess_path):
        return False
    try:
        with open(sess_path, "rb") as fh:
            sess = pickle.load(fh)
        if not isinstance(sess, dict) or sess.get("kind") != "ec_gc":
            return False
        sess["dqdv_2d"] = snap
        try:
            from .session import _package_versions_stamp

            sess["package_versions"] = _package_versions_stamp()
        except Exception:
            pass
        with open(sess_path, "wb") as fh:
            pickle.dump(sess, fh)
        return True
    except Exception:
        return False
