"""Users + audit log + backups (owner)."""
from __future__ import annotations

from nicegui import ui

import config
from core.audit import Action
from core.context import AppContext
from core.schemas import Role, Sheet
from ui import components as C
from ui.components import card, col, data_table, guarded, ok, set_rows

ACTION_AR = {"create": "إضافة", "update": "تعديل", "login": "دخول", "login_failed": "دخول فاشل", "logout": "خروج",
             "auto_logout": "خروج تلقائي", "export_pdf": "تصدير PDF", "password_changed": "تغيير كلمة المرور",
             "setup": "إعداد النظام"}


def body(ctx: AppContext) -> None:
    f = {"q": "", "action": ""}

    # ------------------------------------------------------------------ users
    def users_rows() -> list[dict]:
        rows = []
        for u in ctx.auth.list_users():
            r_val = str(u.role.value if hasattr(u.role, "value") else u.role)
            if r_val == Role.OWNER.value:
                access_summary = "صلاحية كاملة (كل الصفحات)"
            else:
                feats = ctx.auth.parse_permissions(u.permissions) if u.permissions else ctx.auth.default_features_for_role(u.role)
                labels = [config.FEATURE_LABELS_AR.get(k, k) for k in feats if k in config.FEATURE_LABELS_AR]
                access_summary = "، ".join(labels) if labels else "بدون صلاحيات"
            rows.append(dict(
                username=u.username,
                role_code=r_val,
                role=config.ROLE_LABELS_AR.get(r_val, r_val),
                access=access_summary,
                status_label="نشط" if getattr(u, "status", "active") != "inactive" else "موقوف",
                status_color="positive" if getattr(u, "status", "active") != "inactive" else "negative",
                created=str(u.created_at.date()) if u.created_at else "",
                raw_permissions=u.permissions or "",
                raw_status=getattr(u, "status", "active") or "active",
            ))
        return rows

    C.section_title("المستخدمون وسجل العمليات", "إدارة حسابات المستخدمين والأدوار وصلاحيات الوصول والبرامج التعليمية والنسخ الاحتياطية")
    with card("المستخدمون وصلاحيات الوصول"):
        ui.button("مستخدم جديد", icon="person_add", on_click=lambda: _user_dialog(ctx, lambda: set_rows(ut, users_rows()))) \
            .props("outline no-caps dense")
        ut = data_table([col("username", "اسم المستخدم"), col("role", "الدور الوظيفي"),
                         col("access", "الصفحات المسموحة"), col("status_label", "الحالة"),
                         col("created", "تاريخ الإنشاء"), col("actions", "")],
                        users_rows(), "username", no_data="لا يوجد مستخدمون")
        C.badge_cell(ut, "status_label", "status_color", "status_label")
        C.action_buttons(ut, [
            ("access", "tune", "تعديل الدور والصلاحيات", "secondary"),
            ("reset", "lock_reset", "إعادة تعيين كلمة المرور", "primary"),
        ])
        ut.on("access", lambda e: _access_dialog(ctx, e.args, lambda: set_rows(ut, users_rows())))
        ut.on("reset", lambda e: _reset_dialog(ctx, e.args["username"]))

    # ------------------------------------------------------------------ educational programs (admin)
    with card("إدارة البرامج التعليمية (إضافة / حذف البرامج)"):
        with ui.row().classes("w-full items-center gap-3"):
            new_prog_in = ui.input("اسم البرنامج التعليمي الجديد (مثال: تطوير الويب / جرافيك)") \
                .props("outlined dense").style("width:320px")

            @guarded
            def add_prog() -> None:
                val = (new_prog_in.value or "").strip()
                ctx.svc.groups.add_program(val)
                ctx.audit.log(Action.CREATE, "Programs", val, after={"program": val})
                new_prog_in.set_value("")
                set_rows(pt, ctx.svc.groups.program_stats())
                ok(f"تمت إضافة البرنامج التعليمي «{val}»")

            new_prog_in.on("keydown.enter", add_prog)
            ui.button("إضافة برنامج تعليمي", icon="add_circle", on_click=add_prog).props("unelevated no-caps dense color=primary")

        pt = data_table(
            [col("name", "اسم البرنامج التعليمي"), col("groups", "عدد المجموعات"),
             col("students", "عدد الطلاب المشتركين"), col("actions", "")],
            ctx.svc.groups.program_stats(), "name", page_size=10, no_data="لا توجد برامج تعليمية مسجلة",
        )
        C.action_buttons(pt, [("del_prog", "delete", "حذف البرنامج", "negative")])

        @guarded
        def del_prog(e) -> None:
            pname = e.args["name"]
            ctx.svc.groups.delete_program(pname)
            ctx.audit.log(Action.UPDATE, "Programs", pname, before={"program": pname}, after={"deleted": True})
            set_rows(pt, ctx.svc.groups.program_stats())
            ok(f"تم حذف البرنامج التعليمي «{pname}»")

        pt.on("del_prog", del_prog)

    # ------------------------------------------------------------------ backups
    with card("النسخ الاحتياطية وقاعدة البيانات"):
        backups = ctx.repo.list_backups()
        with ui.row().classes("items-center gap-4 flex-wrap"):
            ui.label(f"عدد النسخ: {len(backups)}").classes("text-sm")
            ui.label(f"آخر نسخة: {backups[0][0]:%Y-%m-%d %H:%M}" if backups else "لا توجد نسخ بعد").classes("text-sm muted")
            ui.label(str(config.BACKUP_DIR)).classes("text-xs muted ltr")

            @guarded
            def make_backup() -> None:
                path = ctx.repo.backup()
                ok("تم إنشاء نسخة احتياطية")
                ui.navigate.reload()

            @guarded
            def export_excel() -> None:
                path = ctx.repo.export_excel_snapshot()
                C.pdf_dialog(path, "تم تصدير نسخة Excel كاملة من قاعدة البيانات")

            ui.button("نسخة احتياطية الآن", icon="backup", on_click=make_backup).props("outline no-caps dense")
            ui.button("تصدير نسخة Excel كاملة", icon="table_view", on_click=export_excel).props("unelevated no-caps dense")

        if backups:
            b_opts = {str(p): f"{dt:%Y-%m-%d %H:%M:%S} — {p.name}" for dt, p in backups}
            with ui.row().classes("items-center gap-3 mt-2 flex-wrap"):
                b_sel = ui.select(b_opts, value=str(backups[0][1]), label="اختر نسخة احتياطية للاستعادة") \
                    .props("outlined dense").style("width:360px")

                @guarded
                def restore_now() -> None:
                    from pathlib import Path
                    sel_p = Path(b_sel.value)
                    ctx.repo.restore_backup(sel_p)
                    ctx.audit.log(Action.UPDATE, "Database", sel_p.name, after={"restored_backup": str(sel_p)})
                    ok(f"تم استعادة النسخة الاحتياطية «{sel_p.name}» بنجاح")
                    ui.navigate.reload()

                ui.button("استعادة النسخة الاحتياطية", icon="settings_backup_restore", on_click=restore_now) \
                    .props("outline no-caps dense color=warning")

    # ------------------------------------------------------------------ audit log
    def audit_rows() -> list[dict]:
        from services.common import normalize_ar
        out = []
        for a in ctx.audit.recent(500):
            if f["action"] and a.action != f["action"]:
                continue
            hay = normalize_ar(f"{a.user} {a.sheet} {a.record_id} {a.action} {a.before or ''} {a.after or ''}")
            if f["q"] and normalize_ar(f["q"]) not in hay:
                continue
            out.append(dict(k=f"{a.timestamp}{a.record_id}{a.action}{len(out)}", time=f"{a.timestamp:%Y-%m-%d %H:%M:%S}",
                            user=a.user, action=ACTION_AR.get(a.action, a.action), sheet=a.sheet or "—",
                            record=str(a.record_id or ""), after=(a.after or "")[:140]))
        return out

    with card("سجل العمليات (آخر 500)"):
        with ui.row().classes("w-full items-center gap-3"):
            C.search_box("بحث في السجل", lambda v: (f.update(q=v), set_rows(at, audit_rows())), "300px")
            opts = {"": "كل العمليات"}
            opts.update(ACTION_AR)
            ui.select(opts, value="", label="العملية", on_change=lambda e: (f.update(action=e.value or ""), set_rows(at, audit_rows()))) \
                .props("outlined dense").style("width:200px")
        at = data_table([col("time", "الوقت"), col("user", "المستخدم"), col("action", "العملية"), col("sheet", "الورقة"),
                         col("record", "السجل"), col("after", "التفاصيل")], audit_rows(), "k", page_size=15,
                        no_data="لا توجد عمليات")


