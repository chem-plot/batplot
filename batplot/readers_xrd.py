"""XRD vendor file readers (Bruker RAW/BRML and related).

Extracted from :mod:`batplot.readers` so electrochemistry parsers and XRD I/O
can evolve independently. ``batplot.readers`` re-exports these symbols.
"""

from __future__ import annotations

import os
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np  # type: ignore[import-untyped]


# Bruker RAW v4 magic bytes (other instruments may use .raw for different formats)
_BRUKER_RAW_MAGIC = b"RAW4.00\x00"


# Wavelength (Å) K-alpha1 for common anodes (Bruker .raw header lookup)
_BRUKER_RAW_WAVELENGTHS = {
    b"Cu": 1.540598,
    b"Mo": 0.709319,
    b"Co": 1.788996,
    b"Fe": 1.936046,
    b"Cr": 2.289760,
    b"Ag": 0.559420,
}


def is_bruker_raw(fname: str) -> bool:
    """Return True if the file looks like Bruker RAW v4 (magic bytes RAW4.00). Other instruments may use .raw for different formats."""
    if not fname or not str(fname).lower().endswith(".raw"):
        return False
    try:
        with open(fname, "rb") as f:
            header = f.read(8)
        return len(header) == 8 and header == _BRUKER_RAW_MAGIC
    except OSError:
        return False


# Bruker RAW/BRML use these values for missing or invalid detector counts.
_BRUKER_INVALID_INTENSITIES = (-9999.0, -999.0)


def sanitize_xrd_intensity(y: np.ndarray) -> np.ndarray:
    """Replace Bruker missing-value sentinels with NaN so plots mask them."""
    arr = np.asarray(y, dtype=float)
    if arr.size == 0:
        return arr
    bad = np.zeros(arr.shape, dtype=bool)
    for sentinel in _BRUKER_INVALID_INTENSITIES:
        bad |= arr == sentinel
    if not np.any(bad):
        return arr
    out = arr.copy()
    out[bad] = np.nan
    return out


