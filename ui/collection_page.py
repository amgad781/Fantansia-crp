"""Fee collection: month grid per student + overdue list with WhatsApp reminders (step 4)."""
from __future__ import annotations

from typing import Any

from nicegui import ui

from core.context import AppContext
from export import service as ex
from services.common import (ServiceError, money, month_key, month_label, shift_month, today, whatsapp_link)
from ui import components as C
from ui.components import card, col, data_table, guarded, set_rows

STATE_COLOR = {"paid": "positive", "partial": "warning", "unpaid": "negative", "none": "grey-4"}


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    f: dict[str, Any] = {"program": "", "group": "", "first": shift_month(month_key(today()), -2), "count": 4}

    def months() -> list[str]:
        return [shift_month(f["first"], i) for i in range(int(f["count"]))]

    def load() -> tuple[list[dict], list[dict], dict]:
        led = svc.ledger()
        ms = months()
        grid = led.collection_grid(ms, f["program"], f["group"] or None)
        overdue = led.overdue_list(f["program"], f["group"] or None)
        totals = dict(due=sum(r["due"] for r in grid), paid=sum(r["paid"] for r in grid))
        totals["rem"] = round(totals["due"] - totals["paid"], 2)
        rows = []
        for r in grid:
            row = dict(id=r["enrollment_id"], sid=r["student_id"], name=r["name"], program=r["program"],
                       total_rem=money(round(r["due"] - r["paid"], 2)))
            for i, m in enumerate(ms):
                c = r["cells"][m]
                row[f"m{i}"] = "—" if c["state"] == "none" else f"{money(c['paid'])} / {money(c['due'])}"
                row[f"c{i}"] = "negative" if c["overdue"] and c["state"] != "paid" else STATE_COLOR[c["state"]]
            rows.append(row)
        for o in overdue:
            o["months_label"] = "، ".join(month_label(m) for m in o["months"])
            o["amount_label"] = money(o["amount"])
        return rows, overdue, totals

    @ui.refreshable
    def content() -> None:
        rows, overdue, totals = load()
        ms = months()
        with ui.row().classes("w-full gap-3"):
            C.stat_card("إجمالي المستحق", money(totals["due"]) + " ج.م", "request_quote")
            C.stat_card("المحصّل", money(totals["paid"]) + " ج.م", "payments", "success")
            C.stat_card("المتبقي", money(totals["rem"]) + " ج.م", "pending_actions", "warning")
            C.stat_card("طلاب متأخرون", str(len(overdue)), "notification_important")
        with ui.tabs().props("align=right no-caps active-color=primary indicator-color=primary").classes("w-full") as tabs:
            t1 = ui.tab("الجدول الشهري")
            t2 = ui.tab(f"المتأخرات ({len(overdue)})")
        with ui.tab_panels(tabs, value=t1).classes("w-full bg-transparent"):
            with ui.tab_panel(t1).classes("p-0"):
                with card():
                    columns = [col("name", "الطالب", sortable=True), col("program", "البرنامج")] + \
                              [col(f"m{i}", month_label(m)) for i, m in enumerate(ms)] + [col("total_rem", "المتبقي")]
                    t = data_table(columns, rows, "id", no_data="لا توجد اشتراكات في هذه الفترة")
                    for i in range(len(ms)):
                        C.badge_cell(t, f"m{i}", f"c{i}", f"m{i}")
                    t.on("rowClick", lambda e: ui.navigate.to(f"/students/{e.args[1]['sid']}"))
            with ui.tab_panel(t2).classes("p-0"):
                with card():
                    t = data_table([col("name", "الطالب", sortable=True), col("program", "البرنامج"),
                                    col("months_label", "الأشهر المتأخرة"), col("amount_label", "المبلغ المتأخر"),
                                    col("actions", "")], overdue, "enrollment_id", no_data="لا توجد متأخرات 🎉")
                    C.action_buttons(t, [("remind", "chat", "تذكير واتساب", "teal", "props.row.mobile"),
                                         ("pay", "add_card", "إضافة دفعة", "positive"),
                                         ("open", "open_in_new", "فتح الملف", "primary")])

                    @guarded
                    def remind(e) -> None:
                        r = e.args
                        link = whatsapp_link(r["mobile"], f"السلام عليكم، نذكّركم بالمبلغ المتأخر لاشتراك {r['name']} "
                                                          f"في أكاديمية فانتازيا: {r['amount_label']} ج.م ({r['months_label']}). شكرًا لتعاونكم.")
                        if not link:
                            raise ServiceError("رقم ولي الأمر غير صالح للواتساب.")
                        ex.open_url(link)
                    t.on("remind", remind)
                    t.on("pay", lambda e: (ctx.nav.update(student_id=e.args["student_id"]), ui.navigate.to("/receipts")))
                    t.on("open", lambda e: ui.navigate.to(f"/students/{e.args['student_id']}"))

    C.section_title("التحصيل", "متابعة الرسوم المستحقة والمدفوعة والمتأخرات")
    with card():
        with ui.row().classes("w-full items-center gap-3"):
            progs = {"": "كل البرامج"}
            progs.update({g.cost_center: g.cost_center for g in svc.ledger().groups.values()})
            ui.select(progs, value="", label="البرنامج", on_change=lambda e: (f.update(program=e.value or ""), content.refresh())) \
                .props("outlined dense").style("width:200px")
            groups = {"": "كل المجموعات"}
            groups.update({g.group_id: svc.groups.label(g) for g in svc.ledger().groups.values()})
            ui.select(groups, value="", label="المجموعة", on_change=lambda e: (f.update(group=e.value or ""), content.refresh())) \
                .props("outlined dense").style("width:260px")
            ui.select(C.month_options(18, 6), value=f["first"], label="من شهر",
                      on_change=lambda e: (f.update(first=e.value), content.refresh())).props("outlined dense").style("width:180px")
            ui.select({3: "3 شهور", 4: "4 شهور", 6: "6 شهور", 12: "12 شهرًا"}, value=4, label="المدة",
                      on_change=lambda e: (f.update(count=e.value), content.refresh())).props("outlined dense").style("width:130px")
    content()