def _permissions_selector(ctx: AppContext, initial_role: str, initial_perms: set[str] | None = None):
    """Renders role toggle + per-feature checkboxes. Returns (role_toggle, get_selected_features)."""
    role_opts = {
        Role.RECEPTIONIST.value: "موظف استقبال",
        Role.ACCOUNTANT.value: "محاسب",
        Role.CUSTOM.value: "مخصص",
        Role.OWNER.value: "مالك (كامل الصلاحيات)",
    }
    checks: dict[str, ui.checkbox] = {}
    init_set = initial_perms if initial_perms is not None else ctx.auth.default_features_for_role(Role(initial_role))

    def on_role_change(e) -> None:
        r = e.value
        perms_box.set_visibility(r != Role.OWNER.value)
        if r in (Role.RECEPTIONIST.value, Role.ACCOUNTANT.value):
            defaults = ctx.auth.default_features_for_role(Role(r))
            for k, cb in checks.items():
                cb.set_value(k in defaults)

    role = ui.toggle(role_opts, value=initial_role, on_change=on_role_change) \
        .props("no-caps unelevated toggle-color=primary")
    with ui.column().classes("w-full gap-1 p-3 rounded-lg").style("background:#F9FAFB;border:1px solid #E5E7EB") as perms_box:
        ui.label("تحديد الصفحات والصلاحيات المسموحة لهذا المستخدم:").classes("text-xs font-bold muted")
        with ui.row().classes("w-full gap-x-4 gap-y-1"):
            for feat_key, feat_label in config.FEATURE_LABELS_AR.items():
                checks[feat_key] = ui.checkbox(feat_label, value=(feat_key in init_set)).props("dense")
    perms_box.set_visibility(initial_role != Role.OWNER.value)

    def get_features() -> list[str] | None:
        if role.value == Role.OWNER.value:
            return None
        selected = [k for k, cb in checks.items() if cb.value]
        defaults = ctx.auth.default_features_for_role(Role(role.value))
        if set(selected) == defaults and role.value != Role.CUSTOM.value:
            return None
        return selected

    return role, get_features


