# Changelog

## [1.8.27] - 2026-03-06
- Improved interactive menu functionality for cpc mode
- Improved interactive menu display
- Bug fixes


## [1.8.26] - 2026-03-03
- Interactive menus: consistent highlighting and descriptions across CPC, EC, 1D, and Operando
  - Y-ranges (CPC): ly/ry/q with _colorize_menu; range prompts use _colorize_prompt (min max, w/s/a/q)
  - X/Y range prompts: unified format (min max, w=upper, s=lower, a=auto, q=back) with highlighted keys
  - Submenu prompts: Legend (t/p/q), Colors (ly/ry/u/s/q), Rename (x/ly/ry/f/q), Position (w/s/a/d/0/x/y/(x y)/q)
  - Press a key, Toggle visibility, Display, and all input prompts use _colorize_prompt for key highlighting
- Rename menu: colon format with highlighted keys (like color menu) in EC, CPC, and Operando
- CPC: added `f` for file names (alias for `l`); both single- and multi-file support file rename
- EC: `f` for file names now works in single-file mode; file names reflected in p/i/s/b
- Bug fixes


## [1.8.25] - 2026-03-03
- Improved interactive menu functionality for colors/ticks
- Bug fixes


## [1.8.24] - 2026-03-03
- Improved interactive menu functionality for colors/ticks
- Bug fixes


## [1.8.23] - 2026-02-28
- Major update: batplot now support Bruker .brml and .raw files, you can treat them the same as .xy files (still testing)
- .brml and .raw are also supported in operando mode
- Improved --readcol flag, now you can assign the columns to read for each file by using --readcol m n after each file
    e.g. batplot file1.xy --readcol 1 2 file2.xy --readcol 4 6 this will plot col 1 as x and col 2 as y for file1, and col 4 as x and col 6 as y for file2
         batplot file.xy --readcol 1 2 1 3 1 4 1 5 this will plot 4 curves with col 1 as x and col 2, 3, 4, 5 as y


## [1.8.22] - 2026-02-27
- Major update: batplot now support Bruker .brml and .raw files, you can treat them the same as .xy files
- Improved --readcol flag, now you can assign the columns to read for each file by using --readcol m n after each file
    e.g. batplot file1.xy --readcol 1 2 file2.xy --readcol 4 6 this will plot col 1 as x and col 2 as y for file1, and col 4 as x and col 6 as y for file2
         batplot file.xy --readcol 1 2 1 3 1 4 1 5 this will plot 5 curves with col 1 as x and col 2, 3, 4, 5 as y


## [1.8.21] - 2026-02-13
- Improved functionality in operando mode with CIF files


## [1.8.20] - 2026-02-12
- Operando mode now supports CIF tick labels, add cif files in your command together with operando path to try!


## [1.8.19] - 2026-02-10
- Add support for GC data with user defined segments to separate charge and discharge, useful for BatX EC data


## [1.8.18] - 2026-02-10
- Add support for GC plot with only Potential vs Time


## [1.8.17] - 2026-02-09
- Add support for BatX GC plot


## [1.8.16] - 2026-02-08
- GC and dQdV modes now support multiple files


## [1.8.15] - 2026-02-08
- GC and dQdV modes now support multiple files


## [1.8.14] - 2026-02-07
- Fixed title offset command crash in EC/GC interactive menu
- Fixed bugs in color command
- Major update: GC and dQdV modes now support multiple files
