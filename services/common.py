"""Shared helpers for the service layer (no UI, no Excel here)."""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Optional


class ServiceError(Exception):
    """Business-rule violation. The message is Arabic and safe to show to the user."""

    def __init__(self, message_ar: str):
        super().__init__(message_ar)
        self.message_ar = message_ar

    def __str__(self) -> str:
        return self.message_ar


def today() -> date:
    return date.today()


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def parse_month(m: str) -> tuple[int, int]:
    y, mo = m.split("-")
    return int(y), int(mo)


def month_bounds(m: str) -> tuple[date, date]:
    y, mo = parse_month(m)
    return date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1])


def shift_month(m: str, n: int) -> str:
    y, mo = parse_month(m)
    idx = y * 12 + (mo - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def months_between(first: str, last: str) -> list[str]:
    out, cur = [], first
    while cur <= last:
        out.append(cur)
        cur = shift_month(cur, 1)
    return out


MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def month_label(m: str) -> str:
    y, mo = parse_month(m)
    return f"{MONTHS_AR[mo - 1]} {y}"


def money(x: Optional[float]) -> str:
    if x is None:
        return "—"
    s = f"{float(x):,.2f}"
    return s[:-3] if s.endswith(".00") else s


_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")


def normalize_ar(text: Optional[str]) -> str:
    """Lower-case, strip diacritics/tatweel, unify alef/yaa/taa-marbuta/digits for searching."""
    if not text:
        return ""
    s = str(text).translate(_AR_DIGITS).lower()
    s = _DIACRITICS.sub("", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    return " ".join(s.split())


def whatsapp_link(mobile: Optional[str], message: str = "") -> Optional[str]:
    """wa.me link for an Egyptian mobile number (None when the number is unusable)."""
    if not mobile:
        return None
    digits = re.sub(r"\D", "", str(mobile).translate(_AR_DIGITS))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "2" + digits
    elif not digits.startswith("20"):
        digits = "20" + digits
    if len(digits) < 11:
        return None
    from urllib.parse import quote
    return f"https://wa.me/{digits}" + (f"?text={quote(message)}" if message else "")


WHATSAPP_TEMPLATES_AR: dict[str, str] = {
    "welcome": "ترحيب وتأكيد تسجيل الطالب",
    "receipt": "تأكيد استلام دفعة / إيصال",
    "absence": "إشعار غياب الطالب اليوم",
    "low_lessons": "تنبيه بقرب انتهاء رصيد الحصص",
    "overdue": "تذكير بسداد القسط المستحق",
    "certificate": "تهنئة بإتمام المستوى التدريبي",
}


def whatsapp_template_message(
    template_key: str,
    student_name: str = "",
    program: str = "",
    remaining_lessons: Optional[int] = None,
    amount: Optional[float | str] = None,
    serial: Optional[int | str] = None,
    **_extra: Any,
) -> str:
    prog_txt = f" في برنامج «{program}»" if program else ""
    amt_str = (money(float(amount)) if isinstance(amount, (int, float)) else str(amount)) if amount is not None else ""
    if template_key == "welcome":
        return (
            f"السلام عليكم ولي أمر الطالب/ة {student_name} الكرام 🌸\n"
            f"نرحب بكم في أكاديمية فانتازيا للتدريب والتكنولوجيا{prog_txt}.\n"
            f"تم تفعيل ملف الطالب بنجاح، ونتمنى له رحلة تعليمية ممتعة ومثمرة!"
        )
    if template_key == "receipt":
        amt_txt = f" بمبلغ {amt_str} ج.م" if amt_str else ""
        ser_txt = f" (إيصال رقم #{serial})" if serial else ""
        return (
            f"السلام عليكم ولي أمر الطالب/ة {student_name} الكرام،\n"
            f"تم استلام دفعة الاشتراك بنجاح{amt_txt}{ser_txt}{prog_txt} — أكاديمية فانتازيا. شكرًا لثقتكم بنا."
        )
    if template_key == "absence":
        return (
            f"السلام عليكم ولي أمر الطالب/ة {student_name} الكرام،\n"
            f"نود إخطاركم بتغيب الطالب عن حصة اليوم ({today()}){prog_txt} في أكاديمية فانتازيا. نتمنى أن يكون بخير!"
        )
    if template_key == "low_lessons":
        rem = remaining_lessons if remaining_lessons is not None else 1
        return (
            f"السلام عليكم ولي أمر الطالب/ة {student_name} الكرام،\n"
            f"نحيطكم علمًا بأن الرصيد المتبقي للطالب هو ({rem} حصة){prog_txt}.\n"
            f"يرجى تجديد الاشتراك لضمان استمرار حضور الطالب في مجموعته — أكاديمية فانتازيا."
        )
    if template_key == "overdue":
        amt_txt = f" بقيمة {amt_str} ج.م" if amt_str else ""
        return (
            f"السلام عليكم ولي أمر الطالب/ة {student_name} الكرام،\n"
            f"تذكير ودي بموعد سداد القسط المستحق للطالب{amt_txt}{prog_txt} — أكاديمية فانتازيا."
        )
    if template_key == "certificate":
        return (
            f"السلام عليكم ولي أمر الطالب/ة {student_name} الكرام 🎉\n"
            f"تهنئ أكاديمية فانتازيا الطالب/ة بإتمام المستوى التدريبي بنجاح وتفوق{prog_txt}!\n"
            f"نتمنى له دوام النجاح والابتكار."
        )
    return f"السلام عليكم، بخصوص الطالب {student_name} — أكاديمية فانتازيا"


def whatsapp_template_link(
    mobile: Optional[str],
    template_key: str,
    student_name: str = "",
    program: str = "",
    remaining_lessons: Optional[int] = None,
    amount: Optional[float | str] = None,
    serial: Optional[int | str] = None,
    **_extra: Any,
) -> Optional[str]:
    msg = whatsapp_template_message(
        template_key, student_name=student_name, program=program,
        remaining_lessons=remaining_lessons, amount=amount, serial=serial,
        **_extra,
    )
    return whatsapp_link(mobile, msg)

