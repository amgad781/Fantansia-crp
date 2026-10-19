# Fantasia Academy CRP — Project Document (v0.2 — Completed)

Desktop management system for **Fantasia Academy** (أكاديمية فانتازيا للتدريب): student registration (bilingual Arabic + English), assessments, subscriptions, receipts, Visa/bank settlement follow-up, attendance, collection, per-group instructor hourly pay + bonuses/deductions + custom statement/receipt printing, employee salaries, daily cash/expenses journal, analytics dashboard, and granular user permissions.

---

## 1. Scope and Users

| Item | Decision |
|---|---|
| Deployment | Windows Desktop App (or local browser mode), single-instance guarded |
| Users | **Owner** (full access), **Receptionist** (daily operations), **Accountant** (financials & settlements), and **Custom** (admin-selected per-page permissions) |
| Concurrency | SQLite in WAL mode with ACID transactions + single-instance OS mutex |
| Primary Storage | **SQLite** (`data/academy.db`) with automatic migration from `data/academy.xlsx` and 1-click full Excel snapshot export |
| Language | Arabic UI (RTL), Cairo font; student names recorded in **both Arabic and English**; dates and numbers in Western digits |
| Instructor Pay | **Per-group hourly rate** (with fallback to instructor base rate / rate history) × held hours **+ bonuses − deductions** |

### Role Permissions (Configurable per User in `/users`)

| Feature (`permission key`) | Receptionist | Accountant | Owner | Custom Role |
|---|:-:|:-:|:-:|:-:|
| Dashboard & KPIs (`dashboard`) | ✘ | ✘ | ✔ | Configurable |
| Students & Registration (`students`) | ✔ | ✘ | ✔ | Configurable |
| Issue Receipts & PDF (`receipts`) | ✔ | ✔ | ✔ | Configurable |
| Visa & Bank Settlement (`settlements`) | ✔ | ✔ | ✔ | Configurable |
| Attendance & Sessions (`attendance`) | ✔ | ✘ | ✔ | Configurable |
| Collection & Overdue (`collection`) | ✔ | ✔ | ✔ | Configurable |
| Groups & Schedules (`groups`) | ✔ | ✘ | ✔ | Configurable |
| Instructors, Bonuses/Deductions & Custom PDF (`instructors`) | ✘ | ✘ | ✔ | Configurable |
| Employee Salaries & Payslips (`employees`) | ✘ | ✘ | ✔ | Configurable |
| Daily Journal & Expenses (`journal`) | ✔ | ✔ | ✔ | Configurable |
| Financial Reports & Charts (`reports`) | ✘ | ✔ | ✔ | Configurable |
| Users, Roles, Permissions & Backups (`users`) | ✘ | ✘ | ✔ | Configurable |

---

## 2. Technology Stack

| Purpose | Library |
|---|---|
| UI in a native desktop window / local web server | `nicegui`, `pywebview` |
| Primary relational database | Python built-in `sqlite3` (WAL mode, ACID transactions, online backup API) |
| Excel import/export & report snapshots | `openpyxl`, `pandas` |
| Schema & record validation | `pydantic` v2 |
| Password hashing | `bcrypt` |
| PDF generation | `reportlab` |
| Arabic text shaping in PDFs | `arabic-reshaper`, `python-bidi` |
| Amount in Arabic words (receipts) | `num2words` |
| Automated test suite | `pytest`, `pytest-asyncio` (86 automated tests) |

Fonts & Branding:
- **Cairo** (`.ttf`) in `assets/fonts/`, used by both the UI and all generated PDFs.
- **Academy Logo**: `assets/logo.png` integrated across the Login screen, Sidebar brand header, and PDF headers.

---

## 3. Architecture

```
UI (NiceGUI RTL pages)  →  Services (business logic + Ledger)  →  ExcelRepository (SQLite WAL + Excel Sync)
                                          ↓
                              Export (ReportLab PDF / Excel)
```