def _user_dialog(ctx: AppContext, on_saved) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:520px;max-width:96vw"):
        ui.label("مستخدم جديد").classes("text-lg font-bold")
        name = ui.input("اسم المستخدم (3 أحرف على الأقل)").props("outlined dense").classes("w-full")
        pw = ui.input("كلمة المرور", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
        ui.label("الدور الوظيفي ومستوى الصلاحية").classes("text-sm muted")
        role, get_features = _permissions_selector(ctx, Role.RECEPTIONIST.value)
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.auth.create_user(name.value or "", pw.value or "", Role(role.value), permissions=get_features())
                d.close()
                ok("تم إنشاء المستخدم")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _access_dialog(ctx: AppContext, row: dict, on_saved) -> None:
    username = row["username"]
    cur_role = row.get("role_code") or Role.RECEPTIONIST.value
    raw_perms = row.get("raw_permissions") or ""
    init_perms = ctx.auth.parse_permissions(raw_perms) if raw_perms else ctx.auth.default_features_for_role(Role(cur_role))
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:520px;max-width:96vw"):
        ui.label(f"تعديل الدور والصلاحيات — «{username}»").classes("text-lg font-bold")
        role, get_features = _permissions_selector(ctx, cur_role, init_perms)
        status_toggle = ui.toggle({"active": "حساب نشط", "inactive": "حساب موقوف"},
                                  value=row.get("raw_status", "active")) \
            .props("no-caps unelevated toggle-color=primary")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                feats = get_features()
                if feats is None and role.value != Role.OWNER.value:
                    feats = sorted(ctx.auth.default_features_for_role(Role(role.value)))
                ctx.auth.update_user_access(username, Role(role.value), permissions=feats, status=status_toggle.value)
                d.close()
                ok("تم تحديث صلاحيات المستخدم")
                on_saved()
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()


def _reset_dialog(ctx: AppContext, username: str) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("width:420px;max-width:96vw"):
        ui.label(f"إعادة تعيين كلمة مرور «{username}»").classes("text-lg font-bold")
        pw = ui.input("كلمة المرور الجديدة", password=True, password_toggle_button=True).props("outlined dense").classes("w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            @guarded
            def save() -> None:
                ctx.auth.reset_password(username, pw.value or "")
                d.close()
                ok("تم تغيير كلمة المرور")
            ui.button("حفظ", on_click=save).props("unelevated no-caps")
    d.open()
