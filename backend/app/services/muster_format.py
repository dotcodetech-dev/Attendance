"""
PDF and Excel for the two college muster reports, laid out like the printed forms the college already uses:

  Attendance (Time)           S.No | Employee No | Name | one column per day | Late Hrs
  Attendance (Time & Leave)   ... | one column per leave type, A, WO, P | Total | Late Hrs | Late Cl

Each employee takes three lines (IN, OUT, worked hours), a department heading precedes its people and the S.No
restarts at 1 in every department. Book Antiqua in Excel (as the form), Palatino in the PDF (the same design,
and installed with Windows). Columns are shared with the on-screen report through data["Columns"] / row["Counts"].
"""
from __future__ import annotations

import io
import os
import re
from datetime import datetime, time as dtime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_YELLOW = "FFFF99"
_HEAD = ["S.No", "Employee No", "Name"]


# ------------------------------------------------------------------ model shared by PDF and Excel

def _lines(cell: str) -> tuple[str, str, str]:
    parts = (cell or "").split("\n")
    parts += [""] * (3 - len(parts))
    return parts[0], parts[1], parts[2]


_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _fmt(v: Any) -> str:
    """Text for a cell; control characters (stray device data) are dropped, Excel refuses them."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "" if v is None else _ILLEGAL.sub("", str(v))


def _model(data: dict, grouped: bool, with_leave: bool) -> dict:
    cols = list(data.get("Columns") or []) if with_leave else []
    headers = _HEAD + list(data["DateHeaders"]) + cols + (["Total", "Late Hrs", "Late Cl"] if with_leave else ["Late Hrs"])

    def person(e: dict, sno: int) -> dict:
        days = [_lines(c) for c in e["days"]]
        counts = [_fmt((e.get("Counts") or {}).get(c, 0)) for c in cols]
        tail = [_fmt(e["Total"]), _fmt(e["LateHrs"]), _fmt(e["LateCl"])] if with_leave else [_fmt(e["LateHrs"])]
        return {"sno": sno, "code": _fmt(e["EmployeeCode"]), "name": _fmt(e["EmployeeName"]),
                "in": [d[0] for d in days], "out": [d[1] for d in days], "work": [d[2] for d in days],
                "counts": counts, "tail": tail}

    items: list[tuple[str, Any]] = []
    if grouped and data.get("groups"):
        for g in data["groups"]:
            items.append(("dept", _fmt(g["Department"])))
            items += [("emp", person(e, e["SNo"])) for e in g["employees"]]
            items.append(("gap", None))
    else:
        items = [("emp", person(e, i)) for i, e in enumerate(data["employees"], 1)]
    return {"headers": headers, "ndays": len(data["DateHeaders"]), "ncounts": len(cols), "with_leave": with_leave, "items": items}


def _title_lines(data: dict, org: dict | None) -> list[str]:
    org = org or {}
    cat = f"Category : {data['Category']}"
    if data.get("AttendanceCategory"):
        cat += f"    Attendance Category : {data['AttendanceCategory']}"
    return [_fmt(org.get("OrgName")), _fmt(org.get("OrgAddress")),
            f"Attendance Report From {data['FromLabel']} To {data['ToLabel']}", _fmt(cat)]


# ------------------------------------------------------------------ PDF

_FONT_CACHE: dict[str, tuple[str, str]] = {}


def _fonts() -> tuple[str, str]:
    """(regular, bold) PDF font names: Palatino Linotype (installed with Windows; the closest match to the
    Book Antiqua of the printed form), else Times."""
    if "f" in _FONT_CACHE:
        return _FONT_CACHE["f"]
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    pair = ("Times-Roman", "Times-Bold")
    for reg, bold in (("pala.ttf", "palab.ttf"), ("PALA.TTF", "PALAB.TTF")):
        rp, bp = os.path.join(win, reg), os.path.join(win, bold)
        if os.path.exists(rp) and os.path.exists(bp):
            try:
                pdfmetrics.registerFont(TTFont("MusterReg", rp))
                pdfmetrics.registerFont(TTFont("MusterBold", bp))
                pair = ("MusterReg", "MusterBold")
                break
            except Exception:
                pass
    _FONT_CACHE["f"] = pair
    return pair


def _col_widths(m: dict, f: float, reg: str, bold: str) -> list[float]:
    sw = pdfmetrics.stringWidth
    pad = 3.2 + f * 0.25
    emps = [p for k, p in m["items"] if k == "emp"]
    widths = [
        max(sw("S.No", bold, f), sw("999", reg, f)) + pad,
        max([sw("Employee No", bold, f)] + [sw(p["code"], bold, f) for p in emps]) + pad,
        max([sw("Name", bold, f)] + [min(sw(p["name"], bold, f), 150) for p in emps]) + pad,
    ]
    widths += [max(sw("00:00", reg, f), sw("00", bold, f)) + pad] * m["ndays"]
    nd = m["ndays"]
    for h in m["headers"][3 + nd:3 + nd + m["ncounts"]]:
        widths.append(max(sw(h, bold, f), sw("00.0", bold, f)) + pad)
    if m["with_leave"]:
        widths += [max(sw("Total", bold, f), sw("00.0", reg, f)) + pad,
                   max(sw("Late Hrs", bold, f), sw("000:00", reg, f)) + pad,
                   max(sw("Late Cl", bold, f), sw("00", reg, f)) + pad]
    else:
        widths.append(max(sw("Late Hrs", bold, f), sw("000:00", reg, f)) + pad)
    return widths


def muster_pdf(data: dict, org: dict | None, with_leave: bool, grouped: bool = True) -> bytes:
    reg, bold = _fonts()
    m = _model(data, grouped, with_leave)
    nd, nc = m["ndays"], m["ncounts"]

    # Largest font (up to 9 pt) that fits across an A4 landscape page; A3 for very wide months; 5 pt at the very least.
    margin = 12 * mm
    chosen = None
    for page in (landscape(A4), landscape(A3)):
        avail = page[0] - 2 * margin
        for f in [9 - 0.25 * i for i in range(int((9 - 6) / 0.25) + 1)]:
            if sum(_col_widths(m, f, reg, bold)) <= avail:
                chosen = (page, f)
                break
        if chosen:
            break
    if not chosen:
        page = landscape(A3)
        avail = page[0] - 2 * margin
        f = 6.0
        while f > 4.5 and sum(_col_widths(m, f, reg, bold)) > avail:
            f -= 0.25
        chosen = (page, f)
    page, f = chosen
    widths = _col_widths(m, f, reg, bold)

    ncols = len(m["headers"])
    first_count = 3 + nd
    first_tail = first_count + nc
    rows: list[list[str]] = [m["headers"], [""] * ncols]
    style: list[Any] = [
        ("FONT", (0, 0), (-1, -1), reg, f),
        ("FONT", (0, 0), (-1, 0), bold, f + 0.6),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#" + _YELLOW)),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black, 0, (1.4, 1.4)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.9), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.6), ("RIGHTPADDING", (0, 0), (-1, -1), 1.6),
    ]
    pending_dept: int | None = None
    for kind, val in m["items"]:
        if kind == "dept":
            i = len(rows)
            rows.append([val] + [""] * (ncols - 1))
            style += [("SPAN", (0, i), (-1, i)), ("FONT", (0, i), (-1, i), bold, f + 1.7), ("ALIGN", (0, i), (-1, i), "LEFT")]
            pending_dept = i
        elif kind == "gap":
            rows.append([""] * ncols)
        else:
            i = len(rows)
            p = val
            rows.append([str(p["sno"]), p["code"], p["name"]] + p["in"] + p["counts"] + p["tail"])
            rows.append([""] * 3 + p["out"] + [""] * (ncols - 3 - nd))
            rows.append([""] * 3 + p["work"] + [""] * (ncols - 3 - nd))
            style += [
                ("NOSPLIT", (0, i), (-1, i + 2)),
                ("ALIGN", (0, i), (0, i), "CENTER"),
                ("FONT", (1, i), (2, i), bold, f),
                ("ALIGN", (2, i), (2, i), "CENTER"),
                ("ALIGN", (3, i), (3 + nd - 1, i + 1), "RIGHT"),
                ("FONT", (3, i + 2), (3 + nd - 1, i + 2), bold, f),
                ("ALIGN", (3, i + 2), (3 + nd - 1, i + 2), "LEFT"),
            ]
            if nc:
                style += [("FONT", (first_count, i), (first_tail - 1, i), bold, f),
                          ("ALIGN", (first_count, i), (first_tail - 1, i), "RIGHT")]
            if m["with_leave"]:   # Total (right), Late Hrs (left, text), Late Cl (right)
                style += [("ALIGN", (first_tail, i), (first_tail, i), "RIGHT"),
                          ("ALIGN", (first_tail + 1, i), (first_tail + 1, i), "LEFT"),
                          ("ALIGN", (first_tail + 2, i), (first_tail + 2, i), "RIGHT")]
            else:
                style.append(("ALIGN", (first_tail, i), (first_tail, i), "LEFT"))
            if pending_dept is not None:   # keep a department heading with its first person
                style.append(("NOSPLIT", (0, pending_dept), (-1, i + 2)))
                pending_dept = None

    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="CENTER")
    table.setStyle(TableStyle(style))

    title = _title_lines(data, org)
    sizes = [(13, bold), (10, reg), (10, reg), (10, reg)]
    story: list[Any] = []
    for text, (size, font) in zip(title, sizes):
        if text:
            story.append(Paragraph(text.replace("&", "&amp;"), ParagraphStyle(
                "t", fontName=font, fontSize=size, leading=size * 1.25, alignment=1)))
    story.append(Spacer(1, 7))
    story.append(table)

    stamp = "Printed on:" + datetime.now().strftime("%d-%b-%Y %H:%M:%S")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(reg, 8)
        canvas.drawString(margin, 7 * mm, stamp)
        canvas.drawRightString(page[0] - margin, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page, topMargin=10 * mm, bottomMargin=12 * mm,
                            leftMargin=margin, rightMargin=margin, title="Attendance Report")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ------------------------------------------------------------------ Excel

def muster_xlsx(data: dict, org: dict | None, with_leave: bool, grouped: bool = True) -> bytes:
    m = _model(data, grouped, with_leave)
    nd, nc = m["ndays"], m["ncounts"]
    ncols = len(m["headers"])
    first_count = 3 + nd
    first_tail = first_count + nc

    FONT = "Book Antiqua"
    f11 = Font(name=FONT, size=11)
    f11b = Font(name=FONT, size=11, bold=True)
    side = Side(style="dashed", color="000000")
    box = Border(left=side, right=side, top=side, bottom=side)
    yellow = PatternFill("solid", fgColor=_YELLOW)

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"

    for r, (text, font) in enumerate(zip(_title_lines(data, org), (Font(name=FONT, size=14, bold=True), f11, f11, f11)), 1):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        c = ws.cell(r, 1, text)
        c.font = font
        c.alignment = Alignment(horizontal="center")
    ws.row_dimensions[1].height = 18

    def bordered(row: int):
        for col in range(1, ncols + 1):
            ws.cell(row, col).border = box

    HEAD_ROW = 6
    for col, h in enumerate(m["headers"], 1):
        c = ws.cell(HEAD_ROW, col, h)
        c.font, c.fill, c.alignment = f11b, yellow, Alignment(horizontal="center")
    bordered(HEAD_ROW)
    r = HEAD_ROW + 1
    bordered(r)                                   # the blank line under the header, as on the form
    r += 1

    def clock(v: str):
        try:
            hh, mm = v.split(":")
            return dtime(int(hh), int(mm))
        except Exception:
            return v

    for kind, val in m["items"]:
        if kind == "dept":
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
            ws.cell(r, 1, val).font = Font(name=FONT, size=12, bold=True)
            ws.cell(r, 1).alignment = Alignment(horizontal="left")
            ws.row_dimensions[r].height = 15.6
            bordered(r)
            r += 1
        elif kind == "gap":
            bordered(r)
            r += 1
        else:
            p = val
            for k in range(3):
                bordered(r + k)
            a = ws.cell(r, 1, p["sno"]); a.font, a.alignment = f11, Alignment(horizontal="center")
            b = ws.cell(r, 2, p["code"]); b.font, b.alignment = f11b, Alignment(horizontal="left")
            n = ws.cell(r, 3, p["name"]); n.font, n.alignment = f11b, Alignment(horizontal="center")
            for d in range(nd):
                col = 4 + d
                for k, key in enumerate(("in", "out")):
                    v = p[key][d]
                    if v:
                        c = ws.cell(r + k, col, clock(v)); c.number_format = "hh:mm"; c.font = f11
                        c.alignment = Alignment(horizontal="right")
                if p["work"][d]:
                    c = ws.cell(r + 2, col, p["work"][d]); c.font = f11b; c.alignment = Alignment(horizontal="left")
            for j, v in enumerate(p["counts"]):
                c = ws.cell(r, first_count + j, float(v) if "." in v else int(v)); c.font = f11b
            tail = p["tail"]
            if with_leave:
                t = ws.cell(r, first_tail, float(tail[0]) if "." in tail[0] else int(tail[0])); t.font = f11
                ws.cell(r, first_tail + 1, tail[1] or None).font = f11
                lc = ws.cell(r, first_tail + 2, int(tail[2] or 0)); lc.font = f11
            else:
                ws.cell(r, first_tail, tail[0] or None).font = f11
            r += 3

    widths = [6, 14, 26] + [7.5] * nd + [max(4.5, len(h) * 1.25 + 2) for h in m["headers"][first_count:first_tail]]
    widths += [7, 9, 8] if with_leave else [9]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = 8 if ncols > 40 else 9      # A3 for a month with every leave column, else A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = f"{HEAD_ROW}:{HEAD_ROW}"
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.oddFooter.left.text = "Printed on:&D &T"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
