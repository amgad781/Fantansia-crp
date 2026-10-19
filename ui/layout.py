"""RTL application shell: theme, right-hand sidebar, top bar, route registry."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from fastapi.responses import RedirectResponse
from nicegui import app, ui

import config
from core.audit import Action
from core.auth import AuthError
from core.context import AppContext
from core.excel_repo import RepoError
from core.schemas import Role

# ----------------------------------------------------------------------------
# Design tokens (Fantasia Logo Palette: Vibrant Orange #F05500 + Deep Navy #0A194E)
# ----------------------------------------------------------------------------
COLORS = dict(primary="#F05500", primary_light="#FFF4ED", accent="#0A194E",
              navy="#0A194E", navy_light="#EEF2FF",
              success="#16A34A", warning="#D97706", danger="#DC2626",
              bg="#F8FAFC", text="#0F172A", muted="#64748B")

FONT_STACK = "'Cairo','Tajawal','Segoe UI',Tahoma,Arial,sans-serif"


def setup_global_head() -> None:
    """Call ONCE at startup (before ui.run): RTL, font, CSS tokens, activity pings."""
    font_face = ""
    if config.FONT_UI_FILE.exists():
        font_face = ("@font-face{font-family:'Cairo';font-weight:200 1000;font-display:swap;"
                     "src:url('/assets/fonts/%s') format('truetype');}" % config.FONT_UI_FILE.name)
    ui.add_head_html(f"""
<script>
  document.documentElement.setAttribute('dir','rtl');
  document.documentElement.setAttribute('lang','ar');
  (function(){{
    const ping = () => {{ if (window.emitEvent) emitEvent('fantasia_activity'); }};
    ['click','keydown','mousemove','touchstart'].forEach(
      e => window.addEventListener(e, ping, {{passive:true}}));
  }})();
