"""Íconos propios de Focus Flow, dibujados con numpy y Pillow.

Juego al estilo de SF Symbols (DESIGN_SPEC §2.10), pero propio: la licencia de los
SF Symbols no permite usarlos en Windows. Cada ícono se describe en una grilla de
24 unidades con trazos (segmentos, arcos, curvas, círculos) y rellenos (polígonos
con esquinas redondeadas, puntos). Para dibujarlo se calcula la distancia de cada
píxel a la forma a 4× del tamaño final y se reduce con LANCZOS: puntas y uniones
salen redondeadas solas y los bordes quedan suaves a cualquier tamaño.

El trazo mide 1,75 px a 18 px y escala con el tamaño (mínimo 1,5 px), igual en
todos los íconos, así acompaña el peso del texto vecino. La salida es RGBA de un
solo color: el alfa es la cobertura, así se compone sobre cualquier fondo.
"""

from __future__ import annotations

import math
from collections import OrderedDict

import numpy as np
from PIL import Image

__all__ = ["NAMES", "icon", "paste_icon"]

GRID = 24.0                 # unidades de diseño por lado
_REACH = 10.25              # lo más lejos del centro que llega un dibujo (sin el trazo)
SUPERSAMPLE = 4             # se dibuja a 4× y se reduce
STROKE_AT_18 = 1.75         # trazo en px a 18 px
MIN_STROKE = 1.5            # nunca más fino que esto (a escala 1)
CACHE_SIZE = 256            # íconos coloreados (nombre, tamaño, color, trazo)
MASK_CACHE_SIZE = 128       # coberturas sin color: cambiar de color no redibuja

# --------------------------------------------------------------------------- #
# Geometría en unidades de la grilla (puras, sin numpy)
# --------------------------------------------------------------------------- #


def _arc_points(cx, cy, r, start, end, step=5.0):
    """Puntos de un arco; ángulos en grados, 0 a la derecha y creciendo en el
    sentido de las agujas del reloj (como en pantalla, con y hacia abajo)."""
    count = max(2, int(math.ceil(abs(end - start) / step)) + 1)
    return [(cx + r * math.cos(math.radians(start + (end - start) * i / (count - 1))),
             cy + r * math.sin(math.radians(start + (end - start) * i / (count - 1))))
            for i in range(count)]


def _bezier(p0, p1, p2, p3, count=16):
    """Curva cúbica muestreada (sin el primer punto, para encadenar tramos)."""
    points = []
    for i in range(1, count + 1):
        t = i / count
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        points.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                       a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return points


def _curve(start, *segments):
    """Camino de cúbicas encadenadas: segments = (c1, c2, fin), (c1, c2, fin)…"""
    points = [start]
    for c1, c2, end in segments:
        points += _bezier(points[-1], c1, c2, end)
    return points


def _fillet(points, radius, closed=False):
    """Redondea las esquinas de una poligonal con arcos de `radius` tangentes a
    los lados (los lados no se mueven: el ícono conserva su tamaño)."""
    n = len(points)
    if radius <= 0 or n < 3:
        return list(points)
    out = []
    indices = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(points[0])
    for i in indices:
        bx, by = points[i]
        ax, ay = points[i - 1]
        cx, cy = points[(i + 1) % n]
        ux, uy = ax - bx, ay - by
        vx, vy = cx - bx, cy - by
        lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
        if lu == 0 or lv == 0:
            out.append((bx, by))
            continue
        ux, uy, vx, vy = ux / lu, uy / lu, vx / lv, vy / lv
        angle = math.acos(max(-1.0, min(1.0, ux * vx + uy * vy)))
        if angle < 1e-3 or abs(angle - math.pi) < 1e-3:
            out.append((bx, by))
            continue
        # La tangente no puede pasar de la mitad de cada lado.
        r = min(radius, math.tan(angle / 2) * min(lu, lv) / 2)
        t = r / math.tan(angle / 2)
        hx, hy = ux + vx, uy + vy
        hl = math.hypot(hx, hy)
        ox = bx + hx / hl * r / math.sin(angle / 2)
        oy = by + hy / hl * r / math.sin(angle / 2)
        a0 = math.degrees(math.atan2(by + uy * t - oy, bx + ux * t - ox))
        a1 = math.degrees(math.atan2(by + vy * t - oy, bx + vx * t - ox))
        sweep = (a1 - a0 + 180.0) % 360.0 - 180.0      # el arco corto
        out += _arc_points(ox, oy, r, a0, a0 + sweep, step=10.0)
    if not closed:
        out.append(points[-1])
    return out


