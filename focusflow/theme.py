"""Identidad visual de Focus Flow.

Se mantiene el ADN del programa original —el violeta profundo, el celeste, el
ámbar, el menta y el rosa— pero reordenado como sistema: un fondo más oscuro
para que los acentos pesen más, una barra lateral todavía más oscura que da
profundidad, y una categoría de color nueva para el tiempo "ausente".
"""

from __future__ import annotations

import ctypes
import os
import tkinter.font as tkfont

import customtkinter as ctk

from .config import ASSETS_DIR
from .render import mix

COLORS = {
    # --- superficies ---
    "app": "#161238",
    "sidebar": "#1B1646",
    "bg": "#211C52",
    "surface": "#2B255D",
    "surface2": "#332C6A",
    "surface3": "#3D3579",
    "surface4": "#494090",
    "border": "#403896",
    "border_soft": "#332C6A",
    "overlay": "#120F2C",
    # --- texto ---
    "text": "#F6F4FF",
    "text_muted": "#BEB9E6",
    "text_dim": "#8E88C4",
    "text_faint": "#655E9B",
    # --- acentos ---
    "accent": "#7BDFF2",
    "accent_hover": "#95E7F6",
    "accent_press": "#5FC6DA",
    "accent_soft": "#25506B",
    "amber": "#F6C177",
    "amber_hover": "#F9D097",
    "amber_soft": "#4A3C55",
    "mint": "#7BDFA3",
    "mint_hover": "#95E7B6",
    "mint_soft": "#26523F",
    "rose": "#F2A6A6",
    "rose_hover": "#F6BDBD",
    "rose_soft": "#4A3157",
    "pink": "#FBC9D2",
    "pink_text": "#7A2F44",
    "lavender": "#B9A7F0",
    "lavender_soft": "#372F73",
    "cream": "#FBE0BB",
    "cream_text": "#7A5A1F",
    "danger": "#FF5A5A",
    "danger_hover": "#FF7B7B",
    # Naranja y amarillo para el interruptor de la pestaña flotante: tienen que
    # distinguirse entre sí de un vistazo, no ser dos tonos del mismo ámbar.
    "orange": "#F0883E",
    "orange_hover": "#F79A57",
    "yellow": "#F5D061",
    "yellow_hover": "#F8DC85",
}

# En pantalla hay dos categorías y nada más: o estabas concentrado o no. Tener
# cuatro etiquetas distintas (descanso, ausente, distracción) obligaba a leer una
# leyenda entera para entender un gráfico.
DATA = {
    "focus": COLORS["mint"],
    "other": COLORS["rose"],
}

DATA_LABELS = {
    "focus": "Concentración",
    "other": "No concentración",
}

# La base sí guarda el detalle: descanso, pausa corta y distracción siguen siendo
# columnas distintas. Esto sólo decide en qué mitad cae cada tramo al dibujarlo,
# así que el día de mañana se puede volver a abrir sin perder nada de lo medido.
DISPLAY_KIND = {
    "focus": "focus",
    "rest": "other",
    "away": "other",
}

HEAT_RAMP = ["#2A2463", "#2F5E7A", "#3F92AE", "#5FC0DC", "#7BDFF2", "#B9EFFA"]

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 22, "2xl": 30, "3xl": 40}
RADIUS = {"xs": 6, "sm": 10, "md": 14, "lg": 18, "xl": 22, "pill": 999}

# Dos estados a la vista. El motivo (descanso, pausa corta, tolerancia) se cuenta
# en la línea de abajo del reloj, que es donde importa, sin multiplicar etiquetas.
PHASE_STYLE = {
    "idle": ("Sin sesión", COLORS["surface3"], COLORS["text"]),
    "focus": ("Concentración", COLORS["mint"], COLORS["app"]),
    "break": ("No concentración", COLORS["rose"], COLORS["app"]),
    "tolerance": ("No concentración", COLORS["rose"], COLORS["app"]),
    "paused": ("No concentración", COLORS["rose"], COLORS["app"]),
    "away": ("No concentración", COLORS["rose"], COLORS["app"]),
}


def _register_font(path):
    if os.name != "nt":
        return False
    try:
        if ctypes.windll.gdi32.AddFontResourceExW(os.path.abspath(path), 0x10, 0):
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
            return True
    except Exception:
        return False
    return False


FONT_FILES = (
    "SF-Pro-Text-Regular.otf",
    "SF-Pro-Text-Medium.otf",
    "SF-Pro-Text-Semibold.otf",
    "SFUIDisplay-Regular.otf",
)


class Typography:
    """Familias tipográficas resueltas una vez y escala de tamaños."""

    def __init__(self, root):
        for name in FONT_FILES:
            path = os.path.join(ASSETS_DIR, name)
            if os.path.exists(path):
                _register_font(path)
        root.update_idletasks()
        available = set(tkfont.families(root))

        def pick(*candidates):
            for family in candidates:
                if family in available:
                    return family
            return "Segoe UI"

        self.regular = pick("SF Pro Text", "SF Pro Display", "SF UI Display", "Segoe UI")
        self.medium = pick("SF Pro Text Medium", "SF Pro Text", "Segoe UI")
        self.semibold = pick("SF Pro Text Semibold", "SF Pro Text", "Segoe UI")

        self.paths = [
            os.path.join(ASSETS_DIR, "SF-Pro-Text-Regular.otf"),
            os.path.join(ASSETS_DIR, "SFUIDisplay-Regular.otf"),
        ]
        self.paths_bold = [
            os.path.join(ASSETS_DIR, "SF-Pro-Text-Semibold.otf"),
            os.path.join(ASSETS_DIR, "SF-Pro-Text-Medium.otf"),
        ]

        f = ctk.CTkFont
        self.fonts = {
            "clock": f(family=self.semibold, size=76),
            "clock_sm": f(family=self.semibold, size=40),
            "display": f(family=self.semibold, size=34),
            "title": f(family=self.semibold, size=22),
            "section": f(family=self.semibold, size=16),
            "card": f(family=self.semibold, size=13),
            "body": f(family=self.regular, size=13),
            "body_bold": f(family=self.semibold, size=13),
            "small": f(family=self.regular, size=12),
            "small_bold": f(family=self.semibold, size=12),
            "tiny": f(family=self.regular, size=11),
            "tiny_bold": f(family=self.semibold, size=11),
            "micro": f(family=self.regular, size=10),
            "button": f(family=self.medium, size=13),
            "button_lg": f(family=self.medium, size=15),
            "metric": f(family=self.semibold, size=24),
            "metric_sm": f(family=self.semibold, size=17),
            "nav": f(family=self.medium, size=13),
        }

    def __getitem__(self, key):
        return self.fonts[key]


def score_color(percentage):
    """Verde / ámbar / rosa según qué tan buena fue la concentración."""
    if percentage >= 70:
        return COLORS["mint"]
    if percentage >= 45:
        return COLORS["amber"]
    return COLORS["rose"]


def elevate(color, steps=1):
    return mix(color, "#FFFFFF", 0.04 * steps)
