"""Superficies: tarjetas, títulos de tarjeta, métricas, leyendas y chips."""

from __future__ import annotations

import customtkinter as ctk
from PIL import Image, ImageDraw

from .. import render as R
from ..theme import COLORS, DATA, DATA_LABELS, RADIUS, SPACE
from ._base import Dot, PILCanvas, scaling_of

__all__ = [
    "Card", "card_title", "StatTile", "Legend", "Chip",
]


# --------------------------------------------------------------------------- #
# Tarjetas y piezas de composición
# --------------------------------------------------------------------------- #


class Card(ctk.CTkFrame):
    def __init__(self, master, fill=None, radius=None, **kwargs):
        kwargs.setdefault("fg_color", fill or COLORS["surface"])
        kwargs.setdefault("corner_radius", radius or RADIUS["lg"])
        # Filo de 1 px apenas más claro que la tarjeta: la separa del fondo como una
        # superficie elevada, sin necesidad de sombra.
        if isinstance(kwargs["fg_color"], str) and kwargs["fg_color"].startswith("#"):
            kwargs.setdefault("border_width", 1)
            kwargs.setdefault("border_color", R.mix(kwargs["fg_color"], "#FFFFFF", 0.07))
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
