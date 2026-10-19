"""Employees and monthly salaries (owner) – payslip PDF per employee + payroll summary (step 7)."""
from __future__ import annotations

from typing import Any

from nicegui import ui

import config
from core.context import AppContext
from export import service as ex
from services.common import ServiceError, money, month_key, month_label, today
from ui import components as C
from ui.components import STATUS_AR, STATUS_COLOR, card, col, data_table, guarded, ok, set_rows


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    f: dict[str, Any] = {"q": "", "month": month_key(today())}

    def refresh() -> None:
        rows = svc.employees.month_rows(f["month"], f["q"])
        for r in rows:
            r.update(id=r["employee_id"], base_label=money(r["base"]), bonus_label=money(r["bonuses"]),
                     ded_label=money(r["deductions"]), net_label=money(r["net"]),
                     status_label=STATUS_AR.get(r["status"], r["status"]),
                     color=STATUS_COLOR.get(r["status"], "grey"),
                     can_pay=r["status"] != "paid", can_reverse=r["status"] == "paid")
        set_rows(table, rows)
        tot.set_text(f"إجمالي صافي الرواتب لشهر {month_label(f['month'])}: {money(sum(r['net'] for r in rows))} ج.م — "
                     f"مدفوع: {money(sum(r['net'] for r in rows if r['status'] == 'paid'))} ج.م")

    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("الموظفون والرواتب", "الراتب الصافي = الأساسي + المكافآت − الخصومات")
        with ui.row().classes("gap-2"):
            ui.button("مكافأة / خصم", icon="tune", on_click=lambda: _quick_adjust_dialog(ctx, f["month"], refresh)).props("outline no-caps")
            ui.button("تصدير كل كشوف الرواتب للشهر", icon="picture_as_pdf", on_click=lambda: export_all()).props("outline no-caps")
            ui.button("موظف جديد", icon="add", on_click=lambda: _employee_dialog(ctx, None, refresh)).props("unelevated no-caps")

    with card():
        with ui.row().classes("w-full items-center gap-3"):
            C.search_box("ابحث باسم الموظف", lambda v: (f.update(q=v), refresh()), "300px")
            ui.select(C.month_options(18, 3), value=f["month"], label="الشهر",
                      on_change=lambda e: (f.update(month=e.value), refresh())).props("outlined dense").style("width:200px")
        table = data_table([col("name", "الموظف", sortable=True), col("job_title", "الوظيفة"), col("base_label", "الأساسي"),
                            col("bonus_label", "مكافآت"), col("ded_label", "خصومات"), col("net_label", "الصافي"),
                            col("status_label", "الحالة"), col("actions", "")], [], "id", no_data="لا يوجد موظفون")
        C.badge_cell(table, "status_label", "color", "status_label")
        table.add_slot("body-cell-bonus_label", '''
            <q-td :props="props" @click="props.row.can_pay && $parent.$emit('adjust', props.row)" :style="props.row.can_pay ? 'cursor:pointer' : ''">
                <span :class="props.row.bonuses > 0 ? 'text-positive font-bold' : ''">{{ props.value }}</span>
                <q-icon v-if="props.row.can_pay" name="edit" size="13px" class="q-ml-xs text-grey-5" />
            </q-td>
        ''')
        table.add_slot("body-cell-ded_label", '''
            <q-td :props="props" @click="props.row.can_pay && $parent.$emit('adjust', props.row)" :style="props.row.can_pay ? 'cursor:pointer' : ''">
                <span :class="props.row.deductions > 0 ? 'text-negative font-bold' : ''">{{ props.value }}</span>
                <q-icon v-if="props.row.can_pay" name="edit" size="13px" class="q-ml-xs text-grey-5" />
            </q-td>
        ''')
        table.add_slot("body-cell-net_label", '<q-td :props="props"><b style="color:var(--c-primary)">{{ props.value }}</b></q-td>')
        C.action_buttons(table, [("adjust", "tune", "تعديل المكافآت والخصومات", "primary", "props.row.can_pay"),
                                 ("pay", "payments", "صرف الراتب", "positive", "props.row.can_pay"),
                                 ("slip", "picture_as_pdf", "كشف الراتب PDF", "grey-8"),
                                 ("edit", "edit", "تعديل بيانات الموظف", "grey-7"),
                                 ("reverse", "block", "إلغاء الصرف", "negative", "props.row.can_reverse")])
        tot = ui.label("").classes("font-bold text-sm p-2 rounded-lg").style("background:var(--c-primary-light)")

        table.on("adjust", lambda e: _adjust_dialog(ctx, e.args, f["month"], refresh))
        table.on("pay", lambda e: _pay_dialog(ctx, e.args, f["month"], refresh))
        table.on("edit", lambda e: _employee_dialog(ctx, svc.ledger().employees.get(e.args["employee_id"]), refresh))
        table.on("reverse", lambda e: C.confirm_dialog(
            "إلغاء صرف راتب هذا الشهر؟", lambda pid=e.args["payment_id"]: (svc.employees.reverse(pid), ok("تم إلغاء الصرف"), refresh()),
            "إلغاء الصرف", danger=True))

        @guarded
        def slip(e) -> None:
            C.pdf_dialog(ex.export_payslip(ctx, e.args["employee_id"], f["month"]), "تم تصدير كشف الراتب")
            refresh()
        table.on("slip", slip)

    @guarded
    def export_all() -> None:
        summary, slips = ex.export_all_payslips(ctx, f["month"])
        C.pdf_dialog(summary, f"تم تصدير {len(slips)} كشف + ملخص الرواتب")
        refresh()
    refresh()


