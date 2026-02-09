"""Developer-only upgrade functionality for batplot.

This module provides a convenient way to upgrade batplot to PyPI directly
from the command line. It's only available when running from the development
directory.

Usage:
    batplot --dev-upgrade

This will:
1. Read the latest ## VERSION from RELEASE_NOTES.txt (or prompt if none)
2. Clean old build files
3. Update version in __init__.py and pyproject.toml
4. Build the package
5. Upload to PyPI
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional


def is_dev_environment():
    """Check if we're running from the development directory."""
    # Check if we're in the batplot package directory
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    project_root = package_dir.parent
    
    # Check for development indicators
    has_pyproject = (project_root / "pyproject.toml").exists()
    has_upgrade_script = (project_root / "upgrade.sh").exists()
    has_batplot_dir = (project_root / "batplot").is_dir()
    
    return has_pyproject and has_batplot_dir


def get_current_version():
    """Get the current version from __init__.py."""
    try:
        from . import __version__
        return __version__
    except Exception:
        return None


def parse_release_notes_blocks(content: str) -> dict:
    """Parse RELEASE_NOTES.txt into a dict: version -> notes text.
    
    Expects blocks like:
        ## 1.8.14
        - Fix one
        - Fix two
        
        ## 1.8.15
        - Fix three
    
    Returns:
        Dict mapping version string to notes string (e.g. {"1.8.14": "- Fix one\n- Fix two", ...})
    """
    import re
    version_marker = re.compile(r'^##\s+(\d+\.\d+\.\d+(?:\.\d+)?)\s*$')
    blocks = {}
    current_version = None
    current_lines = []
    
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip comment lines but NOT version markers (## 1.2.3)
        if stripped.startswith('#') and not version_marker.match(stripped):
            continue
        match = version_marker.match(stripped)
        if match:
            if current_version is not None:
                blocks[current_version] = '\n'.join(current_lines).strip()
            current_version = match.group(1)
            current_lines = []
        elif current_version is not None:
            current_lines.append(line.rstrip())
    
    if current_version is not None:
        blocks[current_version] = '\n'.join(current_lines).strip()
    
    return blocks


def get_latest_version_from_release_notes(project_root: Path) -> Optional[str]:
    """Read RELEASE_NOTES.txt and return the latest ## VERSION (by version number).
    
    Returns:
        Version string (e.g. '1.8.20') or None if no ## VERSION blocks found.
    """
    release_notes_file = project_root / "RELEASE_NOTES.txt"
    if not release_notes_file.exists():
        return None
    blocks = parse_release_notes_blocks(release_notes_file.read_text())
    if not blocks:
        return None
    try:
        # Sort by version tuple (e.g. 1.8.20 -> (1, 8, 20)) and take the max
        sorted_versions = sorted(
            blocks.keys(),
            key=lambda v: tuple(int(x) for x in v.split('.')),
        )
        return sorted_versions[-1]
    except (ValueError, AttributeError):
        return None


def update_version_check_update_info(project_root: Path, update_notes: str) -> None:
    """Write release notes into version_check.py UPDATE_INFO so users see them in the update notification."""
    if not update_notes or not update_notes.strip():
        return
    
    version_check_file = project_root / "batplot" / "version_check.py"
    if not version_check_file.exists():
        return
    
    lines = update_notes.strip().split('\n')
    # First line as custom_message (short summary)
    custom_message = lines[0].strip() if lines else ""
    # All lines as update_notes list (prefix with "- " if not already)
    update_notes_list = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not line.startswith('-'):
            line = '- ' + line
        update_notes_list.append(line)
    
    # Build the UPDATE_INFO dict as Python source
    custom_repr = repr(custom_message)
    notes_repr = '[\n        ' + ',\n        '.join(repr(n) for n in update_notes_list) + '\n    ]'
    
    new_block = f'''UPDATE_INFO = {{
    # Custom message to include in update notification
    # (Auto-filled from RELEASE_NOTES.txt when using batplot --dev-upgrade)
    'custom_message': {custom_repr},
    # Additional notes (auto-filled from RELEASE_NOTES.txt)
    'update_notes': {notes_repr},
    'show_update_notes': True,
}}'''
    
    content = version_check_file.read_text()
    import re
    # Replace the UPDATE_INFO = { ... } block (match from opening to closing })
    pattern = r'UPDATE_INFO = \{.*?\n\}\s*\n'
    new_content = re.sub(pattern, new_block + '\n\n', content, flags=re.DOTALL)
    if new_content != content:
        version_check_file.write_text(new_content)
        print("\033[0;32m✓ Updated version_check.py (users will see these notes when an update is available)\033[0m")


def write_latest_release_notes_json(project_root: Path, new_version: str, update_notes: str) -> None:
    """Write batplot/data/latest_release_notes.json so old installs can fetch and show what's new."""
    if not update_notes or not update_notes.strip():
        return
    lines = update_notes.strip().split('\n')
    custom_message = lines[0].strip() if lines else ""
    update_notes_list = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not line.startswith('-'):
            line = '- ' + line
        update_notes_list.append(line)
    data_dir = project_root / "batplot" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_file = data_dir / "latest_release_notes.json"
    import json
    payload = {"version": new_version, "custom_message": custom_message, "update_notes": update_notes_list}
    out_file.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print("\033[0;32m✓ Wrote batplot/data/latest_release_notes.json (commit & push so users see notes)\033[0m")


def update_version_files(project_root: Path, new_version: str):
    """Update version in __init__.py and pyproject.toml."""
    # Update __init__.py
    init_file = project_root / "batplot" / "__init__.py"
    content = init_file.read_text()
    updated = content.replace(
        f'__version__ = "{get_current_version()}"',
        f'__version__ = "{new_version}"'
    )
    init_file.write_text(updated)
    print(f"✓ Updated batplot/__init__.py")
    
    # Update pyproject.toml
    toml_file = project_root / "pyproject.toml"
    content = toml_file.read_text()
    import re
    updated = re.sub(
        r'version = "[^"]*"',
        f'version = "{new_version}"',
        content
    )
    toml_file.write_text(updated)
    print(f"✓ Updated pyproject.toml")


def clean_build_files(project_root: Path):
    """Clean old build files."""
    dirs_to_remove = ['dist', 'build', 'batplot.egg-info']
    for dir_name in dirs_to_remove:
        dir_path = project_root / dir_name
        if dir_path.exists():
            shutil.rmtree(dir_path)
    
    # Also remove any .egg-info directories
    for item in project_root.glob("*.egg-info"):
        if item.is_dir():
            shutil.rmtree(item)
    
    print("✓ Cleaned dist/, build/, and .egg-info directories")


def run_upgrade():
    """Run the upgrade process."""
    # Colors
    BLUE = '\033[0;34m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    NC = '\033[0m'
    
    print(f"{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"{BLUE}    Batplot Developer Upgrade{NC}")
    print(f"{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}\n")
    
    # Check if we're in dev environment
    if not is_dev_environment():
        print(f"{RED}Error: This command only works in the development environment.{NC}")
        print(f"You must run this from the batplot development directory.")
        return 1
    
    # Get project root
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    os.chdir(project_root)
    
    print(f"{YELLOW}Working directory:{NC} {project_root}\n")
    
    # Get current version
    current_version = get_current_version()
    print(f"{YELLOW}Current version:{NC} {current_version}")
    
    # New version: from RELEASE_NOTES.txt (latest ## VERSION) or prompt
    new_version = get_latest_version_from_release_notes(project_root)
    if new_version:
        print(f"{YELLOW}New version (from RELEASE_NOTES.txt):{NC} {new_version}")
    if not new_version:
        try:
            new_version = input("Enter new version number: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1
    
    if not new_version:
        print(f"{RED}Error: Version number cannot be empty. Add a ## VERSION line in RELEASE_NOTES.txt or enter it here.{NC}")
        return 1
    
    # Confirm
    print(f"\n{YELLOW}Version bump:{NC} {current_version} → {new_version}")
    try:
        confirm = input("Continue? (y/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return 1
    
    if confirm not in ('y', 'yes'):
        print("Aborted.")
        return 1
    
    # Check for RELEASE_NOTES.txt file
    release_notes_file = project_root / "RELEASE_NOTES.txt"
    update_notes = ""
    used_release_notes_file = False
    all_version_notes = {}  # version -> notes (for CHANGELOG merge)
    
    if release_notes_file.exists():
        raw = release_notes_file.read_text()
        blocks = parse_release_notes_blocks(raw)
        
        if blocks:
            all_version_notes = blocks
            # Use the block for the version we're releasing
            update_notes = blocks.get(new_version, "").strip()
            if not update_notes and blocks:
                # No block for this version: use last block (by version order)
                sorted_versions = sorted(blocks.keys(), key=lambda v: tuple(map(int, v.split('.'))))
                update_notes = blocks[sorted_versions[-1]].strip()
            used_release_notes_file = bool(update_notes)
            if update_notes:
                print(f"\n{GREEN}✓ Found release notes in RELEASE_NOTES.txt{NC}")
                if new_version in blocks:
                    print(f"   Using block for version {new_version}")
                else:
                    print(f"   Using notes for version {new_version} (from {len(blocks)} block(s))")
                print(f"{YELLOW}{update_notes[:200]}{'...' if len(update_notes) > 200 else ''}{NC}")
        else:
            # No ## VERSION blocks: treat whole file as one block (legacy)
            lines = [line for line in raw.splitlines() if line.strip() and not line.strip().startswith('#')]
            if lines:
                update_notes = '\n'.join(lines).strip()
                used_release_notes_file = True
                print(f"\n{GREEN}✓ Found release notes in RELEASE_NOTES.txt:{NC}")
                print(f"{YELLOW}{update_notes[:200]}{'...' if len(update_notes) > 200 else ''}{NC}")
    
    # If no notes from file, prompt for input
    if not update_notes:
        print(f"\n{YELLOW}Update notes (optional, press Enter to skip):{NC}")
        print("Describe what's new in this version:")
        print(f"{YELLOW}Examples:{NC}")
        print("  - Fixed font command crash in EC/GC mode")
        print("  - Fixed mathtext.fontset not restoring on undo")
        print("  - Added new feature X")
        print(f"\n{YELLOW}Tip:{NC} You can also write notes in RELEASE_NOTES.txt beforehand")
        print()
        try:
            update_notes = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            update_notes = ""
            print()
    
    # Save to CHANGELOG: merge all version blocks from RELEASE_NOTES (or single entry)
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    changelog_file = project_root / "CHANGELOG.md"
    
    if all_version_notes:
        import re
        # Parse existing CHANGELOG for versions already present
        existing_versions = set()
        if changelog_file.exists():
            existing = changelog_file.read_text()
            for m in re.finditer(r'^##\s*\[?(\d+\.\d+\.\d+(?:\.\d+)?)\]?\s*[- ]', existing, re.MULTILINE):
                existing_versions.add(m.group(1))
        # Add entries for each version in all_version_notes that isn't already there
        new_entries = []
        for ver in sorted(all_version_notes.keys(), key=lambda v: tuple(map(int, v.split('.')))):
            if ver not in existing_versions:
                new_entries.append(f"## [{ver}] - {today}\n{all_version_notes[ver]}\n")
        if new_entries:
            header = "# Changelog\n\n"
            if changelog_file.exists():
                existing = changelog_file.read_text()
                if existing.startswith("# Changelog"):
                    rest = existing.split("\n", 1)[-1].lstrip() if "\n" in existing else ""
                    changelog_file.write_text(header + "\n\n".join(new_entries) + "\n\n" + rest)
                else:
                    changelog_file.write_text(header + "\n\n".join(new_entries) + "\n\n" + existing)
            else:
                changelog_file.write_text(header + "\n\n".join(new_entries))
            print(f"\n{GREEN}✓ Added {len(new_entries)} version(s) to CHANGELOG.md{NC}")
    elif update_notes:
        # Single entry (from prompt or legacy single-block file)
        changelog_entry = f"## [{new_version}] - {today}\n{update_notes}\n"
        if changelog_file.exists():
            existing = changelog_file.read_text()
            if existing.startswith("# Changelog"):
                lines = existing.split('\n', 1)
                rest = lines[1].lstrip() if len(lines) > 1 else ""
                changelog_file.write_text(f"{lines[0]}\n\n{changelog_entry}\n{rest}")
            else:
                changelog_file.write_text(f"# Changelog\n\n{changelog_entry}\n{existing}")
        else:
            changelog_file.write_text(f"# Changelog\n\n{changelog_entry}")
        print(f"\n{GREEN}✓ Added to CHANGELOG.md{NC}")
    
    if update_notes:
        # So users see this message in the "new version available" notification
        update_version_check_update_info(project_root, update_notes)
        write_latest_release_notes_json(project_root, new_version, update_notes)
    else:
        print(f"\n{YELLOW}Skipped update notes{NC}")
    
    try:
        # Step 1: Clean
        print(f"\n{GREEN}[1/5]{NC} Cleaning old build files...")
        clean_build_files(project_root)
        
        # Step 2: Update versions
        print(f"\n{GREEN}[2/5]{NC} Updating version numbers...")
        update_version_files(project_root, new_version)
        
        # Verification
        print(f"\n{YELLOW}Verification:{NC}")
        init_file = project_root / "batplot" / "__init__.py"
        toml_file = project_root / "pyproject.toml"
        print(f"  __init__.py: {[line.strip() for line in init_file.read_text().splitlines() if '__version__' in line][0]}")
        print(f"  pyproject.toml: {[line.strip() for line in toml_file.read_text().splitlines() if line.startswith('version =')][0]}")
        
        # Sync CHANGELOG into package data so "v" shows it (no network)
        data_dir = project_root / "batplot" / "data"
        changelog_src = project_root / "CHANGELOG.md"
        changelog_dst = data_dir / "CHANGELOG.md"
        if changelog_src.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(changelog_src, changelog_dst)
            print(f"  {GREEN}✓ Synced CHANGELOG.md to package data (for 'v' command){NC}")
        
        # Step 3: Build
        print(f"\n{GREEN}[3/5]{NC} Building package...")
        result = subprocess.run([sys.executable, "-m", "build"], cwd=project_root)
        if result.returncode != 0:
            print(f"{RED}Build failed!{NC}")
            return 1
        print("✓ Package built successfully")
        
        # Step 4: Check dist
        print(f"\n{GREEN}[4/5]{NC} Checking distribution contents...")
        dist_dir = project_root / "dist"
        if dist_dir.exists():
            for item in dist_dir.iterdir():
                size = item.stat().st_size / 1024  # KB
                print(f"  {item.name} ({size:.1f} KB)")
        print("✓ Distribution files created")
        
        # Step 5: Upload
        print(f"\n{GREEN}[5/5]{NC} Uploading to PyPI...")
        # Twine uses ~/.pypirc (or TWINE_USERNAME / TWINE_PASSWORD). Do not hardcode credentials here.
        dist_dir = project_root / "dist"
        dist_files = [str(f) for f in dist_dir.iterdir()] if dist_dir.exists() else []
        if not dist_files:
            print(f"{RED}No files in dist/ to upload.{NC}")
            return 1
        result = subprocess.run(
            [sys.executable, "-m", "twine", "upload"] + dist_files,
            cwd=project_root,
        )
        
        if result.returncode != 0:
            print(f"{RED}Upload failed!{NC}")
            print(f"{RED}If you saw 403 Forbidden: use a PyPI API token (https://pypi.org/manage/account/token/)")
            print(f"  in ~/.pypirc as username=__token__ and password=pypi-...{NC}")
            return 1
        
        print(f"\n{GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
        print(f"{GREEN}✓ Successfully uploaded batplot v{new_version} to PyPI!{NC}")
        print(f"{GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
        
        # RELEASE_NOTES.txt is left unchanged so you can keep adding ## VERSION blocks for future releases.
        
        if update_notes:
            print(f"\n{BLUE}What's new:{NC}")
            for line in update_notes.split('\n'):
                print(f"  {line}")
        
        print(f"\n{BLUE}Installation command:{NC}")
        print(f"  pip install --upgrade batplot")
        print(f"\n{BLUE}View on PyPI:{NC}")
        print(f"  https://pypi.org/project/batplot/{new_version}/")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n{RED}Error during upgrade: {e}{NC}")
        return 1
