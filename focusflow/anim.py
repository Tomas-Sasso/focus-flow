"""Motor de animación.

Un único ticker por ventana en vez de cadenas de `after()` sueltas: mientras hay
algo que animar corre a ~60 fps, y cuando no queda nada se apaga solo. Cada tween
se identifica por una clave, así que relanzar la misma animación reemplaza la
anterior en lugar de superponerse (que es lo que producía los parpadeos).
"""

from __future__ import annotations

import math
import time
import tkinter as tk

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
    """Rebote amortiguado; termina exactamente en 1.0."""
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
# Tweens
# --------------------------------------------------------------------------- #


class Tween:
    __slots__ = ("start", "end", "duration", "easing", "apply", "on_done", "t0", "delay")

    def __init__(self, start, end, duration, easing, apply, on_done=None, delay=0.0):
        self.start = start
        self.end = end
        self.duration = max(0.001, duration)
        self.easing = easing
        self.apply = apply
        self.on_done = on_done
        self.delay = delay
        self.t0 = time.perf_counter() + delay

    def step(self, now):
        elapsed = now - self.t0
        if elapsed < 0:
            return False
        progress = min(1.0, elapsed / self.duration)
        self.apply(self.easing(progress))
        return progress >= 1.0


class Animator:
    """Ticker compartido. Se instancia una vez por ventana raíz."""

    def __init__(self, widget, fps=60):
        self.widget = widget
        self.interval = max(8, int(1000 / fps))
        self._tweens: dict[object, Tween] = {}
        self._job = None
        self._running = False

    # -- ciclo ------------------------------------------------------------- #

    def _ensure_running(self):
        if self._running:
            return
        self._running = True
        self._job = self.widget.after(self.interval, self._tick)

    def _tick(self):
        self._job = None
        now = time.perf_counter()
        finished = []
        # copiamos: un callback puede registrar o cancelar tweens
        for key, tween in list(self._tweens.items()):
            try:
                if tween.step(now):
                    finished.append((key, tween))
            except tk.TclError:
                finished.append((key, None))
            except Exception:
                finished.append((key, None))

        for key, tween in finished:
            if self._tweens.get(key) is tween or tween is None:
                self._tweens.pop(key, None)
            if tween is not None and tween.on_done is not None:
                try:
                    tween.on_done()
                except Exception:
                    pass

        if self._tweens:
            self._job = self.widget.after(self.interval, self._tick)
        else:
            self._running = False

    def stop(self):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except Exception:
                pass
        self._job = None
        self._running = False
        self._tweens.clear()

    def cancel(self, key):
        self._tweens.pop(key, None)

    def is_running(self, key):
        return key in self._tweens

    # -- API --------------------------------------------------------------- #

    def to(self, key, start, end, duration=0.32, easing="out_cubic", on_update=None,
           on_done=None, delay=0.0):
        """Anima un número de `start` a `end` llamando `on_update(valor)`."""
        curve = EASINGS.get(easing, ease_out_cubic) if isinstance(easing, str) else easing

        def apply(eased):
            on_update(start + (end - start) * eased)

        self._tweens[key] = Tween(start, end, duration, curve, apply, on_done, delay)
        self._ensure_running()

    def color(self, key, start, end, duration=0.22, easing="out_cubic", on_update=None,
              on_done=None):
        """Interpola dos colores hex llamando `on_update(hex)`."""
        curve = EASINGS.get(easing, ease_out_cubic) if isinstance(easing, str) else easing
        c0 = hex_to_rgb(start)
        c1 = hex_to_rgb(end)

        def apply(eased):
            on_update(rgb_to_hex(tuple(a + (b - a) * eased for a, b in zip(c0, c1))))

        self._tweens[key] = Tween(0.0, 1.0, duration, curve, apply, on_done)
        self._ensure_running()

    def sequence(self, key, values, duration=0.32, easing="out_cubic", on_update=None,
                 on_done=None):
        """Anima una lista de números en paralelo (p. ej. los tres tramos de la dona)."""
        curve = EASINGS.get(easing, ease_out_cubic) if isinstance(easing, str) else easing
        starts, ends = list(values[0]), list(values[1])

        def apply(eased):
            on_update([a + (b - a) * eased for a, b in zip(starts, ends)])

        self._tweens[key] = Tween(0.0, 1.0, duration, curve, apply, on_done)
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
