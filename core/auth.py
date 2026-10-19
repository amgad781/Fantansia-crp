"""Authentication, roles, granular permissions, and the in-process session."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Optional

import bcrypt

import config
from core.audit import Action, AuditService
from core.excel_repo import ExcelRepository
from core.schemas import Role, Sheet, User

# ----------------------------------------------------------------------------
# Permissions (section 1). Feature key -> default roles allowed.
# ----------------------------------------------------------------------------
_ALL_ROLES = {Role.RECEPTIONIST, Role.ACCOUNTANT, Role.OWNER}
_FINANCE = {Role.ACCOUNTANT, Role.OWNER}
_OWNER = {Role.OWNER}

PERMISSIONS: dict[str, set[Role]] = {
    "students": {Role.RECEPTIONIST, Role.OWNER},
    "receipts": _ALL_ROLES,
    "settlements": _ALL_ROLES,
    "attendance": {Role.RECEPTIONIST, Role.OWNER},
    "collection": _ALL_ROLES,
    "journal": _ALL_ROLES,
    "groups": {Role.RECEPTIONIST, Role.OWNER},
    "dashboard": _FINANCE,
    "instructors": _FINANCE,
    "instructor_statement": _FINANCE,
    "employees": _FINANCE,
    "reports": _FINANCE,
    "users": _OWNER,
    "audit": _OWNER,
}

ALL_FEATURES: list[str] = list(config.FEATURE_LABELS_AR.keys())


def default_features_for_role(role: Role | str = Role.RECEPTIONIST) -> set[str]:
    r = Role(role)
    if r == Role.OWNER:
        return set(PERMISSIONS.keys())
    return {feat for feat, roles in PERMISSIONS.items() if r in roles}


def parse_permissions(perms_str: Optional[str], role: Role | str = Role.CUSTOM) -> frozenset[str]:
    r = Role(role)
    if r == Role.OWNER:
        return frozenset(PERMISSIONS.keys())
    if perms_str is not None and perms_str.strip():
        items = {p.strip() for p in perms_str.split(",") if p.strip()}
        if "instructors" in items:
            items.add("instructor_statement")
        if "users" in items:
            items.add("audit")
        return frozenset(items)
    return frozenset(default_features_for_role(r))


def format_permissions(features: Optional[Iterable[str]]) -> Optional[str]:
    if not features:
        return None
    cleaned = sorted({f.strip() for f in features if f and f.strip()})
    return ",".join(cleaned) if cleaned else None


class AuthError(Exception):
    """Message is Arabic and safe to show to the user."""


# ----------------------------------------------------------------------------
# Password hashing
# ----------------------------------------------------------------------------
_BCRYPT_MAX_BYTES = 72
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=12))   # equalises timing for unknown users


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(password) < config.MIN_PASSWORD_LEN:
        raise AuthError(f"كلمة المرور يجب ألا تقل عن {config.MIN_PASSWORD_LEN} أحرف.")
    if len(raw) > _BCRYPT_MAX_BYTES:
        raise AuthError("كلمة المرور طويلة جدًا.")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:                                                # too long / malformed
        return False


# ----------------------------------------------------------------------------
# Session
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: Role
    permissions: frozenset[str] = frozenset()


class Session:
    """Process-wide session. Safe because exactly one person uses the PC at a time."""

    def __init__(self) -> None:
        self.user: Optional[CurrentUser] = None
        self._last_activity = time.monotonic()

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def username(self) -> str:
        return self.user.username if self.user else "system"

    @property
    def role(self) -> Optional[Role]:
        return self.user.role if self.user else None

    def can(self, feature: str) -> bool:
        if not self.user:
            return False
        if self.user.role == Role.OWNER:
            return True
        if self.user.permissions:
            return feature in self.user.permissions
        return self.user.role in PERMISSIONS.get(feature, set())

    def login(self, user: CurrentUser) -> None:
        self.user = user
        self.touch()

    def logout(self) -> None:
        self.user = None

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity


# ----------------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------------
class AuthService:
    default_features_for_role = staticmethod(default_features_for_role)
    parse_permissions = staticmethod(parse_permissions)

    def __init__(self, repo: ExcelRepository, audit: AuditService, session: Session):
        self.repo, self.audit, self.session = repo, audit, session
        self._failures: dict[str, list[float]] = {}

    # ---- users ----
    def has_users(self) -> bool:
        return bool(self.repo.rows(Sheet.USERS))

    def list_users(self) -> list[User]:
        return self.repo.read(Sheet.USERS)

    def create_user(self, username: str, password: str, role: Role,
                    permissions: Optional[Iterable[str]] = None) -> User:
        username = username.strip().lower()
        if len(username) < 3:
            raise AuthError("اسم المستخدم يجب ألا يقل عن 3 أحرف.")
        perms_str = format_permissions(permissions)
        user = User(username=username, password_hash=hash_password(password),
                    role=role, permissions=perms_str, status="active")
        return self.repo.append(Sheet.USERS, user)              # audit hook masks the hash

    def update_user_access(self, username: str, role: Role,
                           permissions: Optional[Iterable[str]] = None,
                           status: str = "active") -> User:
        username = username.strip().lower()
        user = self.repo.get(Sheet.USERS, username=username)
        if not user:
            raise AuthError("المستخدم غير موجود.")
        if status != "active" or role != Role.OWNER:
            owners = [u for u in self.list_users()
                      if u.role == Role.OWNER.value and u.status == "active" and u.username != username]
            if not owners and user.role == Role.OWNER.value:
                raise AuthError("لا يمكن إلغاء صلاحية المالك الوحيد في النظام.")
        perms_str = format_permissions(permissions)
        updated = self.repo.update(Sheet.USERS, {"username": username},
                                   {"role": role.value if isinstance(role, Role) else role,
                                    "permissions": perms_str,
                                    "status": status})
        if self.session.user and self.session.username == username:
            r = Role(updated.role)
            self.session.login(CurrentUser(username, r, parse_permissions(updated.permissions, r)))
        return updated

    def first_run_setup(self, owner: tuple[str, str], receptionist: tuple[str, str]) -> None:
        """Create both accounts in ONE write (only allowed while Users is empty)."""
        if self.has_users():
            raise AuthError("تم إعداد النظام من قبل.")
        if owner[0].strip().lower() == receptionist[0].strip().lower():
            raise AuthError("اسم المستخدم يجب أن يختلف بين الحسابين.")
        with self.repo.transaction():
            self.create_user(owner[0], owner[1], Role.OWNER)
            self.create_user(receptionist[0], receptionist[1], Role.RECEPTIONIST)
            self.audit.log(Action.SETUP, Sheet.USERS.value, "", user=owner[0].strip().lower())

    def change_password(self, username: str, old: str, new: str) -> None:
        username_clean = username.strip().lower()
        if not username_clean or not old or not new:
            raise AuthError("أدخل كلمة المرور الحالية وكلمة المرور الجديدة.")
        user = self.repo.get(Sheet.USERS, username=username_clean)
        if not user or not verify_password(old, user.password_hash):
            raise AuthError("كلمة المرور الحالية غير صحيحة.")
        if getattr(user, "status", "active") != "active":
            raise AuthError("هذا الحساب موقوف. راجع مدير الأكاديمية.")
        if old == new:
            raise AuthError("كلمة المرور الجديدة يجب أن تختلف عن كلمة المرور الحالية.")
        with self.repo.transaction():
            self.repo.update(Sheet.USERS, {"username": user.username},
                             {"password_hash": hash_password(new)})
            self.audit.log(Action.PASSWORD_CHANGED, Sheet.USERS.value, user.username, user=user.username)
        self._failures.pop(user.username, None)

    def reset_password(self, username: str, new: str) -> None:
        """Owner resets another user's password (the UI only offers this to the owner)."""
        user = self.repo.get(Sheet.USERS, username=username.strip().lower())
        if not user:
            raise AuthError("المستخدم غير موجود.")
        with self.repo.transaction():
            self.repo.update(Sheet.USERS, {"username": user.username}, {"password_hash": hash_password(new)})
            self.audit.log(Action.PASSWORD_CHANGED, Sheet.USERS.value, user.username)
        self._failures.pop(user.username, None)

    # ---- login / logout ----
    def _check_lock(self, username: str) -> None:
        now = time.monotonic()
        recent = [t for t in self._failures.get(username, []) if now - t < config.LOGIN_LOCK_SECONDS]
        self._failures[username] = recent
        if len(recent) >= config.MAX_LOGIN_ATTEMPTS:
            wait = int(config.LOGIN_LOCK_SECONDS - (now - recent[0])) + 1
            raise AuthError(f"محاولات كثيرة خاطئة. حاول بعد {wait} ثانية.")

    def login(self, username: str, password: str) -> CurrentUser:
        username = username.strip().lower()
        if not username or not password:
            raise AuthError("أدخل اسم المستخدم وكلمة المرور.")
        self._check_lock(username)

        user = self.repo.get(Sheet.USERS, username=username)
        ok = verify_password(password, user.password_hash if user else _DUMMY_HASH.decode())
        if not user or not ok:
            self._failures.setdefault(username, []).append(time.monotonic())
            self.audit.log(Action.LOGIN_FAILED, Sheet.USERS.value, username, user=username)
            raise AuthError("اسم المستخدم أو كلمة المرور غير صحيحة.")
        if getattr(user, "status", "active") != "active":
            raise AuthError("هذا الحساب موقوف. راجع مدير الأكاديمية.")

        self._failures.pop(username, None)
        self.audit.log(Action.LOGIN, Sheet.USERS.value, username, user=username)
        r = Role(user.role)
        current = CurrentUser(user.username, r, parse_permissions(getattr(user, "permissions", None), r))
        self.session.login(current)                       # only after the audit write succeeded
        return current

    def logout(self, reason: str = Action.LOGOUT) -> None:
        try:
            if self.session.is_authenticated:
                self.audit.log(reason, Sheet.USERS.value, self.session.username)
        finally:
            self.session.logout()                         # never stay logged in
