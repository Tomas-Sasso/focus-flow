"""Pestaña flotante: el estado de la sesión con la app minimizada.

Sirve para cuando estudiás desde un PDF a pantalla completa y no podés tener la
ventana del programa abierta. Es un `Toplevel` sin marco, siempre encima, que se
puede arrastrar y que se dibuja entero con PIL.

Las esquinas se recortan de verdad con `-transparentcolor`: lo que queda fuera de
la silueta redondeada se pinta con un color clave que Windows vuelve
transparente, así no se ven las esquinas cuadradas de la ventana por detrás.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from . import render as R
from .theme import COLORS, PHASE_STYLE, RADIUS

KEY = R.TRANSPARENT_KEY

# Tamaños de la pestaña en sus dos formas.
EXPANDED_HEIGHT = 64
MINIMIZED_HEIGHT = 38
RING = 36
PAD = 13
MARGIN = 26          # separación al borde de la pantalla en la posición inicial


def _fmt_clock(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _fmt_compact(seconds):
    """Minutos mientras falte más de uno; abajo de eso, segundos."""
    seconds = max(0, int(round(seconds)))
    if seconds >= 60:
        return f"{seconds // 60} min"
    return f"{seconds} s"


class FloatingTab:
    """La pestaña. La app la crea una vez y la enciende o apaga."""

    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.fonts = app.fonts

        self.enabled = False
        self.minimized = False
        self.window = None
        self.canvas = None
        self._photo = None
        self._menu = None
        self._drag = None
        self._shaped = True
        self._placed = False
        self._size = None

        # Estado que se dibuja
        self.label = "Sin sesión"
        self.color = COLORS["surface3"]
        self.time_text = "00:00"
        # Lo lee _size_for antes del primer update_from: sin esto, arrancar con la
        # pestaña activada y minimizada tiraba AttributeError.
        self.compact_text = "—"
        self.fraction = 0.0
        self.running = False

    # ------------------------------------------------------------------ #
    # Ciclo de vida
    # ------------------------------------------------------------------ #

    def _ensure_window(self):
        if self.window is not None and self.window.winfo_exists():
            return
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        # Que no herede la minimización de la ventana principal: justamente
        # tiene que quedar visible cuando la app se minimiza.
        try:
            window.attributes("-toolwindow", True)
        except tk.TclError:
            pass
        try:
            window.attributes("-transparentcolor", KEY)
            window.configure(bg=KEY)
        except tk.TclError:
            self._shaped = False
            window.configure(bg=COLORS["app"])

        canvas = tk.Canvas(window, highlightthickness=0, bd=0,
                           bg=KEY if self._shaped else COLORS["app"])
        canvas.pack()
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Button-3>", self._on_right_click)
        canvas.bind("<Double-Button-1>", lambda _e: self.toggle_minimized())
        canvas.configure(cursor="fleur")

        self.window, self.canvas = window, canvas
        self._placed = False
        self._size = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            self._close_menu()
            self.hide()
        else:
            self.sync_visibility()

    def toggle_minimized(self, value=None):
        self.minimized = (not self.minimized) if value is None else bool(value)
        self.app.settings["floating_tab_minimized"] = self.minimized
        self._close_menu()
        self.render()

    # ------------------------------------------------------------------ #
    # Visibilidad
    # ------------------------------------------------------------------ #

    def _root_hidden(self):
        try:
            return self.root.state() in ("iconic", "withdrawn")
        except tk.TclError:
            return False

    def sync_visibility(self):
        """La pestaña se muestra si está activada y la app está minimizada."""
        if self.enabled and self._root_hidden():
            self.show()
        else:
            self.hide()

    def show(self):
        # `render()` la ubica la primera vez y después sólo la redimensiona: si
        # reposicionara siempre, el primer tick tras arrastrarla la devolvería a
        # su lugar anterior.
        self._ensure_window()
        self.render()
        try:
            self.window.deiconify()
            self.window.attributes("-topmost", True)
        except tk.TclError:
            pass

    def hide(self):
        self._close_menu()
        if self.window is not None and self.window.winfo_exists():
            try:
                self.window.withdraw()
            except tk.TclError:
                pass

    def destroy(self):
        self._close_menu()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    # ------------------------------------------------------------------ #
    # Datos
    # ------------------------------------------------------------------ #

    def update_from(self, engine):
        """Toma el estado del motor. La app la llama en cada tick."""
        self.running = engine.running
        state = engine.state if engine.running else "idle"
        label, color, _text = PHASE_STYLE.get(state, PHASE_STYLE["idle"])
        self.label = label
        self.color = color

        remaining, span = engine.phase_progress()
        if engine.running and span > 0:
            self.fraction = max(0.0, min(1.0, 1.0 - remaining / span))
            self.time_text = _fmt_clock(remaining)
            self.compact_text = _fmt_compact(remaining)
        elif engine.running:
            # Sesión libre: no hay bloque, así que se muestra lo transcurrido.
            elapsed = engine.elapsed()
            self.fraction = 0.0
            self.time_text = _fmt_clock(elapsed)
            self.compact_text = _fmt_compact(elapsed)
        else:
            self.fraction = 0.0
            self.time_text = "00:00"
            self.compact_text = "—"

        if self.window is not None and self.window.winfo_exists() \
                and self.window.state() != "withdrawn":
            self.render()

    # ------------------------------------------------------------------ #
    # Dibujo
    # ------------------------------------------------------------------ #

    def _measure(self):
        """Ancho que necesita la pestaña según su texto."""
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        if self.minimized:
            font = R.load_font(self.fonts.paths_bold, 15)
            width = probe.textbbox((0, 0), self.compact_text, font=font)[2]
            return int(width) + PAD * 2 + 10, MINIMIZED_HEIGHT
        label_font = R.load_font(self.fonts.paths_bold, 11)
        time_font = R.load_font(self.fonts.paths_bold, 20)
        text_width = max(probe.textbbox((0, 0), self.label, font=label_font)[2],
                         probe.textbbox((0, 0), self.time_text, font=time_font)[2])
        return PAD + RING + 12 + int(text_width) + PAD, EXPANDED_HEIGHT

    def render(self):
        if self.window is None or not self.window.winfo_exists():
            return
        width, height = self._measure()
        image = (self._render_minimized(width, height) if self.minimized
                 else self._render_expanded(width, height))

        self._photo = ImageTk.PhotoImage(image)
        self.canvas.configure(width=width, height=height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        # Sólo se toca la geometría si el tamaño cambió de verdad. Pedirla en
        # cada redibujo —una vez por segundo— hacía que la ventana se reubicara
        # y deshacía el arrastre.
        if (width, height) == self._size and self._placed:
            return
        try:
            if self._placed:
                self.window.geometry(f"{width}x{height}")   # conserva dónde está
            else:
                x, y = self._position(width, height)
                self.window.geometry(f"{width}x{height}+{x}+{y}")
                self._placed = True
            self._size = (width, height)
        except tk.TclError:
            pass

    def _panel(self, width, height, radius):
        fill = COLORS["surface2"]
        if self._shaped:
            return R.shaped_panel(width, height, radius, fill,
                                  border=COLORS["border"], border_width=1.6, key=KEY)
        return R.rounded_panel(width, height, radius, COLORS["app"], fill,
                               border=COLORS["border"], border_width=1.6)

    def _render_expanded(self, width, height):
        image = self._panel(width, height, RADIUS["sm"])

        ring = R.progress_ring(RING, self.fraction, self.color, COLORS["surface3"],
                               COLORS["surface2"], thickness=0.16, padding=1)
        image.paste(ring, (PAD, (height - RING) // 2))

        draw = ImageDraw.Draw(image)
        text_x = PAD + RING + 12
        draw.text((text_x, height / 2 - 11), self.label,
                  font=R.load_font(self.fonts.paths_bold, 11), anchor="lm",
                  fill=R.hex_to_rgb(self.color))
        draw.text((text_x, height / 2 + 9), self.time_text,
                  font=R.load_font(self.fonts.paths_bold, 20), anchor="lm",
                  fill=R.hex_to_rgb(COLORS["text"]))
        return image

    def _render_minimized(self, width, height):
        image = self._panel(width, height, height / 2)
        # Franja del color del modo: la misma señal visual que usan los avisos.
        stripe = R.rounded_panel(4, height - 16, 2, COLORS["surface2"], self.color)
        image.paste(stripe, (PAD - 4, 8))

        draw = ImageDraw.Draw(image)
        draw.text((PAD + 6, height / 2), self.compact_text,
                  font=R.load_font(self.fonts.paths_bold, 15), anchor="lm",
                  fill=R.hex_to_rgb(self.color))
        return image

    def _position(self, width, height):
        """Dónde va: donde la dejaste, o abajo a la derecha la primera vez."""
        settings = self.app.settings
        x, y = settings["floating_tab_x"], settings["floating_tab_y"]
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if x < 0 or y < 0:
            x = screen_w - width - MARGIN
            y = screen_h - height - MARGIN - 40
        # Que nunca quede fuera de la pantalla, aunque cambie la resolución.
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height))
        return int(x), int(y)

    # ------------------------------------------------------------------ #
    # Arrastre
    # ------------------------------------------------------------------ #

    def _on_press(self, event):
        self._close_menu()
        self._drag = (event.x_root - self.window.winfo_x(),
                      event.y_root - self.window.winfo_y())

    def _on_drag(self, event):
        if self._drag is None:
            return
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        width, height = self.window.winfo_width(), self.window.winfo_height()
        x = max(0, min(x, self.root.winfo_screenwidth() - width))
        y = max(0, min(y, self.root.winfo_screenheight() - height))
        self.window.geometry(f"+{int(x)}+{int(y)}")

    def _on_release(self, _event):
        if self._drag is None:
            return
        self._drag = None
        self.app.settings.update(floating_tab_x=self.window.winfo_x(),
                                 floating_tab_y=self.window.winfo_y())

    # ------------------------------------------------------------------ #
    # Menú contextual
    # ------------------------------------------------------------------ #

    def _on_right_click(self, event):
        items = [("Maximizar" if self.minimized else "Minimizar",
                  lambda: self.toggle_minimized()),
                 ("Cerrar pestaña", self.app.disable_floating_tab)]
        self._open_menu(event.x_root, event.y_root, items)

    def _open_menu(self, x, y, items):
        self._close_menu()
        menu = ContextMenu(self.root, self.fonts, items, shaped=self._shaped)
        menu.open(x, y)
        self._menu = menu

    def _close_menu(self):
        if self._menu is not None:
            self._menu.close()
            self._menu = None


class ContextMenu:
    """Menú contextual con la estética de la app (no el nativo de Tk)."""

    ROW = 34
    WIDTH = 172
    PAD = 6

    def __init__(self, root, fonts, items, shaped=True):
        self.root = root
        self.fonts = fonts
        self.items = list(items)
        self.shaped = shaped
        self.window = None
        self.canvas = None
        self._photo = None
        self._hover = -1

    @property
    def height(self):
        return self.ROW * len(self.items) + self.PAD * 2

    def open(self, x, y):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        if self.shaped:
            try:
                window.attributes("-transparentcolor", KEY)
                window.configure(bg=KEY)
            except tk.TclError:
                self.shaped = False
        if not self.shaped:
            window.configure(bg=COLORS["surface"])

        canvas = tk.Canvas(window, width=self.WIDTH, height=self.height,
                           highlightthickness=0, bd=0,
                           bg=KEY if self.shaped else COLORS["surface"])
        canvas.pack()
        canvas.bind("<Motion>", self._on_motion)
        canvas.bind("<Leave>", lambda _e: self._set_hover(-1))
        canvas.bind("<Button-1>", self._on_click)
        canvas.configure(cursor="hand2")
        self.window, self.canvas = window, canvas
        self._render()

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, min(x, screen_w - self.WIDTH))
        y = max(0, min(y, screen_h - self.height))
        window.geometry(f"{self.WIDTH}x{self.height}+{int(x)}+{int(y)}")

        # Con el grab, cualquier click va a parar acá: así se puede cerrar el
        # menú cuando el click cae afuera.
        try:
            window.grab_set()
        except tk.TclError:
            pass
        window.bind("<Escape>", lambda _e: self.close())
        window.bind("<Button-1>", self._maybe_close_outside, add="+")
        window.bind("<Button-3>", self._maybe_close_outside, add="+")

    def _maybe_close_outside(self, event):
        if event.widget is not self.canvas:
            self.close()

    def _slot(self, y):
        slot = int((y - self.PAD) // self.ROW)
        return slot if 0 <= slot < len(self.items) else -1

    def _set_hover(self, slot):
        if slot != self._hover:
            self._hover = slot
            self._render()

    def _on_motion(self, event):
        self._set_hover(self._slot(event.y))

    def _on_click(self, event):
        slot = self._slot(event.y)
        if slot < 0:
            self.close()
            return
        action = self.items[slot][1]
        self.close()
        action()

    def _render(self):
        if self.canvas is None:
            return
        width, height = self.WIDTH, self.height
        if self.shaped:
            image = R.shaped_panel(width, height, RADIUS["sm"], COLORS["surface"],
                                   border=COLORS["border"], border_width=1.6, key=KEY)
        else:
            image = R.rounded_panel(width, height, RADIUS["sm"], COLORS["surface"],
                                    COLORS["surface"], border=COLORS["border"])

        draw = ImageDraw.Draw(image)
        font = R.load_font(self.fonts.paths, 13)
        for index, (label, _action) in enumerate(self.items):
            top = self.PAD + index * self.ROW
            if index == self._hover:
                chip = R.rounded_panel(width - 10, self.ROW - 4, 7,
                                       COLORS["surface"], COLORS["surface2"])
                image.paste(chip, (5, top + 2))
            color = COLORS["text"] if index == self._hover else COLORS["text_muted"]
            draw.text((16, top + self.ROW / 2), label, font=font, anchor="lm",
                      fill=R.hex_to_rgb(color))

        self._photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

    def close(self):
        if self.window is not None and self.window.winfo_exists():
            try:
                self.window.grab_release()
            except tk.TclError:
                pass
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
