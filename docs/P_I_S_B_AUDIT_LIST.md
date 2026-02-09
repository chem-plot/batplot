# p / i / s / b Audit List

Audit of all interactive menus to ensure **p** (print/export style or geometry), **i** (import style/geometry), **s** (save project), and **b** (undo) are implemented correctly and that every state-changing command calls the snapshot function **before** the change so undo works.

---

## 1. batplot/interactive.py (1D XY)

### Main commands audited

| Key | Meaning | p/i/s/b | Snapshot (for b) |
|-----|--------|---------|-------------------|
| **q** | Quit | — | — |
| **z** | Toggle CIF hkl labels | — | **Fixed:** now calls `push_state("toggle-cif-hkl")` before change |
| **h** | Legend submenu (v=visibility, s=position) | — | Both subcommands call `push_state` before change ✓ |
| **j** | Toggle CIF title labels | — | **Fixed:** `push_state("toggle-cif-titles")` moved to before change (was after) |
| **b** | Undo | b | `restore_state()` ✓ |
| **n** | Toggle crosshair | — | No persistent state; no snapshot needed ✓ |
| **os** | Quick overwrite last session | s | No snapshot (save only) ✓ |
| **oe** | Quick overwrite last figure export | — | No snapshot ✓ |
| **s** | Save project (.pkl) | s | Uses `_bp_dump_session` with current state ✓ |
| **w** | (hidden) | — | — |
| **c** | Color menu | — | push_state for manual/spine/palette ✓ |
| **r** | Rename curve/axis | — | push_state ✓ |
| **a** | Rearrange curves | — | push_state ✓ |
| **x** | X-range | — | push_state ✓ |
| **y** | Y-range | — | push_state ✓ |
| **d** | Derivative | — | push_state ✓ |
| **o** | Offset | — | push_state ✓ |
| **l** | Line style (lw, frame, grid, line-only, etc.) | — | push_state ✓ |
| **f** | Font | — | push_state ✓ |
| **g** | Geometry (resize frame/canvas) | — | push_state ✓ |
| **h** | Legend (duplicate) | — | push_state ✓ |
| **t** | Ticks (i=invert, p=title offset, l=length) | — | push_state before each ✓ |
| **p** | Print/export style | p | Submenu: e=export, o=overwrite last, number=overwrite ✓ |
| **i** | Import style | i | `push_state("style-import")` before `apply_style_config` ✓ |
| **e** | Export figure (image) | — | No snapshot ✓ |
| **sm** | Smooth/reduce rows | — | push_state for each operation ✓ |
| **v** | Version/changelog | — | — |

### Fixes applied (interactive.py)

- **z (toggle CIF hkl):** Added `push_state("toggle-cif-hkl")` at the start of the handler so **b** can undo.
- **j (toggle CIF titles):** Moved `push_state("toggle-cif-titles")` to before the state change and removed the duplicate call after the change so the snapshot is the pre-toggle state.

---

## 2. batplot/electrochem_interactive.py (EC / GC)

### Main commands audited

| Key | Meaning | p/i/s/b | Snapshot (for b) |
|-----|--------|---------|-------------------|
| **b** | Undo | b | `restore_state()` ✓ |
| **e** | Export figure | — | No snapshot ✓ |
| **h** | Legend (visibility, position) | — | push_state ✓ |
| **p** | Print/export style | p | Submenu: e=export, o=overwrite, ps/psg ✓ |
| **i** | Import style | i | `push_state("import-style")` before apply ✓ |
| **l** | Line style | — | push_state ✓ |
| **k** | (palette info) | — | — |
| **r** | Rename | — | push_state ✓ |
| **t** | Ticks (i=invert, p=title offset, l=length) | — | push_state ✓ |
| **s** | Save session | s | `dump_ec_session` ✓ |
| **c** | Color / palette | — | push_state ✓ |
| **a** | (other) | — | — |
| **f** | Font | — | push_state ✓ |
| **x** / **y** | Limits | — | push_state ✓ |
| **g** | Geometry | — | push_state ✓ |
| **sm** | Smooth | — | push_state ✓ |
| **oe** / **os** | Quick overwrite export/session | — | — |

No code changes required; p/i/s/b and snapshot usage are consistent.

---

## 3. batplot/cpc_interactive.py (CPC)

### Main commands audited

