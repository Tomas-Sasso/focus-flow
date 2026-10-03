"""Análisis: los patrones que no se ven sesión a sesión."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import customtkinter as ctk

from .. import stats
from .. import widgets as W
from ..theme import COLORS, DATA, RADIUS, SPACE, score_color


class InsightsView(ctk.CTkFrame):
    RANGES = ["7 días", "30 días", "90 días", "Todo"]

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.db = app.db
        self.fonts = app.fonts
        self.animator = app.animator
        self._rows = []
        self._build()

    # ------------------------------------------------------------------ #

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["surface2"],
            scrollbar_button_hover_color=COLORS["surface3"])
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        self.body = scroll

        self._build_summary()
        self._build_heatmap()
        self._build_rhythm()
        self._build_tags()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))

        self.range_control = W.SegmentedControl(
            bar, self.animator, COLORS["app"], self.fonts, self.RANGES,
            command=self._on_range, height=32, stretch=False)
        self.range_control.pack(side="left")
        self.range_control.configure(width=self.range_control.measure_width())
        self.range_control.select(self._default_range(), animate=False)

        ctk.CTkLabel(bar, text="Hashtag", font=self.fonts["tiny"],
                     text_color=COLORS["text_dim"]).pack(side="left",
                                                         padx=(SPACE["xl"], SPACE["sm"]))
        self.tag_menu = ctk.CTkOptionMenu(
            bar, values=["Todos"], command=lambda _v: self.refresh(), width=170,
            fg_color=COLORS["surface2"], button_color=COLORS["surface3"],
            button_hover_color=COLORS["surface4"], text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface2"], dropdown_text_color=COLORS["text"],
            dropdown_hover_color=COLORS["surface3"], font=self.fonts["small"],
            dropdown_font=self.fonts["small"], corner_radius=RADIUS["xs"], height=32)
        self.tag_menu.set("Todos")
        self.tag_menu.pack(side="left")

        W.button(bar, self.animator, "Exportar CSV", self.app.export_csv, tone="quiet",
                 font=self.fonts["button"], height=32, width=130).pack(side="right")

        self.range_label = ctk.CTkLabel(bar, text="", font=self.fonts["tiny"],
                                        text_color=COLORS["text_dim"])
        self.range_label.pack(side="right", padx=(0, SPACE["lg"]))

    def _default_range(self):
        """Si el último mes está vacío pero hay historial, arrancamos en Todo."""
        today = date.today()
        recent = self.db.sessions_between(today - timedelta(days=29), today)
        if not recent and self.db.count():
            return "Todo"
        return "30 días"

    def _build_summary(self):
        card = W.Card(self.body)
        card.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))

        tiles = ctk.CTkFrame(card, fg_color="transparent")
        tiles.pack(fill="x", padx=SPACE["xl"], pady=SPACE["lg"])
        tiles.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="sum")

        self.tiles = {}
        specs = (
            ("sessions", "Sesiones", None, lambda v: f"{v:.0f}"),
            ("productivity", "Productividad", COLORS["accent"], lambda v: f"{v:.0f}%"),
            ("focus", "Concentración", DATA["focus"], W.fmt_short),
            ("not_focus", "No concentración", DATA["other"], W.fmt_short),
            ("pauses", "Cortes", None, lambda v: f"{v:.0f}"),
        )
        for index, (key, label, color, formatter) in enumerate(specs):
            tile = W.StatTile(tiles, self.animator, self.fonts, label, color=color,
                              formatter=formatter)
            tile.grid(row=0, column=index, sticky="ew",
                      padx=(0 if index == 0 else SPACE["xs"],
                            0 if index == len(specs) - 1 else SPACE["xs"]))
            self.tiles[key] = tile

        charts = ctk.CTkFrame(card, fg_color="transparent")
        charts.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["lg"]))
        charts.grid_columnconfigure(0, weight=0, minsize=210)
        charts.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(charts, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["xl"]))
        self.donut = W.DonutChart(left, self.animator, COLORS["surface"], self.fonts,
                                  key="insights", max_size=180, height=180)
        self.donut.pack(fill="x")
        self.legend = W.Legend(left, self.fonts, background=COLORS["surface"])
        self.legend.pack(anchor="w", pady=(SPACE["md"], 0))

        right = ctk.CTkFrame(charts, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        self.series_title = ctk.CTkLabel(right, text="Concentración por día",
                                         font=self.fonts["card"],
                                         text_color=COLORS["text_muted"])
        self.series_title.grid(row=0, column=0, sticky="w", pady=(0, SPACE["sm"]))
        self.series_bars = W.BarsView(right, COLORS["surface"], self.fonts,
                                      color=COLORS["accent"], height=190)
        self.series_bars.grid(row=1, column=0, sticky="ew")

    def _build_heatmap(self):
        card = W.Card(self.body)
        card.grid(row=1, column=0, sticky="ew", pady=(0, SPACE["md"]))

        header = W.card_title(card, self.fonts, "Mapa del año")
        self.heat_hint = ctk.CTkLabel(header, text="", font=self.fonts["tiny"],
                                      text_color=COLORS["text_dim"])
        self.heat_hint.pack(side="right", pady=(4, 0))

        self.heatmap = W.Heatmap(card, COLORS["surface"], self.fonts,
                                 on_select=self.app.open_day)
        self.heatmap.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["sm"]))
        self.heatmap.bind("<Motion>", self._on_heat_motion, add="+")
        self.heatmap.bind("<Leave>",
                          lambda _e: self.heat_hint.configure(text=""), add="+")

        self.streak_label = ctk.CTkLabel(card, text="", font=self.fonts["small"],
                                         text_color=COLORS["text_muted"], anchor="w")
        self.streak_label.pack(anchor="w", padx=SPACE["xl"], pady=(0, SPACE["lg"]))

    def _on_heat_motion(self, _event):
        self.heat_hint.configure(text=self.heatmap.tooltip_for(self.heatmap._hover))

    def _build_rhythm(self):
        container = ctk.CTkFrame(self.body, fg_color="transparent")
        container.grid(row=2, column=0, sticky="ew", pady=(0, SPACE["md"]))
        container.grid_columnconfigure(0, weight=0, minsize=330)
        container.grid_columnconfigure(1, weight=1)

        clock_card = W.Card(container)
        clock_card.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["md"]))
        W.card_title(clock_card, self.fonts, "Tu reloj de concentración")
        self.hours = W.RadialHours(clock_card, COLORS["surface"], self.fonts,
                                   max_size=250, height=250)
        self.hours.pack(fill="x", padx=SPACE["xl"])
        self.hours_caption = ctk.CTkLabel(clock_card, text="", font=self.fonts["small"],
                                          text_color=COLORS["text_muted"],
                                          wraplength=280, justify="left")
        self.hours_caption.pack(anchor="w", padx=SPACE["xl"],
                                pady=(SPACE["md"], SPACE["lg"]))

        week_card = W.Card(container)
        week_card.grid(row=0, column=1, sticky="nsew")
        week_card.grid_columnconfigure(0, weight=1)
        W.card_title(week_card, self.fonts, "Por día de la semana")
        self.weekday_bars = W.BarsView(week_card, COLORS["surface"], self.fonts,
                                       color=COLORS["mint"], height=170)
        self.weekday_bars.pack(fill="x", padx=SPACE["xl"])

        ctk.CTkLabel(week_card, text="Récords", font=self.fonts["card"],
                     text_color=COLORS["text_muted"]).pack(
            anchor="w", padx=SPACE["xl"], pady=(SPACE["lg"], SPACE["sm"]))
        self.records_box = ctk.CTkFrame(week_card, fg_color="transparent")
        self.records_box.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["lg"]))

    def _build_tags(self):
        card = W.Card(self.body)
        card.grid(row=3, column=0, sticky="ew")
        W.card_title(card, self.fonts, "Hashtags")
        self.tags_box = ctk.CTkFrame(card, fg_color="transparent")
        self.tags_box.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["lg"]))

    # ------------------------------------------------------------------ #

    def _on_range(self, value):
        self.range_control.select(value)
        self.refresh()

    def refresh_tags(self):
        values = ["Todos"] + [f"#{t}" for t in self.db.all_tags(60)]
        current = self.tag_menu.get()
        self.tag_menu.configure(values=values)
        if current not in values:
            self.tag_menu.set("Todos")

    def _range_bounds(self):
        today = date.today()
        choice = self.range_control.get()
        if choice == "Todo":
            first, _ = self.db.day_bounds()
            return first, today
        days = {"7 días": 7, "30 días": 30, "90 días": 90}.get(choice, 30)
        return today - timedelta(days=days - 1), today

    def refresh(self):
        start, end = self._range_bounds()
        tag_value = self.tag_menu.get()
        tag = None if tag_value == "Todos" else tag_value.lstrip("#")
        rows = self.db.sessions_between(start, end, tag)
        self._rows = rows

        label = f"{start.strftime('%d/%m/%Y')} → {end.strftime('%d/%m/%Y')}"
        if tag:
            label = f"#{tag} · {label}"
        self.range_label.configure(text=label)

        summary = stats.totals(rows)
        for key in ("sessions", "productivity", "focus", "not_focus", "pauses"):
            self.tiles[key].set_value(summary[key])

        self.donut.set_values(stats.display_split(summary))
        self.legend.set_values(stats.display_percentages(summary))

        values, labels, title = stats.daily_series(rows, start, end)
        self.series_title.configure(text=title)
        self.series_bars.set_data(values, labels)

        self._refresh_heatmap(tag)
        self._refresh_rhythm(rows)
        self._refresh_tag_ranking(rows)

    def _refresh_heatmap(self, tag):
        if tag:
            rows = self.db.sessions_between(date(2000, 1, 1), date.today(), tag)
            focus_map = stats.by_day(rows)
        else:
            focus_map = self.db.focus_by_day()
        cells, columns, month_labels, origin = stats.heatmap_cells(
            focus_map, weeks=self.heatmap.weeks_that_fit())
        self.heatmap.set_data(cells, columns, month_labels, origin)

        current = stats.streak(focus_map)
        best = stats.best_streak(focus_map)
        active_days = sum(1 for value in focus_map.values() if value >= 60)
        parts = [f"{active_days} días con actividad"]
        if current:
            parts.append(f"racha actual de {current}")
        if best:
            parts.append(f"mejor racha: {best}")
        self.streak_label.configure(text=" · ".join(parts))

    def _refresh_rhythm(self, rows):
        hours = stats.by_hour(rows, self.db)
        self.hours.set_values([value / 3600.0 for value in hours])
        peak = max(hours) if hours else 0
        if peak > 0:
            best = hours.index(peak)
            morning = sum(hours[5:12])
            afternoon = sum(hours[12:19])
            night = sum(hours[19:24]) + sum(hours[0:5])
            franja = max((("la mañana", morning), ("la tarde", afternoon),
                          ("la noche", night)), key=lambda item: item[1])[0]
            self.hours_caption.configure(
                text=f"Tu mejor hora es entre las {best:02d}:00 y las {best + 1:02d}:00. "
                     f"En conjunto rendís más durante {franja}.")
        else:
            self.hours_caption.configure(text="Todavía no hay suficientes datos.")

        totals_, averages = stats.by_weekday(rows)
        self.weekday_bars.set_data([value / 3600.0 for value in totals_],
                                   stats.WEEKDAY_SHORT)

        for child in self.records_box.winfo_children():
            child.destroy()
        found = stats.records(rows, stats.by_day(rows))

        def line(label, value, detail=""):
            row = ctk.CTkFrame(self.records_box, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, font=self.fonts["small"],
                         text_color=COLORS["text_dim"]).pack(side="left")
            ctk.CTkLabel(row, text=value, font=self.fonts["small_bold"],
                         text_color=COLORS["text"]).pack(side="right")
            if detail:
                ctk.CTkLabel(row, text=detail, font=self.fonts["tiny"],
                             text_color=COLORS["text_faint"]).pack(side="right",
                                                                   padx=(0, SPACE["sm"]))

        session = found["best_session"]
        if session is not None:
            line("Sesión más larga", W.fmt_short(session["focus_seconds"] or 0),
                 session["day"])
        day, seconds = found["best_day"]
        if day is not None and seconds > 0:
            line("Mejor día", W.fmt_short(seconds), day.strftime("%d/%m/%Y"))
        rate = found["best_rate"]
        if rate is not None:
            line("Mejor concentración", f"{rate[1]:.0f}%", rate[0]["day"])
        if not self.records_box.winfo_children():
            ctk.CTkLabel(self.records_box, text="Todavía no hay récords que mostrar.",
                         font=self.fonts["small"],
                         text_color=COLORS["text_faint"]).pack(anchor="w")

    def _refresh_tag_ranking(self, rows):
        for child in self.tags_box.winfo_children():
            child.destroy()
        ranking = stats.tag_ranking(self.db, rows)
        if not ranking:
            ctk.CTkLabel(self.tags_box,
                         text="Escribí #algo en las descripciones y vas a poder medir "
                              "cuánto le dedicaste a cada cosa.",
                         font=self.fonts["small"], text_color=COLORS["text_faint"],
                         wraplength=560, justify="left").pack(anchor="w")
            return

        peak = max(focus for _, focus, _, _ in ranking) or 1
        for tag, focus, percentage, count in ranking:
            row = ctk.CTkFrame(self.tags_box, fg_color="transparent")
            row.pack(fill="x", pady=4)
            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x")
            ctk.CTkLabel(head, text=f"#{tag}", font=self.fonts["small_bold"],
                         text_color=COLORS["lavender"]).pack(side="left")
            ctk.CTkLabel(head,
                         text=f"{W.fmt_hours(focus)} · {percentage:.0f}% · "
                              f"{count} {'sesión' if count == 1 else 'sesiones'}",
                         font=self.fonts["tiny"],
                         text_color=COLORS["text_muted"]).pack(side="right")
            bar = W.ProgressBar(row, self.animator, COLORS["surface"],
                                color=score_color(percentage), height=6)
            bar.pack(fill="x", pady=(3, 0))
            bar.set_fraction(focus / peak, animate=False)

    def current_rows(self):
        return self._rows
