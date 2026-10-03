"""Renderizado de gráficos y materiales con antialiasing real.

Todo se dibuja con numpy sobre un buffer float32 y se compone contra el fondo del
widget: un color hex (como siempre) o un recorte del fondo de la ventana, un
`np.ndarray` (alto, ancho, 3). Los bordes se suavizan con `smoothstep` sobre la
distancia al borde (en píxeles), así que salen limpios a cualquier tamaño y sin
el escalonado de `tk.Canvas.create_arc` ni el peso de matplotlib.

Acá también vive la matemática de los materiales del rediseño (DESIGN_SPEC §2):
fondo ambiental por capas, vidrio (refracción en el borde, saturación, tinte,
brillo especular, sombra interior), sombras proyectadas, cuerpo de las tarjetas,
texto con tracking y reloj con cifras tabulares. Son funciones puras, sin Tk: los
colores y los materiales llegan por parámetro (este módulo no importa `theme`).
Cualquier objeto con los atributos de `theme.Material`, `theme.ShadowSpec` o
`theme.CardStyle` sirve (en las pruebas, un `SimpleNamespace`).
"""

from __future__ import annotations

import math
import os
import sys
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

# --------------------------------------------------------------------------- #
# Color
# --------------------------------------------------------------------------- #


def hex_to_rgb(color):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def rgb_to_hex(rgb):
    r, g, b = (max(0, min(255, int(round(v)))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(color_a, color_b, t):
    """Interpola dos colores hex. t=0 -> a, t=1 -> b."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = hex_to_rgb(color_a)
    rb, gb, bb = hex_to_rgb(color_b)
    return rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def lighten(color, amount=0.12):
    return mix(color, "#FFFFFF", amount)


def darken(color, amount=0.12):
    return mix(color, "#000000", amount)


def relative_luminance(color):
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = hex_to_rgb(color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def readable_on(color, dark="#1B1640", light="#F6F4FF"):
    """Devuelve el color de texto con mejor contraste sobre `color`."""
    return dark if relative_luminance(color) > 0.42 else light


def _rgb32(color):
    """Color hex (o tupla RGB) como vector float32."""
    if isinstance(color, str):
        return np.array(hex_to_rgb(color), np.float32)
    return np.array(color[:3], np.float32)


def _ink(color):
    """Color hex (o tupla) como tupla de enteros para PIL."""
    if isinstance(color, str):
        return hex_to_rgb(color)
    return tuple(int(v) for v in color)


# --------------------------------------------------------------------------- #
# Cachés acotadas
# --------------------------------------------------------------------------- #


class _LRU(OrderedDict):
    """Caché acotada: al pasarse de `maxsize` entradas (o de `maxbytes` en
    arreglos) descarta las menos usadas, de a una. Antes se vaciaban enteras y
    durante un redimensionado se recalculaba todo en cada cuadro.

    Los arreglos que se guardan quedan de sólo lectura: el que los pide no
    tiene que modificarlos (si necesita escribir, que copie)."""

    def __init__(self, maxsize, maxbytes=None):
        super().__init__()
        self.maxsize = maxsize
        self.maxbytes = maxbytes
        self.nbytes = 0
        self._sizes = {}

    def get(self, key, default=None):
        try:
            value = OrderedDict.__getitem__(self, key)
        except KeyError:
            return default
        self.move_to_end(key)
        return value

    def put(self, key, value):
        size = _freeze(value)
        if key in self:
            self.nbytes -= self._sizes.get(key, 0)
        OrderedDict.__setitem__(self, key, value)
        self.move_to_end(key)
        self._sizes[key] = size
        self.nbytes += size
        while len(self) > self.maxsize or (
                self.maxbytes is not None and self.nbytes > self.maxbytes and len(self) > 1):
            old, _ = self.popitem(last=False)
            self.nbytes -= self._sizes.pop(old, 0)
        return value

    def clear(self):
        OrderedDict.clear(self)
        self._sizes.clear()
        self.nbytes = 0


def _freeze(value):
    """Marca de sólo lectura los arreglos de `value` y devuelve cuántos bytes ocupan."""
    if isinstance(value, np.ndarray):
        value.flags.writeable = False
        return value.nbytes
    if isinstance(value, (tuple, list)):
        return sum(_freeze(v) for v in value)
    if isinstance(value, dict):
        return sum(_freeze(v) for v in value.values())
    if hasattr(value, "__dataclass_fields__"):     # GlassShape, AmbientLayers
        return sum(_freeze(getattr(value, f)) for f in value.__dataclass_fields__)
    if isinstance(value, Image.Image):
        return value.width * value.height * len(value.getbands())
    return 0


# --------------------------------------------------------------------------- #
# Utilidades numpy
# --------------------------------------------------------------------------- #


def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / max(1e-6, (edge1 - edge0)), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _ss(e0, e1, x):
    """smoothstep que admite bordes invertidos (e0 > e1), como el del mockup."""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


_POLAR_CACHE = _LRU(16)
_GRID_CACHE = _LRU(16)
_FEATHER_CACHE = _LRU(16)
_RING_CACHE = _LRU(16)
_THETA_CACHE = _LRU(16)
_SUPPORT_CACHE = _LRU(32)


def _grid(size):
    """Grilla de coordenadas (yy, xx) cacheada por tamaño."""
    cached = _GRID_CACHE.get(size)
    if cached is None:
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        cached = _GRID_CACHE.put(size, (yy, xx))
    return cached


def _polar(size):
    """Cachea la grilla polar: es lo más caro y sólo depende del tamaño."""
    cached = _POLAR_CACHE.get(size)
    if cached is not None:
        return cached
    yy, xx = _grid(size)
    c = (size - 1) / 2.0
    dx = xx - c
    dy = yy - c
    radius = np.sqrt(dx * dx + dy * dy)
    # atan2(dy, dx) con y hacia abajo => ángulos crecen en sentido horario,
    # que es exactamente lo que queremos para un gráfico de anillo.
    angle = np.degrees(np.arctan2(dy, dx))
    return _POLAR_CACHE.put(size, (radius, angle))


def _feather_width(size, feather_px=1.0):
    """Ancho angular (en grados) de un píxel a cada radio. Cacheado por tamaño.

    Cerca del centro un píxel abarca muchos grados; en el borde exterior, muy
    pocos. Usar esto como escala del suavizado mantiene los bordes con el mismo
    grosor aparente en todo el anillo.
    """
    key = (size, feather_px)
    cached = _FEATHER_CACHE.get(key)
    if cached is None:
        radius, _ = _polar(size)
        cached = _FEATHER_CACHE.put(
            key, np.degrees(feather_px / np.maximum(radius, 1.0)).astype(np.float32))
    return cached


def _theta_from(size, start_deg):
    """Ángulo normalizado a 0..360 desde `start_deg`. Cacheado."""
    key = (size, round(float(start_deg), 3))
    cached = _THETA_CACHE.get(key)
    if cached is None:
        _, angle = _polar(size)
        cached = _THETA_CACHE.put(key, ((angle - start_deg) % 360.0).astype(np.float32))
    return cached


def _sector_mask(theta_norm, width, start, end):
    """Máscara suavizada del sector [start, end] sobre un ángulo ya normalizado.

    `theta_norm` debe estar en 0..360 medido desde el inicio del anillo, de modo
    que ningún sector cruce la costura y no haga falta partirlo en dos.
    """
    if end - start <= 0:
        return None
    enter = _smoothstep(-1.0, 1.0, (theta_norm - start) / width)
    leave = 1.0 - _smoothstep(-1.0, 1.0, (theta_norm - end) / width)
    enter *= leave
    return enter


def _ring_mask(size, inner, outer, feather=1.0):
    """Corona circular antialiaseada, cacheada."""
    key = (size, round(inner, 2), round(outer, 2), feather)
    cached = _RING_CACHE.get(key)
    if cached is None:
        radius, _ = _polar(size)
        cached = _RING_CACHE.put(key, (
            _smoothstep(inner - feather, inner + feather, radius)
            * (1.0 - _smoothstep(outer - feather, outer + feather, radius))
        ).astype(np.float32))
    return cached


def _ring_support(size, inner, outer, feather=1.0):
    """Índices planos donde la corona no es cero (cacheados con la corona).

    Fuera de ahí las mezclas `buffer += (color − buffer) · 0` no cambian nada,
    así que trabajar sólo sobre estos índices da el mismo resultado bit a bit y
    en un anillo fino ahorra casi todo el trabajo.
    """
    key = ("ring", size, round(inner, 2), round(outer, 2), feather)
    cached = _SUPPORT_CACHE.get(key)
    if cached is None:
        ring = _ring_mask(size, inner, outer, feather)
        cached = _SUPPORT_CACHE.put(key, np.flatnonzero(ring))
    return cached


def _to_image(buffer):
    return Image.fromarray(np.clip(buffer, 0, 255).astype(np.uint8), "RGB")


def _base(background, width, height):
    """Buffer float32 (alto, ancho, 3) de arranque: un color hex o el recorte del fondo.

    `background` es un hex (como siempre), un `np.ndarray` (alto, ancho, 3) uint8 o
    float32, o una imagen PIL. Si el arreglo no mide justo (alto, ancho) se recorta
    o se estira su borde: un widget recién creado puede pedir un tamaño mínimo
    distinto del recorte que le dio su host, y eso no tiene que tirar el redibujo.
    """
    if isinstance(background, str):
        return np.tile(np.array(hex_to_rgb(background), np.float32), (height, width, 1))
    if isinstance(background, Image.Image):
        background = np.asarray(background.convert("RGB"))
    arr = np.asarray(background)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError(f"fondo inválido: se esperaba (alto, ancho, 3), llegó {arr.shape}")
    arr = arr[:height, :width, :3]
    if arr.shape[0] == 0 or arr.shape[1] == 0:
        return np.zeros((height, width, 3), np.float32)
    if arr.shape[0] != height or arr.shape[1] != width:
        arr = np.pad(arr, ((0, height - arr.shape[0]), (0, width - arr.shape[1]), (0, 0)),
                     mode="edge")
    return arr.astype(np.float32)


def _bg_hex(background):
    """Hex representativo del fondo (el promedio si es un recorte)."""
    if isinstance(background, str):
        return background
    if isinstance(background, Image.Image):
        background = np.asarray(background.convert("RGB"))
    return mean_hex(np.asarray(background))


# --------------------------------------------------------------------------- #
# Anillo / dona
# --------------------------------------------------------------------------- #


def donut(
    size,
    segments,
    background,
    inner_ratio=0.63,
    gap_deg=2.2,
    start_deg=-90.0,
    padding=2,
    track=None,
    glow=0.0,
):
    """Anillo segmentado.

    segments   -- [(valor, color_hex), ...]
    background -- hex o recorte del fondo (ndarray (size, size, 3))
    track      -- color del anillo de fondo cuando no hay datos
    glow       -- 0..1, halo suave del color dominante detrás del anillo
    """
    size = max(24, int(size))
    radius, angle = _polar(size)

    outer = size / 2.0 - padding
    inner = outer * inner_ratio
    ring = _ring_mask(size, inner, outer)

    buffer = _base(background, size, size)

    colors = [c for _, c in segments]
    values = [max(0.0, float(v)) for v, _ in segments]
    total = sum(values)

    if glow > 0.0 and total > 0:
        dominant = max(zip(values, colors), key=lambda p: p[0])[1]
        halo = (1.0 - _smoothstep(outer * 0.55, outer * 1.16, radius)) * float(glow)
        buffer += (np.array(hex_to_rgb(dominant), np.float32) - buffer) * halo[..., None]

    if total <= 0:
        color = np.array(hex_to_rgb(track or mix(_bg_hex(background), "#FFFFFF", 0.08)),
                         np.float32)
        buffer += (color - buffer) * ring[..., None]
        return _to_image(buffer)

    live = [i for i, v in enumerate(values) if v > 0]
    if len(live) == 1:  # un único segmento: pintamos la corona entera y evitamos
        rgb = np.array(hex_to_rgb(colors[live[0]]), np.float32)  # la costura en 0º
        buffer += (rgb - buffer) * ring[..., None]
        return _to_image(buffer)

    # Normalizamos el ángulo una sola vez: así ningún sector cruza la costura.
    theta = _theta_from(size, start_deg)
    width = _feather_width(size)
    gap = gap_deg

    cursor = 0.0
    for value, color in zip(values, colors):
        sweep = value / total * 360.0
        if value > 0:
            half = min(gap / 2.0, sweep / 2.5)
            mask = _sector_mask(theta, width, cursor + half, cursor + sweep - half)
            if mask is not None:
                mask *= ring
                rgb = np.array(hex_to_rgb(color), np.float32)
                buffer += (rgb - buffer) * mask[..., None]
        cursor += sweep

    return _to_image(buffer)


def progress_ring(
    size,
    fraction,
    color,
    track_color,
    background,
    thickness=0.14,
    start_deg=-90.0,
    padding=2,
    cap_round=True,
    cap_min_fraction=0.005,
    glow=0.0,
    track_alpha=1.0,
):
    """Anillo de progreso con puntas redondeadas.

    cap_min_fraction -- debajo de esta fracción no se dibujan las tapas: con el
                        progreso casi en cero quedaba un "punto" suelto arriba.
    glow             -- α del resplandor del arco (máscara del arco desenfocada
                        con σ = 0,9 · trazo). Necesita margen (`padding`) para no
                        cortarse contra el borde de la imagen.
    track_alpha      -- α del riel sobre el fondo (riel blanco 0,10 sobre el
                        fondo ambiental: track_color="#FFFFFF", track_alpha=0.10).
    """
    size = max(24, int(size))
    radius, angle = _polar(size)

    outer = size / 2.0 - padding
    band = max(2.0, outer * thickness * 2.0)
    inner = max(1.0, outer - band)
    mid = (outer + inner) / 2.0
    feather = 1.0

    ring = _ring_mask(size, inner, outer)
    # Todo se calcula sólo donde la corona existe (mismo resultado, mucho menos
    # trabajo). Si las tapas pudieran salirse de la corona (anillo tan grueso que
    # el borde interior topa con 1 px), se cae al cálculo sobre la imagen entera.
    caps_inside = band / 2.0 <= (outer - inner) / 2.0 + 1e-6
    support = _ring_support(size, inner, outer) if caps_inside else None

    buffer = _base(background, size, size)
    flat = buffer.reshape(-1, 3)
    track = np.array(hex_to_rgb(track_color), np.float32)
    if support is not None:
        ring_s = ring.reshape(-1)[support][:, None]
        flat[support] += (track - flat[support]) * (
            ring_s if track_alpha >= 1.0 else ring_s * float(track_alpha))
    else:
        buffer += (track - buffer) * (
            ring if track_alpha >= 1.0 else ring * float(track_alpha))[..., None]

    fraction = max(0.0, min(1.0, float(fraction)))
    if fraction <= 0.0:
        return _to_image(buffer)

    sweep = fraction * 360.0
    if support is not None:
        if fraction >= 0.999:
            mask = ring_s[:, 0].copy()
        else:
            theta = _theta_from(size, start_deg).reshape(-1)[support]
            width = _feather_width(size).reshape(-1)[support]
            mask = _sector_mask(theta, width, 0.0, sweep) * ring_s[:, 0]
    else:
        if fraction >= 0.999:
            mask = ring.copy()
        else:
            theta = _theta_from(size, start_deg)
            mask = _sector_mask(theta, _feather_width(size), 0.0, sweep) * ring

    if cap_round and cap_min_fraction <= fraction < 0.999:
        cap_r = band / 2.0
        yy, xx = _grid(size)
        if support is not None:
            yy, xx = yy.reshape(-1)[support], xx.reshape(-1)[support]
        for deg in (start_deg, start_deg + sweep):
            rad = math.radians(deg)
            cx = (size - 1) / 2.0 + math.cos(rad) * mid
            cy = (size - 1) / 2.0 + math.sin(rad) * mid
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            mask = np.maximum(mask, 1.0 - _smoothstep(cap_r - feather, cap_r + feather, dist))

    rgb = np.array(hex_to_rgb(color), np.float32)
    if support is not None:
        flat[support] += (rgb - flat[support]) * mask[:, None]
    else:
        buffer += (rgb - buffer) * mask[..., None]
    image = _to_image(buffer)
    if glow > 0.0:
        # Resplandor: la máscara del arco desenfocada, mezclada hacia el mismo
        # color. Mezclar hacia un mismo color conmuta (resplandor y después arco
        # da lo mismo que al revés), así que va al final y en C: un `paste`.
        full = mask
        if support is not None:
            full = np.zeros(size * size, np.float32)
            full[support] = mask
        full = Image.fromarray((full.reshape(size, size) * 255).astype(np.uint8), "L")
        halo = blur_image(full, band * 0.9, scale=4)
        alpha = max(0.0, min(1.0, float(glow)))
        halo = halo.point([int(v * alpha + 0.5) for v in range(256)])
        image.paste(tuple(int(v) for v in rgb), (0, 0, size, size), halo)
    return image


def _sector_supports(size, count, gap_deg, start_deg, inner, outer):
    """Índices planos de cada franja de `radial_profile` (cuña ∩ corona útil).

    Una franja sólo puede pintar donde su máscara angular y su banda radial son
    distintas de cero: entre a0 − ancho y a1 + ancho, y entre inner − 1 y
    outer + 1. Afuera la mezcla suma cero, así que el resultado es idéntico.
    """
    key = ("radial", size, count, round(float(gap_deg), 4), round(float(start_deg), 3),
           round(float(inner), 3), round(float(outer), 3))
    cached = _SUPPORT_CACHE.get(key)
    if cached is not None:
        return cached
    radius, _ = _polar(size)
    theta = _theta_from(size, start_deg)
    width = _feather_width(size)
    radial = (radius > inner - 1.0) & (radius < outer + 1.0)
    step = 360.0 / count
    supports = []
    for index in range(count):
        a0 = index * step + gap_deg / 2.0
        a1 = (index + 1) * step - gap_deg / 2.0
        wedge = (theta > a0 - width) & (theta < a1 + width) & radial
        supports.append(np.flatnonzero(wedge))
    return _SUPPORT_CACHE.put(key, supports)


def radial_profile(
    size,
    values,
    background,
    color,
    track_color,
    inner_ratio=0.30,
    gap_deg=2.0,
    start_deg=-90.0,
    padding=2,
    highlight=None,
    highlight_color=None,
):
    """Perfil circular: un sector por franja, con el radio según su valor.

    Se usa para el reloj de concentración por hora: de un vistazo se ve si rendís
    de mañana, de tarde o de madrugada, cosa que una fila de barras no muestra
    igual de bien porque el día es cíclico, no lineal.
    """
    size = max(48, int(size))
    radius, _ = _polar(size)
    theta = _theta_from(size, start_deg)
    width = _feather_width(size)

    outer = size / 2.0 - padding
    inner = outer * inner_ratio
    buffer = _base(background, size, size)
    flat = buffer.reshape(-1, 3)

    count = max(1, len(values))
    step = 360.0 / count
    peak = max(values) if values and max(values) > 0 else 1.0

    # Anillo tenue de referencia: marca dónde estaría el máximo.
    guide = _ring_mask(size, outer - 1.2, outer)
    support = _ring_support(size, outer - 1.2, outer)
    guide_s = (guide.reshape(-1)[support] * 0.5)[:, None]
    flat[support] += (np.array(hex_to_rgb(track_color), np.float32) - flat[support]) * guide_s

    # Cada franja trabaja sólo sobre su cuña (cacheada por tamaño): mismo
    # resultado que sobre la imagen entera, ~20 veces menos cuentas.
    supports = _sector_supports(size, count, gap_deg, start_deg, inner, outer)
    radius_f, theta_f, width_f = radius.reshape(-1), theta.reshape(-1), width.reshape(-1)

    for index, value in enumerate(values):
        a0 = index * step + gap_deg / 2.0
        a1 = (index + 1) * step - gap_deg / 2.0
        idx = supports[index]
        if a1 - a0 <= 0 or idx.size == 0:
            continue
        sector = _sector_mask(theta_f[idx], width_f[idx], a0, a1)

        fraction = max(0.0, min(1.0, value / peak))
        tip = inner + (outer - inner) * fraction
        if fraction <= 0.001:
            tip = inner + 1.5   # muñón mínimo para que se vea la franja vacía
            tone = track_color
        else:
            tone = color
        if highlight is not None and index == highlight and highlight_color:
            tone = highlight_color

        rad = radius_f[idx]
        band = (
            _smoothstep(inner - 1.0, inner + 1.0, rad)
            * (1.0 - _smoothstep(tip - 1.0, tip + 1.0, rad))
        )
        mask = sector * band
        flat[idx] += (np.array(hex_to_rgb(tone), np.float32) - flat[idx]) * mask[:, None]

    return _to_image(buffer)


# --------------------------------------------------------------------------- #
# Formas rectangulares
# --------------------------------------------------------------------------- #

_MASK_CACHE = _LRU(128)


def _rounded_mask(width, height, radius, feather=1.0):
    """Máscara antialiaseada de un rectángulo redondeado (cacheada: no modificarla)."""
    width, height = max(1, int(width)), max(1, int(height))
    radius = float(max(0.0, min(radius, min(width, height) / 2.0)))
    key = ("mask", width, height, radius, feather)
    cached = _MASK_CACHE.get(key)
    if cached is not None:
        return cached
    if radius <= 0.5:
        return _MASK_CACHE.put(key, np.ones((height, width), np.float32))
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dx = np.maximum(np.abs(xx - (width - 1) / 2.0) - ((width - 1) / 2.0 - radius), 0.0)
    dy = np.maximum(np.abs(yy - (height - 1) / 2.0) - ((height - 1) / 2.0 - radius), 0.0)
    dist = np.sqrt(dx * dx + dy * dy)
    return _MASK_CACHE.put(
        key, (1.0 - _smoothstep(radius - feather, radius + feather, dist)).astype(np.float32))


def timeline(
    width,
    height,
    spans,
    background,
    empty_color,
    radius=None,
    gap=0.0,
    empty_alpha=1.0,
):
    """Barra de línea de tiempo.

    spans       -- [(inicio_0a1, fin_0a1, color_hex), ...] en orden cronológico.
    empty_alpha -- α del riel (sobre el fondo ambiental: blanco 0,12).
    Muestra en qué momento de la sesión hubo concentración, descanso o distracción.
    """
    width, height = max(8, int(width)), max(4, int(height))
    radius = height / 2.0 if radius is None else radius

    buffer = _base(background, width, height)
    empty = np.array(hex_to_rgb(empty_color), np.float32)
    shape = _rounded_mask(width, height, radius)
    buffer += (empty - buffer) * (
        shape if empty_alpha >= 1.0 else shape * float(empty_alpha))[..., None]

    xx = np.arange(width, dtype=np.float32)[None, :]
    for start, end, color in spans:
        x0 = float(start) * width
        x1 = float(end) * width
        if x1 - x0 <= 0:
            continue
        x0 += gap / 2.0
        x1 -= gap / 2.0
        if x1 <= x0:
            x1 = x0 + 0.6
        mask = _smoothstep(x0 - 0.5, x0 + 0.5, xx) * (1.0 - _smoothstep(x1 - 0.5, x1 + 0.5, xx))
        mask = np.repeat(mask, height, axis=0) * shape
        rgb = np.array(hex_to_rgb(color), np.float32)
        buffer += (rgb - buffer) * mask[..., None]

    return _to_image(buffer)


def bar_chart(
    width,
    height,
    values,
    background,
    color,
    highlight_color=None,
    highlight_index=None,
    baseline_color=None,
    radius=4,
    gap_ratio=0.34,
    min_height=3,
):
    """Barras verticales con esquinas redondeadas."""
    width, height = max(8, int(width)), max(8, int(height))
    buffer = _base(background, width, height)

    if not values:
        return _to_image(buffer)

    peak = max(values) or 1.0
    slot = width / len(values)
    bar_w = max(2.0, slot * (1.0 - gap_ratio))

    if baseline_color:
        line = np.array(hex_to_rgb(baseline_color), np.float32)
        buffer[height - 1 :, :] += (line - buffer[height - 1 :, :]) * 0.85

    for index, value in enumerate(values):
        h = (max(0.0, value) / peak) * (height - 2)
        if value > 0:
            h = max(h, min_height)
        if h <= 0:
            continue
        h = int(round(h))
        x0 = int(round(index * slot + (slot - bar_w) / 2.0))
        x1 = min(width, x0 + int(round(bar_w)))
        if x1 <= x0:
            continue
        y0 = height - h
        piece = buffer[y0:height, x0:x1]
        # Redondeamos sólo arriba: generamos un rectángulo más alto y cortamos la
        # parte de abajo, así la barra "nace" recta desde el eje.
        corner = min(radius, (x1 - x0) / 2.0)
        tall = _rounded_mask(x1 - x0, h + int(corner) + 2, corner)
        mask = tall[: h, :]
        tone = color
        if highlight_color is not None and index == highlight_index:
            tone = highlight_color
        rgb = np.array(hex_to_rgb(tone), np.float32)
        piece += (rgb - piece) * mask[..., None]

    return _to_image(buffer)


def heatmap(
    columns,
    rows,
    values,
    background,
    empty_color,
    ramp,
    cell=13,
    gap=3,
    radius=3,
):
    """Mapa de calor tipo contribuciones (columnas = semanas, filas = días)."""
    width = columns * cell + (columns - 1) * gap
    height = rows * cell + (rows - 1) * gap
    buffer = _base(background, max(1, width), max(1, height))

    mask = _rounded_mask(cell, cell, radius)
    peak = max((v for v in values.values() if v is not None), default=0) or 1.0
    empty = np.array(hex_to_rgb(empty_color), np.float32)

    for (col, row), value in values.items():
        if not (0 <= col < columns and 0 <= row < rows):
            continue
        x0 = col * (cell + gap)
        y0 = row * (cell + gap)
        if value is None:
            continue
        if value <= 0:
            rgb = empty
        else:
            t = min(1.0, (value / peak) ** 0.6)
            stops = len(ramp) - 1
            pos = t * stops
            low = min(stops, int(pos))
            high = min(stops, low + 1)
            rgb = np.array(hex_to_rgb(mix(ramp[low], ramp[high], pos - low)), np.float32)
        piece = buffer[y0 : y0 + cell, x0 : x0 + cell]
        piece += (rgb - piece) * mask[..., None]

    return _to_image(buffer)


def sparkline(width, height, values, background, color, fill_alpha=0.22, thickness=2.0):
    """Línea suave con relleno degradado debajo."""
    width, height = max(8, int(width)), max(8, int(height))
    buffer = _base(background, width, height)
    if len(values) < 2:
        return _to_image(buffer)

    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 3.0
    points = []
    for i, value in enumerate(values):
        x = i / (len(values) - 1) * (width - 1)
        y = height - pad - ((value - lo) / span) * (height - 2 * pad)
        points.append((x, y))

    # Curva de la serie muestreada por columna (interpolación catmull-rom simple)
    xs = np.array([p[0] for p in points], np.float32)
    ys = np.array([p[1] for p in points], np.float32)
    grid_x = np.arange(width, dtype=np.float32)
    curve = np.interp(grid_x, xs, ys)
    # suavizado leve para que no se vean los quiebres
    if width > 6:
        kernel = np.array([0.15, 0.7, 0.15], np.float32)
        curve = np.convolve(np.pad(curve, 1, mode="edge"), kernel, mode="valid")

    yy = np.arange(height, dtype=np.float32)[:, None]
    rgb = np.array(hex_to_rgb(color), np.float32)

    under = _smoothstep(-0.5, 0.5, yy - curve[None, :])
    gradient = np.clip((yy - curve[None, :]) / max(1.0, height), 0.0, 1.0)
    buffer += (rgb - buffer) * (under * (fill_alpha * (1.0 - gradient)))[..., None]

    line = 1.0 - _smoothstep(thickness / 2.0 - 0.6, thickness / 2.0 + 0.6, np.abs(yy - curve[None, :]))
    buffer += (rgb - buffer) * line[..., None]
    return _to_image(buffer)


#: Color clave para ventanas recortadas. No aparece en ninguna paleta, así que
#: nada del contenido se vuelve transparente por accidente.
TRANSPARENT_KEY = "#FE00FE"


def _rounded_sdf(width, height, radius):
    """Distancia en píxeles al borde del rectángulo redondeado (negativa adentro)."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    half_w, half_h = (width - 1) / 2.0, (height - 1) / 2.0
    radius = float(max(0.0, min(radius, half_w, half_h)))
    dx = np.abs(xx - half_w) - (half_w - radius)
    dy = np.abs(yy - half_h) - (half_h - radius)
    outside = np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2)
    inside = np.minimum(np.maximum(dx, dy), 0.0)
    return outside + inside - radius


def shaped_panel(width, height, radius, fill, border=None, border_width=1.6,
                 key=TRANSPARENT_KEY):
    """Tarjeta redondeada para una ventana sin marco.

    Fuera de la silueta se pinta el color clave, que Windows vuelve
    transparente. El corte tiene que ser duro —sin suavizado— porque cualquier
    píxel a medio camino quedaría teñido de magenta; a cambio, no se ven las
    esquinas cuadradas del fondo de la ventana.
    """
    width, height = max(1, int(width)), max(1, int(height))
    sdf = _rounded_sdf(width, height, radius)

    buffer = np.tile(np.array(hex_to_rgb(fill), np.float32), (height, width, 1))
    if border:
        # El borde va hacia adentro, con transición suave: ahí sí se puede
        # suavizar porque los dos colores son opacos.
        band = _smoothstep(-border_width - 0.5, -border_width + 0.5, sdf)
        buffer += (np.array(hex_to_rgb(border), np.float32) - buffer) * band[..., None]

    keep = (sdf <= 0.0)[..., None]
    return _to_image(np.where(keep, buffer, np.array(hex_to_rgb(key), np.float32)))


def _panel_inner(width, height, radius, border_width):
    """Interior (sin el borde) de `rounded_panel`, cacheado. Misma cuenta de siempre."""
    key = ("panel", width, height, float(radius), float(border_width))
    cached = _MASK_CACHE.get(key)
    if cached is not None:
        return cached
    # erosionamos el rectángulo desplazando el radio
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dx = np.maximum(np.abs(xx - (width - 1) / 2.0) - ((width - 1) / 2.0 - radius), 0.0)
    dy = np.maximum(np.abs(yy - (height - 1) / 2.0) - ((height - 1) / 2.0 - radius), 0.0)
    dist = np.sqrt(dx * dx + dy * dy)
    edge = np.minimum(
        np.minimum(xx, width - 1 - xx), np.minimum(yy, height - 1 - yy)
    )
    inner = (1.0 - _smoothstep(radius - border_width - 1.0, radius - border_width + 0.0, dist))
    inner *= _smoothstep(border_width - 0.5, border_width + 0.5, edge)
    return _MASK_CACHE.put(key, inner)


def rounded_panel(width, height, radius, background, fill, border=None, border_width=1.0):
    """Panel redondeado sólido, opcionalmente con borde de 1px real.

    `background` es un hex o el recorte del fondo (ndarray (alto, ancho, 3)).
    """
    width, height = max(1, int(width)), max(1, int(height))
    buffer = _base(background, width, height)
    outer = _rounded_mask(width, height, radius)
    fill_rgb = np.array(hex_to_rgb(fill), np.float32)
    if border:
        border_rgb = np.array(hex_to_rgb(border), np.float32)
        buffer += (border_rgb - buffer) * outer[..., None]
        inner = _panel_inner(width, height, radius, border_width)
        buffer += (fill_rgb - buffer) * inner[..., None]
    else:
        buffer += (fill_rgb - buffer) * outer[..., None]
    return _to_image(buffer)


# --------------------------------------------------------------------------- #
# Formas con distancia firmada y sombras (DESIGN_SPEC §2.5–2.6)
# --------------------------------------------------------------------------- #

_SDF_CACHE = _LRU(64, maxbytes=64 << 20)
_SHADOW_CACHE = _LRU(64, maxbytes=64 << 20)


def rounded_sdf(width, height, radius, pad=0):
    """Distancia firmada al borde de un rectángulo redondeado de `width`×`height`
    centrado en un lienzo con margen `pad` (negativa adentro). LRU(64).

    Es la del mockup (`mk.sdf_rect`): el radio topa en medio lado + 0,5, así una
    cápsula de alto 52 tiene radio 26 de verdad. El arreglo es de la caché: no
    modificarlo.
    """
    width, height, pad = max(1, int(width)), max(1, int(height)), max(0, int(pad))
    key = (width, height, round(float(radius), 3), pad)
    cached = _SDF_CACHE.get(key)
    if cached is not None:
        return cached
    yy = np.arange(height + 2 * pad, dtype=np.float32)[:, None]
    xx = np.arange(width + 2 * pad, dtype=np.float32)[None, :]
    hw, hh = (width - 1) / 2.0, (height - 1) / 2.0
    r = float(max(0.0, min(radius, hw + 0.5, hh + 0.5)))
    dx = np.abs(xx - pad - hw) - (hw - r)
    dy = np.abs(yy - pad - hh) - (hh - r)
    out = np.sqrt(np.maximum(dx, 0.0) ** 2 + np.maximum(dy, 0.0) ** 2)
    ins = np.minimum(np.maximum(dx, dy), 0.0)
    return _SDF_CACHE.put(key, (out + ins - r).astype(np.float32))


def _spec_values(spec, scale=1.0):
    blur = float(getattr(spec, "blur", 0.0) or 0.0) * scale
    alpha = float(getattr(spec, "alpha", 0.0) or 0.0)
    dy = float(getattr(spec, "dy", 0.0) or 0.0) * scale
    edge = float(getattr(spec, "edge", 0.0) or 0.0)
    return blur, alpha, dy, edge


def shadow_pad(spec, scale=1.0):
    """Margen (px) que necesita la sombra de `spec` alrededor de la forma."""
    blur, _, dy, _ = _spec_values(spec, scale)
    return int(blur * 2 + abs(dy) + 2)


def shadow_alpha(width, height, radius, spec, scale=1.0):
    """α (float32) de sombra proyectada + filo oscuro de 1 px, en un lienzo con
    margen `pad` alrededor de la forma; 0 debajo de la forma. LRU(64).

    spec: cualquier objeto con blur, alpha, dy, edge (`theme.ShadowSpec`), en px
    lógicos; `scale` los lleva a px físicos. Devuelve (alfa, pad).
    """
    width, height = max(1, int(width)), max(1, int(height))
    blur, alpha, dy, edge = _spec_values(spec, scale)
    key = (width, height, round(float(radius), 3), round(blur, 3), round(alpha, 4),
           round(dy, 3), round(edge, 4))
    cached = _SHADOW_CACHE.get(key)
    if cached is not None:
        return cached
    pad = int(blur * 2 + abs(dy) + 2)
    sdf = rounded_sdf(width, height, radius, pad)
    inside = _ss(0.5, -0.5, sdf)
    shadow = np.zeros_like(sdf)
    if alpha > 0 and blur > 0:
        mask = Image.fromarray((inside * 255).astype(np.uint8), "L")
        mask = mask.transform(mask.size, Image.AFFINE, (1, 0, 0, 0, 1, -dy),
                              resample=Image.BILINEAR)
        mask = mask.filter(ImageFilter.GaussianBlur(blur / 2))
        shadow = np.asarray(mask, np.float32) * (alpha / 255.0)
    if edge > 0:
        ring = _ss(1.6, 0.4, sdf) * _ss(-0.4, 0.4, sdf) * edge
        shadow = np.maximum(shadow, ring)
    shadow = (shadow * (1.0 - inside)).astype(np.float32)
    return _SHADOW_CACHE.put(key, (shadow, pad))


def apply_shadows(canvas, shapes, scale=1.0):
    """Oscurece `canvas` (float32 o uint8, (H, W, 3)) en el lugar con las sombras
    de `shapes` = [(x, y, w, h, radio, spec), ...] en coordenadas del canvas;
    recorta a los bordes. Un `spec` None se saltea."""
    H, W = canvas.shape[:2]
    for x, y, w, h, radius, spec in shapes:
        if spec is None:
            continue
        shadow, pad = shadow_alpha(w, h, radius, spec, scale)
        x0, y0 = int(round(x)) - pad, int(round(y)) - pad
        xs0, ys0 = max(0, x0), max(0, y0)
        xs1, ys1 = min(W, x0 + shadow.shape[1]), min(H, y0 + shadow.shape[0])
        if xs1 <= xs0 or ys1 <= ys0:
            continue
        keep = 1.0 - shadow[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
        region = canvas[ys0:ys1, xs0:xs1]
        if region.dtype == np.uint8:
            np.multiply(region, keep[..., None], out=region, casting="unsafe")
        else:
            region *= keep[..., None]


# --------------------------------------------------------------------------- #
# Vidrio (DESIGN_SPEC §2.5, matemática de `mk.glass`)
# --------------------------------------------------------------------------- #

#: Pesos de luminancia (Rec. 709) para la saturación del vidrio.
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)

_GLASS_CACHE = _LRU(64, maxbytes=192 << 20)


@dataclass(eq=False)
class GlassShape:
    """Todo lo del vidrio que depende sólo de la forma (y no del fondo).

    Mapas (alto, ancho) float32: `inside` (cobertura AA), `spec` (brillo
    especular del filo), `sheen` (brillo del 40 % superior), `inner` (sombra
    interior abajo), y los factores ya combinados para el caso normal
    `k1 = (1 − g)·inner`, `k2 = 255·g·inner` con g = spec + sheen. La
    refracción sólo existe en la banda del borde: por cada píxel de la banda,
    su posición (`by`, `bx`), el desplazamiento (redondeado y en float, para
    materializar) y el peso de la muestra nítida `edge_w`. `aa_*` y `out_*`
    son los píxeles del borde suavizado y los de afuera de la forma.
    """

    width: int
    height: int
    radius: float
    scale: float
    sdf: np.ndarray
    inside: np.ndarray
    spec: np.ndarray
    sheen: np.ndarray
    inner: np.ndarray
    k1: np.ndarray
    k2: np.ndarray
    by: np.ndarray
    bx: np.ndarray
    off_y: np.ndarray
    off_x: np.ndarray
    off_yf: np.ndarray
    off_xf: np.ndarray
    edge_w: np.ndarray
    aa_y: np.ndarray
    aa_x: np.ndarray
    aa_v: np.ndarray
    out_y: np.ndarray
    out_x: np.ndarray


def _mat(material, name, default=0.0):
    value = getattr(material, name, default)
    return default if value is None else value


def glass_shape(width, height, radius, material, scale=1.0):
    """Forma de vidrio cacheada por (ancho, alto, radio, parámetros de forma del
    material, escala). LRU(64). `width`/`height`/`radius` en px físicos; las
    medidas del material (refracción, filo) en px lógicos × `scale`."""
    width, height = max(1, int(width)), max(1, int(height))
    s = float(scale)
    lens_px = max(1e-3, float(_mat(material, "lens_px", 10.0)) * s)
    lens_amt = float(_mat(material, "lens_amt", 0.0)) * s
    rim_top = float(_mat(material, "rim_top"))
    rim_base = float(_mat(material, "rim_base"))
    sheen_a = float(_mat(material, "sheen"))
    inner_a = float(_mat(material, "inner_shadow"))
    key = (width, height, round(float(radius), 3), round(lens_px, 4), round(lens_amt, 4),
           rim_top, rim_base, sheen_a, inner_a, round(s, 4))
    cached = _GLASS_CACHE.get(key)
    if cached is not None:
        return cached

    sdf = rounded_sdf(width, height, radius)
    inside = _ss(0.5, -0.5, sdf).astype(np.float32)
    gy, gx = np.gradient(sdf)
    norm = np.sqrt(gx * gx + gy * gy) + 1e-6
    nx, ny = gx / norm, gy / norm
    depth = np.clip(-sdf, 0.0, None)
    # La refracción: cerca del borde el vidrio muestrea "hacia adentro" (lente).
    bend = lens_amt * (1.0 - np.clip(depth / lens_px, 0.0, 1.0)) ** 2
    yy0 = np.arange(height, dtype=np.float32)[:, None]

    rim = _ss(-2.0 * s, -0.6 * s, sdf) * _ss(0.4, -0.4, sdf)
    facing = np.clip(-ny, 0.0, 1.0) ** 1.5 * 0.8 + np.clip(-nx, 0.0, 1.0) ** 2 * 0.2
    spec = (rim * (rim_base + rim_top * facing)).astype(np.float32)
    sheen = (np.clip(1.0 - yy0 / max(height * 0.40, 1.0), 0.0, 1.0) ** 2
             * sheen_a * inside).astype(np.float32)
    inner = (1.0 - _ss(-6.0 * s, -1.0 * s, sdf) * np.clip(ny, 0.0, 1.0)
             * inner_a).astype(np.float32)
    g = np.clip(spec + sheen, 0.0, 1.0)
    k1 = ((1.0 - g) * inner).astype(np.float32)
    k2 = (255.0 * g * inner).astype(np.float32)

    # Banda de refracción: sólo los píxeles de adentro (o del borde) que se
    # desplazan o mezclan la muestra nítida.
    in_band = (bend > 1e-6) & (inside > 0.0)
    by, bx = np.nonzero(in_band)
    off_yf = (-ny * bend)[by, bx].astype(np.float32)
    off_xf = (-nx * bend)[by, bx].astype(np.float32)
    edge_w = (bend[by, bx] / max(lens_amt, 1e-6) * 0.6).astype(np.float32)
    aa = (inside > 0.0) & (inside < 1.0)
    aa_y, aa_x = np.nonzero(aa)
    out_y, out_x = np.nonzero(inside <= 0.0)

    shape = GlassShape(
        width, height, float(radius), s, sdf, inside, spec, sheen, inner, k1, k2,
        by.astype(np.int32), bx.astype(np.int32),
        np.round(off_yf).astype(np.int32), np.round(off_xf).astype(np.int32),
        off_yf, off_xf, edge_w,
        aa_y.astype(np.int32), aa_x.astype(np.int32), inside[aa_y, aa_x].copy(),
        out_y.astype(np.int32), out_x.astype(np.int32))
    return _GLASS_CACHE.put(key, shape)


def _saturation_matrix(sat):
    """Matriz (3×3) que aplicada a filas RGB hace `l + (c − l)·sat`."""
    return (np.eye(3, dtype=np.float32) * sat
            + (1.0 - sat) * LUMA[:, None] * np.ones((1, 3), np.float32)).astype(np.float32)


def _glass_body(sharp, blurred, rect, radius, material, tint, tint_a, fill, press,
                materialize, scale, extend):
    """Compone el vidrio y devuelve (salida uint8, (y0, x0, cobertura)) para quien
    necesite la máscara (glass_rgba)."""
    out = np.array(sharp, dtype=np.uint8, copy=True) if np.asarray(sharp).dtype == np.uint8 \
        else np.clip(sharp, 0, 255).astype(np.uint8)
    H, W = out.shape[:2]
    x, y, w, h = (int(round(v)) for v in rect)
    left, top, right, bottom = (int(round(v)) for v in extend)
    X0, Y0 = x - left, y - top
    SW, SH = w + left + right, h + top + bottom
    m = max(0.0, min(1.0, float(materialize)))
    if m <= 0.0 or SW <= 0 or SH <= 0:
        return out, None
    if m < 1.0:
        # Materializar: la forma crece de 0,94 a 1 desde su centro.
        k = 0.94 + 0.06 * m
        nw, nh = max(1, int(round(SW * k))), max(1, int(round(SH * k)))
        X0 += (SW - nw) // 2
        Y0 += (SH - nh) // 2
        SW, SH, radius = nw, nh, radius * k

    shape = glass_shape(SW, SH, radius, material, scale)
    # Ventana visible de la forma dentro del arreglo.
    ax0, ay0 = max(0, X0), max(0, Y0)
    ax1, ay1 = min(W, X0 + SW), min(H, Y0 + SH)
    if ax1 <= ax0 or ay1 <= ay0:
        return out, None
    sx0, sy0, sx1, sy1 = ax0 - X0, ay0 - Y0, ax1 - X0, ay1 - Y0
    region = out[ay0:ay1, ax0:ax1]
    solid = _mat(material, "solid", None)
    border = _mat(material, "border", None)
    fill = max(0.0, min(1.0, float(fill))) * m
    press = max(0.0, min(1.0, float(press)))

    if solid:
        # Reducir transparencia / Aumentar contraste: cuerpo sólido, sin muestreo.
        color = _rgb32(tint if tint is not None else solid)
        body = np.empty((ay1 - ay0, ax1 - ax0, 3), np.float32)
        body[...] = color * (1.0 - fill) + 255.0 * fill
        spec_k, sheen_k = 0.5, (0.0 if border else 0.5)
    else:
        sharp_a = np.asarray(sharp)
        blur_a = np.asarray(blurred) if blurred is not None else sharp_a
        src = blur_a[ay0:ay1, ax0:ax1, :3].astype(np.float32)
        if m < 1.0:
            # Sin materializar del todo, la lente todavía deja ver el fondo nítido.
            src *= m
            src += sharp_a[ay0:ay1, ax0:ax1, :3].astype(np.float32) * (1.0 - m)
        # Banda del borde: muestra desplazada (refracción) y más nítida.
        by, bx = shape.by, shape.bx
        sel = (by >= sy0) & (by < sy1) & (bx >= sx0) & (bx < sx1)
        if sel.any():
            by, bx = by[sel], bx[sel]
            if m < 1.0:
                oy = np.round(shape.off_yf[sel] * m).astype(np.int32)
                ox = np.round(shape.off_xf[sel] * m).astype(np.int32)
                e = (1.0 - m * (1.0 - shape.edge_w[sel]))[:, None]
            else:
                oy, ox = shape.off_y[sel], shape.off_x[sel]
                e = shape.edge_w[sel][:, None]
            py = np.clip(Y0 + by + oy, 0, H - 1)
            px = np.clip(X0 + bx + ox, 0, W - 1)
            src[by - sy0, bx - sx0] = (blur_a[py, px, :3].astype(np.float32) * (1.0 - e)
                                       + sharp_a[py, px, :3].astype(np.float32) * e)
        # Saturación, tinte y relleno de estado en una sola transformación afín.
        sat = 1.0 + (float(_mat(material, "sat", 1.0)) - 1.0) * m
        a = float(_mat(material, "tint_a") if tint_a is None else tint_a) * m
        a = max(0.0, min(1.0, a))
        t = _rgb32(tint if tint is not None else _mat(material, "tint", "#000000"))
        matrix = _saturation_matrix(sat) * ((1.0 - a) * (1.0 - fill))
        offset = t * (a * (1.0 - fill)) + 255.0 * fill
        body = src.reshape(-1, 3) @ matrix
        body += offset
        body = body.reshape(src.shape)
        spec_k, sheen_k = 1.0, 1.0

    # Brillo especular, sheen y sombra interior: body·k1 + k2.
    win = (slice(sy0, sy1), slice(sx0, sx1))
    if not solid and m >= 1.0 and press <= 0.0:
        k1, k2 = shape.k1[win], shape.k2[win]
    else:
        spec = shape.spec[win] * (spec_k * (1.0 + press))
        g = np.clip((spec + shape.sheen[win] * sheen_k + 0.10 * press) * m, 0.0, 1.0)
        inner = 1.0 - (1.0 - shape.inner[win]) * m
        k1 = (1.0 - g) * inner
        k2 = 255.0 * g * inner
    body *= k1[..., None]
    body += k2[..., None]

    if border:
        # Aumentar contraste: borde interior visible (color, ancho en px lógicos).
        bcolor, bwidth = border
        bw = float(bwidth) * scale
        ring = _ss(-bw - 0.5, -bw + 0.5, shape.sdf[win]) * m
        body += (_rgb32(bcolor) - body) * ring[..., None]
    if solid and m < 1.0:
        body *= m
        body += region.astype(np.float32) * (1.0 - m)

    # Borde suavizado contra lo que había y afuera de la forma, lo que había.
    for ys, xs, values in ((shape.aa_y, shape.aa_x, shape.aa_v),
                           (shape.out_y, shape.out_x, None)):
        sel = (ys >= sy0) & (ys < sy1) & (xs >= sx0) & (xs < sx1)
        if not sel.any():
            continue
        ry, rx = ys[sel] - sy0, xs[sel] - sx0
        if values is None:
            body[ry, rx] = region[ry, rx]
        else:
            v = values[sel][:, None]
            body[ry, rx] = region[ry, rx] * (1.0 - v) + body[ry, rx] * v
    np.clip(body, 0.0, 255.0, out=body)
    region[...] = body
    return out, (Y0, X0, shape.inside)


def glass_compose(sharp, blurred, rect, radius, material, *, tint=None, tint_a=None,
                  fill=0.0, press=0.0, materialize=1.0, scale=1.0, extend=(0, 0, 0, 0)):
    """Devuelve una COPIA de `sharp` (uint8, mismo tamaño) con el cuerpo de vidrio
    compuesto en `rect` = (x, y, ancho, alto), en coordenadas del arreglo.

    sharp, blurred -- el recorte del fondo nítido y el mismo desenfocado
                      (DESIGN_SPEC §2.1), (alto, ancho, 3) uint8 o float32.
    material       -- `theme.Material` (o cualquier objeto con sus atributos).
    tint, tint_a   -- pisan los del material (prominente con su tono, hover).
                      Con `material.solid`, `tint` pisa el color sólido.
    fill           -- relleno blanco de estado (hover 0,07 · presionado 0,16).
    press          -- brillo extra al presionar (0..1).
    materialize    -- m de DESIGN_SPEC §5.1: forma a escala 0,94 + 0,06·m y
                      tinte, especular, sheen, saturación y refracción × m (con
                      m = 0 no se ve nada).
    scale          -- escala de la interfaz (refracción y filos en px lógicos).
    extend         -- (izq, arriba, der, abajo) px que la forma se pasa del rect
                      (barra lateral de borde a borde: sólo se ve su filo derecho).

    No dibuja la sombra proyectada ni el filo oscuro exterior: los pone el host
    con `apply_shadows` (shadow=material.shadow, edge=material.edge_dark).
    """
    out, _ = _glass_body(sharp, blurred, rect, radius, material, tint, tint_a, fill,
                         press, materialize, scale, extend)
    return out


def glass_margin(material, scale=1.0):
    """Margen (px) que deja `glass_rgba` alrededor de la forma cuando dibuja la
    sombra del material (sin foto). 0 si el material no tiene sombra."""
    spec = _mat(material, "shadow", None)
    if spec is None:
        return 0
    return shadow_pad(spec, scale)


def _synthetic_backdrop(width, height, glow_hex, center, radius):
    """Fondo sintético para vidrio sin foto: base oscura con un resplandor suave."""
    base = _rgb32("#0C0A1F")
    yy = np.arange(height, dtype=np.float32)[:, None]
    xx = np.arange(width, dtype=np.float32)[None, :]
    # Degradé vertical apenas más claro arriba (como la luz ambiente).
    top = _rgb32(mix("#0C0A1F", "#5B3FD9", 0.10))
    grad = (yy / max(1.0, height - 1.0))[..., None]
    out = np.empty((height, width, 3), np.float32)
    out[...] = top + (base - top) * grad
    if glow_hex:
        cx, cy = center
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        f = np.exp(-d2 / (2.0 * max(1.0, radius) ** 2)) * 0.35
        out += (_rgb32(glow_hex) - out) * f[..., None]
    return out.astype(np.uint8)


def glass_rgba(behind, size, radius, material, *, tint=None, fill=0.0, materialize=1.0,
               scale=1.0, synthetic=None):
    """RGBA de `size` para ventanas sin marco (avisos, menús, pestaña, splash).

    behind    -- foto de lo que hay detrás (del tamaño `size`; se desenfoca con
                 `material.blur`). Con foto la forma ocupa todo `size`.
    synthetic -- sin foto: hex del color de fase para el vidrio 'hud' sintético
                 (resplandor α 0,18 detrás del anillo, a la izquierda).
    Sin foto y con `material.shadow`, la forma deja alrededor `glass_margin()` px
    de margen donde va la sombra (α del negro): sirve con alfa por píxel; con
    color clave `keyed()` la recorta sola (α < 0,5).
    """
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    spec = _mat(material, "shadow", None)
    pad = 0 if behind is not None else glass_margin(material, scale)
    if 2 * pad >= min(width, height):
        pad = 0
    sw, sh = width - 2 * pad, height - 2 * pad
    m = max(0.0, min(1.0, float(materialize)))

    if behind is not None:
        photo = behind.convert("RGB")
        if photo.size != (width, height):
            photo = photo.resize((width, height), Image.BILINEAR)
        sharp = np.asarray(photo)
        blur_r = float(_mat(material, "blur", 0.0)) * scale
        blurred = np.asarray(blur_image(photo, blur_r)) if blur_r > 0 else sharp
    else:
        sharp = _synthetic_backdrop(width, height, synthetic, (pad + sh / 2.0, pad + sh / 2.0),
                                    sh * 0.9)
        blurred = sharp

    rgb, info = _glass_body(sharp, blurred, (pad, pad, sw, sh), radius, material, tint,
                            None, fill, 0.0, m, scale, (0, 0, 0, 0))
    alpha = np.zeros((height, width), np.float32)
    if info is not None:
        y0, x0, inside = info
        ys0, xs0 = max(0, y0), max(0, x0)
        ys1, xs1 = min(height, y0 + inside.shape[0]), min(width, x0 + inside.shape[1])
        alpha[ys0:ys1, xs0:xs1] = inside[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
    rgb = rgb.astype(np.float32)

    if synthetic and behind is None and info is not None:
        # Resplandor del color de fase detrás del anillo (sobre el tinte).
        yy = np.arange(height, dtype=np.float32)[:, None]
        xx = np.arange(width, dtype=np.float32)[None, :]
        cx, cy, rr = pad + sh / 2.0, pad + sh / 2.0, max(1.0, sh * 0.85)
        glow = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * rr * rr)) * 0.18 * m
        rgb += (_rgb32(synthetic) - rgb) * (glow * alpha)[..., None]

    if pad and spec is not None:
        # Sombra (negro con α) debajo de la forma: "over" con alfa directo.
        sh_a, sh_pad = shadow_alpha(sw, sh, radius, spec, scale)
        shadow = np.zeros((height, width), np.float32)
        oy, ox = pad - sh_pad, pad - sh_pad
        ys0, xs0 = max(0, oy), max(0, ox)
        ys1, xs1 = min(height, oy + sh_a.shape[0]), min(width, ox + sh_a.shape[1])
        shadow[ys0:ys1, xs0:xs1] = sh_a[ys0 - oy:ys1 - oy, xs0 - ox:xs1 - ox] * m
        total = alpha + shadow * (1.0 - alpha)
        safe = np.where(total > 1e-6, total, 1.0)
        rgb *= (alpha / safe)[..., None]
        alpha = total

    out = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha * 255.0 + 0.5, 0, 255)])
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def keyed(rgba, behind, key=TRANSPARENT_KEY, threshold=0.5):
    """RGB para ventanas con color clave: compone el borde suavizado contra
    `behind` (foto o hex) y pone `key` donde α < `threshold` (Windows lo vuelve
    transparente; ningún píxel queda a medio camino con el magenta)."""
    rgba = rgba.convert("RGBA")
    size = rgba.size
    if behind is None:
        behind = "#0C0A1F"
    if isinstance(behind, str):
        back = Image.new("RGB", size, hex_to_rgb(behind))
    else:
        back = behind.convert("RGB")
        if back.size != size:
            back = back.resize(size, Image.BILINEAR)
    alpha = rgba.getchannel("A")
    out = Image.composite(rgba.convert("RGB"), back, alpha)
    cut = int(round(max(0.0, min(1.0, threshold)) * 255))
    hole = alpha.point(lambda v: 255 if v < cut else 0)
    out.paste(hex_to_rgb(key), (0, 0) + size, hole)
    return out


