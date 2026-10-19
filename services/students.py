"""Students, assessments, groups, enrollments and fee schedules (build-plan steps 2 and 4)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import config
from core.schemas import Sheet
from services.common import ServiceError, month_key, normalize_ar, shift_month, today


_AR_NAME_MAP = {
    "احمد": "Ahmed", "أحمد": "Ahmed", "محمد": "Mohamed", "محمود": "Mahmoud",
    "مصطفى": "Mostafa", "مصطفي": "Mostafa", "علي": "Ali", "على": "Ali",
    "عمر": "Omar", "عمرو": "Amr", "يوسف": "Youssef", "ابراهيم": "Ibrahim",
    "إبراهيم": "Ibrahim", "اسماعيل": "Ismail", "إسماعيل": "Ismail",
    "حسن": "Hassan", "حسين": "Hussein", "خالد": "Khaled", "وليد": "Walid",
    "طارق": "Tarek", "كريم": "Karim", "شريف": "Sherif", "تامر": "Tamer",
    "رامي": "Ramy", "رامى": "Ramy", "هشام": "Hisham", "عادل": "Adel",
    "اشرف": "Ashraf", "أشرف": "Ashraf", "ايمن": "Ayman", "أيمن": "Ayman",
    "سعيد": "Saeed", "سمير": "Samir", "سليم": "Selim", "زياد": "Ziad",
    "ادم": "Adam", "آدم": "Adam", "ياسين": "Yassin", "حمزة": "Hamza",
    "حمزه": "Hamza", "مروان": "Marwan", "اياد": "Eyad", "إياد": "Eyad",
    "سيف": "Seif", "مازن": "Mazen", "زين": "Zein", "قنديل": "Kandil",
    "سارة": "Sara", "ساره": "Sara", "مريم": "Mariam", "فاطمة": "Fatma",
    "فاطمه": "Fatma", "نور": "Nour", "ياسمين": "Yasmin", "سلمى": "Salma",
    "سلمي": "Salma", "ملك": "Malak", "جنى": "Jana", "جني": "Jana",
    "حبيبة": "Habiba", "حبيبه": "Habiba", "ليلى": "Laila", "ليلي": "Laila",
    "سما": "Sama", "هنا": "Hana", "فريدة": "Farida", "فريده": "Farida",
    "رقية": "Roqaya", "رقيه": "Roqaya", "تسنيم": "Tasneem", "ندى": "Nada",
    "منة": "Menna", "منه": "Menna", "هاجر": "Hagar", "شهد": "Shahd",
    "فرح": "Farah", "يارا": "Yara", "لينا": "Lina", "دينا": "Dina",
    "رانيا": "Rania", "نورهان": "Nourhan", "محسن": "Mohsen", "جمال": "Gamal",
    "كمال": "Kamal", "نبيل": "Nabil", "صلاح": "Salah", "مجدي": "Magdy",
    "مجدى": "Magdy", "عبدالله": "Abdullah", "عبدالرحمن": "Abdelrahman",
    "عبدالعزيز": "Abdelaziz", "عبدالحميد": "Abdelhamid", "السيد": "Elsayed",
}

_AR_CHAR_MAP = {
    "ا": "a", "أ": "a", "إ": "e", "آ": "a", "ء": "", "ؤ": "o", "ئ": "e",
    "ب": "b", "ت": "t", "ث": "th", "ج": "g", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh",
    "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "ة": "a", "و": "w", "ي": "y", "ى": "a",
}


def transliterate_ar_to_en(text: str) -> str:
    """Convert an Arabic name into a readable English name."""
    words = [w.strip() for w in (text or "").split() if w.strip()]
    out: list[str] = []
    i = 0
    while i < len(words):
        if words[i] == "عبد" and i + 1 < len(words):
            combined = "عبد" + words[i + 1]
            if combined in _AR_NAME_MAP:
                out.append(_AR_NAME_MAP[combined])
                i += 2
                continue
        w = words[i]
        if w in _AR_NAME_MAP:
            out.append(_AR_NAME_MAP[w])
        elif all(ord(c) < 128 for c in w):
            out.append(w.capitalize())
        else:
            mapped = "".join(_AR_CHAR_MAP.get(ch, ch if ord(ch) < 128 else "") for ch in w)
            out.append((mapped or "Student").capitalize())
        i += 1
    return " ".join(out)


SURVEY_QUESTIONS: list[dict[str, Any]] = [
    dict(
        key="interest",
        question="1. ما هو أكثر نشاط يجذب اهتمام الطالب؟",
        options={
            "hardware": "تركيب المجسمات والدوائر الإلكترونية والمحركات",
            "coding": "تصميم الألعاب والتطبيقات وكتابة الأكواد",
            "ai": "الذكاء الاصطناعي والأنظمة الذكية وتحليل البيانات",
            "competition": "المشاركة في البطولات والمسابقات الجماعية",
        },
        default="hardware",
    ),
    dict(
        key="experience",
        question="2. ما هي الخبرة السابقة للطالب في البرمجة أو الإلكترونيات؟",
        options={
            "none": "لا توجد خبرة سابقة (يبدأ من الصفر)",
            "visual": "جرب البرمجة المرئية (Scratch / Blockly) أو تركيب الليجو",
            "text_or_hw": "كتب أكواد نصية (Python / C++) أو ركّب دوائر أردوينو سابقًا",
        },
        default="none",
    ),
    dict(
        key="style",
        question="3. ما هي طريقة التعلم المفضلة للطالب؟",
        options={
            "hands_on": "التجربة العملية باليد والأدوات الملموسة",
            "screen": "التفكير المنطقي وحل التحديات على شاشة الكمبيوتر",
            "both": "الجمع بين التركيب العملي والبرمجة على الكمبيوتر",
        },
        default="both",
    ),
    dict(
        key="computer_skill",
        question="4. ما مدى إتقان الطالب لاستخدام الكمبيوتر والكتابة بالإنجليزية؟",
        options={
            "basic": "مبتدئ (يحتاج مساعدة في الماوس ولوحة المفاتيح)",
            "good": "جيد (يتعامل مع الكمبيوتر ويكتب الحروف الإنجليزية)",
            "advanced": "ممتاز وسريع في التعامل مع البرامج والكتابة",
        },
        default="good",
    ),
    dict(
        key="mode",
        question="5. ما هو نظام الحضور المفضل لولي الأمر والطالب؟",
        options={
            "onsite": "حضوري بمقر الأكاديمية",
            "online": "أونلاين من المنزل",
        },
        default="onsite",
    ),
    dict(
        key="goal",
        question="6. ما هو الهدف الأساسي من الالتحاق بالأكاديمية؟",
        options={
            "foundation": "تأسيس قوي في التكنولوجيا والتفكير المنطقي",
            "projects": "بناء مشاريع عملية وابتكارات إلكترونية وبرمجية",
            "competitions": "التأهل للمسابقات والبطولات المحلية والدولية",
        },
        default="foundation",
    ),
]


class StudentService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    # ------------------------------------------------------------------ recommendation engine
    def recommend_program(
        self,
        survey: Optional[dict[str, str]] = None,
        age_group: Optional[str] = None,
        assessment: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Score available programs based on survey answers, student age group, and 5-criteria assessment."""
        s = {q["key"]: (survey or {}).get(q["key"], q["default"]) for q in SURVEY_QUESTIONS}
        assess = assessment or {}
        avail_programs = self.svc.groups.list_programs()
        scores: dict[str, float] = {p: 10.0 for p in avail_programs}
        for core_p in ("روبوتيكس", "أردوينو", "بايثون", "بايثون أونلاين", "ذكاء اصطناعي", "مسابقة"):
            scores.setdefault(core_p, 10.0)

        reasons: list[str] = []

        # 1. Age group weighting
        if age_group == "5-7":
            scores["روبوتيكس"] += 35
            reasons.append("الفئة العمرية (5-7 سنوات) تناسبها أنشطة الروبوتيكس التفاعلية والتركيب الحركي.")
        elif age_group == "8-10":
            scores["روبوتيكس"] += 25
            scores["أردوينو"] += 20
            scores["بايثون"] += 15
            reasons.append("الفئة العمرية (8-10 سنوات) مثالية للروبوتيكس وبدايات الأردوينو والبرمجة.")
        elif age_group == "11-14":
            scores["أردوينو"] += 25
            scores["بايثون"] += 28
            scores["بايثون أونلاين"] += 22
            scores["ذكاء اصطناعي"] += 20
            reasons.append("الفئة العمرية (11-14 سنة) جاهزة للبرمجة النصية (بايثون) والدوائر الإلكترونية (أردوينو).")
        elif age_group == "15-18":
            scores["بايثون"] += 30
            scores["ذكاء اصطناعي"] += 32
            scores["أردوينو"] += 25
            scores["بايثون أونلاين"] += 25
            reasons.append("الفئة العمرية (15-18 سنة) مؤهلة لمسارات الذكاء الاصطناعي والبرمجة المتقدمة والأنظمة المدمجة.")

        # 2. Primary Interest
        interest = s.get("interest")
        if interest == "hardware":
            scores["روبوتيكس"] += 30
            scores["أردوينو"] += 32
            reasons.append("اهتمام الطالب بتركيب المجسمات والدوائر يدعم مسار الأردوينو والروبوتيكس.")
        elif interest == "coding":
            scores["بايثون"] += 35
            scores["بايثون أونلاين"] += 30
            reasons.append("شغف الطالب بتصميم الألعاب والتطبيقات والأكواد يتوافق مباشرة مع برنامج بايثون.")
        elif interest == "ai":
            scores["ذكاء اصطناعي"] += 38
            scores["بايثون"] += 25
            reasons.append("اهتمام الطالب بالأنظمة الذكية والبيانات يرشحه بقوة لبرنامج الذكاء الاصطناعي وبايثون.")
        elif interest == "competition":
            scores["مسابقة"] += 40
            scores["روبوتيكس"] += 25
            reasons.append("رغبة الطالب في خوض البطولات الجماعية تجعله مناسبًا لفرق المسابقات والروبوتيكس.")

        # 3. Learning Style
        style = s.get("style")
        if style == "hands_on":
            scores["أردوينو"] += 20
            scores["روبوتيكس"] += 22
        elif style == "screen":
            scores["بايثون"] += 22
            scores["بايثون أونلاين"] += 22
            scores["ذكاء اصطناعي"] += 20
        else:
            scores["أردوينو"] += 15
            scores["روبوتيكس"] += 15
            scores["بايثون"] += 12

        # 4. Computer & English Typing Skill
        comp = s.get("computer_skill")
        if comp == "basic":
            scores["روبوتيكس"] += 22
            scores["بايثون"] -= 10
            scores["ذكاء اصطناعي"] -= 15
        elif comp == "good":
            scores["أردوينو"] += 15
            scores["بايثون"] += 15
        elif comp == "advanced":
            scores["بايثون"] += 20
            scores["ذكاء اصطناعي"] += 25
            scores["بايثون أونلاين"] += 18

        # 5. Attendance Mode (Onsite vs Online)
        mode = s.get("mode")
        if mode == "online":
            scores["بايثون أونلاين"] += 45
            reasons.append("تفضيل الحضور أونلاين يرشح «بايثون أونلاين» كأفضل خيار متاح عن بُعد.")
        else:
            scores["بايثون أونلاين"] -= 20

        # 6. Goal
        goal = s.get("goal")
        if goal == "competitions":
            scores["مسابقة"] += 35
            scores["روبوتيكس"] += 15
        elif goal == "projects":
            scores["أردوينو"] += 18
            scores["ذكاء اصطناعي"] += 15
            scores["بايثون"] += 15
        else:
            scores["روبوتيكس"] += 12
            scores["بايثون"] += 12

        # 7. Assessment grades (1..5)
        grade_vals = []
        for k, _ in config.ASSESSMENT_CRITERIA:
            raw_g = assess.get(f"{k}_grade")
            if raw_g and str(raw_g).isdigit():
                grade_vals.append(int(raw_g))
        avg_grade = (sum(grade_vals) / len(grade_vals)) if grade_vals else 3.0
        tech_g = int(assess["technical_grade"]) if str(assess.get("technical_grade") or "").isdigit() else 3
        think_g = int(assess["thinking_grade"]) if str(assess.get("thinking_grade") or "").isdigit() else 3

        if think_g >= 4 and tech_g >= 4:
            scores["ذكاء اصطناعي"] += 15
            scores["مسابقة"] += 15

        # Determine starting level
        exp = s.get("experience")
        if exp == "text_or_hw" and avg_grade >= 4.0:
            start_level = "متقدم"
        elif exp == "text_or_hw" or (exp == "visual" and avg_grade >= 3.5) or avg_grade >= 4.4:
            start_level = "متوسط"
        else:
            start_level = "مبتدئ"

        # Filter to available programs if any exist, otherwise all scored programs
        candidate_pool = avail_programs if avail_programs else list(scores.keys())
        ranked_raw = sorted(
            ((p, max(5.0, scores.get(p, 15.0))) for p in candidate_pool),
            key=lambda x: -x[1],
        )
        top_score = ranked_raw[0][1] if ranked_raw else 100.0
        rankings = [
            dict(program=p, score=round(min(99, max(45, (sc / max(top_score, 1.0)) * 96))))
            for p, sc in ranked_raw[:4]
        ]
        best_program = rankings[0]["program"] if rankings else "روبوتيكس"

        # Map recommended program -> track
        prog_to_track = {
            "روبوتيكس": "روبوتيكس",
            "أردوينو": "أردوينو",
            "بايثون": "برمجة",
            "بايثون أونلاين": "برمجة",
            "ذكاء اصطناعي": "ذكاء اصطناعي",
            "مسابقة": "روبوتيكس",
        }
        best_track = prog_to_track.get(best_program, config.TRACKS_AR[0] if config.TRACKS_AR else "برمجة")

        # Find best matching group in ledger
        led = self.svc.ledger()
        matching_group_id: Optional[int] = None
        for g in led.groups.values():
            if g.cost_center == best_program and (not g.level or g.level == start_level):
                matching_group_id = g.group_id
                break
        if matching_group_id is None:
            for g in led.groups.values():
                if g.cost_center == best_program:
                    matching_group_id = g.group_id
                    break

        return dict(
            program=best_program,
            track=best_track,
            start_level=start_level,
            match_pct=rankings[0]["score"] if rankings else 95,
            rankings=rankings,
            reasons=reasons[:3],
            suggested_group_id=matching_group_id,
        )

    # ------------------------------------------------------------------ students
    def register(self, student: dict[str, Any], assessment: Optional[dict[str, Any]] = None,
                 enrollment: Optional[dict[str, Any]] = None) -> int:
        """Create student (+ assessment, + enrollment with fee schedule) in ONE atomic write."""
        name = " ".join(str(student.get("name_ar", "")).split())
        if len(name.split()) < 2:
            raise ServiceError("اكتب اسم الطالب ثنائيًا على الأقل (بالعربية).")
        if "name_en" in student and student["name_en"] is not None:
            name_en = " ".join(str(student.get("name_en", "")).split())
            if len(name_en.split()) < 2:
                raise ServiceError("اكتب اسم الطالب بالإنجليزية (ثنائيًا على الأقل).")
        else:
            name_en = transliterate_ar_to_en(name)
        student = {**student, "name_ar": name, "name_en": name_en}
        mobile = student.get("parent_mobile")
        for s in self.repo.read(Sheet.STUDENTS):
            if normalize_ar(s.name_ar) == normalize_ar(name) and (not mobile or s.parent_mobile == mobile or not s.parent_mobile):
                raise ServiceError(f"الطالب «{s.name_ar}» مسجل بالفعل (رقم {s.student_id}).")
        with self.repo.transaction():
            sid = self.repo.next_id(Sheet.STUDENTS)
            self.repo.append(Sheet.STUDENTS, {**student, "student_id": sid, "status": "active"})
            if assessment and any(v not in (None, "") for k, v in assessment.items()):
                self.save_assessment(sid, assessment)
            if enrollment:
                self.add_enrollment(sid, **enrollment)
        return sid

    def update_student(self, student_id: int, changes: dict[str, Any]) -> None:
        changes = {k: v for k, v in changes.items() if k not in ("student_id", "created_at", "created_by")}
        if "name_ar" in changes:
            changes["name_ar"] = " ".join(str(changes["name_ar"]).split())
            if len(changes["name_ar"].split()) < 2:
                raise ServiceError("اكتب اسم الطالب ثنائيًا على الأقل (بالعربية).")
        if "name_en" in changes and changes["name_en"] is not None:
            changes["name_en"] = " ".join(str(changes["name_en"]).split())
            if len(changes["name_en"].split()) < 2:
                raise ServiceError("اكتب اسم الطالب بالإنجليزية (ثنائيًا على الأقل).")
        self.repo.update(Sheet.STUDENTS, {"student_id": student_id}, changes)

    def save_assessment(self, student_id: int, data: dict[str, Any], on_date: Optional[date] = None) -> None:
        on_date = on_date or today()
        row = {k: v for k, v in data.items() if k not in ("student_id", "date")}
        existing = self.repo.get(Sheet.ASSESSMENTS, student_id=student_id, date=on_date)
        if existing:
            self.repo.update(Sheet.ASSESSMENTS, {"student_id": student_id, "date": on_date}, row)
        else:
            self.repo.append(Sheet.ASSESSMENTS, {**row, "student_id": student_id, "date": on_date})

    def latest_assessment(self, student_id: int):
        rows = [a for a in self.repo.read(Sheet.ASSESSMENTS) if a.student_id == student_id]
        return max(rows, key=lambda a: a.date) if rows else None

    # --------------------------------------------------------------- siblings & discounts
    def detect_siblings(self, parent_mobile: Optional[str], exclude_student_id: Optional[int] = None) -> list[Any]:
        import re
        if not parent_mobile:
            return []
        digits = re.sub(r"\D", "", str(parent_mobile))
        if len(digits) < 8:
            return []
        tail = digits[-9:]
        out = []
        for s in self.repo.read(Sheet.STUDENTS):
            if exclude_student_id and s.student_id == exclude_student_id:
                continue
            pm = re.sub(r"\D", "", str(s.parent_mobile or ""))
            pw = re.sub(r"\D", "", str(s.parent_whatsapp or ""))
            if (pm and pm.endswith(tail)) or (pw and pw.endswith(tail)):
                out.append(s)
        return out

    # --------------------------------------------------------------- waiting list / leads CRM
    def list_leads(self) -> list[dict[str, Any]]:
        leads = self.repo.get_setting("waiting_list", [])
        if not isinstance(leads, list):
            return []
        return sorted(leads, key=lambda x: -int(x.get("id", 0)))

    def add_lead(self, name_ar: str, phone: str, age_group: str = "",
                 recommended_program: str = "", program: str = "",
                 source: str = "", notes: str = "") -> dict[str, Any]:
        clean_name = " ".join((name_ar or "").split())
        if len(clean_name) < 2:
            raise ServiceError("اكتب اسم الطالب المهتم بالحجز.")
        clean_phone = (phone or "").strip()
        if len(clean_phone) < 8:
            raise ServiceError("أدخل رقم موبايل ولي الأمر للتواصل.")
        leads = self.list_leads()
        next_id = (max((int(l.get("id", 0)) for l in leads), default=0) + 1)
        prog_val = (program or recommended_program or "").strip()
        entry = dict(
            id=next_id,
            name=clean_name,
            name_ar=clean_name,
            name_en=transliterate_ar_to_en(clean_name),
            phone=clean_phone,
            age_group=age_group or "",
            program=prog_val,
            recommended_program=prog_val,
            source=source or "",
            status="جديد",
            notes=(notes or "").strip(),
            created_at=str(today()),
        )
        leads.append(entry)
        self.repo.set_setting("waiting_list", leads)
        return entry

    def update_lead_status(self, lead_id: int, status: str, notes: Optional[str] = None) -> dict[str, Any]:
        leads = self.list_leads()
        target = None
        for l in leads:
            if int(l.get("id", 0)) == int(lead_id):
                l["status"] = status
                if notes is not None:
                    l["notes"] = notes.strip()
                target = l
                break
        if not target:
            raise ServiceError("السجل غير موجود في قائمة الانتظار.")
        self.repo.set_setting("waiting_list", leads)
        return target

    def delete_lead(self, lead_id: int) -> None:
        leads = [l for l in self.list_leads() if int(l.get("id", 0)) != int(lead_id)]
        self.repo.set_setting("waiting_list", leads)

    # --------------------------------------------------------------- student certificates history
    def list_certificates(self, student_id: Optional[int] = None) -> list[dict[str, Any]]:
        certs = self.repo.get_setting("student_certificates", [])
        if not isinstance(certs, list):
            return []
        if student_id is not None:
            certs = [c for c in certs if int(c.get("student_id", 0)) == int(student_id)]
        return sorted(certs, key=lambda x: -int(x.get("cert_id", 0)))

    def add_certificate(
        self,
        student_id: int,
        program: str,
        level: str = "",
        grade: str = "امتياز",
        instructor: str = "",
        issue_date: Optional[date | str] = None,
        notes: str = "",
        pdf_path: str = "",
    ) -> dict[str, Any]:
        st = self.repo.get(Sheet.STUDENTS, student_id=student_id)
        if not st:
            raise ServiceError("الطالب غير موجود.")
        clean_prog = (program or "").strip()
        if not clean_prog:
            raise ServiceError("اختر البرنامج التعليمي للشهادة.")
        all_certs = self.repo.get_setting("student_certificates", [])
        if not isinstance(all_certs, list):
            all_certs = []
        next_id = max((int(c.get("cert_id", 0)) for c in all_certs), default=0) + 1
        d_str = str(issue_date or today())
        serial = f"CERT-{d_str[:4]}-{next_id:04d}"
        entry = dict(
            cert_id=next_id,
            serial=serial,
            student_id=int(student_id),
            student_name=st.name_ar,
            program=clean_prog,
            level=(level or "Level 1").strip(),
            grade=(grade or "امتياز").strip(),
            instructor=(instructor or "").strip(),
            issue_date=d_str,
            notes=(notes or "").strip(),
            pdf_path=str(pdf_path or ""),
            created_by=self.svc.user(),
        )
        all_certs.append(entry)
        self.repo.set_setting("student_certificates", all_certs)
        return entry

    def delete_certificate(self, cert_id: int) -> None:
        all_certs = self.repo.get_setting("student_certificates", [])
        if not isinstance(all_certs, list):
            return
        updated = [c for c in all_certs if int(c.get("cert_id", 0)) != int(cert_id)]
        self.repo.set_setting("student_certificates", updated)

    # --------------------------------------------------------------- schedule conflict check
    @staticmethod
    def _schedules_overlap(s1: Optional[str], s2: Optional[str]) -> bool:
        n1, n2 = normalize_ar(s1 or ""), normalize_ar(s2 or "")
        if not n1 or not n2:
            return False
        if n1 == n2 or n1 in n2 or n2 in n1:
            return True
        days = ("السبت", "سبت", "الاحد", "احد", "الاثنين", "اثنين", "الثلاثاء", "ثلاثاء", "الاربعاء", "اربعاء", "الخميس", "خميس", "الجمعة", "جمعة")
        d1 = {d.lstrip("ال") for d in days if d in n1}
        d2 = {d.lstrip("ال") for d in days if d in n2}
        import re
        t1 = set(re.findall(r"\d+", n1))
        t2 = set(re.findall(r"\d+", n2))
        if d1 and d2 and (d1 & d2):
            if not t1 or not t2 or (t1 & t2):
                return True
        return False

    def check_student_schedule_conflicts(self, student_id: int, group_id: int) -> list[dict[str, Any]]:
        g_new = self.repo.get(Sheet.GROUPS, group_id=group_id)
        if not g_new or not (g_new.schedule or "").strip():
            return []
        groups = {g.group_id: g for g in self.repo.read(Sheet.GROUPS)}
        conflicts: list[dict[str, Any]] = []
        for e in self.repo.read(Sheet.ENROLLMENTS):
            if e.student_id == student_id and e.group_id != group_id and e.status in ("active", "paused"):
                g_other = groups.get(e.group_id)
                if g_other and g_other.schedule and self._schedules_overlap(g_other.schedule, g_new.schedule):
                    conflicts.append(dict(
                        group_id=g_other.group_id,
                        label=f"{g_other.cost_center} (#{g_other.group_id})",
                        schedule=g_other.schedule,
                        message=f"تعارض مواعيد للطالب مع مجموعة «{g_other.cost_center}» (#{g_other.group_id} — {g_other.schedule})",
                    ))
        return conflicts

    # --------------------------------------------------------------- enrollments
    def add_enrollment(self, student_id: int, group_id: int, start_date: Optional[date] = None,
                       monthly_fee: float = 0, months: int = 1, contest_fee: float = 0,
                       lessons: int = 0, discount_pct: float = 0.0, discount_amount: float = 0.0) -> int:
        start_date = start_date or today()
        if not self.repo.get(Sheet.STUDENTS, student_id=student_id):
            raise ServiceError("الطالب غير موجود.")
        if not self.repo.get(Sheet.GROUPS, group_id=group_id):
            raise ServiceError("اختر مجموعة صحيحة.")
        for e in self.repo.read(Sheet.ENROLLMENTS):
            if e.student_id == student_id and e.group_id == group_id and e.status in ("active", "paused"):
                raise ServiceError("الطالب مشترك بالفعل في هذه المجموعة.")
        disc_p = max(0.0, min(100.0, float(discount_pct or 0.0)))
        disc_a = max(0.0, float(discount_amount or 0.0))
        eff_fee = round(max(0.0, float(monthly_fee or 0.0) * (1.0 - disc_p / 100.0) - disc_a), 2)
        with self.repo.transaction():
            eid = self.repo.next_id(Sheet.ENROLLMENTS)
            self.repo.append(Sheet.ENROLLMENTS, dict(
                enrollment_id=eid, student_id=student_id, group_id=group_id, start_date=start_date,
                lessons_purchased=max(0, int(lessons)), status="active"))
            m0 = month_key(start_date)
            if eff_fee and eff_fee > 0:
                for i in range(max(1, int(months))):
                    self.add_fee(eid, "monthly", shift_month(m0, i), eff_fee)
            if contest_fee and contest_fee > 0:
                self.add_fee(eid, "contest", m0, contest_fee)
        return eid

    def add_fee(self, enrollment_id: int, item: str, month: str, amount: float) -> None:
        if amount is None or amount <= 0:
            raise ServiceError("قيمة الرسوم يجب أن تكون أكبر من صفر.")
        if not self.repo.get(Sheet.ENROLLMENTS, enrollment_id=enrollment_id):
            raise ServiceError("الاشتراك غير موجود.")
        if self.repo.get(Sheet.FEE_SCHEDULE, enrollment_id=enrollment_id, item=item, month=month):
            raise ServiceError("هذا البند مسجل بالفعل لنفس الشهر. اختر شهرًا أو بندًا آخر.")
        self.repo.append(Sheet.FEE_SCHEDULE, dict(enrollment_id=enrollment_id, item=item,
                                                  month=month, amount_due=amount))

    def set_lessons(self, enrollment_id: int, lessons: int) -> None:
        if lessons < 0:
            raise ServiceError("عدد الحصص لا يمكن أن يكون سالبًا.")
        self.repo.update(Sheet.ENROLLMENTS, {"enrollment_id": enrollment_id},
                         {"lessons_purchased": int(lessons)})

    def set_enrollment_status(self, enrollment_id: int, status: str) -> None:
        self.repo.update(Sheet.ENROLLMENTS, {"enrollment_id": enrollment_id}, {"status": status})