def _scaled(points, factor, cx=12.0, cy=12.0):
    """Agranda o achica una poligonal alrededor del centro de la grilla."""
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in points]


# --------------------------------------------------------------------------- #
# Lienzo de cobertura
# --------------------------------------------------------------------------- #


class _Pen:
    """Cobertura a 4× en un arreglo float32. Las formas se piden en unidades de
    la grilla y devuelven su distancia con signo (negativa adentro); `stroke`,
    `fill` y `cut` la convierten en cobertura con un borde de un subpíxel."""

    def __init__(self, px, stroke_px):
        big = px * SUPERSAMPLE
        self.px = px
        self.big = big
        # Con un trazo más grueso que el de diseño (el mínimo de 1,5 px a menos de
        # 15 px, o un `weight` grande) el dibujo se achica alrededor del centro lo
        # justo para que el trazo extra no se salga de la caja.
        nominal = STROKE_AT_18 / 18.0 * GRID / 2.0
        half = stroke_px * GRID / px / 2.0
        zoom = 1.0 if half <= nominal else max(0.75, (_REACH + nominal - half) / _REACH)
        self.unit = px * zoom / GRID                          # px por unidad
        self.k = self.unit * SUPERSAMPLE                      # subpíxeles por unidad
        axis = (np.arange(big, dtype=np.float32) + 0.5) / SUPERSAMPLE
        axis = GRID / 2.0 + (axis - px / 2.0) / self.unit
        self.x = axis[None, :]
        self.y = axis[:, None]
        self.half = stroke_px / 2.0 / self.unit              # medio trazo en unidades
        # Más allá de este margen la distancia exacta no cambia nada.
        self.margin = self.half * 2.5 + 2.0
        self.alpha = np.zeros((big, big), np.float32)

    # --- ajuste a la grilla de píxeles -------------------------------------- #

    def to_px(self, value):
        """Unidades de la grilla -> px del ícono."""
        return self.px / 2.0 + (value - GRID / 2.0) * self.unit

    def to_units(self, pos):
        """px del ícono -> unidades de la grilla."""
        return GRID / 2.0 + (pos - self.px / 2.0) / self.unit

    def _snap(self, value, odd, reach=0.0):
        """Lleva `value` (unidades) al borde de píxel más cercano o, con `odd`, al
        centro de píxel más cercano. Los empates se alejan del centro del ícono: las
        formas simétricas siguen simétricas y los detalles no se pegan. Con
        `reach` (px a cada lado) no deja que la forma se salga de la caja."""
        pos = self.to_px(value)
        shift = 0.5 if odd else 0.0
        lo = math.floor(pos - shift) + shift
        hi = lo + 1.0
        if abs((pos - lo) - (hi - pos)) < 1e-6:
            target = hi if pos > self.px / 2 else lo
        else:
            target = lo if pos - lo < hi - pos else hi
        if target - reach < 0.25:
            target += 1.0
        elif target + reach > self.px - 0.25:
            target -= 1.0
        return self.to_units(target)

    def s(self, value, weight=1.0):
        """Centro de un trazo horizontal o vertical: queda nítido (un trazo de
        ancho par en píxeles va sobre un borde; uno impar, sobre un centro)."""
        width = self.half * 2.0 * weight * self.unit
        return self._snap(value, int(round(width)) % 2 == 1, width / 2.0)

    def e(self, value):
        """Borde de un relleno: sobre el borde de píxel más cercano."""
        return self._snap(value, False)

    # --- distancias ------------------------------------------------------- #

    def _window(self, lo, hi, axis_len):
        a = max(0, int(math.floor(self.to_px(lo - self.margin) * SUPERSAMPLE)))
        b = min(axis_len, int(math.ceil(self.to_px(hi + self.margin) * SUPERSAMPLE)) + 1)
        return a, b

    def path(self, points, closed=False):
        """Distancia a una poligonal; con `closed`, con signo (par-impar)."""
        big = self.big
        d2 = np.full((big, big), self.margin * self.margin, np.float32)
        pts = list(points)
        pairs = list(zip(pts, pts[1:] + pts[:1])) if closed else list(zip(pts, pts[1:]))
        for (x0, y0), (x1, y1) in pairs:
            i0, i1 = self._window(min(y0, y1), max(y0, y1), big)
            j0, j1 = self._window(min(x0, x1), max(x0, x1), big)
            if i0 >= i1 or j0 >= j1:
                continue
            px = self.x[:, j0:j1] - x0
            py = self.y[i0:i1, :] - y0
            dx, dy = x1 - x0, y1 - y0
            length2 = dx * dx + dy * dy
            if length2 > 0:
                t = np.clip((px * dx + py * dy) / length2, 0.0, 1.0)
                ex, ey = px - t * dx, py - t * dy
            else:
                ex, ey = px + 0 * py, py + 0 * px
            np.minimum(d2[i0:i1, j0:j1], ex * ex + ey * ey, out=d2[i0:i1, j0:j1])
        dist = np.sqrt(d2)
        if not closed:
            return dist
        inside = np.zeros((big, big), bool)
        ys = self.y[:, 0]
        for (x0, y0), (x1, y1) in pairs:
            if y0 == y1:
                continue
            rows = (ys >= min(y0, y1)) & (ys < max(y0, y1))
            if not rows.any():
                continue
            cross = x0 + (ys[rows] - y0) * (x1 - x0) / (y1 - y0)
            inside[rows] ^= self.x < cross[:, None]
        return np.where(inside, -dist, dist)

    def circle(self, cx, cy, r):
        return np.hypot(self.x - cx, self.y - cy) - r

    def box(self, x0, y0, x1, y1, r=0.0):
        """Rectángulo con esquinas redondeadas (distancia exacta, sin poligonal)."""
        r = min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0)
        qx = np.abs(self.x - (x0 + x1) / 2.0) - ((x1 - x0) / 2.0 - r)
        qy = np.abs(self.y - (y0 + y1) / 2.0) - ((y1 - y0) / 2.0 - r)
        outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
        return outside + np.minimum(np.maximum(qx, qy), 0.0) - r

    def arc(self, cx, cy, r, start, end):
        return self.path(_arc_points(cx, cy, r, start, end, step=3.0))

    # --- cobertura -------------------------------------------------------- #

    def _cover(self, signed):
        return np.clip(0.5 - signed * self.k, 0.0, 1.0)

    def stroke(self, dist, weight=1.0):
        """Trazo centrado en la forma; `weight` multiplica el grosor común."""
        np.maximum(self.alpha, self._cover(np.abs(dist) - self.half * weight), out=self.alpha)

    def fill(self, dist, grow=0.0):
        np.maximum(self.alpha, self._cover(dist - grow), out=self.alpha)

    def cut(self, dist, gap, stroke=True):
        """Borra lo que quede a menos de `gap` de un trazo (o de un relleno, con
        stroke=False): el corte que separa una barra del resto, como en SF."""
        reach = (np.abs(dist) - self.half) if stroke else dist
        self.alpha *= 1.0 - self._cover(reach - gap)

    def image(self):
        """Cobertura final (L) del tamaño pedido: se reduce el 4× con LANCZOS."""
        big = Image.fromarray(np.round(self.alpha * 255.0).astype(np.uint8), "L")
        return big.resize((self.px, self.px), Image.LANCZOS)


