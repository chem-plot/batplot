"""Terminal input and prompt-color helpers shared by interactive modes."""

from __future__ import annotations

import re
import sys


class FilterIMKWarning:
    """Filter macOS IMK warnings while preserving all other stderr output."""

    def __init__(self, original_stderr):
        self.original_stderr = original_stderr

    def write(self, message):
        if "IMKCFRunLoopWakeUpReliable" not in message:
            self.original_stderr.write(message)

    def flush(self):
        self.original_stderr.flush()


def safe_input(prompt: str = "", *, cancel_on_interrupt: bool = False) -> str:
    """Call ``input`` while suppressing harmless macOS IMK terminal warnings."""
    original_stderr = sys.stderr
    sys.stderr = FilterIMKWarning(original_stderr)
    try:
        return input(prompt)
    except KeyboardInterrupt:
        if cancel_on_interrupt:
            try:
                print()
            except Exception:
                pass
            return ""
        raise
    except EOFError:
        if cancel_on_interrupt:
            try:
                print()
            except Exception:
                pass
            return ""
        raise
    finally:
        sys.stderr = original_stderr


def prompt_float(safe_input_fn, prompt_text: str, *, on_error: str = "Invalid number, using default."):
    """Prompt for a float, returning ``None`` on blank input, ``q``, or a parse error.

    ``safe_input_fn`` is the mode's input callable (usually :func:`safe_input`).
    On a non-numeric entry the ``on_error`` message is printed (pass ``""`` to
    suppress) and ``None`` is returned.
    """
    raw = safe_input_fn(prompt_text).strip()
    if not raw or raw.lower() == "q":
        return None
    try:
        return float(raw)
    except ValueError:
        if on_error:
            print(on_error)
        return None


def colorize_prompt(text: str) -> str:
    """Colorize command keys in parenthesized prompts such as ``(s=size, q=return)``."""
    pattern = r"\(([a-z]+=[^,)]+(?:,\s*[a-z]+=[^,)]+)*|[a-z]+(?:/[a-z]+)+)\)"

    def colorize_match(match: re.Match) -> str:
        content = match.group(1)
        if "/" in content:
            parts = content.split("/")
            colored_parts = [f"\033[96m{p.strip()}\033[0m" for p in parts]
            return f"({'/'.join(colored_parts)})"
        parts = content.split(",")
        colored_parts = []
        for part in parts:
            part = part.strip()
            if "=" in part:
                cmd, desc = part.split("=", 1)
                colored_parts.append(f"\033[96m{cmd.strip()}\033[0m={desc.strip()}")
            else:
                colored_parts.append(part)
        return f"({', '.join(colored_parts)})"

    return re.sub(pattern, colorize_match, text)


def colorize_inline_commands(text: str) -> str:
    """Colorize quoted examples and common inline subcommand keys."""
    text = re.sub(r"'([a-z0-9\s_-]+)'", lambda m: f"'\033[96m{m.group(1)}\033[0m'", text)
    text = re.sub(
        r"\b(q|i|l|list|help|all)\b(?=\s*[=,]|\s*$)",
        lambda m: f"\033[96m{m.group(1)}\033[0m",
        text,
    )

    def _color_key_before_sep(match: re.Match) -> str:
        prefix = match.group(1)
        key = match.group(2)
        sep = match.group(3)
        return f"{prefix}\033[96m{key}\033[0m{sep}"

    return re.sub(
        r"(^|\s)([a-z][a-z0-9_-]{0,3})(\s*[:=])",
        _color_key_before_sep,
        text,
        flags=re.MULTILINE,
    )


def colorize_single_key_inline_commands(text: str) -> str:
    """Colorize operando-style one-character ``x=`` and ``x:`` inline commands."""
    text = re.sub(r"'([a-z0-9\s_-]+)'", lambda m: f"'\033[96m{m.group(1)}\033[0m'", text)
    text = re.sub(r"\b([a-z0-9])=", lambda m: f"\033[96m{m.group(1)}\033[0m=", text)
    return re.sub(r"\b([a-z0-9]): ", lambda m: f"\033[96m{m.group(1)}\033[0m: ", text)


__all__ = [
    "FilterIMKWarning",
    "safe_input",
    "prompt_float",
    "colorize_prompt",
    "colorize_inline_commands",
    "colorize_single_key_inline_commands",
]
