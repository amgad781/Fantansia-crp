"""Students: list (search + remaining lessons), profile, registration form (build-plan step 2)."""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from nicegui import ui

import config
from core.context import AppContext
from core.schemas import Sheet
from export import service as ex
from services.common import (ServiceError, money, month_label, shift_month, today, month_key,
                             whatsapp_link)
from services.ledger import lessons_color
from ui import components as C
from ui.components import (DateField, STATUS_AR, STATUS_COLOR, card, col, data_table, guarded, lessons_text, ok,
                           set_rows)
from ui.layout import COLORS, render_page

W_FIELD = "width:260px;max-width:100%"
ITEM_AR = {"monthly": "اشتراك شهري", "contest": "تسجيل مسابقة", "other": "أخرى"}


def _age(dob: Optional[date]) -> Optional[int]:
    if not dob:
        return None
    t = today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def _age_group(age: Optional[int]) -> Optional[str]:
    if age is None:
        return None
    for g in config.AGE_GROUPS:
        lo, hi = (int(x) for x in g.split("-"))
        if lo <= age <= hi:
            return g
    return None


def _group_options(ctx: AppContext, any_label: str = "") -> dict[Any, str]:
    opts: dict[Any, str] = {"": any_label} if any_label else {}
    for g in ctx.svc.ledger().groups.values():
        opts[g.group_id] = ctx.svc.groups.label(g)
    return opts


def _program_options(ctx: AppContext, any_label: str = "") -> dict[str, str]:
    progs = list(ctx.svc.groups.list_programs())
    opts = {"": any_label} if any_label else {}
    opts.update({p: p for p in progs})
    return opts


# ============================================================================ forms
def personal_form(init: Optional[dict[str, Any]] = None) -> Callable[[], dict[str, Any]]:
    """Personal-data fields. Returns collect() -> dict ready for the Students sheet."""
    from services.students import transliterate_ar_to_en
    v = init or {}
    init_ar = v.get("name_ar", "") or ""
    init_en = v.get("name_en", "") or (transliterate_ar_to_en(init_ar) if init_ar else "")
    auto_state = {"last_auto": init_en}
    with ui.row().classes("w-full gap-3 items-start"):
        name = ui.input("اسم الطالب (ثلاثي بالعربية) *", value=init_ar).props("outlined dense").style(W_FIELD)
        name_en = ui.input("اسم الطالب (ثلاثي بالإنجليزية) *", value=init_en).props("outlined dense dir=ltr").style(W_FIELD)
        dob = DateField("تاريخ الميلاد", v.get("dob"), width="260px")
        grade = ui.input("المرحلة الدراسية", value=v.get("grade", "")).props("outlined dense").style(W_FIELD)
        school = ui.input("اسم المدرسة", value=v.get("school", "")).props("outlined dense").style(W_FIELD)
        pm = ui.input("موبايل ولي الأمر *", value=v.get("parent_mobile", "")).props("outlined dense").style(W_FIELD)
        pw = ui.input("واتساب ولي الأمر", value=v.get("parent_whatsapp", "")).props("outlined dense").style(W_FIELD)
        sm = ui.input("موبايل الطالب", value=v.get("student_mobile", "")).props("outlined dense").style(W_FIELD)
        addr = ui.input("العنوان", value=v.get("address", "")).props("outlined dense").style(W_FIELD)
        src = ui.select(config.LEAD_SOURCES_AR, label="كيف عرفت الأكاديمية؟", value=v.get("source"),
                        clearable=True, new_value_mode="add-unique").props("outlined dense").style(W_FIELD)
        lives = ui.input("مع من يعيش الطالب", value=v.get("lives_with", "")).props("outlined dense").style(W_FIELD)
        sib = C.num_input("عدد الإخوة", v.get("siblings_count"), "260px")
        rank = C.num_input("ترتيب الطالب بين إخوته", v.get("sibling_rank"), "260px")
    with ui.row().classes("items-center gap-3"):
        ui.label("الفئة العمرية").classes("muted text-sm")
        ag = ui.toggle(config.AGE_GROUPS, value=v.get("age_group")).props("no-caps unelevated toggle-color=primary")

    def on_ar_change() -> None:
        cur_en = (name_en.value or "").strip()
        if not cur_en or cur_en == auto_state["last_auto"]:
            suggested = transliterate_ar_to_en(name.value or "")
            auto_state["last_auto"] = suggested
            name_en.set_value(suggested)

    name.on_value_change(lambda _: on_ar_change())

    def on_dob() -> None:
        try:
            g = _age_group(_age(dob.get()))
        except ServiceError:
            return
        if g:
            ag.set_value(g)
    dob.input.on_value_change(lambda e: on_dob())

    def collect() -> dict[str, Any]:
        wa = (pw.value or "").strip() or (pm.value or "").strip()
        en_val = (name_en.value or "").strip()
        return dict(name_ar=name.value or "", name_en=en_val, dob=dob.get(), grade=grade.value, school=school.value,
                    parent_mobile=(pm.value or "").strip() or None, parent_whatsapp=wa or None,
                    student_mobile=(sm.value or "").strip() or None, address=addr.value,
                    source=src.value, lives_with=lives.value,
                    siblings_count=int(sib.value) if sib.value is not None else None,
                    sibling_rank=int(rank.value) if rank.value is not None else None,
                    age_group=ag.value)
    return collect


