"""Daily journal: expenses, petty cash, cash handovers, drawer balance (build-plan step 8)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import config
from core.schemas import Sheet, validate_entry_date
from services.common import ServiceError, normalize_ar, today
from services.ledger import Ledger


class JournalService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    # -------------------------------------------------------------------- categories
    def list_categories(self) -> list[str]:
        saved = self.repo.get_setting("expense_categories")
        if saved is None or not isinstance(saved, list):
            saved = list(config.DEFAULT_EXPENSE_CATEGORIES)
        else:
            saved = [str(c).strip() for c in saved if str(c).strip()]
            for default_cat in config.DEFAULT_EXPENSE_CATEGORIES:
                if not any(normalize_ar(c) == normalize_ar(default_cat) for c in saved):
                    if "أخرى" in saved:
                        saved.insert(saved.index("أخرى"), default_cat)
                    else:
                        saved.append(default_cat)
        if "أخرى" in saved:
            saved = [c for c in saved if c != "أخرى"] + ["أخرى"]
        config.EXPENSE_CATEGORIES[:] = list(saved)
        return list(saved)

    def add_category(self, name: str) -> list[str]:
        clean = (name or "").strip()
        if len(clean) < 2:
            raise ServiceError("اكتب اسم التصنيف (حرفان على الأقل).")
        current = self.list_categories()
        norm_clean = normalize_ar(clean)
        if any(normalize_ar(c) == norm_clean for c in current):
            raise ServiceError(f"التصنيف «{clean}» موجود بالفعل.")
        if "أخرى" in current:
            idx = current.index("أخرى")
            updated = current[:idx] + [clean] + current[idx:]
        else:
            updated = current + [clean]
        self.repo.set_setting("expense_categories", updated)
        config.EXPENSE_CATEGORIES[:] = list(updated)
        return list(updated)

    def delete_category(self, name: str) -> list[str]:
        clean = (name or "").strip()
        if clean == "أخرى":
            raise ServiceError("لا يمكن حذف تصنيف «أخرى».")
        current = self.list_categories()
        if clean not in current:
            raise ServiceError(f"التصنيف «{clean}» غير موجود.")
        led = Ledger(self.repo)
        if any(e.category == clean and e.status == "active" for e in led.expenses):
            raise ServiceError(f"لا يمكن حذف التصنيف «{clean}» لأنه مستخدم في مصروفات مسجلة.")
        updated = [c for c in current if c != clean]
        self.repo.set_setting("expense_categories", updated)
        config.EXPENSE_CATEGORIES[:] = list(updated)
        return list(updated)

    def _check_date(self, d: Optional[date]) -> date:
        d = d or today()
        try:
            return validate_entry_date(d)
        except ValueError as e:
            raise ServiceError(str(e))

    def add_expense(self, amount: float, description: str, category: str = "أخرى",
                    on_date: Optional[date] = None, recipient: Optional[str] = None,
                    attachment: Optional[str] = None) -> int:
        d = self._check_date(on_date)
        if amount is None or amount <= 0:
            raise ServiceError("المبلغ يجب أن يكون أكبر من صفر.")
        if not (description or "").strip():
            raise ServiceError("اكتب بيان المصروف.")
        cat_clean = (category or "").strip() or "أخرى"
        if cat_clean and len(cat_clean) >= 2:
            current_cats = self.list_categories()
            if not any(normalize_ar(c) == normalize_ar(cat_clean) for c in current_cats):
                try:
                    self.add_category(cat_clean)
                except Exception:
                    pass
        with self.repo.transaction():
            xid = self.repo.next_id(Sheet.EXPENSES)
            self.repo.append(Sheet.EXPENSES, dict(
                id=xid, date=d, amount=amount, description=description.strip(),
                category=cat_clean, recipient=(recipient or "").strip() or None,
                attachment=(attachment or "").strip() or None,
                user=self.svc.user(), status="active"))
        return xid

    def add_cashflow(self, kind: str, amount: float, receipt_no: Optional[int] = None,
                     on_date: Optional[date] = None) -> int:
        d = self._check_date(on_date)
        if kind not in ("handover", "petty_cash", "non_cash"):
            raise ServiceError("نوع الحركة غير صحيح.")
        if amount is None or amount <= 0:
            raise ServiceError("المبلغ يجب أن يكون أكبر من صفر.")
        with self.repo.transaction():
            cid = self.repo.next_id(Sheet.CASH_FLOW)
            self.repo.append(Sheet.CASH_FLOW, dict(id=cid, date=d, type=kind, amount=amount,
                                                   receipt_no=receipt_no, user=self.svc.user(), status="active"))
        return cid

    def reverse_expense(self, expense_id: int) -> None:
        e = self.repo.get(Sheet.EXPENSES, id=expense_id)
        if not e or e.status != "active":
            raise ServiceError("المصروف غير موجود أو ملغي بالفعل.")
        self.repo.update(Sheet.EXPENSES, {"id": expense_id}, {"status": "reversed"})

    def reverse_cashflow(self, cashflow_id: int) -> None:
        c = self.repo.get(Sheet.CASH_FLOW, id=cashflow_id)
        if not c or c.status != "active":
            raise ServiceError("الحركة غير موجودة أو ملغاة بالفعل.")
        self.repo.update(Sheet.CASH_FLOW, {"id": cashflow_id}, {"status": "reversed"})

    # -------------------------------------------------------------------- reports
    @staticmethod
    def _cash_totals(led: Ledger, upto: Optional[date] = None, only: Optional[date] = None,
                     d_from: Optional[date] = None, d_to: Optional[date] = None) -> dict[str, float]:
        def ok(d: date) -> bool:
            if d_from is not None and d_to is not None:
                return d_from <= d <= d_to
            return (d == only) if only else (d <= upto)         # type: ignore[operator]
        cash_in = sum(r.amount for r in led.receipts if r.method == "cash" and ok(r.date))
        spent = sum(e.amount for e in led.expenses if ok(e.date))
        cf = [c for c in led._rows(Sheet.CASH_FLOW) if c.status == "active" and ok(c.date)]
        petty = sum(c.amount for c in cf if c.type == "petty_cash")
        hand = sum(c.amount for c in cf if c.type == "handover")
        return dict(cash_in=round(cash_in, 2), expenses=round(spent, 2), petty=round(petty, 2),
                    handover=round(hand, 2), balance=round(cash_in - spent - petty - hand, 2))

    def drawer_balance(self, upto: Optional[date] = None) -> float:
        return self._cash_totals(Ledger(self.repo), upto=upto or today())["balance"]

    def day(self, d: date) -> dict[str, Any]:
        return self.period(d, d)

    def period(self, d_from: date, d_to: date) -> dict[str, Any]:
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        led = Ledger(self.repo)
        names = {s.student_id: s.name_ar for s in led.students.values()}
        receipts = [r for r in led.receipts if d_from <= r.date <= d_to]
        cf = [c for c in led._rows(Sheet.CASH_FLOW) if c.status == "active" and d_from <= c.date <= d_to]
        fmt_r = lambda r: dict(serial=r.serial, date=str(r.date), student=names.get(r.student_id, "—"),
                               amount=r.amount, method=config.PAYMENT_METHODS_AR.get(r.method, r.method),
                               description=r.description or "")
        fmt_c = lambda c: dict(id=c.id, date=str(c.date), amount=c.amount,
                               receipt_no=c.receipt_no or "", status=c.status, user=c.user)
        return dict(
            date=d_to,
            d_from=d_from,
            d_to=d_to,
            days_count=(d_to - d_from).days + 1,
            cash_receipts=[fmt_r(r) for r in receipts if r.method == "cash"],
            noncash_receipts=[fmt_r(r) for r in receipts if r.method != "cash"],
            expenses=[dict(id=e.id, date=str(e.date), amount=e.amount, description=e.description or "",
                           category=e.category,
                           recipient=getattr(e, "recipient", None) or "—",
                           attachment=getattr(e, "attachment", None) or "—",
                           user=e.user) for e in led.expenses if d_from <= e.date <= d_to],
            petty=[fmt_c(c) for c in cf if c.type == "petty_cash"],
            handovers=[fmt_c(c) for c in cf if c.type == "handover"],
            noncash_entries=[fmt_c(c) for c in cf if c.type == "non_cash"],
            day=self._cash_totals(led, d_from=d_from, d_to=d_to),
            total=self._cash_totals(led, upto=d_to),
            receipts_total=round(sum(r.amount for r in receipts), 2),
        )

