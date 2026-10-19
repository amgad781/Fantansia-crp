"""Owner dashboard: today's numbers, today's sessions, overdue fees, month chart (step 9)."""
from __future__ import annotations

from nicegui import ui

import config
from core.context import AppContext
from services.common import money, month_key, month_label, today
from ui import components as C
from ui.components import STATUS_AR, card, col, data_table
from ui.layout import COLORS
from ui.reports_page import bar_options, donut_options


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    st = svc.reports.today_stats()
    cur = month_key(today())

    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("لوحة التحكم", f"اليوم {today():%Y-%m-%d} — مؤشرات الأداء والمتابعة اليومية")
        with ui.row().classes("gap-2"):
            ui.button("تسجيل طالب", icon="person_add", on_click=lambda: ui.navigate.to("/students/new")).props("outline no-caps dense")
            ui.button("إيصال جديد", icon="receipt_long", on_click=lambda: ui.navigate.to("/receipts")).props("unelevated no-caps dense")

    with ui.row().classes("w-full gap-3"):
        C.stat_card("إيرادات اليوم", money(st["revenue_today"]) + " ج.م", "payments", "success")
        C.stat_card("إجمالي المتأخرات", money(st["overdue_total"]) + " ج.م", "notification_important", "warning")
        C.stat_card("حصص اليوم", str(len(st["sessions"])), "event")
        C.stat_card("رصيد الدرج النقدي", money(st["drawer"]) + " ج.م", "account_balance_wallet", "accent")

    with ui.row().classes("w-full gap-3"):
        C.stat_card("الطلاب النشطون", f"{st.get('active_students', 0)} طالب ({st.get('active_groups', 0)} مجموعة)", "school", "primary")
        C.stat_card("نسبة التحصيل", f"{st.get('collection_rate', 100):g}%", "pie_chart", "success")
        C.stat_card("نسبة الحضور", f"{st.get('attendance_rate', 100):g}%", "fact_check", "accent")
        C.stat_card("معاملات فيزا معلّقة", f"{money(st.get('pending_visa', 0))} ج.م ({st.get('pending_visa_count', 0)})", "credit_score", "warning")

    if st.get("pending_visa_count", 0) > 0 or st.get("low_lessons_count", 0) > 0:
        with ui.row().classes("w-full gap-3"):
            if st.get("pending_visa_count", 0) > 0:
                with ui.row().classes("flex-1 items-center justify-between p-3 rounded-xl") \
                        .style("background:#FFF7ED;border:1px solid #FED7AA"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("credit_score", color="warning", size="22px")
                        ui.label(f"يوجد {st['pending_visa_count']} عملية فيزا بقيمة {money(st['pending_visa'])} ج.م قيد التحصيل البنكي").classes("font-semibold text-sm")
                    ui.button("متابعة الفيزا والبنك", on_click=lambda: ui.navigate.to("/settlements")).props("flat dense no-caps color=warning")
            if st.get("low_lessons_count", 0) > 0:
                with ui.row().classes("flex-1 items-center justify-between p-3 rounded-xl") \
                        .style("background:#FEF2F2;border:1px solid #FECACA"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("warning_amber", color="negative", size="22px")
                        ui.label(f"يوجد {st['low_lessons_count']} طالب رصيد حصصهم المتبقية (حصتان أو أقل)").classes("font-semibold text-sm")
                    ui.button("عرض الطلاب", on_click=lambda: ui.navigate.to("/students")).props("flat dense no-caps color=negative")

    with ui.row().classes("w-full gap-4 no-wrap").style("flex-wrap:wrap"):
        with card("حصص اليوم", style="flex:1 1 420px"):
            rows = [dict(r, k=r["session_id"], status_l=STATUS_AR.get(r["status"], r["status"])) for r in st["sessions"]]
            data_table([col("time", "الوقت"), col("group", "المجموعة"), col("instructor", "المدرب"), col("status_l", "الحالة")],
                       rows, "k", page_size=6, no_data="لا توجد حصص اليوم")
            ui.button("الحضور والغياب", icon="fact_check", on_click=lambda: ui.navigate.to("/attendance")).props("flat no-caps dense")
        with card("المتأخرات", style="flex:1 1 420px"):
            rows = [dict(r, months_l="، ".join(month_label(m) for m in r["months"]), amount_l=money(r["amount"]))
                    for r in st["overdue"]]
            t = data_table([col("name", "الطالب"), col("months_l", "الأشهر"), col("amount_l", "المبلغ")], rows,
                           "enrollment_id", page_size=6, no_data="لا توجد متأخرات")
            t.on("rowClick", lambda e: ui.navigate.to(f"/students/{e.args[1]['student_id']}"))
            ui.button("كل المتأخرات", icon="payments", on_click=lambda: ui.navigate.to("/collection")).props("flat no-caps dense")

    t_info = st.get("targets") or svc.reports.get_monthly_targets()
    with card(f"ملخص الشهر والمستهدف — {month_label(cur)}"):
        m = st["month"]
        with ui.row().classes("w-full items-center justify-between gap-4"):
            with ui.row().classes("gap-8 flex-wrap"):
                for label, key in (("الإيرادات", "revenue"), ("المصروفات", "expenses"), ("أجور المدربين", "instructors"),
                                   ("الرواتب", "salaries"), ("الصافي", "net")):
                    with ui.column().classes("gap-0"):
                        ui.label(label).classes("muted text-xs")
                        ui.label(money(m[key]) + " ج.م").classes("font-bold text-lg")
            ui.button("تعديل المستهدف الشهري", icon="flag",
                      on_click=lambda: _targets_dialog(ctx, t_info)).props("outline dense no-caps color=primary")

        if t_info.get("revenue_target", 0) > 0 or t_info.get("expense_budget", 0) > 0:
            with ui.row().classes("w-full gap-4 mt-1 flex-wrap"):
                if t_info.get("revenue_target", 0) > 0:
                    rev_pct = float(t_info.get("revenue_pct", 0.0))
                    with ui.column().classes("flex-1 gap-1 p-3 rounded-xl").style(
                        "min-width:260px;background:#F8FAFC;border:1px solid #E2E8F0"
                    ):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label(f"مستهدف الإيرادات الشهري: {money(t_info['revenue_target'])} ج.م").classes("text-xs font-bold")
                            ui.badge(f"{rev_pct:g}%", color="positive" if rev_pct >= 80 else "primary")
                        ui.linear_progress(value=min(1.0, rev_pct / 100.0), show_value=False) \
                            .props("rounded size=10px color=positive")
                if t_info.get("expense_budget", 0) > 0:
                    exp_pct = float(t_info.get("expense_pct", 0.0))
                    over = bool(t_info.get("budget_exceeded"))
                    with ui.column().classes("flex-1 gap-1 p-3 rounded-xl").style(
                        f"min-width:260px;background:{'#FEF2F2' if over else '#F8FAFC'};"
                        f"border:1px solid {'#FECACA' if over else '#E2E8F0'}"
                    ):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label(
                                f"سقف المصروفات والأجور ({money(t_info.get('month_total_out', 0))} / {money(t_info['expense_budget'])} ج.م)"
                            ).classes("text-xs font-bold")
                            ui.badge(f"{exp_pct:g}%", color="negative" if over else ("warning" if exp_pct >= 85 else "accent"))
                        ui.linear_progress(value=min(1.0, exp_pct / 100.0), show_value=False) \
                            .props(f"rounded size=10px color={'negative' if over else 'accent'}")
                        if over:
                            ui.label("تنبيه: إجمالي المصروفات والأجور تجاوز السقف المحدد لهذا الشهر!") \
                                .classes("text-xs font-bold text-negative")
        with ui.row().classes("w-full gap-4 no-wrap").style("flex-wrap:wrap"):
            series = svc.reports.series(cur, 6)
            ui.echart(bar_options([s["label"] for s in series], [
                {"name": "الإيرادات", "type": "bar", "data": [s["revenue"] for s in series], "itemStyle": {"color": COLORS["primary"]}},
                {"name": "المصروفات", "type": "bar", "data": [round(s["expenses"] + s["instructors"] + s["salaries"], 2) for s in series],
                 "itemStyle": {"color": COLORS["accent"]}}])).classes("flex-1").style("height:280px;min-width:340px")
            prog = svc.reports.by_program(cur, cur)
            if prog:
                ui.echart(donut_options([{"name": p["program"], "value": p["revenue"]} for p in prog])) \
                    .style("height:280px;min-width:260px;flex:1")

    with ui.row().classes("w-full gap-4 no-wrap").style("flex-wrap:wrap"):
        with card("توزيع طرق الدفع", style="flex:1 1 420px"):
            pm = st.get("payment_methods") or svc.reports.by_payment_method(cur, cur)
            if pm:
                ui.echart(donut_options([{"name": m["method"], "value": m["amount"]} for m in pm])) \
                    .classes("w-full").style("height:270px")
            else:
                C.empty_hint("لا توجد مقبوضات مسجلة بعد", "payments")
        with card("مصادر معرفة الأكاديمية", style="flex:1 1 420px"):
            sources = st.get("lead_sources") or []
            if sources:
                ui.echart(donut_options([{"name": s.get("name", s.get("source", "")),
                                          "value": s.get("value", s.get("count", 0))} for s in sources])) \
                    .classes("w-full").style("height:270px")
            else:
                C.empty_hint("لا توجد بيانات مصادر بعد", "pie_chart")

    backups = ctx.repo.list_backups()
    ui.label(f"قاعدة البيانات: {ctx.repo.path}  |  النسخ الاحتياطية: {len(backups)}"
             + (f"  |  آخر نسخة: {backups[0][0]:%Y-%m-%d %H:%M}" if backups else "")).classes("text-xs muted ltr")


def _targets_dialog(ctx: AppContext, cur_targets: dict) -> None:
    from ui.components import guarded, ok
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:460px;max-width:96vw"):
        ui.label("تعديل المستهدف الشهري وسقف المصروفات").classes("text-lg font-bold")
        ui.label("حدّد مستهدف الإيرادات الشهرية وسقف المصروفات لمتابعة التقدم والتنبيه عند التجاوز.").classes("text-xs muted")
        rev_in = C.num_input("مستهدف الإيرادات الشهري", cur_targets.get("revenue_target") or 0, "100%", "ج.م", min_=0)
        exp_in = C.num_input("سقف المصروفات والأجور الشهري", cur_targets.get("expense_budget") or 0, "100%", "ج.م", min_=0)
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.reports.set_monthly_targets(float(rev_in.value or 0), float(exp_in.value or 0))
                d.close()
                ok("تم حفظ المستهدف الشهري")
                ui.navigate.reload()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()