def assessment_form(init: Optional[dict[str, Any]] = None, with_placement: bool = True) -> Callable[[], dict[str, Any]]:
    v = init or {}
    grades: dict[str, ui.toggle] = {}
    comments: dict[str, ui.input] = {}
    with ui.column().classes("w-full gap-2"):
        for key, label in config.ASSESSMENT_CRITERIA:
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.label(label).classes("font-semibold").style("width:170px;flex:none")
                grades[key] = ui.toggle(["1", "2", "3", "4", "5"], value=v.get(f"{key}_grade")) \
                    .props("no-caps unelevated toggle-color=primary size=sm")
                comments[key] = ui.input("ملاحظة", value=v.get(f"{key}_comment", "")) \
                    .props("outlined dense").classes("flex-1")
    track = level = assessor = None
    get_track = lambda: None            # noqa: E731
    if with_placement:
        ui.separator()
        ui.label("التوجيه المبدئي").classes("font-bold")
        get_track = C.choice_cards(config.TRACKS_AR, v.get("track"), lambda _: None)
        with ui.row().classes("gap-3 items-center"):
            level = ui.select(config.LEVELS_AR, label="مستوى البداية", value=v.get("start_level"),
                              clearable=True).props("outlined dense").style("width:200px")
            assessor = ui.input("القائم بالتقييم", value=v.get("assessor", "")).props("outlined dense").style("width:220px")

    def collect() -> dict[str, Any]:
        d: dict[str, Any] = {}
        for key, _ in config.ASSESSMENT_CRITERIA:
            d[f"{key}_grade"] = grades[key].value
            d[f"{key}_comment"] = comments[key].value
        if with_placement:
            d.update(track=get_track(), start_level=level.value, assessor=assessor.value)
        return d
    return collect


# ============================================================================ list page
def body_list(ctx: AppContext) -> None:
    svc = ctx.svc
    f = dict(q="", program="", group="", status="", low=False)

    def load() -> list[dict]:
        from services.students import transliterate_ar_to_en
        rows = svc.ledger().student_rows(f["q"], f["program"], f["group"] or None, f["status"], f["low"])
        for r in rows:
            r["name_en_label"] = r.get("name_en") or transliterate_ar_to_en(r["name"])
            r["lessons_label"] = lessons_text(r["lessons"])
            r["status_label"] = STATUS_AR.get(r["status"], r["status"])
            r["balance_label"] = money(r["balance"])
            r["paid_label"] = money(r["paid"])
            r["warn"] = r["absence_flag"]
        return rows

    def refresh() -> None:
        rows = load()
        set_rows(table, rows)
        count.set_text(f"{len(rows)} طالب")

    def setf(key: str):
        def _(value) -> None:
            f[key] = value if value is not None else ("" if key != "low" else False)
            refresh()
        return _

    with ui.row().classes("w-full items-center justify-between gap-3"):
        C.section_title("الطلاب")
        with ui.row().classes("items-center gap-2"):
            leads_cnt = len([l for l in svc.students.list_leads() if l.get("status") != "تم التسجيل"])
            ui.button(f"قائمة الانتظار والمهتمين ({leads_cnt})", icon="playlist_add_check",
                      on_click=lambda: _leads_dialog(ctx)).props("outline no-caps color=secondary")
            ui.button("طالب جديد", icon="add", on_click=lambda: ui.navigate.to("/students/new")).props("unelevated no-caps")

    with card():
        with ui.row().classes("w-full items-center gap-3"):
            C.search_box("ابحث بالاسم (عربي/إنجليزي) أو الرقم أو الموبايل", setf("q"), "340px")
            ui.select(_program_options(ctx, "كل البرامج"), value="", label="البرنامج",
                      on_change=lambda e: setf("program")(e.value)).props("outlined dense").style("width:190px")
            ui.select(_group_options(ctx, "كل المجموعات"), value="", label="المجموعة",
                      on_change=lambda e: setf("group")(e.value)).props("outlined dense").style("width:230px")
            ui.select({"": "كل الحالات", "active": "نشط", "inactive": "غير نشط"}, value="", label="الحالة",
                      on_change=lambda e: setf("status")(e.value)).props("outlined dense").style("width:150px")
            ui.switch("حصص قليلة فقط", on_change=lambda e: setf("low")(e.value))
            ui.space()
            count = ui.label("").classes("muted text-sm")

        columns = [col("id", "#", sortable=True), col("name", "اسم الطالب (عربي)", sortable=True),
                   col("name_en_label", "الاسم (English)", sortable=True),
                   col("program", "البرنامج"), col("group", "المجموعة"), col("mobile", "موبايل ولي الأمر"),
                   col("paid_label", "المدفوع"), col("balance_label", "المتبقي من الرسوم"),
                   col("lessons_label", "الحصص المتبقية"), col("status_label", "الحالة"), col("actions", "")]
        table = data_table(columns, [], "id", no_data="لا يوجد طلاب مطابقون")
        C.badge_cell(table, "lessons_label", "lessons_color", "lessons_label")
        table.add_slot("body-cell-name", '''<q-td :props="props">
            <span>{{ props.row.name }}</span>
            <q-icon v-if="props.row.warn" name="warning" color="warning" size="18px" class="q-mr-xs">
              <q-tooltip>تجاوز حد الغياب المسموح</q-tooltip></q-icon></q-td>''')
        C.action_buttons(table, [("open", "open_in_new", "فتح الملف", "primary"),
                                 ("pay", "add_card", "إضافة دفعة", "positive"),
                                 ("wa", "chat", "واتساب ولي الأمر", "teal", "props.row.mobile !== '—'"),
                                 ("receipt", "picture_as_pdf", "تصدير آخر إيصال PDF", "grey-8")])
        table.on("rowClick", lambda e: ui.navigate.to(f"/students/{e.args[1]['id']}"))
        table.on("open", lambda e: ui.navigate.to(f"/students/{e.args['id']}"))

        def pay(e) -> None:
            ctx.nav["student_id"] = e.args["id"]
            ui.navigate.to("/receipts")
        table.on("pay", pay)

        @guarded
        def wa(e) -> None:
            st = ctx.svc.ledger().students.get(e.args["id"])
            link = whatsapp_link((st.parent_whatsapp or st.parent_mobile) if st else None,
                                 f"السلام عليكم، بخصوص الطالب {st.name_ar} — أكاديمية فانتازيا")
            if not link:
                raise ServiceError("رقم ولي الأمر غير صالح للواتساب.")
            ex.open_url(link)
        table.on("wa", wa)

        @guarded
        def last_receipt(e) -> None:
            rows = [r for r in svc.receipts.rows(student_id=e.args["id"]) if r["status"] == "active"]
            if not rows:
                raise ServiceError("لا توجد إيصالات لهذا الطالب.")
            C.pdf_dialog(ex.export_receipt(ctx, rows[0]["serial"], reprint=True), "تم تصدير الإيصال")
        table.on("receipt", last_receipt)
    refresh()


