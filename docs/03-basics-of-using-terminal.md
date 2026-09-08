# 3. Basics of using terminal

The terminal (using Anaconda Prompt) is a text-based interface where you type commands to control your computer. *batplot* runs entirely from the terminal, so knowing a few basic navigation commands is all you need to get started. The sections below cover the essentials.

__Seeing Your Current Location: pwd__

If you ever lose track of where you are, type pwd (print working directory) and press Enter. The terminal prints the full path of your current folder. 

pwd

__Navigating Between Folders: cd__

The cd command (change directory) moves you from one folder to another. Type cd followed by the path of the folder you want to enter, then press Enter. The prompt updates to confirm your new location. If the folder name contains spaces, enclose the entire path in quotation marks.

**Enter a subfolder called Data**

```text
cd Data
```

**Go up one level to the parent folder**

```text
cd ..
```

**Jump directly to a folder using its full path**

```text
cd C:\\Users\\YourName\\Documents\\XRD_Data
```

```text
batplot xrd.xy --xaxis 2theta --I # Using batplot to plot an XRD data file
```

The shorthand .. always means the parent folder (one level up). Chaining it — for example cd ..\\..  — moves up two levels. A full (absolute) path like the example above works regardless of where you currently are.

__Listing Files in a Folder: ls / dir__

To see the files and folders inside your current directory, use ls on macOS / Linux, or dir on Windows Anaconda Prompt. This is useful for confirming that your data files are present before running a batplot command.

**macOS / Linux**

```text
ls
```

**Windows Anaconda Prompt**

```text
dir
```

__Tab Completion__

After typing the first few characters of a name, press the Tab key and the terminal will complete the name automatically. If more than one match exists, pressing Tab again cycles through the options. 

__Recalling Previous Commands: Arrow Keys__

Press the up arrow key to scroll back through previously entered commands. This is especially useful when you want to repeat a batplot command with a small change, press the up arrow, edit the line, and press Enter to run it again.

__Tip: __On Windows, the quickest way to navigate to a data folder is to open it in File Explorer, click the address bar to select the path, copy it, and then paste it into Anaconda Prompt after cd. On macOS, you can drag a folder from Finder directly into the Terminal window to insert its full path automatically.
