# Batplot Code Guide

**Version:** 1.4.9  
**Purpose:** Comprehensive guide for developers maintaining and extending batplot

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Organization](#module-organization)
3. [Data Flow](#data-flow)
4. [Adding New Features](#adding-new-features)
5. [Common Patterns](#common-patterns)
6. [Testing & Debugging](#testing--debugging)

---

## Architecture Overview

### Design Principles

**Batplot follows these key principles:**

1. **Lazy Imports**: Modules are imported inside functions to avoid side effects at import time
2. **Mode Separation**: Each plotting mode (CV, GC, CPC, etc.) has its own handler function
3. **Interactive Menus**: All modes support optional interactive customization after initial plot
4. **File Format Flexibility**: Readers handle multiple formats (BioLogic .mpt, Neware .csv, Excel, etc.)
5. **Clean Error Handling**: User-facing errors are ValueError, others are caught gracefully

### Entry Point Flow

```
User runs: batplot --cv data.mpt --interactive
           ↓
cli.main() - Check for updates, parse args
           ↓
batplot_main() - Route to appropriate mode handler
           ↓
modes.handle_cv_mode() - Create plot, launch menu
           ↓
electrochem_interactive_menu() - User customization loop
           ↓
Exit with code 0
```

---

## Module Organization

### Core Entry Points

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `cli.py` | CLI entry point | `main()` - version check & delegation |
| `batplot.py` | Argument parsing & routing | `batplot_main()` - parse args, route to modes |
| `args.py` | Argument definitions | `get_parser()` - define CLI arguments |

### Mode Handlers

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `modes.py` | CV and GC plotting | `handle_cv_mode()`, `handle_gc_mode()` |
| `batplot.py` | dQ/dV and CPC plotting | Inline in `batplot_main()` |
| `operando.py` | Operando XRD+EC plotting | `plot_operando()` |

### Data Readers

| Module | Purpose | Supported Formats |
|--------|---------|-------------------|
| `readers.py` | Parse battery cycler data | .mpt (BioLogic), .csv (Neware), .xlsx (Landt/Lanhe), .txt |

**Key Functions:**
- `read_mpt_file()` - BioLogic native format, handles CV, GC, CPC modes
- `read_ec_csv_file()` - Neware CSV, auto-detects Cycle Index, handles half-cycle merging
- `read_ec_csv_dqdv_file()` - Differential capacity analysis
- `read_biologic_txt_file()` - BioLogic exported text format

### Interactive Menus

| Module | Purpose | Modes |
|--------|---------|-------|
| `electrochem_interactive.py` | Basic EC customization | CV, GC, dQ/dV |
| `cpc_interactive.py` | CPC (capacity-per-cycle) customization | CPC |
| `operando_ec_interactive.py` | Operando contour plot customization | Operando |
| `interactive.py` | XRD plot customization | XRD (legacy) |

**Menu Command Pattern:**
All menus follow similar structure:
1. Display menu options (`_print_menu()`)
2. Get user input
3. Parse command (single letter or compound like `c1 #ff0000`)
4. Execute command (modify plot)
5. Redraw figure
6. Loop until quit

### Utility Modules

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `utils.py` | File organization & text formatting | `ensure_subdirectory()`, `normalize_label_text()` |
| `converters.py` | Data format conversion | `convert_to_qye()` - 2θ to Q-space |
| `style.py` | Plot styling utilities | Color schemes, line styles |
| `session.py` | Save/load project state | `save_project()`, `load_project()` |
| `plotting.py` | Common plotting functions | Shared plotting utilities |
| `ui.py` | Terminal UI helpers | Colored output, progress bars |
| `version_check.py` | Update notifications | `check_for_updates()` - PyPI version check |

---

## Data Flow

### Example: GC Mode Data Flow

```
1. User Input
   batplot --gc data.csv --interactive
   
2. Parse Args (batplot.py)
   args.gc = True
   args.files = ['data.csv']
   args.interactive = True
   
3. Read Data (readers.py)
   read_ec_csv_file('data.csv')
   → Returns: capacity, voltage, cycles, charge_mask, discharge_mask
   
4. Process Cycles (modes.py)
   • Normalize cycle numbers to start at 1
   • Detect half-cycles (Neware bug) and merge
   • Group data by cycle
   • Split into charge/discharge segments
   
5. Create Plot (modes.py)
   • Create figure with matplotlib
   • Plot each cycle with unique color
   • Add labels, legend, grid
   • Apply consistent styling
   
6. Interactive Menu (electrochem_interactive.py)
   • User can modify colors, fonts, ranges
   • Commands update plot in real-time
   • Can save styles, export figures
   
7. Exit
   • Save figure if requested
   • Return exit code 0
```

### Data Structures

**Common data types throughout batplot:**

```python
# EC data from readers
capacity: np.ndarray     # Capacity values (mAh or mAh/g)
voltage: np.ndarray      # Voltage values (V)
cycles: np.ndarray       # Cycle numbers (int or float)
charge_mask: np.ndarray  # Boolean: True for charge points
discharge_mask: np.ndarray  # Boolean: True for discharge points

# Cycle lines dict for interactive menus
cycle_lines: Dict[int, Dict[str, Line2D]] = {
    1: {"charge": line_obj, "discharge": line_obj},
    2: {"charge": line_obj, "discharge": line_obj},
    ...
}

# CPC scatter dict
file_data: List[Dict] = [
    {
        'filename': 'data.csv',
        'cyc_nums': np.array([1, 2, 3, ...]),
        'cap_charge': np.array([...]),
        'cap_discharge': np.array([...]),
        'eff': np.array([...]),
        'sc_charge': scatter_obj,
        'sc_discharge': scatter_obj,
        'sc_eff': scatter_obj,
        'visible': True
    },
    ...
]
```

---

## Adding New Features

### Adding a New Plotting Mode

**Example: Adding a "Power Curve" mode**

1. **Add argument in `args.py`:**
```python
parser.add_argument('--power', action='store_true',
                   help='Power curve mode (power vs time)')
```

2. **Create handler function in `modes.py` or `batplot.py`:**
```python
def handle_power_mode(args) -> int:
    """Handle power curve plotting mode."""
    # Validate input
    if len(args.files) != 1:
        print("Power mode: provide exactly one file")
        return 1
    
    # Read data
    from .readers import read_mpt_file
    time, power, cycles = read_mpt_file(args.files[0], mode='power')
    
    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(time, power)
    ax.set_xlabel('Time (h)')
    ax.set_ylabel('Power (W)')
    
    # Save or show
    if args.out:
        fig.savefig(args.out)
    else:
        plt.show()
    
    return 0
```

3. **Add routing in `batplot_main()` in `batplot.py`:**
```python
if args.power:
    from .modes import handle_power_mode
    return handle_power_mode(args)
```

4. **Test:**
```bash
python -m batplot.cli --power test.mpt --out power.svg
```

### Adding a New File Format

**Example: Adding support for Arbin .res files**

1. **Add reader function in `readers.py`:**
```python
def read_arbin_res_file(filename: str, mode: str = 'gc'):
    """Read Arbin .res file.
    
    Args:
        filename: Path to .res file
        mode: 'gc' or 'cv' or 'cpc'
    
    Returns:
        Depends on mode:
        - gc: (capacity, voltage, cycles, charge_mask, discharge_mask)
        - cv: (voltage, current, cycles)
        - cpc: (cycle_nums, cap_charge, cap_discharge, efficiency)
    """
    # Parse .res format (binary or text)
    # Extract relevant columns
    # Return in standard format
    pass
```

2. **Add support in mode handlers:**
```python
# In modes.py or batplot.py
if ec_file.lower().endswith('.res'):
    from .readers import read_arbin_res_file
    data = read_arbin_res_file(ec_file, mode='gc')
```

3. **Update documentation:**
- Add to USER_MANUAL.md
- Add example in README.md
- Update `args.py` help text

### Adding an Interactive Menu Command

**Example: Adding a "smooth" command to GC menu**

1. **Find the interactive menu file** (`electrochem_interactive.py`)

2. **Add to menu display:**
```python
def _print_menu():
    print(" s: smooth data")  # Add this line
    # ... rest of menu
```

3. **Add command handler:**
```python
# In electrochem_interactive_menu() function
elif inp == 's':
    # Get smoothing window
    window = input("Smoothing window (default=5): ").strip()
    window = int(window) if window else 5
    
    # Apply smoothing to all cycles
    from scipy.signal import savgol_filter
    for cyc, lines in cycle_lines.items():
        for key in ['charge', 'discharge']:
            if lines[key] is not None:
                x, y = lines[key].get_xdata(), lines[key].get_ydata()
                y_smooth = savgol_filter(y, window, 3)
                lines[key].set_ydata(y_smooth)
    
    fig.canvas.draw_idle()
```

4. **Update documentation** in function docstring

---

## Common Patterns

### Error Handling Pattern

```python
try:
    # Main logic
    data = read_file(filename)
    plot_data(data)
    return 0
except FileNotFoundError:
    print(f"File not found: {filename}")
    return 1
except ValueError as e:
    # User-facing errors
    print(f"Error: {e}")
    return 1
except Exception as e:
    # Unexpected errors - print for debugging
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    return 1
```

### Backend Check Pattern

```python
# Check if matplotlib backend is interactive
try:
    _backend = plt.get_backend()
except Exception:
    _backend = "unknown"

_interactive_backends = {"tkagg", "qt5agg", "qtagg", "wxagg", "macosx"}
_is_noninteractive = (
    isinstance(_backend, str) and 
    _backend.lower() not in _interactive_backends and
    ("agg" in _backend.lower() or _backend.lower() in {"pdf", "ps", "svg"})
)

if _is_noninteractive:
    print(f"Backend '{_backend}' is non-interactive")
    print("Set MPLBACKEND=TkAgg or use --out to save")
else:
    plt.show()
```

### SVG Transparent Save Pattern

```python
# Save SVG with transparent background
if outname.endswith('.svg'):
    # Store original colors
    _fig_fc = fig.get_facecolor()
    _ax_fc = ax.get_facecolor()
    
    # Make transparent
    fig.patch.set_alpha(0.0)
    fig.patch.set_facecolor('none')
    ax.patch.set_alpha(0.0)
    ax.patch.set_facecolor('none')
    
    try:
        fig.savefig(outname, dpi=300, transparent=True,
                   facecolor='none', edgecolor='none')
    finally:
        # Restore for interactive display
        fig.patch.set_alpha(1.0)
        fig.patch.set_facecolor(_fig_fc)
        ax.patch.set_alpha(1.0)
        ax.patch.set_facecolor(_ax_fc)
```

### Cycle Discontinuity Handling Pattern

```python
# Split cycle data into continuous segments (handle paused experiments)
parts_x = []
parts_y = []
start = 0

for k in range(1, len(idx)):
    if idx[k] != idx[k-1] + 1:  # Gap detected
        # Save current segment
        parts_x.append(x[idx[start:k]])
        parts_y.append(y[idx[start:k]])
        start = k

# Save final segment
parts_x.append(x[idx[start:]])
parts_y.append(y[idx[start:]])

# Concatenate with NaN separators
X, Y = [], []
for i, (px, py) in enumerate(zip(parts_x, parts_y)):
    if i > 0:
        X.append(np.array([np.nan]))
        Y.append(np.array([np.nan]))
    X.append(px)
    Y.append(py)

x_plot = np.concatenate(X)
y_plot = np.concatenate(Y)
```

---

## Testing & Debugging

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_readers.py

# Run with coverage
pytest --cov=batplot --cov-report=html
```

### Manual Testing

```bash
# Test CV mode
batplot --cv test_data/cv_data.mpt --out test_cv.svg

# Test GC mode with mass
batplot --gc test_data/gc_data.mpt --mass 5.2 --interactive

# Test CPC mode
batplot --cpc test_data/neware.csv --out cpc.png

# Test version check
BATPLOT_NO_VERSION_CHECK=0 batplot --help

# Test with old version to see update notification
python -c "from batplot.version_check import check_for_updates; check_for_updates('1.0.0', force=True)"
```

### Debugging Interactive Menus

```python
# Add debug print statements
def some_menu_command():
    print(f"DEBUG: Processing command, current state: {some_var}")
    # ... rest of function

# Use IPython for interactive debugging
import IPython; IPython.embed()

# Check matplotlib state
print(f"Backend: {plt.get_backend()}")
print(f"Figure exists: {plt.fignum_exists(1)}")
print(f"Axes: {fig.axes}")
```

### Common Issues & Solutions

**Issue: "Backend is non-interactive"**
```bash
# Solution: Set interactive backend
export MPLBACKEND=TkAgg  # or MacOSX on Mac
```

**Issue: Cycle numbers don't start at 1**
```python
# Solution: Normalize in reader or mode handler
cycles = cycles - cycles.min() + 1
```

**Issue: Half-cycles detected as separate cycles**
```python
# Solution: readers.py already has half-cycle merger (lines 1028-1080)
# Merges consecutive charge-only and discharge-only cycles
```

**Issue: Version check blocks startup**
```bash
# Solution: Disable version check
export BATPLOT_NO_VERSION_CHECK=1
```

---

## Code Style Guidelines

### Naming Conventions

- **Functions**: `snake_case` (e.g., `read_mpt_file`, `handle_cv_mode`)
- **Classes**: `PascalCase` (e.g., `SessionManager`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_DPI`, `MAX_CYCLES`)
- **Private functions**: `_leading_underscore` (e.g., `_print_menu`, `_confirm_overwrite`)
- **Module-level**: Avoid globals, use functions to encapsulate state

### Documentation

- **Modules**: Docstring at top explaining purpose, key functions, design principles
- **Functions**: Docstring with Args, Returns, Raises, Examples
- **Complex logic**: Inline comments explaining WHY, not WHAT
- **Magic numbers**: Use named constants or explain in comments

### Import Organization

```python
# Standard library
import os
import sys
from typing import Optional, Dict, List

# Third-party
import numpy as np
import matplotlib.pyplot as plt

# Local
from .readers import read_mpt_file
from .utils import ensure_subdirectory
```

---

## Release Checklist

Before releasing a new version:

1. **Update version number** in `pyproject.toml` and `batplot/__init__.py`
2. **Run tests**: `pytest`
3. **Test manually** with sample files for all modes
4. **Update documentation**: README.md, USER_MANUAL.md, CODE_GUIDE.md
5. **Build package**: `python -m build`
6. **Upload to PyPI**: `python -m twine upload dist/batplot-X.Y.Z*`
7. **Commit and push**: 
   ```bash
   git add -A
   git commit -m "Release X.Y.Z: description"
   git push origin main
   ```
8. **Create GitHub release** with changelog
9. **Tag release**: `git tag vX.Y.Z && git push --tags`

---

## Contact & Contributing

- **Repository**: https://github.com/tiandai-chem/batplot
- **Issues**: https://github.com/tiandai-chem/batplot/issues
- **PyPI**: https://pypi.org/project/batplot/

For questions or contributions, please open an issue or pull request on GitHub.

---

**Last Updated**: November 4, 2025  
**Version**: 1.4.9