# ============================================================================ profile
def _kv(label: str, value: Any) -> None:
    with ui.column().classes("gap-0").style("width:240px"):
        ui.label(label).classes("muted text-xs")
        ui.label(str(value) if value not in (None, "") else "—").classes("font-semibold")


def body_profile(ctx: AppContext, sid: int) -> None:
    from services.students import transliterate_ar_to_en
    svc = ctx.svc
    led = svc.ledger()
    st = led.students.get(sid)
    if not st:
        ui.label("الطالب غير موجود.").classes("text-negative")
        ui.button("رجوع للطلاب", on_click=lambda: ui.navigate.to("/students")).props("flat no-caps")
        return
    enrs = led.student_enrollments(sid)
    sums = [led.summary(e.enrollment_id) for e in enrs]
    live = [s for s in sums if s.enrollment.status in ("active", "paused")]
    en_display = getattr(st, "name_en", None) or transliterate_ar_to_en(st.name_ar)
    siblings = svc.students.detect_siblings(st.parent_mobile, exclude_student_id=sid)

    # ---------------------------------------------------------------- header
    with card():
        with ui.row().classes("w-full items-center gap-4 no-wrap flex-wrap"):
            with ui.element("div").classes("rounded-full flex items-center justify-center") \
                    .style(f"width:64px;height:64px;background:{COLORS['primary_light']};color:{COLORS['primary']};"
                           "font-size:28px;font-weight:800;flex:none"):
                ui.label(st.name_ar.strip()[:1])
            with ui.column().classes("gap-1 flex-1"):
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    ui.label(st.name_ar).classes("text-xl font-bold")
                    ui.label(f"({en_display})").classes("text-base font-semibold muted ltr")
                    ui.badge(STATUS_AR.get(st.status, st.status), color=STATUS_COLOR.get(st.status, "grey"))
                    if siblings:
                        ui.badge(f"إخوة مسجلون: {'، '.join(s.name_ar for s in siblings)}", color="secondary")
                bits = []
                if _age(st.dob) is not None:
                    bits.append(f"{_age(st.dob)} سنة")
                bits += sorted({s.group.cost_center for s in live if s.group})
                ui.label(" — ".join(bits) or "—").classes("muted")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("إضافة دفعة", icon="add_card", on_click=lambda: (ctx.nav.update(student_id=sid),
                                                                          ui.navigate.to("/receipts"))) \
                    .props("unelevated no-caps")

                @guarded
                def export_id_card() -> None:
                    path = ex.export_student_id_card(ctx, sid)
                    C.pdf_dialog(path, "تم تصدير بطاقة عضوية الطالب بـ QR Code")

                ui.button("بطاقة العضوية QR", icon="badge", on_click=export_id_card).props("outline no-caps color=secondary")
                ui.button("شهادة إتمام PDF", icon="workspace_premium",
                          on_click=lambda: _certificate_dialog(ctx, st, live)).props("outline no-caps color=primary")
                ui.button("قوالب واتساب", icon="mark_chat_read",
                          on_click=lambda: _whatsapp_templates_dialog(ctx, st, live)).props("outline no-caps color=teal")

                @guarded
                def open_wa() -> None:
                    link = whatsapp_link(st.parent_whatsapp or st.parent_mobile,
                                         f"السلام عليكم، بخصوص الطالب {st.name_ar} — أكاديمية فانتازيا")
                    if not link:
                        raise ServiceError("رقم ولي الأمر غير صالح للواتساب.")
                    ex.open_url(link)
                ui.button("واتساب", icon="chat", on_click=open_wa).props("outline no-caps color=teal")
                ui.button("تعديل", icon="edit", on_click=lambda: _edit_student_dialog(ctx, st)).props("flat no-caps")

        for sm in live:                                   # remaining lessons progress per live enrollment
            total = max(sm.purchased, 1)
            pct = max(0.0, min(1.0, sm.remaining_lessons / total))
            with ui.row().classes("w-full items-center gap-3 no-wrap"):
                ui.label(f"{sm.group.cost_center if sm.group else '—'}").classes("font-semibold").style("width:160px;flex:none")
                ui.linear_progress(value=pct, show_value=False).props(
                    f"rounded size=12px color={lessons_color(sm.remaining_lessons)}").classes("flex-1")
                ui.label(f"الحصص المتبقية {max(sm.remaining_lessons, 0)} من {sm.purchased}").classes("text-sm") \
                    .style("width:190px;flex:none")
                if sm.absence_exceeded:
                    ui.icon("warning", color="warning").tooltip(f"غياب {sm.absences} — تجاوز الحد المسموح")

    # ------------------------------------------------------------------ tabs
    with ui.tabs().classes("w-full").props("align=right no-caps active-color=primary indicator-color=primary") as tabs:
        t_data = ui.tab("البيانات الشخصية")
        t_ass = ui.tab("التقييم")
        t_sub = ui.tab("الاشتراك والرسوم")
        t_rec = ui.tab("الإيصالات")
        t_att = ui.tab("الحضور")
        t_cert = ui.tab("الشهادات السابقة")
    with ui.tab_panels(tabs, value=t_data).classes("w-full bg-transparent"):
        with ui.tab_panel(t_data).classes("p-0"):
            with card():
                with ui.row().classes("w-full gap-4"):
                    for label, val in (("الاسم بالعربية", st.name_ar), ("الاسم بالإنجليزية", en_display),
                                       ("تاريخ الميلاد", st.dob), ("المرحلة الدراسية", st.grade),
                                       ("المدرسة", st.school), ("موبايل ولي الأمر", st.parent_mobile),
                                       ("واتساب ولي الأمر", st.parent_whatsapp), ("موبايل الطالب", st.student_mobile),
                                       ("العنوان", st.address), ("كيف عرفت الأكاديمية", st.source),
                                       ("مع من يعيش", st.lives_with), ("عدد الإخوة", st.siblings_count),
                                       ("الترتيب بين الإخوة", st.sibling_rank), ("الفئة العمرية", st.age_group),
                                       ("رقم الطالب", st.student_id), ("تاريخ التسجيل", st.created_at and st.created_at.date())):
                        _kv(label, val)
        with ui.tab_panel(t_ass).classes("p-0"):
            _assessment_tab(ctx, sid)
        with ui.tab_panel(t_sub).classes("p-0"):
            _subscription_tab(ctx, sid, sums)
        with ui.tab_panel(t_rec).classes("p-0"):
            _receipts_tab(ctx, sid)
        with ui.tab_panel(t_att).classes("p-0"):
            _attendance_tab(ctx, sid, led, enrs)
        with ui.tab_panel(t_cert).classes("p-0"):
            _certificates_tab(ctx, st, live)