# --------------------------------------------------------------------------- #
# El juego de íconos (grilla de 24; el trazo mide 2,33 unidades)
# --------------------------------------------------------------------------- #

_DRAW = {}


def _icon(name):
    def register(func):
        _DRAW[name] = func
        return func
    return register


@_icon("timer")
def _timer(p):
    # Cronómetro (Enfoque): esfera, aguja y el botón de arriba separado.
    p.stroke(p.circle(12, 13.6, 7.25))
    x = p.s(12)
    p.stroke(p.path([(x, 13.6), (x, 9.75)]))
    p.stroke(p.path([(10, 2.6), (14, 2.6)]))


@_icon("calendar")
def _calendar(p):
    x0, x1, y0, y1 = p.s(3), p.s(21), p.s(4.75), p.s(21)
    p.stroke(p.box(x0, y0, x1, y1, 3.25))
    head = p.s(9.25)
    p.stroke(p.path([(x0, head), (x1, head)]))
    # Anillas: terminan en el marco, así no ensucian la franja de arriba.
    for x in (p.s(8), p.s(16)):
        p.stroke(p.path([(x, 2.75), (x, y0)]))
    _calendar_days(p, (x0, head, x1, y1))


def _calendar_days(p, frame):
    """Días: cuadraditos de lado y paso en píxeles enteros (parejos y nítidos),
    con al menos 0,75 px de aire contra el marco. 3 × 2 si entran; si no, una
    fila (a 16 px); si ni eso, nada."""
    unit = p.unit
    edge = p.half * unit + 0.75
    left, top = p.to_px(frame[0]) + edge, p.to_px(frame[1]) + edge
    right, bottom = p.to_px(frame[2]) - edge, p.to_px(frame[3]) - edge
    side = max(1, round(2.5 * unit))
    for gap in sorted({max(1, round(2.0 * unit)), 1}, reverse=True):
        width = 3 * side + 2 * gap
        x = round((left + right - width) / 2.0)
        if x >= left - 1e-6 and x + width <= right + 1e-6:
            break
    else:
        return
    for rows, gap_y in ((2, max(1, round(1.5 * unit))), (2, 1), (1, 0)):
        height = rows * side + (rows - 1) * gap_y
        y = round((top + bottom - height) / 2.0)
        if y >= top - 1e-6 and y + height <= bottom + 1e-6:
            break
    else:
        return
    for col in range(3):
        for row in range(rows):
            cx = p.to_units(x + col * (side + gap))
            cy = p.to_units(y + row * (side + gap_y))
            p.fill(p.box(cx, cy, cx + side / unit, cy + side / unit, 0.35))


