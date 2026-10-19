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
    """Generate a branded A4 Landscape Graduation / Level Completion Certificate."""
    register_fonts()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = landscape(A4)
    c = rl_canvas.Canvas(str(out_path), pagesize=(W, H))
    c.setTitle(f"شهادة إتمام مستوى — {data.get('name_ar', '')}")

    # Outer & inner decorative borders (Navy + Vibrant Orange)
    m = 12 * mm
    c.setStrokeColor(NAVY)
    c.setLineWidth(3.5)
    c.rect(m, m, W - 2 * m, H - 2 * m)

    m2 = 15.5 * mm
    c.setStrokeColor(RED)
    c.setLineWidth(1.5)
    c.rect(m2, m2, W - 2 * m2, H - 2 * m2)

    # Corner accents
    c.setFillColor(RED)
    for cx, cy in ((m2, m2), (W - m2 - 6 * mm, m2), (m2, H - m2 - 6 * mm), (W - m2 - 6 * mm, H - m2 - 6 * mm)):
        c.rect(cx, cy, 6 * mm, 6 * mm, stroke=0, fill=1)

    # Logo & Academy Header
    cx = W / 2
    if config.LOGO_FILE.exists():
        try:
            c.drawImage(str(config.LOGO_FILE), cx - 14 * mm, H - 46 * mm, 28 * mm, 24 * mm,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    draw_c(c, cx, H - 54 * mm, config.ACADEMY_FULL_NAME_AR, BOLD, 15, NAVY)
    draw_c(c, cx, H - 61 * mm, "FANTASIA ACADEMY FOR TRAINING & TECHNOLOGY — WE MAKE THE NEXT STEP", BOLD, 9.5, RED)

    # Certificate Title Banner
    banner_w = 130 * mm
    banner_h = 13 * mm
    c.setFillColor(RED_LIGHT)
    c.setStrokeColor(RED)
    c.setLineWidth(1)
    c.roundRect(cx - banner_w / 2, H - 79 * mm, banner_w, banner_h, 3 * mm, stroke=1, fill=1)
    draw_c(c, cx, H - 74.5 * mm, "شهادة إتمام مستوى تدريبي  |  CERTIFICATE OF COMPLETION", BOLD, 13.5, NAVY)

    # Body text
    draw_c(c, cx, H - 91 * mm, "تشهد أكاديمية فانتازيا بأن المتدرب / المتدربة:", REG, 12, MUTED)

    name_ar = data.get("name_ar") or "—"
    name_en = data.get("name_en") or ""
    draw_c(c, cx, H - 104 * mm, name_ar, BOLD, 22, RED)
    if name_en:
        draw_c(c, cx, H - 113 * mm, name_en.upper(), BOLD, 13, NAVY)

    program = data.get("program") or "البرمجة والروبوتيكس"
    level = data.get("level") or "مبتدئ"
    grade_label = data.get("grade_label") or "امتياز"
    issue_date = str(data.get("issue_date") or date.today())

    stmt = f"قد أتمّ بنجاح متطلبات البرنامج التدريبي «{program}» — المستوى «{level}» بتقدير عام «{grade_label}»"
    draw_c(c, cx, H - 127 * mm, stmt, BOLD, 13, TEXT)

    notes = (data.get("notes") or "").strip()
    if notes:
        draw_c(c, cx, H - 136 * mm, notes, REG, 10.5, MUTED)
    else:
        draw_c(c, cx, H - 136 * mm, "مع أطيب التمنيات بدوام التفوق والابتكار في مجالات البرمجة والتكنولوجيا الحديثة.", REG, 10.5, MUTED)

    # Metadata & Signatures at bottom
    sig_y = 32 * mm
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)

    # Right: Instructor / Academic Supervisor
    c.line(W - 85 * mm, sig_y, W - 30 * mm, sig_y)
    draw_c(c, W - 57.5 * mm, sig_y - 6 * mm, "المشرف الأكاديمي / المدرّب", BOLD, 10, NAVY)

    # Center: Issue date & Student ID
    draw_c(c, cx, sig_y + 2 * mm, f"تاريخ الإصدار: {issue_date}", REG, 9.5, MUTED)
    draw_c(c, cx, sig_y - 4 * mm, f"رقم قيد الطالب: #{data.get('student_id', '')}", BOLD, 9.5, NAVY)

    # Left: Academy Director
    c.line(30 * mm, sig_y, 85 * mm, sig_y)
    draw_c(c, 57.5 * mm, sig_y - 6 * mm, "إدارة أكاديمية فانتازيا", BOLD, 10, NAVY)

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
