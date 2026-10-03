"""Motor de animación.

Un único ticker por ventana en vez de cadenas de `after()` sueltas: mientras hay
algo que animar corre a ~60 fps, y cuando no queda nada se apaga solo. Cada
animación se identifica por una clave, así que relanzar la misma no la superpone
(que es lo que producía los parpadeos): un tween se reemplaza y un resorte se
redirige.

En el mismo ticker conviven dos tipos de tarea:

* **Tweens** (`to`, `color`, `sequence`): curva de duración fija. Sirven para lo
  que no es movimiento (rellenos de hover, fundidos, la luz de fase).
* **Resortes** (`spring`, `spring_vector`, `spring_color`, `materialize`):
  física de masa 1 que se define como en SwiftUI, por duración percibida y
  rebote. Arrancan del valor que está en pantalla y, si se los redirige a mitad
  de camino, conservan la velocidad: al revertir no hay "pared de ladrillo",
  la física dobla sola. Con "reducir movimiento" saltan al objetivo o se funden
  en `REDUCED_FADE` segundos.

Además `request_frame` junta los redibujos: un widget con varias propiedades en
movimiento se dibuja una sola vez por cuadro, al final del cuadro.

Los tokens (`SPRINGS`, `TWEENS`) son los de DESIGN_SPEC §5.1.
"""

from __future__ import annotations

import math
import sys
import time
import tkinter as tk
import traceback
from dataclasses import dataclass

from .render import hex_to_rgb, rgb_to_hex

# --------------------------------------------------------------------------- #
# Curvas de aceleración
# --------------------------------------------------------------------------- #


def linear(t):
    return t


def ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3


def ease_out_quint(t):
    return 1.0 - (1.0 - t) ** 5


def ease_in_out_cubic(t):
    return 4 * t * t * t if t < 0.5 else 1.0 - ((-2 * t + 2) ** 3) / 2.0


def ease_out_back(t, overshoot=1.24):
    c3 = overshoot + 1.0
    return 1.0 + c3 * ((t - 1.0) ** 3) + overshoot * ((t - 1.0) ** 2)


def ease_out_expo(t):
    return 1.0 if t >= 1.0 else 1.0 - math.pow(2, -10 * t)


def spring(t, tension=5.6, friction=6.0):
    """Rebote amortiguado; termina exactamente en 1.0.

    Es una curva de duración fija (no conserva velocidad): para movimiento de
    verdad usar `Animator.spring`.
    """
    if t >= 1.0:
        return 1.0
    return 1.0 - math.exp(-friction * t) * math.cos(tension * math.pi * t)


EASINGS = {
    "linear": linear,
    "out_cubic": ease_out_cubic,
    "out_quint": ease_out_quint,
    "in_out_cubic": ease_in_out_cubic,
    "out_back": ease_out_back,
    "out_expo": ease_out_expo,
    "spring": spring,
}


# --------------------------------------------------------------------------- #
# Tokens de movimiento
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SpringSpec:
    """Resorte en términos de diseño, como `Spring(duration:bounce:)` de SwiftUI.

    duration -- duración percibida en segundos (la "response" de UIKit), no el
                tiempo hasta quedar quieto.
    bounce   -- 0 = sin rebote (amortiguamiento crítico, el defecto); 0,15 es
                enérgico pero todavía no rebota a la vista; 0,3 rebota; más de
                0,4 es exagerado para interfaz. Negativo = sobreamortiguado.

    Con masa 1: rigidez = (2π/duration)², amortiguamiento = 4π(1 − bounce)/duration
    (SpringSpec(0.5, 0.3) -> 157,9 y 17,6, el ejemplo de la documentación de Apple).
    """

    duration: float
    bounce: float = 0.0

    def __post_init__(self):
        if not self.duration > 0:
            raise ValueError("SpringSpec: la duración tiene que ser positiva")
        if not self.bounce < 1:
            raise ValueError("SpringSpec: con rebote 1 o más el resorte no se detiene nunca")

    @property
    def stiffness(self) -> float:
        return (2 * math.pi / self.duration) ** 2

    @property
    def damping(self) -> float:
        return 4 * math.pi * (1 - self.bounce) / self.duration


