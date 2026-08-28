"""Pantalla de arranque.

Además de dar la bienvenida, cumple una función concreta: mientras se muestra,
la app calcula y dibuja todas las vistas con la ventana ya dimensionada pero
todavía invisible. Antes, la primera vez que se entraba a Análisis se veía cómo
se armaba —los lienzos nacían con tamaño 1 y se redibujaban al recibir su medida
real—; ahora eso ya pasó antes de que la ventana aparezca.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from . import render as R
from .config import APP_NAME, APP_TAGLINE
from .theme import COLORS, RADIUS

KEY = R.TRANSPARENT_KEY

WIDTH = 430
HEIGHT = 150
LOGO = 92
PAD = 26


class SplashScreen:
    """Recuadro redondeado con el logo y el nombre."""

    def __init__(self, root, fonts):
        self.root = root
        self.fonts = fonts
        self.window = None
        self.canvas = None
        self._photo = None
        self._shaped = True

    def _logo(self):
        """El mismo anillo del icono del programa."""
        ring = R.progress_ring(LOGO, 0.72, COLORS["accent"], COLORS["surface2"],
                               COLORS["surface"], thickness=0.115, padding=2)
        dot_size = int(LOGO * 0.20)
        dot = R.rounded_panel(dot_size, dot_size, dot_size / 2,
                              COLORS["surface"], COLORS["mint"])
        offset = (LOGO - dot_size) // 2
        ring.paste(dot, (offset, offset))
        return ring

    def _image(self):
        if self._shaped:
            image = R.shaped_panel(WIDTH, HEIGHT, RADIUS["lg"], COLORS["surface"],
                                   border=COLORS["border"], border_width=1.6, key=KEY)
        else:
            image = R.rounded_panel(WIDTH, HEIGHT, RADIUS["lg"], COLORS["app"],
                                    COLORS["surface"], border=COLORS["border"])

        image.paste(self._logo(), (PAD, (HEIGHT - LOGO) // 2))

        draw = ImageDraw.Draw(image)
        text_x = PAD + LOGO + 24
        draw.text((text_x, HEIGHT / 2 - 12), APP_NAME,
                  font=R.load_font(self.fonts.paths_bold, 30), anchor="lm",
                  fill=R.hex_to_rgb(COLORS["text"]))
        draw.text((text_x, HEIGHT / 2 + 18), APP_TAGLINE,
                  font=R.load_font(self.fonts.paths, 12), anchor="lm",
                  fill=R.hex_to_rgb(COLORS["text_dim"]))
        return image

    def show(self):
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        try:
            window.attributes("-transparentcolor", KEY)
            window.configure(bg=KEY)
        except tk.TclError:
            self._shaped = False
            window.configure(bg=COLORS["app"])

        canvas = tk.Canvas(window, width=WIDTH, height=HEIGHT, highlightthickness=0,
                           bd=0, bg=KEY if self._shaped else COLORS["app"])
        canvas.pack()
        self.window, self.canvas = window, canvas

        self._photo = ImageTk.PhotoImage(self._image())
        canvas.create_image(0, 0, anchor="nw", image=self._photo)

        x = (self.root.winfo_screenwidth() - WIDTH) // 2
        y = (self.root.winfo_screenheight() - HEIGHT) // 2
        window.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
        window.update()

    def close(self):
        if self.window is not None and self.window.winfo_exists():
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