@_icon("chart")
def _chart(p):
    # Tres barras de igual ancho y separación en píxeles enteros (a 18 px: 3 + 2).
    unit = p.unit
    width = max(1, round(4.0 * unit))
    gap = max(1, round(2.25 * unit))
    left = round((p.px - (3 * width + 2 * gap)) / 2.0)
    bottom = p.e(20.75)
    for i, height in enumerate((9, 16, 12)):
        x = p.to_units(left + i * (width + gap))
        p.fill(p.box(x, p.e(20.75 - height), x + width / unit, bottom, 1.4))


@_icon("gear")
def _gear(p):
    # Rueda de seis dientes contorneada y el eje: a 16 px los dientes se leen.
    points = []
    for k in range(6):
        middle = k * 60 + 30
        for angle, radius in ((middle - 21, 6.6), (middle - 11, 9.2),
                              (middle + 11, 9.2), (middle + 21, 6.6)):
            points.append((12 + radius * math.cos(math.radians(angle)),
                           12 + radius * math.sin(math.radians(angle))))
    p.stroke(p.path(_fillet(points, 1.0, closed=True), closed=True))
    p.stroke(p.circle(12, 12, 2.75))


@_icon("pip")
def _pip(p):
    # Pestaña flotante: ventana con un recuadro abajo a la derecha.
    p.stroke(p.box(p.s(3), p.s(4.75), p.s(21), p.s(19.25), 3.25))
    p.fill(p.box(p.e(12.5), p.e(11.5), p.e(18), p.e(16), 1.25))


