# Batplot Developer Guide

This guide is for contributors who want to fix bugs, add plotting features, or
extend Batplot with new file readers, commands, modes, styles, sessions, and
release tooling.

Keep changes small and mode-local whenever possible. Batplot has several
interactive modes that share concepts but not all implementation details, so a
fix in one mode should not silently change another mode unless that is the
explicit goal.

## Development Principles

- Touch only the code path needed for the feature or fix.
- Preserve Windows, macOS, and Linux behavior. Avoid shell-specific assumptions
  in Python code and use `pathlib`, `os.path`, `tempfile`, and structured APIs.
- Prefer existing mode patterns over new abstractions. Add shared helpers only
  when two or more active modes genuinely need the same behavior.
- Keep generated, archived, and release-copy folders out of normal edits. The
  active source tree is `batplot/`; do not edit `archive_unused/`, `dist/`,
  `build/`, `*.egg-info/`, or copied release folders such as `batplot-1.8.42/`.
- If a change fixes a bug, add an entry to `BUGFIXES.md`.
- If a change affects commands, persistence, style files, packaging, or release
  behavior, update this guide in the same pull request or commit.

## Repository Map

```text
batplot_script/
+-- batplot/                    # Active package source
|   +-- cli.py                  # Console entry point wrapper
|   +-- batplot.py              # Main dispatcher and legacy compatibility exports
|   +-- args.py                 # CLI parser and mode flags
|   +-- readers.py              # Text, CSV, Excel, EC, and vendor file readers
|   +-- session.py              # Shared session save/load implementations
|   +-- plotting.py             # Shared plotting utilities
|   +-- ui.py                   # Canvas/frame/tick/label utilities
|   +-- ec_common.py            # Shared GC/CV/dQ/dV/CPC defaults and helpers
|   +-- plot_modes/
|       +-- xy/                 # 1D/XRD/PDF/XAS/general XY mode
|       +-- electrochem/        # GC, CV, dQ/dV routes and interactive menu
|       +-- cpc/                # Capacity/energy per cycle mode
|       +-- operando/           # Operando contour + EC mode
|       +-- common/             # Shared menu, spine, palette, and state helpers
+-- tests/                      # Pytest and type-check contract tests
+-- README.md                   # User-facing overview
+-- BUGFIXES.md                 # Required bug-fix notes
+-- CHANGELOG.md                # Release changelog
+-- RELEASE_NOTES.txt           # Source notes used by --dev-upgrade
+-- pyproject.toml              # Packaging metadata, dependencies, test config
+-- MANIFEST.in                 # Source distribution include/exclude rules
+-- .github/workflows/tests.yml # Cross-platform CI
```

## CLI And Dispatch Flow

The installed command is declared in `pyproject.toml`:

```toml
batplot = "batplot.cli:main"
```

The runtime flow is:

1. `batplot.cli.main()` handles wrapper-only behavior such as `--dev-upgrade`,
   version checking, and test injection of `argv`.
2. `batplot.args.parse_args()` builds and validates command-line options.
3. `batplot.batplot.batplot_main()` dispatches to the appropriate plotting
   route.
4. Mode route functions build the initial figure, then optionally enter the
   mode-specific interactive menu.

The main modes are routed through:

- XY: `batplot.plot_modes.xy.pipeline.run_xy_pipeline()`
- GC: `batplot.plot_modes.electrochem.routing.handle_gc_mode()`
- CV: `batplot.plot_modes.electrochem.routing.handle_cv_mode()`
- dQ/dV: `batplot.plot_modes.electrochem.routing.handle_dqdv_mode()`
- CPC/EPC: `batplot.plot_modes.cpc.routing.handle_cpc_mode()`
- Operando: `batplot.plot_modes.operando.routing.handle_operando_mode()`
- Saved sessions: `batplot.plot_modes.session_routing.handle_session_reload()`

When adding a command-line feature, update `args.py`, then wire the behavior in
the smallest relevant route or interactive action. Avoid adding mode-specific
logic directly to `cli.py`; it should remain a thin entry point.

## Plot Mode Structure

Most active modes follow the same module pattern:

- `routing.py`: non-interactive plotting and setup before interactive mode.
- `interactive.py`: command loop and key dispatch.
- `menu.py`: text shown to users in interactive mode.
- `actions.py`: save/export/undo or other larger command handlers.
- `style.py`: style export/import helpers when the mode supports style files.
- `session.py`: public wrappers around shared session implementations.
- Additional focused modules for labels, colors, line styles, legends, ranges,
  smoothing, peaks, layout, or visibility.

