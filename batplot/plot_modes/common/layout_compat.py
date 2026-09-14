"""Layout fingerprints for style ``.bps`` / ``.bpsg`` import compatibility.

Styles must only apply when the live plot matches the saved layout (curve
count, stack/dual-y, CIF presence for XY geom, EC panel for operando, etc.).

Old styles without a ``layout`` block are inferred from existing keys when
possible; ambiguous families warn and allow (BC).
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence


LAYOUT_VERSION = 1


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def attach_layout(cfg: MutableMapping[str, Any], layout: Mapping[str, Any]) -> None:
    """Write a normalized ``layout`` block onto a style export dict."""
    out = {"version": LAYOUT_VERSION}
    for key, val in layout.items():
        if key == "version":
            continue
        if val is None:
            continue
        out[key] = val
    cfg["layout"] = out


def _print_reject(reason: str, *, silent: bool) -> bool:
    if not silent:
        print(f"Style/geometry layout mismatch: {reason}")
        print("Not applying style/geometry (layouts must match).")
    return False


# ---------------------------------------------------------------------------
# XY / 1D
# ---------------------------------------------------------------------------


def xy_layout_fingerprint(
    *,
    n_curves: int,
    stack: bool = False,
    dual_y: bool = False,
    txaxis: bool = False,
    has_cif: bool = False,
    ro_active: bool = False,
) -> Dict[str, Any]:
    return {
        "version": LAYOUT_VERSION,
        "mode": "xy",
        "n_curves": int(n_curves),
        "stack": bool(stack),
        "dual_y": bool(dual_y),
        "txaxis": bool(txaxis) if dual_y else False,
        "has_cif": bool(has_cif),
        "ro_active": bool(ro_active),
    }


def infer_xy_layout_from_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    """Build XY layout from ``layout`` block or legacy keys."""
    block = cfg.get("layout") if isinstance(cfg.get("layout"), dict) else {}
    lines = cfg.get("lines") if isinstance(cfg.get("lines"), list) else []
    right = cfg.get("right_y_curve_indices") or []
    try:
        dual_y = len(list(right)) > 0
    except Exception:
        dual_y = False
    if "dual_y" in block:
        dual_y = _as_bool(block.get("dual_y"), dual_y)

    cif = cfg.get("cif") if isinstance(cfg.get("cif"), dict) else {}
    cif_ticks = cfg.get("cif_ticks") if isinstance(cfg.get("cif_ticks"), list) else []
    has_cif = bool(cif_ticks) or bool(cif.get("files")) or bool(cif.get("tick_series"))
    if "has_cif" in block:
        has_cif = _as_bool(block.get("has_cif"), has_cif)

    n_curves = _as_int(block.get("n_curves"), len(lines) if lines else 0)
    stack = _as_bool(block.get("stack"), False)
    txaxis = _as_bool(block.get("txaxis"), _as_bool(cfg.get("txaxis"), False))
    # Top-level ``ro_active`` remains authoritative (historical key / tests).
    if "ro_active" in cfg:
        ro_active = _as_bool(cfg.get("ro_active"), False)
    else:
        ro_active = _as_bool(block.get("ro_active"), False)
    return xy_layout_fingerprint(
        n_curves=n_curves,
        stack=stack,
        dual_y=dual_y,
        txaxis=txaxis,
        has_cif=has_cif,
        ro_active=ro_active,
    )


def live_xy_layout(
    *,
    fig: Any,
    args: Any = None,
    n_curves: Optional[int] = None,
    labels: Optional[Sequence[Any]] = None,
    y_data_list: Optional[Sequence[Any]] = None,
    cif_tick_series: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    if n_curves is None:
        if y_data_list is not None:
            n_curves = len(y_data_list)
        elif labels is not None:
            n_curves = len(labels)
        else:
            lines = getattr(fig, "_xy_lines_by_curve", None)
            n_curves = len(lines) if lines is not None else 0
    stack = bool(getattr(args, "stack", False)) if args is not None else False
    right = getattr(fig, "_xy_right_y_curve_indices", frozenset()) or frozenset()
    dual_y = len(right) > 0
    txaxis = bool(getattr(fig, "_xy_use_top_x", False))
    has_cif = bool(cif_tick_series)
    ro_active = bool(getattr(fig, "_ro_active", False))
    return xy_layout_fingerprint(
        n_curves=int(n_curves or 0),
        stack=stack,
        dual_y=dual_y,
        txaxis=txaxis,
        has_cif=has_cif,
        ro_active=ro_active,
    )


def xy_layouts_compatible(
    file_layout: Mapping[str, Any],
    live_layout: Mapping[str, Any],
    *,
    kind: str = "",
    silent: bool = False,
) -> bool:
    """Hard-reject XY style when structural layout differs."""
    if _as_bool(file_layout.get("ro_active")) != _as_bool(live_layout.get("ro_active")):
        return _print_reject(
            "swapped axes (--ro) differ between style and live plot",
            silent=silent,
        )
    file_n = _as_int(file_layout.get("n_curves"), 0)
    live_n = _as_int(live_layout.get("n_curves"), 0)
    if file_n > 0 and live_n > 0 and file_n != live_n:
        return _print_reject(
            f"curve count differs (style={file_n}, live={live_n})",
            silent=silent,
        )
    if _as_bool(file_layout.get("stack")) != _as_bool(live_layout.get("stack")):
        return _print_reject(
            "stack vs overlay layout differs",
            silent=silent,
        )
    if _as_bool(file_layout.get("dual_y")) != _as_bool(live_layout.get("dual_y")):
        return _print_reject(
            "dual-Y (--ry) layout differs",
            silent=silent,
        )
    if _as_bool(file_layout.get("dual_y")) and (
        _as_bool(file_layout.get("txaxis")) != _as_bool(live_layout.get("txaxis"))
    ):
        return _print_reject(
            "top-X for dual-Y (--txaxis) differs",
            silent=silent,
        )
    # CIF presence is required for style+geometry (embedded peaks / stack offsets).
    if str(kind or "") == "xy_style_geom":
        if _as_bool(file_layout.get("has_cif")) != _as_bool(live_layout.get("has_cif")):
            return _print_reject(
                "CIF presence differs (style+geometry requires both with or both without CIF)",
                silent=silent,
            )
    return True


# ---------------------------------------------------------------------------
# EC
# ---------------------------------------------------------------------------


def ec_layout_fingerprint(
    *,
    is_multi_file: bool = False,
    n_files: int = 1,
    plot_family: str = "gc",
    dual_x: bool = False,
    ro_active: bool = False,
) -> Dict[str, Any]:
    return {
        "version": LAYOUT_VERSION,
        "mode": "ec",
        "is_multi_file": bool(is_multi_file),
        "n_files": int(n_files),
        "plot_family": str(plot_family or "gc"),
        "dual_x": bool(dual_x),
        "ro_active": bool(ro_active),
    }


def infer_ec_layout_from_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    block = cfg.get("layout") if isinstance(cfg.get("layout"), dict) else {}
    names = cfg.get("file_display_names")
    vis = cfg.get("file_visibility")
    n_files = 1
    if isinstance(names, list) and len(names) > 1:
        n_files = len(names)
    elif isinstance(vis, list) and len(vis) > 1:
        n_files = len(vis)
    if "n_files" in block:
        n_files = _as_int(block.get("n_files"), n_files)
    is_multi = _as_bool(block.get("is_multi_file"), n_files > 1)

    dual = False
    xdual = cfg.get("xaxis_dual")
    if isinstance(xdual, dict) and str(xdual.get("mode", "")).lower() == "dual":
        dual = True
    if "dual_x" in block:
        dual = _as_bool(block.get("dual_x"), dual)

    family = str(block.get("plot_family") or "").lower()
    if family not in ("gc", "cv", "dqdv"):
        family = ""
        if isinstance(cfg.get("_dqdv_smooth_settings"), dict) or cfg.get("is_dqdv"):
            family = "dqdv"

    return ec_layout_fingerprint(
        is_multi_file=is_multi,
        n_files=n_files,
        plot_family=family or "unknown",
        dual_x=dual,
        ro_active=(
            _as_bool(cfg.get("ro_active"), False)
            if "ro_active" in cfg
            else _as_bool(block.get("ro_active"), False)
        ),
    )


def live_ec_layout(
    *,
    fig: Any,
    is_multi_file: bool = False,
    file_data: Optional[Sequence[Any]] = None,
    is_dqdv: bool = False,
    is_cv: bool = False,
) -> Dict[str, Any]:
    n_files = len(file_data) if file_data is not None else (2 if is_multi_file else 1)
    if is_multi_file and n_files < 2:
        n_files = 2
    if is_dqdv:
        family = "dqdv"
    elif is_cv:
        family = "cv"
    else:
        family = "gc"
    dual = False
    try:
        dual = bool(getattr(fig, "_ec_dual_axis", False)) or (
            getattr(fig, "_xaxis_dual_mode", None) == "dual"
        )
    except Exception:
        dual = False
    xdual = getattr(fig, "_ec_xaxis_dual", None)
    if isinstance(xdual, dict) and str(xdual.get("mode", "")).lower() == "dual":
        dual = True
    return ec_layout_fingerprint(
        is_multi_file=bool(is_multi_file) or n_files > 1,
        n_files=max(1, int(n_files)),
        plot_family=family,
        dual_x=dual,
        ro_active=bool(getattr(fig, "_ro_active", False)),
    )


def ec_layouts_compatible(
    file_layout: Mapping[str, Any],
    live_layout: Mapping[str, Any],
    *,
    silent: bool = False,
) -> bool:
    if _as_bool(file_layout.get("ro_active")) != _as_bool(live_layout.get("ro_active")):
        return _print_reject("swapped axes (--ro) differ", silent=silent)
    if _as_bool(file_layout.get("is_multi_file")) != _as_bool(live_layout.get("is_multi_file")):
        return _print_reject("single-file vs multi-file layout differs", silent=silent)
    if _as_bool(file_layout.get("dual_x")) != _as_bool(live_layout.get("dual_x")):
        return _print_reject("dual X-axis (capacity/ions) layout differs", silent=silent)
    ff = str(file_layout.get("plot_family") or "").lower()
    lf = str(live_layout.get("plot_family") or "").lower()
    if ff in ("gc", "cv", "dqdv") and lf in ("gc", "cv", "dqdv") and ff != lf:
        return _print_reject(
            f"EC plot family differs (style={ff}, live={lf})",
            silent=silent,
        )
    return True


# ---------------------------------------------------------------------------
# CPC
# ---------------------------------------------------------------------------


def cpc_layout_fingerprint(
    *,
    is_multi_file: bool = False,
    n_files: int = 1,
    ro_active: bool = False,
) -> Dict[str, Any]:
    return {
        "version": LAYOUT_VERSION,
        "mode": "cpc",
        "is_multi_file": bool(is_multi_file),
        "n_files": int(n_files),
        "ro_active": bool(ro_active),
    }


def infer_cpc_layout_from_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    block = cfg.get("layout") if isinstance(cfg.get("layout"), dict) else {}
    multi = cfg.get("multi_files")
    n_files = len(multi) if isinstance(multi, list) else 1
    if "n_files" in block:
        n_files = _as_int(block.get("n_files"), n_files)
    is_multi = _as_bool(block.get("is_multi_file"), n_files > 1)
    return cpc_layout_fingerprint(
        is_multi_file=is_multi,
        n_files=max(1, n_files),
        ro_active=(
            _as_bool(cfg.get("ro_active"), False)
            if "ro_active" in cfg
            else _as_bool(block.get("ro_active"), False)
        ),
    )


def live_cpc_layout(
    *,
    fig: Any,
    file_data: Optional[Sequence[Any]] = None,
    is_multi_file: bool = False,
) -> Dict[str, Any]:
    n_files = len(file_data) if file_data is not None else (2 if is_multi_file else 1)
    if is_multi_file and n_files < 2:
        n_files = 2
    return cpc_layout_fingerprint(
        is_multi_file=bool(is_multi_file) or n_files > 1,
        n_files=max(1, int(n_files)),
        ro_active=bool(getattr(fig, "_ro_active", False)),
    )


def cpc_layouts_compatible(
    file_layout: Mapping[str, Any],
    live_layout: Mapping[str, Any],
    *,
    silent: bool = False,
) -> bool:
    if _as_bool(file_layout.get("ro_active")) != _as_bool(live_layout.get("ro_active")):
        return _print_reject("swapped axes (--ro) differ", silent=silent)
    if _as_bool(file_layout.get("is_multi_file")) != _as_bool(live_layout.get("is_multi_file")):
        return _print_reject("single-file vs multi-file layout differs", silent=silent)
    return True


# ---------------------------------------------------------------------------
# Operando
# ---------------------------------------------------------------------------


def operando_layout_fingerprint(
    *,
    has_ec_panel: bool = False,
    is_dqdv_2d: bool = False,
) -> Dict[str, Any]:
    return {
        "version": LAYOUT_VERSION,
        "mode": "operando",
        "has_ec_panel": bool(has_ec_panel),
        "is_dqdv_2d": bool(is_dqdv_2d),
    }


def infer_operando_layout_from_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    block = cfg.get("layout") if isinstance(cfg.get("layout"), dict) else {}
    geom = cfg.get("geometry") if isinstance(cfg.get("geometry"), dict) else {}
    ec = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
    if "has_ec_panel" in block:
        has_ec = _as_bool(block.get("has_ec_panel"), False)
    else:
        has_ec = False
        ec_w = geom.get("ec_w_in")
        try:
            has_ec = ec_w is not None and float(ec_w) > 0
        except (TypeError, ValueError):
            has_ec = False
        if not has_ec and ec:
            # Prefer real EC chrome/artists — bare y_mode="time" is always present.
            has_ec = bool(ec.get("wasd_state") or ec.get("spines") or ec.get("curve"))
    is_dqdv = _as_bool(block.get("is_dqdv_2d"), bool(cfg.get("dqdv_2d")))
    return operando_layout_fingerprint(has_ec_panel=has_ec, is_dqdv_2d=is_dqdv)


def live_operando_layout(*, fig: Any, ec_ax: Any = None) -> Dict[str, Any]:
    return operando_layout_fingerprint(
        has_ec_panel=ec_ax is not None,
        is_dqdv_2d=bool(getattr(fig, "_is_dqdv_2d_contour", False)),
    )


def operando_layouts_compatible(
    file_layout: Mapping[str, Any],
    live_layout: Mapping[str, Any],
    *,
    silent: bool = False,
) -> bool:
    if _as_bool(file_layout.get("is_dqdv_2d")) != _as_bool(live_layout.get("is_dqdv_2d")):
        return _print_reject(
            "dQ/dV 2D contour vs operando XRD layout differs",
            silent=silent,
        )
    if _as_bool(file_layout.get("has_ec_panel")) != _as_bool(live_layout.get("has_ec_panel")):
        return _print_reject(
            "EC side-panel presence differs (both with or both without EC)",
            silent=silent,
        )
    return True


# ---------------------------------------------------------------------------
# Histo
# ---------------------------------------------------------------------------


def histo_layout_fingerprint(*, has_density: bool = False) -> Dict[str, Any]:
    return {
        "version": LAYOUT_VERSION,
        "mode": "histo",
        "has_density": bool(has_density),
    }


def infer_histo_layout_from_cfg(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    block = cfg.get("layout") if isinstance(cfg.get("layout"), dict) else {}
    style = cfg.get("style") if isinstance(cfg.get("style"), dict) else {}
    setup = cfg.get("setup") if isinstance(cfg.get("setup"), dict) else {}
    has_density = _as_bool(
        block.get("has_density"),
        _as_bool(style.get("show_density"), _as_bool(setup.get("show_density"), False)),
    )
    return histo_layout_fingerprint(has_density=has_density)


def live_histo_layout(*, state: Any = None) -> Dict[str, Any]:
    has_density = False
    try:
        setup = getattr(state, "setup", None)
        has_density = bool(getattr(setup, "show_density", False))
    except Exception:
        has_density = False
    return histo_layout_fingerprint(has_density=has_density)


def histo_layouts_compatible(
    file_layout: Mapping[str, Any],
    live_layout: Mapping[str, Any],
    *,
    silent: bool = False,
) -> bool:
    if _as_bool(file_layout.get("has_density")) != _as_bool(live_layout.get("has_density")):
        return _print_reject(
            "density-curve layout differs (both with or both without density)",
            silent=silent,
        )
    return True


__all__ = [
    "LAYOUT_VERSION",
    "attach_layout",
    "cpc_layout_fingerprint",
    "cpc_layouts_compatible",
    "ec_layout_fingerprint",
    "ec_layouts_compatible",
    "histo_layout_fingerprint",
    "histo_layouts_compatible",
    "infer_cpc_layout_from_cfg",
    "infer_ec_layout_from_cfg",
    "infer_histo_layout_from_cfg",
    "infer_operando_layout_from_cfg",
    "infer_xy_layout_from_cfg",
    "live_cpc_layout",
    "live_ec_layout",
    "live_histo_layout",
    "live_operando_layout",
    "live_xy_layout",
    "operando_layout_fingerprint",
    "operando_layouts_compatible",
    "xy_layout_fingerprint",
    "xy_layouts_compatible",
]
