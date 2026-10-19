"""Daily journal: expenses, petty cash, cash handovers, non-cash collection, drawer (step 8)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

import config
from core.context import AppContext
from services.common import ServiceError, money, today
from ui import components as C
from ui.components import DateField, card, col, data_table, guarded, ok, set_rows


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    t_now = today()
    st: dict[str, Any] = {
        "mode": "day",
        "d_from": t_now.replace(day=1),
        "d_to": t_now,
    }

    @ui.refreshable
    def day_view() -> None:
        if st["mode"] == "day":
            try:
                d = day_field.get() or today()
            except ServiceError as e:
                ui.notify(str(e), type="warning", position="top")
                return
            data = svc.journal.day(d)
            active_date = d
            is_period = False
        else:
            d_lo, d_hi = st.get("d_from"), st.get("d_to")
            if not d_lo or not d_hi or d_lo > d_hi:
                ui.label("بداية الفترة بعد نهايتها.").classes("text-warning")
                return
            data = svc.journal.period(d_lo, d_hi)
            active_date = d_hi
            is_period = True

        day, total = data["day"], data["total"]

        with ui.row().classes("w-full gap-3"):
            C.stat_card("المقبوضات النقدية", money(day["cash_in"]) + " ج.م", "payments", "success")
            C.stat_card("المصروفات", money(day["expenses"]) + " ج.م", "shopping_cart", "warning")
            C.stat_card("العهدة النقدية", money(day["petty"]) + " ج.م", "account_balance_wallet")
            C.stat_card("التسليمات للمالك", money(day["handover"]) + " ج.م", "outbox")
        with ui.row().classes("w-full items-center gap-6 p-4 rounded-xl").style("background:var(--c-primary-light);border:1px solid #FED7AA"):
            with ui.column().classes("gap-0"):
                ui.label("صافي حركة الدرج خلال الفترة" if is_period else "رصيد الدرج اليوم").classes("muted text-sm")
                ui.label(f"{money(day['balance'])} ج.م").classes("text-2xl font-extrabold").style("color:var(--c-primary)")
            ui.label("= المقبوضات النقدية − المصروفات − العهدة − التسليمات").classes("muted text-sm")
            ui.space()
            with ui.column().classes("gap-0 items-end"):
                ui.label("الرصيد التراكمي في الدرج حتى نهاية الفترة" if is_period else "الرصيد التراكمي في الدرج حتى هذا اليوم").classes("muted text-sm")
                ui.label(f"{money(total['balance'])} ج.م").classes("text-xl font-bold")

        # ---- cash receipts (read-only, they come from Receipts)
        with card("المقبوضات النقدية (من الإيصالات)"):
            data_table([col("serial", "المسلسل"), col("date", "التاريخ"), col("student", "الطالب"),
                        col("amount_l", "المبلغ"), col("description", "البيان")],
                       [dict(r, amount_l=money(r["amount"])) for r in data["cash_receipts"]], "serial", page_size=8,
                       no_data="لا توجد مقبوضات نقدية")

        # ---- expenses
        with card("المصروفات"):
            with ui.row().classes("w-full items-center justify-between gap-2"):
                with ui.row().classes("items-center gap-2"):
                    ui.button("مصروف جديد", icon="add", on_click=lambda: _expense_dialog(ctx, active_date, day_view.refresh)).props("unelevated no-caps dense color=primary")
                    ui.button("إضافة تصنيف جديد", icon="category", on_click=lambda: _categories_dialog(ctx, day_view.refresh)).props("outline no-caps dense color=secondary")
            t = data_table([col("id", "#"), col("date", "التاريخ"), col("category", "التصنيف"), col("description", "البيان"),
                            col("recipient", "المستلم / المورد"), col("attachment", "رقم المرفق"),
                            col("amount_l", "المبلغ"), col("user", "المستخدم"), col("actions", "")],
                           [dict(r, amount_l=money(r["amount"])) for r in data["expenses"]], "id", page_size=8,
                           no_data="لا توجد مصروفات")
            C.action_buttons(t, [("reverse", "block", "إلغاء المصروف", "negative")])
            t.on("reverse", lambda e: C.confirm_dialog("إلغاء هذا المصروف؟", lambda xid=e.args["id"]: (
                svc.journal.reverse_expense(xid), ok("تم الإلغاء"), day_view.refresh()), "إلغاء المصروف", danger=True))

        # ---- petty cash / handovers / non-cash
        for title, kind, rows in (("العهدة النقدية", "petty_cash", data["petty"]),
                                  ("التسليمات النقدية للمالك", "handover", data["handovers"]),
                                  ("التحصيل غير النقدي (تسجيل يدوي)", "non_cash", data["noncash_entries"])):
            with card(title):
                ui.button("إضافة", icon="add", on_click=lambda k=kind, t=title: _cash_dialog(ctx, active_date, k, t, day_view.refresh)) \
                    .props("outline no-caps dense")
                t = data_table([col("id", "#"), col("date", "التاريخ"), col("amount_l", "المبلغ"),
                                col("receipt_no", "رقم الإيصال"), col("user", "المستخدم"),
                                col("actions", "")], [dict(r, amount_l=money(r["amount"])) for r in rows], "id", page_size=6,
                               no_data="لا توجد حركات")
                C.action_buttons(t, [("reverse", "block", "إلغاء الحركة", "negative")])
                t.on("reverse", lambda e: C.confirm_dialog("إلغاء هذه الحركة؟", lambda cid=e.args["id"]: (
                    svc.journal.reverse_cashflow(cid), ok("تم الإلغاء"), day_view.refresh()), "إلغاء الحركة", danger=True))
        with card("التحصيل غير النقدي (من الإيصالات: فيزا / إنستا باي / فودافون كاش / أخرى)"):
            data_table([col("serial", "المسلسل"), col("date", "التاريخ"), col("student", "الطالب"),
                        col("method", "الطريقة"), col("amount_l", "المبلغ")],
                       [dict(r, amount_l=money(r["amount"])) for r in data["noncash_receipts"]], "serial", page_size=8,
                       no_data="لا يوجد تحصيل غير نقدي")

    def shift(days: int) -> None:
        try:
            day_field.set((day_field.get() or today()) + timedelta(days=days))
        except ServiceError:
            day_field.set(today())

    C.section_title("اليومية", "حركة الدرج النقدي والمصروفات ليوم محدد أو فترة مخصصة بالأيام")
    with card():
        with ui.row().classes("w-full items-center gap-3").style("flex-wrap:wrap"):
            def on_mode_change(e) -> None:
                st["mode"] = e.value
                single_box.set_visibility(e.value == "day")
                period_box.set_visibility(e.value == "period")
                day_view.refresh()

            ui.toggle(
                {"day": "يوم محدد", "period": "فترة مخصصة بالأيام"},
                value="day",
                on_change=on_mode_change,
            ).props("no-caps unelevated toggle-color=primary")

            with ui.row().classes("items-center gap-2") as single_box:
                ui.button(icon="chevron_right", on_click=lambda: shift(-1)).props("flat round dense").tooltip("اليوم السابق")
                day_field = DateField("اليوم", today(), on_change=lambda: day_view.refresh())
                ui.button(icon="chevron_left", on_click=lambda: shift(1)).props("flat round dense").tooltip("اليوم التالي")
                ui.button("اليوم", on_click=lambda: day_field.set(today())).props("flat no-caps")

            with ui.row().classes("items-center gap-2") as period_box:
                def on_d_from() -> None:
                    try:
                        st["d_from"] = df_from.get() or t_now
                    except ServiceError:
                        return
                    day_view.refresh()

                def on_d_to() -> None:
                    try:
                        st["d_to"] = df_to.get() or t_now
                    except ServiceError:
                        return
                    day_view.refresh()

                df_from = DateField("من تاريخ", st["d_from"], width="160px", on_change=on_d_from)
                df_to = DateField("إلى تاريخ", st["d_to"], width="160px", on_change=on_d_to)

                def set_preset(lo_d: date, hi_d: date) -> None:
                    st["d_from"], st["d_to"] = lo_d, hi_d
                    df_from.set(lo_d)
                    df_to.set(hi_d)
                    day_view.refresh()

                ui.button("اليوم", on_click=lambda: set_preset(t_now, t_now)).props("outline dense no-caps color=secondary")
                ui.button("آخر 7 أيام", on_click=lambda: set_preset(t_now - timedelta(days=6), t_now)).props("outline dense no-caps color=secondary")
                ui.button("هذا الشهر", on_click=lambda: set_preset(t_now.replace(day=1), t_now)).props("outline dense no-caps color=secondary")
                ui.button("آخر 30 يومًا", on_click=lambda: set_preset(t_now - timedelta(days=29), t_now)).props("outline dense no-caps color=secondary")
            period_box.set_visibility(False)

    day_view()


def _categories_dialog(ctx: AppContext, on_changed=None) -> None:
    from core.audit import Action
    svc = ctx.svc
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:520px;max-width:96vw"):
        ui.label("تصنيفات المصروفات (إضافة / إدارة)").classes("text-lg font-bold")
        with ui.row().classes("w-full items-center gap-2"):
            new_c = ui.input("اسم التصنيف الجديد").props("outlined dense").classes("flex-1")

            @guarded
            def add_c() -> None:
                val = (new_c.value or "").strip()
                svc.journal.add_category(val)
                if hasattr(ctx, "audit") and ctx.audit:
                    ctx.audit.log(Action.CREATE, "ExpenseCategories", val, after={"category": val})
                new_c.set_value("")
                cats = svc.journal.list_categories()
                set_rows(ct, [{"name": c} for c in cats])
                ok(f"تمت إضافة التصنيف «{val}»")
                if on_changed:
                    on_changed()

            new_c.on("keydown.enter", add_c)
            ui.button("إضافة تصنيف", icon="add_circle", on_click=add_c).props("unelevated no-caps dense color=primary")

        cats = svc.journal.list_categories()
        ct = data_table(
            [col("name", "اسم التصنيف"), col("actions", "")],
            [{"name": c} for c in cats], "name", page_size=8, no_data="لا توجد تصنيفات مسجلة",
        )
        C.action_buttons(ct, [("del_c", "delete", "حذف التصنيف", "negative")])

        @guarded
        def del_c(e) -> None:
            cname = e.args["name"]
            svc.journal.delete_category(cname)
            if hasattr(ctx, "audit") and ctx.audit:
                ctx.audit.log(Action.UPDATE, "ExpenseCategories", cname, before={"category": cname}, after={"deleted": True})
            cats = svc.journal.list_categories()
            set_rows(ct, [{"name": c} for c in cats])
            ok(f"تم حذف التصنيف «{cname}»")
            if on_changed:
                on_changed()

        ct.on("del_c", del_c)
        with ui.row().classes("justify-end w-full"):
            ui.button("إغلاق", on_click=d.close).props("flat no-caps")
    d.open()


def _expense_dialog(ctx: AppContext, d: date, on_saved) -> None:
    categories = ctx.svc.journal.list_categories()
    default_val = categories[-1] if categories else "أخرى"
    with ui.dialog() as dlg, ui.card().classes("p-5 gap-3").style("width:460px;max-width:96vw"):
        ui.label("مصروف جديد").classes("text-lg font-bold")
        amount = C.num_input("المبلغ *", None, "100%", "ج.م")
        with ui.row().classes("w-full items-center gap-2"):
            cat = ui.select(categories, label="التصنيف", value=default_val,
                            new_value_mode="add-unique", with_input=True).props("outlined dense").classes("flex-1")

            def open_add_cat():
                def on_cat_added():
                    updated = ctx.svc.journal.list_categories()
                    cat.set_options(updated)
                    if len(updated) >= 2 and updated[-1] == "أخرى":
                        cat.set_value(updated[-2])
                    else:
                        cat.set_value(updated[-1])
                    if on_saved:
                        on_saved()
                _categories_dialog(ctx, on_cat_added)

            ui.button(icon="add", on_click=open_add_cat).props("outline dense").tooltip("إضافة تصنيف جديد")

        desc = ui.input("البيان *").props("outlined dense").classes("w-full")
        recipient = ui.input("المستلم / المورد (اختياري)").props("outlined dense").classes("w-full")
        attachment = ui.input("رقم المرفق / الفاتورة (اختياري)").props("outlined dense").classes("w-full")
        when = DateField("التاريخ", d, width="100%")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=dlg.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.journal.add_expense(float(amount.value or 0), desc.value or "", cat.value or "أخرى",
                                            when.get(), recipient=recipient.value, attachment=attachment.value)
                dlg.close()
                ok("تم تسجيل المصروف")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    dlg.open()



def _cash_dialog(ctx: AppContext, d: date, kind: str, title: str, on_saved) -> None:
    with ui.dialog() as dlg, ui.card().classes("p-5 gap-3").style("width:420px;max-width:96vw"):
        ui.label(title).classes("text-lg font-bold")
        amount = C.num_input("المبلغ *", None, "100%", "ج.م")
        no = ui.number("رقم الإيصال (اختياري)", min=0, format="%d").props("outlined dense").classes("w-full")
        when = DateField("التاريخ", d, width="100%")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=dlg.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.journal.add_cashflow(kind, float(amount.value or 0), int(no.value) if no.value else None, when.get())
                dlg.close()
                ok("تم التسجيل")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    dlg.open()
