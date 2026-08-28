"""Cosas que dependen del sistema operativo: sonido y ventana en primer plano.

Todo acá degrada con elegancia: si algo no está disponible, la función no hace
nada en vez de romper la aplicación.
"""

from __future__ import annotations

import array
import ctypes
import os
import shutil
import tempfile
import threading
import wave

from .config import ASSETS_DIR

try:
    import miniaudio
except ImportError:
    miniaudio = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import winsound
except ImportError:      # fuera de Windows
    winsound = None

# Todos los sonidos están normalizados al mismo nivel percibido y guardados como
# WAV. Antes convivían MP3 con volúmenes muy distintos: `victoria` sonaba casi
# nueve veces más bajo que `empiezadescanso`. Se regeneran con `make_sounds.py`.
SOUND_BREAK_START = "empiezadescanso.wav"
SOUND_BREAK_END = "findescanso.wav"
SOUND_FOCUS = "victoria.wav"
SOUND_SHORT_PAUSE = "pausacorta.wav"
SOUND_SHORT_PAUSE_END = "vueltapausa.wav"
SOUND_WELCOME = "bienvenida.wav"

ALL_SOUNDS = (SOUND_WELCOME, SOUND_SHORT_PAUSE, SOUND_SHORT_PAUSE_END,
              SOUND_BREAK_START, SOUND_BREAK_END, SOUND_FOCUS)

RATE = 44100         # a esta frecuencia están todos los avisos
CHANNELS = 2
SAMPLE_BYTES = 2
BUFFER_MS = 15       # latencia del dispositivo, de punta a punta


