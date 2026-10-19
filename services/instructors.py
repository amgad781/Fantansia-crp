"""Instructors paid by the hour (build-plan step 6)."""
from __future__ import annotations

from datetime import date, time
from typing import Any, Optional

import config
from core.schemas import Sheet
from services.common import ServiceError, normalize_ar, today
from services.ledger import Ledger

_EPS = 0.005
_ALWAYS = date(2000, 1, 1)


class InstructorService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    # -------------------------------------------------------------------- master
    def add(self, name: str, phone: str = "", hourly_rate: float = 0) -> int:
        name = " ".join((name or "").split())
        if len(name) < 2:
            raise ServiceError("اكتب اسم المدرب.")
        if hourly_rate is None or hourly_rate <= 0:
            raise ServiceError("سعر الساعة يجب أن يكون أكبر من صفر.")
        with self.repo.transaction():
            iid = self.repo.next_id(Sheet.INSTRUCTORS)
            self.repo.append(Sheet.INSTRUCTORS, dict(instructor_id=iid, name=name, phone=phone,
                                                     hourly_rate=hourly_rate, status="active"))
            self.repo.append(Sheet.RATE_HISTORY, dict(instructor_id=iid, effective_from=_ALWAYS,
                                                      hourly_rate=hourly_rate))
        return iid

    def change_rate(self, instructor_id: int, new_rate: float, effective_from: Optional[date] = None) -> None:
        """New rate applies to sessions created from `effective_from` on; frozen sessions keep theirs."""
        if new_rate is None or new_rate <= 0:
            raise ServiceError("سعر الساعة يجب أن يكون أكبر من صفر.")
        effective_from = effective_from or today()
        with self.repo.transaction():
            if self.repo.get(Sheet.RATE_HISTORY, instructor_id=instructor_id, effective_from=effective_from):
                self.repo.update(Sheet.RATE_HISTORY, {"instructor_id": instructor_id,
                                                      "effective_from": effective_from}, {"hourly_rate": new_rate})
            else:
                self.repo.append(Sheet.RATE_HISTORY, dict(instructor_id=instructor_id,
                                                          effective_from=effective_from, hourly_rate=new_rate))
            self.repo.update(Sheet.INSTRUCTORS, {"instructor_id": instructor_id}, {"hourly_rate": new_rate})

    def update(self, instructor_id: int, changes: dict[str, Any]) -> None:
        self.repo.update(Sheet.INSTRUCTORS, {"instructor_id": instructor_id}, changes)

    def rate_for(self, instructor_id: int, on_date: date, group_id: Optional[int] = None) -> float:
        if group_id is not None:
            g = self.repo.get(Sheet.GROUPS, group_id=group_id)
            if g and g.instructor_id == instructor_id and getattr(g, "instructor_hourly_rate", None):
                hist = [h for h in self.repo.read(Sheet.RATE_HISTORY)
                        if h.instructor_id == instructor_id and h.effective_from <= on_date
                        and h.effective_from > _ALWAYS]
                if not hist:
                    return float(g.instructor_hourly_rate)
        hist = [h for h in self.repo.read(Sheet.RATE_HISTORY)
                if h.instructor_id == instructor_id and h.effective_from <= on_date]
        if hist:
            return max(hist, key=lambda h: h.effective_from).hourly_rate
        ins = self.repo.get(Sheet.INSTRUCTORS, instructor_id=instructor_id)
        return ins.hourly_rate if ins else 0.0

    # ------------------------------------------------------------------- salaries
    def _held(self, led: Ledger, instructor_id: int, d_from: date, d_to: date,
              group_id: Optional[int] = None) -> list:
        upto = min(d_to, led.today)                              # "until the moment of the search"
        return sorted((s for s in led.sessions.values()
                       if s.instructor_id == instructor_id and s.status == "held"
                       and (not group_id or s.group_id == group_id)
                       and d_from <= s.date <= upto and s.hours),
                      key=lambda s: (s.date, s.start_time or time(0)))

    @staticmethod
    def _gross(sessions) -> float:
        return round(sum((s.amount if s.amount is not None else (s.hours or 0) * (s.rate_applied or 0))
                         for s in sessions), 2)

    def _paid(self, led: Ledger, instructor_id: int, d_from: date, d_to: date) -> float:
        return round(sum(p.net or 0 for p in led.instructor_payments
                         if p.instructor_id == instructor_id and p.status == "paid"
                         and p.period_from <= d_to and p.period_to >= d_from), 2)

    def _adjustments(self, led: Ledger, instructor_id: int, d_from: date, d_to: date) -> tuple[float, float, str]:
        rows = [p for p in led.instructor_payments
                if p.instructor_id == instructor_id and p.status in ("pending", "paid")
                and p.period_from <= d_to and p.period_to >= d_from]
        bonuses = round(sum(getattr(p, "bonuses", 0) or 0 for p in rows), 2)
        deductions = round(sum(getattr(p, "deductions", 0) or 0 for p in rows), 2)
        notes = " ، ".join(dict.fromkeys(
            (getattr(p, "notes", None) or "").strip()
            for p in rows if (getattr(p, "notes", None) or "").strip()
        ))
        return bonuses, deductions, notes

    def set_adjustments(self, instructor_id: int, d_from: date, d_to: date,
                        bonuses: float = 0.0, deductions: float = 0.0, notes: str = "") -> int:
        if d_to < d_from:
            raise ServiceError("نهاية الفترة قبل بدايتها.")
        if not self.repo.get(Sheet.INSTRUCTORS, instructor_id=instructor_id):
            raise ServiceError("المدرب غير موجود.")
        if (bonuses or 0) < 0 or (deductions or 0) < 0:
            raise ServiceError("المكافآت والخصومات لا يمكن أن تكون سالبة.")
        led = Ledger(self.repo)
        ss = self._held(led, instructor_id, d_from, d_to)
        gross = self._gross(ss)
        hours = round(sum(s.hours or 0 for s in ss), 2)
        paid_rows = [p for p in led.instructor_payments
                     if p.instructor_id == instructor_id and p.status == "paid"
                     and p.period_from <= d_to and p.period_to >= d_from]
        paid_b = sum(getattr(p, "bonuses", 0) or 0 for p in paid_rows)
        paid_d = sum(getattr(p, "deductions", 0) or 0 for p in paid_rows)
        paid_amt = round(sum(p.net or 0 for p in paid_rows), 2)
        rem_b = round(max(0.0, float(bonuses or 0) - paid_b), 2)
        rem_d = round(max(0.0, float(deductions or 0) - paid_d), 2)
        pend_rows = [p for p in led.instructor_payments
                     if p.instructor_id == instructor_id and p.status == "pending"
                     and p.period_from <= d_to and p.period_to >= d_from]
        with self.repo.transaction():
            if pend_rows:
                target = pend_rows[0]
                for extra in pend_rows[1:]:
                    self.repo.update(Sheet.INSTRUCTOR_PAYMENTS, {"id": extra.id}, {"status": "reversed"})
                self.repo.update(Sheet.INSTRUCTOR_PAYMENTS, {"id": target.id}, dict(
                    period_from=d_from, period_to=d_to, total_hours=hours, gross=gross,
                    bonuses=rem_b, deductions=rem_d, previous_paid=paid_amt,
                    net=round(gross + float(bonuses or 0) - float(deductions or 0) - paid_amt, 2),
                    notes=(notes or "").strip() or None,
                ))
                return target.id
            pid = self.repo.next_id(Sheet.INSTRUCTOR_PAYMENTS)
            self.repo.append(Sheet.INSTRUCTOR_PAYMENTS, dict(
                id=pid, instructor_id=instructor_id, period_from=d_from, period_to=d_to,
                total_hours=hours, gross=gross, bonuses=rem_b, deductions=rem_d,
                previous_paid=paid_amt,
                net=round(gross + float(bonuses or 0) - float(deductions or 0) - paid_amt, 2),
                method="cash", notes=(notes or "").strip() or None, status="pending",
            ))
            return pid

    def summary(self, d_from: date, d_to: date, query: str = "",
                status: str = "", group_id: Optional[int] = None) -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        q = normalize_ar(query)
        groups_by_ins: dict[int, list[str]] = {}
        for g in led.groups.values():
            if g.instructor_id:
                r_str = f"{g.instructor_hourly_rate:g}" if getattr(g, "instructor_hourly_rate", None) else ""
                lbl = f"{g.cost_center}" + (f" ({r_str}/س)" if r_str else "")
                groups_by_ins.setdefault(g.instructor_id, []).append(lbl)
        out = []
        for ins in led.instructors.values():
            if status and ins.status != status:
                continue
            if group_id:
                grp = led.groups.get(group_id)
                if not grp or (grp.instructor_id != ins.instructor_id
                               and not any(s.group_id == group_id and s.instructor_id == ins.instructor_id
                                           for s in led.sessions.values())):
                    continue
            if q and q not in normalize_ar(f"{ins.name} {ins.instructor_id} {ins.phone or ''}"):
                continue
            ss = self._held(led, ins.instructor_id, d_from, d_to, group_id=group_id)
            gross, paid = self._gross(ss), self._paid(led, ins.instructor_id, d_from, d_to)
            bonuses, deductions, adj_notes = (
                (0.0, 0.0, "") if group_id else self._adjustments(led, ins.instructor_id, d_from, d_to)
            )
            out.append(dict(
                instructor_id=ins.instructor_id, name=ins.name, phone=ins.phone or "—",
                status=ins.status, rate=ins.hourly_rate,
                groups_info=" ، ".join(groups_by_ins.get(ins.instructor_id, [])) or "—",
                sessions=len(ss),
                hours=round(sum(s.hours or 0 for s in ss), 2),
                gross=gross, bonuses=bonuses, deductions=deductions, notes=adj_notes,
                paid=paid, net_due=round(gross + bonuses - deductions - paid, 2)))
        out.sort(key=lambda r: (r["status"] != "active", normalize_ar(r["name"])))
        return out

    def sessions_for(self, instructor_id: int, d_from: Optional[date] = None, d_to: Optional[date] = None,
                     *, group_id: Optional[int] = None, group_ids: Optional[list[int]] = None,
                     months: Optional[list[str]] = None, session_ids: Optional[list[int]] = None) -> list[dict[str, Any]]:
        led = Ledger(self.repo)
        groups = led.groups
        lo = d_from or _ALWAYS
        hi = d_to or led.today
        gset = set(group_ids) if group_ids else ({group_id} if group_id else set())
        mset = {m.strip() for m in (months or []) if m and m.strip()}
        sset = set(session_ids) if session_ids is not None else None
        out = []
        for s in self._held(led, instructor_id, lo, hi):
            if gset and s.group_id not in gset:
                continue
            if mset and f"{s.date:%Y-%m}" not in mset:
                continue
            if sset is not None and s.session_id not in sset:
                continue
            g = groups.get(s.group_id)
            out.append(dict(
                session_id=s.session_id,
                group_id=s.group_id,
                date=s.date, start=s.start_time, end=s.end_time,
                group=f"{g.cost_center}{' - ' + g.level if g and g.level else ''}" if g else "—",
                course_level=s.course_level or "", hours=s.hours or 0,
                rate=s.rate_applied or 0,
                amount=s.amount if s.amount is not None else round((s.hours or 0) * (s.rate_applied or 0), 2),
            ))
        return out

    def payments(self, instructor_id: int, d_from: date, d_to: date) -> list:
        return sorted((p for p in self.repo.read(Sheet.INSTRUCTOR_PAYMENTS)
                       if p.instructor_id == instructor_id and p.status in ("paid", "reversed")
                       and p.period_from <= d_to and p.period_to >= d_from),
                      key=lambda p: p.id)

    def record_payment(self, instructor_id: int, d_from: date, d_to: date, amount: float,
                       method: str = "cash", approved_by: str = "",
                       bonuses: Optional[float] = None, deductions: Optional[float] = None,
                       notes: str = "") -> int:
        if d_to < d_from:
            raise ServiceError("نهاية الفترة قبل بدايتها.")
        row = next((r for r in self.summary(d_from, d_to) if r["instructor_id"] == instructor_id), None)
        if row is None:
            raise ServiceError("المدرب غير موجود.")
        if amount is None or amount <= 0:
            raise ServiceError("المبلغ يجب أن يكون أكبر من صفر.")

        pend_rows = [p for p in self.repo.read(Sheet.INSTRUCTOR_PAYMENTS)
                     if p.instructor_id == instructor_id and p.status == "pending"
                     and p.period_from <= d_to and p.period_to >= d_from]
        paid_rows = [p for p in self.repo.read(Sheet.INSTRUCTOR_PAYMENTS)
                     if p.instructor_id == instructor_id and p.status == "paid"
                     and p.period_from <= d_to and p.period_to >= d_from]
        paid_b = sum(getattr(p, "bonuses", 0) or 0 for p in paid_rows)
        paid_d = sum(getattr(p, "deductions", 0) or 0 for p in paid_rows)

        total_b = round(float(bonuses) if bonuses is not None else row.get("bonuses", 0.0), 2)
        total_d = round(float(deductions) if deductions is not None else row.get("deductions", 0.0), 2)
        if total_b < 0 or total_d < 0:
            raise ServiceError("المكافآت والخصومات لا يمكن أن تكون سالبة.")

        effective_due = round(row["gross"] + total_b - total_d - row["paid"], 2)
        if amount > effective_due + _EPS:
            raise ServiceError(f"المبلغ أكبر من الصافي المستحق ({effective_due:,.2f}).")

        this_b = round(max(0.0, total_b - paid_b), 2)
        this_d = round(max(0.0, total_d - paid_d), 2)
        this_notes = (notes or "").strip() or " ، ".join(
            (getattr(p, "notes", None) or "").strip()
            for p in pend_rows if (getattr(p, "notes", None) or "").strip()
        )

        with self.repo.transaction():
            if pend_rows:
                target = pend_rows[0]
                for extra in pend_rows[1:]:
                    self.repo.update(Sheet.INSTRUCTOR_PAYMENTS, {"id": extra.id}, {"status": "reversed"})
                self.repo.update(Sheet.INSTRUCTOR_PAYMENTS, {"id": target.id}, dict(
                    period_from=d_from, period_to=d_to,
                    total_hours=row["hours"], gross=row["gross"],
                    bonuses=this_b, deductions=this_d,
                    previous_paid=row["paid"], net=amount,
                    method=method, paid_on=today(), approved_by=approved_by or self.svc.user(),
                    notes=this_notes or None, status="paid"))
                return target.id
            pid = self.repo.next_id(Sheet.INSTRUCTOR_PAYMENTS)
            self.repo.append(Sheet.INSTRUCTOR_PAYMENTS, dict(
                id=pid, instructor_id=instructor_id, period_from=d_from, period_to=d_to,
                total_hours=row["hours"], gross=row["gross"],
                bonuses=this_b, deductions=this_d,
                previous_paid=row["paid"], net=amount,
                method=method, paid_on=today(), approved_by=approved_by or self.svc.user(),
                notes=this_notes or None, status="paid"))
        return pid

    def reverse_payment(self, payment_id: int) -> None:
        p = self.repo.get(Sheet.INSTRUCTOR_PAYMENTS, id=payment_id)
        if not p or p.status != "paid":
            raise ServiceError("الدفعة غير موجودة أو ملغاة بالفعل.")
        with self.repo.transaction():
            self.repo.update(Sheet.INSTRUCTOR_PAYMENTS, {"id": payment_id}, {"status": "reversed"})
            if (getattr(p, "bonuses", 0) or 0) > 0 or (getattr(p, "deductions", 0) or 0) > 0:
                pid = self.repo.next_id(Sheet.INSTRUCTOR_PAYMENTS)
                self.repo.append(Sheet.INSTRUCTOR_PAYMENTS, dict(
                    id=pid, instructor_id=p.instructor_id, period_from=p.period_from, period_to=p.period_to,
                    total_hours=p.total_hours, gross=p.gross,
                    bonuses=p.bonuses, deductions=p.deductions,
                    previous_paid=0, net=round(p.gross + p.bonuses - p.deductions, 2),
                    method=p.method, notes=getattr(p, "notes", None), status="pending",
                ))

    def statement(self, instructor_id: int, d_from: Optional[date] = None, d_to: Optional[date] = None,
                  *, group_id: Optional[int] = None, group_ids: Optional[list[int]] = None,
                  months: Optional[list[str]] = None, session_ids: Optional[list[int]] = None,
                  custom_title: Optional[str] = None, custom_item_label: Optional[str] = None,
                  custom_item_amount: float = 0.0, notes: Optional[str] = None,
                  payment_id: Optional[int] = None) -> dict[str, Any]:
        ins = self.repo.get(Sheet.INSTRUCTORS, instructor_id=instructor_id)
        if not ins:
            raise ServiceError("المدرب غير موجود.")
        led = Ledger(self.repo)
        if payment_id is not None:
            pay_rec = self.repo.get(Sheet.INSTRUCTOR_PAYMENTS, id=payment_id)
            if not pay_rec or pay_rec.instructor_id != instructor_id:
                raise ServiceError("الدفعة غير موجودة.")
            d_from = pay_rec.period_from
            d_to = pay_rec.period_to

        if months and not d_from and not d_to:
            from services.common import month_bounds
            sorted_m = sorted(m for m in months if m)
            if sorted_m:
                d_from = month_bounds(sorted_m[0])[0]
                d_to = month_bounds(sorted_m[-1])[1]
        lo = d_from or today().replace(day=1)
        hi = d_to or today()

        lines = self.sessions_for(
            instructor_id, lo, hi,
            group_id=group_id, group_ids=group_ids,
            months=months, session_ids=session_ids,
        )
        gset = set(group_ids) if group_ids else ({group_id} if group_id else set())
        group_label = ""
        if gset:
            g_names = []
            for gid in sorted(gset):
                g = led.groups.get(gid)
                if g:
                    g_names.append(f"{g.cost_center}{' - ' + g.level if g.level else ''}")
            group_label = " ، ".join(g_names)

        months_label = ""
        if months:
            from services.common import month_label
            months_label = " ، ".join(month_label(m) for m in sorted(months))

        extra_amt = round(float(custom_item_amount or 0.0), 2)
        gross = round(sum(l["amount"] for l in lines) + extra_amt, 2)

        if payment_id is not None:
            pay_rec = self.repo.get(Sheet.INSTRUCTOR_PAYMENTS, id=payment_id)
            bonuses = round(float(getattr(pay_rec, "bonuses", 0) or 0), 2)
            deductions = round(float(getattr(pay_rec, "deductions", 0) or 0), 2)
            paid = round(float(pay_rec.net or 0), 2)
            methods = [pay_rec.method] if pay_rec.method else []
            net_due = round(max(0.0, gross + bonuses - deductions - (pay_rec.previous_paid or 0) - paid), 2)
            if not notes and getattr(pay_rec, "notes", None):
                notes = pay_rec.notes
        elif gset or session_ids is not None or months or custom_item_label:
            pays = [p for p in self.payments(instructor_id, lo, hi) if p.status == "paid"]
            bonuses, deductions = 0.0, 0.0
            paid = 0.0 if (gset or session_ids is not None or custom_item_label) else round(sum(p.net or 0 for p in pays), 2)
            methods = sorted({p.method for p in pays})
            net_due = round(gross + bonuses - deductions - paid, 2)
        else:
            pays = [p for p in self.payments(instructor_id, lo, hi) if p.status == "paid"]
            bonuses, deductions, adj_notes = self._adjustments(led, instructor_id, lo, hi)
            if not notes and adj_notes:
                notes = adj_notes
            paid = round(sum(p.net or 0 for p in pays), 2)
            methods = sorted({p.method for p in pays})
            net_due = round(gross + bonuses - deductions - paid, 2)

        return dict(
            name=ins.name,
            phone=ins.phone,
            period_from=lo,
            period_to=min(hi, today()),
            lines=lines,
            total_hours=round(sum(l["hours"] for l in lines), 2),
            gross=gross,
            bonuses=bonuses,
            deductions=deductions,
            previous_paid=paid,
            net_due=net_due,
            methods=methods,
            group_label=group_label,
            months_label=months_label,
            custom_title=custom_title or "",
            custom_item_label=(custom_item_label or "").strip(),
            custom_item_amount=extra_amt,
            notes=(notes or "").strip(),
            payment_id=payment_id,
        )
