"""Ajustes de accesibilidad: lo que pide Windows y lo que elige el usuario.

Tres preferencias del sistema cambian cómo se ve y se mueve la app:

- Reducir movimiento: "Efectos de animación" apagado en Windows.
- Reducir transparencia: "Efectos de transparencia" apagado.
- Aumentar contraste: un tema de contraste de Windows activo.

Cada una tiene además un ajuste propio en Focus Flow ("auto" / "on" / "off",
que en la interfaz es Automático / Sí / No) que manda sobre el sistema; sirve
fuera de Windows y para quien lo quiera distinto. Se suma el regulador
"Transparencia del vidrio" (0–100), que no depende del sistema.

Este módulo sólo lee y avisa. Quién hace qué con cada cambio (el animador, el
tema, reconstruir la interfaz) lo decide la app al suscribirse.
"""

from __future__ import annotations

import os
import time
import tkinter

#: Lo que se asume si no se puede leer el sistema (o fuera de Windows): todo
#: encendido y sin contraste alto, que es como viene Windows de fábrica.
SAFE_SYSTEM = {"animations": True, "transparency": True, "high_contrast": False}

#: Como mucho una lectura del sistema cada tanto (s): el foco va y viene seguido.
REFRESH_INTERVAL = 2.0

SPI_GETHIGHCONTRAST = 0x0042
SPI_GETCLIENTAREAANIMATION = 0x1042
HCF_HIGHCONTRASTON = 0x0001
_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def _read_animations():
    import ctypes
    from ctypes import wintypes

    value = wintypes.BOOL(True)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
    if not ok:
        raise OSError("SPI_GETCLIENTAREAANIMATION")
    return bool(value.value)


def _read_transparency():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as key:
            return winreg.QueryValueEx(key, "EnableTransparency")[0] != 0
    except FileNotFoundError:
        # Sin el valor, Windows deja la transparencia encendida.
        return True


def _read_high_contrast():
    import ctypes
    from ctypes import wintypes

    class HIGHCONTRASTW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT),
                    ("dwFlags", wintypes.DWORD),
                    ("lpszDefaultScheme", wintypes.LPWSTR)]

    hc = HIGHCONTRASTW()
    hc.cbSize = ctypes.sizeof(HIGHCONTRASTW)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_GETHIGHCONTRAST, hc.cbSize, ctypes.byref(hc), 0)
    if not ok:
        raise OSError("SPI_GETHIGHCONTRAST")
    return bool(hc.dwFlags & HCF_HIGHCONTRASTON)


def read_windows_settings():
    """{"animations": bool, "transparency": bool, "high_contrast": bool}.

    Fuera de Windows o ante cualquier error: {"animations": True,
    "transparency": True, "high_contrast": False}. Cada valor se lee por
    separado, así que un error en uno no tira abajo los otros.
    """
    result = dict(SAFE_SYSTEM)
    if os.name != "nt":
        return result
    for key, reader in (("animations", _read_animations),
                        ("transparency", _read_transparency),
                        ("high_contrast", _read_high_contrast)):
        try:
            result[key] = reader()
        except (OSError, AttributeError, ImportError, ValueError, TypeError):
            pass  # valor seguro de SAFE_SYSTEM: la app arranca igual
    return result


def _choice(value):
    """Normaliza el ajuste propio a "auto" | "on" | "off"."""
    if value is True:
        return "on"
    if value is False:
        return "off"
    value = str(value or "auto").strip().lower()
    return value if value in ("on", "off") else "auto"


class Accessibility:
    """Estado efectivo de accesibilidad: el ajuste propio sobre el sistema.

    `refresh()` relee y devuelve qué cambió; los suscriptores reciben ese mismo
    conjunto. La app lo conecta así: reduce_motion -> animador; transparencia y
    tinte -> `theme.set_appearance` en vivo; contraste -> reconstruir la UI.
    """

    KEYS = ("a11y_reduce_motion", "a11y_reduce_transparency", "a11y_increase_contrast",
            "glass_tint")
    PROPERTIES = ("reduce_motion", "reduce_transparency", "increase_contrast", "glass_tint")

    def __init__(self, root, settings):
        self.root = root
        self.settings = settings
        self._subscribers = {}
        self._next_token = 1
        self._last_read = None
        self._bound = None
        self._pending = False
        self.system = dict(SAFE_SYSTEM)
        self.reduce_motion = False
        self.reduce_transparency = False
        self.increase_contrast = False
        self.glass_tint = 50
        self.refresh(force=True, notify=False)

    # -- lectura -------------------------------------------------------------

    def _setting(self, key, default):
        try:
            return self.settings.get(key, default)
        except (AttributeError, KeyError, TypeError):
            return default

    def _compute(self):
        system = self.system
        values = {}
        for prop, key, from_system in (
                ("reduce_motion", "a11y_reduce_motion", not system["animations"]),
                ("reduce_transparency", "a11y_reduce_transparency", not system["transparency"]),
                ("increase_contrast", "a11y_increase_contrast", system["high_contrast"])):
            choice = _choice(self._setting(key, "auto"))
            values[prop] = from_system if choice == "auto" else choice == "on"
        try:
            tint = int(round(float(self._setting("glass_tint", 50))))
        except (TypeError, ValueError):
            tint = 50
        values["glass_tint"] = max(0, min(100, tint))
        return values

    def refresh(self, force=False, notify=True):
        """Relee sistema (como mucho cada 2 s salvo `force`) y ajustes; devuelve
        el conjunto de propiedades que cambiaron ({"reduce_motion", ...}) y avisa
        a los suscriptores."""
        now = time.monotonic()
        if force or self._last_read is None or now - self._last_read >= REFRESH_INTERVAL:
            self.system = read_windows_settings()
            self._last_read = now
        values = self._compute()
        changed = {prop for prop in self.PROPERTIES if getattr(self, prop) != values[prop]}
        for prop, value in values.items():
            setattr(self, prop, value)
        if changed and notify:
            for callback in list(self._subscribers.values()):
                callback(set(changed))
        return changed

    def as_dict(self):
        return {prop: getattr(self, prop) for prop in self.PROPERTIES}

    def appearance(self):
        """Los argumentos de `theme.set_appearance(**...)` con el estado actual."""
        return {"reduce_transparency": self.reduce_transparency,
                "increase_contrast": self.increase_contrast,
                "glass_tint": self.glass_tint}

    # -- suscripciones -------------------------------------------------------

    def subscribe(self, callback):
        """callback(changed: set[str]); devuelve un token para `unsubscribe`."""
        token = self._next_token
        self._next_token += 1
        self._subscribers[token] = callback
        return token

    def unsubscribe(self, token):
        self._subscribers.pop(token, None)

    def bind_root(self):
        """<FocusIn> del root -> refresh() (la lectura del sistema va con freno de
        2 s). Al volver a la ventana se ve lo que se haya cambiado en Windows."""
        if self._bound is not None:
            return

        # <FocusIn> del root llega también por cada hijo que toma el foco (el
        # root está en sus bindtags): se junta todo en un solo refresh ocioso.
        def run():
            self._pending = False
            self.refresh()

        def on_focus(_event=None):
            if self._pending:
                return
            try:
                self.root.after_idle(run)
                self._pending = True
            except tkinter.TclError:
                pass  # root destruido: no hay nada que refrescar

        self._bound = self.root.bind("<FocusIn>", on_focus, add="+")
