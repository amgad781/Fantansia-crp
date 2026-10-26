"""Cash receipt PDF (A5) — layout matches the Word template 'تصميم إيصال استلام - أكاديمية فانتازيا'."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import config
from export import pdf_common as P

# ── Design constants ──────────────────────────────────────────────────────────
_ACCENT   = P.RED           # #F05500  – orange-red brand colour
_ACCENT_L = P.RED_LIGHT     # #FFF4ED  – tinted background
_NAVY     = P.NAVY          # #0A194E  – dark header colour
_TEXT     = P.TEXT
_MUTED    = P.MUTED
_LINE     = P.LINE
_BOX_BORDER = colors.HexColor("#e2e8f0")   # light grey (matches Word table borders)
_HDR_BG     = colors.HexColor("#f1f5f9")   # row header fill

# Half-widths of the two-column info table (label | value)
_LABEL_W_FRAC = 0.38   # 38 % of usable width
_VALUE_W_FRAC = 0.62


# ── Public entry point ────────────────────────────────────────────────────────

def build_receipt_pdf(path: Path, d: dict[str, Any], reprint: bool = False) -> Path:
    """
    Generate an A5 receipt whose layout mirrors the Word reference document:

      • Logo + academy name + full name subtitle  (header)
      • Coloured band: "إيصال استلام | رقم الإيصال: XXXXXX"
      • Date row
      • Horizontal separator
      • Two-column table (label / value) for each data field
      • Horizontal separator
      • Payment-method checkbox row  (نقدي / إنستا باي / فودافون كاش / POS)
      • Horizontal separator
      • Terms & conditions
      • Cashier signature line
      • Footer timestamp
    """
    P.register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    W, H = A5          # 148 mm × 210 mm
    M = 10 * mm        # page margin
    c = canvas.Canvas(str(path), pagesize=A5)
    c.setTitle(f"إيصال استلام {d['serial']}")

    # ── HEADER ─────────────────────────────────────────────────────────────
    y = _header(c, W, H, M, d)

    # ── SERIAL / DATE BAND ─────────────────────────────────────────────────
    band_h = 9 * mm
    c.setFillColor(_ACCENT)
    c.roundRect(M, y - band_h, W - 2 * M, band_h, 2 * mm, fill=1, stroke=0)

    serial_txt = f"إيصال استلام  |  رقم الإيصال:  {d['serial']}"
    P.draw_r(c, W - M - 3 * mm, y - 6 * mm, serial_txt, P.BOLD, 9.5, colors.white)
    date_txt = f"التاريخ:  {d['date']}"
    P.draw_l(c, M + 3 * mm, y - 6 * mm, date_txt, P.REG, 8.5, colors.white)
    y -= band_h + 3 * mm

    # ── INFO TABLE ─────────────────────────────────────────────────────────
    usable = W - 2 * M
    label_w = usable * _LABEL_W_FRAC
    value_w = usable * _VALUE_W_FRAC

    rows = [
        ("استلمنا من السيد/ة",        d["student_name"],          True,  10.5),
        ("اسم الطالب / المتدرب",      d["student_name"],          True,  10.5),
        ("اسم الدبلومة / النشاط",     d.get("description") or "—", False, 9.5),
        ("المبلغ المدفوع",
         f"{P_money(d['amount'])} جنيه مصري فقط",                  True,  10.5),
        ("المبلغ كتابةً",             P.amount_words(d["amount"]),  False, 8),
    ]
    if d.get("remaining") is not None:
        rows.append(("المتبقي من الرسوم", f"{P_money(d['remaining'])} ج.م", False, 9))
    if d.get("cost_center"):
        rows.append(("مركز التكلفة", d["cost_center"], False, 9))

    for i, (lbl, val, bold, fs) in enumerate(rows):
        even = (i % 2 == 0)
        row_h = _row_height(val, P.BOLD if bold else P.REG, fs, value_w)
        bg = _HDR_BG if even else colors.white
        c.setFillColor(bg)
        c.setStrokeColor(_BOX_BORDER)
        c.setLineWidth(0.5)
        c.rect(M, y - row_h, usable, row_h, fill=1, stroke=1)
        # label (right cell)
        P.draw_r(c, W - M - 2 * mm, y - row_h / 2 - 1.5 * mm, lbl, P.BOLD, 8, _NAVY)
        # value (left cell, right-aligned inside the value column)
        val_lines = P.wrap(val, P.BOLD if bold else P.REG, fs, value_w - 4 * mm)
        line_h = fs * 0.5 * mm + 1.5 * mm
        top_text = y - (row_h - len(val_lines) * line_h) / 2 - line_h * 0.55
        for j, vl in enumerate(val_lines):
            P.draw_r(c, M + value_w - 1 * mm, top_text - j * line_h,
                     vl, P.BOLD if bold else P.REG, fs, _TEXT)
        y -= row_h

    # ── SEPARATOR ──────────────────────────────────────────────────────────
    y -= 2 * mm
    _hr(c, M, y, W - M)
    y -= 4 * mm

    # ── PAYMENT METHOD CHECKBOXES ──────────────────────────────────────────
    selected_method = d.get("method", "")
    _draw_payment_methods(c, W, M, y, usable, selected_method)
    y -= 11 * mm

    # ── SEPARATOR ──────────────────────────────────────────────────────────
    _hr(c, M, y, W - M)
    y -= 4 * mm

    # ── TERMS & CONDITIONS ─────────────────────────────────────────────────
    P.draw_r(c, W - M, y, "تعليمات وشروط عامة", P.BOLD, 8.5, _ACCENT)
    y -= 4.5 * mm
    for term in config.RECEIPT_TERMS_AR:
        for line in P.wrap(term, P.REG, 6.8, usable):
            P.draw_r(c, W - M, y, line, P.REG, 6.8, _MUTED)
            y -= 3.2 * mm
    y -= 2 * mm

    # ── SEPARATOR ──────────────────────────────────────────────────────────
    _hr(c, M, y, W - M)
    y -= 5 * mm

    # ── CASHIER SIGNATURE ──────────────────────────────────────────────────
    sig_label = "توقيع الخزينة / المحصل:"
    P.draw_r(c, W - M, y, sig_label, P.BOLD, 8.5, _TEXT)
    # dotted signature line to the left
    sig_line_x2 = W - M - P.width(sig_label, P.BOLD, 8.5) - 4 * mm
    c.setStrokeColor(_MUTED)
    c.setLineWidth(0.5)
    c.setDash(2, 3)
    c.line(M, y + 1 * mm, sig_line_x2, y + 1 * mm)
    c.setDash()

    # ── FOOTER ─────────────────────────────────────────────────────────────
    P.footer(c, W, M, d.get("user", ""))

    # ── WATERMARKS ─────────────────────────────────────────────────────────
    if d.get("status") == "reversed":
        _watermark(c, W, H, "ملغي", colors.Color(0.78, 0.16, 0.16, alpha=0.28), 70)
    elif reprint:
        _watermark(c, W, H, "نسخة", colors.Color(0.4, 0.4, 0.4, alpha=0.16), 60)

    c.showPage()
    c.save()
    return path


# ── Private helpers ───────────────────────────────────────────────────────────

def _header(c: canvas.Canvas, W: float, H: float, M: float, d: dict) -> float:
    """
    Draw logo (left of centre) + academy name + subtitle (right of centre).
    Returns the y-coordinate just below the header rule.
    """
    top = H - M

    # Logo
    logo_size = 18 * mm
    logo_x    = M
    logo_y    = top - logo_size
    if config.LOGO_FILE.exists():
        try:
            c.drawImage(str(config.LOGO_FILE), logo_x, logo_y,
                        logo_size, logo_size, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    # Academy name (right-aligned, to the right of the logo gap)
    text_x = W - M
    P.draw_r(c, text_x, top - 7 * mm,
             config.ACADEMY_FULL_NAME_AR, P.BOLD, 11, _ACCENT)
    P.draw_r(c, text_x, top - 13 * mm,
             "أكاديمية فانتازيا", P.REG, 8, _MUTED)

    # Horizontal rule
    rule_y = top - logo_size - 2 * mm
    c.setStrokeColor(_ACCENT)
    c.setLineWidth(1.2)
    c.line(M, rule_y, W - M, rule_y)

    return rule_y - 3 * mm


def _hr(c: canvas.Canvas, x1: float, y: float, x2: float) -> None:
    c.setStrokeColor(_BOX_BORDER)
    c.setLineWidth(0.8)
    c.setDash()
    c.line(x1, y, x2, y)


def _row_height(text: str, font: str, size: float, max_w: float,
                min_h: float = 8 * mm) -> float:
    lines = P.wrap(text, font, size, max_w - 4 * mm)
    line_h = size * 0.5 * mm + 1.5 * mm
    return max(min_h, len(lines) * line_h + 3 * mm)


def _draw_payment_methods(c: canvas.Canvas, W: float, M: float,
                          y: float, usable: float, selected: str) -> None:
    """Draw 'طريقة الدفع:' label then one checkbox per payment method."""
    lbl = "طريقة الدفع:"
    P.draw_r(c, W - M, y, lbl, P.BOLD, 8.5, _NAVY)

    # map internal keys → display labels (from Word template)
    methods = [
        ("cash",          "نقدي"),
        ("instapay",      "تحويل أنستا"),
        ("vodafone_cash", "تحويل فودافون كاش"),
        ("visa",          "ماكينة تحصيل (POS)"),
    ]

    # lay out checkboxes RTL, starting from the right, after the label
    box_x = W - M - P.width(lbl, P.BOLD, 8.5) - 5 * mm
    box_size = 3.5 * mm
    mid_y    = y - 0.5 * mm      # baseline centre

    for key, label in methods:
        lw = P.width(label, P.REG, 8)
        box_x -= lw + 2 * mm
        # draw checkbox square
        c.setStrokeColor(_TEXT)
        c.setLineWidth(0.6)
        c.rect(box_x - box_size, mid_y - box_size * 0.5, box_size, box_size)
        # tick if selected
        if key == selected or (selected == "other" and key == "cash"):
            c.setStrokeColor(_ACCENT)
            c.setLineWidth(1.2)
            bx, by = box_x - box_size, mid_y - box_size * 0.5
            c.line(bx + 0.3 * mm, by + box_size * 0.5,
                   bx + box_size * 0.45, by + 0.3 * mm)
            c.line(bx + box_size * 0.45, by + 0.3 * mm,
                   bx + box_size - 0.2 * mm, by + box_size - 0.3 * mm)
        # draw label to the right of the box
        P.draw_r(c, box_x - 1.5 * mm, mid_y - 2 * mm, label, P.REG, 8, _TEXT)
        box_x -= box_size + 5 * mm
        if box_x < M + 10 * mm:   # wrap guard (shouldn't happen on A5)
            break


def P_money(x: float) -> str:
    from services.common import money
    return money(x)


def _watermark(c: canvas.Canvas, W: float, H: float,
               text: str, color: colors.Color, size: float) -> None:
    c.saveState()
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.setFillColor(color)
    c.setFont(P.BOLD, size)
    c.drawCentredString(0, 0, P.ar(text))
    c.restoreState()
