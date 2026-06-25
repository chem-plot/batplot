"""Top-level routing handler for operando contour mode.

Extracted verbatim from ``batplot.batplot.batplot_main`` so the dispatcher
stays lean. ``handle_operando_mode`` owns the ``--operando`` route: it
resolves the target folder and optional CIF files, builds the contour plot
via :func:`batplot.plot_modes.operando.plot.plot_operando_folder`, saves the
figure when requested, and opens the interactive menu otherwise.
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from .plot import plot_operando_folder

try:
    from .interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None


def handle_operando_mode(args) -> int:
    """Handle the ``--operando`` route. Always exits via ``exit()`` on completion."""
    try:
        # Determine target folder and optional CIF files
        # Usage: batplot folder [phase.cif:1.54 ...] --operando --interactive
        folder = None
        cif_files = []
        for f in args.files:
            if os.path.isdir(f):
                if folder is None:
                    folder = os.path.abspath(f)
                else:
                    print("Operando mode: provide at most one folder.")
                    exit(1)
            else:
                # CIF file (optionally with :wl), e.g. phase.cif:1.54
                parts = f.split(":")
                if len(parts) >= 1:
                    fname = parts[0]
                    if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
                        # Windows drive letter: C:\path\to\file.cif:1.54
                        fname = parts[0] + ":" + parts[1]
                        parts = [fname] + (parts[2:] if len(parts) > 2 else [])
                    if os.path.splitext(fname)[1].lower() == '.cif':
                        cif_files.append(f)
        if folder is None:
            folder = os.getcwd()

        # Build plot (pass cif_files for CIF tick labels)
        fig, ax, meta = plot_operando_folder(folder, args, cif_files=cif_files)
        im = meta.get('imshow')
        cbar = meta.get('colorbar')
        has_ec = bool(meta.get('has_ec'))
        ec_ax = meta.get('ec_ax') if has_ec else None

        # Save if requested
        outname = args.savefig or args.out
        if outname:
            if not os.path.splitext(outname)[1]:
                outname += '.svg'
            _, _ext = os.path.splitext(outname)
            if _ext.lower() == '.svg':
                try:
                    _fig_fc = fig.get_facecolor()
                except Exception:
                    _fig_fc = None
                try:
                    _ax_fc = ax.get_facecolor()
                except Exception:
                    _ax_fc = None
                try:
                    if getattr(fig, 'patch', None) is not None:
                        fig.patch.set_alpha(0.0); fig.patch.set_facecolor('none')
                    if getattr(ax, 'patch', None) is not None:
                        ax.patch.set_alpha(0.0); ax.patch.set_facecolor('none')
                    if ec_ax is not None and getattr(ec_ax, 'patch', None) is not None:
                        ec_ax.patch.set_alpha(0.0); ec_ax.patch.set_facecolor('none')
                except Exception:
                    pass
                try:
                    fig.savefig(outname, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                finally:
                    try:
                        if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(1.0); fig.patch.set_facecolor(_fig_fc)
                    except Exception:
                        pass
                    try:
                        if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(1.0); ax.patch.set_facecolor(_ax_fc)
                    except Exception:
                        pass
            else:
                fig.savefig(outname, dpi=300)
            print(f"Operando plot saved to {outname}")

        # Interactive or show
        if args.interactive:
            try:
                _backend = plt.get_backend()
            except Exception:
                _backend = "unknown"
            # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
            _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
            _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
            if _is_noninteractive:
                print(f"Matplotlib backend '{_backend}' is non-interactive; a window cannot be shown.")
                print("Tips: unset MPLBACKEND or set a GUI backend")
                print("Or run without --interactive and use --out to save the figure.")
            else:
                try:
                    plt.ion()
                except Exception:
                    pass
                try:
                    plt.show(block=False)
                except Exception:
                    pass
                try:
                    # Call interactive menu regardless of EC presence
                    # When ec_ax is None, EC-related commands will be disabled
                    if operando_ec_interactive_menu is not None:
                        operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, file_paths=args.files)
                    else:
                        print("Interactive menu not available.")
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                plt.show()
        else:
            if not (args.savefig or args.out):
                try:
                    _backend = plt.get_backend()
                except Exception:
                    _backend = "unknown"
                # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                if not _is_noninteractive:
                    plt.show()
                else:
                    print(f"Matplotlib backend '{_backend}' is non-interactive; use --out to save the figure.")
        exit()
    except Exception as _e:
        print(f"Operando plot failed: {_e}")
        exit(1)
