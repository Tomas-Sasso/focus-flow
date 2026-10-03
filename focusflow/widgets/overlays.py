"""Ventanas flotantes: los avisos y las sugerencias de hashtag."""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from .. import render as R
from ..theme import COLORS, RADIUS

__all__ = [
    "ToastManager", "HashtagPopup",
]


# --------------------------------------------------------------------------- #
# Avisos
# --------------------------------------------------------------------------- #


class ToastManager:
    """Avisos apilados abajo a la derecha, con acción opcional.

    Se dibujan enteros con PIL sobre un lienzo, no con widgets de customtkinter.
    El motivo es el recorte de las esquinas: la ventana usa un color clave que
    Windows vuelve transparente, y customtkinter suaviza sus esquinas mezclando
    con el fondo, lo que dejaba un hilo magenta alrededor de la tarjeta. Con el
    dibujo propio el corte es duro y no queda ningún resto.
    """

    PAD = 14
    STRIPE = 4
    LINE = 18
    MAX_TEXT = 300

    def __init__(self, root, animator, fonts):
        self.root = root
        self.animator = animator
        self.fonts = fonts
        self.active = []

    def _wrap(self, draw, text, font, max_width):
        lines, current = [], ""
        for word in text.split():
            probe = f"{current} {word}".strip()
            if draw.textlength(probe, font=font) <= max_width or not current:
                current = probe
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:3]

    def show(self, message, tone="accent", duration=2800, action=None, action_text=""):
        color = COLORS.get(tone, COLORS["accent"])
        font = R.load_font(self.fonts.paths, 12)
        action_font = R.load_font(self.fonts.paths_bold, 12)
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))

        lines = self._wrap(probe, message, font, self.MAX_TEXT)
        text_width = int(max(probe.textlength(line, font=font) for line in lines))
        action_width = 0
        if action is not None:
            action_width = int(probe.textlength(action_text or "Sí",
                                                font=action_font)) + 28
            duration = max(duration, 9000)

        width = (self.PAD + self.STRIPE + 10 + text_width + self.PAD
                 + (action_width + 10 if action_width else 0))
        height = max(46, len(lines) * self.LINE + self.PAD * 2)

        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        try:
            toast.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        shaped = True
        try:
            toast.attributes("-transparentcolor", R.TRANSPARENT_KEY)
            toast.configure(bg=R.TRANSPARENT_KEY)
        except tk.TclError:
            shaped = False
            toast.configure(bg=COLORS["overlay"])

        canvas = tk.Canvas(toast, width=width, height=height, highlightthickness=0,
                           bd=0, bg=R.TRANSPARENT_KEY if shaped else COLORS["overlay"])
        canvas.pack()

        if shaped:
            image = R.shaped_panel(width, height, RADIUS["sm"], COLORS["surface2"],
                                   border=COLORS["border"], border_width=1.6)
        else:
            image = R.rounded_panel(width, height, RADIUS["sm"], COLORS["overlay"],
                                    COLORS["surface2"], border=COLORS["border"])

        stripe = R.rounded_panel(self.STRIPE, height - 22, 2, COLORS["surface2"], color)
        image.paste(stripe, (self.PAD, 11))

        draw = ImageDraw.Draw(image)
        text_x = self.PAD + self.STRIPE + 10
        top = (height - len(lines) * self.LINE) / 2
        for index, line in enumerate(lines):
            draw.text((text_x, top + index * self.LINE + self.LINE / 2), line,
                      font=font, anchor="lm", fill=R.hex_to_rgb(COLORS["text"]))

        action_box = None
        if action is not None:
            box_w, box_h = action_width, 28
            box_x = width - self.PAD - box_w
            box_y = (height - box_h) // 2
            chip = R.rounded_panel(box_w, box_h, RADIUS["xs"], COLORS["surface2"], color)
            image.paste(chip, (box_x, box_y))
            draw.text((box_x + box_w / 2, box_y + box_h / 2), action_text or "Sí",
                      font=action_font, anchor="mm",
                      fill=R.hex_to_rgb(R.readable_on(color, dark=COLORS["app"])))
            action_box = (box_x, box_y, box_x + box_w, box_y + box_h)

        photo = ImageTk.PhotoImage(image)
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.image = photo   # que no lo junte el recolector

        def dismiss(_event=None):
            def fade_out(value):
                try:
                    toast.attributes("-alpha", value)
                except tk.TclError:
                    pass

            def destroy():
                try:
                    toast.destroy()
                except tk.TclError:
                    pass
                if toast in self.active:
                    self.active.remove(toast)

            self.animator.to(("toast_out", id(toast)), 1.0, 0.0, duration=0.22,
                             easing="out_cubic", on_update=fade_out, on_done=destroy)

        if action_box is not None:
            def on_click(event):
                x0, y0, x1, y1 = action_box
                if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                    action()
                    dismiss()

            canvas.bind("<Button-1>", on_click)
            canvas.bind("<Motion>", lambda e: canvas.configure(
                cursor="hand2" if action_box[0] <= e.x <= action_box[2]
                and action_box[1] <= e.y <= action_box[3] else ""))

        index = len(self.active)
        x = self.root.winfo_rootx() + self.root.winfo_width() - width - 26
        y = (self.root.winfo_rooty() + self.root.winfo_height() - height - 26
             - index * (height + 10))
        toast.geometry(f"{width}x{height}+{x}+{y + 14}")
        self.active.append(toast)

        def fade_in(value):
            try:
                toast.attributes("-alpha", value)
                toast.geometry(f"{width}x{height}+{x}+{int(y + 14 * (1 - value))}")
            except tk.TclError:
                pass

        self.animator.to(("toast_in", id(toast)), 0.0, 1.0, duration=0.26,
                         easing="out_cubic", on_update=fade_in)
        self.root.after(duration, dismiss)


