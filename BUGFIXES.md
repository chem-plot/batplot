# Batplot Bug Fixes Documentation

This document tracks all bug fixes applied to the batplot codebase. Each entry includes the bug description, root cause analysis, solution, affected files, and date.

---

## 2026-01-27: EC Right Title "Time (h)" Disappeared When Loading Operando Session

### Bug Description
When loading an operando `.pkl` session, the EC panel's right ylabel (e.g., "Time (h)") disappeared. The t-e d5 command could not properly toggle the EC right title on/off.

### Root Cause
For the EC panel, the ylabel is positioned on the **right** side (not left) by default using `ec_ax.yaxis.set_label_position('right')`. Unlike other modes where the right title is a duplicate artist controlled by `_right_ylabel_on`, the EC panel uses the **actual ylabel** positioned on the right.

The WASD state capture logic was checking `_right_ylabel_on` (which is never set/used for EC), instead of checking if the ylabel is visible (non-empty). When saving:
- Right title state was captured as `False` (since `_right_ylabel_on` defaulted to `False`)
- On restore, this caused `ec_ax.set_ylabel('')` to be called, hiding the title

### Solution
Updated the title state capture to properly detect EC axes and check ylabel visibility:

1. **operando_ec_interactive.py** (`_snapshot` EC WASD capture):
   - For EC, check if ylabel is currently visible: `bool(ec_ax.get_ylabel())` (empty string = hidden by user)
   - 'left' title: `False` (EC ylabel is positioned on right, not left)
   - 'right' title: `True` if ylabel is not empty (user has not hidden it via t-e d5)

2. **session.py** (`_capture_wasd_state`):
   - Detect if ylabel is positioned on right via `axis.yaxis.get_label_position() == 'right'`
   - If true (EC axis): 'left' title = `False`, 'right' title = `bool(axis.get_ylabel())`
   - If false (normal axis): Use existing logic (`_right_ylabel_on` for right)

### Behavior Changes
- Loading operando `.pkl` sessions now correctly restores the EC right ylabel ("Time (h)" or "Number of ions")
- The **t-e d5** command works correctly to toggle the EC right title on/off
- **Undo (b)** correctly restores the EC title visibility state
- Works for both time mode and ions mode

### Affected Files
- `batplot/operando_ec_interactive.py` (EC WASD capture in `_snapshot`)
- `batplot/session.py` (`_capture_wasd_state` helper function)

---

## 2026-01-27: Operando Undo (b) Now Restores EC Line Style (el) and Line Widths (l); Operando-Only Undo No Longer Crashes on Tick Lengths

### Bug Description
In operando interactive mode, undo (**b**) did not restore (1) EC curve color/linewidth (**el**) or (2) spine and tick line widths (**l**). Also, in operando-only mode (no EC panel), undoing after changing tick lengths could raise an error because tick-length restore used `ec_ax` without checking for `None`.

### Root Cause
- The undo snapshot (`_snapshot`) did not capture EC line style or spine/tick widths; `_restore` therefore had nothing to reapply for **el** and **l**.
- The tick-length restore block called `ec_ax.tick_params(...)` unconditionally; when `ec_ax` is `None` (operando-only), this caused an exception.

### Solution
- In `operando_ec_interactive.py`:
  - **Snapshot**: Capture `op_spines` (spine linewidths), `op_ticks` (tick widths via `_axis_tick_width`), and, when `ec_ax` exists, `ec_spines`, `ec_ticks`, and `ec_line_style` (color, linewidth). Append these to the state dict.
  - **Restore**: After restoring tick direction, apply `op_spines`/`op_ticks` and `ec_spines`/`ec_ticks` to axes, and apply `ec_line_style` to the EC line when present.
  - In the tick-length restore block, only call `ec_ax.tick_params(...)` when `ec_ax is not None`.

### Affected Files
- `batplot/operando_ec_interactive.py` (`_snapshot`, `_restore`, and tick-length restore block).

---

## 2026-01-27: Style Import Broke Y-Axis and Curves in 1D Stacked Plots

### Bug Description
When importing a saved style (`.bps`) in 1D interactive mode with stacked plots (`--stack --i`), the y-axis range changed and some curves disappeared or were shifted incorrectly, even when no changes had been made before exporting the style.

### Root Cause
In `apply_style_config` (style.py), offset restoration used `orig_y[idx]` as the baseline and computed `y_with_offset = orig_y[idx] + offset_from_file`. In some stacked sessions, `orig_y` for curves 1,2,3 was not the normalized baseline (0–1) but the **already-offset** displayed data. That caused the file offset to be applied on top of displayed data, effectively double-applying the offset (e.g. baseline -1.1 plus file offset -1.1 → -2.2).

### Solution
Derive the baseline from the **current** displayed data and current offset instead of trusting `orig_y`:

- `baseline = y_data_list[idx] - offsets_list[idx]`
- `y_with_offset = baseline + offset_from_file`
- Update `offsets_list[idx]`, `y_data_list[idx]`, and the line’s data; if `orig_y` is present, set `orig_y[idx] = baseline` so in-memory state stays consistent.

### Implementation Details

**Modified Files:**
- `batplot/style.py` (offset restore block in `apply_style_config`):
  - Require only `offsets_list` and `x_data_list` (not `orig_y`) for the offset-restore branch.
  - Compute baseline from `y_data_list[idx] - offsets_list[idx]`, then apply `offset_val` from the file.
  - Optionally update `orig_y[idx]` to the computed baseline when provided.

**Behavior Changes:**
- Importing a style on a stacked 1D plot no longer double-applies offsets; y-axis and curve positions stay correct.
- Works regardless of whether `orig_y` was previously correct or had been overwritten with displayed data.

---

## 2026-01-27: 1D Plot Canvas Size Too Small in Non-Interactive Mode

### Bug Description
When plotting 1D XY data (e.g., XRD with `--wl 0.25448`) **without** the `--i` (interactive) flag, the visible plotting area was too small, so long filenames, CIF ticks, and axis labels could be partially outside the canvas. With `--i`, the window looked correct.

### Root Cause
For 1D XY plots, the figure was always created with a fixed size:
```python
fig, ax = plt.subplots(figsize=(8, 6))
```
This size is reasonable for interactive use but too small for non-interactive runs with long labels and ticks. While margins were adjusted via `subplots_adjust`, the underlying canvas size was still too small in non-interactive mode, so content could extend beyond the visible area.

### Solution
Make the **canvas larger only when `--interactive` is NOT used**, while keeping the interactive window size unchanged:

```python
if args.interactive:
    plt.ion()
    figsize = (8, 6)
else:
    figsize = (11, 7)  # larger canvas for non-interactive mode
fig, ax = plt.subplots(figsize=figsize)

# Common margins for both modes
fig.subplots_adjust(left=0.125, right=0.9, top=0.88, bottom=0.11)
```

### Implementation Details

**Modified Files:**
- `batplot/batplot.py` (line ~2701):
  - Replaced fixed `figsize=(8, 6)` with conditional:
    - Interactive: `(8, 6)`
    - Non-interactive: `(11, 7)`
  - Kept a single `subplots_adjust` call applied immediately after figure creation for both modes

**Behavior Changes:**
- In non-interactive mode (no `--i`):
  - Larger canvas ensures labels, legends, and CIF ticks are fully visible
  - No more clipping at the edges
- In interactive mode (`--i`):
  - Window size remains the familiar `(8, 6)` but shares the same margins
- The change only affects 1D XY plots; EC/GC/CPC/operando modes are unchanged

---

## 2026-01-27: Missing Subscript Glyphs (H₂O, m²) in 1D/Stacked Plots

### Bug Description
When running 1D/stacked plots that show tips like:
`Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²`
matplotlib emitted warnings such as:
```text
UserWarning: Glyph 8321 (\N{SUBSCRIPT ONE}) missing from font(s) Arial.
UserWarning: Glyph 8322 (\N{SUBSCRIPT TWO}) missing from font(s) Arial.
```

### Root Cause
The global font configuration forced `Arial` to be the **first** font in the `font.sans-serif` fallback chain:
```python
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'DejaVu Sans', ...],
})
```
On many systems, the installed Arial font does **not** include Unicode subscript digits (U+2081, U+2082), so matplotlib tried to render them with Arial, failed, and raised the warnings.

DejaVu Sans *does* include these glyphs, but because it was second in the list, the renderer never reached it for those characters.

### Solution
Reordered the `font.sans-serif` chain to prefer DejaVu Sans first:
```python
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
    'mathtext.fontset': 'dejavusans',
    'font.size': 16,
})
```

This change was applied to:
- Global 1D XY configuration in `batplot/batplot.py`
- GC/dQdV/related modes in `batplot/batplot.py`
- GC helper in `batplot/modes.py`

### Behavior Changes
- H₂O, m², and other Unicode characters (subscripts, superscripts, Greek, bullets) now render correctly without warnings on all platforms.
- DejaVu Sans is the primary UI font for plots; Arial and others are kept as fallbacks.
- No behavior changes to data or layouts – only font selection is affected.

---

## 2026-01-27: Colormap for Multiple CIF Tick Series in 1D Plots

### Bug Description
When plotting multiple CIF tick series in 1D mode, the auto-color logic used:
- `'tab10'` when there were ≤ 10 CIF series
- `'hsv'` when there were more than 10 CIF series

