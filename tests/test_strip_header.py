"""Tests for CLI --strip-header file export utility."""

from __future__ import annotations

from pathlib import Path

import pytest

from batplot.cli import main
from batplot.strip_header import (
    parse_ext_filters,
    run_strip_header,
    strip_header_bytes,
    strip_header_file,
)


def test_parse_ext_filters():
    assert parse_ext_filters(None) is None
    assert parse_ext_filters("") is None
    assert parse_ext_filters(".xy") == [".xy"]
    assert parse_ext_filters("xy") == [".xy"]
    assert parse_ext_filters(".xy,.DAT,.txt") == [".xy", ".dat", ".txt"]
    assert parse_ext_filters("xy, xy, .dat") == [".xy", ".dat"]


def test_strip_header_bytes_preserves_crlf():
    raw = b"h1\r\nh2\r\n10 20\r\n30 40\r\n"
    body, total, removed = strip_header_bytes(raw, 2)
    assert total == 4
    assert removed == 2
    assert body == b"10 20\r\n30 40\r\n"


def test_strip_header_bytes_lf_and_short_file():
    body, total, removed = strip_header_bytes(b"a\nb\n", 5)
    assert total == 2
    assert removed == 2
    assert body == b""


def test_strip_header_single_file(tmp_path: Path):
    f = tmp_path / "data.txt"
    f.write_text("hdr1\nhdr2\n1 2\n3 4\n", encoding="utf-8")
    out = strip_header_file(str(f), 2)
    assert out is not None
    out_path = tmp_path / "stripped" / "data.txt"
    assert Path(out).resolve() == out_path.resolve()
    assert out_path.read_text(encoding="utf-8") == "1 2\n3 4\n"
    # Original untouched
    assert f.read_text(encoding="utf-8") == "hdr1\nhdr2\n1 2\n3 4\n"


def test_strip_header_folder_requires_ext(tmp_path: Path):
    folder = tmp_path / "patterns"
    folder.mkdir()
    (folder / "a.xy").write_text("h\n1 2\n", encoding="utf-8")
    rc = run_strip_header([str(folder)], 1)
    assert rc == 1


def test_strip_header_folder_with_ext_filter(tmp_path: Path):
    folder = tmp_path / "patterns"
    folder.mkdir()
    (folder / "a.xy").write_text("skip\n10 20\n", encoding="utf-8")
    (folder / "b.xy").write_text("skip\n30 40\n", encoding="utf-8")
    (folder / "c.txt").write_text("skip\nkeep\n", encoding="utf-8")

    rc = run_strip_header([str(folder)], 1, ext=".xy")
    assert rc == 0
    out = folder / "stripped"
    assert (out / "a.xy").read_text(encoding="utf-8") == "10 20\n"
    assert (out / "b.xy").read_text(encoding="utf-8") == "30 40\n"
    assert not (out / "c.txt").exists()


def test_strip_header_multi_ext(tmp_path: Path):
    folder = tmp_path / "mix"
    folder.mkdir()
    (folder / "a.xy").write_text("h\n1\n", encoding="utf-8")
    (folder / "b.dat").write_text("h\n2\n", encoding="utf-8")
    (folder / "c.csv").write_text("h\n3\n", encoding="utf-8")

    rc = run_strip_header([str(folder)], 1, ext=".xy,.dat")
    assert rc == 0
    assert (folder / "stripped" / "a.xy").is_file()
    assert (folder / "stripped" / "b.dat").is_file()
    assert not (folder / "stripped" / "c.csv").exists()


def test_strip_header_skips_binary_ext(tmp_path: Path):
    f = tmp_path / "scan.brml"
    f.write_bytes(b"not-really-brml")
    assert strip_header_file(str(f), 1) is None
    assert not (tmp_path / "stripped").exists()


def test_cli_strip_header_via_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    f = Path("sample.txt")
    f.write_text("A\nB\nC\nD\n", encoding="utf-8")
    rc = main(["sample.txt", "--strip-header", "2"])
    assert rc == 0
    assert Path("stripped/sample.txt").read_text(encoding="utf-8") == "C\nD\n"
