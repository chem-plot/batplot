# Batplot Development Guide for Complete Beginners

**Version:** 1.7.28  
**Author:** Tian Dai  
**Purpose:** A simple, step-by-step guide to understand and work with the batplot codebase

---

## Table of Contents

1. [What is Batplot?](#what-is-batplot)
2. [Understanding Python Basics](#understanding-python-basics)
3. [How Batplot Works - The Big Picture](#how-batplot-works---the-big-picture)
4. [Understanding Files and Folders](#understanding-files-and-folders)
5. [How Code is Organized](#how-code-is-organized)
6. [Following the Path: From Command to Plot](#following-the-path-from-command-to-plot)
7. [Key Concepts Explained Simply](#key-concepts-explained-simply)
8. [Common Tasks: How to Make Changes](#common-tasks-how-to-make-changes)
9. [Troubleshooting: When Things Go Wrong](#troubleshooting-when-things-go-wrong)
10. [Glossary: Simple Explanations](#glossary-simple-explanations)

---

## What is Batplot?

**Batplot** is a computer program that helps scientists create graphs (called "plots") from their research data. Think of it like a special calculator that:
- Takes data files (like spreadsheets)
- Draws beautiful graphs from that data
- Lets you customize colors, labels, and appearance
- Saves your work so you can come back to it later

**Real-World Analogy:** Imagine you have a stack of handwritten notes (your data files). Batplot is like a professional artist who:
1. Reads your notes (reads data files)
2. Draws a beautiful chart (creates plots)
3. Lets you tell them "make this line blue" or "make the title bigger" (interactive menu)
4. Saves the finished drawing (saves plots or sessions)

---

## Understanding Python Basics

### What is Python?

Python is a programming language - a way to tell computers what to do using words that (mostly) make sense to humans.

### Important Python Concepts for Batplot

#### 1. **Functions: The Building Blocks**

Think of a function like a recipe. You give it ingredients (called "arguments" or "parameters"), and it does something with them.

**Example:**
```python
def read_file(filename):
    """This function reads a file and returns its contents."""
    # Code here that reads the file
    return contents
```

**In Plain English:**
- `def` means "define a function" (create a recipe)
- `read_file` is the name of the function (the recipe name)
- `filename` is what you give to the function (an ingredient)
- The function does something (reads the file)
- `return` gives back the result (the finished dish)

**In Batplot:** Functions like `read_mpt_file()` read battery data files and give you back the numbers inside.

#### 2. **Variables: Storage Boxes**

A variable is like a labeled box where you store information.

```python
file_path = "data.csv"  # Store text (called a "string")
number_of_cycles = 50   # Store a number
is_visible = True       # Store True or False (called a "boolean")
```

**In Plain English:**
- `file_path` is the label on the box
- `=` means "put this in the box"
- `"data.csv"` is the text you're storing

**In Batplot:** Variables store things like file names, plot colors, axis ranges, etc.

#### 3. **Lists: Baskets of Items**

A list is like a basket where you can put multiple things.

```python
colors = ["red", "blue", "green"]  # A list of colors
numbers = [1, 2, 3, 4, 5]          # A list of numbers
```

**In Plain English:**
- `colors` is a basket
- Inside are three items: "red", "blue", "green"
- Items are separated by commas
- Items are in order (first item is at position 0, second at 1, etc.)

**In Batplot:** Lists store things like multiple file names, cycle numbers, data points, etc.

#### 4. **Dictionaries: Labeled Storage**

A dictionary is like a filing cabinet with labeled drawers.

```python
person = {
    "name": "John",
    "age": 30,
    "city": "Oslo"
}
```

**In Plain English:**
- `person` is the filing cabinet
- `"name"` is a label on a drawer
- `"John"` is what's inside that drawer
- You find things by their label: `person["name"]` gives you "John"

**In Batplot:** Dictionaries store settings, plot configurations, cycle information, etc.

#### 5. **If/Else: Making Decisions**

This is like a fork in the road - the program decides which path to take.

```python
if temperature > 25:
    print("It's hot!")
else:
    print("It's cool.")
```

**In Plain English:**
- **If** the temperature is greater than 25, say "It's hot!"
- **Otherwise**, say "It's cool."

**In Batplot:** The program uses if/else to decide things like "which file format?" or "which plotting mode?"

#### 6. **Loops: Repeating Actions**

A loop repeats an action multiple times, like a washing machine cycle.

```python
for color in ["red", "blue", "green"]:
    print(color)
```

**In Plain English:**
- Take each color from the list
- Print it
- Repeat until all colors are done

**In Batplot:** Loops are used to plot multiple cycles, process multiple files, etc.

---

## How Batplot Works - The Big Picture

### The Journey of a Command

When you type something like:
```
batplot --gc battery_data.mpt --mass 7.0 --interactive
```

Here's what happens step-by-step:

```
┌─────────────────────────────────────────────────────────┐
│ STEP 1: You type a command in the terminal              │
│ "batplot --gc battery_data.mpt --mass 7.0 --interactive"│
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ STEP 2: CLI Entry Point (cli.py)                        │
│ - Checks if there's a newer version available           │
│ - Prepares the command for processing                   │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ STEP 3: Main Router (batplot.py)                        │
│ - Reads what you typed (arguments)                      │
│ - Decides: "This is GC mode!"                           │
│ - Routes to the GC handler                              │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ STEP 4: GC Mode Handler (modes.py)                      │
│ - Reads the battery data file                           │
│ - Processes the data (calculates capacity, etc.)        │
│ - Groups data by cycles                                 │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ STEP 5: Create Plot                                     │
│ - Draws the graph with matplotlib                       │
│ - Each cycle gets its own color                         │
│ - Adds labels and legend                                │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ STEP 6: Interactive Menu (electrochem_interactive.py)   │
│ - Shows a menu of options                               │
│ - Waits for you to press keys (like 'c' for colors)    │
│ - Updates the plot in real-time                         │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ STEP 7: Exit                                            │
│ - Saves your plot if requested                          │
│ - Returns to terminal                                   │
└─────────────────────────────────────────────────────────┘
```

**Simple Analogy:** 
- You order at a restaurant (type command)
- The host seats you (CLI entry)
- The waiter takes your order (argument parsing)
- The chef cooks your meal (data processing)
- The food arrives (plot appears)
- You can ask for adjustments (interactive menu)
- You pay and leave (exit)

---

## Understanding Files and Folders

### The Project Structure

```
batplot_script/              ← Main folder (like a house)
│
├── batplot/                 ← The main code folder (like rooms in the house)
│   ├── __init__.py          ← Makes this a Python package (like a house number)
│   ├── cli.py               ← Entry point (the front door)
│   ├── batplot.py           ← Main router (the hallway directing to rooms)
│   ├── args.py              ← Argument definitions (the doorbell instructions)
│   ├── modes.py             ← Mode handlers (different rooms for different tasks)
│   ├── readers.py           ← File readers (the mailbox - reads incoming data)
│   ├── interactive.py       ← XY plot menu (one living room)
│   ├── electrochem_interactive.py  ← EC plot menu (another living room)
│   ├── cpc_interactive.py   ← CPC plot menu (yet another living room)
│   ├── operando_ec_interactive.py  ← Operando menu (a special room)
│   ├── session.py           ← Save/load sessions (the storage room)
│   ├── style.py             ← Style management (the decoration room)
│   ├── utils.py             ← Helper functions (the toolbox)
│   └── ... (more files)
│
├── README.md                ← User instructions
├── USER_MANUAL.md           ← Detailed user guide
├── CODE_GUIDE.md            ← Developer guide (existing)
├── DEVELOPMENT_GUIDE.md     ← This file (beginner guide)
├── pyproject.toml           ← Package configuration (like a blueprint)
└── setup.py                 ← Installation script
```

### Key Files Explained

#### `cli.py` - The Front Door

**What it does:** This is the first file Python looks at when you run `batplot`.

**Simple explanation:** 
- Like a receptionist at a hotel
- Checks you in (version check)
- Directs you to the right place (routes to main function)
- Handles problems gracefully (error handling)

**Key function:**
- `main()` - The function that starts everything

#### `batplot.py` - The Main Router

**What it does:** This file decides what mode to use and routes to the right handler.

**Simple explanation:**
- Like a switchboard operator
- Receives your request
- Decides: "They want GC mode" or "They want CV mode"
- Connects you to the right handler

**Key function:**
- `batplot_main()` - The main decision-maker

#### `args.py` - The Instruction Manual

**What it does:** Defines all the command-line options (like `--gc`, `--mass`, etc.).

**Simple explanation:**
- Like a restaurant menu
- Lists all available options
- Explains what each option does
- Validates that you ordered something valid

**Key function:**
- `parse_args()` - Reads and validates your command

#### `modes.py` - The Mode Handlers

**What it does:** Contains functions that handle different plotting modes (GC, CV).

**Simple explanation:**
- Like specialized chefs
- Each chef (function) handles a specific dish (mode)
- `handle_gc_mode()` - Handles galvanostatic cycling
- `handle_cv_mode()` - Handles cyclic voltammetry

#### `readers.py` - The File Readers

**What it does:** Reads different file formats (.mpt, .csv, .xye, etc.).

**Simple explanation:**
- Like translators
- Can read different languages (file formats)
- `read_mpt_file()` - Reads BioLogic .mpt files
- `read_ec_csv_file()` - Reads CSV files
- Converts everything to a common format

#### Interactive Menu Files - The Customization Rooms

**What they do:** Provide interactive menus for customizing plots.

**Simple explanation:**
- Like a customization studio
- You enter commands (press keys)
- The plot changes in real-time
- Each file handles a different type of plot:
  - `interactive.py` - For XY plots (XRD, PDF, etc.)
  - `electrochem_interactive.py` - For GC/CV/dQdV plots
  - `cpc_interactive.py` - For capacity-per-cycle plots
  - `operando_ec_interactive.py` - For operando plots

---

## How Code is Organized

### The Module System

Python code is organized into "modules" (files) and "packages" (folders containing modules).

**Simple Analogy:** 
- A module is like a single book
- A package is like a library shelf with multiple books
- `batplot` is a package (the whole library shelf)
- `cli.py`, `batplot.py`, etc. are modules (individual books)

### How Modules Talk to Each Other

**Importing:**
```python
from .readers import read_mpt_file
```

**In Plain English:**
- "From the readers module, get the read_mpt_file function"
- The `.` means "from the same package"
- Now you can use `read_mpt_file()` in your code

**Example in batplot:**
```python
# In modes.py
from .readers import read_mpt_file  # Get the function
data = read_mpt_file("battery.mpt")  # Use the function
```

### Function Organization

Functions are organized by purpose:

1. **Entry Points** - Functions that start the program
   - `cli.main()` - Starts everything
   - `batplot.batplot_main()` - Routes to modes

2. **Data Processing** - Functions that work with data
   - `readers.read_mpt_file()` - Reads files
   - `modes.handle_gc_mode()` - Processes GC data

3. **Plotting** - Functions that create graphs
   - Functions in `modes.py` create initial plots
   - Interactive menus update plots

4. **Utilities** - Helper functions used everywhere
   - `utils._confirm_overwrite()` - Asks user confirmation
   - `utils.normalize_label_text()` - Formats text

---

## Following the Path: From Command to Plot

Let's trace through a complete example step-by-step.

### Example Command
```
batplot --gc battery_data.mpt --mass 7.0 --interactive
```

### Step-by-Step Journey

#### Step 1: You Type the Command

**Location:** Your terminal/command prompt

**What happens:** You press Enter after typing the command.

---

#### Step 2: Python Finds the Entry Point

**Location:** `batplot/cli.py`

**What happens:**
```python
def main(argv: Optional[list] = None) -> int:
    # Step 2.1: Check for updates (optional, doesn't block)
    check_for_updates(__version__)
    
    # Step 2.2: Import and call the main function
    from .batplot import batplot_main
    return batplot_main()
```

**In Plain English:**
- Python finds the `main()` function in `cli.py`
- It checks for updates (silently, in the background)
- It calls `batplot_main()` to do the actual work

---

#### Step 3: Parse Arguments

**Location:** `batplot/batplot.py`

**What happens:**
```python
def batplot_main() -> int:
    # Step 3.1: Parse what you typed
    args = _bp_parse_args()
    # Now args.gc = True
    #     args.files = ['battery_data.mpt']
    #     args.mass = 7.0
    #     args.interactive = True
    
    # Step 3.2: Check which mode
    if args.gc:  # True! So we go into this block
        return handle_gc_mode(args)
```

**In Plain English:**
- The program reads your command and understands:
  - You want GC mode (`--gc`)
  - Your file is `battery_data.mpt`
  - Mass is 7.0 mg
  - You want interactive mode
- It calls the GC mode handler

---

#### Step 4: Read the Data File

**Location:** `batplot/modes.py` → `handle_gc_mode()`

**What happens:**
```python
def handle_gc_mode(args) -> int:
    # Step 4.1: Get the file name
    ec_file = args.files[0]  # 'battery_data.mpt'
    
    # Step 4.2: Read the file
    from .readers import read_mpt_file
    capacity, voltage, cycles, charge_mask, discharge_mask = \
        read_mpt_file(ec_file, mode='gc', mass_mg=args.mass)
    
    # Now we have:
    # capacity = array of capacity values
    # voltage = array of voltage values  
    # cycles = array of cycle numbers
    # charge_mask = which points are charging
    # discharge_mask = which points are discharging
```

**In Plain English:**
- The program opens your file
- It reads all the numbers inside
- It organizes them into:
  - Capacity measurements
  - Voltage measurements
  - Which cycle each measurement belongs to
  - Whether each point is charging or discharging

---

#### Step 5: Process the Data

**Location:** `batplot/modes.py` → `handle_gc_mode()`

**What happens:**
```python
    # Step 5.1: Group data by cycles
    cycle_dict = {}  # Empty dictionary to store cycles
    
    for cycle_num in unique_cycles:
        # Find all data points for this cycle
        cycle_mask = (cycles == cycle_num)
        
        # Split into charge and discharge
        charge_data = data[cycle_mask & charge_mask]
        discharge_data = data[cycle_mask & discharge_mask]
        
        # Store in dictionary
        cycle_dict[cycle_num] = {
            'charge': charge_data,
            'discharge': discharge_data
        }
```

**In Plain English:**
- The program goes through all the data
- It groups measurements by cycle number
- For each cycle, it separates charging from discharging
- It stores everything in an organized way

---

#### Step 6: Create the Plot

**Location:** `batplot/modes.py` → `handle_gc_mode()`

**What happens:**
```python
    # Step 6.1: Create a figure (empty canvas)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Step 6.2: Plot each cycle
    colors = plt.cm.viridis(np.linspace(0, 1, len(cycle_dict)))
    
    for cycle_num, cycle_data in cycle_dict.items():
        color = colors[cycle_num - 1]  # Pick a color
        
        # Plot charge curve
        ax.plot(cycle_data['charge']['capacity'],
                cycle_data['charge']['voltage'],
                color=color, label=f'Cycle {cycle_num}')
        
        # Plot discharge curve
        ax.plot(cycle_data['discharge']['capacity'],
                cycle_data['discharge']['voltage'],
                color=color)
    
    # Step 6.3: Add labels
    ax.set_xlabel('Capacity (mAh/g)')
    ax.set_ylabel('Voltage (V)')
    ax.legend()
```

**In Plain English:**
- The program creates a blank graph
- It draws a line for each cycle
- Each cycle gets a different color
- It adds axis labels and a legend
- The plot appears on your screen

---

#### Step 7: Launch Interactive Menu (if requested)

**Location:** `batplot/modes.py` → `handle_gc_mode()` → `batplot/electrochem_interactive.py`

**What happens:**
```python
    if args.interactive:
        # Launch the interactive menu
        from .electrochem_interactive import electrochem_interactive_menu
        electrochem_interactive_menu(fig, ax, cycle_lines)
```

**Then in `electrochem_interactive.py`:**
```python
def electrochem_interactive_menu(fig, ax, cycle_lines):
    while True:  # Loop forever until user quits
        # Step 7.1: Show menu
        print_menu()
        
        # Step 7.2: Wait for user input
        cmd = input("Press a key: ").strip().lower()
        
        # Step 7.3: Handle the command
        if cmd == 'c':  # User pressed 'c' for colors
            # Change colors
        elif cmd == 'q':  # User pressed 'q' to quit
            break
        # ... more commands
```

**In Plain English:**
- The program shows you a menu of options
- It waits for you to press a key
- When you press a key, it does something:
  - Press 'c' → Change colors
  - Press 'f' → Change fonts
  - Press 'q' → Quit
- It loops until you quit

---

#### Step 8: Exit

**Location:** Various files

**What happens:**
- The program saves the plot if you requested it
- It cleans up (closes files, releases memory)
- It returns to the terminal

---

## Key Concepts Explained Simply

### 1. Command-Line Arguments

**What they are:** Options you type after the command name.

**Example:**
```
batplot --gc file.mpt --mass 7.0
```

**Breaking it down:**
- `batplot` - The program name
- `--gc` - A flag (tells the program: "use GC mode")
- `file.mpt` - A file name (the data to process)
- `--mass 7.0` - An option with a value (mass is 7.0 mg)

**In the code:**
```python
args.gc = True        # Because you used --gc
args.files = ['file.mpt']  # Your file
args.mass = 7.0       # Because you used --mass 7.0
```

### 2. Modes

**What they are:** Different ways to plot data.

**Types of modes:**
- **GC mode** (`--gc`): Galvanostatic cycling - plots voltage vs capacity for cycles
- **CV mode** (`--cv`): Cyclic voltammetry - plots current vs voltage
- **dQdV mode** (`--dqdv`): Differential capacity - shows dQ/dV vs voltage
- **CPC mode** (`--cpc`): Capacity per cycle - shows capacity fade over cycles
- **Operando mode** (`--operando`): Contour plots of operando data
- **XY mode** (default): Regular XY plots (XRD, PDF, etc.)

**Simple analogy:** 
- Like different types of charts: bar chart, line chart, pie chart
- Each mode creates a different type of visualization

### 3. File Formats

**What they are:** Different ways data is stored in files.

**Common formats in batplot:**
- **.mpt**: BioLogic native format (binary, contains lots of metadata)
- **.csv**: Comma-separated values (text file, like Excel)
- **.xye**: X-Y with errors (three columns: X, Y, error)
- **.xy**: X-Y data (two columns)
- **.qye**: Q-space with errors (for PDF data)

**Why different readers?**
- Each format stores data differently
- Like different languages - need different translators
- `read_mpt_file()` reads .mpt files
- `read_ec_csv_file()` reads .csv files

### 4. Interactive Menus

**What they are:** Menus that let you customize plots in real-time.

**How they work:**
1. Program shows a menu with options
2. You press a key (like 'c' for colors)
3. Program does something (changes colors)
4. Plot updates immediately
5. Menu appears again
6. Repeat until you press 'q' to quit

**Example menu:**
```
Interactive menu:
  c: colors
  f: fonts
  s: save
  q: quit

Press a key: c
```

**In the code:**
```python
while True:  # Keep looping
    cmd = input("Press a key: ")
    
    if cmd == 'c':
        # Change colors code here
    elif cmd == 'q':
        break  # Exit the loop
```

### 5. Sessions

**What they are:** Saved states of your plot that you can reload later.

**What gets saved:**
- Your data
- Plot settings (colors, fonts, ranges)
- Axis limits
- Label text
- Everything needed to recreate the plot

**File format:** `.pkl` files (Python pickle format)

**Simple analogy:**
- Like saving a game - you can come back and continue where you left off
- All your customizations are preserved

**In the code:**
```python
# Save session
dump_session("my_plot.pkl", fig=fig, ax=ax, ...)

# Load session later
load_session("my_plot.pkl")
```

### 6. Styles

**What they are:** Reusable plot appearance settings.

**What gets saved:**
- Colors
- Fonts
- Line widths
- Tick settings
- Everything about appearance (NOT the data)

**File formats:**
- `.bps` - Style only
- `.bpsg` - Style + geometry (sizes, positions)

**Simple analogy:**
- Like a theme for your phone
- You can apply the same theme to different wallpapers
- Style is the theme, data is the wallpaper

**Difference from sessions:**
- **Session**: Saves data + appearance (can only use with same data)
- **Style**: Saves appearance only (can use with any data)

### 7. Batch Processing

**What it is:** Processing multiple files automatically.

**How it works:**
1. Program finds all matching files in a folder
2. Processes each file one by one
3. Saves each plot automatically
4. No interaction needed

**Example:**
```
batplot --gc --all --mass 7.0
```

**In Plain English:**
- Find all .mpt and .csv files in current folder
- Process each one in GC mode
- Save each plot as SVG file
- Use mass 7.0 mg for all

**In the code:**
```python
def batch_process_ec(directory, args):
    # Find all files
    files = find_ec_files(directory)
    
    # Process each file
    for file in files:
        process_file(file, args)
        save_plot(file)
```

---

## Common Tasks: How to Make Changes

### Task 1: Adding a New Command to an Interactive Menu

**Goal:** Add a new menu option, like 'x' to export data.

**Steps:**

1. **Find the menu file** (e.g., `electrochem_interactive.py` for GC/CV plots)

2. **Find the menu display function:**
```python
def _print_menu():
    print(" c: colors")
    print(" f: fonts")
    print(" x: export data")  # ← Add your new option here
    print(" q: quit")
```

3. **Find the command handler (the main loop):**
```python
while True:
    cmd = _safe_input("Press a key: ").strip().lower()
    
    if cmd == 'c':
        # Handle colors
    elif cmd == 'f':
        # Handle fonts
    elif cmd == 'x':  # ← Add your new command here
        # Your code to export data
        export_data_to_csv(cycle_lines)
    elif cmd == 'q':
        break
```

4. **Write your code:**
```python
def export_data_to_csv(cycle_lines):
    """Export cycle data to CSV file."""
    filename = _safe_input("Enter filename: ").strip()
    if not filename:
        return
    
    # Open file for writing
    with open(filename, 'w') as f:
        f.write("Cycle,Capacity,Voltage\n")  # Header
        
        # Write data for each cycle
        for cycle_num, lines in cycle_lines.items():
            if lines['charge']:
                x_data = lines['charge'].get_xdata()
                y_data = lines['charge'].get_ydata()
                for x, y in zip(x_data, y_data):
                    f.write(f"{cycle_num},{x},{y}\n")
    
    print(f"Data exported to {filename}")
```

**What each part does:**
- `with open(...)` - Opens a file for writing
- `f.write(...)` - Writes text to the file
- The loop goes through each cycle and writes the data
- `zip(x_data, y_data)` - Pairs up x and y values

---

### Task 2: Adding Support for a New File Format

**Goal:** Add support for reading `.xyz` files.

**Steps:**

1. **Open `readers.py`**

2. **Add a new reader function:**
```python
def read_xyz_file(filename: str, mode: str = 'xy'):
    """Read .xyz file format.
    
    Args:
        filename: Path to .xyz file
        mode: What type of data to extract ('xy', 'gc', etc.)
    
    Returns:
        Depends on mode. For 'xy': (x_data, y_data) as numpy arrays
    """
    # Read the file
    data = np.loadtxt(filename, skiprows=2)  # Skip first 2 lines
    
    # Extract columns
    x_data = data[:, 0]  # First column
    y_data = data[:, 1]  # Second column
    
    return x_data, y_data
```

3. **Update the mode handler to use it:**
```python
# In modes.py or batplot.py
if filename.endswith('.xyz'):
    from .readers import read_xyz_file
    x_data, y_data = read_xyz_file(filename)
    # Now plot x_data vs y_data
```

**What each part does:**
- `np.loadtxt()` - Reads numbers from a text file
- `skiprows=2` - Skips the first 2 lines (header)
- `data[:, 0]` - Gets all rows, column 0 (first column)
- Returns the data so other code can use it

---

### Task 3: Changing Default Colors

**Goal:** Change the default color scheme for cycles.

**Steps:**

1. **Find where colors are assigned** (usually in the mode handler or interactive menu)

2. **Locate the color assignment:**
```python
# Current code might look like:
colors = plt.cm.viridis(np.linspace(0, 1, num_cycles))
```

3. **Change to a different colormap:**
```python
# Option 1: Use a different built-in colormap
colors = plt.cm.plasma(np.linspace(0, 1, num_cycles))

# Option 2: Use a custom color list
color_list = ['#FF0000', '#00FF00', '#0000FF']  # Red, Green, Blue
colors = [color_list[i % len(color_list)] for i in range(num_cycles)]
```

**What each part does:**
- `plt.cm.viridis` - A colormap (a range of colors)
- `np.linspace(0, 1, num_cycles)` - Creates evenly spaced numbers from 0 to 1
- The colormap converts these numbers to colors
- `color_list[i % len(color_list)]` - Cycles through your color list

---

### Task 4: Adding a New Plotting Mode

**Goal:** Add a "Power vs Time" mode.

**Steps:**

1. **Add argument in `args.py`:**
```python
# In build_parser() function
parser.add_argument('--power', action='store_true',
                   help='Plot power vs time')
```

2. **Add handler function in `modes.py`:**
```python
def handle_power_mode(args) -> int:
    """Handle power vs time plotting mode."""
    # Check input
    if len(args.files) != 1:
        print("Power mode: provide exactly one file")
        return 1
    
    # Read data (you'll need to implement this)
    from .readers import read_mpt_file
    time, current, voltage = read_mpt_file(args.files[0], mode='power')
    
    # Calculate power: P = I * V
    power = current * voltage
    
    # Create plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(time, power)
    ax.set_xlabel('Time (h)')
    ax.set_ylabel('Power (W)')
    ax.set_title('Power vs Time')
    
    # Save or show
    if args.out:
        fig.savefig(args.out, dpi=300)
    else:
        plt.show()
    
    return 0
```

3. **Add routing in `batplot.py`:**
```python
# In batplot_main() function
if args.power:
    from .modes import handle_power_mode
    return handle_power_mode(args)
```

**What each part does:**
- `action='store_true'` - Makes `--power` a flag (True if present)
- `power = current * voltage` - Calculates power (multiplies current and voltage)
- `ax.plot(time, power)` - Draws the line on the graph
- `ax.set_xlabel()` - Adds label to x-axis

---

### Task 5: Fixing a Bug

**Goal:** Fix a bug where colors don't update correctly.

**Steps:**

1. **Reproduce the bug:**
   - Run the program
   - Do the steps that cause the bug
   - Note what goes wrong

2. **Find the relevant code:**
   - Look for error messages in the output
   - Search for keywords in the code
   - Use grep: `grep -r "color" batplot/`

3. **Understand what should happen:**
   - Read the code around the bug
   - Trace through the logic
   - Identify where it goes wrong

4. **Make a small fix:**
   - Change only what's necessary
   - Test immediately
   - Don't change unrelated code

5. **Test the fix:**
   - Run the program again
   - Try the same steps
   - Make sure the bug is gone
   - Make sure nothing else broke

**Example bug fix:**

**Problem:** Colors don't update when you press 'c' in the menu.

**Finding the code:**
```bash
grep -n "cmd == 'c'" batplot/electrochem_interactive.py
```

**Looking at the code:**
```python
elif cmd == 'c':
    # Change colors
    new_color = input("Enter color: ")
    # ... but colors don't actually get applied to the plot
```

**The fix:**
```python
elif cmd == 'c':
    # Change colors
    new_color = _safe_input("Enter color: ").strip()
    
    # Actually apply the color to all cycles
    for cycle_num, lines in cycle_lines.items():
        if lines['charge']:
            lines['charge'].set_color(new_color)
        if lines['discharge']:
            lines['discharge'].set_color(new_color)
    
    # Update the display
    fig.canvas.draw_idle()
```

**What changed:**
- Added code to actually change the colors
- Added `fig.canvas.draw_idle()` to update the display
- Now when you change colors, the plot updates

---

## Troubleshooting: When Things Go Wrong

### Problem 1: "Module not found" Error

**Error message:**
```
ModuleNotFoundError: No module named 'batplot'
```

**What it means:** Python can't find the batplot code.

**Solutions:**

1. **Make sure you're in the right directory:**
```bash
cd /path/to/batplot_script
```

2. **Install the package:**
```bash
pip install -e .
```

The `-e` means "editable" - changes to code take effect immediately.

3. **Or add the path manually:**
```python
import sys
sys.path.insert(0, '/path/to/batplot_script')
```

---

### Problem 2: "ImportError" or "Circular Import"

**Error message:**
```
ImportError: cannot import name 'something' from 'batplot.other_module'
```

**What it means:** Two modules are trying to import each other, creating a loop.

**Solutions:**

1. **Move the import inside the function:**
```python
# Bad (at top of file):
from .other_module import function_a

# Good (inside function):
def my_function():
    from .other_module import function_a  # Import here instead
    function_a()
```

2. **Use a different import structure:**
```python
# Instead of importing the function, import the module:
from . import other_module

# Then use: other_module.function_a()
```

---

### Problem 3: Plot Doesn't Appear

**Symptoms:** Code runs but no window opens.

**Possible causes:**

1. **Non-interactive backend:**
```python
# Check backend
print(plt.get_backend())

# Fix: Set interactive backend
import matplotlib
matplotlib.use('TkAgg')  # or 'Qt5Agg' or 'MacOSX'
```

2. **Forgot to call `plt.show()`:**
```python
# Make sure you have:
plt.show()  # This displays the plot
```

3. **Plotting in batch mode:**
- If `--all` flag is used, plots are saved, not shown
- This is expected behavior

---

### Problem 4: Changes Don't Take Effect

**Symptoms:** You changed code but nothing happens.

**Solutions:**

1. **If installed with `pip install -e .`:**
   - Changes should take effect immediately
   - Try restarting Python/your terminal

2. **If installed normally:**
   - Reinstall: `pip install -e .`
   - Or reinstall: `pip install --force-reinstall .`

3. **Clear Python cache:**
```bash
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -r {} +
```

---

### Problem 5: "AttributeError" or "KeyError"

**Error message:**
```
AttributeError: 'NoneType' object has no attribute 'something'
```

**What it means:** You're trying to use something that doesn't exist (is None).

**Example:**
```python
data = None  # data is None (empty)
data.length  # Error! None doesn't have a 'length' attribute
```

**Solutions:**

1. **Check if it exists first:**
```python
if data is not None:
    length = data.length
else:
    print("Data is empty")
```

2. **Provide a default:**
```python
length = data.length if data is not None else 0
```

---

### Problem 6: Understanding Error Messages

**Python error messages look scary but they're helpful!**

**Example error:**
```
Traceback (most recent call last):
  File "batplot/modes.py", line 450, in handle_gc_mode
    capacity = data['capacity']
KeyError: 'capacity'
```

**Reading it:**
1. **Traceback** - Shows the path the error took through your code
2. **File "batplot/modes.py"** - The file where the error occurred
3. **line 450** - The line number
4. **in handle_gc_mode** - The function name
5. **KeyError: 'capacity'** - The actual error (tried to find 'capacity' key but it doesn't exist)

**What to do:**
1. Open `batplot/modes.py`
2. Go to line 450
3. Look at the code around that line
4. Understand what went wrong
5. Fix it

---

## Glossary: Simple Explanations

### Programming Terms

**Argument / Parameter:**
- Information you give to a function
- Like ingredients you give to a recipe

**Array:**
- A list of numbers stored efficiently
- Like a column in a spreadsheet

**Boolean:**
- True or False
- Like a light switch (on or off)

**Class:**
- A blueprint for creating objects
- Like a cookie cutter that makes cookies

**Dictionary (dict):**
- Storage with labeled boxes
- Like a filing cabinet with labeled drawers

**Function:**
- A reusable piece of code
- Like a recipe you can use many times

**Import:**
- Bringing code from another file into your file
- Like borrowing a tool from a neighbor

**List:**
- An ordered collection of items
- Like a shopping list

**Loop:**
- Repeating code multiple times
- Like a washing machine cycle

**Module:**
- A Python file containing code
- Like a single book in a library

**Package:**
- A folder containing multiple modules
- Like a library shelf with multiple books

**String:**
- Text data
- Like a word or sentence in quotes: "hello"

**Variable:**
- A named storage box for data
- Like a labeled container

### Batplot-Specific Terms

**Batch Mode:**
- Processing multiple files automatically
- Like a factory assembly line

**CLI (Command Line Interface):**
- Typing commands in terminal instead of clicking buttons
- Like talking to the computer with text

**Colormap:**
- A range of colors for plotting
- Like a color palette

**Cycle:**
- One complete charge/discharge of a battery
- Like one round trip

**GC Mode (Galvanostatic Cycling):**
- Plotting voltage vs capacity for battery cycles
- Shows how battery performs over many cycles

**Interactive Menu:**
- A menu where you press keys to change the plot
- Like a remote control for your plot

**Mode:**
- A different way to plot data
- Like different chart types (bar, line, pie)

**Session:**
- A saved state of your plot
- Like a saved game you can reload

**Style:**
- Appearance settings (colors, fonts, etc.)
- Like a theme you can reuse

---

## How to Read Code

### Step 1: Start at the Top

Always start reading a function from the top. The top usually explains what the function does.

```python
def read_mpt_file(filename: str, mode: str = 'gc'):
    """Read BioLogic .mpt file.
    
    This function reads battery cycling data from a .mpt file
    and returns the data in a format that batplot can use.
    
    Args:
        filename: Path to the .mpt file
        mode: What type of data to extract ('gc', 'cv', etc.)
    
    Returns:
        A tuple of (capacity, voltage, cycles, charge_mask, discharge_mask)
    """
```

**What this tells you:**
- Function name: `read_mpt_file`
- What it does: Reads .mpt files
- What it needs: A filename and mode
- What it gives back: Capacity, voltage, cycles, and masks

### Step 2: Look for the Main Logic

After the docstring, find the main code that does the work.

```python
    # Open the file
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    # Parse the data
    capacity = []
    voltage = []
    # ... more parsing code
    
    return capacity, voltage, cycles, charge_mask, discharge_mask
```

**What this tells you:**
- Opens the file
- Reads the lines
- Parses (processes) the data
- Returns the results

### Step 3: Understand the Flow

Follow the code line by line:

```python
# Line 1: Do something
result = calculate_something()

# Line 2: Check if result is good
if result > 0:
    # Line 3: Do this if result is good
    print("Success")
else:
    # Line 4: Do this if result is not good
    print("Failed")
```

**Reading order:**
1. Line 1 executes
2. Line 2 checks a condition
3. If True → Line 3 executes
4. If False → Line 4 executes

### Step 4: Don't Get Lost in Details

If you see a function call you don't understand:

```python
data = process_complex_calculation(input_data)
```

**Don't worry about what `process_complex_calculation()` does inside!**

Just understand:
- It takes `input_data`
- It returns `data`
- You use `data` later

**You can look inside later if you need to, but don't get distracted.**

---

## Common Code Patterns in Batplot

### Pattern 1: Reading Files

```python
def read_some_file(filename: str):
    """Read a file and return data."""
    # Open file
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    # Process lines
    data = []
    for line in lines:
        # Parse each line
        values = line.split(',')  # Split by comma
        data.append(float(values[0]))  # Convert to number
    
    return data
```

**Key points:**
- `with open()` - Safely opens and closes file
- `readlines()` - Reads all lines
- Loop through lines
- Process each line
- Return results

### Pattern 2: Processing Data

```python
# Group data by cycles
cycle_dict = {}
for i, cycle_num in enumerate(cycles):
    if cycle_num not in cycle_dict:
        cycle_dict[cycle_num] = []  # Create new list for this cycle
    cycle_dict[cycle_num].append(data[i])  # Add data point
```

**Key points:**
- Create empty dictionary
- Loop through data
- Check if cycle exists in dictionary
- If not, create it
- Add data to cycle's list

### Pattern 3: Creating Plots

```python
# Create figure
fig, ax = plt.subplots(figsize=(10, 6))

# Plot data
ax.plot(x_data, y_data, color='blue', label='Data')

# Customize
ax.set_xlabel('X Axis')
ax.set_ylabel('Y Axis')
ax.legend()

# Show or save
plt.show()
```

**Key points:**
- `plt.subplots()` - Creates figure and axes
- `ax.plot()` - Draws a line
- `ax.set_xlabel()` - Adds labels
- `plt.show()` - Displays plot

### Pattern 4: Interactive Menu Loop

```python
while True:  # Loop forever
    # Show menu
    print_menu()
    
    # Get user input
    cmd = input("Press a key: ").strip().lower()
    
    # Handle commands
    if cmd == 'q':
        break  # Exit loop
    elif cmd == 'c':
        # Handle 'c' command
        change_colors()
    # ... more commands
    
    # Update plot
    fig.canvas.draw_idle()
```

**Key points:**
- `while True` - Loop forever
- Show menu each iteration
- Get user input
- Handle different commands
- `break` to exit
- Update plot after changes

### Pattern 5: Error Handling

```python
try:
    # Try to do something
    data = read_file(filename)
    process_data(data)
except FileNotFoundError:
    # Handle file not found
    print(f"File not found: {filename}")
except ValueError as e:
    # Handle invalid data
    print(f"Invalid data: {e}")
except Exception as e:
    # Handle any other error
    print(f"Unexpected error: {e}")
```

**Key points:**
- `try` - Attempt the code
- `except` - Handle errors
- Specific error types first
- Generic `Exception` last
- Print helpful error messages

---

## Where to Find Things

### I Want to...

**...change how command-line arguments work:**
→ Look in `batplot/args.py`

**...change how files are read:**
→ Look in `batplot/readers.py`

**...change how plots are created:**
→ Look in `batplot/modes.py` or `batplot/batplot.py`

**...change interactive menu options:**
→ Look in the `*_interactive.py` files:
- `interactive.py` - XY plots
- `electrochem_interactive.py` - GC/CV/dQdV
- `cpc_interactive.py` - Capacity per cycle
- `operando_ec_interactive.py` - Operando plots

**...change how sessions are saved/loaded:**
→ Look in `batplot/session.py`

**...change how styles work:**
→ Look in `batplot/style.py`

**...find utility functions:**
→ Look in `batplot/utils.py`

**...understand the overall flow:**
→ Look in `batplot/cli.py` and `batplot/batplot.py`

---

## Testing Your Changes

### Manual Testing

**The best way to test is to actually use the program:**

1. **Make your change**

2. **Run the program:**
```bash
python -m batplot.cli --gc test_file.mpt --mass 7.0 --interactive
```

3. **Try the feature you changed:**
   - If you changed colors, try changing colors
   - If you changed file reading, try reading a file
   - If you changed the menu, try using the menu

4. **Check that it works correctly:**
   - Does it do what you expect?
   - Are there any error messages?
   - Does it work with different inputs?

5. **Check that you didn't break anything:**
   - Try other features
   - Try different file types
   - Try different modes

### Common Test Cases

**Test with different file formats:**
```bash
# Test .mpt file
batplot --gc test.mpt --mass 7.0

# Test .csv file
batplot --gc test.csv

# Test .xye file
batplot test.xye --xaxis 2theta
```

**Test with different modes:**
```bash
# Test GC mode
batplot --gc test.mpt --mass 7.0

# Test CV mode
batplot --cv test.mpt

# Test batch mode
batplot --gc --all --mass 7.0
```

**Test interactive features:**
```bash
# Test interactive menu
batplot --gc test.mpt --mass 7.0 --interactive

# Try different menu commands
# Press 'c' for colors
# Press 'f' for fonts
# Press 's' to save
# Press 'q' to quit
```

---

## Getting Help

### When You're Stuck

1. **Read error messages carefully:**
   - They tell you what went wrong
   - They tell you where (file and line number)
   - They often suggest the problem

2. **Search the code:**
   ```bash
   # Find where a function is defined
   grep -r "def function_name" batplot/
   
   # Find where a function is used
   grep -r "function_name" batplot/
   
   # Find a specific error message
   grep -r "error message" batplot/
   ```

3. **Add print statements:**
   ```python
   print(f"DEBUG: Variable value is {variable}")
   print(f"DEBUG: At line X, data looks like {data}")
   ```
   This helps you see what's happening inside the code.

4. **Check similar code:**
   - Find similar functionality
   - See how it's done there
   - Copy the pattern

5. **Ask for help:**
   - Describe what you're trying to do
   - Describe what's going wrong
   - Show the error message
   - Show the relevant code

---

## Best Practices

### When Making Changes

1. **Make small changes:**
   - Change one thing at a time
   - Test after each change
   - If something breaks, you know what caused it

2. **Keep it simple:**
   - Simple code is easier to understand
   - Simple code has fewer bugs
   - Don't overcomplicate things

3. **Follow existing patterns:**
   - Look at how similar things are done
   - Use the same style
   - Consistency helps everyone

4. **Add comments:**
   - Explain WHY, not WHAT
   - Comment complex logic
   - Update comments when you change code

5. **Test thoroughly:**
   - Test normal cases
   - Test edge cases (empty files, very large files, etc.)
   - Test that you didn't break anything

### Code Style

**Naming:**
- Functions: `snake_case` (like `read_file`)
- Variables: `snake_case` (like `file_name`)
- Constants: `UPPER_CASE` (like `MAX_CYCLES`)

**Formatting:**
- Use 4 spaces for indentation (not tabs)
- Put blank lines between functions
- Keep lines under 100 characters when possible

**Comments:**
```python
# Good comment: explains WHY
# Merge half-cycles because Neware CSV files sometimes
# split one cycle into two entries
merge_half_cycles(data)

# Bad comment: just repeats WHAT the code says
# Merge half cycles
merge_half_cycles(data)
```

---

## Summary: The Big Picture

**Batplot is organized like a well-run restaurant:**

1. **cli.py** - The host (greets you, checks reservations/version)
2. **batplot.py** - The head waiter (takes your order, routes to right station)
3. **args.py** - The menu (defines all available options)
4. **modes.py** - The chefs (handle different types of orders)
5. **readers.py** - The prep cooks (prepare ingredients/data)
6. **Interactive menus** - The servers (take customization requests)
7. **session.py & style.py** - The storage (saves recipes and themes)

**When you want to make a change:**

1. **Identify which "station" handles it:**
   - File reading? → `readers.py`
   - Plotting? → `modes.py`
   - Menu options? → `*_interactive.py`

2. **Find the relevant function:**
   - Use grep to search
   - Read the function
   - Understand what it does

3. **Make your change:**
   - Change only what's necessary
   - Follow existing patterns
   - Add comments if needed

4. **Test it:**
   - Run the program
   - Try your change
   - Make sure nothing broke

**Remember:**
- Start simple
- Understand before changing
- Test often
- Ask for help when stuck

---

## Final Words

This guide is meant to help you understand batplot's codebase even if you're completely new to programming. Don't worry if some concepts seem confusing at first - that's normal! 

**Key takeaways:**
- Code is just instructions for the computer
- Functions are reusable recipes
- The code flows from top to bottom (with some routing)
- Making changes is like modifying a recipe - small changes are safer
- When in doubt, look at similar code to see how it's done

**You've got this!** Start small, be patient, and don't hesitate to explore. Every expert was once a beginner.

---

**Good luck with your batplot development journey!**

---



