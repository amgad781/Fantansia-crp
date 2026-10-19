"""Login page + first-run setup (no default passwords are ever shipped)."""
from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

import config
from core.auth import AuthError
from core.context import AppContext
from core.excel_repo import RepoError
from ui.layout import COLORS, apply_page_theme, home_route


def register_login(ctx: AppContext) -> None:
    @ui.page("/login")
    def login_page():
        apply_page_theme()
        if ctx.session.is_authenticated:
            return RedirectResponse(home_route(ctx.session.role))

        try:
            first_run = not ctx.auth.has_users()
        except RepoError as e:
            first_run = False
            startup_error = str(e)
        else:
            startup_error = ""

        ui.query("body").style(f"background:linear-gradient(135deg, {COLORS['navy']} 0%, #152C70 55%, {COLORS['primary']} 100%)")
        with ui.column().classes("w-full min-h-screen items-center justify-center p-4"):
            with ui.column().classes("card items-stretch gap-4 p-8").style("width:420px;max-width:100%"):
                with ui.column().classes("items-center gap-1 w-full"):
                    if config.LOGO_FILE.exists():
                        ui.image("/assets/logo.png").classes("w-20 h-20 object-contain")
                    ui.label(config.APP_NAME_AR).classes("text-2xl font-extrabold") \
                        .style(f"color:{COLORS['primary']}")
                    ui.label("إعداد أول تشغيل" if first_run else "تسجيل الدخول").classes("muted")

                error = ui.label(startup_error).classes("text-negative text-sm whitespace-pre-line")
                error.set_visibility(bool(startup_error))

                def fail(e: Exception) -> None:
                    error.set_text(str(e))
                    error.set_visibility(True)

                if first_run:
                    _setup_form(ctx, fail)
                else:
                    _login_form(ctx, fail)


def _pw(label: str):
    return ui.input(label, password=True, password_toggle_button=True).props("outlined dense").classes("w-full")


def _login_form(ctx: AppContext, fail) -> None:
    username = ui.input("اسم المستخدم").props("outlined dense autofocus").classes("w-full")
    password = _pw("كلمة المرور")

    def submit() -> None:
        try:
            user = ctx.auth.login(username.value or "", password.value or "")
        except (AuthError, RepoError) as e:
            password.set_value("")
            fail(e)
            return
        ui.navigate.to(home_route(user.role))

    password.on("keydown.enter", submit)
    username.on("keydown.enter", submit)
    ui.button("دخول", on_click=submit).props("unelevated no-caps").classes("w-full").style("height:44px")
    with ui.row().classes("w-full justify-center pt-1"):
        ui.button("تغيير كلمة المرور لحسابي", icon="key",
                  on_click=lambda: _login_change_pw_dialog(ctx, username.value or "")) \
            .props("flat dense no-caps color=secondary")


def _login_change_pw_dialog(ctx: AppContext, prefill_username: str = "") -> None:
    with ui.dialog() as d, ui.card().classes("p-6 gap-3").style("width:420px;max-width:96vw"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("lock_reset", size="24px").style(f"color:{COLORS['primary']}")
            ui.label("تغيير كلمة المرور").classes("text-lg font-bold").style(f"color:{COLORS['navy']}")
        ui.label(f"أدخل اسم المستخدم وكلمة المرور الحالية ثم الجديدة ({config.MIN_PASSWORD_LEN} أحرف على الأقل).") \
            .classes("text-xs muted")
        err_lbl = ui.label("").classes("text-negative text-xs")
        err_lbl.set_visibility(False)
        u_in = ui.input("اسم المستخدم", value=prefill_username).props("outlined dense autofocus").classes("w-full")
        old_pw = _pw("كلمة المرور الحالية")
        new_pw = _pw("كلمة المرور الجديدة")
        new_pw2 = _pw("تأكيد كلمة المرور الجديدة")

        def save() -> None:
            if (new_pw.value or "") != (new_pw2.value or ""):
                err_lbl.set_text("كلمتا المرور غير متطابقتين.")
                err_lbl.set_visibility(True)
                return
            try:
                ctx.auth.change_password(u_in.value or "", old_pw.value or "", new_pw.value or "")
            except (AuthError, RepoError) as e:
                err_lbl.set_text(str(e))
                err_lbl.set_visibility(True)
                return
            d.close()
            ui.notify("تم تغيير كلمة المرور بنجاح. يمكنك تسجيل الدخول الآن.", type="positive", position="top")

        new_pw2.on("keydown.enter", save)
        with ui.row().classes("justify-end gap-2 w-full pt-1"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")
            ui.button("حفظ كلمة المرور", icon="check", on_click=save).props("unelevated no-caps color=primary")
    d.open()



def _setup_form(ctx: AppContext, fail) -> None:
    ui.label("أنشئ حساب المالك وحساب موظف الاستقبال").classes("text-sm muted")
    ui.label("حساب المالك").classes("font-bold")
    o_user = ui.input("اسم المستخدم", value="owner").props("outlined dense").classes("w-full")
    o_pw, o_pw2 = _pw("كلمة المرور"), _pw("تأكيد كلمة المرور")
    ui.label("حساب موظف الاستقبال").classes("font-bold")
    r_user = ui.input("اسم المستخدم", value="reception").props("outlined dense").classes("w-full")
    r_pw, r_pw2 = _pw("كلمة المرور"), _pw("تأكيد كلمة المرور")

    def submit() -> None:
        if o_pw.value != o_pw2.value or r_pw.value != r_pw2.value:
            return fail(AuthError("كلمتا المرور غير متطابقتين."))
        try:
            ctx.auth.first_run_setup((o_user.value or "", o_pw.value or ""),
                                     (r_user.value or "", r_pw.value or ""))
        except (AuthError, RepoError) as e:
            return fail(e)
        ui.notify("تم إنشاء الحسابين. سجّل الدخول الآن.", type="positive")
        ui.navigate.reload()

    ui.button("حفظ وبدء الاستخدام", on_click=submit).props("unelevated no-caps") \
        .classes("w-full").style("height:44px")