Core Engineering Rules:
1. **Single Source of Truth (`data/academy.db`)**: All 17 tables are stored in SQLite (`academy.db`) with automatic schema migration (`ALTER TABLE` for new columns) and automatic initial import if `academy.xlsx` is present.
2. **Computed, Never Typed Twice**: Collection grids, FIFO fee allocation, remaining lessons, instructor salary to date, net pay after bonuses/deductions, and daily cash drawer balances are dynamically computed by `Ledger`.
3. **No Deletion (Reversal Only)**: Financial and operational records are never deleted; cancelling creates or marks a reversal (`status = reversed`).
4. **Automatic Backups & Audit Trail**: Every transaction creates an online backup in `data/backups/` and records `before`/`after` JSON snapshots in `AuditLog`.

### Folder Structure

```
fantasia_crp/
├── main.py                       # Startup, single-instance lock, login & route registration
├── config.py                     # Paths, constants, categories, payment methods, roles
├── data/
│   ├── academy.db                # Primary SQLite database (WAL mode)
│   ├── academy.xlsx              # Synced / exported Excel workbook
│   ├── backups/                  # Automatic dated backups (.db and .xlsx)
│   └── exports/
│       ├── receipts/             # receipt_<serial>.pdf
│       ├── instructors/          # instructor_<name>_<spec>.pdf (statements & receipts)
│       ├── employees/            # payslip_<name>_<YYYY-MM>.pdf & payroll_<YYYY-MM>.pdf
│       └── reports/              # fantasia_report_<from>_<to>.pdf & .xlsx
├── core/
│   ├── excel_repo.py             # Dual SQLite + Excel repository with transactions & backups
│   ├── schemas.py                # Pydantic v2 models for all 17 tables
│   ├── auth.py                   # Authentication, lockout, roles & granular permissions
│   ├── audit.py                  # Audit log hook & queries
│   ├── context.py                # Application context container
│   └── single_instance.py        # Windows named mutex + lockfile guard
├── services/
│   ├── common.py                 # Arabic normalization, money formatting, date helpers, WhatsApp links
│   ├── ledger.py                 # Read-only FIFO fee allocation, remaining lessons, overdue calculations
│   ├── students.py               # Bilingual student registration (AR/EN), transliteration, assessments, enrollments
│   ├── receipts.py               # Receipt numbering, fee coverage, Visa/bank settlement workflow
│   ├── attendance.py             # Sessions (per-group rate freezing) & attendance tracking (check-in/out, notes)
│   ├── instructors.py            # Per-group hourly rates, bonuses/deductions, payments, custom statements
│   ├── employees.py              # Monthly payroll, bonuses, deductions, payslips
│   ├── journal.py                # Daily cash drawer, expenses (recipient/attachment), petty cash, handovers
│   ├── reports.py                # Monthly & daily-period P&L, KPI analysis, payment method & program analytics
│   └── registry.py               # Service registry
├── ui/
│   ├── layout.py                 # RTL shell, Fantasia Logo Navy & Orange theme, sidebar & top bar
│   ├── components.py             # Reusable tables, date pickers, dialogs, stat cards, badges
│   ├── login_page.py             # Login & first-run setup with Fantasia logo branding
│   ├── dashboard.py              # KPIs, alerts, monthly bar chart, payment method distribution & lead sources
│   ├── students_page.py          # Bilingual student list, profile (5 tabs), and registration form
│   ├── receipts_page.py          # Receipt creation, Visa settlement status, search & PDF export
│   ├── settlements_page.py       # Dedicated Visa & bank transaction settlement follow-up page
│   ├── attendance_page.py        # 4-session attendance grid, check-in/out & session management
│   ├── collection_page.py        # Multi-month collection grid & overdue WhatsApp reminders
│   ├── groups_page.py            # Groups management with assigned instructor & custom group hourly rate
│   ├── instructors_page.py       # Instructor pay to date, bonuses/deductions, custom receipt/statement printer
│   ├── employees_page.py         # Employee monthly salaries, adjustments & bulk payslip export
│   ├── journal_page.py           # Daily cash journal, expenses, petty cash & owner handovers
│   ├── reports_page.py           # Monthly/Daily period reports, operational KPIs, 5 interactive ECharts, PDF & Excel export
│   └── users_page.py             # Admin user management, granular access matrix, audit log & Excel snapshot
├── export/
│   ├── pdf_common.py             # Cairo font registration, Arabic shaping, logo header, amount in words
│   ├── pdf_receipt.py            # Student payment receipt PDF (A5)
│   ├── pdf_instructor.py         # Custom & monthly instructor statement / payment receipt PDF (A4)
│   ├── pdf_payslip.py            # Employee payslip (A5) & monthly payroll summary (A4)
│   ├── pdf_report.py             # Comprehensive period Dashboard & Financial/Operational Analysis PDF (A4)
│   └── service.py                # Export orchestration & audit logging
└── assets/
    ├── logo.png                  # Official Fantasia Academy logo
    └── fonts/                    # Cairo-Regular.ttf, Cairo-Bold.ttf, Cairo-Variable.ttf
```

