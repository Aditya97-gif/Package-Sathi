"""
report_generator.py — Generates a PDF compliance report using ReportLab.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage
)
from reportlab.lib.colors import HexColor

# ---------------------------------------------------------------------------
# Colour palette (matches frontend dark theme accent colours)
# ---------------------------------------------------------------------------
C_BG          = HexColor("#0f172a")
C_CARD        = HexColor("#1e293b")
C_ACCENT      = HexColor("#6366f1")    # indigo
C_SUCCESS     = HexColor("#22c55e")    # green
C_WARNING     = HexColor("#f59e0b")    # amber
C_ERROR       = HexColor("#ef4444")    # red
C_TEXT        = HexColor("#e2e8f0")
C_MUTED       = HexColor("#94a3b8")
C_WHITE       = colors.white

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "reports"
)
os.makedirs(REPORT_DIR, exist_ok=True)


def _status_color(status: str) -> HexColor:
    if status == "pass":
        return C_SUCCESS
    if status == "warning":
        return C_WARNING
    return C_ERROR


def _status_emoji(status: str) -> str:
    return {"pass": "✓  PASS", "fail": "✗  FAIL", "warning": "⚠  WARNING"}.get(status, status.upper())


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

def generate_pdf_report(
    scan_id: int,
    image_filename: str,
    extracted_fields: dict,
    compliance_report: dict,
    ocr_text: str = "",
    output_path: Optional[str] = None,
) -> str:
    """
    Generate a PDF compliance report and save it to disk.

    Returns:
        Absolute path to the saved PDF file.
    """
    if output_path is None:
        fname = f"report_scan_{scan_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(REPORT_DIR, fname)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Compliance Report — Scan #{scan_id}",
        author="Legal Metrology Compliance Checker",
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontSize=20,
        textColor=C_ACCENT,
        spaceAfter=4,
        alignment=TA_LEFT,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=C_MUTED,
        spaceAfter=12,
    )

    story.append(Paragraph("Legal Metrology Compliance Report", title_style))
    story.append(Paragraph(
        f"Label: <b>{image_filename}</b> &nbsp;|&nbsp; "
        f"Scan ID: #{scan_id} &nbsp;|&nbsp; "
        f"Generated: {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')}",
        sub_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=10))

    # ── Overall Status Banner ────────────────────────────────────────────────
    overall = compliance_report.get("overall_status", "unknown")
    score   = compliance_report.get("compliance_score", 0)
    banner_color = C_SUCCESS if overall == "compliant" else C_ERROR
    banner_text  = "✓  COMPLIANT" if overall == "compliant" else "✗  NON-COMPLIANT"

    banner_data = [[
        Paragraph(f"<b>{banner_text}</b>", ParagraphStyle(
            "Banner", fontSize=14, textColor=C_WHITE, alignment=TA_CENTER
        )),
        Paragraph(f"<b>Score: {score:.0f}%</b>", ParagraphStyle(
            "Score", fontSize=14, textColor=C_WHITE, alignment=TA_CENTER
        )),
    ]]
    banner_table = Table(banner_data, colWidths=["60%", "40%"])
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), banner_color),
        ("ROUNDEDCORNERS", [6]),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 10 * mm))

    # ── Extracted Fields Table ───────────────────────────────────────────────
    story.append(Paragraph("Extracted Declarations", ParagraphStyle(
        "SectionHead", fontSize=13, textColor=C_ACCENT, spaceBefore=6, spaceAfter=4
    )))

    FIELD_LABELS = {
        "mrp": "MRP",
        "net_quantity": "Net Quantity",
        "mfg_date": "Mfg / Packing Date",
        "expiry_date": "Expiry / Best Before",
        "batch_number": "Batch / Lot Number",
        "fssai_license": "FSSAI License",
        "consumer_helpline": "Consumer Helpline",
        "consumer_email": "Consumer Email",
        "manufacturer_name": "Manufacturer / Packer",
        "inclusive_of_taxes": "MRP Inclusive of Taxes",
    }
    field_rows = [["Field", "Extracted Value"]]
    for key, label in FIELD_LABELS.items():
        val = extracted_fields.get(key)
        if val is None or val == "" or val is False:
            display = "— not detected —"
        elif val is True:
            display = "Yes"
        else:
            display = str(val)
        field_rows.append([label, display])

    field_table = Table(field_rows, colWidths=["45%", "55%"])
    field_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#f8fafc"), C_WHITE]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(field_table)
    story.append(Spacer(1, 8 * mm))

    # ── Compliance Check Results ─────────────────────────────────────────────
    story.append(Paragraph("Compliance Check Results", ParagraphStyle(
        "SectionHead", fontSize=13, textColor=C_ACCENT, spaceBefore=6, spaceAfter=4
    )))

    checks = compliance_report.get("checks", [])
    check_rows = [["Field", "Status", "Details", "Rule Ref"]]
    for c in checks:
        status = c.get("status", "")
        check_rows.append([
            c.get("field_label", c.get("field_id", "")),
            _status_emoji(status),
            c.get("message", ""),
            c.get("rule_ref", "—"),
        ])

    check_table = Table(check_rows, colWidths=["22%", "14%", "48%", "16%"])
    check_style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("WORDWRAP", (2, 1), (2, -1), True),
    ]
    for i, c in enumerate(checks, start=1):
        status = c.get("status", "")
        bg = {
            "pass": HexColor("#f0fdf4"),
            "fail": HexColor("#fef2f2"),
            "warning": HexColor("#fffbeb"),
        }.get(status, C_WHITE)
        text_c = _status_color(status)
        check_style.append(("BACKGROUND", (0, i), (-1, i), bg))
        check_style.append(("TEXTCOLOR", (1, i), (1, i), text_c))
        check_style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

    check_table.setStyle(TableStyle(check_style))
    story.append(check_table)

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_MUTED))
    story.append(Paragraph(
        "This report is auto-generated by the Legal Metrology Compliance Checker. "
        "It is based on OCR text extraction and pattern matching, and is not a substitute for professional legal advice. "
        "Refer to the Legal Metrology (Packaged Commodities) Rules, 2011 and the latest DOCA FAQ updates for authoritative guidance.",
        ParagraphStyle("Footer", fontSize=7, textColor=C_MUTED, spaceBefore=4, alignment=TA_LEFT)
    ))

    doc.build(story)
    return output_path
