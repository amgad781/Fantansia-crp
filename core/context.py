"""Wires the core objects together once at startup."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import config
from core.audit import AuditService
from core.auth import AuthService, Session
from core.excel_repo import ExcelRepository


@dataclass
class AppContext:
    repo: ExcelRepository
    audit: AuditService
    session: Session
    auth: AuthService
    nav: dict = field(default_factory=dict)   # one-shot hand-over between pages (e.g. chosen student)
    svc: Any = None                      # services.registry.Services (set in build_context)


def build_context() -> AppContext:
    session = Session()
    repo = ExcelRepository(config.DB_PATH, config.BACKUP_DIR,
                           current_user=lambda: session.username)
    repo.ensure_workbook()
    audit = AuditService(repo, lambda: session.username)
    from services.registry import Services      # local import: services -> core, never the reverse
    return AppContext(repo, audit, session, AuthService(repo, audit, session),
                      svc=Services(repo, lambda: session.username))