</script>
<style>
  {font_face}
  :root {{
    --c-primary:{COLORS['primary']}; --c-primary-light:{COLORS['primary_light']};
    --c-navy:{COLORS['navy']}; --c-navy-light:{COLORS['navy_light']};
    --c-bg:{COLORS['bg']}; --c-text:{COLORS['text']}; --c-muted:{COLORS['muted']};
    --radius-card:14px; --radius-input:10px;
  }}
  html, body, button, input, textarea, select, .q-btn, .q-field {{ font-family:{FONT_STACK} !important; }}
  body {{ background:var(--c-bg); color:var(--c-text); font-variant-numeric:lining-nums; }}
  .q-field--outlined .q-field__control {{ border-radius:var(--radius-input); background:#fff; }}
  .card {{ background:#fff; border-radius:var(--radius-card); border:1px solid #E2E8F0;
           box-shadow:0 4px 14px -2px rgba(10,25,78,.06), 0 2px 4px -2px rgba(10,25,78,.04);
           transition:box-shadow .2s ease, transform .2s ease; }}
  .nav-item {{ border-radius:10px; margin:3px 10px; min-height:44px; color:var(--c-navy);
               font-weight:600; transition:all .15s ease; }}
  .nav-item:hover {{ background:var(--c-navy-light); color:var(--c-primary); }}
  .nav-active {{ background:var(--c-primary-light) !important; color:var(--c-primary) !important;
                 font-weight:800; box-shadow:inset -3.5px 0 0 var(--c-primary); }}
  .muted {{ color:var(--c-muted); }}
  .q-table th, .q-table td {{ text-align:start !important; padding:10px 14px !important; }}
  .q-table thead th {{ font-weight:700; color:var(--c-navy); background:#F1F5F9; font-size:13px; }}
  .q-table tbody tr:hover {{ background:#FFF7ED !important; }}
  .stat-label {{ color:var(--c-muted); font-size:13px; font-weight:600; }}
  .stat-value {{ font-size:25px; font-weight:800; line-height:1.25; color:var(--c-navy); }}
  .ltr {{ direction:ltr; unicode-bidi:isolate; display:inline-block; }}
</style>
""", shared=True)


def apply_page_theme() -> None:
    """Quasar palette – must be called inside each page function."""
    ui.colors(primary=COLORS["primary"], secondary=COLORS["accent"], accent=COLORS["accent"],
              positive=COLORS["success"], negative=COLORS["danger"], warning=COLORS["warning"])


# ----------------------------------------------------------------------------
# Navigation
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: str            # Material icon name
    route: str
    feature: str         # permission key in core.auth.PERMISSIONS
    step: Optional[int]  # build-plan step that implements the page


NAV_ITEMS: list[NavItem] = [
    NavItem("dashboard",   "لوحة التحكم",       "dashboard",      "/dashboard",   "dashboard",   9),
    NavItem("students",    "الطلاب",            "groups",         "/students",    "students",    2),
    NavItem("new_student", "تسجيل طالب جديد",   "person_add",     "/students/new", "students",   2),
    NavItem("receipts",    "الإيصالات",         "receipt_long",   "/receipts",    "receipts",    3),
    NavItem("settlements", "متابعة الفيزا والبنك", "credit_card",  "/settlements", "settlements", 3),
    NavItem("attendance",  "الحضور والغياب",    "fact_check",     "/attendance",  "attendance",  5),
    NavItem("collection",  "التحصيل",           "payments",       "/collection",  "collection",  4),
    NavItem("groups",      "المجموعات",         "diversity_3",    "/groups",      "groups",      4),
    NavItem("instructors", "المدرّبون",         "badge",          "/instructors", "instructors", 6),
    NavItem("employees",   "الموظفون والرواتب", "work",           "/employees",   "employees",   7),
    NavItem("journal",     "اليومية",           "menu_book",      "/journal",     "journal",     8),
    NavItem("reports",     "التقارير",          "bar_chart",      "/reports",     "reports",     9),
    NavItem("users",       "المستخدمون وسجل العمليات", "admin_panel_settings", "/users", "users", None),
]


def home_route(role: Optional[Role | str], session=None) -> str:
    if session is not None and session.is_authenticated:
        if session.can("dashboard") and role == Role.OWNER:
            return "/dashboard"
        for nav in NAV_ITEMS:
            if session.can(nav.feature):
                return nav.route
    return "/dashboard" if role == Role.OWNER else "/students"


def notify_error(e: Exception) -> None:
    ui.notify(str(e), type="negative", position="top", multi_line=True, timeout=6000)


# ----------------------------------------------------------------------------
# Shell
# ----------------------------------------------------------------------------
def _logo(size_cls: str = "w-11 h-11") -> None:
    if config.LOGO_FILE.exists():
        ui.image("/assets/logo.png").classes(f"{size_cls} rounded-xl object-contain bg-white p-0.5") \
            .style("border:1px solid #F1F5F9;box-shadow:0 1px 3px rgba(0,0,0,.06)")
    else:
        with ui.element("div").classes(f"{size_cls} rounded-xl flex items-center justify-center") \
                .style(f"background:{COLORS['primary']};color:#fff;font-weight:800;font-size:20px"):
            ui.label("F")


def _change_password_dialog(ctx: AppContext) -> None:
    role_key = str(ctx.session.role.value if hasattr(ctx.session.role, "value") else (ctx.session.role or ""))
    role_label = config.ROLE_LABELS_AR.get(role_key, role_key)
    with ui.dialog() as d, ui.card().classes("p-6 gap-3").style("width:430px;max-width:96vw"):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("lock_reset", size="24px").style(f"color:{COLORS['primary']}")
                ui.label("تغيير كلمة المرور").classes("text-lg font-bold").style(f"color:{COLORS['navy']}")
            ui.badge(f"{ctx.session.username} ({role_label})", color="secondary").props("text-color=white")
        ui.label(f"أدخل كلمة المرور الحالية ثم كلمة المرور الجديدة ({config.MIN_PASSWORD_LEN} أحرف على الأقل).") \
            .classes("text-xs muted")
        old_pw = ui.input("كلمة المرور الحالية", password=True, password_toggle_button=True) \
            .props("outlined dense autofocus").classes("w-full")
        new_pw = ui.input("كلمة المرور الجديدة", password=True, password_toggle_button=True) \
            .props("outlined dense").classes("w-full")
        new_pw2 = ui.input("تأكيد كلمة المرور الجديدة", password=True, password_toggle_button=True) \
            .props("outlined dense").classes("w-full")

        def save() -> None:
            if (new_pw.value or "") != (new_pw2.value or ""):
                notify_error(AuthError("كلمتا المرور غير متطابقتين."))
                return
            try:
                ctx.auth.change_password(ctx.session.username, old_pw.value or "", new_pw.value or "")
            except (AuthError, RepoError) as e:
                notify_error(e)
                return
            d.close()
            ui.notify("تم تغيير كلمة المرور بنجاح", type="positive", position="top")

        old_pw.on("keydown.enter", save)
        new_pw.on("keydown.enter", save)
        new_pw2.on("keydown.enter", save)
        with ui.row().classes("justify-end gap-2 w-full pt-1"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")
            ui.button("حفظ كلمة المرور", icon="check", on_click=save).props("unelevated no-caps color=primary")
    d.open()


@contextmanager
def app_shell(ctx: AppContext, active: NavItem) -> Iterator[None]:
    apply_page_theme()
    session = ctx.session

    def logout(reason: str = Action.LOGOUT) -> None:
        try:
            ctx.auth.logout(reason)
        except RepoError as e:                      # session is cleared anyway
            notify_error(e)
        ui.navigate.to("/login")

    # --- keep-alive / idle logout ------------------------------------------
    ui.on("fantasia_activity", lambda: session.touch(), throttle=10)

    def check_idle() -> None:
        if session.idle_seconds() > config.AUTO_LOGOUT_MINUTES * 60:
            logout(Action.AUTO_LOGOUT)
    ui.timer(30, check_idle)

    # --- sidebar (physically on the RIGHT) -------------------------------------
    with ui.left_drawer(value=True, bordered=True).props("width=265 show-if-above") \
            .classes("bg-white") as drawer:
        with ui.row().classes("items-center gap-3 px-4 py-3.5 w-full no-wrap") \
                .style(f"background:linear-gradient(135deg, {COLORS['navy']} 0%, #152C70 100%)"):
            _logo("w-12 h-12")
            with ui.column().classes("gap-0"):
                ui.label(config.APP_NAME_AR).classes("font-extrabold text-base leading-tight") \
                    .style("color:#FFFFFF")
                ui.label("We make the next step").classes("text-xs font-semibold leading-tight") \
                    .style(f"color:{COLORS['primary']}")
        ui.separator()
        with ui.list().props("padding"):
            for nav in NAV_ITEMS:
                if not session.can(nav.feature):
                    continue
                is_active = nav.key == active.key
                props = "clickable" + (" active active-class=nav-active" if is_active else "")
                with ui.item(on_click=lambda r=nav.route: ui.navigate.to(r)) \
                        .props(props).classes("nav-item"):
                    with ui.item_section().props("avatar"):
                        ui.icon(nav.icon)
                    with ui.item_section():
                        ui.label(nav.label)
        ui.space()
        ui.separator()
        with ui.list().props("dense padding"):
            with ui.item(on_click=lambda: _change_password_dialog(ctx)).props("clickable").classes("nav-item"):
                with ui.item_section().props("avatar"):
                    ui.icon("key")
                with ui.item_section():
                    ui.label("تغيير كلمة المرور")
        with ui.row().classes("items-center justify-between px-4 py-2.5 w-full"):
            ui.label(f"الإصدار {config.APP_VERSION}").classes("text-xs muted")
            ui.badge("SQLite", color="secondary").props("text-color=white")

    # --- top bar -----------------------------------------------------------------
    with ui.header().classes("bg-white items-center justify-between px-5") \
            .style(f"height:64px;color:{COLORS['navy']};border-bottom:2px solid {COLORS['primary_light']};box-shadow:none"):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="menu", on_click=drawer.toggle).props("flat round dense color=secondary") \
                .classes("lg:hidden")
            ui.icon(active.icon, size="22px").style(f"color:{COLORS['primary']}")
            ui.label(active.label).classes("text-lg font-bold").style(f"color:{COLORS['navy']}")
        with ui.row().classes("items-center gap-2"):
            with ui.column().classes("gap-0 items-end"):
                ui.label(session.username).classes("text-sm font-bold leading-tight").style(f"color:{COLORS['navy']}")
                role_key = str(session.role.value if hasattr(session.role, "value") else (session.role or ""))
                ui.label(config.ROLE_LABELS_AR.get(role_key, role_key)).classes("text-xs muted leading-tight")
            ui.button("تغيير كلمة المرور", icon="key", on_click=lambda: _change_password_dialog(ctx)) \
                .props("outline dense no-caps color=secondary").tooltip("تغيير كلمة المرور")
            ui.button(icon="logout", on_click=lambda: logout()) \
                .props("flat round dense color=primary").tooltip("تسجيل الخروج")

    # --- content -------------------------------------------------------------------
    with ui.column().classes("w-full gap-4 p-6").style("max-width:1440px;margin-inline:auto"):
        yield


# ----------------------------------------------------------------------------
# Route registry
# ----------------------------------------------------------------------------
Body = Callable[[AppContext], None]


def placeholder_body(nav: NavItem) -> Body:
    def body(ctx: AppContext) -> None:
        with ui.column().classes("card w-full items-center justify-center gap-2 p-12"):
            ui.icon("construction", size="48px").classes("muted")
            ui.label(f"صفحة «{nav.label}» قيد الإنشاء").classes("text-lg font-bold")
            if nav.step is not None:
                ui.label(f"ستُنفَّذ في الخطوة {nav.step} من خطة البناء").classes("muted")
    return body


def nav_by_key(key: str) -> NavItem:
    return next(n for n in NAV_ITEMS if n.key == key)


def page_guard(ctx: AppContext, feature: str):
    """None when the user may see the page, otherwise the redirect to return from the page function."""
    if not ctx.session.is_authenticated:
        return RedirectResponse("/login")
    if not ctx.session.can(feature):
        return RedirectResponse(home_route(ctx.session.role, ctx.session))
    ctx.session.touch()
    return None


def render_page(ctx: AppContext, nav_key: str, body: Callable[..., None], *args):
    """Guard + shell + friendly error box. Return its value from the @ui.page function."""
    nav = nav_by_key(nav_key)
    redirect = page_guard(ctx, nav.feature)
    if redirect is not None:
        return redirect
    with app_shell(ctx, nav):
        try:
            body(ctx, *args)
        except RepoError as e:
            with ui.column().classes("card w-full p-6"):
                ui.label(str(e)).classes("text-negative whitespace-pre-line")
    return None


def register_pages(ctx: AppContext, bodies: Optional[dict[str, Body]] = None) -> None:
    """Register one protected route per nav item. Pass real bodies as steps are built."""
    bodies = bodies or {}

    def make(nav: NavItem, body: Body) -> None:
        @ui.page(nav.route)
        def page():
            return render_page(ctx, nav.key, body)

    for nav in NAV_ITEMS:
        make(nav, bodies.get(nav.key) or placeholder_body(nav))

    @ui.page("/")
    def root():
        if ctx.session.is_authenticated:
            return RedirectResponse(home_route(ctx.session.role, ctx.session))
        return RedirectResponse("/login")
