"""Identidad visual de Focus Flow (Liquid Glass 2026).

Se mantiene el ADN del programa original —el violeta profundo, el celeste, el
ámbar, el menta y el rosa— pero reordenado como sistema de dos capas: una capa
funcional de vidrio (barra lateral, controles flotantes, menús, avisos, hojas)
sobre un fondo casi negro con luz ambiente de color, y una capa de contenido de
tarjetas sólidas. El violeta deja de ser una pintura plana y pasa a ser luz que
el vidrio recoge.

Acá viven los tokens (paleta con sus variantes, rellenos, materiales, tarjetas,
radios, espaciado, layout y escala tipográfica) y las cuentas de color que los
consumen: etiquetas "vibrantes" con piso de contraste, rellenos sobre vidrio y
el contraste WCAG con el que se verifica todo.

Tres modos visuales, todos en vivo salvo el contraste alto:
- estándar;
- Reducir transparencia (RT): vidrio sólido, manchas de luz a la mitad;
- Aumentar contraste (AC): paleta propia (`PALETTES["contrast"]`), bordes
  visibles y sin manchas. Cambia los valores de `COLORS` **en el lugar**, así
  que la interfaz se reconstruye para tomarlos.
"""

from __future__ import annotations

import ctypes
import os
import re
import struct
import tkinter
import tkinter.font as tkfont
from dataclasses import dataclass, replace
from functools import lru_cache

import customtkinter as ctk
from PIL import ImageFont

from .config import ASSETS_DIR
from .render import mix, relative_luminance

# --------------------------------------------------------------------------- #
# Paleta
# --------------------------------------------------------------------------- #

# Cada acento con sus cuatro caras: base, hover, presionado y "suave" (el acento
# al 22 % sobre la tarjeta, para rieles y fondos de chips).
_ACCENTS = {
    #            base       hover      presionado suave      AC
    "accent": ("#64D2FF", "#7BD9FF", "#58B9E0", "#22405E", "#8BE0FF"),
    "mint": ("#5FE3A1", "#79E8B2", "#54C88E", "#24474A", "#7CF0BE"),
    "rose": ("#FF8A9E", "#FF9EAF", "#E0798B", "#4B2E4D", "#FFA8B6"),
    "amber": ("#FFC56B", "#FFD08A", "#E0AD5E", "#4A3B3E", "#FFD38A"),
    "lavender": ("#B4A5FF", "#C2B6FF", "#9E91E0", "#3A3466", "#CEC4FF"),
    "danger": ("#FF5A60", "#FF7378", "#E04F54", "#4B2236", "#FF7A80"),
    # Naranja y amarillo para la pestaña flotante: tienen que distinguirse
    # entre sí de un vistazo, no ser dos tonos del mismo ámbar.
    "orange": ("#FF9F45", "#FFB066", "#E08C3D", "#4B3433", "#FFB873"),
    "yellow": ("#FFD84D", "#FFE170", "#E0BE44", "#4A4232", "#FFE27A"),
}

_STANDARD = {
    # --- superficies ---
    "bg_base": "#0C0A1F",          # base del fondo ambiental y barra de título
    "app": "#0C0A1F",              # = bg_base (texto oscuro sobre acentos en TONES)
    "sidebar": "#15122E",          # color sólido equivalente del vidrio lateral
    "bg": "#12102A",               # heredado (diálogos viejos); no usar en código nuevo
    "surface": "#1C1938",          # tarjeta
    "surface_raised": "#252142",   # mosaicos, filas y campos dentro de tarjetas
    "surface_sunken": "#120F28",   # rieles de barras, fondos de gráficos
    "surface2": "#252142",         # = surface_raised (heredada)
    "surface3": "#2F2A50",         # riel del anillo vacío, botones "ghost"
    "surface4": "#3A355E",         # hover de "ghost"
    "separator": "#2F2B4C",        # divisores de 1 px
    "border": "#2F2B4C",           # = separator; en AC es el borde visible de tarjetas
    "border_soft": "#252142",
    "hairline": "#2B2847",
    "overlay": "#08071A",          # velo de las hojas
    "focus_ring": "#64D2FF",       # anillo de foco de teclado (2 px)
    # --- etiquetas sobre superficies sólidas ---
    "label": "#F4F3FA",
    "text": "#F4F3FA",             # = label
    "text_muted": "#C6C4D8",       # secundario fuerte: valores, leyendas
    "label_secondary": "#A9A6BF",
    "text_dim": "#A9A6BF",         # = label_secondary
    "text_faint": "#8E8BA9",       # ayudas y pistas (cumple 4,5:1)
    "label_tertiary": "#7F7C98",   # sólo placeholder, deshabilitado, no esencial
    "label_quaternary": "#4A4766",  # nunca texto: marcas y líneas punteadas
    "on_accent": "#0C0A1F",        # etiqueta sobre rellenos de acento
    "danger_text": "#FF7A7F",      # "Borrar", "Terminar sesión"
    # --- heredadas (los hashtags pasan a lavender) ---
    "pink": "#FFB3C4",
    "pink_text": "#5C1F33",
    "cream": "#FFE2B8",
    "cream_text": "#5C3F12",
}

_CONTRAST = {
    "bg_base": "#05040F",
    "app": "#05040F",
    "sidebar": "#17143A",
    "bg": "#0A0920",
    "surface": "#121027",
    "surface_raised": "#1C1938",
    "surface_sunken": "#05040F",
    "surface2": "#1C1938",
    "surface3": "#2A2648",
    "surface4": "#3A3660",
    "separator": "#6E6A8C",
    "border": "#9A96B8",
    "border_soft": "#6E6A8C",
    "hairline": "#9A96B8",
    "overlay": "#000000",
    "focus_ring": "#FFFFFF",
    "label": "#FFFFFF",
    "text": "#FFFFFF",
    "text_muted": "#E6E4F4",
    "label_secondary": "#DAD8EC",
    "text_dim": "#DAD8EC",
    "text_faint": "#ADA9C8",
    "label_tertiary": "#ADA9C8",
    "label_quaternary": "#6E6A8C",
    "on_accent": "#05040F",
    "danger_text": "#FF9AA0",
    "pink": "#FFB3C4",
    "pink_text": "#5C1F33",
    "cream": "#FFE2B8",
    "cream_text": "#5C3F12",
}

