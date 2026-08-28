#!/usr/bin/env python3
"""Genera y normaliza los sonidos de Focus Flow.

    pip install miniaudio
    python make_sounds.py

Todo lo que conviene tocar está en el bloque de AJUSTES de acá abajo: el volumen
de cada sonido por separado, cuánto dura cada nota y cuánto silencio va entre una
y otra.

Los avisos de la pausa corta y el de bienvenida se sintetizan. Los otros tres son
las grabaciones de `originales/`, que no se tocan: sólo se les ajusta el nivel.

Escribe en `assets/`, que es exactamente de donde la app lee los sonidos. Ojo:
el ejecutable lleva su propia copia adentro, así que después de regenerar hay que
recompilarlo para que los cambios lleguen ahí.
"""

import os
import wave

import numpy as np

try:
    import miniaudio
except ImportError:
    miniaudio = None

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")          # de acá lee la app
ORIGINALS = os.path.join(BASE, "originales")   # las grabaciones sin tocar
RATE = 44100


# =========================================================================== #
#                                  AJUSTES
# =========================================================================== #

#: Volumen de cada sonido, uno por uno. 1.0 es el nivel de referencia; 1.5 lo
#: sube a la mitad más, 0.6 lo baja. Si un valor pide más de lo que entra sin
#: distorsionar, se sube hasta el máximo posible y se avisa al generar.
VOLUMEN = {
    # Los tres sintetizados arrancan en 1.8: son campanas, tienen mucho pico y
    # poco cuerpo, así que a volumen 1.0 les sobraba margen sin usar.
    "bienvenida":       1.80,    # al abrir la app
    "pausacorta":       1.80,    # al entrar en pausa corta
    "vueltapausa":      1.80,    # al volver de la pausa corta
    "empiezadescanso":  1.00,    # arranca el descanso del pomodoro
    "findescanso":      1.00,    # se acabó el descanso
    "victoria":         1.00,    # volver a concentración
}

#: Cuánto dura cada nota, en milisegundos. Vale para las dos de la pausa corta y
#: para las tres de la bienvenida: todas duran lo mismo.
NOTA_MS = 380

#: Silencio entre el final de una nota y el comienzo de la siguiente, en
#: milisegundos. Con 0 la segunda arranca justo cuando termina la primera.
#: Ojo con subirlo: pasados un par de cientos de milisegundos las dos notas
#: dejan de escucharse como un aviso y pasan a ser dos avisos sueltos.
SILENCIO_MS = 90

#: Silencio al principio del archivo. Algunos reproductores se comen los primeros
#: milisegundos, y eso se llevaría el ataque de la primera nota.
ENTRADA_MS = 60

#: Nivel de referencia (RMS de la parte con señal). Todos apuntan acá, así que se
#: perciben parejos entre sí.
NIVEL = 0.6

#: Pico máximo permitido. Si para llegar al nivel hubiera que pasarse de acá, se
#: sube sólo hasta el techo: preferimos un sonido un poco más bajo antes que uno
#: aplastado. Comprimir para ganar volumen arruina los ataques, y sin ataques dos
#: notas se escuchan como una sola.
TECHO = 0.94

#: Las notas de cada aviso, de la primera a la última.
#: El intervalo importa: a una quinta justa el tercer armónico de una nota cae
#: casi encima del segundo de la otra y el oído las funde en un solo timbre. Una
#: séptima menor (razón 1,78) no comparte ninguno de los parciales que se
#: sintetizan.
SOL4, RE5, DO6, MI6 = 392.00, 587.33, 1046.50, 1318.51

NOTAS = {
    "pausacorta":  (DO6, RE5),          # bajan: "me ausento un momento"
    "vueltapausa": (RE5, DO6),          # suben: "ya volví"
    "bienvenida":  (SOL4, DO6, MI6),    # tres que suben, al abrir la app
}


# =========================================================================== #
# Síntesis
# =========================================================================== #


def bell(frecuencia, duracion, decay=4.5, parciales=(1.0, 0.40, 0.14)):
    """Una nota con timbre de campana: fundamental más dos armónicos.

    Se apaga del todo antes de terminar, para que el silencio entre notas sea
    silencio de verdad y no una cola montada encima de la siguiente.
    """
    largo = max(1, int(RATE * duracion))
    t = np.linspace(0.0, duracion, largo, endpoint=False)

    onda = np.zeros_like(t)
    for indice, amplitud in enumerate(parciales, start=1):
        onda += amplitud * np.sin(2 * np.pi * frecuencia * indice * t)

    envolvente = np.exp(-decay * t)
    # Ataque de 6 ms: sin esto el arranque brusco suena como un chasquido.
    ataque = min(int(RATE * 0.006), largo)
    envolvente[:ataque] *= np.linspace(0.0, 1.0, ataque)
    # Cierre: la nota tiene que llegar a cero antes de que entre la siguiente.
    cierre = min(int(RATE * 0.035), largo)
    envolvente[-cierre:] *= np.linspace(1.0, 0.0, cierre)
    return onda * envolvente


