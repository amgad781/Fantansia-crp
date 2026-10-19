"""Reusable UI building blocks (consistent look across every page)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time
from functools import wraps
from typing import Any, Callable, Iterator, Optional

from nicegui import ui

import config
from core.auth import AuthError
from core.excel_repo import RepoError
from export import service as ex
from services.common import MONTHS_AR, ServiceError, month_key, month_label, shift_month
from ui.layout import COLORS, notify_error

USER_ERRORS = (ServiceError, RepoError, AuthError)


# ------------------------------------------------------------------ errors / feedback
def guarded(fn: Callable) -> Callable:
    """Run a UI action; show Arabic business/storage errors as a toast instead of crashing."""
    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except USER_ERRORS as e:
            notify_error(e)
            return None
    return wrapper


def ok(message: str) -> None:
    ui.notify(message, type="positive", position="top")


def lessons_text(n: Optional[int]) -> str:
    if n is None:
        return "—"
    if n <= 0:
        return "لا حصص" if n == 0 else f"{abs(n)} زيادة"
    if n == 1:
        return "حصة واحدة"
    return f"{n} حصص" if n <= 10 else f"{n} حصة"


# ----------------------------------------------------------------------- containers
@contextmanager
def card(title: Optional[str] = None, classes: str = "", style: str = "") -> Iterator[ui.column]:
    with ui.column().classes(f"card w-full p-4 gap-3 {classes}").style(style) as c:
        if title:
            ui.label(title).classes("font-bold text-base")
        yield c


def stat_card(label: str, value: str, icon: str, tint: str = "primary") -> None:
    color = {"primary": COLORS["primary"], "success": COLORS["success"], "warning": COLORS["warning"],
             "accent": COLORS["accent"]}.get(tint, COLORS["primary"])
    bg = COLORS["primary_light"] if tint == "primary" else "#F3F4F6"
    with ui.row().classes("card items-center gap-4 p-4 no-wrap").style("flex:1 1 200px;min-width:200px"):
        with ui.element("div").classes("rounded-xl flex items-center justify-center") \
                .style(f"width:48px;height:48px;background:{bg};color:{color}"):
            ui.icon(icon, size="26px")
        with ui.column().classes("gap-0"):
            ui.label(label).classes("stat-label")
            ui.label(value).classes("stat-value")


def section_title(text: str, subtitle: str = "") -> None:
    with ui.column().classes("gap-0"):
        ui.label(text).classes("text-xl font-bold")
        if subtitle:
            ui.label(subtitle).classes("muted text-sm")


def empty_hint(text: str, icon: str = "inbox") -> None:
    with ui.column().classes("w-full items-center py-8 gap-1"):
        ui.icon(icon, size="40px").classes("muted")
        ui.label(text).classes("muted")


# ---------------------------------------------------------------------------- inputs
def search_box(placeholder: str, on_change: Callable[[str], None], width: str = "320px") -> ui.input:
    inp = ui.input(placeholder=placeholder, on_change=lambda e: on_change(e.value or "")) \
        .props("outlined dense clearable debounce=250").style(f"width:{width};max-width:100%")
    with inp.add_slot("prepend"):
        ui.icon("search")
    return inp


class DateField:
    """Text field (yyyy-mm-dd) with a calendar popup. .get() -> date | None."""

    def __init__(self, label: str, value: Optional[date] = None, on_change: Optional[Callable[[], None]] = None,
                 width: str = "170px", clearable: bool = False):
        self.input = ui.input(label, value=value.isoformat() if value else "") \
            .props("outlined dense" + (" clearable" if clearable else "")).style(f"width:{width}")
        with self.input:
            with ui.menu().props("no-parent-event") as menu:
                with ui.date().bind_value(self.input):
                    with ui.row().classes("justify-end"):
                        ui.button("إغلاق", on_click=menu.close).props("flat")
        with self.input.add_slot("append"):
            ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
        if on_change:
            self.input.on_value_change(lambda e: on_change())

    def get(self) -> Optional[date]:
        v = (self.input.value or "").strip()
        if not v:
            return None
        try:
            return date.fromisoformat(v)
        except ValueError:
            raise ServiceError("صيغة التاريخ غير صحيحة (اكتب yyyy-mm-dd).")

    def set(self, d: Optional[date]) -> None:
        self.input.set_value(d.isoformat() if d else "")


def time_input(label: str, value: str = "", width: str = "120px") -> ui.input:
    return ui.input(label, value=value, placeholder="17:00") \
        .props('outlined dense mask="##:##"').style(f"width:{width}")


def parse_time(v: Optional[str], required: bool = True) -> Optional[time]:
    v = (v or "").strip()
    if not v:
        if required:
            raise ServiceError("اكتب الوقت بصيغة 17:00.")
        return None
    try:
        h, m = v.split(":")
        return time(int(h), int(m))
    except Exception:
        raise ServiceError("وقت غير صحيح — اكتبه بصيغة 17:00.")


def num_input(label: str, value: Optional[float] = None, width: str = "150px", suffix: str = "",
              min_: Optional[float] = 0) -> ui.number:
    n = ui.number(label, value=value, min=min_, format="%g").props("outlined dense").style(f"width:{width}")
    if suffix:
        with n.add_slot("append"):
            ui.label(suffix).classes("text-sm muted")
    return n


def month_options(back: int = 18, forward: int = 6) -> dict[str, str]:
    cur = month_key(date.today())
    return {m: month_label(m) for m in (shift_month(cur, i) for i in range(forward, -back - 1, -1))}


def choice_cards(options: list[str], value: Optional[str], on_change: Callable[[str], None]) -> Callable[[], Optional[str]]:
    """Row of selectable cards (design: track / age-group chips). Returns a getter."""
    state = {"v": value}
    cards: dict[str, ui.element] = {}

    def paint() -> None:
        for k, el in cards.items():
            sel = k == state["v"]
            el.style(f"border:2px solid {COLORS['primary'] if sel else '#E5E7EB'};"
                     f"background:{COLORS['primary_light'] if sel else '#fff'};"
                     f"color:{COLORS['primary'] if sel else COLORS['text']};font-weight:{700 if sel else 500}")

    def pick(k: str) -> None:
        state["v"] = k
        paint()
        on_change(k)

    with ui.row().classes("gap-2"):
        for opt in options:
            el = ui.element("div").classes("px-4 py-2 rounded-xl cursor-pointer select-none")
            with el:
                ui.label(opt)
            el.on("click", lambda _, k=opt: pick(k))
            cards[opt] = el
    paint()
    return lambda: state["v"]


# ---------------------------------------------------------------------------- dialogs
def confirm_dialog(message: str, on_yes: Callable[[], None], yes_label: str = "تأكيد", danger: bool = False) -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("min-width:360px"):
        ui.label(message).classes("text-base whitespace-pre-line")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إلغاء", on_click=d.close).props("flat no-caps")

            def go() -> None:
                d.close()
                guarded(on_yes)()
            ui.button(yes_label, on_click=go).props("unelevated no-caps" + (" color=negative" if danger else ""))
    d.open()


def reason_dialog(title: str, on_submit: Callable[[str], None], yes_label: str = "تأكيد الإلغاء") -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("min-width:380px"):
        ui.label(title).classes("text-base font-bold")
        reason = ui.input("السبب").props("outlined dense autofocus").classes("w-full")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("رجوع", on_click=d.close).props("flat no-caps")

            @guarded
            def go() -> None:
                if not (reason.value or "").strip():
                    raise ServiceError("اكتب السبب.")
                on_submit(reason.value)
                d.close()
            ui.button(yes_label, on_click=go).props("unelevated no-caps color=negative")
    d.open()


def pdf_dialog(path, title: str = "تم إنشاء الملف") -> None:
    with ui.dialog() as d, ui.card().classes("p-5 gap-3").style("min-width:400px;max-width:90vw"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("task_alt", size="28px").classes("text-positive")
            ui.label(title).classes("text-base font-bold")
        ui.label(str(path)).classes("text-xs muted ltr").style("word-break:break-all")
        with ui.row().classes("justify-end gap-2 w-full"):
            ui.button("إغلاق", on_click=d.close).props("flat no-caps")
            ui.button("فتح المجلد", icon="folder_open", on_click=lambda: ex.open_path(path, folder=True)) \
                .props("outline no-caps")
            ui.button("فتح / طباعة", icon="print", on_click=lambda: ex.open_path(path)).props("unelevated no-caps")
    d.open()


def side_panel() -> tuple[ui.dialog, ui.card]:
    """Slide-in panel (design: instructor drawer). Physical LEFT edge = opposite the right-hand sidebar."""
    d = ui.dialog().props("position=left maximized=false")
    with d:
        c = ui.card().classes("p-5 gap-3 overflow-auto").style(
            "width:620px;max-width:96vw;height:100vh;border-radius:0")
    return d, c


# ----------------------------------------------------------------------------- tables
def col(name: str, label: str, field: Optional[str] = None, sortable: bool = False,
        align: str = "right") -> dict[str, Any]:
    return {"name": name, "label": label, "field": field or name, "align": align, "sortable": sortable}


def data_table(columns: list[dict], rows: list[dict], row_key: str, page_size: int = 15,
               no_data: str = "لا توجد بيانات") -> ui.table:
    t = ui.table(columns=columns, rows=rows, row_key=row_key,
                 pagination={"rowsPerPage": page_size}).classes("w-full").props(
        f'flat dense no-data-label="{no_data}" rows-per-page-label="عدد الصفوف:" '
        f':rows-per-page-options="[10,15,25,50,0]"')
    return t


def set_rows(table: ui.table, rows: list[dict]) -> None:
    table.rows = rows
    table.update()


def action_buttons(table: ui.table, buttons: list[tuple], name: str = "actions") -> None:
    """buttons: (event, icon, tooltip, color[, v-if expression on `props.row`])."""
    html = ""
    for b in buttons:
        event, icon, tip, color = b[:4]
        cond = f' v-if="{b[4]}"' if len(b) > 4 else ""
        html += (f'<q-btn{cond} flat round dense size="sm" color="{color}" icon="{icon}" '
                 f'@click.stop="() => $parent.$emit(\'{event}\', props.row)"><q-tooltip>{tip}</q-tooltip></q-btn>')
    table.add_slot(f"body-cell-{name}", f'<q-td :props="props" auto-width>{html}</q-td>')


def badge_cell(table: ui.table, name: str, color_field: str, label_field: str) -> None:
    table.add_slot(f"body-cell-{name}", f'''<q-td :props="props">
        <q-badge :color="props.row.{color_field}" :label="props.row.{label_field}" class="q-px-sm q-py-xs" />
    </q-td>''')


STATUS_AR = {"active": "نشط", "inactive": "غير نشط", "paused": "متوقف", "completed": "منتهي",
             "cancelled": "ملغي", "reversed": "ملغي", "paid": "مدفوع", "pending": "قيد الصرف",
             "held": "منفذة", "postponed": "مؤجلة", "unsaved": "لم يُسجَّل"}
STATUS_COLOR = {"active": "positive", "paid": "positive", "held": "positive", "inactive": "grey",
                "paused": "warning", "pending": "warning", "postponed": "warning", "completed": "grey",
                "cancelled": "negative", "reversed": "negative", "unsaved": "grey"}
