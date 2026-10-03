"""Botones: el botón de customtkinter con color interpolado y sus tonos."""

from __future__ import annotations

import customtkinter as ctk

from .. import render as R
from ..theme import COLORS, RADIUS

__all__ = [
    "SmoothButton", "TONES", "button",
]


# --------------------------------------------------------------------------- #
# Botones
# --------------------------------------------------------------------------- #


class SmoothButton(ctk.CTkButton):
    """Botón cuyo color se interpola en vez de saltar."""

    def __init__(self, master, animator=None, base_color=None, hover_color=None,
                 press_depth=0.12, **kwargs):
        base_color = base_color or kwargs.get("fg_color") or COLORS["accent"]
        kwargs.setdefault("fg_color", base_color)
        kwargs.setdefault("corner_radius", RADIUS["sm"])
        kwargs.setdefault("border_width", 0)
        kwargs.setdefault("height", 38)
        kwargs["hover"] = False
        super().__init__(master, **kwargs)
        self.animator = animator
        self.base_color = base_color
        self.hover_target = hover_color or R.lighten(base_color, 0.10)
        self.press_depth = press_depth
        self._current = base_color
        self._hovering = False
        self._pressed = False
        for widget in self._targets():
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")
            widget.bind("<ButtonPress-1>", self._on_press, add="+")
            widget.bind("<ButtonRelease-1>", self._on_release, add="+")

    def _targets(self):
        widgets = [self]
        for attr in ("_canvas", "_text_label", "_image_label"):
            child = getattr(self, attr, None)
            if child is not None:
                widgets.append(child)
        return widgets

    def set_base_color(self, color, hover_color=None, animate=True):
        self.base_color = color
        self.hover_target = hover_color or R.lighten(color, 0.10)
        self._to(self._resting(), animate=animate)

    def _resting(self):
        if str(self.cget("state")) == "disabled":
            return R.mix(self.base_color, COLORS["surface2"], 0.6)
        if self._pressed:
            return R.darken(self.base_color, self.press_depth)
        if self._hovering:
            return self.hover_target
        return self.base_color

    def _to(self, color, animate=True, duration=0.16):
        if not animate or self.animator is None:
            self._current = color
            try:
                self.configure(fg_color=color)
            except Exception:
                pass
            return

        def update(value):
            self._current = value
            try:
                if self.winfo_exists():
                    self.configure(fg_color=value)
            except Exception:
                pass

        self.animator.color(("btn", id(self)), self._current, color,
                            duration=duration, easing="out_cubic", on_update=update)

    def _on_enter(self, _e=None):
        if str(self.cget("state")) == "disabled":
            return
        self._hovering = True
        self._to(self._resting())

    def _on_leave(self, _e=None):
        self._hovering = self._pressed = False
        self._to(self._resting(), duration=0.22)

    def _on_press(self, _e=None):
        if str(self.cget("state")) == "disabled":
            return
        self._pressed = True
        self._to(self._resting(), duration=0.07)

    def _on_release(self, _e=None):
        self._pressed = False
        self._to(self._resting(), duration=0.28)

    def configure(self, **kwargs):
        super().configure(**kwargs)
        if "state" in kwargs:
            self._to(self._resting(), animate=False)


TONES = {
    "accent": ("accent", "accent_hover", "app"),
    "mint": ("mint", "mint_hover", "app"),
    "amber": ("amber", "amber_hover", "app"),
    "rose": ("rose", "rose_hover", "app"),
    "lavender": ("lavender", "lavender", "app"),
    "ghost": ("surface3", "surface4", "text"),
    "quiet": ("surface2", "surface3", "text"),
    "danger": ("danger", "danger_hover", "text"),
    "orange": ("orange", "orange_hover", "app"),
    "yellow": ("yellow", "yellow_hover", "app"),
}


def button(master, animator, text, command, tone="accent", **kwargs):
    fill, hover, text_key = TONES.get(tone, TONES["accent"])
    kwargs.setdefault("text_color", COLORS[text_key])
    return SmoothButton(master, animator=animator, base_color=COLORS[fill],
                        hover_color=COLORS[hover], text=text, command=command, **kwargs)