for _name, (_base, _hover, _press, _soft, _hc) in _ACCENTS.items():
    _STANDARD.update({_name: _base, f"{_name}_hover": _hover,
                      f"{_name}_press": _press, f"{_name}_soft": _soft})
    # En AC el spec fija sólo la base; las otras caras salen con las mismas
    # proporciones que en la paleta estándar (hover +15 % de blanco,
    # presionado −12 %, suave = 22 % sobre la tarjeta de AC).
    _CONTRAST.update({_name: _hc, f"{_name}_hover": mix(_hc, "#FFFFFF", 0.15),
                      f"{_name}_press": mix(_hc, "#000000", 0.12),
                      f"{_name}_soft": mix(_CONTRAST["surface"], _hc, 0.22)})

PALETTES = {"standard": _STANDARD, "contrast": _CONTRAST}

#: Lo que cambia Reducir transparencia en la paleta estándar (en AC manda AC).
RT_OVERRIDES = {"sidebar": "#1A1736"}

#: Paleta activa. Se muta en el lugar (`apply_palette`) para que todos los
#: `from ..theme import COLORS` vean el cambio.
COLORS = dict(_STANDARD)

#: Etiqueta sobre el ámbar prominente: el `on_accent` común queda justo; este
#: marrón casi negro da 9,6:1.
ON_TONE = {"amber": "#1F1503"}

# --------------------------------------------------------------------------- #
# Rellenos (blanco con alfa) sobre vidrio y sobre sólidos
# --------------------------------------------------------------------------- #

FILLS = {
    "hover": 0.07,
    "selected": 0.12,
    "pressed": 0.16,
    "control": 0.10,
    "control_hover": 0.14,
    "control_pressed": 0.18,
    "track": 0.16,
    "keycap": 0.12,
}
#: En AC los rellenos se multiplican por esto y llevan un borde de 1 px.
FILLS_HC_FACTOR = 1.8
FILL_BORDER_HC = ("#FFFFFF", 0.55)

# --------------------------------------------------------------------------- #
# Datos y estados
# --------------------------------------------------------------------------- #

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

#: Rampa del mapa de calor (se reemplaza en el lugar con la paleta).
HEAT_RAMP = ["#1E1A40", "#21456A", "#2A6F96", "#3E9CC4", "#64D2FF", "#B8ECFF"]
_HEAT = {
    "standard": ("#1E1A40", "#21456A", "#2A6F96", "#3E9CC4", "#64D2FF", "#B8ECFF"),
    "contrast": ("#2A2648", "#2B5684", "#3A86B8", "#5CB8E4", "#8BE0FF", "#DFF6FF"),
}

# Dos estados a la vista. El motivo (descanso, pausa corta, tolerancia) se cuenta
# en la línea de abajo del reloj, que es donde importa, sin multiplicar etiquetas.
# (etiqueta, color de relleno, color del texto encima)
PHASE_STYLE = {}

#: Rótulo corto y específico de cada estado (insignia del anillo, pestaña).
PHASE_DETAIL = {
    "idle": "Sin sesión",
    "focus": "Concentración",
    "break": "Descanso",
    "tolerance": "Tolerancia",
    "paused": "En pausa",
    "away": "Pausa corta",
}

#: Estado del motor -> fase de la luz ambiente.
PHASE_OF_STATE = {
    "idle": "idle",
    "focus": "focus",
    "break": "other",
    "tolerance": "other",
    "paused": "other",
    "away": "other",
}

#: Fase de luz -> (color de la mancha E, intensidad k).
PHASE_LIGHT = {
    "idle": ("#3B3F99", 0.30),
    "focus": ("#1F9A6E", 0.46),
    "other": ("#A23C66", 0.44),
}

# --------------------------------------------------------------------------- #
# Fondo ambiental
# --------------------------------------------------------------------------- #

#: Manchas A–D: (cx, cy, radio, color, k) en fracciones del ancho y alto.
BACKDROP_BLOBS = [
    (0.06, 0.10, 0.62, "#5B3FD9", 0.60),   # violeta, detrás de la barra lateral
    (0.98, 0.02, 0.46, "#2E7FB8", 0.34),   # celeste, arriba a la derecha
    (0.62, 1.04, 0.58, "#7A3C8F", 0.32),   # magenta, abajo
    (0.20, 0.78, 0.40, "#1E5F73", 0.26),   # verde azulado, tenue
]
#: Mancha E (de fase), detrás del anillo de Enfoque: (cx, cy, radio).
BACKDROP_PHASE_POS = (0.445, 0.42, 0.46)
#: Radio del desenfoque del fondo para el vidrio de la ventana (px).
BACKDROP_BLUR = 28

# --------------------------------------------------------------------------- #
# Espaciado, radios y layout
# --------------------------------------------------------------------------- #

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 20, "2xl": 24, "3xl": 32, "4xl": 40}

# Concentricidad: r_hijo = max(r_padre − margen, 6); cápsula = alto / 2.
RADIUS = {"xs": 6, "sm": 8, "md": 16, "lg": 24, "xl": 26, "pill": 999,
          "card": 24, "group": 16, "session": 20, "sheet": 26, "menu": 14, "tile": 8,
          "control_sm": 8, "keycap": 5}

LAYOUT = {"sidebar_w": 240, "page_margin": 24, "header_h": 52, "header_gap": 18,
          "body_top": 94, "gutter": 20, "card_pad": 16, "toolbar_h": 36,
          "toolbar_gap": 12, "row_h": 44, "min_w": 1120, "min_h": 720,
          "start_w": 1280, "start_h": 820}

# --------------------------------------------------------------------------- #
# Sombras, materiales de vidrio y tarjetas
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ShadowSpec:
    blur: float          # radio de desenfoque en px lógicos (σ = blur / 2)
    alpha: float         # α del negro de la sombra
    dy: float            # desplazamiento vertical
    edge: float          # α del filo oscuro de 1 px exterior (0 = sin filo)


