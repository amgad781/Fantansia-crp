"""Fantasia CRP – entry point.

    python main.py             # native desktop window
    python main.py --browser   # dev mode: opens in the default browser instead
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from logging.handlers import RotatingFileHandler

import config

# Must be set BEFORE nicegui is imported (NiceGUI's storage folder otherwise lands in the CWD).
config.NICEGUI_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NICEGUI_STORAGE_PATH", str(config.NICEGUI_STORAGE_DIR))

from nicegui import app, ui  # noqa: E402

from core.context import build_context  # noqa: E402
from core.excel_repo import RepoError  # noqa: E402
from ui.app import register_all  # noqa: E402

log = logging.getLogger("fantasia")

_ICON_PATH = config.ICON_FILE if config.ICON_FILE.exists() else config.LOGO_FILE
if _ICON_PATH.exists():
    app.native.start_args["icon"] = str(_ICON_PATH)

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nicegui.app")
    except Exception:
        pass


# ============================================================================
# Single instance (rule 6)
# ============================================================================
class SingleInstance:
    """Windows: named mutex. Other OSes (dev only): exclusive lock on a temp file."""
    NAME = "FantasiaCRP_SingleInstance"

    def __init__(self) -> None:
        self._handle = None          # keep a reference for the whole process lifetime

    def acquire(self) -> bool:
        if sys.platform == "win32":
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
            k32.CreateMutexW.restype = ctypes.c_void_p
            self._handle = k32.CreateMutexW(None, False, f"Local\\{self.NAME}")
            return ctypes.get_last_error() != 183          # ERROR_ALREADY_EXISTS
        import fcntl
        import tempfile
        self._handle = open(os.path.join(tempfile.gettempdir(), self.NAME + ".lock"), "w")
        try:
            fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False


def fatal(message_ar: str, title: str = config.APP_NAME_AR) -> None:
    """Arabic error before the UI exists: native message box on Windows."""
    log.error(message_ar)
    if sys.platform == "win32":
        import ctypes
        # MB_ICONERROR | MB_TOPMOST | MB_RIGHT | MB_RTLREADING
        ctypes.windll.user32.MessageBoxW(None, message_ar, title, 0x10 | 0x40000 | 0x80000 | 0x100000)
    else:
        print(message_ar, file=sys.stderr)


def setup_logging() -> None:
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(config.LOG_DIR / "app.log", maxBytes=1_000_000,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


# ============================================================================
# Startup
# ============================================================================
def main() -> None:
    setup_logging()

    instance = SingleInstance()
    if not instance.acquire():
        fatal("البرنامج يعمل بالفعل على هذا الجهاز.\nاستخدم النافذة المفتوحة.")
        sys.exit(0)

    try:
        ctx = build_context()                    # creates / migrates academy.xlsx
    except RepoError as e:
        fatal(str(e))
        sys.exit(1)

    browser_mode = "--browser" in sys.argv

    if config.ASSETS_DIR.exists():
        app.add_static_files("/assets", str(config.ASSETS_DIR))
    register_all(ctx)

    ui.run(
        title=config.APP_NAME_AR,
        language="ar",
        native=not browser_mode,
        window_size=None if browser_mode else (1440, 900),   # window_size implies native=True
        reload=False,                  # required for native mode and PyInstaller
        show=browser_mode,
        dark=False,
        show_welcome_message=False,
        favicon=str(_ICON_PATH) if _ICON_PATH.exists() else None,
    )


if __name__ in {"__main__", "__mp_main__"}:
    multiprocessing.freeze_support()
    # The native window runs in a child process that re-imports this module: only the parent starts the app.
    if multiprocessing.current_process().name == "MainProcess":
        main()
