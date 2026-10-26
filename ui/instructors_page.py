"""Instructors (owner): search, period, salary calculated to the moment of the search (step 6)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from nicegui import ui

import config
from core.context import AppContext
from export import service as ex
from services.common import ServiceError, money, today
from ui import components as C
from ui.components import DateField, STATUS_AR, card, col, data_table, guarded, ok, set_rows

PERIODS = {"month": "الشهر الحالي حتى اليوم", "prev": "الشهر السابق", "custom": "فترة مخصصة"}


def _period(kind: str, d_from: date | None, d_to: date | None) -> tuple[date, date]:
    t = today()
    if kind == "month":
        return t.replace(day=1), t
    if kind == "prev":
        last = t.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if not d_from or not d_to:
        raise ServiceError("حدد بداية ونهاية الفترة.")
    if d_to < d_from:
        raise ServiceError("نهاية الفترة قبل بدايتها.")
    return d_from, d_to


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    f: dict[str, Any] = {"q": "", "kind": "month", "group": ""}

    def current_period() -> tuple[date, date]:
        return _period(f["kind"], d_from.get(), d_to.get())

    # ------------------------------------------------------------------ table
    @ui.refreshable
    def milestones_banner() -> None:
        try:
            ms = svc.instructors.pending_4_lesson_milestones()
        except Exception:
            ms = []
        if not ms:
            return
        with ui.column().classes("w-full gap-2 p-3 rounded-xl mb-3").style("background:#FFF7ED;border:1px solid #FED7AA"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("notification_important", color="warning", size="24px")
                    ui.label(f"تنبيهات استحقاق الراتب (إتمام 4 حصص) — يوجد {len(ms)} استحقاق جاهز للصرف").classes("font-bold text-sm")
                ui.badge("حان موعد صرف الراتب", color="warning")
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for m in ms:
                    with ui.row().classes("items-center justify-between gap-3 p-3 rounded-lg bg-white").style("border:1px solid #FED7AA;flex:1;min-width:320px"):
                        with ui.column().classes("gap-0"):
                            ui.label(f"المدرب: {m['instructor_name']} — مجموعة: {m['group_label']}").classes("font-bold text-xs")
                            ui.label(f"أتم 4 حصص ({m['period_from']} إلى {m['period_to']}) — المستحق: {money(m['amount'])} ج.م").classes("text-xs text-primary font-semibold")
                        ui.button("صرف الراتب الآن", icon="payments", on_click=lambda _, item=m: _pay_milestone_dialog(ctx, item, refresh)) \
                            .props("unelevated dense no-caps color=primary")

    def refresh() -> None:
        try:
            lo, hi = current_period()
        except ServiceError as e:
            ui.notify(str(e), type="warning", position="top")
            return
        gid = int(f["group"]) if f["group"] else None
        rows = svc.instructors.summary(lo, hi, f["q"], group_id=gid)
        for r in rows:
            r.update(id=r["instructor_id"], rate_label=money(r["rate"]),
                     groups_label=r.get("groups_info") or "—",
                     gross_label=money(r["gross"]),
                     bonus_label=money(r.get("bonuses", 0)),
                     ded_label=money(r.get("deductions", 0)),
                     paid_label=money(r["paid"]), due_label=money(r["net_due"]), hours_label=f"{r['hours']:g}",
                     can_pay=r["net_due"] > 0.005 or r["gross"] > 0.005)
        set_rows(table, rows)
        period_label.set_text(f"من {lo} إلى {hi}")
        tot.set_text(f"الإجمالي — ساعات: {sum(r['hours'] for r in rows):g}  |  الحصص: "
                     f"{money(sum(r['gross'] for r in rows))}  |  مكافآت: {money(sum(r.get('bonuses', 0) for r in rows))}  |  "
                     f"خصومات: {money(sum(r.get('deductions', 0) for r in rows))}  |  المدفوع: {money(sum(r['paid'] for r in rows))}  |  "
                     f"الصافي المستحق: {money(sum(r['net_due'] for r in rows))} ج.م")
        milestones_banner.refresh()

    # ----------------------------------------------------------------- header
    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("المدرّبون", "الراتب المحسوب = أجر الحصص المنفذة + المكافآت − الخصومات − المدفوع")
        with ui.row().classes("gap-2"):
            ui.button("طباعة إيصال / كشف مخصص", icon="print",
                      on_click=lambda: _custom_print_dialog(ctx, None, int(f["group"]) if f["group"] else None, current_period())) \
                .props("outline no-caps color=primary")
            ui.button("تصدير كشوف الجميع PDF", icon="picture_as_pdf", on_click=lambda: export_all()).props("outline no-caps")
            ui.button("مدرب جديد", icon="add", on_click=lambda: _add_dialog(ctx, refresh)).props("unelevated no-caps")

    milestones_banner()

    with card():
        with ui.row().classes("w-full items-center gap-3"):
            C.search_box("ابحث باسم المدرب", lambda v: (f.update(q=v), refresh()), "260px")
            grp_opts: dict[Any, str] = {"": "كل المجموعات"}
            grp_opts.update({g.group_id: svc.groups.label(g) for g in svc.ledger().groups.values()})
            ui.select(grp_opts, value="", label="المجموعة",
                      on_change=lambda e: (f.update(group=e.value or ""), refresh())) \
                .props("outlined dense").style("width:230px")
            ui.select(PERIODS, value="month", label="الفترة",
                      on_change=lambda e: (f.update(kind=e.value), custom.set_visibility(e.value == "custom"), refresh())) \
                .props("outlined dense").style("width:210px")
            with ui.row().classes("gap-2") as custom:
                d_from = DateField("من", today().replace(day=1), on_change=lambda: refresh())
                d_to = DateField("إلى", today(), on_change=lambda: refresh())
            custom.set_visibility(False)
            ui.space()
            period_label = ui.label("").classes("muted text-sm")
        table = data_table([col("id", "#", sortable=True), col("name", "المدرب", sortable=True),
                            col("rate_label", "السعر الأساسي"), col("groups_label", "المجموعات وأسعارها"),
                            col("sessions", "الحصص"),
                            col("hours_label", "الساعات"), col("gross_label", "أجر الحصص"),
                            col("bonus_label", "مكافآت"), col("ded_label", "خصومات"),
                            col("paid_label", "المدفوع"), col("due_label", "الصافي المستحق"), col("actions", "")],
                           [], "id", no_data="لا يوجد مدربون مطابقون")
        table.add_slot("body-cell-due_label", '<q-td :props="props"><b style="color:var(--c-primary)">{{ props.value }}</b></q-td>')
        C.action_buttons(table, [("details", "visibility", "التفاصيل والحصص", "primary"),
                                 ("adjust", "exposure", "مكافآت / خصومات المدرب", "warning"),
                                 ("pay", "payments", "تسجيل دفعة", "positive", "props.row.can_pay"),
                                 ("cycles", "tune", "نظام صرف المجموعات (شهري / كل 4 حصص)", "secondary"),
                                 ("custom_pdf", "settings", "طباعة مخصصة (مجموعة / أشهر / حصص / بند)", "grey-8"),
                                 ("pdf", "picture_as_pdf", "تصدير كشف PDF", "grey-8")])
        tot = ui.label("").classes("font-bold text-sm p-2 rounded-lg").style("background:var(--c-primary-light)")
        table.on("rowClick", lambda e: _details(ctx, e.args[1]["instructor_id"], current_period(), refresh))
        table.on("details", lambda e: _details(ctx, e.args["instructor_id"], current_period(), refresh))
        table.on("adjust", lambda e: _adjust_dialog(ctx, e.args, current_period(), refresh))
        table.on("pay", lambda e: _pay_dialog(ctx, e.args, current_period(), refresh))
        table.on("cycles", lambda e: _group_pay_cycle_dialog(ctx, e.args["instructor_id"], refresh))
        table.on("custom_pdf", lambda e: _custom_print_dialog(
            ctx, e.args["instructor_id"], int(f["group"]) if f["group"] else None, current_period()))

        @guarded
        def pdf(e) -> None:
            lo, hi = current_period()
            gid = int(f["group"]) if f["group"] else None
            C.pdf_dialog(ex.export_instructor_statement(ctx, e.args["instructor_id"], lo, hi, group_id=gid),
                         "تم تصدير كشف المدرب")
        table.on("pdf", pdf)

    @guarded
    def export_all() -> None:
        lo, hi = current_period()
        gid = int(f["group"]) if f["group"] else None
        rows = [r for r in svc.instructors.summary(lo, hi, group_id=gid) if r["sessions"] > 0]
        if not rows:
            raise ServiceError("لا توجد حصص منفذة في هذه الفترة.")
        paths = [ex.export_instructor_statement(ctx, r["instructor_id"], lo, hi, group_id=gid) for r in rows]
        C.pdf_dialog(paths[0], f"تم تصدير {len(paths)} كشف (المجلد: instructors)")
    refresh()


# ============================================================================ dialogs
def _group_pay_cycle_dialog(ctx: AppContext, instructor_id: int, on_saved=None) -> None:
    svc = ctx.svc
    ins = svc.repo.get(Sheet.INSTRUCTORS, instructor_id=instructor_id)
    if not ins:
        return
    groups = svc.instructors.groups_for_instructor(instructor_id)
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:580px;max-width:96vw"):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("tune", color="primary", size="24px")
                ui.label(f"نظام صرف المجموعات — {ins.name}").classes("text-lg font-bold")
            ui.badge(f"{len(groups)} مجموعة", color="secondary")
        ui.label("حدد نظام الصرف لكل مجموعة للمدرب: إما شهريًا أو كل 4 حصص منفذة.").classes("text-xs muted")

        if not groups:
            ui.label("لا توجد مجموعات مسندة لهذا المدرب حاليًا.").classes("text-sm text-warning p-3")
            cycle_selectors = {}
        else:
            cycle_selectors = {}
            with ui.column().classes("w-full gap-2 max-h-96 overflow-auto"):
                for g in groups:
                    with ui.row().classes("w-full items-center justify-between p-3 rounded-lg border").style("background:#F8FAFC"):
                        with ui.column().classes("gap-0"):
                            ui.label(g["label"]).classes("font-bold text-sm")
                            rate_text = f"{money(g['rate'])} ج.م/س" if g["rate"] else "سعر غير محدد"
                            ui.label(f"{rate_text}  |  الحصص المنفذة: {g['held_sessions_count']}").classes("text-xs muted")
                        sel = ui.toggle(
                            {"monthly": "شهري", "every_4_lessons": "كل 4 حصص"},
                            value=g["pay_cycle"]
                        ).props("dense no-caps unelevated toggle-color=primary")
                        cycle_selectors[g["group_id"]] = sel

        with ui.row().classes("justify-end gap-2 w-full pt-2"):
            ui.button("إغلاق", on_click=d.close).props("flat no-caps")
            if groups:
                @guarded
                def save_cycles() -> None:
                    for gid, selector in cycle_selectors.items():
                        svc.instructors.set_group_pay_cycle(gid, selector.value)
                    d.close()
                    ok("تم تحديث نظام الصرف للمجموعات بنجاح")
                    if on_saved:
                        on_saved()
                ui.button("حفظ التغييرات", icon="check", on_click=save_cycles).props("unelevated no-caps color=primary")
    d.open()


def _pay_milestone_dialog(ctx: AppContext, m: dict, on_saved=None) -> None:
    svc = ctx.svc
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:560px;max-width:96vw"):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("payments", color="positive", size="26px")
                ui.label(f"صرف راتب إتمام 4 حصص — {m['instructor_name']}").classes("text-lg font-bold")
            ui.badge("استحقاق 4 حصص", color="warning")

        ui.label(f"المجموعة: {m['group_label']}  |  الفترة: من {m['period_from']} إلى {m['period_to']}").classes("text-xs muted")

        with ui.column().classes("w-full gap-1 p-3 rounded-lg border").style("background:#F8FAFC"):
            ui.label("الحصص الـ 4 المنفذة المشمولة في هذا الصرف:").classes("text-xs font-bold")
            for s in m.get("sessions_summary", []):
                t_str = f"{s['start_time']:%H:%M}–{s['end_time']:%H:%M}" if s.get("start_time") and s.get("end_time") else ""
                with ui.row().classes("w-full items-center justify-between text-xs py-1 border-b last:border-none"):
                    ui.label(f"حصة بتاريخ {s['date']} {t_str}")
                    ui.label(f"{s['hours']:g} س × {money(s['rate'])} = {money(s['amount'])} ج.م").classes("font-semibold")

        with ui.row().classes("w-full items-center justify-between p-3 rounded-xl").style("background:var(--c-primary-light);border:1px solid #FED7AA"):
            ui.label(f"إجمالي الساعات: {m['total_hours']:g} ساعة").classes("text-sm font-semibold")
            ui.label(f"المبلغ الإجمالي المستحق: {money(m['amount'])} ج.م").classes("text-base font-extrabold text-primary")

        method = ui.toggle(config.PAYMENT_METHODS_AR, value="cash").props("no-caps unelevated toggle-color=primary")
        notes = ui.input("ملاحظات إضافية (اختياري)", value=f"صرف مستحقات 4 حصص لمجموعة {m['cost_center']}").props("outlined dense").classes("w-full")

        with ui.row().classes("justify-end gap-2 w-full pt-1"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def do_pay() -> None:
                pid = svc.instructors.record_payment(
                    m["instructor_id"],
                    m["period_from"],
                    m["period_to"],
                    float(m["amount"]),
                    method=method.value,
                    approved_by=ctx.session.username,
                    notes=notes.value or "",
                    group_id=m["group_id"],
                    session_ids=m["session_ids"],
                )
                d.close()
                ok(f"تم تسجيل صرف الراتب بنجاح (دفعة رقم #{pid})")
                if on_saved:
                    on_saved()
            ui.button("تأكيد وصرف الراتب", icon="check_circle", on_click=do_pay).props("unelevated no-caps color=positive")
    d.open()


def _add_dialog(ctx: AppContext, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:420px;max-width:96vw"):
        ui.label("مدرب جديد").classes("text-lg font-bold")
        name = ui.input("اسم المدرب *").props("outlined dense").classes("w-full")
        phone = ui.input("الموبايل").props("outlined dense").classes("w-full")
        rate = C.num_input("سعر الساعة *", None, "100%", "ج.م / ساعة")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.instructors.add(name.value or "", phone.value or "", float(rate.value or 0))
                d.close()
                ok("تمت إضافة المدرب")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _rate_dialog(ctx: AppContext, row: dict, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:420px;max-width:96vw"):
        ui.label(f"تعديل سعر الساعة — {row['name']}").classes("text-lg font-bold")
        ui.label("السعر الجديد يسري على الحصص الجديدة فقط؛ الحصص السابقة تحتفظ بسعرها.").classes("muted text-sm")
        rate = C.num_input("سعر الساعة الجديد", row["rate"], "100%", "ج.م / ساعة")
        eff = DateField("يسري من", today(), width="100%")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.instructors.change_rate(row["instructor_id"], float(rate.value or 0), eff.get())
                d.close()
                ok("تم تعديل السعر")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _adjust_dialog(ctx: AppContext, row: dict, period: tuple[date, date], on_saved) -> None:
    lo, hi = period
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:440px;max-width:96vw"):
        ui.label(f"مكافآت وخصومات — {row['name']}").classes("text-lg font-bold")
        ui.label(f"الفترة {lo} → {hi}  |  أجر الحصص: {money(row['gross'])} ج.م").classes("muted text-sm")
        bonus = C.num_input("المكافآت", row.get("bonuses", 0), "100%", "ج.م", min_=0)
        ded = C.num_input("الخصومات", row.get("deductions", 0), "100%", "ج.م", min_=0)
        notes = ui.input("سبب المكافأة / الخصم (ملاحظات)", value=row.get("notes", "")).props("outlined dense").classes("w-full")
        net_lbl = ui.label("").classes("font-bold text-base").style("color:var(--c-primary)")

        def recalc() -> None:
            b = float(bonus.value or 0)
            dd = float(ded.value or 0)
            net_val = round(row["gross"] + b - dd - row["paid"], 2)
            net_lbl.set_text(f"الصافي المستحق بعد التعديل: {money(net_val)} ج.م")

        bonus.on_value_change(lambda _: recalc())
        ded.on_value_change(lambda _: recalc())
        recalc()
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.instructors.set_adjustments(
                    row["instructor_id"], lo, hi,
                    float(bonus.value or 0), float(ded.value or 0), notes.value or "",
                )
                d.close()
                ok("تم حفظ المكافآت والخصومات")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _pay_dialog(ctx: AppContext, row: dict, period: tuple[date, date], on_saved) -> None:
    lo, hi = period
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:480px;max-width:96vw"):
        ui.label(f"تسجيل دفعة — {row['name']}").classes("text-lg font-bold")
        ui.label(f"الفترة {lo} → {hi}").classes("muted text-sm")
        with ui.row().classes("gap-6"):
            for label, val in (("أجر الحصص", row["gross"]), ("المدفوع سابقًا", row["paid"])):
                with ui.column().classes("gap-0"):
                    ui.label(label).classes("muted text-xs")
                    ui.label(f"{money(val)} ج.م").classes("font-bold")
        with ui.row().classes("w-full gap-3 no-wrap"):
            bonus = C.num_input("المكافآت", row.get("bonuses", 0), "50%", "ج.م", min_=0)
            ded = C.num_input("الخصومات", row.get("deductions", 0), "50%", "ج.م", min_=0)
        notes = ui.input("ملاحظات الدفعة / المكافأة / الخصم", value=row.get("notes", "")).props("outlined dense").classes("w-full")
        due_lbl = ui.label("").classes("text-sm font-bold").style("color:var(--c-primary)")
        amount = C.num_input("المبلغ المدفوع", row["net_due"], "100%", "ج.م")

        def recalc_due() -> None:
            b = float(bonus.value or 0)
            dd = float(ded.value or 0)
            new_due = round(max(0.0, row["gross"] + b - dd - row["paid"]), 2)
            due_lbl.set_text(f"الصافي المستحق: {money(new_due)} ج.م")
            amount.set_value(new_due)

        bonus.on_value_change(lambda _: recalc_due())
        ded.on_value_change(lambda _: recalc_due())
        due_lbl.set_text(f"الصافي المستحق: {money(row['net_due'])} ج.م")

        method = ui.toggle(config.PAYMENT_METHODS_AR, value="cash").props("no-caps unelevated toggle-color=primary")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.instructors.record_payment(
                    row["instructor_id"], lo, hi, float(amount.value or 0), method.value,
                    ctx.session.username,
                    bonuses=float(bonus.value or 0),
                    deductions=float(ded.value or 0),
                    notes=notes.value or "",
                )
                d.close()
                ok("تم تسجيل الدفعة")
                on_saved()
            ui.button("تأكيد الدفع", on_click=save).props("unelevated no-caps")
    d.open()


def _custom_print_dialog(ctx: AppContext, instructor_id: int | None = None,
                         default_group_id: int | None = None,
                         default_period: tuple[date, date] | None = None) -> None:
    svc = ctx.svc
    led = svc.ledger()
    ins_opts = {i.instructor_id: i.name for i in led.instructors.values()}
    if not ins_opts:
        ui.notify("لا يوجد مدربون بعد.", type="warning", position="top")
        return
    init_iid = instructor_id if instructor_id in ins_opts else next(iter(ins_opts))
    lo_def, hi_def = default_period or (today().replace(day=1), today())
    from services.common import month_key
    cur_m = month_key(lo_def)

    session_checks: dict[int, ui.checkbox] = {}

    def group_opts_for(iid: int | None) -> dict[int, str]:
        if not iid:
            return {}
        used_gids = {s.group_id for s in led.sessions.values() if s.instructor_id == iid}
        out = {}
        for g in led.groups.values():
            if g.instructor_id == iid or g.group_id in used_gids:
                rate_s = f" ({g.instructor_hourly_rate:g} ج.م/س)" if getattr(g, "instructor_hourly_rate", None) else ""
                out[g.group_id] = f"{svc.groups.label(g)}{rate_s}"
        return out or {g.group_id: svc.groups.label(g) for g in led.groups.values()}

    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:650px;max-width:96vw"):
        ui.label("تخصيص وطباعة إيصال / كشف حساب مدرب").classes("text-lg font-bold")
        ui.label("اختر المدرب والمجموعة والأشهر أو الحصص المحددة أو أضف بندًا مخصصًا للطباعة").classes("muted text-xs")

        doc_title = ui.toggle(
            {"كشف حساب المدرب": "كشف حساب مدرب", "إيصال صرف مستحقات مدرب": "إيصال استلام مستحقات"},
            value="كشف حساب المدرب",
        ).props("no-caps unelevated toggle-color=primary")

        with ui.row().classes("w-full gap-3 no-wrap"):
            ins_sel = ui.select(ins_opts, value=init_iid, label="المدرب *") \
                .props("outlined dense").classes("flex-1")
            init_g_opts = group_opts_for(init_iid)
            init_g_val = [default_group_id] if (default_group_id and default_group_id in init_g_opts) else []
            grp_sel = ui.select(init_g_opts, value=init_g_val, label="تخصيص مجموعة (اتركه فارغًا لكل المجموعات)",
                                multiple=True, clearable=True).props("outlined dense use-chips").classes("flex-1")

        mode_toggle = ui.toggle(
            {"months": "تحديد أشهر معينة", "dates": "تحديد فترة بالتاريخ (من / إلى)"},
            value="months",
        ).props("no-caps unelevated toggle-color=primary")

        with ui.row().classes("w-full gap-3") as months_box:
            months_sel = ui.select(C.month_options(18, 2), value=[cur_m], label="الأشهر المختارة *",
                                   multiple=True).props("outlined dense use-chips").classes("w-full")

        with ui.row().classes("w-full gap-3") as dates_box:
            df_in = DateField("من تاريخ", lo_def, width="220px")
            dt_in = DateField("إلى تاريخ", hi_def, width="220px")
        dates_box.set_visibility(False)

        # --- Specific sessions selection
        with ui.column().classes("w-full gap-1 p-3 rounded-lg").style("background:#F8FAFC;border:1px solid #E2E8F0"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("الحصص المشمولة في الإيصال / الكشف (يمكنك تحديد حصص بعينها):").classes("text-xs font-bold")
                with ui.row().classes("gap-1"):
                    ui.button("تحديد الكل", on_click=lambda: _set_all_sessions(True)).props("flat dense no-caps size=sm")
                    ui.button("إلغاء الكل", on_click=lambda: _set_all_sessions(False)).props("flat dense no-caps size=sm")
            sessions_container = ui.column().classes("w-full gap-1 max-h-44 overflow-auto")
            summary_lbl = ui.label("").classes("text-xs font-bold").style("color:var(--c-primary)")

        # --- Specific custom item / note
        with ui.expansion("إضافة بند مخصص / مكافأة / ملاحظات على الإيصال (اختياري)", icon="post_add") \
                .classes("w-full border rounded-lg"):
            with ui.column().classes("w-full gap-2 p-2"):
                with ui.row().classes("w-full gap-3 no-wrap"):
                    custom_lbl = ui.input("بيان البند المخصص (مثال: تدريب مسابقة / ورشة عمل / مكافأة)") \
                        .props("outlined dense").classes("flex-1")
                    custom_amt = C.num_input("مبلغ البند (ج.م)", 0, "180px", "ج.م", min_=0)
                notes_in = ui.input("ملاحظات إضافية تُطبع في الكشف / الإيصال").props("outlined dense").classes("w-full")

        def _current_matching_sessions() -> list[dict[str, Any]]:
            iid = ins_sel.value
            if not iid:
                return []
            gids = [int(x) for x in (grp_sel.value or [])] if grp_sel.value else None
            if mode_toggle.value == "months":
                ms = list(months_sel.value or [])
                if not ms:
                    return []
                return svc.instructors.sessions_for(int(iid), None, None, group_ids=gids, months=ms)
            try:
                lo, hi = df_in.get(), dt_in.get()
            except ServiceError:
                return []
            if not lo or not hi or hi < lo:
                return []
            return svc.instructors.sessions_for(int(iid), lo, hi, group_ids=gids)

        def _update_summary() -> None:
            lines = _current_matching_sessions()
            chosen = [l for l in lines if session_checks.get(l["session_id"]) and session_checks[l["session_id"]].value]
            hrs = sum(l["hours"] for l in chosen)
            amt = sum(l["amount"] for l in chosen) + float(custom_amt.value or 0)
            summary_lbl.set_text(f"المختار للطباعة: {len(chosen)} حصة  |  {hrs:g} ساعة  |  الإجمالي: {money(amt)} ج.م")

        def _rebuild_sessions() -> None:
            session_checks.clear()
            sessions_container.clear()
            lines = _current_matching_sessions()
            with sessions_container:
                if not lines:
                    ui.label("لا توجد حصص منفذة تطابق هذا الاختيار (يمكنك طباعة بند مخصص أو تغيير الفترة/المجموعة).") \
                        .classes("text-xs muted py-2")
                else:
                    for l in lines:
                        t_str = f"{l['start']:%H:%M}–{l['end']:%H:%M}" if l["start"] and l["end"] else ""
                        lbl = f"{l['date']} ({t_str}) — {l['course_level'] or l['group']} — {l['hours']:g} س × {money(l['rate'])} = {money(l['amount'])} ج.م"
                        cb = ui.checkbox(lbl, value=True, on_change=lambda _: _update_summary()).props("dense").classes("text-xs")
                        session_checks[l["session_id"]] = cb
            _update_summary()

        def _set_all_sessions(val: bool) -> None:
            for cb in session_checks.values():
                cb.set_value(val)
            _update_summary()

        def _on_instructor_change(e) -> None:
            opts = group_opts_for(e.value)
            grp_sel.set_options(opts, value=[])
            _rebuild_sessions()

        def _on_mode_change(e) -> None:
            months_box.set_visibility(e.value == "months")
            dates_box.set_visibility(e.value == "dates")
            _rebuild_sessions()

        ins_sel.on_value_change(_on_instructor_change)
        grp_sel.on_value_change(lambda _: _rebuild_sessions())
        mode_toggle.on_value_change(_on_mode_change)
        months_sel.on_value_change(lambda _: _rebuild_sessions())
        df_in.input.on_value_change(lambda _: _rebuild_sessions())
        dt_in.input.on_value_change(lambda _: _rebuild_sessions())
        custom_amt.on_value_change(lambda _: _update_summary())

        _rebuild_sessions()

        @guarded
        def do_export(open_direct: bool) -> None:
            if not ins_sel.value:
                raise ServiceError("اختر المدرب.")
            gids = [int(x) for x in (grp_sel.value or [])] if grp_sel.value else None
            ms = list(months_sel.value or []) if mode_toggle.value == "months" else None
            if mode_toggle.value == "months" and not ms:
                raise ServiceError("اختر شهرًا واحدًا على الأقل.")
            lo = df_in.get() if mode_toggle.value == "dates" else None
            hi = dt_in.get() if mode_toggle.value == "dates" else None
            if mode_toggle.value == "dates" and (not lo or not hi or hi < lo):
                raise ServiceError("حدد فترة تاريخ صحيحة.")

            selected_sids = [sid for sid, cb in session_checks.items() if cb.value]
            path = ex.export_instructor_statement(
                ctx, int(ins_sel.value), lo, hi,
                group_ids=gids, months=ms, session_ids=selected_sids,
                custom_title=doc_title.value,
                custom_item_label=custom_lbl.value,
                custom_item_amount=float(custom_amt.value or 0),
                notes=notes_in.value,
            )
            d.close()
            if open_direct:
                ex.open_path(path)
            else:
                C.pdf_dialog(path, f"تم إنشاء {doc_title.value}")

        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")
            ui.button("تصدير PDF", icon="picture_as_pdf", on_click=lambda: do_export(False)).props("outline no-caps")
            ui.button("طباعة مباشرة", icon="print", on_click=lambda: do_export(True)).props("unelevated no-caps")
    d.open()


def _details(ctx: AppContext, instructor_id: int, period: tuple[date, date], on_changed) -> None:
    svc = ctx.svc
    lo, hi = period
    panel, content = C.side_panel()
    row = next(r for r in svc.instructors.summary(lo, hi) if r["instructor_id"] == instructor_id)
    with content:
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(row["name"]).classes("text-xl font-bold")
            ui.button(icon="close", on_click=panel.close).props("flat round dense")
        ui.label(f"الفترة {lo} → {min(hi, today())}  |  السعر الأساسي {money(row['rate'])} ج.م  |  المجموعات: {row.get('groups_info', '—')}") \
            .classes("muted text-sm")
        with ui.row().classes("gap-5 flex-wrap"):
            for label, val in (("الحصص", row["sessions"]), ("الساعات", f"{row['hours']:g}"),
                               ("أجر الحصص", f"{money(row['gross'])} ج.م"),
                               ("المكافآت", f"{money(row.get('bonuses', 0))} ج.م"),
                               ("الخصومات", f"{money(row.get('deductions', 0))} ج.م"),
                               ("المدفوع", f"{money(row['paid'])} ج.م"),
                               ("الصافي المستحق", f"{money(row['net_due'])} ج.م")):
                with ui.column().classes("gap-0"):
                    ui.label(label).classes("muted text-xs")
                    ui.label(str(val)).classes("font-bold")
        with ui.row().classes("gap-2 flex-wrap"):
            ui.button("تسجيل دفعة", icon="payments", on_click=lambda: (panel.close(), _pay_dialog(ctx, row, period, on_changed))) \
                .props("unelevated no-caps").set_enabled(row["net_due"] > 0.005 or row["gross"] > 0.005)
            ui.button("مكافآت / خصومات", icon="exposure",
                      on_click=lambda: (panel.close(), _adjust_dialog(ctx, row, period, on_changed))) \
                .props("outline no-caps color=warning")

            @guarded
            def pdf() -> None:
                C.pdf_dialog(ex.export_instructor_statement(ctx, instructor_id, lo, hi), "تم تصدير كشف المدرب")
            ui.button("تصدير كشف PDF", icon="picture_as_pdf", on_click=pdf).props("outline no-caps")
            ui.button("طباعة مخصصة...", icon="tune",
                      on_click=lambda: _custom_print_dialog(ctx, instructor_id, None, period)) \
                .props("outline no-caps color=secondary")
            ui.button("تعديل السعر", icon="edit", on_click=lambda: (panel.close(), _rate_dialog(ctx, row, on_changed))) \
                .props("flat no-caps")
            ui.button("نظام صرف المجموعات", icon="tune",
                      on_click=lambda: (panel.close(), _group_pay_cycle_dialog(ctx, instructor_id, on_changed))) \
                .props("outline no-caps color=accent")
        if row.get("has_milestone_4_lessons"):
            for ms in row.get("milestones_4_lessons", []):
                with ui.row().classes("w-full items-center justify-between p-3 rounded-lg").style("background:#FFF7ED;border:1px solid #FED7AA"):
                    with ui.column().classes("gap-0"):
                        ui.label(f"استحقاق صرف راتب 4 حصص — {ms['group_label']}").classes("font-bold text-xs")
                        ui.label(f"المستحق: {money(ms['amount'])} ج.م ({ms['period_from']} إلى {ms['period_to']})").classes("text-xs text-primary font-semibold")
                    ui.button("صرف الراتب الآن", icon="payments", on_click=lambda _, item=ms: (panel.close(), _pay_milestone_dialog(ctx, item, on_changed))) \
                        .props("unelevated dense no-caps color=primary")
        ui.separator()
        ui.label("الحصص المنفذة").classes("font-bold")
        lines = svc.instructors.sessions_for(instructor_id, lo, hi)
        rows = [dict(k=i, date=str(l["date"]), time=f"{l['start']:%H:%M}–{l['end']:%H:%M}" if l["start"] and l["end"] else "—",
                     group=l["course_level"] or l["group"], hours=f"{l['hours']:g}", amount=money(l["amount"]))
                for i, l in enumerate(lines)]
        data_table([col("date", "التاريخ"), col("time", "الوقت"), col("group", "المجموعة / المستوى"),
                    col("hours", "الساعات"), col("amount", "المبلغ")], rows, "k", page_size=8, no_data="لا توجد حصص منفذة")
        ui.label("الدفعات").classes("font-bold")
        pays = [dict(id=p.id, date=str(p.paid_on or ""), amount=money(p.net), method=config.PAYMENT_METHODS_AR.get(p.method, p.method),
                     status=STATUS_AR.get(p.status, p.status), can=p.status == "paid")
                for p in svc.instructors.payments(instructor_id, lo, hi)]
        t = data_table([col("date", "التاريخ"), col("amount", "المبلغ"), col("method", "الطريقة"), col("status", "الحالة"),
                        col("actions", "")], pays, "id", page_size=6, no_data="لا توجد دفعات")
        C.action_buttons(t, [
            ("print_pay", "print", "طباعة إيصال الدفعة PDF", "primary", "props.row.can"),
            ("reverse", "block", "إلغاء الدفعة", "negative", "props.row.can"),
        ])

        @guarded
        def print_payment(e) -> None:
            pid = int(e.args["id"])
            path = ex.export_instructor_statement(
                ctx, instructor_id, lo, hi,
                payment_id=pid,
                custom_title="إيصال صرف مستحقات مدرب",
            )
            C.pdf_dialog(path, f"تم تصدير إيصال الدفعة #{pid}")

        t.on("print_pay", print_payment)
        t.on("reverse", lambda e: C.confirm_dialog(
            "إلغاء هذه الدفعة؟ سيعود المبلغ إلى المستحق.",
            lambda pid=e.args["id"]: (svc.instructors.reverse_payment(pid), ok("تم إلغاء الدفعة"), panel.close(), on_changed()),
            "إلغاء الدفعة", danger=True))
    panel.open()
