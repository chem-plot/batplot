Layout Persistence Fixes
========================

Context
-------
- Saving sessions from the XY interactive menu preserves exact axes bbox, subplot margins, and frame inches.
- On reload, `interactive_menu()` called `ensure_text_visibility()` before any user input. That helper shrinks subplot margins when it thinks labels might overflow, which shaved ~0.08″ off each side, so a saved 6.20×4.62″ frame reopened as ~6.12×4.56″.
- Operando interactive sessions run layout “rebalance” logic on startup to tighten the EC gap and widen the operando axes. That block always executed, even for layouts restored from `.pkl`, so colorbar and EC widths drifted immediately after load.
- Session loads also executed `ax.grid(grid_state, color=...)` even when `grid_state` was False. Matplotlib treats non-default keyword args as a request to draw the grid, so the grid reappeared despite being disabled.

Fix Summary
-----------
1. **XY sessions** (`batplot.py` + `interactive.py`)
   - When we apply stored `axes_bbox`, `subplot_margins`, or `frame_size`, we set `fig._skip_initial_text_visibility = True`.
   - `interactive_menu()` now checks for that flag and skips the very first `ensure_text_visibility()` call. Everything else (resize command, label toggles, etc.) still use the guard normally.
   - Result: `g → p` shows exactly the saved inch values after reopening a `.pkl`.

2. **Operando sessions** (`session.py` + `operando_ec_interactive.py`)
   - Loader tags restored figures with `fig._skip_initial_operando_layout = True`.
   - On menu startup we read & clear that flag; if it was set we skip the automatic EC-gap tightening and width transfer that normally runs once per session.
   - Colorbar, operando axes, and EC widths now stay exactly as saved until the user explicitly runs `ow/ew/g` adjustments.

3. **Grid state on load**
   - Replaced `ax.grid(grid_state, color=...)` with a conditional: use style args only when enabling the grid, and call `ax.grid(False)` cleanly when disabling.
   - Removes the Matplotlib warning and—more importantly—prevents the grid from turning itself back on.

Verification Checklist
----------------------
1. XY interactive:
   - Launch any plot, run `g → p`, set frame to something obvious (e.g., `3 4`), save via `s`.
   - Reopen the `.pkl`, check `g → p` again → it should read `3.00 × 4.00` exactly.
   - Toggle grid off with `f → g` subcommand, save, reload, confirm grid stays off (no warning).

2. Operando interactive:
   - Open a combined operando+EC session, adjust widths using `ow` / `ew` or manual gap commands, save to `.pkl`.
   - Reload via `batplot session.pkl --interactive`, confirm colorbar/EC widths match saved layout before issuing any commands.

3. Regression guard:
   - If frames start drifting again, search for usages of `_skip_initial_text_visibility` and `_skip_initial_operando_layout` to ensure the flags are still set/cleared precisely once. Re-run the checklist above.

Keep this note handy whenever layout persistence is touched—if frames or colorbars “mysteriously” change on load, check whether our skip flags are still honored and whether any new helpers auto-adjust margins before the user explicitly asks for it.