class SoundPlayer:
    """Mantiene el dispositivo de audio abierto y mezcla los avisos por software.

    Antes esto llamaba a `winsound.PlaySound` en cada aviso, y ahí estaba el
    problema. Medido en esta máquina: con el endpoint de audio dormido —que es
    como está siempre, porque Windows lo apaga a los pocos segundos de silencio—
    la reproducción tarda alrededor de 1,05 s en salir por los parlantes; con el
    dispositivo ya despierto, 0,10 s. Los avisos de Focus Flow van separados por
    minutos, así que *todos* pagaban el arranque en frío.

    Y no era sólo llegar tarde: mientras el endpoint termina de encender no sale
    nada, así que también se comía el principio. Por eso los dos tonos de la
    pausa corta se escuchaban como uno solo, tanto al entrar como al salir: el
    primero entraba entero dentro de ese arranque.

    Acá el dispositivo se abre una vez y queda abierto; cuando no hay nada que
    sonar la devolución de llamada escribe silencio. El endpoint nunca se
    duerme, así que el aviso sale entero, desde la primera muestra, con la
    latencia del buffer y nada más.

    De paso el volumen se aplica al mezclar: es exacto, se puede mover con un
    sonido ya sonando y no depende del mezclador de Windows. Y no quedan copias
    en disco, que era lo que hacía la versión anterior para poder escalarlo.

    Si `miniaudio` no está o el dispositivo no abre, se cae al camino viejo con
    `winsound`: llega tarde, pero suena.
    """

    def __init__(self, enabled=True, volume=70, muted=False):
        self.enabled = bool(enabled)
        self.volume = max(0, min(100, int(volume)))
        self.muted = bool(muted)

        self._lock = threading.Lock()
        self._voices = []        # sonando ahora: [muestras, posición, archivo]
        self._clips = {}         # archivo -> muestras int16 estéreo intercaladas
        self._silence = b""      # bloque mudo, que es el caso normal
        self._device = None

        self._folder = None      # de acá para abajo, sólo el camino de respaldo
        self._rendered = {}

        self._open_device()

    @property
    def audible(self):
        return self.enabled and not self.muted and self.volume > 0

    def configure(self, volume=None, muted=None, enabled=None):
        if volume is not None:
            self.volume = max(0, min(100, int(volume)))
        if muted is not None:
            self.muted = bool(muted)
        if enabled is not None:
            self.enabled = bool(enabled)
            # Con los avisos apagados no hay por qué tener el dispositivo
            # despierto; al volver a encenderlos se reabre.
            if self.enabled:
                self._open_device()
            else:
                self._close_device()

    # -- el dispositivo, que queda abierto ---------------------------------- #

    def _open_device(self):
        if self._device is not None or not self.enabled:
            return
        if miniaudio is None or np is None:
            return
        try:
            device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=CHANNELS, sample_rate=RATE,
                buffersize_msec=BUFFER_MS)
            # Sin placa de sonido miniaudio abre igual, contra un dispositivo
            # nulo que se traga todo. Antes que eso, preferimos el respaldo.
            if device.backend.lower().startswith("null"):
                device.close()
                return
            mixer = self._mixer()
            next(mixer)
            device.start(mixer)
        except Exception:
            return
        self._device = device
        # Descomprimir los seis avisos lleva unos milisegundos. Hacerlo ahora, y
        # no cuando toque sonar, es lo que mantiene el disparo instantáneo.
        threading.Thread(target=self._preload, daemon=True).start()

    def _close_device(self):
        device, self._device = self._device, None
        with self._lock:
            self._voices = []
        if device is not None:
            try:
                device.close()
            except Exception:
                pass

    # -- mezcla -------------------------------------------------------------- #

    def _mixer(self):
        """Devolución de llamada del dispositivo, en el hilo de audio.

        Corre cada `BUFFER_MS`. Si acá se escapa una excepción, miniaudio suelta
        el generador y el dispositivo queda mudo para siempre, así que ante
        cualquier problema se devuelve silencio y se sigue.
        """
        frames = yield b""
        while True:
            try:
                block = self._mix(frames)
            except Exception:
                block = bytes(frames * CHANNELS * SAMPLE_BYTES)
            frames = yield block

    def _mix(self, frames):
        needed = frames * CHANNELS
        with self._lock:
            if not self._voices:
                if len(self._silence) != needed * SAMPLE_BYTES:
                    self._silence = bytes(needed * SAMPLE_BYTES)
                return self._silence

            block = np.zeros(needed, dtype=np.float32)
            alive = []
            for voice in self._voices:
                samples, position, _ = voice
                chunk = samples[position:position + needed]
                block[:len(chunk)] += chunk
                voice[1] = position + len(chunk)
                if voice[1] < len(samples):
                    alive.append(voice)
            self._voices = alive
            gain = (self.volume / 100.0) if self.audible else 0.0

        block *= gain
        np.clip(block, -32768.0, 32767.0, out=block)
        return block.astype(np.int16).tobytes()

    def _clip(self, filename):
        """Muestras del aviso, en estéreo a 44,1 kHz. Se decodifica una sola vez."""
        cached = self._clips.get(filename, False)
        if cached is not False:
            return cached
        source = os.path.join(ASSETS_DIR, filename)
        samples = None
        if os.path.exists(source):
            try:
                decoded = miniaudio.decode_file(
                    source, output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=CHANNELS, sample_rate=RATE)
                samples = np.array(decoded.samples, dtype=np.int16)
            except Exception:
                samples = None
        # Asignar en un dict es atómico, así que la precarga desde su hilo y el
        # disparo desde la interfaz conviven sin candado: lo peor que puede
        # pasar es decodificar dos veces el mismo archivo.
        self._clips[filename] = samples
        return samples

    def _preload(self):
        for filename in ALL_SOUNDS:
            try:
                self._clip(filename)
            except Exception:
                pass

    # -- reproducción -------------------------------------------------------- #

    def play(self, filename, alias=None):
        """`alias` queda por compatibilidad con las llamadas; ya no se usa."""
        if not self.audible:
            return
        if self._device is None:
            self._play_fallback(filename)
            return
        samples = self._clip(filename)
        if samples is None or not len(samples):
            return
        with self._lock:
            # Si el mismo aviso ya venía sonando se reemplaza, para que un doble
            # disparo no lo deje corriendo dos veces contra sí mismo.
            self._voices = [v for v in self._voices if v[2] != filename]
            self._voices.append([samples, 0, filename])

    def stop_all(self):
        self._close_device()
        self._stop_fallback()

    # -- respaldo con winsound ----------------------------------------------- #
    # Sólo entra en juego si `miniaudio` no está o el dispositivo no abrió. Es el
    # camino que tenía antes la aplicación: llega tarde, pero suena.

    def _workspace(self):
        if self._folder is None or not os.path.isdir(self._folder):
            self._folder = tempfile.mkdtemp(prefix="focusflow-audio-")
        return self._folder

    def _render(self, filename):
        """Deja en disco una copia del sonido ya escalada al volumen actual."""
        source = os.path.join(ASSETS_DIR, filename)
        if not os.path.exists(source):
            return None
        target = os.path.join(self._workspace(), filename)
        gain = self.volume / 100.0
        try:
            with wave.open(source, "rb") as handle:
                params = handle.getparams()
                frames = handle.readframes(handle.getnframes())
            samples = array.array("h")
            samples.frombytes(frames)
            if gain < 0.999:
                for index, value in enumerate(samples):
                    samples[index] = int(value * gain)
            with wave.open(target, "wb") as out:
                out.setnchannels(params.nchannels)
                out.setsampwidth(params.sampwidth)
                out.setframerate(params.framerate)
                out.writeframes(samples.tobytes())
        except (OSError, wave.Error, EOFError):
            return None
        return target

    def _play_fallback(self, filename):
        if winsound is None:
            return
        cached = self._rendered.get(filename)
        if cached is None or cached[0] != self.volume:
            path = self._render(filename)
            if path is None:
                return
            self._rendered[filename] = (self.volume, path)
        else:
            path = cached[1]
        try:
            winsound.PlaySound(
                path, winsound.SND_FILENAME | winsound.SND_ASYNC
                | winsound.SND_NODEFAULT)
        except Exception:
            pass

    def _stop_fallback(self):
        if winsound is not None and self._rendered:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if self._folder and os.path.isdir(self._folder):
            shutil.rmtree(self._folder, ignore_errors=True)
        self._folder = None
        self._rendered.clear()


