#!/usr/bin/env python3
"""Rename files to numeric names (0, 1, 2, ...) and export to a destination folder.

Usage:
    python rename_and_export.py [source_dir] [dest_dir]

    source_dir: folder containing files to rename (default: Heating folder in 260210)
    dest_dir:   destination folder (default: Heating/numbered subfolder)

Example:
    python rename_and_export.py
    python rename_and_export.py ./at750 "/path/to/Heating"
"""
from __future__ import annotations

import argparse
import os
import re
import shutil


def natural_sort_key(name: str):
    """Sort key for natural ordering: file1, file2, file10 (not file1, file10, file2)."""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def main():
    base = "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/Li2FeSeO_processing/InsituSynthesis/260210"
    default_src = os.path.join(base, "Heating")
    # Subfolder to avoid overwriting originals when source=Heating
    default_dest = os.path.join(base, "Heating", "numbered")

    parser = argparse.ArgumentParser(description="Rename files to 0.ext, 1.ext, ... and export")
    parser.add_argument("source", nargs="?", default=default_src, help="Source folder")
    parser.add_argument("dest", nargs="?", default=default_dest, help="Destination folder")
    args = parser.parse_args()

    src = os.path.abspath(os.path.expanduser(args.source))
    dest = os.path.abspath(os.path.expanduser(args.dest))

    if not os.path.isdir(src):
        print(f"Error: source folder does not exist: {src}")
        return 1

    # Collect files (exclude dirs and hidden)
    files = [
        f
        for f in os.listdir(src)
        if os.path.isfile(os.path.join(src, f)) and not f.startswith(".")
    ]
    files.sort(key=natural_sort_key)

    if not files:
        print(f"No files found in {src}")
        return 0

    os.makedirs(dest, exist_ok=True)

    for i, fname in enumerate(files):
        ext = os.path.splitext(fname)[1] or ""
        new_name = f"{i}{ext}"
        src_path = os.path.join(src, fname)
        dest_path = os.path.join(dest, new_name)
        try:
            shutil.copy2(src_path, dest_path)
            print(f"  {fname} -> {new_name}")
        except Exception as e:
            print(f"  Error copying {fname}: {e}")

    print(f"\nExported {len(files)} files to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