# --------------------------------------------------------------------------- #
# Superficies sólidas (tarjetas, DESIGN_SPEC §2.6)
# --------------------------------------------------------------------------- #


def _card_masks(width, height, radius, scale):
    """Cobertura, filo interior de 1 px y luz superior de una tarjeta (cacheado).

    Sólo se guardan los píxeles que no son "interior liso": el cuerpo de la
    tarjeta es el color de relleno salvo en esa banda del borde."""
    key = ("card", width, height, round(float(radius), 3), round(float(scale), 3))
    cached = _MASK_CACHE.get(key)
    if cached is not None:
        return cached
    sdf = rounded_sdf(width, height, radius)
    inside = _ss(0.5, -0.5, sdf)
    s = float(scale)
    ring = _ss(-1.6 * s, -0.6 * s, sdf) * _ss(0.4, -0.4, sdf)
    # Aumentar contraste: borde opaco de 1 px (× escala) pegado al filo suavizado.
    ring_hc = _ss(-(s + 1.0), -(s + 0.5), sdf)
    yy = np.arange(height, dtype=np.float32)[:, None]
    top = np.broadcast_to(np.clip(1.0 - yy / max(radius * 1.4, 1.0), 0.0, 1.0), sdf.shape)
    ys, xs = np.nonzero((inside < 1.0) | (ring > 0.0) | (ring_hc > 0.0))
    return _MASK_CACHE.put(key, (ys.astype(np.int32), xs.astype(np.int32),
                                 inside[ys, xs].astype(np.float32),
                                 ring[ys, xs].astype(np.float32),
                                 top[ys, xs].astype(np.float32),
                                 ring_hc[ys, xs].astype(np.float32)))