_SPEAKER_BODY = [(3.75, 9.25), (7.25, 9.25), (12, 4.9), (12, 19.1), (7.25, 14.75), (3.75, 14.75)]


def _speaker_body(p):
    # Cuerpo relleno (contorneado no se distingue a 16 px) con esquinas suaves.
    p.fill(p.path(_SPEAKER_BODY, closed=True), grow=0.75)


@_icon("speaker")
def _speaker(p):
    _speaker_body(p)
    p.stroke(p.arc(12.5, 12, 4.0, -48, 48))
    p.stroke(p.arc(12.5, 12, 7.75, -50, 50))


@_icon("speaker.slash")
def _speaker_slash(p):
    # El cuerpo queda en el mismo lugar que en "speaker": alternar no salta.
    _speaker_body(p)
    p.stroke(p.arc(12.5, 12, 4.0, -48, 48))
    slash = p.path([(4, 3.5), (20, 20.5)])
    p.cut(slash, 1.0)
    p.stroke(slash)


@_icon("play")
def _play(p):
    # Corrido a la derecha del centro de la caja: así se ve centrado.
    p.stroke(p.path(_fillet([(6.75, 4.25), (19.75, 12), (6.75, 19.75)], 2.0, closed=True),
                    closed=True))


def _bars(p, offset, top, bottom, weight=1.0):
    """Dos barras verticales simétricas, nítidas y con al menos 1 px de aire
    entre ellas aunque el trazo mínimo las engorde (pausa)."""
    a, b = p.s(12 - offset, weight), p.s(12 + offset, weight)
    width = p.half * 2.0 * weight * p.unit
    while p.to_px(b) - p.to_px(a) - width < 1.0:
        a, b = a - 1.0 / p.unit, b + 1.0 / p.unit
    for x in (a, b):
        p.stroke(p.path([(x, top), (x, bottom)]), weight=weight)


@_icon("pause")
def _pause(p):
    _bars(p, 3.25, 5.5, 18.5, 1.15)


@_icon("stop")
def _stop(p):
    p.stroke(p.box(p.s(5), p.s(5), p.s(19), p.s(19), 3.25))


@_icon("forward")
def _forward(p):
    # Ir a la otra fase: dos triángulos que se tocan en el centro.
    for x in (3.5, 12.5):
        p.stroke(p.path(_fillet([(x, 5.75), (x + 9, 12), (x, 18.25)], 1.25, closed=True),
                        closed=True))


@_icon("sliders")
def _sliders(p):
    # Ajustar ritmo: tres rieles, cada uno cortado por su perilla.
    for y, knob in ((5.5, 15), (12, 8.5), (18.5, 13.5)):
        y = p.s(y)
        p.stroke(p.path([(3.5, y), (20.5, y)]))
        ring = p.circle(knob, y, 2.25)
        p.cut(ring, 0.0, stroke=False)
        p.stroke(ring)


def _tray(p):
    # Bandeja abierta arriba (exportar / importar).
    x0, x1, y0, y1 = p.s(4.75), p.s(19.25), p.s(9.5), p.s(20.75)
    p.stroke(p.path(_fillet([(8, y0), (x0, y0), (x0, y1), (x1, y1), (x1, y0), (16, y0)], 2.75)))


@_icon("export")
def _export(p):
    _tray(p)
    x = p.s(12)
    p.stroke(p.path([(x, 2.75), (x, 14.25)]))
    p.stroke(p.path([(x - 3.5, 6.25), (x, 2.75), (x + 3.5, 6.25)]))