SPRINGS = {
    "snappy": SpringSpec(0.30, 0.00),    # cambios de estado, reacomodos, colores
    "select": SpringSpec(0.42, 0.12),    # píldoras, perillas, mes del calendario
    "pop_in": SpringSpec(0.38, 0.15),    # materializar menús, avisos, hojas
    "pop_out": SpringSpec(0.24, 0.00),   # desmaterializar
    "press": SpringSpec(0.15, 0.00),     # hundirse al presionar (escala 0,97)
    "release": SpringSpec(0.40, 0.30),   # volver al soltar (único con rebote visible)
    "data": SpringSpec(0.55, 0.00),      # anillos, barras, donas (sólo en saltos)
    "page": SpringSpec(0.28, 0.00),      # los 6 px de la transición de vista
    "scroll": SpringSpec(0.25, 0.00),    # desplazamiento con rueda
}

# Lo que no es resorte: (duración, curva). La luz de fase va a 15 cuadros/s;
# eso lo limita quien dibuja (min_frame_ms), no el ticker.
TWEENS = {
    "hover": (0.12, "out_cubic"),
    "hover_out": (0.20, "out_cubic"),
    "ambient": (1.2, "in_out_cubic"),
    "ambient_reduced": (0.3, "in_out_cubic"),
}

REDUCED_FADE = 0.15       # duración del fundido que reemplaza al movimiento

_MAX_DT = 0.25            # tope por cuadro: tras una suspensión no se integran horas
_MAX_LIFE = 10.0          # un resorte que no se asienta en 10 s (eps imposible) se termina


def _resolve_spec(spec) -> SpringSpec:
    if isinstance(spec, SpringSpec):
        return spec
    if isinstance(spec, str):
        return SPRINGS[spec]
    duration, bounce = spec                 # también se acepta (duración, rebote)
    return SpringSpec(float(duration), float(bounce))


def _now():
    return time.perf_counter()


# --------------------------------------------------------------------------- #
# Resorte
# --------------------------------------------------------------------------- #


class Spring:
    """Valor que persigue un objetivo con física de resorte (masa 1).

    `step(dt)` avanza con la solución exacta del oscilador amortiguado (como
    SwiftUI y CASpringAnimation), con el `dt` real que le pasen: no hay error de
    integración, así que el rebote se ve igual a cualquier duración y a
    cualquier cantidad de cuadros por segundo, y es estable con cualquier
    rigidez. Entre un cuadro y el siguiente el objetivo es fijo; redirigirlo
    (`retarget`) no toca ni el valor ni la velocidad: por eso una animación
    interrumpida sigue sin saltos.
    """

    __slots__ = ("value", "velocity", "target", "spec", "_w0", "_zeta")

    def __init__(self, value=0.0, spec: SpringSpec | str = "snappy", velocity=0.0):
        self.value = float(value)
        self.velocity = float(velocity)
        self.target = self.value
        self._set_spec(spec)

    def _set_spec(self, spec):
        self.spec = _resolve_spec(spec)
        self._w0 = 2 * math.pi / self.spec.duration     # frecuencia propia = √rigidez
        self._zeta = 1.0 - self.spec.bounce              # = amortiguamiento / (2·√rigidez)

    def retarget(self, target, velocity=None, spec=None):
        # No se reinicia nada: posición y velocidad siguen como estaban.
        self.target = float(target)
        if velocity is not None:
            self.velocity = float(velocity)
        if spec is not None:
            self._set_spec(spec)

    def step(self, dt: float) -> float:
        if dt <= 0:
            return self.value
        w0, zeta = self._w0, self._zeta
        e0 = self.value - self.target                    # desplazamiento respecto del objetivo
        v0 = self.velocity
        if abs(zeta - 1.0) < 1e-6:
            # crítico (rebote 0): llega lo antes posible sin pasarse
            b = v0 + w0 * e0
            decay = math.exp(-w0 * dt)
            e = (e0 + b * dt) * decay
            v = (v0 - w0 * b * dt) * decay
        elif zeta < 1.0:
            # subamortiguado: oscila alrededor del objetivo mientras se apaga
            a = zeta * w0
            wd = w0 * math.sqrt(1.0 - zeta * zeta)
            decay = math.exp(-a * dt)
            cos, sin = math.cos(wd * dt), math.sin(wd * dt)
            e = decay * (e0 * cos + (v0 + a * e0) / wd * sin)
            v = decay * (v0 * cos - (w0 * w0 * e0 + a * v0) / wd * sin)
        else:
            # sobreamortiguado (rebote negativo): suma de dos exponenciales
            root = w0 * math.sqrt(zeta * zeta - 1.0)
            r1, r2 = -zeta * w0 + root, -zeta * w0 - root
            c2 = (v0 - r1 * e0) / (r2 - r1)
            c1 = e0 - c2
            g1, g2 = math.exp(r1 * dt), math.exp(r2 * dt)
            e = c1 * g1 + c2 * g2
            v = c1 * r1 * g1 + c2 * r2 * g2
        self.value = self.target + e
        self.velocity = v
        return self.value

    def settled(self, eps: float = 1e-3) -> bool:
        return abs(self.value - self.target) < eps and abs(self.velocity) < eps * 10

    def snap(self):
        """Lo deja quieto exactamente en el objetivo."""
        self.value = self.target
        self.velocity = 0.0


