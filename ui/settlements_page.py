"""Visa & Electronic Payment Settlement Follow-Up Page (/settlements)."""
from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

import config
from core.context import AppContext
from export import service as ex
from services.common import ServiceError, money, today
from ui import components as C
from ui.components import DateField, card, col, data_table, guarded, ok, set_rows

METHOD_FILTER_AR = {
    "visa": "فيزا فقط",
    "non_cash": "كل غير النقدي (فيزا / إنستا باي / فودافون كاش)",
    "": "كل طرق الدفع",
    "instapay": "إنستا باي",
    "vodafone_cash": "فودافون كاش",
    "other": "أخرى",
}

SETTLEMENT_FILTER_AR = {
    "": "كل الحالات",
    "pending": "معلّق (قيد التحصيل)",
    "settled": "في حساب الأكاديمية",
}

SETTLEMENT_COLOR = {
    "settled": "positive",
    "pending": "warning",
}


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    flt: dict[str, Any] = {"q": "", "method": "visa", "settlement": "", "d_from": None, "d_to": None}

    def filtered_rows() -> list[dict[str, Any]]:
        method_arg = flt["method"] if flt["method"] not in ("", "non_cash") else ""
        rows = svc.receipts.rows(
            query=flt["q"],
            method=method_arg,
            status="active",
            settlement_status=flt["settlement"],
            date_from=d_from.get(),
            date_to=d_to.get(),
        )
        if flt["method"] == "non_cash":
            rows = [r for r in rows if r["method_code"] != "cash"]
        for r in rows:
            st = r["settlement_status"]
            r["amount_label"] = money(r["amount"]) + " ج.م"
            r["settlement_label"] = config.SETTLEMENT_STATUS_AR.get(st, st)
            r["settlement_color"] = SETTLEMENT_COLOR.get(st, "grey")
            r["bank_ref_label"] = r.get("bank_ref") or "—"
            if st == "settled" and r.get("settled_at"):
                by = f" ({r['settled_by']})" if r.get("settled_by") else ""
                r["settled_info"] = f"{r['settled_at']}{by}"
            else:
                r["settled_info"] = "—"
            r["can_settle"] = st == "pending"
            r["can_unsettle"] = st == "settled"
        return rows

    @ui.refreshable
    def stats_bar() -> None:
        method_scope = flt["method"] if flt["method"] not in ("", "non_cash") else "visa"
        sm = svc.receipts.settlement_summary(method=method_scope)
        with ui.row().classes("w-full gap-3"):
            C.stat_card("معلّق (قيد التحصيل)", f"{money(sm['pending_amount'])} ج.م", "pending_actions", "warning")
            C.stat_card("في حساب الأكاديمية", f"{money(sm['settled_amount'])} ج.م", "account_balance", "success")
            C.stat_card("إجمالي المعاملات", f"{money(sm['total_amount'])} ج.م", "credit_card", "primary")
            C.stat_card("عمليات بانتظار التأكيد", f"{sm['pending_count']} عملية", "Receipt_long", "accent")

    def refresh(init: bool = False) -> None:
        try:
            rows = filtered_rows()
        except ServiceError as e:
            ui.notify(str(e), type="warning", position="top")
            return
        set_rows(table, rows)
        if not init:
            stats_bar.refresh()

    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("متابعة الفيزا والبنك", "متابعة تحصيل مدفوعات الفيزا والتأكد من وصولها لحساب الأكاديمية البنكي")
        ui.button("تأكيد تحصيل المعلّق المعروض", icon="done_all", on_click=lambda: _bulk_settle_dialog()).props("unelevated no-caps")

    stats_bar()

    with card():
        with ui.row().classes("w-full items-center gap-3"):
            C.search_box("ابحث بالمسلسل أو الطالب أو المرجع البنكي", lambda v: (flt.update(q=v), refresh()), "300px")
            ui.select(METHOD_FILTER_AR, value="visa", label="طريقة الدفع",
                      on_change=lambda e: (flt.update(method=e.value or ""), refresh())) \
                .props("outlined dense").style("width:240px")
            ui.select(SETTLEMENT_FILTER_AR, value="", label="حالة التحصيل",
                      on_change=lambda e: (flt.update(settlement=e.value or ""), refresh())) \
                .props("outlined dense").style("width:210px")
            d_from = DateField("من تاريخ", None, on_change=refresh, width="155px", clearable=True)
            d_to = DateField("إلى تاريخ", None, on_change=refresh, width="155px", clearable=True)

        columns = [
            col("serial", "المسلسل", sortable=True),
            col("date", "تاريخ العملية", sortable=True),
            col("student", "الطالب", sortable=True),
            col("program", "البرنامج"),
            col("method", "الطريقة"),
            col("amount_label", "المبلغ"),
            col("bank_ref_label", "مرجع البنك / الـ POS"),
            col("settlement_label", "حالة الحساب"),
            col("settled_info", "تاريخ التأكيد"),
            col("actions", ""),
        ]
        table = data_table(columns, [], "serial", page_size=15, no_data="لا توجد معاملات مطابقة")
        C.badge_cell(table, "settlement_label", "settlement_color", "settlement_label")
        C.action_buttons(table, [
            ("settle", "check_circle", "تأكيد دخول حساب الأكاديمية", "positive", "props.row.can_settle"),
            ("unsettle", "undo", "إرجاع إلى معلّق (قيد التحصيل)", "warning", "props.row.can_unsettle"),
            ("pdf", "picture_as_pdf", "تصدير الإيصال PDF", "primary"),
        ])

        table.on("settle", lambda e: _settle_dialog(ctx, e.args, refresh))
        table.on("unsettle", lambda e: C.confirm_dialog(
            f"هل تريد إرجاع الإيصال رقم {e.args['serial']} إلى حالة «معلّق (قيد التحصيل)»؟",
            lambda s=e.args["serial"]: (svc.receipts.set_settlement(s, "pending"), ok("تم تحديث الحالة إلى معلّق"), refresh()),
            "إرجاع إلى معلّق",
        ))

        @guarded
        def export_pdf(e) -> None:
            C.pdf_dialog(ex.export_receipt(ctx, e.args["serial"], reprint=True), "تم تصدير الإيصال")

        table.on("pdf", export_pdf)

    def _bulk_settle_dialog() -> None:
        pending_rows = [r for r in table.rows if r.get("settlement_status") == "pending"]
        if not pending_rows:
            ui.notify("لا توجد عمليات معلّقة في القائمة الحالية.", type="info", position="top")
            return
        total_amt = sum(r["amount"] for r in pending_rows)
        with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:440px;max-width:96vw"):
            ui.label("تأكيد تحصيل المعاملات المعلّقة").classes("text-lg font-bold")
            ui.label(f"سيتم تأكيد وصول {len(pending_rows)} عملية بإجمالي {money(total_amt)} ج.م إلى حساب الأكاديمية.").classes("text-sm muted")
            ref = ui.input("مرجع التسوية البنكية / رقم الحافظة (اختياري)").props("outlined dense").classes("w-full")
            sdate = DateField("تاريخ دخول الحساب", today(), width="100%")
            with ui.row().classes("justify-end gap-2 w-full"):
                ui.button("إلغاء", on_click=d.close).props("flat no-caps")

                @guarded
                def go() -> None:
                    dt = sdate.get() or today()
                    for r in pending_rows:
                        svc.receipts.set_settlement(r["serial"], "settled", bank_ref=ref.value or r.get("bank_ref"), settled_at=dt)
                    d.close()
                    ok(f"تم تأكيد تحصيل {len(pending_rows)} عملية")
                    refresh()

                ui.button("تأكيد التحصيل", on_click=go).props("unelevated no-caps color=positive")
        d.open()

    refresh(init=True)


def _settle_dialog(ctx: AppContext, row: dict, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:430px;max-width:96vw"):
        ui.label(f"تأكيد تحصيل إيصال #{row['serial']}").classes("text-lg font-bold")
        ui.label(f"الطالب: {row['student']}  |  المبلغ: {row['amount_label']}").classes("text-sm muted")
        ref = ui.input("رقم المرجع البنكي / Auth Code (اختياري)", value=row.get("bank_ref") or "") \
            .props("outlined dense autofocus").classes("w-full")
        sdate = DateField("تاريخ دخول الحساب", today(), width="100%")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.receipts.set_settlement(
                    int(row["serial"]),
                    "settled",
                    bank_ref=(ref.value or "").strip() or None,
                    settled_at=sdate.get() or today(),
                )
                d.close()
                ok("تم تأكيد دخول المبلغ في حساب الأكاديمية")
                on_saved()

            ui.button("تأكيد التحصيل", on_click=save).props("unelevated no-caps color=positive")
    d.open()
