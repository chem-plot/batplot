#!/usr/bin/env python3
"""Deprecated alias — use repair_user_manual_docx.py instead."""

from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("repair_user_manual_docx.py")), run_name="__main__")
