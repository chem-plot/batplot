"""Top-level routing handlers for electrochemistry plotting modes.

These handlers were extracted verbatim from
``batplot.batplot.batplot_main`` to keep the central dispatcher lean. Each
function owns one CLI route and terminates the process via ``exit()`` once
its work is done (mirroring the original inline behaviour):

* :func:`handle_gc_mode`   -- ``--gc``   galvanostatic cycling
* :func:`handle_dqdv_mode` -- ``--dqdv`` differential capacity

The shared electrochem layout / mass helpers live in
:mod:`batplot.ec_common` so importing them here does not create a circular
dependency back to :mod:`batplot.batplot`.
"""

from __future__ import annotations

import os
import json
from typing import Any, Tuple, cast

import numpy as np  # type: ignore
import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...ec_common import (
    _resolve_mass,
    _default_ec_figsize,
    _apply_default_ec_layout,
)
from ..._mpl_backend import ensure_gui_backend, require_interactive_display, show_figure_if_possible
from ...batch import _apply_ec_style
from ...utils import ensure_subdirectory
from ...readers import (
    read_mpt_file,
    read_ec_csv_file,
    read_ec_csv_dqdv_file,
    compute_dqdv_numerical,
    read_mpt_dqdv_file,
    read_cs_b_csv_file,
    is_cs_b_format,
    is_biologic_datalogger_csv,
    read_biologic_datalogger_csv,
    read_biologic_datalogger_dqdv_file,
    _load_csv_header_and_rows,
    read_batx_file,
    read_indexed_voltage_time_file,
    read_biologic_txt_file,
)
from .interactive import electrochem_interactive_menu
from ..common.palettes import TAB10_HEX


