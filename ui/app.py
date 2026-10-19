"""Registers every page. Used by main.py and by the UI tests (single source of truth)."""
from __future__ import annotations

from core.context import AppContext
from ui import groups_page, receipts_page, students_page
from ui.layout import register_pages, setup_global_head
from ui.login_page import register_login


def bodies() -> dict:
    """nav key -> page body. Pages not listed here show the 'under construction' placeholder."""
    from ui import (attendance_page, collection_page, dashboard, employees_page, instructors_page,
                    journal_page, reports_page, settlements_page, users_page)
    return {
        "dashboard": dashboard.body,
        "students": students_page.body_list,
        "new_student": students_page.body_new,
        "receipts": receipts_page.body,
        "settlements": settlements_page.body,
        "attendance": attendance_page.body,
        "collection": collection_page.body,
        "groups": groups_page.body,
        "instructors": instructors_page.body,
        "employees": employees_page.body,
        "journal": journal_page.body,
        "reports": reports_page.body,
        "users": users_page.body,
    }


def register_all(ctx: AppContext, with_head: bool = True) -> None:
    if with_head:
        setup_global_head()
    register_login(ctx)
    register_pages(ctx, bodies())
    students_page.register_routes(ctx)          # AFTER register_pages: /students/new must win over /students/{sid}
