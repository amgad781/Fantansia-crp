"""Ledger – read-only calculations over ONE snapshot of the workbook.

Everything that is "computed, never typed twice" lives here:
fee lines (FIFO allocation of receipts), remaining lessons, collection grid,
overdue list, instructor hours. Build a fresh Ledger per page render / operation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import config
from core.excel_repo import ExcelRepository
from core.schemas import (AttendanceRecord, ClassSession, Employee, EmployeePayment,
                          Enrollment, Expense, FeeScheduleItem, Group, Instructor,
                          InstructorPayment, Receipt, Sheet, Student)
from services.common import month_key, normalize_ar

_ITEM_RANK = {"contest": 0, "monthly": 1, "other": 2}
_EPS = 0.005


@dataclass
class FeeLine:
    item: str
    month: str
    due: float
    paid: float = 0.0

    @property
    def remaining(self) -> float:
        return round(self.due - self.paid, 2)

    @property
    def state(self) -> str:
        if self.remaining <= _EPS:
            return "paid"
        return "partial" if self.paid > _EPS else "unpaid"


@dataclass
class EnrollmentSummary:
    enrollment: Enrollment
    student: Optional[Student]
    group: Optional[Group]
    lines: list[FeeLine]
    paid: float                  # all active receipts of this enrollment
    purchased: int
    consumed: int
    absences: int
    overdue: float
    overdue_months: list[str]

    @property
    def due(self) -> float:
        return round(sum(l.due for l in self.lines), 2)

    @property
    def remaining_fees(self) -> float:
        return round(sum(l.remaining for l in self.lines), 2)

    @property
    def credit(self) -> float:
        """Paid in advance beyond the scheduled fees."""
        return max(0.0, round(self.paid - self.due, 2))

    @property
    def remaining_lessons(self) -> int:
        return self.purchased - self.consumed

    @property
    def absence_exceeded(self) -> bool:
        return self.absences > config.ABSENCE_LIMIT


def lessons_color(n: Optional[int]) -> str:
    """Quasar colour for the remaining-lessons badge: green >1, amber 1, red <=0."""
    if n is None:
        return "grey"
    return "positive" if n > 1 else ("warning" if n == 1 else "negative")


class Ledger:
    def __init__(self, repo: ExcelRepository, today: Optional[date] = None):
        self.repo = repo
        self.today = today or date.today()
        self._cache: dict[str, list] = {}
        self._summ: dict[int, EnrollmentSummary] = {}

    # ---------------------------------------------------------------- raw sheets
    def _rows(self, sheet: Sheet) -> list:
        if sheet.value not in self._cache:
            self._cache[sheet.value] = self.repo.read(sheet)
        return self._cache[sheet.value]

    @property
    def students(self) -> dict[int, Student]:
        return {s.student_id: s for s in self._rows(Sheet.STUDENTS)}

    @property
    def groups(self) -> dict[int, Group]:
        return {g.group_id: g for g in self._rows(Sheet.GROUPS)}

    @property
    def instructors(self) -> dict[int, Instructor]:
        return {i.instructor_id: i for i in self._rows(Sheet.INSTRUCTORS)}

    @property
    def enrollments(self) -> list[Enrollment]:
        return self._rows(Sheet.ENROLLMENTS)

    @property
    def sessions(self) -> dict[int, ClassSession]:
        return {s.session_id: s for s in self._rows(Sheet.SESSIONS)}

    @property
    def receipts_all(self) -> list[Receipt]:
        return self._rows(Sheet.RECEIPTS)

    @property
    def receipts(self) -> list[Receipt]:
        """Active receipts only – the ones that count in every total."""
        return [r for r in self.receipts_all if r.status == "active"]

    @property
    def expenses(self) -> list[Expense]:
        return [e for e in self._rows(Sheet.EXPENSES) if e.status == "active"]

    @property
    def attendance(self) -> list[AttendanceRecord]:
        return self._rows(Sheet.ATTENDANCE)

    @property
    def employees(self) -> dict[int, Employee]:
        return {e.employee_id: e for e in self._rows(Sheet.EMPLOYEES)}

    @property
    def employee_payments(self) -> list[EmployeePayment]:
        return self._rows(Sheet.EMPLOYEE_PAYMENTS)

    @property
    def instructor_payments(self) -> list[InstructorPayment]:
        return self._rows(Sheet.INSTRUCTOR_PAYMENTS)

    def fees_of(self, enrollment_id: int) -> list[FeeScheduleItem]:
        if "_fees_by_enr" not in self._cache:
            d: dict[int, list] = defaultdict(list)
            for f in self._rows(Sheet.FEE_SCHEDULE):
                d[f.enrollment_id].append(f)
            self._cache["_fees_by_enr"] = d          # type: ignore[assignment]
        return self._cache["_fees_by_enr"].get(enrollment_id, [])  # type: ignore[union-attr]

    def _attendance_by_student(self) -> dict[int, list[AttendanceRecord]]:
        if "_att_by_student" not in self._cache:
            d: dict[int, list] = defaultdict(list)
            for a in self.attendance:
                d[a.student_id].append(a)
            self._cache["_att_by_student"] = d       # type: ignore[assignment]
        return self._cache["_att_by_student"]         # type: ignore[return-value]

    def _paid_by_enrollment(self) -> dict[int, float]:
        if "_paid_by_enr" not in self._cache:
            d: dict[int, float] = defaultdict(float)
            for r in self.receipts:
                if r.enrollment_id is not None:
                    d[r.enrollment_id] += r.amount
            self._cache["_paid_by_enr"] = d          # type: ignore[assignment]
        return self._cache["_paid_by_enr"]            # type: ignore[return-value]

    # ----------------------------------------------------------- enrollment maths
    def summary(self, enrollment_id: int) -> EnrollmentSummary:
        if enrollment_id in self._summ:
            return self._summ[enrollment_id]
        enr = next((e for e in self.enrollments if e.enrollment_id == enrollment_id), None)
        if enr is None:
            raise KeyError(enrollment_id)

        lines = [FeeLine(f.item, f.month, f.amount_due) for f in self.fees_of(enrollment_id)]
        lines.sort(key=lambda l: (l.month, _ITEM_RANK.get(l.item, 9)))
        paid_total = round(self._paid_by_enrollment().get(enrollment_id, 0.0), 2)
        left = paid_total
        for l in lines:                                    # FIFO: oldest fee first
            take = min(max(left, 0.0), l.due)
            l.paid = round(take, 2)
            left -= take

        this_month = month_key(self.today)
        late = [l for l in lines if l.remaining > _EPS and l.month <= this_month]

        sessions = self.sessions
        consumed = absences = 0
        for a in self._attendance_by_student().get(enr.student_id, []):
            s = sessions.get(a.session_id)
            if not s or s.status != "held" or s.group_id != enr.group_id or s.date < enr.start_date:
                continue
            if a.status in config.CONSUMING_ATTENDANCE:
                consumed += 1
            if a.status == "absent":
                absences += 1

        summ = EnrollmentSummary(
            enrollment=enr, student=self.students.get(enr.student_id),
            group=self.groups.get(enr.group_id), lines=lines, paid=paid_total,
            purchased=enr.lessons_purchased, consumed=consumed, absences=absences,
            overdue=round(sum(l.remaining for l in late), 2),
            overdue_months=sorted({l.month for l in late}))
        self._summ[enrollment_id] = summ
        return summ

    def student_enrollments(self, student_id: int) -> list[Enrollment]:
        return [e for e in self.enrollments if e.student_id == student_id]

    def paid_monthly_count(self, enrollment_id: int) -> int:
        """Months whose monthly fee is fully covered (drives lessons_purchased)."""
        return sum(1 for l in self.summary(enrollment_id).lines
                   if l.item == "monthly" and l.state == "paid" and l.due > 0)

    # --------------------------------------------------------------- student list
    def student_rows(self, query: str = "", program: str = "", group_id: Optional[int] = None,
                     status: str = "", low_only: bool = False) -> list[dict[str, Any]]:
        q = normalize_ar(query)
        enrs_by_student: dict[int, list[Enrollment]] = defaultdict(list)
        for e in self.enrollments:
            enrs_by_student[e.student_id].append(e)
        paid_by_student: dict[int, float] = defaultdict(float)
        for r in self.receipts:
            paid_by_student[r.student_id] += r.amount

        out: list[dict[str, Any]] = []
        for s in self.students.values():
            if status and s.status != status:
                continue
            if q:
                hay = " ".join([normalize_ar(s.name_ar), normalize_ar(getattr(s, "name_en", None) or ""),
                                str(s.student_id),
                                normalize_ar(s.parent_mobile), normalize_ar(s.parent_whatsapp),
                                normalize_ar(s.student_mobile)])
                if q not in hay:
                    continue
            enrs = enrs_by_student.get(s.student_id, [])
            live = [e for e in enrs if e.status in ("active", "paused")]
            if program and not any((self.groups.get(e.group_id) and
                                    self.groups[e.group_id].cost_center == program) for e in live):
                continue
            if group_id and not any(e.group_id == group_id for e in live):
                continue
            summaries = [self.summary(e.enrollment_id) for e in live]
            main = summaries[-1] if summaries else None            # latest enrollment
            rem = main.remaining_lessons if main else None
            if low_only and (rem is None or rem > 1):
                continue
            programs = sorted({sm.group.cost_center for sm in summaries if sm.group})
            out.append(dict(
                id=s.student_id, name=s.name_ar, name_en=getattr(s, "name_en", None) or "",
                program=" + ".join(programs) or "—",
                group=(f"مجموعة {main.group.group_id}" if main and main.group else "—"),
                mobile=s.parent_mobile or s.parent_whatsapp or s.student_mobile or "—",
                paid=round(paid_by_student.get(s.student_id, 0.0), 2),
                balance=round(sum(sm.remaining_fees for sm in summaries), 2),
                lessons=rem, lessons_color=lessons_color(rem),
                absence_flag=any(sm.absence_exceeded for sm in summaries),
                status=s.status))
        out.sort(key=lambda r: normalize_ar(r["name"]))
        return out

    # ------------------------------------------------------------------ collection
    def live_summaries(self, program: str = "", group_id: Optional[int] = None) -> list[EnrollmentSummary]:
        out = []
        for e in self.enrollments:
            if e.status not in ("active", "paused"):
                continue
            sm = self.summary(e.enrollment_id)
            if program and not (sm.group and sm.group.cost_center == program):
                continue
            if group_id and e.group_id != group_id:
                continue
            out.append(sm)
        return out

    def collection_grid(self, months: list[str], program: str = "",
                        group_id: Optional[int] = None) -> list[dict[str, Any]]:
        this_month = month_key(self.today)
        rows = []
        for sm in self.live_summaries(program, group_id):
            cells: dict[str, dict[str, Any]] = {}
            for m in months:
                ls = [l for l in sm.lines if l.month == m]
                if not ls:
                    cells[m] = dict(due=0.0, paid=0.0, state="none", overdue=False)
                    continue
                due, paid = sum(l.due for l in ls), sum(l.paid for l in ls)
                rem = round(due - paid, 2)
                state = "paid" if rem <= _EPS else ("partial" if paid > _EPS else "unpaid")
                cells[m] = dict(due=round(due, 2), paid=round(paid, 2), state=state,
                                overdue=rem > _EPS and m <= this_month)
            rows.append(dict(
                enrollment_id=sm.enrollment.enrollment_id,
                student_id=sm.enrollment.student_id,
                name=sm.student.name_ar if sm.student else "—",
                program=sm.group.cost_center if sm.group else "—",
                cells=cells,
                due=round(sum(c["due"] for c in cells.values()), 2),
                paid=round(sum(c["paid"] for c in cells.values()), 2)))
        rows.sort(key=lambda r: normalize_ar(r["name"]))
        return rows

    def overdue_list(self, program: str = "", group_id: Optional[int] = None) -> list[dict[str, Any]]:
        out = []
        for sm in self.live_summaries(program, group_id):
            if sm.overdue <= _EPS:
                continue
            st = sm.student
            out.append(dict(
                enrollment_id=sm.enrollment.enrollment_id,
                student_id=sm.enrollment.student_id,
                name=st.name_ar if st else "—",
                program=sm.group.cost_center if sm.group else "—",
                months=sm.overdue_months, amount=sm.overdue,
                mobile=(st.parent_whatsapp or st.parent_mobile) if st else None))
        out.sort(key=lambda r: -r["amount"])
        return out

    # -------------------------------------------------------------------- sessions
    def sessions_on(self, d: date) -> list[dict[str, Any]]:
        out = []
        for s in self.sessions.values():
            if s.date != d:
                continue
            g, ins = self.groups.get(s.group_id), self.instructors.get(s.instructor_id)
            out.append(dict(
                session_id=s.session_id,
                time=f"{s.start_time:%H:%M}" + (f" - {s.end_time:%H:%M}" if s.end_time else "") if s.start_time else "—",
                group=f"{g.cost_center} — {g.level or ''}".strip(" —") if g else "—",
                instructor=ins.name if ins else "—", status=s.status))
        out.sort(key=lambda r: r["time"])
        return out