def handle_gc_mode(args) -> int:
    ensure_gui_backend(args)
    # Separate style files from data files
    data_files = []
    style_file_path = None
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            if style_file_path is None:
                style_file_path = f
            else:
                print(f"Warning: Multiple style files provided, using first: {style_file_path}")
        else:
            data_files.append(f)
    
    if not data_files:
        print("GC mode: no data files found (only style files provided).")
        exit(1)
    
    # Load style file if provided
    style_cfg = None
    if style_file_path:
        if not os.path.isfile(style_file_path):
            print(f"Warning: Style file not found: {style_file_path}")
        else:
            try:
                with open(style_file_path, 'r', encoding='utf-8') as f:
                    style_cfg = json.load(f)
                print(f"Using style file: {os.path.basename(style_file_path)}")
            except Exception as e:
                print(f"Warning: Could not load style file {style_file_path}: {e}")
    
    # Process each data file
    out_dir = None
    if len(data_files) > 1 and (args.savefig or args.out):
        # Multiple files: create output directory
        out_dir = ensure_subdirectory('Figures', os.getcwd())

    # GC multi-file: one figure with all files overlaid (same for interactive and non-interactive)
    if len(data_files) > 1:
        fig, ax = plt.subplots(figsize=_default_ec_figsize())
        file_data = []
        base_colors = TAB10_HEX
        # Default to specific capacity; may be overridden to absolute capacity
        x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'

        def _contiguous_blocks(mask):
            inds = np.where(mask)[0]
            if inds.size == 0:
                return []
            blocks = []
            start, prev = inds[0], inds[0]
            for j in inds[1:]:
                if j == prev + 1:
                    prev = j
                else:
                    blocks.append((start, prev))
                    start, prev = j, j
            blocks.append((start, prev))
            return blocks

        def _broken_arrays_from_idx(idx, x, y):
            if idx.size == 0:
                return np.array([]), np.array([])
            parts_x, parts_y = [], []
            start = 0
            for k in range(1, idx.size):
                if idx[k] != idx[k - 1] + 1:
                    parts_x.append(x[idx[start:k]])
                    parts_y.append(y[idx[start:k]])
                    start = k
            parts_x.append(x[idx[start:]])
            parts_y.append(y[idx[start:]])
            X, Y = [], []
            for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                if i > 0:
                    X.append(np.array([np.nan]))
                    Y.append(np.array([np.nan]))
                X.append(px)
                Y.append(py)
            return np.concatenate(X) if X else np.array([]), np.concatenate(Y) if Y else np.array([])

        for file_idx, ec_file in enumerate(data_files):
            if not os.path.isfile(ec_file) or not (ec_file.lower().endswith('.mpt') or ec_file.lower().endswith('.csv')):
                continue
            try:
                mass_mg = _resolve_mass(getattr(args, 'mass', None), file_idx)
                if ec_file.lower().endswith('.mpt'):
                    if mass_mg is None:
                        continue
                    specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = cast(
                        Tuple[Any, Any, Any, Any, Any], read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg)
                    )
                    cap_x = specific_capacity
                elif ec_file.lower().endswith('.csv'):
                    if is_biologic_datalogger_csv(ec_file):
                        if mass_mg is None:
                            continue
                        cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_biologic_datalogger_csv(
                            ec_file, mass_mg=mass_mg
                        )
                        header = None
                    else:
                        try:
                            header, _, _ = _load_csv_header_and_rows(ec_file)
                            if is_cs_b_format(header):
                                cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_cs_b_csv_file(ec_file, mode='gc')
                            else:
                                cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                        except Exception:
                            header = None
                            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                    # If we only have absolute capacity and the user supplied --mass,
                    # convert Capacity(mAh) → Specific Capacity (mAh g⁻¹).
                    if header is not None:
                        header_stripped = [h.strip().replace('\t', '') for h in header]
                        has_spec = any('Spec. Cap.(mAh/g)' in h for h in header_stripped)
                        has_abs = any('Capacity(mAh)' == h for h in header_stripped)
                        if has_abs and not has_spec:
                            if mass_mg is not None and mass_mg > 0:
                                # Treat cap_x as absolute capacity (mAh) and rescale to mAh/g
                                cap_x = cap_x * (1000.0 / float(mass_mg))
                                x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                            else:
                                # No mass supplied: keep absolute capacity but warn the user
                                print(f"GC mode: {os.path.basename(ec_file)!r} contains only Capacity(mAh) with no specific-capacity column.")
                                print("         Pass --mass <mg> to plot specific capacity (mAh g^-1) instead of raw mAh.")
                else:
                    continue
                color_offset = (file_idx * 5) % len(base_colors)
                if cycle_numbers is not None:
                    cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
                    min_c = int(np.min(cyc_int_raw)) if cyc_int_raw.size else 1
                    shift = 1 - min_c if min_c <= 0 else 0
                    cyc_int = cyc_int_raw + shift
                    cycles_present = sorted(int(c) for c in np.unique(cyc_int))
                else:
                    cycles_present = [1]
                inferred = len(cycles_present) <= 1
                if inferred:
                    ch_blocks = _contiguous_blocks(charge_mask)
                    dch_blocks = _contiguous_blocks(discharge_mask)
                    cycles_present = list(range(1, max(len(ch_blocks), len(dch_blocks)) + 1)) if (ch_blocks or dch_blocks) else [1]
                # Legend: multi-file use filename (or display_name) so legend reflects data
                file_lbl = os.path.basename(ec_file) if len(data_files) > 1 else ""
                cycle_lines = {}
                if not inferred and cycle_numbers is not None:
                    for cyc in cycles_present:
                        mask_c = (cyc_int == cyc) & charge_mask
                        idx = np.where(mask_c)[0]
                        ln_c = None
                        if idx.size >= 2:
                            x_b, y_b = _broken_arrays_from_idx(idx, cap_x, voltage)
                            col = base_colors[(color_offset + cyc - 1) % len(base_colors)]
                            leg_cyc = f"{file_lbl}: {cyc}" if file_lbl else str(cyc)
                            if getattr(args, 'ro', False):
                                ln_c, = ax.plot(y_b, x_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                            else:
                                ln_c, = ax.plot(x_b, y_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                        mask_d = (cyc_int == cyc) & discharge_mask
                        idxd = np.where(mask_d)[0]
                        ln_d = None
                        if idxd.size >= 2:
                            xd_b, yd_b = _broken_arrays_from_idx(idxd, cap_x, voltage)
                            lbl = '_nolegend_' if ln_c is not None else (f"{file_lbl}: {cyc}" if file_lbl else str(cyc))
                            col = base_colors[(color_offset + cyc - 1) % len(base_colors)]
                            if getattr(args, 'ro', False):
                                ln_d, = ax.plot(yd_b, xd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                            else:
                                ln_d, = ax.plot(xd_b, yd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                        cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                else:
                    ch_blocks = _contiguous_blocks(charge_mask)
                    dch_blocks = _contiguous_blocks(discharge_mask)
                    N = max(len(ch_blocks), len(dch_blocks))
                    for i in range(N):
                        cyc = i + 1
                        col = base_colors[(color_offset + cyc - 1) % len(base_colors)]
                        leg_cyc = f"{file_lbl}: {cyc}" if file_lbl else str(cyc)
                        ln_c = None
                        if i < len(ch_blocks):
                            a, b = ch_blocks[i]
                            idx = np.arange(a, b + 1)
                            x_b, y_b = _broken_arrays_from_idx(idx, cap_x, voltage)
                            if getattr(args, 'ro', False):
                                ln_c, = ax.plot(y_b, x_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                            else:
                                ln_c, = ax.plot(x_b, y_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                        ln_d = None
                        if i < len(dch_blocks):
                            a, b = dch_blocks[i]
                            idx = np.arange(a, b + 1)
                            xd_b, yd_b = _broken_arrays_from_idx(idx, cap_x, voltage)
                            lbl = '_nolegend_' if ln_c is not None else (f"{file_lbl}: {cyc}" if file_lbl else str(cyc))
                            if getattr(args, 'ro', False):
                                ln_d, = ax.plot(yd_b, xd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                            else:
                                ln_d, = ax.plot(xd_b, yd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                        cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                file_data.append({
                    'filename': os.path.basename(ec_file),
                    'display_name': os.path.basename(ec_file),
                    'cycle_lines': cycle_lines,
                    'visible': True,
                    'filepath': ec_file,
                })
            except Exception as _e:
                print(f"GC multi-file: skip {ec_file}: {_e}")
        if not file_data:
            print("GC multi-file: no files loaded.")
            exit(1)
        if getattr(args, 'ro', False):
            ax.set_xlabel('Potential (V)', labelpad=8.0)
            ax.set_ylabel(x_label_gc, labelpad=8.0)
        else:
            ax.set_xlabel(x_label_gc, labelpad=8.0)
            ax.set_ylabel('Potential (V)', labelpad=8.0)
        ax.legend(title='Cycle')
        fig._ec_legend_title = "Cycle"
        _apply_default_ec_layout(fig)
        if style_cfg:
            try:
                _apply_ec_style(fig, ax, style_cfg)
                if hasattr(fig, 'canvas'):
                    fig.canvas.draw()
            except Exception as e:
                print(f"Warning: Error applying style file: {e}")
        try:
            plt.ion()
        except Exception:
            pass
        plt.show(block=False)
        try:
            fig._bp_source_paths = [os.path.abspath(f.get('filepath', '')) for f in file_data if f.get('filepath')]
        except Exception:
            pass
        if args.interactive:
            try:
                electrochem_interactive_menu(fig, ax, file_data=file_data)
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            plt.show()
        else:
            if out_dir and (args.savefig or getattr(args, 'out', None)):
                out_path = getattr(args, 'out', None)
                if not out_path:
                    ext = getattr(args, 'format', 'svg') or 'svg'
                    out_path = os.path.join(out_dir, f'GC_combined.{ext}')
                try:
                    fig.savefig(out_path, dpi=300, bbox_inches='tight')
                    print(f"Saved {out_path}")
                except Exception as e:
                    print(f"Could not save: {e}")
            try:
                plt.ioff()
            except Exception:
                pass
            print(f"Processed {len(file_data)} GC files.")
            plt.show(block=True)
        exit(0)

    for ec_file_idx, ec_file in enumerate(data_files):
        if not os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            continue
        
        try:
            mass_mg = _resolve_mass(getattr(args, 'mass', None), ec_file_idx)
            # Check for potential-window mode first (custom voltage-time format)
            if getattr(args, 'pw', None) is not None:
                v_min, v_max = args.pw
                current_density = getattr(args, 'cd', None)
                if current_density is None:
                    print("Potential-window mode: --cd parameter is required (current density in mA/g).")
                    print("Example: batplot file.mpt --pw 0.01 3 --cd 0.2")
                    if len(data_files) > 1:
                        continue
                    else:
                        exit(1)
                # Import the potential-window (voltage-time to GC) reader
                b_tol = getattr(args, 'b', None)
                tol_upper = b_tol[0] if b_tol is not None and len(b_tol) >= 2 else 0.05
                tol_lower = b_tol[1] if b_tol is not None and len(b_tol) >= 2 else 0.005
                cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_batx_file(ec_file, v_min, v_max, current_density, tol_upper=tol_upper, tol_lower=tol_lower)
                x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
            # Branch by extension
            elif ec_file.lower().endswith('.mpt'):
                # If anode/cathode flags are set, try indexed voltage-time format first
                if getattr(args, 'anode', False) or getattr(args, 'cathode', False):
                    is_anode = bool(getattr(args, 'anode', False))
                    cd = getattr(args, 'cd', None)
                    cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_indexed_voltage_time_file(
                        ec_file,
                        is_anode=is_anode,
                        current_density=cd,
                    )
                    x_label_gc = r'Specific Capacity (mAh g$^{-1}$)' if cd is not None else "Relative Capacity (h)"
                else:
                    # For standard .mpt, mass is required to compute specific capacity
                    if mass_mg is None:
                        print("GC mode (.mpt): --mass parameter is required (active material mass in milligrams).")
                        print("Example: batplot file.mpt --gc --mass 7.0")
                        if len(data_files) > 1:
                            continue
                        else:
                            exit(1)
                    specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = cast(
                        Tuple[Any, Any, Any, Any, Any], read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg)
                    )
                    x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                    cap_x = specific_capacity
            elif ec_file.lower().endswith('.csv'):
                header = None
                if is_biologic_datalogger_csv(ec_file):
                    if mass_mg is None:
                        print("GC mode (Biologic DataLogger CSV): --mass parameter is required (active material mass in milligrams).")
                        print("Example: batplot file.csv --gc --mass 7.0")
                        if len(data_files) > 1:
                            continue
                        else:
                            exit(1)
                    cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_biologic_datalogger_csv(
                        ec_file, mass_mg=mass_mg
                    )
                else:
                    try:
                        header, _, _ = _load_csv_header_and_rows(ec_file)
                        if is_cs_b_format(header):
                            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_cs_b_csv_file(ec_file, mode='gc')
                        else:
                            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                    except Exception:
                        cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                # Decide whether we should treat cap_x as absolute or specific capacity.
                x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                # If the CSV only has absolute capacity and no specific capacity, rescale
                # using --mass (already resolved per file above).
                if header is not None:
                    header_stripped = [h.strip().replace('\t', '') for h in header]
                    has_spec = any('Spec. Cap.(mAh/g)' in h for h in header_stripped)
                    has_abs = any(h == 'Capacity(mAh)' for h in header_stripped)
                    if has_abs and not has_spec:
                        if mass_mg is not None and mass_mg > 0:
                            # Treat cap_x as absolute capacity (mAh) and rescale to mAh/g
                            cap_x = cap_x * (1000.0 / float(mass_mg))
                            x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                        else:
                            print(f"GC mode: {os.path.basename(ec_file)!r} contains only Capacity(mAh) with no specific-capacity column.")
                            print("         Pass --mass <mg> to plot specific capacity (mAh g^-1) instead of raw mAh.")
            else:
                print(f"GC mode: file must be .mpt or .csv: {ec_file}")
                if len(data_files) > 1:
                    continue
                else:
                    exit(1)

            # Create the plot
            fig, ax = plt.subplots(figsize=_default_ec_figsize())

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
                """Insert NaNs between non-consecutive indices so a single Line2D can represent disjoint segments."""
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
                # Concatenate with NaN separators
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
                # Normalize cycle indices to start at 1 (BioLogic may start at 0)
                # But first, identify cycles with sufficient data (>= 2 points) to be plotted
                cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
                if cyc_int_raw.size:
                    # Find the minimum cycle number that has at least 2 data points
                    unique_cycles_raw = np.unique(cyc_int_raw)
                    valid_min_c = None
                    for c in sorted(unique_cycles_raw):
                        if np.sum(cyc_int_raw == c) >= 2:
                            valid_min_c = int(c)
                            break
                    
                    if valid_min_c is not None:
                        # Shift so the first valid cycle becomes cycle 1
                        shift = 1 - valid_min_c
                    else:
                        # No valid cycles found, use original min
                        min_c = int(np.min(cyc_int_raw))
                        shift = 1 - min_c if min_c <= 0 else 0
                else:
                    shift = 0
                
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

            # Prepare colors
            base_colors = TAB10_HEX

            # Mapping: cycle_number -> {'charge': Line2D|None, 'discharge': Line2D|None}
            cycle_lines = {}

            if not inferred and cycle_numbers is not None:
                for cyc in cycles_present:
                    # Charge
                    mask_c = (cyc_int == cyc) & charge_mask
                    idx = np.where(mask_c)[0]
                    if idx.size >= 2:
                        x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                        # Label only once per cycle for legend: Cycle N
                        # Swap x and y if --ro flag is set
                        if getattr(args, 'ro', False):
                            ln_c, = ax.plot(y_b, x_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                            linewidth=2.0, label=str(cyc), alpha=0.8)
                        else:

                            ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                            linewidth=2.0, label=str(cyc), alpha=0.8)
                    else:
                        ln_c = None
                    # Discharge
                    mask_d = (cyc_int == cyc) & discharge_mask
                    idxd = np.where(mask_d)[0]
                    if idxd.size >= 2:
                        xd_b, yd_b = _broken_arrays_from_indices(idxd, cap_x, voltage)
                        # Use no legend entry for the second line of the same cycle
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
                # Infer cycles by alternating contiguous charge/discharge blocks
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
            # Labels with consistent labelpad
            # Swap axis labels if --ro flag is set
            if getattr(args, 'ro', False):
                ax.set_xlabel('Potential (V)', labelpad=8.0)
                ax.set_ylabel(x_label_gc, labelpad=8.0)
            else:
                ax.set_xlabel(x_label_gc, labelpad=8.0)
                ax.set_ylabel('Potential (V)', labelpad=8.0)
            legend = ax.legend(title='Cycle')
            if legend is not None:
                try:
                    legend.set_frame_on(False)
                except Exception:
                    pass
                legend.get_title().set_fontsize('medium')
            fig._ec_legend_title = "Cycle"
            # No background grid by default for GC plots
        
            # Adjust layout to ensure top and bottom labels/titles are visible
            _apply_default_ec_layout(fig)
            
            # Apply style file if provided
            if style_cfg:
                try:
                    _apply_ec_style(fig, ax, style_cfg)
                    # Redraw after applying style
                    fig.canvas.draw() if hasattr(fig, 'canvas') else None
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")

            # Save if requested
            if len(data_files) > 1 and (args.savefig or args.out):
                # Multiple files: save to Figures/ directory
                base_name = os.path.splitext(os.path.basename(ec_file))[0]
                output_format = getattr(args, 'format', 'svg')
                outname = os.path.join(out_dir or "", f"{base_name}.{output_format}")
            else:
                outname = args.savefig or args.out
            if outname:
                if not os.path.splitext(outname)[1]:
                    outname += '.svg'
                # Transparent background for SVG exports
                _, _ext = os.path.splitext(outname)
                if _ext.lower() == '.svg':
                    # Fix for Affinity Designer/Photo compatibility issues
                    # Use 'none' to embed fonts as text (not paths) - prevents phantom labels
                    # Set hashsalt to empty to avoid duplicate text elements
                    plt.rcParams['svg.fonttype'] = 'none'
                    plt.rcParams['svg.hashsalt'] = None
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
                print(f"GC plot saved to {outname} ({x_label_gc})")

            # Show plot / interactive menu
            if args.interactive:
                if require_interactive_display(args, context="GC interactive menu"):
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
                    show_figure_if_possible(args)
            # For multiple files, close the figure and continue to next file
            if len(data_files) > 1:
                plt.close(fig)
                continue
            else:
                exit()
        except Exception as _e:
            print(f"GC plot failed for {ec_file}: {_e}")
            if len(data_files) > 1:
                continue
            else:
                exit(1)
    # Exit after processing all files
    if len(data_files) > 1:
        print(f"Processed {len(data_files)} GC files.")
        exit()
    return 0


def handle_dqdv_mode(args) -> int:
    ensure_gui_backend(args)
    # Separate style files from data files
    data_files = []
    style_file_path = None
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            if style_file_path is None:
                style_file_path = f
            else:
                print(f"Warning: Multiple style files provided, using first: {style_file_path}")
        else:
            data_files.append(f)
    
    if not data_files:
        print("dQ/dV mode: no data files found (only style files provided).")
        exit(1)
    
    # Load style file if provided
    style_cfg = None
    if style_file_path:
        if not os.path.isfile(style_file_path):
            print(f"Warning: Style file not found: {style_file_path}")
        else:
            try:
                with open(style_file_path, 'r', encoding='utf-8') as f:
                    style_cfg = json.load(f)
                print(f"Using style file: {os.path.basename(style_file_path)}")
            except Exception as e:
                print(f"Warning: Could not load style file {style_file_path}: {e}")
    
    # Process each data file
    out_dir = None
    if len(data_files) > 1 and (args.savefig or args.out):
        # Multiple files: create output directory
        out_dir = ensure_subdirectory('Figures', os.getcwd())

    def _mask_segments(mask: np.ndarray, role: str):
        inds = np.where(mask)[0]
        if inds.size == 0:
            return []
        segs = []
        start, prev = inds[0], inds[0]
        for idx in inds[1:]:
            if idx == prev + 1:
                prev = idx
            else:
                segs.append((start, prev, role))
                start, prev = idx, idx
        segs.append((start, prev, role))
        return segs

    # dQ/dV multi-file: one figure with all files overlaid (same for interactive and non-interactive)
    if len(data_files) > 1:
        fig, ax = plt.subplots(figsize=_default_ec_figsize())
        ax._is_dqdv_mode = True
        file_data = []
        base_colors = TAB10_HEX
        y_label_used = None
        for file_idx, ec_file in enumerate(data_files):
            if not os.path.isfile(ec_file) or not (ec_file.lower().endswith('.csv') or ec_file.lower().endswith('.mpt')):
                continue
            try:
                _mf_mass = _resolve_mass(getattr(args, 'mass', None), file_idx)
                if ec_file.lower().endswith('.mpt'):
                    if _mf_mass is None or _mf_mass <= 0:
                        continue
                    voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_mpt_dqdv_file(ec_file, mass_mg=_mf_mass, prefer_specific=True)
                else:
                    _mf_dqdv_header = None
                    _mf_loaded = False
                    if is_biologic_datalogger_csv(ec_file):
                        if _mf_mass is None or _mf_mass <= 0:
                            continue
                        voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_biologic_datalogger_dqdv_file(
                            ec_file, mass_mg=_mf_mass, prefer_specific=True
                        )
                        _mf_loaded = True
                    else:
                        try:
                            _mf_dqdv_header, _, _ = _load_csv_header_and_rows(ec_file)
                        except Exception:
                            pass

                        if _mf_dqdv_header is not None and is_cs_b_format(_mf_dqdv_header):
                            voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_cs_b_csv_file(ec_file, mode='dqdv')
                            _mf_loaded = True

                        if not _mf_loaded:
                            try:
                                voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)
                                _mf_loaded = True
                            except ValueError:
                                pass

                        if not _mf_loaded:
                            _mf_gc_cap, _mf_gc_volt, _mf_gc_cyc, _mf_gc_chgm, _mf_gc_dchm = read_ec_csv_file(ec_file, prefer_specific=True)
                            if _mf_dqdv_header is not None:
                                _mf_hdrs = [h.strip().replace('\t', '') for h in _mf_dqdv_header]
                                _mf_has_spec = any('Spec. Cap.(mAh/g)' in h for h in _mf_hdrs)
                                _mf_has_abs = any(h == 'Capacity(mAh)' for h in _mf_hdrs)
                                if _mf_has_abs and not _mf_has_spec:
                                    if _mf_mass and _mf_mass > 0:
                                        _mf_gc_cap = _mf_gc_cap * (1000.0 / float(_mf_mass))
                                    else:
                                        print(f"dQ/dV mode: {os.path.basename(ec_file)!r} contains only Capacity(mAh) — pass --mass <mg>.")
                            voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = compute_dqdv_numerical(
                                _mf_gc_cap, _mf_gc_volt, _mf_gc_cyc, _mf_gc_chgm, _mf_gc_dchm
                            )
                            print(f"dQ/dV mode: computing numerically from GC data for {os.path.basename(ec_file)!r}.")
                if y_label_used is None:
                    y_label_used = y_label
                segments = _mask_segments(charge_mask, 'charge') + _mask_segments(discharge_mask, 'discharge')
                segments.sort(key=lambda x: x[0])
                cycle_lines = {}
                cycle_id = 1
                cycle_lines[cycle_id] = {"charge": None, "discharge": None}
                color_offset = (file_idx * 5) % len(base_colors)

                def _append_segment(line_obj, x_new, y_new):
                    try:
                        x_old = np.asarray(line_obj.get_xdata(), float)
                        y_old = np.asarray(line_obj.get_ydata(), float)
                        x_cat = np.concatenate([x_old, np.array([np.nan]), x_new])
                        y_cat = np.concatenate([y_old, np.array([np.nan]), y_new])
                        line_obj.set_xdata(x_cat)
                        line_obj.set_ydata(y_cat)
                    except Exception:
                        pass

                for start, end, role in segments:
                    if end - start + 1 < 2:
                        continue
                    idx = np.arange(start, end + 1)
                    x_seg, y_seg = voltage[idx], dqdv[idx]
                    current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                    color = base_colors[(color_offset + cycle_id - 1) % len(base_colors)]
                    first_seg = current['charge'] is None and current['discharge'] is None
                    if current[role] is not None:
                        if current['charge'] and current['discharge']:
                            cycle_id += 1
                            current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                        else:
                            if getattr(args, 'ro', False):
                                _append_segment(current[role], y_seg, x_seg)
                            else:
                                _append_segment(current[role], x_seg, y_seg)
                            continue
                    # Multi-file: label as "filename: cycle" so legend reflects data
                    file_lbl = os.path.basename(ec_file) if len(data_files) > 1 else ""
                    label = (f"{file_lbl}: {cycle_id}" if file_lbl else str(cycle_id)) if first_seg else '_nolegend_'
                    if getattr(args, 'ro', False):
                        ln, = ax.plot(y_seg, x_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                    else:
                        ln, = ax.plot(x_seg, y_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                    current[role] = ln
                    if current['charge'] and current['discharge']:
                        cycle_id += 1
                if cycle_lines.get(cycle_id) == {"charge": None, "discharge": None}:
                    cycle_lines.pop(cycle_id, None)
                file_data.append({
                    'filename': os.path.basename(ec_file),
                    'display_name': os.path.basename(ec_file),
                    'cycle_lines': cycle_lines,
                    'visible': True,
                    'filepath': ec_file,
                })
            except Exception as _e:
                print(f"dQ/dV multi-file: skip {ec_file}: {_e}")
        if not file_data:
            print("dQ/dV multi-file: no files loaded.")
            exit(1)
        if getattr(args, 'ro', False):
            ax.set_xlabel(y_label_used or 'dQ/dV', labelpad=8.0)
            ax.set_ylabel('Potential (V)', labelpad=8.0)
        else:
            ax.set_xlabel('Potential (V)', labelpad=8.0)
            ax.set_ylabel(y_label_used or 'dQ/dV', labelpad=8.0)
        ax.legend(title='Cycle')
        fig._ec_legend_title = "Cycle"
        _apply_default_ec_layout(fig)
        if style_cfg:
            try:
                _apply_ec_style(fig, ax, style_cfg)
                if hasattr(fig, 'canvas'):
                    fig.canvas.draw()
            except Exception as e:
                print(f"Warning: Error applying style file: {e}")
        try:
            plt.ion()
        except Exception:
            pass
        plt.show(block=False)
        try:
            fig._bp_source_paths = [os.path.abspath(f.get('filepath', '')) for f in file_data if f.get('filepath')]
        except Exception:
            pass
        if args.interactive:
            try:
                electrochem_interactive_menu(fig, ax, file_data=file_data)
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            plt.show()
        else:
            if out_dir and (args.savefig or getattr(args, 'out', None)):
                out_path = getattr(args, 'out', None)
                if not out_path:
                    ext = getattr(args, 'format', 'svg') or 'svg'
                    out_path = os.path.join(out_dir, f'dQdV_combined.{ext}')
                try:
                    fig.savefig(out_path, dpi=300, bbox_inches='tight')
                    print(f"Saved {out_path}")
                except Exception as e:
                    print(f"Could not save: {e}")
            try:
                plt.ioff()
            except Exception:
                pass
            print(f"Processed {len(file_data)} dQ/dV files.")
            plt.show(block=True)
        exit(0)

    for _dqdv_file_idx, ec_file in enumerate(data_files):
        if not os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            continue
        if not (ec_file.lower().endswith('.csv') or ec_file.lower().endswith('.mpt')):
            print(f"dQ/dV mode: file must be a supported cycler .csv or .mpt export: {ec_file}")
            continue
        
        try:
            _dqdv_mass = _resolve_mass(getattr(args, 'mass', None), _dqdv_file_idx)
            # Load voltage, dQ/dV, cycles, and charge/discharge masks
            if ec_file.lower().endswith('.mpt'):
                # .mpt files require mass for dQ/dV calculation
                if _dqdv_mass is None or _dqdv_mass <= 0:
                    print(f"dQ/dV mode (.mpt): --mass parameter is required (active material mass in milligrams).")
                    print(f"Example: batplot {ec_file} --dqdv --mass 7.0")
                    continue
                voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_mpt_dqdv_file(ec_file, mass_mg=_dqdv_mass, prefer_specific=True)
            else:
                # Load header for format detection and mass-scaling check
                _dqdv_header = None
                _loaded_dqdv = False
                if is_biologic_datalogger_csv(ec_file):
                    if _dqdv_mass is None or _dqdv_mass <= 0:
                        print(f"dQ/dV mode (Biologic DataLogger CSV): --mass parameter is required.")
                        print(f"Example: batplot {ec_file} --dqdv --mass 7.0")
                        continue
                    voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_biologic_datalogger_dqdv_file(
                        ec_file, mass_mg=_dqdv_mass, prefer_specific=True
                    )
                    _loaded_dqdv = True
                else:
                    try:
                        _dqdv_header, _, _ = _load_csv_header_and_rows(ec_file)
                    except Exception:
                        pass

                    if _dqdv_header is not None and is_cs_b_format(_dqdv_header):
                        voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_cs_b_csv_file(ec_file, mode='dqdv')
                        _loaded_dqdv = True

                if not _loaded_dqdv:
                    try:
                        voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)
                        _loaded_dqdv = True
                    except ValueError:
                        pass  # No dQ/dV columns — fall through to numerical computation

                if not _loaded_dqdv:
                    # Numerical dQ/dV from GC data (for files with no pre-calculated dQ/dV column)
                    _gc_cap, _gc_volt, _gc_cyc, _gc_chgm, _gc_dchm = read_ec_csv_file(ec_file, prefer_specific=True)
                    if _dqdv_header is not None:
                        _hdrs_dqdv = [h.strip().replace('\t', '') for h in _dqdv_header]
                        _has_spec_dqdv = any('Spec. Cap.(mAh/g)' in h for h in _hdrs_dqdv)
                        _has_abs_dqdv = any(h == 'Capacity(mAh)' for h in _hdrs_dqdv)
                        if _has_abs_dqdv and not _has_spec_dqdv:
                            if _dqdv_mass and _dqdv_mass > 0:
                                _gc_cap = _gc_cap * (1000.0 / float(_dqdv_mass))
                            else:
                                print(f"dQ/dV mode: {os.path.basename(ec_file)!r} contains only Capacity(mAh) — pass --mass <mg> for specific dQ/dV.")
                    voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = compute_dqdv_numerical(
                        _gc_cap, _gc_volt, _gc_cyc, _gc_chgm, _gc_dchm
                    )
                    print(f"dQ/dV mode: no dQ/dV column found — computing numerically from GC data for {os.path.basename(ec_file)!r}.")

            # Create the plot
            fig, ax = plt.subplots(figsize=_default_ec_figsize())

            segments = _mask_segments(charge_mask, 'charge') + _mask_segments(discharge_mask, 'discharge')
            segments.sort(key=lambda item: item[0])

            base_colors = TAB10_HEX

            cycle_lines = {}
            ax._is_dqdv_mode = True
            cycle_id = 1
            cycle_lines[cycle_id] = {"charge": None, "discharge": None}

            def _append_segment(line_obj, x_new, y_new):
                try:
                    x_old = np.asarray(line_obj.get_xdata(), float)
                    y_old = np.asarray(line_obj.get_ydata(), float)
                    x_cat = np.concatenate([x_old, np.array([np.nan]), x_new])
                    y_cat = np.concatenate([y_old, np.array([np.nan]), y_new])
                    line_obj.set_xdata(x_cat)
                    line_obj.set_ydata(y_cat)
                except Exception:
                    pass

            for start, end, role in segments:
                if end - start + 1 < 2:
                    continue
                idx = np.arange(start, end + 1)
                x_seg = voltage[idx]
                y_seg = dqdv[idx]
                current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                color = base_colors[(cycle_id - 1) % len(base_colors)]
                first_segment = current['charge'] is None and current['discharge'] is None

                if current[role] is not None:
                    if current['charge'] is not None and current['discharge'] is not None:
                        cycle_id += 1
                        current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                    else:
                        # Swap x and y if --ro flag is set when appending segment
                        if getattr(args, 'ro', False):
                            _append_segment(current[role], y_seg, x_seg)
                        else:
                            _append_segment(current[role], x_seg, y_seg)
                        continue

                label = str(cycle_id) if first_segment else '_nolegend_'
                # Swap x and y if --ro flag is set
                if getattr(args, 'ro', False):
                    ln, = ax.plot(y_seg, x_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                else:
                    ln, = ax.plot(x_seg, y_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                current[role] = ln

                if current['charge'] is not None and current['discharge'] is not None:
                    cycle_id += 1

            if cycle_lines.get(cycle_id) == {"charge": None, "discharge": None}:
                cycle_lines.pop(cycle_id, None)

            # Labels with consistent labelpad (same as GC/CPC)
            # Swap axis labels if --ro flag is set
            if getattr(args, 'ro', False):
                ax.set_xlabel(y_label, labelpad=8.0)
                ax.set_ylabel('Potential (V)', labelpad=8.0)
            else:

                ax.set_xlabel('Potential (V)', labelpad=8.0)
            ax.set_ylabel(y_label, labelpad=8.0)
            legend = ax.legend(title='Cycle')
            if legend is not None:
                try:
                    legend.set_frame_on(False)
                except Exception:
                    pass
                legend.get_title().set_fontsize('medium')
            fig._ec_legend_title = "Cycle"
            # No background grid by default (same as GC)
        
            # Adjust layout to ensure top and bottom labels/titles are visible (same as GC/CPC)
            _apply_default_ec_layout(fig)
            
            # Apply style file if provided
            if style_cfg:
                try:
                    _apply_ec_style(fig, ax, style_cfg)
                    # Redraw after applying style
                    if hasattr(fig, 'canvas'):
                        fig.canvas.draw()
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")

            # Save if requested
            if len(data_files) > 1 and (args.savefig or args.out):
                # Multiple files: save to Figures/ directory
                base_name = os.path.splitext(os.path.basename(ec_file))[0]
                output_format = getattr(args, 'format', 'svg')
                outname = os.path.join(out_dir or "", f"{base_name}.{output_format}")
            else:
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
                print(f"dQ/dV plot saved to {outname} ({y_label})")

            # Show / interactive
            if args.interactive:
                if require_interactive_display(args, context="dQ/dV interactive menu"):
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
                    show_figure_if_possible(args)
            # For multiple files, close the figure and continue to next file
            if len(data_files) > 1:
                plt.close(fig)
                continue
            else:
                exit()
        except Exception as _e:
            print(f"dQ/dV plot failed for {ec_file}: {_e}")
            if len(data_files) > 1:
                continue
            else:
                exit(1)
    # Exit after processing all files
    if len(data_files) > 1:
        print(f"Processed {len(data_files)} dQ/dV files.")
        exit(0)
    return 0


def handle_cv_mode(args) -> int:
    """
    Handle CV mode plotting and routing.
    Returns an integer exit code (0 for success, non-zero for error).
    """
    ensure_gui_backend(args)
    # Separate style files from data files
    data_files = []
    style_file_path = None
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            if style_file_path is None:
                style_file_path = f
            else:
                print(f"Warning: Multiple style files provided, using first: {style_file_path}")
        else:
            data_files.append(f)

    if not data_files:
        print("CV mode: no data files found (only style files provided).")
        return 1

    # Load style file if provided
    style_cfg = None
    if style_file_path:
        if not os.path.isfile(style_file_path):
            print(f"Warning: Style file not found: {style_file_path}")
        else:
            try:
                with open(style_file_path, 'r', encoding='utf-8') as f:
                    style_cfg = json.load(f)
                print(f"Using style file: {os.path.basename(style_file_path)}")
            except Exception as e:
                print(f"Warning: Could not load style file {style_file_path}: {e}")

    # Process each data file
    out_dir = None
    if len(data_files) > 1 and (args.savefig or args.out):
        # Multiple files: create output directory
        out_dir = ensure_subdirectory('Figures', os.getcwd())

    # CV multi-file combined mode: one figure with all files overlaid (like GC/dQ/dV)
    if len(data_files) > 1:
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
            'mathtext.fontset': 'dejavusans',
            'font.size': 16
        })
        fig, ax = plt.subplots(figsize=_default_ec_figsize())
        file_data = []
        base_colors = TAB10_HEX
        for file_idx, ec_file in enumerate(data_files):
            if not os.path.isfile(ec_file) or not (ec_file.lower().endswith('.mpt') or ec_file.lower().endswith('.txt')):
                continue
            try:
                if ec_file.lower().endswith('.txt'):
                    voltage, current, cycles = read_biologic_txt_file(ec_file, mode='cv')
                else:
                    mpt_result = read_mpt_file(ec_file, mode='cv')
                    voltage = mpt_result[0]
                    current = mpt_result[1]
                    cycles = mpt_result[2]
                if cycles is None:
                    continue
                cyc_int_raw = np.array(np.rint(cycles), dtype=int)
                if cyc_int_raw.size:
                    unique_cycles_raw = np.unique(cyc_int_raw)
                    valid_min_c = None
                    for c in sorted(unique_cycles_raw):
                        if np.sum(cyc_int_raw == c) >= 2:
                            valid_min_c = int(c)
                            break
                    if valid_min_c is not None:
                        shift = 1 - valid_min_c
                    else:
                        min_c = int(np.min(cyc_int_raw))
                        shift = 1 - min_c if min_c <= 0 else 0
                else:
                    shift = 0
                cyc_int = cyc_int_raw + shift
                cycles_present = sorted(int(c) for c in np.unique(cyc_int)) if cyc_int.size else [1]
                color = base_colors[file_idx % len(base_colors)]
                cycle_lines = {}
                file_lbl = os.path.basename(ec_file)
                for cyc in cycles_present:
                    mask = (cyc_int == cyc)
                    idx = np.where(mask)[0]
                    if idx.size >= 2:
                        parts_x, parts_y = [], []
                        start = 0
                        for k in range(1, idx.size):
                            if idx[k] != idx[k - 1] + 1:
                                parts_x.append(voltage[idx[start:k]])
                                parts_y.append(current[idx[start:k]])
                                start = k
                        parts_x.append(voltage[idx[start:]])
                        parts_y.append(current[idx[start:]])
                        X, Y = [], []
                        for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                            if i > 0:
                                X.append(np.array([np.nan]))
                                Y.append(np.array([np.nan]))
                            X.append(px)
                            Y.append(py)
                        x_b = np.concatenate(X) if X else np.array([])
                        y_b = np.concatenate(Y) if Y else np.array([])
                        label = f"{file_lbl}: {cyc}" if file_lbl else str(cyc)
                        if getattr(args, 'ro', False):
                            ln, = ax.plot(y_b, x_b, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                        else:
                            ln, = ax.plot(x_b, y_b, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                        cycle_lines[cyc] = ln
                file_data.append({
                    'filename': os.path.basename(ec_file),
                    'display_name': os.path.basename(ec_file),
                    'cycle_lines': cycle_lines,
                    'visible': True,
                    'filepath': ec_file,
                })
            except Exception as _e:
                print(f"CV multi-file: skip {ec_file}: {_e}")
        if not file_data:
            print("CV multi-file: no files loaded.")
            return 1
        if getattr(args, 'ro', False):
            ax.set_xlabel('Current (mA)', labelpad=8.0)
            ax.set_ylabel('Potential (V)', labelpad=8.0)
        else:
            ax.set_xlabel('Potential (V)', labelpad=8.0)
            ax.set_ylabel('Current (mA)', labelpad=8.0)
        ax.legend(title='Cycle')
        fig._ec_legend_title = "Cycle"
        _apply_default_ec_layout(fig)
        if style_cfg:
            try:
                _apply_ec_style(fig, ax, style_cfg)
                if hasattr(fig, 'canvas'):
                    fig.canvas.draw()
            except Exception as e:
                print(f"Warning: Error applying style file: {e}")
        try:
            plt.ion()
        except Exception:
            pass
        plt.show(block=False)
        try:
            fig._ro_active = bool(getattr(args, "ro", False))
        except Exception:
            pass
        try:
            fig._bp_source_paths = [os.path.abspath(f.get('filepath', '')) for f in file_data if f.get('filepath')]
        except Exception:
            pass
        if args.interactive:
            try:
                electrochem_interactive_menu(fig, ax, file_data=file_data)
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            plt.show()
        else:
            if out_dir and (args.savefig or getattr(args, 'out', None)):
                out_path = getattr(args, 'out', None)
                if not out_path:
                    ext = getattr(args, 'format', 'svg') or 'svg'
                    out_path = os.path.join(out_dir, f'CV_combined.{ext}')
                try:
                    fig.savefig(out_path, dpi=300, bbox_inches='tight')
                    print(f"Saved {out_path}")
                except Exception as e:
                    print(f"Could not save: {e}")
            try:
                plt.ioff()
            except Exception:
                pass
            print(f"Processed {len(file_data)} CV files.")
            plt.show(block=True)
        return 0

    for ec_file in data_files:
        if not os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            if len(data_files) > 1:
                continue
            return 1
        try:
            # Support both .mpt and .txt formats
            if ec_file.lower().endswith('.txt'):
                voltage, current, cycles = read_biologic_txt_file(ec_file, mode='cv')
            else:
                # read_mpt_file can return different tuple sizes depending on mode;
                # in CV mode we only use the first three elements (voltage, current, cycles).
                mpt_result = read_mpt_file(ec_file, mode='cv')
                voltage = mpt_result[0]
                current = mpt_result[1]
                cycles = mpt_result[2]
            if cycles is None:
                continue
            # Normalize cycle indices to start at 1
            # Find the first cycle with at least 2 data points (needed for plotting)
            cyc_int_raw = np.array(np.rint(cycles), dtype=int)
            if cyc_int_raw.size:
                unique_cycles_raw = np.unique(cyc_int_raw)
                valid_min_c = None
                for c in sorted(unique_cycles_raw):
                    if np.sum(cyc_int_raw == c) >= 2:
                        valid_min_c = int(c)
                        break

                if valid_min_c is not None:
                    shift = 1 - valid_min_c
                else:
                    min_c = int(np.min(cyc_int_raw))
                    shift = 1 - min_c if min_c <= 0 else 0
            else:
                shift = 0
            cyc_int = cyc_int_raw + shift
            cycles_present = sorted(int(c) for c in np.unique(cyc_int)) if cyc_int.size else [1]
            # Color palette
            base_colors = TAB10_HEX
            # Ensure font and canvas settings match GC/dQdV
            plt.rcParams.update({
                'font.family': 'sans-serif',
                # Prefer DejaVu Sans first because it has good Unicode
                # coverage (including subscript/superscript digits), then
                # fall back to other common sans-serif fonts.
                'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
                'mathtext.fontset': 'dejavusans',
                'font.size': 16
            })
            fig, ax = plt.subplots(figsize=_default_ec_figsize())
            cycle_lines = {}
            for cyc in cycles_present:
                mask = (cyc_int == cyc)
                idx = np.where(mask)[0]
                if idx.size >= 2:
                    # Insert NaNs between non-consecutive indices for proper cycle breaks
                    parts_x = []
                    parts_y = []
                    start = 0
                    for k in range(1, idx.size):
                        if idx[k] != idx[k-1] + 1:
                            parts_x.append(voltage[idx[start:k]])
                            parts_y.append(current[idx[start:k]])
                            start = k
                    parts_x.append(voltage[idx[start:]])
                    parts_y.append(current[idx[start:]])
                    X = []
                    Y = []
                    for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                        if i > 0:
                            X.append(np.array([np.nan]))
                            Y.append(np.array([np.nan]))
                        X.append(px)
                        Y.append(py)
                    x_b = np.concatenate(X) if X else np.array([])
                    y_b = np.concatenate(Y) if Y else np.array([])
                    ln, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                  linewidth=2.0, label=str(cyc), alpha=0.8)
                    cycle_lines[cyc] = ln
            # Swap axis labels if --ro flag is set
            if getattr(args, 'ro', False):
                ax.set_xlabel('Current (mA)', labelpad=8.0)
                ax.set_ylabel('Potential (V)', labelpad=8.0)
            else:
                ax.set_xlabel('Potential (V)', labelpad=8.0)
                ax.set_ylabel('Current (mA)', labelpad=8.0)
            legend = ax.legend(title='Cycle')
            if legend is not None:
                try:
                    legend.set_frame_on(False)
                except Exception:
                    pass
                legend.get_title().set_fontsize('medium')
            fig._ec_legend_title = "Cycle"
            # Match GC/dQdV: consistent label/title displacement and canvas
            _apply_default_ec_layout(fig)

            # Apply style file if provided
            if style_cfg:
                try:
                    _apply_ec_style(fig, ax, style_cfg)
                    # Redraw after applying style
                    if hasattr(fig, 'canvas'):
                        fig.canvas.draw()
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")

            # Save if requested
            if len(data_files) > 1 and (args.savefig or args.out):
                # Multiple files: save to Figures/ directory
                base_name = os.path.splitext(os.path.basename(ec_file))[0]
                output_format = getattr(args, 'format', 'svg')
                outname = os.path.join(out_dir or "", f"{base_name}.{output_format}")
                try:
                    _, _ext = os.path.splitext(outname)
                    if _ext.lower() == '.svg':
                        plt.rcParams['svg.fonttype'] = 'none'
                        plt.rcParams['svg.hashsalt'] = None
                    fig.savefig(outname, dpi=300, transparent=True if _ext.lower() == '.svg' else False)
                    print(f"CV plot saved to {outname}")
                except Exception as e:
                    print(f"Warning: Could not save CV plot: {e}")

            # Interactive menu: use electrochem_interactive_menu for consistency with GC
            if args.interactive:
                if require_interactive_display(args, context="CV interactive menu"):
                    try:
                        plt.ion()
                    except Exception:
                        pass
                    plt.show(block=False)
                    try:
                        fig._ro_active = bool(getattr(args, "ro", False))
                    except Exception:
                        pass
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
                    show_figure_if_possible(args)
                # For multiple files, close the figure and continue to next file
                if len(data_files) > 1:
                    plt.close(fig)
                    continue
                return 0
        except Exception as e:
            print(f"CV plot failed for {ec_file}: {e}")
            if len(data_files) > 1:
                continue
            return 1

    # Exit after processing all files
    if len(data_files) > 1:
        print(f"Processed {len(data_files)} CV files.")
        return 0

    return 0