#: Sin sombra ni filo (tarjetas en AC, mosaicos).
NO_SHADOW = ShadowSpec(0.0, 0.0, 0.0, 0.0)

SHADOWS = {
    "card": ShadowSpec(10, 0.30, 3, 0.40),
    "control": ShadowSpec(12, 0.32, 4, 0.32),
    "prominent": ShadowSpec(14, 0.36, 5, 0.32),
    "popover": ShadowSpec(28, 0.45, 12, 0.38),
    "sheet": ShadowSpec(40, 0.50, 16, 0.40),
    # Sólo con ventana con alfa por píxel (FOCUSFLOW_LAYERED=1).
    "hud": ShadowSpec(16, 0.40, 6, 0.40),
}


@dataclass(frozen=True)
class Material:
    name: str
    tint: str
    tint_a: float
    sat: float
    lens_px: float
    lens_amt: float
    rim_top: float
    rim_base: float
    sheen: float
    inner_shadow: float
    edge_dark: float
    shadow: ShadowSpec | None
    blur: float                      # sólo materiales sobre foto (popover, sheet)
    solid: str | None = None         # si no es None: cuerpo sólido (RT/AC), sin muestreo
    border: tuple[str, float] | None = None   # (color, ancho px) en AC


# Valores estándar (DESIGN_SPEC §2.5). El tinte del prominente es el del tono:
# `material("prominent", tone=...)` lo completa.
MATERIALS = {
    "sidebar": Material("sidebar", "#14112C", 0.56, 1.30, 12, 6, 0.42, 0.10, 0.05,
                        0.10, 0.38, None, 0),
    "control": Material("control", "#1C1840", 0.42, 1.45, 10, 7, 0.55, 0.12, 0.06,
                        0.16, 0.32, SHADOWS["control"], 0),
    "prominent": Material("prominent", "#64D2FF", 0.90, 1.20, 10, 7, 0.50, 0.14, 0.08,
                          0.16, 0.32, SHADOWS["prominent"], 0),
    "popover": Material("popover", "#191536", 0.66, 1.30, 14, 9, 0.45, 0.10, 0.05,
                        0.14, 0.38, SHADOWS["popover"], 32),
    "sheet": Material("sheet", "#1A1638", 0.72, 1.25, 16, 10, 0.45, 0.10, 0.04,
                      0.12, 0.40, SHADOWS["sheet"], 32),
    "hud": Material("hud", "#1A1638", 0.88, 1.20, 10, 6, 0.55, 0.12, 0.06,
                    0.12, 0.40, SHADOWS["hud"], 0),
}

#: Variante transparente de Apple. **No se usa en Focus Flow** (todo es regular y
#: nunca se mezclan las dos); queda definida para una pestaña flotante futura con
#: foto real del escritorio. Si la luminancia media del recorte supera 0,5 lleva
#: debajo una capa negra de α `CLEAR_DIM`.
MATERIAL_CLEAR = Material("clear", "#000000", 0.0, 1.10, 10, 8, 0.50, 0.12, 0.05,
                          0.12, 0.30, SHADOWS["control"], 0)
CLEAR_DIM = 0.35

# Cuerpos sólidos con Reducir transparencia, y el de Aumentar contraste.
_RT_SOLID = {"sidebar": "#1A1736", "control": "#24204A", "popover": "#201C42",
             "sheet": "#201C42", "hud": "#1C1840"}
_HC_SOLID = "#17143A"
_HC_BORDER = ("#9795A6", 1.5)
_HC_BORDER_PROMINENT = ("#FFFFFF", 1.5)
#: Tope del α del tinte con el regulador "Transparencia del vidrio".
TINT_CAP = 0.95


@dataclass(frozen=True)
class CardStyle:
    radius: float
    fill_key: str
    border_a: float
    top_light_a: float
    edge_dark: float
    shadow: ShadowSpec
    border_hc: str | None


#: Tarjeta (grupo de formulario = mismo estilo con radius 16). Sigue al modo
#: como COLORS: en AC `apply_palette` la cambia por la variante con borde visible
#: (`border_hc`), sin luz ni sombra. Fuera de AC `border_hc` es None, que es lo
#: que render.card_layer entiende como "sin borde de contraste". Leerla como
#: `theme.CARD_STYLE` (o con `card_style()`), no con `from theme import`.
CARD_STYLE = CardStyle(24, "surface", 0.06, 0.10, 0.40, SHADOWS["card"], None)
#: Mosaico dentro de una tarjeta (concéntrico: 24 − 16).
TILE_STYLE = CardStyle(8, "surface_raised", 0.0, 0.0, 0.0, NO_SHADOW, None)
_CARD_STANDARD, _TILE_STANDARD = CARD_STYLE, TILE_STYLE
_CARD_HC_BORDER, _TILE_HC_BORDER = "#9A96B8", "#6E6A8C"

# --------------------------------------------------------------------------- #
# Tipografía: escala
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TypeRole:
    design: str        # "text" | "display"
    weight: int        # 400, 500, 600, 700
    px: int
    line: int
    tracking: float    # em
    engine: str        # "tk" | "pil"
    upper: bool = False


# px a 96 dpi. "tk" = ítem de texto o widget CTk; "pil" = dibujado en imagen.
# Texto < 20 px que no se anima va por Tk (ClearType); ≥ 20 px, con tracking o
# animado, por PIL. Nada por debajo de 11 px.
TYPE_SCALE = {
    # El reloj del anillo mide round(0,18 · diámetro): ver clock_px(). 79 = 440.
    "clock": TypeRole("display", 600, 79, 84, -0.01, "pil"),
    "clock_sm": TypeRole("display", 600, 22, 26, 0.0, "pil"),
    "large_title": TypeRole("display", 700, 28, 34, 0.0, "pil"),
    "sheet_title": TypeRole("display", 700, 20, 26, 0.0, "pil"),
    "title1": TypeRole("display", 600, 22, 28, 0.0, "pil"),
    "title2": TypeRole("display", 600, 20, 24, 0.0, "pil"),
    "title3": TypeRole("text", 600, 15, 20, -0.005, "tk"),
    "headline": TypeRole("text", 600, 13, 18, 0.0, "tk"),
    "body": TypeRole("text", 400, 13, 18, 0.0, "tk"),
    "control": TypeRole("text", 500, 13, 18, 0.0, "tk"),
    "control_lg": TypeRole("text", 600, 15, 20, -0.005, "tk"),
    "callout": TypeRole("text", 400, 12, 16, 0.0, "tk"),
    "caption": TypeRole("text", 500, 11, 14, 0.01, "tk"),
    "badge": TypeRole("text", 600, 11, 14, 0.06, "pil", upper=True),
}