### XY Mode

Use `batplot/plot_modes/xy/` for general 1D data such as XRD, PDF, XAS, and
custom XY text files.

Important files:

- `pipeline.py`: reads input files, applies conversions, creates the plot.
- `interactive.py`: user command loop.
- `actions.py`: style export/import, figure export, session save, undo.
- `style.py`: `.bps`, `.bpsg`, and `.bpcfg` style and geometry helpers.
- `session.py`: public XY session wrappers.
- `colors.py`, `line_style.py`, `labels.py`, `axis_range.py`, `smoothing.py`,
  `derivative.py`, `peaks.py`, `cif.py`, `data_ops.py`, `arrange.py`: focused
  XY features.

### Electrochemistry Mode

Use `batplot/plot_modes/electrochem/` for GC, CV, and dQ/dV.

Important files:

- `routing.py`: `handle_gc_mode()`, `handle_cv_mode()`, `handle_dqdv_mode()`.
- `interactive.py`: shared EC interactive command loop.
- `actions.py`: EC style/session/export/undo commands.
- `dqdv_2d.py`: dQ/dV 2D companion contour persistence and helpers.
- `style.py`, `colors.py`, `line_style.py`, `labels.py`, `legend.py`,
  `legend_order.py`, `spine_colors.py`: EC styling features.

Shared EC/CPC defaults live in `batplot/ec_common.py`. Canvas size, plot layout,
and mass-resolution behavior should be changed there when the goal is parity
between GC, CV, dQ/dV, and CPC.

### CPC And EPC Mode

Use `batplot/plot_modes/cpc/` for capacity per cycle and energy per cycle.

Important files:

- `routing.py`: reads EC files, computes charge/discharge/efficiency series,
  and creates the default CPC/EPC figure.
- `interactive.py`: CPC-specific interactive command loop.
- `actions.py`: save/export/undo actions.
- `legend.py`, `colors.py`, `labels.py`, `snapshots.py`: CPC-specific behavior.
- `session.py`: public CPC session wrappers.

CPC shares several expectations with EC but has a second y-axis and scatter
series for charge, discharge, and efficiency. Test both axes whenever changing
style, legend, or color behavior.

### Operando Mode

Use `batplot/plot_modes/operando/` for contour plots and coupled EC/operando
interactive workflows.

Important files:

- `routing.py`: command-line route.
- `plot.py`: plot construction from folders and data grids.
- `interactive.py`: combined operando/EC interactive menu.
- `actions.py`: save/export/undo actions.
- `layout.py`, `grid.py`, `ions_axis.py`, `visibility.py`: contour layout and
  display behavior.
- `style.py`, `colors.py`, `labels.py`, `line_style.py`, `peaks.py`: styling
  and annotation behavior.
- `session.py`: public operando session wrappers.

Operando state has more moving parts than the other modes. Keep changes focused
and add round-trip tests for persistence changes.

## Shared Systems

### Readers

File parsing lives primarily in `batplot/readers.py`.

Add a reader here when:

- A new file format is needed by more than one mode.
- Parsing requires format-specific handling.
- The data needs robust header, delimiter, encoding, or mixed text/numeric
  behavior.

For XY formats, also check `batplot/plot_modes/xy/pipeline.py` and any extension
lists in `batplot/batplot.py`. For electrochemistry formats, wire the reader in
`electrochem/routing.py` or `cpc/routing.py`.

Reader guidelines:

- Use `encoding="utf-8"` when writing text; handle common read encodings only
  where necessary.
- Avoid platform-specific paths or separators.
- Return plain Python/numpy structures that routes can validate.
- Add focused tests with tiny fixture files or temporary files.

### Style Files

Interactive style export/import uses `.bps`, `.bpsg`, and `.bpcfg` files.

The important rule is p/i parity:

- `p`: export/print/save style or style+geometry.
- `i`: import the same fields back.

When adding a style field, update all relevant export and import code in the
same mode. For geometry-affecting fields, verify style+geometry files as well as
style-only files.

Mode locations:

- XY: `batplot/plot_modes/xy/style.py` and `xy/actions.py`
- EC: `batplot/plot_modes/electrochem/style.py` and `electrochem/actions.py`
- CPC: `batplot/plot_modes/cpc/actions.py` and related helpers
- Operando: `batplot/plot_modes/operando/style.py` and `operando/actions.py`

