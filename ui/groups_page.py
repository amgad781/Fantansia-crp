"""Groups (classes): program, level, instructor, schedule, mode."""
from __future__ import annotations

from typing import Any, Optional

from nicegui import ui

import config
from core.context import AppContext
from services.common import ServiceError
from ui import components as C
from ui.components import card, col, data_table, guarded, ok, set_rows

MODE_AR = {"online": "أونلاين", "onsite": "حضوري"}


def _group_dialog(ctx: AppContext, group=None, on_saved=None) -> None:
    svc = ctx.svc
    led = svc.ledger()
    instructors = {i.instructor_id: f"{i.name} ({i.hourly_rate:g} ج.م/س)"
                   for i in led.instructors.values() if i.status == "active"}
    programs = svc.groups.list_programs()
    if group and group.cost_center and group.cost_center not in programs:
        programs.append(group.cost_center)
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:520px;max-width:96vw"):
        ui.label("تعديل المجموعة" if group else "مجموعة جديدة").classes("text-lg font-bold")
        prog = ui.select(programs, label="البرنامج / مركز التكلفة *", value=group.cost_center if group else None,
                         new_value_mode="add-unique", with_input=True).props("outlined dense").classes("w-full")
        track = ui.select(config.TRACKS_AR, label="المسار", value=group.track if group else None,
                          clearable=True).props("outlined dense").classes("w-full")
        level = ui.select(config.LEVELS_AR, label="المستوى", value=group.level if group else None,
                          clearable=True).props("outlined dense").classes("w-full")

        def on_instr_change(e) -> None:
            iid = e.value
            if iid and iid in led.instructors and (rate_inp.value is None or not group):
                rate_inp.set_value(led.instructors[iid].hourly_rate)
            _check_conflicts()

        instr = ui.select(instructors, label="المدرب", value=group.instructor_id if group else None,
                          clearable=True, on_change=on_instr_change).props("outlined dense").classes("w-full")
        init_rate = group.instructor_hourly_rate if group else None
        if init_rate is None and group and group.instructor_id and group.instructor_id in led.instructors:
            init_rate = led.instructors[group.instructor_id].hourly_rate
        rate_inp = C.num_input("سعر ساعة المدرب للمجموعة", init_rate, "100%", "ج.م / ساعة", min_=0)
        if not instructors:
            ui.label("لا يوجد مدربون بعد — يضيفهم المالك من صفحة المدرّبين.").classes("text-sm text-warning")
        sched = ui.input("الموعد (مثال: السبت والثلاثاء 5–6 م)", value=group.schedule if group else "",
                         on_change=lambda _: _check_conflicts()) \
            .props("outlined dense").classes("w-full")
        conflict_lbl = ui.label("").classes("text-xs font-bold text-warning")
        conflict_lbl.set_visibility(False)

        def _check_conflicts() -> None:
            conflicts = svc.groups.check_schedule_conflicts(
                instr.value, sched.value or "", exclude_group_id=group.group_id if group else None
            )
            if conflicts:
                conflict_lbl.set_text(
                    "تنبيه تعارض مواعيد للمدرب مع: " + " | ".join(f"{c['label']} ({c['schedule']})" for c in conflicts)
                )
                conflict_lbl.set_visibility(True)
            else:
                conflict_lbl.set_visibility(False)

        _check_conflicts()
        with ui.row().classes("w-full items-center justify-between gap-3"):
            ui.label("نظام صرف مستحقات المدرب:").classes("text-sm font-semibold")
            pay_cycle = ui.toggle(
                {"monthly": "شهري", "every_4_lessons": "كل 4 حصص"},
                value=getattr(group, "pay_cycle", "monthly") if group else "monthly"
            ).props("no-caps unelevated toggle-color=primary")
        mode = ui.toggle(MODE_AR, value=group.mode if group else "onsite").props("no-caps unelevated toggle-color=primary")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                r_val = float(rate_inp.value) if rate_inp.value is not None else None
                if group:
                    svc.groups.update(group.group_id, dict(
                        cost_center=prog.value, track=track.value, level=level.value,
                        instructor_id=instr.value, instructor_hourly_rate=r_val,
                        pay_cycle=pay_cycle.value,
                        schedule=sched.value, mode=mode.value,
                    ))
                else:
                    svc.groups.add(prog.value or "", track.value or "", level.value or "", instr.value,
                                   sched.value or "", mode.value, instructor_hourly_rate=r_val,
                                   pay_cycle=pay_cycle.value)
                d.close()
                ok("تم الحفظ")
                if on_saved:
                    on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _promote_dialog(ctx: AppContext, group, on_saved=None) -> None:
    if not group:
        return
    svc = ctx.svc
    levels = list(config.LEVELS_AR)
    cur_idx = levels.index(group.level) if group.level in levels else -1
    next_lvl = levels[cur_idx + 1] if 0 <= cur_idx < len(levels) - 1 else (levels[0] if levels else "Level 2")
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:480px;max-width:96vw"):
        ui.label(f"ترقية المجموعة للمستوى التالي — {svc.groups.label(group)}").classes("text-lg font-bold")
        ui.label("سيتم تحديث مستوى المجموعة ويمكنك اختيار تجديد حصص ورسوم الطلاب النشطين تلقائيًا.").classes("text-xs muted")
        lvl_sel = ui.select(levels, label="المستوى الجديد *", value=next_lvl,
                            new_value_mode="add-unique", with_input=True).props("outlined dense").classes("w-full")
        add_les = C.num_input("إضافة حصص لكل طالب نشط", config.LESSONS_PER_MONTH, "100%", "حصة", min_=0)
        fee_in = C.num_input("إضافة رسوم شهرية للمستوى الجديد (اختياري)", 0, "100%", "ج.م", min_=0)
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def do_promote() -> None:
                res = svc.groups.promote_group(
                    group.group_id,
                    lvl_sel.value or "",
                    add_lessons=int(add_les.value or 0),
                    monthly_fee=float(fee_in.value or 0),
                )
                d.close()
                ok(f"تمت ترقية المجموعة إلى «{res['new_level']}» وتحديث {res['students_promoted']} طالب")
                if on_saved:
                    on_saved()

            ui.button("ترقية المجموعة", icon="trending_up", on_click=do_promote).props("unelevated no-caps color=positive")
    d.open()