---

## 4. Database Schema (17 SQLite Tables / Excel Sheets)

| Table / Sheet | Columns |
|---|---|
| **Students** | `student_id`, `name_ar`, **`name_en`**, `dob`, `grade`, `school`, `parent_mobile`, `parent_whatsapp`, `student_mobile`, `address`, `source`, `lives_with`, `siblings_count`, `sibling_rank`, `age_group`, `status`, `created_at`, `created_by` |
| **Assessments** | `student_id`, `date`, `expressing_ideas_grade`, `expressing_ideas_comment`, `communication_grade`, `communication_comment`, `following_instructions_grade`, `following_instructions_comment`, `thinking_grade`, `thinking_comment`, `technical_grade`, `technical_comment`, `track`, `start_level`, `assessor`, `created_at`, `created_by` |
| **Groups** | `group_id`, `cost_center`, `track`, `level`, `instructor_id`, **`instructor_hourly_rate`**, `schedule`, `mode`, `created_at`, `created_by` |
| **Enrollments** | `enrollment_id`, `student_id`, `group_id`, `start_date`, `lessons_purchased`, `status`, `created_at`, `created_by` |
| **FeeSchedule** | `enrollment_id`, `item`, `month`, `amount_due`, `created_at`, `created_by` |
| **Receipts** | `serial`, `date`, `student_id`, `enrollment_id`, `amount`, `method` (`cash`/`visa`/`instapay`/`vodafone_cash`/`other`), `cost_center`, `description`, `status`, `reversal_of`, `user`, **`settlement_status`** (`pending`/`settled`), **`settled_at`**, **`settled_by`**, **`bank_ref`**, `created_at`, `created_by` |
| **Sessions** | `session_id`, `date`, `start_time`, `end_time`, `hours`, `group_id`, `instructor_id`, `course_level`, `status`, `rate_applied`, `amount`, `created_at`, `created_by` |
| **Attendance** | `session_id`, `student_id`, `status`, **`check_in`**, **`check_out`**, `notes`, `created_at`, `created_by` |
| **Instructors** | `instructor_id`, `name`, `phone`, `hourly_rate`, `status`, `created_at`, `created_by` |
| **RateHistory** | `instructor_id`, `effective_from`, `hourly_rate`, `created_at`, `created_by` |
| **InstructorPayments** | `id`, `instructor_id`, `period_from`, `period_to`, `total_hours`, `gross`, **`bonuses`**, **`deductions`**, `previous_paid`, `net`, `method`, `paid_on`, `approved_by`, **`notes`**, `status`, `reversal_of`, `created_at`, `created_by` |
| **Employees** | `employee_id`, `name`, `job_title`, `phone`, `base_salary`, `status`, `created_at`, `created_by` |
| **EmployeePayments** | `id`, `employee_id`, `month`, `base_salary`, `bonuses`, `deductions`, `net`, `method`, `paid_on`, `status`, `reversal_of`, `created_at`, `created_by` |
| **Expenses** | `id`, `date`, `amount`, `description`, `category`, **`recipient`**, **`attachment`**, `user`, `status`, `reversal_of`, `created_at`, `created_by` |
| **CashFlow** | `id`, `date`, `type`, `amount`, `receipt_no`, `user`, `status`, `reversal_of`, `created_at`, `created_by` |
| **Users** | `username`, `password_hash`, `role` (`owner`/`receptionist`/`accountant`/`custom`), **`permissions`**, **`status`**, `created_at`, `created_by` |
| **AuditLog** | `timestamp`, `user`, `action`, `sheet`, `record_id`, `before`, `after`, `created_at`, `created_by` |

