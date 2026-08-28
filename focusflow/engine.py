"""Máquina de estados de la sesión.

No importa nada de Tk a propósito: se puede correr y testear sin abrir ventana.

La diferencia grande con el programa original es cómo se cuenta el tiempo. Antes
había relojes en paralelo (`c2`, `rest_time`, banderas de "está corriendo") que
había que sumar y restar a mano en cada transición, y cualquier camino olvidado
descuadraba los totales. Acá lo único que se guarda son los tramos; los totales
se derivan de ellos, así que por construcción siempre suman el tiempo real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# --- estados ---
IDLE = "idle"          # no hay sesión
FOCUS = "focus"        # concentrado
BREAK = "break"        # descanso del pomodoro
TOLERANCE = "tolerance"  # se acabó el descanso y todavía no volviste
PAUSED = "paused"      # cortaste vos: el bloque se reinicia
AWAY = "away"          # pausa corta: algo puntual, sin perder el bloque

# --- tipos de tramo (los que se guardan y se dibujan) ---
# Tres tipos de tramo. Cortar por distracción y la pausa corta caen los dos en
# "away": la diferencia entre ambos es sólo qué pasa con el bloque de pomodoro
# (uno lo reinicia y el otro lo congela), no qué clase de tiempo fue.
KIND_OF_STATE = {
    FOCUS: "focus",
    BREAK: "rest",
    TOLERANCE: "rest",
    PAUSED: "away",
    AWAY: "away",
}

#: Tipos de tramo que ya no existen. Una sesión interrumpida antes de que se
#: unificaran distracción y ausente puede traer "idle" en su archivo de
#: recuperación, y sin esto al retomarla se caía.
LEGACY_KINDS = {"idle": "away"}


def normalize_kind(kind):
    return LEGACY_KINDS.get(kind, kind)

# --- eventos que la interfaz escucha ---
PHASE_CHANGED = "phase_changed"
BLOCK_DONE = "block_done"
BREAK_DONE = "break_done"
AUTO_PAUSED = "auto_paused"
AWAY_EXPIRED = "away_expired"
AWAY_ENDED = "away_ended"      # volviste de la pausa corta
NAG = "nag"


@dataclass
class Event:
    name: str
    detail: str = ""


@dataclass
class Totals:
    total: float = 0.0
    focus: float = 0.0
    rest: float = 0.0
    away: float = 0.0

    @property
    def productivity(self):
        return (self.focus / self.total * 100.0) if self.total > 0 else 0.0

    def as_dict(self):
        """El detalle que se guarda en la base."""
        return {"focus": self.focus, "rest": self.rest, "away": self.away}

    def as_display(self):
        """Las dos categorías que se muestran: concentrado o no."""
        return {"focus": self.focus, "other": self.rest + self.away}


@dataclass
class Engine:
    """Una sesión en curso."""

    focus_target: int = 0        # segundos por bloque de concentración
    break_target: int = 0
    tolerance_target: int = 0
    away_limit: int = 300        # cuánto puede durar una pausa corta
    auto_start_break: bool = True
    auto_start_focus: bool = False
    preset: str = ""

    state: str = IDLE
    started_at: datetime | None = None
    ended_at: datetime | None = None
    segments: list = field(default_factory=list)
    pauses: int = 0
    blocks: int = 0

    focus_remaining: float = 0.0
    break_remaining: float = 0.0
    tolerance_remaining: float = 0.0
    away_remaining: float = 0.0

    _segment_kind: str | None = None
    _segment_start: float = 0.0
    _last_tick: datetime | None = None
    _resume_state: str = FOCUS
    _next_nag: datetime | None = None

    # ------------------------------------------------------------------ #
    # Consultas
    # ------------------------------------------------------------------ #

    @property
    def running(self):
        return self.state != IDLE

    @property
    def pomodoro_on(self):
        return self.focus_target > 0 and self.break_target > 0

    def elapsed(self, now=None):
        if self.started_at is None:
            return 0.0
        return max(0.0, ((now or datetime.now()) - self.started_at).total_seconds())

    def totals(self, now=None):
        """Suma los tramos cerrados más el que está abierto."""
        result = Totals()
        for segment in self.segments:
            kind = normalize_kind(segment["kind"])
            setattr(result, kind, getattr(result, kind) + segment["end"] - segment["start"])
        if self._segment_kind is not None:
            kind = normalize_kind(self._segment_kind)
            open_length = max(0.0, self.elapsed(now) - self._segment_start)
            setattr(result, kind, getattr(result, kind) + open_length)
        result.total = result.focus + result.rest + result.away
        return result

    def spans(self, now=None):
        """Tramos para dibujar, incluyendo el abierto."""
        result = [(s["start"], s["end"], s["kind"]) for s in self.segments]
        if self._segment_kind is not None:
            end = self.elapsed(now)
            if end > self._segment_start:
                result.append((self._segment_start, end, self._segment_kind))
        return result

    def phase_progress(self):
        """(restante, total) de la fase actual, para el anillo y el reloj."""
        if self.state == FOCUS and self.focus_target:
            return self.focus_remaining, self.focus_target
        if self.state == BREAK and self.break_target:
            return self.break_remaining, self.break_target
        if self.state == TOLERANCE and self.tolerance_target:
            return self.tolerance_remaining, self.tolerance_target
        if self.state == AWAY and self.away_limit:
            return self.away_remaining, self.away_limit
        return 0.0, 0.0

    # ------------------------------------------------------------------ #
    # Tramos
    # ------------------------------------------------------------------ #

    def _switch(self, state, now):
        """Cierra el tramo abierto y abre el del estado nuevo."""
        offset = self.elapsed(now)
        kind = KIND_OF_STATE.get(state)

        if self._segment_kind is not None and offset - self._segment_start > 0.4:
            if self.segments and self.segments[-1]["kind"] == self._segment_kind:
                self.segments[-1]["end"] = round(offset, 2)   # contiguo: se extiende
            else:
                self.segments.append({
                    "start": round(self._segment_start, 2),
                    "end": round(offset, 2),
                    "kind": self._segment_kind,
                })

        self._segment_kind = kind
        self._segment_start = offset
        self.state = state

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #

    def start(self, focus_target, break_target, tolerance_target, away_limit=300,
              preset="", now=None):
        now = now or datetime.now()
        self.focus_target = max(0, int(focus_target))
        self.break_target = max(0, int(break_target))
        self.tolerance_target = max(0, int(tolerance_target))
        self.away_limit = max(30, int(away_limit))
        self.preset = preset

        self.started_at = now
        self.ended_at = None
        self.segments = []
        self.pauses = 0
        self.blocks = 1 if self.pomodoro_on else 0
        self.focus_remaining = self.focus_target
        self.break_remaining = self.break_target
        self.tolerance_remaining = self.tolerance_target
        self.away_remaining = self.away_limit
        self._segment_kind = None
        self._segment_start = 0.0
        self._last_tick = now
        self._next_nag = None
        self._switch(FOCUS, now)
        return [Event(PHASE_CHANGED, FOCUS)]

    def finish(self, title="", notes="", now=None):
        """Cierra la sesión y devuelve el registro listo para guardar."""
        now = now or datetime.now()
        self._switch(IDLE, now)
        self._segment_kind = None
        self.ended_at = now
        self.state = IDLE
        totals = self.totals(now)
        record = {
            "started_at": self.started_at or now,
            "ended_at": now,
            "total": totals.total,
            "focus": totals.focus,
            "rest": totals.rest,
            "away": totals.away,
            "pauses": self.pauses,
            "blocks": self.blocks,
            "focus_target": self.focus_target,
            "break_target": self.break_target,
            "preset": self.preset,
            "title": title,
            "notes": notes,
            "segments": list(self.segments),
        }
        return record

    # ------------------------------------------------------------------ #
    # Acciones del usuario
    # ------------------------------------------------------------------ #

    def pause(self, now=None):
        """Corte por distracción: el bloque se reinicia al volver."""
        if self.state in (IDLE, PAUSED):
            return []
        now = now or datetime.now()
        self._switch(PAUSED, now)
        self.pauses += 1
        self._last_tick = now
        self._next_nag = None
        return [Event(PHASE_CHANGED, PAUSED)]

    def resume(self, now=None):
        """Vuelve a concentrarse desde cualquier estado que no sea concentración."""
        if self.state in (IDLE, FOCUS):
            return []
        now = now or datetime.now()
        return self._enter_focus(now, reset=True)

    def short_pause(self, now=None):
        """Pausa corta: se congela el bloque y no cuenta como distracción.

        Es la idea anotada en `ideas.txt`: te hablan o vas al baño, no estás
        pelotudeando ni descansando, y no querés perder el pomodoro.
        """
        if self.state in (IDLE, AWAY):
            return []
        now = now or datetime.now()
        self._resume_state = self.state if self.state in (FOCUS, BREAK) else FOCUS
        self.away_remaining = self.away_limit
        self._switch(AWAY, now)
        self._last_tick = now
        return [Event(PHASE_CHANGED, AWAY)]

    def end_short_pause(self, now=None):
        """Vuelve a la fase que estaba, con el bloque donde lo había dejado."""
        if self.state != AWAY:
            return []
        now = now or datetime.now()
        target = self._resume_state
        self._switch(target, now)
        self._last_tick = now
        # Evento propio y no PHASE_CHANGED: volver de una pausa corta tiene su
        # aviso, distinto del de empezar a concentrarse de cero.
        return [Event(AWAY_ENDED, target)]

    def toggle_phase(self, now=None):
        """Cambia a mano entre concentración y descanso."""
        if not self.pomodoro_on or self.state in (IDLE, PAUSED, AWAY):
            return []
        now = now or datetime.now()
        if self.state == FOCUS:
            return self._enter_break(now)
        return self._enter_focus(now, reset=True)

    def reconfigure(self, focus_target, break_target, tolerance_target, now=None):
        """Cambia los tiempos con la sesión andando."""
        now = now or datetime.now()
        self.focus_target = max(0, int(focus_target))
        self.break_target = max(0, int(break_target))
        self.tolerance_target = max(0, int(tolerance_target))

        if not self.pomodoro_on:
            # Sin bloques el reloj corre libre: si estabas descansando o en
            # tolerancia, no tiene sentido seguir ahí.
            if self.state in (BREAK, TOLERANCE):
                return self._enter_focus(now, reset=False)
            return []

        if self.state == FOCUS:
            self.focus_remaining = min(self.focus_remaining or self.focus_target,
                                       self.focus_target)
            if self.focus_remaining <= 0:
                self.focus_remaining = self.focus_target
        elif self.state == BREAK:
            self.break_remaining = min(self.break_remaining or self.break_target,
                                       self.break_target)
        elif self.state == TOLERANCE:
            self.tolerance_remaining = self.tolerance_target
        return []

    # ------------------------------------------------------------------ #
    # Transiciones internas
    # ------------------------------------------------------------------ #

    def _enter_focus(self, now, reset=True):
        if reset:
            self.focus_remaining = self.focus_target
        if self.pomodoro_on:
            self.blocks += 1
        self._switch(FOCUS, now)
        self._last_tick = now
        self._next_nag = None
        return [Event(PHASE_CHANGED, FOCUS)]

    def _enter_break(self, now):
        self.break_remaining = self.break_target
        self.tolerance_remaining = self.tolerance_target
        self._switch(BREAK, now)
        self._last_tick = now
        self._next_nag = None
        return [Event(PHASE_CHANGED, BREAK)]

    def _enter_tolerance(self, now):
        self.tolerance_remaining = self.tolerance_target
        self._switch(TOLERANCE, now)
        self._last_tick = now
        self._next_nag = now + timedelta(seconds=20)
        return [Event(PHASE_CHANGED, TOLERANCE)]

    # ------------------------------------------------------------------ #
    # Reloj
    # ------------------------------------------------------------------ #

    def tick(self, now=None, _depth=0):
        """Avanza los contadores. Devuelve los eventos que ocurrieron.

        Cuando un contador vence en medio del intervalo, la transición se hace en
        el instante exacto del vencimiento y no cuando llegó el tick. Si no, el
        sobrante se anotaba en la categoría equivocada: una pausa corta de 2
        minutos de margen podía terminar contando 2:20 de "ausente" sólo porque
        el tick cayó veinte segundos tarde.
        """
        now = now or datetime.now()
        if self.state == IDLE or self._last_tick is None:
            self._last_tick = now
            return []

        delta = (now - self._last_tick).total_seconds()
        if delta <= 0:
            return []
        self._last_tick = now

        def expiry_moment(before):
            """Instante en que se agotó el contador dentro de este intervalo."""
            return now - timedelta(seconds=max(0.0, delta - before))

        def carry(events):
            """Consume el resto del intervalo ya en la fase nueva."""
            if _depth < 6:
                events += self.tick(now, _depth + 1)
            return events

        events = []

        if self.state == FOCUS and self.pomodoro_on:
            before = self.focus_remaining
            self.focus_remaining = max(0.0, before - delta)
            if self.focus_remaining <= 0:
                events.append(Event(BLOCK_DONE))
                if self.auto_start_break:
                    return carry(events + self._enter_break(expiry_moment(before)))
                self.focus_remaining = self.focus_target

        elif self.state == BREAK:
            before = self.break_remaining
            self.break_remaining = max(0.0, before - delta)
            if self.break_remaining <= 0:
                moment = expiry_moment(before)
                events.append(Event(BREAK_DONE))
                if self.auto_start_focus:
                    return carry(events + self._enter_focus(moment, reset=True))
                if self.tolerance_target > 0:
                    return carry(events + self._enter_tolerance(moment))
                events += self.pause(moment)
                events.append(Event(AUTO_PAUSED))
                return carry(events)

        elif self.state == TOLERANCE:
            before = self.tolerance_remaining
            self.tolerance_remaining = max(0.0, before - delta)
            if self._next_nag is not None and now >= self._next_nag:
                self._next_nag = now + timedelta(seconds=20)
                events.append(Event(NAG))
            if self.tolerance_remaining <= 0:
                events += self.pause(expiry_moment(before))
                events.append(Event(AUTO_PAUSED))
                return carry(events)

        elif self.state == AWAY:
            before = self.away_remaining
            self.away_remaining = max(0.0, before - delta)
            if self.away_remaining <= 0:
                # Se pasó del margen: a partir de acá sí cuenta como distracción.
                events += self.pause(expiry_moment(before))
                events.append(Event(AWAY_EXPIRED))
                return carry(events)

        return events


