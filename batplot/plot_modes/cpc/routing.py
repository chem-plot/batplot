"""Top-level routing handler for capacity-per-cycle (CPC / EPC) mode.

Extracted verbatim from ``batplot.batplot.batplot_main`` so the dispatcher
stays lean. :func:`handle_cpc_mode` owns the ``--cpc`` / ``--epc`` route
(capacity / energy per cycle with coulombic efficiency) and terminates the
process via ``exit()`` once its work is done.

Shared electrochem layout / mass helpers come from
:mod:`batplot.ec_common` to avoid a circular dependency back to
:mod:`batplot.batplot`.
"""

from __future__ import annotations

import os
import json
from typing import Tuple, cast

import numpy as np  # type: ignore
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.colors as mcolors  # type: ignore[import-untyped]

from ...color_utils import get_colormap

from ...ec_common import (
    _resolve_mass,
    _default_ec_figsize,
    _apply_default_ec_layout,
)
from ..._mpl_backend import (
    ensure_gui_backend,
    hold_figure_open,
    prime_interactive_figure,
    require_interactive_display,
    show_figure_if_possible,
)
from ...batch import _apply_ec_style
from ...readers import (
    read_mpt_file,
    read_ec_csv_file,
    read_cs_b_csv_file,
    is_cs_b_format,
    _load_csv_header_and_rows,
)
from ..common.palettes import TAB10_HEX

try:
    from .interactive import cpc_interactive_menu, _build_compact_cpc_legend
except ImportError:
    cpc_interactive_menu = None
    _build_compact_cpc_legend = None