# --------------------------------------------------------------------------- #
# Tareas del ticker
# --------------------------------------------------------------------------- #
#
# Toda tarea viva está en `Animator._tweens` (lo leen las herramientas de
# captura) y tiene: step(now) -> True si terminó, on_done, value y velocity
# (el valor y la velocidad "presentados", para que otra animación con la misma
# clave arranque desde ahí).


def _payload(kind, values):
    """Lo que recibe on_update según el tipo de resorte."""
    if kind == "scalar":
        return values[0]
    if kind == "unit":                      # materializar: m acotado a 0..1
        return min(1.0, max(0.0, values[0]))
    if kind == "vector":
        return list(values)
    return rgb_to_hex(values)               # "color"


def _numbers(kind, payload, count):
    """Pasa un valor presentado a la lista de números del resorte (o None)."""
    if payload is None:
        return None
    if kind == "color":
        if isinstance(payload, str):
            try:
                return [float(c) for c in hex_to_rgb(payload)]
            except ValueError:
                return None
        payload_list = payload
    elif kind in ("scalar", "unit"):
        if isinstance(payload, (int, float)):
            return [float(payload)]
        return None
    else:
        payload_list = payload
    if isinstance(payload_list, (list, tuple)) and len(payload_list) == count:
        try:
            return [float(v) for v in payload_list]
        except (TypeError, ValueError):
            return None
    return None


class Tween:
    __slots__ = ("start", "end", "duration", "easing", "apply", "on_done", "t0", "delay",
                 "value", "_t", "_prev", "_prev_t")

    def __init__(self, start, end, duration, easing, apply, on_done=None, delay=0.0,
                 now=None):
        self.start = start
        self.end = end
        self.duration = max(0.001, duration)
        self.easing = easing
        self.apply = apply
        self.on_done = on_done
        self.delay = delay
        self.t0 = (time.perf_counter() if now is None else now) + delay
        # valor presentado: lo que devolvió `apply` en el último cuadro (None si
        # `apply` no devuelve nada, como en los tweens armados a mano)
        self.value = None
        self._t = self._prev = self._prev_t = None

    def step(self, now):
        elapsed = now - self.t0
        if elapsed < 0:
            return False
        progress = min(1.0, elapsed / self.duration)
        value = self.apply(self.easing(progress))
        if value is not None:
            self._prev, self._prev_t = self.value, self._t
            self.value, self._t = value, now
        return progress >= 1.0

    @property
    def velocity(self):
        """Velocidad presentada (diferencia entre los dos últimos cuadros)."""
        if self._prev is None or self._prev_t is None or self._t == self._prev_t:
            return None
        span = self._t - self._prev_t
        if isinstance(self.value, (int, float)) and isinstance(self._prev, (int, float)):
            return (self.value - self._prev) / span
        if isinstance(self.value, list) and isinstance(self._prev, list):
            return [(a - b) / span for a, b in zip(self.value, self._prev)]
        return None


