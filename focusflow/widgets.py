"""Widgets de Focus Flow.

Todo lo que tiene forma propia se dibuja con PIL sobre un `tk.Canvas`: barra de
navegación, anillos, mapa de calor, calendario, línea de tiempo. Los widgets de
customtkinter se usan sólo donde alcanzan (etiquetas, entradas, scroll).
"""

from __future__ import annotations

import calendar as _calendar
import time
import tkinter as tk
from datetime import date, timedelta

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from . import render as R
from .theme import (COLORS, DATA, DATA_LABELS, DISPLAY_KIND, HEAT_RAMP, RADIUS,
                    SPACE)

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


# --------------------------------------------------------------------------- #
# Botones
# --------------------------------------------------------------------------- #


class SmoothButton(ctk.CTkButton):
    """Botón cuyo color se interpola en vez de saltar."""

    def __init__(self, master, animator=None, base_color=None, hover_color=None,
                 press_depth=0.12, **kwargs):
        base_color = base_color or kwargs.get("fg_color") or COLORS["accent"]
        kwargs.setdefault("fg_color", base_color)
        kwargs.setdefault("corner_radius", RADIUS["sm"])
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("height", 38)
        kwargs["hover"] = False
        super().__init__(master, **kwargs)
        self.animator = animator
        self.base_color = base_color
        self.hover_target = hover_color or R.lighten(base_color, 0.10)
        self.press_depth = press_depth
        self._current = base_color
        self._hovering = False
        self._pressed = False
        for widget in self._targets():
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
            widget.bind("<ButtonPress-1>", self._on_press, add="+")
            widget.bind("<ButtonRelease-1>", self._on_release, add="+")

    def _targets(self):
        widgets = [self]
        for attr in ("_canvas", "_text_label", "_image_label"):
            child = getattr(self, attr, None)
            if child is not None:
                widgets.append(child)
        return widgets

    def set_base_color(self, color, hover_color=None, animate=True):
        self.base_color = color
        self.hover_target = hover_color or R.lighten(color, 0.10)
        self._to(self._resting(), animate=animate)

    def _resting(self):
        if str(self.cget("state")) == "disabled":
            return R.mix(self.base_color, COLORS["surface2"], 0.6)
        if self._pressed:
            return R.darken(self.base_color, self.press_depth)
        if self._hovering:
            return self.hover_target
        return self.base_color

    def _to(self, color, animate=True, duration=0.16):
        if not animate or self.animator is None:
            self._current = color
            try:
                self.configure(fg_color=color)
            except Exception:
                pass
            return

        def update(value):
            self._current = value
            try:
                if self.winfo_exists():
                    self.configure(fg_color=value)
            except Exception:
                pass

        self.animator.color(("btn", id(self)), self._current, color,
                            duration=duration, easing="out_cubic", on_update=update)

    def _on_enter(self, _e=None):
        if str(self.cget("state")) == "disabled":
            return
        self._hovering = True
        self._to(self._resting())

    def _on_leave(self, _e=None):
        self._hovering = self._pressed = False
        self._to(self._resting(), duration=0.22)

    def _on_press(self, _e=None):
        if str(self.cget("state")) == "disabled":
            return
        self._pressed = True
        self._to(self._resting(), duration=0.07)

    def _on_release(self, _e=None):
        self._pressed = False
        self._to(self._resting(), duration=0.28)

    def configure(self, **kwargs):
        super().configure(**kwargs)
        if "state" in kwargs:
            self._to(self._resting(), animate=False)


TONES = {
    "accent": ("accent", "accent_hover", "app"),
    "mint": ("mint", "mint_hover", "app"),
    "amber": ("amber", "amber_hover", "app"),
    "rose": ("rose", "rose_hover", "app"),
    "lavender": ("lavender", "lavender", "app"),
    "ghost": ("surface3", "surface4", "text"),
    "quiet": ("surface2", "surface3", "text"),
    "danger": ("danger", "danger_hover", "text"),
    "orange": ("orange", "orange_hover", "app"),
    "yellow": ("yellow", "yellow_hover", "app"),
}


def button(master, animator, text, command, tone="accent", **kwargs):
    fill, hover, text_key = TONES.get(tone, TONES["accent"])
    kwargs.setdefault("text_color", COLORS[text_key])
    return SmoothButton(master, animator=animator, base_color=COLORS[fill],
                        hover_color=COLORS[hover], text=text, command=command, **kwargs)


# --------------------------------------------------------------------------- #
# Navegación lateral
# --------------------------------------------------------------------------- #


def _draw_icon(draw, name, cx, cy, size, color):
    """Iconos geométricos simples: se leen bien y no dependen de una fuente."""
    rgb = R.hex_to_rgb(color)
    half = size / 2

    if name == "Enfoque":
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), outline=rgb, width=2)
        draw.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=rgb)
    elif name == "Historial":
        draw.rounded_rectangle((cx - half, cy - half + 1, cx + half, cy + half),
                               radius=3, outline=rgb, width=2)
        draw.line((cx - half, cy - half + 5, cx + half, cy - half + 5), fill=rgb, width=2)
        for i in range(2):
            for j in range(3):
                x = cx - half + 4 + j * 4
                y = cy - half + 10 + i * 4
                draw.rectangle((x, y, x + 1.5, y + 1.5), fill=rgb)
    elif name == "Análisis":
        for index, height in enumerate((0.45, 0.8, 0.62)):
            x = cx - half + 1 + index * (size / 3)
            draw.rounded_rectangle(
                (x, cy + half - size * height, x + size / 3 - 3, cy + half),
                radius=1.5, fill=rgb)
    elif name == "Ajustes":
        for index, offset in enumerate((-5, 0, 5)):
            draw.line((cx - half, cy + offset, cx + half, cy + offset), fill=rgb, width=2)
            knob = cx - half + (size * (0.7 if index == 1 else 0.3))
            draw.ellipse((knob - 2.5, cy + offset - 2.5, knob + 2.5, cy + offset + 2.5),
                         fill=R.hex_to_rgb(COLORS["sidebar"]), outline=rgb, width=2)