# Claves heredadas de `fonts[...]` -> (rol, peso distinto del rol o None).
_LEGACY_FONTS = {
    "title": ("title1", None),
    "section": ("title3", None),
    "card": ("headline", None),
    "body": ("body", None),
    "body_bold": ("headline", None),
    "small": ("callout", None),
    "small_bold": ("callout", 600),
    "tiny": ("caption", 400),
    "tiny_bold": ("caption", 600),
    "micro": ("caption", None),
    "button": ("control", None),
    "button_lg": ("control_lg", None),
    "metric": ("title1", None),
    "metric_sm": ("title2", None),
    "clock": ("clock", None),
    "clock_sm": ("clock_sm", None),
    "display": ("large_title", None),
    "nav": ("control", None),
}


def clock_px(diameter):
    """Tamaño del reloj del anillo: round(0,18 · D) (440 -> 79)."""
    return max(11, round(0.18 * diameter))


# --------------------------------------------------------------------------- #
# Modo visual vigente
# --------------------------------------------------------------------------- #

_APPEARANCE = {"reduce_transparency": False, "increase_contrast": False, "glass_tint": 50}


def _rebuild_derived():
    """Recalcula en el lugar lo que depende de COLORS (DATA, PHASE_STYLE)."""
    DATA["focus"] = COLORS["mint"]
    DATA["other"] = COLORS["rose"]
    PHASE_STYLE.update({
        "idle": ("Sin sesión", COLORS["surface3"], COLORS["label"]),
        "focus": ("Concentración", COLORS["mint"], COLORS["on_accent"]),
        "break": ("No concentración", COLORS["rose"], COLORS["on_accent"]),
        "tolerance": ("No concentración", COLORS["rose"], COLORS["on_accent"]),
        "paused": ("No concentración", COLORS["rose"], COLORS["on_accent"]),
        "away": ("No concentración", COLORS["rose"], COLORS["on_accent"]),
    })


_rebuild_derived()


def apply_palette(mode):
    """mode: "standard" | "contrast". Muta en el lugar COLORS, DATA, PHASE_STYLE,
    HEAT_RAMP y el estado interno de materiales. No toca widgets: quien llama
    decide si reconstruye la UI."""
    global CARD_STYLE, TILE_STYLE
    if mode not in PALETTES:
        raise ValueError(f"paleta desconocida: {mode!r}")
    _APPEARANCE["increase_contrast"] = mode == "contrast"
    # update y no clear+update: mismo dict, mismas claves, mismo orden.
    COLORS.update(PALETTES[mode])
    if mode == "standard" and _APPEARANCE["reduce_transparency"]:
        COLORS.update(RT_OVERRIDES)
    HEAT_RAMP[:] = _HEAT[mode]
    _rebuild_derived()
    _label_on.cache_clear()
    CARD_STYLE, TILE_STYLE = card_style(), card_style(tile=True)


def set_appearance(*, reduce_transparency=None, increase_contrast=None, glass_tint=None):
    """Guarda el modo visual vigente; devuelve True si cambió algo.

    `increase_contrast` llama a `apply_palette`. Un argumento en None conserva
    el valor actual. Lo usa la app al recibir avisos de a11y.
    """
    new = dict(_APPEARANCE)
    if reduce_transparency is not None:
        new["reduce_transparency"] = bool(reduce_transparency)
    if increase_contrast is not None:
        new["increase_contrast"] = bool(increase_contrast)
    if glass_tint is not None:
        new["glass_tint"] = max(0, min(100, int(round(glass_tint))))
    if new == _APPEARANCE:
        return False
    palette_changed = (new["increase_contrast"] != _APPEARANCE["increase_contrast"]
                       or new["reduce_transparency"] != _APPEARANCE["reduce_transparency"])
    _APPEARANCE.update(new)
    if palette_changed:
        apply_palette("contrast" if new["increase_contrast"] else "standard")
    return True


def appearance():
    """{"reduce_transparency": bool, "increase_contrast": bool, "glass_tint": int}"""
    return dict(_APPEARANCE)


def tint_multiplier(value=None):
    """Factor del regulador "Transparencia del vidrio" (0–100, 50 = neutro)."""
    v = _APPEARANCE["glass_tint"] if value is None else max(0, min(100, value))
    if v <= 50:
        return 0.60 + 0.008 * v
    return 1.0 + 0.014 * (v - 50)


def material(name, *, tone=None):
    """Material listo para dibujar con el modo vigente aplicado: regulador de
    tinte, RT (solid), AC (solid + border). `tone` (clave de COLORS) sólo para
    "prominent".

    Con `solid`, render.glass_compose ya baja el especular a la mitad: acá no se
    toca para no aplicarlo dos veces.
    """
    base = MATERIAL_CLEAR if name == "clear" else MATERIALS[name]
    if name == "prominent":
        tone_hex = COLORS.get(tone or "accent", tone or COLORS["accent"])
        base = replace(base, tint=tone_hex)
        # El prominente no responde al regulador: es un color, no un vidrio.
        if _APPEARANCE["increase_contrast"]:
            return replace(base, solid=tone_hex, sheen=0.0, border=_HC_BORDER_PROMINENT)
        if _APPEARANCE["reduce_transparency"]:
            return replace(base, solid=tone_hex)
        return base
    tint_a = min(TINT_CAP, base.tint_a * tint_multiplier())
    if _APPEARANCE["increase_contrast"]:
        return replace(base, tint_a=tint_a, solid=_HC_SOLID, sheen=0.0, border=_HC_BORDER)
    if _APPEARANCE["reduce_transparency"]:
        return replace(base, tint_a=tint_a, solid=_RT_SOLID.get(name, _RT_SOLID["control"]))
    return replace(base, tint_a=tint_a)


