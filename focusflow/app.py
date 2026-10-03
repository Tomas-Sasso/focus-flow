"""Ventana principal: conecta el motor, la base y las vistas."""

from __future__ import annotations

import os
import time
import tkinter as tk
from datetime import date, datetime

import customtkinter as ctk

from . import engine as E
from . import render as R
from . import stats
from . import widgets as W
from .anim import Animator
from .config import (APP_NAME, BASE_DIR, PRESETS, RECOVERY_PATH,
                     Settings)
from .db import Database
from .floating import FloatingTab
from .splash import SplashScreen
from .system import (SOUND_BREAK_END, SOUND_BREAK_START, SOUND_FOCUS,
                     SOUND_SHORT_PAUSE, SOUND_SHORT_PAUSE_END, SOUND_WELCOME,
                     DistractionWatcher, SoundPlayer)
from .theme import COLORS, RADIUS, SPACE, Typography
from .views.focus import FocusView
from .views.history import HistoryView
from .views.insights import InsightsView
from .views.settings import SettingsView

try:
    import keyboard
except Exception:  # pragma: no cover - pide permisos en algunos equipos
    keyboard = None

VIEWS = ("Enfoque", "Historial", "Análisis", "Ajustes")

#: Ancho de la barra lateral. Tiene que dar para "Desactivar pestaña flotante",
#: que es el texto más largo que va ahí adentro.
SIDEBAR_WIDTH = 234

#: Cuánto se muestra como mínimo la pantalla de carga. Si la precarga tarda más,
#: se espera a que termine; si tarda menos, se completa este tiempo.
SPLASH_SECONDS = 1.0


