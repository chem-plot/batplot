#!/usr/bin/env python3
"""Repair batplot_user_manual.docx after a broken XML rewrite."""

from __future__ import annotations

import re
import uuid
import zipfile
from pathlib import Path

BACKUP = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/"
    "My files/batplot_manuscript/batplot_user_manual.docx"
)
TARGETS = [
    Path(__file__).resolve().parents[1] / "batplot_user_manual.docx",
    Path(
        "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/"
        "NAFUMA Battery - Antiperovskites/batplot/batplot_user_manual.docx"
    ),
]


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _body_p(text: str) -> str:
    pid = uuid.uuid4().hex[:8].upper()
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


def _chapter8_xml() -> str:
    return "".join(
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
        ]
    )


def _histo_flags_xml() -> str:
    rows = [
        ("--histo", "Launch histogram mode for CSV/TXT tables", "batplot file.csv --histo --i"),
        ("--histocol N", "Column to histogram (1-indexed or header name)", "batplot file.csv --histo --histocol Length"),
        ("--xrange A B", "Histogram display range", "batplot file.csv --histo --histocol 7 --xrange 0 20"),
        ("--binwidth W", "Width of each bin", "batplot file.csv --histo --histocol 7 --binwidth 1"),
        ("--bins N", "Number of equal-width bins", "batplot file.csv --histo --histocol 7 --bins 16"),
        ("--all", "Batch export each CSV/TXT file (requires --histocol)", "batplot --all --histo --histocol Length"),
        ("allfiles", "Expand folder CSV/TXT list (batch export or --i batch edit)", "batplot allfiles --histo --histocol 7"),
    ]
    parts = [_heading2("9.5  Histogram Mode Flags", "_TocHisto95"), _body_p("Flag"), _body_p("Description"), _body_p("Example")]
    for flag, desc, ex in rows:
        parts.extend([_body_p(flag), _body_p(desc), _code_p(ex)])
    return "".join(parts)


def _toc_histo_xml() -> str:
    return "".join(
        [
            _toc1("8  Examples: Histogram Mode", "_TocHistoMain"),
            _toc2("Example 8.1: Basic Histogram Launch", "_TocHisto81"),
            _toc2("Example 8.2: Column, Range, and Bins from Flags", "_TocHisto82"),
            _toc2("Example 8.3: Batch Export", "_TocHisto83"),
            _toc2("Example 8.4: Batch Interactive Editing", "_TocHisto84"),
        ]
    )


def _para_text(p: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)).strip()


def _replace_heading_text(p: str, new_text: str) -> str:
    """Replace visible text in a heading paragraph without breaking XML structure."""
    if not re.search(r"<w:t[^>]*>[^<]*</w:t>", p):
        return p
    return re.sub(
        r"(<w:t(?: xml:space=\"preserve\")?>)([^<]*)(</w:t>)",
        lambda m: m.group(1) + _esc(new_text) + m.group(3),
        p,
        count=1,
    )


def _renumber_flags_section(paras: list[str]) -> list[str]:
    mapping = {
        "8  Summary of Flags": "9  Summary of Flags",
        "8.1  General Flags": "9.1  General Flags",
        "8.2  1D / XY Mode Flags/Keywords": "9.2  1D / XY Mode Flags/Keywords",
        "8.3  Electrochemistry (EC) Mode Flags": "9.3  Electrochemistry (EC) Mode Flags",
        "8.4  Operando Mode Flags": "9.4  Operando Mode Flags",
    }
    out = []
    for p in paras:
        text = _para_text(p)
        if text in mapping and ("Heading" in p or "TOC" in p):
            out.append(_replace_heading_text(p, mapping[text]))
        else:
            out.append(p)
    return out


def _insert_before_summary(paras: list[str], insert_xml: str) -> list[str]:
    for i, p in enumerate(paras):
        if _para_text(p) == "8  Summary of Flags" and "Heading1" in p:
            return paras[:i] + re.findall(r"(<w:p[^>]*>.*?</w:p>)", insert_xml, re.DOTALL) + paras[i:]
    raise RuntimeError("Could not find chapter 8 Summary heading")