def card_style(radius=None, *, tile=False):
    """Estilo de tarjeta (o de mosaico) con el modo vigente aplicado.

    En AC: borde visible `border_hc`, sin luz superior, sin filo ni sombra. Fuera
    de AC, `border_hc` sale en None (no hay borde que dibujar).
    """
    style = _TILE_STANDARD if tile else _CARD_STANDARD
    if radius is not None:
        style = replace(style, radius=radius)
    if _APPEARANCE["increase_contrast"]:
        return replace(style, border_a=0.0, top_light_a=0.0, edge_dark=0.0, shadow=NO_SHADOW,
                       border_hc=_TILE_HC_BORDER if tile else _CARD_HC_BORDER)
    return style


def ambient_intensity():
    """Multiplicador de las manchas del fondo: 1 estándar, 0,5 RT, 0 AC (plano)."""
    if _APPEARANCE["increase_contrast"]:
        return 0.0
    return 0.5 if _APPEARANCE["reduce_transparency"] else 1.0


# --------------------------------------------------------------------------- #
# Color: contraste, etiquetas "vibrantes" y rellenos
# --------------------------------------------------------------------------- #


def contrast(a, b):
    """Contraste WCAG 2 entre dos colores hex (1 a 21)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


# nivel -> (color base, α inicial, piso de contraste)
VIBRANCY = {
    "label": ("#FFFFFF", 0.92, 7.0),
    "secondary": ("#EBEBF5", 0.64, 4.5),
    "tertiary": ("#EBEBF5", 0.46, 3.0),
    "quaternary": ("#EBEBF5", 0.22, 0.0),
}
_LEVEL_ALIASES = {"label_secondary": "secondary", "label_tertiary": "tertiary",
                  "label_quaternary": "quaternary", "primary": "label"}


_LEVEL_KEYS = {"label": "label", "secondary": "label_secondary",
               "tertiary": "label_tertiary", "quaternary": "label_quaternary"}


@lru_cache(maxsize=1024)
def _label_on(level, over, high_contrast):
    if high_contrast:
        return COLORS[_LEVEL_KEYS[level]]
    base, alpha, floor = VIBRANCY[level]
    # Sube de a 0,02 hasta llegar al piso (en pasos enteros, sin deriva de float).
    step = 0
    while True:
        a = min(1.0, alpha + 0.02 * step)
        color = mix(over, base, a)
        if a >= 1.0 or contrast(color, over) >= floor:
            return color
        step += 1


def label_on(level, over):
    """Color opaco de etiqueta 'vibrante' sobre el hex `over`, con piso de contraste.

    level: "label" | "secondary" | "tertiary" | "quaternary". Se mezcla la base
    con α sobre `over` y, si el contraste no llega al piso del nivel, el α sube
    de a 0,02 hasta llegar (máx. 1). En AC devuelve los colores fijos.
    """
    level = _LEVEL_ALIASES.get(level, level)
    if level not in VIBRANCY:
        raise KeyError(level)
    return _label_on(level, over.upper(), _APPEARANCE["increase_contrast"])


def fill_alpha(name):
    """α efectivo del relleno `name` (× 1,8 en AC, tope 1)."""
    alpha = FILLS[name]
    if _APPEARANCE["increase_contrast"]:
        alpha *= FILLS_HC_FACTOR
    return min(1.0, alpha)


def fill_on(name, over):
    """Mezcla blanco con α FILLS[name] sobre `over` (× 1,8 en AC)."""
    return mix(over, "#FFFFFF", fill_alpha(name))


def fill_border():
    """(color, α) del borde de 1 px de los rellenos en AC; None fuera de AC."""
    return FILL_BORDER_HC if _APPEARANCE["increase_contrast"] else None


def on_tone(tone):
    """Color de etiqueta sobre un relleno sólido del tono (clave de COLORS)."""
    return ON_TONE.get(tone, COLORS["on_accent"])


def score_color(percentage):
    """Verde / ámbar / rosa según qué tan buena fue la concentración."""
    if percentage >= 70:
        return COLORS["mint"]
    if percentage >= 45:
        return COLORS["amber"]
    return COLORS["rose"]


def elevate(color, steps=1):
    return mix(color, "#FFFFFF", 0.04 * steps)


# --------------------------------------------------------------------------- #
# Escala de pantalla
# --------------------------------------------------------------------------- #


def ui_scale(widget):
    """Escala de widgets de customtkinter (DPI × la del usuario); 1.0 si falla.

    Un `tk.Toplevel` suelto (avisos, menús) no está registrado en el
    ScalingTracker: en ese caso se usa la de su raíz.
    """
    tracker = ctk.ScalingTracker
    try:
        return float(tracker.get_widget_scaling(widget))
    except (KeyError, AttributeError):
        pass
    try:
        return float(tracker.window_dpi_scaling_dict[widget._root()] * tracker.widget_scaling)
    except (KeyError, AttributeError):
        return 1.0


def window_scale(root):
    """Escala de ventanas de customtkinter para `root`; 1.0 si falla."""
    tracker = ctk.ScalingTracker
    try:
        return float(tracker.get_window_scaling(root))
    except (KeyError, AttributeError):
        pass
    try:
        return float(tracker.window_dpi_scaling_dict[root._root()] * tracker.window_scaling)
    except (KeyError, AttributeError):
        return 1.0


# --------------------------------------------------------------------------- #
# Tipografía: archivos y familias
# --------------------------------------------------------------------------- #

# Orden de resolución: SF Pro si el usuario la puso en assets/ (copia local, no
# se distribuye) -> Inter 4.1 empaquetada (OFL) -> Segoe UI Variable -> Segoe UI.

_WEIGHT_WORDS = {
    "ultralight": 100, "extralight": 200, "thin": 200, "light": 300,
    "regular": 400, "": 400, "book": 400, "medium": 500, "semibold": 600,
    "demibold": 600, "bold": 700, "heavy": 800, "extrabold": 800, "black": 900,
}
_WEIGHT_NAMES = {100: "Ultralight", 200: "Thin", 300: "Light", 400: "Regular",
                 500: "Medium", 600: "Semibold", 700: "Bold", 800: "Heavy", 900: "Black"}
# Mezclar el diseño de texto con el Display pesa como 150 de peso: un Semibold de
# texto le gana a un Regular de Display para un título Bold.
_DESIGN_PENALTY = 150


@dataclass(frozen=True)
class _FontFile:
    path: str
    design: str          # "text" | "display" | "any" (variable con eje opsz)
    weight: int          # 0 en una variable (cualquier peso)
    variable: bool = False


def _norm(filename):
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    return re.sub(r"[^a-z0-9]", "", stem)


def _font_dirs(assets_dir):
    return [assets_dir, os.path.join(assets_dir, "fonts")]


def _list_fonts(dirs):
    found = []
    for folder in dirs:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if os.path.splitext(name)[1].lower() in (".otf", ".ttf"):
                found.append(os.path.join(folder, name))
    return found


def _scan_sf(dirs):
    """Archivos de SF Pro con los nombres de la descarga actual de Apple
    (SF-Pro-Display-*.otf, SF-Pro-Text-*.otf, SF-Pro.ttf variable) y los viejos
    (SFProText-*.otf, SFUIDisplay-*.otf, SFUIText-*.otf). Sin itálicas, Rounded,
    Compact ni Mono."""
    files = []
    for path in _list_fonts(dirs):
        key = _norm(path)
        if key in ("sfpro", "sfprovariable"):
            files.append(_FontFile(path, "any", 0, True))
            continue
        match = re.fullmatch(r"sf(?:pro|ui)(text|display)([a-z]*)", key)
        if not match or "italic" in match.group(2):
            continue
        weight = _WEIGHT_WORDS.get(match.group(2))
        if weight is not None:
            files.append(_FontFile(path, match.group(1), weight))
    return files


def _scan_inter(dirs):
    """Inter 4.1 estática: Inter-*.ttf (texto) e InterDisplay-*.ttf."""
    files = []
    for path in _list_fonts(dirs):
        match = re.fullmatch(r"inter(display)?([a-z]*)", _norm(path))
        if not match or "italic" in match.group(2):
            continue
        weight = _WEIGHT_WORDS.get(match.group(2))
        if weight is not None:
            files.append(_FontFile(path, "display" if match.group(1) else "text", weight))
    return files


def _windows_fonts_dir():
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _scan_segoe(variable):
    """Segoe UI del sistema (sólo existe en Windows)."""
    folder = _windows_fonts_dir()
    if variable:
        path = os.path.join(folder, "SegUIVar.ttf")
        return [_FontFile(path, "any", 0, True)] if os.path.exists(path) else []
    files = []
    for name, weight in (("segoeui.ttf", 400), ("seguisb.ttf", 600), ("segoeuib.ttf", 700)):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            files.append(_FontFile(path, "text", weight))
    return files


def _pick(files, design, weight):
    """El archivo más cercano al (diseño, peso) pedido; None si no hay ninguno."""
    best, best_score = None, None
    for f in files:
        if f.variable:
            score = 1          # cualquier peso, pero mejor un estático exacto (hinting)
        else:
            score = abs(f.weight - weight) + (0 if f.design == design else _DESIGN_PENALTY)
            if f.weight < weight:
                score += 0.5   # a igual distancia, el más pesado
        if best_score is None or score < best_score:
            best, best_score = f, score
    return best


@lru_cache(maxsize=64)
def _font_names(path):
    """Nombres de la tabla `name` de un TTF/OTF: {id: texto} para los ids 1, 2,
    16 y 17 (familia y estilo heredados de GDI, y los tipográficos)."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
        num_tables = struct.unpack_from(">H", data, 4)[0]
        name_offset = None
        for i in range(num_tables):
            tag, _check, offset, _length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            if tag == b"name":
                name_offset = offset
                break
        if name_offset is None:
            return {}
        _fmt, count, strings = struct.unpack_from(">HHH", data, name_offset)
        found = {}
        for i in range(count):
            platform, encoding, language, name_id, length, offset = struct.unpack_from(
                ">HHHHHH", data, name_offset + 6 + 12 * i)
            if name_id not in (1, 2, 16, 17):
                continue
            raw = data[name_offset + strings + offset:name_offset + strings + offset + length]
            if platform == 3 and encoding in (0, 1, 10):
                # Windows: preferimos inglés de EE. UU.
                rank = 0 if language == 0x409 else 1
                text = raw.decode("utf-16-be", "replace")
            elif platform == 1 and encoding == 0:
                rank, text = 2, raw.decode("mac_roman", "replace")
            else:
                continue
            if name_id not in found or rank < found[name_id][0]:
                found[name_id] = (rank, text)
        return {key: value[1] for key, value in found.items()}
    except (OSError, struct.error, ValueError):
        return {}


