"""Batch processing for exporting plots to SVG."""

from __future__ import annotations

import os
import json
import numpy as np
import matplotlib.pyplot as plt

from .readers import (
    read_gr_file, 
    robust_loadtxt_skipheader,
    read_mpt_file,
    read_ec_csv_file,
    read_ec_csv_dqdv_file,
)
from .utils import _confirm_overwrite


def _load_style_file(style_path: str) -> dict | None:
    """Load a .bps, .bpsg, or .bpcfg style file.
    
    Args:
        style_path: Path to style configuration file
        
    Returns:
        Style configuration dict or None if loading fails
    """
    try:
        with open(style_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg
    except Exception as e:
        print(f"Warning: Could not load style file {style_path}: {e}")
        return None


def _apply_ec_style(fig, ax, cfg: dict):
    """Apply style configuration to an EC batch plot.
    
    Applies formatting from .bps/.bpsg files including fonts, colors,
    tick parameters, and geometry (if present in .bpsg files).
    
    Args:
        fig: Matplotlib figure object
        ax: Matplotlib axes object
        cfg: Style configuration dictionary
    """
    try:
        # Apply fonts
        font_cfg = cfg.get('font', {})
        if font_cfg:
            family = font_cfg.get('family')
            size = font_cfg.get('size')
            if family:
                plt.rcParams['font.sans-serif'] = [family] if isinstance(family, str) else family
            if size is not None:
                plt.rcParams['font.size'] = size
        
        # Apply figure size if present
        fig_cfg = cfg.get('figure', {})
        if fig_cfg:
            canvas_size = fig_cfg.get('canvas_size')
            if canvas_size and isinstance(canvas_size, (list, tuple)) and len(canvas_size) == 2:
                try:
                    fig.set_size_inches(canvas_size[0], canvas_size[1])
                except Exception:
                    pass
        
        # Apply tick parameters
        ticks_cfg = cfg.get('ticks', {})
        if ticks_cfg:
            # Tick widths
            widths = ticks_cfg.get('widths', {})
            if widths.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=widths['x_major'])
            if widths.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=widths['x_minor'])
            if widths.get('y_major') is not None or widths.get('ly_major') is not None:
                w = widths.get('y_major') or widths.get('ly_major')
                ax.tick_params(axis='y', which='major', width=w)
            if widths.get('y_minor') is not None or widths.get('ly_minor') is not None:
                w = widths.get('y_minor') or widths.get('ly_minor')
                ax.tick_params(axis='y', which='minor', width=w)
            
            # Tick lengths
            lengths = ticks_cfg.get('lengths', {})
            if lengths.get('major') is not None:
                ax.tick_params(axis='both', which='major', length=lengths['major'])
            if lengths.get('minor') is not None:
                ax.tick_params(axis='both', which='minor', length=lengths['minor'])
            
            # Tick direction
            direction = ticks_cfg.get('direction')
            if direction:
                ax.tick_params(axis='both', which='both', direction=direction)
        
        # Apply geometry if present (for .bpsg files)
        kind = cfg.get('kind', '')
        if 'geom' in kind.lower() and 'geometry' in cfg:
            geom = cfg.get('geometry', {})
            if geom.get('xlabel'):
                ax.set_xlabel(geom['xlabel'])
            if geom.get('ylabel'):
                ax.set_ylabel(geom['ylabel'])
            if 'xlim' in geom and isinstance(geom['xlim'], (list, tuple)) and len(geom['xlim']) == 2:
                try:
                    ax.set_xlim(geom['xlim'][0], geom['xlim'][1])
                except Exception:
                    pass
            if 'ylim' in geom and isinstance(geom['ylim'], (list, tuple)) and len(geom['ylim']) == 2:
                try:
                    ax.set_ylim(geom['ylim'][0], geom['ylim'][1])
                except Exception:
                    pass
        
        # Apply line colors if available (for GC/CV/dQdV modes)
        lines_cfg = cfg.get('lines', [])
        if lines_cfg and len(ax.lines) > 0:
            for entry in lines_cfg:
                idx = entry.get('index')
                if idx is not None and 0 <= idx < len(ax.lines):
                    ln = ax.lines[idx]
                    if 'color' in entry:
                        try:
                            ln.set_color(entry['color'])
                        except Exception:
                            pass
                    if 'linewidth' in entry:
                        try:
                            ln.set_linewidth(entry['linewidth'])
                        except Exception:
                            pass
                    if 'linestyle' in entry:
                        try:
                            ln.set_linestyle(entry['linestyle'])
                        except Exception:
                            pass
        
        # Apply spine configuration
        spines_cfg = cfg.get('spines', {})
        for spine_name, spine_props in spines_cfg.items():
            if spine_name in ax.spines:
                sp = ax.spines[spine_name]
                if 'lw' in spine_props or 'linewidth' in spine_props:
                    try:
                        lw = spine_props.get('lw') or spine_props.get('linewidth')
                        sp.set_linewidth(lw)
                    except Exception:
                        pass
                if 'color' in spine_props:
                    try:
                        sp.set_edgecolor(spine_props['color'])
                    except Exception:
                        pass
                if 'visible' in spine_props:
                    try:
                        sp.set_visible(spine_props['visible'])
                    except Exception:
                        pass
        
    except Exception as e:
        print(f"Warning: Error applying style: {e}")


