"""PDF export tests:  python -m pytest -q tests/test_pdf.py"""
from datetime import date, time, timedelta

import pytest

import config
from core.audit import AuditService
from core.auth import AuthService, Session
from core.context import AppContext
from core.excel_repo import ExcelRepository
from export import pdf_common as P
from export import service as ex
from services.registry import Services

TODAY = date.today()
M0 = f"{TODAY:%Y-%m}"


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    for name in ("RECEIPTS_DIR", "INSTRUCTORS_DIR", "EMPLOYEES_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    session = Session()
    repo = ExcelRepository(tmp_path / "academy.xlsx", tmp_path / "backups", current_user=lambda: "reception")
    repo.ensure_workbook()
    audit = AuditService(repo, lambda: "reception")
    return AppContext(repo, audit, session, AuthService(repo, audit, session),
                      svc=Services(repo, lambda: "reception"))


def _setup(ctx):
    s = ctx.svc
    iid = s.instructors.add("كريم حسن", "01199998888", 120)
    gid = s.groups.add("بايثون أونلاين", "برمجة", "مبتدئ", iid, "", "online")
    sid = s.students.register(dict(name_ar="عمر أحمد سمير"),
                              enrollment=dict(group_id=gid, start_date=TODAY, monthly_fee=1500, months=1))
    eid = s.ledger().student_enrollments(sid)[0].enrollment_id
    s.attendance.create_session(gid, TODAY - timedelta(days=1), time(17, 0), time(18, 30))
    return iid, gid, sid, eid


def _is_pdf(p):
    b = p.read_bytes()
    return b.startswith(b"%PDF") and len(b) > 1500


def test_amount_words():
    assert P.amount_words(1500) == "فقط ألف وخمسمائة جنيه لا غير"
    assert "قرش" in P.amount_words(10.5) and P.amount_words(2) == "فقط جنيهان لا غير"


def test_all_pdfs_are_built_and_audited(ctx):
    iid, gid, sid, eid = _setup(ctx)
    r = ctx.svc.receipts.create(student_id=sid, enrollment_id=eid, amount=1500, cost_center="بايثون أونلاين",
                                description="اشتراك الشهر الأول")
    p = ex.export_receipt(ctx, r.serial)
    assert p.name == f"receipt_{r.serial}.pdf" and _is_pdf(p)
    assert _is_pdf(ex.export_receipt(ctx, r.serial, reprint=True))
    ctx.svc.receipts.reverse(r.serial, "خطأ")
    assert _is_pdf(ex.export_receipt(ctx, r.serial))                      # cancelled watermark version

    first = TODAY.replace(day=1)
    p = ex.export_instructor_statement(ctx, iid, min(first, TODAY - timedelta(days=1)), TODAY)
    assert _is_pdf(p) and "كريم" in p.name

    eid2 = ctx.svc.employees.add("منى السيد", "موظفة استقبال", "", 4000)
    assert _is_pdf(ex.export_payslip(ctx, eid2, M0))
    summary, slips = ex.export_all_payslips(ctx, M0)
    assert _is_pdf(summary) and len(slips) == 1

    actions = [a.action for a in ctx.audit.recent()]
    assert actions.count("export_pdf") >= 6


def test_empty_statement_and_long_table_paginate(ctx):
    iid, gid, sid, eid = _setup(ctx)
    p = ex.export_instructor_statement(ctx, iid, TODAY - timedelta(days=400), TODAY - timedelta(days=300))
    assert _is_pdf(p)                                                      # no sessions -> still valid
    for i in range(60):                                                    # 60 sessions -> multi-page
        day = TODAY - timedelta(days=i % 25 + 1)
        ctx.svc.attendance.create_session(gid, day, time(8 + (i % 8), 0) if i < 48 else time(20, 0),
                                          time(9 + (i % 8), 0) if i < 48 else time(21, 0))
    p = ex.export_instructor_statement(ctx, iid, TODAY - timedelta(days=30), TODAY)
    assert _is_pdf(p)
