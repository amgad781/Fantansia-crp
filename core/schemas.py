"""Pydantic models for every Excel sheet (section 4 of the project document).

Conventions
-----------
* One model per sheet; field order == column order in Excel.
* ``created_at`` / ``created_by`` are appended to the end of every sheet (rule 5).
* Blank cells are dropped before validation, so defaults / Optional apply.
* Computed values (session hours/amount, payment net) are filled when missing.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Annotated, Any, Optional

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict,
                      Field, model_validator)

import config


# ============================================================================
# Sheet registry
# ============================================================================
class Sheet(str, Enum):
    STUDENTS = "Students"
    ASSESSMENTS = "Assessments"
    GROUPS = "Groups"
    ENROLLMENTS = "Enrollments"
    FEE_SCHEDULE = "FeeSchedule"
    RECEIPTS = "Receipts"
    SESSIONS = "Sessions"
    ATTENDANCE = "Attendance"
    INSTRUCTORS = "Instructors"
    RATE_HISTORY = "RateHistory"
    INSTRUCTOR_PAYMENTS = "InstructorPayments"
    EMPLOYEES = "Employees"
    EMPLOYEE_PAYMENTS = "EmployeePayments"
    EXPENSES = "Expenses"
    CASH_FLOW = "CashFlow"
    USERS = "Users"
    AUDIT_LOG = "AuditLog"


# ============================================================================
# Enums
# ============================================================================
class Role(str, Enum):
    RECEPTIONIST = "receptionist"
    OWNER = "owner"
    ACCOUNTANT = "accountant"
    CUSTOM = "custom"


class EntityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Mode(str, Enum):
    ONLINE = "online"
    ONSITE = "onsite"


class FeeItem(str, Enum):
    MONTHLY = "monthly"
    CONTEST = "contest"
    OTHER = "other"


class PaymentMethod(str, Enum):
    CASH = "cash"
    VISA = "visa"
    INSTAPAY = "instapay"
    VODAFONE_CASH = "vodafone_cash"
    OTHER = "other"


class SettlementStatus(str, Enum):
    SETTLED = "settled"
    PENDING = "pending"


class RecordStatus(str, Enum):
    """Receipts / expenses / cash-flow. Cancelling = new row + original marked reversed."""
    ACTIVE = "active"
    REVERSED = "reversed"


class PayStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    REVERSED = "reversed"


class SessionStatus(str, Enum):
    HELD = "held"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class CashFlowType(str, Enum):
    HANDOVER = "handover"
    PETTY_CASH = "petty_cash"
    NON_CASH = "non_cash"


class PayCycle(str, Enum):
    MONTHLY = "monthly"
    EVERY_4_LESSONS = "every_4_lessons"


# ============================================================================
# Cell-level coercion helpers (values coming back from Excel)
# ============================================================================
def _to_date(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
    return v


def _to_time(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.time().replace(microsecond=0)
    if isinstance(v, str):
        try:
            return time.fromisoformat(v.strip())
        except ValueError:
            return v
    return v


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _clean_phone(v: Any) -> Any:
    if v is None:
        return None
    s = str(v).translate(_AR_DIGITS)
    return re.sub(r"[\s\-().]", "", s) or None


def _round2(v: float) -> float:
    return round(float(v), 2)


ReqDate = Annotated[date, BeforeValidator(_to_date)]
OptDate = Annotated[Optional[date], BeforeValidator(_to_date)]
OptTime = Annotated[Optional[time], BeforeValidator(_to_time)]
Phone = Annotated[Optional[str], BeforeValidator(_clean_phone)]
Money = Annotated[float, AfterValidator(_round2)]
Month = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]      # "YYYY-MM"


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return isinstance(v, float) and v != v          # NaN


# ============================================================================
# Base row
# ============================================================================
class Row(BaseModel):
    model_config = ConfigDict(
        use_enum_values=True,          # enums are stored as plain strings
        validate_default=True,
        coerce_numbers_to_str=True,    # phone typed as number in Excel -> str
        str_strip_whitespace=True,
        extra="ignore",                # user-added columns in Excel are ignored
    )

    created_at: Optional[datetime] = None
    created_by: str = ""

    @model_validator(mode="before")
    @classmethod
    def _drop_blanks(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if not _is_blank(v)}
        return data


# ============================================================================
# Sheet models
# ============================================================================
class Student(Row):
    student_id: int
    name_ar: str = Field(min_length=2)
    name_en: Optional[str] = None
    dob: OptDate = None
    grade: Optional[str] = None
    school: Optional[str] = None
    parent_mobile: Phone = None
    parent_whatsapp: Phone = None
    student_mobile: Phone = None
    address: Optional[str] = None
    source: Optional[str] = None
    lives_with: Optional[str] = None
    siblings_count: Optional[int] = Field(default=None, ge=0)
    sibling_rank: Optional[int] = Field(default=None, ge=1)
    age_group: Optional[str] = None
    status: EntityStatus = EntityStatus.ACTIVE


class Assessment(Row):
    student_id: int
    date: ReqDate
    expressing_ideas_grade: Optional[str] = None       # scale TBD -> free text for now
    expressing_ideas_comment: Optional[str] = None
    communication_grade: Optional[str] = None
    communication_comment: Optional[str] = None
    following_instructions_grade: Optional[str] = None
    following_instructions_comment: Optional[str] = None
    thinking_grade: Optional[str] = None
    thinking_comment: Optional[str] = None
    technical_grade: Optional[str] = None
    technical_comment: Optional[str] = None
    track: Optional[str] = None
    start_level: Optional[str] = None
    assessor: Optional[str] = None


class Group(Row):
    group_id: int
    cost_center: str                                    # program
    track: Optional[str] = None
    level: Optional[str] = None
    instructor_id: Optional[int] = None
    instructor_hourly_rate: Optional[Money] = Field(default=None, ge=0)
    pay_cycle: PayCycle = PayCycle.MONTHLY
    schedule: Optional[str] = None
    mode: Mode = Mode.ONSITE


class Enrollment(Row):
    enrollment_id: int
    student_id: int
    group_id: int
    start_date: ReqDate
    lessons_purchased: int = Field(default=0, ge=0)
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE


class FeeScheduleItem(Row):
    enrollment_id: int
    item: FeeItem = FeeItem.MONTHLY
    month: Month
    amount_due: Money = Field(ge=0)


class Receipt(Row):
    serial: int
    date: ReqDate
    student_id: int
    enrollment_id: Optional[int] = None
    amount: Money
    method: PaymentMethod = PaymentMethod.CASH
    cost_center: Optional[str] = None
    description: Optional[str] = None
    status: RecordStatus = RecordStatus.ACTIVE
    reversal_of: Optional[int] = None
    user: str = ""
    settlement_status: Optional[SettlementStatus] = None
    settled_at: OptDate = None
    settled_by: Optional[str] = None
    bank_ref: Optional[str] = None

    @model_validator(mode="after")
    def _default_settlement(self) -> "Receipt":
        if self.settlement_status is None:
            self.settlement_status = (SettlementStatus.PENDING.value
                                      if self.method == PaymentMethod.VISA.value
                                      else SettlementStatus.SETTLED.value)
        return self


class ClassSession(Row):
    session_id: int
    date: ReqDate
    start_time: OptTime = None
    end_time: OptTime = None
    hours: Optional[float] = Field(default=None, ge=0)
    group_id: int
    instructor_id: int
    course_level: Optional[str] = None
    status: SessionStatus = SessionStatus.HELD
    rate_applied: Optional[Money] = Field(default=None, ge=0)   # frozen when marked held
    amount: Optional[Money] = None
    payment_id: Optional[int] = None

    @model_validator(mode="after")
    def _compute(self) -> "ClassSession":
        if self.hours is None and self.start_time and self.end_time:
            d = datetime.combine(date.min, self.end_time) - datetime.combine(date.min, self.start_time)
            if d.total_seconds() > 0:
                self.hours = round(d.total_seconds() / 3600, 2)
        if self.amount is None and self.hours is not None and self.rate_applied is not None:
            self.amount = round(self.hours * self.rate_applied, 2)
        return self


class AttendanceRecord(Row):
    session_id: int
    student_id: int
    status: AttendanceStatus = AttendanceStatus.PRESENT
    check_in: OptTime = None
    check_out: OptTime = None
    notes: Optional[str] = None


class Instructor(Row):
    instructor_id: int
    name: str = Field(min_length=2)
    phone: Phone = None
    hourly_rate: Money = Field(default=0, ge=0)
    status: EntityStatus = EntityStatus.ACTIVE


class RateHistoryEntry(Row):
    instructor_id: int
    effective_from: ReqDate
    hourly_rate: Money = Field(ge=0)


class InstructorPayment(Row):
    id: int
    instructor_id: int
    group_id: Optional[int] = None
    period_from: ReqDate
    period_to: ReqDate
    total_hours: float = Field(ge=0)
    gross: Money
    bonuses: Money = Field(default=0, ge=0)
    deductions: Money = Field(default=0, ge=0)
    previous_paid: Money = 0
    net: Optional[Money] = None
    method: PaymentMethod = PaymentMethod.CASH
    paid_on: OptDate = None
    approved_by: Optional[str] = None
    notes: Optional[str] = None
    status: PayStatus = PayStatus.PENDING
    reversal_of: Optional[int] = None

    @model_validator(mode="after")
    def _compute(self) -> "InstructorPayment":
        if self.net is None:
            self.net = round(self.gross + self.bonuses - self.deductions - self.previous_paid, 2)
        return self


class Employee(Row):
    employee_id: int
    name: str = Field(min_length=2)
    job_title: Optional[str] = None
    phone: Phone = None
    base_salary: Money = Field(default=0, ge=0)
    status: EntityStatus = EntityStatus.ACTIVE


class EmployeePayment(Row):
    id: int
    employee_id: int
    month: Month
    base_salary: Money = Field(ge=0)
    bonuses: Money = Field(default=0, ge=0)
    deductions: Money = Field(default=0, ge=0)
    net: Optional[Money] = None
    method: PaymentMethod = PaymentMethod.CASH
    paid_on: OptDate = None
    status: PayStatus = PayStatus.PENDING
    reversal_of: Optional[int] = None

    @model_validator(mode="after")
    def _compute(self) -> "EmployeePayment":
        if self.net is None:                              # net = base + bonuses - deductions
            self.net = round(self.base_salary + self.bonuses - self.deductions, 2)
        return self


class Expense(Row):
    id: int
    date: ReqDate
    amount: Money = Field(gt=0)
    description: Optional[str] = None
    category: str = "أخرى"
    recipient: Optional[str] = None
    attachment: Optional[str] = None
    user: str = ""
    status: RecordStatus = RecordStatus.ACTIVE
    reversal_of: Optional[int] = None


class CashFlowEntry(Row):
    id: int
    date: ReqDate
    type: CashFlowType
    amount: Money = Field(gt=0)
    receipt_no: Optional[int] = None
    user: str = ""
    status: RecordStatus = RecordStatus.ACTIVE
    reversal_of: Optional[int] = None


class User(Row):
    username: str = Field(min_length=3)
    password_hash: str
    role: Role
    permissions: Optional[str] = None
    status: EntityStatus = EntityStatus.ACTIVE


class AuditLogEntry(Row):
    timestamp: datetime
    user: str = ""
    action: str
    sheet: Optional[str] = None
    record_id: Optional[str] = None
    before: Optional[str] = None       # JSON
    after: Optional[str] = None        # JSON


# ============================================================================
# Registry helpers
# ============================================================================
SHEET_MODELS: dict[Sheet, type[Row]] = {
    Sheet.STUDENTS: Student,
    Sheet.ASSESSMENTS: Assessment,
    Sheet.GROUPS: Group,
    Sheet.ENROLLMENTS: Enrollment,
    Sheet.FEE_SCHEDULE: FeeScheduleItem,
    Sheet.RECEIPTS: Receipt,
    Sheet.SESSIONS: ClassSession,
    Sheet.ATTENDANCE: AttendanceRecord,
    Sheet.INSTRUCTORS: Instructor,
    Sheet.RATE_HISTORY: RateHistoryEntry,
    Sheet.INSTRUCTOR_PAYMENTS: InstructorPayment,
    Sheet.EMPLOYEES: Employee,
    Sheet.EMPLOYEE_PAYMENTS: EmployeePayment,
    Sheet.EXPENSES: Expense,
    Sheet.CASH_FLOW: CashFlowEntry,
    Sheet.USERS: User,
    Sheet.AUDIT_LOG: AuditLogEntry,
}

# Fields that uniquely identify a row (used for duplicate checks, updates, audit record_id).
KEY_FIELDS: dict[Sheet, tuple[str, ...]] = {
    Sheet.STUDENTS: ("student_id",),
    Sheet.ASSESSMENTS: ("student_id", "date"),
    Sheet.GROUPS: ("group_id",),
    Sheet.ENROLLMENTS: ("enrollment_id",),
    Sheet.FEE_SCHEDULE: ("enrollment_id", "item", "month"),
    Sheet.RECEIPTS: ("serial",),
    Sheet.SESSIONS: ("session_id",),
    Sheet.ATTENDANCE: ("session_id", "student_id"),
    Sheet.INSTRUCTORS: ("instructor_id",),
    Sheet.RATE_HISTORY: ("instructor_id", "effective_from"),
    Sheet.INSTRUCTOR_PAYMENTS: ("id",),
    Sheet.EMPLOYEES: ("employee_id",),
    Sheet.EMPLOYEE_PAYMENTS: ("id",),
    Sheet.EXPENSES: ("id",),
    Sheet.CASH_FLOW: ("id",),
    Sheet.USERS: ("username",),
    Sheet.AUDIT_LOG: (),
}

# Stored columns that are derived from others; the repo recomputes them on update.
DERIVED_FIELDS: dict[Sheet, tuple[str, ...]] = {
    Sheet.SESSIONS: ("amount",),
    Sheet.INSTRUCTOR_PAYMENTS: ("net",),
    Sheet.EMPLOYEE_PAYMENTS: ("net",),
}

_TAIL = ("created_at", "created_by")


def sheet_columns(sheet: Sheet | str) -> list[str]:
    """Header row for a sheet: model fields in order, audit columns last."""
    model = SHEET_MODELS[Sheet(sheet)]
    cols = [f for f in model.model_fields if f not in _TAIL]
    return cols + list(_TAIL)


def record_key(sheet: Sheet | str, row: dict[str, Any]) -> str:
    fields = KEY_FIELDS[Sheet(sheet)]
    return "|".join(str(row.get(f, "")) for f in fields)


def validate_entry_date(d: date, *, today: Optional[date] = None) -> date:
    """Call when a user *enters* a date (not when reading old data).

    Rejects future dates and dates older than ``config.MAX_BACKDATE_DAYS`` – this
    catches the typo dates found in the academy's current receipt log.
    """
    today = today or date.today()
    if d > today:
        raise ValueError("التاريخ في المستقبل")
    if d < today - timedelta(days=config.MAX_BACKDATE_DAYS):
        raise ValueError(f"التاريخ أقدم من {config.MAX_BACKDATE_DAYS} يومًا — تأكد من صحته")
    return d
