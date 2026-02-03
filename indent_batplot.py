#!/usr/bin/env python3
"""Script to indent the main execution code in batplot.py to wrap it in batplot_main()."""

import sys

def process_file(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the start and end of code to indent
    # Start: after "args = _bp_parse_args()" (now inside batplot_main)
    # End: before "def main():" at line ~2025
    
    start_idx = None
    end_idx = None
    
    for i, line in enumerate(lines):
        if 'args = _bp_parse_args()' in line and start_idx is None:
            start_idx = i + 1  # Start indenting from next line
        if line.strip().startswith('def main():') and start_idx is not None:
            end_idx = i
            break
    
    if start_idx is None or end_idx is None:
        print(f"Could not find boundaries: start={start_idx}, end={end_idx}")
        return False
    
    print(f"Indenting lines {start_idx+1} to {end_idx} (0-indexed: {start_idx}-{end_idx-1})")
    
    # Create new content
    new_lines = []
    for i, line in enumerate(lines):
        if start_idx <= i < end_idx:
            # Add 4-space indent
            if line.strip():  # Don't indent empty lines
                new_lines.append('    ' + line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    
    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"✓ Processed {len(lines)} lines")
    print(f"✓ Indented {end_idx - start_idx} lines")
    return True

if __name__ == '__main__':
    input_file = 'batplot/batplot.py'
    output_file = 'batplot/batplot_new.py'
    
    if process_file(input_file, output_file):
        print(f"\n✓ Success! Review {output_file}")
        print(f"  If good, run: mv {output_file} {input_file}")
    else:
        print("\n✗ Failed!")
        sys.exit(1)