def batch_process(directory: str, args):
    print(f"Batch mode: scanning {directory}")
    # Known extensions that don't need --xaxis
    known_axis_ext = {'.qye', '.gr', '.nor', '.chik', '.chir'}
    # All acceptable data extensions (known + common generic formats)
    known_ext = {'.xye', '.xy', '.qye', '.dat', '.csv', '.gr', '.nor', '.chik', '.chir', '.txt'}
    # Extensions to exclude from processing
    excluded_ext = {'.cif', '.pkl', '.py', '.md', '.json', '.yml', '.yaml', '.sh', '.bat', '.mpt'}
    
    from .utils import ensure_subdirectory
    out_dir = ensure_subdirectory('Figures', directory)
    
    # Collect all files, including those with unknown extensions
    files = []
    unknown_ext_files = []
    for f in sorted(os.listdir(directory)):
        if not os.path.isfile(os.path.join(directory, f)):
            continue
        ext = os.path.splitext(f)[1].lower()
        # Skip excluded extensions and files without extensions
        if ext in excluded_ext or not ext:
            continue
        # Include known extensions
        if ext in known_ext:
            files.append(f)
        else:
            # Include unknown extensions (require --xaxis)
            files.append(f)
            unknown_ext_files.append(f)
    
    if not files:
        print("No data files found.")
        return
    
    # Check if --xaxis is required for unknown extensions
    if unknown_ext_files and not args.xaxis:
        print(f"Error: Found {len(unknown_ext_files)} file(s) with unknown extension(s) that require --xaxis:")
        for uf in unknown_ext_files[:5]:  # Show first 5
            print(f"  - {uf}")
        if len(unknown_ext_files) > 5:
            print(f"  ... and {len(unknown_ext_files) - 5} more")
        print("\nKnown extensions that don't require --xaxis: .qye, .gr, .nor, .chik, .chir")
        print("Please specify x-axis type with --xaxis (options: 2theta, Q, r, energy, k, rft)")
        print("Example: batplot --all --xaxis 2theta")
        return
    
    if unknown_ext_files:
        print(f"Note: Processing {len(unknown_ext_files)} file(s) with unknown extension(s) using --xaxis {args.xaxis}")
    
    print(f"Found {len(files)} files. Exporting SVG plots to Figures/")
    for fname in files:
        fpath = os.path.join(directory, fname)
        ext = os.path.splitext(fname)[1].lower()
        try:
            # ---- Read data ----
            if ext == '.gr':
                x, y = read_gr_file(fpath); e = None
                axis_mode = 'r'
            elif ext == '.nor':
                data = np.loadtxt(fpath, comments="#")
                if data.ndim == 1: data = data.reshape(1, -1)
                if data.shape[1] < 2: raise ValueError("Invalid .nor format")
                x, y = data[:,0], data[:,1]
                e = data[:,2] if data.shape[1] >= 3 else None
                axis_mode = 'energy'
            elif 'chik' in ext:
                data = np.loadtxt(fpath, comments="#")
                if data.ndim == 1: data = data.reshape(1, -1)
                if data.shape[1] < 2: raise ValueError("Invalid .chik data")
                x, y = data[:,0], data[:,1]; e = data[:,2] if data.shape[1] >= 3 else None
                axis_mode = 'k'
            elif 'chir' in ext:
                data = np.loadtxt(fpath, comments="#")
                if data.ndim == 1: data = data.reshape(1, -1)
                if data.shape[1] < 2: raise ValueError("Invalid .chir data")
                x, y = data[:,0], data[:,1]; e = data[:,2] if data.shape[1] >= 3 else None
                axis_mode = 'rft'
            else:
                data = robust_loadtxt_skipheader(fpath)
                if data.ndim == 1: data = data.reshape(1, -1)
                if data.shape[1] < 2: raise ValueError("Invalid 2-column data")
                # Handle --readcol flag to select specific columns
                # Check for extension-specific readcol first, then fall back to general --readcol
                readcol_spec = None
                if hasattr(args, 'readcol_by_ext') and ext in args.readcol_by_ext:
                    readcol_spec = args.readcol_by_ext[ext]
                elif args.readcol:
                    readcol_spec = args.readcol
                
                if readcol_spec:
                    x_col, y_col = readcol_spec
                    # Convert from 1-indexed to 0-indexed
                    x_col_idx = x_col - 1
                    y_col_idx = y_col - 1
                    if x_col_idx < 0 or x_col_idx >= data.shape[1]:
                        raise ValueError(f"X column {x_col} out of range (has {data.shape[1]} columns)")
                    if y_col_idx < 0 or y_col_idx >= data.shape[1]:
                        raise ValueError(f"Y column {y_col} out of range (has {data.shape[1]} columns)")
                    x, y = data[:, x_col_idx], data[:, y_col_idx]
                    e = None  # Error bars not supported with custom column selection
                else:
                    x, y = data[:,0], data[:,1]
                    e = data[:,2] if data.shape[1] >= 3 else None
                if ext == '.qye':
                    axis_mode = 'Q'
                elif ext == '.gr':
                    axis_mode = 'r'
                elif ext == '.nor':
                    axis_mode = 'energy'
                elif 'chik' in ext:
                    axis_mode = 'k'
                elif 'chir' in ext:
                    axis_mode = 'rft'
                elif args.xaxis:
                    axis_mode = args.xaxis
                    # Print note once per unknown extension type
                    if not hasattr(args, '_batch_warned_extensions'):
                        args._batch_warned_extensions = set()
                    if ext and ext not in args._batch_warned_extensions and ext not in known_axis_ext:
                        args._batch_warned_extensions.add(ext)
                        print(f"  Note: Reading '{ext}' files as 2-column (x, y) data with x-axis = {args.xaxis}")
                else:
                    raise ValueError(f"Unknown file type: {fname}. Use --xaxis [Q|2theta|r|k|energy|rft] or batplot -h for help.")

            # Convert to Q if needed
            if axis_mode == 'Q' and ext not in ('.qye', '.gr', '.nor'):
                if args.wl is None:
                    axis_mode = '2theta'
                    x_plot = x
                else:
                    theta_rad = np.radians(x/2)
                    x_plot = 4*np.pi*np.sin(theta_rad)/args.wl
            else:
                x_plot = x

            # Normalize if --norm flag is set
            if getattr(args, 'norm', False):
                if y.size:
                    ymin = float(y.min()); ymax = float(y.max())
                    span = ymax - ymin
                    y_plot = (y - ymin)/span if span > 0 else np.zeros_like(y)
                else:
                    y_plot = y
            else:
                y_plot = y.copy()

            # Plot and save
            fig_b, ax_b = plt.subplots(figsize=(6,4))
            ax_b.plot(x_plot, y_plot, lw=1)
            
            # Apply x-range if specified
            if args.xrange:
                ax_b.set_xlim(args.xrange[0], args.xrange[1])
            
            if axis_mode == 'Q':
                ax_b.set_xlabel(r"Q ($\mathrm{\AA}^{-1}$)")
            elif axis_mode == 'r':
                ax_b.set_xlabel("r (Å)")
            elif axis_mode == 'energy':
                ax_b.set_xlabel("Energy (eV)")
            elif axis_mode == 'k':
                ax_b.set_xlabel(r"k ($\mathrm{\AA}^{-1}$)")
            elif axis_mode == 'rft':
                ax_b.set_xlabel("Radial distance (Å)")
            else:
                ax_b.set_xlabel(r"$2\theta\ (\mathrm{deg})$")
            ax_b.set_ylabel("Normalized intensity (a.u.)" if getattr(args, 'norm', False) else "Intensity")
            ax_b.set_title(fname)
            fig_b.subplots_adjust(left=0.18, right=0.97, bottom=0.16, top=0.90)
            # Get output format from args, default to svg
            output_format = getattr(args, 'format', 'svg')
            out_name = os.path.splitext(fname)[0] + f".{output_format}"
            out_path = os.path.join(out_dir, out_name)
            target = _confirm_overwrite(out_path)
            if not target:
                plt.close(fig_b)
                print(f"  Skipped {out_name} (user canceled)")
            else:
                # Transparent background for SVG exports
                _, _ext = os.path.splitext(target)
                if _ext.lower() == '.svg':
                    # Fix for Affinity Designer/Photo compatibility issues
                    # Use 'none' to embed fonts as text (not paths) - prevents phantom labels
                    # Set hashsalt to empty to avoid duplicate text elements
                    plt.rcParams['svg.fonttype'] = 'none'
                    plt.rcParams['svg.hashsalt'] = None
                    try:
                        _fig_fc = fig_b.get_facecolor()
                    except Exception:
                        _fig_fc = None
                    try:
                        _ax_fc = ax_b.get_facecolor()
                    except Exception:
                        _ax_fc = None
                    try:
                        if getattr(fig_b, 'patch', None) is not None:
                            fig_b.patch.set_alpha(0.0); fig_b.patch.set_facecolor('none')
                        if getattr(ax_b, 'patch', None) is not None:
                            ax_b.patch.set_alpha(0.0); ax_b.patch.set_facecolor('none')
                    except Exception:
                        pass
                    try:
                        fig_b.savefig(target, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                    finally:
                        try:
                            if _fig_fc is not None and getattr(fig_b, 'patch', None) is not None:
                                fig_b.patch.set_alpha(1.0); fig_b.patch.set_facecolor(_fig_fc)
                        except Exception:
                            pass
                        try:
                            if _ax_fc is not None and getattr(ax_b, 'patch', None) is not None:
                                ax_b.patch.set_alpha(1.0); ax_b.patch.set_facecolor(_ax_fc)
                        except Exception:
                            pass
                else:
                    fig_b.savefig(target, dpi=300)
                plt.close(fig_b)
                print(f"  Saved {os.path.basename(target)}")
        except Exception as e:
            print(f"  Skipped {fname}: {e}")
    print("Batch processing complete.")


def batch_process_ec(directory: str, args):
    """Batch process electrochemistry files in a directory.
    
    Supports GC (.mpt/.csv), CV (.mpt), dQdV (.csv), and CPC (.mpt/.csv) modes.
    Exports SVG plots to batplot_svg subdirectory.
    
    Can apply style/geometry from .bps/.bpsg files using --all flag:
        batplot --all --gc style.bps       # Apply style.bps to all .mpt/.csv GC files
        batplot --all --cv style.bpsg      # Apply style+geom to all CV files
        batplot --all --dqdv mystyle.bps   # Apply style to all dQdV files
        batplot --all --cpc config.bpsg    # Apply to all CPC files
    
    Note: For GC and CPC modes with .csv files, --mass is not required as the
    capacity data is already in the file. For .mpt files, --mass is required.
    
    Args:
        directory: Directory containing EC files
        args: Argument namespace with mode flags (gc, cv, dqdv, cpc), mass, and all
    """
    print(f"EC Batch mode: scanning {directory}")
    
    # Check if --all flag was used with a style file
    style_cfg = None
    style_file_arg = getattr(args, 'all', None)
    if style_file_arg and style_file_arg != 'all':
        # User provided a style file path
        style_path = style_file_arg if os.path.isabs(style_file_arg) else os.path.join(directory, style_file_arg)
        if os.path.exists(style_path) and style_path.lower().endswith(('.bps', '.bpsg', '.bpcfg')):
            style_cfg = _load_style_file(style_path)
            if style_cfg:
                print(f"Using style file: {os.path.basename(style_path)}")
        else:
            # Try to find the file in current directory
            for ext in ['.bps', '.bpsg', '.bpcfg']:
                test_path = style_file_arg if style_file_arg.endswith(ext) else style_file_arg + ext
                test_full = os.path.join(directory, test_path)
                if os.path.exists(test_full):
                    style_cfg = _load_style_file(test_full)
                    if style_cfg:
                        print(f"Using style file: {os.path.basename(test_full)}")
                    break
            if not style_cfg:
                print(f"Warning: Could not find style file '{style_file_arg}'")
    
    # Determine which EC mode is active
    mode = None
    if getattr(args, 'gc', False):
        mode = 'gc'
        supported_ext = {'.mpt', '.csv'}
    elif getattr(args, 'cv', False):
        mode = 'cv'
        supported_ext = {'.mpt', '.txt'}
    elif getattr(args, 'dqdv', False):
        mode = 'dqdv'
        supported_ext = {'.csv'}
    elif getattr(args, 'cpc', False):
        mode = 'cpc'
        supported_ext = {'.mpt', '.csv'}
    else:
        print("EC batch mode requires one of: --gc, --cv, --dqdv, or --cpc")
        return
    
    from .utils import ensure_subdirectory
    out_dir = ensure_subdirectory('Figures', directory)
    
    files = [f for f in sorted(os.listdir(directory))
             if os.path.splitext(f)[1].lower() in supported_ext 
             and os.path.isfile(os.path.join(directory, f))]
    
    if not files:
        print(f"No {mode.upper()} files found.")
        return
    
    print(f"Found {len(files)} {mode.upper()} files. Exporting SVG plots to Figures/")
    
    # Enhanced color palette using matplotlib colormaps
    # Start with base colors, then generate more using colormap if needed
    base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                   '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    def get_color_palette(n_colors):
        """Generate a color palette with n_colors distinct colors.
        
        For large numbers of cycles (>70), uses continuous colormaps to ensure
        all cycles get visually distinct colors.
        """
        if n_colors <= len(base_colors):
            return base_colors[:n_colors]
        else:
            import matplotlib.cm as cm
            colors = list(base_colors)  # Start with base colors
            remaining = n_colors - len(base_colors)
            
            if remaining <= 60:
                # Use tab20, tab20b, tab20c for categorical colors (up to 70 total)
                tab20 = cm.get_cmap('tab20')
                tab20b = cm.get_cmap('tab20b')
                tab20c = cm.get_cmap('tab20c')
                
                for i in range(remaining):
                    cmap_idx = i % 60
                    if cmap_idx < 20:
                        color = tab20(cmap_idx / 20)
                    elif cmap_idx < 40:
                        color = tab20b((cmap_idx - 20) / 20)
                    else:
                        color = tab20c((cmap_idx - 40) / 20)
                    hex_color = '#{:02x}{:02x}{:02x}'.format(
                        int(color[0]*255), int(color[1]*255), int(color[2]*255))
                    if hex_color not in colors:
                        colors.append(hex_color)
                    if len(colors) >= n_colors:
                        break
            else:
                # For >70 cycles, use continuous colormaps for smooth color gradients
                # Combine multiple perceptually uniform colormaps
                cmaps = ['viridis', 'plasma', 'inferno', 'magma', 'cividis', 
                         'turbo', 'twilight', 'hsv']
                colors_per_map = (remaining + len(cmaps) - 1) // len(cmaps)
                
                for cmap_name in cmaps:
                    cmap = cm.get_cmap(cmap_name)
                    # Sample evenly across the colormap
                    for i in range(colors_per_map):
                        if len(colors) >= n_colors:
                            break
                        # Sample from middle 80% of colormap to avoid extreme light/dark
                        t = 0.1 + 0.8 * (i / max(colors_per_map - 1, 1))
                        color = cmap(t)
                        hex_color = '#{:02x}{:02x}{:02x}'.format(
                            int(color[0]*255), int(color[1]*255), int(color[2]*255))
                        if hex_color not in colors:
                            colors.append(hex_color)
                    if len(colors) >= n_colors:
                        break
            
            return colors[:n_colors]  # Ensure exact count
    
    for fname in files:
        fpath = os.path.join(directory, fname)
        ext = os.path.splitext(fname)[1].lower()
        
        try:
            fig_b, ax_b = plt.subplots(figsize=(6, 4))
            
            # ---- GC Mode ----
            if mode == 'gc':
                if ext == '.mpt':
                    mass_mg = getattr(args, 'mass', None)
                    if mass_mg is None:
                        print(f"  Skipped {fname}: GC mode (.mpt) requires --mass parameter")
                        plt.close(fig_b)
                        continue
                    specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = \
                        read_mpt_file(fpath, mode='gc', mass_mg=mass_mg)
                    cap_x = specific_capacity
                    x_label = r'Specific Capacity (mAh g$^{-1}$)'
                elif ext == '.csv':
                    cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = \
                        read_ec_csv_file(fpath, prefer_specific=True)
                    x_label = r'Specific Capacity (mAh g$^{-1}$)'
                else:
                    raise ValueError(f"Unsupported file type for GC: {ext}")
                
                # Plot cycles
                if cycle_numbers is not None:
                    cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
                    if cyc_int_raw.size:
                        min_c = int(np.min(cyc_int_raw))
                        shift = 1 - min_c if min_c <= 0 else 0
                        cyc_int = cyc_int_raw + shift
                        cycles_present = sorted(int(c) for c in np.unique(cyc_int))
                    else:
                        cycles_present = [1]
                else:
                    cycles_present = [1]
                
                # Generate color palette for the number of cycles
                cycle_colors = get_color_palette(len(cycles_present))
                
                for idx, cyc in enumerate(cycles_present):  # Plot all cycles
                    if cycle_numbers is not None:
                        mask_c = (cyc_int == cyc) & charge_mask
                        mask_d = (cyc_int == cyc) & discharge_mask
                    else:
                        mask_c = charge_mask
                        mask_d = discharge_mask
                    
                    color = cycle_colors[idx]
                    
                    # Plot charge and discharge with the same color and label
                    plotted = False
                    if np.any(mask_c):
                        ax_b.plot(cap_x[mask_c], voltage[mask_c], '-', 
                                 color=color, linewidth=1.5, alpha=0.8, label=str(cyc))
                        plotted = True
                    if np.any(mask_d):
                        if plotted:
                            # Don't add another label for discharge
                            ax_b.plot(cap_x[mask_d], voltage[mask_d], '-', 
                                     color=color, linewidth=1.5, alpha=0.8)
                        else:
                            ax_b.plot(cap_x[mask_d], voltage[mask_d], '-', 
                                     color=color, linewidth=1.5, alpha=0.8, label=str(cyc))
                
                ax_b.set_xlabel(x_label)
                ax_b.set_ylabel('Voltage (V)')
                ax_b.set_title(f"{fname}")
                legend = ax_b.legend(loc='best', fontsize='small', framealpha=0.8, title='Cycle')
                legend.get_title().set_fontsize('small')
            
            # ---- CV Mode ----
            elif mode == 'cv':
                if ext == '.txt':
                    from .readers import read_biologic_txt_file
                    voltage, current, cycles = read_biologic_txt_file(fpath, mode='cv')
                elif ext == '.mpt':
                    voltage, current, cycles = read_mpt_file(fpath, mode='cv')
                else:
                    raise ValueError("CV mode requires .mpt or .txt file")
                
                cyc_int_raw = np.array(np.rint(cycles), dtype=int)
                if cyc_int_raw.size:
                    min_c = int(np.min(cyc_int_raw))
                    shift = 1 - min_c if min_c <= 0 else 0
                    cyc_int = cyc_int_raw + shift
                    cycles_present = sorted(int(c) for c in np.unique(cyc_int))
                else:
                    cycles_present = [1]
                
                # Generate color palette for the number of cycles
                cycle_colors = get_color_palette(len(cycles_present))
                
                for idx, cyc in enumerate(cycles_present):  # Plot all cycles
                    mask = (cyc_int == cyc)
                    mask_idx = np.where(mask)[0]
                    if mask_idx.size >= 2:
                        color = cycle_colors[idx]
                        ax_b.plot(voltage[mask], current[mask], '-', 
                                 color=color, linewidth=1.5, alpha=0.8, label=str(cyc))
                
                ax_b.set_xlabel('Voltage (V)')
                ax_b.set_ylabel('Current (mA)')
                ax_b.set_title(f"{fname}")
                legend = ax_b.legend(loc='best', fontsize='small', framealpha=0.8, title='Cycle')
                legend.get_title().set_fontsize('small')
            
            # ---- dQdV Mode ----
            elif mode == 'dqdv':
                if ext != '.csv':
                    raise ValueError("dQdV mode requires .csv file")
                
                # Read dQdV data with cycle information
                voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = \
                    read_ec_csv_dqdv_file(fpath, prefer_specific=True)
                
                # Process cycles similar to GC mode
                if cycles is not None and cycles.size > 0:
                    cyc_int_raw = np.array(np.rint(cycles), dtype=int)
                    if cyc_int_raw.size:
                        min_c = int(np.min(cyc_int_raw))
                        shift = 1 - min_c if min_c <= 0 else 0
                        cyc_int = cyc_int_raw + shift
                        cycles_present = sorted(int(c) for c in np.unique(cyc_int))
                    else:
                        cycles_present = [1]
                else:
                    cycles_present = [1]
                
                # Generate color palette for the number of cycles
                cycle_colors = get_color_palette(len(cycles_present))
                
                # Plot each cycle
                for idx, cyc in enumerate(cycles_present):
                    if cycles is not None:
                        mask_c = (cyc_int == cyc) & charge_mask
                        mask_d = (cyc_int == cyc) & discharge_mask
                    else:
                        mask_c = charge_mask
                        mask_d = discharge_mask
                    
                    color = cycle_colors[idx]
                    
                    # Plot charge and discharge with the same color and label
                    plotted = False
                    if np.any(mask_c):
                        ax_b.plot(voltage[mask_c], dqdv[mask_c], '-', 
                                 color=color, linewidth=1.5, alpha=0.8, label=str(cyc))
                        plotted = True
                    if np.any(mask_d):
                        if plotted:
                            # Don't add another label for discharge
                            ax_b.plot(voltage[mask_d], dqdv[mask_d], '-', 
                                     color=color, linewidth=1.5, alpha=0.8)
                        else:
                            ax_b.plot(voltage[mask_d], dqdv[mask_d], '-', 
                                     color=color, linewidth=1.5, alpha=0.8, label=str(cyc))
                
                ax_b.set_xlabel('Voltage (V)')
                ax_b.set_ylabel(y_label)
                ax_b.set_title(f"{fname}")
                legend = ax_b.legend(loc='best', fontsize='small', framealpha=0.8, title='Cycle')
                legend.get_title().set_fontsize('small')
            
            # ---- CPC Mode ----
            elif mode == 'cpc':
                if ext == '.mpt':
                    mass_mg = getattr(args, 'mass', None)
                    if mass_mg is None:
                        print(f"  Skipped {fname}: CPC mode (.mpt) requires --mass parameter")
                        plt.close(fig_b)
                        continue
                    cyc_nums, cap_charge, cap_discharge, eff = \
                        read_mpt_file(fpath, mode='cpc', mass_mg=mass_mg)
                    x_label = r'Specific Capacity (mAh g$^{-1}$)'
                elif ext == '.csv':
                    # For CSV CPC, read as GC-like data
                    cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = \
                        read_ec_csv_file(fpath, prefer_specific=True)
                    # Plot capacity vs cycle number
                    if cycle_numbers is not None:
                        cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
                        if cyc_int_raw.size:
                            cycles_present = sorted(int(c) for c in np.unique(cyc_int_raw))
                            # Calculate capacity per cycle
                            cap_charge = []
                            cap_discharge = []
                            for cyc in cycles_present:
                                mask_c = (cyc_int_raw == cyc) & charge_mask
                                mask_d = (cyc_int_raw == cyc) & discharge_mask
                                cap_charge.append(np.max(cap_x[mask_c]) if np.any(mask_c) else 0)
                                cap_discharge.append(np.max(cap_x[mask_d]) if np.any(mask_d) else 0)
                            cyc_nums = np.array(cycles_present)
                            cap_charge = np.array(cap_charge)
                            cap_discharge = np.array(cap_discharge)
                        else:
                            cyc_nums = np.array([1])
                            cap_charge = np.array([0])
                            cap_discharge = np.array([0])
                    else:
                        cyc_nums = np.array([1])
                        cap_charge = np.array([0])
                        cap_discharge = np.array([0])
                    x_label = r'Specific Capacity (mAh g$^{-1}$)'
                else:
                    raise ValueError(f"Unsupported file type for CPC: {ext}")
                
                # Plot CPC data
                ax_b.plot(cyc_nums, cap_charge, 'o-', color='#1f77b4', 
                         linewidth=1.5, markersize=4, label='Charge', alpha=0.8)
                ax_b.plot(cyc_nums, cap_discharge, 's-', color='#ff7f0e', 
                         linewidth=1.5, markersize=4, label='Discharge', alpha=0.8)
                ax_b.set_xlabel('Cycle Number')
                ax_b.set_ylabel(x_label)
                ax_b.legend()
                ax_b.set_title(f"{fname}")
            
            # Apply style/geometry if provided via --all flag
            if style_cfg:
                try:
                    _apply_ec_style(fig_b, ax_b, style_cfg)
                except Exception as e:
                    print(f"  Warning: Could not apply style to {fname}: {e}")
            
            # Adjust layout and save
            fig_b.subplots_adjust(left=0.18, right=0.97, bottom=0.16, top=0.90)
            # Get output format from args, default to svg
            output_format = getattr(args, 'format', 'svg')
            out_name = os.path.splitext(fname)[0] + f"_{mode}.{output_format}"
            out_path = os.path.join(out_dir, out_name)
            
            target = _confirm_overwrite(out_path)
            if not target:
                plt.close(fig_b)
                print(f"  Skipped {out_name} (user canceled)")
            else:
                # Transparent background for SVG
                _, _ext = os.path.splitext(target)
                if _ext.lower() == '.svg':
                    try:
                        _fig_fc = fig_b.get_facecolor()
                    except Exception:
                        _fig_fc = None
                    try:
                        _ax_fc = ax_b.get_facecolor()
                    except Exception:
                        _ax_fc = None
                    try:
                        if getattr(fig_b, 'patch', None) is not None:
                            fig_b.patch.set_alpha(0.0)
                            fig_b.patch.set_facecolor('none')
                        if getattr(ax_b, 'patch', None) is not None:
                            ax_b.patch.set_alpha(0.0)
                            ax_b.patch.set_facecolor('none')
                    except Exception:
                        pass
                    try:
                        fig_b.savefig(target, dpi=300, transparent=True, 
                                     facecolor='none', edgecolor='none')
                    finally:
                        try:
                            if _fig_fc is not None and getattr(fig_b, 'patch', None) is not None:
                                fig_b.patch.set_alpha(1.0)
                                fig_b.patch.set_facecolor(_fig_fc)
                        except Exception:
                            pass
                        try:
                            if _ax_fc is not None and getattr(ax_b, 'patch', None) is not None:
                                ax_b.patch.set_alpha(1.0)
                                ax_b.patch.set_facecolor(_ax_fc)
                        except Exception:
                            pass
                else:
                    fig_b.savefig(target, dpi=300)
                plt.close(fig_b)
                print(f"  Saved {os.path.basename(target)}")
                
        except Exception as e:
            plt.close(fig_b)
            print(f"  Skipped {fname}: {e}")
    
    print(f"EC batch processing complete ({mode.upper()} mode).")


__all__ = ["batch_process", "batch_process_ec"]