_REGISTERED = set()


def _register_font(path):
    """Registra la tipografía para este proceso (sólo Windows).

    FR_PRIVATE (0x10) la deja visible sólo para nosotros y no hace falta avisar
    a nadie: el aviso WM_FONTCHANGE a todas las ventanas (HWND_BROADCAST) que se
    mandaba antes podía colgar el arranque si alguna no respondía.
    """
    if os.name != "nt":
        return False
    path = os.path.abspath(path)
    if path in _REGISTERED:
        return True
    try:
        if ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0):
            _REGISTERED.add(path)
            return True
    except (AttributeError, OSError):
        return False
    return False


# Familias de respaldo por (diseño, peso): candidatos (familia, peso Tk) en orden.
# GDI recorta los nombres a 31 caracteres ("Segoe UI Variable Display Semib").
_SEGOE_VARIABLE_TK = {
    ("text", 400): [("Segoe UI Variable Text", "normal")],
    ("text", 500): [("Segoe UI Variable Text", "normal")],
    ("text", 600): [("Segoe UI Variable Text Semibold", "normal"),
                    ("Segoe UI Variable Text", "bold")],
    ("text", 700): [("Segoe UI Variable Text", "bold")],
    ("display", 400): [("Segoe UI Variable Display", "normal")],
    ("display", 500): [("Segoe UI Variable Display", "normal")],
    ("display", 600): [("Segoe UI Variable Display Semibold", "normal"),
                       ("Segoe UI Variable Display Semib", "normal"),
                       ("Segoe UI Variable Display", "bold")],
    ("display", 700): [("Segoe UI Variable Display", "bold")],
}
_SEGOE_TK = {
    400: [("Segoe UI", "normal")],
    500: [("Segoe UI", "normal")],
    600: [("Segoe UI Semibold", "normal"), ("Segoe UI", "bold")],
    700: [("Segoe UI", "bold")],
}
_INTER_BUNDLE = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf",
                 "Inter-Bold.ttf", "InterDisplay-Medium.ttf", "InterDisplay-SemiBold.ttf",
                 "InterDisplay-Bold.ttf")