class GroupService:
    def __init__(self, svc):
        self.svc = svc
        self.repo = svc.repo

    # ---- Schedule Conflict Detection & Level Promotion ----
    def check_schedule_conflicts(self, instructor_id: Optional[int], schedule: Optional[str],
                                 exclude_group_id: Optional[int] = None) -> list[dict[str, Any]]:
        if not instructor_id or not (schedule or "").strip():
            return []
        conflicts: list[dict[str, Any]] = []
        for g in self.repo.read(Sheet.GROUPS):
            if exclude_group_id and g.group_id == exclude_group_id:
                continue
            if g.instructor_id == instructor_id and g.schedule and StudentService._schedules_overlap(g.schedule, schedule):
                conflicts.append(dict(
                    group_id=g.group_id,
                    label=self.label(g),
                    schedule=g.schedule,
                    message=f"تعارض موعد المدرب مع مجموعة «{g.cost_center}» (#{g.group_id} — {g.schedule})",
                ))
        return conflicts

    def promote_group(self, group_id: int, new_level: Optional[str] = None,
                      add_lessons: int = 0, renew_months: int = 0, monthly_fee: float = 0.0) -> dict[str, Any]:
        g = self.repo.get(Sheet.GROUPS, group_id=group_id)
        if not g:
            raise ServiceError("المجموعة غير موجودة.")
        levels = list(config.LEVELS_AR)
        if not new_level:
            if g.level in levels:
                idx = levels.index(g.level)
                new_level = levels[min(idx + 1, len(levels) - 1)]
            else:
                new_level = levels[0] if levels else "متوسط"
        promoted_students = 0
        cur_m = month_key(today())
        months_to_schedule = max(int(renew_months or 0), 1 if monthly_fee > 0 else 0)
        with self.repo.transaction():
            self.repo.update(Sheet.GROUPS, {"group_id": group_id}, {"level": new_level})
            existing_fees = {(f.enrollment_id, f.item, f.month) for f in self.repo.read(Sheet.FEE_SCHEDULE)}
            for e in self.repo.read(Sheet.ENROLLMENTS):
                if e.group_id == group_id and e.status == "active":
                    promoted_students += 1
                    if add_lessons and int(add_lessons) > 0:
                        self.repo.update(
                            Sheet.ENROLLMENTS,
                            {"enrollment_id": e.enrollment_id},
                            {"lessons_purchased": int(e.lessons_purchased or 0) + int(add_lessons)},
                        )
                    if months_to_schedule > 0 and monthly_fee > 0:
                        for i in range(months_to_schedule):
                            target_m = shift_month(cur_m, i)
                            while (e.enrollment_id, "monthly", target_m) in existing_fees:
                                target_m = shift_month(target_m, 1)
                            self.repo.append(
                                Sheet.FEE_SCHEDULE,
                                dict(enrollment_id=e.enrollment_id, item="monthly", month=target_m, amount_due=monthly_fee),
                            )
                            existing_fees.add((e.enrollment_id, "monthly", target_m))
        return dict(
            group_id=group_id,
            old_level=g.level,
            new_level=new_level,
            students_promoted=promoted_students,
            renewed_students=promoted_students,
        )

    # ---- Educational Programs Management (Admin) ----
    def list_programs(self) -> list[str]:
        saved = self.repo.get_setting("programs_ar")
        if saved is None or not isinstance(saved, list):
            saved = list(config.DEFAULT_PROGRAMS_AR)
        else:
            saved = [str(p).strip() for p in saved if str(p).strip()]
        config.PROGRAMS_AR[:] = list(saved)
        return list(saved)

    def add_program(self, name: str) -> list[str]:
        clean = (name or "").strip()
        if len(clean) < 2:
            raise ServiceError("اكتب اسم البرنامج التعليمي (حرفان على الأقل).")
        current = self.list_programs()
        norm_clean = normalize_ar(clean)
        if any(normalize_ar(p) == norm_clean for p in current):
            raise ServiceError(f"البرنامج التعليمي «{clean}» موجود بالفعل.")
        updated = current + [clean]
        self.repo.set_setting("programs_ar", updated)
        config.PROGRAMS_AR[:] = list(updated)
        return list(updated)

    def delete_program(self, name: str) -> list[str]:
        clean = (name or "").strip()
        current = self.list_programs()
        if clean not in current:
            raise ServiceError(f"البرنامج التعليمي «{clean}» غير موجود.")
        updated = [p for p in current if p != clean]
        self.repo.set_setting("programs_ar", updated)
        config.PROGRAMS_AR[:] = list(updated)
        return list(updated)

    def program_stats(self) -> list[dict[str, Any]]:
        led = self.svc.ledger()
        programs = self.list_programs()
        g_counts: dict[str, int] = {p: 0 for p in programs}
        s_counts: dict[str, int] = {p: 0 for p in programs}
        enr_by_group: dict[int, int] = {}
        for e in led.enrollments:
            if e.status in ("active", "paused"):
                enr_by_group[e.group_id] = enr_by_group.get(e.group_id, 0) + 1
        for g in led.groups.values():
            p = g.cost_center
            g_counts[p] = g_counts.get(p, 0) + 1
            s_counts[p] = s_counts.get(p, 0) + enr_by_group.get(g.group_id, 0)
        return [
            dict(name=p, groups=g_counts.get(p, 0), students=s_counts.get(p, 0))
            for p in programs
        ]

    def add(self, cost_center: str, track: str = "", level: str = "", instructor_id: Optional[int] = None,
            schedule: str = "", mode: str = "onsite", instructor_hourly_rate: Optional[float] = None) -> int:
        if not (cost_center or "").strip():
            raise ServiceError("اختر البرنامج.")
        if instructor_hourly_rate is not None and instructor_hourly_rate < 0:
            raise ServiceError("سعر ساعة المدرب لا يمكن أن يكون سالبًا.")
        if instructor_hourly_rate is None and instructor_id:
            ins = self.repo.get(Sheet.INSTRUCTORS, instructor_id=instructor_id)
            if ins and ins.hourly_rate:
                instructor_hourly_rate = ins.hourly_rate
        clean_cc = cost_center.strip()
        with self.repo.transaction():
            gid = self.repo.next_id(Sheet.GROUPS)
            self.repo.append(Sheet.GROUPS, dict(group_id=gid, cost_center=clean_cc, track=track,
                                                level=level, instructor_id=instructor_id,
                                                instructor_hourly_rate=instructor_hourly_rate,
                                                schedule=schedule, mode=mode))
        progs = self.list_programs()
        if clean_cc not in progs and self.repo.get_setting("programs_ar") is not None:
            # Keep custom program added via group creation in the managed list
            self.repo.set_setting("programs_ar", progs + [clean_cc])
            config.PROGRAMS_AR[:] = progs + [clean_cc]
        return gid

    def update(self, group_id: int, changes: dict[str, Any]) -> None:
        if "instructor_hourly_rate" in changes and changes["instructor_hourly_rate"] is not None:
            if float(changes["instructor_hourly_rate"]) < 0:
                raise ServiceError("سعر ساعة المدرب لا يمكن أن يكون سالبًا.")
        self.repo.update(Sheet.GROUPS, {"group_id": group_id}, changes)

    def label(self, g) -> str:
        parts = [g.cost_center, g.level or "", g.schedule or ""]
        return f"{g.group_id} — " + " | ".join(p for p in parts if p)


