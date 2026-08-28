"""Renderizado de gráficos con antialiasing real.

Todo se dibuja con numpy sobre un buffer float32 y se compone contra el color de
fondo del widget. Los bordes se suavizan con `smoothstep` sobre la distancia al
borde (en píxeles), así que salen limpios a cualquier tamaño y sin el escalonado
de `tk.Canvas.create_arc` ni el peso de matplotlib.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

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


# --------------------------------------------------------------------------- #
# Utilidades numpy
# --------------------------------------------------------------------------- #


def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / max(1e-6, (edge1 - edge0)), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _grid(size):
    """Grilla de coordenadas (yy, xx) cacheada por tamaño."""
    cached = _GRID_CACHE.get(size)
    if cached is None:
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        if len(_GRID_CACHE) > 12:
            _GRID_CACHE.clear()
        cached = _GRID_CACHE[size] = (yy, xx)
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
    result = (radius, angle)
    if len(_POLAR_CACHE) > 12:
        _POLAR_CACHE.clear()
    _POLAR_CACHE[size] = result
    return result


_POLAR_CACHE: dict[int, tuple] = {}
_GRID_CACHE: dict[int, tuple] = {}
_FEATHER_CACHE: dict[tuple, np.ndarray] = {}
_RING_CACHE: dict[tuple, np.ndarray] = {}
_THETA_CACHE: dict[tuple, np.ndarray] = {}


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
        cached = np.degrees(feather_px / np.maximum(radius, 1.0)).astype(np.float32)
        if len(_FEATHER_CACHE) > 12:
            _FEATHER_CACHE.clear()
        _FEATHER_CACHE[key] = cached
    return cached


def _theta_from(size, start_deg):
    """Ángulo normalizado a 0..360 desde `start_deg`. Cacheado."""
    key = (size, round(float(start_deg), 3))
    cached = _THETA_CACHE.get(key)
    if cached is None:
        _, angle = _polar(size)
        cached = ((angle - start_deg) % 360.0).astype(np.float32)
        if len(_THETA_CACHE) > 12:
            _THETA_CACHE.clear()
        _THETA_CACHE[key] = cached
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
        cached = (
            _smoothstep(inner - feather, inner + feather, radius)
            * (1.0 - _smoothstep(outer - feather, outer + feather, radius))
        ).astype(np.float32)
        if len(_RING_CACHE) > 16:
            _RING_CACHE.clear()
        _RING_CACHE[key] = cached
    return cached


def _to_image(buffer):
    return Image.fromarray(np.clip(buffer, 0, 255).astype(np.uint8), "RGB")


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

    segments -- [(valor, color_hex), ...]
    track    -- color del anillo de fondo cuando no hay datos
    glow     -- 0..1, halo suave del color dominante detrás del anillo
    """
    size = max(24, int(size))
    radius, angle = _polar(size)

    outer = size / 2.0 - padding
    inner = outer * inner_ratio
    ring = _ring_mask(size, inner, outer)

    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (size, size, 1))

    colors = [c for _, c in segments]
    values = [max(0.0, float(v)) for v, _ in segments]
    total = sum(values)

    if glow > 0.0 and total > 0:
        dominant = max(zip(values, colors), key=lambda p: p[0])[1]
        halo = (1.0 - _smoothstep(outer * 0.55, outer * 1.16, radius)) * float(glow)
        buffer += (np.array(hex_to_rgb(dominant), np.float32) - base) * halo[..., None]

    if total <= 0:
        color = np.array(hex_to_rgb(track or mix(background, "#FFFFFF", 0.08)), np.float32)
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
):
    """Anillo de progreso con puntas redondeadas."""
    size = max(24, int(size))
    radius, angle = _polar(size)

    outer = size / 2.0 - padding
    band = max(2.0, outer * thickness * 2.0)
    inner = max(1.0, outer - band)
    mid = (outer + inner) / 2.0
    feather = 1.0

    ring = _ring_mask(size, inner, outer)

    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (size, size, 1))
    buffer += (np.array(hex_to_rgb(track_color), np.float32) - buffer) * ring[..., None]

    fraction = max(0.0, min(1.0, float(fraction)))
    if fraction <= 0.0:
        return _to_image(buffer)

    if fraction >= 0.999:
        mask = ring.copy()
    else:
        theta = _theta_from(size, start_deg)
        mask = _sector_mask(theta, _feather_width(size), 0.0, fraction * 360.0) * ring
    sweep = fraction * 360.0

    if cap_round and fraction < 0.999:
        cap_r = band / 2.0
        yy, xx = _grid(size)
        for deg in (start_deg, start_deg + sweep):
            rad = math.radians(deg)
            cx = (size - 1) / 2.0 + math.cos(rad) * mid
            cy = (size - 1) / 2.0 + math.sin(rad) * mid
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            mask = np.maximum(mask, 1.0 - _smoothstep(cap_r - feather, cap_r + feather, dist))

    buffer += (np.array(hex_to_rgb(color), np.float32) - buffer) * mask[..., None]
    return _to_image(buffer)


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
    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (size, size, 1))

    count = max(1, len(values))
    step = 360.0 / count
    peak = max(values) if values and max(values) > 0 else 1.0

    # Anillo tenue de referencia: marca dónde estaría el máximo.
    guide = _ring_mask(size, outer - 1.2, outer)
    buffer += (np.array(hex_to_rgb(track_color), np.float32) - buffer) * (guide * 0.5)[..., None]

    for index, value in enumerate(values):
        a0 = index * step + gap_deg / 2.0
        a1 = (index + 1) * step - gap_deg / 2.0
        sector = _sector_mask(theta, width, a0, a1)
        if sector is None:
            continue

        fraction = max(0.0, min(1.0, value / peak))
        tip = inner + (outer - inner) * fraction
        if fraction <= 0.001:
            tip = inner + 1.5   # muñón mínimo para que se vea la franja vacía
            tone = track_color
        else:
            tone = color
        if highlight is not None and index == highlight and highlight_color:
            tone = highlight_color

        band = (
            _smoothstep(inner - 1.0, inner + 1.0, radius)
            * (1.0 - _smoothstep(tip - 1.0, tip + 1.0, radius))
        )
        mask = sector * band
        buffer += (np.array(hex_to_rgb(tone), np.float32) - buffer) * mask[..., None]

    return _to_image(buffer)


