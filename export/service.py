"""Glue between services and the PDF builders: choose file names, write, audit-log, open."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path
from typing import Optional

import config
from core.audit import Action
from core.schemas import Sheet
from export.pdf_certificate import build_certificate_pdf, build_student_id_card_pdf
from export.pdf_evaluation import build_evaluation_pdf
from export.pdf_instructor import build_instructor_pdf
from export.pdf_payslip import build_payroll_summary_pdf, build_payslip_pdf
from export.pdf_receipt import build_receipt_pdf
from export.pdf_report import build_report_pdf


def _safe(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("_") or "x"


def export_student_certificate(
    ctx,
    student_id: int,
    program: str = "",
    level: str = "",
    grade: str = "",
    grade_label: str = "امتياز",
    instructor_name: str = "",
    notes: str = "",
    issue_date: Optional[date | str] = None,
    record_history: bool = True,
) -> Path:
    from services.students import transliterate_ar_to_en
    led = ctx.svc.ledger()
    st = led.students.get(student_id)
    if not st:
        from services.common import ServiceError
        raise ServiceError("الطالب غير موجود.")
    enrs = led.student_enrollments(student_id)
    grp = led.groups.get(enrs[0].group_id) if enrs else None
    prog = program or (grp.cost_center if grp else "البرمجة والروبوتيكس")
    lvl = level or (grp.level if grp and grp.level else "مبتدئ")
    eff_grade = grade or grade_label or "امتياز"
    eff_date = issue_date or date.today()
    name_en = getattr(st, "name_en", None) or transliterate_ar_to_en(st.name_ar)
    eff_notes = notes or (f"بإشراف المدرب: {instructor_name}" if instructor_name else "")
    data = dict(
        student_id=st.student_id,
        name_ar=st.name_ar,
        name_en=name_en,
        program=prog,
        level=lvl,
        grade=eff_grade,
        grade_label=eff_grade,
        instructor=instructor_name,
        notes=eff_notes,
        issue_date=eff_date,
    )
    path = config.EXPORT_DIR / "certificates" / f"certificate_{st.student_id}_{_safe(prog)}_{_safe(lvl)}.pdf"
    build_certificate_pdf(path, data)
    if record_history:
        ctx.svc.students.add_certificate(
            student_id=st.student_id,
            program=prog,
            level=lvl,
            grade=eff_grade,
            instructor=instructor_name,
            issue_date=eff_date,
            notes=eff_notes,
            pdf_path=str(path),
        )
    ctx.audit.log(Action.EXPORT_PDF, Sheet.STUDENTS.value, f"cert|{student_id}")
    return path


def export_student_id_card(ctx, student_id: int) -> Path:
    from services.students import transliterate_ar_to_en
    led = ctx.svc.ledger()
    st = led.students.get(student_id)
    if not st:
        from services.common import ServiceError
        raise ServiceError("الطالب غير موجود.")
    enrs = led.student_enrollments(student_id)
    grp = led.groups.get(enrs[0].group_id) if enrs else None
    name_en = getattr(st, "name_en", None) or transliterate_ar_to_en(st.name_ar)
    data = dict(
        student_id=st.student_id,
        name_ar=st.name_ar,
        name_en=name_en,
        program=grp.cost_center if grp else "—",
        group_label=f"#{grp.group_id} ({grp.schedule or grp.level or ''})" if grp else "—",
        parent_mobile=st.parent_mobile or st.parent_whatsapp or "—",
    )
    path = config.EXPORT_DIR / "id_cards" / f"id_card_{st.student_id}.pdf"
    build_student_id_card_pdf(path, data)
    ctx.audit.log(Action.EXPORT_PDF, Sheet.STUDENTS.value, f"idcard|{student_id}")
    return path


def export_period_report_pdf(ctx, d_from: date | str, d_to: date | str, program: str = "") -> Path:
    data = ctx.svc.reports.period_analysis(d_from, d_to, program=program)
    lo, hi = data["period_from"], data["period_to"]
    prog_tag = f"_{_safe(program)}" if program else ""
    path = config.EXPORT_DIR / f"report_analysis_{lo:%Y-%m-%d}_{hi:%Y-%m-%d}{prog_tag}.pdf"
    build_report_pdf(path, data, user=ctx.session.username)
    ctx.audit.log(Action.EXPORT_PDF, "Reports", f"{lo}..{hi}")
    return path


def export_receipt(ctx, serial: int, reprint: bool = False) -> Path:
    d = ctx.svc.receipts.pdf_data(serial)
    path = config.RECEIPTS_DIR / f"receipt_{serial}.pdf"
    build_receipt_pdf(path, d, reprint=reprint)
    ctx.audit.log(Action.EXPORT_PDF, Sheet.RECEIPTS.value, serial)
    return path


def export_instructor_statement(ctx, instructor_id: int, d_from: Optional[date] = None, d_to: Optional[date] = None,
                                *, group_id: Optional[int] = None, group_ids: Optional[list[int]] = None,
                                months: Optional[list[str]] = None, session_ids: Optional[list[int]] = None,
                                custom_title: Optional[str] = None, custom_item_label: Optional[str] = None,
                                custom_item_amount: float = 0.0, notes: Optional[str] = None,
                                payment_id: Optional[int] = None) -> Path:
    st = ctx.svc.instructors.statement(
        instructor_id, d_from, d_to,
        group_id=group_id, group_ids=group_ids,
        months=months, session_ids=session_ids,
        custom_title=custom_title, custom_item_label=custom_item_label,
        custom_item_amount=custom_item_amount, notes=notes,
        payment_id=payment_id,
    )
    lo, hi = st["period_from"], st["period_to"]
    tag = f"{lo:%Y-%m-%d}_{hi:%Y-%m-%d}" if (lo.day != 1 or lo.month != hi.month) else f"{lo:%Y-%m}"
    if st.get("group_label"):
        tag += f"_{_safe(st['group_label'])}"
    if payment_id is not None:
        tag += f"_pay{payment_id}"
    path = config.INSTRUCTORS_DIR / f"instructor_{_safe(st['name'])}_{tag}.pdf"
    build_instructor_pdf(path, st, user=ctx.session.username)
    ctx.audit.log(Action.EXPORT_PDF, Sheet.INSTRUCTORS.value, instructor_id)
    return path


def export_payslip(ctx, employee_id: int, month: str) -> Path:
    d = ctx.svc.employees.payslip_data(employee_id, month)
    path = config.EMPLOYEES_DIR / f"payslip_{_safe(d['name'])}_{month}.pdf"
    build_payslip_pdf(path, d, user=ctx.session.username)
    ctx.audit.log(Action.EXPORT_PDF, Sheet.EMPLOYEE_PAYMENTS.value, f"{employee_id}|{month}")
    return path


def export_all_payslips(ctx, month: str) -> tuple[Path, list[Path]]:
    """One payslip per employee + a summary PDF. Returns (summary_path, payslip_paths)."""
    from services.common import ServiceError
    rows = ctx.svc.employees.month_rows(month)
    if not rows:
        raise ServiceError("لا يوجد موظفون.")
    slips = [export_payslip(ctx, r["employee_id"], month) for r in rows]
    rows = ctx.svc.employees.month_rows(month)                    # refreshed (rows now saved)
    summary = config.EMPLOYEES_DIR / f"payroll_{month}.pdf"
    build_payroll_summary_pdf(summary, month, rows, user=ctx.session.username)
    ctx.audit.log(Action.EXPORT_PDF, Sheet.EMPLOYEE_PAYMENTS.value, f"all|{month}")
    return summary, slips


def open_path(path: Path | str, folder: bool = False) -> None:
    """Open a file (or its folder) with the OS default app. Local desktop use only."""
    target = Path(path)
    if folder:
        target = target.parent
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))                              # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception:
        webbrowser.open(target.as_uri())


def open_url(url: str) -> None:
    webbrowser.open(url)


def export_student_evaluation(ctx, student_id: int, scores: dict = None,
                               recommendation: str = "", group_id: int = None) -> Path:
    """Generate and save a printable evaluation form for a student."""
    led = ctx.svc.ledger()
    st = led.students.get(student_id)
    if not st:
        from services.common import ServiceError
        raise ServiceError("الطالب غير موجود.")
    enrs = led.student_enrollments(student_id)
    grp = None
    if group_id:
        grp = led.groups.get(group_id)
    elif enrs:
        grp = led.groups.get(enrs[0].group_id)
    data = {
        'student_name': st.name_ar,
        'level': (grp.level if grp and grp.level else ""),
        'group_label': (f"#{grp.group_id} \u2014 {grp.cost_center}" if grp else ""),
        'date': str(date.today()),
        'scores': scores or {},
        'recommendation': recommendation,
        'user': ctx.session.username,
    }
    path = config.EXPORT_DIR / "evaluations" / f"eval_{student_id}.pdf"
    build_evaluation_pdf(path, data)
    ctx.audit.log(Action.EXPORT_PDF, "Students", f"eval|{student_id}")
    return path