def _assessment_tab(ctx: AppContext, sid: int) -> None:
    a = ctx.svc.students.latest_assessment(sid)
    with card():
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(f"آخر تقييم — {a.date}" if a else "لا يوجد تقييم بعد").classes("font-bold")
            ui.button("تقييم جديد / تعديل", icon="edit_note",
                      on_click=lambda: _assessment_dialog(ctx, sid, a)).props("outline no-caps")
        if a:
            rows = [dict(c=label, g=getattr(a, f"{k}_grade") or "—", n=getattr(a, f"{k}_comment") or "")
                    for k, label in config.ASSESSMENT_CRITERIA]
            data_table([col("c", "المعيار"), col("g", "الدرجة (من 5)"), col("n", "ملاحظات")], rows, "c", page_size=10)
            with ui.row().classes("gap-6"):
                _kv("التوجيه المبدئي", a.track)
                _kv("مستوى البداية", a.start_level)
                _kv("القائم بالتقييم", a.assessor)


def _assessment_dialog(ctx: AppContext, sid: int, a) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:820px;max-width:96vw"):
        ui.label("تقييم الطالب").classes("text-lg font-bold")
        collect = assessment_form(a.model_dump() if a else {"assessor": ctx.session.username})
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.students.save_assessment(sid, collect())
                d.close()
                ok("تم حفظ التقييم")
                ui.navigate.reload()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _edit_student_dialog(ctx: AppContext, st) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:900px;max-width:96vw"):
        ui.label("تعديل بيانات الطالب").classes("text-lg font-bold")
        collect = personal_form(st.model_dump())
        status = ui.select({"active": "نشط", "inactive": "غير نشط"}, value=st.status, label="الحالة") \
            .props("outlined dense").style("width:200px")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                data = collect()
                data["status"] = status.value
                ctx.svc.students.update_student(st.student_id, data)
                d.close()
                ok("تم حفظ التعديلات")
                ui.navigate.reload()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _subscription_tab(ctx: AppContext, sid: int, sums: list) -> None:
    with ui.row().classes("w-full justify-end"):
        ui.button("اشتراك جديد في مجموعة", icon="add", on_click=lambda: _new_enrollment_dialog(ctx, sid)) \
            .props("outline no-caps")
    if not sums:
        with card():
            C.empty_hint("لا توجد اشتراكات بعد", "school")
    for sm in sums:
        enr = sm.enrollment
        with card():
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label(ctx.svc.groups.label(sm.group) if sm.group else f"مجموعة {enr.group_id}").classes("font-bold")
                    ui.label(f"بداية الاشتراك: {enr.start_date}").classes("muted text-sm")
                with ui.row().classes("items-center gap-2"):
                    ui.badge(STATUS_AR.get(enr.status, enr.status), color=STATUS_COLOR.get(enr.status, "grey"))
                    ui.button("رسوم", icon="add", on_click=lambda e=enr: _add_fee_dialog(ctx, e)).props("flat dense no-caps")
                    ui.button("الحصص", icon="edit", on_click=lambda e=enr: _lessons_dialog(ctx, e)).props("flat dense no-caps")
                    ui.select({"active": "نشط", "paused": "متوقف", "completed": "منتهي", "cancelled": "ملغي"},
                              value=enr.status, on_change=lambda ev, e=enr: _set_status(ctx, e, ev.value)) \
                        .props("outlined dense").style("width:120px")
            with ui.row().classes("gap-8"):
                _kv("إجمالي الرسوم", money(sm.due))
                _kv("المدفوع", money(sm.paid))
                _kv("المتبقي", money(sm.remaining_fees))
                _kv("رصيد دائن", money(sm.credit) if sm.credit else "—")
                _kv("الحصص (مشتراة / مستهلكة / متبقية)", f"{sm.purchased} / {sm.consumed} / {sm.remaining_lessons}")
                _kv("الغياب", sm.absences)
            rows = [dict(k=f"{l.item}|{l.month}", item=ITEM_AR.get(l.item, l.item), month=month_label(l.month),
                         due=money(l.due), paid=money(l.paid), rem=money(l.remaining),
                         state=dict(paid="مسدد", partial="جزئي", unpaid="غير مسدد")[l.state],
                         color=dict(paid="positive", partial="warning", unpaid="negative")[l.state])
                    for l in sm.lines]
            t = data_table([col("item", "البند"), col("month", "الشهر"), col("due", "المستحق"), col("paid", "المسدد"),
                            col("rem", "المتبقي"), col("state", "الحالة")], rows, "k", page_size=12,
                           no_data="لا توجد رسوم مجدولة")
            C.badge_cell(t, "state", "color", "state")


@guarded
def _set_status(ctx: AppContext, enr, status: str) -> None:
    if status != enr.status:
        ctx.svc.students.set_enrollment_status(enr.enrollment_id, status)
        ok("تم تحديث حالة الاشتراك")
        ui.navigate.reload()