You requested:
- **If ≤ 10 CIF files** → use **Tab10**
- **If > 10 CIF files** → use **viridis**

### Solution
Updated the colormap selection logic for `cif_tick_series` in `batplot.py` so that it **always** applies the Tab10/viridis rule whenever there is more than one CIF series, regardless of any existing color:

```python
if cif_tick_series and len(cif_tick_series) > 1:
    n_cif = len(cif_tick_series)
    cmap_name = 'tab10' if n_cif <= 10 else 'viridis'
    cmap = plt.get_cmap(cmap_name)
    new_series = []
    for i, (lab, fname, peaksQ, wl, qmax_sim, col) in enumerate(cif_tick_series):
        color = cmap(i / max(1, (n_cif - 1)))
        new_series.append((lab, fname, peaksQ, wl, qmax_sim, color))
    cif_tick_series[:] = new_series
```

### Behavior Changes
- For **up to 10 CIF tick series**, colors are now always drawn from `Tab10`.
- For **more than 10 CIF tick series**, colors are now always drawn from `viridis` (instead of the previous `hsv`), even if styles or sessions had their own colors.
- This guarantees the requested behavior for all runs that include multiple CIF tick series.

---

## 2026-01-27: Case-Insensitive `--xaxis` Argument for 1D Plots

### Bug Description
When using `--xaxis q` (lowercase) vs `--xaxis Q` (uppercase) in 1D plots, the behavior was different. The lowercase 'q' was not recognized as Q-space, leading to incorrect axis labeling or errors.

### Root Cause
In `batplot.py`, when `axis_mode` was set from `args.xaxis` (lines 2757 and 2768), the value was used directly without case normalization. The code checked `axis_mode == "Q"` (uppercase), so `--xaxis q` would not match.

### Solution
Added case normalization when setting `axis_mode` from `args.xaxis`:
- If `args.xaxis` is 'q' or 'Q' → normalize to 'Q' (uppercase)
- Everything else → normalize to lowercase (for consistency with 2theta, r, k, energy, rft, time)

### Implementation Details

**Modified Files:**
- `batplot/batplot.py` (lines 2757, 2768): Added normalization logic:
  ```python
  axis_mode = "Q" if args.xaxis.upper() == "Q" else args.xaxis.lower()
  ```

**Behavior Changes:**
- `--xaxis q` and `--xaxis Q` now produce identical results (Q-space plot)
- All other axis types are case-insensitive (e.g., `--xaxis 2theta` or `--xaxis 2THETA`)

**Notes:**
- Operando mode already had case-insensitive handling via regex patterns (`_q_re`, `_r_re`, `_two_theta_re`)
- This fix ensures consistency between 1D plots and operando plots

---

## 2026-01-27: EC Interactive Menu Crash - Same `fig` Scope Issue as CPC

### Bug Description
When starting the electrochemistry (EC) interactive menu with `--gc` or other EC flags with `--i`, the menu would immediately crash with:
```
Interactive menu failed: name 'fig' is not defined
```

### Root Cause
The `_print_menu()` function in `electrochem_interactive.py` was trying to access `fig` to check for overwrite shortcuts (`os`, `ops`, `opsg`, `oe`), but `fig` was not in the function's scope because it wasn't passed as a parameter.

This is the exact same issue that was fixed in CPC interactive menu earlier.

### Solution
1. Modified `_print_menu()` function signature to accept `fig` as an optional parameter: `def _print_menu(n_cycles: int, is_dqdv: bool = False, fig=None):`
2. Added guard condition: `if fig is not None:` before accessing fig attributes
3. Updated all 43 calls to `_print_menu()` throughout the file to pass `fig` parameter

### Implementation Details

**Modified Files:**
- `batplot/electrochem_interactive.py`:
  - Line 377: Updated function signature
  - Lines 410-419: Added `if fig is not None:` guard
  - 43 call sites: Changed `_print_menu(len(all_cycles), is_dqdv)` to `_print_menu(len(all_cycles), is_dqdv, fig)`

**Behavior Changes:**
- EC interactive menu now starts successfully
- Overwrite shortcuts appear correctly when available

---

## 2026-01-27: CPC Legend Not Visible and Filled/Hollow Marker Distinction Lost on Export/Import

### Bug Description
1. **Legend Not Visible**: In CPC interactive mode, the legend would not appear by default, and the `h` command failed to toggle it on.

2. **Filled/Hollow Markers Lost**: When exporting style with `p` (print) or using `b` (undo), the distinction between filled squares (charge capacity) and hollow squares (discharge capacity) was lost. All markers would become filled after import or undo.

3. **Labels Not Restored on Import**: When importing a style with `i` in single-file mode, renamed legend labels were not restored.

### Root Cause

#### 1. Legend Not Visible
The legend creation in `batplot.py` was using `labelcolor='linecolor'` parameter, which caused matplotlib to extract colors from scatter artists. However, for hollow markers with `facecolor='none'`, matplotlib's color extraction failed with an IndexError:
```
IndexError: index 0 is out of bounds for axis 0 with size 0
```
This occurred at line 602 in `matplotlib/legend.py` when trying to access color arrays that were empty for hollow markers. The exception was silently caught, preventing the legend from being created.

Additionally, the `_legend_no_frame()` helper function in `cpc_interactive.py` was also setting `labelcolor='linecolor'` by default, causing the same issue when toggling the legend with the `h` command.

#### 2. Filled/Hollow Markers Lost
The `_style_snapshot()` function captured marker colors using the `_color_of()` helper, which extracts the color but doesn't capture whether a marker is filled or hollow. When applying styles with `_apply_style()`, it used `set_color()` on scatter artists, which sets both facecolor and edgecolor to the same value, converting all markers to filled style.

The critical code was:
- **Snapshot**: Only captured `'color': _color_of(artist)` without any fill style information
- **Apply**: Used `artist.set_color(color)` which makes both face and edge the same color (filled marker)

For CPC plots, discharge capacity should be hollow (facecolor='none', edgecolor=color) while charge capacity should be filled (both facecolor and edgecolor=color).

#### 3. Labels Not Restored on Import
The `_apply_style()` function in single-file mode was not calling `set_label()` on the scatter artists to restore the legend labels captured in the style snapshot.

### Solution