def foreground_window_title():
    """Título de la ventana que está adelante. Cadena vacía si no se puede leer."""
    if os.name != "nt":
        return ""
    try:
        user32 = ctypes.windll.user32
        handle = user32.GetForegroundWindow()
        if not handle:
            return ""
        length = user32.GetWindowTextLengthW(handle)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, length + 1)
        return buffer.value or ""
    except Exception:
        return ""


class DistractionWatcher:
    """Mira qué ventana está adelante y avisa si aparece algo de la lista.

    Es la idea de `ideas.txt`: "que registre si abro Instagram, tw o algo y me
    pregunte si quiero pausar el temporizador".

    No pausa nada por su cuenta: sólo avisa, y el corte lo decidís vos. Además
    espera unos segundos antes de molestar, porque pasar de largo por una
    pestaña no es distraerse.
    """

    def __init__(self, keywords=None, grace_seconds=25):
        self.keywords = [k.lower() for k in (keywords or []) if k.strip()]
        self.grace_seconds = max(3, int(grace_seconds))
        self.enabled = False
        self._current = None
        self._since = 0.0
        self._notified = set()

    def configure(self, keywords=None, grace_seconds=None, enabled=None):
        if keywords is not None:
            self.keywords = [k.lower() for k in keywords if k.strip()]
        if grace_seconds is not None:
            self.grace_seconds = max(3, int(grace_seconds))
        if enabled is not None:
            self.enabled = bool(enabled)
            if not enabled:
                self.reset()

    def reset(self):
        self._current = None
        self._since = 0.0
        self._notified.clear()

    def poll(self, monotonic_now):
        """Devuelve el nombre de la distracción cuando supera el margen, o None."""
        if not self.enabled or not self.keywords:
            return None

        title = foreground_window_title().lower()
        if not title or "focus flow" in title:
            self._current = None
            return None

        match = next((word for word in self.keywords if word in title), None)
        if match is None:
            self._current = None
            return None

        if match != self._current:
            self._current = match
            self._since = monotonic_now
            return None

        if monotonic_now - self._since >= self.grace_seconds and match not in self._notified:
            self._notified.add(match)
            return match
        return None

    def forgive(self, keyword=None):
        """Permite que vuelva a avisar por esa aplicación más adelante."""
        if keyword is None:
            self._notified.clear()
        else:
            self._notified.discard(keyword)
