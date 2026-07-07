"""Developer-only release tooling for batplot.

This module is only available when running from the development directory.

Usage:
    batplot --dev-upgrade
        Bump version, build, upload to PyPI, commit, and push to GitHub.

    batplot --dev-git
        Sync release metadata and push to GitHub **without** a PyPI upload or
        version bump. Use after ``--dev-upgrade`` if the GitHub push failed, or
        to publish ``latest_release_notes.json`` so update notifications work.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
import json
import subprocess
import shutil
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


# Kept for tests that assert the old pathspec-based approach is not used.
GIT_STAGE_EXCLUDE_PATHS = (
    ":(exclude).DS_Store",
    ":(exclude)**/.DS_Store",
    ":(exclude)__pycache__/**",
    ":(exclude)**/__pycache__/**",
    ":(exclude)**/*.pyc",
    ":(exclude)**/*.pyo",
    ":(exclude)**/*.pyd",
    ":(exclude).pytest_cache/**",
    ":(exclude).ruff_cache/**",
    ":(exclude).mypy_cache/**",
    ":(exclude).pyright/**",
    ":(exclude).coverage",
    ":(exclude)htmlcov/**",
    ":(exclude)build/**",
    ":(exclude)dist/**",
    ":(exclude)*.egg-info/**",
    ":(exclude)**/*.egg-info/**",
)

# fnmatch patterns applied to repository-relative paths when adding untracked files.
GIT_STAGE_EXCLUDE_GLOBS = (
    ".DS_Store",
    "**/.DS_Store",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    ".pytest_cache/**",
    ".ruff_cache/**",
    ".mypy_cache/**",
    ".pyright/**",
    ".coverage",
    "htmlcov/**",
    "build/**",
    "dist/**",
    "*.egg-info/**",
    "**/*.egg-info/**",
    ".venv/**",
    "venv/**",
    "env/**",
)

# Paths intentionally kept out of GitHub release commits (PyPI/local-only assets).
GIT_RELEASE_SKIP_PATHS = (
    "batplot/data/USER_MANUAL.md",
    "batplot_user_manual.docx",
)


def _git_run(cmd: list[str], project_root: Path, *, check: bool = True, **kwargs):
    return subprocess.run(cmd, cwd=project_root, check=check, **kwargs)


def _git_current_branch(project_root: Path) -> str:
    result = _git_run(
        ["git", "branch", "--show-current"],
        project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    branch = (result.stdout or "").strip()
    return branch or "main"


def _path_matches_any_glob(relpath: str, patterns: tuple[str, ...]) -> bool:
    normalized = relpath.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatch(normalized, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
    return False


def _list_untracked_release_paths(project_root: Path) -> list[str]:
    """Return untracked, non-ignored repository paths eligible for release staging."""
    result = _git_run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "."],
        project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    paths: list[str] = []
    for line in (result.stdout or "").splitlines():
        relpath = line.strip().replace("\\", "/")
        if not relpath:
            continue
        if relpath in GIT_RELEASE_SKIP_PATHS:
            continue
        if _path_matches_any_glob(relpath, GIT_STAGE_EXCLUDE_GLOBS):
            continue
        paths.append(relpath)
    return sorted(paths)


def _git_unstage_release_skips(project_root: Path) -> None:
    """Keep local-only assets out of the release commit even when they are tracked."""
    for relpath in GIT_RELEASE_SKIP_PATHS:
        _git_run(["git", "reset", "HEAD", "--", relpath], project_root, check=False)


def _git_staged_paths(project_root: Path) -> list[str]:
    result = _git_run(
        ["git", "diff", "--cached", "--name-only"],
        project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _git_unstage_excluded_patterns(project_root: Path) -> None:
    """Drop bytecode, caches, and build artifacts from the index even if tracked."""
    staged = _git_staged_paths(project_root)
    to_reset = [
        relpath
        for relpath in staged
        if relpath in GIT_RELEASE_SKIP_PATHS or _path_matches_any_glob(relpath, GIT_STAGE_EXCLUDE_GLOBS)
    ]
    if to_reset:
        _git_run(["git", "reset", "HEAD", "--", *to_reset], project_root, check=False)


def _git_worktree_dirty(project_root: Path) -> bool:
    result = _git_run(
        ["git", "status", "--porcelain"],
        project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return bool((result.stdout or "").strip())


def _git_stash_worktree(project_root: Path, message: str) -> bool:
    """Stash unstaged/untracked changes. Returns True when a stash was created."""
    if not _git_worktree_dirty(project_root):
        return False
    stash_result = _git_run(
        ["git", "stash", "push", "-u", "-m", message],
        project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if stash_result.returncode != 0:
        return False
    combined = (stash_result.stdout or "") + (stash_result.stderr or "")
    return "No local changes to save" not in combined


def _git_stage_release_snapshot(project_root: Path) -> None:
    """Stage the repository snapshot that should replace GitHub on release.

    Uses ``git add -u`` for tracked updates/deletions, then adds only untracked
    paths reported by ``git ls-files --others --exclude-standard``. This avoids
    ``git add -- .`` failing when ignored build/cache directories exist locally,
    and automatically picks up future new source/test/workflow files without a
    hand-maintained allow-list.
    """
    _git_run(["git", "add", "-u", "--", "."], project_root)
    untracked = _list_untracked_release_paths(project_root)
    if untracked:
        _git_run(["git", "add", "--", *untracked], project_root)
    _git_unstage_release_skips(project_root)
    _git_unstage_excluded_patterns(project_root)


def is_dev_environment():
    """Check if we're running from the development directory."""
    current_file = Path(__file__).resolve()
    package_dir = current_file.parent
    project_root = package_dir.parent

    has_pyproject = (project_root / "pyproject.toml").exists()
    has_batplot_dir = (project_root / "batplot").is_dir()
    has_dev_upgrade = (project_root / "batplot" / "dev_upgrade.py").exists()

    return has_pyproject and has_batplot_dir and has_dev_upgrade