def handle_cpc_mode(args) -> int:
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
    
    if len(data_files) < 1:
        print("CPC mode: provide at least one file (.csv, .xlsx, or .mpt).")
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
    
    is_epc = bool(getattr(args, 'epc', False))
    # Process multiple files
    file_data = []  # List of dicts with file info and data
    # Use tab10 for capacity and viridis for efficiency
    n_files = len(data_files)
    
    if n_files <= 1:
        capacity_colors = [TAB10_HEX[0]]
        eff_positions = [0.55]
    else:
        capacity_colors = [TAB10_HEX[i % len(TAB10_HEX)] for i in range(n_files)]
        eff_positions = np.linspace(0.08, 0.88, n_files)
    
    # Use viridis for efficiency
    efficiency_cmap = get_colormap('viridis')
    if efficiency_cmap is None:
        print("Could not load viridis colormap.")
        exit(1)
    efficiency_colors = [mcolors.rgb2hex(efficiency_cmap(pos)[:3]) for pos in eff_positions]
    
    for file_idx, ec_file in enumerate(data_files):
        if not os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            continue

        ext = os.path.splitext(ec_file)[1].lower()
        file_basename = os.path.basename(ec_file)
        
        try:
            mass_mg = _resolve_mass(getattr(args, 'mass', None), file_idx)
            if ext in ['.csv', '.xlsx', '.xls']:
                # For EPC, prefer explicit per-point energy-density columns if available;
                # otherwise, fall back to integrating V vs capacity.
                if not is_epc:
                    _cpc_header = None
                    try:
                        _cpc_header, _, _ = _load_csv_header_and_rows(ec_file)
                    except Exception:
                        pass
                    if _cpc_header is not None and is_cs_b_format(_cpc_header):
                        cyc_nums, cap_charge, cap_discharge, eff = read_cs_b_csv_file(ec_file, mode='cpc')
                    else:
                        cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                        # Apply mass scaling when file only has absolute capacity (mAh)
                        _cpc_mass = mass_mg
                        if _cpc_header is not None:
                            _cpc_hdr_s = [h.strip().replace('\t', '') for h in _cpc_header]
                            _has_spec = any('Spec. Cap.(mAh/g)' in h for h in _cpc_hdr_s)
                            _has_abs = any(h == 'Capacity(mAh)' for h in _cpc_hdr_s)
                            if _has_abs and not _has_spec:
                                if _cpc_mass is not None and _cpc_mass > 0:
                                    cap_x = cap_x * (1000.0 / float(_cpc_mass))
                                else:
                                    print(f"CPC mode: {file_basename!r} contains only Capacity(mAh) — pass --mass <mg> for specific capacity.")
                        cyc = np.array(cycles, dtype=int)
                        unique_cycles = np.unique(cyc)
                        unique_cycles = unique_cycles[np.isfinite(unique_cycles)]
                        unique_cycles = [int(x) for x in unique_cycles] or [1]
                        cyc_nums = []
                        cap_charge = []
                        cap_discharge = []
                        eff = []
                        for c in sorted(unique_cycles):
                            m_c = (cyc == c)
                            qchg = np.nanmax(cap_x[m_c & chg_mask]) if np.any(m_c & chg_mask) else np.nan
                            qdch = np.nanmax(cap_x[m_c & dchg_mask]) if np.any(m_c & dchg_mask) else np.nan
                            # Efficiency from capacity ratio (no explicit efficiency column)
                            eta = (qdch / qchg * 100.0) if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch)) else np.nan
                            cyc_nums.append(c)
                            cap_charge.append(qchg)
                            cap_discharge.append(qdch)
                            eff.append(eta)
                        cyc_nums = np.array(cyc_nums, dtype=float)
                        cap_charge = np.array(cap_charge, dtype=float)
                        cap_discharge = np.array(cap_discharge, dtype=float)
                        eff = np.array(eff, dtype=float)
                else:
                    header, rows, _ = _load_csv_header_and_rows(ec_file)
                    # Check for explicit energy-density columns
                    header_stripped = [h.strip().replace('\t', '') for h in header]
                    has_chg_en = any('Chg. Spec. Energy(mWh/g)' in h for h in header_stripped)
                    has_dch_en = any('DChg. Spec. Energy(mWh/g)' in h for h in header_stripped)
                    has_en = any('Spec. Energy(mWh/g)' in h for h in header_stripped)
                    if has_chg_en or has_dch_en or has_en:
                        # Use the existing GC parsing to get cycles and masks
                        cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                        cyc = np.array(cycles, dtype=int)
                        unique_cycles = np.unique(cyc)
                        unique_cycles = unique_cycles[np.isfinite(unique_cycles)]
                        unique_cycles = [int(x) for x in unique_cycles] or [1]
                        # Build name->index map
                        name_to_idx = {h.strip().replace('\t', ''): i for i, h in enumerate(header)}
                        def _idx(name: str):
                            return name_to_idx.get(name, None)
                        idx_chg_en = _idx('Chg. Spec. Energy(mWh/g)')
                        idx_dch_en = _idx('DChg. Spec. Energy(mWh/g)')
                        idx_en = _idx('Spec. Energy(mWh/g)')
                        # Extract per-point energy arrays
                        def _col(idx):
                            if idx is None:
                                return None
                            vals = []
                            for row in rows:
                                if idx < len(row):
                                    val = row[idx]
                                else:
                                    val = ''
                                try:
                                    vals.append(float(str(val).strip() or 'nan'))
                                except Exception:
                                    vals.append(float('nan'))
                            return np.array(vals, dtype=float)
                        en_chg = _col(idx_chg_en)
                        en_dch = _col(idx_dch_en)
                        en_any = _col(idx_en)
                        cyc_nums = []
                        cap_charge = []
                        cap_discharge = []
                        eff = []
                        for c in sorted(unique_cycles):
                            m_c = (cyc == c)
                            mask_c = m_c & chg_mask
                            mask_d = m_c & dchg_mask
                            # Prefer charge/discharge-specific energy columns; fall back to generic Spec. Energy if needed
                            if en_chg is not None:
                                e_c = float(np.nanmax(en_chg[mask_c])) if np.any(mask_c) else float('nan')
                            elif en_any is not None:
                                e_c = float(np.nanmax(en_any[mask_c])) if np.any(mask_c) else float('nan')
                            else:
                                e_c = float('nan')
                            if en_dch is not None:
                                e_d = float(np.nanmax(en_dch[mask_d])) if np.any(mask_d) else float('nan')
                            elif en_any is not None:
                                e_d = float(np.nanmax(en_any[mask_d])) if np.any(mask_d) else float('nan')
                            else:
                                e_d = float('nan')
                            # Efficiency still based on capacity
                            qchg = np.nanmax(cap_x[mask_c]) if np.any(mask_c) else np.nan
                            qdch = np.nanmax(cap_x[mask_d]) if np.any(mask_d) else np.nan
                            eta = (qdch / qchg * 100.0) if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch)) else np.nan
                            cyc_nums.append(c)
                            cap_charge.append(e_c)
                            cap_discharge.append(e_d)
                            eff.append(eta)
                        print(f"EPC mode: using Spec. Energy(mWh/g) columns from {file_basename!r} (no numerical integration).")
                        cyc_nums = np.array(cyc_nums, dtype=float)
                        cap_charge = np.array(cap_charge, dtype=float)
                        cap_discharge = np.array(cap_discharge, dtype=float)
                        eff = np.array(eff, dtype=float)
                    else:
                        # Fallback: compute energy density by integrating V vs capacity
                        cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                        # Apply mass scaling when file only has absolute capacity (mAh),
                        # so that ∫V dQ yields mWh/g instead of mWh
                        _epc_mass = mass_mg
                        _epc_hdr_s = header_stripped  # already built above
                        _epc_has_spec = any('Spec. Cap.(mAh/g)' in h for h in _epc_hdr_s)
                        _epc_has_abs = any(h == 'Capacity(mAh)' for h in _epc_hdr_s)
                        if _epc_has_abs and not _epc_has_spec:
                            if _epc_mass is not None and _epc_mass > 0:
                                cap_x = cap_x * (1000.0 / float(_epc_mass))
                            else:
                                print(f"EPC mode: {file_basename!r} contains only Capacity(mAh) — pass --mass <mg> for specific energy (mWh/g).")
                        cyc = np.array(cycles, dtype=int)
                        unique_cycles = np.unique(cyc)
                        unique_cycles = unique_cycles[np.isfinite(unique_cycles)]
                        unique_cycles = [int(x) for x in unique_cycles] or [1]
                        cyc_nums = []
                        cap_charge = []
                        cap_discharge = []
                        eff = []
                        for c in sorted(unique_cycles):
                            m_c = (cyc == c)
                            mask_c = m_c & chg_mask
                            mask_d = m_c & dchg_mask
                            if np.count_nonzero(mask_c) >= 2:
                                e_c = float((getattr(np, "trapezoid", None) or np.trapz)(voltage[mask_c], cap_x[mask_c]))
                            else:
                                e_c = np.nan
                            if np.count_nonzero(mask_d) >= 2:
                                e_d = float((getattr(np, "trapezoid", None) or np.trapz)(voltage[mask_d], cap_x[mask_d]))
                            else:
                                e_d = np.nan
                            qchg = np.nanmax(cap_x[mask_c]) if np.any(mask_c) else np.nan
                            qdch = np.nanmax(cap_x[mask_d]) if np.any(mask_d) else np.nan
                            eta = (qdch / qchg * 100.0) if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch)) else np.nan
                            cyc_nums.append(c)
                            cap_charge.append(e_c)
                            cap_discharge.append(e_d)
                            eff.append(eta)
                        print(f"EPC mode: computing energy density by integrating V vs capacity for {file_basename!r}.")
                        cyc_nums = np.array(cyc_nums, dtype=float)
                        cap_charge = np.array(cap_charge, dtype=float)
                        cap_discharge = np.array(cap_discharge, dtype=float)
                        eff = np.array(eff, dtype=float)
            elif ext == '.mpt':
                if mass_mg is None:
                    mode_name = "EPC" if is_epc else "CPC"
                    print(f"Skipped {file_basename}: {mode_name} mode (.mpt) requires --mass parameter.")
                    continue
                if is_epc:
                    cap_x, voltage, cycles, chg_mask, dchg_mask = cast(
                        Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
                        read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg),
                    )
                    cyc = np.array(cycles, dtype=int)
                    unique_cycles = np.unique(cyc)
                    unique_cycles = unique_cycles[np.isfinite(unique_cycles)]
                    unique_cycles = [int(x) for x in unique_cycles] or [1]
                    cyc_nums = []
                    cap_charge = []
                    cap_discharge = []
                    eff = []
                    for c in sorted(unique_cycles):
                        m_c = (cyc == c)
                        mask_c = m_c & chg_mask
                        mask_d = m_c & dchg_mask
                        if np.count_nonzero(mask_c) >= 2:
                            e_c = float((getattr(np, "trapezoid", None) or np.trapz)(voltage[mask_c], cap_x[mask_c]))
                        else:
                            e_c = np.nan
                        if np.count_nonzero(mask_d) >= 2:
                            e_d = float((getattr(np, "trapezoid", None) or np.trapz)(voltage[mask_d], cap_x[mask_d]))
                        else:
                            e_d = np.nan
                        qchg = np.nanmax(cap_x[mask_c]) if np.any(mask_c) else np.nan
                        qdch = np.nanmax(cap_x[mask_d]) if np.any(mask_d) else np.nan
                        eta = (qdch / qchg * 100.0) if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch)) else np.nan
                        cyc_nums.append(c)
                        cap_charge.append(e_c)
                        cap_discharge.append(e_d)
                        eff.append(eta)
                    cyc_nums = np.array(cyc_nums, dtype=float)
                    cap_charge = np.array(cap_charge, dtype=float)
                    cap_discharge = np.array(cap_discharge, dtype=float)
                    eff = np.array(eff, dtype=float)
                else:
                    cyc_nums, cap_charge, cap_discharge, eff = cast(
                        Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
                        read_mpt_file(ec_file, mode='cpc', mass_mg=mass_mg),
                    )
            else:
                print(f"Skipped {file_basename}: unsupported format (must be .csv, .xlsx, or .mpt)")
                continue
            
            # Assign colors: distinct hue per file
            capacity_color = capacity_colors[file_idx % len(capacity_colors)]
            efficiency_color = efficiency_colors[file_idx % len(efficiency_colors)]
            
            file_data.append({
                'filename': file_basename,
                'filepath': ec_file,
                'cyc_nums': cyc_nums,
                'cap_charge': cap_charge,
                'cap_discharge': cap_discharge,
                'eff': eff,
                'color': capacity_color,
                'eff_color': efficiency_color,
                'visible': True
            })
            
        except Exception as e:
            print(f"Failed to read {file_basename}: {e}")
            continue
    
    if not file_data:
        print("No valid CPC data files to plot.")
        exit(1)

    # Plot (same canvas and frame size as GC/CV/dQ/dV)
    fig, ax = plt.subplots(figsize=_default_ec_figsize())
    ax.set_xlabel('Cycle number', labelpad=8.0)
    if is_epc:
        ax.set_ylabel(r'Specific Energy (mWh g$^{-1}$)', labelpad=8.0)
    else:
        ax.set_ylabel(r'Specific Capacity (mAh g$^{-1}$)', labelpad=8.0)
    ax.grid(True, alpha=0.25, linestyle='--', linewidth=0.8)

    ax2 = ax.twinx()
    ax2.set_ylabel('Efficiency (%)', labelpad=8.0)
    
    # Create scatter plots for each file
    for file_info in file_data:
        cyc_nums = file_info['cyc_nums']
        cap_charge = file_info['cap_charge']
        cap_discharge = file_info['cap_discharge']
        eff = file_info['eff']
        color = file_info['color']  # Base color for capacity (both charge/discharge)
        eff_color = file_info['eff_color']  # Cold color for efficiency
        label = file_info['filename']
        
        # For single file, use simple labels; for multiple files, prefix with filename
        if len(file_data) == 1:
            if is_epc:
                label_chg = 'Charge energy density'
                label_dch = 'Discharge energy density'
            else:
                label_chg = 'Charge capacity'
                label_dch = 'Discharge capacity'
            label_eff = 'Coulombic efficiency'
        else:
            # Keep compact suffix labels; underlying quantity is determined by Y-axis label
            label_chg = f'{label} (Chg)'
            label_dch = f'{label} (Dch)'
            label_eff = f'{label} (Eff)'
        
        # Capacity curves: same color, different fill style
        # - Charge: filled square
        # - Discharge: hollow square (edge only)
        sc_charge = ax.scatter(
            cyc_nums,
            cap_charge,
            label=label_chg,
            s=32,
            zorder=3,
            alpha=0.8,
            marker='s',
            color=color,
        )
        sc_discharge = ax.scatter(
            cyc_nums,
            cap_discharge,
            label=label_dch,
            s=32,
            zorder=3,
            alpha=0.8,
            marker='s',
            facecolor='none',
            edgecolor=color,
        )
        sc_eff = ax2.scatter(cyc_nums, eff, color=eff_color, marker='^', label=label_eff, 
                           s=40, alpha=0.7, zorder=3)
        
        # Store scatter artists in file_info for interactive menu
        file_info['sc_charge'] = sc_charge
        file_info['sc_discharge'] = sc_discharge
        file_info['sc_eff'] = sc_eff

    # Set efficiency y-range to 0-120 by default
    ax2.set_ylim(0, 120)

    # Compose legend
    try:
        if len(file_data) > 1 and _build_compact_cpc_legend is not None:
            # Multi-file: compact header row + one colored row per file
            _build_compact_cpc_legend(ax, ax2, file_data)
        else:
            # Single-file: standard two-entry legend
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            combined_handles = h1 + h2
            combined_labels = l1 + l2
            if combined_handles:
                ax.legend(
                    combined_handles, combined_labels,
                    loc='best',
                    frameon=False,
                    handlelength=1.0,
                    handletextpad=0.35,
                    labelspacing=0.25,
                    borderaxespad=0.5,
                    borderpad=0.3,
                    columnspacing=0.6,
                )
    except Exception as e:
        print(f"Warning: Could not create CPC legend: {e}")

    # Adjust layout to ensure top and bottom labels/titles are visible
    _apply_default_ec_layout(fig)
    
    # Check for style file in file list
    style_file_path = None
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            style_file_path = f
            break
    
    # Load and apply style file if provided
    if style_file_path:
        if os.path.isfile(style_file_path):
            try:
                with open(style_file_path, 'r', encoding='utf-8') as f:
                    style_cfg = json.load(f)
                print(f"Using style file: {os.path.basename(style_file_path)}")
                _apply_ec_style(fig, ax, style_cfg)
                # Also apply to twin axis
                _apply_ec_style(fig, ax2, style_cfg)
                # Redraw after applying style
                if hasattr(fig, 'canvas'):
                    fig.canvas.draw()
            except Exception as e:
                print(f"Warning: Error applying style file: {e}")
        else:
            print(f"Warning: Style file not found: {style_file_path}")

    from ...cli_save import run_cli_save_if_requested, should_show_plot
    from ...session import dump_cpc_session

    sc0 = file_data[0]
    sc_charge = sc0.get("sc_charge")
    sc_discharge = sc0.get("sc_discharge")
    sc_eff = sc0.get("sc_eff")
    cpc_paths = [os.path.abspath(f.get("filepath", "")) for f in file_data if f.get("filepath")]

    def _do_cpc_cli_save(target: str) -> None:
        dump_cpc_session(
            target,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data if len(file_data) > 1 else None,
            skip_confirm=True,
        )
        fig._last_session_save_path = os.path.abspath(target)

    if run_cli_save_if_requested(
        args,
        cpc_paths,
        purpose="CPC session save",
        default_stem=os.path.splitext(os.path.basename(cpc_paths[0]))[0] if len(file_data) == 1 else None,
        combined_plot=len(file_data) > 1,
        save_fn=_do_cpc_cli_save,
    ):
        try:
            plt.close(fig)
        except Exception:
            pass
        exit(0)

    if args.interactive and cpc_interactive_menu is not None:
        if require_interactive_display(args, context="CPC interactive menu"):
            prime_interactive_figure(fig)
            try:
                # Always pass file_data so filename is available
                    cpc_interactive_menu(fig, ax, ax2,
                                       file_data[0]['sc_charge'],
                                       file_data[0]['sc_discharge'],
                                       file_data[0]['sc_eff'],
                                       file_data=file_data)
            except Exception as _ie:
                print(f"CPC interactive menu failed: {_ie}")
            hold_figure_open()
    else:
        if should_show_plot(args):
            show_figure_if_possible(args)
    exit(0)