@_icon("import")
def _import(p):
    _tray(p)
    x = p.s(12)
    p.stroke(p.path([(x, 2.5), (x, 14.5)]))
    p.stroke(p.path([(x - 3.5, 11), (x, 14.5), (x + 3.5, 11)]))


@_icon("hashtag")
def _hashtag(p):
    p.stroke(p.path([(9.75, 3.5), (7.75, 20.5)]))
    p.stroke(p.path([(16.25, 3.5), (14.25, 20.5)]))
    p.stroke(p.path([(4.5, p.s(9)), (20, p.s(9))]))
    p.stroke(p.path([(4, p.s(15)), (19.5, p.s(15))]))


@_icon("chevron.left")
def _chevron_left(p):
    p.stroke(p.path([(15.25, 5.5), (8.75, 12), (15.25, 18.5)]))


@_icon("chevron.right")
def _chevron_right(p):
    p.stroke(p.path([(8.75, 5.5), (15.25, 12), (8.75, 18.5)]))


@_icon("chevron.down")
def _chevron_down(p):
    p.stroke(p.path([(5.5, 8.75), (12, 15.25), (18.5, 8.75)]))


@_icon("chevron.up.down")
def _chevron_up_down(p):
    # Más chatos que los sueltos: a 12 px (pop-ups de formulario) no se tocan.
    p.stroke(p.path([(8.5, 8.5), (12, 5), (15.5, 8.5)]))
    p.stroke(p.path([(8.5, 15.5), (12, 19), (15.5, 15.5)]))


@_icon("xmark")
def _xmark(p):
    p.stroke(p.path([(6, 6), (18, 18)]))
    p.stroke(p.path([(18, 6), (6, 18)]))


@_icon("checkmark")
def _checkmark(p):
    p.stroke(p.path([(4.5, 12.75), (9.5, 17.75), (19.5, 6.25)]))


def _ring(p):
    # Contorno común de los íconos ".circle": 18 unidades + el trazo.
    p.stroke(p.circle(12, 12, 9))


@_icon("checkmark.circle")
def _checkmark_circle(p):
    _ring(p)
    p.stroke(p.path([(8, 12.25), (10.75, 15), (16, 9)]))


@_icon("exclamationmark.circle")
def _exclamationmark_circle(p):
    _ring(p)
    x = p.s(12)
    p.stroke(p.path([(x, 7), (x, 12.75)]))
    p.fill(p.circle(x, 16.5, 1.35))


@_icon("exclamationmark.triangle")
def _exclamationmark_triangle(p):
    p.stroke(p.path(_fillet([(12, 2.25), (21.75, 19.75), (2.25, 19.75)], 2.5, closed=True),
                    closed=True))
    x = p.s(12)
    p.stroke(p.path([(x, 8.5), (x, 13)]))
    p.fill(p.circle(x, 16.25, 1.35))


@_icon("info.circle")
def _info_circle(p):
    _ring(p)
    x = p.s(12)
    p.fill(p.circle(x, 7.75, 1.35))
    p.stroke(p.path([(x, 11), (x, 16.75)]))


@_icon("pause.circle")
def _pause_circle(p):
    _ring(p)
    _bars(p, 2.5, 8.75, 15.25)


@_icon("eye")
def _eye(p):
    # Almendra con dos arcos que se cortan en los extremos + pupila.
    half_w, half_h = 9.25, 6.5
    radius = (half_w ** 2 + half_h ** 2) / (2 * half_h)
    spread = math.degrees(math.asin(half_w / radius))
    p.stroke(p.arc(12, 12 - half_h + radius, radius, 270 - spread, 270 + spread))
    p.stroke(p.arc(12, 12 + half_h - radius, radius, 90 - spread, 90 + spread))
    p.stroke(p.circle(12, 12, 2.75))


