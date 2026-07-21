"""Top-level routing for reloading saved ``.pkl`` sessions.

Extracted verbatim from ``batplot.batplot.batplot_main``. When the user runs
``batplot session.pkl`` this module loads the session, dispatches to the
matching interactive menu (XY / EC / operando+EC / CPC) and -- for legacy
sessions without a recognised ``kind`` -- reconstructs a minimal XY figure.

All collaborators are imported from their owning submodules so this module
does not depend on :mod:`batplot.batplot` (no circular import).
"""

from __future__ import annotations

import os
import sys
import pickle
from typing import Any, Tuple, cast

import numpy as np  # type: ignore
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.ticker import AutoMinorLocator, NullFormatter  # type: ignore[import-untyped]

from ..ec_common import _run_saved_dqdv_2d_companion
from .._mpl_backend import (
    ensure_gui_backend,
    hold_figure_open,
    is_interactive_backend,
    prime_interactive_figure,
    running_headless,
    warn_if_noninteractive,
)
from ..session import (
    load_xy_session,
    load_ec_session,
    load_operando_session,
    load_cpc_session,
    _apply_axes_bbox as _session_apply_axes_bbox,
    _try_extract_version_from_pickle,
    _get_current_numpy_version,
)
from ..plotting import update_labels
from ..utils import (
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
)
from ..ui import (
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    set_spine_side_color,
    finalize_spine_colors,
)
from .xy.interactive import interactive_menu, normalize_xy_menu_kwargs
from .electrochem.interactive import electrochem_interactive_menu

try:
    from .cpc.interactive import cpc_interactive_menu
except ImportError:
    cpc_interactive_menu = None

try:
    from .operando.interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None


_VALID_SESSION_KINDS = frozenset(
    {"histo", "ec_gc", "cpc", "operando_ec", "xy", "dqdv_2d_contour"}
)


def _is_valid_session_header(sess: object) -> bool:
    """Return True for legacy XY sessions and kind-tagged mode sessions."""
    if not isinstance(sess, dict):
        return False
    kind = sess.get("kind")
    if kind in _VALID_SESSION_KINDS:
        return True
    # Legacy XY / batplot sessions without an explicit kind field.
    return "version" in sess


def _load_session_dict_with_diagnostics(sess_path: str) -> tuple[dict | None, int | None]:
    """Load a session header dict, preserving the existing NumPy mismatch diagnostics."""
    try:
        with open(sess_path, 'rb') as f:
            sess = pickle.load(f)
        if not _is_valid_session_header(sess):
            print("Not a valid batplot session file.")
            return None, 1
        return sess, None
    except ModuleNotFoundError as e:
        # Handle numpy._core and other module import errors
        if '_core' in str(e) or 'numpy' in str(e).lower():
            # Try to extract version info before the error
            saved_versions = _try_extract_version_from_pickle(sess_path)
            current_numpy = _get_current_numpy_version()

            saved_numpy = saved_versions.get('numpy', 'unknown')

            print(f"\nERROR: NumPy version mismatch detected when loading: {sess_path}")
            print("This session was saved with a different NumPy version.")
            print()
            print(f"Session was saved with:  NumPy {saved_numpy}")
            print(f"Currently installed:     NumPy {current_numpy}")
            print()
            print("The error 'No module named numpy._core' indicates:")
            print("  - Session saved with NumPy 2.0+ but loading with NumPy <2.0, OR")
            print("  - Session saved with NumPy <2.0 but loading with NumPy 2.0+")
            print()
            print("Solutions:")
            if saved_numpy != 'unknown':
                print(f"  1. Install matching version: pip install 'numpy=={saved_numpy}'")
            else:
                print("  1. Try installing NumPy <2.0: pip install 'numpy<2.0'")
                print("     OR try installing NumPy 2.0+: pip install 'numpy>=2.0'")
            print("  2. Recreate the session from original data files")
        else:
            print(f"\nERROR: Module import error when loading: {sess_path}")
            print(f"Error: {e}")
            print("This usually indicates a package version mismatch.")
        return None, 1
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None, 1