def read_bruker_raw(fname: str) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[float]]:
    """Read Bruker/Siemens RAW v4 binary: extract 2θ (degrees) and intensity as x, y.

    Parses the binary directly. Intensity block is at end of file; start angle
    and step (degrees) are found in the header.

    Returns:
        (x, y, e, wavelength): x = 2θ in degrees, y = intensity, e = None, wavelength in Å if known.
    """
    if not (fname and str(fname).lower().endswith(".raw")):
        raise ValueError("read_bruker_raw expects a .raw file")

    try:
        with open(fname, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ValueError(f"Cannot read .raw file {fname}: {e}") from e

    n_total = len(data)
    if n_total < 1000:
        raise ValueError(f"File too small to be a valid Bruker .raw: {fname}")

    # Intensity at end: largest n such that last n*4 bytes are n non-negative float32, max > 1
    n = None
    for candidate in range(min(20000, (n_total - 500) // 4), 500 - 1, -1):
        if candidate * 4 > n_total - 100:
            continue
        try:
            block = data[n_total - candidate * 4 : n_total]
            floats = struct.unpack("<%df" % candidate, block)
            if all(f >= 0 and f < 1e10 and f == f for f in floats) and max(floats) > 1:
                n = candidate
                y_arr = np.array(floats, dtype=float)
                break
        except Exception:
            continue
    if n is None:
        raise ValueError(f"Could not find valid intensity block in {fname}")

    header_len = n_total - n * 4
    header = data[:header_len]

    # Start angle and step (consecutive float64) in header
    start_angle = None
    step_size = None
    for i in range(0, header_len - 16, 8):
        try:
            a, b = struct.unpack("<dd", header[i : i + 16])
            if 0 <= a <= 120 and 0.001 <= b <= 0.5:
                end_angle = a + (n - 1) * b
                if 10 <= end_angle <= 180:
                    start_angle = a
                    step_size = b
                    break
        except Exception:
            continue
    if start_angle is None or step_size is None:
        raise ValueError(f"Could not find scan angles (start/step) in {fname}")

    x_arr = start_angle + step_size * np.arange(n, dtype=float)

    wavelength = None
    for offset in (0x01A8, 0x200, 0x100, 0x300):
        if offset + 8 <= header_len:
            segment = header[offset : offset + 8]
            for key, wl in _BRUKER_RAW_WAVELENGTHS.items():
                if key in segment:
                    wavelength = wl
                    break
            if wavelength is not None:
                break

    return x_arr, sanitize_xrd_intensity(y_arr), None, wavelength


def read_bruker_brml(fname: str) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[float]]:
    """Read Bruker .brml (zip of XML): extract 2θ (degrees) and intensity as x, y.

    Parses the .brml zip directly using DataContainer and RawData*.xml inside the zip.

    Returns:
        (x, y, e, wavelength): x = 2θ in degrees, y = intensity, e = None, wavelength in Å if found.
    """
    if not (fname and str(fname).lower().endswith(".brml")):
        raise ValueError("read_bruker_brml expects a .brml file")

    def _first_experiment_and_datacontainer(zip_f):
        for name in zip_f.namelist():
            if "/DataContainer.xml" in name and "Experiment" in name:
                return name.split("/DataContainer.xml")[0], name
        return None, None

    def _raw_reference_list(zip_f, dc_path):
        with zip_f.open(dc_path, "r") as f:
            tree = ET.parse(f)
        root = tree.getroot()
        ns = {"": ""}  # no namespace
        ref = root.find(".//RawDataReferenceList/string")
        if ref is not None and ref.text:
            return [ref.text.strip()]
        refs = root.findall(".//RawDataReferenceList/string")
        if refs:
            return [r.text.strip() for r in refs if r.text]
        return []

    def _parse_raw_xml(zip_f, raw_path):
        with zip_f.open(raw_path, "r") as f:
            tree = ET.parse(f)
        root = tree.getroot()
        # DataRoutes -> DataRoute -> ScanInformation (ScanAxes), Datum
        dr = root.find(".//DataRoute")
        if dr is None:
            return None, None, None, None
        si = dr.find("ScanInformation")
        start_deg = None
        step_deg = None
        two_theta_name = None
        if si is not None:
            for axis in si.findall(".//ScanAxisInfo"):
                aname = axis.get("AxisName") or axis.get("AxisId") or ""
                if "TwoTheta" in aname or "2Theta" in aname or "2theta" in aname.lower():
                    two_theta_name = aname
                    ref = float(axis.findtext("Reference") or "0")
                    start_deg = float(axis.findtext("Start") or "0") + ref
                    stop_deg = float(axis.findtext("Stop") or "0") + ref
                    step_deg = float(axis.findtext("Increment") or "0")
                    break
        # Datum lines: comma-separated; layout often (MeasuredTime, AbsorptionFactor, TwoTheta, Theta, Count)
        datum_elts = dr.findall("Datum")
        if not datum_elts:
            return None, None, None, None
        rows = []
        for d in datum_elts:
            if d.text:
                rows.append([float(x) for x in d.text.strip().split(",")])
        if not rows:
            return None, None, None, None
        arr = np.array(rows)
        ncols = arr.shape[1]
        # Column indices: 0=time, 1=absorption?, 2=TwoTheta, 3=Theta, 4=Count (or similar)
        if ncols >= 5:
            x_col, y_col = 2, 4
        elif ncols >= 3:
            x_col, y_col = 0, 1  # fallback
        else:
            return None, None, None, None
        x_arr = np.asarray(arr[:, x_col], dtype=float)
        y_arr = sanitize_xrd_intensity(np.asarray(arr[:, y_col], dtype=float))
        return x_arr, y_arr, start_deg, step_deg

    try:
        with zipfile.ZipFile(fname, "r") as zf:
            exp_prefix, dc_path = _first_experiment_and_datacontainer(zf)
            if not dc_path:
                raise ValueError(f"No DataContainer.xml found in {fname}")
            raw_list = _raw_reference_list(zf, dc_path)
            if not raw_list:
                raise ValueError(f"No RawDataReferenceList in {fname}")
            x_list, y_list = [], []
            for raw_path in raw_list:
                x_arr, y_arr, start_deg, step_deg = _parse_raw_xml(zf, raw_path)
                if x_arr is not None and y_arr is not None:
                    x_list.append(x_arr)
                    y_list.append(y_arr)
            if not x_list:
                raise ValueError(f"No scan data in {fname}")
            x_arr = np.concatenate(x_list) if len(x_list) > 1 else x_list[0]
            y_arr = np.concatenate(y_list) if len(y_list) > 1 else y_list[0]

    except (zipfile.BadZipFile, OSError) as e:
        raise ValueError(f"Cannot read .brml file {fname}: {e}") from e
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML in .brml file {fname}: {e}") from e

    # Wavelength: optional from PreMeasContainer or TemplateContainer (Cu Kα1 = 1.540598)
    wavelength = None
    try:
        with zipfile.ZipFile(fname, "r") as zf:
            for cand in ("Experiment0/PreMeasContainer.xml", "Experiment0/TemplateContainer.xml"):
                if cand in zf.namelist():
                    with zf.open(cand, "r") as f:
                        content = f.read().decode("utf-8", errors="ignore")
                    if "Cu" in content and ("KAlpha" in content or "K_alpha" in content or "Wavelength" in content):
                        wavelength = 1.540598
                        break
    except Exception:
        pass

    return x_arr, sanitize_xrd_intensity(y_arr), None, wavelength


def _parse_brml_raw_xml(zip_f, raw_path):
    """Parse a single RawData XML from BRML. Returns (x, y, start_deg, step_deg) or (None,)*4."""
    with zip_f.open(raw_path, "r") as f:
        tree = ET.parse(f)
    root = tree.getroot()
    dr = root.find(".//DataRoute")
    if dr is None:
        return None, None, None, None
    start_deg = None
    step_deg = None
    si = dr.find("ScanInformation")
    if si is not None:
        for axis in si.findall(".//ScanAxisInfo"):
            aname = axis.get("AxisName") or axis.get("AxisId") or ""
            if "TwoTheta" in aname or "2Theta" in aname or "2theta" in aname.lower():
                ref = float(axis.findtext("Reference") or "0")
                start_deg = float(axis.findtext("Start") or "0") + ref
                step_deg = float(axis.findtext("Increment") or "0")
                break
    if start_deg is None or step_deg is None:
        for axis in root.findall(".//ScaleAxisInfo"):
            aname = axis.get("AxisName") or axis.get("AxisId") or ""
            if "TwoTheta" in aname or "2Theta" in aname or "2theta" in aname.lower():
                ref = float(axis.findtext("Reference") or "0")
                start_deg = float(axis.findtext("Start") or "0") + ref
                step_deg = float(axis.findtext("Increment") or "0")
                break
    if start_deg is None or step_deg is None:
        return None, None, None, None
    datum_elts = dr.findall("Datum")
    if not datum_elts:
        return None, None, None, None
    rows = []
    for d in datum_elts:
        if d.text:
            rows.append([float(x) for x in d.text.strip().split(",")])
    if not rows:
        return None, None, None, None
    arr = np.array(rows)
    nrows, ncols = arr.shape
    if nrows == 1 and ncols >= 10:
        n_counts = ncols - 2
        y_arr = np.asarray(arr[0, 2:], dtype=float)
        if len(y_arr) != n_counts:
            y_arr = np.asarray(arr[0, 2 : 2 + n_counts], dtype=float)
        n_pts = len(y_arr)
        x_arr = start_deg + np.arange(n_pts, dtype=float) * step_deg
        return x_arr, sanitize_xrd_intensity(y_arr), start_deg, step_deg
    if ncols >= 5:
        x_col, y_col = 2, 4
    elif ncols >= 3:
        x_col, y_col = 0, 1
    else:
        return None, None, None, None
    x_arr = np.asarray(arr[:, x_col], dtype=float)
    y_arr = sanitize_xrd_intensity(np.asarray(arr[:, y_col], dtype=float))
    return x_arr, y_arr, start_deg, step_deg


def extract_bruker_brml_scans(
    fname: str,
    out_dir: Optional[str] = None,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Extract each XRD scan from a Bruker .brml file as separate (x, y) datasets.

    Skips non-XRD RawData (e.g. Biologic electrochemistry in operando files).
    Supports both ScanAxisInfo (older) and ScaleAxisInfo (newer) formats.

    Args:
        fname: Path to .brml file.
        out_dir: If provided, write each scan to scan_001.xy, scan_002.xy, etc.

    Returns:
        List of (x, y) tuples; x = 2θ (degrees), y = intensity.
    """
    if not (fname and str(fname).lower().endswith(".brml")):
        raise ValueError("extract_bruker_brml_scans expects a .brml file")

    def _first_experiment_and_datacontainer(zip_f):
        for name in zip_f.namelist():
            if "/DataContainer.xml" in name and "Experiment" in name:
                return name.split("/DataContainer.xml")[0], name
        return None, None

    def _raw_reference_list(zip_f, dc_path):
        with zip_f.open(dc_path, "r") as f:
            tree = ET.parse(f)
        root = tree.getroot()
        refs = root.findall(".//RawDataReferenceList/string")
        if refs:
            return [r.text.strip() for r in refs if r.text]
        return []

    scans: List[Tuple[np.ndarray, np.ndarray]] = []
    with zipfile.ZipFile(fname, "r") as zf:
        _exp_prefix, dc_path = _first_experiment_and_datacontainer(zf)
        if not dc_path:
            raise ValueError(f"No DataContainer.xml found in {fname}")
        raw_list = _raw_reference_list(zf, dc_path)
        if not raw_list:
            raise ValueError(f"No RawDataReferenceList in {fname}")
        for raw_path in raw_list:
            x_arr, y_arr, _s, _st = _parse_brml_raw_xml(zf, raw_path)
            if x_arr is not None and y_arr is not None:
                scans.append((x_arr, y_arr))

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        for i, (x_arr, y_arr) in enumerate(scans):
            out_path = os.path.join(out_dir, f"scan_{i + 1:03d}.xy")
            with open(out_path, "w", encoding="utf-8") as f:
                for xi, yi in zip(x_arr, y_arr):
                    f.write(f"{xi}\t{yi}\n")

    return scans


def read_xrd_vendor_file(fname: str) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], Optional[float]]:
    """Read Bruker .raw or .brml (built-in parsers). Returns 2θ (degrees) and intensity.

    .xrdml and .rasx are not supported; convert to .xy or use another tool.

    Returns:
        (x, y, e, wavelength): x in degrees (2θ), y intensity, e=None, wavelength in Å if known.
    """
    fname_lower = fname.lower()
    if fname_lower.endswith(".raw"):
        return read_bruker_raw(fname)
    if fname_lower.endswith(".brml"):
        return read_bruker_brml(fname)
    if fname_lower.endswith(".xrdml") or fname_lower.endswith(".rasx"):
        raise ValueError(
            f"Format {fname_lower[-5:]!r} is not supported. "
            "Batplot supports Bruker .raw and .brml only for vendor XRD. "
            "Convert to .xy (2θ, intensity) or use another tool for .xrdml/.rasx."
        )
    raise ValueError(f"Unsupported file type for XRD reading: {fname}")

__all__ = [
    "is_bruker_raw",
    "sanitize_xrd_intensity",
    "read_bruker_raw",
    "read_bruker_brml",
    "extract_bruker_brml_scans",
    "read_xrd_vendor_file",
]
