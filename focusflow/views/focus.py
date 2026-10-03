"""Pantalla de enfoque: la sesión en curso.

Los controles siguen una regla: **un solo botón grande a la vez**. Cuál es
depende del estado, y sólo aparecen los secundarios que tienen sentido en ese
momento. Sin sesión hay un único botón en toda la pantalla; concentrado hay uno
grande y dos chicos. Antes había cinco botones siempre visibles, la mitad de
ellos deshabilitados, y no quedaba claro cuál apretar.
"""

from __future__ import annotations

from datetime import date, timedelta

import customtkinter as ctk

from .. import engine as E
from .. import stats
from .. import widgets as W
from ..theme import COLORS, DATA, PHASE_STYLE, RADIUS, SPACE

# Qué hace el botón grande en cada estado: (texto, tono, ayuda).
# El rojo queda reservado para "Terminar sesión", que es lo irreversible; pausar
# es ámbar, que se distingue de un vistazo y no compite con él.
PRIMARY_ACTION = {
    "idle":      ("Comenzar sesión",       "accent",  ""),
    E.FOCUS:     ("Pausar",                "amber",
                  "Pausar reinicia el bloque. Si es algo puntual, usá Pausa corta."),
    E.PAUSED:    ("Volver a concentrarme", "mint",    "El bloque arranca de nuevo."),
    E.BREAK:     ("Volver a concentrarme", "mint",    ""),
    E.TOLERANCE: ("Volver a concentrarme", "mint",    "Volvé antes de que se pause solo."),
    E.AWAY:      ("Ya volví",              "mint",
                  "El bloque está congelado, seguís donde lo dejaste."),
}


