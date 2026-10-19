"""One container that wires every service together (ctx.svc)."""
from __future__ import annotations

from typing import Callable

from core.excel_repo import ExcelRepository
from services.attendance import AttendanceService
from services.employees import EmployeeService
from services.instructors import InstructorService
from services.journal import JournalService
from services.ledger import Ledger
from services.receipts import ReceiptService
from services.reports import ReportService
from services.students import GroupService, StudentService


class Services:
    def __init__(self, repo: ExcelRepository, user: Callable[[], str]):
        self.repo = repo
        self.user = user
        self.students = StudentService(self)
        self.groups = GroupService(self)
        self.receipts = ReceiptService(self)
        self.attendance = AttendanceService(self)
        self.instructors = InstructorService(self)
        self.employees = EmployeeService(self)
        self.journal = JournalService(self)
        self.reports = ReportService(self)

    def ledger(self) -> Ledger:
        return Ledger(self.repo)