---

## 5. Key Calculations & Business Rules

### 5.1 Bilingual Student Identification (`name_ar` + `name_en`)
- Every student is registered with both their **Arabic full name (`name_ar`)** and **English full name (`name_en`)** (minimum 2 words each).
- Typing the Arabic name in the registration form automatically suggests the English transliteration in real time, which the user can freely customize.
- Search works across Arabic name, English name, student ID, and parent/student phone numbers.

### 5.2 Remaining Lessons & Attendance
```
consumed_lessons  = count of attendance rows for the student's enrollment where
                    session.status = held AND attendance.status in (present, late, absent)
remaining_lessons = lessons_purchased - consumed_lessons
```
- `excused` absences do not consume a lesson.
- `lessons_purchased` automatically increases by `4` for each fully paid monthly fee line.

### 5.3 Per-Group Instructor Hourly Rate, Bonuses & Deductions
```
rate_applied = group.instructor_hourly_rate (if set on the group) else instructor's rate on session date
gross        = sum(session.hours × session.rate_applied) for held sessions up to today
net_due      = gross + bonuses - deductions - paid_in_period
```
- Each group can have its own assigned instructor and a **group-specific hourly rate (`instructor_hourly_rate`)**.
- When a session is created/held, `rate_applied` is frozen on the session record so future rate changes never alter historical statements.
- Owners can record **Bonuses (`المكافآت`)** and **Deductions (`الخصومات`)** with explanatory notes per instructor for any period, either beforehand (`مكافآت / خصومات`) or directly inside the payment dialog (`تسجيل دفعة`).

### 5.4 Custom Instructor Receipt / Statement Printing
From `/instructors`, the owner can print or export a customized PDF (`كشف حساب مدرب` or `إيصال صرف مستحقات مدرب`) scoped to:
1. **Specific Group(s)** (`group_ids`)
2. **Specific Month(s)** (`months`) or **Custom Date Range** (`d_from` → `d_to`)
3. **Specific Chosen Session(s)** (interactive checklist of sessions)
4. **Specific Custom Line Item** (custom label + custom amount, e.g., competition coaching or workshop) + custom notes
5. **Specific Recorded Payment** (`payment_id` receipt reprint from the payments table)

### 5.5 Visa & Electronic Payment Settlement Follow-Up (`/settlements`)
- Payment methods: **Cash (`نقدي`), Visa (`فيزا`), InstaPay (`إنستا باي`), Vodafone Cash (`فودافون كاش`), Other (`أخرى`)**.
- Visa transactions default to `settlement_status = "pending"` (`قيد التحصيل البنكي`) until confirmed in `/settlements` as deposited into the academy's bank account (`settled` / `تمت التسوية بالحساب البنكي`) with bank reference and settlement date.

### 5.6 Daily Period Reports & Comprehensive PDF Dashboard Analysis (`/reports`)
- Users can filter `/reports` either **by Month (`تحديد بالشهور`)** or **by Specific Day Range (`فترة مخصصة باليوم`: `من تاريخ` → `إلى تاريخ`)** with 1-click quick presets (**اليوم**, **آخر 7 أيام**, **هذا الشهر**, **آخر 30 يومًا**).
- For any selected date range (and optional program filter), `/reports` computes and displays both financial totals and operational KPIs (**الإيصالات المحصلة**, **الحصص المنفذة**, **نسبة التحصيل**, **نسبة الحضور**, **فيزا معلّقة بالفترة**), plus daily/monthly trend charts.
- Clicking **"تصدير تقرير وتحليل PDF"** or **"طباعة التقرير PDF"** generates an A4 analytical report (`export/pdf_report.py`) containing the executive KPI dashboard, P&L summary, payment method distribution with percentages, revenue by program, expenses by category, instructor cost & net due breakdown, and daily/monthly performance table.