### Sessions

Sessions are `.pkl` files that preserve a full plot state. Public mode modules
mostly re-export implementations from `batplot/session.py`.

The important rule is s/b parity:

- `s`: save enough state to reproduce the figure later.
- `b`: undo must restore the same user-visible state when applicable.

When adding a persistent field:

1. Add it to the relevant dump function in `batplot/session.py` or the
   mode-local state builder.
2. Load it in the corresponding load function.
3. Add it to undo snapshots if users can change it interactively.
4. Keep backward compatibility with old session files by using safe defaults for
   missing keys.
5. Add or update a round-trip test.

Saved-session dispatch is in `batplot/plot_modes/session_routing.py`. New
session kinds must be routed there.

### Undo

Undo is mode-specific and should restore the state a user just changed. When
adding an interactive command that mutates the figure:

- Capture state before mutation.
- Restore artists, axes, labels, colors, legends, limits, visibility, and helper
  attributes touched by the command.
- Redraw the canvas after restore where the mode already does so.

Do not add broad undo state if only one artist needs tracking.

### Menus And Interactive Commands

Interactive command additions usually require three edits:

1. Add the displayed command to the mode's `menu.py`.
2. Dispatch the command in the mode's `interactive.py`.
3. Put larger behavior in `actions.py` or a focused helper module.

Common command conventions:

- `p`: export style or style+geometry.
- `i`: import style or style+geometry.
- `e`: export figure.
- `s`: save session.
- `b`: undo.
- `q`: quit.
- `oe`, `os`, `ops`, `opsg`: overwrite previous export/session/style paths
  where supported.

Keep command syntax consistent across XY, EC, CPC, and operando when adding a
shared concept.

### Colors And Palettes

Use shared color helpers when possible:

- `batplot/color_utils.py`: colormap lookup and terminal color helpers.
- `batplot/plot_modes/common/palettes.py`: palette aliases, range parsing, and
  sampling.
- `batplot/plotting.py`: shared artist helpers such as color application.

When a line can be shown as markers only, make sure both line color and marker
face/edge colors are updated. Legends and plotted artists should not diverge.

### Axes, Canvas, And Layout

Use `batplot/ui.py` for canvas, frame, tick, and label positioning helpers.
Use `batplot/plot_modes/common/spines.py` for WASD spine/tick/title state.

Shared GC/CV/dQ/dV/CPC defaults live in `batplot/ec_common.py`:

- `_EC_DEFAULT_FIGSIZE`
- `_EC_DEFAULT_LAYOUT`
- `_CPC_DEFAULT_LAYOUT`
- `_default_ec_figsize()`
- `_default_cpc_figsize()`
- `_apply_default_ec_layout()`

Do not hardcode replacement figure sizes in individual EC/CPC routes unless a
mode is intentionally different and tests document the difference.

## How To Add Common Features

### Add A New CLI Flag

1. Add the option in `batplot/args.py`.
2. Decide whether it is global or mode-specific.
3. Read the value in the smallest route that needs it.
4. Add CLI smoke tests when the flag affects dispatch.
5. Update `README.md` or user-facing help if the flag is public.

### Add A New File Reader

1. Implement parsing in `batplot/readers.py`.
2. Add a tiny representative test file or temporary-file test.
3. Wire the reader into the relevant route:
   - XY: `batplot/plot_modes/xy/pipeline.py`
   - GC/CV/dQ/dV: `batplot/plot_modes/electrochem/routing.py`
   - CPC/EPC: `batplot/plot_modes/cpc/routing.py`
   - Operando: `batplot/plot_modes/operando/plot.py` or `routing.py`
4. Update extension handling if `--all` or `--showcol` should recognize it.
5. Confirm behavior on paths with spaces.

### Add A New Interactive Command

1. Choose a command syntax that does not conflict with existing keys.
2. Add menu text in the mode's `menu.py`.
3. Add parsing/dispatch in `interactive.py`.
4. Put non-trivial logic in `actions.py` or a focused module.
5. Add undo support if it mutates the plot.
6. Add style/session support if the result should persist.
7. Add an interactive smoke test or a focused unit test for the helper.

### Add A New Style Field

1. Find the mode's style export and import code.
2. Export the field under a clear key.
3. Import the key with a safe default for older style files.
4. Add the field to geometry export/import if it affects layout.
5. Add or update a round-trip test.

