"""Shared PDF helpers: Cairo font registration, Arabic shaping, header/footer, amount in words."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Optional

import arabic_reshaper
from bidi.algorithm import get_display
from num2words import num2words
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

import config

RED = colors.HexColor("#F05500")
NAVY = colors.HexColor("#0A194E")
RED_LIGHT = colors.HexColor("#FFF4ED")
ZEBRA = colors.HexColor("#F8FAFC")
TEXT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#D1D5DB")

REG, BOLD = "Cairo", "Cairo-Bold"
_ready = False
_reshaper = arabic_reshaper.ArabicReshaper()
_cmap: set[int] = set()
_FIXED: dict[str, str] = {}


def register_fonts() -> None:
    global _ready
    if _ready:
        return
    pdfmetrics.registerFont(TTFont(REG, str(config.FONT_PDF_REGULAR)))
    pdfmetrics.registerFont(TTFont(BOLD, str(config.FONT_PDF_BOLD)))
    pdfmetrics.registerFontFamily(REG, normal=REG, bold=BOLD)
    _cmap.update(pdfmetrics.getFont(REG).face.charToGlyph.keys())
    _ready = True


def _glyph_safe(ch: str) -> str:
    """Cairo lacks a few *isolated* presentation forms (alef, jeem, lam, meem...). Its base letter
    already draws the isolated shape, so fall back to the base codepoint when a form is missing."""
    if ord(ch) in _cmap or not (0xFB50 <= ord(ch) <= 0xFEFF):
        return ch
    if ch not in _FIXED:
        dec = unicodedata.decomposition(ch)
        base = dec.split()[-1] if dec.startswith("<") else ""
        _FIXED[ch] = chr(int(base, 16)) if base and len(dec.split()) == 2 else ch
    return _FIXED[ch]


def ar(text) -> str:
    """Logical Arabic text -> shaped + visually reordered string reportlab can draw."""
    register_fonts()
    text = re.sub(r"(\d{4})-(\d{2})(?:-(\d{2}))?",              # ISO dates flip inside RTL text with '-',
                  lambda m: "/".join(g for g in m.groups() if g), str(text if text is not None else ""))  # '/' keeps order
    shaped = _reshaper.reshape(text)
    return get_display("".join(_glyph_safe(ch) for ch in shaped))


def width(text, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(ar(text), font, size)


def wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    """Greedy word wrap on the LOGICAL text (each returned line is still logical)."""
    lines: list[str] = []
    cur = ""
    for word in str(text).split():
        trial = f"{cur} {word}".strip()
        if cur and width(trial, font, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_r(c: rl_canvas.Canvas, x: float, y: float, text, font: str = REG, size: float = 10,
           color=TEXT) -> None:
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawRightString(x, y, ar(text))


def draw_c(c: rl_canvas.Canvas, x: float, y: float, text, font: str = REG, size: float = 10,
           color=TEXT) -> None:
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(x, y, ar(text))


def draw_l(c: rl_canvas.Canvas, x: float, y: float, text, font: str = REG, size: float = 10,
           color=TEXT) -> None:
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawString(x, y, ar(text))


def header(c: rl_canvas.Canvas, page_w: float, page_h: float, margin: float, subtitle: str = "") -> float:
    """Academy header; returns the y just below it."""
    top = page_h - margin
    if config.LOGO_FILE.exists():
        try:
            c.drawImage(str(config.LOGO_FILE), page_w - margin - 14 * mm, top - 14 * mm, 14 * mm, 14 * mm,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    draw_r(c, page_w - margin - 17 * mm, top - 6 * mm, config.ACADEMY_FULL_NAME_AR, BOLD, 11, RED)
    if subtitle:
        draw_r(c, page_w - margin - 17 * mm, top - 11.5 * mm, subtitle, REG, 8.5, MUTED)
    c.setStrokeColor(RED)
    c.setLineWidth(1.2)
    c.line(margin, top - 16 * mm, page_w - margin, top - 16 * mm)
    return top - 20 * mm


def footer(c: rl_canvas.Canvas, page_w: float, margin: float, user: str = "", page: Optional[int] = None) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(margin, margin + 4 * mm, page_w - margin, margin + 4 * mm)
    stamp = f"{datetime.now():%Y-%m-%d %H:%M}"
    draw_r(c, page_w - margin, margin, f"تاريخ الإصدار: {stamp}" + (f"  |  بواسطة: {user}" if user else ""),
           REG, 7.5, MUTED)
    if page is not None:
        draw_l(c, margin, margin, f"صفحة {page}", REG, 7.5, MUTED)


def _num_words(n: int) -> str:
    s = num2words(n, lang="ar")
    s = re.sub(r"\s*,\s*", " ", re.sub(r" و ", " و", s)).strip()
    return s            # library already gives the construct form before a noun: 'ألفا جنيه', 'مئتا جنيه'


def _counted(n: int, one: str, two: str, few: str, many: str, base: str) -> str:
    """Arabic number-noun agreement: 1 -> 'جنيه واحد', 2 -> 'جنيهان', 3-10 plural, 11-99 accusative."""
    if n == 1:
        return f"{one} واحد"
    if n == 2:
        return two
    r = n % 100
    if 3 <= r <= 10:
        return f"{_num_words(n)} {few}"
    if 11 <= r <= 99:
        return f"{_num_words(n)} {many}"
    return f"{_num_words(n)} {base}"


def amount_words(amount: float) -> str:
    """1500 -> 'فقط ألف وخمسمائة جنيه لا غير' (with piasters when present)."""
    amount = round(float(amount), 2)
    pounds, piasters = int(amount), int(round((amount - int(amount)) * 100))
    parts = []
    if pounds:
        parts.append(_counted(pounds, "جنيه", "جنيهان", "جنيهات", "جنيهًا", "جنيه"))
    if piasters:
        parts.append(_counted(piasters, "قرش", "قرشان", "قروش", "قرشًا", "قرش"))
    return "فقط " + (" و".join(parts) if parts else "صفر جنيه") + " لا غير"


# ---------------------------------------------------------------- platypus helpers (tables)
from reportlab.lib.pagesizes import A4                                   # noqa: E402
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, PageTemplate,  # noqa: E402
                                Spacer, Table, TableStyle)


def rtl_table(rows: list[list], col_widths: list[float], header: bool = True, font_size: float = 8.5,
              align: str = "CENTER", zebra: bool = True, repeat: int = 1) -> Table:
    """Table whose FIRST logical column is drawn at the RIGHT edge (Arabic reading order)."""
    data = [[ar(cell) if isinstance(cell, str) else ar(str(cell)) for cell in reversed(r)] for r in rows]
    t = Table(data, colWidths=list(reversed(col_widths)), repeatRows=repeat if header else 0)
    style = [("FONT", (0, 0), (-1, -1), REG, font_size), ("TEXTCOLOR", (0, 0), (-1, -1), TEXT),
             ("ALIGN", (0, 0), (-1, -1), align), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), BOLD, font_size)]
    if zebra:
        style += [("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, ZEBRA])]
    t.setStyle(TableStyle(style))
    return t


class SignatureLines(Flowable):
    def __init__(self, width: float, labels: list[str]):
        super().__init__()
        self.width, self.height, self.labels = width, 26 * mm, labels

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        n = len(self.labels)
        seg = self.width / n
        for i, label in enumerate(self.labels):                          # first label at the right
            xr = self.width - i * seg
            self.canv.setStrokeColor(TEXT)
            self.canv.setLineWidth(0.6)
            self.canv.line(xr - seg + 8 * mm, 14 * mm, xr - 8 * mm, 14 * mm)
            self.canv.setFont(REG, 8.5)
            self.canv.setFillColor(MUTED)
            self.canv.drawCentredString(xr - seg / 2, 9 * mm, ar(label))


class MethodChecks(Flowable):
    """'طريقة الدفع: [x] نقدي  [ ] إنستا باي ...' with real check boxes."""
    def __init__(self, width: float, selected: list[str]):
        super().__init__()
        self.width, self.height, self.selected = width, 9 * mm, set(selected)

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c, x = self.canv, self.width
        c.setFont(BOLD, 9)
        c.setFillColor(TEXT)
        c.drawRightString(x, 3 * mm, ar("طريقة الدفع:"))
        x -= 28 * mm
        for key, label in config.PAYMENT_METHODS_AR.items():
            c.setStrokeColor(TEXT)
            c.setLineWidth(0.7)
            c.rect(x - 4 * mm, 2.4 * mm, 4 * mm, 4 * mm)
            if key in self.selected:
                c.setStrokeColor(RED)
                c.setLineWidth(1.4)
                c.line(x - 3.6 * mm, 4.4 * mm, x - 2.2 * mm, 3 * mm)
                c.line(x - 2.2 * mm, 3 * mm, x - 0.4 * mm, 6 * mm)
            c.setFont(REG, 9)
            c.setFillColor(TEXT)
            c.drawRightString(x - 6 * mm, 3 * mm, ar(label))
            x -= 6 * mm + width(label, REG, 9) + 8 * mm


def build_doc(path, title: str, subtitle: str, story: list, user: str = "", pagesize=A4,
              margin: float = 14 * mm) -> None:
    """Flowable document with the academy header/footer on every page."""
    register_fonts()
    W, H = pagesize

    def on_page(c, doc):
        header(c, W, H, margin, subtitle)
        footer(c, W, margin, user, doc.page)

    doc = BaseDocTemplate(str(path), pagesize=pagesize, leftMargin=margin, rightMargin=margin,
                          topMargin=margin + 22 * mm, bottomMargin=margin + 8 * mm, title=title)
    frame = Frame(margin, margin + 8 * mm, W - 2 * margin, H - 2 * margin - 30 * mm, id="f",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=on_page)])
    doc.build(story)