def card_layer(crop, radius, fill_hex, style, scale=1.0):
    """Compone sobre `crop` (alto, ancho, 3) el cuerpo de una tarjeta del tamaño del
    recorte: cuerpo redondeado AA, borde interior de 1 px (blanco α
    `style.border_a`) y luz superior (blanco α `style.top_light_a` que se apaga en
    1,4·r). NO la sombra exterior (la pone el host). Con `style.border_hc`
    (Aumentar contraste) el borde es ese color, opaco y sin luz. Devuelve uint8.
    """
    crop = np.asarray(crop)
    height, width = crop.shape[:2]
    out = np.empty((height, width, 3), np.uint8)
    fill = _rgb32(fill_hex)
    out[...] = np.array(hex_to_rgb(fill_hex), np.uint8)
    if height == 0 or width == 0:
        return out
    ys, xs, inside, ring, top, ring_hc = _card_masks(width, height, radius, scale)
    if ys.size == 0:
        return out
    hc = getattr(style, "border_hc", None)
    body = np.broadcast_to(fill, (ys.size, 3)).astype(np.float32)
    if hc:
        body += (_rgb32(hc) - body) * ring_hc[:, None]
    else:
        light = ring * (float(getattr(style, "border_a", 0.0) or 0.0)
                        + float(getattr(style, "top_light_a", 0.0) or 0.0) * top)
        body += (255.0 - body) * light[:, None]
    under = crop[ys, xs, :3].astype(np.float32)
    v = inside[:, None]
    out[ys, xs] = np.clip(under * (1.0 - v) + body * v, 0, 255)
    return out