def _lessons_dialog(ctx: AppContext, enr) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("min-width:360px"):
        ui.label("تعديل عدد الحصص المشتراة").classes("font-bold")
        ui.label("يُزاد تلقائيًا عند سداد كل شهر. عدّله يدويًا للطلاب المسجلين قبل بدء البرنامج.").classes("muted text-sm")
        n = ui.number("عدد الحصص", value=enr.lessons_purchased, min=0, format="%d").props("outlined dense")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.students.set_lessons(enr.enrollment_id, int(n.value or 0))
                d.close()
                ok("تم الحفظ")
                ui.navigate.reload()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _add_fee_dialog(ctx: AppContext, enr) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("min-width:380px"):
        ui.label("إضافة رسوم مستحقة").classes("font-bold")
        item = ui.select(ITEM_AR, value="monthly", label="البند").props("outlined dense").classes("w-full")
        month = ui.select(C.month_options(3, 12), value=month_key(today()), label="الشهر").props("outlined dense").classes("w-full")
        amount = C.num_input("المبلغ", None, "100%", "ج.م", min_=0)
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.svc.students.add_fee(enr.enrollment_id, item.value, month.value, float(amount.value or 0))
                d.close()
                ok("تمت إضافة الرسوم")
                ui.navigate.reload()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _new_enrollment_dialog(ctx: AppContext, sid: int) -> None:
    st = ctx.svc.ledger().students.get(sid)
    siblings = ctx.svc.students.detect_siblings(st.parent_mobile if st else None, exclude_student_id=sid)
    default_disc = 10.0 if siblings else 0.0
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("min-width:460px;max-width:96vw"):
        ui.label("اشتراك جديد").classes("font-bold")
        if siblings:
            ui.label(f"تم اكتشاف أخ مسجل ({'، '.join(s.name_ar for s in siblings)}) — تم تفعيل خصم الإخوة المقترح 10%") \
                .classes("text-xs font-bold text-positive")
        conflict_lbl = ui.label("").classes("text-xs font-bold text-warning")
        conflict_lbl.set_visibility(False)

        def on_grp_change(e) -> None:
            if e.value:
                conf = ctx.svc.students.check_student_schedule_conflicts(sid, int(e.value))
                if conf:
                    conflict_lbl.set_text("تنبيه تعارض مواعيد للطالب مع: " + " | ".join(f"{c['label']} ({c['schedule']})" for c in conf))
                    conflict_lbl.set_visibility(True)
                    return
            conflict_lbl.set_visibility(False)

        group = ui.select(_group_options(ctx), label="المجموعة", on_change=on_grp_change).props("outlined dense").classes("w-full")
        start = DateField("تاريخ البداية", today(), width="100%")
        fee = C.num_input("قيمة الاشتراك الشهري", None, "100%", "ج.م")
        disc_pct = C.num_input("خصم الإخوة / منحة (%)", default_disc, "100%", "%", min_=0)
        months = C.num_input("عدد الشهور", 1, "100%", min_=1)
        contest = C.num_input("رسوم تسجيل مسابقة (اختياري)", None, "100%", "ج.م")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                if not group.value:
                    raise ServiceError("اختر المجموعة.")
                ctx.svc.students.add_enrollment(
                    sid, int(group.value), start.get(), float(fee.value or 0),
                    int(months.value or 1), float(contest.value or 0),
                    discount_pct=float(disc_pct.value or 0),
                )
                d.close()
                ok("تم تسجيل الاشتراك")
                ui.navigate.reload()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _leads_dialog(ctx: AppContext) -> None:
    svc = ctx.svc
    progs = list(svc.groups.list_programs())
    status_opts = {"جديد": "جديد", "تم التواصل": "تم التواصل", "قائمة انتظار": "قائمة انتظار", "تم التسجيل": "تم التسجيل"}
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:880px;max-width:96vw"):
        ui.label("قائمة الانتظار والمهتمين بالحجز (Leads CRM)").classes("text-lg font-bold")
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            l_name = ui.input("اسم الطالب / المهتم *").props("outlined dense").style("width:200px")
            l_phone = ui.input("رقم الموبايل / واتساب *").props("outlined dense").style("width:160px")
            l_prog = ui.select(progs, label="البرنامج المطلوب", value=progs[0] if progs else None,
                               new_value_mode="add-unique", with_input=True).props("outlined dense").style("width:160px")
            l_notes = ui.input("ملاحظة / الموعد المفضل").props("outlined dense").classes("flex-1")

            @guarded
            def add_l() -> None:
                svc.students.add_lead(l_name.value or "", l_phone.value or "", program=l_prog.value or "", notes=l_notes.value or "")
                l_name.set_value("")
                l_phone.set_value("")
                l_notes.set_value("")
                set_rows(lt, svc.students.list_leads())
                ok("تمت الإضافة لقائمة الانتظار")

            ui.button("إضافة للقائمة", icon="person_add", on_click=add_l).props("unelevated no-caps dense color=primary")

        lt = data_table(
            [col("id", "#"), col("name", "الاسم"), col("phone", "الموبايل"), col("program", "البرنامج"),
             col("status", "الحالة"), col("notes", "ملاحظات"), col("created_at", "التاريخ"), col("actions", "")],
            svc.students.list_leads(), "id", page_size=8, no_data="لا يوجد مسجلون في قائمة الانتظار",
        )
        C.action_buttons(lt, [
            ("contact", "Done", "تم التواصل", "positive"),
            ("convert", "how_to_reg", "تحويل لطالب", "primary"),
            ("del_lead", "delete", "حذف", "negative"),
        ])

        @guarded
        def mark_contacted(e) -> None:
            svc.students.update_lead_status(int(e.args["id"]), "تم التواصل")
            set_rows(lt, svc.students.list_leads())
            ok("تم تحديث الحالة إلى «تم التواصل»")

        @guarded
        def convert_lead(e) -> None:
            svc.students.update_lead_status(int(e.args["id"]), "تم التسجيل")
            d.close()
            ui.navigate.to("/students/new")

        @guarded
        def del_l(e) -> None:
            svc.students.delete_lead(int(e.args["id"]))
            set_rows(lt, svc.students.list_leads())
            ok("تم الحذف من قائمة الانتظار")

        lt.on("contact", mark_contacted)
        lt.on("convert", convert_lead)
        lt.on("del_lead", del_l)
        with ui.row().classes("justify-end w-full"):
            ui.button("إغلاق", on_click=d.close).props("flat no-caps")
    d.open()


