"""Cash receipts + Visa / Bank settlement tracking (build-plan step 3)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import config
from core.schemas import Receipt, Sheet, validate_entry_date
from services.common import ServiceError, normalize_ar, today
from services.ledger import Ledger


class ReceiptService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    def next_serial(self) -> int:
        return self.repo.next_id(Sheet.RECEIPTS, start=config.RECEIPT_FIRST_SERIAL)

    def _sync_lessons(self, enrollment_id: int, before: int, after: int) -> None:
        """Each newly fully-paid monthly fee adds LESSONS_PER_PAID_MONTH (and reversal removes them)."""
        delta = (after - before) * config.LESSONS_PER_PAID_MONTH
        if not delta:
            return
        enr = self.repo.get(Sheet.ENROLLMENTS, enrollment_id=enrollment_id)
        if enr:
            self.repo.update(Sheet.ENROLLMENTS, {"enrollment_id": enrollment_id},
                             {"lessons_purchased": max(0, enr.lessons_purchased + delta)})

    def create(self, *, student_id: int, amount: float, method: str = "cash",
               enrollment_id: Optional[int] = None, cost_center: Optional[str] = None,
               description: Optional[str] = None, on_date: Optional[date] = None,
               settlement_status: Optional[str] = None, bank_ref: Optional[str] = None) -> Receipt:
        d = on_date or today()
        try:
            validate_entry_date(d)
        except ValueError as e:
            raise ServiceError(str(e))
        if amount is None or amount <= 0:
            raise ServiceError("المبلغ يجب أن يكون أكبر من صفر.")
        if not self.repo.get(Sheet.STUDENTS, student_id=student_id):
            raise ServiceError("اختر الطالب.")
        enrs = [e for e in self.repo.read(Sheet.ENROLLMENTS) if e.student_id == student_id]
        if enrollment_id is None and any(e.status in ("active", "paused") for e in enrs):
            raise ServiceError("اختر الاشتراك الذي يخصه هذا الإيصال.")
        if enrollment_id is not None and not any(e.enrollment_id == enrollment_id for e in enrs):
            raise ServiceError("هذا الاشتراك لا يخص الطالب المختار.")

        if settlement_status is None:
            settlement_status = "pending" if method == "visa" else "settled"
        settled_at = d if settlement_status == "settled" else None
        settled_by = self.svc.user() if settlement_status == "settled" else None

        with self.repo.transaction():
            before = Ledger(self.repo).paid_monthly_count(enrollment_id) if enrollment_id else 0
            rec = self.repo.append(Sheet.RECEIPTS, dict(
                serial=self.next_serial(), date=d, student_id=student_id, enrollment_id=enrollment_id,
                amount=amount, method=method, cost_center=cost_center, description=description,
                status="active", user=self.svc.user(), settlement_status=settlement_status,
                settled_at=settled_at, settled_by=settled_by, bank_ref=bank_ref))
            if enrollment_id:
                self._sync_lessons(enrollment_id, before, Ledger(self.repo).paid_monthly_count(enrollment_id))
        return rec

    def set_settlement(self, serial: int, settled: bool | str, bank_ref: Optional[str] = None,
                       settled_date: Optional[date] = None, settled_at: Optional[date] = None) -> Receipt:
        """Mark a Visa/non-cash transaction as settled in the academy bank account (or back to pending)."""
        r = self.repo.get(Sheet.RECEIPTS, serial=serial)
        if not r:
            raise ServiceError("الإيصال غير موجود.")
        if r.status != "active":
            raise ServiceError("لا يمكن تسوية إيصال ملغي.")
        is_settled = (settled == "settled") if isinstance(settled, str) else bool(settled)
        new_status = "settled" if is_settled else "pending"
        dt = settled_at or settled_date or today()
        changes: dict[str, Any] = {
            "settlement_status": new_status,
            "settled_at": dt if is_settled else None,
            "settled_by": self.svc.user() if is_settled else None,
        }
        if bank_ref is not None:
            changes["bank_ref"] = bank_ref.strip() or None
        return self.repo.update(Sheet.RECEIPTS, {"serial": serial}, changes)

    def reverse(self, serial: int, reason: str) -> None:
        """Cancel = mark reversed + keep the row (the serial stays visible, no deletion)."""
        reason = (reason or "").strip()
        if not reason:
            raise ServiceError("اكتب سبب الإلغاء.")
        r = self.repo.get(Sheet.RECEIPTS, serial=serial)
        if not r:
            raise ServiceError("الإيصال غير موجود.")
        if r.status != "active":
            raise ServiceError("الإيصال ملغي بالفعل.")
        with self.repo.transaction():
            before = Ledger(self.repo).paid_monthly_count(r.enrollment_id) if r.enrollment_id else 0
            note = f"{r.description or ''} [ملغي: {reason}]".strip()
            self.repo.update(Sheet.RECEIPTS, {"serial": serial}, {"status": "reversed", "description": note})
            if r.enrollment_id:
                self._sync_lessons(r.enrollment_id, before, Ledger(self.repo).paid_monthly_count(r.enrollment_id))

    def remaining_after(self, serial: int) -> Optional[float]:
        """Fees still due on the enrollment right after this receipt (stable for reprints)."""
        r = self.repo.get(Sheet.RECEIPTS, serial=serial)
        if not r or not r.enrollment_id:
            return None
        due = sum(f.amount_due for f in self.repo.read(Sheet.FEE_SCHEDULE) if f.enrollment_id == r.enrollment_id)
        paid = sum(x.amount for x in self.repo.read(Sheet.RECEIPTS)
                   if x.enrollment_id == r.enrollment_id and x.status == "active" and x.serial <= serial)
        return round(due - paid, 2)

    def rows(self, query: str = "", date_from: Optional[date] = None, date_to: Optional[date] = None,
             student_id: Optional[int] = None, method: str = "", cost_center: str = "",
             status: str = "", settlement_status: str = "") -> list[dict[str, Any]]:
        names = {s.student_id: s.name_ar for s in self.repo.read(Sheet.STUDENTS)}
        q = normalize_ar(query)
        out = []
        for r in self.repo.read(Sheet.RECEIPTS):
            if student_id and r.student_id != student_id:
                continue
            if method and r.method != method:
                continue
            if cost_center and (r.cost_center or "") != cost_center:
                continue
            if status and r.status != status:
                continue
            s_stat = getattr(r, "settlement_status", None) or ("pending" if r.method == "visa" else "settled")
            if settlement_status and s_stat != settlement_status:
                continue
            if date_from and r.date < date_from or date_to and r.date > date_to:
                continue
            name = names.get(r.student_id, "—")
            ref = getattr(r, "bank_ref", None) or ""
            if q and q not in normalize_ar(f"{r.serial} {name} {r.description or ''} {r.cost_center or ''} {ref}"):
                continue
            out.append(dict(serial=r.serial, date=str(r.date), student=name, student_id=r.student_id,
                            amount=r.amount, method_key=r.method, method_code=r.method,
                            method=config.PAYMENT_METHODS_AR.get(r.method, r.method),
                            cost_center=r.cost_center or "", program=r.cost_center or "—",
                            description=r.description or "",
                            status=r.status, user=r.user,
                            settlement_status=s_stat,
                            settlement_label=config.SETTLEMENT_STATUS_AR.get(s_stat, s_stat),
                            settled_at=str(r.settled_at) if getattr(r, "settled_at", None) else "",
                            settled_by=getattr(r, "settled_by", None) or "",
                            bank_ref=ref))
        out.sort(key=lambda x: -x["serial"])
        return out

    def settlement_summary(self, method: str = "visa", date_from: Optional[date] = None,
                           date_to: Optional[date] = None, query: str = "") -> dict[str, Any]:
        """Summary and rows for the Visa / Bank Settlement follow-up page."""
        all_rows = self.rows(query=query, date_from=date_from, date_to=date_to,
                             method=method if method not in ("all_non_cash", "non_cash", "") else "", status="active")
        if method in ("all_non_cash", "non_cash"):
            all_rows = [r for r in all_rows if r["method_key"] != "cash"]
        pending_total = round(sum(r["amount"] for r in all_rows if r["settlement_status"] == "pending"), 2)
        settled_total = round(sum(r["amount"] for r in all_rows if r["settlement_status"] == "settled"), 2)
        pending_count = sum(1 for r in all_rows if r["settlement_status"] == "pending")
        settled_count = sum(1 for r in all_rows if r["settlement_status"] == "settled")
        tot = round(pending_total + settled_total, 2)
        return dict(
            rows=all_rows,
            pending_total=pending_total,
            settled_total=settled_total,
            total=tot,
            pending_amount=pending_total,
            settled_amount=settled_total,
            total_amount=tot,
            pending_count=pending_count,
            settled_count=settled_count,
        )

    def pdf_data(self, serial: int) -> dict[str, Any]:
        r = self.repo.get(Sheet.RECEIPTS, serial=serial)
        if not r:
            raise ServiceError("الإيصال غير موجود.")
        st = self.repo.get(Sheet.STUDENTS, student_id=r.student_id)
        return dict(serial=r.serial, date=r.date, student_name=st.name_ar if st else "—",
                    amount=r.amount, method=config.PAYMENT_METHODS_AR.get(r.method, r.method),
                    cost_center=r.cost_center or "", description=r.description or "",
                    remaining=self.remaining_after(serial), status=r.status, user=r.user)
