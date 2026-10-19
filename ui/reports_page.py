"""Reports (owner): summary cards, operational KPIs, daily/monthly period selector, charts, PDF & Excel export (step 9)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

import config
from core.context import AppContext
from export import service as ex
from services.common import ServiceError, money, month_key, months_between, shift_month, today
from ui import components as C
from ui.components import DateField, card, guarded
from ui.layout import COLORS

FONT = {"fontFamily": "Cairo, Tajawal, sans-serif"}

CHART_PALETTE = ["#F05500", "#0A194E", "#FB923C", "#1E3A8A", "#F59E0B", "#16A34A", "#64748B"]


def bar_options(labels: list[str], series: list[dict]) -> dict:
    return {"color": CHART_PALETTE, "textStyle": FONT, "tooltip": {"trigger": "axis"}, "legend": {"top": 0, "textStyle": FONT},
            "grid": {"left": 50, "right": 20, "top": 40, "bottom": 30, "containLabel": True},
            "xAxis": {"type": "category", "data": labels}, "yAxis": {"type": "value"}, "series": series}


def donut_options(data: list[dict]) -> dict:
    return {"color": CHART_PALETTE, "textStyle": FONT, "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"bottom": 0, "textStyle": FONT},
            "series": [{"type": "pie", "radius": ["45%", "70%"], "avoidLabelOverlap": True,
                        "label": {"show": False}, "data": data}]}


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    t_now = today()
    cur = month_key(t_now)
    f: dict[str, Any] = {
        "mode": "months",
        "first": shift_month(cur, -5),
        "last": cur,
        "d_from": t_now.replace(day=1),
        "d_to": t_now,
        "program": "",
    }

    def _current_bounds() -> tuple[date | str, date | str]:
        if f["mode"] == "days":
            return f["d_from"], f["d_to"]
        return f["first"], f["last"]

    @ui.refreshable
    def content() -> None:
        if f["mode"] == "months":
            if f["first"] > f["last"]:
                ui.label("بداية الفترة بعد نهايتها.").classes("text-warning")
                return
            months = months_between(f["first"], f["last"])
            if len(months) > 24:
                ui.label("اختر فترة لا تزيد على 24 شهرًا.").classes("text-warning")
                return
            lo_arg, hi_arg = f["first"], f["last"]
            series = svc.reports.series(f["last"], len(months), f["program"])
            tot = {k: round(sum(s[k] for s in series), 2) for k in ("revenue", "expenses", "instructors", "salaries", "net")}
            analysis = svc.reports.period_analysis(lo_arg, hi_arg, f["program"])
            chart_title = "الإيرادات مقابل التكاليف شهريًا"
        else:
            d_lo, d_hi = f.get("d_from"), f.get("d_to")
            if not d_lo or not d_hi or d_lo > d_hi:
                ui.label("بداية الفترة بعد نهايتها.").classes("text-warning")
                return
            if (d_hi - d_lo).days > 730:
                ui.label("اختر فترة لا تزيد على سنتين (730 يومًا).").classes("text-warning")
                return
            lo_arg, hi_arg = d_lo, d_hi
            analysis = svc.reports.period_analysis(d_lo, d_hi, f["program"])
            tot = analysis["totals"]
            series = analysis["series"]
            chart_title = f"الإيرادات مقابل التكاليف ({d_lo} → {d_hi})"

        kpis = analysis["kpis"]

        with ui.row().classes("w-full gap-3"):
            C.stat_card("الإيرادات", money(tot["revenue"]) + " ج.م", "trending_up", "success")
            C.stat_card("المصروفات", money(tot["expenses"]) + " ج.م", "shopping_cart", "warning")
            C.stat_card("أجور المدربين", money(tot["instructors"]) + " ج.م", "badge")
            C.stat_card("الرواتب", money(tot["salaries"]) + " ج.م", "work")
            C.stat_card("الصافي", money(tot["net"]) + " ج.م", "account_balance", "accent")

        with ui.row().classes("w-full gap-3"):
            C.stat_card("الإيصالات المحصلة", f"{kpis['receipts_count']} إيصال", "receipt_long", "primary")
            C.stat_card("الحصص المنفذة", f"{kpis['sessions_held']} حصة ({kpis['sessions_hours']:g} س)", "event", "accent")
            C.stat_card("نسبة التحصيل", f"{kpis['collection_rate']:g}%", "pie_chart", "success")
            C.stat_card("نسبة الحضور", f"{kpis['attendance_rate']:g}%", "fact_check", "accent")
            C.stat_card("فيزا معلّقة بالفترة", f"{money(kpis['pending_visa'])} ج.م ({kpis['pending_visa_count']})", "credit_score", "warning")

        with card(chart_title):
            ui.echart(bar_options([s["label"] for s in series], [
                {"name": "الإيرادات", "type": "bar", "data": [s["revenue"] for s in series], "itemStyle": {"color": COLORS["primary"]}},
                {"name": "التكاليف", "type": "bar", "data": [round(s["expenses"] + s["instructors"] + s["salaries"], 2) for s in series],
                 "itemStyle": {"color": "#9CA3AF"}},
                {"name": "الصافي", "type": "line", "data": [s["net"] for s in series], "itemStyle": {"color": COLORS["accent"]}}])) \
                .classes("w-full").style("height:320px")
        with ui.row().classes("w-full gap-4 no-wrap").style("flex-wrap:wrap"):
            with card("الإيراد حسب البرنامج", style="flex:1 1 380px"):
                prog = analysis["by_program"]
                if prog:
                    ui.echart(donut_options([{"name": p["program"], "value": p["revenue"]} for p in prog])) \
                        .classes("w-full").style("height:300px")
                else:
                    C.empty_hint("لا توجد إيرادات في هذه الفترة", "pie_chart")
            with card("تكلفة المدربين", style="flex:1 1 380px"):
                ins = analysis["instructor_cost"]
                if ins:
                    ui.echart(bar_options([i["instructor"] for i in ins], [
                        {"name": "المبلغ", "type": "bar", "data": [i["amount"] for i in ins],
                         "itemStyle": {"color": COLORS["primary"]}}])).classes("w-full").style("height:300px")
                else:
                    C.empty_hint("لا توجد حصص منفذة في هذه الفترة", "bar_chart")
        with ui.row().classes("w-full gap-4 no-wrap").style("flex-wrap:wrap"):
            with card("الإيراد حسب طريقة الدفع", style="flex:1 1 380px"):
                pm = analysis["by_payment_method"]
                if pm:
                    ui.echart(donut_options([{"name": m["method"], "value": m["amount"]} for m in pm])) \
                        .classes("w-full").style("height:280px")
                else:
                    C.empty_hint("لا توجد مقبوضات في هذه الفترة", "payments")
            with card("المصروفات حسب التصنيف", style="flex:1 1 380px"):
                ec = analysis["by_expense_category"]
                if ec:
                    ui.echart(bar_options([c["category"] for c in ec], [
                        {"name": "المبلغ", "type": "bar", "data": [c["amount"] for c in ec],
                         "itemStyle": {"color": COLORS["warning"]}}])).classes("w-full").style("height:280px")
                else:
                    C.empty_hint("لا توجد مصروفات في هذه الفترة", "shopping_cart")

    @guarded
    def export_excel() -> None:
        lo, hi = _current_bounds()
        if not lo or not hi or lo > hi:
            raise ServiceError("بداية الفترة بعد نهايتها.")
        tag = f"{lo}_{hi}"
        path = svc.reports.export_excel(config.EXPORT_DIR / f"report_{tag}.xlsx", lo, hi, f["program"])
        C.pdf_dialog(path, "تم تصدير التقرير (Excel)")

    @guarded
    def export_pdf(open_direct: bool = False) -> None:
        lo, hi = _current_bounds()
        if not lo or not hi or lo > hi:
            raise ServiceError("بداية الفترة بعد نهايتها.")
        path = ex.export_period_report_pdf(ctx, lo, hi, program=f["program"])
        if open_direct:
            ex.open_path(path)
        else:
            C.pdf_dialog(path, "تم تصدير تقرير لوحة التحكم والتحليل المالي (PDF)")

    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("التقارير", "ملخص مالي وتحليل بيانات شامل للفترة المختارة (بالشهور أو بالأيام)")
        with ui.row().classes("gap-2"):
            ui.button("تصدير تقرير وتحليل PDF", icon="picture_as_pdf", on_click=lambda: export_pdf(False)) \
                .props("unelevated no-caps color=primary")
            ui.button("طباعة التقرير PDF", icon="print", on_click=lambda: export_pdf(True)) \
                .props("outline no-caps color=secondary")
            ui.button("تصدير Excel", icon="download", on_click=export_excel).props("outline no-caps")

    with card():
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            mode_toggle = ui.toggle(
                {"months": "تحديد بالشهور", "days": "فترة مخصصة باليوم"},
                value=f["mode"],
            ).props("no-caps unelevated toggle-color=primary")

            with ui.row().classes("items-center gap-3") as months_box:
                ui.select(C.month_options(24, 0), value=f["first"], label="من شهر",
                          on_change=lambda e: (f.update(first=e.value), content.refresh())).props("outlined dense").style("width:185px")
                ui.select(C.month_options(24, 0), value=f["last"], label="إلى شهر",
                          on_change=lambda e: (f.update(last=e.value), content.refresh())).props("outlined dense").style("width:185px")

            with ui.row().classes("items-center gap-2") as days_box:
                df_in = DateField("من تاريخ", f["d_from"], width="165px",
                                  on_change=lambda: (f.update(d_from=df_in.get()), content.refresh()))
                dt_in = DateField("إلى تاريخ", f["d_to"], width="165px",
                                  on_change=lambda: (f.update(d_to=dt_in.get()), content.refresh()))
                ui.button("اليوم", on_click=lambda: _set_days(t_now, t_now)).props("flat dense no-caps size=sm")
                ui.button("آخر 7 أيام", on_click=lambda: _set_days(t_now - timedelta(days=6), t_now)).props("flat dense no-caps size=sm")
                ui.button("هذا الشهر", on_click=lambda: _set_days(t_now.replace(day=1), t_now)).props("flat dense no-caps size=sm")
                ui.button("آخر 30 يومًا", on_click=lambda: _set_days(t_now - timedelta(days=29), t_now)).props("flat dense no-caps size=sm")
            days_box.set_visibility(False)

            def _set_days(d1: date, d2: date) -> None:
                f.update(d_from=d1, d_to=d2)
                df_in.set(d1)
                dt_in.set(d2)
                content.refresh()

            def _on_mode(e) -> None:
                f["mode"] = e.value
                months_box.set_visibility(e.value == "months")
                days_box.set_visibility(e.value == "days")
                content.refresh()

            mode_toggle.on_value_change(_on_mode)

            progs = {"": "كل البرامج"}
            progs.update({g.cost_center: g.cost_center for g in svc.ledger().groups.values()})
            ui.select(progs, value="", label="البرنامج",
                      on_change=lambda e: (f.update(program=e.value or ""), content.refresh())).props("outlined dense").style("width:210px")
    content()