def secuencia(frecuencias, nota_ms=None, silencio_ms=None):
    """Encadena las notas: todas duran lo mismo y entre ellas va el silencio."""
    nota = (NOTA_MS if nota_ms is None else nota_ms) / 1000.0
    hueco = (SILENCIO_MS if silencio_ms is None else silencio_ms) / 1000.0
    paso = nota + hueco

    total = int(RATE * (paso * (len(frecuencias) - 1) + nota)) + 1
    salida = np.zeros(total, dtype=np.float64)
    for indice, frecuencia in enumerate(frecuencias):
        muestras = bell(frecuencia, nota)
        desde = int(RATE * paso * indice)
        salida[desde:desde + len(muestras)] += muestras
    return salida


# =========================================================================== #
# Nivel
# =========================================================================== #


def rms_activo(muestras):
    """RMS de la parte con señal, ignorando el silencio."""
    pico = np.max(np.abs(muestras))
    if pico <= 0:
        return 0.0
    activo = muestras[np.abs(muestras) > pico * 0.02]
    return float(np.sqrt(np.mean(activo ** 2))) if activo.size else 0.0


def ajustar_nivel(muestras, volumen):
    """Lleva el sonido al nivel buscado. Nunca comprime: sólo escala.

    Si el nivel pedido no entra por debajo del techo de pico, se sube hasta donde
    se puede. Antes acá había un limitador y fue un error: para ganar volumen
    aplastaba la envolvente, y con los ataques planchados las dos notas de un
    aviso se escuchaban como un solo bloque.
    """
    rms = rms_activo(muestras)
    pico = np.max(np.abs(muestras))
    if rms <= 0 or pico <= 0:
        return muestras, 1.0, False

    deseada = NIVEL * volumen / rms
    maxima = TECHO / pico
    return muestras * min(deseada, maxima), min(deseada, maxima), deseada > maxima


def guardar(nombre, muestras, canales=1):
    """Aplica el volumen del sonido, agrega el silencio de entrada y lo escribe."""
    clave = os.path.splitext(nombre)[0]
    volumen = VOLUMEN.get(clave, 1.0)
    muestras, ganancia, en_el_techo = ajustar_nivel(muestras, volumen)

    entrada = np.zeros(int(RATE * ENTRADA_MS / 1000.0) * canales)
    cola = np.zeros(int(RATE * 0.04) * canales)
    muestras = np.concatenate([entrada, muestras, cola])

    ruta = os.path.join(ASSETS, nombre)
    datos = (np.clip(muestras, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(ruta, "wb") as salida:
        salida.setnchannels(canales)
        salida.setsampwidth(2)
        salida.setframerate(RATE)
        salida.writeframes(datos.tobytes())

    aviso = "   <- llegó al techo, no se puede subir más" if en_el_techo else ""
    print(f"  {nombre:22s} vol x{volumen:.2f}  ganancia x{ganancia:6.2f}  "
          f"pico {np.max(np.abs(muestras)):.2f}  rms {rms_activo(muestras):.3f}  "
          f"{len(muestras) / canales / RATE:.2f}s{aviso}")


def convertir(origen, destino):
    """Trae una grabación original y le ajusta el nivel."""
    decodificado = miniaudio.decode_file(
        os.path.join(ORIGINALS, origen),
        output_format=miniaudio.SampleFormat.SIGNED16, sample_rate=RATE)
    muestras = np.array(decodificado.samples, dtype=np.float64) / 32768.0
    guardar(destino, muestras, canales=decodificado.nchannels)


# =========================================================================== #

if __name__ == "__main__":
    os.makedirs(ASSETS, exist_ok=True)
    print(f"nivel de referencia rms {NIVEL} · techo de pico {TECHO}")
    print(f"notas de {NOTA_MS} ms con {SILENCIO_MS} ms de silencio entre ellas\n")

    print("sintetizados:")
    for clave, frecuencias in NOTAS.items():
        guardar(f"{clave}.wav", secuencia(frecuencias))

    print("\ndesde las grabaciones originales:")
    if miniaudio is None:
        print("  falta miniaudio (pip install miniaudio)")
    else:
        for origen, destino in (("empiezadescanso.mp3", "empiezadescanso.wav"),
                                ("findescanso.mp3", "findescanso.wav"),
                                ("victoria.mp3", "victoria.wav")):
            if os.path.exists(os.path.join(ORIGINALS, origen)):
                convertir(origen, destino)
            else:
                print(f"  {origen}: no está en {ORIGINALS}")

    print(f"\nlisto, escritos en {ASSETS}")
    print("el ejecutable lleva su propia copia: para que los use, recompilalo con")
    print("    python ../build.py flow")