class FocusView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.fonts = app.fonts
        self.animator = app.animator
        self._build()

    # ------------------------------------------------------------------ #
    # Construcción
    # ------------------------------------------------------------------ #

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=5, uniform="focus")
        self.grid_columnconfigure(1, weight=4, uniform="focus")

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["md"]))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        self._build_stage(left)
        self._build_controls(left)
        self._build_breakdown(right)
        self._build_today(right)

    def _build_stage(self, parent):
        """El anillo grande con el reloj: lo primero que se mira."""
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="nsew", pady=(0, SPACE["md"]))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=SPACE["xl"],
                    pady=(SPACE["lg"], 0))
        self.phase_chip = W.Chip(header, self.animator, COLORS["surface"], self.fonts,
                                 text="Sin sesión", color=COLORS["surface3"],
                                 height=28, width=180)
        self.phase_chip.pack(side="left")

        # "Terminar" vive acá arriba, discreto, para no competir con la acción
        # principal de abajo.
        # En rosa: es la acción que cierra todo, conviene que se reconozca, pero
        # sin un rojo lleno que compita con la acción principal.
        self.end_button = W.button(header, self.animator, "Terminar sesión",
                                   self.app.on_end, tone="destructive",
                                   font=self.fonts["button"], height=30, width=136)
        self.block_label = ctk.CTkLabel(header, text="", font=self.fonts["tiny"],
                                        text_color=COLORS["text_dim"])
        self.block_label.pack(side="right", padx=(SPACE["md"], 0), pady=(6, 0))

        self.ring = W.GoalRing(card, self.animator, COLORS["surface"], self.fonts,
                               max_size=330)
        self.ring.grid(row=1, column=0, sticky="nsew", padx=SPACE["xl"],
                       pady=SPACE["md"])
        self.ring.set_text("00:00:00", "Todavía no arrancaste")

        self.timeline = W.TimelineBar(card, COLORS["surface"], height=14)
        self.timeline.grid(row=2, column=0, sticky="ew", padx=SPACE["xl"])

        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=SPACE["xl"],
                    pady=(SPACE["sm"], SPACE["lg"]))
        ctk.CTkLabel(footer, text="La línea muestra cuándo pasó cada cosa",
                     font=self.fonts["tiny"],
                     text_color=COLORS["text_faint"]).pack(side="left")
        self.pause_label = ctk.CTkLabel(footer, text="", font=self.fonts["tiny"],
                                        text_color=COLORS["text_dim"])
        self.pause_label.pack(side="right")

    def _build_controls(self, parent):
        card = W.Card(parent)
        card.grid(row=1, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        self.primary_button = W.button(
            card, self.animator, "Comenzar sesión", self.app.on_primary,
            tone="accent", font=self.fonts["button_lg"], height=50,
            corner_radius=RADIUS["sm"])
        self.primary_button.grid(row=0, column=0, sticky="ew", padx=SPACE["xl"],
                                 pady=(SPACE["lg"], SPACE["sm"]))

        # Fila secundaria: se muestra entera o no se muestra.
        self.secondary = ctk.CTkFrame(card, fg_color="transparent")
        self.secondary.grid(row=1, column=0, sticky="ew", padx=SPACE["xl"])
        self.secondary.grid_columnconfigure((0, 1, 2), weight=1, uniform="sec")

        self.away_button = W.button(self.secondary, self.animator, "Pausa corta",
                                    self.app.on_short_pause, tone="ghost",
                                    font=self.fonts["button"], height=36)
        self.phase_button = W.button(self.secondary, self.animator, "Ir a descanso",
                                     self.app.on_toggle_phase, tone="ghost",
                                     font=self.fonts["button"], height=36)
        self.tune_button = W.button(self.secondary, self.animator, "Ajustar ritmo",
                                    self.app.show_tune_dialog, tone="ghost",
                                    font=self.fonts["button"], height=36)

        self.hint_label = ctk.CTkLabel(card, text="", font=self.fonts["tiny"],
                                       text_color=COLORS["text_faint"],
                                       wraplength=430, justify="left")
        self.hint_label.grid(row=2, column=0, sticky="w", padx=SPACE["xl"],
                             pady=(SPACE["sm"], 0))

        self.shortcuts = ctk.CTkFrame(card, fg_color="transparent")
        self.shortcuts.grid(row=3, column=0, sticky="ew", padx=SPACE["xl"],
                            pady=(SPACE["sm"], SPACE["lg"]))
        for key, text in (("F8", "pausar"), ("F9", "volver"), ("F10", "pausa corta")):
            ctk.CTkLabel(self.shortcuts, text=key, font=self.fonts["micro"],
                         text_color=COLORS["text_muted"], fg_color=COLORS["surface2"],
                         corner_radius=5, width=30, height=19).pack(
                side="left", padx=(0, SPACE["xs"]))
            ctk.CTkLabel(self.shortcuts, text=text, font=self.fonts["micro"],
                         text_color=COLORS["text_faint"]).pack(
                side="left", padx=(0, SPACE["md"]))

        self.config_label = ctk.CTkLabel(card, text="", font=self.fonts["small"],
                                         text_color=COLORS["text_dim"],
                                         wraplength=430, justify="left")
        self.config_label.grid(row=4, column=0, sticky="w", padx=SPACE["xl"],
                               pady=(0, SPACE["lg"]))

    def _build_breakdown(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))

        W.card_title(card, self.fonts, "Reparto de la sesión")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["md"]))
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        self.donut = W.DonutChart(body, self.animator, COLORS["surface"], self.fonts,
                                  key="live", max_size=170, width=170, height=170)
        self.donut.grid(row=0, column=0, sticky="nw")

        self.legend = W.Legend(body, self.fonts, background=COLORS["surface"])
        self.legend.grid(row=0, column=1, sticky="w", padx=(SPACE["lg"], 0))

        tiles = ctk.CTkFrame(card, fg_color="transparent")
        tiles.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["lg"]))
        tiles.grid_columnconfigure((0, 1), weight=1, uniform="ft")

        self.tiles = {}
        for index, (key, label, color, formatter) in enumerate((
            ("total", "Tiempo total", None, W.fmt_hms),
            ("focus", "Concentración", DATA["focus"], W.fmt_hms),
        )):
            tile = W.StatTile(tiles, self.animator, self.fonts, label, color=color,
                              formatter=formatter)
            tile.grid(row=0, column=index, sticky="ew",
                      padx=(0, SPACE["xs"]) if index == 0 else (SPACE["xs"], 0))
            self.tiles[key] = tile

    def _build_today(self, parent):
        card = W.Card(parent)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=SPACE["xl"],
                    pady=(SPACE["lg"], SPACE["sm"]))
        ctk.CTkLabel(header, text="Objetivo de hoy", font=self.fonts["section"],
                     text_color=COLORS["text"]).pack(side="left")
        # El objetivo se cambia desde acá mismo, que es donde se lo mira.
        W.button(header, self.animator, "Cambiar", self.app.show_goal_dialog,
                 tone="quiet", font=self.fonts["button"], height=26, width=84,
                 corner_radius=RADIUS["xs"]).pack(side="right")
        self.goal_label = ctk.CTkLabel(header, text="", font=self.fonts["tiny"],
                                       text_color=COLORS["text_dim"])
        self.goal_label.pack(side="right", padx=(0, SPACE["md"]), pady=(4, 0))

        self.goal_bar = W.ProgressBar(card, self.animator, COLORS["surface"],
                                      color=COLORS["accent"], height=8)
        self.goal_bar.grid(row=1, column=0, sticky="ew", padx=SPACE["xl"])

        self.streak_label = ctk.CTkLabel(card, text="", font=self.fonts["small"],
                                         text_color=COLORS["text_muted"], anchor="w",
                                         justify="left")
        self.streak_label.grid(row=2, column=0, sticky="ew", padx=SPACE["xl"],
                               pady=(SPACE["md"], SPACE["sm"]))

        week = ctk.CTkFrame(card, fg_color="transparent")
        week.grid(row=3, column=0, sticky="nsew", padx=SPACE["xl"],
                  pady=(0, SPACE["lg"]))
        week.grid_columnconfigure(0, weight=1)
        week.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(week, text="Últimos 7 días", font=self.fonts["card"],
                     text_color=COLORS["text_muted"]).grid(row=0, column=0, sticky="w",
                                                           pady=(0, SPACE["sm"]))
        self.week_bars = W.BarsView(week, COLORS["surface"], self.fonts,
                                    color=COLORS["accent"], height=110,
                                    empty_text="Todavía no hay sesiones")
        self.week_bars.grid(row=1, column=0, sticky="nsew")

    # ------------------------------------------------------------------ #
    # Actualización
    # ------------------------------------------------------------------ #

    def refresh_engine(self, engine, now=None):
        """Se llama en cada tick con el estado del motor."""
        running = engine.running
        state = engine.state if running else "idle"
        label, color, text_color = PHASE_STYLE.get(state, PHASE_STYLE["idle"])

        self.phase_chip.set_state(label, color, text_color)
        self.ring.set_color(color if running else COLORS["surface3"])

        totals = engine.totals(now)
        remaining, span = engine.phase_progress()

        if not running:
            self.ring.set_progress(0.0)
            self.ring.set_text("00:00:00", "Todavía no arrancaste", "")
        elif span > 0:
            self.ring.set_progress(1.0 - remaining / span, animate=False)
            self.ring.set_text(W.fmt_ms(remaining), _caption_for(state), label)
        else:
            self.ring.set_progress(0.0, animate=False)
            self.ring.set_text(W.fmt_hms(totals.total), "Tiempo total de la sesión",
                               label)

        self.timeline.set_spans(engine.spans(now), engine.elapsed(now))
        self.pause_label.configure(
            text=f"{engine.pauses} corte{'s' if engine.pauses != 1 else ''}"
            if running else "")
        self.block_label.configure(
            text=f"Bloque {engine.blocks}" if running and engine.pomodoro_on else "")

        self.tiles["total"].set_value(totals.total, animate=False)
        self.tiles["focus"].set_value(totals.focus, animate=False)
        split = totals.as_display()
        self.donut.set_values(split)
        if totals.total > 0:
            self.legend.set_values({
                key: f"{value / totals.total * 100:.0f}%"
                for key, value in split.items()})
        else:
            self.legend.set_values({"focus": "0%", "other": "0%"})

        self._refresh_buttons(engine)

    def _refresh_buttons(self, engine):
        """Muestra sólo lo que sirve en este estado."""
        running = engine.running
        state = engine.state if running else "idle"

        text, tone, hint = PRIMARY_ACTION.get(state, PRIMARY_ACTION["idle"])
        fill, hover, text_key = W.TONES[tone]
        self.primary_button.configure(text=text, text_color=COLORS[text_key])
        self.primary_button.set_base_color(COLORS[fill], COLORS[hover])
        self.hint_label.configure(text=hint)

        if not running:
            # Sin sesión hay un solo botón en toda la pantalla.
            self.secondary.grid_remove()
            self.shortcuts.grid_remove()
            self.end_button.pack_forget()
            return

        self.secondary.grid()
        self.shortcuts.grid()
        self.end_button.pack(side="right", pady=(0, 0))

        column = 0

        def place(button, show):
            nonlocal column
            if show:
                button.grid(row=0, column=column, sticky="ew",
                            padx=(0 if column == 0 else SPACE["xs"], 0))
                column += 1
            else:
                button.grid_remove()

        # La pausa corta no tiene sentido si ya estás en una.
        place(self.away_button, state != E.AWAY)
        place(self.phase_button, engine.pomodoro_on and state in (E.FOCUS, E.BREAK,
                                                                 E.TOLERANCE))
        place(self.tune_button, True)
        self.phase_button.configure(
            text="Ir a descanso" if state == E.FOCUS else "Ir a concentración")

    def set_config_text(self, engine, settings):
        if engine.running:
            if engine.pomodoro_on:
                text = (f"Bloques de {W.fmt_ms(engine.focus_target)} con "
                        f"{W.fmt_ms(engine.break_target)} de descanso.")
                if engine.tolerance_target:
                    text += f" Tolerancia de {W.fmt_ms(engine.tolerance_target)}."
            else:
                text = "Sesión libre: el reloj corre hasta que la termines."
            text += f" La pausa corta te da {W.fmt_ms(engine.away_limit)}."
        else:
            text = ("Al comenzar elegís el ritmo. La pausa corta sirve para cuando te "
                    "hablan o vas al baño: no te reinicia el bloque de pomodoro.")
        self.config_label.configure(text=text)

    def refresh_today(self, db, settings):
        today = date.today()
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        focus_map = db.focus_by_day()

        values = [focus_map.get(day, 0.0) / 3600.0 for day in days]
        labels = [W.WEEKDAY_INITIALS[day.weekday()] for day in days]
        self.week_bars.set_data(values, labels)

        goal_seconds = max(60, settings["daily_goal_minutes"] * 60)
        done = focus_map.get(today, 0.0)
        self.goal_bar.set_fraction(done / goal_seconds)
        self.goal_bar.set_color(COLORS["mint"] if done >= goal_seconds
                                else COLORS["accent"])
        self.goal_label.configure(
            text=f"{W.fmt_short(done)} de {W.fmt_short(goal_seconds)}")

        current = stats.streak(focus_map, today)
        week_total = sum(focus_map.get(day, 0.0) for day in days)
        parts = [f"Esta semana llevás {W.fmt_hours(week_total)}."]
        if done >= goal_seconds:
            parts.append("Objetivo de hoy cumplido.")
        if current > 1:
            parts.append(f"Racha de {current} días seguidos.")
        elif current == 1:
            parts.append("Arrancaste una racha.")
        self.streak_label.configure(text="  ".join(parts))

    def refresh(self):
        """Para que la vista responda a la misma interfaz que las demás."""
        self.refresh_today(self.app.db, self.app.settings)


def _caption_for(state):
    """Por qué no estás concentrado: el detalle va acá, no en más etiquetas."""
    return {
        E.FOCUS: "Restante del bloque",
        E.BREAK: "Descanso del pomodoro",
        E.TOLERANCE: "Se acabó el descanso: volvé antes de que se pause solo",
        E.AWAY: "Pausa corta: el bloque está congelado",
    }.get(state, "")
