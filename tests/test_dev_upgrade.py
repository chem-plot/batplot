"""Developer upgrade packaging safety tests."""

from __future__ import annotations

import tarfile
import zipfile
from types import SimpleNamespace

from batplot.dev_upgrade import (
    GIT_RELEASE_SKIP_PATHS,
    GIT_STAGE_EXCLUDE_GLOBS,
    _git_stage_release_snapshot,
    _git_unstage_excluded_patterns,
    _list_untracked_release_paths,
    _path_matches_any_glob,
    _required_package_data_files,
    get_release_notes_for_version,
    validate_distribution_contents,
)


def _write_project_files(root):
    pkg = root / "batplot"
    nested = pkg / "plot_modes" / "xy"
    nested.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (nested / "__init__.py").write_text("", encoding="utf-8")
    (nested / "interactive.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[tool.setuptools.package-data]\n"batplot" = ["data/CHANGELOG.md"]\n',
        encoding="utf-8",
    )
    (pkg / "data").mkdir(parents=True, exist_ok=True)
    (pkg / "data" / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")


def test_validate_distribution_contents_accepts_wheel_with_all_package_py(tmp_path):
    _write_project_files(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "batplot-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.write(tmp_path / "batplot" / "__init__.py", "batplot/__init__.py")
        zf.write(
            tmp_path / "batplot" / "plot_modes" / "xy" / "__init__.py",
            "batplot/plot_modes/xy/__init__.py",
        )
        zf.write(
            tmp_path / "batplot" / "plot_modes" / "xy" / "interactive.py",
            "batplot/plot_modes/xy/interactive.py",
        )
        zf.write(
            tmp_path / "batplot" / "data" / "CHANGELOG.md",
            "batplot/data/CHANGELOG.md",
        )

    assert validate_distribution_contents(tmp_path, [wheel]) is True


def test_validate_distribution_contents_rejects_missing_package_py(tmp_path):
    _write_project_files(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "batplot-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.write(tmp_path / "batplot" / "__init__.py", "batplot/__init__.py")

    assert validate_distribution_contents(tmp_path, [wheel]) is False


def test_validate_distribution_contents_rejects_missing_package_data(tmp_path):
    _write_project_files(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "batplot-0.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.write(tmp_path / "batplot" / "__init__.py", "batplot/__init__.py")
        zf.write(
            tmp_path / "batplot" / "plot_modes" / "xy" / "__init__.py",
            "batplot/plot_modes/xy/__init__.py",
        )
        zf.write(
            tmp_path / "batplot" / "plot_modes" / "xy" / "interactive.py",
            "batplot/plot_modes/xy/interactive.py",
        )

    assert validate_distribution_contents(tmp_path, [wheel]) is False


def test_validate_distribution_contents_accepts_sdist_prefix(tmp_path):
    _write_project_files(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    sdist = dist / "batplot-0.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as tf:
        for rel in (
            "batplot/__init__.py",
            "batplot/plot_modes/xy/__init__.py",
            "batplot/plot_modes/xy/interactive.py",
            "batplot/data/CHANGELOG.md",
        ):
            tf.add(tmp_path / rel, arcname=f"batplot-0.0.0/{rel}")

    assert validate_distribution_contents(tmp_path, [sdist]) is True


def test_required_package_data_files_reads_pyproject(tmp_path):
    _write_project_files(tmp_path)
    assert _required_package_data_files(tmp_path) == ["batplot/data/CHANGELOG.md"]


def test_path_matches_exclude_globs():
    assert _path_matches_any_glob("dist/wheel.whl", GIT_STAGE_EXCLUDE_GLOBS)
    assert _path_matches_any_glob("batplot/__pycache__/x.pyc", GIT_STAGE_EXCLUDE_GLOBS)
    assert not _path_matches_any_glob("tests/test_cli_smoke.py", GIT_STAGE_EXCLUDE_GLOBS)


def test_git_stage_release_snapshot_stages_tracked_updates_and_untracked_files(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, _project_root, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("batplot.dev_upgrade._list_untracked_release_paths", lambda _root: ["tests/test_new.py"])
    monkeypatch.setattr("batplot.dev_upgrade._git_run", fake_run)

    _git_stage_release_snapshot(tmp_path)

    assert calls[0] == ["git", "add", "-u", "--", "."]
    assert calls[1] == ["git", "add", "--", "tests/test_new.py"]
    assert calls[2][0:3] == ["git", "reset", "HEAD"]
    for skip_path in GIT_RELEASE_SKIP_PATHS:
        assert ["git", "reset", "HEAD", "--", skip_path] in calls


def test_git_unstage_excluded_patterns_drops_tracked_pycache(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, _project_root, **kwargs):
        calls.append(cmd)
        if cmd[:4] == ["git", "diff", "--cached", "--name-only"]:
            return SimpleNamespace(
                returncode=0,
                stdout="batplot/__pycache__/cli.cpython-314.pyc\nbatplot/_mpl_backend.py\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("batplot.dev_upgrade._git_run", fake_run)
    _git_unstage_excluded_patterns(tmp_path)
    assert ["git", "reset", "HEAD", "--", "batplot/__pycache__/cli.cpython-314.pyc"] in calls


def test_get_release_notes_for_version_reads_block(tmp_path):
    (tmp_path / "RELEASE_NOTES.txt").write_text(
        "## 1.8.44\n- old\n\n## 1.8.45\n- Bug fixes with backend setting\n",
        encoding="utf-8",
    )
    notes = get_release_notes_for_version(tmp_path, "1.8.45")
    assert "backend setting" in notes


def test_git_stage_release_snapshot_does_not_use_repo_wide_git_add_dot(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, _project_root, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("batplot.dev_upgrade._list_untracked_release_paths", lambda _root: [])
    monkeypatch.setattr("batplot.dev_upgrade._git_run", fake_run)

    _git_stage_release_snapshot(tmp_path)

    assert not any(cmd[:4] == ["git", "add", "--", "."] for cmd in calls)


def test_list_untracked_release_paths_skips_local_only_assets(tmp_path, monkeypatch):
    def fake_run(cmd, _project_root, **kwargs):
        stdout = "\n".join(
            [
                "tests/test_new.py",
                "batplot/data/USER_MANUAL.md",
                "dist/wheel.whl",
            ]
        )
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("batplot.dev_upgrade._git_run", fake_run)

    assert _list_untracked_release_paths(tmp_path) == ["tests/test_new.py"]