# --------------------------------------------------------------------------- #
# Fondo ambiental (DESIGN_SPEC §2.1, matemática de `mk.ambient`)
# --------------------------------------------------------------------------- #


@dataclass
class AmbientLayers:
    """Capas del fondo de una ventana: `base` (manchas A–D, con tramado) y la
    mancha de fase sin color como máscara L (`phase_mask`, 0..255 = f/k), cada una
    también desenfocada para el vidrio. `ambient_compose` las junta."""

    size: tuple[int, int]
    base: Image.Image            # RGB, manchas A–D
    base_blur: Image.Image       # RGB, desenfoque BACKDROP_BLUR
    phase_mask: Image.Image      # L, mancha E sin color (0..255 = f/k)
    phase_mask_blur: Image.Image  # L
    intensity: float = 1.0
    _small_mask: np.ndarray | None = None       # máscara E a 1/4 (recuadro útil)
    _small_mask_blur: np.ndarray | None = None


_AMBIENT_CACHE = _LRU(2)
_DITHER_CACHE = _LRU(2)


def _dither(width, height, seed):
    """Tramado fijo 0/1 (mismo valor en los tres canales) del tamaño pedido."""
    key = (width, height, seed)
    cached = _DITHER_CACHE.get(key)
    if cached is None:
        tile = np.random.default_rng(seed).integers(0, 2, (128, 128, 1), dtype=np.uint8)
        full = np.tile(tile, (height // 128 + 1, width // 128 + 1, 3))[:height, :width]
        cached = _DITHER_CACHE.put(key, Image.fromarray(np.ascontiguousarray(full), "RGB"))
    return cached


def ambient_layers(width, height, *, base_hex, blobs, phase_pos, intensity=1.0,
                   blur_radius=28, seed=7):
    """Capas del fondo ambiental de una ventana de `width`×`height`. LRU(2).

    base_hex  -- color de base (`bg_base`).
    blobs     -- [(cx, cy, r, color, k), ...] manchas A–D en fracciones de la ventana.
    phase_pos -- (cx, cy, r) de la mancha de fase E.
    intensity -- multiplica TODAS las k (Reducir transparencia: 0,5; 0 = plano).
                 También la de la mancha E: `ambient_compose` recibe la k de
                 `PHASE_LIGHT` tal cual.
    Se calcula a 1/4 de resolución en float32 y se agranda con BILINEAR; la base
    lleva un tramado fijo 0/1 (semilla `seed`) para que el degradé no haga
    escalones. El desenfoque es un gaussiano a 1/4 (σ = blur_radius/4).
    """
    w, h = max(1, int(width)), max(1, int(height))
    blobs = tuple((float(cx), float(cy), float(r), str(c).upper(), float(k))
                  for cx, cy, r, c, k in (blobs or ()))
    key = (w, h, base_hex.upper(), blobs, tuple(float(v) for v in phase_pos),
           round(float(intensity), 4), float(blur_radius), seed)
    cached = _AMBIENT_CACHE.get(key)
    if cached is not None:
        return cached

    sw, sh = max(8, w // 4), max(8, h // 4)
    xx = (np.arange(sw, dtype=np.float32) / sw)[None, :]
    yy = (np.arange(sh, dtype=np.float32) / sh)[:, None]
    aspect = w / h
    acc = np.empty((sh, sw, 3), np.float32)
    acc[...] = _rgb32(base_hex)
    gain = max(0.0, float(intensity))
    if gain > 0:
        for cx, cy, r, color, k in blobs:
            d2 = ((xx - cx) * aspect) ** 2 + (yy - cy) ** 2
            f = np.exp(-d2 / (2 * (r * 0.5) ** 2)) * (k * gain)
            acc += (_rgb32(color) - acc) * f[..., None]
    small = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), "RGB")
    base = ImageChops.add(small.resize((w, h), Image.BILINEAR), _dither(w, h, seed))
    blur_small = blur_radius / 4.0
    base_blur = small.filter(ImageFilter.GaussianBlur(blur_small)) if blur_small > 0 else small
    base_blur = base_blur.resize((w, h), Image.BILINEAR)

    pcx, pcy, pr = (float(v) for v in phase_pos)
    d2 = ((xx - pcx) * aspect) ** 2 + (yy - pcy) ** 2
    fe = np.exp(-d2 / (2 * (pr * 0.5) ** 2)) * min(1.0, gain)
    small_mask = np.round(fe * 255.0).astype(np.uint8)
    mask_small = Image.fromarray(small_mask, "L")
    phase_mask = mask_small.resize((w, h), Image.BILINEAR)
    mask_blur = mask_small.filter(ImageFilter.GaussianBlur(blur_small)) if blur_small > 0 \
        else mask_small
    phase_mask_blur = mask_blur.resize((w, h), Image.BILINEAR)

    layers = AmbientLayers((w, h), base, base_blur, phase_mask, phase_mask_blur,
                           float(intensity), small_mask, np.asarray(mask_blur).copy())
    _AMBIENT_CACHE.put(key, layers)
    return layers


def _phase_strips(small, k, size):
    """Recuadros (en px de la ventana) donde la máscara E escalada por k no da cero.

    `lut[v] > 0` sólo si v ≥ ceil(0,5/k); al agrandar con BILINEAR un píxel llega
    a eso sólo si algún vecino de la máscara chica llega, así que alcanza con los
    recuadros de la chica más un píxel chico (4 px) de margen. Se parte en franjas
    horizontales que siguen la elipse de la mancha: PIL mezcla píxel por píxel
    aunque la máscara sea cero, y así se mezcla bastante menos."""
    live = small >= max(1, int(math.ceil(0.5 / k)))
    rows = np.flatnonzero(live.any(axis=1))
    if not rows.size:
        return []
    w, h = size
    sh, sw = small.shape
    fx, fy = w / sw, h / sh
    strips = []
    edges = np.linspace(rows[0], rows[-1] + 1, 9).astype(int)
    for r0, r1 in zip(edges[:-1], edges[1:]):
        if r1 <= r0:
            continue
        a0, a1 = max(0, r0 - 1), min(sh, r1 + 1)
        cols = np.flatnonzero(live[a0:a1].any(axis=0))
        if not cols.size:
            continue
        y0 = 0 if r0 == rows[0] else int(r0 * fy)
        y1 = h if r1 == rows[-1] + 1 else int(r1 * fy)
        y0 = max(0, y0 - (6 if r0 == rows[0] else 0))
        y1 = min(h, y1 + (6 if r1 == rows[-1] + 1 else 0))
        x0 = max(0, int(cols[0] * fx) - 6)
        x1 = min(w, int(math.ceil((cols[-1] + 1) * fx)) + 6)
        if y1 > y0 and x1 > x0:
            strips.append((x0, y0, x1, y1))
    return strips


def ambient_compose(layers, color_hex, k, *, blurred=False):
    """Fondo de una fase: `composite(color_E, base, máscara_E · k)` (en C, una
    composición por llamada; el fundido de fase sólo interpola color y k).
    `blurred=True` usa las capas desenfocadas (para el vidrio). Devuelve RGB."""
    base = layers.base_blur if blurred else layers.base
    mask = layers.phase_mask_blur if blurred else layers.phase_mask
    k = max(0.0, min(1.0, float(k)))
    if k <= 0.0:
        return base.copy()
    lut = [int(v * k + 0.5) for v in range(256)]
    small = getattr(layers, "_small_mask_blur" if blurred else "_small_mask", None)
    strips = _phase_strips(small, k, layers.size) if small is not None \
        else [(0, 0) + tuple(layers.size)]
    out = base.copy()
    if not strips:
        return out
    rgb = hex_to_rgb(color_hex)
    for box in strips:
        size = (box[2] - box[0], box[3] - box[1])
        out.paste(Image.new("RGB", size, rgb), box, mask.crop(box).point(lut))
    return out


# --------------------------------------------------------------------------- #
# Texto sobre imagen
# --------------------------------------------------------------------------- #

_FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}


