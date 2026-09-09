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
from ..common.palettes import TAB10_HEX
from .load import load_cpc_file_arrays

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
            if ext not in ('.csv', '.xlsx', '.xls', '.mpt'):
                print(f"Skipped {file_basename}: unsupported format (must be .csv, .xlsx, or .mpt)")
                continue
            if ext == '.mpt' and mass_mg is None:
                mode_name = "EPC" if is_epc else "CPC"
                print(f"Skipped {file_basename}: {mode_name} mode (.mpt) requires --mass parameter.")
                continue
            cyc_nums, cap_charge, cap_discharge, eff = load_cpc_file_arrays(
                ec_file, mass_mg=mass_mg, is_epc=is_epc
            )

            # Assign colors: distinct hue per file
            capacity_color = capacity_colors[file_idx % len(capacity_colors)]
            efficiency_color = efficiency_colors[file_idx % len(efficiency_colors)]

            file_data.append({
                'filename': file_basename,
                'filepath': ec_file,
                'mass_mg': float(mass_mg) if mass_mg is not None else None,
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
    try:
        fig._cpc_is_epc = bool(is_epc)
    except Exception:
        pass
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
                from .style import _apply_style

                sc0 = file_data[0]
                _apply_style(
                    fig,
                    ax,
                    ax2,
                    sc0.get('sc_charge'),
                    sc0.get('sc_discharge'),
                    sc0.get('sc_eff'),
                    style_cfg,
                    file_data,
                )
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

    # Honor --out / --savefig (parity with GC / XY / dQdV CLI export).
    outname = getattr(args, "savefig", None) or getattr(args, "out", None)
    if outname:
        if not os.path.splitext(str(outname))[1]:
            outname = f"{outname}.svg"
        _, _ext = os.path.splitext(str(outname))
        try:
            if _ext.lower() == ".svg":
                plt.rcParams["svg.fonttype"] = "none"
                plt.rcParams["svg.hashsalt"] = None
                try:
                    _fig_fc = fig.get_facecolor()
                except Exception:
                    _fig_fc = None
                try:
                    _ax_fc = ax.get_facecolor()
                except Exception:
                    _ax_fc = None
                try:
                    if getattr(fig, "patch", None) is not None:
                        fig.patch.set_alpha(0.0)
                        fig.patch.set_facecolor("none")
                    if getattr(ax, "patch", None) is not None:
                        ax.patch.set_alpha(0.0)
                        ax.patch.set_facecolor("none")
                except Exception:
                    pass
                try:
                    fig.savefig(
                        outname,
                        dpi=300,
                        transparent=True,
                        facecolor="none",
                        edgecolor="none",
                    )
                finally:
                    try:
                        if _fig_fc is not None and getattr(fig, "patch", None) is not None:
                            fig.patch.set_alpha(1.0)
                            fig.patch.set_facecolor(_fig_fc)
                    except Exception:
                        pass
                    try:
                        if _ax_fc is not None and getattr(ax, "patch", None) is not None:
                            ax.patch.set_alpha(1.0)
                            ax.patch.set_facecolor(_ax_fc)
                    except Exception:
                        pass
            else:
                fig.savefig(outname, dpi=300)
            mode_tag = "EPC" if is_epc else "CPC"
            print(f"{mode_tag} plot saved to {outname}")
        except Exception as exc:
            print(f"Warning: Could not save CPC/EPC figure to {outname}: {exc}")

    def _do_cpc_cli_save(target: str) -> None:
        ok = dump_cpc_session(
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
        if not ok:
            raise RuntimeError(f"Failed to save CPC session to {target}")

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
