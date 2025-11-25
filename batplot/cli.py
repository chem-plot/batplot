"""CLI entry for batplot.

This module provides the main entry point for the batplot command-line interface.
It handles version checking, argument delegation, and error handling.

Design principles:
- Lazy imports: imports happen inside main() to avoid side effects during module load
- Clean separation: delegates actual work to batplot_main() in batplot.py
- Non-intrusive: version check is silent and non-blocking (max 2s timeout)
"""

from __future__ import annotations

import sys
from typing import Optional


def main(argv: Optional[list] = None) -> int:
	"""
	Main CLI entry point for batplot.
	
	This function is the entry point when users run 'batplot' from the command line.
	It's also the function called by the 'batplot' command installed via pip/setuptools.
	
	HOW IT WORKS:
	-----------
	When you type 'batplot file.xy --interactive' in terminal:
	
	1. Python's setuptools calls this main() function
	2. main() performs version check (non-blocking, cached)
	3. main() parses command-line arguments
	4. main() delegates to batplot_main() which routes to appropriate mode
	5. Errors are caught and displayed cleanly (no scary tracebacks)
	
	WHY LAZY IMPORTS?
	----------------
	We import batplot_main() inside the try block, not at module level.
	This is called "lazy importing" and has benefits:
	- Faster startup: Only imports what's needed when needed
	- Avoids side effects: Some modules might do things at import time
	- Better error handling: Import errors happen in try/except block
	
	Args:
		argv: Optional command line arguments for testing/programmatic use.
		      If None, uses sys.argv (normal CLI usage).
		      Format: ['--mode', 'file.ext', ...]
		      Note: Do NOT include 'batplot' itself, it's added automatically.
		
	Returns:
		Exit code: 0 for success, non-zero for error.
		This follows Unix convention where 0 = success, non-zero = error.
		
	Examples:
		>>> # Testing mode (programmatic use)
		>>> main(['--cv', 'data.mpt'])
		0
		
		>>> # Normal CLI usage (reads from sys.argv)
		>>> main()
		0
	"""
	# ====================================================================
	# STEP 1: VERSION CHECK (NON-BLOCKING)
	# ====================================================================
	# Check PyPI for newer versions of batplot.
	# This is done asynchronously and doesn't block the main program.
	#
	# Features:
	# - Non-blocking: 2 second timeout (won't slow down startup)
	# - Cached: Only checks once per day (saves network requests)
	# - Optional: Can be disabled with BATPLOT_NO_VERSION_CHECK=1 environment variable
	# - Silent failure: If check fails, program continues normally
	#
	# Why check for updates?
	# - Users get notified of bug fixes and new features
	# - Helps maintain an up-to-date installation
	# ====================================================================
	try:
		from . import __version__
		from .version_check import check_for_updates
		check_for_updates(__version__)
	except Exception:
		# Silently ignore any errors in version checking.
		# We NEVER want version checking to crash the main program.
		# If PyPI is down, network is slow, or any other error occurs,
		# the program should continue normally.
		pass
	
	# ====================================================================
	# STEP 2: PREPARE ARGUMENTS (TESTING MODE SUPPORT)
	# ====================================================================
	# If argv is provided (testing/programmatic mode), temporarily replace
	# sys.argv so argparse reads from our test arguments instead of real
	# command line.
	#
	# Why? This allows unit tests to call main() with fake arguments without
	# actually running from command line.
	#
	# Example:
	#   main(['--cv', 'test.mpt'])  # Test with fake arguments
	#   # sys.argv temporarily becomes ['batplot', '--cv', 'test.mpt']
	# ====================================================================
	if argv is not None:
		old_argv = sys.argv  # Save original for restoration
		sys.argv = ['batplot'] + list(argv)  # Replace with test arguments
		
	try:
		# ====================================================================
		# STEP 3: DELEGATE TO MAIN FUNCTION
		# ====================================================================
		# Import here (lazy import) to avoid side effects at module import time.
		# batplot_main() will:
		#   1. Parse command-line arguments using args.parse_args()
		#   2. Route to appropriate mode handler (XY, EC, Operando, Batch)
		#   3. Handle mode-specific logic
		# ====================================================================
		from .batplot import batplot_main
		return batplot_main()
		
	except ValueError as e:
		# ====================================================================
		# STEP 4: ERROR HANDLING
		# ====================================================================
		# ValueError is used for user-facing errors:
		# - Bad command-line arguments
		# - File not found
		# - Invalid file format
		# - Missing required parameters (e.g., --mass for .mpt files)
		#
		# We print a clean error message without scary Python traceback.
		# This makes errors more user-friendly.
		#
		# Other exceptions (unexpected bugs) will still show full traceback
		# for debugging purposes.
		# ====================================================================
		print(f"Error: {e}", file=sys.stderr)
		return 1  # Non-zero exit code indicates error
		
	finally:
		# ====================================================================
		# CLEANUP: RESTORE ORIGINAL sys.argv
		# ====================================================================
		# If we modified sys.argv for testing, restore it now.
		# This ensures tests don't affect each other.
		# ====================================================================
		if argv is not None:
			sys.argv = old_argv

__all__ = ["main"]
