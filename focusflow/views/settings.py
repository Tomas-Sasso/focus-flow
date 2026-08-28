"""Ajustes."""

from __future__ import annotations

import customtkinter as ctk

from .. import widgets as W
from ..config import PRESETS
from ..theme import COLORS, RADIUS, SPACE


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.settings = app.settings
        self.fonts = app.fonts
        self.animator = app.animator
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ #

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        left = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["surface2"],
            scrollbar_button_hover_color=COLORS["surface3"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["md"]))
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["surface2"],
            scrollbar_button_hover_color=COLORS["surface3"])
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        self._build_rhythm(left)
        self._build_goal(left)
        self._build_watcher(right)
        self._build_data(right)

    def _field(self, parent, label, hint=""):
        ctk.CTkLabel(parent, text=label, font=self.fonts["small_bold"],
                     text_color=COLORS["text"]).pack(anchor="w", padx=SPACE["xl"],
                                                     pady=(SPACE["md"], 0))
        if hint:
            ctk.CTkLabel(parent, text=hint, font=self.fonts["tiny"],
                         text_color=COLORS["text_faint"], wraplength=420,
                         justify="left").pack(anchor="w", padx=SPACE["xl"], pady=(1, 4))
        entry = ctk.CTkEntry(parent, fg_color=COLORS["surface2"],
                             border_color=COLORS["border"], border_width=1,
                             text_color=COLORS["text"], font=self.fonts["body"],
                             corner_radius=RADIUS["xs"], height=34)
        entry.pack(fill="x", padx=SPACE["xl"])
        return entry

    def _build_rhythm(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))
        W.card_title(card, self.fonts, "Ritmo por defecto")
        ctk.CTkLabel(card, text="Es lo que aparece propuesto al comenzar una sesión.",
                     font=self.fonts["small"], text_color=COLORS["text_dim"],
                     wraplength=420, justify="left").pack(anchor="w", padx=SPACE["xl"])

        presets = ctk.CTkFrame(card, fg_color="transparent")
        presets.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["md"], 0))
        for index, preset in enumerate(PRESETS):
            W.button(presets, self.animator, preset["name"],
                     lambda p=preset: self._apply_preset(p), tone="quiet",
                     font=self.fonts["button"], height=30).pack(
                side="left", padx=(0, SPACE["xs"]) if index < len(PRESETS) - 1 else 0)

        self.focus_entry = self._field(card, "Concentración (minutos)")
        self.break_entry = self._field(card, "Descanso (minutos)")
        self.tolerance_entry = self._field(
            card, "Tolerancia (minutos)",
            "Después del descanso, cuánto espera antes de pausarse solo. 0 lo desactiva.")
        self.away_entry = self._field(
            card, "Pausa corta (minutos)",
            "El margen para atender algo puntual sin que se te reinicie el bloque.")

        toggles = ctk.CTkFrame(card, fg_color="transparent")
        toggles.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["md"], 0))
        self.auto_break = self._switch(toggles, "Pasar al descanso automáticamente")
        self.auto_focus = self._switch(toggles, "Volver a concentración automáticamente")

        W.button(card, self.animator, "Guardar ritmo", self._save_rhythm, tone="accent",
                 font=self.fonts["button"], height=36).pack(
            fill="x", padx=SPACE["xl"], pady=(SPACE["lg"], SPACE["lg"]))

    def _switch(self, parent, text):
        switch = ctk.CTkSwitch(parent, text=text, font=self.fonts["small"],
                               text_color=COLORS["text_muted"],
                               progress_color=COLORS["accent"],
                               button_color=COLORS["text"],
                               button_hover_color=COLORS["text"],
                               fg_color=COLORS["surface3"])
        switch.pack(anchor="w", pady=4)
        return switch

    def _build_goal(self, parent):
        card = W.Card(parent)
        card.grid(row=1, column=0, sticky="ew")
        W.card_title(card, self.fonts, "Objetivo diario")
        self.goal_entry = self._field(
            card, "Minutos de concentración por día",
            "Es la meta del anillo de la pantalla de enfoque y de la racha.")
        W.button(card, self.animator, "Guardar objetivo", self._save_goal, tone="accent",
                 font=self.fonts["button"], height=36).pack(
            fill="x", padx=SPACE["xl"], pady=(SPACE["lg"], SPACE["lg"]))

    def _build_watcher(self, parent):
        card = W.Card(parent)
        card.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["md"]))
        W.card_title(card, self.fonts, "Vigilante de distracciones")
        ctk.CTkLabel(
            card,
            text="Mira el título de la ventana que tenés adelante. Si aparece alguna de "
                 "estas palabras durante más de unos segundos, te pregunta si querés "
                 "cortar la concentración. Nunca pausa por su cuenta y no manda nada a "
                 "ningún lado: se queda en tu computadora.",
            font=self.fonts["small"], text_color=COLORS["text_dim"], wraplength=420,
            justify="left").pack(anchor="w", padx=SPACE["xl"])

        holder = ctk.CTkFrame(card, fg_color="transparent")
        holder.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["md"], 0))
        self.watcher_switch = self._switch(holder, "Activar el vigilante")

        self.grace_entry = self._field(card, "Esperar (segundos) antes de avisar")
        ctk.CTkLabel(card, text="Palabras a vigilar, separadas por coma",
                     font=self.fonts["small_bold"], text_color=COLORS["text"]).pack(
            anchor="w", padx=SPACE["xl"], pady=(SPACE["md"], 4))
        self.keywords_box = ctk.CTkTextbox(
            card, height=90, fg_color=COLORS["surface2"], border_color=COLORS["border"],
            border_width=1, text_color=COLORS["text"], font=self.fonts["small"],
            corner_radius=RADIUS["xs"], wrap="word")
        self.keywords_box.pack(fill="x", padx=SPACE["xl"])

        W.button(card, self.animator, "Guardar vigilante", self._save_watcher,
                 tone="accent", font=self.fonts["button"], height=36).pack(
            fill="x", padx=SPACE["xl"], pady=(SPACE["lg"], SPACE["lg"]))

    def _build_data(self, parent):
        card = W.Card(parent)
        card.grid(row=1, column=0, sticky="ew")
        W.card_title(card, self.fonts, "Datos")

        self.data_label = ctk.CTkLabel(card, text="", font=self.fonts["small"],
                                       text_color=COLORS["text_muted"], wraplength=420,
                                       justify="left")
        self.data_label.pack(anchor="w", padx=SPACE["xl"])

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["md"], SPACE["lg"]))
        buttons.grid_columnconfigure((0, 1), weight=1, uniform="data")
        W.button(buttons, self.animator, "Importar del programa viejo",
                 self.app.import_legacy, tone="quiet", font=self.fonts["button"],
                 height=34).grid(row=0, column=0, sticky="ew", padx=(0, SPACE["xs"]))
        W.button(buttons, self.animator, "Exportar CSV", self.app.export_csv,
                 tone="quiet", font=self.fonts["button"], height=34).grid(
            row=0, column=1, sticky="ew", padx=(SPACE["xs"], 0))

        ctk.CTkLabel(card,
                     text="La base es un archivo SQLite (focusflow.db) al lado del "
                          "programa. Copialo y tenés todo tu historial.",
                     font=self.fonts["tiny"], text_color=COLORS["text_faint"],
                     wraplength=420, justify="left").pack(
            anchor="w", padx=SPACE["xl"], pady=(0, SPACE["lg"]))

    # ------------------------------------------------------------------ #

    def _apply_preset(self, preset):
        for entry, value in ((self.focus_entry, preset["focus"]),
                             (self.break_entry, preset["break"]),
                             (self.tolerance_entry, preset["tolerance"])):
            entry.delete(0, "end")
            entry.insert(0, str(value))

    @staticmethod
    def _int_from(entry, fallback, minimum=0, maximum=100000):
        try:
            return max(minimum, min(maximum, int(float(entry.get().replace(",", ".")))))
        except (ValueError, AttributeError):
            return fallback

    def _save_rhythm(self):
        self.settings.update(
            focus_minutes=self._int_from(self.focus_entry,
                                         self.settings["focus_minutes"], 0, 600),
            break_minutes=self._int_from(self.break_entry,
                                         self.settings["break_minutes"], 0, 240),
            tolerance_minutes=self._int_from(self.tolerance_entry,
                                             self.settings["tolerance_minutes"], 0, 120),
            short_pause_minutes=max(1, self._int_from(
                self.away_entry, self.settings["short_pause_minutes"], 1, 120)),
            auto_start_break=bool(self.auto_break.get()),
            auto_start_focus=bool(self.auto_focus.get()),
        )
        self.app.apply_settings()
        self.app.toasts.show("Ritmo guardado.", tone="mint")
        self.refresh()

    def _save_goal(self):
        self.settings["daily_goal_minutes"] = max(5, self._int_from(
            self.goal_entry, self.settings["daily_goal_minutes"], 5, 1440))
        self.app.apply_settings()
        self.app.toasts.show("Objetivo actualizado.", tone="mint")
        self.refresh()

    def _save_watcher(self):
        raw = self.keywords_box.get("1.0", "end-1c")
        keywords = [word.strip().lower() for word in raw.split(",") if word.strip()]
        self.settings.update(
            watcher_enabled=bool(self.watcher_switch.get()),
            watcher_keywords=keywords,
            watcher_grace_seconds=max(3, self._int_from(
                self.grace_entry, self.settings["watcher_grace_seconds"], 3, 600)),
        )
        self.app.apply_settings()
        state = "activado" if self.settings["watcher_enabled"] else "desactivado"
        self.app.toasts.show(f"Vigilante {state}.", tone="mint")
        self.refresh()

    def refresh(self):
        pairs = (
            (self.focus_entry, self.settings["focus_minutes"]),
            (self.break_entry, self.settings["break_minutes"]),
            (self.tolerance_entry, self.settings["tolerance_minutes"]),
            (self.away_entry, self.settings["short_pause_minutes"]),
            (self.goal_entry, self.settings["daily_goal_minutes"]),
            (self.grace_entry, self.settings["watcher_grace_seconds"]),
        )
        for entry, value in pairs:
            entry.delete(0, "end")
            entry.insert(0, str(value))

        for switch, key in ((self.auto_break, "auto_start_break"),
                            (self.auto_focus, "auto_start_focus"),
                            (self.watcher_switch, "watcher_enabled")):
            switch.select() if self.settings[key] else switch.deselect()

        self.keywords_box.delete("1.0", "end")
        self.keywords_box.insert("1.0", ", ".join(self.settings["watcher_keywords"]))

        count = self.app.db.count()
        first, last = self.app.db.day_bounds()
        if count:
            self.data_label.configure(
                text=f"{count} {'sesión guardada' if count == 1 else 'sesiones guardadas'}, "
                     f"desde {first.strftime('%d/%m/%Y')} hasta {last.strftime('%d/%m/%Y')}.")
        else:
            self.data_label.configure(
                text="Todavía no hay sesiones. Si venías usando el programa anterior, "
                     "podés importar tu historial.")
