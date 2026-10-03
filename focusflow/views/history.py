"""Historial: qué pasó cada día."""

from __future__ import annotations

from datetime import date, datetime

import customtkinter as ctk

from .. import stats
from .. import widgets as W
from ..theme import COLORS, DATA, RADIUS, SPACE, score_color


class HistoryView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.db = app.db
        self.fonts = app.fonts
        self.animator = app.animator
        self.tag_filter = None
        self._build()

    def _build(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=300)
        self.grid_columnconfigure(1, weight=1)

        side = ctk.CTkFrame(self, fg_color="transparent")
        side.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE["md"]))
        side.grid_columnconfigure(0, weight=1)
        # Sólo queda el calendario arriba; el resto de la columna va vacío.
        side.grid_rowconfigure(1, weight=1)

        # --- calendario ---
        calendar_card = W.Card(side)
        calendar_card.grid(row=0, column=0, sticky="ew")
        self.calendar = W.MiniCalendar(calendar_card, self.animator, COLORS["surface"],
                                       self.fonts, on_select=self._on_day)
        self.calendar.pack(padx=SPACE["md"], pady=(SPACE["md"], SPACE["sm"]))
        # Abrimos en el último día con sesiones: si hace rato que no usás el
        # programa, ver "hoy" vacío no dice nada.
        _, last = self.db.day_bounds()
        if self.db.count():
            self.calendar.set_selected(last)

        filters = ctk.CTkFrame(calendar_card, fg_color="transparent")
        filters.pack(fill="x", padx=SPACE["lg"], pady=(0, SPACE["lg"]))
        ctk.CTkLabel(filters, text="Filtrar por hashtag", font=self.fonts["tiny"],
                     text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, SPACE["xs"]))
        self.tag_menu = ctk.CTkOptionMenu(
            filters, values=["Todos"], command=lambda _v: self.refresh(),
            fg_color=COLORS["surface2"], button_color=COLORS["surface3"],
            button_hover_color=COLORS["surface4"], text_color=COLORS["text"],
            dropdown_fg_color=COLORS["surface2"], dropdown_text_color=COLORS["text"],
            dropdown_hover_color=COLORS["surface3"], font=self.fonts["small"],
            dropdown_font=self.fonts["small"], corner_radius=RADIUS["xs"], height=32)
        self.tag_menu.set("Todos")
        self.tag_menu.pack(fill="x")

        # --- lista ---
        # Ya no hay tarjeta de resumen del día: repetía lo que cada sesión de la
        # lista muestra por su cuenta. La fecha se mudó al encabezado de la
        # lista, que es donde hace falta saber qué día se está mirando.
        list_card = W.Card(self)
        list_card.grid(row=0, column=1, sticky="nsew")
        list_card.grid_rowconfigure(1, weight=1)
        list_card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(list_card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=SPACE["xl"],
                    pady=(SPACE["lg"], SPACE["sm"]))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left")
        self.day_title = ctk.CTkLabel(titles, text="", font=self.fonts["section"],
                                      text_color=COLORS["text"], anchor="w")
        self.day_title.pack(anchor="w")
        self.count_label = ctk.CTkLabel(header, text="", font=self.fonts["small"],
                                        text_color=COLORS["text_dim"])
        self.count_label.pack(side="right", pady=(4, 0))

        self.list_frame = ctk.CTkScrollableFrame(
            list_card, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=COLORS["surface2"],
            scrollbar_button_hover_color=COLORS["surface3"])
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=SPACE["md"],
                             pady=(0, SPACE["md"]))

    # ------------------------------------------------------------------ #

    def _on_day(self, _day):
        self.refresh()

    def _selected_tag(self):
        value = self.tag_menu.get()
        return None if not value or value == "Todos" else value.lstrip("#")

    def refresh_tags(self):
        values = ["Todos"] + [f"#{t}" for t in self.db.all_tags(60)]
        current = self.tag_menu.get()
        self.tag_menu.configure(values=values)
        if current not in values:
            self.tag_menu.set("Todos")

    def focus_day(self, day):
        self.calendar.set_selected(day)
        self.refresh()

    def refresh(self):
        self.calendar.set_marked(self.db.focus_by_day())
        day = self.calendar.selected
        tag = self._selected_tag()
        rows = self.db.sessions_on(day, tag)

        self.day_title.configure(
            text=f"{W.WEEKDAY_NAMES[day.weekday()]} {day.strftime('%d/%m/%Y')}")

        summary = stats.totals(rows)
        detail = f"{len(rows)} {'sesión' if len(rows) == 1 else 'sesiones'}"
        if len(rows) > 1:
            # Con una sola sesión el total del día sería el mismo que el de la
            # tarjeta; recién con dos o más aporta algo.
            detail += (f" · {W.fmt_short(summary['total'])} en total · "
                       f"{summary['productivity']:.0f}% concentrado")
        self.count_label.configure(text=detail)

        for child in self.list_frame.winfo_children():
            child.destroy()

        if not rows:
            box = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            box.pack(fill="both", expand=True, pady=70)
            ctk.CTkLabel(box, text="Sin sesiones este día", font=self.fonts["body_bold"],
                         text_color=COLORS["text_muted"]).pack()
            ctk.CTkLabel(box, text="Elegí otro día en el calendario.",
                         font=self.fonts["small"],
                         text_color=COLORS["text_faint"]).pack(pady=(4, 0))
            return

        for row in rows:
            self._build_card(row)

    def _build_card(self, row):
        total = row["total_seconds"] or 0.0
        percentage = (row["focus_seconds"] or 0) / total * 100 if total else 0

        card = W.Card(self.list_frame, fill=COLORS["surface2"], radius=RADIUS["md"])
        card.pack(fill="x", padx=SPACE["sm"], pady=(0, SPACE["md"]))
        card.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=SPACE["lg"],
                    pady=(SPACE["md"], SPACE["sm"]))
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text=row["title"] or "Sesión", font=self.fonts["card"],
                     text_color=COLORS["text"], anchor="w").pack(anchor="w")

        detail = f'{row["started_at"][11:16]} – {row["ended_at"][11:16]} · {W.fmt_short(total)}'
        if row["pauses"]:
            detail += f' · {row["pauses"]} corte{"s" if row["pauses"] != 1 else ""}'
        if row["blocks"]:
            detail += f' · {row["blocks"]} bloque{"s" if row["blocks"] != 1 else ""}'
        if row["preset"]:
            detail += f' · {row["preset"]}'
        ctk.CTkLabel(titles, text=detail, font=self.fonts["tiny"],
                     text_color=COLORS["text_faint"], anchor="w").pack(anchor="w",
                                                                       pady=(1, 0))
        ctk.CTkLabel(header, text=f"{percentage:.0f}%", font=self.fonts["metric"],
                     text_color=score_color(percentage)).pack(side="right")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=(SPACE["lg"], SPACE["sm"]))

        focus_seconds = row["focus_seconds"] or 0.0
        other_seconds = (row["rest_seconds"] or 0.0) + (row["away_seconds"] or 0.0)

        metrics = ctk.CTkFrame(body, fg_color="transparent")
        metrics.pack(fill="x")
        for key, label, value in (("focus", "Concentración", focus_seconds),
                                  ("other", "No concentración", other_seconds)):
            item = ctk.CTkFrame(metrics, fg_color="transparent")
            item.pack(side="left", padx=(0, SPACE["2xl"]))
            head = ctk.CTkFrame(item, fg_color="transparent")
            head.pack(anchor="w")
            W.Dot(head, COLORS["surface2"], DATA[key], size=8).pack(
                side="left", pady=(1, 0))
            ctk.CTkLabel(head, text=label, font=self.fonts["tiny"],
                         text_color=COLORS["text_dim"]).pack(side="left", padx=(5, 0))
            ctk.CTkLabel(item, text=W.fmt_short(value), font=self.fonts["small_bold"],
                         text_color=COLORS["text"]).pack(anchor="w")

        spans = [(s["start_offset"], s["end_offset"], s["kind"])
                 for s in self.db.segments_of(row["id"])]
        timeline = W.TimelineBar(body, COLORS["surface2"], height=10)
        timeline.pack(fill="x", pady=(SPACE["md"], 0))
        timeline.set_spans(spans, total)

        notes = (row["notes"] or "").strip() or "Sin descripción"
        text = ctk.CTkTextbox(body, height=58, fg_color=COLORS["surface"],
                              text_color=COLORS["text_muted"], font=self.fonts["small"],
                              wrap="word", corner_radius=RADIUS["xs"], border_width=0,
                              activate_scrollbars=False)
        text.insert("1.0", notes)
        text.configure(state="disabled")
        text.pack(fill="x", pady=(SPACE["md"], 0))

        tags = self.db.tags_of(row["id"])
        if tags:
            tag_row = ctk.CTkFrame(body, fg_color="transparent")
            tag_row.pack(fill="x", pady=(SPACE["sm"], 0))
            for tag in tags[:8]:
                ctk.CTkLabel(tag_row, text=f"#{tag}", font=self.fonts["tiny_bold"],
                             text_color=COLORS["lavender"], fg_color=COLORS["lavender_soft"],
                             corner_radius=8, height=20).pack(side="left",
                                                              padx=(0, SPACE["xs"]))
        ctk.CTkFrame(body, fg_color="transparent", height=SPACE["md"]).pack()

        side = ctk.CTkFrame(card, fg_color="transparent")
        side.grid(row=1, column=1, sticky="ne", padx=(0, SPACE["lg"]),
                  pady=(0, SPACE["md"]))
        donut = W.MiniDonut(side, COLORS["surface2"], self.fonts, size=84)
        donut.pack()
        donut.set_values({"focus": focus_seconds, "other": other_seconds})

        actions = ctk.CTkFrame(side, fg_color="transparent")
        actions.pack(pady=(SPACE["sm"], 0))

        def toggle_edit():
            if str(text.cget("state")) == "disabled":
                text.configure(state="normal")
                if text.get("1.0", "end-1c").strip() == "Sin descripción":
                    text.delete("1.0", "end")
                self.app.hashtag_popup.attach(text)
                text.focus_set()
                edit.configure(text="Guardar")
                edit.set_base_color(COLORS["mint"], COLORS["mint_hover"])
                edit.configure(text_color=COLORS["app"])
            else:
                new_notes = text.get("1.0", "end-1c").strip()
                self.db.update_session(row["id"], notes=new_notes)
                text.configure(state="disabled")
                self.app.toasts.show("Descripción actualizada.", tone="mint")
                self.app.mark_stale("Análisis")
                self.refresh_tags()
                self.refresh()

        edit = W.button(actions, self.animator, "Editar", toggle_edit, tone="ghost",
                        font=self.fonts["button"], height=30, width=88)
        edit.pack(pady=(0, SPACE["xs"]))

        W.button(actions, self.animator, "Borrar",
                 lambda: self.app.confirm(
                     "Borrar sesión",
                     f'«{row["title"] or "Sesión"}» se borra para siempre.',
                     "Borrar", lambda: self._delete(row["id"]), tone="rose"),
                 tone="destructive", font=self.fonts["button"], height=30, width=88).pack()

    def _delete(self, session_id):
        self.db.delete_session(session_id)
        self.app.mark_stale()
        self.refresh()
        self.app.toasts.show("Sesión borrada.", tone="rose")
