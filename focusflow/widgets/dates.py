"""Fechas: el calendario del mes y el campo de fecha desplegable."""

from __future__ import annotations

import calendar as _calendar
import tkinter as tk
from datetime import date

import customtkinter as ctk
from PIL import Image, ImageDraw

from .. import render as R
from ..theme import COLORS, RADIUS, SPACE
from ._base import MONTHS_ES, WEEKDAY_INITIALS, PILCanvas, scaling_of
from .buttons import SmoothButton

__all__ = [
    "MiniCalendar", "DateField",
]


# --------------------------------------------------------------------------- #
# Calendario
# --------------------------------------------------------------------------- #


class MiniCalendar(PILCanvas):
    CELL = 34
    HEADER = 50
    WEEK_ROW = 22

    def __init__(self, master, animator, background, fonts, on_select=None,
                 on_month_change=None, **kwargs):
        self.animator = animator
        self.fonts = fonts
        self.on_select = on_select
        self.on_month_change = on_month_change
        self.today = date.today()
        self.view = date(self.today.year, self.today.month, 1)
        self.selected = self.today
        self.marked = {}
        self._hover = None
        self._cells = []
        self._slide = 0.0
        self._nav_hover = None
        super().__init__(master, background,
                         width=self.CELL * 7 + 16,
                         height=self.HEADER + self.WEEK_ROW + self.CELL * 6 + 8,
                         **kwargs)
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click, add="+")
        self.bind("<MouseWheel>", self._on_wheel, add="+")

    def set_marked(self, marked):
        self.marked = dict(marked)
        self.schedule_redraw()

    def set_selected(self, day, notify=False):
        self.selected = day
        if (day.year, day.month) != (self.view.year, self.view.month):
            self.view = date(day.year, day.month, 1)
        self.schedule_redraw()
        if notify and self.on_select:
            self.on_select(day)

    def shift_month(self, delta):
        year, month = self.view.year, self.view.month + delta
        while month < 1:
            month, year = month + 12, year - 1
        while month > 12:
            month, year = month - 12, year + 1
        self.view = date(year, month, 1)
        self._slide = -0.32 if delta > 0 else 0.32

        def update(value):
            self._slide = value
            self.redraw()

        self.animator.to(("cal", id(self)), self._slide, 0.0, duration=0.3,
                         easing="out_quint", on_update=update)
        if self.on_month_change:
            self.on_month_change(self.view)

    def _hit(self, x, y):
        for rect, day in self._cells:
            if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
                return day
        return None

    def _nav_hit(self, x, y):
        if y > self.HEADER - 12:
            return None
        width = self.winfo_width()
        if x > width - 38:
            return "next"
        if x > width - 72:
            return "prev"
        return None

    def _on_motion(self, event):
        nav = self._nav_hit(event.x, event.y)
        day = None if nav else self._hit(event.x, event.y)
        if nav != self._nav_hover or day != self._hover:
            self._nav_hover, self._hover = nav, day
            self.configure(cursor="hand2" if (nav or day) else "")
            self.redraw()

    def _on_leave(self, _e=None):
        if self._hover or self._nav_hover:
            self._hover = self._nav_hover = None
            self.redraw()

    def _on_click(self, event):
        nav = self._nav_hit(event.x, event.y)
        if nav:
            self.shift_month(1 if nav == "next" else -1)
            return
        day = self._hit(event.x, event.y)
        if day is not None:
            self.selected = day
            self.redraw()
            if self.on_select:
                self.on_select(day)

    def _on_wheel(self, event):
        self.shift_month(-1 if event.delta > 0 else 1)
        return "break"

    def render(self, width, height):
        scale = scaling_of(self)
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        draw = ImageDraw.Draw(image)
        title_font = R.load_font(self.fonts.paths_bold, max(12, int(14 * scale)))
        day_font = R.load_font(self.fonts.paths, max(10, int(12 * scale)))
        head_font = R.load_font(self.fonts.paths_bold, max(9, int(10 * scale)))

        draw.text((8, 18), f"{MONTHS_ES[self.view.month - 1]} {self.view.year}",
                  font=title_font, anchor="lm", fill=R.hex_to_rgb(COLORS["text"]))

        for name, cx in (("prev", width - 55), ("next", width - 21)):
            active = self._nav_hover == name
            if active:
                image.paste(R.rounded_panel(26, 26, 8, self.background,
                                            COLORS["surface2"]), (int(cx - 13), 5))
            color = COLORS["text"] if active else COLORS["text_dim"]
            _chevron(draw, cx, 18, 5, "left" if name == "prev" else "right", color)

        cell = (width - 16) / 7.0
        for index, label in enumerate(WEEKDAY_INITIALS):
            draw.text((8 + cell * (index + 0.5), self.HEADER + self.WEEK_ROW / 2),
                      label, font=head_font, anchor="mm",
                      fill=R.hex_to_rgb(COLORS["text_faint"]))

        self._cells = []
        first_weekday, days_in_month = _calendar.monthrange(self.view.year, self.view.month)
        y0 = self.HEADER + self.WEEK_ROW
        offset = self._slide * width
        peak = max(self.marked.values()) if self.marked else 1.0

        for number in range(1, days_in_month + 1):
            current = date(self.view.year, self.view.month, number)
            row, col = divmod(first_weekday + number - 1, 7)
            cx = 8 + cell * (col + 0.5) + offset
            cy = y0 + self.CELL * (row + 0.5)
            if -cell < cx < width + cell:
                self._paint_day(image, draw, current, cx, cy, cell, day_font, peak)
            self._cells.append(((cx - cell / 2, cy - self.CELL / 2,
                                 cx + cell / 2, cy + self.CELL / 2), current))
        return image

    def _paint_day(self, image, draw, current, cx, cy, cell, font, peak):
        chip = int(min(cell, self.CELL) - 5)
        intensity = self.marked.get(current)

        if current == self.selected:
            image.paste(R.rounded_panel(chip, chip, 10, self.background,
                                        COLORS["accent"]), (int(cx - chip / 2), int(cy - chip / 2)))
            text_color = COLORS["app"]
        elif current == self._hover:
            image.paste(R.rounded_panel(chip, chip, 10, self.background,
                                        COLORS["surface2"]), (int(cx - chip / 2), int(cy - chip / 2)))
            text_color = COLORS["text"]
        elif current == self.today:
            image.paste(R.rounded_panel(chip, chip, 10, self.background,
                                        COLORS["surface"]), (int(cx - chip / 2), int(cy - chip / 2)))
            text_color = COLORS["accent"]
        else:
            text_color = COLORS["text"] if intensity else COLORS["text_faint"]

        draw.text((cx, cy - 3), str(current.day), font=font, anchor="mm",
                  fill=R.hex_to_rgb(text_color))

        if intensity:
            level = min(1.0, (intensity / peak) ** 0.6) if peak else 0.0
            color = (COLORS["app"] if current == self.selected
                     else R.mix(COLORS["accent_soft"], COLORS["accent"], 0.3 + level * 0.7))
            draw.ellipse((cx - 2, cy + 6, cx + 2, cy + 10), fill=R.hex_to_rgb(color))


