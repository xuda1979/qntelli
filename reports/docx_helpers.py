"""Shared python-docx helpers for high-quality qntelli research reports."""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ACCENT = RGBColor(0x1F, 0x4E, 0x79)
GOOD = RGBColor(0x2E, 0x7D, 0x32)
BAD = RGBColor(0xC0, 0x39, 0x2B)
GREY = RGBColor(0x59, 0x59, 0x59)


def _shade_cell(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:fill'), hexcolor); tcPr.append(shd)


def new_doc(title, subtitle, authors):
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.0); section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2); section.right_margin = Cm(2.2)
        # footer with page number
        footer = section.footer
        p = footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        fld = OxmlElement('w:fldSimple'); fld.set(qn('w:instr'), 'PAGE')
        run._r.append(fld)
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
    # Title block
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(36)
    r = p.add_run(title); r.bold = True; r.font.size = Pt(24); r.font.color.rgb = ACCENT
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(subtitle); r.italic = True; r.font.size = Pt(13); r.font.color.rgb = GREY
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(authors); r.font.size = Pt(10); r.font.color.rgb = GREY
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("qntelli (无极量智) — quantum algorithm R&D agent harness")
    r.font.size = Pt(9); r.font.color.rgb = GREY; r.italic = True
    doc.add_paragraph()
    return doc


def h1(doc, text):
    p = doc.add_heading(text, level=1)
    for r in p.runs: r.font.color.rgb = ACCENT
    return p


def h2(doc, text):
    p = doc.add_heading(text, level=2)
    for r in p.runs: r.font.color.rgb = ACCENT
    return p


def para(doc, text, bold=False, italic=False, justify=True):
    p = doc.add_paragraph()
    r = p.add_run(text); r.bold = bold; r.italic = italic
    if justify: p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def bullet(doc, text, level=0, bold=False):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    r = p.add_run(text); r.bold = bold
    return p


def numbered(doc, text):
    p = doc.add_paragraph(style="List Number")
    p.add_run(text)
    return p


def code_table(doc, code, title=None):
    if title:
        para(doc, title, bold=True)
    lines = (code or "").splitlines()
    t = doc.add_table(rows=1, cols=1); t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.cell(0, 0)
    p = cell.paragraphs[0]
    for i, ln in enumerate(lines):
        r = p.add_run(ln); r.font.name = "Courier New"; r.font.size = Pt(8)
        if i < len(lines) - 1: r.add_break()
    doc.add_paragraph()


def _use_auto(t):
    tblPr = t._tbl.tblPr
    layout = OxmlElement('w:tblLayout'); layout.set(qn('w:type'), 'autofit')
    tblPr.append(layout); return t


def data_table(doc, headers, rows, caption=None, col_widths=None, font_size=9):
    """A properly styled data table with a shaded header row.
    col_widths: optional list of row-heights-style widths (Inches/Cm/Qtn).
    font_size: base size for data cells."""
    if caption:
        p = doc.add_paragraph(); p.add_run(caption).italic = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(2)
    t = doc.add_table(rows=1, cols=len(headers)); t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        r = hdr[i].paragraphs[0].add_run(str(h)); r.bold = True; r.font.size = Pt(9)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        _shade_cell(hdr[i], "1F4E79")
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(val)); r.font.size = Pt(font_size)
            if isinstance(val, str) and val.startswith("*"):
                r.font.color.rgb = GOOD; r.bold = True
    if col_widths:
        for row in t.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = w
    doc.add_paragraph()
    return t


def kv_table(doc, pairs, caption=None):
    """Two-column key-value table (label | value) with a shaded header.
    pairs: list of (label, value); values may be Python scalars/strings."""
    return data_table(doc, ["Parameter", "Value"],
                      [[k, str(v)] for k, v in pairs], caption,
                      col_widths=[Cm(6.0), Cm(10.5)])


def callout(doc, text, kind="info"):
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = t.cell(0, 0)
    fill = "E8F0F8" if kind == "info" else "FDEBEB"
    _shade_cell(cell, fill)
    p = cell.paragraphs[0]; r = p.add_run(text); r.font.size = Pt(10)
    if kind in ("good", "success"):
        r.font.color.rgb = GOOD
    elif kind == "bad":
        r.font.color.rgb = BAD
    else:
        r.font.color.rgb = ACCENT
    doc.add_paragraph()


def reference_list(doc, refs):
    for i, ref in enumerate(refs, 1):
        p = doc.add_paragraph(); p.paragraph_format.left_indent = Inches(0.4)
        p.paragraph_format.first_line_indent = Inches(-0.4)
        r = p.add_run(f"[{i}] {ref}"); r.font.size = Pt(9)


def key_results(doc, metrics):
    """Executive-summary key-results table: list of (label, value) pairs."""
    t = doc.add_table(rows=1, cols=2); t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    hdr[0].text = ""; hdr[1].text = ""
    r = hdr[0].paragraphs[0].add_run("Key result"); r.bold = True; r.font.color.rgb = RGBColor(255,255,255); r.font.size = Pt(9)
    r = hdr[1].paragraphs[0].add_run("Outcome"); r.bold = True; r.font.color.rgb = RGBColor(255,255,255); r.font.size = Pt(9)
    _shade_cell(hdr[0], "1F4E79"); _shade_cell(hdr[1], "1F4E79")
    for label, val in metrics:
        c2 = t.add_row().cells
        c2[0].text = ""; c2[1].text = ""
        r = c2[0].paragraphs[0].add_run(label); r.bold = True; r.font.size = Pt(9)
        r = c2[1].paragraphs[0].add_run(val); r.font.size = Pt(9)
    doc.add_paragraph()
    return t
