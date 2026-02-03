"""Manual utilities for batplot.

Instead of generating a PDF, this module exposes the packaged Markdown
manual as a plain text file and opens it in the user's preferred editor.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import hashlib
import os
import shlex
import subprocess
import sys
import tempfile

try:  # Python 3.9+ exposes .files API directly
	from importlib import resources as importlib_resources  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
	import importlib_resources  # type: ignore


MANUAL_RESOURCE = ("batplot.data", "USER_MANUAL.md")
TEXT_NAME = "batplot_manual.txt"
HASH_NAME = "batplot_manual.sha256"
MANUAL_RENDER_VERSION = "4"


def _manual_text() -> str:
	"""
	Load the Markdown manual bundled with the package.
	
	HOW IT WORKS:
	------------
	This function tries multiple methods to find and load the USER_MANUAL.md file:
	
	1. **Modern method (Python 3.9+)**: Uses importlib.resources.files()
	   - This is the recommended way to access package data files
	   - Works with both regular packages and namespace packages
	   - Handles zipped packages (when installed as .egg or .whl)
	
	2. **Fallback method (older Python)**: Uses importlib.resources.open_text()
	   - Compatible with Python 3.7+
	   - Works for most package structures
	
	3. **Local file fallback**: Tries to read from batplot/data/ directory
	   - Used during development (when package isn't installed)
	   - Path(__file__) gets the directory containing this file
	   - .parent / "data" goes up one level and into data/ folder
	
	WHY MULTIPLE METHODS?
	--------------------
	Different Python versions and installation methods require different approaches.
	We try the most modern method first, then fall back to older methods.
	This ensures the manual can be loaded regardless of Python version or
	how batplot was installed (pip, editable install, or running from source).
	
	Returns:
		String containing the full manual text (Markdown format)
	
	Raises:
		FileNotFoundError: If manual cannot be found by any method
	"""
	package, resource = MANUAL_RESOURCE  # Unpack tuple: ("batplot.data", "USER_MANUAL.md")
	
	# METHOD 1: Try modern importlib.resources.files() API (Python 3.9+)
	try:
		# .files() gets a Traversable object representing the package directory
		# .joinpath() navigates to the resource file
		# .read_text() reads the file as a string
		data = importlib_resources.files(package).joinpath(resource).read_text(encoding="utf-8")  # type: ignore[attr-defined]
		return data
	except Exception:
		# Method 1 failed, try next method
		pass
	
	# METHOD 2: Try older importlib.resources.open_text() API (Python 3.7+)
	try:
		# open_text() opens the file as a text file (handles encoding)
		# 'with' statement ensures file is closed automatically
		with importlib_resources.open_text(package, resource, encoding="utf-8") as handle:  # type: ignore[attr-defined]
			return handle.read()  # Read entire file contents
	except Exception:
		# Method 2 failed, try next method
		pass
	
	# METHOD 3: Fallback to local file system (for development)
	# Path(__file__) = path to this file (manual.py)
	# .resolve() = convert to absolute path
	# .parent = go up one directory (from batplot/ to batplot_script/)
	# / "data" / resource = navigate to batplot/data/USER_MANUAL.md
	local_path = Path(__file__).resolve().parent / "data" / resource
	if local_path.exists():
		return local_path.read_text(encoding="utf-8")
	
	# All methods failed - raise error with helpful message
	raise FileNotFoundError(f"Unable to locate manual resource '{resource}'. Tried package '{package}' and {local_path}")


def _manual_hash(text: str) -> str:
	"""
	Calculate SHA256 hash of manual content for cache validation.
	
	HOW IT WORKS:
	------------
	This function creates a "fingerprint" of the manual content. If the content
	changes, the hash changes. We use this to detect when the manual has been
	updated and needs to be regenerated.
	
	WHY INCLUDE VERSION?
	-------------------
	We include MANUAL_RENDER_VERSION in the hash. This means if we change how
	the manual is formatted (even if content is the same), the hash changes
	and cache is invalidated. This ensures users always get the latest format.
	
	HASH ALGORITHM:
	--------------
	SHA256 produces a 256-bit (32-byte) hash. It's:
	- Deterministic: Same input always produces same hash
	- One-way: Can't reverse hash to get original text
	- Collision-resistant: Very unlikely two different texts produce same hash
	
	Args:
		text: Manual content (Markdown text)
	
	Returns:
		64-character hexadecimal string (SHA256 hash)
		Example: "a3f5b2c1d4e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2"
	"""
	# Create SHA256 hash object
	digest = hashlib.sha256()
	# Add version to hash (ensures cache invalidates when format changes)
	digest.update(MANUAL_RENDER_VERSION.encode("utf-8"))
	# Add manual text to hash (ensures cache invalidates when content changes)
	digest.update(text.encode("utf-8"))
	# Return hash as hexadecimal string (64 characters)
	return digest.hexdigest()


def _cache_dir() -> Path:
	"""
	Get the directory where manual cache files are stored.
	
	HOW IT WORKS:
	------------
	This function determines where to store cached manual files. It tries multiple
	locations in order of preference:
	
	1. **Environment variable override**: BATPLOT_CACHE_DIR (user-specified)
	2. **Platform-specific standard locations**:
	   - Windows: %LOCALAPPDATA%\\batplot (usually C:\\Users\\username\\AppData\\Local\\batplot)
	   - Linux/macOS: ~/.cache/batplot (or $XDG_CACHE_HOME/batplot if set)
	3. **Temporary directory fallback**: If standard locations aren't writable
	
	WHY CACHE?
	---------
	The manual is generated from Markdown and cached to avoid regenerating it
	on every run. This speeds up the 'batplot -m' command.
	
	WHY PLATFORM-SPECIFIC?
	----------------------
	Different operating systems have different conventions for where application
	data should be stored. We follow platform conventions for better integration.
	
	Returns:
		Path object pointing to cache directory (always writable)
	"""
	# Check for user override via environment variable
	env_override = os.environ.get("BATPLOT_CACHE_DIR")
	if env_override:
		# User specified custom location - use it
		# expanduser() converts ~ to actual home directory path
		target = Path(env_override).expanduser()
	elif os.name == "nt":
		# Windows: Use LOCALAPPDATA (standard location for app data)
		# Fallback to AppData/Local if environment variable not set
		base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
		target = base / "batplot"
	else:
		# Linux/macOS: Use XDG_CACHE_HOME (standard location) or ~/.cache
		# XDG_CACHE_HOME is a Linux standard, ~/.cache is the default
		base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
		target = base / "batplot"
	
	# Try to create and use the preferred directory
	try:
		# mkdir(parents=True, exist_ok=True) creates directory and all parent directories
		# parents=True: Create parent dirs if they don't exist
		# exist_ok=True: Don't raise error if directory already exists
		target.mkdir(parents=True, exist_ok=True)
		# Check if directory is writable (permissions check)
		if os.access(target, os.W_OK):
			return target
	except OSError:
		# Creation failed or not writable, fall back to temp directory
		pass
	
	# Fallback: Use system temporary directory
	# This is always writable, but files may be cleaned up by system
	fallback = Path(tempfile.gettempdir()) / "batplot-manual"
	fallback.mkdir(parents=True, exist_ok=True)
	return fallback


def _resolve_editor_command() -> List[str]:
	"""
	Determine which text editor command to use for opening the manual.
	
	HOW IT WORKS:
	------------
	This function checks environment variables and platform defaults to find
	the best text editor to use. It follows this priority order:
	
	1. BATPLOT_MANUAL_EDITOR: User's explicit choice for batplot
	2. VISUAL: Standard environment variable (preferred for GUI editors)
	3. EDITOR: Standard environment variable (fallback, often terminal editor)
	4. Platform defaults:
	   - Windows: notepad.exe (built-in text editor)
	   - macOS: open (opens with default app for .txt files)
	   - Linux: xdg-open (opens with default app for .txt files)
	
	WHY SHLEX.SPLIT()?
	-----------------
	Environment variables might contain commands with arguments:
	Example: EDITOR="code --wait" or EDITOR="vim -R"
	shlex.split() properly splits the command string into a list:
	"code --wait" → ["code", "--wait"]
	This prevents errors when the command has spaces or arguments.
	
	Returns:
		List of command and arguments, ready for subprocess.Popen()
		Example: ["code", "--wait"] or ["notepad.exe"]
	"""
	# Check environment variables in priority order
	for var in ("BATPLOT_MANUAL_EDITOR", "VISUAL", "EDITOR"):
		cmd = os.environ.get(var)
		if cmd:
			# Split command string into list (handles arguments properly)
			# Example: "code --wait" → ["code", "--wait"]
			return shlex.split(cmd)
	
	# No environment variable set - use platform defaults
	if sys.platform.startswith("win"):
		# Windows: Use built-in Notepad
		return ["notepad.exe"]
	if sys.platform.startswith("darwin"):
		# macOS: Use 'open' command (opens with default app)
		return ["open"]
	# Linux/other: Use xdg-open (opens with default app)
	return ["xdg-open"]


def _open_editor(path: Path) -> None:
	cmd = _resolve_editor_command()
	try:
		process_args = cmd + [str(path)]
		subprocess.Popen(process_args)
	except Exception as exc:  # pragma: no cover - best effort
		print(f"Manual saved to {path} (auto-open failed: {exc})")


def show_manual(open_viewer: bool = True) -> str:
	"""
	Ensure a plain-text manual exists and optionally open it.
	
	HOW IT WORKS:
	------------
	This function manages the manual cache and opens the manual for viewing:
	
	1. **Load manual text**: Read USER_MANUAL.md from package
	2. **Check cache**: See if we already have a cached .txt file
	3. **Validate cache**: Compare hash of current content vs cached hash
	4. **Regenerate if needed**: If content changed, create new .txt file
	5. **Open editor**: Launch user's preferred text editor (if requested)
	
	CACHING STRATEGY:
	---------------
	We cache the manual to avoid regenerating it on every run. The cache is
	invalidated when:
	- Manual content changes (detected by hash comparison)
	- Manual format version changes (MANUAL_RENDER_VERSION)
	
	This means users get fresh manual when it's updated, but don't regenerate
	unnecessarily when nothing has changed.
	
	Args:
		open_viewer: If True, automatically open manual in text editor.
		            If False, just ensure file exists but don't open it.
	
	Returns:
		Path to the manual .txt file (as string)
		Example: "/Users/username/.cache/batplot/batplot_manual.txt"
	"""
	text = _manual_text()
	target_dir = _cache_dir()
	txt_path = target_dir / TEXT_NAME
	hash_path = target_dir / HASH_NAME
	content_hash = _manual_hash(text)
	cached_hash = hash_path.read_text(encoding="utf-8").strip() if hash_path.exists() else ""

	if (not txt_path.exists()) or (cached_hash != content_hash):
		txt_path.write_text(text, encoding="utf-8")
		hash_path.write_text(content_hash, encoding="utf-8")

	if open_viewer:
		_open_editor(txt_path)
	return str(txt_path)


def main(argv: list[str] | None = None) -> int:
	path = show_manual(open_viewer=True)
	print(f"batplot manual ready at {path}")
	return 0


__all__ = ["show_manual", "main"]


if __name__ == "__main__":  # pragma: no cover
	sys.exit(main())

