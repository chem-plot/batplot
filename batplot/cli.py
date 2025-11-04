"""CLI entry for batplot.

Clean entry point that delegates to mode handlers without import-time side effects.
"""

from __future__ import annotations

import sys
from typing import Optional

def main(argv: Optional[list] = None) -> int:
	"""Main CLI entry point for batplot.
	
	Args:
		argv: Optional command line arguments (defaults to sys.argv)
		
	Returns:
		Exit code (0 for success, non-zero for error)
	"""
	# Check for updates (non-blocking, cached daily)
	try:
		from . import __version__
		from .version_check import check_for_updates
		check_for_updates(__version__)
	except Exception:
		# Silently ignore any errors in version checking
		pass
	
	# Import here to avoid side effects at module import time
	if argv is not None:
		# Temporarily replace sys.argv for argument parsing
		old_argv = sys.argv
		sys.argv = ['batplot'] + list(argv)
		
	try:
		# Import the main batplot function (now refactored to be safe)
		from .batplot import batplot_main
		return batplot_main()
	except ValueError as e:
		# Print clean error message without traceback
		print(f"Error: {e}", file=sys.stderr)
		return 1
	finally:
		if argv is not None:
			sys.argv = old_argv

__all__ = ["main"]