def _insert_toc_histo(paras: list[str], toc_xml: str) -> list[str]:
    for i, p in enumerate(paras):
        if _para_text(p) == "Example 7.4: Derivative Contour" and "TOC2" in p:
            return paras[: i + 1] + re.findall(r"(<w:p[^>]*>.*?</w:p>)", toc_xml, re.DOTALL) + paras[i + 1 :]
    raise RuntimeError("Could not find TOC insertion point")


def _append_histo_flags(paras: list[str], flags_xml: str) -> list[str]:
    flag_paras = re.findall(r"(<w:p[^>]*>.*?</w:p>)", flags_xml, re.DOTALL)
    sect_idx = None
    for i, p in enumerate(paras):
        if "<w:sectPr" in p:
            sect_idx = i
            break
    if sect_idx is None:
        for i, p in enumerate(paras):
            if "<w:sectPr" in p:
                sect_idx = i
    if sect_idx is None:
        return paras + flag_paras
    return paras[:sect_idx] + flag_paras + paras[sect_idx:]


def _build_document_xml(source_xml: str) -> str:
    paras = re.findall(r"(<w:p[^>]*>.*?</w:p>)", source_xml, re.DOTALL)
    if any(_para_text(p) == "8  Examples: Histogram Mode" for p in paras):
        paras = _renumber_flags_section(paras)
    else:
        paras = _insert_toc_histo(paras, _toc_histo_xml())
        paras = _insert_before_summary(paras, _chapter8_xml())
        paras = _renumber_flags_section(paras)
        paras = _append_histo_flags(paras, _histo_flags_xml())
        paras.append(
            _toc2("9.5  Histogram Mode Flags", "_TocHisto95")
        )

    m = re.search(r"^(.*?<w:body>)(.*?)(</w:body>\s*</w:document>\s*)$", source_xml, re.DOTALL)
    if not m:
        raise RuntimeError("Unexpected document.xml structure in backup")
    return m.group(1) + "".join(paras) + m.group(3)


def _validate_xml(xml: str) -> None:
    from xml.etree import ElementTree as ET

    ET.fromstring(xml.encode("utf-8"))


def repair_target(target: Path) -> None:
    with zipfile.ZipFile(BACKUP, "r") as zin:
        parts = {name: zin.read(name) for name in zin.namelist()}
        backup_xml = parts["word/document.xml"].decode("utf-8")

    if target.exists():
        with zipfile.ZipFile(target, "r") as zin:
            try:
                broken = zin.read("word/document.xml").decode("utf-8")
            except Exception:
                broken = ""
        if broken.startswith("<w:body>") and "<w:document" not in broken:
            # Attempt to salvage v1.8.46 body by fixing the one malformed heading, then merge.
            fixed_body = broken.replace(
                'w:rsidP="00B743F9"/><w:pPr>', 'w:rsidP="00B743F9"><w:pPr>', 1
            )
            inner = re.search(r"<w:body>(.*)</w:body>", fixed_body, re.DOTALL)
            if inner:
                m = re.search(r"^(.*?<w:body>)(.*?)(</w:body>\s*</w:document>\s*)$", backup_xml, re.DOTALL)
                if m:
                    candidate = m.group(1) + inner.group(1) + m.group(3)
                    try:
                        _validate_xml(candidate)
                        parts["word/document.xml"] = candidate.encode("utf-8")
                        tmp = target.with_suffix(".repaired.docx")
                        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
                            for name, data in parts.items():
                                zout.writestr(name, data)
                        tmp.replace(target)
                        print(f"Salvage-repaired {target}")
                        return
                    except Exception:
                        pass

    new_xml = _build_document_xml(backup_xml)
    _validate_xml(new_xml)
    parts["word/document.xml"] = new_xml.encode("utf-8")
    tmp = target.with_suffix(".repaired.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in parts.items():
            zout.writestr(name, data)
    tmp.replace(target)
    print(f"Rebuilt {target} from backup + histogram chapter")


def main() -> None:
    if not BACKUP.exists():
        raise SystemExit(f"Backup not found: {BACKUP}")
    for target in TARGETS:
        repair_target(target)


if __name__ == "__main__":
    main()