Checklist:

- `p` exports it.
- `i` imports it.
- `s` saves it if it should persist in sessions.
- `b` undoes it if it can be changed interactively.

### Add A New Session Field

1. Add the field to the relevant dump function in `batplot/session.py`.
2. Add load logic in the matching load function.
3. Use defaults for missing legacy keys.
4. Add undo state if the field can be changed from the interactive menu.
5. Add a round-trip test in the relevant `tests/test_*_roundtrip.py` file.

### Add A New Plot Mode

1. Create `batplot/plot_modes/<mode>/`.
2. Start with `routing.py`, `interactive.py`, `menu.py`, `actions.py`, and
   `session.py` if persistence is needed.
3. Add CLI flags in `batplot/args.py`.
4. Dispatch in `batplot/batplot.py`.
5. Add session reload support in `batplot/plot_modes/session_routing.py` if the
   mode saves `.pkl` sessions.
6. Add tests for CLI dispatch, output creation, style/session round trips, and
   any readers.
7. Update `README.md`, `CHANGELOG.md` or `RELEASE_NOTES.txt` when user-facing.

Prefer extracting shared helpers only after the new mode proves it needs the
same behavior as an existing active mode.

## Testing

Install development dependencies:

```bash
python -m pip install -e ".[test]"
```

Run the full test suite:

```bash
python -m pytest tests/ -q
```

Run the type checker:

```bash
python -m basedpyright .
```

Useful focused tests:

- CLI behavior: `python -m pytest tests/test_cli_smoke.py -q`
- Public contracts: `python -m pytest tests/test_contracts.py -q`
- XY round trips: `python -m pytest tests/test_xy_roundtrip.py -q`
- EC round trips: `python -m pytest tests/test_ec_roundtrip.py -q`
- CPC round trips: `python -m pytest tests/test_cpc_roundtrip.py -q`
- Operando round trips: `python -m pytest tests/test_operando_roundtrip.py -q`
- Readers: `python -m pytest tests/test_csv_readers.py -q`
- Release tooling: `python -m pytest tests/test_dev_upgrade.py -q`

For fixes that touch plotting, prefer at least one focused unit or round-trip
test plus one smoke test for the user path. For small documentation-only edits,
no test run is required.

## Packaging And Release Workflow

Packaging metadata is in:

- `pyproject.toml`
- `setup.py`
- `MANIFEST.in`
- `CITATION.cff`
- `batplot/__init__.py`
- `batplot/version_check.py`

Release notes are maintained in:

- `RELEASE_NOTES.txt`
- `CHANGELOG.md`
- `batplot/data/CHANGELOG.md`

The `batplot --dev-upgrade` command is implemented in `batplot/dev_upgrade.py`.
It reads release notes, updates version-related files, validates distribution
contents, builds, uploads, and stages release changes.

Before changing release behavior:

1. Read `batplot/dev_upgrade.py`.
2. Add or update tests in `tests/test_dev_upgrade.py`.
3. Confirm future files are included through package discovery or manifest rules.
4. Keep GitHub/PyPI conflict handling explicit and testable.

## Cross-Platform Checklist

Use this checklist before finishing code changes:

- Paths with spaces work.
- No hardcoded `/` or `\` path assumptions in Python logic.
- Temporary files use `tempfile` or pytest `tmp_path`.
- Text files specify encoding when written.
- No dependency on an interactive terminal unless the command is explicitly
  interactive.
- Matplotlib code does not require a GUI backend for tests.
- Tests pass on case-sensitive and case-insensitive filesystems.
- New dependencies are declared in `pyproject.toml` and are OS independent.

## Documentation Maintenance

Update this guide whenever a change adds, removes, or significantly changes:

- A CLI flag or mode dispatch path.
- A plot mode package or module responsibility.
- A file reader or supported input format.
- Interactive command syntax.
- Style/session/undo behavior.
- Packaging, release, or `--dev-upgrade` behavior.
- Required test commands or CI expectations.

For bug fixes, also update `BUGFIXES.md`. For user-visible features, update
`README.md`, `CHANGELOG.md`, or `RELEASE_NOTES.txt` as appropriate.

The goal is for a future contributor to answer two questions quickly:

1. Where should this change be made?
2. What else must be updated so p/i/s/b, tests, docs, and releases stay in sync?