def _bundled_font(name="Inter-Regular.ttf"):
    """Ruta de una tipografía empaquetada en assets/fonts (como config.resource_dir)."""
    if getattr(sys, "frozen", False):
        root = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "assets", "fonts", name)


def load_font(paths, size):
    key = (tuple(paths), size)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    font = None
    for path in paths:
        try:
            font = ImageFont.truetype(path, size)
            break
        except Exception:
            continue
    if font is None:
        # Respaldo: Inter empaquetada antes que las del sistema.
        for fallback in (_bundled_font(), "segoeui.ttf", "arial.ttf"):
            try:
                font = ImageFont.truetype(fallback, size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _font_px(font):
    return float(getattr(font, "size", 0) or 0)


def text_width(font, text, tracking_em=0.0):
    """Ancho de `text` con tracking (en em) entre letras."""
    if not text:
        return 0.0
    return float(font.getlength(text)) + tracking_em * _font_px(font) * (len(text) - 1)


def draw_text(image, xy, text, font, color, anchor="la", tracking_em=0.0):
    """Texto sobre `image`. Con `tracking_em` se dibuja letra por letra midiendo los
    prefijos (no se pierde el kerning); sin tracking, igual que siempre."""
    draw = ImageDraw.Draw(image)
    fill = _ink(color)
    if not tracking_em or len(text) < 2:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        return image
    size = _font_px(font)
    total = text_width(font, text, tracking_em)
    x, y = xy
    if anchor[0] == "m":
        x -= total / 2.0
    elif anchor[0] == "r":
        x -= total
    vertical = anchor[1] if len(anchor) > 1 else "a"
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        draw.text((x + font.getlength(text[:i]) + i * tracking_em * size, y), ch,
                  font=font, fill=fill, anchor="l" + vertical)
    return image


def _ellipsize(font, line, max_width, tracking_em):
    line = line.rstrip()
    while line and text_width(font, line + "…", tracking_em) > max_width:
        line = line[:-1].rstrip()
    return line + "…"


def wrap_text(font, text, max_width, max_lines=2, tracking_em=0.0):
    """Parte `text` en líneas de hasta `max_width` px (como mucho `max_lines`); si
    sobra texto, la última termina en "…". Respeta los saltos de línea y corta
    por letras las palabras que no entran solas."""
    max_lines = max(1, int(max_lines))

    def fits(s):
        return text_width(font, s, tracking_em) <= max_width

    lines = []
    for paragraph in str(text).split("\n"):
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}" if current else word
            if fits(candidate):
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""
            while word and not fits(word):
                cut = len(word) - 1
                while cut > 1 and not fits(word[:cut]):
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        if current or not paragraph.strip():
            lines.append(current)
    while lines and not lines[-1]:
        lines.pop()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(font, lines[-1], max_width, tracking_em)
    return lines


