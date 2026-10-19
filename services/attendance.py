"""Sessions and attendance (build-plan step 5)."""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional

import config
from core.schemas import Sheet
from services.common import ServiceError, month_bounds
from services.ledger import Ledger

STATUS_CYCLE = ["present", "absent", "late", "excused"]
STATUS_AR = {"present": "حاضر", "absent": "غائب", "late": "متأخر", "excused": "بعذر"}


class AttendanceService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    def _resolve_rate(self, g, instructor_id: int, on_date: date,
                      rate_override: Optional[float] = None) -> float:
        if rate_override is not None and rate_override > 0:
            return round(float(rate_override), 2)
        if g and g.instructor_id == instructor_id and getattr(g, "instructor_hourly_rate", None):
            # If the instructor's rate history was updated more recently than the group creation,
            # check if rate_for differs or if group has a custom rate.
            # When a group has an explicit instructor_hourly_rate, use it unless RateHistory has a newer entry:
            hist = [h for h in self.repo.read(Sheet.RATE_HISTORY)
                    if h.instructor_id == instructor_id and h.effective_from <= on_date
                    and h.effective_from > date(2000, 1, 1)]
            if hist:
                return max(hist, key=lambda h: h.effective_from).hourly_rate
            return round(float(g.instructor_hourly_rate), 2)
        return self.svc.instructors.rate_for(instructor_id, on_date)

    # ------------------------------------------------------------------ sessions
    def create_session(self, group_id: int, on_date: date, start: Optional[time], end: Optional[time],
                       instructor_id: Optional[int] = None, course_level: Optional[str] = None,
                       status: str = "held", rate_applied: Optional[float] = None) -> int:
        g = self.repo.get(Sheet.GROUPS, group_id=group_id)
        if not g:
            raise ServiceError("اختر المجموعة.")
        instructor_id = instructor_id or g.instructor_id
        if not instructor_id or not self.repo.get(Sheet.INSTRUCTORS, instructor_id=instructor_id):
            raise ServiceError("اختر المدرب.")
        if status == "held":
            if not start or not end:
                raise ServiceError("حدد وقت بداية ونهاية الحصة.")
            if datetime.combine(date.min, end) <= datetime.combine(date.min, start):
                raise ServiceError("وقت النهاية يجب أن يكون بعد وقت البداية.")
        for s in self.repo.read(Sheet.SESSIONS):               # same group, same day, overlapping time
            if (s.group_id == group_id and s.date == on_date and s.status == "held" and status == "held"
                    and s.start_time and s.end_time and start and end
                    and start < s.end_time and s.start_time < end):
                raise ServiceError("توجد حصة أخرى لنفس المجموعة في هذا الوقت.")
        rate = self._resolve_rate(g, instructor_id, on_date, rate_applied) if status == "held" else None
        with self.repo.transaction():
            sid = self.repo.next_id(Sheet.SESSIONS)
            self.repo.append(Sheet.SESSIONS, dict(
                session_id=sid, date=on_date, start_time=start, end_time=end, group_id=group_id,
                instructor_id=instructor_id,
                course_level=course_level or (f"{g.cost_center} - {g.level}" if g.level else g.cost_center),
                status=status, rate_applied=rate))
        return sid

    def set_session_status(self, session_id: int, status: str) -> None:
        s = self.repo.get(Sheet.SESSIONS, session_id=session_id)
        if not s:
            raise ServiceError("الحصة غير موجودة.")
        if status == s.status:
            return
        if status == "held":
            if not (s.start_time and s.end_time):
                raise ServiceError("حدد وقت بداية ونهاية الحصة أولًا.")
            g = self.repo.get(Sheet.GROUPS, group_id=s.group_id)
            rate = self._resolve_rate(g, s.instructor_id, s.date)
            self.repo.update(Sheet.SESSIONS, {"session_id": session_id},
                             {"status": "held", "rate_applied": rate})
        else:                                                   # cancelled / postponed: no pay
            self.repo.update(Sheet.SESSIONS, {"session_id": session_id},
                             {"status": status, "rate_applied": None, "amount": None})

    # ---------------------------------------------------------------- attendance
    def mark(self, session_id: int, student_id: int, status: str,
             check_in: Optional[time] = None, check_out: Optional[time] = None,
             notes: Optional[str] = None) -> None:
        if status not in STATUS_CYCLE:
            raise ServiceError("حالة حضور غير صحيحة.")
        if not self.repo.get(Sheet.SESSIONS, session_id=session_id):
            raise ServiceError("الحصة غير موجودة.")
        cur = self.repo.get(Sheet.ATTENDANCE, session_id=session_id, student_id=student_id)
        if cur:
            changes: dict[str, Any] = {"status": status}
            if check_in is not None:
                changes["check_in"] = check_in
            if check_out is not None:
                changes["check_out"] = check_out
            if notes is not None:
                changes["notes"] = notes
            self.repo.update(Sheet.ATTENDANCE, {"session_id": session_id, "student_id": student_id}, changes)
        else:
            self.repo.append(Sheet.ATTENDANCE, dict(
                session_id=session_id, student_id=student_id, status=status,
                check_in=check_in, check_out=check_out, notes=notes))

    def next_status(self, current: Optional[str]) -> str:
        if current not in STATUS_CYCLE:
            return "present"
        return STATUS_CYCLE[(STATUS_CYCLE.index(current) + 1) % len(STATUS_CYCLE)]

    def mark_all_present(self, session_id: int, group_id: int) -> int:
        n = 0
        with self.repo.transaction():
            for s in self.roster(group_id):
                if not self.repo.get(Sheet.ATTENDANCE, session_id=session_id, student_id=s.student_id):
                    self.mark(session_id, s.student_id, "present")
                    n += 1
        return n

    def quick_check_in(self, code_or_id: str | int, group_id: Optional[int] = None,
                       on_date: Optional[date] = None) -> dict[str, Any]:
        """Mark student present by Student ID or QR payload ('FANTASIA-SID:123') and record check-in time."""
        import re
        from services.common import today as _today
        raw = str(code_or_id or "").strip()
        m = re.search(r"(\d+)", raw)
        if not m:
            raise ServiceError("أدخل رقم كود الطالب أو امسح باركود البطاقة.")
        sid = int(m.group(1))
        st = self.repo.get(Sheet.STUDENTS, student_id=sid)
        if not st:
            raise ServiceError(f"الطالب رقم #{sid} غير موجود.")
        enrs = [e for e in self.repo.read(Sheet.ENROLLMENTS)
                if e.student_id == sid and e.status in ("active", "paused")]
        if group_id:
            enrs = [e for e in enrs if e.group_id == group_id] or enrs
        if not enrs and not group_id:
            raise ServiceError(f"الطالب «{st.name_ar}» غير مسجل في أي مجموعة نشطة.")
        gid = group_id or enrs[0].group_id
        d = on_date or _today()
        sessions = [s for s in self.repo.read(Sheet.SESSIONS)
                    if s.group_id == gid and s.date == d and s.status == "held"]
        now_t = datetime.now().time().replace(second=0, microsecond=0)
        if sessions:
            sess_id = sessions[-1].session_id
        else:
            g = self.repo.get(Sheet.GROUPS, group_id=gid)
            if not g or not g.instructor_id:
                raise ServiceError("لا توجد حصة مسجلة اليوم لهذه المجموعة ولا يوجد مدرب معين للمجموعة.")
            sess_id = self.create_session(gid, d, time(16, 0), time(18, 0))
        self.mark(sess_id, sid, "present", check_in=now_t)
        led = Ledger(self.repo)
        enr_match = next((e for e in enrs if e.group_id == gid), enrs[0] if enrs else None)
        rem_les = led.summary(enr_match.enrollment_id).remaining_lessons if enr_match else 0
        return dict(
            student_id=sid,
            name_ar=st.name_ar,
            student_name=st.name_ar,
            group_id=gid,
            session_id=sess_id,
            status="present",
            date=d,
            check_in=f"{now_t:%H:%M}",
            remaining_lessons=rem_les,
        )


    def roster(self, group_id: int) -> list:
        ids = {e.student_id for e in self.repo.read(Sheet.ENROLLMENTS)
               if e.group_id == group_id and e.status in ("active", "paused", "completed")}
        studs = {s.student_id: s for s in self.repo.read(Sheet.STUDENTS)}
        return sorted((studs[i] for i in ids if i in studs), key=lambda s: s.name_ar)

    def grid(self, group_id: int, month: str) -> dict[str, Any]:
        first, last = month_bounds(month)
        led = Ledger(self.repo)
        instructors = led.instructors
        sess = sorted((s for s in led.sessions.values()
                       if s.group_id == group_id and first <= s.date <= last),
                      key=lambda s: (s.date, s.start_time or time(0)))
        att = {(a.session_id, a.student_id): a.status for a in led.attendance}
        att_details = {(a.session_id, a.student_id): a for a in led.attendance}
        enr_by_student = {e.student_id: e for e in led.enrollments
                          if e.group_id == group_id and e.status in ("active", "paused", "completed")}
        students = []
        for st in self.roster(group_id):
            sm = led.summary(enr_by_student[st.student_id].enrollment_id) if st.student_id in enr_by_student else None
            students.append(dict(
                student_id=st.student_id, name=st.name_ar,
                cells={s.session_id: att.get((s.session_id, st.student_id)) for s in sess},
                details={s.session_id: att_details.get((s.session_id, st.student_id)) for s in sess},
                absences=sm.absences if sm else 0,
                exceeded=bool(sm and sm.absence_exceeded)))
        return dict(
            sessions=[dict(session_id=s.session_id, date=s.date, status=s.status,
                           time=f"{s.start_time:%H:%M}" if s.start_time else "",
                           end_time=f"{s.end_time:%H:%M}" if s.end_time else "",
                           rate=s.rate_applied,
                           instructor=instructors[s.instructor_id].name if s.instructor_id in instructors else "—")
                      for s in sess],
            students=students)