| Key | Meaning | p/i/s/b | Snapshot (for b) |
|-----|--------|---------|-------------------|
| **b** | Undo | b | `restore_state()` ✓ |
| **s** | Save session | s | `dump_cpc_session` ✓ |
| **p** | Print/export style | p | Submenu: e=export, o=overwrite, ps/psg ✓ |
| **i** | Import style | i | `push_state("import-style")` before apply ✓ |
| **t** | Ticks (i=invert, p=title offset, l=length) | — | push_state / _ensure_snapshot ✓ |
| Other (l, k, h, f, g, r, x, y, etc.) | Various | — | push_state where state changes ✓ |

No code changes required; p/i/s/b and snapshot usage are consistent.

---

## 4. batplot/operando_ec_interactive.py (Operando + EC)

### Main commands audited

| Cmd | Meaning | p/i/s/b | Snapshot (for b) |
|-----|--------|---------|-------------------|
| **b** | Undo | b | `_restore()` ✓ |
| **s** | Save session | s | `dump_operando_session` ✓ |
| **p** | Print/export style | p | Style submenu with export ✓ |
| **i** | Import style | i | `_snapshot("import-style")` before apply ✓ |
| **t** | Ticks: **i** = invert, **l** = length | — | **Fixed:** use `_snapshot` instead of undefined `push_state` |
| Other (v, oc, ow, ew, h, el, l, f, g, r, ox, oy, oz, et, ex, ey, etc.) | Various | — | _snapshot before state change ✓ |

### Fixes applied (operando_ec_interactive.py)

- **t → i (tick direction):** Replaced `push_state("tick-direction")` with `_snapshot("tick-direction")` (operando menu only defines `_snapshot`, not `push_state`).
- **t → l (tick length):** Replaced `push_state("tick-length")` with `_snapshot("tick-length")`.

Without this, using **t** then **i** or **l** would raise `NameError`.

---

## Summary of fixes

| File | What was fixed |
|------|----------------|
| **interactive.py** | **z:** Add `push_state("toggle-cif-hkl")` before toggling CIF hkl labels. **j:** Call `push_state("toggle-cif-titles")` before toggling CIF titles and remove the duplicate call after. |
| **operando_ec_interactive.py** | In tick submenu (**t**), replace `push_state(...)` with `_snapshot(...)` for tick direction (**i**) and tick length (**l**) so undo works and NameError is avoided. |
| **electrochem_interactive.py** | No changes. |
| **cpc_interactive.py** | No changes. |

---

## Convention checked

- **b (undo):** Restore from the last snapshot. Snapshot must be taken **before** the state-changing action so the stored state is the previous one.
- **s (save):** Persist full session (data + style + geometry) via the appropriate `dump_*_session`.
- **p (print/export):** Export style (and optionally geometry) to .bps/.bpsg/.bpcfg; submenus offer e=export, o=overwrite last, number=overwrite.
- **i (import):** Load style (and optionally geometry) from file; snapshot is taken **before** applying so **b** can undo the import.

All four menus now follow this convention for p, i, s, and b, and state-changing commands that support undo call the correct snapshot function before modifying state.

---

## Color changes and p/i/s/b

Spine and curve/cycle color changes are integrated with p, i, s, and b in all interactive menus:

- **p (print/export):** Style export includes per-spine colors in `spines` (and curve/cycle colors in `lines` or cycle style). Export uses the same per-side spine representation so re-import restores correctly.
- **i (import):** Style import applies spine colors via `set_spine_side_color` (per-side) so only the intended side is colored. Import is preceded by `push_state`/`_snapshot` so **b** can undo. In **style.py**, `apply_style_config` uses `_ui_set_spine_side_color` for spine color; legacy axis-wide `tick_colors`/`axis_label_colors` are only applied when the config has no per-spine color.
- **s (save):** Session dump captures spine colors (and curve/cycle colors) in the session dict; load uses `_set_spine_side_color` (from ui) when restoring spines.
- **b (undo):** Snapshot includes `spines` with `color` per name; `restore_state` applies them via `_ui_set_spine_side_color` so per-side colors are restored correctly.

Menus: **interactive** (1D XY), **electrochem**, **cpc**, **operando** all use the shared `set_spine_side_color` (in **batplot/ui.py**) for applying spine color so that only one side is updated and p/i/s/b stay consistent.
