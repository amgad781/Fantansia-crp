"""Monthly instructor statement (A4) – replaces the academy's manual account form."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, TableStyle

import config
from export import pdf_common as P
from services.common import money


def build_instructor_pdf(path: Path, st: dict[str, Any], user: str = "") -> Path:
    P.register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    W = A4[0] - 28 * mm
    story = []
    title_text = st.get("custom_title") or ("إيصال صرف مستحقات مدرب" if st.get("payment_id") else "كشف حساب المدرب")
    # title + info
    story.append(P.rtl_table([[title_text]], [W], header=False, font_size=15, zebra=False))
    story[-1].setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), P.BOLD, 15), ("TEXTCOLOR", (0, 0), (-1, -1), P.RED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    period_str = st.get("months_label") or f"{st['period_from']}  إلى  {st['period_to']}"
    info = [["المدرب", st["name"], "الفترة / الأشهر", period_str]]
    if st.get("group_label"):
        info.append(["المجموعة المحددة", st["group_label"], "رقم الدفعة" if st.get("payment_id") else "التخصيص",
                     f"#{st['payment_id']}" if st.get("payment_id") else "حسب المجموعة المختارة"])
    elif st.get("payment_id"):
        info.append(["رقم الدفعة", f"#{st['payment_id']}", "الحالة", "تم الصرف"])

    t = P.rtl_table(info, [26 * mm, W * 0.36, 24 * mm, W - 26 * mm - W * 0.36 - 24 * mm],
                    header=False, font_size=10, zebra=False, align="RIGHT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), P.BOLD, 10), ("BACKGROUND", (0, 0), (-1, -1), P.RED_LIGHT),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [t, Spacer(1, 6 * mm)]

    # sessions + optional custom item
    rows = [["م", "التاريخ", "من", "إلى", "المجموعة / البيان", "الساعات", "سعر الساعة", "المبلغ"]]
    for i, l in enumerate(st["lines"], 1):
        rows.append([str(i), str(l["date"]), f"{l['start']:%H:%M}" if l["start"] else "—",
                     f"{l['end']:%H:%M}" if l["end"] else "—", l["course_level"] or l["group"],
                     f"{l['hours']:g}", money(l["rate"]), money(l["amount"])])
    if st.get("custom_item_label") or st.get("custom_item_amount"):
        idx = len(rows)
        rows.append([
            str(idx),
            str(st["period_to"]),
            "—",
            "—",
            st.get("custom_item_label") or "بند مخصص",
            "—",
            "—",
            money(st.get("custom_item_amount") or 0),
        ])
    if len(rows) == 1:
        rows.append(["", "لا توجد حصص منفذة في هذه الفترة", "", "", "", "", "", ""])
    widths = [10 * mm, 24 * mm, 15 * mm, 15 * mm, W - 10 * mm - 24 * mm - 30 * mm - 17 * mm - 22 * mm - 24 * mm,
              17 * mm, 22 * mm, 24 * mm]
    story += [P.rtl_table(rows, widths, font_size=8.5), Spacer(1, 6 * mm)]

    if st.get("notes"):
        note_tbl = P.rtl_table([["ملاحظات / بيان:", st["notes"]]], [28 * mm, W - 28 * mm],
                               header=False, font_size=9.5, zebra=False, align="RIGHT")
        note_tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (0, 0), P.BOLD, 9.5),
            ("BACKGROUND", (0, 0), (-1, -1), P.ZEBRA),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [note_tbl, Spacer(1, 4 * mm)]

    # totals (right-aligned block)
    tot_w = [55 * mm, 40 * mm]
    paid_lbl = "المبلغ المنصرف في هذه الدفعة" if st.get("payment_id") else "دفعات سابقة"
    totals = [
        ["إجمالي الساعات", f"{st['total_hours']:g}"],
        ["إجمالي المستحق (الحصص)", f"{money(st['gross'])} ج.م"],
    ]
    if st.get("bonuses") or st.get("deductions"):
        totals.append(["المكافآت (+)", f"{money(st.get('bonuses') or 0)} ج.م"])
        totals.append(["الخصومات (−)", f"{money(st.get('deductions') or 0)} ج.م"])
    totals += [
        [paid_lbl, f"{money(st['previous_paid'])} ج.م"],
        ["الصافي المستحق", f"{money(st['net_due'])} ج.م"],
    ]
    last_idx = len(totals) - 1
    tt = P.rtl_table(totals, tot_w, header=False, font_size=10, zebra=False, align="RIGHT")
    tt.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), P.REG, 10), ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                            ("LINEBELOW", (0, 0), (-1, -1), 0.4, P.LINE),
                            ("FONT", (0, last_idx), (-1, last_idx), P.BOLD, 11),
                            ("TEXTCOLOR", (0, last_idx), (-1, last_idx), P.RED),
                            ("BACKGROUND", (0, last_idx), (-1, last_idx), P.RED_LIGHT),
                            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    tt.hAlign = "RIGHT"
    story += [tt, Spacer(1, 8 * mm), P.MethodChecks(W, st.get("methods", [])), Spacer(1, 12 * mm),
              P.SignatureLines(W, ["توقيع المدرب", "توقيع مدير المركز"])]
    P.build_doc(path, f"{title_text} - {st['name']}", f"{title_text} — حساب الساعات", story, user)
    return path