_CLOCK_CACHE = _LRU(16)


def _clock_metrics(font):
    """Celdas del reloj para una fuente: ancho de celda (el dígito más ancho),
    ancho de los dos puntos, alturas de cifras y de ':' y los glifos como
    máscaras L (cacheadas: el reloj cambia por segundo)."""
    key = (id(font), getattr(font, "path", None), _font_px(font))
    cached = _CLOCK_CACHE.get(key)
    if cached is not None:
        return cached
    cell = max(font.getlength(c) for c in "0123456789")
    colon = font.getlength(":") * 0.90
    _, d0, _, d1 = font.getbbox("0", anchor="ls")
    _, c0, _, c1 = font.getbbox(":", anchor="ls")
    metrics = {"cell": cell, "colon": colon, "digit": (d0, d1), "colon_y": (c0, c1),
               "glyphs": {}, "font": font}
    _CLOCK_CACHE.put(key, metrics)
    return metrics


def _glyph(metrics, ch):
    """Máscara L del carácter con ancla "ms" y su desplazamiento (cacheada)."""
    glyph = metrics["glyphs"].get(ch)
    if glyph is None:
        font = metrics["font"]
        x0, y0, x1, y1 = font.getbbox(ch, anchor="ms")
        mask = Image.new("L", (max(1, x1 - x0), max(1, y1 - y0)), 0)
        ImageDraw.Draw(mask).text((-x0, -y0), ch, font=font, fill=255, anchor="ms")
        glyph = metrics["glyphs"][ch] = (mask, x0, y0)
    return glyph


