"""Ventanas sin marco: avisos, menús, sugerencias, pestaña flotante y splash.

Todas estas piezas son un `Toplevel` sin marco que muestra una sola imagen PIL
dibujada entera por quien la usa. Este módulo se ocupa de lo que tienen en
común —cómo se recorta la forma, qué hay detrás, dónde está el área de trabajo y
a qué escala dibujar— para que cada una no lo resuelva a su manera.

Tres modos de recorte (`FramelessWindow.mode`):

- ``"colorkey"`` (el de siempre en Windows): lo que queda fuera de la forma se
  pinta con el color clave `KEY` (#FE00FE) y Windows lo vuelve transparente con
  `-transparentcolor`. El corte es binario, así que el borde suavizado se
  compone acá **contra lo que hay detrás** (una foto tomada antes de mostrar, o
  un color promedio): los píxeles con α ≥ 0,5 se mezclan con eso y los de
  α < 0,5 pasan a ser clave. Así nunca queda un píxel a medio camino con el
  magenta, que era el hilo rosado que se veía alrededor de las tarjetas.
- ``"layered"`` (sólo Windows y sólo con ``FOCUSFLOW_LAYERED=1``, experimental):
  ventana con alfa por píxel (`WS_EX_LAYERED` + `UpdateLayeredWindow` con BGRA
  premultiplicado). Bordes suaves de verdad, sombra real y fundidos sin volver a
  dibujar. Si cualquier paso falla, la ventana vuelve sola a color clave.
- ``"plain"`` (X11 y cualquier Tk sin color clave): la imagen se aplana entera
  contra lo de atrás (la foto si la hay; si no, `bg_base`). Con la foto, en las
  capturas de desarrollo se ve igual que en Windows.

A verificar en Windows (no se puede probar en el contenedor de desarrollo):

1. Modo ``layered``: que `UpdateLayeredWindow` funcione sobre el `Toplevel` de
   Tk (marco obtenido con `wm frame`), que el lienzo siga recibiendo clics y la
   rueda, que `-topmost` se mantenga, que `withdraw`/`deiconify` conserven la
   imagen y que el DPI (px físicos) coincida con la geometría de Tk.
2. `snapshot` con `include_layered_windows=True`: que la ventana principal salga
   en la foto aunque use `-alpha`, el costo de la captura (Pillow fotografía la
   pantalla entera y recorta) y las coordenadas con escalado ≠ 100 % y con
   monitores a la izquierda o arriba del principal (coordenadas negativas).
3. `screen_work_area`: `SPI_GETWORKAREA` da el área del monitor **principal**.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk

import numpy as np
from PIL import Image, ImageGrab, ImageTk

from . import render as R
from . import theme

__all__ = [
    "KEY",
    "EDGE_FALLBACK",
    "snapshot",
    "screen_work_area",
    "layered_enabled",
    "FramelessWindow",
]

_IS_WINDOWS = os.name == "nt"

#: Color clave de las ventanas recortadas (el mismo de siempre en render.py).
KEY = R.TRANSPARENT_KEY

#: Color contra el que se suaviza el borde si no hay foto de lo de atrás: un
#: gris medio queda bien tanto sobre fondos claros como oscuros.
EDGE_FALLBACK = "#808080"

#: Por debajo de esta opacidad un píxel se corta (pasa a ser clave).
ALPHA_THRESHOLD = 0.5

#: Alto que se le descuenta a la pantalla por la barra de tareas cuando no se
#: puede preguntar el área de trabajo (px lógicos).
TASKBAR_FALLBACK = 48

_RING = 2   # ancho del anillo que mide edge_color_around


def _bg_base():
    return theme.COLORS.get("bg_base", "#0C0A1F")


def _intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


# --------------------------------------------------------------------------- #
# Fotos de pantalla
# --------------------------------------------------------------------------- #


def _virtual_screen_win():
    """Rect (x0, y0, x1, y1) de todos los monitores juntos, en px físicos.

    Sólo Windows. Puede empezar en negativo si hay un monitor a la izquierda o
    arriba del principal. None si no se puede preguntar.
    """
    if not _IS_WINDOWS:
        return None
    try:
        import ctypes

        metrics = ctypes.windll.user32.GetSystemMetrics
        # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
        x, y = metrics(76), metrics(77)
        w, h = metrics(78), metrics(79)
    except (OSError, AttributeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, x + w, y + h)


def _grab(bbox):
    """Foto de `bbox` y la parte que de verdad cayó dentro de la pantalla.

    Devuelve (imagen RGB del tamaño pedido, (x0, y0, x1, y1) válido en coords de
    la imagen) o (None, None). Lo que queda fuera de la pantalla se rellena
    repitiendo el borde, así un desenfoque posterior no arrastra negro.
    """
    x0, y0, x1, y1 = (int(round(v)) for v in bbox)
    if x1 <= x0 or y1 <= y0:
        return None, None
    try:
        if _IS_WINDOWS:
            screen = _virtual_screen_win()
            clip = _intersect((x0, y0, x1, y1), screen) if screen else (x0, y0, x1, y1)
            if clip is None:
                return None, None
            # include_layered_windows: sin esto Windows deja afuera de la foto a
            # las ventanas "layered", y la principal lo es mientras usa -alpha.
            part = ImageGrab.grab(bbox=clip, include_layered_windows=True, all_screens=True)
        else:
            full = ImageGrab.grab(xdisplay=os.environ.get("DISPLAY") or None)
            clip = _intersect((x0, y0, x1, y1), (0, 0, full.width, full.height))
            if clip is None:
                return None, None
            part = full.crop(clip)
    except Exception:   # noqa: BLE001 — sin foto hay respaldo (color promedio o bg_base)
        return None, None

    part = part.convert("RGB")
    left, top = clip[0] - x0, clip[1] - y0
    valid = (left, top, left + part.width, top + part.height)
    if part.size == (x1 - x0, y1 - y0):
        return part, valid
    arr = np.asarray(part)
    arr = np.pad(arr, ((top, (y1 - y0) - valid[3]), (left, (x1 - x0) - valid[2]), (0, 0)),
                 mode="edge")
    return Image.fromarray(arr, "RGB"), valid


def snapshot(bbox):
    """Foto de pantalla de `bbox` = (x0, y0, x1, y1) en px físicos.

    Devuelve una imagen RGB exactamente del tamaño pedido (lo que cae fuera de la
    pantalla repite el borde) o None si la captura falla. En X11 usa
    `xdisplay=$DISPLAY`; en Windows incluye las ventanas con transparencia.
    """
    image, _valid = _grab(bbox)
    return image


def screen_work_area(root):
    """Área de trabajo (x0, y0, x1, y1) en px físicos: la pantalla sin la barra de tareas.

    Windows: `SPI_GETWORKAREA` (monitor principal). Si no se puede, la pantalla
    entera menos 48 px lógicos abajo.
    """
    if _IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                if rect.right > rect.left and rect.bottom > rect.top:
                    return (rect.left, rect.top, rect.right, rect.bottom)
        except (OSError, AttributeError, ValueError):
            pass   # respaldo de abajo
    try:
        width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    except tk.TclError:
        width, height = 1920, 1080
    taskbar = int(round(TASKBAR_FALLBACK * _window_scale(root)))
    return (0, 0, width, max(1, height - taskbar))


def layered_enabled():
    """Alfa por píxel: sólo en Windows y sólo si se pidió con FOCUSFLOW_LAYERED=1."""
    return os.name == "nt" and os.environ.get("FOCUSFLOW_LAYERED") == "1"


def _window_scale(root):
    """Escala de ventana de customtkinter para `root` (1,0 si no se puede saber)."""
    scale_of = getattr(theme, "window_scale", None)
    try:
        if scale_of is not None:
            return float(scale_of(root))
        import customtkinter as ctk

        return float(ctk.ScalingTracker.get_window_scaling(root))
    except Exception:   # noqa: BLE001 — un root que CTk no registró (tk.Tk de pruebas)
        return 1.0


# --------------------------------------------------------------------------- #
# Composición
# --------------------------------------------------------------------------- #


def _under(behind, width, height):
    """Lo de atrás como arreglo float32 que se pueda difundir a (h, w, 3)."""
    if isinstance(behind, Image.Image):
        if behind.size == (width, height):
            return np.asarray(behind.convert("RGB"), np.float32)
        # Una foto de otro tamaño no se puede alinear: se usa su color promedio.
        mean = np.asarray(behind.convert("RGB"), np.float32).reshape(-1, 3).mean(axis=0)
        return mean.reshape(1, 1, 3)
    color = behind if isinstance(behind, str) else EDGE_FALLBACK
    return np.array(R.hex_to_rgb(color), np.float32).reshape(1, 1, 3)


def _compose(rgba, behind, key=None, threshold=ALPHA_THRESHOLD):
    """Aplana `rgba` sobre `behind`; con `key`, corta lo de α < threshold.

    Los píxeles que quedan se mezclan contra lo de atrás —nunca contra la clave—,
    y si alguno saliera idéntico a la clave se corre un nivel de verde para que
    Windows no lo agujeree.
    """
    arr = np.asarray(rgba, np.float32)
    height, width = arr.shape[:2]
    alpha = arr[..., 3:4] * (1.0 / 255.0)
    under = _under(behind, width, height)
    out = arr[..., :3] * alpha + under * (1.0 - alpha)
    out = np.clip(np.rint(out), 0, 255).astype(np.uint8)
    if key is not None:
        key_rgb = np.array(R.hex_to_rgb(key), np.uint8)
        clash = np.all(out == key_rgb, axis=-1)
        if clash.any():
            out[clash, 1] = key_rgb[1] + 1
        out[alpha[..., 0] < threshold] = key_rgb
    return Image.fromarray(out, "RGB")


def _premultiplied_bgra(rgba):
    """Bytes BGRA con alfa premultiplicado, filas de arriba abajo (para UpdateLayeredWindow)."""
    arr = np.asarray(rgba, np.uint16)
    alpha = arr[..., 3]
    out = np.empty(arr.shape, np.uint8)
    for dst, src in ((0, 2), (1, 1), (2, 0)):
        out[..., dst] = (arr[..., src] * alpha + 127) // 255
    out[..., 3] = alpha
    return out.tobytes()


# --------------------------------------------------------------------------- #
# Alfa por píxel (sólo Windows, FOCUSFLOW_LAYERED=1) — a verificar en Windows
# --------------------------------------------------------------------------- #


class _LayeredBackend:
    """`WS_EX_LAYERED` + `UpdateLayeredWindow` sobre el marco de un Toplevel de Tk.

    Tk deja de pintar esa ventana: lo que se ve es el mapa de bits que se le pasa
    a Windows. Los clics siguen llegando al lienzo (los píxeles con α = 0 los
    dejan pasar). No se puede mezclar con `-alpha` ni `-transparentcolor` (usan
    `SetLayeredWindowAttributes` y desde ahí `UpdateLayeredWindow` falla), por
    eso la opacidad general va por `SourceConstantAlpha`.

    Todo este código está escrito según la documentación de Win32 y NO se probó
    en Windows: cualquier falla (excepción o retorno 0) hace que la ventana
    vuelva a color clave.
    """

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    ULW_ALPHA = 0x00000002
    AC_SRC_OVER = 0x00
    AC_SRC_ALPHA = 0x01
    BI_RGB = 0
    DIB_RGB_COLORS = 0

    def __init__(self, window):
        if not _IS_WINDOWS:
            raise OSError("UpdateLayeredWindow sólo existe en Windows")
        import ctypes
        from ctypes import wintypes

        self.window = window
        self.hwnd = None
        self._ctypes = ctypes
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                        ("SourceConstantAlpha", ctypes.c_ubyte),
                        ("AlphaFormat", ctypes.c_ubyte)]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        self.BLENDFUNCTION, self.BITMAPINFO = BLENDFUNCTION, BITMAPINFO
        self.BITMAPINFOHEADER = BITMAPINFOHEADER
        self.POINT, self.SIZE = wintypes.POINT, wintypes.SIZE

        # Tipos explícitos: en 64 bits los handles no entran en el int por
        # defecto de ctypes y se truncarían.
        u, g = self._user32, self._gdi32
        handle = ctypes.c_void_p
        u.GetDC.argtypes, u.GetDC.restype = [handle], handle
        u.ReleaseDC.argtypes, u.ReleaseDC.restype = [handle, handle], ctypes.c_int
        u.GetWindowLongW.argtypes = [handle, ctypes.c_int]
        u.GetWindowLongW.restype = wintypes.LONG
        u.SetWindowLongW.argtypes = [handle, ctypes.c_int, wintypes.LONG]
        u.SetWindowLongW.restype = wintypes.LONG
        u.UpdateLayeredWindow.argtypes = [
            handle, handle, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
            handle, ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
            ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
        u.UpdateLayeredWindow.restype = wintypes.BOOL
        g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = [handle], handle
        g.CreateDIBSection.argtypes = [handle, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_void_p), handle, wintypes.DWORD]
        g.CreateDIBSection.restype = handle
        g.SelectObject.argtypes, g.SelectObject.restype = [handle, handle], handle
        g.DeleteObject.argtypes, g.DeleteObject.restype = [handle], wintypes.BOOL
        g.DeleteDC.argtypes, g.DeleteDC.restype = [handle], wintypes.BOOL

    def _frame(self):
        """HWND del marco real del Toplevel (`wm frame`), ya mapeado."""
        return int(self.window.wm_frame(), 16)

    def attach(self):
        """Marca el marco como layered. Tk puede recrear el marco (p. ej. al cambiar
        -toolwindow), así que se vuelve a comprobar antes de cada actualización."""
        hwnd = self._frame()
        if not hwnd:
            raise OSError("el Toplevel todavía no tiene marco")
        style = self._user32.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
        if not style & self.WS_EX_LAYERED:
            self._user32.SetWindowLongW(hwnd, self.GWL_EXSTYLE, style | self.WS_EX_LAYERED)
        self.hwnd = hwnd

    def detach(self):
        """Saca el estilo layered (para volver a color clave)."""
        if not self.hwnd:
            return
        try:
            style = self._user32.GetWindowLongW(self.hwnd, self.GWL_EXSTYLE)
            self._user32.SetWindowLongW(self.hwnd, self.GWL_EXSTYLE,
                                        style & ~self.WS_EX_LAYERED)
        except (OSError, AttributeError, ValueError):
            pass   # la ventana ya no existe: no hay nada que restaurar
        self.hwnd = None

    def _blend(self, alpha):
        return self.BLENDFUNCTION(self.AC_SRC_OVER, 0, max(0, min(255, int(round(alpha * 255)))),
                                  self.AC_SRC_ALPHA)

    def update(self, rgba, x, y, alpha=1.0):
        """Sube el mapa de bits y ubica la ventana. Devuelve False si Windows se negó."""
        ctypes = self._ctypes
        if self.hwnd != self._frame():
            self.attach()
        width, height = rgba.size
        data = _premultiplied_bgra(rgba)

        info = self.BITMAPINFO()
        header = info.bmiHeader
        header.biSize = ctypes.sizeof(self.BITMAPINFOHEADER)
        header.biWidth, header.biHeight = width, -height    # negativo: de arriba abajo
        header.biPlanes, header.biBitCount = 1, 32
        header.biCompression = self.BI_RGB

        u, g = self._user32, self._gdi32
        screen_dc = u.GetDC(None)
        memory_dc = g.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        bitmap = g.CreateDIBSection(memory_dc, ctypes.byref(info), self.DIB_RGB_COLORS,
                                    ctypes.byref(bits), None, 0)
        ok = False
        try:
            if not bitmap or not bits.value:
                return False
            ctypes.memmove(bits, data, len(data))
            previous = g.SelectObject(memory_dc, bitmap)
            try:
                ok = bool(u.UpdateLayeredWindow(
                    self.hwnd, screen_dc, ctypes.byref(self.POINT(int(x), int(y))),
                    ctypes.byref(self.SIZE(width, height)), memory_dc,
                    ctypes.byref(self.POINT(0, 0)), 0, ctypes.byref(self._blend(alpha)),
                    self.ULW_ALPHA))
            finally:
                g.SelectObject(memory_dc, previous)
        finally:
            if bitmap:
                g.DeleteObject(bitmap)
            g.DeleteDC(memory_dc)
            u.ReleaseDC(None, screen_dc)
        return ok

    def set_alpha(self, alpha):
        """Opacidad general sin volver a subir la imagen (hdcSrc NULL = misma forma)."""
        if not self.hwnd:
            return False
        return bool(self._user32.UpdateLayeredWindow(
            self.hwnd, None, None, None, None, None, 0,
            self._ctypes.byref(self._blend(alpha)), self.ULW_ALPHA))


# --------------------------------------------------------------------------- #
# La ventana
# --------------------------------------------------------------------------- #


class FramelessWindow:
    """Toplevel sin marco que muestra una imagen RGBA con la forma recortada.

    Uso típico (aviso, menú): calcular el rect final, `grab_behind` ANTES de
    mostrar, dibujar el vidrio con esa foto y `show_image(rgba, x, y,
    behind=foto)`. Para animar, volver a llamar a `show_image` con la misma foto
    (o sin `behind`: se reutiliza la última que cubra el rect). Para la pestaña
    flotante, que se mueve: `edge_color_around` al mostrarla y al soltar el
    arrastre, y pasarle ese color como `behind`.

    `mode` se puede forzar con el argumento del mismo nombre o con la variable de
    entorno FOCUSFLOW_FRAMELESS=colorkey|plain (para capturas en X11: con
    "colorkey" se ve el magenta exacto que Windows vuelve transparente). El modo
    "layered" no se fuerza así: sólo se activa en Windows con FOCUSFLOW_LAYERED=1.
    """

    def __init__(self, root, *, topmost=True, toolwindow=False, mode=None):
        self.root = root
        self.topmost = bool(topmost)
        self._visible = False
        self._destroyed = False
        self._alpha = 1.0
        self._photo = None
        self._item = None
        self._rect = None           # (x, y, w, h) de lo último mostrado
        self._behind_cache = None   # ((x0, y0, x1, y1), imagen) de la última foto
        self._edge = None           # último color medido alrededor
        self._layered = None

        window = tk.Toplevel(root)
        window.withdraw()           # que no aparezca un cuadrado vacío al crearla
        window.overrideredirect(True)
        if _IS_WINDOWS and toolwindow:
            # Sin botón en la barra de tareas y sin heredar la minimización del
            # root. Va antes de lo demás: Tk recrea el marco al cambiarlo.
            try:
                window.attributes("-toolwindow", True)
            except tk.TclError:
                pass   # Tk sin el atributo: queda como ventana común
        if self.topmost:
            try:
                window.attributes("-topmost", True)
            except tk.TclError:
                pass   # sin "siempre encima"; igual se levanta con lift() al mostrar

        self.window = window
        self.mode = self._pick_mode(mode)
        bg = KEY if self.mode in ("colorkey", "layered") else _bg_base()
        window.configure(bg=bg)
        self.canvas = tk.Canvas(window, highlightthickness=0, bd=0, bg=bg, width=1, height=1)
        self.canvas.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Modo
    # ------------------------------------------------------------------ #

    def _pick_mode(self, requested):
        """layered (Windows + FOCUSFLOW_LAYERED=1) → colorkey (Windows) → plain.

        `requested` (o FOCUSFLOW_FRAMELESS) sólo acepta "colorkey" o "plain" y
        manda sobre lo automático; el alfa por píxel se pide únicamente con
        FOCUSFLOW_LAYERED=1.
        """
        if requested is None:
            requested = os.environ.get("FOCUSFLOW_FRAMELESS") or None
        if requested not in ("colorkey", "plain"):
            requested = None
        if requested == "plain":
            return "plain"
        if requested is None and layered_enabled():
            try:
                self._layered = _LayeredBackend(self.window)
                return "layered"
            except Exception:   # noqa: BLE001 — sin ctypes/Win32 utilizable: color clave
                self._report("no se pudo preparar la ventana con alfa por píxel")
                self._layered = None
        if self._apply_colorkey():
            return "colorkey"
        # Fuera de Windows no hay -transparentcolor: se simula sólo si lo piden
        # (capturas y pruebas: el magenta queda a la vista); si no, se aplana
        # contra lo de atrás.
        return "colorkey" if requested == "colorkey" else "plain"

    def _apply_colorkey(self):
        """-transparentcolor: sólo en Windows (en X11 Tk ni tiene el atributo)."""
        if not _IS_WINDOWS:
            return False
        try:
            self.window.attributes("-transparentcolor", KEY)
            return True
        except tk.TclError:
            return False

    def _fall_back_from_layered(self):
        """El modo layered falló: se vuelve a color clave sin perder la ventana."""
        self._report("UpdateLayeredWindow falló; la ventana vuelve a color clave")
        if self._layered is not None:
            self._layered.detach()
        self._layered = None
        self.mode = "colorkey" if self._apply_colorkey() else "plain"
        bg = KEY if self.mode == "colorkey" else _bg_base()
        try:
            self.window.configure(bg=bg)
            self.canvas.configure(bg=bg)
        except tk.TclError:
            pass   # ventana destruida en el medio

    _reported = set()

    @classmethod
    def _report(cls, message):
        """Avisa por stderr una sola vez por mensaje (no es un error de la app)."""
        if message in cls._reported:
            return
        cls._reported.add(message)
        import traceback

        print(f"[frameless] {message}", file=sys.stderr)
        if sys.exc_info()[0] is not None:
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    # Escala y estado
    # ------------------------------------------------------------------ #

    @property
    def scale(self):
        """Escala de ventana de customtkinter del root (DPI × factor del usuario)."""
        return _window_scale(self.root)

    @property
    def visible(self):
        if self._destroyed or not self._visible:
            return False
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    @property
    def rect(self):
        """(x, y, w, h) de lo último mostrado, o None."""
        return self._rect

    # ------------------------------------------------------------------ #
    # Lo de atrás
    # ------------------------------------------------------------------ #

    def grab_behind(self, x, y, w, h):
        """Foto de lo que hay en (x, y, w, h), tomada ANTES de mostrar la ventana.

        Con la ventana visible encima de ese rect no se puede fotografiar lo de
        atrás (saldría ella misma): se devuelve un recorte de la última foto si
        lo cubre, o None. La foto queda guardada para `show_image`.
        """
        x, y, w, h = int(x), int(y), int(w), int(h)
        bbox = (x, y, x + w, y + h)
        if self.visible and self._rect is not None:
            rx, ry, rw, rh = self._rect
            if _intersect(bbox, (rx, ry, rx + rw, ry + rh)) is not None:
                return self._cached_behind(x, y, w, h)
        image, _valid = _grab(bbox)
        if image is not None:
            self._behind_cache = (bbox, image)
        return image

    def _cached_behind(self, x, y, w, h):
        if self._behind_cache is None:
            return None
        (cx0, cy0, cx1, cy1), image = self._behind_cache
        if x >= cx0 and y >= cy0 and x + w <= cx1 and y + h <= cy1:
            return image.crop((x - cx0, y - cy0, x - cx0 + w, y - cy0 + h))
        return None

    def edge_color_around(self, x, y, w, h):
        """Color promedio del anillo de 2 px que rodea (x, y, w, h) por fuera.

        Lo que cae fuera de la pantalla no cuenta. Sin captura: EDGE_FALLBACK.
        """
        x, y, w, h = int(x), int(y), int(w), int(h)
        ring = _RING
        image, valid = _grab((x - ring, y - ring, x + w + ring, y + h + ring))
        if image is None:
            return EDGE_FALLBACK
        arr = np.asarray(image, np.float32)
        mask = np.zeros(arr.shape[:2], bool)
        vx0, vy0, vx1, vy1 = valid
        mask[vy0:vy1, vx0:vx1] = True
        mask[ring:ring + max(0, h), ring:ring + max(0, w)] = False
        if not mask.any():
            return EDGE_FALLBACK
        self._edge = R.rgb_to_hex(arr[mask].mean(axis=0))
        return self._edge

    def _resolve_behind(self, behind, x, y, w, h):
        if behind is not None:
            return behind
        cached = self._cached_behind(x, y, w, h)
        if cached is not None:
            return cached
        if self._edge is not None:
            return self._edge
        return EDGE_FALLBACK if self.mode == "colorkey" else _bg_base()

    # ------------------------------------------------------------------ #
    # Mostrar
    # ------------------------------------------------------------------ #

    def show_image(self, rgba, x, y, *, behind=None):
        """Muestra (o actualiza) la ventana con `rgba` arriba a la izquierda en (x, y).

        colorkey: el borde se compone contra `behind` (foto del mismo tamaño o
        color hex) y lo de α < 0,5 pasa a ser `KEY`. layered: `UpdateLayeredWindow`
        con BGRA premultiplicado. plain: se aplana todo contra `behind` (si no
        hay, `bg_base`). Sin `behind` se usa la última foto que cubra el rect, el
        último color de `edge_color_around` o el respaldo del modo.
        """
        if self._destroyed:
            return
        if rgba.mode != "RGBA":
            rgba = rgba.convert("RGBA")
        x, y = int(round(x)), int(round(y))
        width, height = rgba.size

        if self.mode == "layered":
            if self._show_layered(rgba, x, y):
                return
            self._fall_back_from_layered()

        under = self._resolve_behind(behind, x, y, width, height)
        key = KEY if self.mode == "colorkey" else None
        image = _compose(rgba, under, key=key)
        self._set_image(image)
        self._place(x, y, width, height)
        self._map()

    def _set_image(self, image):
        """Reutiliza el PhotoImage si el tamaño no cambió (paste es mucho más barato)."""
        photo = self._photo
        if photo is not None and (photo.width(), photo.height()) == image.size:
            photo.paste(image)
            return
        self._photo = ImageTk.PhotoImage(image, master=self.canvas)
        self.canvas.configure(width=image.width, height=image.height)
        if self._item is None:
            self._item = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        else:
            self.canvas.itemconfigure(self._item, image=self._photo)

    def _place(self, x, y, width, height):
        rect = (x, y, width, height)
        if rect == self._rect:
            return
        if self._rect is not None and self._rect[2:] == (width, height):
            self.window.geometry(f"+{x}+{y}")
        else:
            self.window.geometry(f"{width}x{height}+{x}+{y}")
        self._rect = rect

    def _map(self):
        if self._visible:
            return
        self._visible = True
        try:
            self.window.deiconify()
            self.window.lift()
            if self.topmost:
                self.window.attributes("-topmost", True)
        except tk.TclError:
            pass   # se destruyó mientras tanto

    def _show_layered(self, rgba, x, y):
        """Camino layered. False si hay que volver a color clave. A verificar en Windows."""
        width, height = rgba.size
        try:
            self.canvas.configure(width=width, height=height)
            if not self._visible:
                # Se mapea lejos de la pantalla: la primera vez para que Tk cree
                # el marco sin que se vea nada (recién ahí se lo marca layered) y
                # al volver de hide() para no mostrar un cuadro de la imagen vieja.
                self.window.geometry(f"{width}x{height}+-32000+-32000")
                self._rect = None
                self.window.deiconify()
                self.window.update_idletasks()
                self._layered.attach()
            if not self._layered.update(rgba, x, y, self._alpha):
                return False
            # Tk tiene que saber dónde quedó (eventos, winfo_x/y).
            self._place(x, y, width, height)
            if not self._visible:
                self._visible = True
                self.window.lift()
                if self.topmost:
                    self.window.attributes("-topmost", True)
            return True
        except Exception:   # noqa: BLE001 — cualquier falla de Win32 o Tk: color clave
            return False

    # ------------------------------------------------------------------ #
    # Resto de la API
    # ------------------------------------------------------------------ #

    def set_alpha(self, value):
        """Opacidad general 0..1 (-alpha; en layered, SourceConstantAlpha)."""
        self._alpha = max(0.0, min(1.0, float(value)))
        if self._destroyed:
            return
        if self.mode == "layered" and self._layered is not None:
            try:
                if self._layered.set_alpha(self._alpha):
                    return
            except Exception:   # noqa: BLE001 — a verificar en Windows; se ignora el fundido
                pass
            return   # nunca -alpha sobre una ventana layered: rompería UpdateLayeredWindow
        try:
            self.window.attributes("-alpha", self._alpha)
        except tk.TclError:
            pass   # Tk/gestor sin transparencia: el fundido no se ve, nada más

    def move(self, x, y):
        """Mueve la ventana sin volver a dibujarla (el arrastre de la pestaña)."""
        if self._destroyed or self._rect is None:
            return
        x, y = int(round(x)), int(round(y))
        _ox, _oy, width, height = self._rect
        try:
            self.window.geometry(f"+{x}+{y}")
        except tk.TclError:
            return
        self._rect = (x, y, width, height)

    def hide(self):
        if self._destroyed or not self._visible:
            return
        self._visible = False
        try:
            self.window.withdraw()
        except tk.TclError:
            pass   # ya no existe

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._visible = False
        if self._layered is not None:
            self._layered.detach()
            self._layered = None
        self._photo = None
        self._behind_cache = None
        try:
            self.window.destroy()
        except tk.TclError:
            pass   # el root ya se cerró y se la llevó

    def bind(self, sequence, func, add=None):
        """Bind sobre el lienzo (clics, movimiento, rueda)."""
        return self.canvas.bind(sequence, func, add)
