"""UI smoke + interaction tests (NiceGUI user simulation):  python -m pytest -q tests/test_ui.py"""
import asyncio
from datetime import date, time, timedelta

import pytest
from nicegui import ui
from nicegui.testing import User

import config
from core.audit import AuditService
from core.auth import AuthService, Session
from core.context import AppContext
from core.excel_repo import ExcelRepository
from services.registry import Services
from ui.app import register_all

TODAY = date.today()
OWNER_PW, RECEP_PW = "Owner#12345", "Recep#12345"


@pytest.fixture
def app(user: User, tmp_path, monkeypatch):
    for name in ("RECEIPTS_DIR", "INSTRUCTORS_DIR", "EMPLOYEES_DIR", "EXPORT_DIR", "BACKUP_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    session = Session()
    repo = ExcelRepository(tmp_path / "academy.xlsx", tmp_path / "backups", current_user=lambda: session.username)
    repo.ensure_workbook()
    audit = AuditService(repo, lambda: session.username)
    ctx = AppContext(repo, audit, session, AuthService(repo, audit, session),
                     svc=Services(repo, lambda: session.username))
    ctx.auth.first_run_setup(("owner", OWNER_PW), ("reception", RECEP_PW))
    register_all(ctx)
    return ctx


def populate(ctx):
    s = ctx.svc
    iid = s.instructors.add("كريم حسن", "01199998888", 120)
    gid = s.groups.add("بايثون أونلاين", "برمجة", "مبتدئ", iid, "سبت وثلاثاء", "online")
    sid = s.students.register(dict(name_ar="عمر أحمد سمير", parent_mobile="01012345678"),
                              enrollment=dict(group_id=gid, start_date=TODAY - timedelta(days=40), monthly_fee=1500, months=3))
    eid = s.ledger().student_enrollments(sid)[0].enrollment_id
    s.receipts.create(student_id=sid, enrollment_id=eid, amount=1500, cost_center="بايثون أونلاين", description="اشتراك")
    sess = s.attendance.create_session(gid, TODAY, time(17, 0), time(18, 30))
    s.attendance.mark(sess, sid, "present")
    s.employees.add("منى السيد", "موظفة استقبال", "01000000000", 4000)
    s.journal.add_expense(100, "أدوات مكتبية", "أدوات ومستلزمات")
    return dict(iid=iid, gid=gid, sid=sid, eid=eid, session=sess)


OWNER_PAGES = {"/dashboard": "لوحة التحكم", "/students": "الطلاب", "/students/new": "تسجيل طالب جديد",
               "/receipts": "الإيصالات", "/attendance": "الحضور والغياب", "/collection": "التحصيل",
               "/groups": "المجموعات", "/instructors": "المدرّبون", "/employees": "الموظفون والرواتب",
               "/journal": "اليومية", "/reports": "التقارير", "/users": "المستخدمون وسجل العمليات"}


async def test_unauthenticated_redirects_to_login(user: User, app):
    await user.open("/students")
    await user.should_see("تسجيل الدخول")


@pytest.mark.parametrize("route,title", list(OWNER_PAGES.items()))
async def test_owner_pages_load_empty(user: User, app, route, title):
    app.auth.login("owner", OWNER_PW)
    await user.open(route)
    await user.should_see(title)


@pytest.mark.parametrize("route,title", list(OWNER_PAGES.items()))
async def test_owner_pages_load_with_data(user: User, app, route, title):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open(route)
    await user.should_see(title)


async def test_receptionist_cannot_open_owner_pages(user: User, app):
    app.auth.login("reception", RECEP_PW)
    for route in ("/instructors", "/employees", "/reports", "/users", "/dashboard"):
        await user.open(route)
        await user.should_see("الطلاب")                     # redirected home (students)
        await user.should_not_see("الموظفون والرواتب")
    for route in ("/students", "/students/new", "/receipts", "/attendance", "/collection", "/groups", "/journal"):
        await user.open(route)
        await user.should_see(OWNER_PAGES[route])


async def test_students_table_rows_and_profile(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/students")
    table = user.find(kind=ui.table).elements.pop()
    assert len(table.rows) == 1
    row = table.rows[0]
    # enrolled 40 days ago, 3 x 1500 fees, one receipt (month 1 paid -> 4 lessons), 1 attended -> 3 left
    assert row["name"] == "عمر أحمد سمير" and row["lessons"] == 3 and row["lessons_label"] == "3 حصص"
    assert row["balance"] == 3000 and row["paid"] == 1500 and row["lessons_color"] == "positive"
    await user.open(f"/students/{ids['sid']}")
    await user.should_see("عمر أحمد سمير")
    await user.should_see("الاشتراك والرسوم")
    await user.open("/students/9999")
    await user.should_see("الطالب غير موجود")


async def test_students_live_search_filters(user: User, app):
    populate(app)
    app.svc.students.register(dict(name_ar="سلمى محمود علي", parent_mobile="01155556666"))
    app.auth.login("reception", RECEP_PW)
    await user.open("/students")
    table = user.find(kind=ui.table).elements.pop()
    assert len(table.rows) == 2
    box = user.find(kind=ui.input, marker=None).elements  # first input is the search box
    search = next(e for e in box if "ابحث" in (e.props.get("placeholder") or ""))
    search.set_value("سلمى")
    assert [r["name"] for r in table.rows] == ["سلمى محمود علي"]
    search.set_value("")
    assert len(table.rows) == 2


async def test_receipts_page_prefills_from_overdue_and_lists(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    app.nav["student_id"] = ids["sid"]
    await user.open("/receipts")
    await user.should_see("رقم الإيصال القادم: 221")
    table = user.find(kind=ui.table).elements.pop()
    assert len(table.rows) == 1 and table.rows[0]["serial"] == 220
    # the form pre-filled the next unpaid month (1500)
    nums = [e for e in user.find(kind=ui.number).elements if e.props.get("label") == "المبلغ *"]
    assert nums and nums[0].value == 1500


async def test_new_student_form_creates_student(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/students/new")
    await user.should_see("أولًا: البيانات الشخصية")
    await user.should_see("ثانيًا: استبيان تحديد الميول والتوصية الذكية بالبرنامج")
    await user.should_see("ثالثًا: التقييم والتوجيه")
    await user.should_see("رابعًا: الاشتراك في مجموعة")


async def test_instructors_page_shows_salary_to_date(user: User, app):
    ids = populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/instructors")
    table = user.find(kind=ui.table).elements.pop()
    assert len(table.rows) == 1
    r = table.rows[0]
    assert r["name"] == "كريم حسن" and r["hours"] == 1.5 and r["gross"] == 180 and r["net_due"] == 180


async def test_employees_and_journal_pages_data(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/employees")
    table = user.find(kind=ui.table).elements.pop()
    assert table.rows[0]["name"] == "منى السيد" and table.rows[0]["net"] == 4000
    await user.open("/journal")
    await user.should_see("رصيد الدرج اليوم")
    await user.open("/reports")
    await user.should_see("الإيرادات مقابل التكاليف شهريًا")


async def test_dashboard_numbers(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/dashboard")
    await user.should_see("إيرادات اليوم")
    await user.should_see("1,500 ج.م")


# ===================================================================== interactions
from nicegui.events import GenericEventArguments, handle_event          # noqa: E402

from core.schemas import Sheet                                           # noqa: E402


def fire(el, event: str, args) -> None:
    """Emit a custom Quasar event (e.g. a row-action button) on an element."""
    hit = False
    for l in list(el._event_listeners.values()):
        if l.type == event:
            hit = True
            handle_event(l.handler, GenericEventArguments(sender=el, client=el.client, args=args))
    assert hit, f"no listener for {event}"


def _in_open_ui(el) -> bool:
    """False when the element lives inside a dialog that is currently closed (the simulator keeps those)."""
    p = el
    while p is not None:
        if isinstance(p, ui.dialog) and not p.value:
            return False
        slot = getattr(p, "parent_slot", None)
        p = slot.parent if slot else None
    return True


def field(user: User, kind, label: str):
    """The (most recently created) visible input/select/number with this label."""
    hits = [e for e in user.find(kind=kind).elements if e.props.get("label") == label and _in_open_ui(e)]
    assert hits, f"{kind.__name__} '{label}' not found"
    return hits[-1]


def press(user: User, label: str, kind=ui.button) -> None:
    """Click the visible button whose label is EXACTLY `label` (ignores buttons in closed dialogs)."""
    from nicegui.testing.user_interaction import UserInteraction
    hits = [e for e in user.find(kind=kind, content=label).elements
            if _in_open_ui(e) and e.props.get("label") == label]
    assert hits, f"button '{label}' not found"
    UserInteraction(user, {hits[-1]}, label).click()


def press_menu(user: User, label: str) -> None:
    """Click a ui.menu_item (its text lives in a child section)."""
    for el in user.find(content=label).elements:
        p = el
        while p is not None and not any(l.type == "click" for l in p._event_listeners.values()):
            slot = getattr(p, "parent_slot", None)
            p = slot.parent if slot else None
        if p is not None and _in_open_ui(p):
            fire(p, "click", None)
            return
    raise AssertionError(f"menu item '{label}' not found")


async def test_attendance_click_cycles_status(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/attendance")
    field(user, ui.select, "المجموعة").set_value(ids["gid"])
    await user.should_see("عمر أحمد سمير")
    user.find(kind=ui.button, content="حاضر").click()                      # present -> absent
    att = app.repo.get(Sheet.ATTENDANCE, session_id=ids["session"], student_id=ids["sid"])
    assert att.status == "absent"
    await asyncio.sleep(0.3)                                                # grid re-renders after the click
    user.find(kind=ui.button, content="غائب").click()                      # absent -> late
    assert app.repo.get(Sheet.ATTENDANCE, session_id=ids["session"], student_id=ids["sid"]).status == "late"


async def test_receipt_saved_from_the_form(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    app.nav["student_id"] = ids["sid"]
    await user.open("/receipts")
    user.find("حفظ الإيصال").click()
    await user.should_see("تم حفظ الإيصال رقم 221")
    rec = app.repo.get(Sheet.RECEIPTS, serial=221)
    assert rec.amount == 1500 and rec.student_id == ids["sid"] and rec.user == "reception"
    # export + cancel through the table actions
    table = user.find(kind=ui.table).elements.pop()
    fire(table, "pdf", {"serial": 221})
    assert (config.RECEIPTS_DIR / "receipt_221.pdf").exists()
    fire(table, "cancel", {"serial": 221})
    await user.should_see("إلغاء الإيصال رقم 221")
    field(user, ui.input, "السبب").set_value("خطأ في المبلغ")
    user.find("تأكيد الإلغاء").click()
    assert app.repo.get(Sheet.RECEIPTS, serial=221).status == "reversed"


async def test_receipt_form_shows_business_errors(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/receipts")
    user.find("حفظ الإيصال").click()                                         # no student chosen
    await asyncio.sleep(0.1)
    assert user.notify.contains("اختر الطالب")
    assert len(app.repo.read(Sheet.RECEIPTS)) == 1


async def test_instructor_pay_and_pdf_from_the_table(user: User, app):
    ids = populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/instructors")
    table = user.find(kind=ui.table).elements.pop()
    fire(table, "pdf", {"instructor_id": ids["iid"]})
    assert list(config.INSTRUCTORS_DIR.glob("instructor_*.pdf"))
    fire(table, "pay", table.rows[0])
    await user.should_see("تسجيل دفعة — كريم حسن")
    field(user, ui.number, "المبلغ المدفوع").set_value(100)
    user.find("تأكيد الدفع").click()
    pays = app.repo.read(Sheet.INSTRUCTOR_PAYMENTS)
    assert len(pays) == 1 and pays[0].net == 100 and pays[0].status == "paid" and pays[0].approved_by == "owner"
    assert table.rows[0]["paid"] == 100 and table.rows[0]["net_due"] == 80


async def test_employee_adjust_pay_and_payslip(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/employees")
    table = user.find(kind=ui.table).elements.pop()
    fire(table, "adjust", table.rows[0])
    await user.should_see("مكافآت وخصومات — منى السيد")
    field(user, ui.number, "المكافآت").set_value(500)
    field(user, ui.number, "الخصومات").set_value(200)
    user.find("حفظ").click()
    assert table.rows[0]["net"] == 4300
    fire(table, "pay", table.rows[0])
    user.find("تأكيد الصرف").click()
    assert table.rows[0]["status"] == "paid"
    fire(table, "slip", table.rows[0])
    assert list(config.EMPLOYEES_DIR.glob("payslip_*.pdf"))
    fire(table, "reverse", table.rows[0])
    user.find("إلغاء الصرف").click()
    assert table.rows[0]["status"] == "unsaved"

    # Pay with bonus and deduction entered directly in pay dialog
    fire(table, "pay", table.rows[0])
    field(user, ui.number, "المكافآت").set_value(600)
    field(user, ui.number, "الخصومات").set_value(150)
    press(user, "تأكيد الصرف")
    assert table.rows[0]["status"] == "paid"
    assert table.rows[0]["bonuses"] == 600
    assert table.rows[0]["deductions"] == 150
    assert table.rows[0]["net"] == 4450


async def test_employee_quick_adjust_dialog(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/employees")
    table = user.find(kind=ui.table).elements.pop()
    press(user, "مكافأة / خصم")
    await user.should_see("تسجيل مكافأة أو خصم")
    field(user, ui.number, "المكافآت").set_value(350)
    field(user, ui.number, "الخصومات").set_value(50)
    press(user, "حفظ")
    assert table.rows[0]["bonuses"] == 350
    assert table.rows[0]["deductions"] == 50
    assert table.rows[0]["net"] == 4300


async def test_journal_adds_expense_and_balance(user: User, app):
    populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/journal")
    await user.should_see("1,400 ج.م")                                      # 1500 cash in - 100 expense


async def test_register_student_through_the_form(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/students/new")
    field(user, ui.input, "اسم الطالب (ثلاثي بالعربية) *").set_value("ياسين محمد قنديل")
    field(user, ui.input, "موبايل ولي الأمر *").set_value("01234567890")
    field(user, ui.select, "المجموعة").set_value(ids["gid"])
    field(user, ui.number, "الاشتراك الشهري").set_value(1100)
    user.find("حفظ وإنشاء ملف الطالب").click()
    await user.should_see("ياسين محمد قنديل")
    studs = [s for s in app.repo.read(Sheet.STUDENTS) if s.name_ar == "ياسين محمد قنديل"]
    assert len(studs) == 1 and studs[0].parent_whatsapp == "01234567890"       # whatsapp defaults to mobile
    assert len([f for f in app.repo.read(Sheet.FEE_SCHEDULE) if f.amount_due == 1100]) == 1


async def test_register_student_validation_error_is_a_toast(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/students/new")
    field(user, ui.input, "اسم الطالب (ثلاثي بالعربية) *").set_value("عمر")
    user.find("حفظ وإنشاء ملف الطالب").click()                               # group not chosen yet
    await asyncio.sleep(0.1)
    assert user.notify.contains("اختر المجموعة")
    field(user, ui.select, "المجموعة").set_value(ids["gid"])
    user.find("حفظ وإنشاء ملف الطالب").click()
    await asyncio.sleep(0.1)
    assert user.notify.contains("اكتب اسم الطالب ثنائيًا على الأقل")
    assert len(app.repo.read(Sheet.STUDENTS)) == 1


async def test_groups_page_creates_group(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/groups")
    user.find("مجموعة جديدة").click()
    await user.should_see("البرنامج / مركز التكلفة *")
    field(user, ui.select, "البرنامج / مركز التكلفة *").set_value("أردوينو")
    user.find("حفظ").click()
    assert any(g.cost_center == "أردوينو" for g in app.repo.read(Sheet.GROUPS))


async def test_users_page_audit_and_new_user(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/users")
    await user.should_see("سجل العمليات")
    tables = user.find(kind=ui.table).elements
    assert any("username" in t.rows[0] for t in tables if t.rows)


# ================================================================ dialogs & secondary flows
async def test_student_profile_dialogs(user: User, app):
    ids = populate(app)
    g2 = app.svc.groups.add("أردوينو", "أردوينو", "مبتدئ", ids["iid"], "", "onsite")
    app.auth.login("reception", RECEP_PW)
    await user.open(f"/students/{ids['sid']}")
    # edit personal data
    press(user, "تعديل")
    await user.should_see("تعديل بيانات الطالب")
    field(user, ui.input, "اسم المدرسة").set_value("مدرسة النيل")
    press(user, "حفظ")
    await asyncio.sleep(0.4)                                                 # simulated page reload settles
    assert app.svc.ledger().students[ids["sid"]].school == "مدرسة النيل"
    # lessons dialog
    await user.open(f"/students/{ids['sid']}")
    press(user, "الحصص")
    field(user, ui.number, "عدد الحصص").set_value(10)
    press(user, "حفظ")
    await asyncio.sleep(0.4)                                                 # simulated page reload settles
    assert app.repo.get(Sheet.ENROLLMENTS, enrollment_id=ids["eid"]).lessons_purchased == 10
    # add fee
    await user.open(f"/students/{ids['sid']}")
    press(user, "رسوم")
    field(user, ui.number, "المبلغ").set_value(250)
    press(user, "حفظ")                                                        # same month + item already exists
    await asyncio.sleep(0.1)
    assert user.notify.contains("مسجل بالفعل")
    assert not any(f.amount_due == 250 for f in app.repo.read(Sheet.FEE_SCHEDULE))
    field(user, ui.select, "البند").set_value("other")
    press(user, "حفظ")
    await asyncio.sleep(0.4)                                                 # simulated page reload settles
    assert any(f.amount_due == 250 and f.item == "other" for f in app.repo.read(Sheet.FEE_SCHEDULE))
    # new enrollment in another group
    await user.open(f"/students/{ids['sid']}")
    press(user, "اشتراك جديد في مجموعة")
    field(user, ui.select, "المجموعة").set_value(g2)
    field(user, ui.number, "قيمة الاشتراك الشهري").set_value(900)
    press(user, "حفظ")
    await asyncio.sleep(0.4)                                                 # simulated page reload settles
    assert len(app.svc.ledger().student_enrollments(ids["sid"])) == 2
    # assessment dialog
    await user.open(f"/students/{ids['sid']}")
    press(user, "تقييم جديد / تعديل")
    await user.should_see("تقييم الطالب")
    press(user, "حفظ")
    await asyncio.sleep(0.4)                                                 # simulated page reload settles
    assert app.svc.students.latest_assessment(ids["sid"]) is not None
    # certificate PDF, previous certificates tab, QR ID card PDF, and WhatsApp templates dialog
    await user.open(f"/students/{ids['sid']}")
    await user.should_see("الشهادات السابقة")
    press(user, "شهادة إتمام PDF")
    await user.should_see("إصدار شهادة إتمام مستوى PDF")
    press(user, "تصدير الشهادة PDF")
    await user.should_see("تم إصدار وحفظ شهادة إتمام المستوى PDF")
    certs = app.svc.students.list_certificates(ids["sid"])
    assert len(certs) == 1 and certs[0]["serial"].startswith("CERT-")
    await user.open(f"/students/{ids['sid']}")
    press(user, "بطاقة العضوية QR")
    await user.should_see("تم تصدير بطاقة عضوية الطالب بـ QR Code")
    await user.open(f"/students/{ids['sid']}")
    press(user, "قوالب واتساب")
    await user.should_see("قوالب رسائل واتساب جاهزة")


async def test_attendance_session_dialog_and_menu(user: User, app):
    ids = populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/attendance")
    press(user, "حصة جديدة")
    assert user.notify.contains("اختر المجموعة")                           # no group yet
    field(user, ui.select, "المجموعة").set_value(ids["gid"])
    await asyncio.sleep(0.2)
    press(user, "حصة جديدة")
    await user.should_see("المقرر / المستوى")
    field(user, ui.input, "من").set_value("10:00")
    field(user, ui.input, "إلى").set_value("11:00")
    press(user, "حفظ")
    assert len(app.repo.read(Sheet.SESSIONS)) == 2
    await asyncio.sleep(0.3)
    press_menu(user, "تحديد الكل حاضر")
    await asyncio.sleep(0.1)
    press_menu(user, "إلغاء الحصة")
    sessions = app.repo.read(Sheet.SESSIONS)
    assert any(s.status == "cancelled" for s in sessions)


async def test_collection_actions(user: User, app, monkeypatch):
    ids = populate(app)
    opened = []
    from export import service as ex
    monkeypatch.setattr(ex, "open_url", lambda url: opened.append(url))
    app.auth.login("reception", RECEP_PW)
    await user.open("/collection")
    await user.should_see("المتأخرات")
    tables = user.find(kind=ui.table).elements
    overdue = next(t for t in tables if t.rows and "months_label" in t.rows[0])
    assert overdue.rows[0]["name"] == "عمر أحمد سمير" and overdue.rows[0]["amount"] >= 1500
    fire(overdue, "remind", overdue.rows[0])
    assert opened and opened[0].startswith("https://wa.me/20101234")
    fire(overdue, "pay", overdue.rows[0])
    assert app.nav["student_id"] == ids["sid"]


async def test_instructor_drawer_add_and_rate(user: User, app):
    ids = populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/instructors")
    table = user.find(kind=ui.table).elements.pop()
    fire(table, "details", table.rows[0])
    await user.should_see("الحصص المنفذة")
    await user.should_see("تعديل السعر")
    press(user, "تعديل السعر")
    await user.should_see("تعديل سعر الساعة — كريم حسن")
    field(user, ui.number, "سعر الساعة الجديد").set_value(150)
    press(user, "حفظ")
    assert app.repo.get(Sheet.INSTRUCTORS, instructor_id=ids["iid"]).hourly_rate == 150
    press(user, "مدرب جديد")
    field(user, ui.input, "اسم المدرب *").set_value("سارة علي")
    field(user, ui.number, "سعر الساعة *").set_value(100)
    press(user, "حفظ")
    assert any(i.name == "سارة علي" for i in app.repo.read(Sheet.INSTRUCTORS))
    press(user, "تصدير كشوف الجميع PDF")
    assert len(list(config.INSTRUCTORS_DIR.glob("instructor_*.pdf"))) >= 1


async def test_journal_dialogs(user: User, app):
    populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/journal")
    press(user, "مصروف جديد")
    field(user, ui.number, "المبلغ *").set_value(50)
    field(user, ui.input, "البيان *").set_value("مياه")
    press(user, "حفظ")
    assert sum(1 for e in app.repo.read(Sheet.EXPENSES) if e.description == "مياه") == 1
    await asyncio.sleep(0.2)
    await user.should_see("1,350 ج.م")                                       # 1500 - 100 - 50
    press(user, "إضافة")                               # petty cash / handover / non-cash buttons
    await asyncio.sleep(0.1)


async def test_journal_category_dialog_ui(user: User, app):
    populate(app)
    app.auth.login("reception", RECEP_PW)
    await user.open("/journal")
    press(user, "إضافة تصنيف جديد")
    await asyncio.sleep(0.1)
    field(user, ui.input, "اسم التصنيف الجديد").set_value("مشتريات هدايا")
    press(user, "إضافة تصنيف")
    await asyncio.sleep(0.1)
    assert "مشتريات هدايا" in app.svc.journal.list_categories()


async def test_reports_filters_and_export(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/reports")
    field(user, ui.select, "البرنامج").set_value("بايثون أونلاين")
    await asyncio.sleep(0.2)
    await user.should_see("الإيراد حسب البرنامج")
    user.find("تصدير Excel").click()
    assert list(config.EXPORT_DIR.glob("report_*.xlsx"))
    field(user, ui.select, "من شهر").set_value(f"{TODAY.year + 1}-01")        # start after end -> friendly message
    await asyncio.sleep(0.2)
    await user.should_see("بداية الفترة بعد نهايتها")


async def test_users_dialogs_and_backup(user: User, app):
    populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/users")
    press(user, "مستخدم جديد")
    field(user, ui.input, "اسم المستخدم (3 أحرف على الأقل)").set_value("newuser")
    field(user, ui.input, "كلمة المرور").set_value("Another#1234")
    press(user, "حفظ")
    assert any(u.username == "newuser" for u in app.auth.list_users())
    tables = user.find(kind=ui.table).elements
    ut = next(t for t in tables if t.rows and "username" in t.rows[0])
    fire(ut, "reset", {"username": "newuser"})
    await user.should_see("إعادة تعيين كلمة مرور «newuser»")
    field(user, ui.input, "كلمة المرور الجديدة").set_value("Reset#98765")
    press(user, "حفظ")
    app.auth.login("newuser", "Reset#98765")
    app.auth.logout()
    app.auth.login("owner", OWNER_PW)
    press(user, "نسخة احتياطية الآن")
    assert app.repo.list_backups()


async def test_group_edit(user: User, app):
    ids = populate(app)
    app.auth.login("owner", OWNER_PW)
    await user.open("/groups")
    table = user.find(kind=ui.table).elements.pop()
    assert table.rows[0]["students"] == 1 and table.rows[0]["instructor"] == "كريم حسن"
    fire(table, "edit", table.rows[0])
    await user.should_see("تعديل المجموعة")
    field(user, ui.input, "الموعد (مثال: السبت والثلاثاء 5–6 م)").set_value("الجمعة 4م")
    press(user, "حفظ")
    assert app.repo.get(Sheet.GROUPS, group_id=ids["gid"]).schedule == "الجمعة 4م"


async def test_students_row_actions(user: User, app, monkeypatch):
    ids = populate(app)
    opened = []
    from export import service as ex
    monkeypatch.setattr(ex, "open_url", lambda url: opened.append(url))
    app.auth.login("reception", RECEP_PW)
    await user.open("/students")
    table = user.find(kind=ui.table).elements.pop()
    fire(table, "wa", {"id": ids["sid"]})
    assert opened and "wa.me/2010123" in opened[0]
    fire(table, "receipt", {"id": ids["sid"]})
    assert (config.RECEIPTS_DIR / "receipt_220.pdf").exists()
    fire(table, "pay", {"id": ids["sid"]})
    assert app.nav["student_id"] == ids["sid"]
