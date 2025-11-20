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
from typing import Optional


def _ask_directory_dialog(initialdir: Optional[str] = None) -> Optional[str]:
    """Open a folder picker dialog with per-platform helpers.
    
    On macOS it uses AppleScript (osascript), avoiding the fragile Tk backend.
    On other platforms it tries tkinter first, then optional desktop helpers.
    Returns ``None`` if the dialog isn't available or the user cancels.
    """
    initialdir = os.path.abspath(initialdir or os.getcwd())
    if not os.path.isdir(initialdir):
        initialdir = os.path.expanduser("~")
    
    # macOS: prefer osascript dialog to avoid Tk crashes
    if sys.platform.startswith("darwin"):
        path = _ask_directory_dialog_macos(initialdir)
        if path:
            return path
        # Fall through to tkinter/other helpers only if AppleScript fails
    
    # Try tkinter (works well on Windows/Linux with X11)
    path = _ask_directory_dialog_tk(initialdir)
    if path:
        return path
    
    # Linux desktop fallback via zenity/kdialog if available
    if sys.platform.startswith("linux"):
        path = _ask_directory_dialog_zenity(initialdir)
        if path:
            return path
    
    return None


def _ask_directory_dialog_macos(initialdir: str) -> Optional[str]:
    """Use AppleScript (osascript) to show the native folder picker on macOS."""
    if not shutil.which("osascript"):
        return None
    prompt = "Select a folder"
    safe_prompt = prompt.replace('"', '\\"')
    safe_initial = initialdir.replace('"', '\\"')
    
    if os.path.isdir(initialdir):
        script = f'''set defaultLocation to POSIX file "{safe_initial}"
try
    set theFolder to choose folder with prompt "{safe_prompt}" default location defaultLocation
    POSIX path of theFolder
on error number -128
    return ""
end try'''
    else:
        script = f'''try
    set theFolder to choose folder with prompt "{safe_prompt}"
    POSIX path of theFolder
on error number -128
    return ""
end try'''
    try:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            selection = res.stdout.strip()
            return selection or None
    except Exception:
        pass
    return None


def _ask_directory_dialog_tk(initialdir: str) -> Optional[str]:
    """Tkinter-based folder picker (Windows/Linux)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None
    
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes('-topmost', True)
        except Exception:
            pass
        folder = filedialog.askdirectory(
            title="Select a folder",
            initialdir=initialdir,
            mustexist=False,
        )
        return folder or None
    except Exception:
        return None
    finally:
        if root is not None:
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
                dialog_path = _ask_directory_dialog(initialdir=cwd)
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
                manual = input("Enter directory path (q=cancel): ").strip()
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
