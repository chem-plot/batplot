"""File display helpers shared by interactive plot modes."""

from __future__ import annotations

import os
import time
from typing import Any, Callable


def format_file_timestamp(filepath: str) -> str:
    """Return a stable local timestamp string for an existing file path."""
    try:
        mtime = os.path.getmtime(filepath)
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    except Exception:
        return ""


def confirm_previous_path(
    owner: Any,
    attr_name: str,
    *,
    safe_input: Callable[[str], str],
    missing_message: str,
    missing_file_message: str,
    confirm_prompt: str,
    canceled_message: str | None = "Canceled.",
) -> str | None:
    """Return a remembered file path after existence and overwrite confirmation."""
    path = getattr(owner, attr_name, None)
    if not path:
        print(missing_message)
        return None
    if not os.path.exists(path):
        print(missing_file_message.format(path=path, basename=os.path.basename(path)))
        return None
    yn = safe_input(confirm_prompt.format(path=path, basename=os.path.basename(path))).strip().lower()
    if yn != "y":
        if canceled_message:
            print(canceled_message)
        return None
    return path
