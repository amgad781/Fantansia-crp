"""Student Evaluation Form PDF builder (A4 Portrait, canvas-based)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

import config
from export.pdf_common import (
    BOLD, LINE, MUTED, NAVY, RED, REG, TEXT, ZEBRA,
    ar, draw_r, footer as P_footer, register_fonts,
)

# ---------------------------------------------------------------------------
# Evaluation schema
# ---------------------------------------------------------------------------
CRITERIA = [
    ("attendance",   "Attendance"),
    ("assignments",  "Assignments"),
    ("technical",    "Technical Skills \u2014 Trainee understands and is able to apply new engineering concepts"),
    ("thinking",     "Thinking Skills \u2014 Trainee used creative and scientific thinking to complete tasks "
                     "and create models during session"),
    ("presentation", "Presentation Skills \u2014 Trainee is able to express himself/herself using good "
                     "presentation skills"),
    ("teamwork",     "Team Work \u2014 Trainee efficiently worked in a team during sessions"),
]

RATINGS = ["exceeds", "accomplished", "developing", "beginning"]
RATING_LABELS = ["Exceeds", "Accomplished", "Developing", "Beginning"]

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
_MARGIN = 14 * mm
_CRITERIA_W = 100 * mm   # criteria column
_RATING_W = 22 * mm      # each of the 4 rating columns
_ROW_H = 14 * mm         # table body row height
_HDR_H = 10 * mm         # table header row height
_CB_SIZE = 4 * mm        # checkbox square side
_FONT_TABLE = 8.0        # pt — table body


def build_evaluation_pdf(path: Path, data: dict[str, Any]) -> Path:
    """Generate a printable A4 student evaluation form and save to *path*."""
    register_fonts()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    W, H = A4
    c = rl_canvas.Canvas(str(path), pagesize=(W, H))
    student_name = str(data.get("student_name") or "")
    level = str(data.get("level") or "")
    group_label = str(data.get("group_label") or "")
    date_str = str(data.get("date") or "")
    scores: dict = data.get("scores") or {}
    recommendation = str(data.get("recommendation") or "")
    user = str(data.get("user") or "")

    c.setTitle(f"Student Evaluation — {student_name}")

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    top = H - _MARGIN

    # Logo (left side of A4)
    if config.LOGO_FILE.exists():
        try:
            c.drawImage(
                str(config.LOGO_FILE),
                _MARGIN, top - 18 * mm,
                18 * mm, 18 * mm,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # Arabic academy name — bold red, right-aligned
    draw_r(c, W - _MARGIN, top - 6 * mm,
           "فانتازيا لتطوير الذات والتدريب التكنولوجي",
           BOLD, 12, RED)
    # English sub-line — muted, right-aligned
    c.setFont(REG, 8.5)
    c.setFillColor(MUTED)
    c.drawRightString(W - _MARGIN, top - 13 * mm,
                      "Fantasia for self-development and technological training")

    # Horizontal rule
    c.setStrokeColor(RED)
    c.setLineWidth(1.2)
    c.line(_MARGIN, top - 20 * mm, W - _MARGIN, top - 20 * mm)

    y = top - 27 * mm   # cursor below header rule

    # -----------------------------------------------------------------------
    # Document title
    # -----------------------------------------------------------------------
    c.setFont(BOLD, 13)
    c.setFillColor(NAVY)
    c.drawCentredString(W / 2, y, "Student Evaluation Form")
    y -= 8 * mm

    # -----------------------------------------------------------------------
    # Student info row
    # -----------------------------------------------------------------------
    c.setFont(BOLD, 9.5)
    c.setFillColor(TEXT)

    name_label = ar("الاسم / Name:  ")
    level_label = ar("المستوى / Level:  ")

    # Right side: الاسم (Arabic reads right-to-left so we draw from right)
    c.drawRightString(W - _MARGIN, y, name_label)
    # Value or underline
    name_x = W - _MARGIN - c.stringWidth(name_label, BOLD, 9.5)
    if student_name:
        c.setFont(REG, 9.5)
        c.setFillColor(TEXT)
        c.drawRightString(name_x - 1, y, student_name)
    else:
        c.setStrokeColor(TEXT)
        c.setLineWidth(0.5)
        c.line(name_x - 45 * mm, y - 1, name_x - 2, y - 1)

    # Left side: Level
    c.setFont(BOLD, 9.5)
    c.setFillColor(TEXT)
    c.drawString(_MARGIN, y, level_label)
    lv_x = _MARGIN + c.stringWidth(level_label, BOLD, 9.5)
    if level:
        c.setFont(REG, 9.5)
        c.setFillColor(TEXT)
        c.drawString(lv_x + 1, y, level)
    else:
        c.setStrokeColor(TEXT)
        c.setLineWidth(0.5)
        c.line(lv_x + 2, y - 1, lv_x + 45 * mm, y - 1)

    # Group + date (smaller, muted)
    if group_label or date_str:
        info_parts = []
        if group_label:
            info_parts.append(f"Group: {group_label}")
        if date_str:
            info_parts.append(f"Date: {date_str}")
        c.setFont(REG, 8)
        c.setFillColor(MUTED)
        c.drawCentredString(W / 2, y - 6 * mm, "   |   ".join(info_parts))
        y -= 6 * mm

    y -= 8 * mm   # gap before table

    # -----------------------------------------------------------------------
    # Evaluation table
    # -----------------------------------------------------------------------
    table_x = _MARGIN
    table_w = _CRITERIA_W + len(RATINGS) * _RATING_W   # ~188 mm

    # --- Table header row ---
    c.setFillColor(NAVY)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.4)
    c.rect(table_x, y - _HDR_H, table_w, _HDR_H, stroke=1, fill=1)

    # "Criteria" column header
    c.setFont(BOLD, 9)
    c.setFillColor(colors.white)
    c.drawString(table_x + 3 * mm, y - _HDR_H + 3.5 * mm, "Evaluation Criteria")

    # Rating column headers — centred in each column
    for i, label in enumerate(RATING_LABELS):
        col_x = table_x + _CRITERIA_W + i * _RATING_W
        c.setFont(BOLD, 8)
        c.setFillColor(colors.white)
        c.drawCentredString(col_x + _RATING_W / 2, y - _HDR_H + 3.5 * mm, label)

    y -= _HDR_H

    # --- Table body rows ---
    for row_idx, (key, label) in enumerate(CRITERIA):
        bg = colors.white if row_idx % 2 == 0 else ZEBRA
        c.setFillColor(bg)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.4)
        c.rect(table_x, y - _ROW_H, table_w, _ROW_H, stroke=1, fill=1)

        # Draw criteria text (English, wrapped to fit column width)
        _draw_wrapped_text(c, label, REG, _FONT_TABLE,
                           table_x + 2 * mm, y - 2.5 * mm,
                           _CRITERIA_W - 4 * mm, _ROW_H - 4 * mm)

        # Draw checkboxes for each rating column
        chosen = str(scores.get(key) or "").lower().strip()
        for i, rating in enumerate(RATINGS):
            col_x = table_x + _CRITERIA_W + i * _RATING_W
            cb_x = col_x + (_RATING_W - _CB_SIZE) / 2
            cb_y = y - _ROW_H / 2 - _CB_SIZE / 2

            # Checkbox square
            c.setStrokeColor(NAVY)
            c.setLineWidth(0.7)
            c.setFillColor(bg)
            c.rect(cb_x, cb_y, _CB_SIZE, _CB_SIZE, stroke=1, fill=1)

            # Filled checkmark if this rating is selected
            if chosen == rating:
                c.setStrokeColor(RED)
                c.setLineWidth(1.4)
                # Draw a tick: bottom-left angle then up-right
                c.line(cb_x + 0.6 * mm, cb_y + _CB_SIZE * 0.45,
                       cb_x + _CB_SIZE * 0.40, cb_y + 0.6 * mm)
                c.line(cb_x + _CB_SIZE * 0.40, cb_y + 0.6 * mm,
                       cb_x + _CB_SIZE - 0.5 * mm, cb_y + _CB_SIZE - 0.5 * mm)

        y -= _ROW_H

    # Bottom border of last row already drawn; just move cursor
    y -= 4 * mm

    # -----------------------------------------------------------------------
    # Recommendation field
    # -----------------------------------------------------------------------
    c.setFont(BOLD, 9.5)
    c.setFillColor(TEXT)
    c.drawString(table_x, y, "Recommendation / التوصية:")
    y -= 7 * mm

    if recommendation:
        c.setFont(REG, 9)
        c.setFillColor(TEXT)
        # Simple wrap for recommendation text
        _draw_wrapped_text(c, recommendation, REG, 9,
                           table_x, y, table_w - 4 * mm, 20 * mm,
                           line_h=5.5 * mm)
        y -= 12 * mm
    else:
        # Three dotted lines
        for _ in range(3):
            c.setStrokeColor(LINE)
            c.setLineWidth(0.5)
            c.setDash(1, 2)
            c.line(table_x, y, table_x + table_w, y)
            c.setDash()
            y -= 6 * mm
        y -= 2 * mm

    y -= 6 * mm

    # -----------------------------------------------------------------------
    # Signature line
    # -----------------------------------------------------------------------
    sig_w = 60 * mm
    sig_x = _MARGIN
    c.setFont(BOLD, 9)
    c.setFillColor(TEXT)
    c.drawString(sig_x, y, "Instructor Signature:")
    c.setStrokeColor(TEXT)
    c.setLineWidth(0.6)
    c.line(sig_x + 46 * mm, y - 1, sig_x + 46 * mm + sig_w, y - 1)
    y -= 3 * mm

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------
    P_footer(c, W, _MARGIN, user=user)

    c.showPage()
    c.save()
    return path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _draw_wrapped_text(
    c: rl_canvas.Canvas,
    text: str,
    font: str,
    size: float,
    x: float,
    y: float,
    max_w: float,
    max_h: float,
    line_h: float | None = None,
) -> None:
    """Draw left-to-right English text with simple word-wrap inside a bounding box."""
    if line_h is None:
        line_h = size * 1.35
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if cur and c.stringWidth(trial, font, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)

    c.setFont(font, size)
    c.setFillColor(TEXT)
    cur_y = y
    for line in lines:
        if y - cur_y > max_h:
            break
        c.drawString(x, cur_y, line)
        cur_y -= line_h