class _Fade(Tween):
    """Fundido corto que reemplaza a un resorte con "reducir movimiento"."""

    __slots__ = ("kind", "on_update", "_from", "_to")

    def __init__(self, kind, start, end, on_update, on_done, now):
        self.kind = kind
        self.on_update = on_update
        self._from = list(start)
        self._to = list(end)
        super().__init__(0.0, 1.0, REDUCED_FADE, ease_out_cubic, self._apply, on_done, now=now)
        self.value, self._t = _payload(kind, self._from), self.t0

    def _apply(self, eased):
        value = _payload(self.kind, [a + (b - a) * eased for a, b in zip(self._from, self._to)])
        self.on_update(value)
        return value

    def heads_to(self, end):
        return self._to == list(end)


class _SpringTask:
    """Uno o más resortes que avanzan juntos y entregan un solo valor por cuadro."""

    __slots__ = ("kind", "springs", "eps", "on_update", "on_done", "last", "fresh",
                 "frame_dt", "emitted", "age")

    def __init__(self, kind, springs, eps, on_update, on_done, now, frame_dt):
        self.kind = kind
        self.springs = springs
        self.eps = eps
        self.on_update = on_update
        self.on_done = on_done
        self.last = now
        self.fresh = True
        self.frame_dt = frame_dt
        self.emitted = None
        self.age = 0.0

    @property
    def value(self):
        return _payload(self.kind, [s.value for s in self.springs])

    @property
    def velocity(self):
        if self.kind in ("scalar", "unit"):
            return self.springs[0].velocity
        return [s.velocity for s in self.springs]

    def step(self, now):
        dt = now - self.last
        self.last = now
        if self.fresh:
            # El primer cuadro avanza un cuadro, aunque el manejador que lanzó la
            # animación haya tardado: arranca cuando se ve, no cuando se pidió.
            self.fresh = False
            dt = min(dt, self.frame_dt)
        dt = min(dt, _MAX_DT)
        self.age += dt
        for item in self.springs:
            item.step(dt)
        done = self.age > _MAX_LIFE or all(
            item.settled(eps) for item, eps in zip(self.springs, self.eps))
        if done:
            for item in self.springs:
                item.snap()
        value = self.value
        # sólo se entrega si cambió lo que se ve (p. ej. un color ya redondeado)
        if value != self.emitted:
            self.emitted = value
            self.on_update(value)
        return done


def _auto_eps(kind, start, target):
    """Tolerancia de asentado: 1e-3 relativo al recorrido (DESIGN_SPEC §5.1)."""
    if kind == "color":
        return 0.5                           # medio nivel de 0–255: ya no se ve
    return 1e-3 * max(1.0, abs(target - start))


# --------------------------------------------------------------------------- #
# Animator
# --------------------------------------------------------------------------- #