def _certificates_tab(ctx: AppContext, st, live_sums: list) -> None:
    svc = ctx.svc

    def load_rows() -> list[dict]:
        rows = svc.students.list_certificates(st.student_id)
        for r in rows:
            r["instructor_label"] = r.get("instructor") or "—"
            r["notes_label"] = r.get("notes") or "—"
        return rows

    with card():
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("سجل الشهادات والمستويات التي أتمّها الطالب بالأكاديمية").classes("font-bold")
            ui.button(
                "إصدار / تسجيل شهادة جديدة",
                icon="workspace_premium",
                on_click=lambda: _certificate_dialog(ctx, st, live_sums, on_saved=lambda: set_rows(ct, load_rows())),
            ).props("unelevated no-caps color=primary")

        ct = data_table(
            [
                col("serial", "رقم الشهادة", sortable=True),
                col("issue_date", "تاريخ الإصدار", sortable=True),
                col("program", "البرنامج التعليمي"),
                col("level", "المستوى / الدبلومة"),
                col("grade", "التقدير"),
                col("instructor_label", "المدرب المشرف"),
                col("notes_label", "ملاحظات"),
                col("actions", ""),
            ],
            load_rows(),
            "cert_id",
            no_data="لا توجد شهادات سابقة مسجلة لهذا الطالب",
        )
        C.action_buttons(ct, [
            ("pdf", "picture_as_pdf", "طباعة / تصدير PDF", "primary"),
            ("del_cert", "delete", "حذف الشهادة", "negative"),
        ])

        @guarded
        def reprint_cert(e) -> None:
            import importlib
            importlib.reload(ex)
            row = e.args
            path = ex.export_student_certificate(
                ctx,
                st.student_id,
                program=row.get("program", ""),
                level=row.get("level", ""),
                grade=row.get("grade", ""),
                grade_label=row.get("grade", ""),
                instructor_name=row.get("instructor", ""),
                notes=row.get("notes", ""),
                issue_date=row.get("issue_date") or today(),
                record_history=False,
            )
            C.pdf_dialog(path, f"تم تصدير الشهادة رقم {row.get('serial', '')}")

        @guarded
        def remove_cert(e) -> None:
            svc.students.delete_certificate(int(e.args["cert_id"]))
            set_rows(ct, load_rows())
            ok("تم حذف الشهادة من السجل")

        ct.on("pdf", reprint_cert)
        ct.on("del_cert", remove_cert)


