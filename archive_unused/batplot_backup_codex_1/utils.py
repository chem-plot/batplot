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


def choose_save_path(file_paths: list) -> str:
    """Prompt user to choose save location when terminal path differs from file paths.
    
    Compares current working directory with the directory/directories containing
    the data files. If they differ, prompts user to choose where to save.
    
    Args:
        file_paths: List of file paths (from args.files)
    
    Returns:
        Chosen base directory path (terminal cwd or one of the file directories)
        Returns cwd if paths are the same or on error
        
    Example:
        Terminal: /Users/name/Desktop
        File: /Users/name/Documents/data.csv
        
        Prompts:
          Save location differs from file location. Choose:
            1. Current directory: /Users/name/Desktop [default]
            2. File directory: /Users/name/Documents
          Enter choice (1-2, Enter=1): 
    """
    try:
        # Get current working directory (terminal path)
        cwd = os.getcwd()
        
        # Extract unique directory paths from file list
        file_dirs = set()
        for fpath in file_paths:
            if fpath:
                fdir = os.path.dirname(os.path.abspath(fpath))
                if fdir:  # Only add non-empty directories
                    file_dirs.add(fdir)
        
        # Remove cwd from file_dirs if present (no need to show it twice)
        file_dirs.discard(cwd)
        
        # If no difference or no file directories found, use cwd silently
        if not file_dirs:
            return cwd
        
        # Convert to sorted list for consistent ordering
        file_dirs_list = sorted(file_dirs)
        
        # Build prompt with numbered options
        print("\nSave location differs from file location. Choose:")
        print(f"  1. Current directory: {cwd} [default]")
        
        for idx, fdir in enumerate(file_dirs_list, start=2):
            print(f"  {idx}. File directory: {fdir}")
        
        # Get user choice
        max_choice = len(file_dirs_list) + 1
        prompt = f"Enter choice (1-{max_choice}, Enter=1): "
        
        try:
            choice_str = input(prompt).strip()
        except KeyboardInterrupt:
            print("\nCanceled, using current directory.")
            return cwd
        
        # Default to option 1 (cwd) if Enter pressed
        if not choice_str:
            return cwd
        
        # Parse choice
        try:
            choice = int(choice_str)
            if choice == 1:
                return cwd
            elif 2 <= choice <= max_choice:
                return file_dirs_list[choice - 2]
            else:
                print(f"Invalid choice. Using current directory: {cwd}")
                return cwd
        except ValueError:
            print(f"Invalid input. Using current directory: {cwd}")
            return cwd
    
    except Exception as e:
        # On any error, fall back to cwd
        print(f"Error in path selection: {e}. Using current directory.")
        return os.getcwd()
