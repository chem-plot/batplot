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
	"""Main CLI entry point for batplot.
	
	This function is called when the user runs 'batplot' from command line.
	It performs these steps in order:
	1. Check for updates from PyPI (cached, once per day)
	2. Parse command line arguments
	3. Delegate to batplot_main() which routes to the appropriate mode
	4. Handle errors gracefully
	
	Args:
		argv: Optional command line arguments for testing/programmatic use.
		      If None, uses sys.argv. Format: ['--mode', 'file.ext', ...]
		      (do not include 'batplot' itself, it's added automatically)
		
	Returns:
		Exit code: 0 for success, non-zero for error
		
	Examples:
		>>> main(['--cv', 'data.mpt'])  # For testing
		>>> main()  # Normal CLI usage (reads from sys.argv)
	"""
	# === STEP 1: Version check ===
	# Check PyPI for newer versions, show notification if available
	# This is non-blocking (2s timeout) and cached (24h)
	# Can be disabled with BATPLOT_NO_VERSION_CHECK=1
	try:
		from . import __version__
		from .version_check import check_for_updates
		check_for_updates(__version__)
	except Exception:
		# Silently ignore any errors in version checking
		# We never want this to crash the main program
		pass
	
	# === STEP 2: Prepare arguments ===
	# If argv is provided (testing mode), temporarily replace sys.argv
	# This allows us to test the CLI without actually running from command line
	if argv is not None:
		old_argv = sys.argv
		sys.argv = ['batplot'] + list(argv)
		
	try:
		# === STEP 3: Delegate to main function ===
		# Import here to avoid side effects at module import time
		# batplot_main() will parse args and route to appropriate mode handler
		from .batplot import batplot_main
		return batplot_main()
		
	except ValueError as e:
		# === STEP 4: Error handling ===
		# ValueError is used for user-facing errors (bad args, file not found, etc.)
		# Print clean error message without scary traceback
		print(f"Error: {e}", file=sys.stderr)
		return 1
		
	finally:
		# Restore original sys.argv if we changed it
		if argv is not None:
			sys.argv = old_argv

__all__ = ["main"]
