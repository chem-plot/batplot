#!/usr/bin/env python3
"""Import batplot_user_manual.docx into docs/ for MkDocs (docs-only; no package impact).

Usage:
  python scripts/import_user_manual_docx.py [path/to/batplot_user_manual.docx]

Requires: pip install mammoth
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCX = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/"
    "My files/batplot_manuscript/batplot_user_manual.docx"
)


def _clean_mammoth_md(text: str) -> str:
    text = re.sub(r'<a id="[^"]*"></a>', "", text)
    text = text.replace("\\.", ".").replace("\\-", "-")
    text = text.replace("\\(", "(").replace("\\)", ")")
    text = text.replace("\\[", "[").replace("\\]", "]")
    text = re.sub(r"\\([#*`_>~|])", r"\1", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Drop Word TOC before chapter 1
    m = re.search(r"(?m)^#\s+1\s+", text)
    if m:
        text = text[m.start() :]
    # Only numbered chapters stay H1; other single-# → ##
    lines = []
    for line in text.splitlines():
        if re.match(r"^#\s+\d+(\.| |\t|$)", line):
            lines.append(line)
        elif re.match(r"^#\s+", line) and not line.startswith("##"):
            lines.append("#" + line)
        else:
            lines.append(line)
    text = "\n".join(lines)
    # Simplify image alts (Word often injects junk)
    text = re.sub(
        r"!\[(?:(?!\]\().)*?\]\((images/[^)]+)\)",
        r"![](\1)",
        text,
        flags=re.S,
    )
    return text


def _slugify(title: str) -> str:
    t = re.sub(r"^#+\s*", "", title)
    t = re.sub(r"\*+", "", t).strip().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return (t[:80] or "section")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "docx",
        nargs="?",
        type=Path,
        default=DEFAULT_DOCX if DEFAULT_DOCX.is_file() else None,
        help="Path to batplot_user_manual.docx",
    )
    args = parser.parse_args(argv)
    if args.docx is None or not Path(args.docx).is_file():
        print("DOCX not found. Pass the path explicitly.", file=sys.stderr)
        return 1

    try:
        import mammoth
    except ImportError:
        print("Install mammoth first: pip install mammoth", file=sys.stderr)
        return 1

    docs = ROOT / "docs"
    img_dir = docs / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    import_dir = docs / "_import"
    import_dir.mkdir(parents=True, exist_ok=True)

    counter = {"n": 0}

    def convert_image(image):
        counter["n"] += 1
        ext = (image.content_type or "image/png").split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        name = f"fig{counter['n']:02d}.{ext}"
        path = img_dir / name
        with image.open() as src:
            path.write_bytes(src.read())
        return {"src": f"images/{name}"}

    # Clear previous extracted figures so numbering matches a fresh import
    for old in img_dir.glob("fig*.*"):
        old.unlink()

    with Path(args.docx).open("rb") as f:
        result = mammoth.convert_to_markdown(
            f, convert_image=mammoth.images.img_element(convert_image)
        )

    raw_path = import_dir / "manual_raw.md"
    raw_path.write_text(result.value, encoding="utf-8")
    text = _clean_mammoth_md(result.value)

    parts = re.split(r"(?m)^(#[^#].*)$", text)
    chapters: list[tuple[str, str]] = []
    i = 1
    while i < len(parts):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if re.match(r"^#\s+\d+", heading):
            chapters.append((heading, body.strip()))
        i += 2

    for p in docs.glob("*.md"):
        if p.name != "index.md" and re.match(r"^\d{2}-", p.name):
            p.unlink()

    nav: list[tuple[str, str]] = []
    for heading, body in chapters:
        title = re.sub(r"^#\s*", "", heading).strip()
        title = re.sub(r"\*+", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        mnum = re.match(r"^(\d+)\s*[.]?\s*(.*)$", title)
        if not mnum:
            continue
        num = int(mnum.group(1))
        rest = mnum.group(2).strip(" .") or "chapter"
        fname = f"{num:02d}-{_slugify(rest)}.md"
        (docs / fname).write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        nav.append((title, fname))
        print(f"wrote {fname}")

    index = (
        "# Batplot user manual\n\n"
        "Interactive CLI plotting for battery and materials characterization data.\n\n"
        "Tian Dai · University of Oslo · "
        "[GitHub](https://github.com/chem-plot/batplot)\n\n"
        "Use the **left sidebar** to open each chapter.\n\n"
        "## Chapters\n\n"
    )
    for title, fname in nav:
        index += f"- [{title}]({fname})\n"
    (docs / "index.md").write_text(index + "\n", encoding="utf-8")
    print(f"images: {counter['n']}")
    print("Done. (Local preview: mkdocs serve — see docs/CONTRIBUTING_DOCS.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