def _certificate_dialog(ctx: AppContext, st, live_sums: list, on_saved=None) -> None:
    svc = ctx.svc
    progs = list(svc.groups.list_programs())
    def_prog = live_sums[0].group.cost_center if (live_sums and live_sums[0].group) else (progs[0] if progs else "برمجة")
    def_lvl = (live_sums[0].group.level if (live_sums and live_sums[0].group and live_sums[0].group.level) else "Level 1")
    def_inst = ""
    if live_sums and live_sums[0].group and live_sums[0].group.instructor_id:
        ins = svc.ledger().instructors.get(live_sums[0].group.instructor_id)
        if ins:
            def_inst = ins.name
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:480px;max-width:96vw"):
        ui.label(f"إصدار شهادة إتمام مستوى PDF — {st.name_ar}").classes("text-lg font-bold")
        prog_in = ui.select(progs, label="البرنامج التعليمي", value=def_prog,
                            new_value_mode="add-unique", with_input=True).props("outlined dense").classes("w-full")
        lvl_in = ui.select(config.LEVELS_AR, label="المستوى / الدبلومة", value=def_lvl,
                           new_value_mode="add-unique", with_input=True).props("outlined dense").classes("w-full")
        grade_in = ui.select(["امتياز مع مرتبة الشرف (Excellent)", "امتياز (Distinction)", "جيد جدًا (Very Good)", "اجتياز بنجاح (Pass)"],
                             label="التقدير", value="امتياز مع مرتبة الشرف (Excellent)").props("outlined dense").classes("w-full")
        inst_in = ui.input("اسم المدرب المشرف", value=def_inst).props("outlined dense").classes("w-full")
        date_in = DateField("تاريخ الإصدار", today(), width="100%")
        notes_in = ui.input("ملاحظات إضافية (اختياري)").props("outlined dense").classes("w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def gen_cert() -> None:
                import importlib
                importlib.reload(ex)
                inst_val = (inst_in.value or "").strip()
                note_val = (notes_in.value or "").strip()
                if not note_val and inst_val:
                    note_val = f"بإشراف المدرب: {inst_val}"
                path = ex.export_student_certificate(
                    ctx, st.student_id, program=prog_in.value or def_prog,
                    level=lvl_in.value or def_lvl,
                    grade=grade_in.value or "امتياز",
                    grade_label=grade_in.value or "امتياز",
                    instructor_name=inst_val,
                    notes=note_val,
                    issue_date=date_in.get() or today(),
                    record_history=True,
                )
                d.close()
                if on_saved:
                    on_saved()
                C.pdf_dialog(path, "تم إصدار وحفظ شهادة إتمام المستوى PDF")

            ui.button("تصدير الشهادة PDF", icon="picture_as_pdf", on_click=gen_cert).props("unelevated no-caps color=primary")
    d.open()


def _whatsapp_templates_dialog(ctx: AppContext, st, live_sums: list) -> None:
    import importlib
    import services.common as s_common
    importlib.reload(s_common)
    from services.common import WHATSAPP_TEMPLATES_AR, whatsapp_template_message
    svc = ctx.svc
    prog = live_sums[0].group.cost_center if (live_sums and live_sums[0].group) else "البرنامج التعليمي"
    lvl = (live_sums[0].group.level if (live_sums and live_sums[0].group and live_sums[0].group.level) else "Level 1")
    sched = (live_sums[0].group.schedule if (live_sums and live_sums[0].group and live_sums[0].group.schedule) else "حسب الجدول")
    rem_les = live_sums[0].remaining_lessons if live_sums else 0
    rem_fee = float(sum(s.remaining_fees for s in live_sums))
    recs = [r for r in svc.receipts.rows(student_id=st.student_id) if r["status"] == "active"]
    last_amt = float(recs[0]["amount"]) if recs else 0.0
    last_ser = recs[0]["serial"] if recs else "—"

    tpl_opts = {k: (v["label"] if isinstance(v, dict) else str(v)) for k, v in WHATSAPP_TEMPLATES_AR.items()}
    ctx_vars = dict(
        student_name=st.name_ar, program=prog, level=lvl, schedule=sched,
        remaining_lessons=rem_les, amount=rem_fee if rem_fee > 0 else last_amt,
        serial=last_ser, date=str(today()), months="الشهر الحالي", grade="امتياز",
    )

    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:540px;max-width:96vw"):
        ui.label(f"قوالب رسائل واتساب جاهزة — {st.name_ar}").classes("text-lg font-bold")
        tpl_sel = ui.select(tpl_opts, value="welcome", label="اختر قالب الرسالة",
                            on_change=lambda e: msg_area.set_value(whatsapp_template_message(e.value, **ctx_vars))) \
            .props("outlined dense").classes("w-full")
        msg_area = ui.textarea("نص الرسالة (يمكنك التعديل قبل الإرسال)",
                               value=whatsapp_template_message("welcome", **ctx_vars)) \
            .props("outlined rows=5").classes("w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def send_wa() -> None:
                link = whatsapp_link(st.parent_whatsapp or st.parent_mobile, msg_area.value or "")
                if not link:
                    raise ServiceError("رقم ولي الأمر غير صالح للواتساب.")
                d.close()
                ex.open_url(link)

            ui.button("إرسال عبر واتساب", icon="send", on_click=send_wa).props("unelevated no-caps color=teal")
    d.open()


def _receipts_tab(ctx: AppContext, sid: int) -> None:
    rows = ctx.svc.receipts.rows(student_id=sid)
    for r in rows:
        r["amount_label"] = money(r["amount"])
        r["status_label"] = STATUS_AR.get(r["status"], r["status"])
        r["can_cancel"] = r["status"] == "active"
    with card():
        with ui.row().classes("w-full justify-end"):
            ui.button("إضافة دفعة", icon="add_card",
                      on_click=lambda: (ctx.nav.update(student_id=sid), ui.navigate.to("/receipts"))).props("unelevated no-caps")
        t = data_table([col("serial", "المسلسل", sortable=True), col("date", "التاريخ"), col("amount_label", "المبلغ"),
                        col("method", "الطريقة"), col("description", "البيان"), col("status_label", "الحالة"),
                        col("actions", "")], rows, "serial", no_data="لا توجد إيصالات")
        C.action_buttons(t, [("pdf", "picture_as_pdf", "تصدير PDF", "primary"),
                             ("cancel", "block", "إلغاء الإيصال", "negative", "props.row.can_cancel")])

        @guarded
        def pdf(e) -> None:
            C.pdf_dialog(ex.export_receipt(ctx, e.args["serial"], reprint=True), "تم تصدير الإيصال")
        t.on("pdf", pdf)
        t.on("cancel", lambda e: C.reason_dialog(
            f"إلغاء الإيصال رقم {e.args['serial']}",
            lambda reason, s=e.args["serial"]: (ctx.svc.receipts.reverse(s, reason), ok("تم إلغاء الإيصال"),
                                                 ui.navigate.reload())))


def _attendance_tab(ctx: AppContext, sid: int, led, enrs: list) -> None:
    from services.attendance import STATUS_AR as ATT_AR
    sessions = led.sessions
    groups = led.groups
    rows = []
    for a in led.attendance:
        if a.student_id != sid:
            continue
        s = sessions.get(a.session_id)
        if not s:
            continue
        g = groups.get(s.group_id)
        rows.append(dict(k=a.session_id, date=str(s.date), group=g.cost_center if g else "—",
                         time=f"{s.start_time:%H:%M}" if s.start_time else "", status=ATT_AR.get(a.status, a.status),
                         session=STATUS_AR.get(s.status, s.status)))
    rows.sort(key=lambda r: r["date"], reverse=True)
    with card():
        data_table([col("date", "التاريخ", sortable=True), col("time", "الوقت"), col("group", "البرنامج"),
                    col("status", "الحضور"), col("session", "حالة الحصة")], rows, "k", no_data="لا يوجد سجل حضور")


# ============================================================================ new student
def body_new(ctx: AppContext) -> None:
    from services.students import SURVEY_QUESTIONS
    svc = ctx.svc
    survey_ans: dict[str, str] = {q["key"]: q["default"] for q in SURVEY_QUESTIONS}

    C.section_title("تسجيل طالب جديد", "بيانات الطالب، استبيان تحديد البرنامج المناسب، التقييم، ثم الاشتراك في مجموعة")
    with card("أولًا: البيانات الشخصية"):
        get_personal = personal_form()

    with card("ثانيًا: استبيان تحديد الميول والتوصية الذكية بالبرنامج"):
        ui.label("أجب عن الأسئلة التالية ليقوم النظام بترشيح البرنامج التعليمي والمسار والمستوى الأنسب للطالب تلقائيًا:") \
            .classes("text-sm muted")
        with ui.row().classes("w-full gap-4 items-start"):
            for q in SURVEY_QUESTIONS:
                with ui.column().classes("gap-1 p-3 rounded-xl").style(
                    "width:48%;min-width:300px;background:#F8FAFC;border:1px solid #E2E8F0"
                ):
                    ui.label(q["question"]).classes("font-bold text-sm").style(f"color:{COLORS['navy']}")

                    def _on_q(e, k=q["key"]) -> None:
                        survey_ans[k] = e.value
                        rec_panel.refresh()

                    ui.select(q["options"], value=q["default"], on_change=_on_q) \
                        .props("outlined dense").classes("w-full")

        @ui.refreshable
        def rec_panel() -> None:
            try:
                p_data = get_personal()
                age_grp = p_data.get("age_group")
            except Exception:
                age_grp = None
            try:
                a_data = get_assess()
            except Exception:
                a_data = {}
            rec = svc.students.recommend_program(survey_ans, age_group=age_grp, assessment=a_data)
            with ui.column().classes("w-full gap-2 p-4 rounded-xl mt-2").style(
                f"background:{COLORS['primary_light']};border:1.5px solid {COLORS['primary']}"
            ):
                with ui.row().classes("w-full items-center justify-between gap-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("auto_awesome", size="26px").style(f"color:{COLORS['primary']}")
                        with ui.column().classes("gap-0"):
                            ui.label(f"البرنامج المقترح للطالب: «{rec['program']}» (نسبة التوافق {rec['match_pct']}%)") \
                                .classes("text-base font-extrabold").style(f"color:{COLORS['navy']}")
                            ui.label(f"المسار المقترح: {rec['track']}  |  مستوى البداية المقترح: {rec['start_level']}") \
                                .classes("text-xs font-bold").style(f"color:{COLORS['primary']}")

                    def apply_rec(r=rec) -> None:
                        if r.get(" suggested_group_id") or r.get("suggested_group_id"):
                            gid_sug = r["suggested_group_id"]
                            if gid_sug in groups:
                                enroll_on.set_value(True)
                                group.set_value(gid_sug)
                        ok(f"تم اختيار البرنامج المقترح «{r['program']}» ({r['start_level']})")

                    ui.button("تطبيق التوصية واختيار المجموعة المناسبة", icon="check_circle", on_click=apply_rec) \
                        .props("unelevated dense no-caps color=primary")

                with ui.row().classes("items-center gap-2 flex-wrap"):
                    ui.label("ترتيب البرامج حسب ملاءمتها للطالب:").classes("text-xs font-bold muted")
                    for idx, rk in enumerate(rec["rankings"]):
                        badge_col = "primary" if idx == 0 else "secondary"
                        ui.badge(f"{rk['program']}: {rk['score']}%", color=badge_col).props("text-color=white")

                if rec.get("reasons"):
                    with ui.column().classes("gap-0.5 pt-1"):
                        for r_txt in rec["reasons"]:
                            ui.label(f"• {r_txt}").classes("text-xs").style(f"color:{COLORS['navy']}")

        rec_panel()

    with card("ثالثًا: التقييم والتوجيه"):
        get_assess = assessment_form({"assessor": ctx.session.username})
    with card("رابعًا: الاشتراك في مجموعة"):
        groups = _group_options(ctx)
        if not groups:
            ui.label("لا توجد مجموعات بعد. أنشئ مجموعة أولًا ثم ارجع لتسجيل الاشتراك.").classes("muted")
            ui.button("إنشاء مجموعة", icon="add", on_click=lambda: ui.navigate.to("/groups")).props("outline no-caps")
        enroll_on = ui.switch("تسجيل الطالب في مجموعة الآن", value=bool(groups))
        with ui.row().classes("w-full gap-3").bind_visibility_from(enroll_on, "value"):
            group = ui.select(groups, label="المجموعة").props("outlined dense").style(W_FIELD)
            start = DateField("تاريخ البداية", today(), width="260px")
            fee = C.num_input("الاشتراك الشهري", None, "260px", "ج.م")
            disc_pct = C.num_input("خصم الإخوة / منحة (%)", 0, "260px", "%", min_=0)
            months = C.num_input("عدد الشهور", 1, "260px", min_=1)
            contest = C.num_input("رسوم مسابقة (اختياري)", None, "260px", "ج.م")

    with ui.row().classes("w-full justify-end gap-2 sticky bottom-0 py-3").style(
            f"background:{COLORS['bg']};z-index:5"):
        ui.button("إلغاء", on_click=lambda: ui.navigate.to("/students")).props("flat no-caps")

        @guarded
        def save() -> None:
            enrollment = None
            if enroll_on.value:
                if not group.value:
                    raise ServiceError("اختر المجموعة أو أوقف خيار التسجيل في مجموعة.")
                enrollment = dict(group_id=int(group.value), start_date=start.get() or today(),
                                  monthly_fee=float(fee.value or 0), months=int(months.value or 1),
                                  contest_fee=float(contest.value or 0),
                                  discount_pct=float(disc_pct.value or 0))
            assess_payload = get_assess()
            if not assess_payload.get("track") or not assess_payload.get("start_level"):
                rec_now = svc.students.recommend_program(survey_ans, age_group=get_personal().get("age_group"), assessment=assess_payload)
                if not assess_payload.get("track"):
                    assess_payload["track"] = rec_now["track"]
                if not assess_payload.get("start_level"):
                    assess_payload["start_level"] = rec_now["start_level"]
            sid = svc.students.register(get_personal(), assess_payload, enrollment)
            ok("تم إنشاء ملف الطالب")
            ui.navigate.to(f"/students/{sid}")
        ui.button("حفظ وإنشاء ملف الطالب", icon="save", on_click=save).props("unelevated no-caps")



# ============================================================================ registration
def register_routes(ctx: AppContext) -> None:
    """Extra (parameterised) route. Call AFTER register_pages so /students/new wins over /students/{sid}."""
    @ui.page("/students/{sid}")
    def profile(sid: int):
        return render_page(ctx, "students", body_profile, sid)
