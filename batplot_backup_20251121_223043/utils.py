"""Utility helpers for batplot.

This module provides file organization and text formatting utilities.
Main functions:
- Directory management: Create and use subdirectories for organized output
- File path resolution: Get appropriate paths for figures, styles, projects
- Text normalization: Format labels for matplotlib rendering
- Overwrite protection: Ask user before overwriting files
"""

import os
import sys
import shutil
import subprocess
from typing import Optional, List, Tuple


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
    
    # Windows/Linux: Try tkinter first
    if not sys.platform.startswith("darwin"):
        try:
            path = _ask_directory_dialog_tk(initialdir)
            if path:
                return path
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
            f'set initialPath to "{initialdir}"',
            "try",
            "    set defaultLocation to POSIX file initialPath",
            f'    set theFolder to choose folder with prompt "{prompt}" default location defaultLocation',
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
            f'    set theFolder to choose folder with prompt "{prompt}"',
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
            selection = res.stdout.strip()
            # Empty string means user canceled (error -128 was caught and returned "")
            if not selection:
                return None
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


def _ask_directory_dialog_tk(initialdir: str) -> Optional[str]:
    """Tkinter-based folder picker (Windows/Linux only - never used on macOS)."""
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
        result = folder if folder else None
        return result
    except Exception as e:
        # Silently fail - will fall back to manual input
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
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            selection = res.stdout.strip()
            return selection or None
    except Exception:
        pass
    return None


def _ask_file_dialog(initialdir: Optional[str] = None, filetypes: Optional[Tuple[str, ...]] = None) -> Optional[str]:
    """Open a platform-aware file picker dialog."""
    initialdir = os.path.abspath(initialdir or os.getcwd())
    if not os.path.isdir(initialdir):
        initialdir = os.path.expanduser("~")
    
    # macOS: use AppleScript for file selection
    if sys.platform.startswith("darwin"):
        return _ask_file_dialog_macos(initialdir)

    # Windows/Linux: try tkinter first
    if not sys.platform.startswith("darwin"):
        try:
            path = _ask_file_dialog_tk(initialdir, filetypes=filetypes)
            if path:
                return path
        except Exception:
            pass

    # Linux desktop fallback via zenity/kdialog if available
    if sys.platform.startswith("linux"):
        try:
            path = _ask_file_dialog_zenity(initialdir, filetypes=filetypes)
            if path:
                return path
        except Exception:
            pass
    
    return None


def _ask_file_dialog_macos(initialdir: str) -> Optional[str]:
    if not shutil.which("osascript"):
        return None
    
    script_parts = [
        f'set initialPath to "{initialdir}"',
        "try",
        "    set defaultLocation to POSIX file initialPath",
        '    set theFile to choose file with prompt "Select a style file" default location defaultLocation',
        "    return POSIX path of theFile",
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
        res = subprocess.run(
            ["osascript"],
            input=script,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if res.returncode == 0:
            selection = res.stdout.strip()
            if selection and os.path.isfile(selection):
                return selection
            return None
        return None
    except Exception:
        return None


def _ask_file_dialog_tk(initialdir: str, filetypes: Optional[Tuple[str, ...]] = None) -> Optional[str]:
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
            tk_filetypes.insert(0, ("Style files", patterns))
        file_path = filedialog.askopenfilename(
            title="Select a style file",
            initialdir=initialdir,
            filetypes=tk_filetypes,
        )
        return file_path or None
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


def _ask_file_dialog_zenity(initialdir: str, filetypes: Optional[Tuple[str, ...]] = None) -> Optional[str]:
    cmd = None
    if shutil.which("zenity"):
        filename_arg = f"--filename={os.path.join(initialdir.rstrip(os.sep), '')}"
        zenity_cmd = [
            "zenity",
            "--file-selection",
            "--title=Select a style file",
            filename_arg,
        ]
        if filetypes:
            patterns = " ".join(f"*{ext}" if ext.startswith('.') else f"*.{ext}" for ext in filetypes)
            zenity_cmd.append(f"--file-filter=Style files | {patterns}")
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
            "Select a style file",
        ]
    if cmd is None:
        return None
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            selection = res.stdout.strip()
            if selection and os.path.isfile(selection):
                return selection
        return None
    except Exception:
        return None


def ensure_subdirectory(subdir_name: str, base_path: str = None) -> str:
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


def get_organized_path(filename: str, file_type: str, base_path: str = None) -> str:
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


def list_files_in_subdirectory(extensions: tuple, file_type: str, base_path: str = None) -> list:
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
    
    # Sort alphabetically by filename for consistent display
    return sorted(files, key=lambda x: x[0])


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
            print(f"  {idx}. {label}{extra}")
        print("  c. Custom path")
        print("  q. Cancel (return to menu)")
        
        max_choice = len(options)
        while True:
            try:
                choice = input(f"Choose path for {purpose} (1-{max_choice}, Enter=1): ").strip()
            except KeyboardInterrupt:
                print("\nCanceled path selection.")
                return None
            
            if not choice:
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
                    # User selected a folder via dialog
                    try:
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
                manual_path = os.path.abspath(os.path.expanduser(manual))
                try:
                    os.makedirs(manual_path, exist_ok=True)
                except Exception as e:
                    print(f"Could not use directory: {e}")
                    continue
                return manual_path
            if choice.isdigit():
                num = int(choice)
                if 1 <= num <= max_choice:
                    return options[num - 1]['path']
                print(f"Invalid number. Enter between 1 and {max_choice}.")
                continue
            # Treat any other input as a manual path entry
            manual_path = os.path.abspath(os.path.expanduser(choice))
            try:
                os.makedirs(manual_path, exist_ok=True)
            except Exception as e:
                print(f"Could not use directory: {e}")
                continue
            return manual_path
    except Exception as e:
        print(f"Error in path selection: {e}. Using current directory.")
        return os.getcwd()


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
            entries = sorted(os.listdir(directory))
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
    if style_candidates:
        print("\nAvailable style files:")
        for idx, cand in enumerate(style_candidates, start=1):
            print(f"  {idx}. {cand['name']}  (in {cand['location']})")
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
    
    while True:
        try:
            choice = input("Select style file (number/path/c=custom/q=cancel): ").strip()
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
