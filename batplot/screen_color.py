"""Screen eyedropper with magnifier (cross-platform: macOS / Windows / Linux).

Opens in a *subprocess* so tkinter never touches the matplotlib parent process
(critical on macOS). Prints ``PICKED:#rrggbb`` on stdout when confirmed.

Design notes
------------
* Prefer **native** region capture per OS, then optional Pillow ``ImageGrab``.
* Sample a cursor-centered region (not a full-desktop remap) so Retina /
  multi-monitor layouts stay accurate.
* Windows: enable DPI awareness *before* creating Tk so cursor and BitBlt
  share the same coordinate space.
* Linux: try Wayland (``grim``) and X11 tools (ImageMagick / scrot / …).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Optional, Tuple

# Zoom: odd sample size so there is a true center pixel.
_SAMPLE = 15
_MAG_SCALE = 14  # pixels per sample cell in the magnifier view
_REFRESH_MS = 50


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_wayland_session() -> bool:
    """True when the active Linux session is Wayland (not pure X11)."""
    if not _is_linux():
        return False
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


_last_cursor_source = "unknown"  # wayland | x11 | tk | win | mac | none


def _cursor_pos_wayland() -> Optional[Tuple[int, int]]:
    """Best-effort compositor cursor position (not XWayland/Tk space)."""
    # Hyprland: `hyprctl cursorpos` → "x,y"
    if shutil.which("hyprctl"):
        try:
            out = subprocess.check_output(
                ["hyprctl", "cursorpos"], text=True, timeout=1,
            )
            raw = (out or "").strip().replace(",", " ")
            parts = [p for p in raw.split() if p]
            if len(parts) >= 2:
                return int(float(parts[0])), int(float(parts[1]))
        except Exception:
            pass
    return None


def pick_screen_color(*, timeout: float = 600.0) -> Optional[str]:
    """Pick one or more screen colors; return the last pick (or ``None``).

    Magnifier stays open across picks. Terminal: Enter = add color, q = done.
    """
    colors = pick_screen_colors(timeout=timeout)
    return colors[-1] if colors else None


def _try_read_line(timeout: float = 0.25) -> Optional[str]:
    """Read one terminal line with timeout, or ``None`` if nothing yet.

    Used so closing the magnifier window is detected while waiting at ``Picker>``.
    """
    if _is_windows():
        return _try_read_line_windows(timeout)
    try:
        import select

        ready, _, _ = select.select([sys.stdin], [], [], max(0.0, float(timeout)))
        if not ready:
            return None
        line = sys.stdin.readline()
        if line == "":
            return ""
        return line.rstrip("\r\n")
    except Exception:
        try:
            import time as _t

            _t.sleep(max(0.0, float(timeout)))
        except Exception:
            pass
        return None


_win_picker_buf: list = []


def _try_read_line_windows(timeout: float) -> Optional[str]:
    """Line reader for Windows consoles (``select`` does not work on stdin)."""
    import time as _t

    try:
        import msvcrt  # type: ignore
    except Exception:
        _t.sleep(max(0.0, float(timeout)))
        return None

    end = _t.monotonic() + max(0.0, float(timeout))
    while _t.monotonic() < end:
        if not msvcrt.kbhit():
            _t.sleep(0.02)
            continue
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            line = "".join(_win_picker_buf)
            _win_picker_buf.clear()
            return line
        if ch == "\x08":  # backspace
            if _win_picker_buf:
                _win_picker_buf.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if ch in ("\x00", "\xe0"):  # function / arrow prefix
            try:
                msvcrt.getwch()
            except Exception:
                pass
            continue
        if ch == "\x03":  # Ctrl+C
            raise KeyboardInterrupt
        _win_picker_buf.append(ch)
        sys.stdout.write(ch)
        sys.stdout.flush()
    return None


def _windows_popen_kwargs() -> dict:
    """Avoid an extra console flash when spawning the magnifier on Windows."""
    if not sys.platform.startswith("win"):
        return {}
    # CREATE_NO_WINDOW = 0x08000000 (Python 3.7+ exposes the constant).
    flag = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    return {"creationflags": flag}


def pick_screen_colors(*, timeout: float = 600.0, show_intro: bool = True) -> list:
    """Show magnifier; pick multiple colors via the terminal; window stays open.

    - Enter = sample color under the cursor (magnifier stays)
    - q then Enter = finish and close magnifier
    - Window close (X) = same as done
    Returns the list of picked ``#rrggbb`` values (may be empty if cancelled).
    """
    live_path = None
    proc = None
    picked: list = []
    try:
        fd, live_path = tempfile.mkstemp(prefix="batplot_color_", suffix=".hex")
        os.close(fd)
        try:
            os.unlink(live_path)
        except OSError:
            pass

        cmd = [sys.executable, "-m", "batplot.screen_color", "--live", live_path]
        env = os.environ.copy()
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "XAUTHORITY"):
            if key in os.environ:
                env[key] = os.environ[key]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            **_windows_popen_kwargs(),
        )

        if show_intro:
            try:
                from .plot_modes.common.menu_rendering import menu_block_begin, menu_block_end

                menu_block_begin(force_new=True)
                print("Screen color picker (magnifier is preview only):")
                print("  Keep the mouse on a color.")
                print("  In THIS terminal:")
                print("    Enter        = pick this color (window stays — pick more)")
                print("    q then Enter = done (close magnifier, return to color menu)")
                print("  Or close the magnifier window (X) = done.")
                menu_block_end()
            except Exception:
                sep = "-" * 60
                print(sep)
                print("Screen color picker (magnifier is preview only):")
                print("  Keep the mouse on a color.")
                print("  Enter = pick (stays open) | q / window X = done")
                print(sep)
        sys.stdout.flush()

        import time as _time

        deadline = _time.monotonic() + min(float(timeout), 3600.0)
        need_prompt = True
        while _time.monotonic() < deadline:
            if proc.poll() is not None:
                err = ""
                try:
                    err = (proc.stderr.read() or "") if proc.stderr else ""
                except Exception:
                    pass
                if err.strip():
                    print(err.strip())
                print("Magnifier closed.")
                break
            if need_prompt:
                sys.stdout.write("Picker> ")
                sys.stdout.flush()
                need_prompt = False
            try:
                raw = _try_read_line(0.25)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if raw is None:
                continue
            need_prompt = True
            low = (raw or "").strip().lower()
            if low in ("q", "quit", "done", "cancel", "esc", "escape"):
                break
            if low in ("", "y", "yes", "p", "pick", "ok", "a", "add"):
                hex_c = _read_live_hex(live_path)
                if not hex_c:
                    _time.sleep(0.15)
                    hex_c = _read_live_hex(live_path)
                if not hex_c:
                    print("No color yet — move the mouse onto a color, then press Enter.")
                    continue
                picked.append(hex_c)
                try:
                    from .color_utils import format_color_listing

                    shown = format_color_listing(hex_c)
                except Exception:
                    shown = hex_c
                print(
                    f"  + {shown}  ({len(picked)} picked). "
                    "Enter = pick another, q or window X = done."
                )
                sys.stdout.flush()
                continue
            print("Enter = pick, q or window X = done.")
        return list(picked)
    except Exception as exc:
        print(f"Screen color picker failed: {exc}")
        return list(picked)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if live_path:
            try:
                os.unlink(live_path)
            except OSError:
                pass
        # Prevent leftover Enter keystrokes from exiting the color menu
        # (blank input often means "q/back" in batplot menus).
        _flush_stdin()
        _win_picker_buf.clear()


def _flush_stdin() -> None:
    """Discard buffered terminal keystrokes (cross-platform best-effort).

    Critical: a leftover Enter after the picker makes many batplot color menus
    treat blank input as \"back/quit\" and exit the whole color UI.
    """
    try:
        if _is_windows():
            import msvcrt  # type: ignore

            # Match the live reader (getwch): getch leaves orphan bytes after
            # non-ASCII / wide console input and can re-trigger blank "back".
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    try:
                        msvcrt.getwch()
                    except Exception:
                        pass
            return
    except Exception:
        pass
    # POSIX: termios flush is the reliable way (select+os.read can fight
    # with Python's text stdin buffering).
    try:
        import termios

        if sys.stdin and hasattr(sys.stdin, "fileno"):
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            return
    except Exception:
        pass
    try:
        import select

        if not sys.stdin or not hasattr(sys.stdin, "fileno"):
            return
        fd = sys.stdin.fileno()
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if not ready:
                break
            try:
                os.read(fd, 1024)
            except Exception:
                break
    except Exception:
        pass


def _read_live_hex(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return _normalize_hex(fh.read().strip())
    except Exception:
        return None


def _write_live_hex(path: str, hex_c: str) -> None:
    """Atomically write current hex so the parent can read a complete value."""
    try:
        directory = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(prefix="batplot_color_tmp_", suffix=".hex", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(hex_c)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except Exception:
                    pass
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(hex_c)
        except Exception:
            pass


def _normalize_hex(value: str) -> Optional[str]:
    if not value:
        return None
    s = value.strip().lower()
    if not s.startswith("#"):
        s = "#" + s
    if len(s) >= 7 and all(c in "0123456789abcdef" for c in s[1:7]):
        return s[:7]
    return None


def _capture_help_text() -> str:
    if _is_macos():
        return (
            "Screen color picker needs Screen Recording permission "
            "(System Settings → Privacy & Security → Screen Recording)."
        )
    if _is_windows():
        return (
            "Screen color picker failed. Try again; if it persists, install Pillow "
            "(pip install Pillow) which provides a reliable Windows grab fallback."
        )
    return (
        "Screen color picker failed. Install one of: Pillow, grim (Wayland), "
        "scrot / ImageMagick import / gnome-screenshot (X11)."
    )


# ---------------------------------------------------------------------------
# Windows DPI (must run before Tk)
# ---------------------------------------------------------------------------

def _windows_enable_dpi_awareness() -> None:
    if not _is_windows():
        return
    try:
        import ctypes

        # Per-monitor v2 when available (Win10 1703+).
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cursor / screen size
# ---------------------------------------------------------------------------

def _cursor_pos(tk_root: Any = None) -> Tuple[int, int]:
    """Return global cursor position in screen coordinates.

    On Wayland, prefer compositor APIs (``hyprctl``) and avoid mixing Tk/X11
    pointer coords with ``grim`` region geometry.
    """
    global _last_cursor_source
    wayland = _is_wayland_session()
    if wayland:
        wl = _cursor_pos_wayland()
        if wl is not None:
            _last_cursor_source = "wayland"
            return wl

    # Prefer existing Tk root on X11 / macOS / Windows (same DPI space as UI).
    # On Wayland Tk is XWayland — skip when compositor query already failed so
    # ``_grab_region_linux`` can avoid pairing X11 coords with ``grim``.
    if tk_root is not None and not wayland:
        try:
            _last_cursor_source = "tk"
            return int(tk_root.winfo_pointerx()), int(tk_root.winfo_pointery())
        except Exception:
            pass

    if _is_macos():
        try:
            import ctypes
            import ctypes.util

            path = ctypes.util.find_library("CoreGraphics") or (
                "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            )
            cg = ctypes.CDLL(path)

            class CGPoint(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

            cg.CGEventCreate.restype = ctypes.c_void_p
            cg.CGEventCreate.argtypes = [ctypes.c_void_p]
            cg.CGEventGetLocation.restype = CGPoint
            cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            event = cg.CGEventCreate(None)
            if event:
                pt = cg.CGEventGetLocation(event)
                _last_cursor_source = "mac"
                return int(pt.x), int(pt.y)
        except Exception:
            pass

    if _is_windows():
        try:
            import ctypes
            from ctypes import wintypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

            pt = POINT()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                _last_cursor_source = "win"
                return int(pt.x), int(pt.y)
        except Exception:
            pass

    # Linux X11 helper — skip on Wayland (XWayland coords != compositor coords)
    if not wayland and shutil.which("xdotool"):
        try:
            out = subprocess.check_output(
                ["xdotool", "getmouselocation", "--shell"],
                text=True,
                timeout=1,
            )
            vals = {}
            for line in out.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    vals[k] = v
            _last_cursor_source = "x11"
            return int(vals["X"]), int(vals["Y"])
        except Exception:
            pass

    # Last resort: temporary Tk (XWayland on Wayland)
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            root.update_idletasks()
        except Exception:
            pass
        x, y = int(root.winfo_pointerx()), int(root.winfo_pointery())
        try:
            root.destroy()
        except Exception:
            pass
        _last_cursor_source = "tk"
        return x, y
    except Exception:
        _last_cursor_source = "none"
        return 0, 0


def _screen_logical_size(tk_root: Any = None) -> Tuple[int, int]:
    if tk_root is not None:
        try:
            return int(tk_root.winfo_screenwidth()), int(tk_root.winfo_screenheight())
        except Exception:
            pass
    if _is_windows():
        try:
            import ctypes

            user32 = ctypes.windll.user32
            # Virtual desktop (multi-monitor)
            w = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
            h = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
            if w > 0 and h > 0:
                return w, h
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except Exception:
            pass
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        w, h = int(root.winfo_screenwidth()), int(root.winfo_screenheight())
        root.destroy()
        return w, h
    except Exception:
        return 1920, 1080


# ---------------------------------------------------------------------------
# Screenshots → RGB uint8 (H, W, 3)
# ---------------------------------------------------------------------------

def _as_rgb_u8(arr):
    import numpy as np

    a = np.asarray(arr)
    if a.ndim == 2:
        a = np.stack([a, a, a], axis=-1)
    if a.ndim == 3 and a.shape[2] >= 3:
        a = a[:, :, :3]
    if a.dtype != np.uint8:
        mx = float(np.nanmax(a)) if a.size else 0.0
        if mx <= 1.0:
            a = (a * 255.0).clip(0, 255)
        a = a.astype("uint8")
    return a


def _read_image_file(path: str):
    try:
        from PIL import Image  # type: ignore

        return _as_rgb_u8(Image.open(path).convert("RGB"))
    except Exception:
        pass
    try:
        import matplotlib.image as mpimg  # type: ignore

        return _as_rgb_u8(mpimg.imread(path))
    except Exception:
        return None


def _downsample_to_sample(rgb):
    import numpy as np

    if rgb is None or getattr(rgb, "size", 0) == 0:
        return None
    h, w = rgb.shape[:2]
    if h <= 0 or w <= 0:
        return None
    if h == _SAMPLE and w == _SAMPLE:
        return rgb
    ys = np.linspace(0, max(h - 1, 0), _SAMPLE).astype(int)
    xs = np.linspace(0, max(w - 1, 0), _SAMPLE).astype(int)
    return rgb[np.ix_(ys, xs)].copy()


def _center_hex(patch) -> Optional[str]:
    if patch is None or getattr(patch, "size", 0) == 0:
        return None
    half = patch.shape[0] // 2
    r, g, b = (int(v) for v in patch[half, half, :3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _grab_region_pillow(left: int, top: int, width: int, height: int):
    try:
        from PIL import ImageGrab  # type: ignore

        box = (left, top, left + width, top + height)
        try:
            img = ImageGrab.grab(bbox=box, all_screens=True)
        except TypeError:
            img = ImageGrab.grab(bbox=box)
        return _as_rgb_u8(img)
    except Exception:
        return None


def _grab_region_macos(left: int, top: int, width: int, height: int):
    path = None
    try:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        # -R: left,top,width,height in screen points; Retina PNG may be 2×.
        res = subprocess.run(
            ["screencapture", "-x", "-t", "png", f"-R{left},{top},{width},{height}", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
        if res.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
            return None
        return _read_image_file(path)
    except Exception:
        return None
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _grab_region_windows(left: int, top: int, width: int, height: int):
    """GDI BitBlt of a rectangle (supports multi-monitor / negative virtual coords)."""
    try:
        import ctypes
        from ctypes import wintypes
        import numpy as np

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        if not hdc:
            return None
        memdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
        old = gdi32.SelectObject(memdc, bmp)
        ok = gdi32.BitBlt(memdc, 0, 0, width, height, hdc, left, top, 0x00CC0020)
        if not ok:
            gdi32.SelectObject(memdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(memdc)
            user32.ReleaseDC(0, hdc)
            return None

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = width
        bmi.biHeight = -height  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0
        buf_size = width * height * 4
        buf = (ctypes.c_ubyte * buf_size)()
        got = gdi32.GetDIBits(memdc, bmp, 0, height, buf, ctypes.byref(bmi), 0)
        gdi32.SelectObject(memdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)
        if not got:
            return None
        arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4))
        return arr[:, :, [2, 1, 0]].copy()  # BGRA → RGB
    except Exception:
        return None


def _grab_region_linux(left: int, top: int, width: int, height: int):
    """Wayland (grim) and X11 (ImageMagick / scrot / gnome-screenshot / …).

    Never mix Tk/X11 cursor coords with ``grim`` on Wayland: if the compositor
    cursor query failed, skip ``grim`` and use X11 grab tools instead.
    """
    geom_grim = f"{left},{top} {width}x{height}"
    geom_im = f"{width}x{height}+{left}+{top}"
    wayland = _is_wayland_session()
    # Only use grim when cursor coords came from a Wayland compositor query.
    # Precise region tools first, then full-screen + crop.
    attempts: list[list[str]] = []
    if shutil.which("grim") and (not wayland or _last_cursor_source == "wayland"):
        attempts.append(["grim", "-g", geom_grim, "{path}"])
    if shutil.which("import"):
        attempts.append(["import", "-silent", "-window", "root", "-crop", geom_im, "{path}"])
    if shutil.which("maim"):
        attempts.append(["maim", "-g", geom_im, "{path}"])
    if shutil.which("scrot"):
        attempts.append(["scrot", "-o", "{path}"])
    if shutil.which("gnome-screenshot"):
        attempts.append(["gnome-screenshot", "-f", "{path}"])
    if shutil.which("spectacle"):
        attempts.append(["spectacle", "-b", "-n", "-o", "{path}"])

    for template in attempts:
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            cmd = [path if part == "{path}" else part for part in template]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=8)
            if res.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
                continue
            rgb = _read_image_file(path)
            if rgb is None or rgb.size == 0:
                continue
            tool = os.path.basename(cmd[0])
            if tool in ("scrot", "gnome-screenshot", "spectacle"):
                ih, iw = rgb.shape[:2]
                x0 = max(0, min(left, iw - 1))
                y0 = max(0, min(top, ih - 1))
                x1 = max(x0 + 1, min(left + width, iw))
                y1 = max(y0 + 1, min(top + height, ih))
                rgb = rgb[y0:y1, x0:x1]
            if rgb is not None and rgb.size:
                return rgb
        except Exception:
            continue
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    return None


def _grab_region(left: int, top: int, width: int, height: int):
    """Capture a screen rectangle; return RGB uint8 or None."""
    left, top = int(left), int(top)
    width, height = max(int(width), 1), max(int(height), 1)

    # Native first (most reliable region + DPI behavior), then Pillow.
    native = None
    if _is_macos():
        native = _grab_region_macos(left, top, width, height)
    elif _is_windows():
        native = _grab_region_windows(left, top, width, height)
    else:
        native = _grab_region_linux(left, top, width, height)
    if native is not None and getattr(native, "size", 0):
        return native

    pillow = _grab_region_pillow(left, top, width, height)
    if pillow is not None and getattr(pillow, "size", 0):
        return pillow
    return None


def _grab_patch_at_cursor(tk_root: Any = None) -> Tuple[Optional[object], Optional[str]]:
    """Capture ``_SAMPLE``×``_SAMPLE`` region around cursor → (patch, hex)."""
    cx, cy = _cursor_pos(tk_root)
    half = _SAMPLE // 2
    left, top = cx - half, cy - half
    rgb = _grab_region(left, top, _SAMPLE, _SAMPLE)
    patch = _downsample_to_sample(rgb)
    return patch, _center_hex(patch)


def _sample_around_cursor(rgb, cx: int, cy: int, logical_w: int, logical_h: int):
    """Test helper: sample from a full-frame buffer with logical→pixel mapping."""
    import numpy as np

    if rgb is None or rgb.size == 0:
        return None, None
    ih, iw = rgb.shape[0], rgb.shape[1]
    sx = iw / max(logical_w, 1)
    sy = ih / max(logical_h, 1)
    px = int(round(cx * sx))
    py = int(round(cy * sy))
    px = max(0, min(iw - 1, px))
    py = max(0, min(ih - 1, py))
    half = _SAMPLE // 2
    patch = np.zeros((_SAMPLE, _SAMPLE, 3), dtype=np.uint8)
    for dy in range(_SAMPLE):
        for dx in range(_SAMPLE):
            x = px - half + dx
            y = py - half + dy
            if 0 <= x < iw and 0 <= y < ih:
                patch[dy, dx] = rgb[y, x]
            else:
                patch[dy, dx] = (40, 40, 40)
    return patch, _center_hex(patch)


# ---------------------------------------------------------------------------
# Live magnifier (subprocess --live <hexfile>) — display only, no key handling
# ---------------------------------------------------------------------------

def _run_live_magnifier(live_path: str) -> int:
    """Update magnifier + write current cursor hex to ``live_path`` until killed."""
    _windows_enable_dpi_awareness()

    try:
        import tkinter as tk
    except Exception as exc:
        print(f"ERROR: tkinter unavailable: {exc}", file=sys.stderr)
        print(_capture_help_text(), file=sys.stderr)
        return 2

    import numpy as np

    root = tk.Tk()
    root.title("batplot color picker (preview)")
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        root.resizable(False, False)
    except Exception:
        pass

    logical_w, _logical_h = _screen_logical_size(root)
    view = _SAMPLE * _MAG_SCALE

    frame = tk.Frame(root, padx=10, pady=10)
    frame.pack()
    ui_font = ("Segoe UI", 11) if _is_windows() else ("Helvetica", 12)
    tk.Label(
        frame,
        text=(
            "PREVIEW ONLY — type in the TERMINAL\n"
            "Keep mouse on a color\n"
            "Enter = pick (stays open) | q or window X = done"
        ),
        font=ui_font,
        justify="left",
    ).pack(pady=(0, 8), anchor="w")

    canvas = tk.Canvas(
        frame, width=view, height=view, highlightthickness=1, highlightbackground="#333"
    )
    canvas.pack()
    swatch = tk.Canvas(
        frame, width=view, height=28, highlightthickness=1, highlightbackground="#333"
    )
    swatch.pack(pady=(6, 2))
    hex_var = tk.StringVar(value="#------")
    mono = "Menlo" if _is_macos() else ("Consolas" if _is_windows() else "Courier")
    tk.Label(frame, textvariable=hex_var, font=(mono, 16)).pack(pady=(2, 4))

    photo_holder: dict = {"img": None, "path": None}

    def _pointer_over_self() -> bool:
        try:
            px, py = int(root.winfo_pointerx()), int(root.winfo_pointery())
            x = int(root.winfo_rootx())
            y = int(root.winfo_rooty())
            w = int(root.winfo_width())
            h = int(root.winfo_height())
            return x <= px < x + w and y <= py < y + h
        except Exception:
            return False

    def _draw_magnifier(patch, hex_c: str):
        big = np.repeat(np.repeat(patch, _MAG_SCALE, axis=0), _MAG_SCALE, axis=1)
        h, w, _ = big.shape
        path = photo_holder.get("path")
        if not path:
            fd, path = tempfile.mkstemp(suffix=".ppm")
            os.close(fd)
            photo_holder["path"] = path
        with open(path, "wb") as fh:
            fh.write(f"P6\n{w} {h}\n255\n".encode("ascii"))
            fh.write(np.ascontiguousarray(big, dtype="uint8").tobytes())
        img = tk.PhotoImage(file=path)
        photo_holder["img"] = img
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=img)
        mid = view // 2
        canvas.create_line(mid, 0, mid, mid - 6, fill="#ffffff", width=1)
        canvas.create_line(mid, mid + 6, mid, view, fill="#ffffff", width=1)
        canvas.create_line(0, mid, mid - 6, mid, fill="#ffffff", width=1)
        canvas.create_line(mid + 6, mid, view, mid, fill="#ffffff", width=1)
        canvas.create_rectangle(mid - 4, mid - 4, mid + 4, mid + 4, outline="#000000", width=1)
        canvas.create_rectangle(mid - 5, mid - 5, mid + 5, mid + 5, outline="#ffffff", width=1)
        swatch.delete("all")
        swatch.create_rectangle(0, 0, view, 28, fill=hex_c, outline="")
        hex_var.set(hex_c.upper())
        _write_live_hex(live_path, hex_c)

    def _tick():
        if not _pointer_over_self():
            patch, hex_c = _grab_patch_at_cursor(root)
            if patch is not None and hex_c:
                try:
                    _draw_magnifier(patch, hex_c)
                except Exception:
                    pass
        root.after(_REFRESH_MS, _tick)

    def _on_close() -> None:
        try:
            root.destroy()
        except Exception:
            pass
        try:
            root.quit()
        except Exception:
            pass

    try:
        root.protocol("WM_DELETE_WINDOW", _on_close)
    except Exception:
        pass

    try:
        root.update_idletasks()
        win_w = max(int(root.winfo_reqwidth()), view + 40)
        margin = 24
        wx = max(margin, logical_w - win_w - margin)
        root.geometry(f"+{wx}+{margin}")
    except Exception:
        root.geometry("+40+40")

    try:
        root.lift()
        root.update()
    except Exception:
        pass

    if not _pointer_over_self():
        patch0, hex0 = _grab_patch_at_cursor(root)
        if patch0 is not None and hex0 is not None:
            try:
                _draw_magnifier(patch0, hex0)
            except Exception:
                pass

    root.after(_REFRESH_MS, _tick)
    try:
        root.mainloop()
    finally:
        path = photo_holder.get("path")
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    return 0


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "--live":
        return _run_live_magnifier(argv[1])
    print(
        "Usage: python -m batplot.screen_color --live <hexfile>\n"
        "(Normally launched by batplot color menu key e.)",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
