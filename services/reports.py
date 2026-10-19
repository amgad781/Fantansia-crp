"""Owner dashboard + reports + data insights (build-plan step 9)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

import config
from core.schemas import Sheet
from services.common import (month_bounds, month_key, month_label, months_between, shift_month, today)
from services.ledger import Ledger


class ReportService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    @staticmethod
    def _bounds(lo: date | str, hi: date | str) -> tuple[date, date]:
        first = lo if isinstance(lo, date) else month_bounds(str(lo))[0]
        last = hi if isinstance(hi, date) else month_bounds(str(hi))[1]
        return first, last

    # ------------------------------------------------------------------ monthly & daily
    def month_summary(self, month: str, program: str = "", led: Optional[Ledger] = None) -> dict[str, float]:
        led = led or Ledger(self.repo)
        first, last = month_bounds(month)
        return self.period_summary(first, last, program=program, led=led, include_month_salaries=[month])

    def period_summary(self, d_from: date, d_to: date, program: str = "",
                       led: Optional[Ledger] = None,
                       include_month_salaries: Optional[list[str]] = None) -> dict[str, float]:
        led = led or Ledger(self.repo)
        groups = led.groups
        revenue = sum(r.amount for r in led.receipts
                      if d_from <= r.date <= d_to and (not program or r.cost_center == program))
        instr = sum((s.amount or 0) for s in led.sessions.values()
                    if s.status == "held" and d_from <= s.date <= d_to
                    and (not program or (groups.get(s.group_id) and groups[s.group_id].cost_center == program)))
        expenses = sum(e.amount for e in led.expenses if d_from <= e.date <= d_to) if not program else 0.0
        if not program:
            if include_month_salaries is not None:
                mset = set(include_month_salaries)
                salaries = sum((p.net or 0) for p in led.employee_payments
                               if p.month in mset and p.status != "reversed")
            else:
                mset = set(months_between(month_key(d_from), month_key(d_to)))
                salaries = sum((p.net or 0) for p in led.employee_payments
                               if p.month in mset and p.status != "reversed"
                               and (p.paid_on is None or d_from <= p.paid_on <= d_to or (d_from.day == 1 and d_to >= month_bounds(p.month)[1])))
        else:
            salaries = 0.0
        return dict(revenue=round(revenue, 2), expenses=round(expenses, 2),
                    instructors=round(instr, 2), salaries=round(salaries, 2),
                    net=round(revenue - expenses - instr - salaries, 2))

    def series(self, last_month: str, count: int = 6, program: str = "") -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        return [dict(month=m, label=month_label(m), **self.month_summary(m, program, led))
                for m in months_between(shift_month(last_month, -(count - 1)), last_month)]

    def period_series(self, d_from: date, d_to: date, program: str = "") -> list[dict[str, Any]]:
        """Daily series when range <= 62 days (showing active days or daily buckets), otherwise monthly series."""
        led = Ledger(self.repo)
        days_span = (d_to - d_from).days + 1
        if days_span <= 62:
            from datetime import timedelta
            groups = led.groups
            out = []
            # If span <= 14 days, show every day; if 15..62 days, show days with any transaction/session or all days if none
            all_days = [d_from + timedelta(days=i) for i in range(days_span)]
            for cur_d in all_days:
                rev = round(sum(r.amount for r in led.receipts
                                if r.date == cur_d and (not program or r.cost_center == program)), 2)
                exp = round(sum(e.amount for e in led.expenses if e.date == cur_d), 2) if not program else 0.0
                ins = round(sum((s.amount or 0) for s in led.sessions.values()
                                if s.status == "held" and s.date == cur_d
                                and (not program or (groups.get(s.group_id) and groups[s.group_id].cost_center == program))), 2)
                sal = round(sum((p.net or 0) for p in led.employee_payments
                                if p.paid_on == cur_d and p.status != "reversed"), 2) if not program else 0.0
                if days_span <= 14 or (rev or exp or ins or sal):
                    out.append(dict(
                        date=cur_d.isoformat(),
                        label=cur_d.strftime("%m-%d"),
                        revenue=rev, expenses=exp, instructors=ins, salaries=sal,
                        net=round(rev - exp - ins - sal, 2),
                    ))
            if not out:
                out.append(dict(
                    date=d_from.isoformat(),
                    label=f"{d_from:%m-%d}..{d_to:%m-%d}",
                    revenue=0.0, expenses=0.0, instructors=0.0, salaries=0.0, net=0.0,
                ))
            return out
        ms = months_between(month_key(d_from), month_key(d_to))
        return [dict(month=m, label=month_label(m), **self.month_summary(m, program, led)) for m in ms]

    def by_program(self, m_from: date | str, m_to: date | str) -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        first, last = self._bounds(m_from, m_to)
        acc: dict[str, float] = defaultdict(float)
        cnt: dict[str, int] = defaultdict(int)
        for r in led.receipts:
            if first <= r.date <= last:
                k = r.cost_center or "غير محدد"
                acc[k] += r.amount
                cnt[k] += 1
        total = sum(acc.values()) or 1.0
        return sorted(({"program": k, "revenue": round(v, 2), "count": cnt[k],
                        "pct": round((v / total) * 100, 1)} for k, v in acc.items()),
                      key=lambda x: -x["revenue"])

    def by_payment_method(self, m_from: date | str, m_to: date | str, program: str = "") -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        first, last = self._bounds(m_from, m_to)
        acc: dict[str, float] = defaultdict(float)
        cnt: dict[str, int] = defaultdict(int)
        for r in led.receipts:
            if first <= r.date <= last and (not program or r.cost_center == program):
                k = config.PAYMENT_METHODS_AR.get(r.method, r.method)
                acc[k] += r.amount
                cnt[k] += 1
        total = sum(acc.values()) or 1.0
        return sorted(({"method": k, "amount": round(v, 2), "count": cnt[k],
                        "pct": round((v / total) * 100, 1)} for k, v in acc.items()),
                      key=lambda x: -x["amount"])

    def by_expense_category(self, m_from: date | str, m_to: date | str) -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        first, last = self._bounds(m_from, m_to)
        acc: dict[str, float] = defaultdict(float)
        cnt: dict[str, int] = defaultdict(int)
        for e in led.expenses:
            if first <= e.date <= last:
                k = e.category or "أخرى"
                acc[k] += e.amount
                cnt[k] += 1
        total = sum(acc.values()) or 1.0
        return sorted(({"category": k, "amount": round(v, 2), "count": cnt[k],
                        "pct": round((v / total) * 100, 1)} for k, v in acc.items()),
                      key=lambda x: -x["amount"])

    def instructor_cost(self, m_from: date | str, m_to: date | str, program: str = "") -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        first, last = self._bounds(m_from, m_to)
        groups = led.groups
        acc: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
        for s in led.sessions.values():
            if (s.status == "held" and first <= s.date <= last
                    and (not program or (groups.get(s.group_id) and groups[s.group_id].cost_center == program))):
                acc[s.instructor_id][0] += s.hours or 0
                acc[s.instructor_id][1] += s.amount or 0
                acc[s.instructor_id][2] += 1
        ins = led.instructors
        return sorted(({"instructor": ins[i].name if i in ins else str(i),
                        "hours": round(h, 2), "amount": round(a, 2), "sessions": int(c)}
                       for i, (h, a, c) in acc.items()), key=lambda x: -x["amount"])

    def period_analysis(self, d_from: date | str, d_to: date | str, program: str = "") -> dict[str, Any]:
        """Complete Dashboard KPIs + Financial & Operational Data Analysis for [d_from, d_to]."""
        first, last = self._bounds(d_from, d_to)
        led = Ledger(self.repo)
        groups = led.groups
        tot = self.period_summary(first, last, program=program, led=led)

        period_receipts = [r for r in led.receipts
                           if first <= r.date <= last and (not program or r.cost_center == program)]
        pending_visa_recs = [
            r for r in period_receipts
            if (getattr(r, "settlement_status", None) or ("pending" if r.method == "visa" else "settled")) == "pending"
        ]
        settled_visa_recs = [
            r for r in period_receipts
            if r.method == "visa" and (getattr(r, "settlement_status", None) or "pending") == "settled"
        ]
        held_sessions = [
            s for s in led.sessions.values()
            if s.status == "held" and first <= s.date <= last
            and (not program or (groups.get(s.group_id) and groups[s.group_id].cost_center == program))
        ]
        held_ids = {s.session_id for s in held_sessions}
        att_rows = [a for a in led.attendance if a.session_id in held_ids]
        att_present = sum(1 for a in att_rows if a.status in ("present", "late"))
        attendance_rate = round((att_present / len(att_rows)) * 100, 1) if att_rows else 100.0

        mset = set(months_between(month_key(first), month_key(last)))
        live_enrs = [led.summary(e.enrollment_id) for e in led.enrollments
                     if e.status in ("active", "paused")
                     and (not program or (groups.get(e.group_id) and groups[e.group_id].cost_center == program))]
        period_due = sum(l.due for sm in live_enrs for l in sm.lines if l.month in mset)
        period_paid = sum(l.paid for sm in live_enrs for l in sm.lines if l.month in mset)
        collection_rate = round((period_paid / period_due) * 100, 1) if period_due > 0 else 100.0

        new_enrs = [e for e in led.enrollments
                    if first <= e.start_date <= last
                    and (not program or (groups.get(e.group_id) and groups[e.group_id].cost_center == program))]
        overdue = led.overdue_list(program=program)

        prog_rows = self.by_program(first, last)
        if program:
            prog_rows = [p for p in prog_rows if p["program"] == program]

        return dict(
            period_from=first,
            period_to=last,
            days_count=(last - first).days + 1,
            program=program or "كل البرامج",
            totals=tot,
            kpis=dict(
                receipts_count=len(period_receipts),
                active_students=sum(1 for s in led.students.values() if s.status == "active"),
                new_enrollments=len(new_enrs),
                sessions_held=len(held_sessions),
                sessions_hours=round(sum(s.hours or 0 for s in held_sessions), 2),
                attendance_rate=attendance_rate,
                collection_rate=collection_rate,
                pending_visa=round(sum(r.amount for r in pending_visa_recs), 2),
                pending_visa_count=len(pending_visa_recs),
                settled_visa=round(sum(r.amount for r in settled_visa_recs), 2),
                overdue_total=round(sum(o["amount"] for o in overdue), 2),
                overdue_count=len(overdue),
            ),
            by_program=prog_rows,
            by_payment_method=self.by_payment_method(first, last, program),
            by_expense_category=self.by_expense_category(first, last),
            instructor_cost=self.instructor_cost(first, last, program),
            series=self.period_series(first, last, program),
            overdue=overdue[:15],
        )

    # ---------------------------------------------------------------- dashboard & targets
    def get_monthly_targets(self) -> dict[str, float]:
        saved = self.repo.get_setting("monthly_targets")
        if not isinstance(saved, dict):
            return dict(revenue_target=50000.0, expense_budget=15000.0)
        return dict(
            revenue_target=max(0.0, float(saved.get("revenue_target", 50000.0))),
            expense_budget=max(0.0, float(saved.get("expense_budget", 15000.0))),
        )

    def set_monthly_targets(self, revenue_target: float, expense_budget: float) -> dict[str, float]:
        from services.common import ServiceError
        if revenue_target < 0 or expense_budget < 0:
            raise ServiceError("المستهدف والميزانية لا يمكن أن يكونا بالسالب.")
        val = dict(revenue_target=round(float(revenue_target), 2), expense_budget=round(float(expense_budget), 2))
        self.repo.set_setting("monthly_targets", val)
        return val

    def today_stats(self) -> dict[str, Any]:
        led = Ledger(self.repo)
        d = today()
        cur = month_key(d)
        overdue = led.overdue_list()
        active_students = sum(1 for s in led.students.values() if s.status == "active")
        live_enrs = [led.summary(e.enrollment_id) for e in led.enrollments if e.status in ("active", "paused")]
        low_lessons = [sm for sm in live_enrs if sm.remaining_lessons <= 1]
        pending_visa = sum(
            r.amount for r in led.receipts
            if (getattr(r, "settlement_status", None) or ("pending" if r.method == "visa" else "settled")) == "pending"
        )
        pending_visa_count = sum(
            1 for r in led.receipts
            if (getattr(r, "settlement_status", None) or ("pending" if r.method == "visa" else "settled")) == "pending"
        )
        # Collection rate for current month
        month_due = sum(l.due for sm in live_enrs for l in sm.lines if l.month == cur)
        month_paid = sum(l.paid for sm in live_enrs for l in sm.lines if l.month == cur)
        collection_rate = round((month_paid / month_due) * 100, 1) if month_due > 0 else 100.0
        # Attendance rate across held sessions
        held_ids = {s.session_id for s in led.sessions.values() if s.status == "held"}
        att_rows = [a for a in led.attendance if a.session_id in held_ids]
        att_present = sum(1 for a in att_rows if a.status in ("present", "late"))
        attendance_rate = round((att_present / len(att_rows)) * 100, 1) if att_rows else 100.0
        # Lead sources breakdown
        sources: dict[str, int] = defaultdict(int)
        for s in led.students.values():
            sources[s.source or "غير محدد"] += 1
        # Payment methods distribution (across all active receipts)
        pm_acc: dict[str, float] = defaultdict(float)
        pm_cnt: dict[str, int] = defaultdict(int)
        for r in led.receipts:
            k = config.PAYMENT_METHODS_AR.get(r.method, r.method)
            pm_acc[k] += r.amount
            pm_cnt[k] += 1
        payment_methods = sorted(
            ({"method": k, "amount": round(v, 2), "count": pm_cnt[k]} for k, v in pm_acc.items()),
            key=lambda x: -x["amount"],
        )

        m_sum = self.month_summary(cur, led=led)
        targets = self.get_monthly_targets()
        rev_t = targets["revenue_target"]
        exp_b = targets["expense_budget"]
        rev_pct = round((m_sum["revenue"] / rev_t) * 100, 1) if rev_t > 0 else 100.0
        exp_pct = round((m_sum["expenses"] / exp_b) * 100, 1) if exp_b > 0 else 0.0

        return dict(
            revenue_today=round(sum(r.amount for r in led.receipts if r.date == d), 2),
            overdue_total=round(sum(o["amount"] for o in overdue), 2),
            overdue=overdue[:8],
            sessions=led.sessions_on(d),
            drawer=self.svc.journal.drawer_balance(d),
            month=m_sum,
            active_students=active_students,
            active_groups=len(led.groups),
            low_lessons_count=len(low_lessons),
            pending_visa=round(pending_visa, 2),
            pending_visa_count=pending_visa_count,
            collection_rate=collection_rate,
            attendance_rate=attendance_rate,
            lead_sources=sorted(({"name": k, "value": v} for k, v in sources.items()), key=lambda x: -x["value"]),
            payment_methods=payment_methods,
            targets=dict(
                revenue_target=rev_t,
                expense_budget=exp_b,
                revenue_pct=rev_pct,
                expense_pct=exp_pct,
                budget_exceeded=(exp_b > 0 and m_sum["expenses"] > exp_b),
            ),
        )


    # ------------------------------------------------------------------- export
    def export_excel(self, path: Path, m_from: date | str, m_to: date | str, program: str = "") -> Path:
        led = Ledger(self.repo)
        first, last = self._bounds(m_from, m_to)
        names = {s.student_id: s.name_ar for s in led.students.values()}
        months = months_between(month_key(first), month_key(last))
        if isinstance(m_from, date) or isinstance(m_to, date):
            tot = self.period_summary(first, last, program=program, led=led)
            summary = pd.DataFrame([dict(الفترة=f"{first} → {last}", الإيرادات=tot["revenue"], المصروفات=tot["expenses"],
                                         أجور_المدربين=tot["instructors"], الرواتب=tot["salaries"], الصافي=tot["net"])])
        else:
            summary = pd.DataFrame([dict(الشهر=month_label(m), الإيرادات=v["revenue"], المصروفات=v["expenses"],
                                         أجور_المدربين=v["instructors"], الرواتب=v["salaries"], الصافي=v["net"])
                                    for m in months for v in [self.month_summary(m, program, led)]])
        receipts = pd.DataFrame([dict(
            المسلسل=r.serial, التاريخ=r.date, الطالب=names.get(r.student_id, ""),
            المبلغ=r.amount, الطريقة=config.PAYMENT_METHODS_AR.get(r.method, r.method),
            حالة_التسوية=config.SETTLEMENT_STATUS_AR.get(
                getattr(r, "settlement_status", None) or ("pending" if r.method == "visa" else "settled"), ""),
            البرنامج=r.cost_center or "", البيان=r.description or "")
            for r in led.receipts if first <= r.date <= last
            and (not program or r.cost_center == program)])
        expenses = pd.DataFrame([dict(التاريخ=e.date, المبلغ=e.amount, التصنيف=e.category,
                                      المستلم=getattr(e, "recipient", None) or "", البيان=e.description or "")
                                 for e in led.expenses if first <= e.date <= last])
        prog = pd.DataFrame(self.by_program(first, last)).rename(
            columns={"program": "البرنامج", "revenue": "الإيراد", "count": "عدد_العمليات", "pct": "النسبة_المئوية"})
        inst = pd.DataFrame(self.instructor_cost(first, last, program)).rename(
            columns={"instructor": "المدرب", "hours": "الساعات", "amount": "المبلغ", "sessions": "الحصص"})
        pm_df = pd.DataFrame(self.by_payment_method(first, last, program)).rename(
            columns={"method": "طريقة_الدفع", "amount": "المبلغ", "count": "العمليات", "pct": "النسبة_المئوية"})
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            for name, df in (("ملخص", summary), ("الإيصالات", receipts), ("توزيع طرق الدفع", pm_df),
                             ("المصروفات", expenses), ("الإيراد حسب البرنامج", prog), ("أجور المدربين", inst)):
                df.to_excel(xw, sheet_name=name, index=False)
                xw.sheets[name].sheet_view.rightToLeft = True
        return path