def _snap_weight(weight):
    return min((400, 500, 600, 700), key=lambda w: (abs(w - weight), -w))


class Typography:
    """Familias tipográficas resueltas una vez, escala de roles y fuentes PIL.

    `fonts["section"]` (claves heredadas y roles nuevos) devuelve un CTkFont;
    `tk(rol, escala)` la tupla para ítems de canvas; `pil(rol, escala)` la
    fuente de Pillow cargada del archivo exacto del peso.

    Fuera de Windows no se instala nada: Tk ve lo que conozca fontconfig (en
    desarrollo, `FONTCONFIG_FILE` con `assets/`) y PIL carga por ruta. Ojo con
    X11: Tk pide "normal" como FC_WEIGHT_MEDIUM, así que "Inter" normal sale en
    Medium salvo que fontconfig lo corrija (ver el fonts.conf de las capturas).
    """

    _current = None

    def __init__(self, root, *, assets_dir=None):
        self._root = root
        self.assets_dir = assets_dir or ASSETS_DIR
        dirs = _font_dirs(self.assets_dir)

        sf = _scan_sf(dirs)
        inter = _scan_inter(dirs)
        self._fallback_files = inter        # Inter siempre de respaldo para PIL
        if sf:
            self.source, self._files = "sf", sf
        elif inter:
            self.source, self._files = "inter", inter
        else:
            self.source, self._files = None, []

        for f in self._files:
            _register_font(f.path)
        try:
            root.update_idletasks()
        except tkinter.TclError:
            pass  # un root a medio crear no debe impedir arrancar

        self._tk_cache = {}
        self._probe_cache = {}
        self._pil_cache = {}
        self._measure_fonts = {}

        if self.source is None:
            variable = os.name == "nt" and self._probe("Segoe UI Variable Text")
            self.source = "segoe-variable" if variable else "segoe"
            self._files = _scan_segoe(variable) or _scan_segoe(False)

        # Familia Tk por (diseño, peso) que usa la escala.
        self._families = {}
        sources = {}
        for design in ("text", "display"):
            for weight in (400, 500, 600, 700):
                family, tk_weight, src = self._resolve_tk(design, weight)
                self._families[(design, weight)] = (family, tk_weight)
                sources[(design, weight)] = src
        #: Qué terminó usando Tk para el cuerpo ("sf" | "inter" | "segoe-variable"
        #: | "segoe"): difiere de `source` si los archivos están pero Tk no los ve.
        self.tk_source = sources[("text", 400)]

        # Compatibilidad con el código viejo.
        self.regular = self._families[("text", 400)][0]
        self.medium = self._families[("text", 500)][0]
        self.semibold = self._families[("text", 600)][0]
        self.paths = self._compat_paths(400)
        self.paths_bold = self._compat_paths(600)

        self.fonts = {}
        for key in list(TYPE_SCALE) + list(_LEGACY_FONTS):
            design, weight, px = self._spec(key)[:3]
            family, tk_weight = self._families[(design, _snap_weight(weight))]
            self.fonts[key] = ctk.CTkFont(family=family, size=px, weight=tk_weight)

        Typography._current = self

    # -- resolución ----------------------------------------------------------

    @classmethod
    def current(cls):
        """Última instancia creada (para widgets que no reciben `fonts`)."""
        if cls._current is None:
            root = getattr(tkinter, "_default_root", None)
            if root is None:
                raise RuntimeError("Typography.current() sin ventana raíz")
            cls(root)
        return cls._current

    def _probe(self, family, extra=()):
        """True si Tk resuelve `family` a sí misma (o a uno de `extra`, que es lo
        que devuelve fontconfig para las familias secundarias como "Inter
        SemiBold" -> "Inter")."""
        key = (family, tuple(extra))
        cached = self._probe_cache.get(key)
        if cached is not None:
            return cached
        try:
            actual = tkfont.Font(root=self._root, family=family, size=-13).actual("family")
        except (tkinter.TclError, RuntimeError):
            actual = ""  # raíz destruida o sin pantalla: la candidata no sirve
        accepted = {n.casefold() for n in (family, *extra) if n}
        ok = actual.casefold() in accepted
        self._probe_cache[key] = ok
        return ok

    def _candidates(self, f, design, weight):
        """Candidatos (familia, peso Tk) para el archivo `f` elegido."""
        names = _font_names(f.path)
        n1, n2, n16 = names.get(1, ""), names.get(2, ""), names.get(16, "")
        extra = (n1, n16)
        bold = "bold" if weight >= 600 else "normal"
        out = []
        if not f.variable and n1 and n2.lower() in ("regular", "bold", "italic", "bold italic"):
            # Lo que ve GDI: familia heredada (nameID 1) + Regular/Bold (nameID 2).
            # Con un estilo heredado no RIBBI ("Semibold") Tk no llega a ese peso
            # por esta familia: se prueba con los nombres de abajo.
            out.append((n1, "bold" if n2.lower().startswith("bold") else "normal", extra))
        family = n16 or n1
        if f.variable and family:
            # Instancias con nombre de la variable, como las expone Windows.
            word = _WEIGHT_NAMES.get(weight, "Regular")
            for name in (f"{family} {design.title()} {word}", f"{family} {word}"):
                out.append((name, "normal", extra))
            out.append((f"{family} {design.title()}", bold, extra))
        if family:
            # Lo que ve fontconfig: familia tipográfica con normal/bold.
            out.append((family, bold, extra))
        if self.source == "sf":
            plain = "SF Pro Display" if design == "display" else "SF Pro Text"
            out += [(f"{plain} {_WEIGHT_NAMES.get(weight, 'Regular')}", "normal", ()),
                    (plain, bold, ()), ("SF Pro", bold, ())]
        return out

    def _resolve_tk(self, design, weight):
        """(familia, peso Tk, fuente) para (diseño, peso): la primera candidata
        que Tk resuelve de verdad."""
        if self.source in ("sf", "inter"):
            f = _pick(self._files, design, weight)
            if f is not None:
                for family, tk_weight, extra in self._candidates(f, design, weight):
                    if self._probe(family, extra):
                        return family, tk_weight, self.source
        if os.name == "nt":
            for family, tk_weight in _SEGOE_VARIABLE_TK[(design, weight)]:
                if self._probe(family):
                    return family, tk_weight, "segoe-variable"
            for family, tk_weight in _SEGOE_TK[weight]:
                if self._probe(family):
                    return family, tk_weight, "segoe"
        # Como antes: "Segoe UI" aunque no esté; Tk elige la más parecida.
        family, tk_weight = _SEGOE_TK[weight][0]
        return family, tk_weight, "segoe"

    def _spec(self, key):
        """(diseño, peso, px, interlínea, tracking, motor, mayúsculas) de un rol o
        de una clave heredada."""
        if key in TYPE_SCALE:
            role, weight = TYPE_SCALE[key], None
        elif key in _LEGACY_FONTS:
            name, weight = _LEGACY_FONTS[key]
            role = TYPE_SCALE[name]
        else:
            raise KeyError(key)
        return (role.design, weight or role.weight, role.px, role.line, role.tracking,
                role.engine, role.upper)

    def _compat_paths(self, weight):
        paths = []
        f = _pick(self._files, "text", weight)
        if f is not None:
            paths.append(f.path)
        g = _pick(self._fallback_files, "text", weight)
        if g is not None:
            paths.append(g.path)
        paths.append("segoeui.ttf" if weight < 600 else "seguisb.ttf")
        return list(dict.fromkeys(paths))

    # -- API -----------------------------------------------------------------

    def __getitem__(self, key):
        return self.fonts[key]

    def tk(self, role, scale=1.0):
        """(familia, -px, "normal"|"bold") para ítems de texto de un canvas."""
        key = (role, round(scale, 4))
        cached = self._tk_cache.get(key)
        if cached is None:
            design, weight, px = self._spec(role)[:3]
            family, tk_weight = self._families[(design, _snap_weight(weight))]
            cached = self._tk_cache[key] = (family, -max(1, round(px * scale)), tk_weight)
        return cached

    def pil_path(self, design, weight):
        """Ruta del archivo para (diseño, peso), o None si no hay ninguno."""
        f = _pick(self._files, design, weight) or _pick(self._fallback_files, design, weight)
        return f.path if f is not None else None

    def pil(self, role, scale=1.0, px=None):
        """Fuente de Pillow del archivo exacto del peso (en una variable, con los
        ejes de peso y tamaño óptico). `px` pisa el tamaño del rol (reloj)."""
        design, weight, role_px = self._spec(role)[:3]
        logical = role_px if px is None else px
        size = max(1, round(logical * scale))
        f = _pick(self._files, design, weight) or _pick(self._fallback_files, design, weight)
        key = (f.path if f else None, size, weight if f and f.variable else 0,
               round(logical) if f and f.variable else 0)
        cached = self._pil_cache.get(key)
        if cached is not None:
            return cached
        font = None
        if f is not None:
            try:
                font = ImageFont.truetype(f.path, size)
                if f.variable:
                    _set_axes(font, weight, logical)
            except OSError:
                font = None
        if font is None:
            font = _fallback_pil(size, weight, self._fallback_files, design)
        self._pil_cache[key] = font
        return font

    def measure(self, role, text, scale=1.0):
        """Ancho en px de `text` con la fuente Tk del rol."""
        spec = self.tk(role, scale)
        font = self._measure_fonts.get(spec)
        if font is None:
            family, size, weight = spec
            font = self._measure_fonts[spec] = tkfont.Font(
                root=self._root, family=family, size=size, weight=weight)
        return font.measure(text)

    def role(self, key):
        """El TypeRole efectivo de un rol o clave heredada."""
        design, weight, px, line, tracking, engine, upper = self._spec(key)
        return TypeRole(design, weight, px, line, tracking, engine, upper)


def _set_axes(font, weight, px):
    """Ejes de una variable: peso y tamaño óptico (los demás, por defecto)."""
    try:
        axes = font.get_variation_axes()
    except (OSError, AttributeError):
        return
    values = []
    for axis in axes:
        name = axis.get("name", b"")
        name = name.decode("latin-1", "replace") if isinstance(name, bytes) else str(name)
        name = name.lower().replace(" ", "")
        if name in ("weight", "wght"):
            value = weight
        elif name in ("opticalsize", "optical", "opsz"):
            value = px
        else:
            value = axis.get("default", axis["minimum"])
        values.append(max(axis["minimum"], min(axis["maximum"], value)))
    try:
        font.set_variation_by_axes(values)
    except (OSError, ValueError):
        pass


def _fallback_pil(size, weight, inter_files, design):
    """Inter empaquetada -> Segoe UI -> DejaVu -> la de Pillow."""
    f = _pick(inter_files, design, weight)
    candidates = [f.path] if f else []
    candidates += ["seguisb.ttf" if weight >= 600 else "segoeui.ttf",
                   "DejaVuSans-Bold.ttf" if weight >= 600 else "DejaVuSans.ttf"]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()   # Pillow < 10.1: sin tamaño