# --------------------------------------------------------------------------- #
# Formas rectangulares
# --------------------------------------------------------------------------- #


def _rounded_mask(width, height, radius, feather=1.0):
    """Máscara antialiaseada de un rectángulo redondeado."""
    width, height = max(1, int(width)), max(1, int(height))
    radius = float(max(0.0, min(radius, min(width, height) / 2.0)))
    if radius <= 0.5:
        return np.ones((height, width), np.float32)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    dx = np.maximum(np.abs(xx - (width - 1) / 2.0) - ((width - 1) / 2.0 - radius), 0.0)
    dy = np.maximum(np.abs(yy - (height - 1) / 2.0) - ((height - 1) / 2.0 - radius), 0.0)
    dist = np.sqrt(dx * dx + dy * dy)
    return (1.0 - _smoothstep(radius - feather, radius + feather, dist)).astype(np.float32)


def timeline(
    width,
    height,
    spans,
    background,
    empty_color,
    radius=None,
    gap=0.0,
):
    """Barra de línea de tiempo.

    spans -- [(inicio_0a1, fin_0a1, color_hex), ...] en orden cronológico.
    Muestra en qué momento de la sesión hubo concentración, descanso o distracción.
    """
    width, height = max(8, int(width)), max(4, int(height))
    radius = height / 2.0 if radius is None else radius

    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (height, width, 1))
    empty = np.array(hex_to_rgb(empty_color), np.float32)
    shape = _rounded_mask(width, height, radius)
    buffer += (empty - buffer) * shape[..., None]

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
    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (height, width, 1))

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
    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (max(1, height), max(1, width), 1))

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
    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (height, width, 1))
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


def rounded_panel(width, height, radius, background, fill, border=None, border_width=1.0):
    """Panel redondeado sólido, opcionalmente con borde de 1px real."""
    width, height = max(1, int(width)), max(1, int(height))
    base = np.array(hex_to_rgb(background), np.float32)
    buffer = np.tile(base, (height, width, 1))
    outer = _rounded_mask(width, height, radius)
    fill_rgb = np.array(hex_to_rgb(fill), np.float32)
    if border:
        border_rgb = np.array(hex_to_rgb(border), np.float32)
        buffer += (border_rgb - buffer) * outer[..., None]
        inner = _rounded_mask(width, height, radius, feather=1.0)
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
        buffer += (fill_rgb - buffer) * inner[..., None]
    else:
        buffer += (fill_rgb - buffer) * outer[..., None]
    return _to_image(buffer)


# --------------------------------------------------------------------------- #
# Texto sobre imagen (para el popup de hashtags y las leyendas)
# --------------------------------------------------------------------------- #

_FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}


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
        for fallback in ("segoeui.ttf", "arial.ttf"):
            try:
                font = ImageFont.truetype(fallback, size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def draw_text(image, xy, text, font, color, anchor="la"):
    draw = ImageDraw.Draw(image)
    draw.text(xy, text, font=font, fill=hex_to_rgb(color), anchor=anchor)
    return image


def to_photo(image):
    return ImageTk.PhotoImage(image)


def speaker_icon(size, color, background, muted=False):
    """Parlante para el control de volumen; tachado cuando está en silencio."""
    size = max(12, int(size))
    scale = 4                       # se dibuja en grande y se reduce: sale suave
    big = size * scale
    image = Image.new("RGB", (big, big), hex_to_rgb(background))
    draw = ImageDraw.Draw(image)
    rgb = hex_to_rgb(color)
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

    return image.resize((size, size), Image.LANCZOS)
