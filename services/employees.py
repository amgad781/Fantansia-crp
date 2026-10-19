"""Employees and monthly salaries (build-plan step 7). net = base + bonuses - deductions."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from core.schemas import Sheet
from services.common import ServiceError, normalize_ar, today


class EmployeeService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    def add(self, name: str, job_title: str = "", phone: str = "", base_salary: float = 0) -> int:
        name = " ".join((name or "").split())
        if len(name) < 2:
            raise ServiceError("اكتب اسم الموظف.")
        if base_salary is None or base_salary <= 0:
            raise ServiceError("الراتب الأساسي يجب أن يكون أكبر من صفر.")
        with self.repo.transaction():
            eid = self.repo.next_id(Sheet.EMPLOYEES)
            self.repo.append(Sheet.EMPLOYEES, dict(employee_id=eid, name=name, job_title=job_title,
                                                   phone=phone, base_salary=base_salary, status="active"))
        return eid

    def update(self, employee_id: int, changes: dict[str, Any]) -> None:
        self.repo.update(Sheet.EMPLOYEES, {"employee_id": employee_id}, changes)

    # ---------------------------------------------------------------- monthly rows
    def _payment(self, employee_id: int, month: str):
        rows = [p for p in self.repo.read(Sheet.EMPLOYEE_PAYMENTS)
                if p.employee_id == employee_id and p.month == month and p.status != "reversed"]
        return rows[-1] if rows else None

    def month_rows(self, month: str, query: str = "") -> list[dict[str, Any]]:
        q = normalize_ar(query)
        out = []
        for e in self.repo.read(Sheet.EMPLOYEES):
            if e.status != "active" or (q and q not in normalize_ar(f"{e.name} {e.job_title or ''}")):
                continue
            p = self._payment(e.employee_id, month)
            base = p.base_salary if p else e.base_salary
            bonus, ded = (p.bonuses, p.deductions) if p else (0.0, 0.0)
            out.append(dict(employee_id=e.employee_id, payment_id=p.id if p else None, name=e.name,
                            job_title=e.job_title or "", base=base, bonuses=bonus, deductions=ded,
                            net=round(base + bonus - ded, 2),
                            status=p.status if p else "unsaved", method=p.method if p else "",
                            paid_on=str(p.paid_on) if p and p.paid_on else ""))
        out.sort(key=lambda r: normalize_ar(r["name"]))
        return out

    def ensure_row(self, employee_id: int, month: str) -> int:
        p = self._payment(employee_id, month)
        if p:
            return p.id
        e = self.repo.get(Sheet.EMPLOYEES, employee_id=employee_id)
        if not e:
            raise ServiceError("الموظف غير موجود.")
        with self.repo.transaction():
            pid = self.repo.next_id(Sheet.EMPLOYEE_PAYMENTS)
            self.repo.append(Sheet.EMPLOYEE_PAYMENTS, dict(id=pid, employee_id=employee_id, month=month,
                                                          base_salary=e.base_salary, status="pending"))
        return pid

    def set_adjustments(self, employee_id: int, month: str, bonuses: float, deductions: float) -> None:
        if (bonuses or 0) < 0 or (deductions or 0) < 0:
            raise ServiceError("المكافآت والخصومات لا يمكن أن تكون سالبة.")
        with self.repo.transaction():
            pid = self.ensure_row(employee_id, month)
            p = self.repo.get(Sheet.EMPLOYEE_PAYMENTS, id=pid)
            if p.status == "paid":
                raise ServiceError("تم صرف راتب هذا الشهر. ألغِ الصرف أولًا للتعديل.")
            e = self.repo.get(Sheet.EMPLOYEES, employee_id=employee_id)
            self.repo.update(Sheet.EMPLOYEE_PAYMENTS, {"id": pid},
                             {"bonuses": bonuses or 0, "deductions": deductions or 0,
                              "base_salary": e.base_salary})          # pending rows follow current base

    def pay(self, employee_id: int, month: str, method: str = "cash",
            bonuses: Optional[float] = None, deductions: Optional[float] = None) -> int:
        with self.repo.transaction():
            pid = self.ensure_row(employee_id, month)
            p = self.repo.get(Sheet.EMPLOYEE_PAYMENTS, id=pid)
            if p.status == "paid":
                raise ServiceError("تم صرف راتب هذا الشهر بالفعل.")
            if bonuses is not None or deductions is not None:
                b = float(bonuses if bonuses is not None else (p.bonuses or 0))
                d = float(deductions if deductions is not None else (p.deductions or 0))
                self.set_adjustments(employee_id, month, b, d)
                p = self.repo.get(Sheet.EMPLOYEE_PAYMENTS, id=pid)
            if p.net is not None and p.net <= 0:
                raise ServiceError("صافي الراتب صفر أو أقل.")
            self.repo.update(Sheet.EMPLOYEE_PAYMENTS, {"id": pid},
                             {"status": "paid", "method": method, "paid_on": today()})
        return pid

    def reverse(self, payment_id: int) -> None:
        p = self.repo.get(Sheet.EMPLOYEE_PAYMENTS, id=payment_id)
        if not p or p.status == "reversed":
            raise ServiceError("السجل غير موجود أو ملغي بالفعل.")
        self.repo.update(Sheet.EMPLOYEE_PAYMENTS, {"id": payment_id}, {"status": "reversed"})

    def payslip_data(self, employee_id: int, month: str) -> dict[str, Any]:
        pid = self.ensure_row(employee_id, month)
        p = self.repo.get(Sheet.EMPLOYEE_PAYMENTS, id=pid)
        e = self.repo.get(Sheet.EMPLOYEES, employee_id=employee_id)
        return dict(name=e.name, job_title=e.job_title or "", month=month, base=p.base_salary,
                    bonuses=p.bonuses, deductions=p.deductions, net=p.net, status=p.status,
                    method=p.method, paid_on=p.paid_on)
