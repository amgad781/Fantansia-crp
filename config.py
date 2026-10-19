"""Paths, constants and lookup lists for Fantasia CRP."""
from __future__ import annotations

import sys
from pathlib import Path

APP_NAME_AR = "أكاديمية فانتازيا"
APP_NAME_EN = "Fantasia Academy"
APP_VERSION = "0.1.0"

# --- Paths -----------------------------------------------------------------
# Bundled read-only resources (assets) vs. writable user data (next to the .exe).
if getattr(sys, "frozen", False):                       # PyInstaller build
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "academy.db"
WORKBOOK_PATH = DATA_DIR / "academy.xlsx"
BACKUP_DIR = DATA_DIR / "backups"
EXPORT_DIR = DATA_DIR / "exports"
RECEIPTS_DIR = EXPORT_DIR / "receipts"
INSTRUCTORS_DIR = EXPORT_DIR / "instructors"
EMPLOYEES_DIR = EXPORT_DIR / "employees"
LOG_DIR = DATA_DIR / "logs"
NICEGUI_STORAGE_DIR = DATA_DIR / ".nicegui"

ASSETS_DIR = RESOURCE_DIR / "assets"
FONT_UI_FILE = ASSETS_DIR / "fonts" / "Cairo-Variable.ttf"   # UI (variable font)
LOGO_FILE = ASSETS_DIR / "logo.png"
ICON_FILE = ASSETS_DIR / "logo.ico"

# --- Backups ---------------------------------------------------------------
BACKUP_KEEP_RECENT_HOURS = 24      # keep every backup newer than this ...
BACKUP_MAX_RECENT = 150            # ... capped to the newest N
BACKUP_KEEP_DAILY_DAYS = 60        # older: keep only the last backup of each day

# --- Business rules --------------------------------------------------------
RECEIPT_FIRST_SERIAL = 220         # open decision #1: serial continues from the paper pad
LESSONS_PER_PAID_MONTH = 4         # open decision #3
CONSUMING_ATTENDANCE = ("present", "late", "absent")   # open decision #4 ("excused" excluded)
MAX_BACKDATE_DAYS = 62             # entry-date validation (see schemas.validate_entry_date)

# --- Security --------------------------------------------------------------
MIN_PASSWORD_LEN = 6
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 60
AUTO_LOGOUT_MINUTES = 20

# --- Lookups ---------------------------------------------------------------
PAYMENT_METHODS_AR = {
    "cash": "نقدي",
    "visa": "فيزا",
    "instapay": "إنستا باي",
    "vodafone_cash": "فودافون كاش",
    "other": "أخرى",
}

SETTLEMENT_STATUS_AR = {
    "settled": "في حساب الأكاديمية",
    "pending": "معلّق (قيد التحصيل)",
}

DEFAULT_EXPENSE_CATEGORIES = [
    "إيجار", "كهرباء ومياه", "إنترنت واتصالات", "أدوات ومستلزمات",
    "صيانة", "ضيافة", "مواصلات", "دعاية وتسويق", "أخرى",
]
EXPENSE_CATEGORIES = list(DEFAULT_EXPENSE_CATEGORIES)

ROLE_LABELS_AR = {"receptionist": "موظف الاستقبال", "owner": "المالك", "accountant": "محاسب", "custom": "صلاحيات مخصصة"}

FEATURE_LABELS_AR = {
    "dashboard": "لوحة التحكم",
    "students": "الطلاب والتسجيل",
    "receipts": "الإيصالات",
    "settlements": "متابعة الفيزا والبنك",
    "attendance": "الحضور والغياب",
    "collection": "التحصيل والمتأخرات",
    "groups": "المجموعات",
    "instructors": "المدرّبون وحساباتهم",
    "employees": "الموظفون والرواتب",
    "journal": "اليومية والمصروفات",
    "reports": "التقارير المالية",
    "users": "المستخدمون وسجل العمليات",
}

# --- Step 2+ additions -----------------------------------------------------
ACADEMY_FULL_NAME_AR = "أكاديمية فانتازيا لتطوير الذات والتدريب التكنولوجي"
FONT_PDF_REGULAR = ASSETS_DIR / "fonts" / "Cairo-Regular.ttf"      # static instances (reportlab
FONT_PDF_BOLD = ASSETS_DIR / "fonts" / "Cairo-Bold.ttf"            # cannot use variable fonts)

ABSENCE_LIMIT = 1                  # receipt terms: one absence allowed during the diploma
WHATSAPP_COUNTRY_CODE = "20"       # Egypt: 010xxxxxxxx -> 2010xxxxxxxx

TRACKS_AR = ["روبوتيكس", "برمجة", "ذكاء اصطناعي", "أردوينو"]
LEVELS_AR = ["مبتدئ", "متوسط", "متقدم"]
AGE_GROUPS = ["5-7", "8-10", "11-14", "15-18"]
DEFAULT_PROGRAMS_AR = ["بايثون أونلاين", "بايثون", "أردوينو", "روبوتيكس", "ذكاء اصطناعي", "مسابقة"]
PROGRAMS_AR = list(DEFAULT_PROGRAMS_AR)
LEAD_SOURCES_AR = ["فيسبوك", "إنستجرام", "واتساب", "صديق / معارف", "لافتة / مرور", "أخرى"]
ASSESSMENT_CRITERIA = [
    ("expressing_ideas", "التعبير عن الأفكار"),
    ("communication", "التواصل"),
    ("following_instructions", "اتباع التعليمات"),
    ("thinking", "مهارات التفكير"),
    ("technical", "المهارات التقنية"),
]
RECEIPT_TERMS_AR = [
    "1- يمكن استرداد رسوم الاشتراك أو استمارة الحجز أو التحويل من نشاط لآخر في موعد أقصاه يومين قبل بدء النشاط.",
    "2- عند حضور المتدرب أول مرة من النشاط ورغب في الخروج منه يتم خصم 50% من قيمة الاشتراك، "
    "وإذا حضر أكثر من مرة يتم خصم الاشتراك بالكامل.",
    "3- يتم سداد قيمة النشاط قبل بداية أول سيشن من الشهر التدريبي.",
    "4- نظام الحضور والغياب: مسموح للمتدرب بالغياب مرة واحدة خلال مدة الدبلومة.",
]
