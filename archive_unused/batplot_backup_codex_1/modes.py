"""Mode handlers for different batplot plotting modes.

This module implements the core plotting logic for each supported mode:

Supported Modes:
    - CV (Cyclic Voltammetry): voltage vs current curves by cycle
    - GC (Galvanostatic Cycling): capacity vs voltage curves by cycle
    - dQ/dV: differential capacity analysis
    - CPC (Capacity-per-Cycle): capacity and efficiency vs cycle number
    - Operando: combined XRD/electrochemistry contour plots

Architecture:
    Each mode has a handle_*_mode() function that:
    1. Validates input files and arguments
    2. Reads and processes data using readers.py
    3. Creates matplotlib figure with appropriate styling
    4. Optionally launches interactive menu for customization
    5. Saves figure if requested
    6. Returns exit code (0=success, 1=error)

Design Principles:
    - Mode handlers are independent and can be called directly
    - All imports happen at module level (extracted from batplot.py)
    - Interactive menus are optional (graceful degradation)
    - Consistent styling across all modes
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Any, Optional

import numpy as np
import matplotlib.pyplot as plt

from .readers import read_mpt_file, read_ec_csv_file, read_ec_csv_dqdv_file, read_biologic_txt_file
from .electrochem_interactive import electrochem_interactive_menu

# Try to import optional interactive menus
# These may not be available if dependencies are missing
try:
    from .operando_ec_interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None

try:
    from .cpc_interactive import cpc_interactive_menu
except ImportError:
    cpc_interactive_menu = None


def handle_cv_mode(args) -> int:
    """Handle cyclic voltammetry (CV) plotting mode.
    
    Cyclic voltammetry plots show current vs. voltage curves. Each cycle is
    a complete voltage sweep (forward and reverse). This is useful for
    studying redox reactions, electrode kinetics, and electrochemical windows.
    
    Data Flow:
        1. Validate input (single .mpt or .txt file required)
        2. Read voltage, current, cycle data from file
        3. Normalize cycle numbers to start at 1
        4. Plot each cycle with unique color
        5. Handle discontinuities in cycle data (insert NaNs for breaks)
        6. Launch interactive menu or save/show figure
    
    Args:
        args: Argument namespace containing:
            - files: List with single file path (.mpt or .txt)
            - interactive: bool, whether to launch interactive customization menu
            - savefig/out: optional output filename
        
    Returns:
        Exit code: 0 for success, 1 for error
        
    File Format Requirements:
        - .mpt: BioLogic native format with CV mode data
        - .txt: BioLogic exported text format
        - Must contain voltage, current, and cycle index columns
    """
    # === INPUT VALIDATION ===
    if len(args.files) != 1:
        print("CV mode: provide exactly one file (.mpt or .txt).")
        return 1
        
    ec_file = args.files[0]
    if not os.path.isfile(ec_file):
        print(f"File not found: {ec_file}")
        return 1
        
    try:
        # === DATA LOADING ===
        # Support both .mpt (native) and .txt (exported) formats
        if ec_file.lower().endswith('.txt'):
            voltage, current, cycles = read_biologic_txt_file(ec_file, mode='cv')
        else:
            voltage, current, cycles = read_mpt_file(ec_file, mode='cv')
        
        # === CYCLE NORMALIZATION ===
        # Convert cycle numbers to integers and ensure they start at 1
        # Some files may have cycles starting at 0 or negative numbers
        cyc_int_raw = np.array(np.rint(cycles), dtype=int)
        if cyc_int_raw.size:
            min_c = int(np.min(cyc_int_raw))
        else:
            min_c = 1
        
        # Calculate shift needed to start at 1
        shift = 1 - min_c if min_c <= 0 else 0
        cyc_int = cyc_int_raw + shift
        
        # Get sorted list of unique cycle numbers present in data
        cycles_present = sorted(int(c) for c in np.unique(cyc_int)) if cyc_int.size else [1]
        
        # === STYLING SETUP ===
        # Use matplotlib's default color cycle (Tab10 colormap)
        base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                       '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        
        # Configure fonts to match other modes (consistent across batplot)
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.sans-serif': ['Arial', 'DejaVu Sans', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
            'mathtext.fontset': 'dejavusans',
            'font.size': 16
        })
        
        # === FIGURE CREATION ===
        fig, ax = plt.subplots(figsize=(10, 6))
        cycle_lines = {}  # Store line objects for interactive menu
        
        # === PLOTTING EACH CYCLE ===
        for cyc in cycles_present:
            # Get data points belonging to this cycle
            mask = (cyc_int == cyc)
            idx = np.where(mask)[0]
            
            if idx.size >= 2:
                # === HANDLE DISCONTINUITIES ===
                # Some cycles may have gaps (e.g., paused experiments)
                # Split into continuous segments and insert NaN between them
                # This prevents matplotlib from drawing lines across gaps
                
                # Find continuous segments
                parts_x = []
                parts_y = []
                start = 0
                for k in range(1, idx.size):
                    if idx[k] != idx[k-1] + 1:  # Gap detected
                        # Save current segment
                        parts_x.append(voltage[idx[start:k]])
                        parts_y.append(current[idx[start:k]])
                        start = k
                # Save final segment
                parts_x.append(voltage[idx[start:]])
                parts_y.append(current[idx[start:]])
                
                # Concatenate segments with NaN separators
                X = []
                Y = []
                for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                    if i > 0:
                        # Insert NaN between segments
                        X.append(np.array([np.nan]))
                        Y.append(np.array([np.nan]))
                    X.append(px)
                    Y.append(py)
                
                x_b = np.concatenate(X) if X else np.array([])
                y_b = np.concatenate(Y) if Y else np.array([])
                
                # Plot with cycling color (wraps around after 10 colors)
                ln, = ax.plot(x_b, y_b, '-', 
                             color=base_colors[(cyc-1) % len(base_colors)],
                             linewidth=2.0, 
                             label=str(cyc),  # Cycle number in legend
                             alpha=0.8)
                cycle_lines[cyc] = ln
        
        # === FINAL STYLING ===
        ax.set_xlabel('Voltage (V)', labelpad=8.0)
        ax.set_ylabel('Current (mA)', labelpad=8.0)
        legend = ax.legend(title='Cycle')
        legend.get_title().set_fontsize('medium')
        # Adjust margins to prevent label clipping
        fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)
        
        # === SAVE FIGURE (if requested) ===
        outname = args.savefig or args.out
        if outname:
            # Default to SVG if no extension provided
            if not os.path.splitext(outname)[1]:
                outname += '.svg'
            _, _ext = os.path.splitext(outname)
            
            # Special handling for SVG: save with transparent background
            # This allows figures to blend nicely into presentations/documents
            if _ext.lower() == '.svg':
                # Save current background colors so we can restore them
                try:
                    _fig_fc = fig.get_facecolor()
                except Exception:
                    _fig_fc = None
                try:
                    _ax_fc = ax.get_facecolor()
                except Exception:
                    _ax_fc = None
                
                # Temporarily make backgrounds transparent
                try:
                    if getattr(fig, 'patch', None) is not None:
                        fig.patch.set_alpha(0.0)
                        fig.patch.set_facecolor('none')
                    if getattr(ax, 'patch', None) is not None:
                        ax.patch.set_alpha(0.0)
                        ax.patch.set_facecolor('none')
                except Exception:
                    pass
                
                # Save with transparency
                try:
                    fig.savefig(outname, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                finally:
                    # Restore original backgrounds (for interactive display)
                    try:
                        if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(1.0)
                            fig.patch.set_facecolor(_fig_fc)
                    except Exception:
                        pass
                    try:
                        if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(1.0)
                            ax.patch.set_facecolor(_ax_fc)
                    except Exception:
                        pass
            else:
                # Other formats: simple save with high DPI
                fig.savefig(outname, dpi=300)
            print(f"CV plot saved to {outname}")
        
        # Interactive menu
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
                plt.show(block=False)
                try:
                    electrochem_interactive_menu(fig, ax, cycle_lines, file_path=ec_file)
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
        return 0
        
    except Exception as e:
        print(f"CV plot failed: {e}")
        return 1


def handle_gc_mode(args) -> int:
    """Handle galvanostatic cycling (GC) plotting mode.
    
    Galvanostatic cycling plots show voltage vs. capacity curves for each cycle.
    This is the primary visualization for battery cycling data, showing charge/
    discharge behavior, capacity fade, and voltage plateaus.
    
    Features:
        - Automatic cycle detection from file data or inferred from charge/discharge
        - Each cycle plotted in unique color (charge and discharge together)
        - Handles both specific capacity (.mpt with --mass, CSV) and raw capacity
        - Supports discontinuous cycles (paused experiments)
        - Interactive menu for customization
    
    Data Flow:
        1. Validate input (single .mpt or .csv file)
        2. Read capacity, voltage, cycles, charge/discharge masks
        3. For .mpt: requires --mass parameter, calculates specific capacity
        4. For .csv: reads specific capacity directly from file
        5. Group data by cycle, split into charge/discharge segments
        6. Plot each cycle with unique color
        7. Launch interactive menu or save/show
    
    Args:
        args: Argument namespace containing:
            - files: List with single file path (.mpt or .csv)
            - mass: Active material mass in mg (required for .mpt files)
            - interactive: bool, launch customization menu
            - savefig/out: optional output filename
            - raw: unused (legacy parameter)
        
    Returns:
        Exit code: 0 for success, 1 for error
        
    File Format Requirements:
        - .mpt: BioLogic native format, requires --mass parameter
        - .csv: Neware or similar with capacity and cycle columns
    """
    # === INPUT VALIDATION ===
    if len(args.files) != 1:
        print("GC mode: provide exactly one file argument (.mpt or .csv).")
        return 1
    
    ec_file = args.files[0]
    if not os.path.isfile(ec_file):
        print(f"File not found: {ec_file}")
        return 1
    
    try:
        # Branch by extension
        if ec_file.lower().endswith('.mpt'):
            mass_mg = getattr(args, 'mass', None)
            if mass_mg is None:
                print("GC mode (.mpt): --mass parameter is required (active material mass in milligrams).")
                print("Example: batplot file.mpt --gc --mass 7.0")
                return 1
            specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg)
            x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
            cap_x = specific_capacity
        elif ec_file.lower().endswith('.csv'):
            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
            x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
        else:
            print("GC mode: file must be .mpt or .csv")
            return 1

        # Create the plot
        fig, ax = plt.subplots(figsize=(10, 6))

        # Build per-cycle lines for charge and discharge
        def _contiguous_blocks(mask):
            inds = np.where(mask)[0]
            if inds.size == 0:
                return []
            blocks = []
            start = inds[0]
            prev = inds[0]
            for j in inds[1:]:
                if j == prev + 1:
                    prev = j
                else:
                    blocks.append((start, prev))
                    start = j
                    prev = j
            blocks.append((start, prev))
            return blocks

        def _broken_arrays_from_indices(idx: np.ndarray, x: np.ndarray, y: np.ndarray):
            if idx.size == 0:
                return np.array([]), np.array([])
            parts_x = []
            parts_y = []
            start = 0
            for k in range(1, idx.size):
                if idx[k] != idx[k-1] + 1:
                    parts_x.append(x[idx[start:k]])
                    parts_y.append(y[idx[start:k]])
                    start = k
            parts_x.append(x[idx[start:]])
            parts_y.append(y[idx[start:]])
            X = []
            Y = []
            for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                if i > 0:
                    X.append(np.array([np.nan]))
                    Y.append(np.array([np.nan]))
                X.append(px)
                Y.append(py)
            return np.concatenate(X) if X else np.array([]), np.concatenate(Y) if Y else np.array([])

        if cycle_numbers is not None:
            cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
            if cyc_int_raw.size:
                min_c = int(np.min(cyc_int_raw))
            else:
                min_c = 1
            shift = 1 - min_c if min_c <= 0 else 0
            cyc_int = cyc_int_raw + shift
            cycles_present = sorted(int(c) for c in np.unique(cyc_int))
        else:
            cycles_present = [1]

        # Determine if cycle numbers are meaningful
        inferred = len(cycles_present) <= 1
        if inferred:
            ch_blocks = _contiguous_blocks(charge_mask)
            dch_blocks = _contiguous_blocks(discharge_mask)
            cycles_present = list(range(1, max(len(ch_blocks), len(dch_blocks)) + 1)) if (ch_blocks or dch_blocks) else [1]

        base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                   '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

        cycle_lines = {}

        if not inferred and cycle_numbers is not None:
            for cyc in cycles_present:
                mask_c = (cyc_int == cyc) & charge_mask
                idx = np.where(mask_c)[0]
                if idx.size >= 2:
                    x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                    ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                    linewidth=2.0, label=str(cyc), alpha=0.8)
                else:
                    ln_c = None
                mask_d = (cyc_int == cyc) & discharge_mask
                idxd = np.where(mask_d)[0]
                if idxd.size >= 2:
                    xd_b, yd_b = _broken_arrays_from_indices(idxd, cap_x, voltage)
                    lbl = '_nolegend_' if ln_c is not None else str(cyc)
                    ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                    linewidth=2.0, label=lbl, alpha=0.8)
                else:
                    ln_d = None
                cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
        else:
            ch_blocks = _contiguous_blocks(charge_mask)
            dch_blocks = _contiguous_blocks(discharge_mask)
            N = max(len(ch_blocks), len(dch_blocks))
            for i in range(N):
                cyc = i + 1
                ln_c = None
                if i < len(ch_blocks):
                    a, b = ch_blocks[i]
                    idx = np.arange(a, b + 1)
                    x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                    ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                    linewidth=2.0, label=str(cyc), alpha=0.8)
                ln_d = None
                if i < len(dch_blocks):
                    a, b = dch_blocks[i]
                    idx = np.arange(a, b + 1)
                    xd_b, yd_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                    lbl = '_nolegend_' if ln_c is not None else str(cyc)
                    ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                    linewidth=2.0, label=lbl, alpha=0.8)
                cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                
        ax.set_xlabel(x_label_gc, labelpad=8.0)
        ax.set_ylabel('Voltage (V)', labelpad=8.0)
        legend = ax.legend(title='Cycle')
        legend.get_title().set_fontsize('medium')
        fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)

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
                        fig.patch.set_alpha(0.0)
                        fig.patch.set_facecolor('none')
                    if getattr(ax, 'patch', None) is not None:
                        ax.patch.set_alpha(0.0)
                        ax.patch.set_facecolor('none')
                except Exception:
                    pass
                try:
                    fig.savefig(outname, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                finally:
                    try:
                        if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(1.0)
                            fig.patch.set_facecolor(_fig_fc)
                    except Exception:
                        pass
                    try:
                        if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(1.0)
                            ax.patch.set_facecolor(_ax_fc)
                    except Exception:
                        pass
            else:
                fig.savefig(outname, dpi=300)
            print(f"GC plot saved to {outname} ({x_label_gc})")

        # Show plot / interactive menu
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
                plt.show(block=False)
                try:
                    electrochem_interactive_menu(fig, ax, cycle_lines, file_path=ec_file)
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
        return 0
        
    except Exception as _e:
        print(f"GC plot failed: {_e}")
        return 1


__all__ = ['handle_cv_mode', 'handle_gc_mode']
