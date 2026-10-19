"""Cash receipt PDF (A5) following the academy's paper receipt."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

import config
from export import pdf_common as P


def build_receipt_pdf(path: Path, d: dict[str, Any], reprint: bool = False) -> Path:
    P.register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = A5
    M = 11 * mm
    c = canvas.Canvas(str(path), pagesize=A5)
    c.setTitle(f"إيصال {d['serial']}")
    y = P.header(c, W, H, M, "إيصال استلام نقدية")

    # title + serial/date box
    P.draw_c(c, W / 2, y - 4 * mm, "إيصال استلام نقدية", P.BOLD, 17, P.RED)
    y -= 12 * mm
    c.setFillColor(P.RED_LIGHT)
    c.setStrokeColor(P.RED)
    c.roundRect(M, y - 9 * mm, W - 2 * M, 10 * mm, 2 * mm, fill=1, stroke=0)
    P.draw_r(c, W - M - 4 * mm, y - 5.5 * mm, f"مسلسل:  {d['serial']}", P.BOLD, 11, P.RED)
    P.draw_l(c, M + 4 * mm, y - 5.5 * mm, f"التاريخ:  {d['date']}", P.REG, 10.5)
    y -= 17 * mm

    def row(label: str, value: str, bold: bool = False, size: float = 11) -> None:
        """Label (small, muted) above the value; dotted rule underneath."""
        nonlocal y
        P.draw_r(c, W - M, y, label, P.REG, 8, P.MUTED)
        font = P.BOLD if bold else P.REG
        lines = P.wrap(value, font, size, W - 2 * M)
        for i, line in enumerate(lines):
            P.draw_r(c, W - M, y - 5.2 * mm - i * 5 * mm, line, font, size)
        yy = y - 6.8 * mm - (len(lines) - 1) * 5 * mm
        c.setStrokeColor(P.LINE)
        c.setLineWidth(0.5)
        c.setDash(1, 2)
        c.line(M, yy, W - M, yy)
        c.setDash()
        y = yy - 5.5 * mm

    row("استلمت من السيد / السيدة", d["student_name"], bold=True, size=12)
    row("المبلغ", f"{P_money(d['amount'])} ج.م", bold=True, size=13)
    row("المبلغ كتابةً", P.amount_words(d["amount"]), size=9.5)
    row("البيان", d["description"] or "—")
    row("مركز التكلفة", d["cost_center"] or "—")
    row("طريقة الدفع", d["method"])
    if d.get("remaining") is not None:
        row("المتبقي من الرسوم بعد هذه الدفعة", f"{P_money(d['remaining'])} ج.م")

    # signatures
    sy = 50 * mm
    c.setStrokeColor(P.TEXT)
    c.setLineWidth(0.6)
    c.line(W - M - 45 * mm, sy, W - M, sy)
    c.line(M, sy, M + 45 * mm, sy)
    P.draw_c(c, W - M - 22.5 * mm, sy - 4.5 * mm, "توقيع المستلم", P.REG, 8.5, P.MUTED)
    P.draw_c(c, M + 22.5 * mm, sy - 4.5 * mm, "ختم الأكاديمية", P.REG, 8.5, P.MUTED)

    # terms
    ty = 36 * mm
    P.draw_r(c, W - M, ty, "تعليمات عامة", P.BOLD, 8, P.RED)
    ty -= 4 * mm
    for term in config.RECEIPT_TERMS_AR:
        for line in P.wrap(term, P.REG, 6.8, W - 2 * M):
            P.draw_r(c, W - M, ty, line, P.REG, 6.8, P.MUTED)
            ty -= 3.1 * mm
    P.footer(c, W, M, d.get("user", ""))

    # watermarks
    if d.get("status") == "reversed":
        _watermark(c, W, H, "ملغي", P.colors.Color(0.78, 0.16, 0.16, alpha=0.28), 70)
    elif reprint:
        _watermark(c, W, H, "نسخة", P.colors.Color(0.4, 0.4, 0.4, alpha=0.16), 60)
    c.showPage()
    c.save()
    return path


def P_money(x: float) -> str:
    from services.common import money
    return money(x)


def _watermark(c, W, H, text, color, size) -> None:
    c.saveState()
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.setFillColor(color)
    c.setFont(P.BOLD, size)
    c.drawCentredString(0, 0, P.ar(text))
    c.restoreState()
