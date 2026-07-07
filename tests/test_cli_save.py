"""Tests for non-interactive ``--save`` session export."""

from __future__ import annotations

import pickle

import pytest

from batplot.cli import main


def _run(argv):
    try:
        rc = main(list(argv))
    except SystemExit as exc:
        rc = exc.code
    return 0 if rc is None else rc


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _xrd_xy(path):
    lines = []
    for j in range(40):
        x = 10.0 + j * 0.5
        y = 100.0 + 800.0 * pow(2.718281828, -((x - 25.0) ** 2) / 3.0)
        lines.append(f"{x:.4f} {y:.4f}")
    _write(path, "\n".join(lines) + "\n")


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def _mock_save_prompts(monkeypatch, workdir):
    monkeypatch.setattr("batplot.cli_save.choose_save_path", lambda *_a, **_k: str(workdir))
    monkeypatch.setattr("builtins.input", lambda _p="": "")


def test_xy_save_default_name(workdir, _mock_save_prompts):
    xy = workdir / "scan.xy"
    _xrd_xy(xy)
    assert _run(["scan.xy", "--xaxis", "2theta", "--save"]) == 0
    pkl = workdir / "scan.pkl"
    assert pkl.is_file()
    with open(pkl, "rb") as fh:
        payload = pickle.load(fh)
    assert isinstance(payload, dict)


def test_xy_allfiles_save_requires_name(workdir, monkeypatch):
    _xrd_xy(workdir / "a.xy")
    _xrd_xy(workdir / "b.xy")
    monkeypatch.setattr("batplot.cli_save.choose_save_path", lambda *_a, **_k: str(workdir))
    monkeypatch.setattr("builtins.input", lambda _p="": "combined_session")
    assert _run(["allfiles", "--xaxis", "2theta", "--save"]) == 0
    assert (workdir / "combined_session.pkl").is_file()


def test_batch_all_save_per_file(workdir, monkeypatch):
    for name in ("one.xy", "two.xy"):
        _xrd_xy(workdir / name)
    monkeypatch.setattr("batplot.cli_save.choose_save_path", lambda *_a, **_k: str(workdir))
    assert _run(["--all", "--xaxis", "2theta", "--save"]) == 0
    assert (workdir / "one.pkl").is_file()
    assert (workdir / "two.pkl").is_file()