@_icon("pencil")
def _pencil(p):
    # Lápiz en diagonal: cuerpo con punta y la franja de la goma.
    ax, ay, bx, by = 4.0, 20.0, 18.75, 5.25
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length, (by - ay) / length
    nx, ny = -uy, ux
    w, tip, back = 2.6, 4.25, 4.25
    body = [(ax, ay),
            (ax + ux * tip + nx * w, ay + uy * tip + ny * w),
            (bx + nx * w, by + ny * w),
            (bx - nx * w, by - ny * w),
            (ax + ux * tip - nx * w, ay + uy * tip - ny * w)]
    p.stroke(p.path(_fillet(body, 1.0, closed=True), closed=True))
    p.stroke(p.path([(bx - ux * back + nx * w, by - uy * back + ny * w),
                     (bx - ux * back - nx * w, by - uy * back - ny * w)]))


@_icon("trash")
def _trash(p):
    lid = p.s(6.25)
    p.stroke(p.path([(3.5, lid), (20.5, lid)]))
    p.stroke(p.path(_fillet([(9, lid), (9, 3), (15, 3), (15, lid)], 1.25)))
    bottom = p.s(20.75)
    p.stroke(p.path(_fillet([(5.5, lid), (6.75, bottom), (17.25, bottom), (18.5, lid)], 2.25)))


@_icon("plus")
def _plus(p):
    c = p.s(12)
    p.stroke(p.path([(c, 4.75), (c, 19.25)]))
    p.stroke(p.path([(4.75, c), (19.25, c)]))


@_icon("minus")
def _minus(p):
    c = p.s(12)
    p.stroke(p.path([(4.75, c), (19.25, c)]))


@_icon("today")
def _today(p):
    _ring(p)
    p.fill(p.circle(12, 12, 3.5))


@_icon("flame")
def _flame(p):
    # Llama con una lengua a la izquierda y otra llama chica adentro (racha).
    outer = _curve((12, 21.5),
                   ((16.3, 21.5), (19.25, 18.4), (19.25, 14.6)),
                   ((19.25, 10.2), (15.6, 7.4), (12, 2.5)),
                   ((12.2, 5.4), (10.6, 7.6), (9.0, 9.6)),
                   ((8.5, 8.9), (8.2, 8.4), (8.0, 7.6)),
                   ((5.9, 9.6), (4.75, 12.1), (4.75, 14.6)),
                   ((4.75, 18.4), (7.7, 21.5), (12, 21.5)))
    p.stroke(p.path(_scaled(outer, 0.94), closed=True))
    inner = _curve((12, 21.5),
                   ((10.2, 21.5), (9.25, 20.1), (9.25, 18.4)),
                   ((9.25, 16.4), (11.0, 15.2), (12, 13.25)),
                   ((13.0, 15.2), (14.75, 16.4), (14.75, 18.4)),
                   ((14.75, 20.1), (13.8, 21.5), (12, 21.5)))
    p.stroke(p.path(_scaled(inner, 0.94), closed=True))


@_icon("target")
def _target(p):
    _ring(p)
    p.stroke(p.circle(12, 12, 4.25))
    p.fill(p.circle(12, 12, 1.25))


@_icon("clock")
def _clock(p):
    _ring(p)
    x = p.s(12)
    p.stroke(p.path([(x, 6.75), (x, 12), (15.75, 14.25)]))


@_icon("arrow.up.forward.app")
def _arrow_up_forward_app(p):
    # Abrir la app: recuadro abierto arriba a la derecha y una flecha que sale.
    x0, x1, y0, y1 = p.s(3.5), p.s(18.5), p.s(5.5), p.s(20.5)
    p.stroke(p.path(_fillet([(11, y0), (x0, y0), (x0, y1), (x1, y1), (x1, 13)], 3.5)))
    top, right = p.s(3.5), p.s(20.5)
    p.stroke(p.path([(10.75, 13.25), (right, top)]))
    p.stroke(p.path([(14.5, top), (right, top), (right, 9.5)]))