def _clock_layout(font, text, tracking_em):
    metrics = _clock_metrics(font)
    widths = [metrics["cell"] if c.isdigit() else metrics["colon"] if c == ":"
              else font.getlength(c) for c in text]
    gap = tracking_em * _font_px(font)
    total = sum(widths) + gap * max(0, len(text) - 1)
    return metrics, widths, gap, total


def clock_size(font, text, tracking_em=-0.01):
    """(ancho, alto) del reloj tabular: el alto es el de las cifras."""
    metrics, _, _, total = _clock_layout(font, text, tracking_em)
    d0, d1 = metrics["digit"]
    return int(math.ceil(total)), int(d1 - d0)


def draw_clock(image, xy, text, font, color, *, tracking_em=-0.01, anchor="mm"):
    """Reloj con cifras tabulares: cada dígito en una celda del ancho del más ancho
    y los dos puntos centrados en la altura de las cifras (como SF; ver `mk.clock`).
    Así "11:11" y "00:00" miden igual y el reloj no "baila" al cambiar.

    anchor -- horizontal l/m/r y vertical m (centro de las cifras), s (línea de
              base), t (arriba de las cifras) o b (abajo). Devuelve (ancho, alto).
    """
    metrics, widths, gap, total = _clock_layout(font, text, tracking_em)
    d0, d1 = metrics["digit"]
    c0, c1 = metrics["colon_y"]
    x, y = xy
    horizontal = anchor[0] if anchor else "m"
    vertical = anchor[1] if len(anchor) > 1 else "m"
    if horizontal == "m":
        x -= total / 2.0
    elif horizontal == "r":
        x -= total
    if vertical == "m":
        base = y - (d0 + d1) / 2.0
    elif vertical == "t":
        base = y - d0
    elif vertical == "b":
        base = y - d1
    else:
        base = y
    center = base + (d0 + d1) / 2.0
    base_colon = center - (c0 + c1) / 2.0
    fill = _ink(color)
    if image.mode == "RGBA" and len(fill) == 3:
        fill = fill + (255,)
    for ch, w in zip(text, widths):
        if ch != " ":
            mask, gx, gy = _glyph(metrics, ch)
            px = int(round(x + w / 2.0 + gx))
            py = int(round((base_colon if ch == ":" else base) + gy))
            image.paste(fill, (px, py, px + mask.width, py + mask.height), mask)
        x += w + gap
    return int(math.ceil(total)), int(d1 - d0)