class Animator:
    """Ticker compartido. Se instancia una vez por ventana raíz.

    `clock` (opcional) reemplaza a `time.perf_counter`; lo usan las pruebas.
    """

    def __init__(self, widget, fps=60, *, clock=None):
        self.widget = widget
        self.interval = max(8, int(1000 / fps))
        self._tweens: dict[object, object] = {}   # TODAS las tareas vivas (tweens y resortes)
        self._frames: dict[object, object] = {}   # redibujos pedidos para el fin del cuadro
        self._job = None
        self._running = False
        self._clock = clock or _now
        self._generation = 0                       # cambia con stop(): corta el cuadro en curso
        self._reported: set = set()
        self.reduced_motion = False                # lo setea la app desde a11y
        self.frame_count = 0                       # cuadros procesados desde el arranque

    @property
    def idle(self) -> bool:
        """True si no hay tareas vivas ni redibujos pendientes (ticker apagado)."""
        return not self._tweens and not self._frames

    # -- ciclo ------------------------------------------------------------- #

    def _ensure_running(self):
        if self._running:
            return
        self._schedule(self.interval)

    def _schedule(self, delay):
        try:
            self._job = self.widget.after(delay, self._tick)
            self._running = True
        except tk.TclError:
            # La ventana ya no existe (se está cerrando): no hay nada que animar.
            self._job = None
            self._running = False
            self._tweens.clear()
            self._frames.clear()

    def _sleep_if_empty(self):
        """Sin tareas ni pedidos, cancela el `after` pendiente en vez de esperar
        un cuadro vacío. Dentro de un cuadro no hay `after` pendiente: decide
        el final del cuadro."""
        if self._tweens or self._frames or self._job is None:
            return
        try:
            self.widget.after_cancel(self._job)
        except Exception:
            pass    # la ventana pudo haberse destruido: no hay nada que cancelar
        self._job = None
        self._running = False

    def _tick(self):
        self._job = None
        if not self._tweens and not self._frames:
            self._running = False
            return
        generation = self._generation
        now = self._clock()
        finished = []
        # copiamos: un callback puede registrar, redirigir o cancelar tareas
        for key, task in list(self._tweens.items()):
            if self._generation != generation:
                return                          # stop() en medio del cuadro
            if self._tweens.get(key) is not task:
                continue                        # cancelada o reemplazada en este cuadro
            try:
                done = task.step(now)
            except Exception:
                self._report(key, "on_update")
                if self._tweens.get(key) is task:
                    del self._tweens[key]
                continue
            if done and self._tweens.get(key) is task:
                del self._tweens[key]
                finished.append((key, task))

        for key, task in finished:
            if self._generation != generation:
                return
            # si alguien relanzó la clave en este mismo cuadro, el on_done viejo
            # se pierde (como al reemplazar un tween)
            if task.on_done is None or key in self._tweens:
                continue
            try:
                task.on_done()
            except Exception:
                self._report(key, "on_done")

        # Fin del cuadro: cada destino pedido se redibuja una sola vez. Lo que
        # se pida mientras tanto queda para el cuadro siguiente.
        frames, self._frames = self._frames, {}
        for fkey, target in frames.items():
            if self._generation != generation:
                return
            self._run_frame(fkey, target)

        self.frame_count += 1
        if self._tweens or self._frames:
            # el `dt` real lo mide cada tarea; acá sólo se descuenta lo que tardó
            # el cuadro para sostener ~60 fps sin ahogar al bucle de eventos
            spent = (self._clock() - now) * 1000.0
            self._schedule(max(4, int(self.interval - spent)))
        else:
            self._running = False

    def _run_frame(self, fkey, target):
        owner = getattr(target, "__self__", target)
        exists = getattr(owner, "winfo_exists", None)
        if exists is not None:
            try:
                if not exists():
                    return                      # se destruyó antes del cuadro: nada que dibujar
            except tk.TclError:
                return
        redraw = getattr(target, "redraw", None)
        try:
            (redraw if callable(redraw) else target)()
        except Exception:
            self._report(("frame", fkey), "redibujo")

    def _report(self, key, what):
        """Imprime el traceback de la excepción en curso, una sola vez por clave."""
        try:
            hash(key)
            marker = key
        except TypeError:
            marker = id(key)
        if marker in self._reported:
            return
        if len(self._reported) >= 512:
            self._reported.clear()
        self._reported.add(marker)
        print(f"[anim] error en {what} ({key!r}); se descarta:", file=sys.stderr)
        traceback.print_exc()

    def _call(self, key, func, *args):
        """Llama un callback fuera del ticker con la misma regla de errores."""
        if func is None:
            return
        try:
            func(*args)
        except Exception:
            self._report(key, "callback")

    def stop(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass    # la ventana pudo haberse destruido: no hay nada que cancelar
        self._job = None
        self._running = False
        self._tweens.clear()
        self._frames.clear()
        self._generation += 1

    def cancel(self, key):
        self._tweens.pop(key, None)
        self._sleep_if_empty()

    def is_running(self, key):
        return key in self._tweens

    # -- tweens (API original) ----------------------------------------------- #

    def to(self, key, start, end, duration=0.32, easing="out_cubic", on_update=None,
           on_done=None, delay=0.0):
        """Anima un número de `start` a `end` llamando `on_update(valor)`."""
        curve = EASINGS.get(easing, ease_out_cubic) if isinstance(easing, str) else easing

        def apply(eased):
            value = start + (end - start) * eased
            on_update(value)
            return value

        tween = Tween(start, end, duration, curve, apply, on_done, delay, now=self._clock())
        tween.value, tween._t = start, tween.t0
        self._tweens[key] = tween
        self._ensure_running()

    def color(self, key, start, end, duration=0.22, easing="out_cubic", on_update=None,
              on_done=None):
        """Interpola dos colores hex llamando `on_update(hex)`."""
        curve = EASINGS.get(easing, ease_out_cubic) if isinstance(easing, str) else easing
        c0 = hex_to_rgb(start)
        c1 = hex_to_rgb(end)

        def apply(eased):
            value = rgb_to_hex(tuple(a + (b - a) * eased for a, b in zip(c0, c1)))
            on_update(value)
            return value

        tween = Tween(0.0, 1.0, duration, curve, apply, on_done, now=self._clock())
        tween.value, tween._t = start, tween.t0
        self._tweens[key] = tween
        self._ensure_running()

    def sequence(self, key, values, duration=0.32, easing="out_cubic", on_update=None,
                 on_done=None):
        """Anima una lista de números en paralelo (p. ej. los tres tramos de la dona)."""
        curve = EASINGS.get(easing, ease_out_cubic) if isinstance(easing, str) else easing
        starts, ends = list(values[0]), list(values[1])

        def apply(eased):
            value = [a + (b - a) * eased for a, b in zip(starts, ends)]
            on_update(value)
            return value

        tween = Tween(0.0, 1.0, duration, curve, apply, on_done, now=self._clock())
        tween.value, tween._t = list(starts), tween.t0
        self._tweens[key] = tween
        self._ensure_running()

    # -- resortes -------------------------------------------------------------- #

    def spring(self, key, target: float, *, on_update, value: float | None = None,
               velocity: float | None = None, spec: SpringSpec | str = "snappy",
               on_done=None, eps: float | None = None, fade: bool = False) -> None:
        """Lleva un número a `target` con un resorte, llamando `on_update(valor)`.

        Si ya hay un resorte vivo con `key` lo redirige: conserva valor y
        velocidad (`value` se ignora; `velocity`, si viene, la pisa, p. ej. la
        del puntero al soltar un arrastre). Si no, arranca desde `value`
        (obligatorio la primera vez; si la clave tenía un tween vivo, sirve su
        valor presentado). Si ya está en el objetivo no se anima: se llama una
        vez `on_update(target)` y `on_done`. El último `on_update` es siempre
        el objetivo exacto; `on_done` corre al asentarse (o se pierde si otra
        llamada lo reemplaza).

        eps: tolerancia absoluta de asentado; por defecto 1e-3 relativo al
        recorrido. Para posiciones en px conviene 0,5 × escala.
        Con `reduced_motion`: fade=False salta al objetivo (un on_update y
        on_done); fade=True hace un fundido de REDUCED_FADE s (out_cubic).
        """
        self._spring(key, "scalar", [float(target)], on_update,
                     None if value is None else [float(value)],
                     None if velocity is None else [float(velocity)],
                     spec, on_done, None if eps is None else [float(eps)], fade)

    def spring_vector(self, key, targets: list[float], *, on_update,
                      values: list[float] | None = None, spec: SpringSpec | str = "snappy",
                      on_done=None, fade: bool = False) -> None:
        """Como `spring` para varios números a la vez (un rect, los tramos de un
        gráfico). on_update recibe una lista. Cada componente conserva su propia
        velocidad al redirigir."""
        targets = [float(t) for t in targets]
        self._spring(key, "vector", targets, on_update,
                     None if values is None else [float(v) for v in values],
                     None, spec, on_done, None, fade)

    def spring_color(self, key, target_hex: str, *, on_update, value_hex: str | None = None,
                     spec: SpringSpec | str = "snappy", on_done=None) -> None:
        """Lleva un color a `target_hex` con un resorte por canal RGB y llama
        `on_update(hex)` sólo cuando cambia el color visible. Desde el reposo es
        lo mismo que un resorte de t; al redirigirlo a otro color conserva la
        velocidad de cada canal. Con reduced_motion el cambio es directo."""
        self._spring(key, "color", [float(c) for c in hex_to_rgb(target_hex)], on_update,
                     None if value_hex is None else [float(c) for c in hex_to_rgb(value_hex)],
                     None, spec, on_done, None, False)

    def materialize(self, key, show: bool, *, on_update, value: float | None = None,
                    on_done=None) -> None:
        """m de 0 a 1 con `pop_in` (show) o de 1 a 0 con `pop_out` (DESIGN_SPEC
        §5.1). on_update recibe m acotado a 0..1. Si se invierte a mitad de
        camino sigue desde donde está, con su velocidad. Con reduced_motion es
        un fundido de REDUCED_FADE s."""
        target = 1.0 if show else 0.0
        if value is None and key not in self._tweens:
            value = 1.0 - target
        self._spring(key, "unit", [target], on_update,
                     None if value is None else [float(value)], None,
                     "pop_in" if show else "pop_out", on_done, [1e-3], True)

    def value_of(self, key):
        """Valor presentado de la animación viva con `key` (float, lista o hex
        según el tipo) o None si no hay ninguna."""
        task = self._tweens.get(key)
        return None if task is None else task.value

    def velocity_of(self, key):
        """Velocidad presentada (unidades por segundo; lista en vectores y
        colores) o None si no hay animación viva o no se puede saber."""
        task = self._tweens.get(key)
        return None if task is None else task.velocity

    # -- redibujos por cuadro ---------------------------------------------------- #

    def request_frame(self, target) -> None:
        """Pide que `target` (widget con redraw() o callable) se ejecute UNA vez
        al final del cuadro en curso, o del próximo si no hay ticker, aunque se
        pida muchas veces. Si para entonces el widget ya no existe, no pasa nada."""
        if not callable(getattr(target, "redraw", None)) and not callable(target):
            raise TypeError("request_frame espera un widget con redraw() o algo llamable")
        key = self._frame_key(target)
        if key not in self._frames:
            self._frames[key] = target
        self._ensure_running()

    def cancel_frame(self, target) -> None:
        """Retira un pedido de redibujo pendiente (p. ej. al destruir el widget)."""
        self._frames.pop(self._frame_key(target), None)
        self._sleep_if_empty()

    @staticmethod
    def _frame_key(target):
        try:
            hash(target)
        except TypeError:
            return id(target)
        return target

    # -- motor común de resortes ------------------------------------------------ #

    def _spring(self, key, kind, targets, on_update, values, velocities, spec, on_done,
                eps, fade):
        if self.reduced_motion:
            self._reduced(key, kind, targets, on_update, values, on_done, fade)
            return
        task = self._tweens.get(key)
        if isinstance(task, _SpringTask) and task.kind == kind \
                and len(task.springs) == len(targets):
            # Redirigir: el resorte sigue desde el valor y la velocidad presentes.
            for index, (item, target) in enumerate(zip(task.springs, targets)):
                item.retarget(target, None if velocities is None else velocities[index], spec)
            task.eps = eps or [_auto_eps(kind, item.value, item.target) for item in task.springs]
            task.on_update = on_update
            task.on_done = on_done
            return

        start, speed = self._present(key, task, kind, targets, values, velocities)
        tolerances = eps or [_auto_eps(kind, a, b) for a, b in zip(start, targets)]
        if all(abs(a - b) < e and abs(v) < e * 10
               for a, b, v, e in zip(start, targets, speed, tolerances)):
            # Ya está ahí: no hace falta ticker.
            self._tweens.pop(key, None)
            self._sleep_if_empty()
            self._call(key, on_update, _payload(kind, targets))
            self._call(key, on_done)
            return
        springs = []
        for a, b, v in zip(start, targets, speed):
            item = Spring(a, spec, v)
            item.retarget(b)
            springs.append(item)
        self._tweens[key] = _SpringTask(kind, springs, tolerances, on_update, on_done,
                                        self._clock(), self.interval / 1000.0)
        self._ensure_running()

    def _present(self, key, task, kind, targets, values, velocities):
        """Valor y velocidad de arranque: los pedidos, o los que hay en pantalla."""
        count = len(targets)
        shown = None if task is None else _numbers(kind, task.value, count)
        shown_speed = None
        if shown is not None:
            shown_speed = _numbers("vector", task.velocity, count) \
                if kind in ("vector", "color") else _numbers(kind, task.velocity, count)
        if values is not None:
            start = values
            # si el valor pedido es el que se ve, también se hereda la velocidad
            if velocities is None and shown is not None and all(
                    abs(a - b) <= 1e-6 * max(1.0, abs(a)) for a, b in zip(start, shown)):
                velocities = shown_speed
        elif shown is not None:
            start = shown
            if velocities is None:
                velocities = shown_speed
        else:
            raise ValueError(f"Animator: la animación {key!r} no está corriendo; "
                             "hay que pasar el valor de arranque")
        return list(start), list(velocities) if velocities is not None else [0.0] * count

    def _reduced(self, key, kind, targets, on_update, values, on_done, fade):
        """Reducir movimiento: salto directo o fundido corto, nunca un resorte."""
        end = _payload(kind, targets)
        task = self._tweens.get(key)
        if not fade:
            self._tweens.pop(key, None)
            self._sleep_if_empty()
            self._call(key, on_update, end)
            self._call(key, on_done)
            return
        if isinstance(task, _Fade) and task.kind == kind and task.heads_to(targets):
            task.on_update = on_update          # mismo objetivo: sigue el fundido en curso
            task.on_done = on_done
            return
        shown = None if task is None else _numbers(kind, task.value, len(targets))
        start = values if values is not None else shown
        if start is None or all(abs(a - b) < 1e-6 for a, b in zip(start, targets)):
            self._tweens.pop(key, None)
            self._sleep_if_empty()
            self._call(key, on_update, end)
            self._call(key, on_done)
            return
        self._tweens[key] = _Fade(kind, start, targets, on_update, on_done, self._clock())
        self._ensure_running()


# --------------------------------------------------------------------------- #
# Valor animado: guarda su propio estado y sólo anima el delta
# --------------------------------------------------------------------------- #


class AnimatedValue:
    """Número que persigue suavemente a su objetivo."""

    def __init__(self, animator, key, value=0.0, duration=0.35, easing="out_cubic",
                 on_update=None):
        self.animator = animator
        self.key = key
        self.value = float(value)
        self.duration = duration
        self.easing = easing
        self.on_update = on_update

    def set(self, target, animate=True, duration=None):
        target = float(target)
        if not animate or abs(target - self.value) < 1e-6:
            self.animator.cancel(self.key)
            self.value = target
            if self.on_update:
                self.on_update(self.value)
            return

        def update(v):
            self.value = v
            if self.on_update:
                self.on_update(v)

        self.animator.to(
            self.key,
            self.value,
            target,
            duration if duration is not None else self.duration,
            self.easing,
            on_update=update,
        )


class AnimatedVector:
    """Lo mismo pero para una tupla de números (los tramos de un gráfico)."""

    def __init__(self, animator, key, values, duration=0.4, easing="out_cubic",
                 on_update=None):
        self.animator = animator
        self.key = key
        self.values = [float(v) for v in values]
        self.duration = duration
        self.easing = easing
        self.on_update = on_update

    def set(self, targets, animate=True, duration=None):
        targets = [float(v) for v in targets]
        if len(targets) != len(self.values):
            self.values = targets
            animate = False
        if not animate or all(abs(a - b) < 1e-6 for a, b in zip(self.values, targets)):
            self.animator.cancel(self.key)
            self.values = targets
            if self.on_update:
                self.on_update(self.values)
            return

        def update(vs):
            self.values = vs
            if self.on_update:
                self.on_update(vs)

        self.animator.sequence(
            self.key,
            (self.values, targets),
            duration if duration is not None else self.duration,
            self.easing,
            on_update=update,
        )
