"""Cash receipts: issue, list, export PDF, cancel (build-plan step 3)."""
from __future__ import annotations

from typing import Any, Optional

from nicegui import ui

import config
from core.context import AppContext
from export import service as ex
from services.common import ServiceError, month_label, money, today
from ui import components as C
from ui.components import (DateField, STATUS_AR, STATUS_COLOR, card, col, data_table, guarded, ok, set_rows)

ITEM_AR = {"monthly": "اشتراك شهري", "contest": "تسجيل مسابقة", "other": "أخرى"}


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    state: dict[str, Any] = {"student": ctx.nav.pop("student_id", None), "enr": None}
    flt: dict[str, Any] = {"q": "", "method": "", "settlement": "", "status": ""}

    # ------------------------------------------------------------------ helpers
    def student_options() -> dict[int, str]:
        return {s.student_id: f"{s.name_ar} — {s.student_id}"
                for s in sorted(svc.ledger().students.values(), key=lambda s: s.name_ar)}

    def enrollment_options(sid: Optional[int]) -> dict[int, str]:
        if not sid:
            return {}
        led = svc.ledger()
        out = {}
        for e in led.student_enrollments(sid):
            if e.status not in ("active", "paused"):
                continue
            sm = led.summary(e.enrollment_id)
            label = f"{sm.group.cost_center if sm.group else 'مجموعة ' + str(e.group_id)} — متبقي {money(sm.remaining_fees)}"
            out[e.enrollment_id] = label
        return out

    def suggest() -> None:
        """Pre-fill amount / description / cost-center from the enrollment's next unpaid fee."""
        eid = enr.value
        if not eid:
            return
        sm = svc.ledger().summary(int(eid))
        if sm.group:
            cost.set_value(sm.group.cost_center)
        wanted = item.value
        line = next((l for l in sm.lines if l.remaining > 0.005 and (l.item == wanted or wanted == "other")), None)
        if line:
            amount.set_value(line.remaining)
            desc.set_value(f"{ITEM_AR.get(line.item, line.item)} — {month_label(line.month)}")
        elif wanted == "other":
            desc.set_value("")

    def on_student(e=None) -> None:
        opts = enrollment_options(student.value)
        enr.set_options(opts, value=next(iter(opts), None))
        suggest()

    # ----------------------------------------------------------------- layout
    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("الإيصالات", "إيصال استلام نقدية / مدفوعات إلكترونية وفيزا")
        ui.button("متابعة تحصيل الفيزا والبنك", icon="credit_score",
                  on_click=lambda: ui.navigate.to("/settlements")).props("outline no-caps")

    with ui.row().classes("w-full gap-4 items-start no-wrap").style("flex-wrap:wrap"):
        # --- form
        with card("إيصال استلام نقدية", style="width:430px;max-width:100%;flex:none"):
            serial_label = ui.label("").classes("text-sm muted")
            student = ui.select(student_options(), label="الطالب *", value=state["student"], with_input=True,
                                on_change=on_student).props("outlined dense use-input").classes("w-full")
            enr = ui.select({}, label="الاشتراك *", on_change=lambda e: suggest()).props("outlined dense").classes("w-full")
            item = ui.select(ITEM_AR, label="بند الدفع", value="monthly", on_change=lambda e: suggest()) \
                .props("outlined dense").classes("w-full")
            amount = C.num_input("المبلغ *", None, "100%", "ج.م", min_=0)
            ui.label("طريقة الدفع").classes("muted text-sm")
            method = ui.toggle(
                config.PAYMENT_METHODS_AR, value="cash",
                on_change=lambda e: visa_box.set_visibility(e.value == "visa"),
            ).props("no-caps unelevated toggle-color=primary")
            with ui.column().classes("w-full gap-1 p-2 rounded-lg").style("background:#FFF7ED;border:1px solid #FED7AA") as visa_box:
                ui.label("معاملات الفيزا تُسجّل افتراضيًا كـ «معلّق (قيد التحصيل)» حتى تأكيد دخولها حساب الأكاديمية.").classes("text-xs text-warning")
                bank_ref = ui.input("رقم مرجع الفيزا / Auth Code (اختياري)").props("outlined dense").classes("w-full")
            visa_box.set_visibility(False)
            cost = ui.select(svc.groups.list_programs(), label="مركز التكلفة", value=None, with_input=True,
                             new_value_mode="add-unique", clearable=True).props("outlined dense").classes("w-full")
            desc = ui.input("البيان").props("outlined dense").classes("w-full")
            rdate = DateField("التاريخ", today(), width="100%")
            ui.button("حفظ الإيصال", icon="save", on_click=lambda: save()).props("unelevated no-caps").classes("w-full")

        # --- list
        with card("آخر الإيصالات", style="flex:1 1 560px;min-width:0"):
            with ui.row().classes("w-full items-center gap-2"):
                C.search_box("بحث بالمسلسل أو اسم الطالب أو البيان", lambda v: (flt.update(q=v), refresh()), "280px")
                methods_flt = {"": "كل طرق الدفع"}
                methods_flt.update(config.PAYMENT_METHODS_AR)
                ui.select(methods_flt, value="", label="طريقة الدفع",
                          on_change=lambda e: (flt.update(method=e.value or ""), refresh())) \
                    .props("outlined dense").style("width:155px")
                settle_flt = {"": "كل التحصيل", "pending": "معلّق (قيد التحصيل)", "settled": "في الحساب"}
                ui.select(settle_flt, value="", label="حالة التحصيل",
                          on_change=lambda e: (flt.update(settlement=e.value or ""), refresh())) \
                    .props("outlined dense").style("width:165px")
            table = data_table([col("serial", "المسلسل", sortable=True), col("date", "التاريخ", sortable=True),
                                col("student", "الطالب"), col("amount_label", "المبلغ"), col("method", "الطريقة"),
                                col("settlement_label", "التحصيل"), col("description", "البيان"),
                                col("status_label", "الحالة"), col("actions", "")],
                               [], "serial", page_size=12, no_data="لا توجد إيصالات")
            C.badge_cell(table, "status_label", "color", "status_label")
            C.badge_cell(table, "settlement_label", "settlement_color", "settlement_label")
            C.action_buttons(table, [("pdf", "picture_as_pdf", "تصدير PDF", "primary"),
                                     ("cancel", "block", "إلغاء الإيصال", "negative", "props.row.can_cancel")])

            @guarded
            def pdf(e) -> None:
                C.pdf_dialog(ex.export_receipt(ctx, e.args["serial"], reprint=True), "تم تصدير الإيصال")
            table.on("pdf", pdf)
            table.on("cancel", lambda e: C.reason_dialog(
                f"إلغاء الإيصال رقم {e.args['serial']}",
                lambda reason, s=e.args["serial"]: (svc.receipts.reverse(s, reason), ok("تم إلغاء الإيصال"), refresh())))

    # ------------------------------------------------------------------ actions
    def refresh() -> None:
        rows = svc.receipts.rows(flt["q"], method=flt["method"], status=flt["status"], settlement_status=flt["settlement"])
        for r in rows:
            r["amount_label"] = money(r["amount"])
            r["status_label"] = STATUS_AR.get(r["status"], r["status"])
            r["color"] = STATUS_COLOR.get(r["status"], "grey")
            st = r.get("settlement_status", "settled")
            r["settlement_label"] = "معلّق" if st == "pending" else "في الحساب"
            r["settlement_color"] = "warning" if st == "pending" else "positive"
            r["can_cancel"] = r["status"] == "active"
        set_rows(table, rows)
        serial_label.set_text(f"رقم الإيصال القادم: {svc.receipts.next_serial()}")

    @guarded
    def save() -> None:
        if not student.value:
            raise ServiceError("اختر الطالب.")
        rec = svc.receipts.create(student_id=int(student.value), amount=float(amount.value or 0),
                                  method=method.value, enrollment_id=int(enr.value) if enr.value else None,
                                  cost_center=cost.value, description=desc.value, on_date=rdate.get(),
                                  bank_ref=(bank_ref.value or "").strip() or None)
        refresh()
        amount.set_value(None)
        desc.set_value("")
        bank_ref.set_value("")
        _success_dialog(ctx, rec)
        suggest()

    on_student()
    refresh()


def _success_dialog(ctx: AppContext, rec) -> None:
    with ui.dialog() as d, ui.card().classes("p-6 gap-3 items-center").style("min-width:380px"):
        ui.icon("check_circle", size="56px").classes("text-positive")
        ui.label(f"تم حفظ الإيصال رقم {rec.serial}").classes("text-lg font-bold")
        ui.label(f"{money(rec.amount)} ج.م").classes("muted")

        @guarded
        def export(open_it: bool) -> None:
            path = ex.export_receipt(ctx, rec.serial)
            if open_it:
                ex.open_path(path)
            else:
                C.pdf_dialog(path, "تم تصدير الإيصال")
        with ui.row().classes("gap-2 justify-center"):
            ui.button("تصدير PDF", icon="picture_as_pdf", on_click=lambda: export(False)).props("unelevated no-caps")
            ui.button("طباعة", icon="print", on_click=lambda: export(True)).props("outline no-caps")
            ui.button("إغلاق", on_click=d.close).props("flat no-caps")
    d.open()
