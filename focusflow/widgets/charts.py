"""Gráficos: anillos, barras, líneas de tiempo y el mapa del año."""

from __future__ import annotations

from datetime import date, timedelta

from PIL import Image, ImageDraw

from .. import render as R
from ..theme import COLORS, DATA, DISPLAY_KIND, HEAT_RAMP
from ._base import PILCanvas, fmt_short, scaling_of

__all__ = [
    "DonutChart", "MiniDonut", "GoalRing", "RadialHours", "ProgressBar", "TimelineBar",
    "BarsView", "Heatmap",
]


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
