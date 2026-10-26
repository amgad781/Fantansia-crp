"""Attendance: group x month grid, click a cell to cycle the status (build-plan step 5)."""
from __future__ import annotations

from datetime import date
from typing import Any

from nicegui import ui

from core.context import AppContext
from services.attendance import STATUS_AR, STATUS_CYCLE
from services.common import ServiceError, month_key, today
from ui import components as C
from ui.components import DateField, card, guarded, ok, parse_time
from ui.layout import COLORS

CELL = {  # status -> (label, background, text colour)
    None: ("—", "#F3F4F6", "#9CA3AF"),
    "present": ("حاضر", "#DCFCE7", "#166534"),
    "absent": ("غائب", "#FEE2E2", "#991B1B"),
    "late": ("متأخر", "#FEF3C7", "#92400E"),
    "excused": ("بعذر", "#E0E7FF", "#3730A3"),
}
SESSION_AR = {"held": "منفذة", "cancelled": "ملغاة", "postponed": "مؤجلة"}
WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def body(ctx: AppContext) -> None:
    svc = ctx.svc
    sel: dict[str, Any] = {"group": None, "month": month_key(today())}

    def group_options() -> dict[int, str]:
        return {g.group_id: svc.groups.label(g) for g in svc.ledger().groups.values()}

    # ------------------------------------------------------------------ grid
    @ui.refreshable
    def grid_view() -> None:
        gid = sel["group"]
        if not gid:
            C.empty_hint("اختر المجموعة لعرض كشف الحضور", "fact_check")
            return
        data = svc.attendance.grid(gid, sel["month"])
        sessions, students = data["sessions"], data["students"]
        if not sessions:
            C.empty_hint("لا توجد حصص في هذا الشهر — أضف حصة من الزر أعلاه", "event")
            return
        if not students:
            C.empty_hint("لا يوجد طلاب مشتركون في هذه المجموعة", "groups")
            return
        for s in students:
            if s["exceeded"]:
                with ui.row().classes("w-full items-center gap-2 p-3 rounded-lg").style("background:#FEF3C7"):
                    ui.icon("warning", color="warning")
                    ui.label(f"الطالب «{s['name']}» تجاوز حد الغياب المسموح ({s['absences']} غياب)")

        cols = f"minmax(190px,1.4fr) repeat({len(sessions)}, minmax(104px,1fr))"
        with ui.element("div").classes("w-full overflow-auto"):
            with ui.element("div").style(f"display:grid;grid-template-columns:{cols};gap:6px;align-items:center;min-width:100%"):
                ui.label("الطالب").classes("font-bold muted text-sm")
                for se in sessions:                                       # header cells
                    with ui.column().classes("items-center gap-0").style("padding:4px 0"):
                        with ui.row().classes("items-center gap-1 no-wrap"):
                            ui.label(f"{se['date'].day}/{se['date'].month}").classes("font-bold")
                            _session_menu(ctx, se, gid, grid_view.refresh)
                        ui.label(WEEKDAYS[se["date"].weekday()] + (f" {se['time']}" if se["time"] else "")) \
                            .classes("text-xs muted")
                        ui.label(se["instructor"]).classes("text-xs muted")
                        if se["status"] != "held":
                            ui.badge(SESSION_AR[se["status"]], color="negative" if se["status"] == "cancelled" else "warning")
                for s in students:
                    with ui.row().classes("items-center gap-1 no-wrap"):
                        ui.label(s["name"]).classes("font-semibold")
                        if s["exceeded"]:
                            ui.icon("warning", color="warning", size="18px")
                    for se in sessions:
                        status = s["cells"].get(se["session_id"])
                        label, bg, fg = CELL[status]
                        btn = ui.button(label, on_click=lambda _, sid=s["student_id"], ss=se["session_id"], cur=status:
                                        cycle(ss, sid, cur)).props("unelevated no-caps dense").classes("w-full") \
                            .style(f"background:{bg} !important;color:{fg} !important;min-height:34px")
                        if se["status"] != "held":
                            btn.disable()

    @guarded
    def cycle(session_id: int, student_id: int, current) -> None:
        svc.attendance.mark(session_id, student_id, svc.attendance.next_status(current))
        grid_view.refresh()

    # ------------------------------------------------------------------ header
    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("الحضور والغياب", "اضغط على خانة الطالب لتغيير الحالة أو سجل الحضور فورًا برقم الطالب / QR")
        ui.button("حصة جديدة", icon="add", on_click=lambda: _session_dialog(ctx, sel, grid_view.refresh)) \
            .props("unelevated no-caps")
    with card():
        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
            grp_sel = ui.select(group_options(), label="المجموعة", on_change=lambda e: (sel.update(group=e.value), grid_view.refresh())) \
                .props("outlined dense").style("width:320px")
            ui.select(C.month_options(12, 3), value=sel["month"], label="الشهر",
                      on_change=lambda e: grid_view.refresh()).props("outlined dense").style("width:180px") \
                .bind_value(sel, "month")

            qr_in = ui.input("تسجيل حضور سريع (رقم الطالب أو QR)").props("outlined dense").style("width:260px")

            @guarded
            def do_quick_checkin() -> None:
                val = (qr_in.value or "").strip()
                res = svc.attendance.quick_check_in(val, group_id=sel.get("group"))
                qr_in.set_value("")
                if sel.get("group") != res["group_id"]:
                    sel["group"] = res["group_id"]
                    grp_sel.set_value(res["group_id"])
                sel["month"] = f"{res['date']:%Y-%m}"
                grid_view.refresh()
                ok(f"تم تسجيل حضور الطالب «{res['student_name']}» ({res['check_in']}) — متبقي {res['remaining_lessons']} حصص")

            qr_in.on("keydown.enter", do_quick_checkin)
            ui.button("تسجيل حضور فوري", icon="qr_code_scanner", on_click=do_quick_checkin) \
                .props("outline no-caps dense color=positive")

            ui.space()
            for st in STATUS_CYCLE:
                label, bg, fg = CELL[st]
                ui.label(label).classes("px-3 py-1 rounded-lg text-sm").style(f"background:{bg};color:{fg}")
        grid_view()