def to_photo(image):
    return ImageTk.PhotoImage(image)


def speaker_icon(size, color, background, muted=False):
    """Parlante para el control de volumen; tachado cuando está en silencio.

    `background` es un hex o el recorte del fondo (ndarray (size, size, 3))."""
    size = max(12, int(size))
    scale = 4                       # se dibuja en grande y se reduce: sale suave
    big = size * scale
    vector = not isinstance(background, str)
    if vector:
        image = Image.new("L", (big, big), 0)
        rgb = 255
    else:
        image = Image.new("RGB", (big, big), hex_to_rgb(background))
        rgb = hex_to_rgb(color)
    draw = ImageDraw.Draw(image)
    unit = big / 24.0

    # Cuerpo del parlante: el rectángulo pegado al cono.
    draw.rectangle((3 * unit, 9 * unit, 8 * unit, 15 * unit), fill=rgb)
    draw.polygon([(8 * unit, 9 * unit), (14 * unit, 4 * unit),
                  (14 * unit, 20 * unit), (8 * unit, 15 * unit)], fill=rgb)

    if muted:
        # Raya en diagonal, como en cualquier reproductor.
        draw.line((4 * unit, 20 * unit, 20 * unit, 4 * unit), fill=rgb,
                  width=int(2.1 * unit))
    else:
        for radius, width in ((4.5, 1.6), (7.5, 1.6)):
            box = (14 * unit - radius * unit, 12 * unit - radius * unit,
                   14 * unit + radius * unit, 12 * unit + radius * unit)
            draw.arc(box, start=-55, end=55, fill=rgb, width=int(width * unit))

    if not vector:
        return image.resize((size, size), Image.LANCZOS)
    # Sobre un recorte del fondo: la forma es una máscara que se compone encima.
    mask = np.asarray(image.resize((size, size), Image.LANCZOS), np.float32)[..., None] / 255.0
    mask[mask < 3.0 / 255.0] = 0.0     # el "rebote" de LANCZOS no ensucia el fondo
    buffer = _base(background, size, size)
    buffer += (np.array(hex_to_rgb(color), np.float32) - buffer) * mask
    return _to_image(buffer)


# --------------------------------------------------------------------------- #
# Utilidades de composición
# --------------------------------------------------------------------------- #


def composite(base, overlay, x, y):
    """Compone `overlay` (imagen RGBA, o ndarray (h, w, 4)) sobre `base` (ndarray
    (H, W, 3) uint8 o float32) en el lugar, con su esquina en (x, y); recorta a
    los bordes."""
    ov = np.asarray(overlay.convert("RGBA") if isinstance(overlay, Image.Image) else overlay)
    H, W = base.shape[:2]
    h, w = ov.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    piece = ov[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    alpha = piece[..., 3:4] / 255.0
    region = base[y0:y1, x0:x1]
    mixed = region[..., :3].astype(np.float32)
    mixed += (piece[..., :3] - mixed) * alpha
    if base.dtype == np.uint8:
        region[..., :3] = np.clip(mixed + 0.5, 0, 255)
    else:
        region[..., :3] = mixed


def blur_image(image, radius, scale=4):
    """Desenfoque barato: achicar a 1/scale, gaussiano (σ = radius/scale) y volver a
    agrandar. Para fotos de lo que hay detrás de una ventana sin marco."""
    if radius <= 0:
        return image.copy()
    width, height = image.size
    factor = max(1, int(scale))
    if min(width, height) < 2 * factor:
        factor = 1
    small = image.reduce(factor) if factor > 1 else image
    small = small.filter(ImageFilter.GaussianBlur(radius / factor))
    return small.resize((width, height), Image.BILINEAR) if factor > 1 else small


def mean_hex(array):
    """Color promedio de un recorte (alto, ancho, 3) como hex."""
    arr = np.asarray(array)
    if arr.size == 0:
        return "#000000"
    return rgb_to_hex(arr.reshape(-1, arr.shape[-1])[:, :3].mean(axis=0))
