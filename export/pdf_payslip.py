"""Employee payslip (A5) and the all-employees monthly summary (A4)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Spacer, TableStyle

import config
from export import pdf_common as P
from services.common import money, month_label


def build_payslip_pdf(path: Path, d: dict[str, Any], user: str = "") -> Path:
    P.register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W, H = A5
    M = 11 * mm
    c = canvas.Canvas(str(path), pagesize=A5)
    c.setTitle(f"كشف راتب - {d['name']}")
    y = P.header(c, W, H, M, "كشف راتب شهري")
    P.draw_c(c, W / 2, y - 4 * mm, "كشف راتب", P.BOLD, 17, P.RED)
    y -= 14 * mm

    def row(label: str, value: str, bold: bool = False, shade: bool = False) -> None:
        nonlocal y
        if shade:
            c.setFillColor(P.RED_LIGHT)
            c.roundRect(M, y - 3.5 * mm, W - 2 * M, 10 * mm, 2 * mm, fill=1, stroke=0)
        P.draw_r(c, W - M - 3 * mm, y, label, P.BOLD if bold else P.REG, 10.5, P.RED if shade else P.TEXT)
        P.draw_l(c, M + 3 * mm, y, value, P.BOLD if bold else P.REG, 10.5, P.RED if shade else P.TEXT)
        if not shade:
            c.setStrokeColor(P.LINE)
            c.setLineWidth(0.4)
            c.line(M, y - 3 * mm, W - M, y - 3 * mm)
        y -= 11 * mm

    row("اسم الموظف", d["name"], bold=True)
    row("الوظيفة", d["job_title"] or "—")
    row("الشهر", month_label(d["month"]))
    y -= 3 * mm
    row("الراتب الأساسي", f"{money(d['base'])} ج.م")
    row("المكافآت", f"+ {money(d['bonuses'])} ج.م")
    row("الخصومات", f"- {money(d['deductions'])} ج.م")
    y -= 2 * mm
    row("صافي الراتب", f"{money(d['net'])} ج.م", bold=True, shade=True)
    y -= 4 * mm
    status = "تم الصرف" if d["status"] == "paid" else "لم يتم الصرف بعد"
    row("حالة الصرف", status + (f" — {config.PAYMENT_METHODS_AR.get(d['method'], d['method'])} — {d['paid_on']}"
                                if d["status"] == "paid" else ""))
    sy = 38 * mm
    for x0, label in ((W - M - 45 * mm, "توقيع الموظف"), (M, "اعتماد الإدارة")):
        c.setStrokeColor(P.TEXT)
        c.setLineWidth(0.6)
        c.line(x0, sy, x0 + 45 * mm, sy)
        P.draw_c(c, x0 + 22.5 * mm, sy - 4.5 * mm, label, P.REG, 8.5, P.MUTED)
    P.footer(c, W, M, user)
    c.showPage()
    c.save()
    return path


def build_payroll_summary_pdf(path: Path, month: str, rows: list[dict[str, Any]], user: str = "") -> Path:
    P.register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W = A4[0] - 28 * mm
    data = [["م", "الموظف", "الوظيفة", "الأساسي", "مكافآت", "خصومات", "الصافي", "الحالة"]]
    for i, r in enumerate(rows, 1):
        data.append([str(i), r["name"], r["job_title"] or "—", money(r["base"]), money(r["bonuses"]),
                     money(r["deductions"]), money(r["net"]), "مدفوع" if r["status"] == "paid" else "غير مدفوع"])
    data.append(["", "الإجمالي", "", money(sum(r["base"] for r in rows)), money(sum(r["bonuses"] for r in rows)),
                 money(sum(r["deductions"] for r in rows)), money(sum(r["net"] for r in rows)), ""])
    widths = [9 * mm, 42 * mm, 34 * mm, 23 * mm, 20 * mm, 20 * mm, 24 * mm, W - 9 * mm - 42 * mm - 34 * mm - 87 * mm]
    t = P.rtl_table(data, widths, font_size=8.5)
    t.setStyle(TableStyle([("FONT", (0, len(data) - 1), (-1, len(data) - 1), P.BOLD, 9),
                           ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), P.RED_LIGHT)]))
    story = [t, Spacer(1, 12 * mm), P.SignatureLines(W, ["توقيع المحاسب", "اعتماد المالك"])]
    P.build_doc(path, f"رواتب {month}", f"كشف رواتب شهر {month_label(month)}", story, user)
    return path