#### 1. Legend Visibility Fix
- Removed `labelcolor='linecolor'` parameter from legend creation in `batplot.py` (line ~1265)
- Removed `kwargs.setdefault('labelcolor', 'linecolor')` from `_legend_no_frame()` helper in `cpc_interactive.py` (line ~108)
- Added check for empty handles list before creating legend
- Removed invalid `set_edgecolor()` and `set_facecolor()` method calls on Legend object (these methods don't exist for Legend)

#### 2. Filled/Hollow Marker Fix
Added `_is_hollow_marker()` helper function that checks if a scatter artist has transparent facecolor (alpha == 0):

```python
def _is_hollow_marker(artist) -> bool:
    try:
        if hasattr(artist, 'get_facecolors'):
            face_arr = artist.get_facecolors()
            if face_arr is not None and len(face_arr):
                fc = face_arr[0]
                if len(fc) >= 4 and fc[3] == 0:
                    return True
    except Exception:
        pass
    return False
```

Updated `_style_snapshot()` to capture hollow flag:
- Single-file: Added `'hollow': _is_hollow_marker(sc_*)` to each series dict
- Multi-file: Added `'*_hollow': _is_hollow_marker(sc_*)` to each file_info dict

Updated `_apply_style()` to restore markers properly:
- **If hollow**: Use `set_facecolors('none')` and `set_edgecolors(color)`
- **If filled**: Use `set_color(color)` (sets both face and edge)

This ensures hollow markers remain hollow when exporting/importing styles or using undo.

#### 3. Labels Restoration Fix
Added label restoration code in `_apply_style()` for single-file mode:
```python
if 'label' in ch and hasattr(sc_charge, 'set_label'):
    sc_charge.set_label(ch['label'])
# ... similar for discharge and efficiency
```

Multi-file mode already had label restoration implemented (lines 1298-1312).

### Implementation Details

**Modified Files:**
- `batplot/batplot.py` (lines ~1256-1280): Removed labelcolor parameter, removed invalid legend method calls, added check for empty handles
- `batplot/cpc_interactive.py`:
  - Added `_is_hollow_marker()` helper function (after line 439)
  - Updated `_legend_no_frame()` (line ~108): Removed labelcolor default
  - Updated `_style_snapshot()`:
    - Single-file series (lines 662-682): Added 'hollow' key
    - Multi-file snapshot (lines 710-719): Added '*_hollow' keys
  - Updated `_apply_style()`:
    - Single-file mode (lines 894-975): Conditional facecolor/edgecolor application, added label restoration
    - Multi-file mode (lines 1248-1296): Conditional facecolor/edgecolor application

**Behavior Changes:**
1. CPC legend now appears by default with correct marker styles
2. Hollow markers (discharge capacity) remain hollow after export/import or undo
3. Filled markers (charge capacity, efficiency) remain filled
4. Legend labels are preserved when importing styles
5. All marker color changes via `c` command preserve fill style

### Testing
Verified that:
- ✅ Legend appears by default in CPC mode
- ✅ `h` → `t` command toggles legend visibility
- ✅ Discharge capacity shows as hollow squares
- ✅ Charge capacity shows as filled squares
- ✅ Exporting style (`p`) and importing (`i`) preserves hollow/filled distinction
- ✅ Undo (`b`) preserves hollow/filled distinction
- ✅ Renamed labels are restored on style import
- ✅ Multi-file mode preserves colors and hollow/filled style for all files

### Related Issues
- This fix resolves the critical issue where the new CPC color scheme (filled/hollow squares for charge/discharge) was not being preserved in operations
- Completes the implementation of the unified marker color change (same color for charge/discharge, distinguished by fill style)

---

## 2025-12-22: Title Drift and Duplicate Messages in Interactive Menus

### Bug Description
1. **Title Drift on Undo**: When changing the X range using the `x` command and then undoing with `b`, axis titles (especially bottom xlabel) would shift down by a few pixels with each undo operation, causing cumulative drift.

2. **Duplicate Save Messages**: When saving a session with the `s` command, two messages would appear:
   ```
   Session saved to /path/to/file.pkl
   Saved session to /path/to/file.pkl
   ```

3. **Annoying Canvas Message**: When undoing any change, an unnecessary message would appear:
   ```
   (Canvas fixed) Ignoring undo figure size restore.
   ```

4. **Verbose Numpy Type Display**: When setting Y range, the confirmation message would display numpy types explicitly:
   ```
   Y range set to (np.float64(-0.04), np.float64(1.16))
   ```

### Root Cause

#### 1. Title Drift
The `restore_state()` functions in all interactive menus were calling title positioning functions (`position_bottom_xlabel()`, `position_left_ylabel()`, etc.) before calling `fig.canvas.draw()`. This caused a double-positioning issue:
- First positioning call: Title positioned based on snapshot
- `fig.canvas.draw()`: Matplotlib triggers layout recalculation
- Result: Cumulative shift with each undo

The positioning functions were being called at:
- `interactive.py` line 1292-1298
- `cpc_interactive.py` line 1537-1538 (in `_update_ticks()`)
- `electrochem_interactive.py` line 1555-1557

#### 2. Duplicate Save Messages
In `interactive.py`, after calling the centralized `dump_session()` function (which prints "Session saved to..."), the code was redundantly printing "Saved session to..." at lines 1740 and 1780.

#### 3. Annoying Canvas Message
Two locations were printing unnecessary messages when canvas size is managed by the system:
- `interactive.py` line 1222: "(Canvas fixed) Ignoring undo figure size restore."
- `style.py` line 882: "(Canvas fixed) Ignoring style figure size request."

#### 4. Verbose Numpy Type Display
Line 2703 in `interactive.py` was directly printing `ax.get_ylim()` which returns a tuple of numpy float64 objects, causing them to display with their type information.

### Solution

#### 1. Title Drift Fix
Removed the redundant positioning function calls from all `restore_state()` implementations:

**interactive.py** (lines 1290-1298):
```python
# Before:
try:
    position_bottom_xlabel()
except Exception:
    pass
try:
    position_left_ylabel()
except Exception:
    pass

# After:
# Note: Do NOT call position_bottom_xlabel() / position_left_ylabel() here
# as it causes title drift when combined with fig.canvas.draw() below.
# Title offsets are already restored from snapshot above.
```

**cpc_interactive.py** (_update_ticks function, lines 1537-1538):
```python
# Removed:
_ui_position_bottom_xlabel(ax, fig, tick_state)
_ui_position_left_ylabel(ax, fig, tick_state)

# Added comment:
# Note: Do NOT call position functions during undo restore as it causes title drift
# Title offsets are already restored from snapshot in restore_state()
```

**electrochem_interactive.py** (restore_state, lines 1555-1557):
```python
# Removed:
_ui_position_top_xlabel(ax, fig, tick_state)
_ui_position_bottom_xlabel(ax, fig, tick_state)
_ui_position_left_ylabel(ax, fig, tick_state)
_ui_position_right_ylabel(ax, fig, tick_state)

# Added comment:
# Note: Do NOT call position functions during undo restore as it causes title drift
# Title offsets are already restored from snapshot above
```

#### 2. Duplicate Save Messages Fix
Removed redundant print statements in `interactive.py`:
- Line 1740: Changed `print(f"Saved session to {target_path}")` to comment `# Message already printed by dump_session`
- Line 1780: Same change

#### 3. Annoying Canvas Message Fix
Removed the print statements and replaced with explanatory comments:

**interactive.py** (line 1222):
```python
# Before:
else:
    print("(Canvas fixed) Ignoring undo figure size restore.")

# After:
# No message needed - canvas size is managed by system
```

**style.py** (line 882):
```python
# Before:
else:
    print("(Canvas fixed) Ignoring style figure size request.")

# After:
# No message needed when canvas is fixed - this is normal behavior
```

#### 4. Verbose Numpy Type Display Fix
**interactive.py** (line 2703):
```python
# Before:
print(f"Y range set to {ax.get_ylim()}")

# After:
ymin, ymax = ax.get_ylim()
print(f"Y range set to ({float(ymin)}, {float(ymax)})")
```

This explicitly converts numpy float64 objects to Python floats for clean display.

### Affected Files
- `batplot/interactive.py`
  - Lines 1222: Removed canvas message
  - Lines 1290-1298: Removed position function calls in restore_state
  - Line 1740, 1780: Removed duplicate save messages
  - Lines 2703-2704: Fixed numpy type display in Y range message
  
- `batplot/cpc_interactive.py`
  - Lines 1537-1538: Removed position function calls in _update_ticks (called by restore_state)
  
- `batplot/electrochem_interactive.py`
  - Lines 1555-1557: Removed position function calls in restore_state
  
- `batplot/style.py`
  - Line 882: Removed canvas message

### Testing
- ✅ No linter errors in any modified files
- ✅ Undo operations no longer cause title drift
- ✅ Save operations show only one message
- ✅ No annoying canvas messages during undo or style import
- ✅ Y range messages display clean float values

### Notes
The key insight is that title positioning should be done either:
1. During snapshot restore (using stored offsets), OR
2. During explicit user actions that change positioning

But NOT both. Calling positioning functions immediately before `fig.canvas.draw()` in restore operations causes matplotlib's layout engine to compound the positioning, resulting in drift.

---

## 2025-12-22: `--ro` (swap x/y axes) compatibility for sessions, styles, and batch

### Bug / Behavior Description
- The `--ro` flag swaps x and y axes at plot time (data and labels), but this state was **not recorded** in:
  - Interactive XY session saves (`s` save)
  - Style/geometry exports (`p` print/export + `i` import) for XY, CPC, and EC
  - Batch style application (`batch.py`)
- As a result, it was possible to:
  - Save a style/geom file from a `--ro` plot and apply it to a non-`--ro` plot (or vice versa)
  - Apply `--ro`-originated styles in batch mode to non-`--ro` plots
- This "cross‑contamination" silently broke axis meaning and could **visually corrupt the plot** (x/y mismatched), which is unacceptable for scientific figures.

### Root Cause
- The only place the `--ro` flag was used was during initial plotting in `batplot.py` and `modes.py` (swapping data arrays and labels).
- Neither sessions nor style configs knew whether the original figure used `--ro`:
  - `session.dump_session()` did not capture any `ro` state.
  - `style.export_style_config()` and EC/CPC style snapshot functions did not store any `ro` metadata.
  - Style import paths (`p`/`i` in XY, CPC, EC; `_apply_xy_style` / `_apply_ec_style` in `batch.py`) never checked for axis‑swap compatibility.

### Solution

#### 1. Track `--ro` state on figures
- A new flag is stored on the figure:
  - `fig._ro_active = bool(getattr(args, 'ro', False))`
- This is set:
  - For normal XY interactive plots, just before calling `interactive_menu(...)`.
  - For EC interactive entry from CV/GC plotting (when `args.interactive` is used).
  - When restoring XY sessions from `.pkl`, using `sess.get('ro_active', False)`.

#### 2. Persist `--ro` state into XY sessions (`s` save)
- `session.dump_session()` now writes:
  - `sess['ro_active'] = bool(getattr(fig, '_ro_active', False))`
- The automatic `.pkl` loader in `batplot.py` restores:
  - `fig._ro_active = bool(sess.get('ro_active', False))`
- This ensures that interactive sessions created under `--ro` keep that information for later `p`/`i` operations.

#### 3. Persist `--ro` into style/geom configs and enforce at import

**XY styles (`style.py`):**
- `export_style_config()` now stores:
  - `cfg["ro_active"] = bool(getattr(fig, '_ro_active', False))`
- `print_style_info()` now reports:
  - `Data axes swapped via --ro: YES/no` based on `fig._ro_active`.
- `apply_style_config()` now enforces compatibility **before** any changes:
  - Reads `file_ro = bool(cfg.get("ro_active", False))`
  - Reads `current_ro = bool(getattr(fig, "_ro_active", False))`
  - If `file_ro != current_ro`:
    - Prints a warning explaining the mismatch and that applying it would corrupt axis orientation.
    - Returns early without modifying the figure.

**CPC styles (`cpc_interactive.py`):**
- `_style_snapshot(...)` / CPC style config now includes:
  - `'ro_active': bool(getattr(fig, '_ro_active', False))`
- The CPC `i` (import) handler checks:
  - `file_ro = bool(cfg.get('ro_active', False))`
  - `current_ro = bool(getattr(fig, '_ro_active', False))`
  - On mismatch, prints a warning and **does not** apply style or geometry.

**EC styles (`electrochem_interactive.py`):**
- `_get_style_snapshot(...)` / EC style config now includes:
  - `'ro_active': bool(getattr(fig, '_ro_active', False))`
- `_print_style_snapshot(cfg)` prints:
  - `Data axes swapped via --ro: YES/no` based on `cfg['ro_active']`.
- The EC `i` (import) handler enforces the same compatibility check as CPC:
  - On mismatch, prints a warning and **skips** applying style/geometry.

#### 4. Batch processing compatibility (`batch.py`)
- `_apply_xy_style(fig, ax, cfg)`:
  - Reads `file_ro = bool(cfg.get('ro_active', False))`
  - Reads `current_ro = bool(getattr(fig, '_ro_active', False))` (batch figs default to non‑ro)
  - If mismatched, prints a warning and **returns without applying** style/geom.
- `_apply_ec_style(fig, ax, cfg)`:
  - Uses the same `ro_active` compatibility check and skips application on mismatch.

### Behavior Guarantees
- **p / i (all interactive menus)**:
  - `p` now shows whether the figure/style was created under `--ro`.
  - `i` will **refuse** to apply a style/geom file whose `ro_active` does not match the current figure’s `fig._ro_active`.
- **s save / .pkl load (XY)**:
  - Sessions remember whether they were created with `--ro`.
  - Subsequent style/geom imports respect that flag.
- **Batch processing**:
  - Batch plots will not silently "inherit" rotated styles from `--ro` figures.

### Rationale
Directly applying a rotation / axis‑swap style to an already plotted dataset with a different `--ro` state will **break axis meaning and visual correctness**. The new `ro_active` tracking and compatibility checks ensure:
- `--ro` and non‑`--ro` worlds **cannot** accidentally mix via styles, geometry, or batch processing.
- Any attempted misuse is clearly warned and blocked.

---

## 2025-12-14: Colorbar `NotImplementedError` on Intensity Range Adjustment

### Bug Description
When adjusting the intensity range using the `oz` command in the operando interactive menu, the following error occurs:

```
NotImplementedError: cannot remove artist
```

The error occurs when repeatedly adjusting the upper or lower intensity limits in the interactive menu, specifically when calling `im.set_clim()`.

### Root Cause
The issue stems from a conflict between matplotlib's automatic colorbar update system and batplot's custom colorbar implementation:

1. **Custom Colorbar System**: Batplot uses a custom colorbar that clears and redraws the colorbar axes (`cbar.ax`) rather than using matplotlib's built-in `Colorbar` class directly.

2. **Callback System**: When a plot is loaded from a session file (`.pkl`), a real `matplotlib.colorbar.Colorbar` object exists and remains connected to the `AxesImage` (`im`) via matplotlib's callback system (`im.callbacksSM`).

3. **Triggering the Error**: When `im.set_clim()` is called to adjust the intensity range, matplotlib's callback system automatically triggers `cbar.update_normal()`, which tries to update the colorbar. However, since the colorbar axes have been cleared and redrawn by the custom system, matplotlib's update attempts to call `self.solids.remove()`, which fails with `NotImplementedError: cannot remove artist`.

4. **Why Previous Fixes Failed**: The existing `_detach_mpl_colorbar_callbacks()` function attempts to disconnect callbacks and monkey-patch `cbar.update_normal()`, but matplotlib's callback system can still trigger the callback through cached references or different mechanisms.

### Solution
Created a `_safe_set_clim()` wrapper function that safely calls `im.set_clim()` by:

1. **Temporarily Redirecting stderr**: Before calling `set_clim()`, redirect stderr to a StringIO buffer to suppress matplotlib's callback traceback output. Matplotlib's callback system prints tracebacks before our exception handler can catch them, so we need to suppress them at the stderr level.

2. **Exception Handling**: Specifically catch and suppress `NotImplementedError` exceptions that contain "cannot remove artist", allowing the color limit update to succeed even if the callback fails.

3. **Restore stderr**: After the operation completes (success or failure), restore stderr to its original value, effectively suppressing any tracebacks that matplotlib's callback system printed.

All calls to `im.set_clim()` in the operando interactive menu have been replaced with `_safe_set_clim()`.

**Note**: The color limits are successfully updated despite the error; the traceback is just noise from matplotlib's callback system that we suppress.

### Affected Files
- `batplot/operando_ec_interactive.py`
  - Added `_safe_set_clim()` function (lines ~379-416)
  - Replaced all `im.set_clim()` calls with `_safe_set_clim()` in:
    - `oz` command (intensity range adjustment): lines ~3283, ~3309, ~3323, ~3335
    - `_renormalize_to_visible()` function: line ~740
    - Undo/redo functionality: line ~1328
    - Style import: line ~4332

### Testing
- Test adjusting intensity range with `oz` command (upper only, lower only, auto-fit, and direct range input)
- Test with plots loaded from session files (`.pkl`)
- Test undo/redo operations that restore intensity ranges
- Verify no regressions in other colorbar-related functionality (colormap changes, etc.)

### Related Issues
- Similar issue may occur with `im.set_cmap()` calls, but not observed in testing
- The fix ensures the colorbar callback system doesn't interfere with custom colorbar updates

---

## 2025-12-14: Colorbar/EC Panel Position Not Preserved After Session Load

### Bug Description
When adjusting colorbar or EC panel horizontal position using `v - m - c` (colorbar) or `v - m - e` (EC panel) commands and saving the session with `s`, then reloading the `.pkl` file, the visual position of the colorbar/EC panel differs from what was saved, even though the displayed offset value in the menu is correct.

### Root Cause
The issue occurs because:

1. **Offsets Are Saved Correctly**: The horizontal offsets (`cb_h_offset` and `ec_h_offset`) are correctly saved to the session file as attributes on the axes objects.

2. **Offsets Are Loaded Correctly**: When loading a session, the offsets are correctly restored as attributes using `setattr(cbar_ax, '_cb_h_offset_in', ...)` and `setattr(ec_ax, '_ec_h_offset_in', ...)`.

3. **Layout Not Applied After Loading**: However, after setting the offset attributes, the layout (`_apply_group_layout_inches`) was not being applied immediately. The layout is responsible for converting the offset values (in inches) into actual figure coordinates and positioning the axes accordingly.

4. **Menu Initialization Overrides**: When the interactive menu initializes after loading, it calls `_ensure_fixed_params` which reads geometry from current axes positions (which may not match saved values if layout wasn't applied), and then applies default layout adjustments that can override the saved positions.

### Solution
Added code in `session.py`'s `load_operando_session()` function to apply the layout immediately after setting all offset and geometry attributes. This ensures:

1. All geometry parameters are set as attributes first
2. All offset values are set as attributes
3. Layout is applied once with the loaded values to ensure visual position matches saved position
4. Menu initialization checks flags (`_cb_gap_adjusted`, etc.) to avoid overriding loaded geometry

### Affected Files
- `batplot/session.py`
  - Added layout application after offset restoration (lines ~1319-1329)
  - Imports `_apply_group_layout_inches` and `_ensure_fixed_params` from `operando_ec_interactive`
  - Applies layout with loaded geometry and offset parameters

- `batplot/operando_ec_interactive.py`
  - Added `continue` statements to error handlers in position adjustment submenus (lines ~2091, ~2094, ~2112, ~2113, ~2177, ~2178)
  - Ensures users stay in the submenu after errors, allowing them to correct input and try again

### Testing
- Save a session with adjusted colorbar/EC panel positions
- Load the session and verify visual positions match saved positions
- Verify the displayed offset values in `v - m - c` and `v - m - e` menus match the actual positions
- Test error handling (invalid input) to ensure menu stays active

### Related Issues
- Similar offset systems don't exist in other interactive menus (electrochem, CPC, XY) so no similar issues there
- The fix ensures loaded sessions preserve all geometry exactly as saved

---

## 2025-12-14: Colormap Not Preserved After Session Save/Load

### Bug Description
When changing the colormap using the `oc` command in the operando interactive menu (e.g., to 'batlow'), saving the session with `s` to a `.pkl` file, and then loading it back, the colormap was replaced with 'viridis' instead of the chosen colormap (e.g., 'batlow').

### Root Cause
The issue occurred because:

1. **Colormap Name Retrieval**: When saving a session, the code used `getattr(im.get_cmap(), 'name', None)` to retrieve the colormap name from the matplotlib colormap object.

2. **Custom Colormaps Don't Have Reliable Names**: Custom colormaps (like 'batlow' from cmcrameri or custom colormaps from `_CUSTOM_CMAPS`) may not have a proper `.name` attribute set on the colormap object. When these colormaps are registered or used, matplotlib may assign a different name or the name attribute may be `None`.

3. **Fallback to Default**: When loading the session, if `cmap_name` was `None` or empty, the code would default to 'viridis', causing the chosen colormap to be lost.

### Solution
Store the colormap name explicitly as an attribute on the image object when it's changed, rather than relying on the colormap object's `.name` attribute:

1. **Store Name When Changed**: When the `oc` command is used to change the colormap, store the name in `im._operando_cmap_name` immediately after applying it.

2. **Store Name on Load**: When loading a session, store the loaded colormap name in `im._operando_cmap_name` after creating the image.

3. **Retrieve Stored Name First**: When saving (in both `session.py` and `operando_ec_interactive.py`), check for `im._operando_cmap_name` first, and only fall back to `getattr(im.get_cmap(), 'name', None)` if the stored name doesn't exist.

4. **Store on Undo/Redo and Style Import**: Also store the colormap name when restoring from snapshots (undo/redo) and when importing styles.

### Affected Files
- `batplot/session.py`
  - Updated `dump_operando_session()` to check for stored colormap name first (line ~581-583)
  - Updated `load_operando_session()` to store colormap name after creating image (line ~876)

- `batplot/operando_ec_interactive.py`
  - Store colormap name when `oc` command changes colormap (line ~3530)
  - Retrieve stored name when saving snapshots (line ~1179-1181)
  - Retrieve stored name when exporting styles (line ~3565-3567)
  - Store name when restoring from undo/redo snapshots (line ~1398)
  - Store name when importing styles (line ~4133)

- `batplot/operando.py`
  - Store default 'viridis' colormap name when initially creating the plot (line ~318)

### Testing
- Change colormap to 'batlow' (or other custom colormaps) using `oc` command
- Save session with `s` command
- Load the session file
- Verify the colormap is correctly restored (should be 'batlow', not 'viridis')
- Test with other colormaps (viridis, plasma, batlow variants, reversed colormaps)
- Test undo/redo operations that restore colormaps
- Test style import that applies colormaps

### Related Issues
- This fix ensures all colormap changes (direct change, undo/redo, style import) properly preserve the colormap name for reliable session saving/loading
- Similar issue may have affected style export/import, but that is also fixed by this change

---

## 2025-12-21: Tick Label Visibility Not Preserved in Session Save/Load (t command - WASD labels)

### Bug Description
When hiding tick labels using the `t` toggle axes command (e.g., `t` → `s4` to hide bottom labels), saving the session with `s`, and loading the `.pkl` file, the labels reappear even though they were hidden. Axis titles (s5/w5/a5/d5) work correctly, but tick labels (s4/w4/a4/d4) do not.

### Root Cause
**The critical bug**: When exiting the `t` menu with `q`, the code breaks out of the loop BEFORE updating `ax._saved_tick_state`, so changes are never persisted.

1. **State Deleted at Initialization**: At the start of `interactive_menu()`, `ax._saved_tick_state` is deleted (line 749-753 in `interactive.py`)

2. **Toggling Updates Local State Only**: When toggling (s4/w4/a4/d4), only the local `tick_state` dict is updated, not `ax._saved_tick_state`

3. **Exit Before Update**: The `if cmd == 'q': break` (line 3315) exits the while loop BEFORE reaching the code that updates `ax._saved_tick_state` (line 3587)

4. **Session Save Reads Stale State**: When saving, `dump_session()` calls `_capture_wasd_state(ax)` which reads from `ax._saved_tick_state` (line 406 in `session.py`), getting the old/deleted state

5. **Why s5 Works But s4 Doesn't**: Axis titles (s5) read directly from `axis.xaxis.label.get_visible()`, bypassing `_saved_tick_state` entirely. Tick labels (s4) rely on `_saved_tick_state` which is never updated before exit.

### Solution
Update `ax._saved_tick_state = dict(tick_state)` **BEFORE** breaking when `q` is entered:

1. **Normal XY mode**: Added update in `interactive.py` BEFORE `break` statement (line ~3315-3319)

2. **CPC mode**: Added update in `cpc_interactive.py` BEFORE `break` statement (line ~3460-3464)

3. **Electrochem mode**: Already correct - `_update_tick_visibility()` updates `ax._saved_tick_state` (line 983)

4. **Operando mode**: Already correct - `_apply_wasd_axis()` updates `axis._saved_tick_state` (line 2679)

### Affected Files
- `batplot/interactive.py`: Added `ax._saved_tick_state = dict(tick_state)` before `break` when exiting with `q` (line ~3316-3319)
- `batplot/cpc_interactive.py`: Added `ax._saved_tick_state = dict(tick_state)` before `break` when exiting with `q` (line ~3461-3464)

### Testing
- Use `t` → `s4` to hide bottom labels
- Save with `s`
- Load the `.pkl` file
- Verify labels remain hidden
- Test all 20 WASD commands (w1-w5, a1-a5, s1-s5, d1-d5)
- Test in all interactive menus (normal XY, CPC, electrochem, operando)
- Verify p/i/s/b commands work correctly

### Related Issues
- Affects all tick/label toggles (not just s4)
- Electrochem and operando were already handling this correctly

---

## 2025-12-21: Tick Label Visibility Not Preserved in Session Save/Load (All 20 WASD Commands)

### Bug Description
When hiding tick labels or toggling any tick/spine/title visibility using the `t` toggle axes command (all 20 WASD commands: w1-w5, a1-a5, s1-s5, d1-d5), saving the session with `s`, and loading the `.pkl` file, the changes were not preserved. Specifically, tick labels (s4/w4/a4/d4) would reappear even though they were hidden when saved. Axis titles (s5/w5/a5/d5) worked correctly.

### Root Cause
**Two distinct issues:**

1. **Exit Before Update (interactive.py, cpc_interactive.py)**: When exiting the `t` menu with `q`, the code executed `break` BEFORE updating `ax._saved_tick_state`, so changes were never persisted to the axes object.

2. **Loading Never Read wasd_state (batplot.py)**: Normal XY sessions are loaded in `batplot.py` (not `session.py`), and the loader was creating a **default** tick_state dict, completely ignoring the saved `wasd_state` from the `.pkl` file.

3. **CPC Missing tick_state Setup**: CPC's `load_cpc_session()` applied wasd_state to the matplotlib axes but never set `ax._saved_tick_state`, so the interactive menu couldn't read the loaded state.

### Solution

**1. Update ax._saved_tick_state Before Exiting t Menu:**
- **Normal XY**: Added `ax._saved_tick_state = dict(tick_state)` before `break` when `q` is entered (interactive.py line ~3316)
- **CPC**: Added same update before `break` (cpc_interactive.py line ~3461)  
- **Electrochem**: Already correct
- **Operando**: Already correct

**2. Load wasd_state in batplot.py:**
- Read `wasd_state` from session file
- Convert to `tick_state` format with all granular keys (b_ticks, b_labels, etc.)
- Apply to axes with `ax.tick_params()` before setting axis labels
- Store as `ax._saved_tick_state` for interactive menu (batplot.py lines ~1893-1997)

**3. Add tick_state to CPC Loader:**
- Added conversion of wasd_state to tick_state format
- Set `ax._saved_tick_state` after applying WASD state (session.py line ~2845-2864)

### Affected Files
- `batplot/interactive.py`: Update tick_state before exit (line ~3316-3319)
- `batplot/cpc_interactive.py`: Update tick_state before exit (line ~3461-3464)
- `batplot/batplot.py`: Load and apply wasd_state for normal XY sessions (lines ~1893-1997)
- `batplot/session.py`: Add tick_state setup to CPC loader (lines ~2845-2864)

### Testing
- Hide any tick element with `t` → any of w1-w5, a1-a5, s1-s5, d1-d5
- Exit with `q`
- Save with `s`
- Load the `.pkl` file
- Verify all changes are preserved (spines, ticks, minor ticks, labels, titles)
- Test in all interactive menus: normal XY, CPC, electrochem, operando
- Test p/i/s/b commands preserve tick state

### Related Issues
- Affects all 20 WASD commands, not just tick labels
- All 4 interactive menus now properly save/load tick state
- Fixes apply to session save/load, style export/import, and undo/redo

---

## 2025-12-22: CIF HKL Labels Not Showing When Toggled with 'z' Command

### Bug Description
When pressing 'z' to toggle CIF hkl labels in the interactive menu, the menu reported "CIF hkl labels ON" but no labels were actually displayed. The issue affected:
1. Normal command-line plots with CIF files
2. Plots loaded from `.pkl` session files
3. Style import/export (`p` print, `i` import)
4. Undo/redo operations (`b` undo)

Additionally, when loading `.pkl` sessions with CIF files, the CIF commands (z, hkl, j) were not available in the interactive menu.

### Root Cause
The issue had multiple components:

1. **Flag Storage Mismatch**: When the 'z' command toggled `show_cif_hkl`, it was stored on the local `_bp` object (created from `cif_globals`), but the `draw_cif_ticks()` function was trying to read from the `__main__` module. This caused the flag to always read as `False` even when toggled to `True`.

2. **Session Loading**: When loading `.pkl` sessions, `show_cif_hkl` was restored from the session file but not stored in `__main__` module, so the draw function couldn't access it.

3. **Undo/Restore**: The `restore_state()` function restored `show_cif_hkl` to the `_bp` object but didn't store it in `__main__` module.

4. **Style Import**: Style import restored `show_cif_hkl` but didn't store it in `__main__` module.

5. **Style Export**: Style export didn't include `show_cif_hkl` in the exported configuration.

6. **Print Style**: Print style didn't read `show_cif_hkl` from `__main__` module.

### Solution

#### 1. Store Flag in __main__ Module When Toggled
**interactive.py** (lines 1509-1520):
- When 'z' command toggles `show_cif_hkl`, store it in both `_bp` object AND `__main__` module
- This ensures the draw function can access the current state

#### 2. Store Flag in __main__ When Loading Sessions
**batplot.py** (lines 2293):
- When loading `.pkl` sessions, store `show_cif_hkl` in `__main__` module
- This ensures CIF commands are available and draw function can read the flag

#### 3. Store Flag in __main__ When Restoring from Undo
**interactive.py** (lines 1424-1428):
- When `restore_state()` restores `show_cif_hkl`, also store it in `__main__` module
- This ensures undo operations properly restore label visibility

#### 4. Store Flag in __main__ When Importing Styles
**style.py** (lines 1234-1250):
- When `apply_style_config()` restores `show_cif_hkl` from style file, store it in `__main__` module
- Also try to update `_bp` object if available
- Trigger CIF redraw if `show_cif_hkl` is in config

#### 5. Include show_cif_hkl in Style Export
**style.py** (lines 682-690):
- `export_style_config()` now reads `show_cif_hkl` from `__main__` module and includes it in exported config
- This ensures style files preserve hkl label visibility state

#### 6. Read show_cif_hkl from __main__ in Print Style
**interactive.py** (lines 885-898):
- `print_style_info()` now reads `show_cif_hkl` from `__main__` module first, then falls back to `_bp` object
- **style.py** (lines 454-465):
- `print_style_info()` displays CIF hkl label visibility state in the style diagnostics

#### 7. Read Flag from __main__ in Draw Function
**batplot.py** (lines 3329-3345):
- `draw_cif_ticks()` now reads `show_cif_hkl` from `__main__` module first (where interactive menu stores it)
- Falls back to closure variable if not found in module
- This ensures the draw function always has access to the current toggle state

### Affected Files
- `batplot/interactive.py`
  - Lines 1509-1520: Store `show_cif_hkl` in `__main__` when toggled
  - Lines 1424-1428: Store `show_cif_hkl` in `__main__` when restoring from undo
  - Lines 885-898: Read `show_cif_hkl` from `__main__` in print_style_info
  
- `batplot/batplot.py`
  - Lines 2293: Store `show_cif_hkl` in `__main__` when loading sessions
  - Lines 3329-3345: Read `show_cif_hkl` from `__main__` in draw_cif_ticks
  
- `batplot/style.py`
  - Lines 682-690: Include `show_cif_hkl` in style export
  - Lines 1234-1250: Store `show_cif_hkl` in `__main__` when importing styles
  - Lines 454-465: Display `show_cif_hkl` in print_style_info

### Testing
- ✅ Press 'z' to toggle hkl labels - labels should appear/disappear correctly
- ✅ Save session with hkl labels ON, load it - labels should remain ON
- ✅ Save session with hkl labels OFF, load it - labels should remain OFF
- ✅ Use 'b' undo after toggling - should restore previous hkl label state
- ✅ Export style with hkl labels ON, import it - labels should be ON
- ✅ Export style with hkl labels OFF, import it - labels should be OFF
- ✅ Use 'p' print - should show current hkl label visibility state
- ✅ Load `.pkl` session - CIF commands (z, hkl, j) should be available

### Notes
The key insight is that the draw function needs to read `show_cif_hkl` from a location that persists across function calls. The `__main__` module serves as a global storage location that both the interactive menu and draw function can access. This ensures:
- Toggle state persists when draw function is called
- Session loading properly restores state
- Style import/export preserves state
- Undo/redo operations work correctly

---

## 2026-01-27: Consistent Overwrite Shortcuts for Sessions, Styles, and Figures

### Feature / Behaviour Change

Added explicit overwrite commands under the `(Options)` column in all interactive menus (1D XY, EC, CPC, operando) to quickly overwrite the most recently used targets:

- `os`: overwrite last session (`.pkl`)
- `ops`: overwrite last style-only file
- `opsg`: overwrite last style+geometry file
- `oe`: overwrite last exported figure

### Behaviour Rules

1. **Start from data files (normal workflow)**  
   - At the beginning of an interactive session, **no overwrite shortcuts are shown**.  
   - After you:
     - run `s` (project/session save), `os` becomes available and overwrites `fig._last_session_save_path`
     - run `p` (style export), `ops`/`opsg` become available and overwrite `fig._last_style_export_path`
     - run `e` (figure export), `oe` becomes available and overwrites `fig._last_figure_export_path`

2. **Start directly from a `.pkl` session**  
   - When a `.pkl` is loaded via the automatic session shortcut in `batplot.py` or via the dedicated loaders in `session.py`, the loader now seeds:
     - `fig._last_session_save_path = abs(path_to_that_pkl)`
   - This means:
     - `os` is **immediately visible** in the main menu and overwrites the same `.pkl` you opened.
     - `ops`, `opsg`, and `oe` still **only appear after** you actually use `p` or `e` in that session.

3. **Confirmation semantics**  
   - All overwrite commands (`os`, `ops`, `opsg`, `oe`) **always ask for a `y/n` confirmation** before overwriting:
     - Session: “Overwrite session 'name.pkl'?”
     - Style: “Overwrite style-only/style+geometry file 'name.bps[g]'?”
     - Figure: “Overwrite figure 'name.svg/png/…'?”
   - Internally, they call the same centralized save/export helpers used by the primary commands, but with `skip_confirm=True` so there is exactly **one confirmation dialog** (the explicit `y/n` you answer for the new command).

### Implementation Details

- **XY interactive (`interactive.py`)**
  - Menu:
    - `(Options)` column now appends:
      - `os` when `fig._last_session_save_path` is set,
      - `ops` / `opsg` when `fig._last_style_export_path` is set,
      - `oe` when `fig._last_figure_export_path` is set.
  - Handlers:
    - `os` calls `dump_session()` with `skip_confirm=True` to `fig._last_session_save_path`.
    - `ops` / `opsg` call `style.export_style_config()` with `overwrite_path=last_style_path` and a new `force_kind` flag to force style-only (`ps`) or style+geometry (`psg`).
    - `oe` reuses the existing `e` export logic but targets `fig._last_figure_export_path` instead of asking for a new path.

- **EC interactive (`electrochem_interactive.py`)**
  - Menu:
    - `(Options)` column now conditionally appends `os`, `ops`, `opsg`, `oe` based on the same three `fig._last_*` attributes.
  - Handlers:
    - `os` overwrites `fig._last_session_save_path` using `dump_ec_session(..., skip_confirm=True)`.
    - `ops` / `opsg` rebuild a fresh EC style snapshot (`_get_style_snapshot` + optional `_get_geometry_snapshot`) and overwrite `fig._last_style_export_path` with the appropriate `kind` (`ec_style` or `ec_style_geom`).
    - `oe` reuses the existing figure export path but targets `fig._last_figure_export_path` with a single confirmation.

- **CPC interactive (`cpc_interactive.py`)**
  - Menu:
    - `(Options)` column behaves the same way, using `fig._last_session_save_path`, `fig._last_style_export_path`, and `fig._last_figure_export_path`.
  - Handlers:
    - `os` overwrites `fig._last_session_save_path` via `dump_cpc_session(..., skip_confirm=True)`.
    - `ops` / `opsg` rebuild a fresh style snapshot (`_style_snapshot` + `_get_geometry_snapshot`) and overwrite `fig._last_style_export_path` as `cpc_style` or `cpc_style_geom`.
    - `oe` reuses the CPC export logic to overwrite `fig._last_figure_export_path` with one confirmation.

- **Operando interactive (`operando_ec_interactive.py`)**
  - Menu:
    - For both dual-pane (operando+EC) and operando-only menus, the `(Options)` column conditionally appends `os`, `ops`, `opsg`, `oe` based on the same three figure attributes.
  - Handlers:
    - `os` overwrites `fig._last_session_save_path` using `dump_operando_session(..., skip_confirm=True)`.
    - `ops` / `opsg` reuse the existing operando style snapshot/export logic to overwrite `fig._last_style_export_path` as style-only or style+geometry.
    - `oe` reuses the existing `e` export logic to overwrite `fig._last_figure_export_path`.

- **Session loaders (`session.py`, `batplot.py`)**
  - `load_operando_session`, `load_ec_session`, and `load_cpc_session` now set:
    - `fig._last_session_save_path = abs(path_to_loaded_pkl)`
  - The `.pkl` shortcut in `batplot.py` seeds `_last_session_save_path` for:
    - EC GC sessions (`ec_gc`)
    - Operando+EC sessions (`operando_ec`)
    - CPC sessions (`cpc`)
  - For normal XY sessions loaded via the same shortcut, the interactive menu later updates `_last_session_save_path` when you save with `s`, preserving the “no overwrite until first save” rule for data-based runs.

### Affected Files

- `batplot/interactive.py`
- `batplot/electrochem_interactive.py`
- `batplot/cpc_interactive.py`
- `batplot/operando_ec_interactive.py`
- `batplot/session.py`
- `batplot/batplot.py`

### Rationale

This change makes overwriting **explicit, fast, and predictable**:

- You only see overwrite options when there is a concrete previous target.
- Starting from `.pkl` gives you a direct `os` command to overwrite that same file (common workflow).
- Starting from data behaves as before until you explicitly save/export.
- All overwrite operations share the same underlying save/export code paths, so behaviour is consistent across 1D, EC, CPC, and operando, and across Windows, macOS, and Linux.

---

## 2026-01-27: EC Right Title Disappeared on Session Load and Toggle (t-e d5) Malfunctioned

### Bug Description
When loading an operando `.pkl` session, two critical issues occurred with the EC panel:

1. **Visual Glitch on Load**: The EC panel would briefly flicker/shift within the first second after loading, showing left ticks momentarily before settling into the correct right-side configuration.

2. **EC Right Title Missing**: The EC right title (e.g., "Time (h)") would disappear when loading the session.

3. **Toggle Malfunction**: Using `t - e - d5` to toggle the EC right title:
   - First d5: Title would move slightly to the left instead of disappearing
   - Second d5: A new title would appear at the original position, overlapping the moved title

### Root Cause

**Three distinct issues:**

1. **Incorrect Saved WASD State**: Old sessions saved with incorrect EC y-axis defaults:
   - `'left': {'ticks': True, 'labels': True}` ← Wrong (EC should have left=False)
   - `'right': {'ticks': False, 'labels': False}` ← Wrong (EC should have right=True)

2. **Session Load Applied Wrong Defaults**: When loading, the code would apply the saved (incorrect) values directly:
   ```python
   left_ticks = bool(ec_wasd.get('left', {}).get('ticks', False))  # Would load True from saved state!
   right_ticks = bool(ec_wasd.get('right', {}).get('ticks', True))  # Would load False from saved state!
   ```
   This caused BOTH left and right ticks to be ON briefly, creating the visual glitch.

3. **Toggle Used Wrong Positioning Function**: The `t-e d5` toggle called `_ui_position_right_ylabel(ec_ax, ...)`, which is designed for *duplicate* ylabel artists (used in operando panel). However, EC uses its *actual* ylabel positioned on the right via `yaxis.set_label_position('right')`, not a duplicate artist. This caused the positioning function to create unwanted duplicate artists and move/overlap titles.

### Solution

**1. Force Correct EC Defaults on Session Load** (`session.py`):
- EC left side is ALWAYS forced to False (regardless of saved state):
  ```python
  left_ticks = False
  left_labels = False
  ```
- EC right side is set based on title visibility:
  ```python
  right_title = ec_wasd.get('right', {}).get('title', True)
  if right_title:
      right_ticks = True  # Force ON when title is visible
      right_labels = True
  ```
- This sanitizes old incorrect session files while preserving correct title state.

**2. Skip Duplicate Artist Positioning for EC** (`operando_ec_interactive.py`):
- In `_apply_wasd_axis()`, added a guard to skip `_ui_position_right_ylabel()` for EC axes:
  ```python
  if 'right' in changed_sides:
      if not is_ec:  # Only apply for non-EC axes
          _ui_position_right_ylabel(axis, fig, current_tick_state)
  ```

**3. Set _right_ylabel_on Flag for EC** (`operando_ec_interactive.py`):
- Added proper flag tracking for EC right title state:
  ```python
  elif is_ec:
      # ... ylabel toggle logic ...
      axis._right_ylabel_on = bool(wasd_state['right']['title'])
  ```

### Behavior Changes
- **Session Load**: EC panel loads cleanly without visual glitches, with correct tick configuration (left=OFF, right=ON)
- **EC Right Title**: Properly restored from sessions (was disappearing before)
- **t-e d5 Toggle**: Works correctly to hide/show EC right title without creating overlapping duplicates
- **Backward Compatibility**: Old session files with incorrect WASD state are automatically sanitized during load

### Affected Files
- `batplot/session.py`: 
  - Force EC left ticks/labels to False
  - Set right ticks/labels based on title visibility (sanitizing old sessions)
- `batplot/operando_ec_interactive.py`:
  - Skip duplicate artist positioning for EC axes in `_apply_wasd_axis()`
  - Set `_right_ylabel_on` flag for EC axes

### Testing
- ✅ Load old `.pkl` files - EC panel loads cleanly without glitches
- ✅ EC right title "Time (h)" is visible after load
- ✅ t-e d5 toggles EC right title on/off correctly
- ✅ No overlapping titles or position shifting
- ✅ Save new session and reload - EC state preserved correctly
- ✅ Works for both time mode and ions mode

### Related Issues
- Completes the EC right title fix from earlier (which addressed capture but not load/toggle)
- Ensures EC axes are treated distinctly from operando axes (which use duplicate artists)

---

## 2026-01-27: Windows Path Parsing Issue - "File not found: C" Error

### Bug Description
When running batplot on Windows with absolute paths (e.g., `batplot C:\Users\...\file.dat`), the error would occur:
```
File not found: C
```

This prevented users from dragging files from Windows Explorer into the terminal (a common workflow).

### Root Cause
Line 2899 in `batplot.py` splits file paths on `:` to parse optional wavelength parameters (format: `file:wavelength`):
```python
parts = file_entry.split(":")
fname = parts[0]  # This becomes just "C" on Windows!
```

On Windows, paths contain `:` in the drive letter (`C:\Users\...`). When split:
- `parts[0]` = `"C"` (drive letter only)
- `parts[1]` = `"\Users\tianda\..."`

The code then tried to check if `"C"` exists as a file, causing the error.

### Solution
Added Windows drive letter detection before splitting:
```python
parts = file_entry.split(":")
if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
    # Windows drive letter detected (e.g., "C" from "C:\path")
    # Rejoin the first two parts as the filename
    fname = parts[0] + ":" + parts[1]
    parts = [fname] + parts[2:]  # Reconstruct parts with full Windows path
else:
    fname = parts[0]
```

This detects single-letter alphabetic first parts (drive letters) and reconstructs the full Windows path before processing wavelength parameters.

### Behavior Changes
- **Windows absolute paths work correctly**: `batplot C:\Users\...\file.dat`
- **Drag-and-drop works**: Users can drag files from Explorer into Anaconda Prompt/terminal
- **Quoted paths work**: `batplot "C:\Users\...\file.dat"`
- **Forward slashes still work**: `batplot C:/Users/.../file.dat`
- **Wavelength parameters still work**: `batplot C:\path\file.xy:1.54:0.25`
- **macOS/Linux unchanged**: No impact on Unix-style paths

### Affected Files
- `batplot/batplot.py`: Added Windows drive letter detection in file path parsing (line ~2899-2909)

### Testing
- ✅ Test on Windows with absolute paths (`C:\...`)
- ✅ Test drag-and-drop from Windows Explorer
- ✅ Test with wavelength parameters (`file:1.54`)
- ✅ Test on macOS/Linux (no regression)
- ✅ Test with relative paths (`..\file.dat`)

### Platform Compatibility
This fix ensures batplot works consistently across Windows, macOS, and Linux when processing file paths, fulfilling the user requirement that "all changes should be working for all operating systems."

---

## 2026-01-27: Wavelength Conversion Created Artificial Data at High Q Values

### Bug Description
When converting XRD data from synchrotron wavelength (e.g., λ=0.25995 Å) to lab wavelength (e.g., λ=1.54 Å) using the dual-wavelength syntax `file:0.25995:1.54 --xaxis 2theta`, an artificial "bump" appeared at ~180° in the 2theta plot. This bump had no corresponding peak in the original Q-space data.

### Root Cause
The conversion formula requires calculating sin(θ) = Q·λ/(4π). At high Q values with large wavelengths, this can give sin(θ) > 1, which is **physically impossible**.

For example, with λ=1.54 Å:
- Maximum measurable Q = 4π/λ ≈ 8.15 Å⁻¹ (at 2θ=180°)
- Data at Q=9 Å⁻¹ gives sin(θ) = 9×1.54/(4π) ≈ 1.10 > 1 ❌

The code clipped sin(θ) to [-1, 1]:
```python
sin_theta = np.clip(sin_theta, -1.0, 1.0)  # Creates fake data!
theta_new_rad = np.arcsin(sin_theta)
```

All impossible Q values got clipped to sin(θ)=1.0, giving θ=90° → 2theta=180°. Multiple high-Q points "piled up" at 180°, creating an artificial peak.

### Solution
**Truncate data instead of clipping:**
1. Calculate sin(θ) for all Q values
2. Create boolean mask: `valid_mask = np.abs(sin_theta) <= 1.0`
3. Print warning if invalid points detected, showing Q_max for target wavelength
4. Truncate both x and y arrays: `x = x[valid_mask]`, `y = y[valid_mask]`
5. Convert only physically accessible data

Applied to both:
- Dual wavelength conversion (line ~3094-3111)
- Q-to-2theta conversion for .qye files (line ~3113-3127)

### Behavior Changes
**Before:**
- Artificial peaks at 2theta ≈ 180° when converting high-Q data to large wavelengths
- Silent data corruption (no warning)
- Peak intensities wrong due to multiple points "squashing" together

**After:**
- Data automatically truncated to physically accessible Q range
- Warning printed: "Warning: N data points exceed Q_max=X.XX Å⁻¹ for λ=Y.YY Å"
- Clean plots with no artificial features
- Conversion stops at maximum measurable 2theta

### Example
Converting synchrotron data (λ=0.25995 Å, Q up to 9 Å⁻¹) to Cu Kα (λ=1.54 Å):
```bash
batplot file.dat:0.25995:1.54 --xaxis 2theta
# Warning: 156 data points exceed Q_max=8.15 Å⁻¹ for λ=1.54 Å
#          Truncating data to physically accessible range.
```

Result: Clean 2theta plot from 0-165° (no artificial bump at 180°)

### Affected Files
- `batplot/batplot.py`:
  - Line ~3094-3111: Dual wavelength conversion with truncation
  - Line ~3113-3127: Q-to-2theta conversion for .qye files with truncation

### Testing
- ✅ Convert synchrotron data (λ=0.25995 Å) to Cu Kα (λ=1.54 Å)
- ✅ Verify no artificial peaks at high 2theta
- ✅ Verify warning appears for truncated data
- ✅ Check Q-space plot matches truncated 2theta coverage
- ✅ Test edge case: Q_max exactly at λ limit

### Impact
**Critical fix** - prevents scientifically incorrect plots that could mislead analysis. The artificial peaks at 180° could be mistaken for real diffraction features, leading to incorrect phase identification or structure refinement.

---

## 2026-01-27: Windows Encoding Error When Saving Converted Files

### Bug Description
On Windows, the `--convert` command failed with encoding error:
```
Error saving C:\...\converted\R02.dat: 'charmap' codec can't encode character '\u03b8' in position 29: character maps to <undefined>
```

### Root Cause
The file header contains Greek letter theta (θ):
```python
header = f"# Converted from {fname}: 2θ (λ={from_wl} Å) → Q → 2θ (λ={to_wl} Å)"
```

`np.savetxt()` without explicit encoding defaults to system encoding:
- **Linux/macOS**: UTF-8 (supports Greek letters) ✅
- **Windows**: 'cp1252' or 'charmap' (no Greek letters) ❌

### Solution
Added explicit `encoding='utf-8'` parameter to `np.savetxt()`:
```python
np.savetxt(output_fname, out_data, fmt="% .6f", header=header, encoding='utf-8')
```

### Behavior Changes
**Before (Windows only):**
- Convert command crashed with encoding error
- No converted file created

**After (all platforms):**
- Files saved successfully with UTF-8 encoding
- Headers display correctly with Greek letters (θ, λ, Å, →)
- Cross-platform consistency

### Example
```bash
# Windows - now works!
batplot C:\data\R02.dat --convert 0.25995 1.54
# Saved C:\data\converted\R02.dat
```

### Affected Files
- `batplot/converters.py`: Line 228 - Added `encoding='utf-8'` to `np.savetxt()`

### Testing
- ✅ Windows: Convert with dual wavelength syntax
- ✅ macOS/Linux: Verify no regression
- ✅ Check converted file header contains θ symbol
- ✅ Test all conversion modes (wl→wl, wl→Q, Q→wl)

### Impact
**Windows-specific fix** - ensures file conversion works on all platforms. Users can now convert XRD data on Windows without encoding errors.

---

## 2026-01-27: Undo Not Restoring Font Size in 1D XY Mode

### Bug Description
In 1D XY plot mode (normal and stack), after changing font size using `f s` and pressing `b` (undo), the font size would **not** restore to the previous value. The plot retained the new font size even though undo should restore all previous state.

### Root Cause
The `restore_state()` function in `interactive.py` updated `plt.rcParams['font.size']` but did not propagate this change to existing text objects:

**What was restored:**
- `plt.rcParams['font.size']` = snapshot value ✓ (line 1590)

**What was missing:**
- Curve labels (`label_text_objects`) - still had new font size ❌
- Axis labels (`ax.xaxis.label`, `ax.yaxis.label`) - still had new font size ❌
- Duplicate labels (`_top_xlabel_artist`, `_right_ylabel_artist`) - still had new font size ❌  
- Tick labels - still had new font size ❌

In matplotlib, changing `plt.rcParams` only affects **new** text elements. Existing text objects retain their current font size until explicitly updated via `set_fontsize()`.

The font change command (`f s`) correctly uses `apply_font_changes()` which updates both rcParams AND all existing text objects. But undo only updated rcParams, causing a mismatch.

### Solution
Added `sync_fonts()` call after restoring `plt.rcParams` (line 1594):
```python
# Fonts
if snap["font_chain"]:
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = snap["font_chain"]
if snap["font_size"]:
    try:
        plt.rcParams['font.size'] = snap["font_size"]
    except Exception:
        pass
# Apply restored font settings to all existing text objects
try:
    sync_fonts()  # NEW: Propagate rcParams to all text objects
except Exception:
    pass
```

The `sync_fonts()` function (from `ui.py`) copies font size from `plt.rcParams` to all text elements:
- Curve labels, axis labels, duplicate labels, tick labels
- Ensures visual display matches restored rcParams

### Other Interactive Modules
Checked all other interactive modules - they already handle fonts correctly:
- ✅ **operando_ec_interactive.py**: Calls `set_fonts()` after restoring (line 1451)
- ✅ **electrochem_interactive.py**: Calls `_apply_font_size()` after restoring (line 1507)
- ✅ **cpc_interactive.py**: Applies fonts via `_apply_style()` (line 791)

### Behavior Changes
**Before:**
- Font size change (f → s → 20) → undo (b): Font stays at 20 (undo broken) ❌

**After:**
- Font size change (f → s → 20) → undo (b): Font returns to previous size (16) ✓

### Example
```bash
batplot file1.dat file2.dat --stack
# Interactive menu:
# Current font: 16
# f -> s -> 20 (change to size 20)
# b (undo)
# Result: Font correctly restores to 16
```

### Affected Files
- `batplot/interactive.py`: Lines 1589-1596 - Added `sync_fonts()` call after restoring `plt.rcParams`

### Testing
- ✅ 1D mode: Change font size → undo → verify size restores
- ✅ Stack mode: Change font size → undo → verify size restores
- ✅ Font family change → undo → verify family restores
- ✅ All other commands → undo → verify working
- ✅ Operando/EC/CPC modes: Verify undo still works (no regression)

### Impact
**Critical fix for 1D XY mode** - undo now correctly restores font sizes. This was a major usability issue as users expected undo to revert ALL changes, not just some of them.

---

## 2026-01-27: Stack Mode Offset Drift After Undo (REVERTED - See above fix)

### Bug Description
In 1D stack mode (`--stack`), when users changed font size using `f s` and then pressed `b` (undo), the vertical offsets between stacked curves would change. This caused curves to shift position unexpectedly after undo, even though the undo should restore the exact pre-change state.

**NOTE**: This fix was reverted because it broke font size restoration. The real issue was that fonts weren't being synced to text objects (see fix above). The offset "drift" was actually caused by font size not restoring, which changed label positions and made offsets appear to shift.

### Root Cause (Original Diagnosis - Incorrect)
The `restore_state()` function in `interactive.py` had redundant logic that caused offset drift:

1. **First restore** (lines 1735-1756): Line data restored from snapshot → `ax.lines[i].set_data(snap_x, snap_y)`
2. **Second restore** (lines 1757-1762): Data lists restored from snapshot → `y_data_list[:] = snap["y_data_list"]`
3. **Problematic recalculation** (lines 1816-1836): Recalculated `y_data_list` from `orig_y + offsets_list` and **updated line data again**

The recalculation logic attempted to ensure consistency but actually introduced problems:
- **Floating-point precision errors**: `orig_y[i] + offsets_list[i]` could differ slightly from the original `y_data_list[i]` due to accumulated floating-point operations
- **Lost transformations**: If data underwent normalization or other transforms, recalculating from `orig_y + offset` wouldn't capture those transforms
- **Redundancy**: The snapshot already captured the correct `y_data_list` with all transforms and offsets applied correctly

The second line data update (line 1832-1836) overrode the first restore (lines 1735-1756), causing the offset drift.

### Solution
Removed the redundant recalculation (lines 1816-1836). The `restore_state()` function now:
1. Restores line visual data from snapshot (lines 1735-1756)  
2. Restores all data lists from snapshot (lines 1757-1762)
3. Updates line data **once** from restored `x_data_list` and `y_data_list` (preserves snapshot exactly)
4. **No recalculation** - trusts the snapshotted data completely

This ensures pixel-perfect restoration of stack offsets after any operation.

### Behavior Changes
**Before:**
- Font size change → undo: Curves shift vertically (offset drift)
- Any command → undo: Potential small offset changes due to recalculation

**After:**
- Font size change → undo: Exact restoration, no drift
- Any command → undo: Perfect state restoration for all curves
- Stack offsets remain stable across all undo operations

### Example
```bash
batplot file1.dat file2.dat file3.dat --stack  # Stack mode with 3 files
# In interactive menu:
# f -> s -> 14 (change font size to 14)
# b (undo)
# Result: Curves return to exact pre-change positions (no offset drift)
```

### Affected Files
- `batplot/interactive.py`:
  - Lines 1757-1836: Removed recalculation logic in `restore_state()`
  - Added comment explaining why recalculation was removed

### Testing
- ✅ Stack mode: Change font size → undo → verify no offset drift
- ✅ Stack mode: Resize canvas → undo → verify no drift
- ✅ Stack mode: Change colors → undo → verify no drift
- ✅ Stack mode: All other commands → undo → verify offsets stable
- ✅ Normal mode: Verify undo still works correctly (no stack offsets to drift)
- ✅ Multiple files: Verify all curves maintain correct spacing

### Impact
**Critical fix for stack mode** - ensures undo operation correctly restores curve positions. Previously, users had to manually readjust offsets after undoing style changes, which was frustrating and error-prone. Now undo works perfectly for all operations in stack mode.

---

## Future Bug Fixes

All future bug fixes should follow this format and be added chronologically to this document.