def _programs_dialog(ctx: AppContext, on_changed=None) -> None:
    from core.audit import Action
    svc = ctx.svc
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:540px;max-width:96vw"):
        ui.label("إدارة البرامج التعليمية (إضافة / حذف)").classes("text-lg font-bold")
        with ui.row().classes("w-full items-center gap-2"):
            new_p = ui.input("اسم البرنامج التعليمي الجديد").props("outlined dense").classes("flex-1")

            @guarded
            def add_p() -> None:
                val = (new_p.value or "").strip()
                svc.groups.add_program(val)
                ctx.audit.log(Action.CREATE, "Programs", val, after={"program": val})
                new_p.set_value("")
                set_rows(pt, svc.groups.program_stats())
                ok(f"تمت إضافة البرنامج «{val}»")
                if on_changed:
                    on_changed()

            new_p.on("keydown.enter", add_p)
            ui.button("إضافة برنامج", icon="add_circle", on_click=add_p).props("unelevated no-caps dense color=primary")

        pt = data_table(
            [col("name", "البرنامج التعليمي"), col("groups", "المجموعات"),
             col("students", "الطلاب"), col("actions", "")],
            svc.groups.program_stats(), "name", page_size=8, no_data="لا توجد برامج مسجلة",
        )
        C.action_buttons(pt, [("del_p", "delete", "حذف البرنامج", "negative")])

        @guarded
        def del_p(e) -> None:
            pname = e.args["name"]
            svc.groups.delete_program(pname)
            ctx.audit.log(Action.UPDATE, "Programs", pname, before={"program": pname}, after={"deleted": True})
            set_rows(pt, svc.groups.program_stats())
            ok(f"تم حذف البرنامج «{pname}»")
            if on_changed:
                on_changed()

        pt.on("del_p", del_p)
        with ui.row().classes("justify-end w-full"):
            ui.button("إغلاق", on_click=d.close).props("flat no-caps")
    d.open()


