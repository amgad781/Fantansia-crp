"""Comprehensive Dashboard & Data Analysis PDF Report for a specific date/month period."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, TableStyle

from export import pdf_common as P
from services.common import money


def _section_heading(title: str, w: float):
    t = P.rtl_table([[title]], [w], header=False, font_size=11, zebra=False, align="RIGHT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), P.BOLD, 11),
        ("TEXTCOLOR", (0, 0), (-1, -1), P.NAVY),
        ("BACKGROUND", (0, 0), (-1, -1), P.RED_LIGHT),
        ("LINEBELOW", (0, 0), (-1, -1), 1.0, P.RED),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build_report_pdf(path: Path, data: dict[str, Any], user: str = "") -> Path:
    P.register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W = A4[0] - 28 * mm
    story = []

    # 1. Main Title
    title_tbl = P.rtl_table([["تقرير لوحة التحكم والتحليل المالي والإداري"]], [W], header=False, font_size=15, zebra=False)
    title_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), P.BOLD, 15),
        ("TEXTCOLOR", (0, 0), (-1, -1), P.RED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(title_tbl)

    # 2. Period & Filter Info Box
    period_str = f"من {data['period_from']}  إلى  {data['period_to']}  ({data.get('days_count', 1)} يوم)"
    info = [
        ["الفترة الزمنية", period_str, "البرنامج / المركز", data.get("program") or "كل البرامج"],
    ]
    info_tbl = P.rtl_table(info, [28 * mm, W * 0.44, 28 * mm, W - 56 * mm - W * 0.44],
                           header=False, font_size=9.5, zebra=False, align="RIGHT")
    info_tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), P.BOLD, 9.5),
        ("BACKGROUND", (0, 0), (-1, -1), P.ZEBRA),
        ("BOX", (0, 0), (-1, -1), 0.6, P.LINE),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [info_tbl, Spacer(1, 5 * mm)]

    tot = data["totals"]
    kpis = data["kpis"]

    # 3. Section 1: Financial Summary & Net Profit
    story += [_section_heading("أولًا: الملخص المالي للفترة المختارة", W), Spacer(1, 2 * mm)]
    fin_rows = [
        ["إجمالي الإيرادات", "المصروفات التشغيلية", "أجور المدربين", "رواتب الموظفين", "صافي الربح / الفائض"],
        [f"{money(tot['revenue'])} ج.م", f"{money(tot['expenses'])} ج.م",
         f"{money(tot['instructors'])} ج.م", f"{money(tot['salaries'])} ج.م", f"{money(tot['net'])} ج.م"],
    ]
    col_w5 = [W / 5.0] * 5
    fin_tbl = P.rtl_table(fin_rows, col_w5, header=True, font_size=9.5, zebra=False)
    fin_tbl.setStyle(TableStyle([
        ("FONT", (0, 1), (-1, 1), P.BOLD, 10),
        ("BACKGROUND", (0, 1), (0, 1), P.RED_LIGHT),
        ("TEXTCOLOR", (0, 1), (0, 1), P.RED),
    ]))
    story += [fin_tbl, Spacer(1, 5 * mm)]

    # 4. Section 2: Operational & Dashboard KPIs
    story += [_section_heading("ثانيًا: مؤشرات الأداء والتشغيل (Dashboard KPIs)", W), Spacer(1, 2 * mm)]
    kpi_rows = [
        ["عدد الإيصالات المحصلة", str(kpis["receipts_count"]),
         "نسبة التحصيل للفترة", f"{kpis['collection_rate']:g}%"],
        ["الحصص المنفذة (ساعات)", f"{kpis['sessions_held']} حصة ({kpis['sessions_hours']:g} ساعة)",
         "نسبة حضور الطلاب", f"{kpis['attendance_rate']:g}%"],
        ["الطلاب النشطون حاليًا", f"{kpis['active_students']} طالب",
         "اشتراكات جديدة في الفترة", f"{kpis['new_enrollments']} اشتراك"],
        ["فيزا معلّقة (قيد التحصيل البنكي)", f"{money(kpis['pending_visa'])} ج.م ({kpis['pending_visa_count']})",
         "فيزا تمت تسويتها بالبنك", f"{money(kpis['settled_visa'])} ج.م"],
    ]
    kpi_w = [42 * mm, W * 0.5 - 42 * mm, 42 * mm, W * 0.5 - 42 * mm]
    kpi_tbl = P.rtl_table(kpi_rows, kpi_w, header=False, font_size=9, zebra=True, align="RIGHT")
    kpi_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, P.LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, P.LINE),
    ]))
    story += [kpi_tbl, Spacer(1, 5 * mm)]

    # 5. Section 3: Payment Methods Distribution
    story += [_section_heading("ثالثًا: تحليل وتوزيع طرق الدفع", W), Spacer(1, 2 * mm)]
    pm_rows = [["طريقة الدفع", "عدد العمليات", "إجمالي المبلغ", "النسبة المئوية"]]
    for m in data.get("by_payment_method", []):
        pm_rows.append([m["method"], str(m.get("count", 0)), f"{money(m['amount'])} ج.م", f"{m.get('pct', 0):g}%"])
    if len(pm_rows) == 1:
        pm_rows.append(["لا توجد مقبوضات في هذه الفترة", "0", "0 ج.م", "0%"])
    story += [P.rtl_table(pm_rows, [W * 0.35, W * 0.2, W * 0.25, W * 0.2], font_size=9), Spacer(1, 5 * mm)]

    # 6. Section 4: Revenue by Program
    story += [_section_heading("رابعًا: تحليل الإيرادات حسب البرنامج", W), Spacer(1, 2 * mm)]
    prog_rows = [["البرنامج / مركز التكلفة", "عدد الإيصالات", "الإيراد", "النسبة المئوية"]]
    for p in data.get("by_program", []):
        prog_rows.append([p["program"], str(p.get("count", 0)), f"{money(p['revenue'])} ج.م", f"{p.get('pct', 0):g}%"])
    if len(prog_rows) == 1:
        prog_rows.append(["لا توجد إيرادات في هذه الفترة", "0", "0 ج.م", "0%"])
    story += [P.rtl_table(prog_rows, [W * 0.35, W * 0.2, W * 0.25, W * 0.2], font_size=9), Spacer(1, 5 * mm)]

    # 7. Section 5: Instructor Cost & Hours
    story += [_section_heading("خامسًا: تكلفة وساعات المدربين خلال الفترة", W), Spacer(1, 2 * mm)]
    ins_rows = [["المدرب", "عدد الحصص", "إجمالي الساعات", "التكلفة المستحقة"]]
    for i in data.get("instructor_cost", []):
        ins_rows.append([i["instructor"], str(i.get("sessions", 0)), f"{i['hours']:g}", f"{money(i['amount'])} ج.م"])
    if len(ins_rows) == 1:
        ins_rows.append(["لا توجد حصص منفذة في هذه الفترة", "0", "0", "0 ج.م"])
    story += [P.rtl_table(ins_rows, [W * 0.4, W * 0.2, W * 0.2, W * 0.2], font_size=9), Spacer(1, 5 * mm)]

    # 8. Section 6: Expenses by Category
    story += [_section_heading("سادسًا: تحليل المصروفات حسب التصنيف", W), Spacer(1, 2 * mm)]
    exp_rows = [["التصنيف", "عدد الحركات", "المبلغ", "النسبة المئوية"]]
    for c in data.get("by_expense_category", []):
        exp_rows.append([c["category"], str(c.get("count", 0)), f"{money(c['amount'])} ج.م", f"{c.get('pct', 0):g}%"])
    if len(exp_rows) == 1:
        exp_rows.append(["لا توجد مصروفات في هذه الفترة", "0", "0 ج.م", "0%"])
    story += [P.rtl_table(exp_rows, [W * 0.35, W * 0.2, W * 0.25, W * 0.2], font_size=9), Spacer(1, 5 * mm)]

    # 9. Section 7: Period Breakdown (Daily or Monthly Series)
    series = data.get("series", [])
    if series:
        story += [_section_heading("سابعًا: التدفق المالي التفصيلي خلال الفترة", W), Spacer(1, 2 * mm)]
        ser_rows = [["الفترة / التاريخ", "الإيرادات", "المصروفات", "أجور المدربين", "الرواتب", "الصافي"]]
        for s in series:
            ser_rows.append([
                str(s.get("date") or s.get("label") or ""),
                money(s["revenue"]), money(s["expenses"]),
                money(s["instructors"]), money(s["salaries"]), money(s["net"]),
            ])
        story += [P.rtl_table(ser_rows, [W * 0.22, W * 0.16, W * 0.15, W * 0.16, W * 0.15, W * 0.16], font_size=8.5),
                  Spacer(1, 8 * mm)]

    story.append(P.SignatureLines(W, ["إعداد المحاسب / الإدارة", "اعتماد مدير الأكاديمية"]))
    P.build_doc(
        path,
        f"تقرير التحليل المالي والإداري ({data['period_from']} - {data['period_to']})",
        f"تقرير الأداء والتحليل المالي — {data['period_from']} إلى {data['period_to']}",
        story,
        user=user,
    )
    return path