class FocusFlowApp:
    def __init__(self, root):
        self.root = root
        self.settings = Settings()
        self.db = Database()
        self.fonts = Typography(root)
        self.animator = Animator(root, fps=60)
        self.sounds = SoundPlayer(self.settings["sounds_enabled"],
                                  volume=self.settings["volume"],
                                  muted=self.settings["muted"])
        self.watcher = DistractionWatcher(self.settings["watcher_keywords"],
                                          self.settings["watcher_grace_seconds"])
        self.engine = E.Engine()
        self.tab = None
        self.toasts = None
        self.hashtag_popup = None
        self._tick_job = None
        self._current_view = None

        self._setup_window()
        self._build_shell()
        self._build_views()

        self.toasts = W.ToastManager(root, self.animator, self.fonts)
        self.hashtag_popup = W.HashtagPopup(root, self.animator, self.fonts,
                                            self.db.suggest_tags)

        self.tab = FloatingTab(self)
        self.tab.minimized = self.settings["floating_tab_minimized"]
        self._refresh_tab_button()
        # `<Unmap>` salta al minimizar y `<Map>` al restaurar. Se filtra por
        # widget porque el evento también llega desde los hijos.
        root.bind("<Unmap>", self._on_root_visibility, add="+")
        root.bind("<Map>", self._on_root_visibility, add="+")

        self.apply_settings()
        self._register_hotkeys()
        self.show_view(self.settings["start_view"] if
                       self.settings["start_view"] in VIEWS else "Enfoque",
                       animate=False)

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._clear_recovery()          # de versiones anteriores
        self._boot()
        self._schedule_tick()

    # ------------------------------------------------------------------ #
    # Arranque
    # ------------------------------------------------------------------ #

    def _boot(self):
        """Muestra la pantalla de carga y calcula todo antes de aparecer.

        La ventana se abre con opacidad cero: así tiene su tamaño real y los
        lienzos pueden dibujarse, pero no se ve cómo se arma.
        """
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.root.deiconify()

        self.splash = SplashScreen(self.root, self.fonts)
        self.splash.show()
        self._boot_started = time.monotonic()
        self.root.after(30, self._settle_geometry)

    def _settle_geometry(self, attempts=16, stable=0):
        """Deja la ventana en su tamaño definitivo antes de dibujar nada.

        Si se precarga con un tamaño y después la ventana se maximiza, todo se
        reacomoda justo cuando aparece y se ve el salto. Además hay que esperar
        a que el tamaño se sostenga: customtkinter reaplica `geometry()` cuando
        ajusta su escalado, y eso deshace el maximizado un instante después.
        """
        self._maximize()
        self.root.update_idletasks()
        try:
            firme = self.root.state() == "zoomed"
        except tk.TclError:
            firme = False
        stable = stable + 1 if firme else 0
        if stable < 3 and attempts > 0:
            self.root.after(70, lambda: self._settle_geometry(attempts - 1, stable))
            return
        self._preload()

    def _preload(self):
        """Calcula y dibuja las cuatro vistas con la ventana ya dimensionada."""
        try:
            self.root.update_idletasks()
            for name in VIEWS:
                view = self.views[name]
                view.refresh()
                self._stale[name] = False
                self.root.update()      # vacía los redibujos pendientes
            self.refresh_all()
            self.root.update()
        except tk.TclError:
            return

        restante = SPLASH_SECONDS - (time.monotonic() - self._boot_started)
        self.root.after(max(0, int(restante * 1000)), self._finish_boot)

    def _finish_boot(self):
        if getattr(self, "splash", None) is not None:
            self.splash.close()
            self.splash = None

        def fade(value):
            try:
                self.root.attributes("-alpha", value)
            except tk.TclError:
                pass

        self.animator.to("boot_fade", 0.0, 1.0, duration=0.28, easing="out_cubic",
                         on_update=fade)
        self.sounds.play(SOUND_WELCOME, "ff_welcome")
        self.root.after(600, self._offer_import)

    # ------------------------------------------------------------------ #
    # Ventana y estructura
    # ------------------------------------------------------------------ #

    def _setup_window(self):
        self.root.title(APP_NAME)
        self.root.geometry("1280x820")
        self.root.minsize(1120, 720)
        self.root.configure(fg_color=COLORS["app"])
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

    def _maximize(self, attempts=8):
        """Maximiza la ventana, reintentando si hace falta.

        Empaquetado como .exe el arranque es más lento y el primer intento puede
        caer antes de que la ventana esté mapeada.
        """
        try:
            self.root.update_idletasks()
            self.root.state("zoomed")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)
                return
            except tk.TclError:
                pass
        try:
            if self.root.state() == "zoomed":
                return
        except tk.TclError:
            pass
        if attempts > 0:
            self.root.after(120, lambda: self._maximize(attempts - 1))

    def _keep_maximized(self, checks=(250, 700, 1400)):
        """Vuelve a maximizar si algo lo deshizo.

        customtkinter reaplica `geometry()` cuando ajusta su escalado al
        arrancar, y eso devuelve la ventana a su tamaño fijo aunque uno ya la
        haya maximizado. Con estas verificaciones el maximizado sobrevive.
        """
        self._maximize()
        for delay in checks:
            self.root.after(delay, self._maximize)

    def _build_shell(self):
        # --- barra lateral ---
        # El ancho lo manda la barra, no sus hijos: sin `columnconfigure` la
        # columna crecía hasta el widget más ancho —el deslizador de volumen pide
        # 200 px por su cuenta— y el contenido terminaba desbordando sobre el
        # panel central.
        sidebar = ctk.CTkFrame(self.root, fg_color=COLORS["sidebar"], corner_radius=0,
                               width=SIDEBAR_WIDTH)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=SPACE["xl"],
                   pady=(SPACE["2xl"], SPACE["xl"]))
        # Marca como en una barra lateral de Apple: el anillo de la app al lado del
        # nombre, sin bajada (la frase de la app queda en el splash).
        logo = R.progress_ring(72, 0.78, COLORS["accent"], COLORS["surface3"],
                               COLORS["sidebar"], thickness=0.16, padding=4)
        self._logo = ctk.CTkImage(light_image=logo, dark_image=logo, size=(24, 24))
        ctk.CTkLabel(brand, text=f"  {APP_NAME}", image=self._logo, compound="left",
                     font=self.fonts["title"], text_color=COLORS["text"]).pack(anchor="w")

        self.nav = W.NavRail(sidebar, self.animator, self.fonts, VIEWS,
                             command=self.show_view, width=SIDEBAR_WIDTH)
        self.nav.grid(row=1, column=0, sticky="ew")

        # --- abajo a la izquierda: sólo el interruptor de la pestaña flotante ---
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=SPACE["md"],
                    pady=(0, SPACE["xl"]))
        # Un interruptor, como en Ajustes de macOS: dice el estado sin tener que leer
        # un botón que cambia de texto.
        tab_row = ctk.CTkFrame(footer, fg_color="transparent")
        tab_row.pack(fill="x", padx=(SPACE["xs"], 0))
        ctk.CTkLabel(tab_row, text="Pestaña flotante", font=self.fonts["body"],
                     text_color=COLORS["text"]).pack(side="left")
        self.tab_switch = ctk.CTkSwitch(
            tab_row, text="", width=40, switch_width=36, switch_height=20,
            fg_color=COLORS["surface3"], progress_color=COLORS["accent"],
            button_color=COLORS["text"], button_hover_color=COLORS["text"],
            command=self.toggle_floating_tab)
        self.tab_switch.pack(side="right")

        self.volume = W.VolumeControl(footer, self.fonts, self.settings,
                                      self._on_volume_change,
                                      background=COLORS["sidebar"])
        self.volume.pack(fill="x", pady=(SPACE["lg"], 0))

        # --- área de contenido ---
        self.content = ctk.CTkFrame(self.root, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=SPACE["xl"],
                          pady=SPACE["xl"])

    def _build_views(self):
        self.views = {
            "Enfoque": FocusView(self.content, self),
            "Historial": HistoryView(self.content, self),
            "Análisis": InsightsView(self.content, self),
            "Ajustes": SettingsView(self.content, self),
        }
        # Las cuatro vistas se apilan en el mismo lugar y se alternan con
        # tkraise(). Antes se hacía place/place_forget en cada cambio: cada
        # lienzo perdía su tamaño, tenía que recalcularlo y redibujarse entero,
        # y encima se relanzaban todas las animaciones. Eso era el tirón al
        # cambiar de menú.
        for view in self.views.values():
            view.place(relx=0, rely=0, relwidth=1, relheight=1)
        # Vistas que hay que recalcular porque cambiaron los datos de abajo.
        self._stale = {name: True for name in self.views}

    def mark_stale(self, *names):
        for name in (names or tuple(self.views)):
            self._stale[name] = True

    def show_view(self, name, animate=True):
        if name not in self.views:
            return
        self.nav.select(name, animate=animate)
        if name == self._current_view:
            return
        self._current_view = name
        self.views[name].tkraise()
        # Sólo recalculamos si algo cambió desde la última vez.
        if self._stale.get(name, True):
            self._stale[name] = False
            self.views[name].refresh()

    # ------------------------------------------------------------------ #
    # Preferencias
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Pestaña flotante
    # ------------------------------------------------------------------ #

    def _on_root_visibility(self, event):
        if event.widget is self.root and self.tab is not None:
            self.tab.sync_visibility()

    def _refresh_tab_button(self):
        # select/deselect no llaman al command, así que no hay vuelta en círculo.
        if self.settings["floating_tab"]:
            self.tab_switch.select()
        else:
            self.tab_switch.deselect()

    def toggle_floating_tab(self):
        activa = not self.settings["floating_tab"]
        self.settings["floating_tab"] = activa
        self.tab.set_enabled(activa)
        self._refresh_tab_button()
        if activa:
            self.toasts.show("Pestaña flotante activada: aparece al minimizar la app.",
                             tone="yellow")
        else:
            self.toasts.show("Pestaña flotante desactivada.", tone="orange")

    def disable_floating_tab(self):
        """La usa el menú contextual de la pestaña ("Cerrar pestaña")."""
        if self.settings["floating_tab"]:
            self.toggle_floating_tab()

    def _on_volume_change(self):
        """La barra o el parlante cambiaron el volumen; ya quedó guardado."""
        self.sounds.configure(volume=self.settings["volume"],
                              muted=self.settings["muted"])

    def apply_settings(self):
        self.sounds.configure(enabled=self.settings["sounds_enabled"],
                              volume=self.settings["volume"],
                              muted=self.settings["muted"])
        if hasattr(self, "volume"):
            self.volume.refresh()
        if self.tab is not None:
            self.tab.set_enabled(self.settings["floating_tab"])
        self.watcher.configure(keywords=self.settings["watcher_keywords"],
                               grace_seconds=self.settings["watcher_grace_seconds"],
                               enabled=self.settings["watcher_enabled"])
        self.engine.auto_start_break = self.settings["auto_start_break"]
        self.engine.auto_start_focus = self.settings["auto_start_focus"]
        self.views["Enfoque"].refresh_today(self.db, self.settings)
        self.views["Enfoque"].set_config_text(self.engine, self.settings)

    def _register_hotkeys(self):
        """F8/F9/F10, también con la ventana atrás.

        Una sola vía por tecla. El enganche global de `keyboard` dispara igual
        con Focus Flow adelante, así que sumarle el atajo de Tk hacía que cada
        tecla contara dos veces: F10 entraba y salía de la pausa corta en el
        mismo golpe, con los dos avisos pisándose. El atajo de Tk queda para las
        teclas que el enganche global no pudo tomar.
        """
        for key, action in (("F8", self.on_pause), ("F9", self.on_resume),
                            ("F10", self.on_short_pause)):
            if self._add_global_hotkey(key, action):
                continue
            self.root.bind_all(f"<{key}>", lambda _e, a=action: a())

    def _add_global_hotkey(self, key, action):
        if keyboard is None:
            return False
        try:
            keyboard.add_hotkey(key, lambda: self.root.after(0, action))
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------ #
    # Acciones de sesión
    # ------------------------------------------------------------------ #

    def on_primary(self):
        """El botón grande: su significado depende del estado."""
        if not self.engine.running:
            self.show_start_dialog()
        elif self.engine.state == E.FOCUS:
            self.on_pause()
        elif self.engine.state == E.AWAY:
            self._handle(self.engine.end_short_pause())
            self.toasts.show("Seguimos donde estábamos.", tone="mint")
        else:
            self.on_resume()

    def on_resume(self):
        if not self.engine.running:
            return
        if self.engine.state == E.AWAY:
            self._handle(self.engine.end_short_pause())
            return
        self._handle(self.engine.resume())

    def on_pause(self):
        if not self.engine.running or self.engine.state == E.PAUSED:
            return
        self._handle(self.engine.pause())
        self.toasts.show("Concentración cortada.", tone="rose")

    def on_short_pause(self):
        if not self.engine.running:
            return
        if self.engine.state == E.AWAY:
            self._handle(self.engine.end_short_pause())
            self.toasts.show("Seguimos donde estábamos.", tone="mint")
            return
        self._handle(self.engine.short_pause())
        self.toasts.show(
            f"Pausa corta: tenés {W.fmt_ms(self.engine.away_limit)} sin perder el bloque.",
            tone="lavender")

    def on_toggle_phase(self):
        self._handle(self.engine.toggle_phase())

    def on_end(self):
        if not self.engine.running:
            return
        self.confirm("Terminar sesión",
                     "Vas a poder ponerle nombre y anotaciones antes de guardarla.",
                     "Terminar", self._end_session, tone="amber")

    def _end_session(self):
        record = self.engine.finish()
        self._clear_recovery()
        self._refresh_engine_ui()
        # Siempre se ofrece guardar, dure lo que dure. Antes las sesiones de
        # menos de 30 segundos se descartaban solas y no había forma de anotar
        # nada, que es justo lo que pasa cuando uno prueba el programa.
        self.show_save_dialog(record)

    def _handle(self, events):
        """Aplica los efectos de los eventos que devolvió el motor."""
        for event in events:
            if event.name == E.PHASE_CHANGED:
                if event.detail == E.BREAK:
                    self.sounds.play(SOUND_BREAK_START, "ff_break")
                elif event.detail == E.FOCUS:
                    self.sounds.play(SOUND_FOCUS, "ff_focus")
                elif event.detail == E.AWAY:
                    self.sounds.play(SOUND_SHORT_PAUSE, "ff_away")
                self.watcher.forgive()
            elif event.name == E.AWAY_ENDED:
                self.sounds.play(SOUND_SHORT_PAUSE_END, "ff_back")
                self.watcher.forgive()
            elif event.name == E.BREAK_DONE:
                self.sounds.play(SOUND_BREAK_END, "ff_break")
            elif event.name == E.NAG:
                self.sounds.play(SOUND_BREAK_END, "ff_nag")
            elif event.name == E.AUTO_PAUSED:
                self.toasts.show("Se agotó la tolerancia: el reloj quedó en pausa.",
                                 tone="rose")
            elif event.name == E.AWAY_EXPIRED:
                self.toasts.show("Se pasó la pausa corta: el bloque se reinicia.",
                                 tone="rose")
            elif event.name == E.BLOCK_DONE:
                self.toasts.show(f"Bloque {self.engine.blocks} completo.", tone="mint")
        self._refresh_engine_ui()

    # ------------------------------------------------------------------ #
    # Reloj
    # ------------------------------------------------------------------ #

    def _schedule_tick(self):
        self._tick_job = self.root.after(500, self._tick)

    def _tick(self):
        self._tick_job = None
        try:
            if self.engine.running:
                self._handle(self.engine.tick())
                self._poll_watcher()
            self._schedule_tick()
        except tk.TclError:
            pass

    def _poll_watcher(self):
        if self.engine.state != E.FOCUS:
            return
        found = self.watcher.poll(time.monotonic())
        if not found:
            return
        self.toasts.show(f"Parece que estás en {found}. ¿Corto la concentración?",
                         tone="amber", action=self.on_pause, action_text="Cortar")

    def _refresh_engine_ui(self):
        view = self.views["Enfoque"]
        view.refresh_engine(self.engine)
        view.set_config_text(self.engine, self.settings)

        if self.tab is not None:
            self.tab.update_from(self.engine)

    def refresh_all(self):
        self._refresh_engine_ui()
        self.views["Enfoque"].refresh_today(self.db, self.settings)
        self.views["Historial"].refresh_tags()
        self.views["Análisis"].refresh_tags()

    # ------------------------------------------------------------------ #
    # Diálogos
    # ------------------------------------------------------------------ #

    def _modal(self, title, width, height):
        window = ctk.CTkToplevel(self.root)
        window.title(title)
        window.configure(fg_color=COLORS["bg"])
        window.resizable(False, False)
        window.update_idletasks()
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.transient(self.root)
        try:
            window.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        window.after(10, window.grab_set)

        def fade(value):
            try:
                window.attributes("-alpha", value)
            except tk.TclError:
                pass

        self.animator.to(("modal", id(window)), 0.0, 1.0, duration=0.18,
                         easing="out_cubic", on_update=fade)

        container = ctk.CTkFrame(window, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=SPACE["2xl"], pady=SPACE["2xl"])
        ctk.CTkLabel(container, text=title, font=self.fonts["section"],
                     text_color=COLORS["text"]).pack(anchor="w", pady=(0, SPACE["sm"]))

        # El pie se reserva ANTES que el contenido. Tk reparte el espacio en el
        # orden en que se empaqueta, así que si los botones van últimos y el
        # contenido no entra, quedan fuera de la ventana. Eso pasaba en el
        # diálogo de comenzar sesión: no se veían Cancelar ni Comenzar, y la
        # única forma de arrancar era apretar Enter.
        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(side="bottom", fill="x", pady=(SPACE["md"], 0))
        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(side="top", fill="both", expand=True)
        return window, body, footer

    def _footer_buttons(self, footer, cancel_text, accept_text, on_accept,
                        tone="accent", window=None):
        footer.grid_columnconfigure((0, 1), weight=1, uniform="footer")
        W.button(footer, self.animator, cancel_text, window.destroy, tone="quiet",
                 font=self.fonts["button"], height=40).grid(
            row=0, column=0, sticky="ew", padx=(0, SPACE["xs"]))
        W.button(footer, self.animator, accept_text, on_accept, tone=tone,
                 font=self.fonts["button"], height=40).grid(
            row=0, column=1, sticky="ew", padx=(SPACE["xs"], 0))

    def confirm(self, title, message, confirm_text, on_confirm, tone="rose"):
        window, body, footer = self._modal(title, 440, 230)
        ctk.CTkLabel(body, text=message, font=self.fonts["body"],
                     text_color=COLORS["text_muted"], wraplength=370,
                     justify="left").pack(anchor="w", pady=(0, SPACE["lg"]))

        def accept():
            window.destroy()
            on_confirm()

        self._footer_buttons(footer, "Cancelar", confirm_text, accept, tone, window)

    def _minutes_field(self, parent, label, value):
        ctk.CTkLabel(parent, text=label, font=self.fonts["tiny"],
                     text_color=COLORS["text_dim"]).pack(anchor="w",
                                                         pady=(0, SPACE["xs"]))
        entry = ctk.CTkEntry(parent, fg_color=COLORS["surface2"],
                             border_color=COLORS["border"], border_width=1,
                             text_color=COLORS["text"], font=self.fonts["body"],
                             corner_radius=RADIUS["xs"], height=34)
        entry.insert(0, str(value))
        entry.pack(fill="x", pady=(0, SPACE["md"]))
        return entry

    @staticmethod
    def _read_minutes(entry, fallback):
        try:
            return max(0, int(float(entry.get().replace(",", "."))))
        except (ValueError, AttributeError):
            return fallback

    def show_start_dialog(self):
        window, body, footer = self._modal("Comenzar sesión", 540, 600)
        ctk.CTkLabel(body, text="Elegí el ritmo. Podés cambiarlo con la sesión andando.",
                     font=self.fonts["small"], text_color=COLORS["text_muted"],
                     wraplength=430, justify="left").pack(anchor="w",
                                                          pady=(0, SPACE["md"]))

        chosen = {"preset": ""}
        entries = {}

        # Los presets en dos columnas: apilados uno por fila ocupaban tanto que
        # empujaban los botones fuera de la ventana.
        preset_box = ctk.CTkFrame(body, fg_color="transparent")
        preset_box.pack(fill="x", pady=(0, SPACE["sm"]))
        preset_box.grid_columnconfigure((0, 1), weight=1, uniform="preset")

        def apply_preset(preset):
            chosen["preset"] = preset["name"]
            for key, entry in entries.items():
                entry.delete(0, "end")
                entry.insert(0, str(preset[key]))
            hint.configure(text=preset["hint"])

        for index, preset in enumerate(PRESETS):
            W.button(preset_box, self.animator, preset["name"],
                     lambda p=preset: apply_preset(p), tone="quiet",
                     font=self.fonts["button"], height=32, width=120).grid(
                row=index // 2, column=index % 2, sticky="ew",
                padx=(0 if index % 2 == 0 else SPACE["xs"], 0),
                pady=(0, SPACE["xs"]))

        hint = ctk.CTkLabel(body, text="", font=self.fonts["tiny"],
                            text_color=COLORS["text_faint"])
        hint.pack(anchor="w", pady=(0, SPACE["sm"]))

        fields = ctk.CTkFrame(body, fg_color="transparent")
        fields.pack(fill="x")
        entries["focus"] = self._minutes_field(fields, "Concentración (minutos)",
                                               self.settings["focus_minutes"])
        entries["break"] = self._minutes_field(fields, "Descanso (minutos)",
                                               self.settings["break_minutes"])
        entries["tolerance"] = self._minutes_field(fields, "Tolerancia (minutos)",
                                                   self.settings["tolerance_minutes"])

        def begin():
            focus = self._read_minutes(entries["focus"], self.settings["focus_minutes"])
            rest = self._read_minutes(entries["break"], self.settings["break_minutes"])
            tolerance = self._read_minutes(entries["tolerance"],
                                           self.settings["tolerance_minutes"])
            window.destroy()
            self._start(focus * 60, rest * 60, tolerance * 60, chosen["preset"])

        self._footer_buttons(footer, "Cancelar", "Comenzar", begin, "accent", window)
        window.bind("<Return>", lambda _e: begin())
        window.bind("<Escape>", lambda _e: window.destroy())

    def show_tune_dialog(self):
        """Cambia los tiempos con la sesión andando."""
        if not self.engine.running:
            self.toasts.show("Sólo se puede ajustar durante una sesión.", tone="amber")
            return

        window, body, footer = self._modal("Ajustar ritmo", 480, 460)
        ctk.CTkLabel(body, text="Los cambios se aplican al bloque en curso. "
                               "Poné 0 en concentración o descanso para seguir sin "
                               "bloques.",
                     font=self.fonts["small"], text_color=COLORS["text_muted"],
                     wraplength=380, justify="left").pack(anchor="w",
                                                          pady=(0, SPACE["md"]))

        fields = ctk.CTkFrame(body, fg_color="transparent")
        fields.pack(fill="x")
        focus_entry = self._minutes_field(fields, "Concentración (minutos)",
                                          round(self.engine.focus_target / 60))
        break_entry = self._minutes_field(fields, "Descanso (minutos)",
                                          round(self.engine.break_target / 60))
        tolerance_entry = self._minutes_field(fields, "Tolerancia (minutos)",
                                              round(self.engine.tolerance_target / 60))

        def accept():
            focus = self._read_minutes(focus_entry, round(self.engine.focus_target / 60))
            rest = self._read_minutes(break_entry, round(self.engine.break_target / 60))
            tolerance = self._read_minutes(tolerance_entry,
                                           round(self.engine.tolerance_target / 60))
            self._handle(self.engine.reconfigure(focus * 60, rest * 60, tolerance * 60))
            window.destroy()
            self.toasts.show("Ritmo actualizado.", tone="mint")

        self._footer_buttons(footer, "Cancelar", "Aceptar", accept, "accent", window)
        window.bind("<Return>", lambda _e: accept())
        window.bind("<Escape>", lambda _e: window.destroy())

    def show_goal_dialog(self):
        """Cambiar el objetivo diario sin ir hasta Ajustes."""
        window, body, footer = self._modal("Objetivo de hoy", 460, 380)
        ctk.CTkLabel(body, text="Cuántos minutos de concentración querés sumar por día. "
                               "Es la meta de la barra y de la racha.",
                     font=self.fonts["small"], text_color=COLORS["text_muted"],
                     wraplength=360, justify="left").pack(anchor="w",
                                                          pady=(0, SPACE["md"]))

        quick = ctk.CTkFrame(body, fg_color="transparent")
        quick.pack(fill="x", pady=(0, SPACE["md"]))
        quick.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="goal")

        entry = ctk.CTkEntry(body, fg_color=COLORS["surface2"],
                             border_color=COLORS["border"], border_width=1,
                             text_color=COLORS["text"], font=self.fonts["body"],
                             corner_radius=RADIUS["xs"], height=38)
        entry.insert(0, str(self.settings["daily_goal_minutes"]))

        for index, (label, minutes) in enumerate((("1 h", 60), ("2 h", 120),
                                                  ("3 h", 180), ("4 h", 240))):
            def pick(value=minutes):
                entry.delete(0, "end")
                entry.insert(0, str(value))

            W.button(quick, self.animator, label, pick, tone="quiet",
                     font=self.fonts["button"], height=34, width=60).grid(
                row=0, column=index, sticky="ew",
                padx=(0 if index == 0 else SPACE["xs"], 0))

        ctk.CTkLabel(body, text="Minutos por día", font=self.fonts["tiny"],
                     text_color=COLORS["text_dim"]).pack(anchor="w",
                                                         pady=(0, SPACE["xs"]))
        entry.pack(fill="x")

        def accept():
            minutes = max(5, min(1440, self._read_minutes(
                entry, self.settings["daily_goal_minutes"])))
            self.settings["daily_goal_minutes"] = minutes
            self.apply_settings()
            self.views["Ajustes"].refresh()
            window.destroy()
            self.toasts.show(f"Objetivo: {minutes // 60} h {minutes % 60:02d} min "
                             "por día.", tone="mint")

        self._footer_buttons(footer, "Cancelar", "Guardar", accept, "accent", window)
        window.bind("<Return>", lambda _e: accept())
        window.bind("<Escape>", lambda _e: window.destroy())
        entry.focus_set()

    def _start(self, focus, rest, tolerance, preset=""):
        self.engine.auto_start_break = self.settings["auto_start_break"]
        self.engine.auto_start_focus = self.settings["auto_start_focus"]
        self._handle(self.engine.start(
            focus, rest, tolerance,
            away_limit=self.settings["short_pause_minutes"] * 60, preset=preset))
        self.watcher.reset()
        self.show_view("Enfoque")
        self.toasts.show("Sesión iniciada.", tone="mint")

    def show_save_dialog(self, record):
        window, body, footer = self._modal("Guardar sesión", 540, 560)

        productivity = record["focus"] / record["total"] * 100 if record["total"] else 0
        summary = ctk.CTkFrame(body, fg_color=COLORS["surface"],
                               corner_radius=RADIUS["sm"])
        summary.pack(fill="x", pady=(0, SPACE["md"]))
        row = ctk.CTkFrame(summary, fg_color="transparent")
        row.pack(fill="x", padx=SPACE["lg"], pady=SPACE["md"])
        for label, value in (("Duración", W.fmt_short(record["total"])),
                             ("Concentración", W.fmt_short(record["focus"])),
                             ("Productividad", f"{productivity:.0f}%"),
                             ("Cortes", str(record["pauses"])),
                             ("Bloques", str(record["blocks"]))):
            item = ctk.CTkFrame(row, fg_color="transparent")
            item.pack(side="left", expand=True, fill="x")
            ctk.CTkLabel(item, text=label, font=self.fonts["tiny"],
                         text_color=COLORS["text_dim"]).pack(anchor="w")
            ctk.CTkLabel(item, text=value, font=self.fonts["metric_sm"],
                         text_color=COLORS["text"]).pack(anchor="w")

        timeline = W.TimelineBar(body, COLORS["bg"], height=12)
        timeline.pack(fill="x", pady=(0, SPACE["md"]))
        timeline.set_spans([(s["start"], s["end"], s["kind"]) for s in record["segments"]],
                           record["total"])

        ctk.CTkLabel(body, text="¿Qué estuviste haciendo?", font=self.fonts["tiny"],
                     text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, SPACE["xs"]))
        title_entry = ctk.CTkEntry(body, fg_color=COLORS["surface2"],
                                   border_color=COLORS["border"], border_width=1,
                                   text_color=COLORS["text"], font=self.fonts["body"],
                                   placeholder_text="Nombre de la sesión",
                                   placeholder_text_color=COLORS["text_faint"],
                                   corner_radius=RADIUS["xs"], height=38)
        title_entry.pack(fill="x", pady=(0, SPACE["md"]))
        title_entry.focus_set()

        ctk.CTkLabel(body, text="Anotaciones — usá # para etiquetar",
                     font=self.fonts["tiny"], text_color=COLORS["text_dim"]).pack(
            anchor="w", pady=(0, SPACE["xs"]))
        notes = ctk.CTkTextbox(body, height=100, fg_color=COLORS["surface2"],
                               border_color=COLORS["border"], border_width=1,
                               text_color=COLORS["text"], font=self.fonts["body"],
                               corner_radius=RADIUS["xs"], wrap="word")
        notes.pack(fill="both", expand=True, pady=(0, SPACE["md"]))
        self.hashtag_popup.attach(notes)

        def save():
            record["title"] = title_entry.get().strip() or "Sesión sin nombre"
            record["notes"] = notes.get("1.0", "end-1c").strip()
            self.db.save_session(record)
            window.destroy()
            self.mark_stale()
            self.refresh_all()
            self.views["Historial"].refresh_tags()
            self.views["Análisis"].refresh_tags()
            self.toasts.show(f"«{record['title']}» guardada.", tone="mint")

        def discard():
            window.destroy()
            self.toasts.show("Sesión descartada.", tone="rose")

        self._footer_buttons(footer, "No guardar", "Guardar", save, "accent", window)
        # "No guardar" descarta, no sólo cierra: hay que cambiarle la acción.
        footer.winfo_children()[0].configure(command=discard)
        window.bind("<Escape>", lambda _e: discard())

    # ------------------------------------------------------------------ #
    # Navegación auxiliar
    # ------------------------------------------------------------------ #

    def open_day(self, day):
        self.views["Historial"].focus_day(day)
        self.show_view("Historial")

    def export_csv(self):
        rows = self.views["Análisis"].current_rows()
        if not rows:
            rows = self.db.sessions_between(date(2000, 1, 1), date.today())
        if not rows:
            self.toasts.show("No hay sesiones para exportar.", tone="rose")
            return
        path = os.path.join(BASE_DIR, f"focusflow-{date.today().isoformat()}.csv")
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(stats.to_csv(self.db, rows))
        except OSError as exc:
            self.toasts.show(f"No se pudo exportar: {exc}", tone="rose")
            return
        self.toasts.show(f"Exportado a {os.path.basename(path)}", tone="mint")

    def import_legacy(self):
        candidates = self.db.legacy_candidates()
        if not candidates:
            self.toasts.show("No encontré ninguna base del programa anterior.",
                             tone="rose")
            return

        def run():
            total = sum(self.db.import_legacy(path) for path in candidates)
            self.settings["imported_legacy"] = True
            self.mark_stale()
            self.refresh_all()
            self.views["Historial"].refresh()
            self.views["Ajustes"].refresh()
            if total:
                self.toasts.show(
                    f"Importadas {total} {'sesión' if total == 1 else 'sesiones'}.",
                    tone="mint")
            else:
                self.toasts.show("No había sesiones nuevas para importar.", tone="accent")

        self.confirm("Importar historial",
                     f"Encontré {len(candidates)} "
                     f"{'base' if len(candidates) == 1 else 'bases'} del programa "
                     "anterior. Las sesiones que ya estén no se duplican.",
                     "Importar", run, tone="accent")

    def _offer_import(self):
        if self.settings["imported_legacy"] or self.db.count() > 0:
            return
        if not self.db.legacy_candidates():
            return
        self.toasts.show("Encontré historial del programa anterior. ¿Lo importo?",
                         tone="accent", action=self.import_legacy,
                         action_text="Importar")

    # ------------------------------------------------------------------ #
    # Recuperación
    # ------------------------------------------------------------------ #

    def _clear_recovery(self):
        try:
            if os.path.exists(RECOVERY_PATH):
                os.remove(RECOVERY_PATH)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Cierre
    # ------------------------------------------------------------------ #

    def on_close(self):
        if self.engine.running:
            self.confirm("Salir con una sesión abierta",
                         "Hay una sesión en curso y todavía no la guardaste. Si salís "
                         "ahora se pierde lo medido.",
                         "Salir igual", self._shutdown, tone="rose")
            return
        self._shutdown()

    def _shutdown(self):
        if self._tick_job is not None:
            try:
                self.root.after_cancel(self._tick_job)
            except tk.TclError:
                pass
        if self.tab is not None:
            self.tab.destroy()
        try:
            self.animator.stop()
        except Exception:
            pass
        self.sounds.stop_all()
        if keyboard is not None:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        self.db.close()
        self.root.destroy()


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    FocusFlowApp(root)
    root.mainloop()