def body(ctx: AppContext) -> None:
    from core.schemas import Role
    svc = ctx.svc
    flt = {"q": "", "program": "", "mode": ""}

    def _prog_filter_opts() -> dict[str, str]:
        opts = {"": "كل البرامج"}
        for p in svc.groups.list_programs():
            opts[p] = p
        for g in svc.ledger().groups.values():
            if g.cost_center and g.cost_center not in opts:
                opts[g.cost_center] = g.cost_center
        return opts

    def load() -> list[dict[str, Any]]:
        led = svc.ledger()
        counts: dict[int, int] = {}
        for e in led.enrollments:
            if e.status in ("active", "paused"):
                counts[e.group_id] = counts.get(e.group_id, 0) + 1
        rows = []
        from services.common import money, normalize_ar
        for g in led.groups.values():
            if flt["program"] and g.cost_center != flt["program"]:
                continue
            if flt["mode"] and g.mode != flt["mode"]:
                continue
            ins = led.instructors.get(g.instructor_id) if g.instructor_id else None
            eff_rate = g.instructor_hourly_rate if g.instructor_hourly_rate is not None else (ins.hourly_rate if ins else None)
            rate_str = f"{money(eff_rate)} ج.م/س" if eff_rate is not None else "—"
            cycle = getattr(g, "pay_cycle", "monthly") or "monthly"
            cycle_label = "كل 4 حصص" if cycle == "every_4_lessons" else "شهري"
            r = dict(id=g.group_id, program=g.cost_center, track=g.track or "—", level=g.level or "—",
                     instructor=ins.name if ins else "— بدون مدرب —", rate_label=rate_str,
                     pay_cycle_label=cycle_label,
                     schedule=g.schedule or "—", mode=MODE_AR.get(g.mode, g.mode),
                     students=counts.get(g.group_id, 0))
            if flt["q"] and normalize_ar(flt["q"]) not in normalize_ar(" ".join(str(x) for x in r.values())):
                continue
            rows.append(r)
        return sorted(rows, key=lambda r: r["id"])

    def refresh() -> None:
        prog_sel.set_options(_prog_filter_opts(), value=flt["program"])
        set_rows(table, load())

    with ui.row().classes("w-full items-center justify-between"):
        C.section_title("المجموعات", "مجموعات الدراسة المرتبطة بالمدربين وأسعار ساعاتهم والبرامج")
        with ui.row().classes("items-center gap-2"):
            if ctx.session.role == Role.OWNER or ctx.session.can("users"):
                ui.button("إدارة البرامج التعليمية", icon="school",
                          on_click=lambda: _programs_dialog(ctx, refresh)).props("outline no-caps color=secondary")
            ui.button("مجموعة جديدة", icon="add", on_click=lambda: _group_dialog(ctx, None, refresh)).props("unelevated no-caps")
    with card():
        with ui.row().classes("w-full items-center gap-3"):
            C.search_box("ابحث في المجموعات", lambda v: (flt.update(q=v), refresh()), "300px")
            prog_sel = ui.select(_prog_filter_opts(), value="", label="تصفية بالبرنامج",
                                 on_change=lambda e: (flt.update(program=e.value or ""), refresh())) \
                .props("outlined dense").style("width:200px")
            modes = {"": "كل الأنظمة", "onsite": "حضوري", "online": "أونلاين"}
            ui.select(modes, value="", label="النظام",
                      on_change=lambda e: (flt.update(mode=e.value or ""), refresh())) \
                .props("outlined dense").style("width:160px")
        table = data_table([col("id", "#", sortable=True), col("program", "البرنامج", sortable=True),
                            col("track", "المسار"), col("level", "المستوى"), col("instructor", "المدرب"),
                            col("rate_label", "سعر ساعة المدرب"), col("pay_cycle_label", "نظام الصرف"),
                            col("schedule", "الموعد"),
                            col("mode", "النظام"), col("students", "عدد الطلاب"),
                            col("actions", "")], [], "id", no_data="لا توجد مجموعات بعد")
        C.action_buttons(table, [
            ("promote", "trending_up", "ترقية المستوى", "positive"),
            ("edit", "edit", "تعديل", "primary"),
        ])
        table.on("promote", lambda e: _promote_dialog(ctx, svc.ledger().groups.get(e.args["id"]), refresh))
        table.on("edit", lambda e: _group_dialog(ctx, svc.ledger().groups.get(e.args["id"]), refresh))
    refresh()

