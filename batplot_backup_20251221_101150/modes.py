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
        
        # ====================================================================
        # CYCLE NORMALIZATION
        # ====================================================================
        # Different cycler software may number cycles differently:
        #   - Some start at 0 (Cycle 0, Cycle 1, Cycle 2, ...)
        #   - Some start at 1 (Cycle 1, Cycle 2, Cycle 3, ...)
        #   - Some use negative numbers or other schemes
        #
        # We normalize all cycles to start at 1 for consistency and user-friendliness.
        # This ensures Cycle 1 always means "the first cycle" regardless of file format.
        #
        # HOW IT WORKS:
        # 1. Round cycle numbers to integers (they might be floats from file)
        # 2. Find the minimum cycle number
        # 3. Calculate shift needed to make minimum = 1
        # 4. Apply shift to all cycles
        #
        # Example:
        #   File has cycles: [0, 0, 0, 1, 1, 1, 2, 2, 2]
        #   min_c = 0
        #   shift = 1 - 0 = 1
        #   Result: [1, 1, 1, 2, 2, 2, 3, 3, 3]
        # ====================================================================
        
        # Convert cycle numbers to integers (round to nearest integer first)
        # Some files might have fractional cycle numbers due to data processing
        cyc_int_raw = np.array(np.rint(cycles), dtype=int)
        
        # Find the minimum cycle number in the data
        if cyc_int_raw.size:
            min_c = int(np.min(cyc_int_raw))
        else:
            min_c = 1  # Default if no data
        
        # Calculate shift needed to make cycles start at 1
        # If min_c is 0 or negative, we need to shift up
        # If min_c is already 1 or greater, no shift needed
        shift = 1 - min_c if min_c <= 0 else 0
        
        # Apply shift to all cycles
        cyc_int = cyc_int_raw + shift
        
        # Get sorted list of unique cycle numbers present in data
        # This tells us which cycles we need to plot (e.g., [1, 2, 3, 5, 7] if cycles 4 and 6 are missing)
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
        
        # ====================================================================
        # PLOTTING EACH CYCLE
        # ====================================================================
        # Loop through each cycle and plot it as a separate line.
        # Each cycle gets a different color from the base_colors list.
        #
        # HOW CYCLES ARE READ:
        # --------------------
        # The data file contains voltage and current measurements, with each
        # measurement point labeled with a cycle number. We group points by
        # cycle number and plot each group as a separate line.
        #
        # Example data structure:
        #   voltage = [3.0, 3.1, 3.2, 2.9, 2.8, 2.7, 3.0, 3.1, 3.2, ...]
        #   current = [0.1, 0.2, 0.3, -0.1, -0.2, -0.3, 0.1, 0.2, 0.3, ...]
        #   cycles  = [1,   1,   1,   2,   2,   2,   3,   3,   3,   ...]
        #
        # This means:
        #   - Points 0-2 belong to Cycle 1 (voltage increasing = charge)
        #   - Points 3-5 belong to Cycle 2 (voltage decreasing = discharge)
        #   - Points 6-8 belong to Cycle 3 (voltage increasing = charge)
        #
        # We plot each cycle as a separate line with a different color.
        # ====================================================================
        
        for cyc in cycles_present:
            # STEP 1: Find all data points that belong to this cycle
            # Create a boolean mask: True where cycle number matches current cycle
            mask = (cyc_int == cyc)
            # Get indices where mask is True (these are the data points for this cycle)
            idx = np.where(mask)[0]
            
            # Need at least 2 points to draw a line
            if idx.size >= 2:
                # ============================================================
                # HANDLE DISCONTINUITIES (Gaps in Data)
                # ============================================================
                # Sometimes experiments are paused, or data is recorded in segments.
                # This creates gaps in the data where consecutive indices are not
                # sequential (e.g., indices [10, 11, 12, 50, 51, 52] has a gap).
                #
                # Problem: If we plot all points as one line, matplotlib will draw
                #          a line connecting the gap (which looks wrong).
                #
                # Solution: Split into continuous segments and insert NaN between them.
                #           Matplotlib treats NaN as a break in the line, so it won't
                #           draw across the gap.
                #
                # Example:
                #   Original indices: [10, 11, 12, 50, 51, 52]
                #   Segments found: [10-12] and [50-52]
                #   After NaN insertion: [10, 11, 12, NaN, 50, 51, 52]
                #   Result: Two separate line segments, no line across the gap
                # ============================================================
                
                # Find all continuous segments (runs of consecutive indices)
                parts_x = []  # Will store voltage arrays for each segment
                parts_y = []  # Will store current arrays for each segment
                start = 0     # Start index of current segment
                
                # Scan through indices looking for gaps
                for k in range(1, idx.size):
                    # If current index is not consecutive with previous, we found a gap
                    if idx[k] != idx[k-1] + 1:  # Gap detected
                        # Save the segment we just finished (from start to k-1)
                        parts_x.append(voltage[idx[start:k]])
                        parts_y.append(current[idx[start:k]])
                        # Start tracking a new segment
                        start = k
                
                # Don't forget the last segment (after the loop ends)
                parts_x.append(voltage[idx[start:]])
                parts_y.append(current[idx[start:]])
                
                # STEP 2: Concatenate segments with NaN separators
                # This creates one array per axis, with NaN values marking segment breaks
                X = []  # Will contain all voltage segments with NaN separators
                Y = []  # Will contain all current segments with NaN separators
                
                for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                    if i > 0:
                        # Insert NaN between segments (except before the first segment)
                        # This tells matplotlib to break the line here
                        X.append(np.array([np.nan]))
                        Y.append(np.array([np.nan]))
                    # Add the segment data
                    X.append(px)
                    Y.append(py)
                
                # Concatenate all segments into single arrays for plotting
                x_b = np.concatenate(X) if X else np.array([])
                y_b = np.concatenate(Y) if Y else np.array([])
                
                # STEP 3: Plot this cycle with a unique color
                # Color selection: Cycle through base_colors list, wrapping around if needed
                # Example: Cycle 1 → color[0], Cycle 2 → color[1], ..., Cycle 11 → color[0] (wrapped)
                # The modulo operator (%) ensures we wrap around: (cyc-1) % 10 gives 0-9
                # Swap x and y if --ro flag is set
                if getattr(args, 'ro', False):
                    ln, = ax.plot(y_b, x_b, '-',  # '-' = solid line style
                                 color=base_colors[(cyc-1) % len(base_colors)],  # Cycle through colors
                                 linewidth=2.0,   # Line thickness
                                 label=str(cyc),  # Cycle number for legend
                                 alpha=0.8)       # Slight transparency (80% opaque)
                else:
                    ln, = ax.plot(x_b, y_b, '-',  # '-' = solid line style
                                 color=base_colors[(cyc-1) % len(base_colors)],  # Cycle through colors
                                 linewidth=2.0,   # Line thickness
                                 label=str(cyc),  # Cycle number for legend
                                 alpha=0.8)       # Slight transparency (80% opaque)
                
                # Store line object for interactive menu (allows changing color later)
                cycle_lines[cyc] = ln
        
        # === FINAL STYLING ===
        # Swap axis labels if --ro flag is set
        if getattr(args, 'ro', False):
            ax.set_xlabel('Current (mA)', labelpad=8.0)
            ax.set_ylabel('Voltage (V)', labelpad=8.0)
        else:
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
                    fig._bp_source_paths = [os.path.abspath(ec_file)]
                except Exception:
                    pass
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

        # ====================================================================
        # CYCLE PROCESSING: BUILD PER-CYCLE LINES FOR CHARGE AND DISCHARGE
        # ====================================================================
        # In GC mode, each cycle consists of two parts:
        #   1. Charge segment: capacity increases, voltage increases
        #   2. Discharge segment: capacity continues, voltage decreases
        #
        # We need to:
        #   - Group data points by cycle number
        #   - Separate charge and discharge segments within each cycle
        #   - Handle gaps in data (paused experiments)
        #   - Plot each cycle with a unique color
        #
        # Helper functions below handle the data segmentation.
        # ====================================================================
        
        def _contiguous_blocks(mask):
            """
            Find all contiguous blocks (runs) of True values in a boolean mask.
            
            HOW IT WORKS:
            ------------
            Scans through indices where mask is True, looking for gaps.
            Each continuous run becomes one block.
            
            Example:
                mask = [F, T, T, T, F, F, T, T, F]
                indices = [1, 2, 3, 6, 7]
                Blocks found: (1, 3) and (6, 7)
            
            Returns:
                List of (start_index, end_index) tuples for each contiguous block
            """
            inds = np.where(mask)[0]  # Get all indices where mask is True
            if inds.size == 0:
                return []
            
            blocks = []
            start = inds[0]  # Start of current block
            prev = inds[0]   # Previous index seen
            
            # Scan through indices looking for gaps
            for j in inds[1:]:
                if j == prev + 1:
                    # Consecutive, continue current block
                    prev = j
                else:
                    # Gap found, save current block and start new one
                    blocks.append((start, prev))
                    start = j
                    prev = j
            
            # Don't forget the last block
            blocks.append((start, prev))
            return blocks

        def _broken_arrays_from_indices(idx: np.ndarray, x: np.ndarray, y: np.ndarray):
            """
            Extract x and y data for given indices, handling gaps with NaN separators.
            
            HOW IT WORKS:
            ------------
            If indices are not consecutive (e.g., [10, 11, 12, 50, 51, 52]),
            we split into segments and insert NaN between them. This prevents
            matplotlib from drawing lines across gaps.
            
            Example:
                idx = [10, 11, 12, 50, 51, 52]
                x = [0, 1, 2, ..., 100]
                y = [3.0, 3.1, 3.2, ..., 4.0]
                
                Result:
                    x_b = [x[10], x[11], x[12], NaN, x[50], x[51], x[52]]
                    y_b = [y[10], y[11], y[12], NaN, y[50], y[51], y[52]]
            
            This creates two separate line segments with no connecting line.
            
            Args:
                idx: Array of indices to extract
                x: Full x data array
                y: Full y data array
            
            Returns:
                Tuple of (x_broken, y_broken) arrays with NaN separators
            """
            if idx.size == 0:
                return np.array([]), np.array([])
            
            # Find continuous segments
            parts_x = []  # Will store x segments
            parts_y = []  # Will store y segments
            start = 0     # Start of current segment
            
            # Scan for gaps
            for k in range(1, idx.size):
                if idx[k] != idx[k-1] + 1:  # Gap detected
                    # Save segment from start to k-1
                    parts_x.append(x[idx[start:k]])
                    parts_y.append(y[idx[start:k]])
                    start = k
            
            # Save last segment
            parts_x.append(x[idx[start:]])
            parts_y.append(y[idx[start:]])
            
            # Concatenate with NaN separators
            X = []
            Y = []
            for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                if i > 0:
                    # Insert NaN between segments
                    X.append(np.array([np.nan]))
                    Y.append(np.array([np.nan]))
                X.append(px)
                Y.append(py)
            
            return np.concatenate(X) if X else np.array([]), np.concatenate(Y) if Y else np.array([])

        # ====================================================================
        # CYCLE NUMBER PROCESSING
        # ====================================================================
        # Some files have explicit cycle numbers, others don't.
        # We handle both cases:
        #
        # Case 1: File has cycle numbers
        #   - Normalize to start at 1 (same as CV mode)
        #   - Use cycle numbers directly
        #
        # Case 2: File has no cycle numbers (or only one cycle)
        #   - Infer cycles from charge/discharge segments
        #   - Each charge+discharge pair becomes one cycle
        # ====================================================================

        if cycle_numbers is not None:
            # File has cycle numbers: normalize them to start at 1
            cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
            if cyc_int_raw.size:
                min_c = int(np.min(cyc_int_raw))
            else:
                min_c = 1
            shift = 1 - min_c if min_c <= 0 else 0
            cyc_int = cyc_int_raw + shift
            cycles_present = sorted(int(c) for c in np.unique(cyc_int))
        else:
            # No cycle numbers in file
            cycles_present = [1]

        # ====================================================================
        # DETERMINE IF WE NEED TO INFER CYCLES
        # ====================================================================
        # If file has only 1 cycle (or none), we infer cycles from charge/discharge
        # segments. This handles files where cycle numbers weren't recorded.
        #
        # Inference method:
        #   - Find all contiguous charge blocks
        #   - Find all contiguous discharge blocks
        #   - Pair them sequentially: block 0+1 = Cycle 1, block 2+3 = Cycle 2, etc.
        # ====================================================================
        inferred = len(cycles_present) <= 1
        if inferred:
            # Infer cycles from charge/discharge segments
            ch_blocks = _contiguous_blocks(charge_mask)   # All charge segments
            dch_blocks = _contiguous_blocks(discharge_mask)  # All discharge segments
            
            # Number of cycles = max of charge or discharge segments
            # (Some experiments might start with charge, others with discharge)
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
                    # Swap x and y if --ro flag is set
                    if getattr(args, 'ro', False):
                        ln_c, = ax.plot(y_b, x_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=str(cyc), alpha=0.8)
                    else:
                        ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=str(cyc), alpha=0.8)
                else:
                    ln_c = None
                mask_d = (cyc_int == cyc) & discharge_mask
                idxd = np.where(mask_d)[0]
                if idxd.size >= 2:
                    xd_b, yd_b = _broken_arrays_from_indices(idxd, cap_x, voltage)
                    lbl = '_nolegend_' if ln_c is not None else str(cyc)
                    # Swap x and y if --ro flag is set
                    if getattr(args, 'ro', False):
                        ln_d, = ax.plot(yd_b, xd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=lbl, alpha=0.8)
                    else:
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
                    # Swap x and y if --ro flag is set
                    if getattr(args, 'ro', False):
                        ln_c, = ax.plot(y_b, x_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=str(cyc), alpha=0.8)
                    else:
                        ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=str(cyc), alpha=0.8)
                ln_d = None
                if i < len(dch_blocks):
                    a, b = dch_blocks[i]
                    idx = np.arange(a, b + 1)
                    xd_b, yd_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                    lbl = '_nolegend_' if ln_c is not None else str(cyc)
                    # Swap x and y if --ro flag is set
                    if getattr(args, 'ro', False):
                        ln_d, = ax.plot(yd_b, xd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=lbl, alpha=0.8)
                    else:
                        ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=lbl, alpha=0.8)
                cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                
        # Swap x and y if --ro flag is set
        if getattr(args, 'ro', False):
            ax.set_xlabel('Voltage (V)', labelpad=8.0)
            ax.set_ylabel(x_label_gc, labelpad=8.0)
        else:
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
                    fig._bp_source_paths = [os.path.abspath(ec_file)]
                except Exception:
                    pass
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
