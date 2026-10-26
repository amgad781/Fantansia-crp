"""Storage Repository – SQLite primary engine + full Excel (.xlsx) compatibility & snapshot export.

Architecture
------------
* When ``path.suffix == '.db'`` (the default in production: ``data/academy.db``):
  - Uses Python's built-in ``sqlite3`` in WAL mode with ACID transactions.
  - Automatically creates all 17 tables and adds any new columns non-destructively.
  - On first creation of ``academy.db``, if ``academy.xlsx`` exists beside it, automatically
    migrates all existing rows into SQLite AND keeps ``academy.xlsx`` updated so the owner
    can always inspect or export Excel workbooks.
  - Uses SQLite's online backup API + keeps ``academy.xlsx`` synced.
* When ``path.suffix == '.xlsx'`` (or when exporting to Excel):
  - Maintains 100% compatibility with the atomic Excel protocol (temp file, fsync,
    re-open verification, ``os.replace``, lock check, and dated backups).
* Intentionally NO delete method (rule 3: reversal entries only).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time as _time
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import ValidationError

import config
from core.schemas import (DERIVED_FIELDS, KEY_FIELDS, SHEET_MODELS, Row, Sheet,
                          record_key, sheet_columns)

log = logging.getLogger(__name__)

# (tx, action, sheet, record_id, before, after)
ChangeHook = Callable[["Transaction", str, str, str, Optional[dict], Optional[dict]], None]


# ============================================================================
# Errors (all carry an Arabic message that the UI can show as-is)
# ============================================================================
class RepoError(Exception):
    def __init__(self, message_ar: str):
        super().__init__(message_ar)
        self.message_ar = message_ar

    def __str__(self) -> str:
        return self.message_ar


class ExcelFileLockedError(RepoError):
    def __init__(self) -> None:
        super().__init__("ملف البيانات (academy.xlsx) مفتوح في برنامج Excel.\n"
                         "من فضلك أغلق الملف ثم حاول مرة أخرى.")


class ExcelCorruptError(RepoError):
    def __init__(self, detail: str = "") -> None:
        super().__init__("تعذّرت قراءة ملف البيانات، وقد يكون تالفًا.\n"
                         "يمكنك استرجاع آخر نسخة احتياطية من مجلد data/backups.\n" + detail)


class DataValidationError(RepoError):
    pass


class DuplicateKeyError(RepoError):
    pass


class RecordNotFoundError(RepoError):
    pass


# ============================================================================
# Helpers
# ============================================================================
def _sheet_name(sheet: Sheet | str) -> str:
    return Sheet(sheet).value


def _to_cell(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, float) and v != v:
        return None
    return v


def _to_sql_val(v: Any) -> Any:
    v = _to_cell(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    return v


def _cmp(v: Any) -> str:
    """Normalise a key value (raw cell or python value) for equality checks."""
    if isinstance(v, Enum):
        v = v.value
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return "" if v is None else str(v).strip()


def _raw_key(sh: Sheet, raw: dict) -> str:
    return "|".join(_cmp(raw.get(f)) for f in KEY_FIELDS[sh])


_NUMBER_FORMATS = {datetime: "yyyy-mm-dd hh:mm:ss", date: "yyyy-mm-dd", time: "hh:mm"}


def _jsonable(d: Optional[dict]) -> Optional[dict]:
    if d is None:
        return None
    return json.loads(json.dumps(d, default=str, ensure_ascii=False))


def _style_header(ws, headers: list[str]) -> None:
    fill = PatternFill("solid", start_color="C62828")
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = max(14, len(h) + 4)
    ws.freeze_panes = "A2"
    ws.sheet_view.rightToLeft = True


def _read_rows(ws) -> tuple[list[str], list[tuple[int, dict[str, Any]]]]:
    """Return (headers, [(excel_row_number, {header: value})...]) skipping empty rows."""
    it = ws.iter_rows(values_only=True)
    try:
        header_row = next(it)
    except StopIteration:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in header_row]
    out: list[tuple[int, dict[str, Any]]] = []
    for n, values in enumerate(it, start=2):
        if values is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            continue
        out.append((n, {h: v for h, v in zip(headers, values) if h}))
    return headers, out


def _sql_col_type(col: str) -> str:
    if col in ("student_id", "group_id", "enrollment_id", "serial", "session_id",
               "instructor_id", "employee_id", "id", "lessons_purchased",
               "siblings_count", "sibling_rank", "reversal_of", "receipt_no", "payment_id"):
        return "INTEGER"
    if col in ("amount_due", "amount", "hours", "rate_applied", "hourly_rate",
               "instructor_hourly_rate", "total_hours", "gross", "previous_paid",
               "net", "base_salary", "bonuses", "deductions"):
        return "REAL"
    return "TEXT"


# ============================================================================
# Transaction – one atomic write, may contain many operations
# ============================================================================
class Transaction:
    def __init__(self, repo: "ExcelRepository", wb: Optional[Workbook] = None,
                 conn: Optional[sqlite3.Connection] = None):
        self._repo = repo
        self.wb = wb
        self.conn = conn
        self.dirty = False

    # ---- reads inside the transaction (see uncommitted changes) -------------
    def rows(self, sheet: Sheet | str) -> list[dict[str, Any]]:
        sh = Sheet(sheet)
        if self.conn is not None:
            cols = sheet_columns(sh)
            col_list = ", ".join(f'"{c}"' for c in cols)
            cur = self.conn.execute(f'SELECT {col_list} FROM "{sh.value}" ORDER BY rowid')
            return [{c: val for c, val in zip(cols, row) if val is not None} for row in cur.fetchall()]
        ws = self.wb[sh.value]
        return [r for _, r in _read_rows(ws)[1]]

    def next_id(self, sheet: Sheet | str, start: int = 1) -> int:
        key = KEY_FIELDS[Sheet(sheet)][0]
        ids = [int(r[key]) for r in self.rows(sheet)
               if isinstance(r.get(key), (int, float)) or (isinstance(r.get(key), str) and str(r.get(key)).isdigit())]
        return max(max(ids, default=start - 1) + 1, start)

    # ---- writes ---------------------------------------------------------------
    def append(self, sheet: Sheet | str, record: Row | dict, *, audit: bool = True,
               user: str = "") -> Row:
        sh = Sheet(sheet)
        model = SHEET_MODELS[sh]
        data = record.model_dump() if isinstance(record, Row) else dict(record)
        if not data.get("created_at"):
            data["created_at"] = datetime.now().replace(microsecond=0)
        if not data.get("created_by"):
            data["created_by"] = user or self._repo.current_user()
        row = self._validate(model, data, sh)

        if KEY_FIELDS[sh]:
            new_key = _raw_key(sh, row.model_dump())
            if any(_raw_key(sh, r) == new_key for r in self.rows(sh)):
                raise DuplicateKeyError(f"السجل موجود بالفعل ({new_key}) في «{sh.value}».")

        values = row.model_dump()
        if self.conn is not None:
            cols = sheet_columns(sh)
            placeholders = ", ".join("?" for _ in cols)
            col_names = ", ".join(f'"{c}"' for c in cols)
            sql_vals = [_to_sql_val(values.get(c)) for c in cols]
            self.conn.execute(f'INSERT INTO "{sh.value}" ({col_names}) VALUES ({placeholders})', sql_vals)
        else:
            ws = self.wb[sh.value]
            headers = [c.value for c in ws[1]]
            ws.append([_to_cell(values.get(h)) for h in headers])
            self._format_last_row(ws, [values.get(h) for h in headers])
        self.dirty = True

        if audit and sh is not Sheet.AUDIT_LOG:
            self._repo._fire_hook(self, "create", sh.value, record_key(sh, values), None, values)
        return row

    def update(self, sheet: Sheet | str, where: dict[str, Any], changes: dict[str, Any],
               *, audit: bool = True) -> Row:
        sh = Sheet(sheet)
        model = SHEET_MODELS[sh]
        if self.conn is not None:
            cols = sheet_columns(sh)
            col_list = ", ".join(f'"{c}"' for c in cols)
            cur = self.conn.execute(f'SELECT rowid, {col_list} FROM "{sh.value}" ORDER BY rowid')
            all_rows = [(r[0], {c: v for c, v in zip(cols, r[1:]) if v is not None}) for r in cur.fetchall()]
            matches = [(rid, r) for rid, r in all_rows
                       if all(_cmp(r.get(k)) == _cmp(v) for k, v in where.items())]
            if not matches:
                raise RecordNotFoundError(f"لم يتم العثور على السجل في «{sh.value}».")
            if len(matches) > 1:
                raise RecordNotFoundError(f"أكثر من سجل مطابق في «{sh.value}» — حدّد المفتاح بدقة.")
            rowid, raw = matches[0]
            before = self._validate(model, raw, sh).model_dump()
            drop = [f for f in DERIVED_FIELDS.get(sh, ()) if f not in changes]
            if sh is Sheet.SESSIONS and {"start_time", "end_time"} & changes.keys() and "hours" not in changes:
                drop.append("hours")
            merged = {k: v for k, v in {**raw, **changes}.items() if k not in drop}
            after_row = self._validate(model, merged, sh)
            after = after_row.model_dump()
            set_clause = ", ".join(f'"{c}" = ?' for c in cols)
            sql_vals = [_to_sql_val(after.get(c)) for c in cols] + [rowid]
            self.conn.execute(f'UPDATE "{sh.value}" SET {set_clause} WHERE rowid = ?', sql_vals)
            self.dirty = True
            if audit and sh is not Sheet.AUDIT_LOG:
                self._repo._fire_hook(self, "update", sh.value, record_key(sh, after), before, after)
            return after_row

        ws = self.wb[sh.value]
        headers, rows = _read_rows(ws)
        matches = [(n, r) for n, r in rows
                   if all(_cmp(r.get(k)) == _cmp(v) for k, v in where.items())]
        if not matches:
            raise RecordNotFoundError(f"لم يتم العثور على السجل في «{sh.value}».")
        if len(matches) > 1:
            raise RecordNotFoundError(f"أكثر من سجل مطابق في «{sh.value}» — حدّد المفتاح بدقة.")
        n, raw = matches[0]
        before = self._validate(model, raw, sh).model_dump()
        drop = [f for f in DERIVED_FIELDS.get(sh, ()) if f not in changes]
        if sh is Sheet.SESSIONS and {"start_time", "end_time"} & changes.keys() \
                and "hours" not in changes:
            drop.append("hours")                              # recompute from the new times
        merged = {k: v for k, v in {**raw, **changes}.items() if k not in drop}
        after_row = self._validate(model, merged, sh)
        after = after_row.model_dump()

        for col, h in enumerate(headers, start=1):
            if h in after and after[h] != before.get(h):
                cell = ws.cell(row=n, column=col, value=_to_cell(after[h]))
                fmt = _NUMBER_FORMATS.get(type(after[h]))
                if fmt:
                    cell.number_format = fmt
        self.dirty = True
        if audit and sh is not Sheet.AUDIT_LOG:
            self._repo._fire_hook(self, "update", sh.value, record_key(sh, after),
                                  before, after)
        return after_row

    # ---- internals ------------------------------------------------------------
    @staticmethod
    def _validate(model: type[Row], data: dict, sh: Sheet) -> Row:
        try:
            return model.model_validate(data)
        except ValidationError as e:
            fields = "، ".join(str(err["loc"][0]) for err in e.errors() if err["loc"])
            raise DataValidationError(f"بيانات غير صحيحة في «{sh.value}»: {fields}") from e

    @staticmethod
    def _format_last_row(ws, values: list[Any]) -> None:
        r = ws.max_row
        for col, v in enumerate(values, start=1):
            fmt = _NUMBER_FORMATS.get(type(v))
            if fmt:
                ws.cell(row=r, column=col).number_format = fmt


# ============================================================================
# Repository (Supports both SQLite .db and Excel .xlsx transparently)
# ============================================================================
class ExcelRepository:
    def __init__(self, path: Path = config.DB_PATH,
                 backup_dir: Path = config.BACKUP_DIR,
                 current_user: Callable[[], str] = lambda: "system"):
        self.path = Path(path)
        self.backup_dir = Path(backup_dir)
        self.current_user = current_user
        self._is_sqlite = self.path.suffix.lower() in (".db", ".sqlite", ".sqlite3")
        self._lock = threading.RLock()
        self._tx: Optional[Transaction] = None
        self._hook: Optional[ChangeHook] = None
        self._cache: Optional[dict[str, list[dict[str, Any]]]] = None
        self._cache_stamp: Optional[tuple[int, int]] = None

    @property
    def is_sqlite(self) -> bool:
        return self._is_sqlite

    # ------------------------------------------------------------------ setup
    def set_change_hook(self, hook: ChangeHook) -> None:
        self._hook = hook

    def _fire_hook(self, tx: Transaction, action: str, sheet: str, rid: str,
                   before: Optional[dict], after: Optional[dict]) -> None:
        if self._hook:
            self._hook(tx, action, sheet, rid, before, after)

    def _connect_sqlite(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.path, timeout=10.0)
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            return conn
        except sqlite3.DatabaseError as e:
            raise ExcelCorruptError(str(e)) from e

    def ensure_workbook(self) -> None:
        """Initialize or migrate the SQLite database (or Excel workbook)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        if self._is_sqlite:
            self._ensure_sqlite()
            return

        if not self.path.exists():
            wb = Workbook()
            wb.remove(wb.active)
            for sh in Sheet:
                ws = wb.create_sheet(sh.value)
                _style_header(ws, sheet_columns(sh))
            self._atomic_save(wb)
            log.info("Created new workbook at %s", self.path)
            return

        with self.transaction() as tx:                       # migrate existing file
            for sh in Sheet:
                cols = sheet_columns(sh)
                if sh.value not in tx.wb.sheetnames:
                    ws = tx.wb.create_sheet(sh.value)
                    _style_header(ws, cols)
                    tx.dirty = True
                    continue
                ws = tx.wb[sh.value]
                existing = [c.value for c in ws[1] if c.value]
                missing = [c for c in cols if c not in existing]
                if missing:
                    base = len(existing)
                    for i, h in enumerate(missing, start=1):
                        ws.cell(row=1, column=base + i, value=h)
                    _style_header(ws, existing + missing)
                    tx.dirty = True

    def _ensure_sqlite(self) -> None:
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        conn = self._connect_sqlite()
        try:
            with conn:
                for sh in Sheet:
                    cols = sheet_columns(sh)
                    keys = KEY_FIELDS[sh]
                    col_defs = [f'"{c}" {_sql_col_type(c)}' for c in cols]
                    if keys:
                        pk = ", ".join(f'"{k}"' for k in keys)
                        col_defs.append(f"PRIMARY KEY ({pk})")
                    conn.execute(f'CREATE TABLE IF NOT EXISTS "{sh.value}" ({", ".join(col_defs)})')

                    # Migrate missing columns if any were added to schemas.py
                    existing = {r[1] for r in conn.execute(f'PRAGMA table_info("{sh.value}")').fetchall()}
                    for c in cols:
                        if c not in existing:
                            conn.execute(f'ALTER TABLE "{sh.value}" ADD COLUMN "{c}" {_sql_col_type(c)}')

                # Helpful indexes for fast filtering
                conn.execute('CREATE INDEX IF NOT EXISTS idx_enr_student ON "Enrollments"("student_id")')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_enr_group ON "Enrollments"("group_id")')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_rec_student ON "Receipts"("student_id")')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_rec_date ON "Receipts"("date")')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_sess_group_date ON "Sessions"("group_id", "date")')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_att_student ON "Attendance"("student_id")')
                conn.execute('CREATE TABLE IF NOT EXISTS "_Settings" ("key" TEXT PRIMARY KEY, "value" TEXT)')

            # One-time automatic migration from existing academy.xlsx if academy.db was just created
            xlsx_candidate = self.path.with_suffix(".xlsx")
            if is_new and xlsx_candidate.exists():
                self._import_from_xlsx(xlsx_candidate, conn)
        finally:
            conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if not hasattr(self, "_settings_mem"):
                self._settings_mem = {}
            if not self._is_sqlite or not self.path.exists():
                return self._settings_mem.get(key, default)
            conn = self._connect_sqlite()
            try:
                conn.execute('CREATE TABLE IF NOT EXISTS "_Settings" ("key" TEXT PRIMARY KEY, "value" TEXT)')
                row = conn.execute('SELECT "value" FROM "_Settings" WHERE "key" = ?', (key,)).fetchone()
                if row and row[0] is not None:
                    val = json.loads(row[0])
                    self._settings_mem[key] = val
                    return val
                return self._settings_mem.get(key, default)
            finally:
                conn.close()

    def set_setting(self, key: str, value: Any) -> None:
        with self._lock:
            if not hasattr(self, "_settings_mem"):
                self._settings_mem = {}
            self._settings_mem[key] = value
            if self._is_sqlite and self.path.exists():
                conn = self._connect_sqlite()
                try:
                    with conn:
                        conn.execute('CREATE TABLE IF NOT EXISTS "_Settings" ("key" TEXT PRIMARY KEY, "value" TEXT)')
                        conn.execute(
                            'INSERT OR REPLACE INTO "_Settings" ("key", "value") VALUES (?, ?)',
                            (key, json.dumps(value, ensure_ascii=False)),
                        )
                finally:
                    conn.close()


    def _import_from_xlsx(self, xlsx_path: Path, conn: sqlite3.Connection) -> None:
        try:
            wb = load_workbook(xlsx_path, read_only=True, data_only=True)
        except Exception as e:
            log.warning("Could not import existing Excel workbook %s: %s", xlsx_path, e)
            return
        try:
            with conn:
                for sh in Sheet:
                    if sh.value not in wb.sheetnames:
                        continue
                    _, rows = _read_rows(wb[sh.value])
                    if not rows:
                        continue
                    model = SHEET_MODELS[sh]
                    cols = sheet_columns(sh)
                    col_names = ", ".join(f'"{c}"' for c in cols)
                    placeholders = ", ".join("?" for _ in cols)
                    for _, raw in rows:
                        try:
                            validated = model.model_validate(raw).model_dump()
                            sql_vals = [_to_sql_val(validated.get(c)) for c in cols]
                            conn.execute(
                                f'INSERT OR IGNORE INTO "{sh.value}" ({col_names}) VALUES ({placeholders})',
                                sql_vals,
                            )
                        except Exception as row_err:
                            log.warning("Skipped invalid row during Excel import in %s: %s", sh.value, row_err)
            log.info("Migrated existing data from %s into SQLite %s", xlsx_path, self.path)
        finally:
            wb.close()

    def export_excel_snapshot(self, target_path: Optional[Path] = None) -> Path:
        """Export all 17 tables from the repository into a styled RTL Excel workbook."""
        out_path = Path(target_path or config.WORKBOOK_PATH)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        wb.remove(wb.active)
        for sh in Sheet:
            cols = sheet_columns(sh)
            ws = wb.create_sheet(sh.value)
            _style_header(ws, cols)
            for row_obj in self.read(sh):
                values = row_obj.model_dump()
                ws.append([_to_cell(values.get(h)) for h in cols])
                Transaction._format_last_row(ws, [values.get(h) for h in cols])
        tmp = out_path.with_name(f"{out_path.stem}.tmp.xlsx")
        wb.save(tmp)
        wb.close()
        os.replace(tmp, out_path)
        return out_path

    # ------------------------------------------------------------------ reads
    def _stamp(self) -> tuple[int, int]:
        st = self.path.stat()
        if self._is_sqlite:
            wal = self.path.with_name(self.path.name + "-wal")
            if wal.exists():
                wst = wal.stat()
                return st.st_mtime_ns ^ wst.st_mtime_ns, st.st_size + wst.st_size
        return st.st_mtime_ns, st.st_size

    def _load_all(self) -> dict[str, list[dict[str, Any]]]:
        try:
            stamp = self._stamp()
        except FileNotFoundError:
            raise ExcelCorruptError("الملف غير موجود.")
        if self._cache is not None and stamp == self._cache_stamp:
            return self._cache

        if self._is_sqlite:
            try:
                with open(self.path, "rb") as f:
                    header = f.read(16)
                if header and not header.startswith(b"SQLite format 3"):
                    raise ExcelCorruptError("ملف قاعدة البيانات غير صالح.")
            except OSError as e:
                raise ExcelCorruptError(str(e)) from e
            conn = self._connect_sqlite()
            try:
                data: dict[str, list[dict[str, Any]]] = {}
                for sh in Sheet:
                    cols = sheet_columns(sh)
                    col_list = ", ".join(f'"{c}"' for c in cols)
                    cur = conn.execute(f'SELECT {col_list} FROM "{sh.value}" ORDER BY rowid')
                    data[sh.value] = [{c: val for c, val in zip(cols, r) if val is not None}
                                      for r in cur.fetchall()]
            except sqlite3.DatabaseError as e:
                raise ExcelCorruptError(str(e)) from e
            finally:
                conn.close()
            self._cache, self._cache_stamp = data, stamp
            return data

        try:
            wb = load_workbook(self.path, read_only=True, data_only=True)
        except PermissionError:
            raise ExcelFileLockedError()
        except Exception as e:                                # zip/xml errors
            raise ExcelCorruptError(str(e)) from e
        try:
            data = {name: [r for _, r in _read_rows(wb[name])[1]]
                    for name in wb.sheetnames if name in {s.value for s in Sheet}}
        finally:
            wb.close()
        self._cache, self._cache_stamp = data, stamp
        return data

    def rows(self, sheet: Sheet | str) -> list[dict[str, Any]]:
        """Raw rows (dicts). Inside a transaction, includes uncommitted changes."""
        with self._lock:
            if self._tx is not None:
                return self._tx.rows(sheet)
            return list(self._load_all().get(_sheet_name(sheet), []))

    def read(self, sheet: Sheet | str) -> list[Row]:
        sh = Sheet(sheet)
        model = SHEET_MODELS[sh]
        out: list[Row] = []
        for i, raw in enumerate(self.rows(sh), start=2):
            try:
                out.append(model.model_validate(raw))
            except ValidationError as e:
                fields = "، ".join(str(err["loc"][0]) for err in e.errors() if err["loc"])
                raise DataValidationError(
                    f"بيانات غير صحيحة في «{sh.value}» (سطر تقريبي {i}): {fields}") from e
        return out

    def dataframe(self, sheet: Sheet | str) -> pd.DataFrame:
        sh = Sheet(sheet)
        return pd.DataFrame([r.model_dump() for r in self.read(sh)], columns=sheet_columns(sh))

    def find(self, sheet: Sheet | str, **eq: Any) -> list[Row]:
        return [r for r in self.read(sheet)
                if all(getattr(r, k, None) == _to_cell(v) for k, v in eq.items())]

    def get(self, sheet: Sheet | str, **eq: Any) -> Optional[Row]:
        res = self.find(sheet, **eq)
        return res[0] if res else None

    def next_id(self, sheet: Sheet | str, start: int = 1) -> int:
        key = KEY_FIELDS[Sheet(sheet)][0]
        ids = [int(r[key]) for r in self.rows(sheet)
               if isinstance(r.get(key), (int, float)) or (isinstance(r.get(key), str) and str(r.get(key)).isdigit())]
        return max(max(ids, default=start - 1) + 1, start)

    # ----------------------------------------------------------------- writes
    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """Group several operations into ONE backup + ONE atomic write."""
        with self._lock:
            if self._tx is not None:                          # nested -> join outer
                yield self._tx
                return
            self._assert_writable()

            if self._is_sqlite:
                conn = self._connect_sqlite()
                tx = Transaction(self, conn=conn)
                self._tx = tx
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    yield tx
                    if tx.dirty:
                        self.backup()
                        conn.commit()
                        self._cache = None
                    else:
                        conn.rollback()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    self._tx = None
                    conn.close()
                return

            try:
                wb = load_workbook(self.path)
            except PermissionError:
                raise ExcelFileLockedError()
            except Exception as e:
                raise ExcelCorruptError(str(e)) from e
            tx = Transaction(self, wb=wb)
            self._tx = tx
            try:
                yield tx
                if tx.dirty:
                    self._commit(tx)
            finally:
                self._tx = None
                wb.close()

    def append(self, sheet: Sheet | str, record: Row | dict, **kw: Any) -> Row:
        with self.transaction() as tx:
            return tx.append(sheet, record, **kw)

    def update(self, sheet: Sheet | str, where: dict[str, Any], changes: dict[str, Any],
               **kw: Any) -> Row:
        with self.transaction() as tx:
            return tx.update(sheet, where, changes, **kw)

    # -------------------------------------------------------------- internals
    def _assert_writable(self) -> None:
        """Excel opens files with a write-deny share mode, so r+b fails on Windows."""
        try:
            with open(self.path, "r+b"):
                pass
        except PermissionError:
            raise ExcelFileLockedError()

    def _commit(self, tx: Transaction) -> None:
        self.backup()
        self._atomic_save(tx.wb)
        self._cache = None

    def _atomic_save(self, wb: Workbook) -> None:
        tmp = self.path.with_name(f"{self.path.stem}.tmp{self.path.suffix}")   # academy.tmp.xlsx
        try:
            wb.save(tmp)
            with open(tmp, "r+b") as f:
                f.flush()
                os.fsync(f.fileno())
            chk = load_workbook(tmp, read_only=True)           # sanity re-open
            chk.close()
            for attempt in range(4):                          # AV / sync clients can hold briefly
                try:
                    os.replace(tmp, self.path)
                    return
                except PermissionError:
                    if attempt == 3:
                        raise ExcelFileLockedError()
                    _time.sleep(0.3)
        except ExcelFileLockedError:
            tmp.unlink(missing_ok=True)
            raise
        except PermissionError:
            tmp.unlink(missing_ok=True)
            raise ExcelFileLockedError()
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    # ---------------------------------------------------------------- backups
    def backup(self) -> Optional[Path]:
        if not self.path.exists():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3]
        dest = self.backup_dir / f"{self.path.stem}_{stamp}{self.path.suffix}"
        if self._is_sqlite:
            src_conn = sqlite3.connect(self.path, timeout=10.0)
            dst_conn = sqlite3.connect(dest)
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()
        else:
            shutil.copy2(self.path, dest)
        self._prune_backups()
        return dest

    _BK_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{6})_\d{3}\.(xlsx|db|sqlite|sqlite3)$")

    def list_backups(self) -> list[tuple[datetime, Path]]:
        out = []
        for p in self.backup_dir.glob(f"{self.path.stem}_*"):
            m = self._BK_RE.search(p.name)
            if m:
                out.append((datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S"), p))
        return sorted(out, reverse=True)                        # newest first

    def restore_backup(self, backup_path: Path | str) -> Path:
        src = Path(backup_path)
        if not src.exists():
            raise RecordNotFoundError(f"ملف النسخة الاحتياطية غير موجود: {src.name}")
        with self._lock:
            self.backup()  # Safety pre-restore backup
            if self._is_sqlite and src.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                src_conn = sqlite3.connect(src, timeout=10.0)
                dst_conn = sqlite3.connect(self.path, timeout=10.0)
                try:
                    src_conn.backup(dst_conn)
                finally:
                    dst_conn.close()
                    src_conn.close()
                self._ensure_sqlite()
            else:
                shutil.copy2(src, self.path)
            self._cache = None
            self._cache_stamp = None
            if hasattr(self, "_settings_mem"):
                self._settings_mem.clear()
        return self.path

    def _prune_backups(self) -> None:
        now = datetime.now()
        recent_cut = now - timedelta(hours=config.BACKUP_KEEP_RECENT_HOURS)
        daily_cut = now - timedelta(days=config.BACKUP_KEEP_DAILY_DAYS)
        keep: set[Path] = set()
        seen_days: set[date] = set()
        recent_count = 0
        for ts, p in self.list_backups():                       # newest first
            if ts >= recent_cut:
                if recent_count < config.BACKUP_MAX_RECENT:
                    keep.add(p)
                    recent_count += 1
                    seen_days.add(ts.date())
            elif ts >= daily_cut and ts.date() not in seen_days:
                keep.add(p)
                seen_days.add(ts.date())
        for _, p in self.list_backups():
            if p not in keep:
                try:
                    p.unlink()
                except OSError:
                    log.warning("Could not prune backup %s", p)

