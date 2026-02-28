# Changelog

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