NAMES = ("timer", "calendar", "chart", "gear", "pip", "speaker", "speaker.slash", "play",
         "pause", "stop", "forward", "sliders", "export", "import", "hashtag", "chevron.left",
         "chevron.right", "chevron.down", "chevron.up.down", "xmark", "checkmark",
         "checkmark.circle", "exclamationmark.circle", "exclamationmark.triangle",
         "info.circle", "pause.circle", "eye", "pencil", "trash", "plus", "minus", "today",
         "flame", "target", "clock", "arrow.up.forward.app")

# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

_MASKS: OrderedDict = OrderedDict()
_ICONS: OrderedDict = OrderedDict()


def _rgb(color):
    if isinstance(color, (tuple, list)):
        return tuple(int(v) for v in color[:3])
    value = str(color).lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _remember(cache, key, value, limit):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)
    return value


def _mask(name, px, stroke_px):
    key = (name, px, stroke_px)
    mask = _MASKS.get(key)
    if mask is not None:
        _MASKS.move_to_end(key)
        return mask
    pen = _Pen(px, stroke_px)
    _DRAW[name](pen)
    return _remember(_MASKS, key, pen.image(), MASK_CACHE_SIZE)


def icon(name: str, size: float, color: str, *, weight: float | None = None,
         scale: float = 1.0) -> Image.Image:
    """Ícono `name` en RGBA de round(size * scale) px, color plano y alfa = cobertura.

    El trazo por defecto es 1,75 px a 18 px, proporcional al tamaño (mínimo 1,5) y
    multiplicado por `scale`; `weight` lo pisa (en px a escala 1). Nombre
    desconocido -> KeyError (no se dibuja un cuadrado de reemplazo)."""
    if name not in _DRAW:
        raise KeyError(name)
    px = max(1, int(round(size * scale)))
    base = weight if weight is not None else max(MIN_STROKE, STROKE_AT_18 * size / 18.0)
    stroke_px = round(max(0.1, base * scale), 3)
    rgb = _rgb(color)
    key = (name, px, rgb, stroke_px)
    cached = _ICONS.get(key)
    if cached is None:
        cached = Image.new("RGBA", (px, px), rgb + (0,))
        cached.putalpha(_mask(name, px, stroke_px))
        _remember(_ICONS, key, cached, CACHE_SIZE)
    else:
        _ICONS.move_to_end(key)
    # Copia: el que la reciba puede pegarla o modificarla sin tocar la caché.
    return cached.copy()


def paste_icon(image: Image.Image, name, xy, size, color, *, anchor: str = "lt", **kw) -> None:
    """Compone el ícono sobre `image` (RGB o RGBA) en el lugar.

    `xy` es la esquina superior izquierda (anchor "lt") o, con anchor "mm", el
    centro; vale cualquier combinación de l/m/r y t/m/b. El resto de los kw van
    a `icon` (weight, scale)."""
    glyph = icon(name, size, color, **kw)
    w, h = glyph.size
    x, y = float(xy[0]), float(xy[1])
    x -= {"l": 0.0, "m": w / 2.0, "r": float(w)}[anchor[0]]
    y -= {"t": 0.0, "m": h / 2.0, "b": float(h)}[anchor[1]]
    x, y = int(round(x)), int(round(y))
    # Recorte a los bordes del destino (alpha_composite no acepta salirse).
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(w, image.width - x), min(h, image.height - y)
    if right <= left or bottom <= top:
        return
    if (left, top, right, bottom) != (0, 0, w, h):
        glyph = glyph.crop((left, top, right, bottom))
    dest = (x + left, y + top)
    if image.mode == "RGBA":
        image.alpha_composite(glyph, dest)
    else:
        image.paste(glyph.convert(image.mode) if image.mode != "RGB" else _rgb(color),
                    dest + (dest[0] + glyph.width, dest[1] + glyph.height),
                    glyph.getchannel("A"))
