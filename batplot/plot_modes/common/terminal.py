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


_CONSOLE_SAFE_REPLACEMENTS = (
    ("→", "->"),  # right arrow
    ("←", "<-"),  # left arrow
    ("↔", "<->"),  # left-right arrow
    ("✓", "[OK]"),  # check
    ("✗", "[X]"),  # ballot x
    ("✔", "[OK]"),  # heavy check
    ("⚠", "!"),  # warning
    ("θ", "theta"),
    ("Θ", "Theta"),
    ("λ", "lambda"),
    ("Λ", "Lambda"),
    ("µ", "u"),
    ("μ", "u"),
    ("σ", "sigma"),
    ("Δ", "d"),
    ("⁻", "-"),
    ("¹", "1"),
    ("²", "2"),
    ("³", "3"),
    ("₁", "1"),
    ("₂", "2"),
    ("Å", "A"),
    ("•", "*"),
    ("—", "-"),
    ("–", "-"),
    ("…", "..."),
    ("≥", ">="),
    ("≤", "<="),
    ("≠", "!="),
    ("≈", "~"),
    ("×", "x"),
    ("─", "-"),
    ("│", "|"),
    ("╭", "+"),
    ("╮", "+"),
    ("╯", "+"),
    ("╰", "+"),
    ("└", "+"),
    ("┘", "+"),
    ("┌", "+"),
    ("┐", "+"),
)


def _stream_encoding(stream) -> str:
    return (getattr(stream, "encoding", None) or "").lower().replace("-", "")


def stream_needs_console_safe(stream=None) -> bool:
    """True when the stream is unlikely to accept full Unicode (e.g. cp1252)."""
    enc = _stream_encoding(stream if stream is not None else sys.stdout)
    if not enc or enc in ("utf8", "utf8sig", "utf"):
        return False
    return True


def console_safe_text(text: str) -> str:
    """Transliterate menu/banner characters that break classic Windows consoles."""
    out = str(text)
    for src, dst in _CONSOLE_SAFE_REPLACEMENTS:
        if src in out:
            out = out.replace(src, dst)
    return out


_orig_builtin_print = print
_safe_builtins_installed = False


def safe_console_print(*args, **kwargs) -> None:
    """``print`` that never crashes on legacy Windows code pages (cp1252).

    On non-UTF-8 consoles, transliterate common scientific/menu glyphs first.
    Always fall back to ``errors='replace'`` if encoding still fails.
    """
    stream = kwargs.get("file", sys.stdout)
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    flush = bool(kwargs.get("flush", False))
    parts = [str(a) for a in args]
    if stream_needs_console_safe(stream):
        parts = [console_safe_text(p) for p in parts]
    try:
        _orig_builtin_print(*parts, **kwargs)
        return
    except UnicodeEncodeError:
        pass
    text = sep.join(parts) + end
    enc = getattr(stream, "encoding", None) or "utf-8"
    try:
        safe = text.encode(enc, errors="replace").decode(enc, errors="replace")
        stream.write(safe)
        if flush:
            try:
                stream.flush()
            except Exception:
                pass
    except Exception:
        try:
            buf = getattr(stream, "buffer", None)
            if buf is not None:
                buf.write(text.encode(enc, errors="replace"))
        except Exception:
            pass


def _enable_windows_vt_mode() -> None:
    """Enable ANSI escape processing on modern Windows consoles (best-effort)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # STD_OUTPUT_HANDLE = -11, ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def install_safe_builtins() -> None:
    """Route built-in ``print`` through :func:`safe_console_print` (once).

    Called from the CLI entry so interactive menus and errors stay readable on
    Windows cp1252 without editing every ``print`` call site.
    """
    global _safe_builtins_installed
    if _safe_builtins_installed:
        return
    import builtins

    _enable_windows_vt_mode()
    builtins.print = safe_console_print  # type: ignore[assignment]
    _safe_builtins_installed = True


def safe_input(prompt: str = "", *, cancel_on_interrupt: bool = False) -> str:
    """Call ``input`` while suppressing harmless macOS IMK terminal warnings."""
    sys.stdout.flush()
    original_stderr = sys.stderr
    sys.stderr = FilterIMKWarning(original_stderr)
    prompt_s = str(prompt)
    if stream_needs_console_safe(sys.stdout):
        prompt_s = console_safe_text(prompt_s)
    try:
        try:
            return input(prompt_s)
        except UnicodeEncodeError:
            # Prompt still not encodable — ASCII-replace then retry once.
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            prompt_s = prompt_s.encode(enc, errors="replace").decode(enc, errors="replace")
            return input(prompt_s)
    except KeyboardInterrupt:
        if cancel_on_interrupt:
            try:
                safe_console_print()
            except Exception:
                pass
            return ""
        raise
    except EOFError:
        if cancel_on_interrupt:
            try:
                safe_console_print()
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
    """Colorize command keys in parenthesized prompts such as ``(s=size, q=return)``.

    Also closes any open menu-description block (trailing dashed line) so the
    input row is visually separated from the key list above.
    """
    try:
        from .menu_rendering import menu_block_end

        menu_block_end()
    except Exception:
        pass

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
    "console_safe_text",
    "stream_needs_console_safe",
    "safe_console_print",
    "install_safe_builtins",
    "safe_input",
    "prompt_float",
    "colorize_prompt",
    "colorize_inline_commands",
    "colorize_single_key_inline_commands",
]