def _chevron(draw, cx, cy, size, direction, color):
    rgb = R.hex_to_rgb(color)
    dx = size * 0.45
    if direction == "left":
        points = [(cx + dx, cy - size), (cx - dx, cy), (cx + dx, cy + size)]
    else:
        points = [(cx - dx, cy - size), (cx + dx, cy), (cx - dx, cy + size)]
    draw.line(points, fill=rgb, width=2, joint="curve")


class DateField(ctk.CTkFrame):
    def __init__(self, master, animator, fonts, value=None, on_change=None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.animator = animator
        self.fonts = fonts
        self.on_change = on_change
        self.value = value or date.today()
        self._popup = None
        self.button = SmoothButton(
            self, animator=animator, base_color=COLORS["surface2"],
            hover_color=COLORS["surface3"], text=self._label(), command=self.toggle,
            font=fonts["body"], text_color=COLORS["text"], anchor="w", height=34,
            corner_radius=RADIUS["xs"])
        self.button.pack(fill="x")

    def _label(self):
        return self.value.strftime("%d/%m/%Y")

    def get_date(self):
        return self.value

    def set_date(self, value, notify=False):
        self.value = value
        self.button.configure(text=self._label())
        if notify and self.on_change:
            self.on_change(value)

    def toggle(self):
        if self._popup is not None and self._popup.winfo_exists():
            self.close()
        else:
            self.open()

    def open(self):
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(bg=COLORS["surface"])
        frame = ctk.CTkFrame(popup, fg_color=COLORS["surface"], corner_radius=RADIUS["md"])
        frame.pack(padx=1, pady=1)
        calendar = MiniCalendar(frame, self.animator, COLORS["surface"], self.fonts,
                                on_select=self._pick)
        calendar.set_selected(self.value)
        calendar.pack(padx=SPACE["sm"], pady=SPACE["sm"])
        self._popup = popup
        self.update_idletasks()
        popup.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 4}")
        popup.bind("<FocusOut>", lambda _e: self.close())
        popup.after(60, popup.focus_force)

    def _pick(self, day):
        self.set_date(day, notify=True)
        self.close()

    def close(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