def _employee_dialog(ctx: AppContext, emp, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:440px;max-width:96vw"):
        ui.label("تعديل بيانات الموظف" if emp else "موظف جديد").classes("text-lg font-bold")
        name = ui.input("الاسم *", value=emp.name if emp else "").props("outlined dense").classes("w-full")
        title = ui.input("الوظيفة", value=(emp.job_title or "") if emp else "").props("outlined dense").classes("w-full")
        phone = ui.input("الموبايل", value=(emp.phone or "") if emp else "").props("outlined dense").classes("w-full")
        salary = C.num_input("الراتب الأساسي الشهري *", emp.base_salary if emp else None, "100%", "ج.م")
        status = ui.select({"active": "نشط", "inactive": "غير نشط"}, value=emp.status if emp else "active") \
            .props("outlined dense").classes("w-full") if emp else None
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                if emp:
                    if float(salary.value or 0) <= 0:
                        raise ServiceError("الراتب الأساسي يجب أن يكون أكبر من صفر.")
                    ctx.svc.employees.update(emp.employee_id, dict(name=name.value, job_title=title.value, phone=phone.value,
                                                                  base_salary=float(salary.value), status=status.value))
                else:
                    ctx.svc.employees.add(name.value or "", title.value or "", phone.value or "", float(salary.value or 0))
                d.close()
                ok("تم الحفظ")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _adjust_dialog(ctx: AppContext, row: dict, month: str, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:420px;max-width:96vw"):
        ui.label(f"مكافآت وخصومات — {row['name']}").classes("text-lg font-bold")
        ui.label(f"شهر {month_label(month)}  |  الأساسي {money(row['base'])} ج.م").classes("muted text-sm")
        bonus = C.num_input("المكافآت", row.get("bonuses", 0), "100%", "ج.م", min_=0)
        ded = C.num_input("الخصومات", row.get("deductions", 0), "100%", "ج.م", min_=0)
        net = ui.label("").classes("font-bold text-base p-2 rounded-lg w-full text-center") \
            .style("background:var(--c-primary-light);color:var(--c-primary)")

        def recalc() -> None:
            b = float(bonus.value or 0)
            d_val = float(ded.value or 0)
            net.set_text(f"الصافي بعد التعديل: {money(row['base'] + b - d_val)} ج.م")
        bonus.on_value_change(lambda e: recalc())
        ded.on_value_change(lambda e: recalc())
        recalc()
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.employees.set_adjustments(row["employee_id"], month, float(bonus.value or 0), float(ded.value or 0))
                d.close()
                ok("تم حفظ المكافآت والخصومات بنجاح")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _pay_dialog(ctx: AppContext, row: dict, month: str, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:440px;max-width:96vw"):
        ui.label(f"صرف راتب — {row['name']}").classes("text-lg font-bold")
        ui.label(f"شهر {month_label(month)}  |  الأساسي {money(row['base'])} ج.م").classes("muted text-sm")

        with ui.row().classes("w-full gap-2 items-center"):
            bonus = C.num_input("المكافآت", row.get("bonuses", 0), "48%", "ج.م", min_=0)
            ded = C.num_input("الخصومات", row.get("deductions", 0), "48%", "ج.م", min_=0)

        net_lbl = ui.label("").classes("font-bold text-base p-2 rounded-lg w-full text-center") \
            .style("background:var(--c-primary-light);color:var(--c-primary)")

        def recalc() -> None:
            b = float(bonus.value or 0)
            d_val = float(ded.value or 0)
            calc_net = round(row["base"] + b - d_val, 2)
            net_lbl.set_text(f"الصافي المستحق: {money(calc_net)} ج.م")

        bonus.on_value_change(lambda _: recalc())
        ded.on_value_change(lambda _: recalc())
        recalc()

        ui.label("طريقة الصرف:").classes("text-sm font-semibold")
        method = ui.toggle(config.PAYMENT_METHODS_AR, value="cash").props("no-caps unelevated toggle-color=primary")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                b = float(bonus.value or 0)
                d_val = float(ded.value or 0)
                ctx.svc.employees.pay(row["employee_id"], month, method.value, bonuses=b, deductions=d_val)
                d.close()
                ok("تم صرف الراتب بنجاح")
                on_saved()
            ui.button("تأكيد الصرف", on_click=save).props("unelevated no-caps")
    d.open()


def _quick_adjust_dialog(ctx: AppContext, month: str, on_saved) -> None:
    svc = ctx.svc
    rows = svc.employees.month_rows(month)
    eligible = [r for r in rows if r["status"] != "paid"]
    if not eligible:
        ok("جميع رواتب الموظفين لهذا الشهر تم صرفها بالفعل.")
        return

    emp_options = {r["employee_id"]: f"{r['name']} ({r['job_title'] or 'موظف'})" for r in eligible}
    first_id = eligible[0]["employee_id"]

    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:440px;max-width:96vw"):
        ui.label(f"تسجيل مكافأة أو خصم — شهر {month_label(month)}").classes("text-lg font-bold")

        sel_emp = ui.select(emp_options, value=first_id, label="اختر الموظف").props("outlined dense").classes("w-full")

        base_lbl = ui.label("").classes("text-sm muted")
        bonus = C.num_input("المكافآت", 0, "100%", "ج.م", min_=0)
        ded = C.num_input("الخصومات", 0, "100%", "ج.م", min_=0)
        net_lbl = ui.label("").classes("font-bold text-base p-2 rounded-lg w-full text-center") \
            .style("background:var(--c-primary-light);color:var(--c-primary)")

        def update_selected(eid: int) -> None:
            cur = next((r for r in eligible if r["employee_id"] == eid), None)
            if not cur:
                return
            base_lbl.set_text(f"الراتب الأساسي: {money(cur['base'])} ج.م")
            bonus.value = cur["bonuses"]
            ded.value = cur["deductions"]
            recalc()

        def recalc() -> None:
            cur = next((r for r in eligible if r["employee_id"] == sel_emp.value), None)
            if not cur:
                return
            b = float(bonus.value or 0)
            d_val = float(ded.value or 0)
            net_lbl.set_text(f"الصافي بعد التعديل: {money(cur['base'] + b - d_val)} ج.م")

        sel_emp.on_value_change(lambda e: update_selected(e.value))
        bonus.on_value_change(lambda _: recalc())
        ded.on_value_change(lambda _: recalc())
        update_selected(first_id)

        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.employees.set_adjustments(sel_emp.value, month, float(bonus.value or 0), float(ded.value or 0))
                d.close()
                ok("تم حفظ المكافأة / الخصم بنجاح")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()
