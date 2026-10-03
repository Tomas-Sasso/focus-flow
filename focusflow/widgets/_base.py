"""Base del paquete: el lienzo pintado con PIL, el punto de color y los
formatos de tiempo y de fechas que usan las vistas y el resto de los widgets."""

from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from .. import render as R

__all__ = [
    "MONTHS_ES", "MONTHS_SHORT", "WEEKDAY_INITIALS", "WEEKDAY_NAMES", "scaling_of",
    "fmt_hms", "fmt_ms", "fmt_short", "fmt_hours", "PILCanvas", "Dot",
]


MONTHS_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
             "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
                "oct", "nov", "dic"]
WEEKDAY_INITIALS = ["L", "M", "M", "J", "V", "S", "D"]
WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado",
                 "Domingo"]


def scaling_of(widget):
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:
        return 1.0


def fmt_hms(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def fmt_ms(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def fmt_short(seconds):
    seconds = max(0, int(seconds))
    hours, minutes = seconds // 3600, (seconds % 3600) // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def fmt_hours(seconds):
    return f"{max(0.0, seconds) / 3600:.1f} h"


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #


class PILCanvas(tk.Canvas):
    """Canvas repintado con una imagen de PIL. Las subclases definen `render`."""

    #: Milisegundos mínimos entre cuadros durante una animación. 0 = sin tope.
    #: Un anillo grande tarda unos 20 ms en dibujarse; a 60 fps no llega y la
    #: ventana se traba, así que los dibujos caros bajan su propia tasa.
    min_frame_ms = 0

    def __init__(self, master, background, width=100, height=100, **kwargs):
        super().__init__(master, width=width, height=height, bg=background,
                         highlightthickness=0, bd=0, **kwargs)
        self.background = background
        self._photo = None
        self._item = None
        self._pending = False
        self._last_size = (0, 0)
        self._last_paint = 0.0
        self._trailing = False
        self.bind("<Configure>", self._on_configure, add="+")

    def animation_redraw(self):
        """Repintado para cuadros de animación, con tope de tasa."""
        if not self.min_frame_ms:
            self.redraw()
            return
        now = time.perf_counter() * 1000.0
        if now - self._last_paint < self.min_frame_ms:
            # Nos salteamos este cuadro pero agendamos uno al final, así lo que
            # queda en pantalla es siempre el último estado.
            if not self._trailing:
                self._trailing = True
                try:
                    self.after(int(self.min_frame_ms), self._trailing_paint)
                except tk.TclError:
                    self._trailing = False
            return
        self._last_paint = now
        self.redraw()

    def _trailing_paint(self):
        self._trailing = False
        self._last_paint = time.perf_counter() * 1000.0
        self.redraw()

    def _on_configure(self, _event=None):
        size = (self.winfo_width(), self.winfo_height())
        if size != self._last_size:
            self._last_size = size
            self.schedule_redraw()

    def schedule_redraw(self):
        if self._pending:
            return
        self._pending = True
        try:
            self.after_idle(self._do_redraw)
        except tk.TclError:
            self._pending = False

    def _do_redraw(self):
        self._pending = False
        self.redraw()

    def redraw(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 1 or height <= 1:
            return
        image = self.render(width, height)
        if image is None:
            return
        self._photo = ImageTk.PhotoImage(image)
        if self._item is None:
            self._item = self.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.itemconfigure(self._item, image=self._photo)

    def render(self, width, height):  # pragma: no cover
        raise NotImplementedError


def _dot(width, height, color, background):
    size = max(4, min(width, height))
    image = R.rounded_panel(size, size, size / 2, background, color)
    if (width, height) != (size, size):
        canvas = Image.new("RGB", (width, height), R.hex_to_rgb(background))
        canvas.paste(image, ((width - size) // 2, (height - size) // 2))
        return canvas
    return image


class Dot(PILCanvas):
    def __init__(self, master, background, color, size=9, **kwargs):
        super().__init__(master, background, width=size, height=size, **kwargs)
        self.color = color

    def render(self, width, height):
        return _dot(width, height, self.color, self.background)
