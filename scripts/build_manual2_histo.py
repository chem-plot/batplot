#!/usr/bin/env python3
"""Restore the original manual and build batplot_user_manual2.docx with histogram chapter 8.

Workflow:
  1. Strip histogram edits from the current manual → restore original (chapter 8 = flags)
  2. Copy restored original → batplot_user_manual2.docx
  3. Insert histogram chapter 8 + renumber flags to chapter 9 on the copy only
"""

from __future__ import annotations

import re
import shutil
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NAFUMA_DIR = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/"
    "NAFUMA Battery - Antiperovskites/batplot"
)
ORIGINAL = NAFUMA_DIR / "batplot_user_manual.docx"
COPY = NAFUMA_DIR / "batplot_user_manual2.docx"
BACKUP = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/"
    "My files/batplot_manuscript/batplot_user_manual.docx"
)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _para_text(p: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()


def _is_toc_example_74(p: str) -> bool:
    return "TOC2" in p[:300] and _para_text(p).startswith("Example 7.4: Derivative Contour")


def _is_flags_summary_heading(p: str, number: str) -> bool:
    """Match '8  Summary of Flags' / '9  Summary of Flags' headings (TOC or body)."""
    text = _para_text(p)
    return text.startswith(f"{number}  Summary of Flags") and ("Heading1" in p or "TOC1" in p[:300])


def _is_body_flags_summary_heading(p: str, number: str) -> bool:
    return _is_flags_summary_heading(p, number) and "TOC" not in p[:300]


def _heading_number_text(p: str) -> str:
    text = _para_text(p)
    for key in (
        "8  Summary of Flags",
        "9  Summary of Flags",
        "8.1  General Flags",
        "9.1  General Flags",
        "8.2  1D / XY Mode Flags/Keywords",
        "9.2  1D / XY Mode Flags/Keywords",
        "8.3  Electrochemistry (EC) Mode Flags",
        "9.3  Electrochemistry (EC) Mode Flags",
        "8.4  Operando Mode Flags",
        "9.4  Operando Mode Flags",
    ):
        if text.startswith(key):
            return key
    return text


def _split_paras(xml: str) -> tuple[str, list[str], str]:
    m = re.search(r"^(.*?<w:body>)(.*?)(</w:body>\s*</w:document>\s*)$", xml, re.DOTALL)
    if not m:
        raise RuntimeError("Invalid document.xml: missing w:document/w:body wrapper")
    paras = re.findall(r"(<w:p[^>]*>.*?</w:p>)", m.group(2), re.DOTALL)
    return m.group(1), paras, m.group(3)


def _join_document(prefix: str, paras: list[str], suffix: str) -> str:
    doc = prefix + "".join(paras) + suffix
    ET.fromstring(doc.encode("utf-8"))
    return doc


def _replace_heading_text(p: str, new_text: str) -> str:
    return re.sub(
        r"(<w:t(?: xml:space=\"preserve\")?>)([^<]*)(</w:t>)",
        lambda m: m.group(1) + _esc(new_text) + m.group(3),
        p,
        count=1,
    )


def _is_histo_orphan_body(p: str) -> bool:
    if "TOC" in p[:300]:
        return False
    text = _para_text(p)
    if text.startswith("8  Examples: Histogram Mode"):
        return True
    if text.startswith("Example 8."):
        return True
    if text.startswith("9.5  Histogram Mode Flags"):
        return True
    markers = (
        "Histogram mode plots column data",
        "--histo",
        "mystyle.bpsh",
        "The startup wizard lists every column",
        "Non-interactive export: --histocol",
        "Batch mode exports each CSV/TXT file in the folder",
        "With two or more files and --i, batplot opens every histogram",
    )
    return any(m in text for m in markers)


def strip_histo_edits(paras: list[str]) -> list[str]:
    """Remove histogram chapter and revert chapter 9 flags back to chapter 8."""
    histo_toc_prefixes = (
        "8  Examples: Histogram Mode",
        "Example 8.1:",
        "Example 8.2:",
        "Example 8.3:",
        "Example 8.4:",
        "9.5  Histogram Mode Flags",
    )
    flags_renames = {
        "9  Summary of Flags": "8  Summary of Flags",
        "9.1  General Flags": "8.1  General Flags",
        "9.2  1D / XY Mode Flags/Keywords": "8.2  1D / XY Mode Flags/Keywords",
        "9.3  Electrochemistry (EC) Mode Flags": "8.3  Electrochemistry (EC) Mode Flags",
        "9.4  Operando Mode Flags": "8.4  Operando Mode Flags",
    }

    out: list[str] = []
    skipping_flags = False

    for p in paras:
        text = _para_text(p)

        if "TOC" in p[:300] and any(text.startswith(prefix) for prefix in histo_toc_prefixes):
            continue
        if "_TocHisto" in p:
            continue
        if _is_histo_orphan_body(p):
            continue

        if text.startswith("9.5  Histogram Mode Flags") and "Heading2" in p:
            skipping_flags = True
            continue
        if skipping_flags:
            key = _heading_number_text(p)
            if key in flags_renames.values() or key in flags_renames or "Heading1" in p:
                skipping_flags = False
            elif "Heading" in p:
                skipping_flags = False
            else:
                continue

        key = _heading_number_text(p)
        if key in flags_renames and ("Heading" in p or "TOC" in p):
            out.append(_replace_heading_text(p, flags_renames[key]))
        else:
            out.append(p)
    return out


def _body_p(text: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
    if not text:
        return (
            f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
            f'<w:pPr><w:spacing w:before="80"/></w:pPr></w:p>'
        )
    return (
        f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
        f'<w:pPr><w:spacing w:before="60" w:after="80" w:line="276" w:lineRule="auto"/>'
        f'<w:jc w:val="both"/><w:rPr><w:color w:val="595959"/></w:rPr></w:pPr>'
        f'<w:r><w:rPr><w:color w:val="595959"/></w:rPr>'
        f'<w:t xml:space="preserve">{_esc(text)}</w:t></w:r></w:p>'
    )


def _code_p(text: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
    return (
        f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
        f'<w:pPr><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/>'
        f'<w:spacing w:before="40" w:after="40"/><w:ind w:left="360" w:right="360"/>'
        f'<w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
        f'<w:color w:val="1A1A1A"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:pPr>'
        f'<w:r><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" w:cs="Courier New"/>'
        f'<w:color w:val="1A1A1A"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
        f'<w:t xml:space="preserve">{_esc(text)}</w:t></w:r></w:p>'
    )


def _heading1(text: str, bookmark: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
    return (
        f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
        f'<w:pPr><w:pStyle w:val="Heading1"/><w:pageBreakBefore/>'
        f'<w:shd w:val="clear" w:color="auto" w:fill="1F4E79"/>'
        f'<w:ind w:left="120" w:right="120"/></w:pPr>'
        f'<w:bookmarkStart w:id="9001" w:name="{bookmark}"/>'
        f'<w:r><w:t>{_esc(text)}</w:t></w:r>'
        f'<w:bookmarkEnd w:id="9001"/></w:p>'
    )


def _heading2(text: str, bookmark: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
    return (
        f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
        f'<w:pPr><w:pStyle w:val="Heading2"/>'
        f'<w:pBdr><w:bottom w:val="single" w:sz="4" w:space="2" w:color="2E75B6"/></w:pBdr>'
        f'</w:pPr><w:bookmarkStart w:id="9002" w:name="{bookmark}"/>'
        f'<w:r><w:t>{_esc(text)}</w:t></w:r>'
        f'<w:bookmarkEnd w:id="9002"/></w:p>'
    )


def _toc1(text: str, anchor: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
    return (
        f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
        f'<w:pPr><w:pStyle w:val="TOC1"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9710"/></w:tabs>'
        f'<w:rPr><w:noProof/></w:rPr></w:pPr>'
        f'<w:hyperlink w:anchor="{anchor}" w:history="1">'
        f'<w:r><w:rPr><w:rStyle w:val="Hyperlink"/><w:noProof/></w:rPr>'
        f'<w:t>{_esc(text)}</w:t></w:r></w:hyperlink></w:p>'
    )


def _toc2(text: str, anchor: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
    return (
        f'<w:p w14:paraId="{pid}" w14:textId="77777777" w:rsidR="00HIST00" w:rsidRDefault="00HIST00">'
        f'<w:pPr><w:pStyle w:val="TOC2"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9710"/></w:tabs>'
        f'<w:rPr><w:noProof/></w:rPr></w:pPr>'
        f'<w:hyperlink w:anchor="{anchor}" w:history="1">'
        f'<w:r><w:rPr><w:rStyle w:val="Hyperlink"/><w:noProof/></w:rPr>'
        f'<w:t>{_esc(text)}</w:t></w:r></w:hyperlink></w:p>'
    )


def _chapter8_paras() -> list[str]:
    xml = "".join(
        [
            _heading1("8  Examples: Histogram Mode", "_TocHistoMain"),
            _body_p(
                "Histogram mode plots column data from tabular .csv or .txt files "
                "(for example particle-size lists exported from image analysis). "
                "Use --histo to enter the mode and --i for the interactive menu "
                "(colors, range, bins, export, session save). Style files use the "
                ".bpsh extension."
            ),
            _heading2("Example 8.1: Basic Histogram Launch", "_TocHisto81"),
            _code_p("batplot sizes.csv --histo --i"),
            _body_p(
                "The startup wizard lists every column with a preview. Choose the column "
                "to histogram, set the range (xmin xmax or auto), then set bin width or bins=N."
            ),
            _heading2("Example 8.2: Column, Range, and Bins from Flags", "_TocHisto82"),
            _code_p(
                "batplot data.txt --histo --histocol Length --xrange 0 16 --binwidth 1 --out hist.png"
            ),
            _body_p(
                "Non-interactive export: --histocol selects the column (number or header name), "
                "--xrange sets the histogram window, and --binwidth or --bins controls binning."
            ),
            _heading2("Example 8.3: Batch Export", "_TocHisto83"),
            _code_p("batplot --all --histo --histocol Length"),
            _code_p("batplot allfiles --histo --histocol 7 --binwidth 1"),
            _code_p("batplot --all mystyle.bpsh --histo --histocol Length"),
            _body_p(
                "Batch mode exports each CSV/TXT file in the folder as a separate figure "
                "under Figures/. --histocol is required for batch export. Optional .bpsh "
                "style files apply shared colors, fonts, and geometry."
            ),
            _heading2("Example 8.4: Batch Interactive Editing", "_TocHisto84"),
            _code_p("batplot allfiles --histo --i"),
            _body_p(
                "With two or more files and --i, batplot opens every histogram in a batch "
                "interactive menu so you can sync styles, rename labels, and export all figures "
                "together. If --histocol is omitted, the wizard runs once on the first file "
                "and reuses the same column and bin layout for the rest."
            ),
            _body_p(""),
        ]
    )
    return re.findall(r"(<w:p[^>]*>.*?</w:p>)", xml, re.DOTALL)


def _histo_flags_paras() -> list[str]:
    rows = [
        ("--histo", "Launch histogram mode for CSV/TXT tables", "batplot file.csv --histo --i"),
        ("--histocol N", "Column to histogram (1-indexed or header name)", "batplot file.csv --histo --histocol Length"),
        ("--xrange A B", "Histogram display range", "batplot file.csv --histo --histocol 7 --xrange 0 20"),
        ("--binwidth W", "Width of each bin", "batplot file.csv --histo --histocol 7 --binwidth 1"),
        ("--bins N", "Number of equal-width bins", "batplot file.csv --histo --histocol 7 --bins 16"),
        ("--all", "Batch export each CSV/TXT file (requires --histocol)", "batplot --all --histo --histocol Length"),
        ("allfiles", "Expand folder CSV/TXT list (batch export or --i batch edit)", "batplot allfiles --histo --histocol 7"),
    ]
    xml = [_heading2("9.5  Histogram Mode Flags", "_TocHisto95"), _body_p("Flag"), _body_p("Description"), _body_p("Example")]
    for flag, desc, ex in rows:
        xml.extend([_body_p(flag), _body_p(desc), _code_p(ex)])
    blob = "".join(xml)
    return re.findall(r"(<w:p[^>]*>.*?</w:p>)", blob, re.DOTALL)


def _toc_histo_paras() -> list[str]:
    blob = "".join(
        [
            _toc1("8  Examples: Histogram Mode", "_TocHistoMain"),
            _toc2("Example 8.1: Basic Histogram Launch", "_TocHisto81"),
            _toc2("Example 8.2: Column, Range, and Bins from Flags", "_TocHisto82"),
            _toc2("Example 8.3: Batch Export", "_TocHisto83"),
            _toc2("Example 8.4: Batch Interactive Editing", "_TocHisto84"),
        ]
    )
    return re.findall(r"(<w:p[^>]*>.*?</w:p>)", blob, re.DOTALL)


def add_histo_chapter(paras: list[str]) -> list[str]:
    if any(_para_text(p).startswith("8  Examples: Histogram Mode") for p in paras):
        if not any(_para_text(p).startswith("8  Examples: Histogram Mode") and "TOC1" in p for p in paras):
            for i, p in enumerate(paras):
                if _is_toc_example_74(p):
                    paras = paras[: i + 1] + _toc_histo_paras() + paras[i + 1 :]
                    break
        return paras

    for i, p in enumerate(paras):
        if _is_toc_example_74(p):
            paras = paras[: i + 1] + _toc_histo_paras() + paras[i + 1 :]
            break

    for i, p in enumerate(paras):
        if _is_body_flags_summary_heading(p, "8"):
            paras = paras[:i] + _chapter8_paras() + paras[i:]
            break

    flags_renames = {
        "8  Summary of Flags": "9  Summary of Flags",
        "8.1  General Flags": "9.1  General Flags",
        "8.2  1D / XY Mode Flags/Keywords": "9.2  1D / XY Mode Flags/Keywords",
        "8.3  Electrochemistry (EC) Mode Flags": "9.3  Electrochemistry (EC) Mode Flags",
        "8.4  Operando Mode Flags": "9.4  Operando Mode Flags",
    }
    renamed: list[str] = []
    for p in paras:
        key = _heading_number_text(p)
        if key in flags_renames and ("Heading" in p or "TOC" in p):
            renamed.append(_replace_heading_text(p, flags_renames[key]))
        else:
            renamed.append(p)
    paras = renamed

    sect_idx = next((i for i, p in enumerate(paras) if "<w:sectPr" in p), len(paras))
    paras = paras[:sect_idx] + _histo_flags_paras() + [_toc2("9.5  Histogram Mode Flags", "_TocHisto95")] + paras[sect_idx:]
    return paras


def read_docx_parts(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path, "r") as zin:
        return {name: zin.read(name) for name in zin.namelist()}


def write_docx(path: Path, parts: dict[str, bytes]) -> None:
    tmp = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    tmp.replace(path)


def transform_docx(source: Path, dest: Path, *, add_histo: bool) -> None:
    parts = read_docx_parts(source)
    xml = parts["word/document.xml"].decode("utf-8")
    prefix, paras, suffix = _split_paras(xml)
    if add_histo:
        paras = add_histo_chapter(paras)
    else:
        paras = strip_histo_edits(paras)
    parts["word/document.xml"] = _join_document(prefix, paras, suffix).encode("utf-8")
    write_docx(dest, parts)


def main() -> None:
    safety = ORIGINAL.with_name("batplot_user_manual_before_restore.docx")
    source = safety if safety.exists() else ORIGINAL
    if not source.exists():
        raise SystemExit(f"No source manual found in {NAFUMA_DIR}")

    # 1) Restore original from safety snapshot (pre-edit state with broken histo if needed strip)
    transform_docx(source, ORIGINAL, add_histo=False)
    print(f"Restored original: {ORIGINAL.name}")

    # 2) Build working copy with histogram chapter 8
    transform_docx(ORIGINAL, COPY, add_histo=True)
    print(f"Built copy with histogram chapter: {COPY.name}")

    for label, path, expect_histo in [("original", ORIGINAL, False), ("copy", COPY, True)]:
        xml = read_docx_parts(path)["word/document.xml"].decode("utf-8")
        ET.fromstring(xml.encode("utf-8"))
        _, paras, _ = _split_paras(xml)
        texts = [_para_text(p) for p in paras]
        has_histo_body = any(_para_text(p).startswith("8  Examples: Histogram Mode") for p in paras)
        has_histo_toc = any(
            _para_text(p).startswith("8  Examples: Histogram Mode") and "TOC1" in p for p in paras
        )
        has_ch9 = any(_para_text(p).startswith("9  Summary of Flags") for p in paras)
        has_ch8_flags = any(_para_text(p).startswith("8  Summary of Flags") for p in paras)
        media = sum(1 for n in read_docx_parts(path) if n.startswith("word/media/"))
        print(
            f"  {label}: histo_body={has_histo_body} histo_toc={has_histo_toc} "
            f"ch9={has_ch9} ch8_flags={has_ch8_flags} media={media}"
        )
        if expect_histo:
            if not (has_histo_body and has_histo_toc and has_ch9 and not has_ch8_flags):
                raise SystemExit(f"Copy validation failed for {path.name}")
        else:
            if not (not has_histo_body and has_ch8_flags and not has_ch9):
                raise SystemExit(f"Original validation failed for {path.name}")


if __name__ == "__main__":
    main()
