"""Utility helpers for batplot.

This module provides file organization and text formatting utilities used
throughout batplot. It handles cross-platform file dialogs, directory management,
and text formatting.

MAIN FUNCTIONS:
--------------
1. **Directory Management**: Create and manage subdirectories (e.g., Figures/)
   for organized output when batch processing files.

2. **File Dialogs**: Cross-platform folder/file picker dialogs:
   - macOS: Uses AppleScript (native, no dependencies)
   - Windows/Linux: Uses tkinter (if available)
   - Linux fallback: Uses zenity/kdialog (if available)

3. **Text Normalization**: Format labels for matplotlib rendering:
   - Handles LaTeX/mathtext syntax
   - Escapes special characters
   - Ensures proper rendering in plots

4. **Overwrite Protection**: Ask user before overwriting existing files
   (prevents accidental data loss).

CROSS-PLATFORM COMPATIBILITY:
----------------------------
This module handles differences between operating systems:
- macOS: Uses AppleScript (avoids tkinter crashes)
- Windows: Uses tkinter (standard GUI library)
- Linux: Tries tkinter first, falls back to zenity/kdialog

All dialogs gracefully degrade: if GUI dialogs aren't available, functions
return None and calling code can fall back to manual input.
"""

import argparse
import math
import os
import re
import sys
import shutil
import subprocess
import time
from typing import Callable, List, Optional, Tuple

from matplotlib.transforms import offset_copy


def natural_sort_key(name: str) -> list:
    """Generate a natural sorting key for filenames with numbers.

    Converts 'file_10.xy' to [(0,'file_'), (1,10), (0,'.xy')] so numerical
    parts sort numerically and string parts sort lexicographically.
    Wrapping each part as (type_flag, value) prevents TypeError when
    comparing entries whose leading tokens differ in type (e.g. '.DS_Store'
    vs '1.raw').
    """
    parts = []
    for match in re.finditer(r'(\d+|\D+)', name):
        text = match.group(0)
        if text.isdigit():
            parts.append((1, int(text)))
        else:
            parts.append((0, text.lower()))
    return parts


def parse_mass_mg_from_cli(arg: str) -> float:
    """Parse ``--mass`` for EC modes.

    - Plain number (e.g. ``7`` or ``7.0``): active mass in **milligrams**.
    - Suffix ``g`` (e.g. ``10g`` or ``10 g``): mass in **grams**, converted to mg.
    - Suffix ``mg`` (e.g. ``5mg``): explicit milligrams (same as a plain number).

    Raises:
        argparse.ArgumentTypeError: invalid or non-positive values.
    """
    s = str(arg).strip().lower().replace(" ", "")
    if not s:
        raise argparse.ArgumentTypeError("empty --mass value")
    try:
        if s.endswith("mg"):
            val = float(s[:-2])
        elif s.endswith("g"):
            val = float(s[:-1]) * 1000.0
        else:
            val = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid --mass value: {arg!r}") from None
    if not math.isfinite(val) or val <= 0:
        raise argparse.ArgumentTypeError("--mass must be a positive finite number")
    return val


def _ask_directory_dialog(initialdir: Optional[str] = None) -> Optional[str]:
    """Open a folder picker dialog with per-platform helpers.
    
    On macOS it uses AppleScript (osascript), avoiding the fragile Tk backend.
    On other platforms it tries tkinter first, then optional desktop helpers.
    Returns ``None`` if the dialog isn't available or the user cancels.
    """
    initialdir = os.path.abspath(initialdir or os.getcwd())
    if not os.path.isdir(initialdir):
        initialdir = os.path.expanduser("~")
    
    # macOS: ONLY use osascript dialog to avoid Tk crashes (never use tkinter on macOS)
    if sys.platform.startswith("darwin"):
        try:
            path = _ask_directory_dialog_macos(initialdir)
            # path will be None if user canceled, dialog failed, or path invalid
            # This is expected behavior - will fall back to manual input
            return path
        except Exception:
            # If AppleScript fails with an exception, return None (will fall back to manual input)
            return None
    
    # Windows/Linux: Try tkinter first. None → backend unavailable (fall through).
    # Empty-string sentinel is not used; cancel returns False so we do NOT open a
    # second dialog (zenity) after the user already dismissed tk.
    if not sys.platform.startswith("darwin"):
        try:
            path = _ask_directory_dialog_tk(initialdir)
            if path is False:
                return None  # dialog shown; user cancelled
            if path:
                return path
            # path is None → tk unavailable / failed to open
        except Exception:
            # If tkinter fails, continue to other methods
            pass
    
    # Linux desktop fallback via zenity/kdialog if available
    if sys.platform.startswith("linux"):
        try:
            path = _ask_directory_dialog_zenity(initialdir)
            if path:
                return path
        except Exception:
            pass
    
    return None


