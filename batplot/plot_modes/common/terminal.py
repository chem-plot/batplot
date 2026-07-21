"""Terminal input and prompt-color helpers shared by interactive modes."""

from __future__ import annotations

import os
import re
import sys
import threading
from contextlib import contextmanager
from typing import Iterator

_IMK_MARKERS = (
    "IMKCFRunLoopWakeUpReliable",
    "error messaging the mach port",
)


def is_imk_noise(message: str | bytes) -> bool:
    """Return True for harmless macOS Input Method Kit stderr noise."""
    if isinstance(message, bytes):
        try:
            text = message.decode("utf-8", errors="ignore")
        except Exception:
            return False
    else:
        text = message
    return any(marker in text for marker in _IMK_MARKERS)


class FilterIMKWarning:
    """Filter macOS IMK warnings while preserving all other stderr output."""

    def __init__(self, original_stderr):
        self.original_stderr = original_stderr

    def write(self, message):
        if not is_imk_noise(message):
            self.original_stderr.write(message)

    def flush(self):
        self.original_stderr.flush()


class _DarwinFd2Guard:
    """Redirect OS stderr (fd 2) through a pipe that drops macOS IMK noise."""

    def __init__(self) -> None:
        self._orig_stderr = sys.stderr
        self._orig_fd: int | None = None
        self._read_fd: int | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        read_fd, write_fd = os.pipe()
        orig_fd = os.dup(2)
        try:
            os.dup2(write_fd, 2)
            os.close(write_fd)
            self._orig_fd = orig_fd
            self._read_fd = read_fd
            sys.stderr = os.fdopen(
                2,
                "w",
                buffering=1,
                closefd=False,
                encoding=getattr(sys.stderr, "encoding", None) or "utf-8",
                errors="replace",
            )
            self._thread = threading.Thread(
                target=self._pump,
                daemon=True,
                name="batplot-imk-filter",
            )
            self._thread.start()
        except Exception:
            try:
                os.dup2(orig_fd, 2)
            except OSError:
                pass
            try:
                os.close(orig_fd)
            except OSError:
                pass
            try:
                os.close(read_fd)
            except OSError:
                pass
            sys.stderr = self._orig_stderr
            self._orig_fd = None
            self._read_fd = None
            raise

    def _pump(self) -> None:
        read_fd = self._read_fd
        orig_fd = self._orig_fd
        if read_fd is None or orig_fd is None:
            return
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = os.read(read_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._forward(orig_fd, line + b"\n")
        if buf:
            self._forward(orig_fd, buf)

    @staticmethod
    def _forward(orig_fd: int, data: bytes) -> None:
        if is_imk_noise(data):
            return
        try:
            os.write(orig_fd, data)
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        try:
            sys.stderr.flush()
        except Exception:
            pass
        if self._orig_fd is not None:
            try:
                os.dup2(self._orig_fd, 2)
            except OSError:
                pass
        if self._read_fd is not None:
            try:
                os.close(self._read_fd)
            except OSError:
                pass
            self._read_fd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._orig_fd is not None:
            try:
                os.close(self._orig_fd)
            except OSError:
                pass
            self._orig_fd = None
        sys.stderr = self._orig_stderr


_imk_guard: _DarwinFd2Guard | None = None
_imk_guard_depth = 0


@contextmanager
def imk_stderr_guard() -> Iterator[None]:
    """Suppress macOS IMK stderr noise during matplotlib GUI redraws (not ``input()``)."""
    global _imk_guard, _imk_guard_depth
    if sys.platform != "darwin":
        yield
        return
    if _imk_guard_depth == 0:
        _imk_guard = _DarwinFd2Guard()
        _imk_guard.start()
    _imk_guard_depth += 1
    try:
        yield
    finally:
        _imk_guard_depth -= 1
        if _imk_guard_depth == 0 and _imk_guard is not None:
            _imk_guard.stop()
            _imk_guard = None


def safe_input(prompt: str = "", *, cancel_on_interrupt: bool = False) -> str:
    """Call ``input`` while suppressing harmless macOS IMK terminal warnings."""
    sys.stdout.flush()
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


def prompt_menu_key(
    prompt: str = "Press a key: ",
    *,
    cancel_on_interrupt: bool = True,
) -> str:
    """Read a main-menu command after the menu text is fully visible."""
    return safe_input(colorize_prompt(prompt), cancel_on_interrupt=cancel_on_interrupt).strip().lower()


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
    "imk_stderr_guard",
    "is_imk_noise",
    "prompt_menu_key",
    "safe_input",
    "prompt_float",
    "colorize_prompt",
    "colorize_inline_commands",
    "colorize_single_key_inline_commands",
]