class NavRail(PILCanvas):
    """Barra lateral con indicador que se desliza."""

    min_frame_ms = 22
    ROW = 46
    TOP = 8

    def __init__(self, master, animator, fonts, items, command=None, width=196, **kwargs):
        self.animator = animator
        self.fonts = fonts
        self.items = list(items)
        self.command = command
        self._index = 0
        self._marker = 0.0
        self._hover = -1
        super().__init__(master, COLORS["sidebar"], width=width,
                         height=self.TOP * 2 + self.ROW * len(items), **kwargs)
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click, add="+")
        self.configure(cursor="hand2")

    def _hit(self, y):
        index = int((y - self.TOP) // self.ROW)
        return index if 0 <= index < len(self.items) else -1

    def _on_motion(self, event):
        index = self._hit(event.y)
        if index != self._hover:
            self._hover = index
            self.redraw()

    def _on_leave(self, _e=None):
        if self._hover != -1:
            self._hover = -1
            self.redraw()

    def _on_click(self, event):
        index = self._hit(event.y)
        if index >= 0 and self.command:
            self.command(self.items[index])

    def get(self):
        return self.items[self._index]

    def select(self, name, animate=True):
        if name not in self.items or name == self.items[self._index]:
            if name in self.items:
                self._index = self.items.index(name)
                self.schedule_redraw()
            return
        self._index = self.items.index(name)
        target = float(self._index)
        if not animate:
            self._marker = target
            self.schedule_redraw()
            return

        def update(value):
            self._marker = value
            self.animation_redraw()

        self.animator.to(("nav", id(self)), self._marker, target, duration=0.3,
                         easing="out_quint", on_update=update, on_done=self.redraw)

    def render(self, width, height):
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        scale = scaling_of(self)
        font = R.load_font(self.fonts.paths_bold, max(11, int(13 * scale)))

        # --- indicador activo ---
        y = self.TOP + self._marker * self.ROW
        panel = R.rounded_panel(width - 16, self.ROW - 6, RADIUS["sm"],
                                self.background, COLORS["surface2"])
        image.paste(panel, (8, int(round(y + 3))))
        # barrita de acento a la izquierda
        bar = R.rounded_panel(3, self.ROW - 20, 2, COLORS["surface2"], COLORS["accent"])
        image.paste(bar, (12, int(round(y + 10))))

        draw = ImageDraw.Draw(image)
        for index, name in enumerate(self.items):
            row_y = self.TOP + index * self.ROW
            active = index == self._index
            if active:
                color = COLORS["text"]
            elif index == self._hover:
                color = COLORS["text_muted"]
            else:
                color = COLORS["text_dim"]
            _draw_icon(draw, name, 34, row_y + self.ROW / 2, 15, color)
            draw.text((56, row_y + self.ROW / 2), name, font=font, anchor="lm",
                      fill=R.hex_to_rgb(color))
        return image


# --------------------------------------------------------------------------- #
# Anillos
# --------------------------------------------------------------------------- #


class DonutChart(PILCanvas):
    """Anillo de las cuatro categorías con el porcentaje en el centro."""

    ORDER = ("focus", "other")
    min_frame_ms = 45

    def __init__(self, master, animator, background, fonts, key="donut",
                 caption="Concentración", show_center=True, inner_ratio=0.68,
                 max_size=260, glow=0.09, **kwargs):
        super().__init__(master, background, **kwargs)
        self.animator = animator
        self.fonts = fonts
        self.key = key
        self.caption = caption
        self.show_center = show_center
        self.inner_ratio = inner_ratio
        self.max_size = max_size
        self.glow = glow
        self._values = [0.0, 0.0, 0.0, 0.0]
        self._empty = True

    def set_values(self, mapping, animate=True):
        target = [max(0.0, float(mapping.get(k, 0.0))) for k in self.ORDER]
        self._empty = sum(target) <= 0
        # Si los valores no cambiaron no hay nada que animar. Sin esto, cada vez
        # que se volvía a una vista se relanzaba la animación completa y eso era
        # lo que trababa el cambio de menú.
        if all(abs(a - b) < 1e-6 for a, b in zip(self._values, target)):
            self._values = target
            self.schedule_redraw()
            return
        if not animate:
            self._values = target
            self.schedule_redraw()
            return

        def update(values):
            self._values = values
            self.animation_redraw()

        self.animator.sequence((self.key, id(self)), (list(self._values), target),
                               duration=0.5, easing="out_quint", on_update=update,
                               on_done=self.redraw)

    def render(self, width, height):
        side = max(40, min(width, height, int(self.max_size * scaling_of(self))))
        segments = list(zip(self._values, [DATA[k] for k in self.ORDER]))
        image = R.donut(
            side, segments, self.background,
            inner_ratio=0.90 if self._empty else self.inner_ratio,
            gap_deg=2.4, glow=0.0 if self._empty else self.glow,
            track=R.mix(self.background, COLORS["text_dim"], 0.2),
        )
        ox, oy = (width - side) // 2, (height - side) // 2
        if (width, height) != (side, side):
            canvas = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
            canvas.paste(image, (ox, oy))
            image = canvas

        if self.show_center:
            draw = ImageDraw.Draw(image)
            cx, cy = ox + side / 2, oy + side / 2
            big = R.load_font(self.fonts.paths_bold, max(15, int(side * 0.19)))
            small = R.load_font(self.fonts.paths, max(9, int(side * 0.062)))
            if self._empty:
                draw.text((cx, cy), "—", font=big, anchor="mm",
                          fill=R.hex_to_rgb(COLORS["text_faint"]))
            else:
                total = sum(self._values)
                pct = self._values[0] / total * 100.0 if total else 0.0
                draw.text((cx, cy - side * 0.045), f"{pct:.0f}%", font=big, anchor="mm",
                          fill=R.hex_to_rgb(COLORS["text"]))
                draw.text((cx, cy + side * 0.095), self.caption, font=small, anchor="mm",
                          fill=R.hex_to_rgb(COLORS["text_muted"]))
        return image


class MiniDonut(PILCanvas):
    ORDER = ("focus", "other")

    def __init__(self, master, background, fonts, size=84, **kwargs):
        super().__init__(master, background, width=size, height=size, **kwargs)
        self.fonts = fonts
        self.values = [0.0, 0.0, 0.0, 0.0]

    def set_values(self, mapping):
        self.values = [max(0.0, float(mapping.get(k, 0.0))) for k in self.ORDER]
        self.schedule_redraw()

    def render(self, width, height):
        side = max(30, min(width, height))
        image = R.donut(side, list(zip(self.values, [DATA[k] for k in self.ORDER])),
                        self.background, inner_ratio=0.62, gap_deg=3.0,
                        track=COLORS["surface3"])
        total = sum(self.values)
        if total > 0:
            draw = ImageDraw.Draw(image)
            font = R.load_font(self.fonts.paths_bold, max(10, int(side * 0.23)))
            draw.text((side / 2, side / 2), f"{self.values[0] / total * 100:.0f}%",
                      font=font, anchor="mm", fill=R.hex_to_rgb(COLORS["text"]))
        if (width, height) != (side, side):
            canvas = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
            canvas.paste(image, ((width - side) // 2, (height - side) // 2))
            image = canvas
        return image


class GoalRing(PILCanvas):
    """Anillo del objetivo diario, con el reloj de la fase adentro."""

    min_frame_ms = 33

    def __init__(self, master, animator, background, fonts, max_size=300, **kwargs):
        super().__init__(master, background, **kwargs)
        self.animator = animator
        self.fonts = fonts
        self.max_size = max_size
        self.fraction = 0.0
        self.color = COLORS["accent"]
        self.primary = "00:00"
        self.secondary = ""
        self.badge = ""

    def set_progress(self, fraction, animate=True):
        fraction = max(0.0, min(1.0, float(fraction)))
        if abs(fraction - self.fraction) < 1e-4:
            return
        if not animate:
            self.fraction = fraction
            self.schedule_redraw()
            return

        def update(value):
            self.fraction = value
            self.animation_redraw()

        self.animator.to(("goal", id(self)), self.fraction, fraction, duration=0.6,
                         easing="out_quint", on_update=update, on_done=self.redraw)

    def set_color(self, color, animate=True):
        if color == self.color:
            return
        if not animate:
            self.color = color
            self.schedule_redraw()
            return

        def update(value):
            self.color = value
            self.redraw()

        self.animator.color(("goalc", id(self)), self.color, color, duration=0.4,
                            on_update=update)

    def set_text(self, primary, secondary="", badge=""):
        if (primary, secondary, badge) == (self.primary, self.secondary, self.badge):
            return
        self.primary, self.secondary, self.badge = primary, secondary, badge
        self.schedule_redraw()

    def render(self, width, height):
        side = max(80, min(width, height, int(self.max_size * scaling_of(self))))
        image = R.progress_ring(side, self.fraction, self.color, COLORS["surface2"],
                                self.background, thickness=0.055, padding=3)
        ox, oy = (width - side) // 2, (height - side) // 2
        if (width, height) != (side, side):
            canvas = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
            canvas.paste(image, (ox, oy))
            image = canvas

        draw = ImageDraw.Draw(image)
        cx, cy = ox + side / 2, oy + side / 2
        clock = R.load_font(self.fonts.paths_bold, max(20, int(side * 0.215)))
        small = R.load_font(self.fonts.paths, max(9, int(side * 0.056)))
        badge_font = R.load_font(self.fonts.paths_bold, max(9, int(side * 0.052)))

        if self.badge:
            draw.text((cx, cy - side * 0.175), self.badge.upper(), font=badge_font,
                      anchor="mm", fill=R.hex_to_rgb(self.color))
        draw.text((cx, cy), self.primary, font=clock, anchor="mm",
                  fill=R.hex_to_rgb(COLORS["text"]))
        if self.secondary:
            draw.text((cx, cy + side * 0.155), self.secondary, font=small, anchor="mm",
                      fill=R.hex_to_rgb(COLORS["text_muted"]))
        return image


class RadialHours(PILCanvas):
    """Reloj de 24 franjas: a qué hora del día te concentrás."""

    def __init__(self, master, background, fonts, max_size=280, **kwargs):
        super().__init__(master, background, **kwargs)
        self.fonts = fonts
        self.max_size = max_size
        self.values = [0.0] * 24

    def set_values(self, values):
        self.values = list(values)[:24] + [0.0] * max(0, 24 - len(values))
        self.schedule_redraw()

    def render(self, width, height):
        side = max(120, min(width, height, int(self.max_size * scaling_of(self))))
        peak = max(self.values) if self.values else 0
        best = self.values.index(peak) if peak > 0 else None
        image = R.radial_profile(
            side, self.values, self.background, COLORS["accent"], COLORS["surface3"],
            highlight=best, highlight_color=COLORS["amber"],
            start_deg=-90.0 - 360.0 / 48,   # centramos la franja de las 0 h arriba
        )
        ox, oy = (width - side) // 2, (height - side) // 2
        if (width, height) != (side, side):
            canvas = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
            canvas.paste(image, (ox, oy))
            image = canvas

        draw = ImageDraw.Draw(image)
        font = R.load_font(self.fonts.paths, max(8, int(side * 0.045)))
        cx, cy = ox + side / 2, oy + side / 2
        for hour, label in ((0, "0"), (6, "6"), (12, "12"), (18, "18")):
            import math

            angle = math.radians(-90 + hour * 15)
            radius = side * 0.108
            draw.text((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius),
                      label, font=font, anchor="mm",
                      fill=R.hex_to_rgb(COLORS["text_dim"]))
        if peak > 0 and best is not None:
            centre = R.load_font(self.fonts.paths_bold, max(9, int(side * 0.052)))
            draw.text((cx, cy + side * 0.005), f"{best:02d}h", font=centre, anchor="mm",
                      fill=R.hex_to_rgb(COLORS["text"]))
        return image


# --------------------------------------------------------------------------- #
# Barras, líneas de tiempo y mapas
# --------------------------------------------------------------------------- #


class ProgressBar(PILCanvas):
    def __init__(self, master, animator, background, color=None, track=None,
                 height=6, **kwargs):
        super().__init__(master, background, height=height, **kwargs)
        self.animator = animator
        self.color = color or COLORS["accent"]
        self.track = track or COLORS["surface2"]
        self.bar_height = height
        self._fraction = 0.0

    def set_fraction(self, value, animate=True, duration=0.45):
        value = max(0.0, min(1.0, float(value)))
        if abs(value - self._fraction) < 1e-4:
            return
        if not animate:
            self._fraction = value
            self.schedule_redraw()
            return

        def update(v):
            self._fraction = v
            self.redraw()

        self.animator.to(("bar", id(self)), self._fraction, value, duration=duration,
                         easing="out_cubic", on_update=update)

    def set_color(self, color, animate=True):
        if color == self.color:
            return
        if not animate:
            self.color = color
            self.schedule_redraw()
            return

        def update(value):
            self.color = value
            self.redraw()

        self.animator.color(("barc", id(self)), self.color, color, duration=0.3,
                            on_update=update)

    def render(self, width, height):
        bar_h = min(self.bar_height, height)
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        spans = [(0.0, self._fraction, self.color)] if self._fraction > 0 else []
        image.paste(R.timeline(width, bar_h, spans, self.background, self.track),
                    (0, (height - bar_h) // 2))
        return image


class TimelineBar(PILCanvas):
    """Cuándo, dentro de la sesión, hubo cada cosa."""

    def __init__(self, master, background, height=14, **kwargs):
        super().__init__(master, background, height=height, **kwargs)
        self.bar_height = height
        self.spans = []
        self.duration = 0.0

    def set_spans(self, spans, duration=None):
        self.spans = list(spans)
        self.duration = duration or (max((s[1] for s in spans), default=0.0))
        self.schedule_redraw()

    def render(self, width, height):
        bar_h = min(self.bar_height, height)
        top = (height - bar_h) // 2
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        total = self.duration or 1e-6
        normalized = []
        for start, end, kind in self.spans:
            a, b = min(1.0, start / total), min(1.0, end / total)
            if b > a:
                shown = DISPLAY_KIND.get(kind, "other")
                normalized.append((a, b, DATA.get(shown, COLORS["surface3"])))
        image.paste(R.timeline(width, bar_h, normalized, self.background,
                               COLORS["surface2"]), (0, top))
        return image


class BarsView(PILCanvas):
    def __init__(self, master, background, fonts, color=None, height=150,
                 empty_text="Sin datos en el período", **kwargs):
        super().__init__(master, background, height=height, **kwargs)
        self.fonts = fonts
        self.color = color or COLORS["accent"]
        self.values = []
        self.labels = []
        self.empty_text = empty_text

    def set_data(self, values, labels=None):
        self.values = list(values)
        self.labels = list(labels or [])
        self.schedule_redraw()

    def render(self, width, height):
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        draw = ImageDraw.Draw(image)
        if not self.values or max(self.values) <= 0:
            font = R.load_font(self.fonts.paths, max(10, int(12 * scaling_of(self))))
            draw.text((width / 2, height / 2), self.empty_text, font=font, anchor="mm",
                      fill=R.hex_to_rgb(COLORS["text_faint"]))
            return image

        label_h = 18 if self.labels else 0
        peak = max(range(len(self.values)), key=lambda i: self.values[i])
        image.paste(
            R.bar_chart(width, max(8, height - label_h), self.values, self.background,
                        R.mix(self.color, COLORS["surface"], 0.45),
                        highlight_color=self.color, highlight_index=peak,
                        baseline_color=COLORS["border_soft"]),
            (0, 0))

        if self.labels:
            font = R.load_font(self.fonts.paths, max(9, int(10 * scaling_of(self))))
            slot = width / len(self.labels)
            for index, label in enumerate(self.labels):
                if not str(label):
                    continue
                box = draw.textbbox((0, 0), str(label), font=font)
                half = (box[2] - box[0]) / 2 + 2
                x = min(max(slot * (index + 0.5), half), width - half)
                color = COLORS["text"] if index == peak else COLORS["text_dim"]
                draw.text((x, height - label_h / 2 - 1), str(label), font=font,
                          anchor="mm", fill=R.hex_to_rgb(color))
        return image


class Heatmap(PILCanvas):
    """Mapa anual de concentración, estilo mapa de contribuciones."""

    CELL = 13
    GAP = 3
    LEFT = 26
    TOP = 16

    def __init__(self, master, background, fonts, on_select=None, **kwargs):
        super().__init__(master, background, **kwargs)
        self.fonts = fonts
        self.on_select = on_select
        self.cells = {}
        self.columns = 26
        self.month_labels = []
        self.origin = date.today()
        self._hover = None
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click, add="+")
        self.bind("<Configure>", lambda _e: self._fit_cells(), add="+")

    def set_data(self, cells, columns, month_labels, origin):
        self.cells, self.columns = cells, columns
        self.month_labels, self.origin = month_labels, origin
        self._fit_cells()
        self.schedule_redraw()

    def _fit_cells(self):
        """Estira las celdas para ocupar el ancho disponible."""
        width = self.winfo_width()
        if width > 1 and self.columns:
            available = width - self.LEFT - 8
            self.CELL = int(max(10, min(30, available / self.columns - self.GAP)))
        self.configure(height=self.TOP + 7 * (self.CELL + self.GAP) + 6)

    def weeks_that_fit(self, min_cell=15, maximum=53):
        """Cuántas semanas entran cómodas en el ancho actual."""
        width = self.winfo_width()
        if width <= 1:
            return 26
        return max(12, min(maximum, int((width - self.LEFT - 8) // (min_cell + self.GAP))))

    def _cell_at(self, x, y):
        column = int((x - self.LEFT) // (self.CELL + self.GAP))
        row = int((y - self.TOP) // (self.CELL + self.GAP))
        if 0 <= row < 7 and 0 <= column < self.columns and (column, row) in self.cells:
            return column, row
        return None

    def date_of(self, column, row):
        return self.origin + timedelta(days=column * 7 + row)

    def _on_motion(self, event):
        cell = self._cell_at(event.x, event.y)
        if cell != self._hover:
            self._hover = cell
            self.configure(cursor="hand2" if cell else "")
            self.redraw()

    def _on_leave(self, _e=None):
        if self._hover:
            self._hover = None
            self.redraw()

    def _on_click(self, event):
        cell = self._cell_at(event.x, event.y)
        if cell and self.on_select:
            self.on_select(self.date_of(*cell))

    def render(self, width, height):
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        if not self.cells:
            return image

        grid = R.heatmap(self.columns, 7, self.cells, self.background,
                         COLORS["surface2"], HEAT_RAMP, cell=self.CELL,
                         gap=self.GAP, radius=3)
        image.paste(grid, (self.LEFT, self.TOP))

        draw = ImageDraw.Draw(image)
        font = R.load_font(self.fonts.paths, max(8, int(9 * scaling_of(self))))
        for row, label in ((0, "L"), (2, "M"), (4, "V")):
            draw.text((self.LEFT - 8, self.TOP + row * (self.CELL + self.GAP) + self.CELL / 2),
                      label, font=font, anchor="rm", fill=R.hex_to_rgb(COLORS["text_faint"]))
        for column, label in self.month_labels:
            x = self.LEFT + column * (self.CELL + self.GAP)
            if x < width - 20:
                draw.text((x, self.TOP - 6), label, font=font, anchor="ls",
                          fill=R.hex_to_rgb(COLORS["text_dim"]))

        if self._hover:
            column, row = self._hover
            x = self.LEFT + column * (self.CELL + self.GAP)
            y = self.TOP + row * (self.CELL + self.GAP)
            draw.rounded_rectangle((x - 1, y - 1, x + self.CELL, y + self.CELL),
                                   radius=4, outline=R.hex_to_rgb(COLORS["text"]), width=1)
        return image

    def tooltip_for(self, cell):
        if not cell:
            return ""
        day = self.date_of(*cell)
        seconds = self.cells.get(cell, 0.0)
        if seconds <= 0:
            return f"{day.strftime('%d/%m/%Y')} · sin sesiones"
        return f"{day.strftime('%d/%m/%Y')} · {fmt_short(seconds)} concentrado"


# --------------------------------------------------------------------------- #
# Tarjetas y piezas de composición
# --------------------------------------------------------------------------- #


class Card(ctk.CTkFrame):
    def __init__(self, master, fill=None, radius=None, **kwargs):
        kwargs.setdefault("fg_color", fill or COLORS["surface"])
        kwargs.setdefault("corner_radius", radius or RADIUS["lg"])
        super().__init__(master, **kwargs)


def card_title(parent, fonts, text, side_widget=None, pady=None):
    header = ctk.CTkFrame(parent, fg_color="transparent")
    header.pack(fill="x", padx=SPACE["xl"], pady=pady or (SPACE["lg"], SPACE["sm"]))
    ctk.CTkLabel(header, text=text, font=fonts["section"],
                 text_color=COLORS["text"]).pack(side="left")
    return header


class StatTile(ctk.CTkFrame):
    """Métrica con etiqueta chica y valor grande animado."""

    def __init__(self, master, animator, fonts, label, color=None, fill=None,
                 formatter=None, **kwargs):
        kwargs.setdefault("fg_color", fill or COLORS["surface2"])
        kwargs.setdefault("corner_radius", RADIUS["sm"])
        super().__init__(master, **kwargs)
        self.animator = animator
        self.formatter = formatter or (lambda v: f"{v:.0f}")
        self._value = 0.0

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=SPACE["md"], pady=(SPACE["sm"] + 2, 0))
        if color:
            Dot(header, kwargs["fg_color"], color, size=8).pack(side="left", pady=(1, 0))
        ctk.CTkLabel(header, text=label, font=fonts["tiny"],
                     text_color=COLORS["text_dim"]).pack(
            side="left", padx=(SPACE["xs"] + 2 if color else 0, 0))

        self.value_label = ctk.CTkLabel(self, text=self.formatter(0),
                                        font=fonts["metric_sm"],
                                        text_color=COLORS["text"], anchor="w")
        self.value_label.pack(anchor="w", padx=SPACE["md"], pady=(0, SPACE["sm"] + 2))

    def set_value(self, value, animate=True):
        value = float(value)
        if abs(value - self._value) < 1e-6:
            return
        if not animate:
            self._value = value
            self.value_label.configure(text=self.formatter(value))
            return

        def update(v):
            self._value = v
            try:
                if self.winfo_exists():
                    self.value_label.configure(text=self.formatter(v))
            except Exception:
                pass

        self.animator.to(("tile", id(self)), self._value, value, duration=0.55,
                         easing="out_cubic", on_update=update)


class Legend(ctk.CTkFrame):
    def __init__(self, master, fonts, keys=("focus", "other"),
                 background=None, orientation="vertical", **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        bg = background or COLORS["surface"]
        self.rows = {}
        for key in keys:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(side="left" if orientation == "horizontal" else "top", anchor="w",
                     padx=(0, SPACE["lg"]) if orientation == "horizontal" else 0,
                     pady=0 if orientation == "horizontal" else 3)
            Dot(row, bg, DATA[key], size=9).pack(side="left", pady=(2, 0))
            ctk.CTkLabel(row, text=DATA_LABELS[key], font=fonts["tiny"],
                         text_color=COLORS["text_muted"]).pack(side="left",
                                                               padx=(SPACE["xs"] + 2, 0))
            value = ctk.CTkLabel(row, text="0%", font=fonts["tiny_bold"],
                                 text_color=COLORS["text"])
            value.pack(side="left", padx=(SPACE["xs"], 0))
            self.rows[key] = value

    def set_values(self, values):
        for key, label in self.rows.items():
            label.configure(text=values.get(key, "0%"))


class Chip(PILCanvas):
    def __init__(self, master, animator, background, fonts, text="", color=None,
                 text_color=None, height=26, pad_x=14, **kwargs):
        self.animator = animator
        self.fonts = fonts
        self.text = text
        self.color = color or COLORS["surface3"]
        self.text_color = text_color or COLORS["text"]
        self.pad_x = pad_x
        super().__init__(master, background, height=height, **kwargs)

    def set_state(self, text, color, text_color=None, animate=True):
        self.text = text
        self.text_color = text_color or R.readable_on(color, dark=COLORS["app"])
        if not animate:
            self.color = color
            self.schedule_redraw()
            return

        def update(value):
            self.color = value
            self.redraw()

        self.animator.color(("chip", id(self)), self.color, color, duration=0.34,
                            easing="out_cubic", on_update=update)

    def measure(self):
        font = R.load_font(self.fonts.paths_bold, max(10, int(12 * scaling_of(self))))
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        box = draw.textbbox((0, 0), self.text, font=font)
        return int(box[2] - box[0]) + self.pad_x * 2

    def render(self, width, height):
        font = R.load_font(self.fonts.paths_bold, max(10, int(12 * scaling_of(self))))
        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        chip_w = min(width, self.measure())
        image.paste(R.rounded_panel(chip_w, height, height / 2, self.background,
                                    self.color), (0, 0))
        ImageDraw.Draw(image).text((chip_w / 2, height / 2), self.text, font=font,
                                   anchor="mm", fill=R.hex_to_rgb(self.text_color))
        return image


class SegmentedControl(PILCanvas):
    """Selector de opciones con píldora deslizante."""

    def __init__(self, master, animator, background, fonts, items, command=None,
                 height=32, pad_x=14, stretch=True, active_color=None, **kwargs):
        self.animator = animator
        self.fonts = fonts
        self.items = list(items)
        self.command = command
        self.pad_x = pad_x
        self.stretch = stretch
        self.active_color = active_color or COLORS["accent"]
        self._index = 0
        self._pill = [0.0, 0.0]
        self._hover = -1
        self._metrics = []
        super().__init__(master, background, height=height, **kwargs)
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click, add="+")
        self.configure(cursor="hand2")

    def _compute(self, width):
        font = R.load_font(self.fonts.paths_bold, max(10, int(12 * scaling_of(self))))
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        widths = [draw.textbbox((0, 0), label, font=font)[2] + self.pad_x * 2
                  for label in self.items]
        if self.stretch and width > 1:
            widths = [width / len(widths)] * len(widths)
            start = 0.0
        else:
            start = max(0.0, (width - sum(widths)) / 2)
        spans, cursor = [], start
        for w in widths:
            spans.append((cursor, w))
            cursor += w
        return font, spans

    def measure_width(self):
        _, spans = self._compute(0)
        return int(sum(w for _, w in spans)) + 6

    def _hit(self, x):
        for index, (x0, w) in enumerate(self._metrics):
            if x0 <= x <= x0 + w:
                return index
        return -1

    def _on_motion(self, event):
        index = self._hit(event.x)
        if index != self._hover:
            self._hover = index
            self.redraw()

    def _on_leave(self, _e=None):
        if self._hover != -1:
            self._hover = -1
            self.redraw()

    def _on_click(self, event):
        index = self._hit(event.x)
        if index >= 0 and self.command:
            self.command(self.items[index])

    def get(self):
        return self.items[self._index]

    def select(self, name, animate=True):
        if name not in self.items:
            return
        index = self.items.index(name)
        same = index == self._index
        self._index = index
        if not self._metrics:
            self.schedule_redraw()
            return
        target = list(self._metrics[index])
        if not animate or same or self._pill[1] <= 0:
            self._pill = target
            self.redraw()
            return

        def update(values):
            self._pill = values
            self.redraw()

        self.animator.sequence(("seg", id(self)), (list(self._pill), target),
                               duration=0.3, easing="out_quint", on_update=update)

    def render(self, width, height):
        font, spans = self._compute(width)
        self._metrics = spans
        if spans and not self.animator.is_running(("seg", id(self))):
            self._pill = list(spans[self._index])

        image = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
        if spans:
            x0 = int(spans[0][0])
            x1 = int(spans[-1][0] + spans[-1][1])
            image.paste(R.rounded_panel(max(1, x1 - x0), height, height / 2,
                                        self.background, COLORS["surface2"]), (x0, 0))
        pill_w = int(round(self._pill[1]))
        if pill_w > 2:
            image.paste(R.rounded_panel(pill_w, height, height / 2, COLORS["surface2"],
                                        self.active_color),
                        (int(round(self._pill[0])), 0))

        draw = ImageDraw.Draw(image)
        for index, (label, (x0, w)) in enumerate(zip(self.items, spans)):
            if index == self._index:
                color = R.readable_on(self.active_color, dark=COLORS["app"])
            elif index == self._hover:
                color = COLORS["text"]
            else:
                color = COLORS["text_dim"]
            draw.text((x0 + w / 2, height / 2), label, font=font, anchor="mm",
                      fill=R.hex_to_rgb(color))
        return image


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


# --------------------------------------------------------------------------- #
# Avisos
# --------------------------------------------------------------------------- #


class SpeakerButton(PILCanvas):
    """Parlante que se tacha al silenciar. Click para alternar."""

    def __init__(self, master, background, command=None, size=22, **kwargs):
        super().__init__(master, background, width=size, height=size, **kwargs)
        self.size = size
        self.command = command
        self.muted = False
        self._hover = False
        self.bind("<Button-1>", lambda _e: self.command and self.command(), add="+")
        self.bind("<Enter>", lambda _e: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda _e: self._set_hover(False), add="+")
        self.configure(cursor="hand2")

    def _set_hover(self, value):
        if value != self._hover:
            self._hover = value
            self.schedule_redraw()

    def set_muted(self, muted):
        muted = bool(muted)
        if muted != self.muted:
            self.muted = muted
            self.schedule_redraw()

    def render(self, width, height):
        side = min(width, height)
        if self.muted:
            color = COLORS["text"] if self._hover else COLORS["text_faint"]
        else:
            color = COLORS["text"] if self._hover else COLORS["text_muted"]
        icon = R.speaker_icon(side, color, self.background, self.muted)
        if (width, height) != (side, side):
            canvas = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
            canvas.paste(icon, ((width - side) // 2, (height - side) // 2))
            return canvas
        return icon


class VolumeControl(ctk.CTkFrame):
    """Barra de volumen con parlante, para la barra lateral.

    El parlante silencia y devuelve el volumen que había antes, que es lo que
    uno espera: silenciar no debería hacerte perder el nivel que ya elegiste.
    """

    def __init__(self, master, fonts, settings, on_change, background=None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.fonts = fonts
        self.settings = settings
        self.on_change = on_change
        self.background = background or COLORS["sidebar"]

        ctk.CTkLabel(self, text="Sonido de la app", font=fonts["tiny"],
                     text_color=COLORS["text_dim"], anchor="w").pack(
            anchor="w", pady=(0, SPACE["xs"]))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")

        self.speaker = SpeakerButton(row, self.background, command=self.toggle_mute)
        self.speaker.pack(side="left", padx=(0, SPACE["sm"]))

        # `width=1`: sin esto el deslizador pide 200 px y arrastra el ancho de
        # toda la barra lateral. Se estira solo con el `pack(expand=True)`.
        self.slider = ctk.CTkSlider(
            row, from_=0, to=100, number_of_steps=100, command=self._on_slide,
            fg_color=COLORS["surface2"], progress_color=COLORS["accent"],
            button_color=COLORS["text"], button_hover_color=COLORS["accent_hover"],
            height=14, button_length=0, width=1)
        self.slider.pack(side="left", fill="x", expand=True)

        self.refresh()

    # -- estado ------------------------------------------------------------ #

    @property
    def _muted(self):
        return bool(self.settings["muted"]) or int(self.settings["volume"]) <= 0

    def refresh(self):
        self.slider.set(int(self.settings["volume"]))
        self.speaker.set_muted(self._muted)
        self.slider.configure(
            progress_color=COLORS["surface3"] if self._muted else COLORS["accent"])

    def _apply(self, volume, muted):
        self.settings.update(volume=int(volume), muted=bool(muted))
        self.refresh()
        self.on_change()

    def _on_slide(self, value):
        volume = int(round(float(value)))
        if volume > 0:
            # Mover la barra hacia arriba saca del silencio y pasa a ser el
            # nivel que se recuerda.
            self.settings["volume_before_mute"] = volume
            self._apply(volume, False)
        else:
            self._apply(0, True)

    def toggle_mute(self):
        if self._muted:
            previous = int(self.settings["volume_before_mute"]) or 70
            self._apply(max(1, previous), False)
        else:
            self.settings["volume_before_mute"] = int(self.settings["volume"])
            self._apply(0, True)


class ToastManager:
    """Avisos apilados abajo a la derecha, con acción opcional.

    Se dibujan enteros con PIL sobre un lienzo, no con widgets de customtkinter.
    El motivo es el recorte de las esquinas: la ventana usa un color clave que
    Windows vuelve transparente, y customtkinter suaviza sus esquinas mezclando
    con el fondo, lo que dejaba un hilo magenta alrededor de la tarjeta. Con el
    dibujo propio el corte es duro y no queda ningún resto.
    """

    PAD = 14
    STRIPE = 4
    LINE = 18
    MAX_TEXT = 300

    def __init__(self, root, animator, fonts):
        self.root = root
        self.animator = animator
        self.fonts = fonts
        self.active = []

    def _wrap(self, draw, text, font, max_width):
        lines, current = [], ""
        for word in text.split():
            probe = f"{current} {word}".strip()
            if draw.textlength(probe, font=font) <= max_width or not current:
                current = probe
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:3]

    def show(self, message, tone="accent", duration=2800, action=None, action_text=""):
        color = COLORS.get(tone, COLORS["accent"])
        font = R.load_font(self.fonts.paths, 12)
        action_font = R.load_font(self.fonts.paths_bold, 12)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

        lines = self._wrap(probe, message, font, self.MAX_TEXT)
        text_width = int(max(probe.textlength(line, font=font) for line in lines))
        action_width = 0
        if action is not None:
            action_width = int(probe.textlength(action_text or "Sí",
                                                font=action_font)) + 28
            duration = max(duration, 9000)

        width = (self.PAD + self.STRIPE + 10 + text_width + self.PAD
                 + (action_width + 10 if action_width else 0))
        height = max(46, len(lines) * self.LINE + self.PAD * 2)

        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        try:
            toast.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        shaped = True
        try:
            toast.attributes("-transparentcolor", R.TRANSPARENT_KEY)
            toast.configure(bg=R.TRANSPARENT_KEY)
        except tk.TclError:
            shaped = False
            toast.configure(bg=COLORS["overlay"])

        canvas = tk.Canvas(toast, width=width, height=height, highlightthickness=0,
                           bd=0, bg=R.TRANSPARENT_KEY if shaped else COLORS["overlay"])
        canvas.pack()

        if shaped:
            image = R.shaped_panel(width, height, RADIUS["sm"], COLORS["surface2"],
                                   border=COLORS["border"], border_width=1.6)
        else:
            image = R.rounded_panel(width, height, RADIUS["sm"], COLORS["overlay"],
                                    COLORS["surface2"], border=COLORS["border"])

        stripe = R.rounded_panel(self.STRIPE, height - 22, 2, COLORS["surface2"], color)
        image.paste(stripe, (self.PAD, 11))

        draw = ImageDraw.Draw(image)
        text_x = self.PAD + self.STRIPE + 10
        top = (height - len(lines) * self.LINE) / 2
        for index, line in enumerate(lines):
            draw.text((text_x, top + index * self.LINE + self.LINE / 2), line,
                      font=font, anchor="lm", fill=R.hex_to_rgb(COLORS["text"]))

        action_box = None
        if action is not None:
            box_w, box_h = action_width, 28
            box_x = width - self.PAD - box_w
            box_y = (height - box_h) // 2
            chip = R.rounded_panel(box_w, box_h, RADIUS["xs"], COLORS["surface2"], color)
            image.paste(chip, (box_x, box_y))
            draw.text((box_x + box_w / 2, box_y + box_h / 2), action_text or "Sí",
                      font=action_font, anchor="mm",
                      fill=R.hex_to_rgb(R.readable_on(color, dark=COLORS["app"])))
            action_box = (box_x, box_y, box_x + box_w, box_y + box_h)

        photo = ImageTk.PhotoImage(image)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo   # que no lo junte el recolector

        def dismiss(_event=None):
            def fade_out(value):
                try:
                    toast.attributes("-alpha", value)
                except tk.TclError:
                    pass

            def destroy():
                try:
                    toast.destroy()
                except tk.TclError:
                    pass
                if toast in self.active:
                    self.active.remove(toast)

            self.animator.to(("toast_out", id(toast)), 1.0, 0.0, duration=0.22,
                             easing="out_cubic", on_update=fade_out, on_done=destroy)

        if action_box is not None:
            def on_click(event):
                x0, y0, x1, y1 = action_box
                if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                    action()
                    dismiss()

            canvas.bind("<Button-1>", on_click)
            canvas.bind("<Motion>", lambda e: canvas.configure(
                cursor="hand2" if action_box[0] <= e.x <= action_box[2]
                and action_box[1] <= e.y <= action_box[3] else ""))

        index = len(self.active)
        x = self.root.winfo_rootx() + self.root.winfo_width() - width - 26
        y = (self.root.winfo_rooty() + self.root.winfo_height() - height - 26
             - index * (height + 10))
        toast.geometry(f"{width}x{height}+{x}+{y + 14}")
        self.active.append(toast)

        def fade_in(value):
            try:
                toast.attributes("-alpha", value)
                toast.geometry(f"{width}x{height}+{x}+{int(y + 14 * (1 - value))}")
            except tk.TclError:
                pass

        self.animator.to(("toast_in", id(toast)), 0.0, 1.0, duration=0.26,
                         easing="out_cubic", on_update=fade_in)
        self.root.after(duration, dismiss)


# --------------------------------------------------------------------------- #
# Sugerencias de hashtag
# --------------------------------------------------------------------------- #


class HashtagPopup:
    WIDTH = 230
    ROW = 30
    MAX_ROWS = 5

    def __init__(self, root, animator, fonts, provider):
        self.root = root
        self.animator = animator
        self.fonts = fonts
        self.provider = provider
        self.toplevel = None
        self.canvas = None
        self.photo = None
        self.suggestions = []
        self.index = 0
        self.offset = 0
        self.textbox = None
        self.visible = False

    def attach(self, textbox):
        textbox.bind("<KeyRelease>", lambda e: self._on_key(e, textbox), add="+")
        textbox.bind("<FocusOut>", lambda _e: self.root.after(140, self.hide), add="+")
        textbox.bind("<Escape>", lambda _e: self.hide(), add="+")
        textbox.bind("<Down>", lambda _e: self._nav(1), add="+")
        textbox.bind("<Up>", lambda _e: self._nav(-1), add="+")
        textbox.bind("<Tab>", lambda _e: self._accept(), add="+")
        textbox.bind("<Return>", lambda _e: self._accept(), add="+")

    def _nav(self, delta):
        if not self.visible:
            return None
        self.move(delta)
        return "break"

    def _accept(self):
        if not self.visible or not self.suggestions:
            return None
        self._insert(self.suggestions[self.index])
        return "break"

    def _on_key(self, event, textbox):
        import re

        if event.keysym in ("Escape", "Return", "Tab", "Up", "Down"):
            return
        try:
            typed = textbox.get(textbox.index("insert linestart"), textbox.index("insert"))
        except tk.TclError:
            return
        match = re.search(r"#([\wÀ-ɏ-]*)$", typed, re.UNICODE)
        if match is None:
            self.hide()
            return
        suggestions = self.provider(match.group(1))
        if not suggestions:
            self.hide()
            return
        try:
            box = textbox.bbox("insert")
        except tk.TclError:
            box = None
        if not box:
            self.hide()
            return
        self.show(textbox, textbox.winfo_rootx() + box[0],
                  textbox.winfo_rooty() + box[1] + box[3] + 6, suggestions)

    def _ensure(self):
        if self.toplevel is not None and self.toplevel.winfo_exists():
            return
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=COLORS["pink"])
        canvas = tk.Canvas(top, highlightthickness=0, bd=0, bg=COLORS["pink"])
        canvas.pack()
        canvas.bind("<Button-1>", self._on_click)
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Motion>", self._on_motion)
        self.toplevel, self.canvas = top, canvas

    def _rows(self):
        return min(self.MAX_ROWS, len(self.suggestions))

    def _height(self):
        return self._rows() * self.ROW + 12

    def show(self, textbox, x, y, suggestions):
        self.textbox = textbox
        if suggestions != self.suggestions:
            self.suggestions = suggestions
            self.index = self.offset = 0
        self._ensure()
        height = self._height()
        self.canvas.configure(width=self.WIDTH, height=height)
        self._render()
        self.toplevel.geometry(f"{self.WIDTH}x{height}+{int(x)}+{int(y)}")
        if not self.visible:
            self.visible = True
            try:
                self.toplevel.deiconify()
                self.toplevel.attributes("-alpha", 0.0)
            except tk.TclError:
                pass

            def fade(value):
                try:
                    self.toplevel.attributes("-alpha", value)
                except tk.TclError:
                    pass

            self.animator.to(("tagpop", id(self)), 0.0, 1.0, duration=0.14,
                             easing="out_cubic", on_update=fade)

    def hide(self):
        self.visible = False
        if self.toplevel is not None and self.toplevel.winfo_exists():
            try:
                self.toplevel.withdraw()
            except tk.TclError:
                pass

    def move(self, delta):
        if not self.suggestions:
            return
        self.index = max(0, min(len(self.suggestions) - 1, self.index + delta))
        if self.index < self.offset:
            self.offset = self.index
        elif self.index >= self.offset + self._rows():
            self.offset = self.index - self._rows() + 1
        self._render()

    def _slot(self, y):
        slot = int((y - 6) // self.ROW)
        return slot if 0 <= slot < self._rows() else None

    def _on_motion(self, event):
        slot = self._slot(event.y)
        if slot is not None and self.offset + slot != self.index:
            self.index = self.offset + slot
            self._render()

    def _on_click(self, event):
        slot = self._slot(event.y)
        if slot is not None:
            self._insert(self.suggestions[self.offset + slot])

    def _on_wheel(self, event):
        self.move(-1 if event.delta > 0 else 1)
        return "break"

    def _insert(self, tag):
        import re

        box = self.textbox
        if box is None or not box.winfo_exists():
            return
        try:
            here = box.index("insert")
            typed = box.get(box.index("insert linestart"), here)
        except tk.TclError:
            return
        match = re.search(r"#([\wÀ-ɏ-]*)$", typed, re.UNICODE)
        if match is None:
            return
        try:
            box.delete(f"{here} - {len(match.group(1))} chars", here)
            box.insert("insert", tag + " ")
        except tk.TclError:
            return
        self.hide()

    def _render(self):
        if self.canvas is None:
            return
        height = self._height()
        image = R.rounded_panel(self.WIDTH, height, 12, COLORS["pink"], COLORS["pink"])
        draw = ImageDraw.Draw(image)
        font = R.load_font(self.fonts.paths, 13)
        font_bold = R.load_font(self.fonts.paths_bold, 13)

        for slot in range(self._rows()):
            position = self.offset + slot
            if position >= len(self.suggestions):
                break
            y = 6 + slot * self.ROW
            selected = position == self.index
            if selected:
                image.paste(R.rounded_panel(self.WIDTH - 12, self.ROW - 4, 8,
                                            COLORS["pink"],
                                            R.darken(COLORS["pink"], 0.1)), (6, y + 2))
            draw.text((16, y + self.ROW / 2), f"#{self.suggestions[position]}",
                      font=font_bold if selected else font, anchor="lm",
                      fill=R.hex_to_rgb(COLORS["pink_text"]))

        if len(self.suggestions) > self._rows():
            draw.text((self.WIDTH - 14, height - 8),
                      f"{self.index + 1}/{len(self.suggestions)}", font=font, anchor="rs",
                      fill=R.hex_to_rgb(R.mix(COLORS["pink_text"], COLORS["pink"], 0.45)))

        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
