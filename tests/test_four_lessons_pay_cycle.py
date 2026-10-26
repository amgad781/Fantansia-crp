"""Tests for the 4-lessons pay cycle option for instructors per group."""
from datetime import date, time, timedelta
import pytest
from core.audit import AuditService
from core.auth import Session
from core.excel_repo import ExcelRepository
from core.schemas import Sheet
from services.registry import Services

TODAY = date.today()


@pytest.fixture
def svc(tmp_path):
    session = Session()
    repo = ExcelRepository(tmp_path / "academy.db", tmp_path / "backups", current_user=lambda: "reception")
    repo.ensure_workbook()
    AuditService(repo, lambda: "reception")
    return Services(repo, lambda: "reception")


def test_group_pay_cycle_setting(svc):
    iid = svc.instructors.add("أحمد علي", "01012345678", 100)
    # Default is monthly
    gid1 = svc.groups.add("روبوتكس", "روبوتيكس", "مبتدئ", iid, "السبت 5 م", "onsite")
    g1 = svc.repo.get(Sheet.GROUPS, group_id=gid1)
    assert getattr(g1, "pay_cycle", "monthly") == "monthly"

    # Explicit every_4_lessons
    gid2 = svc.groups.add("برمجة بايثون", "برمجة", "متوسط", iid, "الأحد 6 م", "online",
                          pay_cycle="every_4_lessons")
    g2 = svc.repo.get(Sheet.GROUPS, group_id=gid2)
    assert g2.pay_cycle == "every_4_lessons"

    # Update through set_group_pay_cycle
    svc.instructors.set_group_pay_cycle(gid1, "every_4_lessons")
    g1_updated = svc.repo.get(Sheet.GROUPS, group_id=gid1)
    assert g1_updated.pay_cycle == "every_4_lessons"

    # groups_for_instructor inspection
    groups_info = svc.instructors.groups_for_instructor(iid)
    assert len(groups_info) == 2
    assert all(g["pay_cycle"] == "every_4_lessons" for g in groups_info)


def test_four_lessons_milestone_and_payment(svc):
    iid = svc.instructors.add("سارة محمود", "01234567890", 150)
    gid = svc.groups.add("روبوتكس متقدم", "روبوتيكس", "متقدم", iid, "الاثنين 4 م", "onsite",
                         instructor_hourly_rate=120, pay_cycle="every_4_lessons")

    # Before 4 lessons: no milestone
    for i in range(3):
        d = TODAY - timedelta(days=10 - i)
        svc.attendance.create_session(gid, d, time(16, 0), time(17, 30), iid, "روبوتكس", "held")

    milestones = svc.instructors.pending_4_lesson_milestones(iid)
    assert len(milestones) == 0

    # 4th lesson completes!
    s4_id = svc.attendance.create_session(gid, TODAY, time(16, 0), time(17, 30), iid, "روبوتكس", "held")
    milestones = svc.instructors.pending_4_lesson_milestones(iid)
    assert len(milestones) == 1

    m = milestones[0]
    assert m["group_id"] == gid
    assert m["instructor_id"] == iid
    assert m["batch_count"] == 4
    # Each session is 1.5 hours * 120 rate = 180 EGP; 4 sessions = 720 EGP
    assert m["total_hours"] == 6.0
    assert m["amount"] == 720.0
    assert len(m["session_ids"]) == 4

    # Pay the milestone
    pid = svc.instructors.record_payment(
        iid, m["period_from"], m["period_to"], m["amount"],
        method="cash", approved_by="owner",
        group_id=gid, session_ids=m["session_ids"],
    )
    assert pid > 0

    # Milestone should now be settled
    milestones_after = svc.instructors.pending_4_lesson_milestones(iid)
    assert len(milestones_after) == 0

    # Check sessions are marked with payment_id
    sessions = [s for s in svc.repo.read(Sheet.SESSIONS) if s.group_id == gid]
    assert all(s.payment_id == pid for s in sessions)

    # Reversal restores milestone
    svc.instructors.reverse_payment(pid)
    sessions_reversed = [s for s in svc.repo.read(Sheet.SESSIONS) if s.group_id == gid]
    assert all(s.payment_id is None for s in sessions_reversed)

    milestones_restored = svc.instructors.pending_4_lesson_milestones(iid)
    assert len(milestones_restored) == 1


def test_monthly_group_does_not_trigger_milestone(svc):
    iid = svc.instructors.add("محمود كمال", "01111111111", 100)
    gid = svc.groups.add("تأسيس برمجة", "برمجة", "مبتدئ", iid, "الجمعة 2 م", "onsite",
                         pay_cycle="monthly")

    for i in range(5):
        d = TODAY - timedelta(days=15 - i)
        svc.attendance.create_session(gid, d, time(14, 0), time(15, 30), iid, "برمجة", "held")

    milestones = svc.instructors.pending_4_lesson_milestones(iid)
    assert len(milestones) == 0
