"""Sonido: el parlante y el control de volumen de la barra lateral."""

from __future__ import annotations

import customtkinter as ctk
from PIL import Image

from .. import render as R
from ..theme import COLORS, SPACE
from ._base import PILCanvas

__all__ = [
    "SpeakerButton", "VolumeControl",
]


# --------------------------------------------------------------------------- #
# Sonido
# --------------------------------------------------------------------------- #


class SpeakerButton(PILCanvas):
    """Parlante que se tacha al silenciar. Click para alternar."""

    def __init__(self, master, background, command=None, size=22, **kwargs):
        super().__init__(master, background, width=size, height=size, **kwargs)
        self.size = size
        self.command = command
        self.muted = False
        self._hover = False
        self.bind("<Button-1>", lambda _e: self.command and self.command(), add="+")
        self.bind("<Enter>", lambda _e: self._set_hover(True), add="+")
        self.bind("<Leave>", lambda _e: self._set_hover(False), add="+")
        self.configure(cursor="hand2")

    def _set_hover(self, value):
        if value != self._hover:
            self._hover = value
            self.schedule_redraw()

    def set_muted(self, muted):
        muted = bool(muted)
        if muted != self.muted:
            self.muted = muted
            self.schedule_redraw()

    def render(self, width, height):
        side = min(width, height)
        if self.muted:
            color = COLORS["text"] if self._hover else COLORS["text_faint"]
        else:
            color = COLORS["text"] if self._hover else COLORS["text_muted"]
        icon = R.speaker_icon(side, color, self.background, self.muted)
        if (width, height) != (side, side):
            canvas = Image.new("RGB", (width, height), R.hex_to_rgb(self.background))
            canvas.paste(icon, ((width - side) // 2, (height - side) // 2))
            return canvas
        return icon


class VolumeControl(ctk.CTkFrame):
    """Barra de volumen con parlante, para la barra lateral.

    El parlante silencia y devuelve el volumen que había antes, que es lo que
    uno espera: silenciar no debería hacerte perder el nivel que ya elegiste.
    """

    def __init__(self, master, fonts, settings, on_change, background=None, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.fonts = fonts
        self.settings = settings
        self.on_change = on_change
        self.background = background or COLORS["sidebar"]

        ctk.CTkLabel(self, text="Sonido de la app", font=fonts["tiny"],
                     text_color=COLORS["text_dim"], anchor="w").pack(
            anchor="w", pady=(0, SPACE["xs"]))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")

        self.speaker = SpeakerButton(row, self.background, command=self.toggle_mute)
        self.speaker.pack(side="left", padx=(0, SPACE["sm"]))

        # `width=1`: sin esto el deslizador pide 200 px y arrastra el ancho de
        # toda la barra lateral. Se estira solo con el `pack(expand=True)`.
        self.slider = ctk.CTkSlider(
            row, from_=0, to=100, number_of_steps=100, command=self._on_slide,
            fg_color=COLORS["surface2"], progress_color=COLORS["accent"],
            button_color=COLORS["text"], button_hover_color=COLORS["accent_hover"],
            height=14, button_length=0, width=1)
        self.slider.pack(side="left", fill="x", expand=True)

        self.refresh()

    # -- estado ------------------------------------------------------------ #

    @property
    def _muted(self):
        return bool(self.settings["muted"]) or int(self.settings["volume"]) <= 0

    def refresh(self):
        self.slider.set(int(self.settings["volume"]))
        self.speaker.set_muted(self._muted)
        self.slider.configure(
            progress_color=COLORS["surface3"] if self._muted else COLORS["accent"])

    def _apply(self, volume, muted):
        self.settings.update(volume=int(volume), muted=bool(muted))
        self.refresh()
        self.on_change()

    def _on_slide(self, value):
        volume = int(round(float(value)))
        if volume > 0:
            # Mover la barra hacia arriba saca del silencio y pasa a ser el
            # nivel que se recuerda.
            self.settings["volume_before_mute"] = volume
            self._apply(volume, False)
        else:
            self._apply(0, True)

    def toggle_mute(self):
        if self._muted:
            previous = int(self.settings["volume_before_mute"]) or 70
            self._apply(max(1, previous), False)
        else:
            self.settings["volume_before_mute"] = int(self.settings["volume"])
            self._apply(0, True)
