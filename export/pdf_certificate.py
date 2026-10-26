"""Student Graduation Certificate (A4 Landscape) and Student ID / QR Card PDF builders."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

import config
from export.pdf_common import BOLD, LINE, MUTED, NAVY, RED, RED_LIGHT, REG, TEXT, draw_c, draw_l, draw_r, register_fonts


def build_certificate_pdf(out_path: Path, data: dict[str, Any]) -> Path:
    """Generate a Graduation / Level Completion Certificate using certificate.jpg as the full-page
    background image (A4 Landscape).  All dynamic text fields are overlaid on top of the image at
    positions calibrated to the 1280×906 px certificate template.

    Position fractions are measured from the bottom-left of the page (ReportLab convention):
        Arabic name  : center-X, ~57 % height
        English name : center-X, ~50 % height
        Program stmt : center-X, ~43 % height
        Notes        : center-X, ~37 % height
        Date + ID    : center-X, ~22 % height
        Right sig    : x=75 % W,  y=18 % H
        Left  sig    : x=25 % W,  y=18 % H
    """
    register_fonts()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = landscape(A4)
    c = rl_canvas.Canvas(str(out_path), pagesize=(W, H))
    c.setTitle(f"شهادة إتمام مستوى — {data.get('name_ar', '')}")

    # ------------------------------------------------------------------ background
    # Draw certificate.jpg as a full-page background (fallback: plain white).
    if config.CERTIFICATE_BG.exists():
        try:
            c.drawImage(str(config.CERTIFICATE_BG), 0, 0, W, H,
                        preserveAspectRatio=False, mask="auto")
        except Exception:
            pass  # silently skip if image is corrupt / unreadable

    # ------------------------------------------------------------------ helpers
    cx = W / 2  # horizontal centre

    # ------------------------------------------------------------------ student name (Arabic)
    # Large, bold, RED — ~57 % from bottom
    name_ar = data.get("name_ar") or "—"
    draw_c(c, cx, H * 0.57, name_ar, BOLD, 22, RED)

    # ------------------------------------------------------------------ student name (English)
    # Smaller, NAVY — ~50 % from bottom
    name_en = data.get("name_en") or ""
    if name_en:
        draw_c(c, cx, H * 0.50, name_en.upper(), BOLD, 13, NAVY)

    # ------------------------------------------------------------------ program / level / grade statement
    program    = data.get("program")     or "البرمجة والروبوتيكس"
    level      = data.get("level")       or "مبتدئ"
    grade_label = data.get("grade_label") or "امتياز"
    issue_date  = str(data.get("issue_date") or date.today())

    stmt = (
        f"قد أتمّ بنجاح متطلبات البرنامج التدريبي «{program}»"
        f" — المستوى «{level}» بتقدير عام «{grade_label}»"
    )
    draw_c(c, cx, H * 0.43, stmt, BOLD, 13, TEXT)

    # ------------------------------------------------------------------ notes line
    # Muted, smaller — ~37 % from bottom
    notes = (data.get("notes") or "").strip()
    notes_text = notes if notes else (
        "مع أطيب التمنيات بدوام التفوق والابتكار في مجالات البرمجة والتكنولوجيا الحديثة."
    )
    draw_c(c, cx, H * 0.37, notes_text, REG, 10.5, MUTED)

    # ------------------------------------------------------------------ issue date + student ID
    # Centred, near bottom — ~22 % from bottom
    draw_c(c, cx, H * 0.22 + 3 * mm, f"تاريخ الإصدار: {issue_date}", REG, 9.5, MUTED)
    draw_c(c, cx, H * 0.22 - 3 * mm, f"رقم قيد الطالب: #{data.get('student_id', '')}", BOLD, 9.5, NAVY)

    # ------------------------------------------------------------------ signature labels
    # Right signature area (academic supervisor / trainer) — x=75 % W, y=18 % H
    draw_c(c, W * 0.75, H * 0.18, "المشرف الأكاديمي / المدرّب", BOLD, 10, NAVY)

    # Left signature area (academy management) — x=25 % W, y=18 % H
    draw_c(c, W * 0.25, H * 0.18, "إدارة أكاديمية فانتازيا", BOLD, 10, NAVY)

    c.showPage()
    c.save()
    return out_path


def build_student_id_card_pdf(out_path: Path, data: dict[str, Any]) -> Path:
    """Generate a printable Student ID & QR Attendance Card (A4 sheet with front/back card layout)."""
    register_fonts()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = A4
    c = rl_canvas.Canvas(str(out_path), pagesize=(W, H))
    sid = data.get("student_id", "")
    name_ar = data.get("name_ar") or ""
    name_en = data.get("name_en") or ""
    program = data.get("program") or "—"
    group_label = data.get("group_label") or "—"
    mobile = data.get("parent_mobile") or "—"

    c.setTitle(f"بطاقة عضوية الطالب #{sid} — {name_ar}")

    # Card dimensions (CR80 oversized for easy desk printing & cutting: 105mm x 68mm)
    cw, ch = 108 * mm, 68 * mm
    cx = (W - cw) / 2
    cy = H - 95 * mm

    draw_c(c, W / 2, H - 20 * mm, "بطاقة عضوية وحضور الطالب — FANTASIA STUDENT ID", BOLD, 13, NAVY)

    # Card background & border
    c.setFillColor(colors.white)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.8)
    c.roundRect(cx, cy, cw, ch, 4 * mm, stroke=1, fill=1)

    # Top Navy Header Strip inside Card
    c.setFillColor(NAVY)
    c.roundRect(cx, cy + ch - 17 * mm, cw, 17 * mm, 4 * mm, stroke=0, fill=1)
    c.rect(cx, cy + ch - 17 * mm, cw, 6 * mm, stroke=0, fill=1)

    # Orange accent line
    c.setFillColor(RED)
    c.rect(cx, cy + ch - 18.5 * mm, cw, 1.5 * mm, stroke=0, fill=1)

    if config.LOGO_FILE.exists():
        try:
            c.drawImage(str(config.LOGO_FILE), cx + cw - 15 * mm, cy + ch - 15 * mm, 12 * mm, 12 * mm,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    draw_r(c, cx + cw - 17 * mm, cy + ch - 8 * mm, config.APP_NAME_AR, BOLD, 11, colors.white)
    draw_r(c, cx + cw - 17 * mm, cy + ch - 13.5 * mm, "FANTASIA ACADEMY STUDENT CARD", REG, 7.5, colors.HexColor("#FED7AA"))

    # Student details on the right side
    rx = cx + cw - 6 * mm
    draw_r(c, rx, cy + ch - 27 * mm, name_ar, BOLD, 12.5, NAVY)
    if name_en:
        draw_r(c, rx, cy + ch - 33 * mm, name_en, BOLD, 9, RED)
    draw_r(c, rx, cy + ch - 41 * mm, f"رقم الكود (ID): #{sid}", BOLD, 10, TEXT)
    draw_r(c, rx, cy + ch - 47.5 * mm, f"البرنامج: {program}", REG, 9, TEXT)
    draw_r(c, rx, cy + ch - 54 * mm, f"المجموعة: {group_label}", REG, 8.5, MUTED)
    draw_r(c, rx, cy + ch - 60.5 * mm, f"طوارئ ولي الأمر: {mobile}", REG, 8.5, MUTED)

    # QR Code on the left side for fast check-in
    qr_payload = f"FANTASIA-SID:{sid}"
    qr_widget = qr.QrCodeWidget(qr_payload)
    bounds = qr_widget.getBounds()
    qw = bounds[2] - bounds[0]
    qh = bounds[3] - bounds[1]
    qr_size = 28 * mm
    d = Drawing(qr_size, qr_size, transform=[qr_size / qw, 0, 0, qr_size / qh, 0, 0])
    d.add(qr_widget)
    renderPDF.draw(d, c, cx + 5 * mm, cy + 14 * mm)
    draw_c(c, cx + 5 * mm + qr_size / 2, cy + 9 * mm, f"ID: {sid}", BOLD, 9, NAVY)

    c.showPage()
    c.save()
    return out_path