### 5.7 Student Graduation Certificate PDF, QR ID Card & Quick Check-In (`export/pdf_certificate.py`, `/students/{sid}`, `/attendance`)
- **Graduation / Level Completion Certificate PDF (`شهادة إتمام PDF`)**: Generates an A4 landscape bilingual certificate featuring the student's Arabic (`name_ar`) and English (`name_en`) names, completed program & level, grade/evaluation, supervising instructor, and certificate verification number.
- **Student Membership & QR ID Card PDF (`بطاقة العضوية QR`)**: Generates a printable student ID card with a scannable QR code (`FANTASIA-SID:<id>`).
- **Instant QR / ID Attendance Check-In (`تسجيل حضور سريع برقم الطالب أو QR`)**: On `/attendance`, scanning a student's QR code or typing their student ID immediately records them as `present` with check-in timestamp for today's session (automatically creating today's session if needed).

### 5.8 Automated WhatsApp Templates, Waiting List CRM, Sibling Discounts, Schedule Conflict Detection, Group Promotion & Monthly Targets
- **Ready-to-Send WhatsApp Message Templates (`قوالب واتساب`)**: Pre-filled, customizable Arabic WhatsApp templates (`welcome`, `receipt`, `absence`, `low_lessons`, `overdue`, `certificate`) available directly from the student profile.
- **Waiting List & Leads CRM (`قائمة الانتظار والمهتمين بالحجز`)**: Dedicated Leads CRM dialog on `/students` to record prospective students, track follow-up status (`جديد`, `تم التواصل`, `قائمة انتظار`, `تم التسجيل`), and convert leads to enrolled students.
- **Sibling & Scholarship Discounts (`خصم الإخوة / منحة %`)**: Automatically detects registered siblings sharing the same parent phone number, badges the student profile, and applies percentage or fixed discounts to scheduled monthly fees.
- **Automatic Schedule Conflict Detection (`كشف تعارض المواعيد تلقائيًا`)**: Live warnings when assigning an instructor to a group with an overlapping day/time or enrolling a student in a group that conflicts with their active enrollments.
- **1-Click Group Level Promotion (`ترقية المستوى`)**: Upgrades an entire group to the next level (`Level 1` → `Level 2`, etc.) and optionally adds lessons and schedules the new level's monthly fees for all active students in the group.
- **Monthly Revenue Target & Expense Budget Alerts (`مستهدف الإيرادات والميزانية الشهرية`)**: Configurable monthly revenue target and expense budget ceiling on the Dashboard (`/`) with live progress bars and budget-exceeded alerts.
- **1-Click Database Backup Restore (`استعادة النسخة الاحتياطية`)**: Allows the owner on `/users` to restore any historical database backup with an automatic pre-restore safety snapshot.

---

## 6. Brand Color Palette (Matched to Fantasia Logo)

Sampled directly from `assets/logo.png` and applied across the NiceGUI interface (`ui/layout.py`), ECharts visualizations (`ui/reports_page.py`, `ui/dashboard.py`), and ReportLab PDFs (`export/pdf_common.py`):

| Token | Hex | Usage |
|---|---|---|
| **Fantasia Vibrant Orange** (`primary`) | `#F05500` | Primary buttons, active navigation indicator, key highlights, PDF titles & accents |
| **Soft Orange Tint** (`primary_light`) | `#FFF4ED` | Active nav background, summary banners, PDF info box fill |
| **Fantasia Deep Navy** (`navy` / `accent`) | `#0A194E` | Sidebar brand header, table headers, KPI values, secondary actions, PDF table headers |
| **Soft Navy Tint** (`navy_light`) | `#EEF2FF` | Sidebar hover states and secondary badges |
| **Success / Warning / Danger** | `#16A34A` / `#D97706` / `#DC2626` | Financial statuses, Visa pending alerts, overdue and low-lesson badges |
| **Chart Palette** | `["#F05500", "#0A194E", "#FB923C", "#1E3A8A", "#F59E0B", "#16A34A", "#64748B"]` | Bar & donut charts on Dashboard and Reports |

---

## 7. Completed Build Steps & Status

| Step | Deliverable | Status |
|---|---|---|
| **1** | Core repository (`core/excel_repo.py`), Pydantic schemas (`core/schemas.py`), `AuditLog`, `bcrypt` authentication, single-instance lock, RTL shell | ✅ **Completed & Tested** |
| **2** | Students module (`ui/students_page.py`, `services/students.py`): bilingual Arabic + English name registration, live auto-transliteration, **6-question placement survey & smart program/group recommendation engine**, **Waiting List / Leads CRM**, **automatic sibling detection & sibling/scholarship discounts**, **Graduation Certificate PDF**, **Student QR ID Card PDF**, and **WhatsApp message templates** | ✅ **Completed & Tested** |
| **3** | Receipts module (`ui/receipts_page.py`, `export/pdf_receipt.py`): auto-incrementing serials from 220, FIFO fee allocation, Arabic amount-in-words A5 PDF receipt, Visa payment option | ✅ **Completed & Tested** |
| **4** | Visa & Bank Settlements page (`ui/settlements_page.py`): track pending vs. settled Visa/electronic transactions, bank reference numbers, 1-click bank settlement confirmation | ✅ **Completed & Tested** |
| **5** | Collection & Groups (`ui/collection_page.py`, `ui/groups_page.py`, `services/students.py`): multi-month collection matrix, overdue list with WhatsApp reminders, per-group instructor assignment & custom hourly rate, **Admin Educational Programs Management**, **live schedule conflict detection**, and **1-click group level promotion (`ترقية المستوى`)** | ✅ **Completed & Tested** |
| **6** | Sessions & Attendance (`ui/attendance_page.py`, `services/attendance.py`): 4-session group grid, check-in/out times, attendance notes, remaining lessons badge, absence limit warnings, and **instant check-in by Student ID or QR Code (`تسجيل حضور سريع برقم الطالب أو QR`)** | ✅ **Completed & Tested** |
| **7** | Instructors (`ui/instructors_page.py`, `services/instructors.py`, `export/pdf_instructor.py`): per-group hourly rate calculation, **bonuses & deductions**, **custom receipt/statement printing** (by group, month, session, or custom item) | ✅ **Completed & Tested** |
| **8** | Employees & Payroll (`ui/employees_page.py`, `export/pdf_payslip.py`): monthly base salary, bonuses, deductions, individual A5 payslips & combined A4 payroll summary PDF | ✅ **Completed & Tested** |
| **9** | Daily Journal (`ui/journal_page.py`, `services/journal.py`): daily & **multi-day period (`فترة مخصصة بالأيام`)** cash drawer reconciliation, expenses (with recipient & attachment ref), petty cash, and owner handovers | ✅ **Completed & Tested** |
| **10** | Dashboard & Reports (`ui/dashboard.py`, `ui/reports_page.py`, `services/reports.py`, `export/pdf_report.py`): KPIs, **monthly revenue target & expense budget progress/alerts**, **daily date-range filter & quick presets**, monthly/daily revenue vs. cost chart, **payment method distribution graph (`توزيع طرق الدفع`)**, **PDF dashboard & data analysis export (`تصدير تقرير وتحليل PDF`)**, and Excel report export | ✅ **Completed & Tested** |
| **11** | SQLite Primary Engine & Admin Users (`core/excel_repo.py`, `ui/users_page.py`, `core/auth.py`): WAL-mode SQLite (`academy.db`), automatic migration from `academy.xlsx`, 1-click Excel snapshot export, **1-click database backup restore (`استعادة النسخة الاحتياطية`)**, granular user role/permission management, **Admin add/delete educational programs**, and **self-service password change (`تغيير كلمة المرور`) for every account** | ✅ **Completed & Tested** |
| **12** | Brand Identity & Logo Integration (`assets/logo.png`, `ui/layout.py`, `export/pdf_common.py`): full UI & PDF redesign matching the Fantasia Logo Vibrant Orange (`#F05500`) and Deep Navy (`#0A194E`) | ✅ **Completed & Tested** |