def _session_menu(ctx: AppContext, se: dict, gid: int, refresh) -> None:
    with ui.button(icon="more_vert").props("flat round dense size=sm color=grey-7"):
        with ui.menu():
            @guarded
            def all_present() -> None:
                n = ctx.svc.attendance.mark_all_present(se["session_id"], gid)
                ok(f"تم تسجيل {n} طالب حاضرًا")
                refresh()

            @guarded
            def set_status(status: str) -> None:
                ctx.svc.attendance.set_session_status(se["session_id"], status)
                ok("تم تحديث حالة الحصة")
                if status == "held":
                    _check_4_lesson_alert(ctx, gid)
                refresh()
            if se["status"] == "held":
                ui.menu_item("تحديد الكل حاضر", on_click=all_present)
                ui.menu_item("أوقات الدخول وملاحظات الحضور", on_click=lambda: _details_dialog(ctx, se["session_id"], gid, refresh))
                ui.menu_item("إلغاء الحصة", on_click=lambda: set_status("cancelled"))
                ui.menu_item("تأجيل الحصة", on_click=lambda: set_status("postponed"))
            else:
                ui.menu_item("إعادة تفعيل الحصة", on_click=lambda: set_status("held"))


def _details_dialog(ctx: AppContext, session_id: int, gid: int, refresh) -> None:
    svc = ctx.svc
    led = svc.ledger()
    enrs = [e for e in led.enrollments if e.group_id == gid and e.status in ("active", "paused")]
    existing = {(a.session_id, a.student_id): a for a in svc.attendance._records() if a.session_id == session_id}
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:680px;max-width:96vw"):
        ui.label("تفاصيل الحضور (وقت الدخول/الخروج والملاحظات)").classes("text-lg font-bold")
        edits: list[tuple[int, Any, Any, Any, Any]] = []
        with ui.column().classes("w-full gap-2 max-h-96 overflow-auto"):
            for e in enrs:
                st = led.students.get(e.student_id)
                if not st:
                    continue
                rec = existing.get((session_id, st.student_id))
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    ui.label(st.name_ar).classes("font-semibold").style("width:180px;flex:none")
                    status_sel = ui.select(STATUS_AR, value=rec.status if rec else "present", label="الحالة") \
                        .props("outlined dense").style("width:110px")
                    cin = C.time_input("دخول", f"{rec.check_in:%H:%M}" if rec and rec.check_in else "", "95px")
                    cout = C.time_input("خروج", f"{rec.check_out:%H:%M}" if rec and rec.check_out else "", "95px")
                    note = ui.input("ملاحظة", value=(rec.notes or "") if rec else "").props("outlined dense").classes("flex-1")
                    edits.append((st.student_id, status_sel, cin, cout, note))
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                for sid, st_sel, cin, cout, note in edits:
                    svc.attendance.mark(
                        session_id, sid, st_sel.value,
                        notes=(note.value or "").strip() or None,
                        check_in=parse_time(cin.value, required=False),
                        check_out=parse_time(cout.value, required=False),
                    )
                d.close()
                ok("تم حفظ تفاصيل الحضور")
                refresh()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _session_dialog(ctx: AppContext, sel: dict, refresh) -> None:
    svc = ctx.svc
    if not sel["group"]:
        ui.notify("اختر المجموعة أولًا.", type="warning", position="top")
        return
    g = svc.ledger().groups[sel["group"]]
    instructors = {i.instructor_id: i.name for i in svc.ledger().instructors.values() if i.status == "active"}
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:460px;max-width:96vw"):
        ui.label("حصة جديدة").classes("text-lg font-bold")
        ui.label(svc.groups.label(g)).classes("muted text-sm")
        when = DateField("التاريخ", today(), width="100%")
        with ui.row().classes("gap-3 w-full no-wrap"):
            t1 = C.time_input("من", "17:00", "100%")
            t2 = C.time_input("إلى", "18:30", "100%")
        instr = ui.select(instructors, label="المدرب", value=g.instructor_id).props("outlined dense").classes("w-full")
        level = ui.input("المقرر / المستوى", value=f"{g.cost_center} - {g.level}" if g.level else g.cost_center) \
            .props("outlined dense").classes("w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                svc.attendance.create_session(g.group_id, when.get() or today(), parse_time(t1.value), parse_time(t2.value),
                                              instr.value, level.value, "held")
                d.close()
                ok("تمت إضافة الحصة")
                _check_4_lesson_alert(ctx, g.group_id)
                sel["month"] = f"{(when.get() or today()):%Y-%m}"
                refresh()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _check_4_lesson_alert(ctx: AppContext, gid: int) -> None:
    try:
        from services.common import money
        ms = [m for m in ctx.svc.instructors.pending_4_lesson_milestones() if m["group_id"] == gid]
        for m in ms:
            ui.notify(
                f"حان موعد صرف راتب المدرب «{m['instructor_name']}» لمجموعة «{m['group_label']}»: أتم 4 حصص بمبلغ {money(m['amount'])} ج.م",
                type="warning", position="top", timeout=12000, close_button="إغلاق"
            )
    except Exception:
        pass
