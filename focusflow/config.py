"""Rutas y preferencias persistentes.

Las preferencias viven en un JSON al lado del programa. Cada acceso pasa por
`Settings`, que valida el tipo y cae al valor por defecto si el archivo se
corrompió o viene de una versión anterior.
"""

from __future__ import annotations

import json
import os
import sys

APP_NAME = "Focus Flow"

#: Poniendo este archivo al lado del programa, los datos quedan ahí mismo en vez
#: de en el perfil del usuario. Es lo que hace que la versión portable sea
#: portable: se copia la carpeta entera a un pendrive y el historial va adentro.
PORTABLE_MARKER = "portable.txt"

#: Todo lo que el programa escribe. Lo demás (tipografías, sonidos) viaja adentro
#: del ejecutable. Si alguna vez hay que mudar los datos a mano, es esta lista.
DATA_FILES = ("focusflow.db", "settings.json", ".sesion-activa.json")


def frozen():
    """True si corremos dentro del ejecutable empaquetado."""
    return getattr(sys, "frozen", False)


def resource_dir():
    """Carpeta de los recursos de sólo lectura (tipografías, sonidos).

    Empaquetado con PyInstaller viven adentro del .exe, que los descomprime en
    una carpeta temporal apuntada por `sys._MEIPASS` y la borra al cerrar.
    """
    if frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable(folder):
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".escritura")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def program_dir():
    """Carpeta donde está el programa: el `.exe`, o el proyecto si corre del código."""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _profile_dir():
    return os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), APP_NAME)


def _resolve_data_dir():
    """Dónde guardar la base y los ajustes. Se decide una vez, al arrancar.

    Tres reglas, en orden, y el primer sí gana:

    1. Hay un `portable.txt` al lado del programa: los datos van ahí mismo. Es
       lo que lleva el .zip portable, para que la carpeta entera se pueda copiar
       a un pendrive con el historial adentro.
    2. Ya hay un `focusflow.db` al lado del programa: se sigue usando ése. Así
       quien viene de una versión anterior —que guardaba siempre al lado del
       ejecutable— no ve desaparecer su historial de un día para el otro.
    3. Si no, `%LOCALAPPDATA%\\Focus Flow`.

    La tercera es la que importa para quien recibe el programa por primera vez.
    Guardar al lado del ejecutable, que era lo que se hacía antes siempre, tiene
    dos agujeros: el historial se queda atrás si movés el programa de carpeta, y
    una instalación lo dejaría adentro de la carpeta de instalación, que es
    exactamente lo que se borra al desinstalar o al actualizar. El perfil del
    usuario sobrevive a las tres cosas.

    Ojo con la regla 2: es también lo que mantiene juntas la copia compilada y la
    que corre desde el código. El Python de la Microsoft Store redirige lo que se
    escribe en `%LOCALAPPDATA%` a un sandbox propio, así que si las dos cayeran
    en la regla 3 estarían escribiendo en carpetas distintas sin decirlo.
    """
    home = program_dir()
    if os.path.exists(os.path.join(home, PORTABLE_MARKER)) and _writable(home):
        return home
    if os.path.exists(os.path.join(home, DATA_FILES[0])) and _writable(home):
        return home

    profile = _profile_dir()
    if _writable(profile):
        return profile

    # Sin perfil donde escribir no queda mucho margen; al menos que arranque.
    return home


BASE_DIR = _resolve_data_dir()
ASSETS_DIR = os.path.join(resource_dir(), "assets")
DB_PATH = os.path.join(BASE_DIR, "focusflow.db")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
RECOVERY_PATH = os.path.join(BASE_DIR, ".sesion-activa.json")

APP_TAGLINE = "Medí tu concentración, no sólo tus horas"

DEFAULTS = {
    # --- objetivos ---
    "daily_goal_minutes": 180,
    # --- pomodoro ---
    "focus_minutes": 25,
    "break_minutes": 5,
    "tolerance_minutes": 2,
    "short_pause_minutes": 5,
    "auto_start_break": True,
    "auto_start_focus": False,
    # --- sonidos ---
    # El volumen y el silencio se guardan acá, así se configura una vez y queda
    # igual la próxima vez que se abre el programa.
    "sounds_enabled": True,
    "volume": 100,                 # 0..100
    "muted": False,
    "volume_before_mute": 70,      # para restaurar al des-silenciar
    # El control de volumen no tenía efecto real hasta ahora (MCI ignoraba el
    # comando), así que el valor guardado no refleja ninguna preferencia. Se
    # sube a 100 una única vez para que los sonidos no queden más bajos que antes.
    "volume_migrated": False,
    # --- vigilante de distracciones ---
    "watcher_enabled": False,
    "watcher_keywords": [
        "instagram", "tiktok", "youtube", "twitter", " / x", "facebook",
        "reddit", "twitch", "netflix", "whatsapp",
    ],
    "watcher_grace_seconds": 25,
    # --- interfaz ---
    "start_view": "Enfoque",
    "imported_legacy": False,
    # --- pestaña flotante ---
    "floating_tab": False,
    "floating_tab_minimized": False,
    "floating_tab_x": -1,          # -1 = todavía sin mover, va abajo a la derecha
    "floating_tab_y": -1,
    # --- accesibilidad ---
    # "auto" sigue a Windows; "on"/"off" mandan sobre el sistema.
    "a11y_reduce_motion": "auto",
    "a11y_reduce_transparency": "auto",
    "a11y_increase_contrast": "auto",
    "glass_tint": 50,              # 0 = ultra claro .. 100 = totalmente teñido
}

PRESETS = [
    {"name": "Pomodoro clásico", "focus": 25, "break": 5, "tolerance": 2,
     "hint": "El de siempre. Bueno para arrancar."},
    {"name": "Bloque largo", "focus": 50, "break": 10, "tolerance": 3,
     "hint": "Menos cortes, más profundidad."},
    {"name": "Ultradiano", "focus": 90, "break": 20, "tolerance": 5,
     "hint": "Ciclo natural de atención."},
    {"name": "Arranque suave", "focus": 15, "break": 5, "tolerance": 2,
     "hint": "Cuando cuesta empezar."},
    {"name": "Sin bloques", "focus": 0, "break": 0, "tolerance": 0,
     "hint": "El reloj corre libre hasta que lo pares."},
]


class Settings:
    """Diccionario de preferencias que se guarda solo al modificarse."""

    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                stored = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(stored, dict):
            return
        for key, value in stored.items():
            # Sólo aceptamos claves conocidas y del tipo esperado: así un archivo
            # viejo o tocado a mano no rompe la app.
            if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                self._data[key] = value
        self._migrate()

    def _migrate(self):
        """Ajustes que hay que corregir al pasar de una versión a otra."""
        if not self._data.get("volume_migrated"):
            self._data["volume"] = 100
            self._data["volume_before_mute"] = 100
            self._data["volume_migrated"] = True
            self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def __getitem__(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self._data[key] = value
        self.save()

    def get(self, key, default=None):
        return self._data.get(key, DEFAULTS.get(key, default))

    def update(self, **values):
        self._data.update(values)
        self.save()

    def stage(self, **values):
        """Cambia en memoria sin escribir a disco (deslizadores mientras se
        arrastran); el `save()` llega al soltar."""
        self._data.update(values)

    def as_dict(self):
        return dict(self._data)