# Package data files under batplot/data/ that must never be published (local/GitHub-only).
PACKAGE_DATA_EXCLUDE_NAMES = frozenset(
    {
        "USER_MANUAL.md",
        "USER_MANUAL.pdf",
    }
)

# Repository paths checked after a version bump (single source of truth for release verification).
VERSION_CANONICAL_PATHS = (
    "batplot/__init__.py",
    "pyproject.toml",
    "CITATION.cff",
    "batplot/data/latest_release_notes.json",
)


def read_version_from_init_file(init_path: Path) -> str | None:
    """Parse ``__version__`` from ``batplot/__init__.py`` without importing batplot."""
    if not init_path.is_file():
        return None
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init_path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def read_version_from_pyproject(toml_path: Path) -> str | None:
    """Parse ``[project] version`` from pyproject.toml."""
    if not toml_path.is_file():
        return None
    content = toml_path.read_text(encoding="utf-8")
    in_project = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project:
            match = re.match(r'^version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    return None


def read_version_from_citation_cff(cff_path: Path) -> str | None:
    """Parse ``version: vX.Y.Z`` from CITATION.cff."""
    if not cff_path.is_file():
        return None
    match = re.search(r'^version:\s*v([0-9]+(?:\.[0-9]+)*)', cff_path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else None


def read_version_from_latest_release_notes(json_path: Path) -> str | None:
    if not json_path.is_file():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    version = payload.get("version")
    return str(version) if version else None


def discover_shippable_package_data(project_root: Path) -> list[str]:
    """Return ``batplot/data/*`` paths that should ship in wheels/sdists (relative to batplot/)."""
    data_dir = project_root / "batplot" / "data"
    if not data_dir.is_dir():
        return []
    rel_paths: list[str] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in PACKAGE_DATA_EXCLUDE_NAMES:
            continue
        if path.suffix.lower() in {".zip", ".docx", ".pdf"}:
            continue
        rel_paths.append(path.relative_to(project_root / "batplot").as_posix())
    return rel_paths


def sync_pyproject_package_data(project_root: Path) -> list[str]:
    """Rewrite ``[tool.setuptools.package-data]`` from files on disk.

    New files dropped into ``batplot/data/`` are picked up automatically on the
    next ``--dev-upgrade`` without hand-editing ``pyproject.toml``.
    """
    discovered = discover_shippable_package_data(project_root)
    toml_path = project_root / "pyproject.toml"
    if not toml_path.is_file():
        return discovered
    content = toml_path.read_text(encoding="utf-8")
    items = ", ".join(f'"{p}"' for p in discovered)
    pattern = r'(\[tool\.setuptools\.package-data\]\s*\n"batplot"\s*=\s*)\[[^\]]*\]'
    replacement = rf"\1[{items}]"
    new_content, count = re.subn(pattern, replacement, content, count=1)
    if count and new_content != content:
        toml_path.write_text(new_content, encoding="utf-8")
        print(f"✓ Synced pyproject.toml package-data ({len(discovered)} file(s) under batplot/data/)")
    return discovered


def update_version_files(project_root: Path, new_version: str, *, old_version: str | None = None) -> None:
    """Update canonical version strings in release metadata files."""
    _ = old_version  # reserved for stale-version scans

    init_file = project_root / "batplot" / "__init__.py"
    init_content = init_file.read_text(encoding="utf-8")
    new_init, n_init = re.subn(
        r'(__version__\s*=\s*")[^"]+(")',
        rf"\g<1>{new_version}\2",
        init_content,
        count=1,
    )
    if n_init:
        init_file.write_text(new_init, encoding="utf-8")
        print("✓ Updated batplot/__init__.py")
    else:
        raise RuntimeError("Could not update __version__ in batplot/__init__.py")

    toml_file = project_root / "pyproject.toml"
    toml_content = toml_file.read_text(encoding="utf-8")
    lines = toml_content.splitlines()
    in_project = False
    replaced = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project and re.match(r'^version\s*=\s*"[^"]+"', stripped):
            lines[idx] = f'version = "{new_version}"'
            replaced = True
            break
    if replaced:
        toml_file.write_text("\n".join(lines) + ("\n" if toml_content.endswith("\n") else ""), encoding="utf-8")
        print("✓ Updated pyproject.toml")
    else:
        raise RuntimeError('Could not update [project] version in pyproject.toml')


def verify_release_versions(project_root: Path, expected_version: str) -> bool:
    """Fail the release when canonical version files disagree."""
    checks: list[tuple[str, str | None]] = [
        ("batplot/__init__.py", read_version_from_init_file(project_root / "batplot" / "__init__.py")),
        ("pyproject.toml", read_version_from_pyproject(project_root / "pyproject.toml")),
        ("CITATION.cff", read_version_from_citation_cff(project_root / "CITATION.cff")),
        (
            "batplot/data/latest_release_notes.json",
            read_version_from_latest_release_notes(project_root / "batplot" / "data" / "latest_release_notes.json"),
        ),
    ]
    ok = True
    print("\nVersion consistency:")
    for label, found in checks:
        if found is None:
            print(f"  ⚠ {label}: not found or unreadable (skipped)")
            continue
        if found != expected_version:
            ok = False
            print(f"  ✗ {label}: expected {expected_version}, found {found}")
        else:
            print(f"  ✓ {label}: {found}")
    return ok


def find_stale_hardcoded_versions(project_root: Path, old_version: str | None) -> list[str]:
    """Return batplot/*.py paths that still mention the pre-bump version string."""
    if not old_version:
        return []
    hits: list[str] = []
    package_root = project_root / "batplot"
    skip_names = {"dev_upgrade.py"}
    for path in sorted(package_root.rglob("*.py")):
        if path.name in skip_names or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if old_version in text:
            hits.append(path.relative_to(project_root).as_posix())
    return hits


def sync_manifest_package_data(project_root: Path) -> None:
    """Rewrite ``MANIFEST.in`` include lines for shippable ``batplot/data`` files."""
    manifest_path = project_root / "MANIFEST.in"
    discovered = discover_shippable_package_data(project_root)
    lines = [
        "include README.md LICENSE DEVELOPING.md",
        "exclude batplot/data/USER_MANUAL.md",
    ]
    for rel in discovered:
        lines.append(f"include batplot/{rel}")
    content = "\n".join(lines) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") == content:
        return
    manifest_path.write_text(content, encoding="utf-8")
    print(f"✓ Synced MANIFEST.in package-data includes ({len(discovered)} file(s))")


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
    payload = {"version": new_version, "custom_message": custom_message, "update_notes": update_notes_list}
    out_file.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print("\033[0;32m✓ Wrote batplot/data/latest_release_notes.json (commit & push so users see notes)\033[0m")


def _git_restore_stash(project_root: Path, stashed: bool) -> None:
    if not stashed:
        return
    pop_result = _git_run(
        ["git", "stash", "pop"],
        project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if pop_result.returncode == 0:
        print("\033[0;32m✓ Restored stashed local changes\033[0m")
    else:
        print("\033[0;33mStash pop had conflicts. Resolve with: git stash pop\033[0m")
        if pop_result.stderr or pop_result.stdout:
            print(pop_result.stderr or pop_result.stdout)


def git_commit_and_push(
    project_root: Path,
    version: str,
    update_notes: str,
    *,
    commit_title: str | None = None,
) -> bool:
    """Commit version changes and push to GitHub.

    Commits **before** ``git pull --rebase`` so a staged index never blocks the
    sync. Bytecode and cache files are kept out of the commit even when tracked.

    Returns:
        True if successful or skipped, False if failed
    """
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    RED = "\033[0;31m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"

    title = commit_title or f"Release v{version}"

    if not (project_root / ".git").exists():
        print(f"\n{YELLOW}Skipping git push: not a git repository{NC}")
        return True

    try:
        result = _git_run(
            ["git", "status", "--porcelain"],
            project_root,
            check=False,
            capture_output=True,
            text=True,
        )

        if not result.stdout.strip():
            print(f"\n{YELLOW}No changes to commit{NC}")
            return True

        print(f"\n{BLUE}Git: Commit and push changes to GitHub?{NC}")
        print("  This will stage:")
        print("    - All batplot source, tests, CI workflows, docs, and metadata")
        print("    - New files added since the last release (no hand-maintained list)")
        print("    - Tracked deletions so removed files disappear from GitHub")
        print("  Excludes:")
        print("    - Build outputs, caches, bytecode, .DS_Store, virtualenvs")
        print("    - Local-only assets (USER_MANUAL.md, batplot_user_manual.docx)")

        try:
            choice = input(f"\n{YELLOW}Push to GitHub? (y/n): {NC}").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Skipped git push{NC}")
            return True

        if choice != 'y':
            print(f"{YELLOW}Skipped git push{NC}")
            return True

        _git_stage_release_snapshot(project_root)

        staged_files = _git_staged_paths(project_root)
        if not staged_files:
            print(f"{YELLOW}Nothing staged for commit after applying release filters.{NC}")
            return True

        stat = _git_run(
            ["git", "diff", "--cached", "--stat"],
            project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if stat.stdout:
            print(f"\n{BLUE}Staged release snapshot:{NC}")
            print(stat.stdout.rstrip())

        branch = _git_current_branch(project_root)

        commit_msg = f"{title}\n\n"
        if update_notes:
            commit_msg += f"{update_notes}\n"

        _git_run(
            ["git", "commit", "-m", commit_msg],
            project_root,
        )
        print(f"{GREEN}✓ Committed changes{NC}")

        stashed = False
        if _git_worktree_dirty(project_root):
            print(f"\n{BLUE}Stashing leftover local changes before syncing with GitHub...{NC}")
            stashed = _git_stash_worktree(project_root, "batplot dev-release: temporary stash")
            if stashed:
                print(f"{GREEN}✓ Stashed{NC}")
            else:
                print(f"{YELLOW}Could not stash local changes; pull may fail.{NC}")

        print(f"\n{BLUE}Fetching and rebasing onto origin/{branch}...{NC}")
        _git_run(["git", "fetch", "origin"], project_root, check=False)
        pull_result = _git_run(
            ["git", "pull", "--rebase", "origin", branch],
            project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if pull_result.returncode != 0:
            pull_result = _git_run(
                ["git", "pull", "--rebase"],
                project_root,
                check=False,
                capture_output=True,
                text=True,
            )
        if pull_result.returncode != 0:
            _git_restore_stash(project_root, stashed)
            print(f"{RED}Could not sync with GitHub before push.{NC}")
            print(pull_result.stderr or pull_result.stdout)
            print(f"{YELLOW}Your release commit is saved locally. Fix conflicts, then run:{NC}")
            print(f"  git pull --rebase origin {branch}")
            print(f"  git push origin {branch}")
            print(f"{YELLOW}Or run: batplot --dev-git  (GitHub-only sync, no PyPI){NC}")
            return False

        print(f"\n{BLUE}Pushing to GitHub...{NC}")
        result = _git_run(
            ["git", "push", "origin", branch],
            project_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            result = _git_run(
                ["git", "push"],
                project_root,
                check=False,
                capture_output=True,
                text=True,
            )

        if result.returncode == 0:
            print(f"{GREEN}✓ Pushed to GitHub successfully{NC}")
            _git_restore_stash(project_root, stashed)

            remote_result = _git_run(
                ["git", "remote", "get-url", "origin"],
                project_root,
                check=False,
                capture_output=True,
                text=True,
            )
            if remote_result.returncode == 0:
                remote_url = remote_result.stdout.strip()
                if remote_url.startswith("git@github.com:"):
                    remote_url = remote_url.replace("git@github.com:", "https://github.com/").replace(".git", "")
                elif remote_url.endswith(".git"):
                    remote_url = remote_url[:-4]
                print(f"  {remote_url}")
                print(f"{GREEN}✓ Users on older batplot versions will fetch release notes from:{NC}")
                print(f"  https://raw.githubusercontent.com/chem-plot/batplot/main/batplot/data/latest_release_notes.json")

            return True

        _git_restore_stash(project_root, stashed)
        print(f"{RED}✗ Git push failed:{NC}")
        print(result.stderr or result.stdout)
        print(f"{YELLOW}Try: batplot --dev-git  (push to GitHub without uploading to PyPI again){NC}")
        return False

    except subprocess.CalledProcessError as e:
        print(f"{RED}✗ Git operation failed: {e}{NC}")
        print(f"{YELLOW}Try: batplot --dev-git{NC}")
        return False
    except Exception as e:
        print(f"{RED}✗ Unexpected error during git operations: {e}{NC}")
        return False


def update_citation_cff(project_root: Path, new_version: str) -> None:
    """Update version and date-released in CITATION.cff to match the release."""
    cff_file = project_root / "CITATION.cff"
    if not cff_file.exists():
        return
    content = cff_file.read_text()
    today = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r'^version:\s*.+$', f'version: v{new_version}', content, flags=re.MULTILINE)
    content = re.sub(r'^date-released:\s*.+$', f'date-released: {today}', content, flags=re.MULTILINE)
    cff_file.write_text(content)
    print(f"✓ Updated CITATION.cff (version v{new_version}, date {today})")


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


def _required_package_data_files(project_root: Path) -> list[str]:
    """Return shippable package-data paths (pyproject list ∪ batplot/data on disk)."""
    declared: set[str] = set()
    toml_file = project_root / "pyproject.toml"
    if toml_file.exists():
        content = toml_file.read_text(encoding="utf-8")
        match = re.search(
            r'\[tool\.setuptools\.package-data\]\s*\n(?P<body>(?:[^\[]|\[[^\]]+\])*)',
            content,
            flags=re.MULTILINE,
        )
        if match:
            body = match.group("body")
            package_match = re.search(r'"batplot"\s*=\s*\[(?P<items>[^\]]*)\]', body)
            if package_match:
                for item in re.findall(r'"([^"]+)"', package_match.group("items")):
                    declared.add("batplot/" + item.replace("\\", "/"))
    for rel in discover_shippable_package_data(project_root):
        declared.add("batplot/" + rel.replace("\\", "/"))
    return sorted(declared)


def _required_package_python_files(project_root: Path) -> list[str]:
    """Return package Python files that every built archive must contain."""
    package_root = project_root / "batplot"
    required: list[str] = []
    for path in package_root.rglob("*.py"):
        rel = path.relative_to(project_root).as_posix()
        if "__pycache__" in path.parts:
            continue
        required.append(rel)
    return sorted(required)


def _archive_member_names(archive_path: Path) -> set[str]:
    """Return normalized member names for wheels/zips and source tarballs."""
    suffixes = archive_path.suffixes
    if archive_path.suffix == ".whl" or archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            return {name.replace("\\", "/") for name in zf.namelist()}
    if archive_path.suffix == ".gz" and ".tar" in suffixes:
        with tarfile.open(archive_path, "r:gz") as tf:
            return {member.name.replace("\\", "/") for member in tf.getmembers()}
    if archive_path.suffix == ".tar":
        with tarfile.open(archive_path, "r") as tf:
            return {member.name.replace("\\", "/") for member in tf.getmembers()}
    return set()


def _archive_contains(member_names: set[str], relpath: str) -> bool:
    """Return True when an archive contains relpath, allowing sdist prefixes."""
    return relpath in member_names or any(name.endswith("/" + relpath) for name in member_names)


def validate_distribution_contents(project_root: Path, dist_files: list[Path]) -> bool:
    """Fail release upload if built archives miss current batplot package files."""
    required = sorted(
        set(_required_package_python_files(project_root))
        | set(_required_package_data_files(project_root))
    )
    if not required:
        print("No package Python files found to validate.")
        return False
    archives = [Path(p) for p in dist_files if Path(p).suffix in {".whl", ".zip", ".tar"} or Path(p).suffixes[-2:] == [".tar", ".gz"]]
    if not archives:
        print("No wheel/sdist archives found to validate.")
        return False

    ok = True
    for archive in archives:
        try:
            members = _archive_member_names(archive)
        except Exception as exc:
            print(f"Could not inspect {archive.name}: {exc}")
            ok = False
            continue
        missing = [rel for rel in required if not _archive_contains(members, rel)]
        if missing:
            ok = False
            print(f"Archive validation failed for {archive.name}; missing {len(missing)} package files:")
            for rel in missing[:20]:
                print(f"  - {rel}")
            if len(missing) > 20:
                print(f"  ... and {len(missing) - 20} more")
        else:
            print(f"✓ Archive validation passed for {archive.name} ({len(required)} package files)")
    return ok


def get_release_notes_for_version(project_root: Path, version: str) -> str:
    """Return the RELEASE_NOTES.txt block for ``version``, or \"\"."""
    release_notes_file = project_root / "RELEASE_NOTES.txt"
    if not release_notes_file.exists():
        return ""
    blocks = parse_release_notes_blocks(release_notes_file.read_text())
    return blocks.get(version, "").strip()


def sync_release_metadata_files(project_root: Path, version: str, update_notes: str) -> None:
    """Refresh files that old installs fetch for update notifications."""
    if not update_notes or not update_notes.strip():
        print(f"\033[0;33mNo release notes for v{version}; skipped metadata sync.\033[0m")
        return
    update_version_check_update_info(project_root, update_notes)
    write_latest_release_notes_json(project_root, version, update_notes)
    changelog_src = project_root / "CHANGELOG.md"
    changelog_dst = project_root / "batplot" / "data" / "CHANGELOG.md"
    if changelog_src.exists():
        changelog_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(changelog_src, changelog_dst)
        print("\033[0;32m✓ Synced CHANGELOG.md to batplot/data/\033[0m")


def _dev_project_root() -> Path | None:
    if not is_dev_environment():
        return None
    return Path(__file__).resolve().parent.parent


def run_git_sync() -> int:
    """Push the current repo to GitHub without a PyPI upload or version bump."""
    BLUE = "\033[0;34m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[0;31m"
    NC = "\033[0m"

    print(f"{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"{BLUE}    Batplot GitHub Sync (--dev-git){NC}")
    print(f"{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}\n")

    project_root = _dev_project_root()
    if project_root is None:
        print(f"{RED}Error: This command only works in the development environment.{NC}")
        return 1

    os.chdir(project_root)
    print(f"{YELLOW}Working directory:{NC} {project_root}\n")

    version = get_current_version()
    if not version:
        print(f"{RED}Could not read __version__ from batplot/__init__.py{NC}")
        return 1

    print(f"{YELLOW}Current version (unchanged):{NC} {version}")
    update_notes = get_release_notes_for_version(project_root, version)
    if update_notes:
        print(f"{GREEN}Release notes for v{version}:{NC}")
        print(f"{YELLOW}{update_notes[:200]}{'...' if len(update_notes) > 200 else ''}{NC}")
    else:
        print(f"{YELLOW}No ## {version} block in RELEASE_NOTES.txt — metadata sync may be skipped.{NC}")

    print(f"\n{YELLOW}This will:{NC}")
    print("  - Refresh batplot/data/latest_release_notes.json (for update notifications)")
    print("  - Refresh version_check.py UPDATE_INFO")
    print("  - Commit and push to GitHub")
    print(f"{YELLOW}This will NOT:{NC} bump version, build, or upload to PyPI")

    try:
        confirm = input("\nContinue? (y/n): ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        return 1
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return 1

    sync_release_metadata_files(project_root, version, update_notes)
    ok = git_commit_and_push(
        project_root,
        version,
        update_notes,
        commit_title=f"Sync GitHub for v{version}",
    )
    if not ok:
        return 1

    print(f"\n{GREEN}✓ GitHub sync complete for v{version}{NC}")
    if update_notes:
        print(f"\n{BLUE}What's on GitHub:{NC}")
        for line in update_notes.split("\n"):
            print(f"  {line}")
    return 0


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
    today = datetime.now().strftime("%Y-%m-%d")
    changelog_file = project_root / "CHANGELOG.md"
    
    if all_version_notes:
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
        print(f"\n{GREEN}Release notes loaded ({len(update_notes)} chars){NC}")
    else:
        print(f"\n{YELLOW}Skipped update notes{NC}")
    
    try:
        # Step 1: Clean
        print(f"\n{GREEN}[1/5]{NC} Cleaning old build files...")
        clean_build_files(project_root)
        
        # Step 2: Update versions
        print(f"\n{GREEN}[2/5]{NC} Updating version numbers...")
        update_version_files(project_root, new_version, old_version=current_version)
        update_citation_cff(project_root, new_version)

        # Sync CHANGELOG into package data so "v" shows it (no network)
        data_dir = project_root / "batplot" / "data"
        changelog_src = project_root / "CHANGELOG.md"
        changelog_dst = data_dir / "CHANGELOG.md"
        if changelog_src.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(changelog_src, changelog_dst)
            print(f"  {GREEN}✓ Synced CHANGELOG.md to package data (for 'v' command){NC}")

        if update_notes:
            sync_release_metadata_files(project_root, new_version, update_notes)

        sync_pyproject_package_data(project_root)
        sync_manifest_package_data(project_root)

        if not verify_release_versions(project_root, new_version):
            print(f"{RED}Version consistency check failed; fix the files above before releasing.{NC}")
            return 1

        stale = find_stale_hardcoded_versions(project_root, current_version)
        if stale:
            print(f"{YELLOW}Warning: pre-bump version {current_version!r} still appears in:{NC}")
            for path in stale:
                print(f"  - {path}")
            print(f"{YELLOW}Update or remove these references before publishing.{NC}")

        # Verification
        print(f"\n{YELLOW}Verification:{NC}")
        init_file = project_root / "batplot" / "__init__.py"
        toml_file = project_root / "pyproject.toml"
        print(f"  __init__.py: {[line.strip() for line in init_file.read_text().splitlines() if '__version__' in line][0]}")
        print(f"  pyproject.toml: {[line.strip() for line in toml_file.read_text().splitlines() if line.startswith('version =')][0]}")
        
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
            dist_files_for_validation = [p for p in dist_dir.iterdir() if p.is_file()]
            if not validate_distribution_contents(project_root, dist_files_for_validation):
                print(f"{RED}Distribution validation failed; refusing to upload incomplete archives.{NC}")
                return 1
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
        
        # Commit and push to GitHub
        git_commit_and_push(project_root, new_version, update_notes)
        
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
