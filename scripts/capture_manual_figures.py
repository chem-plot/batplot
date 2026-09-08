#!/usr/bin/env python3
"""Capture PNG figures for the batplot user manual from demo files.

Uses the installed ``batplot`` executable (override with ``BATPLOT_BIN``).
Default DEMO_ROOT points at the manuscript demo tree (override with
``BATPLOT_DEMO_ROOT``).

PNG files are resized (max width 900px). Exports with huge multi-cycle legends
are cropped to ``MAX_PNG_ASPECT`` so the manual stays compact. Display size is
further limited by CSS in ``docs/stylesheets/extra.css``.

Demo wavelengths (XRD / *operando*):
  - ``TD_R*`` synchrotron → ``--wl 0.259``
  - ``TD_S0062-64`` Cu lab → ``--wl 1.54``
  - *Operando* ``TD_S0034_*`` Cu lab → ``--wl 1.54``

Usage (from repo root)::

    MPLBACKEND=Agg python scripts/capture_manual_figures.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DEFAULT_DEMO = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/"
    "My files/batplot_manuscript/batplot_demo_files"
)

# Canonical demo wavelengths
WL_SYNC = "0.259"
WL_CU = "1.54"
MAX_PNG_WIDTH = 900
# EC multi-cycle exports can grow a huge legend; keep a landscape-ish frame.
MAX_PNG_ASPECT = 0.72  # height / width after processing


def _batplot_bin() -> str:
    env = os.environ.get("BATPLOT_BIN")
    if env:
        return env
    cand = Path("/opt/miniconda3/envs/tutorial/bin/batplot")
    if cand.is_file():
        return str(cand)
    return "batplot"


def _run(argv: list[str], *, cwd: Path | None = None) -> int:
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    # Use the installed console script (stable). Optional local tree can be
    # forced with BATPLOT_BIN + PYTHONPATH if desired.
    cmd = [_batplot_bin(), *argv]
    print(" ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env)
    return int(proc.returncode)


def _shrink_png(
    path: Path,
    max_width: int = MAX_PNG_WIDTH,
    max_aspect: float = MAX_PNG_ASPECT,
) -> None:
    """Downscale and crop tall exports (e.g. GC legends with many cycles)."""
    if not path.is_file():
        return
    try:
        from PIL import Image
    except ImportError:
        try:
            subprocess.run(
                ["sips", "--resampleWidth", str(max_width), str(path)],
                check=False,
                capture_output=True,
            )
        except OSError:
            pass
        return
    with Image.open(path) as im:
        im = im.convert("RGBA") if im.mode not in ("RGB", "RGBA") else im
        w, h = im.size
        # Crop bottom when a long cycle legend forces an absurd height
        max_h = int(round(w * float(max_aspect)))
        if h > max_h:
            im = im.crop((0, 0, w, max_h))
            w, h = im.size
            print(f"  cropped tall legend → {w}x{h}")
        if w > max_width:
            nh = int(round(h * (max_width / float(w))))
            im = im.resize((max_width, nh), Image.Resampling.LANCZOS)
        im.save(path, optimize=True)


def _prepare_operando_subset(demo: Path, dest: Path, n: int = 40) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.iterdir():
        if old.is_file():
            old.unlink()
    src = demo / "Operando"
    xy = sorted(
        [p for p in src.glob("*_exported.xy")],
        key=lambda p: int(p.stem.split("_")[2]) if p.stem.split("_")[2].isdigit() else 0,
    )
    step = max(1, len(xy) // n)
    picked = xy[::step][:n]
    for p in picked:
        shutil.copy2(p, dest / p.name)
    for mpt in src.glob("*.mpt"):
        shutil.copy2(mpt, dest / mpt.name)
    return dest


def main() -> int:
    demo = Path(os.environ.get("BATPLOT_DEMO_ROOT", str(DEFAULT_DEMO))).expanduser()
    out_dir = REPO / "docs" / "images" / "manual"
    demo_data = REPO / "docs" / "demo_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    op_subset = demo_data / "_operando_subset"

    if not demo.is_dir():
        print(f"ERROR: demo root not found: {demo}", file=sys.stderr)
        return 1

    xrd = demo / "XRD"
    ec = demo / "EC"
    xas = demo / "XAS"

    jobs: list[tuple[str, list[str], str]] = []

    def add(name: str, argv: list[str], note: str) -> None:
        jobs.append((name, argv, note))

    # --- 1D / XY ---
    add(
        "manual-xy-2theta.png",
        [
            str(xrd / "TD_S0062-64.xy"),
            "--xaxis",
            "2theta",
            "--out",
            str(out_dir / "manual-xy-2theta.png"),
        ],
        "Cu XRD in 2θ (`TD_S0062-64.xy --xaxis 2theta`)",
    )
    add(
        "manual-xy-q.png",
        [
            str(xrd / "TD_S0062-64.xy"),
            "--wl",
            WL_CU,
            "--out",
            str(out_dir / "manual-xy-q.png"),
        ],
        f"Cu XRD → Q (`TD_S0062-64.xy --wl {WL_CU}`)",
    )
    add(
        "manual-xy-q-suffix.png",
        [
            f"{xrd / 'TD_S0062-64.xy'}:{WL_CU}",
            "--out",
            str(out_dir / "manual-xy-q-suffix.png"),
        ],
        f"Per-file `:λ` → Q (`TD_S0062-64.xy:{WL_CU}`)",
    )
    add(
        "manual-xy-overlay-same-wl.png",
        [
            str(xrd / "TD_R02.dat"),
            str(xrd / "TD_R03.dat"),
            "--wl",
            WL_SYNC,
            "--out",
            str(out_dir / "manual-xy-overlay-same-wl.png"),
        ],
        f"Synchrotron overlay (`TD_R02`+`TD_R03 --wl {WL_SYNC}`)",
    )
    add(
        "manual-xy-overlay-mixed-wl.png",
        [
            f"{xrd / 'TD_S0062-64.xy'}:{WL_CU}",
            f"{xrd / 'TD_R02.dat'}:{WL_SYNC}",
            "--out",
            str(out_dir / "manual-xy-overlay-mixed-wl.png"),
        ],
        f"Mixed λ overlay (Cu `{WL_CU}` + synchrotron `{WL_SYNC}`)",
    )
    add(
        "manual-xy-reproj.png",
        [
            f"{xrd / 'TD_R02.dat'}:{WL_SYNC}:{WL_CU}",
            "--xaxis",
            "2theta",
            "--out",
            str(out_dir / "manual-xy-reproj.png"),
        ],
        f"Re-project synchrotron → Cu 2θ (`TD_R02.dat:{WL_SYNC}:{WL_CU}`)",
    )
    add(
        "manual-xy-norm.png",
        [
            str(xrd / "TD_R02.dat"),
            str(xrd / "TD_R03.dat"),
            "--norm",
            "--wl",
            WL_SYNC,
            "--out",
            str(out_dir / "manual-xy-norm.png"),
        ],
        f"Normalized overlay (`--norm --wl {WL_SYNC}`)",
    )

    _run([str(demo_data / "demo_cols.txt"), "--strip-header", "2"])
    stripped = demo_data / "stripped" / "demo_cols.txt"
    committed = demo_data / "demo_cols_stripped.txt"
    if stripped.is_file():
        shutil.copy2(stripped, committed)
    readcol_src = str(committed if committed.is_file() else stripped)

    add(
        "manual-xy-readcol.png",
        [
            readcol_src,
            "--readcol",
            "1",
            "4",
            "--xaxis",
            "2theta",
            "--out",
            str(out_dir / "manual-xy-readcol.png"),
        ],
        "`demo_cols_stripped.txt --readcol 1 4`",
    )
    add(
        "manual-xy-readcol-multi.png",
        [
            readcol_src,
            "--readcol",
            "1",
            "2-4",
            "--xaxis",
            "2theta",
            "--out",
            str(out_dir / "manual-xy-readcol-multi.png"),
        ],
        "`--readcol 1 2-4` multi-y curves",
    )
    add(
        "manual-xy-stack.png",
        [
            str(xrd / "TD_R02.dat"),
            str(xrd / "TD_R03.dat"),
            str(xrd / "TD_R05.dat"),
            "--stack",
            "--wl",
            WL_SYNC,
            "--out",
            str(out_dir / "manual-xy-stack.png"),
        ],
        f"Synchrotron stack (`TD_R02/R03/R05 --stack --wl {WL_SYNC}`)",
    )
    add(
        "manual-xy-cif.png",
        [
            f"{xrd / 'TD_S0062-64.xy'}:{WL_CU}",
            f"{xrd / 'TD_R02.dat'}:{WL_SYNC}",
            str(xrd / "Li2FeSeO.cif"),
            str(xrd / "Li2Se.cif"),
            "--stack",
            "--out",
            str(out_dir / "manual-xy-cif.png"),
        ],
        "Stack + CIF ticks (Cu + synchrotron + Li2FeSeO/Li2Se)",
    )
    add(
        "manual-xy-cif-2theta.png",
        [
            str(xrd / "TD_S0062-64.xy"),
            f"{xrd / 'Li2FeSeO.cif'}:{WL_CU}",
            "--xaxis",
            "2theta",
            "--wl",
            WL_CU,
            "--out",
            str(out_dir / "manual-xy-cif-2theta.png"),
        ],
        f"CIF ticks in 2θ (`TD_S0062-64` + `Li2FeSeO.cif:{WL_CU}`)",
    )
    add(
        "manual-xy-xas.png",
        [
            str(xas / "R03_Se.nor"),
            "--xaxis",
            "energy",
            "--out",
            str(out_dir / "manual-xy-xas.png"),
        ],
        "XAS `.nor` (`--xaxis energy`)",
    )
    add(
        "manual-xy-deriv.png",
        [
            str(xas / "R03_Se.nor"),
            "--1d",
            "--xaxis",
            "energy",
            "--out",
            str(out_dir / "manual-xy-deriv.png"),
        ],
        "XAS first derivative (`--1d --xaxis energy`)",
    )
    add(
        "manual-xy-ry.png",
        [
            str(xrd / "TD_R02.dat"),
            str(xrd / "TD_R03.dat"),
            "--ry",
            "--wl",
            WL_SYNC,
            "--out",
            str(out_dir / "manual-xy-ry.png"),
        ],
        f"Dual y-axis (`TD_R02` + `TD_R03 --ry --wl {WL_SYNC}`)",
    )
    add(
        "manual-xy-qye.png",
        [
            str(xrd / "converted" / "R02.qye"),
            "--xaxis",
            "q",
            "--out",
            str(out_dir / "manual-xy-qye.png"),
        ],
        "Already-Q `.qye` (`converted/R02.qye --xaxis q`)",
    )

    # --- EC ---
    add(
        "manual-ec-gc.png",
        [str(ec / "B443.csv"), "--gc", "--out", str(out_dir / "manual-ec-gc.png")],
        "Neware GC (`B443.csv --gc`)",
    )
    add(
        "manual-ec-gc-mpt.png",
        [
            str(ec / "TD_O2.mpt"),
            "--gc",
            "--mass",
            "7",
            "--out",
            str(out_dir / "manual-ec-gc-mpt.png"),
        ],
        "Biologic GC (`TD_O2.mpt --gc --mass 7`)",
    )
    add(
        "manual-ec-gc-multi.png",
        [
            str(ec / "B443.csv"),
            str(ec / "B444.csv"),
            str(ec / "B445.csv"),
            "--gc",
            "--out",
            str(out_dir / "manual-ec-gc-multi.png"),
        ],
        "Multi-file GC (`B443 B444 B445 --gc`)",
    )
    add(
        "manual-ec-dqdv.png",
        [str(ec / "B443.csv"), "--dqdv", "--out", str(out_dir / "manual-ec-dqdv.png")],
        "dQ/dV (`B443.csv --dqdv`)",
    )
    add(
        "manual-ec-cpc.png",
        [str(ec / "B443.csv"), "--cpc", "--out", str(out_dir / "manual-ec-cpc.png")],
        "CPC (`B443.csv --cpc`)",
    )
    add(
        "manual-ec-cpc-multi.png",
        [
            str(ec / "B443.csv"),
            str(ec / "B444.csv"),
            str(ec / "B445.csv"),
            "--cpc",
            "--out",
            str(out_dir / "manual-ec-cpc-multi.png"),
        ],
        "Multi-file CPC (`B443 B444 B445 --cpc`)",
    )
    add(
        "manual-ec-time.png",
        [
            str(ec / "B443.csv"),
            "--xaxis",
            "time",
            "--out",
            str(out_dir / "manual-ec-time.png"),
        ],
        "Time vs voltage (`B443.csv --xaxis time`)",
    )

    # --- Operando (TD_S0034 = Cu) ---
    _prepare_operando_subset(demo, op_subset, n=40)
    add(
        "manual-op-contour.png",
        [
            str(op_subset),
            "--operando",
            "--wl",
            WL_CU,
            "--out",
            str(out_dir / "manual-op-contour.png"),
        ],
        f"*Operando* contour (TD_S0034 subset + `.mpt`, `--wl {WL_CU}`)",
    )
    add(
        "manual-op-cif.png",
        [
            str(op_subset),
            str(xrd / "Li2FeSeO.cif"),
            str(xrd / "Li2Se.cif"),
            "--operando",
            "--wl",
            WL_CU,
            "--out",
            str(out_dir / "manual-op-cif.png"),
        ],
        f"*Operando* + CIF ticks (`--wl {WL_CU}`)",
    )

    # --- Histogram ---
    add(
        "manual-histo.png",
        [
            str(demo_data / "sizes.csv"),
            "--histo",
            "--histocol",
            "2",
            "--bins",
            "10",
            "--out",
            str(out_dir / "manual-histo.png"),
        ],
        "Histogram (`sizes.csv --histo --histocol 2 --bins 10`)",
    )

    # --- Batch peers ---
    for i, name in enumerate(("B443", "B444", "B445"), start=1):
        add(
            f"manual-batch-ec-{i}.png",
            [
                str(ec / f"{name}.csv"),
                "--gc",
                "--out",
                str(out_dir / f"manual-batch-ec-{i}.png"),
            ],
            f"Batch peer GC export ({name}.csv --gc)",
        )

    add(
        "manual-util-convert.png",
        [
            str(xrd / "converted" / "R02.qye"),
            "--xaxis",
            "q",
            "--out",
            str(out_dir / "manual-util-convert.png"),
        ],
        "Converted Q-space XRD (`XRD/converted/R02.qye`)",
    )

    results: list[tuple[str, str, str]] = []
    for png_name, argv, note in jobs:
        target = out_dir / png_name
        if target.is_file():
            target.unlink()
        print(f"\n=== {png_name} ===")
        code = _run(argv)
        if target.is_file():
            _shrink_png(target)
            status = "OK" if code == 0 else f"OK (exit {code})"
            results.append((png_name, status, note))
            print(f"{status} → {target}")
        else:
            results.append((png_name, f"FAIL exit={code}", note))
            print(f"FAIL exit={code}")

    for p in out_dir.glob("_test_*.png"):
        p.unlink()

    manifest = out_dir / "MANIFEST.md"
    lines = [
        "# Manual figure manifest",
        "",
        f"Demo root: `{demo}`",
        f"batplot: `{_batplot_bin()}`",
        f"Wavelengths: TD_R* = {WL_SYNC} Å (synchrotron); TD_S0062-64 / Operando TD_S0034 = {WL_CU} Å (Cu)",
        f"PNG max width: {MAX_PNG_WIDTH}px (CSS also limits display size)",
        "",
        "| PNG | Status | Description |",
        "|-----|--------|-------------|",
    ]
    for name, status, note in results:
        lines.append(f"| `{name}` | {status} | {note} |")
    lines.append("")
    lines.append("Regenerate: `MPLBACKEND=Agg python scripts/capture_manual_figures.py`")
    lines.append("")
    manifest.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {manifest}")

    failed = [r for r in results if not r[1].startswith("OK")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
