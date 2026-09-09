"""XRD file conversion utilities for batplot (``--convert``).

Converts powder-diffraction x-columns among **2θ**, **Q**, and **d**, or
between two wavelengths (2θ@λ₁ → 2θ@λ₂). Writes into a ``converted/``
subfolder next to each input file.

CLI examples
------------
    batplot folder --ext .xy --convert 0.26 q
    batplot folder --ext xy --convert 2theta q --wl 0.26 --convert-ext .qye
    batplot data.qye --convert q d
    batplot data.xy --convert d 2theta --wl 1.5406 --convert-ext .xy
"""

from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np

from .plot_modes.xy.axis_units import convert_x_array
from .readers import loadtxt_with_decimal_comma

# Default output extensions when ``--convert-ext`` is not set.
_DEFAULT_OUT_EXT = {
    "Q": ".qye",
    "d": ".xy",
    "2theta": ".xy",
}

_UNIT_ALIASES = {
    "q": "Q",
    "d": "d",
    "2theta": "2theta",
    "2th": "2theta",
    "tth": "2theta",
    "two_theta": "2theta",
    "twotheta": "2theta",
    "2θ": "2theta",
}


def normalize_extension(raw: str | None) -> str | None:
    """Normalize a user extension token to ``.xyz`` (lowercase) or None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("*."):
        s = s[1:]
    if not s.startswith("."):
        s = "." + s
    return s.lower()


def parse_convert_token(token: str) -> tuple[str, Optional[str], Optional[float]]:
    """Parse one ``--convert`` argument into ``(kind, unit|None, wl|None)``.

    ``kind`` is ``"unit"`` (second value is ``Q``/``d``/``2theta``) or ``"wl"``
    (third value is wavelength; implies 2θ at that λ).
    """
    return _parse_token(token)


def _parse_token(token: str) -> tuple[str, str, Optional[float]]:
    """Return ``(kind, unit_or_empty, wl_or_None)``.

    kind is ``"unit"`` or ``"wl"``. For ``unit``, second value is the mode.
    For ``wl``, second value is ``"2theta"`` and third is λ.
    """
    raw = str(token).strip()
    key = raw.lower()
    if key in _UNIT_ALIASES:
        return ("unit", _UNIT_ALIASES[key], None)
    try:
        wl = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid --convert token {token!r}. "
            "Use a wavelength (e.g. 1.54), or a unit: q, d, 2theta "
            "(aliases: 2th, tth, two_theta)."
        ) from exc
    if not np.isfinite(wl) or wl <= 0:
        raise ValueError(f"Wavelength must be a positive finite number, got {token!r}")
    return ("wl", "2theta", float(wl))


def resolve_conversion(
    from_param: str,
    to_param: str,
    *,
    wl_fallback: Optional[float] = None,
) -> tuple[str, str, Optional[float], Optional[float]]:
    """Resolve ``--convert FROM TO`` into ``(from_mode, to_mode, from_wl, to_wl)``.

    ``from_wl`` / ``to_wl`` are only set when that side is 2θ and a wavelength
    is known (numeric convert token and/or ``--wl``).
    """
    f_kind, f_mode, f_wl = _parse_token(from_param)
    t_kind, t_mode, t_wl = _parse_token(to_param)

    if f_kind == "unit" and f_mode == "2theta":
        f_wl = float(wl_fallback) if wl_fallback is not None else None
    if t_kind == "unit" and t_mode == "2theta":
        t_wl = float(wl_fallback) if wl_fallback is not None else None

    # Numeric token always means 2θ at that λ (legacy).
    if f_kind == "wl":
        f_mode = "2theta"
    if t_kind == "wl":
        t_mode = "2theta"

    if f_mode == "2theta" and f_wl is None:
        raise ValueError(
            "Converting from 2θ requires a wavelength: "
            "use `--convert <λ> q` / `--convert <λ> d`, or "
            "`--convert 2theta q --wl <λ>`."
        )
    if t_mode == "2theta" and t_wl is None:
        raise ValueError(
            "Converting to 2θ requires a wavelength: "
            "use `--convert q <λ>` / `--convert d <λ>`, or "
            "`--convert q 2theta --wl <λ>`."
        )
    if f_mode == t_mode and not (f_kind == "wl" and t_kind == "wl" and f_wl != t_wl):
        # Same unit with no wavelength change → noop
        if f_mode != "2theta" or (f_wl is not None and t_wl is not None and float(f_wl) == float(t_wl)):
            raise ValueError(f"No conversion needed ({f_mode} → {t_mode})")
    return f_mode, t_mode, f_wl, t_wl


def _resolve_readcol_for_file(
    fname: str,
    readcol_by_file: Optional[dict[str, Any]] = None,
    readcol_by_ext: Optional[dict[str, tuple[int, int]]] = None,
    readcol_global: Optional[Any] = None,
) -> Optional[tuple[int, int, Optional[int]]]:
    """Resolve which columns to use for a file (x_col, y_col, e_col)."""
    if not readcol_by_file and not readcol_by_ext and not readcol_global:
        return None

    rc = None
    if readcol_by_file:
        norm_fname = os.path.normpath(fname)
        abs_fname = os.path.abspath(fname)
        base_fname = os.path.basename(fname)
        for key in readcol_by_file:
            key_norm = os.path.normpath(key)
            key_abs = os.path.abspath(key)
            if fname == key or norm_fname == key_norm or abs_fname == key_abs:
                rc = readcol_by_file[key]
                break
        if rc is None and base_fname:
            matches = [k for k in readcol_by_file if os.path.basename(k) == base_fname]
            if len(matches) == 1:
                rc = readcol_by_file[matches[0]]

    if rc is None and readcol_by_ext:
        _, ext = os.path.splitext(fname)
        ext_lower = ext.lower() if ext else ""
        rc = readcol_by_ext.get(ext_lower)

    if rc is None and readcol_global is not None:
        rc = readcol_global

    if rc is None:
        return None

    if isinstance(rc, (list, tuple)) and len(rc) >= 2:
        first = rc[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            x_col, y_col = int(first[0]), int(first[1])
        else:
            x_col, y_col = int(rc[0]), int(rc[1])
    elif isinstance(rc, (list, tuple)) and len(rc) == 1:
        first = rc[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            x_col, y_col = int(first[0]), int(first[1])
        else:
            return None
    else:
        return None

    e_col = y_col + 1
    return (x_col, y_col, e_col)


def _convert_x_values(
    x: np.ndarray,
    *,
    from_mode: str,
    to_mode: str,
    from_wl: Optional[float],
    to_wl: Optional[float],
) -> np.ndarray:
    """Convert x via Q using the shared axis-unit helpers."""
    # Wavelength-to-wavelength (2θ@λ1 → 2θ@λ2): go through Q with each λ.
    if from_mode == "2theta" and to_mode == "2theta":
        assert from_wl is not None and to_wl is not None
        q = convert_x_array(x, frm="2theta", to="Q", wl=from_wl)
        return convert_x_array(q, frm="Q", to="2theta", wl=to_wl)

    wl = from_wl if from_mode == "2theta" else to_wl
    return convert_x_array(x, frm=from_mode, to=to_mode, wl=wl)


def convert_xrd_data(
    filenames,
    from_param: str,
    to_param: str,
    args: Optional[Any] = None,
    *,
    out_ext: Optional[str] = None,
    out_subdir: str = "converted",
):
    """Convert XRD data files and write them under ``converted/`` (per input dir).

    Parameters
    ----------
    filenames:
        Input file paths.
    from_param / to_param:
        Wavelength (numeric string → 2θ at that λ) or unit token
        (``q`` / ``d`` / ``2theta`` and aliases).
    args:
        Optional namespace with ``readcol*`` and ``wl`` (fallback λ for named
        ``2theta`` tokens).
    out_ext:
        Optional output extension override (``.qye``, ``xy``, …).
    out_subdir:
        Subfolder name created next to each input file (default ``converted``).
    """
    wl_fallback = None
    if args is not None:
        try:
            raw_wl = getattr(args, "wl", None)
            if raw_wl is not None:
                wl_fallback = float(raw_wl)
        except Exception:
            wl_fallback = None

    try:
        from_mode, to_mode, from_wl, to_wl = resolve_conversion(
            from_param, to_param, wl_fallback=wl_fallback
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    out_ext_norm = normalize_extension(out_ext) if out_ext else None
    if out_ext_norm is None:
        out_ext_norm = _DEFAULT_OUT_EXT.get(to_mode, ".xy")

    subdir = (out_subdir or "converted").strip() or "converted"
    output_dirs: set[str] = set()
    n_ok = 0

    for fname in filenames:
        if not os.path.isfile(fname):
            print(f"File not found: {fname}")
            continue

        try:
            data = loadtxt_with_decimal_comma(fname)
        except Exception as e:
            print(f"Error reading {fname}: {e}")
            continue

        if data.ndim == 1:
            data = data.reshape(1, -1)
        if data.shape[1] < 2:
            print(f"Invalid data format in {fname}: need at least 2 columns (x, y)")
            continue

        readcol_by_file = getattr(args, "readcol_by_file", None) or {} if args else {}
        readcol_by_ext = getattr(args, "readcol_by_ext", None) or {} if args else {}
        readcol_global = getattr(args, "readcol", None) if args else None
        resolved = _resolve_readcol_for_file(
            fname, readcol_by_file, readcol_by_ext, readcol_global
        )

        if resolved:
            x_col, y_col, e_col = resolved
            x_idx, y_idx = x_col - 1, y_col - 1
            if x_idx < 0 or y_idx < 0 or x_idx >= data.shape[1] or y_idx >= data.shape[1]:
                print(
                    f"Error in {fname}: --readcol columns {x_col}, {y_col} "
                    f"out of range (file has {data.shape[1]} columns)"
                )
                continue
            x = data[:, x_idx]
            y = data[:, y_idx]
            if e_col is not None and e_col <= data.shape[1]:
                e_idx = e_col - 1
                e = data[:, e_idx] if e_idx >= 0 else None
            else:
                e = None
        else:
            x = data[:, 0]
            y = data[:, 1]
            e = data[:, 2] if data.shape[1] >= 3 else None

        try:
            x_new = _convert_x_values(
                x,
                from_mode=from_mode,
                to_mode=to_mode,
                from_wl=from_wl,
                to_wl=to_wl,
            )
        except Exception as e:
            print(f"Error converting {fname}: {e}")
            continue

        if e is None:
            out_data = np.column_stack((x_new, y))
        else:
            out_data = np.column_stack((x_new, y, e))

        input_dir = os.path.dirname(os.path.abspath(fname)) or os.getcwd()
        output_dir = os.path.join(input_dir, subdir)
        os.makedirs(output_dir, exist_ok=True)

        base = os.path.basename(os.path.splitext(fname)[0])
        output_fname = os.path.join(output_dir, f"{base}{out_ext_norm}")

        if from_mode == "2theta" and to_mode == "2theta":
            header = (
                f"# Converted from {os.path.basename(fname)}: "
                f"2θ (λ={from_wl} Å) → 2θ (λ={to_wl} Å)"
            )
        elif from_mode == "2theta":
            header = (
                f"# Converted from {os.path.basename(fname)}: "
                f"2θ (λ={from_wl} Å) → {to_mode}"
            )
        elif to_mode == "2theta":
            header = (
                f"# Converted from {os.path.basename(fname)}: "
                f"{from_mode} → 2θ (λ={to_wl} Å)"
            )
        else:
            header = (
                f"# Converted from {os.path.basename(fname)}: "
                f"{from_mode} → {to_mode}"
            )

        try:
            np.savetxt(output_fname, out_data, fmt="% .6f", header=header, encoding="utf-8")
            print(f"Saved {output_fname}")
            output_dirs.add(output_dir)
            n_ok += 1
        except Exception as e:
            print(f"Error saving {output_fname}: {e}")

    if output_dirs:
        print(f"Exported {n_ok} file(s) to: {', '.join(sorted(output_dirs))}")


def convert_to_qye(filenames, wavelength: float):
    """Legacy helper: 2θ → Q (``.qye``). Prefer :func:`convert_xrd_data`."""
    convert_xrd_data(filenames, str(wavelength), "q")


__all__ = [
    "convert_to_qye",
    "convert_xrd_data",
    "normalize_extension",
    "parse_convert_token",
    "resolve_conversion",
]