def handle_session_reload(args) -> int:
    ensure_gui_backend(args)
    if not is_interactive_backend() and not running_headless():
        warn_if_noninteractive("saved session reload")
        return 1
    sess_path = args.files[0]
    if not os.path.isfile(sess_path):
        print(f"Session file not found: {sess_path}")
        exit(1)
    sess, session_error = _load_session_dict_with_diagnostics(sess_path)
    if session_error is not None:
        return session_error
    if sess is None:
        # Unreachable: the loader always pairs a None session with an error code.
        print("Not a valid batplot session file.")
        return 1
    # If it's an EC GC session, load and open EC interactive menu directly
    if isinstance(sess, dict) and sess.get('kind') == 'ec_gc':
        try:
            res = load_ec_session(sess_path)
            if not res:
                print("Failed to load EC session.")
                exit(1)
            # Multi-file session returns (fig, ax, None, file_data); single-file returns (fig, ax, cycle_lines)
            if len(res) == 4 and res[2] is None:
                fig, ax, _ignored, file_data = res
                prime_interactive_figure(fig)
                try:
                    fig._last_session_save_path = os.path.abspath(sess_path)
                except Exception:
                    pass
                try:
                    source_list = list(getattr(fig, '_bp_source_paths', []) or [])
                    sess_abs = os.path.abspath(sess_path)
                    if sess_abs not in source_list:
                        source_list.append(sess_abs)
                    fig._bp_source_paths = source_list
                except Exception:
                    pass
                try:
                    electrochem_interactive_menu(fig, ax, file_data=file_data)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
            else:
                fig, ax, cycle_lines = cast(Tuple[Any, Any, Any], res)
                prime_interactive_figure(fig)
                try:
                    fig._last_session_save_path = os.path.abspath(sess_path)
                except Exception:
                    pass
                try:
                    source_list = list(getattr(fig, '_bp_source_paths', []) or [])
                    sess_abs = os.path.abspath(sess_path)
                    if sess_abs not in source_list:
                        source_list.append(sess_abs)
                    fig._bp_source_paths = source_list
                except Exception:
                    pass
                try:
                    electrochem_interactive_menu(fig, ax, cycle_lines, file_path=sess_path)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
            try:
                _run_saved_dqdv_2d_companion(fig, sess_path)
            except Exception as _c2d:
                print(f"Saved dQ/dV 2D companion: {_c2d}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"EC session load failed: {e}")
            exit(1)

    # Standalone saved dQ/dV 2D contour (.pkl kind=dqdv_2d_contour)
    if isinstance(sess, dict) and sess.get('kind') == 'dqdv_2d_contour':
        try:
            from .electrochem.dqdv_2d import restore_dqdv_2d_companion_figure
            res = restore_dqdv_2d_companion_figure(sess)
            if not res:
                print("Failed to load dQ/dV 2D contour session.")
                exit(1)
            fig_d, ax_d, im_d, cbar_d = res
            prime_interactive_figure(fig_d)
            try:
                fig_d._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            try:
                if operando_ec_interactive_menu is not None:
                    operando_ec_interactive_menu(
                        fig_d, ax_d, im_d, cbar_d, None,
                        file_paths=[sess_path],
                    )
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"dQ/dV 2D contour session load failed: {e}")
            exit(1)

    # If it's an operando+EC session, load and open the combined interactive menu
    if isinstance(sess, dict) and sess.get('kind') == 'operando_ec':
        try:
            res = load_operando_session(sess_path)
            if not res:
                print("Failed to load operando+EC session.")
                exit(1)
            fig2, ax2, im2, cbar2, ec_ax2 = res
            prime_interactive_figure(fig2)
            # Seed last-session path so 'os' overwrite command is available immediately
            try:
                fig2._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            try:
                if operando_ec_interactive_menu is not None:
                    operando_ec_interactive_menu(fig2, ax2, im2, cbar2, ec_ax2)
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"Operando+EC session load failed: {e}")
            exit(1)

    # If it's a CPC session, load and open CPC interactive menu
    if isinstance(sess, dict) and sess.get('kind') == 'cpc':
        try:
            res = load_cpc_session(sess_path)
            if not res:
                print("Failed to load CPC session.")
                exit(1)
            fig_c, ax_c, ax2_c, sc_c, sc_d, sc_e, file_data = res
            prime_interactive_figure(fig_c)
            # Seed last-session path so 'os' overwrite command is available immediately
            try:
                fig_c._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            try:
                if cpc_interactive_menu is not None:
                    cpc_interactive_menu(fig_c, ax_c, ax2_c, sc_c, sc_d, sc_e, file_data=file_data)
            except Exception as _ie:
                print(f"CPC interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"CPC session load failed: {e}")
            exit(1)

    # If it's a histogram session, load and open histogram interactive menu
    if isinstance(sess, dict) and sess.get('kind') == 'histo':
        try:
            from .histo.session import load_histo_session
            from .histo.interactive import histo_interactive_menu
            from .histo.load import load_table

            res = load_histo_session(sess_path)
            if not res:
                print("Failed to load histogram session.")
                exit(1)
            fig_h, ax_h, state_h = res
            prime_interactive_figure(fig_h)
            try:
                fig_h._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            table_loader = None
            source = getattr(state_h, "source_path", "") or ""
            if source and os.path.isfile(source):
                table_loader = lambda src=source: load_table(src)
            try:
                histo_interactive_menu(fig_h, ax_h, state_h, table_loader=table_loader)
            except Exception as _ie:
                print(f"Histogram interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"Histogram session load failed: {e}")
            exit(1)

    # XY sessions include legacy files without a kind plus current kind='xy'.
    # Use the dedicated loader so saved full-range arrays stay available after load.
    if isinstance(sess, dict) and sess.get('kind') in (None, 'xy'):
        try:
            res = load_xy_session(sess_path)
            if not res:
                print("Failed to load XY session.")
                exit(1)
            fig_xy, ax_xy, menu_kwargs = res
            prime_interactive_figure(fig_xy)
            try:
                fig_xy._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            try:
                interactive_menu(fig_xy, ax_xy, **normalize_xy_menu_kwargs(menu_kwargs))
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"XY session load failed: {e}")
            exit(1)

    # All recognized kinds exit() above via dedicated loaders. Do not fall back to the
    # old inline XY reconstruct (removed 2026-07-14) — it was unreachable for valid
    # sessions and could mis-rebuild unknown headers that only contain ``version``.
    print("Not a recognized batplot session format.")
    return 1