# --------------------------------------------------------------------------- #
# Sugerencias de hashtag
# --------------------------------------------------------------------------- #


class HashtagPopup:
    WIDTH = 230
    ROW = 30
    MAX_ROWS = 5

    def __init__(self, root, animator, fonts, provider):
        self.root = root
        self.animator = animator
        self.fonts = fonts
        self.provider = provider
        self.toplevel = None
        self.canvas = None
        self.photo = None
        self.suggestions = []
        self.index = 0
        self.offset = 0
        self.textbox = None
        self.visible = False

    def attach(self, textbox):
        textbox.bind("<KeyRelease>", lambda e: self._on_key(e, textbox), add="+")
        textbox.bind("<FocusOut>", lambda _e: self.root.after(140, self.hide), add="+")
        textbox.bind("<Escape>", lambda _e: self.hide(), add="+")
        textbox.bind("<Down>", lambda _e: self._nav(1), add="+")
        textbox.bind("<Up>", lambda _e: self._nav(-1), add="+")
        textbox.bind("<Tab>", lambda _e: self._accept(), add="+")
        textbox.bind("<Return>", lambda _e: self._accept(), add="+")

    def _nav(self, delta):
        if not self.visible:
            return None
        self.move(delta)
        return "break"

    def _accept(self):
        if not self.visible or not self.suggestions:
            return None
        self._insert(self.suggestions[self.index])
        return "break"

    def _on_key(self, event, textbox):
        import re

        if event.keysym in ("Escape", "Return", "Tab", "Up", "Down"):
            return
        try:
            typed = textbox.get(textbox.index("insert linestart"), textbox.index("insert"))
        except tk.TclError:
            return
        match = re.search(r"#([\wÀ-ɏ-]*)$", typed, re.UNICODE)
        if match is None:
            self.hide()
            return
        suggestions = self.provider(match.group(1))
        if not suggestions:
            self.hide()
            return
        try:
            box = textbox.bbox("insert")
        except tk.TclError:
            box = None
        if not box:
            self.hide()
            return
        self.show(textbox, textbox.winfo_rootx() + box[0],
                  textbox.winfo_rooty() + box[1] + box[3] + 6, suggestions)

    def _ensure(self):
        if self.toplevel is not None and self.toplevel.winfo_exists():
            return
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=COLORS["surface3"])
        canvas = tk.Canvas(top, highlightthickness=0, bd=0, bg=COLORS["surface3"])
        canvas.pack()
        canvas.bind("<Button-1>", self._on_click)
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<Motion>", self._on_motion)
        self.toplevel, self.canvas = top, canvas

    def _rows(self):
        return min(self.MAX_ROWS, len(self.suggestions))

    def _height(self):
        return self._rows() * self.ROW + 12

    def show(self, textbox, x, y, suggestions):
        self.textbox = textbox
        if suggestions != self.suggestions:
            self.suggestions = suggestions
            self.index = self.offset = 0
        self._ensure()
        height = self._height()
        self.canvas.configure(width=self.WIDTH, height=height)
        self._render()
        self.toplevel.geometry(f"{self.WIDTH}x{height}+{int(x)}+{int(y)}")
        if not self.visible:
            self.visible = True
            try:
                self.toplevel.deiconify()
                self.toplevel.attributes("-alpha", 0.0)
            except tk.TclError:
                pass

            def fade(value):
                try:
                    self.toplevel.attributes("-alpha", value)
                except tk.TclError:
                    pass

            self.animator.to(("tagpop", id(self)), 0.0, 1.0, duration=0.14,
                             easing="out_cubic", on_update=fade)

    def hide(self):
        self.visible = False
        if self.toplevel is not None and self.toplevel.winfo_exists():
            try:
                self.toplevel.withdraw()
            except tk.TclError:
                pass

    def move(self, delta):
        if not self.suggestions:
            return
        self.index = max(0, min(len(self.suggestions) - 1, self.index + delta))
        if self.index < self.offset:
            self.offset = self.index
        elif self.index >= self.offset + self._rows():
            self.offset = self.index - self._rows() + 1
        self._render()

    def _slot(self, y):
        slot = int((y - 6) // self.ROW)
        return slot if 0 <= slot < self._rows() else None

    def _on_motion(self, event):
        slot = self._slot(event.y)
        if slot is not None and self.offset + slot != self.index:
            self.index = self.offset + slot
            self._render()

    def _on_click(self, event):
        slot = self._slot(event.y)
        if slot is not None:
            self._insert(self.suggestions[self.offset + slot])

    def _on_wheel(self, event):
        self.move(-1 if event.delta > 0 else 1)
        return "break"

    def _insert(self, tag):
        import re

        box = self.textbox
        if box is None or not box.winfo_exists():
            return
        try:
            here = box.index("insert")
            typed = box.get(box.index("insert linestart"), here)
        except tk.TclError:
            return
        match = re.search(r"#([\wÀ-ɏ-]*)$", typed, re.UNICODE)
        if match is None:
            return
        try:
            box.delete(f"{here} - {len(match.group(1))} chars", here)
            box.insert("insert", tag + " ")
        except tk.TclError:
            return
        self.hide()

    def _render(self):
        if self.canvas is None:
            return
        height = self._height()
        image = R.rounded_panel(self.WIDTH, height, 12, COLORS["surface3"], COLORS["surface3"])
        draw = ImageDraw.Draw(image)
        font = R.load_font(self.fonts.paths, 13)
        font_bold = R.load_font(self.fonts.paths_bold, 13)

        for slot in range(self._rows()):
            position = self.offset + slot
            if position >= len(self.suggestions):
                break
            y = 6 + slot * self.ROW
            selected = position == self.index
            if selected:
                image.paste(R.rounded_panel(self.WIDTH - 12, self.ROW - 4, 8,
                                            COLORS["surface3"],
                                            COLORS["accent_soft"]), (6, y + 2))
            draw.text((16, y + self.ROW / 2), f"#{self.suggestions[position]}",
                      font=font_bold if selected else font, anchor="lm",
                      fill=R.hex_to_rgb(COLORS["text"]))

        if len(self.suggestions) > self._rows():
            draw.text((self.WIDTH - 14, height - 8),
                      f"{self.index + 1}/{len(self.suggestions)}", font=font, anchor="rs",
                      fill=R.hex_to_rgb(R.mix(COLORS["text"], COLORS["surface3"], 0.45)))

        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