def _applescript_quote(value: str) -> str:
    """Escape a string for embedding in an AppleScript double-quoted literal."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )


def _ask_directory_dialog_macos(initialdir: str) -> Optional[str]:
    """Use AppleScript (osascript) to show the native folder picker on macOS.

    Returns the selected folder path, or None if user cancels or if any error occurs.
    """
    if not shutil.which("osascript"):
        return None

    prompt = "Select a folder"
    # Build AppleScript - use a single error handler to avoid syntax issues
    # Error -128 is user cancel, which is expected behavior
    if os.path.isdir(initialdir):
        # Use a variable for the path to avoid quoting issues
        script_parts = [
            f'set initialPath to "{_applescript_quote(initialdir)}"',
            "try",
            "    set defaultLocation to POSIX file initialPath",
            f'    set theFolder to choose folder with prompt "{_applescript_quote(prompt)}" default location defaultLocation',
            "    return POSIX path of theFolder",
            "on error errMsg number errNum",
            "    if errNum is -128 then",
            '        return ""',
            "    else",
            '        return ""',
            "    end if",
            "end try"
        ]
        script = "\n".join(script_parts)
    else:
        script_parts = [
            "try",
            f'    set theFolder to choose folder with prompt "{_applescript_quote(prompt)}"',
            "    return POSIX path of theFolder",
            "on error errMsg number errNum",
            "    if errNum is -128 then",
            '        return ""',
            "    else",
            '        return ""',
            "    end if",
            "end try"
        ]
        script = "\n".join(script_parts)
    
    try:
        # Run AppleScript - pass script via stdin instead of -e for better multi-line support
        # The dialog should appear and block until user responds
        res = subprocess.run(
            ["osascript"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,  # 5 minute timeout (user might take time to navigate)
        )
        
        # Check return code
        if res.returncode == 0:
            selection = (res.stdout or "").strip()
            # Empty string means user canceled (error -128 was caught and returned "")
            if not selection:
                return None
            # Normalize: resolve symlinks and ensure canonical form (critical for OneDrive/cloud paths)
            try:
                selection = os.path.normpath(os.path.abspath(selection))
                if os.path.isdir(selection):
                    selection = os.path.realpath(selection)
            except (OSError, ValueError):
                pass
            # Validate that the selected path exists and is a directory
            if os.path.isdir(selection):
                return selection
            # Path doesn't exist (shouldn't happen, but be safe)
            return None
        else:
            # AppleScript returned an error code (non-zero)
            # This could be a syntax error or other issue
            # The dialog might not have appeared at all
            # Return None to fall back to manual input
            return None
    except subprocess.TimeoutExpired:
        # Dialog timed out (user took too long or dialog didn't appear)
        return None
    except FileNotFoundError:
        # osascript not found (shouldn't happen since we check with shutil.which)
        return None
    except Exception:
        # Any other error (permission issues, etc.)
        return None


def _ask_directory_dialog_tk(initialdir: str):
    """Tkinter-based folder picker (Windows/Linux only - never used on macOS).

    Returns:
        str: selected folder
        False: dialog was shown and user cancelled (do not fall back to zenity)
        None: backend unavailable / failed before show (caller may fall back)
    """
    # Never use tkinter on macOS to avoid crashes
    if sys.platform.startswith("darwin"):
        return None
    
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    
    try:
        root = tk.Tk()
        root.withdraw()
        # Suppress any window updates that might cause issues
        root.update_idletasks()
        try:
            root.attributes('-topmost', True)
        except Exception:
            pass
        folder = filedialog.askdirectory(
            title="Select a folder",
            initialdir=initialdir,
            mustexist=False,
        )
        if folder:
            return folder
        return False  # shown; cancelled
    except Exception:
        # Failed before/during show — allow Linux zenity fallback
        return None
    finally:
        if root is not None:
            try:
                root.quit()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass


def _ask_directory_dialog_zenity(initialdir: str) -> Optional[str]:
    """Use zenity/kdialog on Linux if available."""
    cmd = None
    if shutil.which("zenity"):
        cmd = [
            "zenity",
            "--file-selection",
            "--directory",
            f"--filename={initialdir.rstrip(os.sep) + os.sep}",
            "--title=Select a folder",
        ]
    elif shutil.which("kdialog"):
        cmd = [
            "kdialog",
            "--getexistingdirectory",
            initialdir,
            "--title",
            "Select a folder",
        ]
    if not cmd:
        return None
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=300,
        )
        if res.returncode == 0:
            selection = res.stdout.strip()
            return selection or None
    except Exception:
        pass
    return None


def _strip_outer_quotes(token: str) -> str:
    """Remove one layer of matching outer quotes (needed for Windows shlex)."""
    tok = str(token)
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
        return tok[1:-1]
    return tok


def _parse_typed_path_list(line: str) -> list:
    """Parse a typed path line into absolute paths (spaces via quotes / shlex).

    Used when an OS file dialog returns empty (cancel or unavailable) so
    headless / SSH / broken-GUI sessions can still add files once.

    On Windows, ``shlex(..., posix=False)`` keeps outer quotes in tokens; those
    are stripped so ``\"C:\\\\My Files\\\\a.cif\"`` resolves correctly while
    unquoted ``C:\\\\Users\\\\...`` backslashes are still preserved.
    """
    text = (line or "").strip()
    if not text:
        return []
    try:
        import shlex

        tokens = shlex.split(text, posix=os.name != "nt")
    except Exception:
        tokens = text.split()
    out = []
    for tok in tokens:
        if not tok:
            continue
        tok = _strip_outer_quotes(tok)
        if not tok:
            continue
        p = os.path.abspath(os.path.expanduser(tok))
        out.append(p)
    return out


def _ask_file_dialog(
    initialdir: Optional[str] = None,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select a file",
) -> Optional[str]:
    """Open a platform-aware file picker dialog (macOS / Windows / Linux).

    ``filetypes`` is a tuple of extensions such as ``(".cif", ".CIF")``.
    Returns an absolute path, or ``None`` if the user cancels / no dialog is available.
    """
    paths = _ask_files_dialog(initialdir=initialdir, filetypes=filetypes, title=title, multiple=False)
    if not paths:
        return None
    return paths[0]


def _ask_files_dialog(
    initialdir: Optional[str] = None,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select file(s)",
    multiple: bool = True,
) -> list:
    """Open a platform-aware file picker; return a list of absolute paths.

    When ``multiple`` is False, at most one path is returned (same as
    :func:`_ask_file_dialog`). Cancel / unavailable dialog → ``[]``.
    """
    initialdir = os.path.abspath(initialdir or os.getcwd())
    if not os.path.isdir(initialdir):
        initialdir = os.path.expanduser("~")

    if sys.platform.startswith("darwin"):
        return _ask_files_dialog_macos(
            initialdir, filetypes=filetypes, title=title, multiple=multiple
        )

    # Tk: None → backend unavailable (fall through on Linux).
    # list (incl. []) → dialog was shown; empty means cancel — do NOT open zenity.
    try:
        paths = _ask_files_dialog_tk(
            initialdir, filetypes=filetypes, title=title, multiple=multiple
        )
        if paths is not None:
            return paths
    except Exception:
        pass

    if sys.platform.startswith("linux"):
        try:
            paths = _ask_files_dialog_zenity(
                initialdir, filetypes=filetypes, title=title, multiple=multiple
            )
            if paths:
                return paths
        except Exception:
            pass

    return []


def _ask_file_dialog_macos(
    initialdir: str,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select a file",
) -> Optional[str]:
    paths = _ask_files_dialog_macos(
        initialdir, filetypes=filetypes, title=title, multiple=False
    )
    return paths[0] if paths else None


def _ask_files_dialog_macos(
    initialdir: str,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select file(s)",
    multiple: bool = True,
) -> list:
    if not shutil.which("osascript"):
        return []

    # AppleScript ``of type`` prefers extension tokens without the leading dot.
    type_tokens: list[str] = []
    if filetypes:
        seen: set[str] = set()
        for ext in filetypes:
            tok = str(ext).lstrip(".").lower()
            if tok and tok not in seen:
                seen.add(tok)
                type_tokens.append(tok)
    type_clause = ""
    if type_tokens:
        quoted = ", ".join(f'"{_applescript_quote(t)}"' for t in type_tokens)
        type_clause = f" of type {{{quoted}}}"
    multi_clause = " with multiple selections allowed" if multiple else ""

    script_parts = [
        f'set initialPath to "{_applescript_quote(initialdir)}"',
        "try",
        "    set defaultLocation to POSIX file initialPath",
        f'    set theFiles to choose file with prompt "{_applescript_quote(title)}"'
        f" default location defaultLocation{type_clause}{multi_clause}",
        "    set out to \"\"",
        "    if class of theFiles is list then",
        "        repeat with f in theFiles",
        "            set out to out & (POSIX path of f) & linefeed",
        "        end repeat",
        "    else",
        "        set out to POSIX path of theFiles",
        "    end if",
        "    return out",
        "on error errMsg number errNum",
        '    return ""',
        "end try",
    ]
    script = "\n".join(script_parts)
    try:
        res = subprocess.run(
            ["osascript"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if res.returncode != 0:
            return []
        out = []
        for line in (res.stdout or "").splitlines():
            selection = line.strip()
            if not selection:
                continue
            try:
                selection = os.path.normpath(os.path.abspath(selection))
                if os.path.isfile(selection):
                    selection = os.path.realpath(selection)
            except (OSError, ValueError):
                pass
            if selection and os.path.isfile(selection):
                out.append(selection)
        return out
    except Exception:
        return []


def _ask_file_dialog_tk(
    initialdir: str,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select a file",
) -> Optional[str]:
    paths = _ask_files_dialog_tk(
        initialdir, filetypes=filetypes, title=title, multiple=False
    )
    return paths[0] if paths else None


def _ask_files_dialog_tk(
    initialdir: str,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select file(s)",
    multiple: bool = True,
):
    """Tk file picker (Windows/Linux).

    Returns a ``list`` of paths when the dialog was shown (empty on cancel).
    Returns ``None`` when the backend is unavailable so the caller may fall
    back (e.g. Linux zenity) without treating cancel as “try another dialog”.
    """
    if sys.platform.startswith("darwin"):
        return None
    root = None
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        try:
            root.attributes('-topmost', True)
        except Exception:
            pass
        tk_filetypes = [("All files", "*.*")]
        if filetypes:
            patterns = " ".join(f"*{ext}" if ext.startswith('.') else f"*.{ext}" for ext in filetypes)
            # Deduplicate case variants for the label (e.g. .cif/.CIF → CIF files)
            label = "Files"
            exts_lower = {str(e).lstrip(".").lower() for e in filetypes if e}
            if exts_lower == {"cif"}:
                label = "CIF files"
            elif "bps" in exts_lower or "bpsg" in exts_lower or "bpsh" in exts_lower:
                label = "Style files"
            tk_filetypes.insert(0, (label, patterns))
        if multiple:
            selection = filedialog.askopenfilenames(
                title=title,
                initialdir=initialdir,
                filetypes=tk_filetypes,
            )
            return [os.path.abspath(p) for p in (selection or ()) if p and os.path.isfile(p)]
        file_path = filedialog.askopenfilename(
            title=title,
            initialdir=initialdir,
            filetypes=tk_filetypes,
        )
        if file_path and os.path.isfile(file_path):
            return [os.path.abspath(file_path)]
        return []
    except Exception:
        return None
    finally:
        if root is not None:
            try:
                root.quit()
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass


def _ask_file_dialog_zenity(
    initialdir: str,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select a file",
) -> Optional[str]:
    paths = _ask_files_dialog_zenity(
        initialdir, filetypes=filetypes, title=title, multiple=False
    )
    return paths[0] if paths else None


def _ask_files_dialog_zenity(
    initialdir: str,
    filetypes: Optional[Tuple[str, ...]] = None,
    *,
    title: str = "Select file(s)",
    multiple: bool = True,
) -> list:
    cmd = None
    if shutil.which("zenity"):
        filename_arg = f"--filename={os.path.join(initialdir.rstrip(os.sep), '')}"
        zenity_cmd = [
            "zenity",
            "--file-selection",
            f"--title={title}",
            filename_arg,
        ]
        if multiple:
            zenity_cmd.extend(["--multiple", "--separator=\n"])
        if filetypes:
            patterns = " ".join(f"*{ext}" if ext.startswith('.') else f"*.{ext}" for ext in filetypes)
            zenity_cmd.append(f"--file-filter=Files | {patterns}")
        cmd = zenity_cmd
    elif shutil.which("kdialog"):
        pattern = " ".join(f"*{ext}" if ext.startswith('.') else f"*.{ext}" for ext in (filetypes or ()))
        if not pattern:
            pattern = "*"
        cmd = [
            "kdialog",
            "--getopenfilename",
            initialdir,
            pattern,
            "--title",
            title,
        ]
        if multiple:
            # Newline-separated paths so names with spaces survive parsing.
            cmd.extend(["--multiple", "--separate-output"])
    if cmd is None:
        return []
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=300,
        )
        if res.returncode != 0:
            return []
        raw = (res.stdout or "").strip()
        if not raw:
            return []
        # zenity (--separator=\n) and kdialog (--separate-output) use newlines.
        parts = [p.strip() for p in raw.replace("\r", "\n").split("\n") if p.strip()]
        if len(parts) == 1 and not os.path.isfile(parts[0]):
            # Legacy kdialog without --separate-output: space-separated (breaks
            # paths with spaces; only used when the whole line is not a file).
            parts = [p for p in raw.split() if p]
        out = []
        for p in parts:
            if os.path.isfile(p):
                out.append(os.path.abspath(p))
        return out
    except Exception:
        return []


def ensure_subdirectory(subdir_name: str, base_path: Optional[str] = None) -> str:
    """Ensure subdirectory exists and return its path.
    
    Creates a subdirectory if it doesn't exist. Used to organize output files
    into Figures/, Styles/, and Projects/ folders.
    
    Args:
        subdir_name: Name of subdirectory ('Figures', 'Styles', or 'Projects')
        base_path: Base directory (defaults to current working directory)
    
    Returns:
        Full path to the subdirectory (or base_path if creation fails)
        
    Example:
        >>> ensure_subdirectory('Figures', '/home/user/data')
        '/home/user/data/Figures'
    """
    # Use current directory if no base path specified
    if base_path is None:
        base_path = os.getcwd()
    
    # Build full path to subdirectory
    subdir_path = os.path.join(base_path, subdir_name)
    
    # Create directory if it doesn't exist
    # exist_ok=True prevents error if directory already exists
    try:
        os.makedirs(subdir_path, exist_ok=True)
    except Exception as e:
        # If creation fails (permissions, etc.), warn and fall back to base directory
        print(f"Warning: Could not create {subdir_name} directory: {e}")
        return base_path
    
    return subdir_path


def get_organized_path(filename: str, file_type: str, base_path: Optional[str] = None) -> str:
    """Get the appropriate path for a file based on its type.
    
    This function helps organize output files into subdirectories:
    - Figures go into Figures/
    - Styles go into Styles/
    - Projects go into Projects/
    
    If the filename already contains a directory path, it's used as-is.
    
    Args:
        filename: The filename (can include path like 'output/fig.svg')
        file_type: 'figure', 'style', or 'project'
        base_path: Base directory (defaults to current working directory)
    
    Returns:
        Full path with appropriate subdirectory
        
    Example:
        >>> get_organized_path('plot.svg', 'figure')
        './Figures/plot.svg'
        >>> get_organized_path('/tmp/plot.svg', 'figure')
        '/tmp/plot.svg'  # Already has path, use as-is
    """
    # Expand ``~/…`` first so home-relative exports work on Windows/macOS/Linux.
    try:
        filename = os.path.expanduser(str(filename))
    except Exception:
        filename = str(filename)
    # If filename already has a directory component, respect user's choice
    # os.path.dirname returns '' for bare filenames, non-empty for paths
    if os.path.dirname(filename):
        return filename
    
    # Map file type to subdirectory name
    subdir_map = {
        'figure': 'Figures',
        'style': 'Styles',
        'project': 'Projects'
    }
    
    subdir_name = subdir_map.get(file_type)
    if not subdir_name:
        # Unknown file type, just use current directory without subdirectory
        if base_path is None:
            base_path = os.getcwd()
        return os.path.join(base_path, filename)
    
    # Ensure subdirectory exists and get its path
    subdir_path = ensure_subdirectory(subdir_name, base_path)
    return os.path.join(subdir_path, filename)


STYLE_FILE_EXTENSIONS = ('.bps', '.bpsg', '.bpcfg')


def list_files_in_subdirectory(extensions: tuple, file_type: str, base_path: Optional[str] = None) -> list:
    """List files with given extensions in the appropriate subdirectory.
    
    Used by interactive menus to show available files for import/load operations.
    For example, listing all .json style files in Styles/ directory.
    
    Args:
        extensions: Tuple of file extensions (e.g., ('.svg', '.png', '.pdf'))
                   Case-insensitive matching
        file_type: 'figure', 'style', or 'project' - determines which subdirectory
        base_path: Base directory (defaults to current working directory)
    
    Returns:
        List of (filename, full_path) tuples sorted alphabetically by filename
        Empty list if directory doesn't exist or can't be read
        
    Example:
        >>> list_files_in_subdirectory(('.json',), 'style')
        [('mystyle.json', './Styles/mystyle.json'), ...]
    """
    if base_path is None:
        base_path = os.getcwd()
    
    # Map file type to subdirectory name (same as get_organized_path)
    subdir_map = {
        'figure': 'Figures',
        'style': 'Styles',
        'project': 'Projects'
    }
    
    subdir_name = subdir_map.get(file_type)
    if not subdir_name:
        # Unknown type, list from current directory
        folder = base_path
    else:
        # Build path to subdirectory
        folder = os.path.join(base_path, subdir_name)
        # Create directory if it doesn't exist (for first-time users)
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            # If creation fails, fall back to base directory
            folder = base_path
    
    # Scan directory for matching files
    files = []
    try:
        all_files = os.listdir(folder)
        for f in all_files:
            # Case-insensitive extension matching
            if f.lower().endswith(extensions):
                files.append((f, os.path.join(folder, f)))
    except Exception:
        # If directory can't be read, return empty list
        # Don't crash - user can still work without listing files
        pass
    
    # Sort by filename using natural order (file2 before file10)
    return sorted(files, key=lambda x: natural_sort_key(x[0]))


def print_recent_axis_names(colorize: Optional[Callable[[str], str]] = None,
                            mode: Optional[str] = None) -> None:
    """Print numbered list of recently typed axis names.

    With ``mode`` (e.g. ``'xy'``, ``'ec'``, ``'cpc'``, ``'operando'``,
    ``'histo'``) only that mode's names are shown; without it the legacy
    shared list is shown (backward compatible).

    Entries that still contain ``{sub()}`` / ``{super()}`` / other shortcuts
    are shown as ``shortcut → converted`` so the list reflects mathtext.
    """
    from .config import get_recent_axis_names

    names = get_recent_axis_names(mode)
    if not names:
        msg = "No recent axis names stored yet."
        print(colorize(msg) if colorize else msg)
        return
    if mode is None:
        header = "Recent axis names (newest first; shared across all modes):"
    else:
        header = "Recent axis names (newest first; this mode only — type its number at a label prompt):"
    print(colorize(header) if colorize else header)
    for i, name in enumerate(names, 1):
        converted = finalize_axis_label_text(name)
        if converted != name and _label_has_shortcuts(name):
            line = f"  {i}: {name}  ->  {converted}"
        else:
            line = f"  {i}: {converted}"
        print(colorize(line) if colorize else line)


def remember_axis_name(name: str, mode: Optional[str] = None) -> None:
    """Store a user-entered axis label in the recent-names list (per-mode when *mode* is given).

    Shortcuts such as ``{sub()}`` / ``{super()}`` are converted before storage
    so saved names always reflect the mathtext that appears on the plot.
    """
    from .config import record_recent_axis_name

    record_recent_axis_name(finalize_axis_label_text(name), mode)


def resolve_recent_axis_name(text: str, mode: Optional[str] = None) -> str:
    """Resolve a label prompt entry against the recent-names list.

    - A pure number (e.g. ``2``) picks recent name #2 for *mode* (1-based,
      newest first). Out-of-range numbers are kept as literal text.
    - A double-quoted entry (e.g. ``"3"``) strips the quotes and is always
      treated as literal text, so numeric axis labels stay reachable.
    - Anything else is returned unchanged (callers still run
      :func:`finalize_axis_label_text` / :func:`convert_label_shortcuts`).

    Picked recent names are finalized so old config entries that still store
    raw ``{sub()}`` / ``{super()}`` convert on reuse.
    """
    from .config import get_recent_axis_names

    s = (text or '').strip()
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.isdigit():
        names = get_recent_axis_names(mode)
        idx = int(s) - 1
        if 0 <= idx < len(names):
            picked = finalize_axis_label_text(names[idx])
            print(f"Using recent name {idx + 1}: {picked}")
            return picked
    return text


def _label_has_shortcuts(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(
            r"\{(?:sub|super|italic)\([^)]*\)\}|"
            r"\{(?:"
            r"alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega|"
            r"Alpha|Beta|Gamma|Delta|Epsilon|Zeta|Eta|Theta|Iota|Kappa|Lambda|Mu|Nu|Xi|Pi|Rho|Sigma|Tau|Upsilon|Phi|Chi|Psi|Omega|"
            r"AA|angstrom|deg|degree|bullet|pm|times|cdot|approx|infty|neq|le|ge|rightarrow|leftarrow"
            r")\}",
            text,
        )
    )


def print_label_math_help(colorize: Optional[Callable[[str], str]] = None) -> None:
    """Print math/science typing help for rename menus (subkey ``m``).

    Covers ``{sub()}`` / ``{super()}`` / ``{italic()}``, Greek, and common
    symbols. Uses ``safe_console_print`` for Windows console safety.
    """
    from .plot_modes.common.terminal import safe_console_print

    safe_console_print("Math / science typing help (shortcuts → mathtext on the plot):")
    bodies = (
        "Sub/super:  Li{sub(2)}O → Li₂O   |   g{super(-1)} → g⁻¹   |   m{super(2)} → m²",
        "Also LaTeX: H$_2$O  |  m$^2$  |  Å$^{-1}$",
        "Italic:     {italic(d)}Q/{italic(d)}V  or  $\\mathit{d}$Q/$\\mathit{d}$V",
        "Greek:      {alpha} {beta} {gamma} {delta} {epsilon} {theta} {lambda} {mu} {pi} {sigma} {omega}",
        "            Capitals: {Gamma} {Delta} {Theta} {Lambda} {Sigma} {Omega} {Phi} {Psi}",
        "Science:    {AA}/{angstrom} → Å  |  {deg} → °  |  {bullet}  |  {pm} ±  |  {times} ×  |  {cdot} ·",
        "            {approx} ≈  |  {infty} ∞  |  {neq} ≠  |  {le} ≤  |  {ge} ≥",
        "Examples:   Capacity (mAh g{super(-1)})   |   {alpha}-Li{sub(3)}PS{sub(4)}   |   2{theta} ({deg})",
    )
    prefix = "  "
    for body in bodies:
        line = colorize(body) if colorize else body
        safe_console_print(prefix + line)


def print_label_latex_tips(colorize: Optional[Callable[[str], str]] = None) -> None:
    """Alias for :func:`print_label_math_help` (kept for older call sites)."""
    print_label_math_help(colorize=colorize)


def convert_label_shortcuts(text: str) -> str:
    """Convert shortcut syntax to LaTeX/mathtext for labels.

    Converts ``{super(...)}``, ``{sub(...)}``, ``{italic(...)}``, Greek letter
    tokens (``{alpha}``, ``{beta}``, …), and common science symbols
    (``{AA}``, ``{deg}``, ``{pm}``, …). Already-converted mathtext is left
    unchanged (safe to run on style/session restore).

    Examples:
        >>> convert_label_shortcuts("g{super(-1)}")
        'g$^{\\\\mathrm{-1}}$'
        >>> convert_label_shortcuts("Li{sub(2)}FeSeO")
        'Li$_{\\\\mathrm{2}}$FeSeO'
        >>> convert_label_shortcuts("{italic(Fe)}")
        '$\\\\mathit{Fe}$'
        >>> convert_label_shortcuts("{alpha}-phase")
        '$\\\\alpha$-phase'
    """
    if not text:
        return text

    # Function-like shortcuts first (may contain greek names as literal args).
    text = re.sub(r'\{italic\(([^)]+)\)\}', r'$\\mathit{\1}$', text)
    text = re.sub(r'\{super\(([^)]+)\)\}', r'$^{\\mathrm{\1}}$', text)
    text = re.sub(r'\{sub\(([^)]+)\)\}', r'$_{\\mathrm{\1}}$', text)

    # Bare science / greek tokens: {alpha}, {AA}, {deg}, …
    _TOKEN_TO_MATH = {
        "alpha": r"$\alpha$",
        "beta": r"$\beta$",
        "gamma": r"$\gamma$",
        "delta": r"$\delta$",
        "epsilon": r"$\epsilon$",
        "zeta": r"$\zeta$",
        "eta": r"$\eta$",
        "theta": r"$\theta$",
        "iota": r"$\iota$",
        "kappa": r"$\kappa$",
        "lambda": r"$\lambda$",
        "mu": r"$\mu$",
        "nu": r"$\nu$",
        "xi": r"$\xi$",
        "pi": r"$\pi$",
        "rho": r"$\rho$",
        "sigma": r"$\sigma$",
        "tau": r"$\tau$",
        "upsilon": r"$\upsilon$",
        "phi": r"$\phi$",
        "chi": r"$\chi$",
        "psi": r"$\psi$",
        "omega": r"$\omega$",
        "Alpha": r"$\mathrm{A}$",
        "Beta": r"$\mathrm{B}$",
        "Gamma": r"$\Gamma$",
        "Delta": r"$\Delta$",
        "Epsilon": r"$\mathrm{E}$",
        "Zeta": r"$\mathrm{Z}$",
        "Eta": r"$\mathrm{H}$",
        "Theta": r"$\Theta$",
        "Iota": r"$\mathrm{I}$",
        "Kappa": r"$\mathrm{K}$",
        "Lambda": r"$\Lambda$",
        "Mu": r"$\mathrm{M}$",
        "Nu": r"$\mathrm{N}$",
        "Xi": r"$\Xi$",
        "Pi": r"$\Pi$",
        "Rho": r"$\mathrm{P}$",
        "Sigma": r"$\Sigma$",
        "Tau": r"$\mathrm{T}$",
        "Upsilon": r"$\Upsilon$",
        "Phi": r"$\Phi$",
        "Chi": r"$\mathrm{X}$",
        "Psi": r"$\Psi$",
        "Omega": r"$\Omega$",
        "AA": r"$\mathrm{\AA}$",
        "angstrom": r"$\mathrm{\AA}$",
        "deg": r"$^{\circ}$",
        "degree": r"$^{\circ}$",
        "bullet": r"$\bullet$",
        "pm": r"$\pm$",
        "times": r"$\times$",
        "cdot": r"$\cdot$",
        "approx": r"$\approx$",
        "infty": r"$\infty$",
        "neq": r"$\neq$",
        "le": r"$\leq$",
        "ge": r"$\geq$",
        "rightarrow": r"$\rightarrow$",
        "leftarrow": r"$\leftarrow$",
    }

    def _replace_token(match: re.Match) -> str:
        key = match.group(1)
        return _TOKEN_TO_MATH.get(key, match.group(0))

    text = re.sub(
        r"\{("
        + "|".join(re.escape(k) for k in sorted(_TOKEN_TO_MATH.keys(), key=len, reverse=True))
        + r")\}",
        _replace_token,
        text,
    )
    return text


def finalize_axis_label_text(text: str) -> str:
    """Convert label shortcuts then normalize for matplotlib (p/i/s/b-safe).

    Idempotent on already-converted mathtext / plain strings. Use whenever a
    label is stored, listed, or applied from style/session/undo so old
    payloads that still contain ``{sub()}`` / ``{super()}`` render correctly.
    """
    if text is None:
        return text
    s = str(text)
    if not s:
        return s
    return normalize_label_text(convert_label_shortcuts(s))


def normalize_label_text(text: str) -> str:
    """Normalize axis label text for proper matplotlib rendering.
    
    Converts various representations of superscripts and special characters
    into matplotlib-compatible LaTeX format. Primarily handles Angstrom units
    with inverse exponents (Å⁻¹ → Å$^{-1}$).
    
    Args:
        text: Raw label text that may contain Unicode or LaTeX notation
        
    Returns:
        Normalized text with proper matplotlib math mode formatting
        
    Example:
        >>> normalize_label_text("Q (Å⁻¹)")
        "Q (Å$^{-1}$)"
    """
    if not text:
        return text
    
    # Convert Unicode superscript minus to LaTeX math mode
    text = text.replace("Å⁻¹", "Å$^{-1}$")
    # Handle various spacing variations
    text = text.replace("Å ^-1", "Å$^{-1}$")
    text = text.replace("Å^-1", "Å$^{-1}$")
    # Handle LaTeX \AA command variations
    text = text.replace(r"\AA⁻¹", r"\AA$^{-1}$")
    
    return text


def _confirm_overwrite(path: str, auto_suffix: bool = True):
    """Ask user before overwriting an existing file.
    
    Provides three behaviors depending on context:
    1. File doesn't exist → return path as-is
    2. Interactive terminal → ask user for confirmation or alternative filename
    3. Non-interactive (pipe/script) → auto-append suffix to avoid overwrite
    
    This prevents accidental data loss while allowing automation in scripts.
    
    Args:
        path: Full path to the file that might be overwritten
        auto_suffix: If True, automatically add _1, _2, etc. in non-interactive mode
                    If False, return None to cancel in non-interactive mode
    
    Returns:
        - Path to use (original or modified)
        - None to cancel the operation
        
    Example:
        >>> _confirm_overwrite('plot.svg')
        # If file exists and user is interactive: prompts "Overwrite? [y/N]:"
        # If file exists and running in script: returns 'plot_1.svg'
    """
    try:
        # If file doesn't exist, no confirmation needed
        if not os.path.exists(path):
            return path
        
        # Check if running in non-interactive context (pipe, script, background)
        if not sys.stdin.isatty():
            # Non-interactive: can't ask user, so auto-suffix or cancel
            if not auto_suffix:
                return None
            
            # Generate unique filename by appending _1, _2, etc.
            base, ext = os.path.splitext(path)
            k = 1
            new_path = f"{base}_{k}{ext}"
            # Keep incrementing until we find an unused name (max 1000 to prevent infinite loop)
            while os.path.exists(new_path) and k < 1000:
                k += 1
                new_path = f"{base}_{k}{ext}"
            return new_path
        
        # Interactive mode: ask user what to do
        ans = input(f"File '{path}' exists. Overwrite? [y/N]: ").strip().lower()
        if ans == 'y':
            return path
        
        # User said no, ask for alternative filename
        alt = input("Enter new filename (blank=cancel): ").strip()
        if not alt:
            # User wants to cancel
            return None
        
        # If user didn't provide extension, copy from original
        if not os.path.splitext(alt)[1] and os.path.splitext(path)[1]:
            alt += os.path.splitext(path)[1]
        
        # Check if alternative also exists
        if os.path.exists(alt):
            print("Chosen alternative also exists; action canceled.")
            return None
        
        return alt
        
    except Exception:
        # If anything goes wrong (KeyboardInterrupt, etc.), just use original path
        # Better to risk overwrite than crash
        return path


def choose_save_path(file_paths: list, purpose: str = "saving") -> Optional[str]:
    """Prompt user to choose a base directory for saving artifacts.
    
    Always shows the current working directory and every unique directory that
    contains an input file. The user can pick from the numbered list or type a
    custom path manually. Returning ``None`` indicates the caller should cancel
    the pending save/export operation.
    
    Args:
        file_paths: List of file paths associated with the current figure/session.
                    Only existing files contribute directory options.
        purpose: Short description used in prompts (e.g., "figure export").
    
    Returns:
        Absolute path chosen by the user, or ``None`` if the selection
        was canceled. Defaults to the current working directory if the
        user simply presses Enter.
    """
    try:
        cwd = os.getcwd()
        file_paths = file_paths or []
        
        # Build ordered mapping of directories → input files originating there
        dir_map = {}
        for fpath in file_paths:
            try:
                if not fpath:
                    continue
                abs_path = os.path.abspath(fpath)
                if not os.path.exists(abs_path):
                    continue
                fdir = os.path.dirname(abs_path)
                if not fdir:
                    continue
                dir_map.setdefault(fdir, [])
                dir_map[fdir].append(os.path.basename(abs_path) or abs_path)
            except Exception:
                continue
        
        cwd_files = dir_map.pop(cwd, [])
        options = [{
            'path': cwd,
            'label': "Current directory (terminal)",
            'files': cwd_files,
        }]
        for dir_path, files in sorted(dir_map.items()):
            options.append({
                'path': dir_path,
                'label': "Input file directory",
                'files': files,
            })
        
        print(f"\nSave location options for {purpose}:")
        for idx, opt in enumerate(options, start=1):
            extra = ""
            if opt['files']:
                preview = ", ".join(opt['files'][:2])
                if len(opt['files']) > 2:
                    preview += ", ..."
                extra = f" (input files: {preview})"
            label = f"{opt['label']}: {opt['path']}"
            print(f"  \033[96m{idx}\033[0m. {label}{extra}")
        print(f"  \033[96mc\033[0m. Custom path")
        print(f"  \033[96mq\033[0m. Cancel (return to menu)")
        
        max_choice = len(options)
        save_prompt = _colorize_option_keys(f"1-{max_choice}: select path, Enter: default(1), c: custom, q: cancel")
        while True:
            try:
                choice = input(f"Choose path for {purpose} ({save_prompt}): ").strip()
            except KeyboardInterrupt:
                print("\nCanceled path selection.")
                return None
            
            if not choice:
                try:
                    cwd = os.path.normpath(os.path.abspath(cwd))
                    if os.path.isdir(cwd):
                        cwd = os.path.realpath(cwd)
                except (OSError, ValueError):
                    pass
                return cwd
            
            low = choice.lower()
            if low == 'q':
                print("Canceled path selection.")
                return None
            if low == 'c':
                # Try to open folder picker dialog first
                dialog_path = None
                try:
                    dialog_path = _ask_directory_dialog(initialdir=cwd)
                except Exception as e:
                    # Dialog failed - fall back to manual input
                    dialog_path = None
                
                if dialog_path:
                    # User selected a folder via dialog - normalize for consistent listing
                    try:
                        dialog_path = os.path.normpath(os.path.abspath(dialog_path.strip()))
                        if os.path.isdir(dialog_path):
                            dialog_path = os.path.realpath(dialog_path)
                        os.makedirs(dialog_path, exist_ok=True)
                        return dialog_path
                    except Exception as e:
                        print(f"Could not use directory: {e}")
                        # Fall through to manual input
                
                # Fallback to manual input if dialog unavailable or canceled
                print("(Dialog unavailable or canceled, enter path manually)")
                try:
                    manual = input("Enter directory path (q=cancel): ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nCanceled path selection.")
                    return None
                if not manual or manual.lower() == 'q':
                    continue
                manual_path = os.path.normpath(os.path.abspath(os.path.expanduser(manual.strip())))
                try:
                    if os.path.isdir(manual_path):
                        manual_path = os.path.realpath(manual_path)
                    os.makedirs(manual_path, exist_ok=True)
                except Exception as e:
                    print(f"Could not use directory: {e}")
                    continue
                return manual_path
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= max_choice:
                    path = options[num - 1]['path']
                    try:
                        path = os.path.normpath(os.path.abspath(path))
                        if os.path.isdir(path):
                            path = os.path.realpath(path)
                    except (OSError, ValueError):
                        pass
                    return path
                print(f"Invalid number. Enter between 1 and {max_choice}.")
                continue
            # Treat any other input as a manual path entry
            manual_path = os.path.normpath(os.path.abspath(os.path.expanduser(choice.strip())))
            try:
                if os.path.isdir(manual_path):
                    manual_path = os.path.realpath(manual_path)
                os.makedirs(manual_path, exist_ok=True)
            except Exception as e:
                print(f"Could not use directory: {e}")
                continue
            return manual_path
    except Exception as e:
        print(f"Error in path selection: {e}. Using current directory.")
        return os.getcwd()


def ensure_exact_case_filename(target_path: str) -> str:
    """Ensure a file is saved with the exact case specified, even on case-insensitive filesystems.
    
    This function handles case-insensitive filesystems (macOS, Windows) by ensuring that
    if a file exists with different case, it is removed first so the new file can be created
    with the exact case specified by the user.
    
    On case-sensitive filesystems (Linux, Unix), this function is safe but has no effect
    since files with different case are treated as different files.
    
    Args:
        target_path: The desired file path with exact case
    
    Returns:
        The same path (for compatibility)
    """
    folder = os.path.dirname(target_path)
    desired_basename = os.path.basename(target_path)
    
    if not folder or not desired_basename:
        return target_path
    
    try:
        # Check if file already exists with exact case
        if os.path.exists(target_path):
            # Check if the actual filename on disk matches the desired case
            existing_files = os.listdir(folder)
            for existing_file in existing_files:
                # If same name (case-insensitive) but different case, we need to fix it
                if existing_file.lower() == desired_basename.lower() and existing_file != desired_basename:
                    existing_path = os.path.join(folder, existing_file)
                    # Delete the existing file with wrong case
                    # This is safe on case-insensitive filesystems and has no effect on case-sensitive ones
                    try:
                        if os.path.exists(existing_path):
                            os.remove(existing_path)
                    except Exception:
                        # Ignore errors (e.g., permission issues, file in use)
                        pass
                    break
    except Exception:
        # If we can't check/list the directory, just return the path as-is
        # This is safe and ensures we don't break on permission errors
        pass
    
    return target_path


def _normalize_extension(ext: str) -> str:
    if not ext:
        return ext
    ext = ext.strip().lower()
    if not ext.startswith('.'):
        ext = '.' + ext
    return ext


def _has_valid_extension(filename: str, extensions: Tuple[str, ...]) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in extensions)


def _colorize_option_keys(text: str) -> str:
    """Highlight option keys (key: desc format) in prompts for consistency with interactive menus."""
    if not text or not text.strip():
        return text
    parts = []
    for segment in text.split(','):
        segment = segment.strip()
        if ':' in segment:
            key, rest = segment.split(':', 1)
            key = key.strip()
            rest = rest.strip()
            parts.append(f"\033[96m{key}\033[0m: {rest}")
        else:
            parts.append(segment)
    return ', '.join(parts)


def choose_style_file(file_paths: List[str], purpose: str = "style import", extensions: Optional[Tuple[str, ...]] = None) -> Optional[str]:
    """Select a style file (.bps/.bpsg/.bpcfg) from known directories or via dialog."""
    extensions = tuple(_normalize_extension(ext) for ext in (extensions or STYLE_FILE_EXTENSIONS))
    if not extensions:
        extensions = STYLE_FILE_EXTENSIONS
    
    search_dirs: List[str] = []
    seen_dirs = set()
    
    def _add_dir(path: str):
        if not path:
            return
        abs_path = os.path.abspath(path)
        if abs_path in seen_dirs:
            return
        if os.path.isdir(abs_path):
            seen_dirs.add(abs_path)
            search_dirs.append(abs_path)
    
    _add_dir(os.getcwd())
    for fpath in file_paths or []:
        try:
            if not fpath:
                continue
            abs_path = os.path.abspath(fpath)
            if not os.path.exists(abs_path):
                continue
            directory = os.path.dirname(abs_path)
            _add_dir(directory)
        except Exception:
            continue
    if not search_dirs:
        search_dirs.append(os.getcwd())
    
    style_candidates = []
    seen_files = set()
    
    def _collect_from_directory(directory: str):
        if not os.path.isdir(directory):
            return
        try:
            entries = sorted(os.listdir(directory), key=natural_sort_key)
        except Exception:
            return
        for entry in entries:
            full_path = os.path.join(directory, entry)
            if not os.path.isfile(full_path):
                continue
            if not _has_valid_extension(entry, extensions):
                continue
            norm = os.path.abspath(full_path)
            if norm in seen_files:
                continue
            seen_files.add(norm)
            style_candidates.append({
                'name': entry,
                'path': norm,
                'location': directory,
            })
    
    for base_dir in search_dirs:
        _collect_from_directory(base_dir)
        styles_dir = os.path.join(base_dir, 'Styles')
        if styles_dir != base_dir:
            _collect_from_directory(styles_dir)
    
    print(f"\nSearching for style files for {purpose} in:")
    for dir_path in search_dirs:
        print(f"  - {dir_path}")
    def _format_file_timestamp(filepath: str) -> str:
        """Format file modification time for display."""
        try:
            mtime = os.path.getmtime(filepath)
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
        except Exception:
            return ""
    
    if style_candidates:
        print("\nAvailable style files:")
        for idx, cand in enumerate(style_candidates, start=1):
            timestamp = _format_file_timestamp(cand['path'])
            if timestamp:
                print(f"  \033[96m{idx}\033[0m. {cand['name']}  ({timestamp})  (in {cand['location']})")
            else:
                print(f"  \033[96m{idx}\033[0m. {cand['name']}  (in {cand['location']})")
    else:
        print("\nNo style files found in scanned directories.")
    
    search_locations = []
    added_locations = set()
    for base_dir in search_dirs:
        if os.path.isdir(base_dir) and base_dir not in added_locations:
            search_locations.append(base_dir)
            added_locations.add(base_dir)
        styles_dir = os.path.join(base_dir, 'Styles')
        if os.path.isdir(styles_dir) and styles_dir not in added_locations:
            search_locations.append(styles_dir)
            added_locations.add(styles_dir)
    
    def _resolve_manual_path(user_input: str) -> Optional[str]:
        raw = os.path.expanduser(user_input.strip())
        candidate_paths = []
        if os.path.isabs(raw):
            candidate_paths.append(os.path.abspath(raw))
        else:
            for loc in search_locations or [os.getcwd()]:
                candidate_paths.append(os.path.abspath(os.path.join(loc, raw)))
        resolved: List[str] = []
        seen = set()
        for cand in candidate_paths:
            if cand not in seen:
                seen.add(cand)
                resolved.append(cand)
            needs_ext = not _has_valid_extension(cand, extensions)
            if needs_ext:
                for ext in extensions:
                    if cand.lower().endswith(ext):
                        continue
                    alt = cand + ext
                    if alt not in seen:
                        seen.add(alt)
                        resolved.append(alt)
        for path in resolved:
            if os.path.isfile(path) and _has_valid_extension(path, extensions):
                return path
        return None
    
    n_candidates = len(style_candidates)
    if n_candidates:
        prompt_text = f"1-{n_candidates}: select file, path: enter path, c: custom dialog, q: cancel"
    else:
        prompt_text = "c: custom path, q: cancel"
    prompt = _colorize_option_keys(prompt_text)

    while True:
        try:
            choice = input(f"Select style file ({prompt}): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nStyle import canceled.")
            return None
        
        if not choice:
            print("Style import canceled.")
            return None
        
        low = choice.lower()
        if low == 'q':
            print("Style import canceled.")
            return None
        if low == 'c':
            dialog_path = _ask_file_dialog(initialdir=search_dirs[0], filetypes=extensions)
            if not dialog_path:
                print("No file selected.")
                continue
            dialog_path = os.path.abspath(dialog_path)
            if not os.path.isfile(dialog_path):
                print("Selected file does not exist.")
                continue
            if not _has_valid_extension(dialog_path, extensions):
                print("Selected file is not a recognized style file.")
                continue
            return dialog_path
        if choice.isdigit() and style_candidates:
            idx = int(choice)
            if 1 <= idx <= len(style_candidates):
                return style_candidates[idx - 1]['path']
            print("Invalid number. Try again.")
            continue
        path = _resolve_manual_path(choice)
        if path:
            return path
        print("File not found. Enter another value or use 'c' for custom dialog.")


def xy_cif_stack_y_offset(fig, index: int) -> float:
    """Vertical offset in data Y for CIF stack row ``index`` (XY / 1D mode)."""
    offs = getattr(fig, "_bp_cif_stack_y_offsets", None)
    if not offs or index < 0 or index >= len(offs):
        return 0.0
    try:
        return float(offs[index])
    except (TypeError, ValueError):
        return 0.0


# Typographic gap (screen points) from tick top to phase filename; same for every row / file.
XY_CIF_TITLE_ABOVE_TICK_PT = 2.0


def xy_cif_add_phase_title(
    ax,
    x_left: float,
    y_line: float,
    tick_h: float,
    label_text: str,
    fontsize,
    color,
    new_art: list,
) -> None:
    """Draw phase filename a fixed number of points above tick tops (uniform visual gap).

    Anchor in data space at the tick tops ``(x_left, y_line + tick_h)``, then shift in
    **display points** via ``offset_copy`` (matplotlib's stable pattern for data+pt mix).
    """
    fig = ax.figure
    trans = offset_copy(
        ax.transData,
        fig=fig,
        x=0.0,
        y=XY_CIF_TITLE_ABOVE_TICK_PT,
        units="points",
    )
    txt = ax.text(
        float(x_left),
        float(y_line + tick_h),
        label_text,
        transform=trans,
        ha="left",
        va="bottom",
        fontsize=fontsize,
        color=color,
        clip_on=False,
        zorder=4,
    )
    new_art.append(txt)


def xy_cif_tick_stack_layout(y_line: float, yr: float):
    """Return (tick_h, hkl_text_y) for CIF tick geometry in data coordinates.

    Phase titles use :func:`xy_cif_add_phase_title` (points above ``y_line + tick_h``).
    """
    yr = max(float(yr), 1e-12)
    tick_h = 0.02 * yr
    hkl_y = y_line + tick_h + 0.005 * yr
    return tick_h, hkl_y


def xy_cif_row_spacing_yr(
    yr_ref: float,
    *,
    show_titles: bool,
    show_hkl: bool,
    stacked_or_multi_y: bool,
) -> float:
    """Vertical gap between consecutive CIF row baselines (``y_line``), in data Y units.

    Must be large enough that phase titles (above tick stems) and optional rotated
    hkl labels do not collide with the next row.
    """
    yr = max(float(yr_ref), 1e-12)
    if stacked_or_multi_y:
        spacing = 0.05 * yr
    else:
        spacing = 0.04 * yr
    if show_titles and show_hkl:
        spacing = max(spacing, 0.088 * yr)
    elif show_titles:
        spacing = max(spacing, 0.076 * yr)
    elif show_hkl:
        spacing = max(spacing, 0.056 * yr)
    return float(spacing)


def xy_cif_stack_bottom_margin_yr(yr_ref: float, *, show_titles: bool) -> float:
    """Extra room below the lowest CIF row (fraction of ``yr_ref``) for axis padding."""
    yr = max(float(yr_ref), 1e-12)
    if show_titles:
        return float(0.055 * yr)
    return float(0.04 * yr)


def normalize_xy_cif_stack_y_offsets(fig, n_sets: int) -> list:
    """Ensure ``fig._bp_cif_stack_y_offsets`` exists and has length ``n_sets``."""
    if n_sets <= 0:
        fig._bp_cif_stack_y_offsets = []
        return []
    cur = getattr(fig, "_bp_cif_stack_y_offsets", None)
    if cur is None:
        out = [0.0] * n_sets
    else:
        out = []
        for x in list(cur)[:n_sets]:
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                out.append(0.0)
        if len(out) < n_sets:
            out.extend([0.0] * (n_sets - len(out)))
    fig._bp_cif_stack_y_offsets = out
    return out
