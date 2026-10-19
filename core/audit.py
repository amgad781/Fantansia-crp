"""Audit trail (rule 5).

* Every ``append`` / ``update`` through the repository is logged automatically,
  inside the SAME transaction (one atomic write, one backup).
* ``AuditService.log`` is for non-data events: login, logout, PDF export, ...
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable, Optional

from core.excel_repo import ExcelRepository, Transaction
from core.schemas import AuditLogEntry, Sheet


class Action:
    CREATE = "create"
    UPDATE = "update"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    AUTO_LOGOUT = "auto_logout"
    EXPORT_PDF = "export_pdf"
    PASSWORD_CHANGED = "password_changed"
    SETUP = "setup"


_SENSITIVE = {"password_hash"}


def _dump(d: Optional[dict]) -> Optional[str]:
    if d is None:
        return None
    clean = {k: ("***" if k in _SENSITIVE else v) for k, v in d.items()
             if k not in ("created_at", "created_by")}
    return json.dumps(clean, default=str, ensure_ascii=False)


class AuditService:
    def __init__(self, repo: ExcelRepository, user_provider: Callable[[], str]):
        self.repo = repo
        self._user = user_provider
        repo.set_change_hook(self._on_change)

    # called by the repository inside the active transaction
    def _on_change(self, tx: Transaction, action: str, sheet: str, record_id: str,
                   before: Optional[dict], after: Optional[dict]) -> None:
        tx.append(Sheet.AUDIT_LOG, self._entry(action, sheet, record_id, before, after),
                  audit=False)

    def _entry(self, action: str, sheet: str = "", record_id: str = "",
               before: Optional[dict] = None, after: Optional[dict] = None,
               user: Optional[str] = None) -> AuditLogEntry:
        return AuditLogEntry(
            timestamp=datetime.now().replace(microsecond=0),
            user=user if user is not None else self._user(),
            action=action,
            sheet=sheet or None,
            record_id=str(record_id) if record_id else None,
            before=_dump(before),
            after=_dump(after),
        )

    def log(self, action: str, sheet: str = "", record_id: Any = "",
            before: Optional[dict] = None, after: Optional[dict] = None,
            user: Optional[str] = None) -> None:
        """Explicit event (joins the current transaction if one is open)."""
        self.repo.append(Sheet.AUDIT_LOG,
                         self._entry(action, sheet, str(record_id), before, after, user),
                         audit=False)

    def recent(self, limit: int = 200) -> list[AuditLogEntry]:
        rows = self.repo.read(Sheet.AUDIT_LOG)
        return sorted(rows, key=lambda r: r.timestamp, reverse=True)[:limit]
