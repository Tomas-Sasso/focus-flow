"""Navegación: la barra lateral y el selector segmentado."""

from __future__ import annotations

from PIL import Image, ImageDraw

from .. import render as R
from ..theme import COLORS, RADIUS
from ..icons import paste_icon
from ._base import PILCanvas, scaling_of

# Cada sección con su ícono de icons.py (estilo SF Symbols).
_SYMBOLS = {"Enfoque": "timer", "Historial": "calendar",
            "Análisis": "chart", "Ajustes": "gear"}

__all__ = [
    "NavRail", "SegmentedControl",
]


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

        # --- indicador activo: una cápsula, como la barra lateral de macOS 27 ---
        y = self.TOP + self._marker * self.ROW
        pill_h = self.ROW - 6
        panel = R.rounded_panel(width - 16, pill_h, pill_h // 2,
                                self.background, COLORS["surface3"])
        image.paste(panel, (8, int(round(y + 3))))

        draw = ImageDraw.Draw(image)
        regular = R.load_font(self.fonts.paths, max(11, int(13 * scale)))
        icon_size = 17 * scale
        for index, name in enumerate(self.items):
            row_y = self.TOP + index * self.ROW
            active = index == self._index
            if active:
                color = COLORS["text"]
            elif index == self._hover:
                color = COLORS["text_muted"]
            else:
                color = COLORS["text_dim"]
            # Íconos siempre en acento, como en la barra lateral de Apple; el
            # estado lo cuentan la cápsula y el peso del texto.
            symbol = _SYMBOLS.get(name)
            if symbol is not None:
                paste_icon(image, symbol, (34, row_y + self.ROW / 2), icon_size,
                           COLORS["accent"], anchor="mm")
            else:
                _draw_icon(draw, name, 34, row_y + self.ROW / 2, 15, color)
            draw.text((56, row_y + self.ROW / 2), name, font=font if active else regular,
                      anchor="lm", fill=R.hex_to_rgb(color))
        return image


# --------------------------------------------------------------------------- #
# Selector segmentado
# --------------------------------------------------------------------------- #


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
